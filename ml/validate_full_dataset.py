"""Independent, scalable validator for the completed FULL enhanced dataset (M3).

Re-verifies the on-disk artefacts *after* generation, from the files alone (it does
not trust the generator's in-process gates). Original vs generated records are routed
by the provenance ``record_origin`` column and validated under DIFFERENT rules:

  * generated rows  -> synthetic invariants (balance identity, per-type fraud rate,
                       scenario coverage, chain integrity, 2-decimal money).
  * original rows   -> verbatim-preservation only (counts, labels, schema); PaySim's
                       own balance inconsistencies are NOT treated as failures.

Transaction-identifier uniqueness uses a bounded-memory external hash-partition
(uid -> 16-byte blake2b digest bucketed across K files; duplicates detected per
bucket), so the 8.36M-id set is never held in RAM.

Read-only. Run from the repo root:
    $env:PYTHONPATH="ml/src"; python ml/validate_full_dataset.py [OUT_DIR]
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import tempfile

import pandas as pd

sys.path.insert(0, os.path.join("ml", "src"))

from data import origindata  # noqa: E402
from generator import config as gconfig  # noqa: E402
from generator import schema  # noqa: E402
from generator.emitter import DEBIT_TYPES  # noqa: E402
from generator.scenarios import ScenarioLibrary  # noqa: E402

CFG = gconfig.default_config()
TX = schema.ENHANCED_FEATURE_COLUMNS
PV = schema.PROVENANCE_COLUMNS
MONEY_RE = re.compile(r"^-?\d+\.\d{2}$")
TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")
CHUNK = 500_000
K_BUCKETS = 64


def sha256_of(path: str) -> str:
    d = hashlib.sha256()
    with open(path, "rb") as fh:
        for blk in iter(lambda: fh.read(1 << 20), b""):
            d.update(blk)
    return d.hexdigest().upper()


def scan_crlf(path: str, window: int = 1 << 20) -> dict:
    """Bounded carriage-return probe on the head and tail of a large file."""
    size = os.path.getsize(path)
    cr = 0
    with open(path, "rb") as fh:
        cr += fh.read(window).count(b"\r")
        if size > window:
            fh.seek(max(0, size - window))
            cr += fh.read(window).count(b"\r")
    return {"size_bytes": size, "cr_in_head_tail": cr}


def new_uid_partition():
    tmp = tempfile.TemporaryDirectory()
    files = [open(os.path.join(tmp.name, f"u{i}.bin"), "wb") for i in range(K_BUCKETS)]

    def add(uid: str):
        dig = hashlib.blake2b(uid.encode("utf-8"), digest_size=16).digest()
        files[dig[0] % K_BUCKETS].write(dig)

    def finish() -> int:
        for f in files:
            f.close()
        dups = 0
        for i in range(K_BUCKETS):
            seen = set()
            with open(files[i].name, "rb") as fh:
                buf = fh.read()
            for j in range(0, len(buf), 16):
                u = buf[j:j + 16]
                if u in seen:
                    dups += 1
                else:
                    seen.add(u)
        tmp.cleanup()
        return dups

    return add, finish


def validate(out_dir: str) -> dict:
    tx_path = os.path.join(out_dir, "enhanced_transactions.csv")
    pv_path = os.path.join(out_dir, "provenance.csv")
    man_path = os.path.join(out_dir, "manifest.json")

    report = {"out_dir": out_dir}
    with open(man_path, "r", encoding="utf-8") as fh:
        report["manifest"] = json.load(fh)

    # Original-vs-generated accumulators.
    gen = dict(rows=0, fraud=0, types={t: 0 for t in schema.TRANSACTION_TYPES},
               fraud_by_type={t: 0 for t in schema.TRANSACTION_TYPES},
               scenarios={}, bad_balance=0, neg_amount=0, neg_balance=0,
               bad_money=0, bad_ts=0, missing_scenario=0, mislabeled=0,
               prov_incomplete=0)
    orig = dict(rows=0, fraud=0, flagged=0,
                types={t: 0 for t in schema.TRANSACTION_TYPES})
    chains: dict = {}
    total_rows = 0
    uid_mismatch = 0
    add_uid, finish_uid = new_uid_partition()

    def money_ok(v):
        return bool(MONEY_RE.match(v))

    tx_chunks = pd.read_csv(tx_path, dtype=str, keep_default_na=False, chunksize=CHUNK)
    pv_chunks = pd.read_csv(pv_path, dtype=str, keep_default_na=False, chunksize=CHUNK)

    for ci, (tc, pc) in enumerate(zip(tx_chunks, pv_chunks)):
        if ci == 0:
            if list(tc.columns) != TX:
                raise SystemExit(f"transaction schema mismatch: {list(tc.columns)}")
            if list(pc.columns) != PV:
                raise SystemExit(f"provenance schema mismatch: {list(pc.columns)}")
        if len(tc) != len(pc):
            raise SystemExit("transaction/provenance chunk length mismatch (alignment)")
        total_rows += len(tc)

        # positional alignment proof: uids must match row-for-row
        tu = tc["record_uid"].to_numpy()
        pu = pc["record_uid"].to_numpy()
        uid_mismatch += int((tu != pu).sum())
        for u in tu:
            add_uid(str(u))

        # vectorised origin routing
        origin = pc["record_origin"].to_numpy()
        is_gen = origin == "generated"
        is_orig = origin == "original"
        if int((~(is_gen | is_orig)).sum()) != 0:
            raise SystemExit("unknown record_origin value encountered")

        # ---- ORIGINAL rows: preservation-only accounting ----
        oc_orig = tc.loc[is_orig]
        orig["rows"] += len(oc_orig)
        if len(oc_orig):
            orig["fraud"] += int((oc_orig["isFraud"] == "1").sum())
            orig["flagged"] += int((oc_orig["isFlaggedFraud"] == "1").sum())
            for t, v in oc_orig["type"].value_counts().items():
                orig["types"][t] = orig["types"].get(t, 0) + int(v)

        # ---- GENERATED rows: synthetic invariants ----
        gc = tc.loc[is_gen]
        if len(gc):
            gcp = pc.loc[is_gen]
            gen["rows"] += len(gc)
            fraud_flag = (gc["isFraud"].to_numpy() == "1")
            gen["fraud"] += int(fraud_flag.sum())
            types = gc["type"].to_numpy()
            amounts = gc["amount"].to_numpy()
            obs = gc["oldbalanceOrg"].to_numpy()
            nbs = gc["newbalanceOrig"].to_numpy()
            scen = gcp["scenario_id"].to_numpy()
            chid = gcp["chain_id"].to_numpy()
            ets = gc["event_ts"].to_numpy()

            for t, v in pd.Series(types).value_counts().items():
                gen["types"][t] = gen["types"].get(t, 0) + int(v)
            for k in range(len(gc)):
                tt = types[k]
                fr = fraud_flag[k]
                s = scen[k]
                gen["scenarios"][s] = gen["scenarios"].get(s, 0) + 1
                if not s:
                    gen["missing_scenario"] += 1
                if fr:
                    gen["fraud_by_type"][tt] = gen["fraud_by_type"].get(tt, 0) + 1

                a, ob, nb = amounts[k], obs[k], nbs[k]
                # serialization: money columns are 2-decimal, step integer, ts formatted
                if not (money_ok(a) and money_ok(ob) and money_ok(nb)):
                    gen["bad_money"] += 1
                    continue
                af, obf, nbf = float(a), float(ob), float(nb)
                if af < 0 or obf < 0 or nbf < 0:
                    gen["neg_balance"] += 1
                delta = af if tt == "CASH_IN" else -af
                if abs(obf + delta - nbf) > CFG.ledger_tolerance + 1e-6:
                    gen["bad_balance"] += 1
                if not TS_RE.match(ets[k]):
                    gen["bad_ts"] += 1
                # chain tracking
                c = chid[k]
                if c:
                    e = chains.get(c)
                    if e is None:
                        chains[c] = [1, int(fr)]
                    else:
                        e[0] += 1
                        if e[1] != int(fr):
                            e[1] = -1  # inconsistent

            # provenance non-empty checks (vectorised, per required col)
            for col in ("source_dataset", "record_origin", "generator_version",
                        "config_version", "generation_run_id", "dataset_version"):
                gen["prov_incomplete"] += int((gcp[col].to_numpy() == "").sum())

    dup_uids = finish_uid()

    # ---------- derived metrics ----------
    expected_rate = (sum(CFG.type_weights[t] * CFG.fraud_rate_by_type[t] for t in CFG.type_weights)
                     / sum(CFG.type_weights.values()))
    gen_rate = gen["fraud"] / gen["rows"] if gen["rows"] else 0.0
    per_type_ok = {t: abs(gen["fraud_by_type"].get(t, 0) - round(gen["types"][t] * CFG.fraud_rate_by_type[t])) <= 1
                   for t in schema.TRANSACTION_TYPES}
    all_scen = {s.scenario_id for s in ScenarioLibrary().scenarios}
    missing_scen = sorted(all_scen - set(gen["scenarios"]))
    below_floor = sorted([s for s, n in gen["scenarios"].items() if n < CFG.min_per_scenario_count])
    single_row_chains = sum(1 for e in chains.values() if e[0] < 2)
    mixed_chains = sum(1 for e in chains.values() if e[1] == -1)

    issues = []
    if orig["rows"] != origindata.EXPECTED_ROWS:
        issues.append(f"original rows {orig['rows']} != expected {origindata.EXPECTED_ROWS}")
    if orig["fraud"] != origindata.EXPECTED_FRAUD:
        issues.append(f"original fraud {orig['fraud']} != expected {origindata.EXPECTED_FRAUD}")
    if orig["flagged"] != origindata.EXPECTED_FLAGGED:
        issues.append(f"original flagged {orig['flagged']} != expected {origindata.EXPECTED_FLAGGED}")
    if total_rows != orig["rows"] + gen["rows"]:
        issues.append("total != original + generated")
    if uid_mismatch:
        issues.append(f"uid positional mismatch {uid_mismatch}")
    if dup_uids:
        issues.append(f"duplicate record_uid {dup_uids}")
    if gen["bad_balance"]:
        issues.append(f"generated balance identity violations {gen['bad_balance']}")
    if gen["neg_balance"]:
        issues.append(f"generated negative balances {gen['neg_balance']}")
    if gen["bad_money"]:
        issues.append(f"generated money-serialization violations {gen['bad_money']}")
    if gen["bad_ts"]:
        issues.append(f"generated event_ts format violations {gen['bad_ts']}")
    if gen["missing_scenario"] or gen["prov_incomplete"]:
        issues.append(f"provenance incompleteness scenario={gen['missing_scenario']} fields={gen['prov_incomplete']}")
    if missing_scen:
        issues.append(f"scenarios with no records {missing_scen}")
    if below_floor:
        issues.append(f"scenarios below floor {below_floor}")
    if single_row_chains or mixed_chains:
        issues.append(f"chain integrity single={single_row_chains} mixed={mixed_chains}")
    if not all(per_type_ok.values()):
        issues.append(f"per-type fraud rate mismatch {per_type_ok}")
    if abs(gen_rate - expected_rate) > 5e-4:
        issues.append(f"generated fraud rate {gen_rate:.5f} far from expected {expected_rate:.5f}")

    # source integrity re-check (read-only)
    fp = origindata.verify_integrity()
    files = {}
    for p in (tx_path, pv_path, man_path):
        meta = scan_crlf(p)
        files[os.path.basename(p)] = {"size_bytes": meta["size_bytes"],
                                      "sha256": sha256_of(p),
                                      "cr_in_head_tail": meta["cr_in_head_tail"]}
    parquet = [os.path.join(r, f) for r, _, fs in os.walk(out_dir) for f in fs if f.endswith(".parquet")]
    if parquet:
        issues.append(f"parquet files present: {parquet}")

    return {
        "combined_rows": total_rows,
        "expected_combined": origindata.EXPECTED_ROWS + CFG.generated_rows,
        "original": {**orig, "fraud_rate": round(orig["fraud"] / orig["rows"], 6) if orig["rows"] else 0},
        "generated": {**gen, "fraud_rate": round(gen_rate, 6),
                      "expected_fraud_rate": round(expected_rate, 6),
                      "per_type_rates_match_config": per_type_ok,
                      "scenarios_covered": len(gen["scenarios"]),
                      "scenarios_expected": len(all_scen)},
        "chains": {"count": len(chains), "single_row": single_row_chains, "mixed_label": mixed_chains},
        "uid": {"positional_mismatch": uid_mismatch, "duplicates": dup_uids,
                "method": f"external blake2b hash-partition (K={K_BUCKETS})"},
        "source_integrity": fp,
        "files": files,
        "parquet_found": parquet,
        "issues": issues,
        "passed": not issues,
    }


if __name__ == "__main__":
    out_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join("ml", "data", "processed", "enhanced_full")
    res = validate(out_dir)
    print(json.dumps(res, indent=2, sort_keys=True, default=str))
    sys.exit(0 if res["passed"] else 1)

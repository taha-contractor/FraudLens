"""TransactionEmitter (M3): deterministic synthetic transaction generation.

Produces legitimate and fraudulent transactions across all five PaySim types, using
repeated origin/destination accounts, linked chains and a consistent balance ledger.

Guarantees / conventions:
  * Deterministic: every random draw derives from (master_seed, labelled stream).
  * Balances are internally consistent: replayed chronologically, the ledger keeps
    ``newbalance = oldbalance ± amount`` and origin balances non-negative.
  * Amounts may be *capped* to the current origin balance for debit-type events
    (documented); "drain" fraud scenarios deliberately withdraw the full balance.
  * ``event_ts`` is a *synthetic reference clock* used only for intra-day ordering /
    velocity. It is NOT a claim about real transaction times, and the original
    PaySim ``step`` (day) semantics are preserved.

Generated labels are the generator's *synthetic scenario* outcomes and must never be
described as validated real-world fraud.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta

from . import rng
from .accounts import AccountRegistry, make_account_ids
from .chains import ChainBuilder
from .config import GeneratorConfig
from .scenarios import ScenarioLibrary

# Synthetic reference epoch for event_ts (arbitrary; ordering only, not real dates).
_EPOCH = datetime(2017, 1, 1)

# Per-type lognormal amount parameters (median, sigma). Configurable assumptions.
TYPE_PARAMS = {
    "PAYMENT": (300.0, 1.2),
    "CASH_IN": (500.0, 1.1),
    "CASH_OUT": (800.0, 1.1),
    "TRANSFER": (600.0, 1.2),
    "DEBIT": (120.0, 1.0),
}
FRAUD_MULTIPLIER = 2.5          # fraud scenarios skew larger amounts
DRAIN_SCENARIOS = {"COUT-F1", "TRF-F2"}   # withdraw (most of) the full balance

DEBIT_TYPES = {"PAYMENT", "CASH_OUT", "TRANSFER", "DEBIT"}
CREDIT_ORIGIN_TYPES = {"CASH_IN"}
CREDIT_DEST_TYPES = {"PAYMENT", "TRANSFER"}


def event_ts(step: int, sec: int) -> str:
    """Deterministic synthetic timestamp: EPOCH + (step-1) days + sec seconds."""
    return (_EPOCH + timedelta(days=int(step) - 1, seconds=int(sec))).strftime("%Y-%m-%d %H:%M:%S")


class TransactionEmitter:
    def __init__(self, config: GeneratorConfig, library: ScenarioLibrary | None = None):
        if not isinstance(config, GeneratorConfig):
            raise TypeError("config must be a GeneratorConfig")
        self.config = config.validate()
        self.library = (library or ScenarioLibrary()).validate()

    # ---- amount sampling --------------------------------------------------
    def _amount(self, g, scenario):
        median, sigma = TYPE_PARAMS[scenario.transaction_type]
        if scenario.scenario_id in DRAIN_SCENARIOS:
            return None  # resolved to full balance during ledger replay
        mu = median * (FRAUD_MULTIPLIER if scenario.is_fraud else 1.0)
        return round(float(g.lognormal(mean=float(rng.np.log(mu)), sigma=sigma)), 2)

    # ---- scenario count allocation ---------------------------------------
    def _allocate_counts(self, total, chain_counts):
        """Standalone rows per scenario so the *realised* per-type fraud rate
        matches ``config.fraud_rate_by_type`` and the overall rate matches
        ``sum(type_weights * fraud_rate_by_type)`` (≈3%).

        Each type's total row budget is taken over the WHOLE run (``total``),
        distributed exactly by largest remainder. A type's fraud budget
        ``round(type_total * rate)`` already *includes* the fraud rows that
        chains contribute, so chains are carved out of the standalone fraud
        allocation rather than added on top of it — this keeps the realised rate
        equal to the configured rate instead of diluting it. This is a coverage
        simulation choice, not a performance tune.
        """
        cfg = self.config
        lib = self.library
        counts: dict = {s.scenario_id: 0 for s in lib.scenarios}
        wsum = sum(cfg.type_weights.values())

        # 1. per-type total row budget over the full run (exact: largest remainder).
        raw = {t: total * cfg.type_weights[t] / wsum for t in cfg.type_weights}
        type_total = {t: int(raw[t]) for t in raw}
        remainder = total - sum(type_total.values())
        for t in sorted(raw, key=lambda t: (-(raw[t] - int(raw[t])), t))[:remainder]:
            type_total[t] += 1

        # 2. split each type into fraud / legit; chains count toward the fraud side.
        for t in sorted(cfg.type_weights):
            tt = type_total[t]
            fraud_scens = sorted(s.scenario_id for s in lib.for_type(t, fraud=True))
            legit_scens = sorted(s.scenario_id for s in lib.for_type(t, fraud=False))
            fraud_target = min(tt, int(round(tt * cfg.fraud_rate_by_type[t])))
            chain_in_fraud = sum(chain_counts.get(sid, 0) for sid in fraud_scens)
            standalone_fraud = max(0, fraud_target - chain_in_fraud)
            legit_target = tt - fraud_target
            for k, sid in enumerate(fraud_scens):
                counts[sid] += standalone_fraud // len(fraud_scens) + (1 if k < standalone_fraud % len(fraud_scens) else 0)
            for k, sid in enumerate(legit_scens):
                counts[sid] += legit_target // len(legit_scens) + (1 if k < legit_target % len(legit_scens) else 0)
        return counts

    def emit(self):
        """Return a list of generated transaction dicts (before provenance/formatting).

        Materialises the whole generated set in memory; intended for pilots, tests and
        small runs. The full-scale path is :meth:`emit_stream` (bounded memory), which
        yields a byte-identical sequence.
        """
        cfg = self.config
        seed = cfg.master_seed
        reg, origin_ids, merchant_ids, ext_ids = self._setup_accounts(cfg, seed)
        chain_rows, chain_counts = self._build_chains(cfg, seed, origin_ids, ext_ids)
        counts = self._allocate_counts(cfg.generated_rows, chain_counts)

        provisional = []
        for row in chain_rows:
            row["record_uid"] = self._uid(row["scenario_id"], row["idx"], row["chain_id"], seed)
            provisional.append(row)
        provisional.extend(
            self._iter_standalone(cfg, counts, origin_ids, merchant_ids, ext_ids, seed))

        provisional.sort(key=lambda r: (r["step"], r["sec"], r["record_uid"]))
        ledger, tracked = self._init_ledger(reg)
        tol = cfg.ledger_tolerance
        return [self._replay_one(r, ledger, tracked, tol) for r in provisional]

    def emit_stream(self, tmp_dir: str, bucket_span: int = 12):
        """Yield generated records with **bounded memory** via external step-bucketed replay.

        Phase A spills every provisional row (chains, then standalone) to a per-step-range
        JSONL file in ``tmp_dir``; Phase B reads one bucket at a time, sorts it by
        ``(step, sec, record_uid)`` and ledger-replays it, yielding final records. Peak
        resident memory is one bucket + the account ledger, **independent of**
        ``generated_rows`` — the full generated set is never held in RAM.

        Output is byte-identical to :meth:`emit` because ``step`` is the primary sort
        key and each bucket is a contiguous ascending step range, so concatenating
        sorted buckets reproduces the global ``(step, sec, record_uid)`` order; the
        ledger then evolves identically. ``tmp_dir`` must be managed (created/cleaned)
        by the caller and kept alive for the whole iteration.
        """
        cfg = self.config
        seed = cfg.master_seed
        reg, origin_ids, merchant_ids, ext_ids = self._setup_accounts(cfg, seed)
        chain_rows, chain_counts = self._build_chains(cfg, seed, origin_ids, ext_ids)
        counts = self._allocate_counts(cfg.generated_rows, chain_counts)

        step_lo = cfg.step_start
        nbuckets = (cfg.step_end - step_lo) // bucket_span + 1

        def bucket_path(b):
            return os.path.join(tmp_dir, f"prov_{b}.jsonl")

        handles: dict = {}

        def spill(prov):
            b = (int(prov["step"]) - step_lo) // bucket_span
            fh = handles.get(b)
            if fh is None:
                fh = handles[b] = open(bucket_path(b), "w", encoding="utf-8", newline="\n")
            fh.write(json.dumps(prov, separators=(",", ":")) + "\n")

        try:
            for row in chain_rows:
                row["record_uid"] = self._uid(row["scenario_id"], row["idx"], row["chain_id"], seed)
                spill(row)
            for prov in self._iter_standalone(cfg, counts, origin_ids, merchant_ids, ext_ids, seed):
                spill(prov)
        finally:
            for fh in handles.values():
                fh.close()
            handles.clear()

        ledger, tracked = self._init_ledger(reg)
        tol = cfg.ledger_tolerance
        for b in range(nbuckets):
            path = bucket_path(b)
            if not os.path.exists(path):
                continue
            with open(path, "r", encoding="utf-8") as fh:
                rows = [json.loads(line) for line in fh]
            rows.sort(key=lambda r: (r["step"], r["sec"], r["record_uid"]))
            for r in rows:
                yield self._replay_one(r, ledger, tracked, tol)
            rows.clear()
            os.remove(path)

    # ---- shared setup helpers --------------------------------------------
    def _setup_accounts(self, cfg, seed):
        reg = AccountRegistry(seed, cfg.n_origin_accounts, cfg.n_dest_accounts)
        origin_ids = reg.origin_ids()
        merchant_ids = reg.dest_ids()
        ext_ids = make_account_ids("C", max(1000, cfg.n_dest_accounts), seed, label="ext-dest")
        # Opening balances so debits do not immediately clamp to zero.
        ob = rng.make_rng("opening-balances", seed).lognormal(
            mean=float(rng.np.log(5000.0)), sigma=1.3, size=len(origin_ids))
        for oid, bal in zip(origin_ids, ob):
            reg.origins[oid].balance = round(float(bal), 2)
        return reg, origin_ids, merchant_ids, ext_ids

    def _build_chains(self, cfg, seed, origin_ids, ext_ids):
        # Chains sized so all-fraud chain rows stay ~1% of rows and fit inside each
        # type's fraud budget (see _allocate_counts) — realised rate still lands on config.
        n_chains = max(1, cfg.generated_rows // 200)
        chain_rows = ChainBuilder(seed).build(
            n_chains, origin_ids, ext_ids, seed, cfg.step_start, cfg.step_end)
        chain_counts: dict = {}
        for row in chain_rows:
            chain_counts[row["scenario_id"]] = chain_counts.get(row["scenario_id"], 0) + 1
        return chain_rows, chain_counts

    @staticmethod
    def _uid(scenario_id, idx, chain_id, seed):
        return rng.stable_id("g-", f"{scenario_id}:{idx}:x{chain_id or ''}", seed, width=16)

    def _iter_standalone(self, cfg, counts, origin_ids, merchant_ids, ext_ids, seed):
        for scenario in sorted(self.library.scenarios, key=lambda s: s.scenario_id):
            g = rng.make_rng(f"scenario:{scenario.scenario_id}", seed)
            for i in range(counts[scenario.scenario_id]):
                prov = self._make_standalone(g, scenario, i, origin_ids, merchant_ids, ext_ids, cfg)
                prov["record_uid"] = self._uid(prov["scenario_id"], prov["idx"], None, seed)
                yield prov

    def _make_standalone(self, g, scenario, i, origin_ids, merchant_ids, ext_ids, cfg):
        t = scenario.transaction_type
        origin = origin_ids[i % len(origin_ids)]
        if t in ("PAYMENT", "DEBIT"):
            dest = merchant_ids[i % len(merchant_ids)]
        elif t == "TRANSFER":
            dest = origin_ids[(i + 1) % len(origin_ids)]  # beneficiary (reused customer account)
        else:  # CASH_IN / CASH_OUT external counterparty
            dest = ext_ids[i % len(ext_ids)]
        step = int(g.integers(cfg.step_start, cfg.step_end + 1))
        sec = int(g.integers(0, 86400)) if cfg.substep_resolution == "second" else 0
        amt = self._amount(g, scenario)
        return {
            "idx": i, "step": step, "sec": sec, "type": t,
            "amount": amt, "nameOrig": origin, "nameDest": dest,
            "is_fraud": 1 if scenario.is_fraud else 0,
            "scenario_id": scenario.scenario_id, "chain_id": None,
            "drain": scenario.scenario_id in DRAIN_SCENARIOS,
        }

    def _init_ledger(self, reg):
        ledger = {aid: acc.balance for aid, acc in reg.origins.items()}
        ledger.update({aid: acc.balance for aid, acc in reg.destinations.items()})
        return ledger, set(ledger)

    def _replay_one(self, r, ledger, tracked, tol):
        """Advance the ledger by one chronologically-ordered provisional row and
        return the final generated record dict. Shared by :meth:`emit` and
        :meth:`emit_stream`, so both produce identical balances/values."""
        o, d = r["nameOrig"], r["nameDest"]
        old_o = ledger.get(o, 0.0)
        old_d = ledger.get(d, 0.0) if d in tracked else 0.0
        t = r["type"]
        if r["drain"]:
            amt = round(old_o, 2)  # full available balance
        elif t in DEBIT_TYPES:
            amt = round(min(r["amount"], old_o), 2)  # cap to keep balance non-negative
        else:  # CASH_IN
            amt = round(r["amount"], 2)
        amt = max(0.0, amt)

        if t in DEBIT_TYPES:
            new_o = round(old_o - amt, 2)
        else:
            new_o = round(old_o + amt, 2)
        if t in CREDIT_DEST_TYPES and d in tracked:
            new_d = round(old_d + amt, 2)
            ledger[d] = new_d
        else:
            new_d = old_d

        ledger[o] = new_o
        rec = {
            "record_uid": r["record_uid"], "step": r["step"], "event_ts": event_ts(r["step"], r["sec"]),
            "type": t, "amount": amt, "nameOrig": o,
            "oldbalanceOrg": old_o, "newbalanceOrig": new_o, "nameDest": d,
            "oldbalanceDest": old_d, "newbalanceDest": new_d,
            "is_fraud": r["is_fraud"], "scenario_id": r["scenario_id"], "chain_id": r.get("chain_id"),
        }
        # balance-identity sanity (defensive; also validated in dataset gates)
        if t in DEBIT_TYPES:
            assert abs(rec["oldbalanceOrg"] - rec["amount"] - rec["newbalanceOrig"]) <= tol + 1e-6, rec
        else:
            assert abs(rec["oldbalanceOrg"] + rec["amount"] - rec["newbalanceOrig"]) <= tol + 1e-6, rec
        return rec

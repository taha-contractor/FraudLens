"""Pilot pipeline (M3): deterministic CSV-only orchestration.

Wires the emitter + original loader + provenance into a reproducible, **CSV-only**
pilot dataset. Nothing here trains a model or produces the final
train/val/test splits; it only emits a small, validated enhanced dataset and its
provenance sidecar so the design can be reviewed before full-scale generation.

CSV-only guarantees (approved decision):
  * Transaction records, the enhanced dataset and provenance are written as CSV.
  * Manifest / generator configuration are written as JSON *metadata* (not datasets).
  * No Parquet is produced anywhere.
  * Writing is chunked; the full multi-million-row dataset is never buffered.
  * Column order, UTF-8 encoding, ``\\n`` newlines and monetary serialisation are
    fixed, so a given seed reproduces byte-for-byte output.

Loading efficiently (documented for reviewers)::

    import pandas as pd
    for chunk in pd.read_csv("enhanced_transactions.csv",
                             dtype=str, keep_default_na=False, chunksize=200_000):
        ...                                 # dtype=str keeps ids/labels verbatim

Original-derived rows keep their source text verbatim (no type coercion, preserved
``isFraud`` / ``isFlaggedFraud``); generated money is serialised with 2 decimals.
Generated rows carry ``isFlaggedFraud = 0`` — the investigation flag is never
fabricated, keeping it out of the predictive signal (approved decision 13).
"""

from __future__ import annotations

import csv
import itertools
import json
import os
import tempfile

from . import rng
from .config import GeneratorConfig, default_config
from .emitter import TransactionEmitter
from .provenance import make_record
from .schema import (ENHANCED_FEATURE_COLUMNS, PROVENANCE_COLUMNS,
                     TRANSACTION_TYPES)
from .stats import GenStats
from .validate import ValidationHarness

GENERATED = "fraudlens_generated"
ORIGINAL = "paysim_original"
_ORIG_UID_NAMESPACE = 0  # fixed namespace so original record_uids are stable across runs


def money(x) -> str:
    """Deterministic 2-decimal serialisation for generated monetary values."""
    return f"{float(x):.2f}"


def _generated_to_row(rec: dict) -> dict:
    return {
        "record_uid": rec["record_uid"],
        "step": int(rec["step"]),
        "event_ts": rec["event_ts"],
        "type": rec["type"],
        "amount": money(rec["amount"]),
        "nameOrig": rec["nameOrig"],
        "oldbalanceOrg": money(rec["oldbalanceOrg"]),
        "newbalanceOrig": money(rec["newbalanceOrig"]),
        "nameDest": rec["nameDest"],
        "oldbalanceDest": money(rec["oldbalanceDest"]),
        "newbalanceDest": money(rec["newbalanceDest"]),
        "isFraud": int(rec["is_fraud"]),
        "isFlaggedFraud": 0,  # never fabricated; keeps oracle flag out of features
    }


def _original_to_row(sample: dict) -> dict:
    """Map a verbatim source row into the enhanced schema (values kept as text)."""
    return {
        "record_uid": rng.stable_id("o-", str(sample["source_row_index"]), _ORIG_UID_NAMESPACE, width=16),
        "step": sample["step"],
        "event_ts": "",  # original PaySim has no sub-day timestamp; never fabricated
        "type": sample["type"],
        "amount": sample["amount"],
        "nameOrig": sample["nameOrig"],
        "oldbalanceOrg": sample["oldbalanceOrg"],
        "newbalanceOrig": sample["newbalanceOrig"],
        "nameDest": sample["nameDest"],
        "oldbalanceDest": sample["oldbalanceDest"],
        "newbalanceDest": sample["newbalanceDest"],
        "isFraud": sample["isFraud"],                # preserved exactly
        "isFlaggedFraud": sample["isFlaggedFraud"],  # preserved exactly
    }


def write_csv_stream(path: str, columns: list, rows_iter, chunksize: int = 5000) -> int:
    """Stream an *iterator* of row dicts to CSV, buffering at most ``chunksize``
    rows. Writes to a temp file then publishes atomically. Used by the full-scale
    path so the multi-million-row dataset is never materialised in memory."""
    tmp = path + ".tmp"
    written = 0
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, lineterminator="\n", extrasaction="raise")
        writer.writeheader()
        for row in rows_iter:
            writer.writerow(row)
            written += 1
    os.replace(tmp, path)
    return written


def _write_csv_chunked(path: str, columns: list, rows: list, chunksize: int = 5000) -> int:
    """Write a materialised list of row dicts to CSV (pilot / test convenience).

    Thin wrapper over :func:`write_csv_stream`; kept so callers and tests that
    hold a small list can write it directly.
    """
    return write_csv_stream(path, columns, iter(rows), chunksize=chunksize)


def _write_pairs_to_temp(tx_tmp: str, pv_tmp: str, pairs_iter) -> int:
    """Write transactions + provenance to temp paths in ONE pass over an iterator of
    ``(tx_row, provenance_row)`` pairs, buffering at most one row. Does NOT publish:
    the caller promotes the temp files only after the dataset gates pass."""
    written = 0
    with open(tx_tmp, "w", encoding="utf-8", newline="") as ftx, \
         open(pv_tmp, "w", encoding="utf-8", newline="") as fpv:
        wtx = csv.DictWriter(ftx, fieldnames=ENHANCED_FEATURE_COLUMNS, lineterminator="\n", extrasaction="raise")
        wpv = csv.DictWriter(fpv, fieldnames=PROVENANCE_COLUMNS, lineterminator="\n", extrasaction="raise")
        wtx.writeheader()
        wpv.writeheader()
        for tx_row, pv_row in pairs_iter:
            wtx.writerow(tx_row)
            wpv.writerow(pv_row)
            written += 1
    return written


def _publish(tx_tmp: str, tx_path: str, pv_tmp: str, pv_path: str) -> None:
    """Atomically promote both temp CSVs to their final names."""
    os.replace(tx_tmp, tx_path)
    os.replace(pv_tmp, pv_path)


def iter_enhanced_csv(path: str, chunksize: int = 200_000):
    """Efficient chunked reader for the enhanced CSV (dtype-preserving, read-only).

    Yields pandas DataFrames with every column read as a raw string, so ids and
    labels are never silently coerced. Callers convert only the columns they need.
    """
    import pandas as pd
    return pd.read_csv(path, dtype=str, keep_default_na=False, chunksize=chunksize)


def _resolve_config(config, *, n_generated=None, pilot=False):
    cfg = (config or default_config())
    cfg.validate()
    if pilot and config is None and n_generated is not None:
        d = cfg.to_dict()
        d["generated_rows"] = int(n_generated)
        # Small pilots: fraud scenarios are inherently rare, so scale the
        # per-scenario coverage floor down or it would falsely fail the gate.
        d["min_per_scenario_count"] = max(1, int(n_generated * 0.001))
        cfg = GeneratorConfig.from_dict(d)
    return cfg


def generate_enhanced_dataset(out_dir: str, config: GeneratorConfig, *,
                              include_original: str = "all",
                              n_original_sample: int = 2000,
                              source_path: str | None = None,
                              bucket_span: int = 12) -> dict:
    """Stream a full enhanced dataset (CSV only) with **bounded memory**.

    ``include_original='all'`` streams every one of the 6,362,620 source records
    verbatim via :func:`origindata.iter_source_records`; ``'sample'`` pulls a small
    evenly-spaced subset (pilot). Generated records come from
    :meth:`TransactionEmitter.emit_stream` (external step-bucketed replay, no full
    materialisation). Generated + original rows are written to temp CSVs in a single
    streaming pass; the §10 gates are evaluated over a single-pass :class:`GenStats`
    accumulator and only publish if every gate passes. Raises ``RuntimeError`` on any
    gate failure (partial temp files are discarded, nothing is published).
    """
    from data import origindata  # local import; requires ml/src on sys.path

    cfg = config.validate()
    if include_original not in ("all", "sample"):
        raise ValueError("include_original must be 'all' or 'sample'")
    run_id = cfg.generation_run_id()

    # 1. confirm the read-only source is untouched before reading it
    fingerprint = origindata.verify_integrity(source_path or origindata.RAW_PATH)

    stats = GenStats(tol=cfg.ledger_tolerance, track_uids=False)
    harness = ValidationHarness(cfg)
    orig_counter = {"rows": 0, "fraud": 0, "flagged": 0, "types": {}}

    def gen_pairs(gen_stream):
        for r in gen_stream:
            stats.add(r)  # single-pass gate/summary accumulator over generated rows
            tx = _generated_to_row(r)
            pv = make_record(tx["record_uid"], GENERATED, "generated",
                             generator_version=cfg.generator_version, config_version=cfg.config_version,
                             generation_run_id=run_id, dataset_version=cfg.dataset_version,
                             scenario_id=r["scenario_id"], chain_id=r["chain_id"] or None)
            yield tx, pv

    def orig_pairs(src_iter):
        for s in src_iter:
            tx = _original_to_row(s)
            pv = make_record(tx["record_uid"], ORIGINAL, "original",
                             generator_version=cfg.generator_version, config_version=cfg.config_version,
                             generation_run_id=run_id, dataset_version=cfg.dataset_version,
                             scenario_id=None, chain_id=None)
            orig_counter["rows"] += 1
            orig_counter["fraud"] += (s["isFraud"] == "1")
            orig_counter["flagged"] += (s["isFlaggedFraud"] == "1")
            t = s["type"]
            orig_counter["types"][t] = orig_counter["types"].get(t, 0) + 1
            yield tx, pv

    if include_original == "all":
        src_iter = origindata.iter_source_records(source_path or origindata.RAW_PATH)
    else:
        src_iter = iter(origindata.load_original_sample(source_path or origindata.RAW_PATH,
                                                        n=n_original_sample))

    os.makedirs(out_dir, exist_ok=True)
    tx_path = os.path.join(out_dir, "enhanced_transactions.csv")
    pv_path = os.path.join(out_dir, "provenance.csv")
    tx_tmp, pv_tmp = tx_path + ".tmp", pv_path + ".tmp"

    # 2. stream generated (emit_stream spills to this temp working dir) + originals
    with tempfile.TemporaryDirectory() as work:
        gen_stream = TransactionEmitter(cfg).emit_stream(work, bucket_span=bucket_span)
        pairs = itertools.chain(gen_pairs(gen_stream), orig_pairs(src_iter))
        n_written = _write_pairs_to_temp(tx_tmp, pv_tmp, pairs)

    # 3. §10 gates over the generated rows (originals validated on the source side)
    issues = harness.evaluate(stats)
    if issues:
        for p in (tx_tmp, pv_tmp):
            if os.path.exists(p):
                os.remove(p)
        raise RuntimeError("dataset gates failed: " + "; ".join(issues))

    # 4. publish atomically only after every gate passed
    _publish(tx_tmp, tx_path, pv_tmp, pv_path)

    summary = _build_summary(cfg, run_id, stats, orig_counter, fingerprint,
                             tx_path, pv_path, n_written, include_original)
    manifest_path = os.path.join(out_dir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, sort_keys=True)
    summary["manifest_path"] = manifest_path
    summary["output_files"] = {
        "transactions": tx_path, "provenance": pv_path, "manifest": manifest_path,
    }
    return summary


def generate_pilot(out_dir: str, config: GeneratorConfig | None = None,
                   *, n_generated: int = 20_000, n_original: int = 2000,
                   source_path: str | None = None) -> dict:
    """Generate a small, validated pilot enhanced dataset (CSV only, sampled source).

    Writes ``enhanced_transactions.csv``, ``provenance.csv`` and ``manifest.json``
    under ``out_dir`` and returns a summary dict. Uses the sampled original path
    (``include_original='sample'``); the full-source engine is
    :func:`generate_enhanced_dataset`.
    """
    cfg = _resolve_config(config, n_generated=n_generated, pilot=True)
    return generate_enhanced_dataset(out_dir, cfg, include_original="sample",
                                     n_original_sample=n_original, source_path=source_path)


def _dist(rows, key):
    out = {}
    for r in rows:
        out[r[key]] = out.get(r[key], 0) + 1
    return dict(sorted(out.items()))


def _build_summary(cfg, run_id, stats, orig_counter, fingerprint,
                   tx_path, pv_path, n_written, include_original) -> dict:
    total_gen = stats.total
    fraud_gen = stats.fraud
    fraud_by_type = {t: stats.fraud_by_type.get(t, 0) for t in TRANSACTION_TYPES}
    type_counts = {t: stats.type_counts.get(t, 0) for t in TRANSACTION_TYPES}
    chain_fraud = stats.chain_rows
    return {
        "generation_run_id": run_id,
        "config_version": cfg.config_version,
        "generator_version": cfg.generator_version,
        "dataset_version": cfg.dataset_version,
        "output_format": cfg.output_format,
        "master_seed": cfg.master_seed,
        "include_original": include_original,
        "source_fingerprint": fingerprint,
        "counts": {
            "generated_rows": total_gen,
            "generated_fraud": fraud_gen,
            "generated_fraud_rate": round(fraud_gen / total_gen, 5) if total_gen else 0.0,
            "generated_chain_fraud": chain_fraud,
            "original_rows": orig_counter["rows"],
            "original_fraud": orig_counter["fraud"],
            "original_flagged": orig_counter["flagged"],
            "transactions_written": n_written,
            "provenance_written": n_written,
        },
        "expected_fraud_rate": round(sum(cfg.type_weights[t] * cfg.fraud_rate_by_type[t]
                                         for t in cfg.type_weights) /
                                     sum(cfg.type_weights.values()), 5),
        "generated_type_counts": dict(sorted(type_counts.items())),
        "generated_fraud_by_type": dict(sorted(fraud_by_type.items())),
        "generated_scenario_counts": dict(sorted(stats.scenario_counts.items())),
        "original_type_counts": dict(sorted(orig_counter["types"].items())),
        "files": {"transactions": tx_path, "provenance": pv_path},
    }

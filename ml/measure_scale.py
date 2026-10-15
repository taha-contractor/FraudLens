"""Scale-readiness measurement for the bounded-memory generator (M3).

Isolates the *generated* path (the originals are already streamed by the pipeline),
spills/replays via ``emit_stream`` and writes CSV, while measuring peak Python-heap
memory and timings. Run from the repo root:

    $env:PYTHONPATH="ml/src"; python ml/measure_scale.py [ROWS]

No full dataset is persisted: all outputs go to a temp dir that is removed. Models
are not trained and no splits are created. Numbers are MEASURED for the exact workload
passed (no extrapolation).
"""
from __future__ import annotations

import csv
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.join("ml", "src"))

from generator import config as gconfig          # noqa: E402
from generator import pipeline                    # noqa: E402
from generator.emitter import TransactionEmitter  # noqa: E402
from generator.schema import ENHANCED_FEATURE_COLUMNS  # noqa: E402
from generator.stats import GenStats              # noqa: E402


def peak_rss_mb():
    """Peak working set (MB) via the OS, with NO interpreter slowdown.

    Windows: psapi GetProcessMemoryInfo (PeakWorkingSetSize). Posix fallback:
    ru_maxrss. Returns None if unavailable.
    """
    try:
        import ctypes
        if sys.platform.startswith("win"):
            import ctypes.wintypes as wt

            class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
                _fields_ = [
                    ("cb", wt.DWORD), ("PageFaultCount", wt.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
                ]
            pmc = PROCESS_MEMORY_COUNTERS()
            pmc.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
            handle = wt.HANDLE(ctypes.windll.kernel32.GetCurrentProcess()).value
            for libname in ("kernel32", "psapi", "K32"):
                try:
                    fn = getattr(ctypes.windll, libname).GetProcessMemoryInfo
                except AttributeError:
                    continue
                fn.argtypes = [wt.HANDLE, ctypes.POINTER(PROCESS_MEMORY_COUNTERS), wt.DWORD]
                fn.restype = wt.BOOL
                if fn(handle, ctypes.byref(pmc), pmc.cb):
                    return round(pmc.PeakWorkingSetSize / 1e6, 1)
            return None
        import resource
        return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6, 1)
    except Exception:
        return None


def run(rows: int):
    d = dict(gconfig.DEFAULT_CONFIG)
    d["generated_rows"] = rows
    d["min_per_scenario_count"] = max(1, int(rows * 0.0001))
    cfg = gconfig.GeneratorConfig.from_dict(d)

    result = {"rows_target": rows, "master_seed": cfg.master_seed, "bucket_span": 12}

    # (A) stream + discard (NO instrumentation): generation + external-sort replay
    #     throughput and the single-pass fraud/coverage/balance/chain accounting.
    t0 = time.perf_counter()
    stats = GenStats(tol=cfg.ledger_tolerance, track_uids=False)
    with tempfile.TemporaryDirectory() as work:
        n_a = 0
        for r in TransactionEmitter(cfg).emit_stream(work, bucket_span=12):
            stats.add(r)
            n_a += 1
        gen_secs = time.perf_counter() - t0

    result["gen_stream_rows"] = n_a
    result["gen_stream_secs"] = round(gen_secs, 3)
    result["gen_rows_per_sec"] = round(n_a / gen_secs, 1)

    # fraud accuracy + coverage from the single-pass accumulator (no full list).
    fraud_by_type = {t: stats.fraud_by_type.get(t, 0) for t in stats.type_counts}
    per_type = {t: stats.type_counts[t] for t in stats.type_counts}
    realised_rate = stats.fraud / stats.total if stats.total else 0.0
    expected = sum(cfg.type_weights[t] * cfg.fraud_rate_by_type[t] for t in cfg.type_weights) / sum(cfg.type_weights.values())
    per_type_ok = all(
        abs(fraud_by_type[t] - round(per_type[t] * cfg.fraud_rate_by_type[t])) <= 1
        for t in per_type
    )
    result["realised_fraud_rate"] = round(realised_rate, 6)
    result["expected_fraud_rate"] = round(expected, 6)
    result["per_type_rates_match_config"] = per_type_ok
    result["scenarios_total"] = len(cfg.fraud_rate_by_type) and len(stats.scenario_counts)
    result["balance_violations"] = stats.bad_balance
    result["chain_rows"] = stats.chain_rows
    result["chains"] = len(stats.chains)
    result["mixed_label_chains"] = sum(1 for e in stats.chains.values() if not e[2])
    result["single_row_chains"] = sum(1 for e in stats.chains.values() if e[0] < 2)

    # (B) stream + write CSV (identical deterministic run): the added write cost is
    #     B - A, both measured WITHOUT instrumentation.
    with tempfile.TemporaryDirectory() as out, tempfile.TemporaryDirectory() as work:
        tx_path = os.path.join(out, "t.csv")
        t1 = time.perf_counter()
        written = 0
        with open(tx_path, "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=ENHANCED_FEATURE_COLUMNS, lineterminator="\n")
            w.writeheader()
            for r in TransactionEmitter(cfg).emit_stream(work, bucket_span=12):
                w.writerow(pipeline._generated_to_row(r))
                written += 1
        write_secs = time.perf_counter() - t1
        size = os.path.getsize(tx_path)
        import hashlib
        digest = hashlib.sha256(open(tx_path, "rb").read()).hexdigest()

    result["csv_rows"] = written
    result["csv_bytes"] = size
    result["csv_total_secs"] = round(write_secs, 3)
    result["combined_rows_per_sec"] = round(written / write_secs, 1)
    csv_overhead = max(0.0, write_secs - gen_secs)
    result["csv_write_overhead_secs"] = round(csv_overhead, 3)
    if csv_overhead > 0:
        result["csv_write_rows_per_sec"] = round(written / csv_overhead, 1)
        result["csv_write_mb_per_sec"] = round(size / 1e6 / csv_overhead, 1)
    result["peak_rss_mb"] = peak_rss_mb()
    result["csv_sha256"] = digest
    return result


if __name__ == "__main__":
    rows = int(sys.argv[1]) if len(sys.argv) > 1 else 2_000_000
    import json
    print(json.dumps(run(rows), indent=2, sort_keys=True))

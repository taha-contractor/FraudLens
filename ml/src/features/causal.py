"""Causal, bounded-memory history features (M4).

Every history feature is computed from records that are STRICTLY EARLIER than the
current one under a deterministic causal key ``(step, ts_seconds, record_uid)``.
No current-row label, no post-execution balance and no future record can influence
a row's features, so recomputing on any chronological prefix reproduces identical
values for the surviving rows (this "prefix stability" is the leakage proof used in
the tests).

Full-scale reads use an external step-partitioned sort so peak memory is one day's
rows plus the per-account accumulators (O(accounts), not O(rows)).
"""

from __future__ import annotations

import csv
import json
import os
from collections import Counter, deque
from datetime import datetime

from .policies import HISTORY_FEATURES

DAY_SECONDS = 86400
_FMT = "%Y-%m-%d %H:%M:%S"


def causal_seconds(row: dict) -> int:
    """Seconds-since-epoch causal clock. Generated rows carry ``event_ts``;
    originals have none, so they fall back to their ``step`` day boundary."""
    ts = row.get("event_ts") or ""
    if ts:
        return int(datetime.strptime(ts, _FMT).timestamp())
    return int(row["step"]) * DAY_SECONDS


def causal_key(row: dict):
    return (int(row["step"]), causal_seconds(row), row["record_uid"])


# rows kept from the source for causal processing (values are raw strings)
_KEEP = ["record_uid", "step", "event_ts", "type", "amount", "nameOrig", "nameDest"]


def iter_time_sorted(tx_path: str, work_dir: str, chunksize: int = 200_000,
                     step_max: int = 743):
    """Yield source rows in causal order using an external step-partition sort.

    Phase A buckets each row by ``step`` into a JSONL file; Phase B reads one step
    at a time, sorts within the step by ``(ts_seconds, record_uid)`` and yields.
    Because ``step`` is the primary causal key and steps are processed ascending,
    the concatenation is globally causal-ordered — identical to a full sort.
    """
    buckets: dict = {}

    def spill(row):
        s = int(row["step"])
        fh = buckets.get(s)
        if fh is None:
            p = os.path.join(work_dir, f"step_{s:05d}.jsonl")
            fh = buckets[s] = open(p, "w", encoding="utf-8", newline="\n")
        fh.write(json.dumps({k: row.get(k, "") for k in _KEEP}, separators=(",", ":")) + "\n")

    try:
        with open(tx_path, "r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                spill({k: row.get(k, "") for k in _KEEP})
    finally:
        for fh in buckets.values():
            fh.close()
        buckets.clear()

    for s in range(1, step_max + 1):
        p = os.path.join(work_dir, f"step_{s:05d}.jsonl")
        if not os.path.exists(p):
            continue
        with open(p, "r", encoding="utf-8") as fh:
            rows = [json.loads(line) for line in fh]
        rows.sort(key=lambda r: (causal_seconds(r), r["record_uid"]))
        for r in rows:
            yield r
        rows.clear()
        os.remove(p)


class CausalFeatureBuilder:
    """Streaming accumulator of strictly-prior account history.

    ``add`` returns the history features for the incoming row computed from state
    BEFORE the row is applied, then folds the row into the per-account state. The
    caller must feed rows in causal order (see :func:`iter_time_sorted`).
    """

    __slots__ = ("origins", "dests")

    def __init__(self):
        self.origins: dict = {}   # aid -> [n, sum_amt, last_ts, deque((ts,amt,dest)), Counter(dest)]
        self.dests: dict = {}     # did -> [n, Counter(origins)]

    def _orig(self, aid):
        st = self.origins.get(aid)
        if st is None:
            st = self.origins[aid] = [0, 0.0, None, deque(), Counter()]
        return st

    def _dest(self, did):
        st = self.dests.get(did)
        if st is None:
            st = self.dests[did] = [0, Counter()]
        return st

    def add(self, row: dict) -> dict:
        o, d = row["nameOrig"], row["nameDest"]
        ts = causal_seconds(row)
        amt = float(row["amount"]) if row["amount"] not in ("", None) else 0.0

        ost = self._orig(o)
        dst = self._dest(d)
        n, sum_amt, last_ts, win, win_dests = ost

        avg_prev = (sum_amt / n) if n else 0.0
        dev_prev = round(amt - avg_prev, 2) if n else 0.0
        since_prev = round((ts - last_ts) / 3600.0, 2) if last_ts is not None else -1.0
        # evict records older than 24h strictly before the current row
        cutoff = ts - DAY_SECONDS
        while win and win[0][0] <= cutoff:
            _, a, dd = win.popleft()
            win_dests[dd] -= 1
            if win_dests[dd] <= 0:
                del win_dests[dd]
        cnt24 = len(win)
        amt24 = round(sum(w[1] for w in win), 2)
        uniq_dest24 = len(win_dests)

        feats = {
            "origin_txn_count_prev": n,
            "origin_avg_amount_prev": round(avg_prev, 2),
            "origin_amount_dev_prev": dev_prev,
            "origin_time_since_prev_txn": since_prev,
            "origin_txn_last24h": cnt24,
            "origin_amount_last24h": amt24,
            "origin_unique_dests_last24h": uniq_dest24,
            "dest_txn_count_prev": dst[0],
            "dest_unique_origins_prev": len(dst[1]),
        }

        # --- fold current row into state (AFTER features are taken) ---
        ost[0] = n + 1
        ost[1] = sum_amt + amt
        ost[2] = ts
        win.append((ts, amt, d))
        win_dests[d] += 1
        dst[0] += 1
        dst[1][o] += 1
        return feats


FEATURE_OUT_COLUMNS = ["record_uid"] + HISTORY_FEATURES


def build_features(tx_path: str, out_path: str, work_dir: str,
                   chunksize: int = 200_000) -> int:
    """Stream the strictly-prior feature matrix to ``out_path`` (CSV only).

    Writes ``record_uid`` + history features for every source row, in causal order.
    Returns the number of rows written. Memory stays bounded to one step + the
    per-account accumulators; the full transaction set is never materialised.
    """
    builder = CausalFeatureBuilder()
    tmp = out_path + ".tmp"
    written = 0
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FEATURE_OUT_COLUMNS, lineterminator="\n",
                           extrasaction="raise")
        w.writeheader()
        for row in iter_time_sorted(tx_path, work_dir, chunksize=chunksize):
            rec = {"record_uid": row["record_uid"]}
            rec.update(builder.add(row))
            w.writerow(rec)
            written += 1
    os.replace(tmp, out_path)
    return written

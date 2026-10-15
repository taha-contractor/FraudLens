"""M5 model-ready feature matrix builder (compact, bounded memory).

Reuses the M4 causal *semantics* to fold each transaction into strictly-prior account
history and carries the base columns needed for modelling/splitting/diagnostics through
the same external step-partition sort, producing ONE denormalised, causally-ordered
matrix (self-contained: no later join; each row's history depends only on strictly-
earlier records).

Memory model
------------
The reference :class:`features.causal.CausalFeatureBuilder` keeps a ``deque`` +
``Counter`` per unique account. At PaySim scale (millions of distinct origins/dests)
those long-lived objects exhaust RAM. Here, per-ROW data lives in compact numeric
``array`` buffers (~1 byte/elem for codes, 8 for floats) and per-account history is
computed by walking each account's rows (contiguous after a stable argsort by account
code, already in causal order) with a short-lived accumulator that is discarded after
each account. Peak memory is therefore ``O(rows)`` numeric (~1-1.5 GB) with NO
long-lived per-account objects.

Because origin features depend only on the same origin account's prior rows and dest
features only on the same dest account's prior rows, computing them in two independent
per-account passes reproduces EXACTLY the single interleaved streaming builder's values
(verified in tests). ``record_origin`` is derived from the file itself (empty
``event_ts`` => verbatim PaySim original).
"""

from __future__ import annotations

import csv
import json
import os
from array import array
from collections import Counter, deque

import numpy as np

from .causal import causal_seconds
from .policies import HISTORY_FEATURES
from generator.schema import TRANSACTION_TYPES

DAY_SECONDS = 86400

_CARRY = ["record_uid", "step", "event_ts", "type", "amount",
          "nameOrig", "oldbalanceOrg", "nameDest", "isFraud"]

MODEL_MATRIX_COLUMNS = (
    ["record_uid", "record_origin", "step", "type", "amount",
     "oldbalanceOrg", "nameDest", "isFraud"] + HISTORY_FEATURES
)

_TYPE_INDEX = {t: i for i, t in enumerate(TRANSACTION_TYPES)}


class BoundedCausalBuilder:
    """Per-account-equivalent reference used by tests (single interleaved stream).

    Produces identical features to CausalFeatureBuilder while holding only that
    account's window per active account; retained so the streaming equivalence can be
    asserted directly against the reference builder.
    """

    def __init__(self):
        self._o_code, self._d_code = {}, {}
        self.on, self.osum, self.olast = [], [], []
        self.owin = {}
        self.dn, self.dorig = [], {}

    def _oc(self, a):
        c = self._o_code.get(a)
        if c is None:
            c = self._o_code[a] = len(self.on)
            self.on.append(0); self.osum.append(0.0); self.olast.append(None)
        return c

    def _dc(self, a):
        c = self._d_code.get(a)
        if c is None:
            c = self._d_code[a] = len(self.dn)
            self.dn.append(0); self.dorig[c] = set()
        return c

    def add(self, row: dict) -> dict:
        ts = causal_seconds(row)
        amt = float(row["amount"]) if row["amount"] not in ("", None) else 0.0
        oc = self._oc(row["nameOrig"]); dc = self._dc(row["nameDest"])
        cutoff = ts - DAY_SECONDS
        win = self.owin.get(oc)
        if win:
            i = 0
            while i < len(win) and win[i][0] <= cutoff:
                i += 1
            if i:
                del win[:i]
        n = self.on[oc]; avg = (self.osum[oc] / n) if n else 0.0; last = self.olast[oc]
        feats = {
            "origin_txn_count_prev": n,
            "origin_avg_amount_prev": round(avg, 2),
            "origin_amount_dev_prev": round(amt - avg, 2) if n else 0.0,
            "origin_time_since_prev_txn": round((ts - last) / 3600.0, 2) if last is not None else -1.0,
            "origin_txn_last24h": len(win) if win else 0,
            "origin_amount_last24h": round(sum(w[1] for w in win), 2) if win else 0,
            "origin_unique_dests_last24h": len({w[2] for w in win}) if win else 0,
            "dest_txn_count_prev": self.dn[dc],
            "dest_unique_origins_prev": len(self.dorig[dc]),
        }
        self.on[oc] = n + 1; self.osum[oc] = self.osum[oc] + amt; self.olast[oc] = ts
        self.owin.setdefault(oc, []).append((ts, amt, dc))
        self.dorig[dc].add(oc); self.dn[dc] += 1
        return feats


def _iter_step_sorted(tx_path: str, work_dir: str, step_max: int = 743):
    buckets: dict = {}

    def spill(row):
        s = int(row["step"])
        fh = buckets.get(s)
        if fh is None:
            fh = buckets[s] = open(os.path.join(work_dir, f"mm_{s:05d}.jsonl"),
                                   "w", encoding="utf-8", newline="\n")
        fh.write(json.dumps({k: row.get(k, "") for k in _CARRY}, separators=(",", ":")) + "\n")

    try:
        with open(tx_path, "r", encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                spill({k: row.get(k, "") for k in _CARRY})
    finally:
        for fh in buckets.values():
            fh.close()
        buckets.clear()

    for s in range(1, step_max + 1):
        p = os.path.join(work_dir, f"mm_{s:05d}.jsonl")
        if not os.path.exists(p):
            continue
        with open(p, "r", encoding="utf-8") as fh:
            rows = [json.loads(line) for line in fh]
        rows.sort(key=lambda r: (causal_seconds(r), r["record_uid"]))
        for r in rows:
            yield r
        rows.clear()
        del rows
        os.remove(p)


def _load_causal(tx_path, work_dir, uid_file, step_max=743):
    """Phase A: fill compact numeric arrays in causal order + account codes."""
    ts = array("q"); amt = array("d"); old = array("d"); step = array("h")
    typ = array("b"); fraud = array("b"); gen = array("b")
    ocode = array("i"); dcode = array("i")
    omap, dmap = {}, {}
    olist, dlist = [], []
    uid_fh = open(uid_file, "w", encoding="utf-8", newline="\n")
    n = 0
    try:
        for row in _iter_step_sorted(tx_path, work_dir, step_max=step_max):
            t = causal_seconds(row)
            a = float(row["amount"]) if row["amount"] not in ("", None) else 0.0
            o = row["nameOrig"]; d = row["nameDest"]
            oc = omap.get(o)
            if oc is None:
                oc = omap[o] = len(olist); olist.append(o)
            dc = dmap.get(d)
            if dc is None:
                dc = dmap[d] = len(dlist); dlist.append(d)
            ts.append(t); amt.append(a)
            old.append(float(row["oldbalanceOrg"]) if row["oldbalanceOrg"] not in ("", None) else 0.0)
            step.append(int(row["step"])); typ.append(_TYPE_INDEX[row["type"]])
            fraud.append(1 if row["isFraud"] == "1" else 0)
            gen.append(0 if not row["event_ts"] else 1)
            ocode.append(oc); dcode.append(dc)
            uid_fh.write(row["record_uid"] + "\n")
            n += 1
    finally:
        uid_fh.close()
    return {
        "ts": np.frombuffer(ts, dtype=np.int64), "amt": np.frombuffer(amt, dtype=np.float64),
        "old": np.frombuffer(old, dtype=np.float64), "step": np.frombuffer(step, dtype=np.int16),
        "typ": np.frombuffer(typ, dtype=np.int8), "fraud": np.frombuffer(fraud, dtype=np.int8),
        "gen": np.frombuffer(gen, dtype=np.int8), "ocode": np.frombuffer(ocode, dtype=np.int32),
        "dcode": np.frombuffer(dcode, dtype=np.int32), "n": n,
        "olist": olist, "dlist": dlist,
    }


def _group_bounds(codes: np.ndarray):
    """Start offsets of equal-code runs after a stable argsort (preserves causal idx)."""
    order = np.argsort(codes, kind="stable")
    changed = np.r_[True, codes[order][1:] != codes[order][:-1]]
    starts = np.flatnonzero(changed)
    ends = np.r_[starts[1:], len(codes)]
    return order, starts, ends


def _origin_feats(base):
    ocode, dcode, ts, amt = base["ocode"], base["dcode"], base["ts"], base["amt"]
    N = base["n"]
    cnt = np.zeros(N, np.int64); avg = np.zeros(N, np.float64); dev = np.zeros(N, np.float64)
    since = np.zeros(N, np.float64); c24 = np.zeros(N, np.int32); a24 = np.zeros(N, np.float64)
    u24 = np.zeros(N, np.int32)
    order, starts, ends = _group_bounds(ocode)
    DAY = DAY_SECONDS
    for s, e in zip(starts, ends):
        win = deque(); wd = Counter()
        nn = 0; sm = 0.0; last = None
        for idx in order[s:e]:
            idx = int(idx)
            t = int(ts[idx]); a = float(amt[idx]); d = int(dcode[idx])
            cutoff = t - DAY
            while win and win[0][0] <= cutoff:
                _, ea, ed = win.popleft()
                wd[ed] -= 1
                if wd[ed] <= 0:
                    del wd[ed]
            avgv = (sm / nn) if nn else 0.0
            cnt[idx] = nn
            avg[idx] = round(avgv, 2)
            dev[idx] = round(a - avgv, 2) if nn else 0.0
            since[idx] = round((t - last) / 3600.0, 2) if last is not None else -1.0
            c24[idx] = len(win)
            a24[idx] = round(sum(x[1] for x in win), 2) if win else 0.0
            u24[idx] = len(wd)
            nn += 1; sm += a; last = t
            win.append((t, a, d)); wd[d] += 1
    return [cnt, avg, dev, since, c24, a24, u24]


def _dest_feats(base):
    ocode, dcode = base["ocode"], base["dcode"]
    N = base["n"]
    dc_prev = np.zeros(N, np.int64); du_prev = np.zeros(N, np.int64)
    order, starts, ends = _group_bounds(dcode)
    for s, e in zip(starts, ends):
        seen = set(); dn = 0
        for idx in order[s:e]:
            dc_prev[idx] = dn
            du_prev[idx] = len(seen)
            seen.add(ocode[idx])
            dn += 1
    return [dc_prev, du_prev]


def build_matrix(tx_path: str, out_path: str, work_dir: str, step_max: int = 743) -> dict:
    """Stream the causally-ordered model matrix to ``out_path`` (CSV only)."""
    uid_file = os.path.join(work_dir, "uids.txt")
    os.makedirs(work_dir, exist_ok=True)
    base = _load_causal(tx_path, work_dir, uid_file, step_max=step_max)
    of = _origin_feats(base)
    df = _dest_feats(base)
    feats = of + df  # order matches HISTORY_FEATURES

    tmp = out_path + ".tmp"
    written = generated = original = 0
    step, typn, fraud, gen, old, amt = (base["step"], base["typ"], base["fraud"],
                                        base["gen"], base["old"], base["amt"])
    dlist = base["dlist"]
    cols = [f.astype(np.float64) if f.dtype.kind in "fc" else f for f in feats]
    with open(tmp, "w", encoding="utf-8", newline="") as out_fh, \
            open(uid_file, "r", encoding="utf-8") as uid_fh:
        w = csv.writer(out_fh, lineterminator="\n")
        w.writerow(MODEL_MATRIX_COLUMNS)
        for i, uid in enumerate(uid_fh):
            g = int(gen[i])
            if g:
                generated += 1
            else:
                original += 1
            written += 1
            w.writerow([uid.rstrip("\n"), "generated" if g else "original",
                        int(step[i]), TRANSACTION_TYPES[int(typn[i])], _f(amt[i]), _f(old[i]),
                        dlist[int(base["dcode"][i])], int(fraud[i])]
                       + [_cell(f[i]) for f in cols])
    os.replace(tmp, out_path)
    return {"rows": written, "generated": generated, "original": original,
            "unique_origins": len(base["olist"]), "unique_dests": len(dlist),
            "columns": MODEL_MATRIX_COLUMNS}


def _f(x):
    v = float(x)
    return f"{v:.2f}" if abs(v - round(v, 2)) < 1e-9 else repr(v)


def _cell(x):
    if isinstance(x, (float, np.floating)):
        return _f(x)
    return int(x)

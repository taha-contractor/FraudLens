"""M5 dataset loading, encoding and fixed evaluation splits.

Loads the causally-built model matrix ONCE into compact arrays (float32 features,
int8 label, categorical codes for diagnostics), encodes the pre-transaction feature
policy (``type`` one-hot; step/amount/oldbalance + strictly-prior history), and
materialises the fixed evaluation partitions:

  * unseen-destination holdout at ACCOUNT level (a destination never straddles
    training and unseen evaluation);
  * chronological train/val/test by ``step`` boundary over the seen population.

Split definitions + dataset fingerprints are recorded for the experiment manifest,
and leakage / temporal-integrity checks run before any training.
"""

from __future__ import annotations

import csv
import hashlib
import os

import numpy as np
import pandas as pd

from generator.schema import TRANSACTION_TYPES
from features.policies import HISTORY_FEATURES
from features import audit

# raw matrix columns we need (record_uid is read separately, only for the split CSV)
_USECOLS = ["record_origin", "step", "type", "amount", "oldbalanceOrg", "nameDest",
            "isFraud"] + HISTORY_FEATURES

# model feature columns (pre-transaction policy with type one-hot)
TYPE_ONEHOT = [f"type_{t}" for t in TRANSACTION_TYPES]
FEATURE_COLUMNS = ["step", "amount", "oldbalanceOrg"] + TYPE_ONEHOT + HISTORY_FEATURES
NUMERIC_FEATURES = ["step", "amount", "oldbalanceOrg"] + HISTORY_FEATURES
_NCOL = len(FEATURE_COLUMNS)


def sha256_of(path: str) -> str:
    d = hashlib.sha256()
    with open(path, "rb") as fh:
        for blk in iter(lambda: fh.read(1 << 20), b""):
            d.update(blk)
    return d.hexdigest().upper()


def load_matrix(matrix_path: str, *, n_rows: int, chunk: int = 1_000_000) -> dict:
    """Stream the model matrix into compact arrays without keeping row strings.

    ``n_rows`` must be supplied (from the build summary / manifest) so the feature
    matrix can be preallocated as a single contiguous float32 block. ``nameDest`` is
    interned to int32 codes (one dict of ~1M strings), never stored per row.
    """
    X = np.empty((n_rows, _NCOL), dtype=np.float32)
    y = np.empty(n_rows, dtype=np.int8)
    step = np.empty(n_rows, dtype=np.int32)
    origin = np.empty(n_rows, dtype=object)   # small: filled with two interned str
    dest = np.empty(n_rows, dtype=np.int64)
    dcode: dict = {}
    pos = 0
    for ch in pd.read_csv(matrix_path, usecols=_USECOLS, chunksize=chunk,
                          dtype={"record_origin": "string", "type": "string",
                                 "nameDest": "string"}):
        m = len(ch)
        sl = slice(pos, pos + m)
        X[sl, FEATURE_COLUMNS.index("step")] = ch["step"].to_numpy(np.float32)
        X[sl, FEATURE_COLUMNS.index("amount")] = ch["amount"].to_numpy(np.float32)
        X[sl, FEATURE_COLUMNS.index("oldbalanceOrg")] = ch["oldbalanceOrg"].to_numpy(np.float32)
        tcode = pd.Categorical(ch["type"], categories=TRANSACTION_TYPES).codes
        for i, t in enumerate(TRANSACTION_TYPES):
            X[sl, FEATURE_COLUMNS.index(f"type_{t}")] = (tcode == i).astype(np.float32)
        for c in HISTORY_FEATURES:
            X[sl, FEATURE_COLUMNS.index(c)] = ch[c].to_numpy(np.float32)
        y[sl] = ch["isFraud"].to_numpy(np.int8)
        step[sl] = ch["step"].to_numpy(np.int32)
        origin[sl] = np.where(ch["record_origin"].to_numpy() == "original", "original", "generated")
        codes = np.empty(m, dtype=np.int64)
        for i, d in enumerate(ch["nameDest"].tolist()):
            c = dcode.get(d)
            if c is None:
                c = dcode[d] = len(dcode)
            codes[i] = c
        dest[sl] = codes
        pos += m
    return {"X": X, "y": y, "step": step, "origin": origin, "dest_codes": dest,
            "feature_columns": FEATURE_COLUMNS, "n": pos, "fraud_rate": float(y.mean())}


def _dest_held(dest_codes: np.ndarray, seed: int, frac: float) -> np.ndarray:
    """Deterministic destination-level holdout via sha256(seed::code)."""
    uniq = np.unique(dest_codes)
    held = np.zeros(len(uniq) + 1, dtype=bool)
    for code in uniq:
        h = hashlib.sha256(f"{seed}::{int(code)}".encode()).hexdigest()
        if (int(h[:8], 16) / 0xFFFFFFFF) < frac:
            held[code] = True
    return held[dest_codes]


def build_splits(data: dict, *, train_max: int, val_max: int,
                 holdout_seed: int, holdout_frac: float) -> dict:
    step, dest = data["step"], data["dest_codes"]
    unseen = _dest_held(dest, holdout_seed, holdout_frac)   # account-level holdout
    # width must fit the longest label ("unseen" = 6 chars); a too-narrow fixed
    # dtype silently TRUNCATES assignments and strands those rows in no split.
    assign = np.empty(len(step), dtype="<U8")
    assign[:] = "test"
    assign[(step <= train_max) & ~unseen] = "train"
    assign[(step > train_max) & (step <= val_max) & ~unseen] = "val"
    assign[(step > val_max) & ~unseen] = "test"
    assign[unseen] = "unseen"
    idx = {lab: np.where(assign == lab)[0]
           for lab in ("train", "val", "test", "unseen")}
    data["assign"] = assign
    data["split_index"] = idx
    data["unseen_mask"] = unseen
    return data


def integrity_report(data: dict) -> dict:
    """Leakage + temporal/disjointness checks; issues must be empty to train."""
    issues = audit.scan_forbidden("pre", data["feature_columns"])
    step = data["step"]
    assign = data["assign"]
    tr_val = np.isin(assign, ["train", "val"])
    te = assign == "test"
    if tr_val.any() and te.any() and step[tr_val].max() > step[te].min():
        issues.append("temporal order violated: max(train/val step) > min(test step)")
    # a destination must not appear in both train and unseen
    dest = data["dest_codes"]
    train_dest = set(dest[assign == "train"].tolist())
    unseen_dest = set(dest[assign == "unseen"].tolist())
    straddle = train_dest & unseen_dest
    if straddle:
        issues.append(f"destinations straddle train and unseen: {len(straddle)}")
    # per-split prevalence
    prev = {lab: float(data["y"][data["split_index"][lab]].mean())
            for lab in data["split_index"] if len(data["split_index"][lab])}
    return {"issues": issues, "prevalence_by_split": prev,
            "counts_by_split": {lab: int(len(ix)) for lab, ix in data["split_index"].items()}}


def write_split_csv(matrix_path: str, assign: np.ndarray, out_path: str) -> int:
    """Write record_uid -> split by streaming the matrix (rows are in causal order,
    so line i corresponds to ``assign[i]``). Keeps no row identifiers in memory."""
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    tmp = out_path + ".tmp"
    written = 0
    with open(matrix_path, "r", encoding="utf-8", newline="") as fin, \
            open(tmp, "w", encoding="utf-8", newline="") as fout:
        r = csv.reader(fin)
        w = csv.writer(fout, lineterminator="\n")
        header = next(r)
        ui, si = header.index("record_uid"), header.index("step")
        w.writerow(["record_uid", "step", "split"])
        for row in r:
            w.writerow([row[ui], row[si], str(assign[written])])
            written += 1
    os.replace(tmp, out_path)
    return written

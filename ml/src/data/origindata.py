"""Read-only loader for the original PaySim source dataset (M1).

This module is strictly **read-only**: it opens the source file only for
reading/hashing and NEVER writes to, overwrites, reformats or renames it. The
original PaySim CSV is a *source* for the enhanced dataset, not an operational
benchmark, and must remain byte-for-byte unchanged.
"""

from __future__ import annotations

import hashlib
import json
import os

import pandas as pd

# --- Frozen facts verified by streaming the actual file (see reports/Enhanced_PaySim_Dataset_Design.md) ---
RAW_PATH = os.path.join("ml", "data", "raw", "PS_20174392719_1491204439457_log.csv")
EXPECTED_SHA256 = "16910F90577B0D981BF8FF289714510BB89BC71BFF7D3F220F024E287E4EEA6B"
EXPECTED_SIZE_BYTES = 493534783
EXPECTED_ROWS = 6362620
EXPECTED_FRAUD = 8213
EXPECTED_FLAGGED = 16

# Exact column order of the source header.
EXPECTED_COLUMNS = [
    "step", "type", "amount", "nameOrig", "oldbalanceOrg", "newbalanceOrig",
    "nameDest", "oldbalanceDest", "newbalanceDest", "isFraud", "isFlaggedFraud",
]

# Semantic dtype kind per column (tolerant of pandas string-backend differences).
EXPECTED_KINDS = {
    "step": "int", "type": "text", "amount": "float", "nameOrig": "text",
    "oldbalanceOrg": "float", "newbalanceOrig": "float", "nameDest": "text",
    "oldbalanceDest": "float", "newbalanceDest": "float",
    "isFraud": "int", "isFlaggedFraud": "int",
}

TRANSACTION_TYPES = {"PAYMENT", "CASH_IN", "CASH_OUT", "TRANSFER", "DEBIT"}


class SchemaError(RuntimeError):
    """Raised when the source file does not match the expected PaySim schema."""


class IntegrityError(RuntimeError):
    """Raised when the source file fingerprint does not match the frozen checksum."""


def _dtype_kind(dtype) -> str:
    d = str(dtype).lower()
    if "int" in d:
        return "int"
    if "float" in d:
        return "float"
    if d in ("object", "string", "str", "str_") or "string" in d:
        return "text"
    return "other"


def file_fingerprint(path: str = RAW_PATH, block: int = 1024 * 1024) -> dict:
    """Return {size_bytes, sha256} for the file, read-only, streamed in blocks."""
    digest = hashlib.sha256()
    size = 0
    with open(path, "rb") as fh:  # binary read only — never "wb"/"r+"
        while True:
            buf = fh.read(block)
            if not buf:
                break
            size += len(buf)
            digest.update(buf)
    return {"path": path, "size_bytes": size, "sha256": digest.hexdigest().upper()}


def verify_integrity(path: str = RAW_PATH) -> dict:
    """Confirm the source is unchanged; raise IntegrityError on mismatch."""
    fp = file_fingerprint(path)
    if fp["size_bytes"] != EXPECTED_SIZE_BYTES:
        raise IntegrityError(f"size {fp['size_bytes']} != expected {EXPECTED_SIZE_BYTES}")
    if fp["sha256"] != EXPECTED_SHA256:
        raise IntegrityError(f"sha256 {fp['sha256']} != expected {EXPECTED_SHA256}")
    return fp


def validate_schema(df: pd.DataFrame) -> None:
    """Assert column names + order + dtype kinds match the frozen schema."""
    cols = list(df.columns)
    if cols != EXPECTED_COLUMNS:
        raise SchemaError(f"column mismatch\n got: {cols}\nexp: {EXPECTED_COLUMNS}")
    for col in EXPECTED_COLUMNS:
        kind = _dtype_kind(df[col].dtype)
        exp = EXPECTED_KINDS[col]
        if kind != exp:
            raise SchemaError(f"dtype kind for '{col}' is {kind}, expected {exp}")


def iter_chunks(path: str = RAW_PATH, chunksize: int = 500_000):
    """Yield read-only DataFrames of the source file, validating each chunk's schema."""
    reader = pd.read_csv(path, chunksize=chunksize)
    for chunk in reader:
        validate_schema(chunk)
        yield chunk


def load_first_chunk(path: str = RAW_PATH, n: int = 1000) -> pd.DataFrame:
    df = pd.read_csv(path, nrows=n)
    validate_schema(df)
    return df


def load_original_sample(path: str = RAW_PATH, n: int = 2000,
                         n_fraud: int = 20, chunksize: int = 500_000) -> list:
    """Read-only, evenly-spaced row sample of the source, values as raw STRINGS.

    ``dtype=str, keep_default_na=False`` preserves labels, identifiers and balance
    text exactly as stored — no type conversion. The source is never modified.
    Returns a list of ``{"source_row_index": int, **{col: str}}`` dicts: ``n``
    rows taken at evenly spaced positions across the file (so late-file fraud
    bands are reachable) plus up to ``n_fraud`` fraud-labelled rows.
    """
    targets = sorted({int(i * EXPECTED_ROWS / n) for i in range(n)})
    target_set = set(targets)
    picked: dict = {}
    fraud_left = max(0, int(n_fraud))
    pos = 0
    for chunk in pd.read_csv(path, dtype=str, keep_default_na=False,
                             nrows=EXPECTED_ROWS, chunksize=chunksize):
        for row in chunk.to_dict("records"):
            if pos in target_set and len(picked) < n:
                picked[pos] = row
            elif row["isFraud"] == "1" and fraud_left > 0:
                picked.setdefault(pos, row)
                fraud_left -= 1
            pos += 1
        if len(picked) >= n and fraud_left == 0:
            break
    return [{"source_row_index": idx, **picked[idx]} for idx in sorted(picked)]


def iter_source_records(path: str = RAW_PATH, chunksize: int = 500_000):
    """Stream EVERY source row read-only, as verbatim STRINGS — no sampling.

    Yields ``{"source_row_index": int, **{col: str}}`` for all ``EXPECTED_ROWS``
    records in file order, holding only one chunk in memory at a time. This is
    the full-source inclusion path (contrast :func:`load_original_sample`, which
    deliberately samples a subset for the pilot). Values use
    ``dtype=str, keep_default_na=False`` so identifiers, labels and balance text
    are preserved byte-for-byte with no type coercion; the file is opened
    read-only and never modified.
    """
    idx = 0
    for chunk in pd.read_csv(path, dtype=str, keep_default_na=False,
                             nrows=EXPECTED_ROWS, chunksize=chunksize):
        for row in chunk.to_dict("records"):
            yield {"source_row_index": idx, **row}
            idx += 1


def profile_source(path: str = RAW_PATH, chunksize: int = 500_000, verify_checksum: bool = True) -> dict:
    """Stream the whole file read-only and report structural + distribution facts.

    Nothing is written or altered; all counters are derived from reads.
    """
    fingerprint = verify_integrity(path) if verify_checksum else file_fingerprint(path)
    rows = 0
    fraud = 0
    flagged = 0
    type_counts = {}
    fraud_by_type = {}
    missing = 0
    duplicate_rows = 0
    seen = set()
    dtypes = None
    for chunk in iter_chunks(path, chunksize=chunksize):
        rows += len(chunk)
        if dtypes is None:
            dtypes = {c: str(chunk[c].dtype) for c in chunk.columns}
        missing += int(chunk.isna().sum().sum())
        fraud += int((chunk["isFraud"] == 1).sum())
        flagged += int((chunk["isFlaggedFraud"] == 1).sum())
        for t, v in chunk["type"].value_counts().items():
            type_counts[t] = type_counts.get(t, 0) + int(v)
        fr = chunk.loc[chunk["isFraud"] == 1, "type"].value_counts()
        for t, v in fr.items():
            fraud_by_type[t] = fraud_by_type.get(t, 0) + int(v)
        # full-row duplicate detection (cross-chunk, hashed)
        for h in pd.util.hash_pandas_object(chunk, index=False).to_numpy():
            hi = int(h)
            if hi in seen:
                duplicate_rows += 1
            else:
                seen.add(hi)

    invalid_types = sorted(set(type_counts) - TRANSACTION_TYPES)
    profile = {
        "fingerprint": fingerprint,
        "rows": rows,
        "columns": EXPECTED_COLUMNS,
        "dtypes": dtypes,
        "missing_values": missing,
        "exact_duplicate_rows": duplicate_rows,
        "fraud": {"count": fraud, "prevalence_pct": round(100 * fraud / rows, 5) if rows else 0.0},
        "flagged": {"count": flagged},
        "transaction_type_counts": type_counts,
        "fraud_by_type": fraud_by_type,
        "invalid_transaction_types": invalid_types,
    }
    return profile


def _coherence_checks(profile: dict) -> list:
    """Basic data-property validation (reports issues; never mutates records)."""
    issues = []
    if profile["missing_values"] != 0:
        issues.append(f"missing values present: {profile['missing_values']}")
    if profile["exact_duplicate_rows"] != 0:
        issues.append(f"exact duplicate rows: {profile['exact_duplicate_rows']}")
    if profile["invalid_transaction_types"]:
        issues.append(f"invalid transaction types: {profile['invalid_transaction_types']}")
    if sum(profile["fraud_by_type"].values()) != profile["fraud"]["count"]:
        issues.append("fraud-by-type totals do not match overall fraud count")
    if profile["rows"] != EXPECTED_ROWS:
        issues.append(f"row count {profile['rows']} != expected {EXPECTED_ROWS}")
    return issues


def main(argv=None):
    import argparse

    ap = argparse.ArgumentParser(description="Read-only PaySim source profiler (M1).")
    ap.add_argument("--path", default=RAW_PATH)
    ap.add_argument("--chunksize", type=int, default=500_000)
    ap.add_argument("--no-checksum", action="store_true", help="skip full SHA-256 (faster)")
    args = ap.parse_args(argv)

    profile = profile_source(args.path, chunksize=args.chunksize, verify_checksum=not args.no_checksum)
    profile["coherence_issues"] = _coherence_checks(profile)
    print(json.dumps(profile, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

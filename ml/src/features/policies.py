"""Feature-policy contract (M4) — single source of truth.

Defines the two SEPARATE feature policies and the hard exclusions that keep
labels, oracle flags, post-execution balances, raw identifiers and provenance out
of the predictive matrix. Everything else in M4 (builder, leakage audit, splits)
imports these names, so the contract cannot silently drift.

Causal order
------------
Records are placed in a deterministic total order by the causal key
``(step, ts_seconds, record_uid)``; history features use ONLY strictly-earlier
records of the same account under that order. See :mod:`features.causal`.
"""

from __future__ import annotations

from generator.schema import DERIVED_FEATURE_COLUMNS

# --- raw columns carried in enhanced_transactions.csv -----------------------
RAW_COLUMNS = [
    "record_uid", "step", "event_ts", "type", "amount",
    "nameOrig", "oldbalanceOrg", "newbalanceOrig",
    "nameDest", "oldbalanceDest", "newbalanceDest", "isFraud", "isFlaggedFraud",
]

# --- targets / labels -------------------------------------------------------
TARGET_COLUMN = "isFraud"
# isFlaggedFraud is a post-hoc oracle review flag -> never a pre-transaction feature.
ORACLE_COLUMNS = ["isFlaggedFraud"]

# --- post-execution / leakage-forbidden base columns for PRE scoring --------
POST_EXECUTION_BALANCES = ["newbalanceOrig", "newbalanceDest", "oldbalanceDest"]

# --- identifiers + provenance: preserved for investigation, never features --
IDENTIFIERS = ["record_uid", "nameOrig", "nameDest"]
PROVENANCE_FIELDS = [
    "source_dataset", "record_origin", "generator_version", "config_version",
    "generation_run_id", "scenario_id", "chain_id", "dataset_version",
]
# event_ts is a synthetic reference clock (ordering metadata), not a signal.
NON_SIGNAL = ["event_ts"]

# Columns that must NEVER appear in either policy's feature matrix.
FORBIDDEN_AS_FEATURES = set(
    [TARGET_COLUMN] + ORACLE_COLUMNS + IDENTIFIERS + PROVENANCE_FIELDS + NON_SIGNAL
)

# Strictly-prior causal history features (names reserved in the M2 schema).
HISTORY_FEATURES = list(DERIVED_FEATURE_COLUMNS)


def pre_transaction_features() -> list:
    """Policy A: observable BEFORE a transaction executes.

    step, type, amount, oldbalanceOrg + strictly-prior causal history. Excludes
    every post-execution balance, the target, the oracle flag, identifiers and
    provenance.
    """
    base = ["step", "type", "amount", "oldbalanceOrg"]
    cols = base + HISTORY_FEATURES
    _assert_policy_clean(cols)
    return cols


def investigation_features() -> list:
    """Policy B: post-transaction investigation.

    May use post-execution balances (available once the transaction has settled),
    but STILL never the target or the oracle review flag, identifiers or provenance.
    """
    base = ["step", "type", "amount",
            "oldbalanceOrg", "newbalanceOrig", "newbalanceDest", "oldbalanceDest"]
    cols = base + HISTORY_FEATURES
    _assert_policy_clean(cols, allow_post_execution=True)
    return cols


def _assert_policy_clean(cols, allow_post_execution: bool = False) -> None:
    s = set(cols)
    if TARGET_COLUMN in s:
        raise ValueError("target isFraud must never be a feature")
    if s & set(ORACLE_COLUMNS):
        raise ValueError("oracle flag isFlaggedFraud must never be a feature")
    if s & set(IDENTIFIERS):
        raise ValueError("identifiers/provenance must never be features")
    if s & set(PROVENANCE_FIELDS):
        raise ValueError("provenance fields must never be features")
    if not allow_post_execution and s & set(POST_EXECUTION_BALANCES):
        raise ValueError("post-execution balances are leakage in pre-transaction scoring")


def policy_columns(policy: str) -> list:
    if policy == "pre":
        return pre_transaction_features()
    if policy == "investigation":
        return investigation_features()
    raise ValueError(f"unknown policy {policy!r}")

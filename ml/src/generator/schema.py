"""Column schema + provenance schema for the enhanced dataset (M2).

Defines the *candidate* columns. The final per-model subset is chosen by the two
feature policies in M4 (pre-transaction vs investigation); this module only fixes
names and the feature/provenance separation so provenance can never leak into the
feature matrix.
"""

from __future__ import annotations

TRANSACTION_TYPES = ["PAYMENT", "CASH_IN", "CASH_OUT", "TRANSFER", "DEBIT"]

# PaySim-compatible base columns carried by every enhanced record.
BASE_FEATURE_COLUMNS = [
    "step", "event_ts", "type", "amount",
    "nameOrig", "oldbalanceOrg", "newbalanceOrig",
    "nameDest", "oldbalanceDest", "newbalanceDest",
]

# Strictly-prior derived features (names reserved; builder is blocked until the
# feature-availability review, so they are NOT computed in M2).
DERIVED_FEATURE_COLUMNS = [
    "origin_txn_count_prev", "origin_avg_amount_prev", "origin_amount_dev_prev",
    "origin_time_since_prev_txn", "origin_txn_last24h", "origin_amount_last24h",
    "origin_unique_dests_last24h", "dest_txn_count_prev", "dest_unique_origins_prev",
]

TARGET_COLUMNS = ["isFraud"]

# Post-event / oracle fields: allowed ONLY in the investigation policy, never in
# the pre-transaction risk model.
INVESTIGATION_ONLY_COLUMNS = ["isFlaggedFraud", "newbalanceOrig", "newbalanceDest", "oldbalanceDest"]

# Raw identifiers are excluded from the pre-transaction model (high-cardinality);
# only aggregated strictly-prior history is used instead.
IDENTIFIER_COLUMNS = ["nameOrig", "nameDest"]

# Provenance metadata — kept in a SEPARATE table, joined by record_uid, never a feature.
PROVENANCE_COLUMNS = [
    "record_uid", "source_dataset", "record_origin", "generator_version",
    "config_version", "generation_run_id", "scenario_id", "chain_id", "dataset_version",
]

SOURCE_DATASETS = {"paysim_original", "fraudlens_generated"}
RECORD_ORIGINS = {"original", "generated"}

# Canonical CSV column order for the enhanced *transaction* file. `record_uid` is a
# join key (never a model feature) linking rows to the separate provenance file.
# All transaction datasets are written as CSV only (approved decision: no Parquet).
ENHANCED_FEATURE_COLUMNS = [
    "record_uid", "step", "event_ts", "type", "amount",
    "nameOrig", "oldbalanceOrg", "newbalanceOrig",
    "nameDest", "oldbalanceDest", "newbalanceDest",
    "isFraud", "isFlaggedFraud",
]

# Columns in the transaction file that are identifiers/join keys, not features.
NON_FEATURE_COLUMNS = ["record_uid"] + IDENTIFIER_COLUMNS

# Internal record dict produced by the emitter *before* the pipeline maps it to the
# CSV schema: carries generator-only bookkeeping fields (is_fraud / scenario_id /
# chain_id) that are split into the target column and the provenance sidecar.
GENERATED_RECORD_COLUMNS = [
    "record_uid", "step", "event_ts", "type", "amount",
    "nameOrig", "oldbalanceOrg", "newbalanceOrig",
    "nameDest", "oldbalanceDest", "newbalanceDest",
    "is_fraud", "scenario_id", "chain_id",
]

# Monetary columns serialised with a fixed 2-decimal format for determinism.
MONEY_COLUMNS = ["amount", "oldbalanceOrg", "newbalanceOrig", "oldbalanceDest", "newbalanceDest"]


class SchemaError(RuntimeError):
    pass


def feature_columns(with_derived: bool = False):
    cols = list(BASE_FEATURE_COLUMNS)
    if with_derived:
        cols += list(DERIVED_FEATURE_COLUMNS)
    return cols


def pre_transaction_feature_columns(with_derived: bool = True):
    """Candidate columns observable BEFORE a transaction executes (availability policy)."""
    excluded = set(TARGET_COLUMNS) | set(INVESTIGATION_ONLY_COLUMNS) | set(IDENTIFIER_COLUMNS)
    return [c for c in feature_columns(with_derived) if c not in excluded]


def assert_feature_provenance_disjoint() -> None:
    overlap = set(feature_columns(with_derived=True)) & set(PROVENANCE_COLUMNS)
    if overlap:
        raise SchemaError(f"feature columns must not overlap provenance columns: {sorted(overlap)}")
    if overlap := (set(TARGET_COLUMNS) & set(PROVENANCE_COLUMNS)):
        raise SchemaError(f"target must not appear in provenance: {sorted(overlap)}")

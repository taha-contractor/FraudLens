"""Provenance annotation (M2): metadata kept strictly separate from features.

Every record in the enhanced dataset is traceable to its origin. Provenance lives in
its own table (joined by ``record_uid``) and must never enter the feature matrix.
"""

from __future__ import annotations

from .schema import (PROVENANCE_COLUMNS, RECORD_ORIGINS, SOURCE_DATASETS,
                     feature_columns)


class ProvenanceError(ValueError):
    pass


REQUIRED_FIELDS = list(PROVENANCE_COLUMNS)


def make_record(record_uid, source_dataset, record_origin, *, generator_version,
                config_version, generation_run_id, dataset_version,
                scenario_id=None, chain_id=None) -> dict:
    rec = {
        "record_uid": record_uid,
        "source_dataset": source_dataset,
        "record_origin": record_origin,
        "generator_version": generator_version,
        "config_version": config_version,
        "generation_run_id": generation_run_id,
        "scenario_id": scenario_id,
        "chain_id": chain_id,
        "dataset_version": dataset_version,
    }
    validate_record(rec)
    return rec


def validate_record(rec: dict) -> None:
    missing = [k for k in REQUIRED_FIELDS if k not in rec]
    if missing:
        raise ProvenanceError(f"provenance record missing fields: {missing}")
    if rec["source_dataset"] not in SOURCE_DATASETS:
        raise ProvenanceError(f"invalid source_dataset {rec['source_dataset']!r}")
    if rec["record_origin"] not in RECORD_ORIGINS:
        raise ProvenanceError(f"invalid record_origin {rec['record_origin']!r}")
    # Provenance must never contain feature columns.
    leaked = set(rec) & set(feature_columns(with_derived=True))
    if leaked:
        raise ProvenanceError(f"provenance must not contain feature columns: {sorted(leaked)}")
    # Origin consistency: original rows are not scenario-tagged; generated rows are.
    if rec["record_origin"] == "original" and rec["scenario_id"] is not None:
        raise ProvenanceError("original rows must not carry a scenario_id")
    if rec["record_origin"] == "generated" and rec["scenario_id"] is None:
        raise ProvenanceError("generated rows must carry a scenario_id")

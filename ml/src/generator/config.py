"""Declarative generator configuration + validation (M2).

Defaults are **coverage-driven, not score-driven** (see spec §13). Everything is
configurable; validation guards against nonsensical or shortcut-prone settings.
No dataset is produced by this module.
"""

from __future__ import annotations

import dataclasses
import json

from . import rng
from .schema import TRANSACTION_TYPES


class ConfigError(ValueError):
    pass


DEFAULT_CONFIG = {
    "master_seed": 42,
    "config_version": "cfg-default-v1",
    "generator_version": "0.1.0",
    "dataset_version": "enhanced-v1",
    "generated_rows": 2_000_000,
    "overall_fraud_rate": 0.03,
    # Every one of the five types must carry fraud (fixes L1); rates are (0, 1].
    # CASH_OUT / TRANSFER stay elevated because that is where PaySim fraud
    # actually concentrates; CASH_IN / PAYMENT are rare-fraud controls.
    "fraud_rate_by_type": {
        "PAYMENT": 0.01, "CASH_IN": 0.01, "CASH_OUT": 0.05,
        "TRANSFER": 0.06, "DEBIT": 0.03,
    },
    # Share of generated rows per type; chosen so the per-type fraud rates above
    # combine to the overall ~3% target. Configurable simulation assumption, not a
    # claim about the real-world type mix.
    "type_weights": {
        "PAYMENT": 0.24, "CASH_IN": 0.24, "CASH_OUT": 0.22,
        "TRANSFER": 0.18, "DEBIT": 0.12,
    },
    "min_per_scenario_count": 200,
    "n_origin_accounts": 200_000,
    "n_dest_accounts": 80_000,
    "step_start": 1,
    "step_end": 743,
    "substep_resolution": "second",   # "day" or "second"
    "output_format": "csv",           # CSV only (approved decision)
    "ledger_tolerance": 0.01,
    "chain_split_keys": ["chain_id", "nameOrig", "nameDest"],
}


@dataclasses.dataclass
class GeneratorConfig:
    master_seed: int
    config_version: str
    generator_version: str
    dataset_version: str
    generated_rows: int
    overall_fraud_rate: float
    fraud_rate_by_type: dict
    type_weights: dict
    min_per_scenario_count: int
    n_origin_accounts: int
    n_dest_accounts: int
    step_start: int
    step_end: int
    substep_resolution: str
    output_format: str
    ledger_tolerance: float
    chain_split_keys: list

    # ---- validation -------------------------------------------------------
    def validate(self) -> "GeneratorConfig":
        if not isinstance(self.master_seed, int) or self.master_seed < 0:
            raise ConfigError("master_seed must be a non-negative int")
        for field_name in ("config_version", "generator_version", "dataset_version"):
            if not isinstance(getattr(self, field_name), str) or not getattr(self, field_name).strip():
                raise ConfigError(f"{field_name} must be a non-empty string")
        if not isinstance(self.generated_rows, int) or self.generated_rows <= 0:
            raise ConfigError("generated_rows must be a positive int")
        if not 0.0 < self.overall_fraud_rate <= 0.5:
            raise ConfigError("overall_fraud_rate must be in (0, 0.5] — do not equal-balance (rules 5/6)")
        # Fraud must be present in all five transaction types (fixes L1).
        if set(self.fraud_rate_by_type) != set(TRANSACTION_TYPES):
            raise ConfigError("fraud_rate_by_type must define exactly the five transaction types")
        for t, r in self.fraud_rate_by_type.items():
            if not isinstance(r, (int, float)) or not 0.0 < r <= 1.0:
                raise ConfigError(f"fraud_rate_by_type['{t}'] must be in (0, 1]")
        if set(self.type_weights) != set(TRANSACTION_TYPES):
            raise ConfigError("type_weights must define exactly the five transaction types")
        if any(not isinstance(w, (int, float)) or w <= 0.0 for w in self.type_weights.values()):
            raise ConfigError("type_weights values must be positive numbers")
        if not isinstance(self.min_per_scenario_count, int) or self.min_per_scenario_count <= 0:
            raise ConfigError("min_per_scenario_count must be a positive int")
        if self.n_origin_accounts <= 0 or self.n_dest_accounts <= 0:
            raise ConfigError("account population sizes must be positive")
        if self.step_start < 1 or self.step_end < self.step_start:
            raise ConfigError("require 1 <= step_start <= step_end")
        if self.substep_resolution not in {"day", "second"}:
            raise ConfigError("substep_resolution must be 'day' or 'second'")
        if self.output_format != "csv":
            raise ConfigError("output_format must be 'csv' (CSV-only requirement; no Parquet)")
        if not 0.0 <= self.ledger_tolerance < 1.0:
            raise ConfigError("ledger_tolerance must be in [0, 1)")
        if not set(self.chain_split_keys) >= {"chain_id"}:
            raise ConfigError("chain_split_keys must include 'chain_id'")
        return self

    # ---- (de)serialisation ------------------------------------------------
    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "GeneratorConfig":
        known = {f.name for f in dataclasses.fields(cls)}
        unknown = set(data) - known
        if unknown:
            raise ConfigError(f"unknown config keys: {sorted(unknown)}")
        missing = known - set(data)
        if missing:
            raise ConfigError(f"missing config keys: {sorted(missing)}")
        return cls(**data).validate()

    @classmethod
    def from_json(cls, path: str) -> "GeneratorConfig":
        with open(path, "r", encoding="utf-8") as fh:
            return cls.from_dict(json.load(fh))

    def to_json(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, indent=2, sort_keys=True)

    # ---- derived, deterministic ------------------------------------------
    def generation_run_id(self) -> str:
        return rng.generation_run_id(self.master_seed, self.config_version)


def default_config() -> GeneratorConfig:
    return GeneratorConfig.from_dict(json.loads(json.dumps(DEFAULT_CONFIG)))

"""ValidationHarness: static structural checks (M2) + dataset-quality gates (M3).

The static checks validate the *configuration surface* (config validity, feature /
provenance disjointness, scenario coverage). ``run_dataset_gates`` implements the
spec §10 record-level data-quality checks over a set of emitted records. It is a
validator, not a cleaner: it reports issues and NEVER mutates records.
"""

from __future__ import annotations

import math

from .config import GeneratorConfig, default_config
from .schema import (GENERATED_RECORD_COLUMNS, TRANSACTION_TYPES,
                     assert_feature_provenance_disjoint,
                     pre_transaction_feature_columns)
from .scenarios import ScenarioLibrary
from .stats import GenStats


class ValidationHarness:
    def __init__(self, config: GeneratorConfig | None = None, library: ScenarioLibrary | None = None):
        self.config = (config or default_config())
        self.library = (library or ScenarioLibrary())

    def run_static_checks(self) -> list:
        """Return a list of human-readable issues; an empty list means all pass."""
        issues = []
        try:
            self.config.validate()
        except Exception as e:  # noqa: BLE001 - report any config error as an issue
            issues.append(f"config: {e}")
        try:
            self.library.validate()
        except Exception as e:  # noqa: BLE001
            issues.append(f"scenarios: {e}")
        try:
            assert_feature_provenance_disjoint()
        except Exception as e:  # noqa: BLE001
            issues.append(f"schema: {e}")
        if not pre_transaction_feature_columns():
            issues.append("pre-transaction feature set is empty")
        return issues

    def run_dataset_gates(self, records) -> list:
        """Spec §10 gates over generated records (iterable of emitter dicts).

        Returns human-readable issues; an empty list means every gate passed.
        Accumulates into a single-pass :class:`GenStats` (with an exact uid scan,
        since this path is used for pilots/tests on materialised lists) and delegates
        to :meth:`evaluate`. Balance-reconciliation applies to *generated* rows only —
        original PaySim rows are validated on the source side (M1) and preserved verbatim.
        """
        stats = GenStats(tol=self.config.ledger_tolerance, track_uids=True)
        for r in records:
            stats.add(r)
        return self.evaluate(stats)

    def evaluate(self, stats: GenStats) -> list:
        """Derive §10 gate issues from an accumulated :class:`GenStats` snapshot."""
        issues = []
        if stats.total == 0:
            return ["no records supplied to dataset gates"]

        if stats.cols != set(GENERATED_RECORD_COLUMNS):
            cols = stats.cols or set()
            issues.append(f"record columns != emitter schema: extra={sorted(cols - set(GENERATED_RECORD_COLUMNS))} "
                          f"missing={sorted(set(GENERATED_RECORD_COLUMNS) - cols)}")

        if stats.track_uids and stats.dup_uids:
            issues.append(f"duplicate record_uid values ({stats.dup_uids} dupes)")

        bad_types = sorted({t for t in stats.type_counts if t not in set(TRANSACTION_TYPES)})
        if bad_types:
            issues.append(f"invalid transaction types: {bad_types}")
        if stats.bad_labels:
            issues.append(f"invalid is_fraud labels: {sorted(stats.bad_labels)}")

        if stats.neg_amount:
            issues.append(f"negative/None amounts: {stats.neg_amount}")
        if stats.neg_oldbalance:
            issues.append(f"negative/None oldbalanceOrg: {stats.neg_oldbalance}")
        if stats.neg_newbalance:
            issues.append(f"negative/None newbalanceOrig: {stats.neg_newbalance}")

        if stats.bad_balance:
            issues.append(f"balance identity violated on {stats.bad_balance} generated records")

        # Fraud coverage must span ALL five types (fixes L1).
        all_types = set(TRANSACTION_TYPES)
        fraud_types = {t for t, n in stats.fraud_by_type.items() if n > 0}
        missing_fraud = sorted(all_types - fraud_types)
        if missing_fraud:
            issues.append(f"no fraud records for types: {missing_fraud}")
        legit_types = {t for t, n in stats.legit_by_type.items() if n > 0}
        missing_legit = sorted(all_types - legit_types)
        if missing_legit:
            issues.append(f"no legitimate records for types: {missing_legit}")

        # Scenario coverage floors.
        floor = self.config.min_per_scenario_count
        expected = {s.scenario_id for s in self.library.validate().scenarios}
        missing_scen = sorted(expected - set(stats.scenario_counts))
        if missing_scen:
            issues.append(f"scenarios with no records: {missing_scen}")
        below = {k: v for k, v in stats.scenario_counts.items() if v < floor}
        if below:
            issues.append(f"scenarios below min_per_scenario_count({floor}): {sorted(below.items())[:6]}")

        # Provenance completeness on every record.
        if stats.missing_scenario:
            issues.append(f"records missing provenance field 'scenario_id': {stats.missing_scenario}")
        if stats.missing_uid:
            issues.append(f"records missing provenance field 'record_uid': {stats.missing_uid}")

        # Chain integrity: every chain must be >=2 rows and carry ONE consistent label.
        single = sum(1 for e in stats.chains.values() if e[0] < 2)
        if single:
            issues.append(f"chain ids with fewer than 2 rows: {single}")
        mixed = [c for c, e in stats.chains.items() if not e[2]]
        if mixed:
            issues.append(f"chains with inconsistent labels: {mixed[:5]}")

        # Overall fraud rate vs configured target (guideline; flag large drift).
        rate = stats.fraud / stats.total
        target = self.config.overall_fraud_rate
        if not math.isfinite(rate) or rate > 2 * target or (rate < target / 2 and stats.total >= 5000):
            issues.append(f"fraud rate {rate:.4f} far from configured target {target}")
        return issues

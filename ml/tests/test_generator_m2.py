"""Tests for the M2 generator skeleton.

Run from the repo root (with the ML source on PYTHONPATH), using the project Python env:
    $env:PYTHONPATH="ml/src"; python -m unittest discover -s ml/tests -t ml/tests
"""

import copy
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "ml" / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from generator import accounts, chains, config, emitter, provenance, rng, schema, scenarios, validate  # noqa: E402


def small_config(**over):
    """A tiny-but-valid config so emit()/gates stay fast in unit tests."""
    import copy
    d = copy.deepcopy(config.DEFAULT_CONFIG)
    d["generated_rows"] = over.get("generated_rows", 4000)
    d["n_origin_accounts"] = over.get("n_origin_accounts", 400)
    d["n_dest_accounts"] = over.get("n_dest_accounts", 150)
    d["min_per_scenario_count"] = over.get("min_per_scenario_count", 1)
    return config.GeneratorConfig.from_dict(d)


class RngDeterminismTests(unittest.TestCase):
    def test_same_label_same_seed(self):
        self.assertEqual(rng.seed_for("a", 123), rng.seed_for("a", 123))

    def test_different_label_different_seed(self):
        self.assertNotEqual(rng.seed_for("a", 123), rng.seed_for("b", 123))

    def test_different_master_seed(self):
        self.assertNotEqual(rng.seed_for("a", 123), rng.seed_for("a", 124))

    def test_run_id_stable(self):
        self.assertEqual(rng.generation_run_id(1, "c1"), rng.generation_run_id(1, "c1"))


class AccountTests(unittest.TestCase):
    def test_ids_deterministic(self):
        a = accounts.make_account_ids("C", 50, 999)
        b = accounts.make_account_ids("C", 50, 999)
        self.assertEqual(a, b)

    def test_ids_differ_by_seed(self):
        self.assertNotEqual(accounts.make_account_ids("C", 50, 1),
                            accounts.make_account_ids("C", 50, 2))

    def test_id_format(self):
        for i in accounts.make_account_ids("M", 10, 7):
            self.assertTrue(i[0] == "M" and len(i) == 11 and i[1:].isdigit())

    def test_ledger_identity(self):
        acc = accounts.LedgerAccount("C1", balance=100.0)
        old, new = acc.debit(30.0)
        self.assertEqual((old, new), (100.0, 70.0))
        old2, new2 = acc.credit(5.0)
        self.assertEqual((old2, new2), (70.0, 75.0))

    def test_registry_populates(self):
        reg = accounts.AccountRegistry(master_seed=5, n_origin=20, n_dest=10)
        self.assertEqual(len(reg.origin_ids()), 20)
        self.assertEqual(len(reg.dest_ids()), 10)
        self.assertIn(reg.origin_ids()[0], reg.origins)


class ConfigTests(unittest.TestCase):
    def test_default_valid(self):
        cfg = config.default_config()
        self.assertEqual(set(cfg.fraud_rate_by_type), set(schema.TRANSACTION_TYPES))

    def test_from_json_file_matches_default(self):
        p = SRC / "generator" / "configs" / "default_v1.json"
        cfg = config.GeneratorConfig.from_json(str(p))
        self.assertEqual(cfg.to_dict(), config.default_config().to_dict())

    def test_missing_type_rejected(self):
        d = copy.deepcopy(config.DEFAULT_CONFIG)
        d["fraud_rate_by_type"].pop("DEBIT")
        with self.assertRaises(config.ConfigError):
            config.GeneratorConfig.from_dict(d)

    def test_equal_balance_rejected(self):
        d = copy.deepcopy(config.DEFAULT_CONFIG)
        d["overall_fraud_rate"] = 0.5 + 1e-9
        with self.assertRaises(config.ConfigError):
            config.GeneratorConfig.from_dict(d)

    def test_unknown_key_rejected(self):
        d = copy.deepcopy(config.DEFAULT_CONFIG)
        d["surprise"] = 1
        with self.assertRaises(config.ConfigError):
            config.GeneratorConfig.from_dict(d)

    def test_zero_rows_rejected(self):
        d = copy.deepcopy(config.DEFAULT_CONFIG)
        d["generated_rows"] = 0
        with self.assertRaises(config.ConfigError):
            config.GeneratorConfig.from_dict(d)


class SchemaTests(unittest.TestCase):
    def test_feature_provenance_disjoint(self):
        schema.assert_feature_provenance_disjoint()  # no raise

    def test_pre_transaction_excludes_leakage(self):
        feats = set(schema.pre_transaction_feature_columns())
        for bad in ["isFraud", "isFlaggedFraud", "newbalanceOrig", "newbalanceDest", "nameOrig", "nameDest"]:
            self.assertNotIn(bad, feats)
        self.assertIn("amount", feats)
        self.assertIn("origin_txn_count_prev", feats)


class ScenarioTests(unittest.TestCase):
    def test_library_valid_and_covers_all_types(self):
        lib = scenarios.ScenarioLibrary().validate()
        for t in schema.TRANSACTION_TYPES:
            self.assertTrue(lib.for_type(t, fraud=True))
            self.assertTrue(lib.for_type(t, fraud=False))

    def test_duplicate_id_rejected(self):
        dup = scenarios.Scenario("PAY-L1", "PAYMENT", False, "dupe")
        with self.assertRaises(scenarios.ScenarioError):
            scenarios.ScenarioLibrary(scenarios.BASE_SCENARIOS + [dup]).validate()


class ProvenanceTests(unittest.TestCase):
    def _base(self, **kw):
        d = dict(generator_version="0.1.0", config_version="c", generation_run_id="r",
                 dataset_version="dv")
        d.update(kw)
        return d

    def test_generated_requires_scenario(self):
        with self.assertRaises(provenance.ProvenanceError):
            provenance.make_record("uid1", "fraudlens_generated", "generated", **self._base())

    def test_original_no_scenario_ok(self):
        rec = provenance.make_record("uid2", "paysim_original", "original",
                                     **self._base(), scenario_id=None)
        self.assertEqual(rec["source_dataset"], "paysim_original")

    def test_generated_with_scenario_ok(self):
        rec = provenance.make_record("uid3", "fraudlens_generated", "generated",
                                     scenario_id="TRF-F1", **self._base())
        self.assertEqual(rec["scenario_id"], "TRF-F1")

    def test_no_feature_leakage_into_provenance(self):
        rec = provenance.make_record("uid4", "fraudlens_generated", "generated",
                                     scenario_id="PAY-F1", **self._base())
        self.assertFalse(set(rec) & set(schema.feature_columns(with_derived=True)))


class GuardTests(unittest.TestCase):
    """M3 implements emission/chains/gates; feature-building and splits stay gated."""

    def test_emitter_produces_records(self):
        e = emitter.TransactionEmitter(small_config())
        recs = e.emit()
        self.assertTrue(recs)
        self.assertTrue(all("record_uid" in r for r in recs))

    def test_chains_build_returns_linked_rows(self):
        origin_ids = accounts.make_account_ids("C", 50, 1)
        ext_ids = accounts.make_account_ids("C", 50, 2)
        rows = chains.ChainBuilder(1).build(3, origin_ids, ext_ids, 1, 1, 10)
        self.assertTrue(rows)
        self.assertTrue(all(r["chain_id"] for r in rows))

    def test_no_derived_feature_columns_emitted(self):
        # M3 must not build the reserved derived-history features (leakage review pending)
        from generator import schema
        e = emitter.TransactionEmitter(small_config())
        rec = e.emit()[0]
        for col in schema.DERIVED_FEATURE_COLUMNS:
            self.assertNotIn(col, rec)

    def test_dataset_gates_run(self):
        cfg = small_config()
        e = emitter.TransactionEmitter(cfg)
        issues = validate.ValidationHarness(cfg).run_dataset_gates(e.emit())
        self.assertEqual(issues, [])

    def test_static_checks_pass(self):
        self.assertEqual(validate.ValidationHarness().run_static_checks(), [])

    def test_chain_id_deterministic(self):
        self.assertEqual(chains.new_chain_id(9, "seq1"), chains.new_chain_id(9, "seq1"))


if __name__ == "__main__":
    unittest.main()

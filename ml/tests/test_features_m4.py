"""M4 feature-pipeline tests: policy contract, leakage and temporal correctness.

Run from the repo root:
    python -m unittest discover -s ml/tests -t ml/tests

The core leakage proof is PREFIX STABILITY: recomputing the causal feature matrix
on any chronological prefix of the data must reproduce byte-identical values for
the surviving rows (proving no future record informs a row's features). A second
test flips labels of the latest transactions and asserts features are unchanged
(proving no current/future label leaks into features).
"""

import csv
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "ml" / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from features import audit, causal, policies, splits  # noqa: E402
from generator.schema import ENHANCED_FEATURE_COLUMNS  # noqa: E402


def write_tx(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=ENHANCED_FEATURE_COLUMNS, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def row(uid, step, etype, amount, orig, dest, ts="", fraud=0, **bal):
    d = {
        "record_uid": uid, "step": step, "event_ts": ts, "type": etype, "amount": f"{amount:.2f}",
        "nameOrig": orig, "oldbalanceOrg": bal.get("ob", "0.00"),
        "newbalanceOrig": bal.get("nb", "0.00"), "nameDest": dest,
        "oldbalanceDest": bal.get("odb", "0.00"), "newbalanceDest": bal.get("ndb", "0.00"),
        "isFraud": fraud, "isFlaggedFraud": 0,
    }
    return d


def build_to_dict(tx_path):
    """Return {record_uid: feature_tuple} using the builder's own ordering."""
    with tempfile.TemporaryDirectory() as work, tempfile.TemporaryDirectory() as outd:
        feat_path = os.path.join(outd, "f.csv")
        n = causal.build_features(tx_path, feat_path, work)
        with open(feat_path, "r", encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh))
    assert len(rows) == n
    return {r["record_uid"]: tuple(r[c] for c in causal.FEATURE_OUT_COLUMNS[1:]) for r in rows}


def causal_sorted_uids(rows):
    return [r["record_uid"] for r in sorted(rows, key=causal.causal_key)]


class PolicyContractTests(unittest.TestCase):
    def test_pre_excludes_labels_oracle_balances_and_ids(self):
        cols = set(policies.pre_transaction_features())
        for bad in ["isFraud", "isFlaggedFraud", "newbalanceOrig", "newbalanceDest",
                    "oldbalanceDest", "nameOrig", "nameDest", "record_uid", "event_ts"]:
            self.assertNotIn(bad, cols, f"{bad} must not be a pre-transaction feature")

    def test_pre_uses_only_preexec_and_history(self):
        cols = policies.pre_transaction_features()
        self.assertIn("amount", cols)
        self.assertIn("oldbalanceOrg", cols)
        self.assertTrue(set(policies.HISTORY_FEATURES).issubset(set(cols)))

    def test_investigation_allows_balances_not_labels(self):
        cols = set(policies.investigation_features())
        self.assertTrue({"newbalanceOrig", "newbalanceDest", "oldbalanceDest"} <= cols)
        self.assertNotIn("isFraud", cols)
        self.assertNotIn("isFlaggedFraud", cols)

    def test_policies_are_separate_not_combined(self):
        self.assertNotEqual(policies.pre_transaction_features(),
                            policies.investigation_features())

    def test_audit_flags_forbidden_column(self):
        poisoned = policies.pre_transaction_features() + ["isFraud"]
        self.assertTrue(audit.audit_columns("pre", poisoned))

    def test_audit_accepts_clean_contract(self):
        self.assertEqual(audit.audit_columns("pre", policies.pre_transaction_features()), [])
        self.assertEqual(audit.audit_columns("investigation", policies.investigation_features()), [])


class CausalCorrectnessTests(unittest.TestCase):
    def test_first_txn_has_no_history(self):
        rows = [row("u1", 5, "PAYMENT", 100, "C1", "M1", ts="2017-01-05 10:00:00")]
        with tempfile.TemporaryDirectory() as d:
            tx = os.path.join(d, "t.csv")
            write_tx(tx, rows)
            feats = build_to_dict(tx)
        f = dict(zip(causal.HISTORY_FEATURES, feats["u1"]))
        self.assertEqual(f["origin_txn_count_prev"], "0")
        self.assertEqual(f["dest_txn_count_prev"], "0")
        self.assertEqual(f["dest_unique_origins_prev"], "0")

    def test_counts_are_strictly_prior(self):
        # same origin over increasing steps; each row should see only prior rows
        rows = [row(f"u{i}", i, "PAYMENT", 10 * i, "C1", f"M{i}", ts=f"2017-01-0{i} 00:00:00")
                for i in range(1, 6)]
        with tempfile.TemporaryDirectory() as d:
            tx = os.path.join(d, "t.csv")
            write_tx(tx, rows)
            feats = build_to_dict(tx)
        for i in range(1, 6):
            f = dict(zip(causal.HISTORY_FEATURES, feats[f"u{i}"]))
            self.assertEqual(int(f["origin_txn_count_prev"]), i - 1)


class TemporalPrefixStabilityTests(unittest.TestCase):
    def _dataset(self):
        rows = []
        for i in range(1, 41):
            step = (i % 7) + 1
            rows.append(row(f"u{i:03d}", step, ["PAYMENT", "CASH_OUT", "TRANSFER"][i % 3],
                            50 + i, f"C{i % 5}", f"M{i % 4}",
                            ts=f"2017-01-0{step} {i % 24:02d}:{i % 60:02d}:00",
                            fraud=i % 9 == 0))
        return rows

    def test_features_stable_under_chronological_prefix(self):
        rows = self._dataset()
        with tempfile.TemporaryDirectory() as d:
            full = os.path.join(d, "full.csv")
            write_tx(full, rows)
            full_feats = build_to_dict(full)

            order = causal_sorted_uids(rows)
            kept = order[:25]
            kept_set = set(kept)
            trunc = os.path.join(d, "trunc.csv")
            write_tx(trunc, [r for r in rows if r["record_uid"] in kept_set])
            trunc_feats = build_to_dict(trunc)

            for uid in kept:
                self.assertEqual(full_feats[uid], trunc_feats[uid],
                                 f"feature drift (future leakage) at {uid}")
            self.assertEqual(set(trunc_feats), kept_set)

    def test_features_invariant_to_future_labels(self):
        base = self._dataset()
        flipped = []
        order = set(causal_sorted_uids(base)[-10:])  # latest causal rows
        for r in base:
            r2 = dict(r)
            if r2["record_uid"] in order:
                r2["isFraud"] = 1 - int(r2["isFraud"])
            flipped.append(r2)
        with tempfile.TemporaryDirectory() as d:
            pa = os.path.join(d, "a.csv")
            pb = os.path.join(d, "b.csv")
            write_tx(pa, base)
            write_tx(pb, flipped)
            self.assertEqual(build_to_dict(pa), build_to_dict(pb))


class SplitIntegrityTests(unittest.TestCase):
    def test_chronological_boundaries_and_disjointness(self):
        a = [splits.chronological_split(s, 300, 500) for s in (100, 300, 301, 500, 501, 743)]
        self.assertEqual(a, ["train", "train", "val", "val", "test", "test"])

    def test_integrity_checks_pass_for_temporal_split(self):
        assignments = [(s, splits.chronological_split(s, 300, 500)) for s in range(1, 744)]
        self.assertEqual(splits.integrity_checks(assignments), [])

    def test_integrity_checks_reject_step_straddle(self):
        bad = [(10, "train"), (10, "test")]
        self.assertTrue(splits.integrity_checks(bad))

    def test_unseen_destination_is_account_level(self):
        dests = [f"M{i}" for i in range(50)]
        held = splits.unseen_destination_holdout(dests, seed=42, holdout_frac=0.3)
        self.assertTrue(0 < len(held) < len(dests))
        rec = {"step": 1, "nameDest": next(iter(held))}
        self.assertEqual(splits.split_of(rec, train_max=300, val_max=500, held_dests=held), "test")


if __name__ == "__main__":
    unittest.main()

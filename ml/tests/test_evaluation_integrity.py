"""Tests for evaluation integrity: feature contract, temporal and account splits.

Two separate claims are being protected:

* temporal split   - training rows are never later than evaluation rows, and the
  features of a training row do not change when the evaluation rows are removed;
* account split    - no account appears on both sides, and the held-out side is a
  deterministic function of the seed.

Run from the repository root:
    ml\\.venv\\Scripts\\python.exe -m unittest discover -s ml/tests -t ml/tests
"""

import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from feature_engineering import INPUT_COLUMNS, create_features
from generate_dataset import RANDOM_SEED, generate_dataset
from ml_config import (
    ACCOUNT_TEST_FRACTION,
    CATEGORICAL_FEATURES,
    FEATURE_COLUMNS,
    FEATURE_GROUPS,
    NON_FEATURE_COLUMNS,
    SPLIT_RANDOM_SEED,
    TARGET_COLUMN,
    LeakageError,
    account_split,
    assert_feature_contract,
    build_preprocessor,
    grouped_features,
    position_fraud_rates,
    temporal_split,
)


def build_frame(num_accounts=45, seed=RANDOM_SEED):
    return create_features(pd.DataFrame(generate_dataset(seed=seed, num_accounts=num_accounts)))


class FeatureContractTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frame = build_frame()

    def test_label_and_identifiers_are_rejected_as_features(self):
        for column in NON_FEATURE_COLUMNS:
            with self.assertRaises(LeakageError):
                assert_feature_contract([column])

    def test_undocumented_feature_is_rejected(self):
        with self.assertRaises(LeakageError):
            assert_feature_contract(["amount", "fraudRateLastWeek"])

    def test_empty_feature_list_is_rejected(self):
        with self.assertRaises(LeakageError):
            assert_feature_contract([])

    def test_documented_feature_set_passes(self):
        self.assertEqual(assert_feature_contract(FEATURE_COLUMNS), FEATURE_COLUMNS)

    def test_feature_list_contains_the_target_only_as_label(self):
        for column in FEATURE_COLUMNS:
            self.assertNotIn(column, NON_FEATURE_COLUMNS)
        self.assertNotIn(TARGET_COLUMN, self.frame.columns.intersection(FEATURE_COLUMNS))

    def test_preprocessor_only_encodes_documented_categoricals(self):
        preprocessor = build_preprocessor(FEATURE_COLUMNS)
        names = [name for name, _, _ in preprocessor.transformers]
        self.assertIn("categorical", names)
        for name, _, columns in preprocessor.transformers:
            if name == "categorical":
                self.assertEqual(list(columns), CATEGORICAL_FEATURES)

    def test_feature_groups_partition_the_feature_list(self):
        families = list(FEATURE_GROUPS.values())
        union = set().union(*(set(group) for group in families))
        self.assertEqual(union, set(FEATURE_COLUMNS))
        for index, first in enumerate(families):
            for second in families[index + 1:]:
                self.assertFalse(set(first) & set(second), "feature families overlap")
        self.assertEqual(len(grouped_features("basic", "behavioural", "velocity")), len(FEATURE_COLUMNS))

    # The regression this guards: fraud was impossible before position 5.
    def test_position_bands_are_not_label_free(self):
        for row in position_fraud_rates(self.frame):
            if row["support"] < 20:
                continue
            self.assertGreater(row["fraud_rate"], 0.0, f"band {row['band']} is fraud-free")
            self.assertLess(row["fraud_rate"], 1.0, f"band {row['band']} is all fraud")


class TemporalSplitTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frame = build_frame()

    def test_training_rows_never_come_after_evaluation_rows(self):
        train_df, test_df, boundary = temporal_split(self.frame)
        self.assertLessEqual(train_df["timestamp"].max(), test_df["timestamp"].min())
        self.assertEqual(boundary["boundary"], test_df["timestamp"].min())

    def test_split_size_follows_the_configured_fraction(self):
        train_df, test_df, _ = temporal_split(self.frame, train_fraction=0.75)
        self.assertEqual(len(train_df) + len(test_df), len(self.frame))
        self.assertAlmostEqual(len(train_df) / len(self.frame), 0.75, places=2)

    def test_split_is_independent_of_input_row_order(self):
        shuffled = self.frame.sample(frac=1, random_state=7).reset_index(drop=True)
        _, _, first = temporal_split(self.frame)
        _, _, second = temporal_split(shuffled)
        self.assertEqual(first["boundary"], second["boundary"])

    def test_degenerate_fraction_is_rejected(self):
        with self.assertRaises(LeakageError):
            temporal_split(self.frame, train_fraction=1.0)
        with self.assertRaises(LeakageError):
            temporal_split(self.frame, train_fraction=0.0)

    def test_causal_features_do_not_change_when_the_future_is_cut(self):
        """Features of training rows must be identical with or without test rows."""
        train_df, test_df, _ = temporal_split(self.frame)
        recomputed = create_features(train_df[INPUT_COLUMNS])
        merged = recomputed.set_index("transactionId").loc[train_df["transactionId"]]
        baseline = train_df.set_index("transactionId")
        for column in FEATURE_COLUMNS:
            self.assertTrue(
                pd.Series(merged[column].to_numpy()).equals(
                    pd.Series(baseline[column].to_numpy())
                ),
                f"{column} changed once the later transactions were removed",
            )

    def test_both_sides_contain_fraud(self):
        # A temporal split with no fraud in the test side would flatter the model.
        train_df, test_df, _ = temporal_split(self.frame)
        self.assertGreater(train_df[TARGET_COLUMN].sum(), 0)
        self.assertGreater(test_df[TARGET_COLUMN].sum(), 0)


class AccountSplitTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frame = build_frame()

    def test_no_account_is_on_both_sides(self):
        train_df, test_df, info = account_split(self.frame)
        self.assertFalse(set(train_df["accountId"]) & set(test_df["accountId"]))
        self.assertEqual(
            info["train_accounts"] + info["test_accounts"], self.frame["accountId"].nunique()
        )
        self.assertEqual(info["test_accounts"], test_df["accountId"].nunique())

    def test_split_is_deterministic_for_a_seed(self):
        first, _, first_info = account_split(self.frame, seed=SPLIT_RANDOM_SEED)
        second, _, second_info = account_split(self.frame, seed=SPLIT_RANDOM_SEED)
        self.assertEqual(first_info["seed"], second_info["seed"])
        self.assertEqual(
            sorted(first["accountId"].unique()), sorted(second["accountId"].unique())
        )

    def test_a_different_seed_holds_out_different_accounts(self):
        _, test_first, _ = account_split(self.frame, seed=SPLIT_RANDOM_SEED)
        _, test_other, _ = account_split(self.frame, seed=SPLIT_RANDOM_SEED + 1)
        self.assertNotEqual(
            sorted(test_first["accountId"].unique()),
            sorted(test_other["accountId"].unique()),
        )

    def test_held_out_share_is_close_to_the_configured_fraction(self):
        _, test_df, info = account_split(self.frame, test_fraction=ACCOUNT_TEST_FRACTION)
        total_accounts = info["train_accounts"] + info["test_accounts"]
        self.assertAlmostEqual(info["test_accounts"] / total_accounts,
                               ACCOUNT_TEST_FRACTION, delta=0.05)

    def test_account_split_moves_whole_histories(self):
        """A held-out account contributes every one of its rows, never some."""
        _, test_df, _ = account_split(self.frame)
        held_out = set(test_df["accountId"].unique())
        self.assertTrue(held_out)
        for account_id, block in self.frame.groupby("accountId"):
            if account_id in held_out:
                self.assertEqual(len(test_df[test_df["accountId"] == account_id]), len(block))
            else:
                self.assertNotIn(account_id, set(test_df["accountId"]))

    def test_unseen_accounts_carry_first_transaction_rows(self):
        # A held-out account's earliest row genuinely has no history for the model.
        _, test_df, _ = account_split(self.frame)
        self.assertGreater(int(test_df["isFirstTransaction"].sum()), 0)
        self.assertEqual(test_df[test_df["isFirstTransaction"] == 1]["transactionCount"].max(), 0)


if __name__ == "__main__":
    unittest.main()

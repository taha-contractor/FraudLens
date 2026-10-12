"""Tests for causal feature engineering.

The central promise of this module is that a HISTORY feature only ever uses
transactions that happened before the transaction being scored. Prefix stability
is the operational test: delete everything after a cutoff and the surviving rows
must keep exactly the same feature values.

Run from the repository root:
    ml\\.venv\\Scripts\\python.exe -m unittest discover -s ml/tests -t ml/tests
"""

import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from feature_engineering import (
    FEATURE_DEFINITIONS,
    HIGH_VALUE_THRESHOLD,
    INPUT_COLUMNS,
    create_features,
)
from generate_dataset import RANDOM_SEED, generate_dataset
from ml_config import CATEGORICAL_FEATURES

HISTORY_COLUMNS = [name for name, (availability, _) in FEATURE_DEFINITIONS.items()
                   if availability == "HISTORY"]


def make_row(transaction_id, account_id, amount, timestamp,
             location="Mumbai", transaction_type="PAYMENT", fraud_label=0):
    return {
        "transactionId": transaction_id,
        "accountId": account_id,
        "amount": float(amount),
        "transactionType": transaction_type,
        "location": location,
        "timestamp": timestamp,
        "fraudLabel": fraud_label,
    }


def naive_history_features(rows):
    """Deliberately slow reference implementation of the windowed features."""
    rows = sorted(rows, key=lambda row: (row["timestamp"], row["transactionId"]))
    output = []
    for index, row in enumerate(rows):
        earlier = rows[:index]
        one_hour = row["timestamp"] - pd.Timedelta(hours=1)
        one_day = row["timestamp"] - pd.Timedelta(hours=24)
        last_hour = [item for item in earlier if item["timestamp"] >= one_hour]
        last_day = [item for item in earlier if item["timestamp"] >= one_day]
        output.append({
            "transactionCount": len(earlier),
            "transactionsLastHour": len(last_hour),
            "transactionsLast24Hours": len(last_day),
            "amountLastHour": round(sum(item["amount"] for item in last_hour), 2),
        })
    return output


class FeatureContractTestCase(unittest.TestCase):
    def test_input_without_required_columns_is_rejected(self):
        frame = pd.DataFrame([{"transactionId": "TX1", "accountId": "A1"}])
        with self.assertRaises(ValueError):
            create_features(frame)

    def test_output_is_raw_contract_plus_documented_features(self):
        frame = pd.DataFrame([make_row("TX1", "A1", 100, "2026-01-01T10:00:00")])
        result = create_features(frame)
        self.assertEqual(
            list(result.columns),
            INPUT_COLUMNS + [
                name for name in FEATURE_DEFINITIONS if name not in INPUT_COLUMNS
            ],
        )

    def test_label_is_never_used_to_build_a_feature(self):
        # Flipping every label must not move any feature value.
        rows = [
            make_row("TX1", "A1", 100, "2026-01-01T10:00:00", fraud_label=0),
            make_row("TX2", "A1", 900, "2026-01-02T10:00:00", fraud_label=0),
        ]
        baseline = create_features(pd.DataFrame(rows))
        flipped = create_features(
            pd.DataFrame([{**row, "fraudLabel": 1} for row in rows])
        )
        for column in FEATURE_DEFINITIONS:
            self.assertTrue(
                baseline[column].equals(flipped[column]),
                f"{column} changed when only the label changed",
            )

    def test_numeric_features_have_no_missing_or_infinite_values(self):
        rows = generate_dataset(seed=RANDOM_SEED, num_accounts=20)
        result = create_features(pd.DataFrame(rows))
        categorical = CATEGORICAL_FEATURES
        for column in FEATURE_DEFINITIONS:
            if column in categorical:
                self.assertTrue(result[column].notna().all(), f"{column} is missing")
                continue
            values = pd.to_numeric(result[column], errors="coerce")
            self.assertFalse(values.isna().any(), f"{column} has missing values")
            self.assertFalse(
                (values.abs() == float("inf")).any(), f"{column} is infinite"
            )


class CurrentFeatureTestCase(unittest.TestCase):
    def setUp(self):
        hours = [0, 5, 6, 21, 22, 23]
        self.frame = pd.DataFrame([
            make_row(f"TX{index}", "A1", 1000, f"2026-01-01T{hour:02d}:30:00")
            for index, hour in enumerate(hours, start=1)
        ])

    def test_night_definition_matches_the_backend_rule(self):
        result = create_features(self.frame).set_index("transactionId")
        expected = {"TX1": 1, "TX2": 1, "TX3": 0, "TX4": 0, "TX5": 1, "TX6": 1}
        for transaction_id, flag in expected.items():
            self.assertEqual(
                int(result.loc[transaction_id, "isNightTransaction"]), flag,
                f"hour boundary wrong for {transaction_id}",
            )

    def test_high_value_threshold_is_inclusive(self):
        frame = pd.DataFrame([
            make_row("TX1", "A1", HIGH_VALUE_THRESHOLD - 0.01, "2026-01-01T10:00:00"),
            make_row("TX2", "A1", HIGH_VALUE_THRESHOLD, "2026-01-01T11:00:00"),
            make_row("TX3", "A1", HIGH_VALUE_THRESHOLD + 1, "2026-01-01T12:00:00"),
        ])
        flags = create_features(frame)["isHighValue"].tolist()
        self.assertEqual(flags, [0, 1, 1])


class HistoryFeatureTestCase(unittest.TestCase):
    def test_first_transaction_of_an_account_has_no_history(self):
        frame = pd.DataFrame([
            make_row("TX1", "A1", 500, "2026-01-05T09:00:00", location="Delhi"),
        ])
        row = create_features(frame).iloc[0]
        self.assertEqual(row["transactionCount"], 0)
        self.assertEqual(row["isFirstTransaction"], 1)
        self.assertEqual(row["previousTotalAmount"], 0)
        self.assertEqual(row["averageAmount"], 0)
        self.assertEqual(row["previousMaximumAmount"], 0)
        self.assertEqual(row["amountDeviation"], 0)
        self.assertEqual(row["exceedsPreviousMaximum"], 0)
        self.assertEqual(row["hoursSincePreviousTransaction"], 0)
        self.assertEqual(row["transactionsLastHour"], 0)
        self.assertEqual(row["transactionsLast24Hours"], 0)
        self.assertEqual(row["amountLastHour"], 0)
        self.assertEqual(row["locationNewForAccount"], 1)

    def test_running_aggregates_use_only_earlier_rows(self):
        frame = pd.DataFrame([
            make_row("TX1", "A1", 100, "2026-01-01T10:00:00"),
            make_row("TX2", "A1", 200, "2026-01-02T10:00:00"),
            make_row("TX3", "A1", 300, "2026-01-03T10:00:00"),
            # A very large later transaction must not touch TX3's aggregates.
            make_row("TX4", "A1", 90000, "2026-01-04T10:00:00"),
        ])
        row = create_features(frame).iloc[2]
        self.assertEqual(row["transactionCount"], 2)
        self.assertEqual(row["previousTotalAmount"], 300)
        self.assertEqual(row["averageAmount"], 150)
        self.assertEqual(row["previousMaximumAmount"], 200)
        self.assertAlmostEqual(row["amountDeviation"], 300 / 150)
        self.assertEqual(row["exceedsPreviousMaximum"], 1)
        self.assertAlmostEqual(row["hoursSincePreviousTransaction"], 24.0)

    def test_removing_the_future_leaves_earlier_rows_unchanged(self):
        rows = [
            make_row("TX1", "A1", 100, "2026-01-01T10:00:00"),
            make_row("TX2", "A1", 200, "2026-01-01T10:30:00"),
            make_row("TX3", "A1", 300, "2026-01-01T10:45:00"),
            make_row("TX4", "A1", 400, "2026-01-02T10:00:00"),
        ]
        full = create_features(pd.DataFrame(rows)).set_index("transactionId")
        truncated = create_features(pd.DataFrame(rows[:3])).set_index("transactionId")
        for column in FEATURE_DEFINITIONS:
            self.assertTrue(
                full.loc[truncated.index, column].equals(truncated[column]),
                f"{column} depended on a later transaction",
            )

    def test_rows_from_other_accounts_never_mix_in(self):
        frame = pd.DataFrame([
            make_row("TX1", "A1", 100, "2026-01-01T10:00:00"),
            make_row("TX2", "A2", 8000, "2026-01-01T10:05:00", location="Delhi"),
            make_row("TX3", "A1", 200, "2026-01-01T10:10:00", location="Delhi"),
        ])
        result = create_features(frame).set_index("transactionId")
        self.assertEqual(result.loc["TX3", "transactionCount"], 1)
        self.assertEqual(result.loc["TX3", "previousTotalAmount"], 100)
        self.assertEqual(result.loc["TX3", "transactionsLastHour"], 1)
        self.assertEqual(result.loc["TX3", "amountLastHour"], 100)
        self.assertEqual(result.loc["TX3", "locationNewForAccount"], 1)
        self.assertEqual(result.loc["TX2", "isFirstTransaction"], 1)

    def test_windowed_velocity_matches_the_naive_reference(self):
        rows = generate_dataset(seed=RANDOM_SEED, num_accounts=12)
        frame = create_features(pd.DataFrame(rows))

        for account_id, block in frame.groupby("accountId", sort=True):
            raw = [
                {
                    "transactionId": row.transactionId,
                    "timestamp": row.timestamp,
                    "amount": row.amount,
                }
                for row in block.itertuples(index=False)
            ]
            expected = naive_history_features(raw)
            actual = block.reset_index(drop=True)
            for index, reference_row in enumerate(expected):
                for column in (
                    "transactionCount",
                    "transactionsLastHour",
                    "transactionsLast24Hours",
                    "amountLastHour",
                ):
                    self.assertAlmostEqual(
                        float(actual.loc[index, column]),
                        float(reference_row[column]),
                        places=2,
                        msg=f"{account_id} row {index} column {column}",
                    )

    def test_amount_last_hour_excludes_the_transaction_itself(self):
        frame = pd.DataFrame([
            make_row("TX1", "A1", 5000, "2026-01-01T10:00:00"),
            make_row("TX2", "A1", 7000, "2026-01-01T10:20:00"),
        ])
        result = create_features(frame)
        self.assertEqual(result.iloc[0]["amountLastHour"], 0)
        self.assertEqual(result.iloc[1]["amountLastHour"], 5000)

    def test_equal_timestamps_are_ordered_deterministically(self):
        rows = [
            make_row("TX1", "A1", 100, "2026-01-01T10:00:00"),
            make_row("TX2", "A1", 200, "2026-01-01T10:00:00"),
        ]
        forward = create_features(pd.DataFrame(rows)).set_index("transactionId")
        backward = create_features(pd.DataFrame(rows[::-1])).set_index("transactionId")
        self.assertEqual(forward.loc["TX2", "transactionCount"], 1)
        for column in ("transactionCount", "previousTotalAmount", "amountLastHour"):
            self.assertTrue(
                forward[column].equals(backward[column]),
                f"{column} depends on the input row order",
            )


class PrefixStabilityTestCase(unittest.TestCase):
    def test_generated_dataset_features_are_prefix_stable(self):
        from ml_config import prefix_stability_report

        raw = pd.DataFrame(generate_dataset(seed=RANDOM_SEED, num_accounts=40))
        for report in prefix_stability_report(raw, quantiles=(0.3, 0.6, 0.9)):
            self.assertEqual(
                report["violating_features"], {},
                f"features changed when the future was removed at {report['cutoff']}",
            )

    def test_history_and_current_features_are_both_documented(self):
        current = [
            name for name, (availability, _) in FEATURE_DEFINITIONS.items()
            if availability == "CURRENT"
        ]
        self.assertTrue(current)
        self.assertTrue(HISTORY_COLUMNS)
        self.assertEqual(len(current) + len(HISTORY_COLUMNS), len(FEATURE_DEFINITIONS))


if __name__ == "__main__":
    unittest.main()

"""Tests for the synthetic generator: reproducibility and leakage safeguards.

Run from the repository root:
    ml\\.venv\\Scripts\\python.exe -m unittest discover -s ml/tests -t ml/tests
"""

import csv
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from generate_dataset import (
    ALL_LOCATIONS,
    COLUMNS,
    HIGH_VALUE_LOOKALIKE_RANGE,
    NIGHT_HOURS,
    RANDOM_SEED,
    TRANSACTION_TYPES,
    UNUSUAL_LOCATIONS,
    generate_dataset,
    write_dataset,
)

# One shared run for the statistical checks. The default seed and account count
# are what the committed dataset was built from, so these assertions describe the
# real dataset rather than an arbitrary sample.
HIGH_VALUE_THRESHOLD = 50000
TWO_HOURS = timedelta(hours=2)


def group_by_account(rows):
    grouped = {}
    for row in rows:
        grouped.setdefault(row["accountId"], []).append(row)
    for members in grouped.values():
        members.sort(key=lambda item: item["timestamp"])
    return grouped


class GeneratedDatasetTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = generate_dataset(seed=RANDOM_SEED)
        cls.by_account = group_by_account(cls.rows)
        cls.fraud = [row for row in cls.rows if row["fraudLabel"] == 1]
        cls.legit = [row for row in cls.rows if row["fraudLabel"] == 0]

    # --- schema, kept compatible with the FraudLens transaction contract ---

    def test_rows_follow_the_documented_schema(self):
        for row in self.rows:
            self.assertEqual(list(row.keys()), COLUMNS)

    def test_transaction_ids_are_unique(self):
        ids = [row["transactionId"] for row in self.rows]
        self.assertEqual(len(ids), len(set(ids)))

    def test_values_are_within_the_documented_domains(self):
        for row in self.rows:
            self.assertGreater(row["amount"], 0)
            self.assertIn(row["transactionType"], TRANSACTION_TYPES)
            self.assertIn(row["location"], ALL_LOCATIONS)
            self.assertIn(row["fraudLabel"], (0, 1))
            self.assertEqual(row["timestamp"].microsecond, 0)

    # --- reproducibility ---

    def test_same_seed_produces_the_same_dataset(self):
        first = generate_dataset(seed=RANDOM_SEED, num_accounts=15)
        second = generate_dataset(seed=RANDOM_SEED, num_accounts=15)
        self.assertEqual(first, second)

    def test_different_seed_produces_a_different_dataset(self):
        first = generate_dataset(seed=RANDOM_SEED, num_accounts=15)
        other = generate_dataset(seed=RANDOM_SEED + 1, num_accounts=15)
        self.assertNotEqual(first, other)

    def test_written_file_round_trips(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "rows.csv"
            write_dataset(self.rows[:50], target)
            with target.open(newline="", encoding="utf-8") as handle:
                records = list(csv.DictReader(handle))
            self.assertEqual(len(records), 50)
            self.assertEqual(list(records[0].keys()), COLUMNS)
            # Timestamps are written as naive local ISO seconds, no offset.
            self.assertRegex(records[0]["timestamp"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")

    # --- ordering integrity ---

    def test_timestamps_increase_within_each_account(self):
        for account_id, members in self.by_account.items():
            for previous, current in zip(members, members[1:]):
                self.assertGreater(
                    current["timestamp"],
                    previous["timestamp"],
                    f"{account_id}: {previous['timestamp']} then {current['timestamp']}",
                )

    # --- label / position independence (the old generator's defect) ---

    def test_fraud_can_be_an_accounts_first_transaction(self):
        first_position_fraud = sum(
            1 for members in self.by_account.values() if members[0]["fraudLabel"] == 1
        )
        self.assertGreater(first_position_fraud, 0)

    def test_no_sequence_position_is_guaranteed_legitimate(self):
        bands = [(0, 0), (1, 4), (5, 9), (10, 19), (20, None)]
        for low, high in bands:
            subset = [
                row
                for members in self.by_account.values()
                for position, row in enumerate(members)
                if position >= low and (high is None or position <= high)
            ]
            fraud = sum(row["fraudLabel"] for row in subset)
            self.assertGreaterEqual(
                fraud, 3, f"band {low}-{high} has too little fraud ({fraud})"
            )
            self.assertLess(fraud, len(subset), f"band {low}-{high} is all fraud")

    def test_transaction_count_is_not_a_label_proxy(self):
        # With the old generator every fraudulent row had transactionCount >= 5,
        # which made this the sharpest regression guard.
        rates = []
        for members in self.by_account.values():
            positions = [
                index for index, row in enumerate(members) if row["fraudLabel"] == 1
            ]
            if positions:
                rates.append(min(positions))
        self.assertGreater(
            sum(1 for value in rates if value == 0), 0,
            "no account has fraud at position 0 - position again carries the label",
        )

    # --- realistic temporal structure ---

    def test_bursts_of_transactions_exist(self):
        rapid = 0
        for members in self.by_account.values():
            for previous, current in zip(members, members[1:]):
                if current["timestamp"] - previous["timestamp"] < TWO_HOURS:
                    rapid += 1
        self.assertGreaterEqual(
            rapid, len(self.rows) * 0.05,
            f"only {rapid} rapid follow-ons in {len(self.rows)} rows",
        )

    def test_bursts_appear_in_both_classes(self):
        rapid = {}
        for account_id, members in self.by_account.items():
            for previous, current in zip(members, members[1:]):
                if current["timestamp"] - previous["timestamp"] < TWO_HOURS:
                    rapid[current["fraudLabel"]] = rapid.get(current["fraudLabel"], 0) + 1
        self.assertIn(0, rapid)
        self.assertIn(1, rapid)

    # --- fraud is not trivially predictable ---

    def test_class_balance_is_in_the_plausible_band(self):
        rate = len(self.fraud) / len(self.rows)
        self.assertGreaterEqual(rate, 0.05)
        self.assertLessEqual(rate, 0.20)

    def test_clean_accounts_exist_for_unseen_account_evaluation(self):
        clean = sum(
            1 for members in self.by_account.values()
            if all(row["fraudLabel"] == 0 for row in members)
        )
        self.assertGreaterEqual(clean, len(self.by_account) * 0.10)

    def test_amount_overlap_between_classes(self):
        legit_high = [row for row in self.legit if row["amount"] >= HIGH_VALUE_THRESHOLD]
        fraud_low = [row for row in self.fraud if row["amount"] < HIGH_VALUE_THRESHOLD]
        self.assertGreater(len(legit_high), len(self.rows) * 0.01)
        self.assertGreater(len(fraud_low), len(self.fraud) * 0.3)
        self.assertLessEqual(
            max(row["amount"] for row in self.fraud), HIGH_VALUE_LOOKALIKE_RANGE[1] * 3
        )

    def test_night_hours_are_not_fraud_specific(self):
        legit_night = sum(
            1 for row in self.legit
            if row["timestamp"].hour in NIGHT_HOURS
        )
        fraud_day = sum(
            1 for row in self.fraud
            if row["timestamp"].hour not in NIGHT_HOURS
        )
        self.assertGreater(legit_night, 0)
        self.assertGreater(fraud_day, 0)

    def test_no_single_observable_rule_identifies_fraud(self):
        for name, predicate in (
            ("isHighValue", lambda row: row["amount"] >= HIGH_VALUE_THRESHOLD),
            ("isNightTransaction", lambda row: row["timestamp"].hour in NIGHT_HOURS),
        ):
            flagged = [row for row in self.rows if predicate(row)]
            fraud_rate = sum(row["fraudLabel"] for row in flagged) / len(flagged)
            self.assertGreater(
                fraud_rate, 0.02, f"{name} would be a near-certain fraud rule"
            )
            self.assertLess(
                fraud_rate, 0.9, f"{name} would be a near-certain fraud rule"
            )

    def test_location_alone_is_not_a_fraud_rule(self):
        unusual = [row for row in self.rows if row["location"] in UNUSUAL_LOCATIONS]
        self.assertGreater(len(unusual), 0)
        fraud_rate = sum(row["fraudLabel"] for row in unusual) / len(unusual)
        self.assertGreater(fraud_rate, 0.02)
        self.assertLess(
            fraud_rate, 0.9, "an unusual location would be a near-certain fraud rule"
        )
        # And the same city must also appear as legitimate activity.
        self.assertGreater(
            sum(1 for row in unusual if row["fraudLabel"] == 0), 0
        )


if __name__ == "__main__":
    unittest.main()

"""Causal feature engineering for the FraudLens ML research prototype.

Reads ml/data/fraud_transactions.csv and writes ml/data/fraud_features.csv.

Every feature carries an explicit availability promise:

* CURRENT  - observable on the transaction itself, so it may use that
  transaction's own values.
* HISTORY  - built only from transactions that happened *before* the transaction
  being scored. The transaction under evaluation is never part of its own
  historical aggregates.

Enforced properties (see ml/tests/test_feature_engineering.py):

1. No target leakage. fraudLabel is read from the input and passed through; it is
   never used to build a feature, and no feature is a deterministic function of
   it.
2. Prefix stability. Recomputing features on a truncated dataset (all rows up to
   some timestamp) returns identical values for the surviving rows. This is the
   operational test for causality: if a feature changed when future rows are
   removed, that feature used the future.
3. Deterministic ordering. Rows are sorted by (accountId, timestamp,
   transactionId) so that ties in timestamps cannot reorder a history.
4. Vectorised, still causal. The windowed velocity features use searchsorted over
   each account's own sorted timeline; the result is checked against a naive
   double loop in the tests.

Timestamps are naive local times read as Asia/Kolkata, matching the generator and
the backend analytics definitions (night = hour >= 22 or hour < 6, high value =
amount >= 50000).
"""

import numpy as np
import pandas as pd

TRANSACTIONS_FILE = "ml/data/fraud_transactions.csv"
FEATURES_FILE = "ml/data/fraud_features.csv"

HIGH_VALUE_THRESHOLD = 50000
NIGHT_HOUR_START = 22
NIGHT_HOUR_END = 6

ONE_HOUR = np.timedelta64(3600, "s")
ONE_DAY = np.timedelta64(86400, "s")

INPUT_COLUMNS = [
    "transactionId",
    "accountId",
    "amount",
    "transactionType",
    "location",
    "timestamp",
    "fraudLabel",
]

# name -> (availability, definition). This table is the documented contract that
# ml/tests and docs/ML_Dataset_and_Features.md describe.
FEATURE_DEFINITIONS = {
    "amount": (
        "CURRENT",
        "Transaction amount in the case currency.",
    ),
    "transactionHour": (
        "CURRENT",
        "Hour of day (0-23) of the transaction in local time.",
    ),
    "isNightTransaction": (
        "CURRENT",
        "1 when transactionHour >= 22 or transactionHour < 6.",
    ),
    "isHighValue": (
        "CURRENT",
        f"1 when amount >= {HIGH_VALUE_THRESHOLD}. Absolute rule, not a learned one.",
    ),
    "transactionType": ("CURRENT", "TRANSFER, PAYMENT, WITHDRAWAL or DEPOSIT."),
    "location": ("CURRENT", "City where the transaction was initiated."),
    "transactionCount": (
        "HISTORY",
        "Number of earlier transactions on this account. 0 for the first one.",
    ),
    "isFirstTransaction": (
        "HISTORY",
        "1 when the account has no earlier transaction, so aggregates that need "
        "history are knowingly empty for that row.",
    ),
    "previousTotalAmount": (
        "HISTORY",
        "Sum of amounts of all earlier transactions on this account.",
    ),
    "averageAmount": (
        "HISTORY",
        "previousTotalAmount / transactionCount, 0 when there is no history.",
    ),
    "previousMaximumAmount": (
        "HISTORY",
        "Largest amount among earlier transactions, 0 when there is no history.",
    ),
    "amountDeviation": (
        "HISTORY",
        "amount / averageAmount, 0 when there is no positive average. A value of "
        "3 or more means the transaction is far above the account's own habit.",
    ),
    "exceedsPreviousMaximum": (
        "HISTORY",
        "1 when the amount is larger than every earlier amount of the account.",
    ),
    "hoursSincePreviousTransaction": (
        "HISTORY",
        "Elapsed hours since the previous transaction of the same account. 0 for "
        "the first transaction; read together with isFirstTransaction.",
    ),
    "locationNewForAccount": (
        "HISTORY",
        "1 when this location has not appeared in an earlier transaction of the "
        "same account.",
    ),
    "transactionsLastHour": (
        "HISTORY",
        "Earlier transactions of this account within the preceding hour.",
    ),
    "transactionsLast24Hours": (
        "HISTORY",
        "Earlier transactions of this account within the preceding 24 hours.",
    ),
    "amountLastHour": (
        "HISTORY",
        "Sum of amounts of the earlier transactions within the preceding hour.",
    ),
}

CURRENT_FEATURES = [
    name for name, (availability, _) in FEATURE_DEFINITIONS.items()
    if availability == "CURRENT"
]
HISTORY_FEATURES = [
    name for name, (availability, _) in FEATURE_DEFINITIONS.items()
    if availability == "HISTORY"
]
FEATURE_COLUMNS = CURRENT_FEATURES + HISTORY_FEATURES

SORT_KEYS = ["accountId", "timestamp", "transactionId"]

# Output order: the raw transaction contract first, then the generated features.
# "amount" is both a raw column and a feature, so it appears only once.
OUTPUT_COLUMNS = INPUT_COLUMNS + [
    column for column in FEATURE_COLUMNS if column not in INPUT_COLUMNS
]


def _account_features(timestamps, amounts, locations):
    """Compute every HISTORY feature for one account, in chronological order.

    `timestamps` is a sorted numpy datetime64 array, `amounts` and `locations`
    align with it. Only rows strictly before position i may feed position i.
    """
    size = len(timestamps)
    positions = np.arange(size)
    running_total = np.cumsum(amounts) - amounts  # sum of strictly earlier amounts

    previous_maximum = np.concatenate(([0.0], np.maximum.accumulate(amounts)[:-1]))
    average = np.divide(
        running_total,
        positions,
        out=np.zeros(size, dtype=float),
        where=positions > 0,
    )
    deviation = np.divide(
        amounts,
        average,
        out=np.zeros(size, dtype=float),
        where=average > 0,
    )

    previous_timestamp = np.concatenate(([timestamps[0]], timestamps[:-1]))
    hours_since = (timestamps - previous_timestamp) / ONE_HOUR
    hours_since[0] = 0.0

    first_in_window = np.searchsorted(timestamps, timestamps - ONE_HOUR, side="right")
    first_in_day = np.searchsorted(timestamps, timestamps - ONE_DAY, side="right")
    count_last_hour = positions - first_in_window
    count_last_day = positions - first_in_day
    # Sum of amounts over the half-open index range [first_in_window, i). Using the
    # exclusive prefix keeps the transaction under evaluation out of its own window.
    total_last_hour = running_total - running_total[first_in_window]

    seen = set()
    location_new = np.zeros(size, dtype=int)
    for index, location in enumerate(locations):
        location_new[index] = 0 if location in seen else 1
        seen.add(location)

    return {
        "transactionCount": positions.astype(float),
        "isFirstTransaction": (positions == 0).astype(int),
        "previousTotalAmount": running_total,
        "averageAmount": average,
        "previousMaximumAmount": previous_maximum,
        "amountDeviation": deviation,
        "exceedsPreviousMaximum": (
            (amounts > previous_maximum) & (positions > 0)
        ).astype(int),
        "hoursSincePreviousTransaction": np.round(hours_since, 4),
        "locationNewForAccount": location_new,
        "transactionsLastHour": count_last_hour,
        "transactionsLast24Hours": count_last_day,
        "amountLastHour": np.round(total_last_hour, 2),
    }


# HISTORY features that are counts or flags, stored as integers.
INTEGER_FEATURES = {
    "transactionCount",
    "isFirstTransaction",
    "exceedsPreviousMaximum",
    "locationNewForAccount",
    "transactionsLastHour",
    "transactionsLast24Hours",
}


def create_features(df):
    """Add the documented CURRENT and HISTORY features to raw transactions."""
    missing = [column for column in INPUT_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(f"input is missing required columns: {', '.join(missing)}")

    frame = df.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"])
    frame = frame.sort_values(SORT_KEYS, kind="stable").reset_index(drop=True)

    hour = frame["timestamp"].dt.hour
    frame["transactionHour"] = hour
    frame["isNightTransaction"] = (
        (hour >= NIGHT_HOUR_START) | (hour < NIGHT_HOUR_END)
    ).astype(int)
    frame["isHighValue"] = (frame["amount"] >= HIGH_VALUE_THRESHOLD).astype(int)

    columns = {
        name: np.zeros(len(frame), dtype=float)
        for name in HISTORY_FEATURES
    }

    for _, block in frame.groupby("accountId", sort=True):
        positions = block.index.to_numpy()
        values = _account_features(
            block["timestamp"].to_numpy(),
            block["amount"].to_numpy(dtype=float),
            block["location"].tolist(),
        )
        for name, array in values.items():
            columns[name][positions] = array

    for name in HISTORY_FEATURES:
        values = columns[name]
        frame[name] = values.astype(int) if name in INTEGER_FEATURES else values

    return frame[OUTPUT_COLUMNS]


def main():
    print("Loading dataset...")
    df = pd.read_csv(TRANSACTIONS_FILE)
    print(f"Original rows: {len(df)}")

    features = create_features(df)
    features.to_csv(FEATURES_FILE, index=False)

    print(f"Output rows: {len(features)}")
    print(f"Generated features: {len(FEATURE_COLUMNS)}")
    print("\nFeature definitions:")
    for name, (availability, definition) in FEATURE_DEFINITIONS.items():
        print(f"  {name} [{availability}] - {definition}")

    print("\nSample rows:")
    print(
        features[
            [
                "transactionId",
                "amount",
                "transactionHour",
                "isNightTransaction",
                "isHighValue",
                "transactionCount",
                "averageAmount",
                "amountDeviation",
                "transactionsLastHour",
                "fraudLabel",
            ]
        ].head(10).to_string(index=False)
    )
    print(f"\nSaved to: {FEATURES_FILE}")


if __name__ == "__main__":
    main()

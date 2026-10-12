"""Leakage and causality audit for the FraudLens ML dataset.

Answers three questions about the generated data and the feature pipeline, and
prints the evidence rather than a verdict alone:

1. Does the label depend on sequence position?  If fraud only ever appears after
   the fifth transaction, transactionCount is a label proxy and the model will
   "learn" a rule that the generator wrote.
2. Can one feature classify alone?  A synthetic dataset may be hard; it must not
   be tautological.
3. Does any feature use the future?  Truncating the dataset at several cutoffs
   must leave every surviving row's features unchanged (prefix stability). This is
   the operational definition of a causal historical feature.

Run from the repository root:  python ml/audit_leakage.py
"""

import argparse

import numpy as np
import pandas as pd

from ml_config import (
    CATEGORICAL_FEATURES,
    FEATURE_COLUMNS,
    TARGET_COLUMN,
    audit_feature_leakage,
    numeric_feature_auc,
    position_fraud_rates,
    prefix_stability_report,
)
from feature_engineering import TRANSACTIONS_FILE, create_features


def report_dataset(frame):
    print("===== DATASET =====")
    fraud = int(frame[TARGET_COLUMN].sum())
    print(f"Transactions: {len(frame)}")
    print(f"Accounts: {frame['accountId'].nunique()}")
    print(f"Fraud: {fraud} ({fraud / len(frame):.2%})   Legitimate: {len(frame) - fraud}")
    print(f"Features: {len(FEATURE_COLUMNS)}")


def report_positions(frame):
    print("\n===== LABEL VS SEQUENCE POSITION =====")
    print(f"{'band':>6} {'rows':>7} {'fraud rate':>11}")
    for row in position_fraud_rates(frame):
        rate = "n/a" if np.isnan(row["fraud_rate"]) else f"{row['fraud_rate']:.4f}"
        print(f"{row['band']:>6} {row['support']:>7} {rate:>11}")
    print(
        "Expectation: every populated band has a rate near the base rate. A 0.0000 "
        "in an early band is the old generator's defect."
    )


def report_single_features(frame):
    print("\n===== SINGLE-FEATURE SEPARATION =====")
    scores = []
    for feature in FEATURE_COLUMNS:
        if feature in CATEGORICAL_FEATURES:
            continue
        auc = numeric_feature_auc(frame, feature)
        scores.append((feature, auc, abs(auc - 0.5)))
    scores.sort(key=lambda item: item[2], reverse=True)
    for feature, auc, separation in scores:
        print(f"{feature:>32}  AUC {auc:6.4f}  |AUC-0.5| {separation:5.4f}")
    print(
        "\nCategorical fraud rates by value:"
    )
    for feature in CATEGORICAL_FEATURES:
        for value, subset in frame.groupby(feature):
            rate = subset[TARGET_COLUMN].mean()
            print(
                f"{feature:>32}  {str(value):<14} rows {len(subset):>5}"
                f"  fraud rate {rate:.4f}"
            )


def report_prefix_stability(raw_frame):
    print("\n===== PREFIX STABILITY (causality) =====")
    for row in prefix_stability_report(raw_frame):
        violations = row["violating_features"]
        status = "causal" if not violations else f"LEAKY {violations}"
        print(f"cutoff {row['cutoff']}  rows {row['rows']:>5}  {status}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--transactions", default=TRANSACTIONS_FILE)
    args = parser.parse_args()

    raw = pd.read_csv(args.transactions)
    frame = create_features(raw)

    report_dataset(frame)
    report_positions(frame)
    report_single_features(frame)
    report_prefix_stability(raw)

    audit = audit_feature_leakage(frame, FEATURE_COLUMNS)
    print("\n===== SUMMARY =====")
    if audit["suspicious_auc"] or audit["suspicious_categories"]:
        print("Flagged:")
        for feature, auc in audit["suspicious_auc"]:
            print(f"  {feature} alone reaches AUC {auc}")
        for feature, value, support, rate in audit["suspicious_categories"]:
            print(f"  {feature}={value} is {rate:.0%} one class over {support} rows")
    else:
        print("No single feature separates the classes at the configured threshold.")


if __name__ == "__main__":
    main()

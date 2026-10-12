"""Temporal (time-ordered) evaluation of the FraudLens fraud classifier.

The first 80% of transactions by time train the model, the remaining 20% are the
future it has to score. No random row split is used: a random split would let the
model train on transactions that happened after the one it is being tested on.

Historical features are causal and prefix-stable (see feature_engineering.py), so
a training row cannot carry information from after its own timestamp. The split
boundary is asserted inside ml_config.temporal_split and raises rather than
warning.

This is a research prototype on synthetic data. Nothing here is production ready.
"""

from ml_config import (
    FEATURE_COLUMNS,
    audit_feature_leakage,
    describe_split,
    fit_and_score,
    load_features,
    temporal_split,
)


def main():
    print("Loading feature dataset...")
    df = load_features()
    print(f"Total transactions: {len(df)}")
    print(f"Accounts: {df['accountId'].nunique()}")
    print(f"Available features: {len(FEATURE_COLUMNS)}")

    train_df, test_df, boundary = temporal_split(df)
    print("\n===== TEMPORAL SPLIT (80/20 by time) =====")
    print(f"Split at: {boundary['boundary']}")
    describe_split("Train (earlier)", train_df)
    describe_split("Test  (later) ", test_df)
    shared_accounts = set(train_df["accountId"]) & set(test_df["accountId"])
    print(f"Accounts represented on both sides: {len(shared_accounts)}")

    print("\n===== SINGLE-FEATURE LEAKAGE AUDIT =====")
    audit = audit_feature_leakage(df, FEATURE_COLUMNS)
    if not audit["suspicious_auc"] and not audit["suspicious_categories"]:
        print("No single feature separates the classes on its own.")
    for feature, auc in audit["suspicious_auc"]:
        print(f"  suspicious AUC: {feature} -> {auc}")
    for feature, value, support, rate in audit["suspicious_categories"]:
        print(f"  pure category: {feature}={value} support {support} fraud rate {rate}")

    print("\nTraining Random Forest on the earlier transactions...")
    result = fit_and_score(train_df, test_df, FEATURE_COLUMNS, verbose=True)
    ranked = sorted(
        zip(result["feature_names"], result["model"].feature_importances_),
        key=lambda pair: pair[1],
        reverse=True,
    )[:8]
    print("\nTop transformed features by impurity reduction:")
    for name, value in ranked:
        print(f"  {name}: {value:.4f}")
    print("\nReminder: synthetic data, research prototype, not a production model.")


if __name__ == "__main__":
    main()

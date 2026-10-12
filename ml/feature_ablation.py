"""Feature ablation for the FraudLens fraud classifier.

Trains the same classifier three times on nested feature families and compares
the result, so the value of the behavioural and velocity features is measured
instead of assumed:

  basic                              current-transaction observables
  basic + behavioural                plus causal account history
  basic + behavioural + velocity     plus windowed activity rates

The comparison uses the temporal split, because that is the split the prototype
is evaluated on; ml_config.temporal_split enforces the ordering. The three
families partition the documented feature list, which
ml/tests/test_ml_config.py checks, so a new feature cannot be forgotten here.
"""

import pandas as pd

from ml_config import (
    FEATURE_COLUMNS,
    FEATURE_GROUPS,
    describe_split,
    fit_and_score,
    grouped_features,
    load_features,
    temporal_split,
)

EXPERIMENTS = [
    ("Basic", ("basic",)),
    ("Basic + Behavioral", ("basic", "behavioural")),
    ("Basic + Behavioral + Velocity", ("basic", "behavioural", "velocity")),
]

METRIC_COLUMNS = ["features", "roc_auc", "precision", "recall", "f1", "accuracy"]


def main():
    print("Loading dataset...")
    df = load_features()
    train_df, test_df, boundary = temporal_split(df)
    print(f"Split at: {boundary['boundary']}")
    describe_split("Training transactions", train_df)
    describe_split("Testing transactions ", test_df)

    covered = set().union(*(set(group) for group in FEATURE_GROUPS.values()))
    print(f"\nFeature families cover {len(covered)} of {len(FEATURE_COLUMNS)} features")

    results = []
    for name, groups in EXPERIMENTS:
        features = grouped_features(*groups)
        print(f"\nRunning: {name} ({len(features)} features)")
        metrics = fit_and_score(train_df, test_df, features)["metrics"]
        results.append({"model": name, "features": len(features), **metrics})

    results_df = pd.DataFrame(results)
    print("\n===== FEATURE ABLATION RESULTS =====")
    print(
        results_df.to_string(
            index=False,
            columns=["model", "features"] + METRIC_COLUMNS[1:],
            float_format=lambda value: f"{value:.4f}",
        )
    )
    print("\nRead the deltas, not the absolute numbers: synthetic data, one seed.")


if __name__ == "__main__":
    main()

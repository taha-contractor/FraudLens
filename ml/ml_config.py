"""Shared ML contract: paths, feature lists, split helpers and leakage audits.

train_model.py, evaluate_unseen_accounts.py and feature_ablation.py all read
their column definitions from here, so they cannot drift apart on what counts as
a feature. Keeping the leakage guard in one place is the point: a guard that each
script re-implements is a guard that one script eventually forgets.

Scripts are run from the repository root (python ml/train_model.py), which is the
convention the existing scripts already used for their data paths.
"""

import random

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.preprocessing import OneHotEncoder

from feature_engineering import (
    CURRENT_FEATURES,
    FEATURE_DEFINITIONS,
    HISTORY_FEATURES,
    create_features,
)

FEATURES_FILE = "ml/data/fraud_features.csv"

TARGET_COLUMN = "fraudLabel"

# Columns that identify a row or carry the label. None of them may be a feature.
NON_FEATURE_COLUMNS = ["transactionId", "accountId", "timestamp", TARGET_COLUMN]

FEATURE_COLUMNS = CURRENT_FEATURES + HISTORY_FEATURES

CATEGORICAL_FEATURES = ["transactionType", "location"]

NUMERICAL_FEATURES = [
    column for column in FEATURE_COLUMNS if column not in CATEGORICAL_FEATURES
]

# Feature families used by the ablation experiment. The three groups partition
# FEATURE_COLUMNS exactly, which ml/tests/test_ml_config.py enforces, so a new
# feature can never be silently left out of the ablation.
FEATURE_GROUPS = {
    "basic": [
        "amount",
        "transactionHour",
        "isNightTransaction",
        "isHighValue",
        "transactionType",
        "location",
    ],
    "behavioural": [
        "transactionCount",
        "isFirstTransaction",
        "previousTotalAmount",
        "averageAmount",
        "previousMaximumAmount",
        "amountDeviation",
        "exceedsPreviousMaximum",
        "locationNewForAccount",
    ],
    "velocity": [
        "hoursSincePreviousTransaction",
        "transactionsLastHour",
        "transactionsLast24Hours",
        "amountLastHour",
    ],
}

# Evaluation design, kept deliberately simple and documented:
# * temporal split - the first 80% of transactions by time train the model, the
#   remaining 20% are the future the model has to score;
# * account split - 20% of whole accounts are held out, so unseen-account scores
#   measure generalisation to customers the model has never seen.
TEMPORAL_TRAIN_FRACTION = 0.8
ACCOUNT_TEST_FRACTION = 0.2
SPLIT_RANDOM_SEED = 42

# The one classifier used by every experiment in ml/. Deliberately fixed here so
# that an ablation or a split change moves the score, and not a different model.
MODEL_RANDOM_STATE = 42
MODEL_N_ESTIMATORS = 200

# A single feature that separates the classes this well is a leak or a rule that
# was written into the generator, not a learned pattern.
SUSPICIOUS_SINGLE_FEATURE_AUC = 0.85
# A category is only flagged when it is near-deterministic for one class. A mildly
# protective category (DEPOSIT is less often fraud than the base rate) is real
# signal, not leakage, and the audit prints every category rate regardless.
SUSPICIOUS_CATEGORY_PURITY = 0.98
MIN_CATEGORY_SUPPORT = 20


class LeakageError(RuntimeError):
    """Raised when the feature contract or a split integrity rule is violated."""


def load_features(path=FEATURES_FILE):
    """Load the engineered feature file with a parsed timestamp column."""
    frame = pd.read_csv(path)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"])
    return frame


def assert_feature_contract(feature_columns):
    """Fail loudly if a feature list touches the label or an unknown column."""
    if not feature_columns:
        raise LeakageError("feature list is empty")
    forbidden = [
        column for column in feature_columns if column in NON_FEATURE_COLUMNS
    ]
    if forbidden:
        raise LeakageError(
            f"these columns must never be features: {', '.join(forbidden)}"
        )
    unknown = [
        column for column in feature_columns if column not in FEATURE_DEFINITIONS
    ]
    if unknown:
        raise LeakageError(f"features without a documented definition: {', '.join(unknown)}")
    return list(feature_columns)


def grouped_features(*group_names):
    """Combine FEATURE_GROUPS entries, in the order requested."""
    columns = []
    for name in group_names:
        if name not in FEATURE_GROUPS:
            raise KeyError(f"unknown feature group: {name}")
        columns.extend(FEATURE_GROUPS[name])
    return assert_feature_contract(columns)


def temporal_split(frame, train_fraction=TEMPORAL_TRAIN_FRACTION):
    """Split by time. Training rows are never later than evaluation rows."""
    ordered = frame.sort_values(["timestamp", "transactionId"], kind="stable")
    ordered = ordered.reset_index(drop=True)
    cut = int(len(ordered) * train_fraction)
    if cut <= 0 or cut >= len(ordered):
        raise LeakageError("temporal split produced an empty side")
    train_df = ordered.iloc[:cut]
    test_df = ordered.iloc[cut:]
    boundary_train = train_df["timestamp"].max()
    boundary_test = test_df["timestamp"].min()
    if boundary_train > boundary_test:
        raise LeakageError(
            "temporal split leaked the future into training: "
            f"train ends {boundary_train} but test starts {boundary_test}"
        )
    return train_df, test_df, {"cut_index": cut, "boundary": boundary_test}


def account_split(frame, test_fraction=ACCOUNT_TEST_FRACTION, seed=SPLIT_RANDOM_SEED):
    """Split by whole accounts, deterministically, with no account on both sides."""
    accounts = sorted(frame["accountId"].unique())
    shuffled = list(accounts)
    random.Random(seed).shuffle(shuffled)
    cut = int(len(shuffled) * (1 - test_fraction))
    train_accounts = shuffled[:cut]
    test_accounts = shuffled[cut:]
    if set(train_accounts) & set(test_accounts):
        raise LeakageError("an account appears on both sides of the account split")
    train_df = frame[frame["accountId"].isin(train_accounts)]
    test_df = frame[frame["accountId"].isin(test_accounts)]
    overlap = set(train_df["accountId"]) & set(test_df["accountId"])
    if overlap:
        raise LeakageError(f"account overlap between splits: {len(overlap)} accounts")
    return train_df, test_df, {
        "train_accounts": len(train_accounts),
        "test_accounts": len(test_accounts),
        "seed": seed,
    }


def build_preprocessor(feature_columns):
    """One-hot known categoricals, pass numerics through, unknown categories ignored."""
    assert_feature_contract(feature_columns)
    categorical = [
        column for column in feature_columns if column in CATEGORICAL_FEATURES
    ]
    numerical = [column for column in feature_columns if column not in categorical]
    transformers = []
    if categorical:
        transformers.append(
            (
                "categorical",
                OneHotEncoder(handle_unknown="ignore"),
                categorical,
            )
        )
    if numerical:
        transformers.append(("numerical", "passthrough", numerical))
    return ColumnTransformer(transformers=transformers)


def describe_split(name, frame):
    """Class distribution of one side of a split, for honest reporting."""
    total = len(frame)
    fraud = int(frame[TARGET_COLUMN].sum())
    if total:
        print(f"{name}: {total} transactions, {fraud} fraud ({fraud / total:.2%})")
    else:
        print(f"{name}: empty")
    return {"rows": total, "fraud": fraud}


def numeric_feature_auc(frame, feature):
    """ROC-AUC of one numeric feature used alone as a score."""
    values = pd.to_numeric(frame[feature], errors="coerce").to_numpy(dtype=float)
    labels = frame[TARGET_COLUMN].to_numpy()
    if len(set(labels.tolist())) < 2:
        return float("nan")
    return roc_auc_score(labels, values)


def category_purity(frame, feature):
    """Return [(value, support, fraud rate)] for one categorical feature."""
    labels = frame[TARGET_COLUMN]
    rows = []
    for value, subset in frame.groupby(feature):
        support = len(subset)
        rows.append((value, support, float(labels.loc[subset.index].mean())))
    return rows


def audit_feature_leakage(frame, features=None):
    """Flag features that separate the classes on their own.

    Returns {"suspicious_auc": [...], "suspicious_categories": [...]}. A synthetic
    dataset is allowed to be hard; it is not allowed to be tautological.
    """
    features = features or FEATURE_COLUMNS
    suspicious_auc = []
    for feature in features:
        if feature in CATEGORICAL_FEATURES:
            continue
        auc = numeric_feature_auc(frame, feature)
        if auc == auc and max(auc, 1 - auc) >= SUSPICIOUS_SINGLE_FEATURE_AUC:
            suspicious_auc.append((feature, round(auc, 4)))

    suspicious_categories = []
    for feature in CATEGORICAL_FEATURES:
        if feature not in frame.columns:
            continue
        for value, support, rate in category_purity(frame, feature):
            if support >= MIN_CATEGORY_SUPPORT and (
                rate <= 1 - SUSPICIOUS_CATEGORY_PURITY
                or rate >= SUSPICIOUS_CATEGORY_PURITY
            ):
                suspicious_categories.append(
                    (feature, value, support, round(rate, 4))
                )
    return {"suspicious_auc": suspicious_auc, "suspicious_categories": suspicious_categories}


def fit_and_score(train_df, test_df, feature_columns, verbose=False):
    """Train the prototype Random Forest and return the model, metrics and names.

    The preprocessor is fitted on the training side only, so categories that exist
    only in the evaluation side are ignored instead of leaking into the matrix.
    """
    preprocessor = build_preprocessor(feature_columns)
    X_train = preprocessor.fit_transform(train_df[feature_columns])
    X_test = preprocessor.transform(test_df[feature_columns])
    feature_names = preprocessor.get_feature_names_out().tolist()

    model = RandomForestClassifier(
        n_estimators=MODEL_N_ESTIMATORS,
        random_state=MODEL_RANDOM_STATE,
        class_weight="balanced",
        n_jobs=-1,
    )
    model.fit(X_train, train_df[TARGET_COLUMN])

    predictions = model.predict(X_test)
    probabilities = model.predict_proba(X_test)[:, 1]
    y_test = test_df[TARGET_COLUMN]

    metrics = {
        "accuracy": accuracy_score(y_test, predictions),
        "precision": precision_score(y_test, predictions, zero_division=0),
        "recall": recall_score(y_test, predictions, zero_division=0),
        "f1": f1_score(y_test, predictions, zero_division=0),
        "roc_auc": roc_auc_score(y_test, probabilities),
    }
    if verbose:
        print("\n===== CONFUSION MATRIX =====")
        print(confusion_matrix(y_test, predictions))
        print("\n===== CLASSIFICATION REPORT =====")
        print(classification_report(y_test, predictions, digits=4, zero_division=0))
        print("===== ROC-AUC =====")
        print(f"ROC-AUC: {metrics['roc_auc']:.4f}")
    return {
        "model": model,
        "metrics": metrics,
        "probabilities": probabilities,
        "feature_names": feature_names,
    }


# Position bands used to test label/position independence. The previous generator
# made fraud impossible below position 5, which turned transactionCount into a
# label proxy; these bands are how that regression is detected.
POSITION_BANDS = [
    ("0", 0, 0),
    ("1-2", 1, 2),
    ("3-4", 3, 4),
    ("5-9", 5, 9),
    ("10-19", 10, 19),
    ("20+", 20, None),
]


def position_fraud_rates(frame):
    """Fraud rate per transactionCount band.

    Every band, including the first, must contain both classes. A band with a 0%
    or 100% rate means sequence position carries label information.
    """
    rows = []
    for label, low, high in POSITION_BANDS:
        mask = frame["transactionCount"] >= low
        if high is not None:
            mask = mask & (frame["transactionCount"] <= high)
        subset = frame[mask]
        support = len(subset)
        rate = float(subset[TARGET_COLUMN].mean()) if support else float("nan")
        rows.append({"band": label, "support": support, "fraud_rate": rate})
    return rows


def prefix_stability_report(raw_frame, quantiles=(0.4, 0.7, 0.9)):
    """Check that removing the future cannot change a row's features.

    Features are causal if and only if truncating the dataset at any timestamp
    leaves every surviving row's values untouched. Any changed cell is direct
    proof of future information in a feature.
    """
    full = create_features(raw_frame).set_index("transactionId")
    timestamps = full["timestamp"].sort_values()
    raw = raw_frame.copy()
    raw["timestamp"] = pd.to_datetime(raw["timestamp"])
    rows = []
    for quantile in quantiles:
        cutoff = timestamps.iloc[min(int(len(timestamps) * quantile), len(timestamps) - 1)]
        truncated = create_features(raw[raw["timestamp"] <= cutoff])
        surviving = full.loc[truncated["transactionId"], FEATURE_COLUMNS]
        violations = {}
        for feature in FEATURE_COLUMNS:
            expected = pd.to_numeric(surviving[feature], errors="coerce").to_numpy(dtype=float)
            actual = pd.to_numeric(truncated[feature], errors="coerce").to_numpy(dtype=float)
            if np.allclose(expected, actual, rtol=1e-9, atol=1e-9, equal_nan=True):
                continue
            violations[feature] = int(np.sum(expected != actual))
        rows.append({
            "cutoff": cutoff,
            "rows": len(truncated),
            "violating_features": violations,
        })
    return rows

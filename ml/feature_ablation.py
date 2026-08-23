import pandas as pd

from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    precision_score,
    recall_score,
    f1_score,
    roc_auc_score
)


INPUT_FILE = "ml/data/fraud_features.csv"


BASIC_FEATURES = [
    "amount",
    "transactionHour",
    "isNightTransaction",
    "isHighValue",
    "transactionType",
    "location"
]


BEHAVIORAL_FEATURES = [
    "transactionCount",
    "averageAmount",
    "previousMaximumAmount",
    "amountDeviation"
]


VELOCITY_FEATURES = [
    "transactionsLastHour",
    "transactionsLast24Hours",
    "amountLastHour"
]


def train_and_evaluate(
    train_df,
    test_df,
    feature_columns
):

    categorical_features = [
        feature
        for feature in feature_columns
        if feature in [
            "transactionType",
            "location"
        ]
    ]

    numerical_features = [
        feature
        for feature in feature_columns
        if feature not in categorical_features
    ]

    X_train = train_df[
        feature_columns
    ]

    y_train = train_df[
        "fraudLabel"
    ]

    X_test = test_df[
        feature_columns
    ]

    y_test = test_df[
        "fraudLabel"
    ]

    preprocessor = ColumnTransformer(
        transformers=[
            (
                "categorical",
                OneHotEncoder(
                    handle_unknown="ignore"
                ),
                categorical_features
            ),
            (
                "numerical",
                "passthrough",
                numerical_features
            )
        ]
    )

    X_train_processed = (
        preprocessor.fit_transform(X_train)
    )

    X_test_processed = (
        preprocessor.transform(X_test)
    )

    model = RandomForestClassifier(
        n_estimators=200,
        random_state=42,
        class_weight="balanced",
        n_jobs=-1
    )

    model.fit(
        X_train_processed,
        y_train
    )

    predictions = model.predict(
        X_test_processed
    )

    probabilities = model.predict_proba(
        X_test_processed
    )[:, 1]

    return {
        "precision": precision_score(
            y_test,
            predictions,
            zero_division=0
        ),
        "recall": recall_score(
            y_test,
            predictions,
            zero_division=0
        ),
        "f1": f1_score(
            y_test,
            predictions,
            zero_division=0
        ),
        "roc_auc": roc_auc_score(
            y_test,
            probabilities
        )
    }


def main():

    print("Loading dataset...")

    df = pd.read_csv(
        INPUT_FILE
    )

    df["timestamp"] = pd.to_datetime(
        df["timestamp"]
    )

    df = df.sort_values(
        "timestamp"
    ).reset_index(
        drop=True
    )

    split_index = int(
        len(df) * 0.8
    )

    train_df = df.iloc[
        :split_index
    ]

    test_df = df.iloc[
        split_index:
    ]

    print(
        f"Training transactions: "
        f"{len(train_df)}"
    )

    print(
        f"Testing transactions: "
        f"{len(test_df)}"
    )

    experiments = {

        "Basic": BASIC_FEATURES,

        "Basic + Behavioral": (
            BASIC_FEATURES
            + BEHAVIORAL_FEATURES
        ),

        "Basic + Behavioral + Velocity": (
            BASIC_FEATURES
            + BEHAVIORAL_FEATURES
            + VELOCITY_FEATURES
        )
    }

    results = []

    for name, features in experiments.items():

        print(
            f"\nRunning: {name}"
        )

        metrics = train_and_evaluate(
            train_df,
            test_df,
            features
        )

        results.append({
            "Model": name,
            **metrics
        })

    results_df = pd.DataFrame(
        results
    )

    print(
        "\n===== FEATURE ABLATION RESULTS ====="
    )

    print(
        results_df.to_string(
            index=False,
            float_format=lambda x:
                f"{x:.4f}"
        )
    )


if __name__ == "__main__":
    main()
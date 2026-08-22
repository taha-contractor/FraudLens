import pandas as pd

from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    roc_auc_score
)


INPUT_FILE = "ml/data/fraud_features.csv"


def main():
    print("Loading feature dataset...")
    df = pd.read_csv(INPUT_FILE)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)
    print(f"Total transactions: {len(df)}")

    split_index = int(len(df) * 0.8)

    train_df = df.iloc[:split_index]
    test_df = df.iloc[split_index:]

    print(f"Training transactions: {len(train_df)}")
    print(f"Testing transactions: {len(test_df)}")

    feature_columns = [
        "amount",
        "transactionHour",
        "isNightTransaction",
        "isHighValue",
        "transactionCount",
        "averageAmount",
        "previousMaximumAmount",
        "amountDeviation",
        "transactionType",
        "location"
    ]

    target_column = "fraudLabel"

    X_train = train_df[feature_columns]
    y_train = train_df[target_column]
    X_test = test_df[feature_columns]
    y_test = test_df[target_column]

    categorical_features = [
        "transactionType",
        "location"
    ]

    numerical_features = [
        "amount",
        "transactionHour",
        "isNightTransaction",
        "isHighValue",
        "transactionCount",
        "averageAmount",
        "previousMaximumAmount",
        "amountDeviation"
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

    X_train_processed = preprocessor.fit_transform(X_train)
    X_test_processed = preprocessor.transform(X_test)

    print(
        f"Processed training shape: "
        f"{X_train_processed.shape}"
    )
    print(
        f"Processed testing shape: "
        f"{X_test_processed.shape}"
    )

    model = RandomForestClassifier(
        n_estimators=200,
        random_state=42,
        class_weight="balanced",
        n_jobs=-1
    )

    print("\nTraining Random Forest...")
    model.fit(
        X_train_processed,
        y_train
    )
    print("Training completed.")

    predictions = model.predict(
        X_test_processed
    )
    probabilities = model.predict_proba(
        X_test_processed
    )[:, 1]

    print("\n===== CONFUSION MATRIX =====")
    print(
        confusion_matrix(y_test, predictions)
    )

    print("\n===== CLASSIFICATION REPORT =====")
    print(
        classification_report(y_test, predictions, digits=4)
    )

    print("\n===== ROC-AUC =====")
    auc = roc_auc_score(y_test, probabilities)
    print(f"ROC-AUC: {auc:.4f}")

if __name__ == "__main__":
    main()
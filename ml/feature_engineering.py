import pandas as pd


INPUT_FILE = "ml/data/fraud_transactions.csv"
OUTPUT_FILE = "ml/data/fraud_features.csv"


def create_features(df):
    df = df.copy()

    # Convert timestamp
    df["timestamp"] = pd.to_datetime(df["timestamp"])

    # Time-based features
    df["transactionHour"] = df["timestamp"].dt.hour

    df["isNightTransaction"] = (
        (df["transactionHour"] >= 22)
        | (df["transactionHour"] < 6)
    ).astype(int)

    # High-value transaction
    df["isHighValue"] = (
        df["amount"] >= 50000
    ).astype(int)

    # Account behavioral features
    account_stats = (
        df.groupby("accountId")["amount"]
        .agg(
            transactionCount="count",
            averageAmount="mean",
            maximumAmount="max"
        )
        .reset_index()
    )

    df = df.merge(
        account_stats,
        on="accountId",
        how="left"
    )

    # Amount deviation
    df["amountDeviation"] = (
        df["amount"] / df["averageAmount"]
    )

    return df


def main():
    print("Loading dataset...")

    df = pd.read_csv(INPUT_FILE)

    print(f"Original rows: {len(df)}")

    features = create_features(df)

    features.to_csv(
        OUTPUT_FILE,
        index=False
    )

    print("\nFeature engineering completed.")

    print(f"Output rows: {len(features)}")

    print("\nGenerated features:")

    print(
        features[
            [
                "amount",
                "transactionHour",
                "isNightTransaction",
                "isHighValue",
                "transactionCount",
                "averageAmount",
                "maximumAmount",
                "amountDeviation",
                "fraudLabel"
            ]
        ].head()
    )

    print(
        f"\nSaved to: {OUTPUT_FILE}"
    )


if __name__ == "__main__":
    main()
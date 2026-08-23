import pandas as pd

INPUT_FILE = "ml/data/fraud_transactions.csv"
OUTPUT_FILE = "ml/data/fraud_features.csv"

def create_features(df):
    df = df.copy()

    df["timestamp"] = pd.to_datetime(df["timestamp"])

    df = df.sort_values(
        ["accountId", "timestamp"]
    ).reset_index(drop=True)

    df["transactionHour"] = df["timestamp"].dt.hour

    df["isNightTransaction"] = (
        (df["transactionHour"] >= 22)
        | (df["transactionHour"] < 6)
    ).astype(int)

    df["isHighValue"] = (
        df["amount"] >= 50000
    ).astype(int)

    df["transactionCount"] = (
        df.groupby("accountId")
        .cumcount()
    )

    df["previousTotalAmount"] = (
        df.groupby("accountId")["amount"]
        .cumsum()
        - df["amount"]
    )

    df["averageAmount"] = (
        df["previousTotalAmount"]
        / df["transactionCount"]
    )

    df["averageAmount"] = (
        df["averageAmount"]
        .fillna(0)
    )

    df["previousMaximumAmount"] = (
        df.groupby("accountId")["amount"]
        .transform(
            lambda x: x.shift(1).cummax()
        )
    )

    df["previousMaximumAmount"] = (
        df["previousMaximumAmount"]
        .fillna(0)
    )

    df["amountDeviation"] = 0.0

    has_history = df["averageAmount"] > 0

    df.loc[has_history, "amountDeviation"] = (
        df.loc[has_history, "amount"]
        / df.loc[has_history, "averageAmount"]
    )

        # -------------------------------------------------
    # Velocity features
    # -------------------------------------------------

    df["transactionsLastHour"] = 0
    df["transactionsLast24Hours"] = 0
    df["amountLastHour"] = 0.0

    for account_id, account_df in df.groupby("accountId"):

        account_df = account_df.sort_values(
            "timestamp"
        )

        timestamps = (
            account_df["timestamp"]
            .tolist()
        )

        amounts = (
            account_df["amount"]
            .tolist()
        )

        indices = (
            account_df.index.tolist()
        )

        for position in range(
            len(account_df)
        ):

            current_time = timestamps[position]

            one_hour_start = (
                current_time
                - pd.Timedelta(hours=1)
            )

            twenty_four_hour_start = (
                current_time
                - pd.Timedelta(hours=24)
            )

            previous_timestamps = (
                timestamps[:position]
            )

            previous_amounts = (
                amounts[:position]
            )

            transactions_last_hour = 0
            transactions_last_24_hours = 0
            amount_last_hour = 0.0

            for previous_position in range(
                position
            ):

                previous_time = (
                    previous_timestamps[
                        previous_position
                    ]
                )

                previous_amount = (
                    previous_amounts[
                        previous_position
                    ]
                )

                if previous_time >= one_hour_start:
                    transactions_last_hour += 1
                    amount_last_hour += previous_amount

                if previous_time >= twenty_four_hour_start:
                    transactions_last_24_hours += 1

            row_index = indices[position]

            df.loc[
                row_index,
                "transactionsLastHour"
            ] = transactions_last_hour

            df.loc[
                row_index,
                "transactionsLast24Hours"
            ] = transactions_last_24_hours

            df.loc[
                row_index,
                "amountLastHour"
            ] = amount_last_hour

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

    print("\nTemporal feature engineering completed.")

    print(f"Output rows: {len(features)}")

    print("\nGenerated features:")

    print(
        features[
            [
                "transactionId",
                "accountId",
                "amount",
                "transactionHour",
                "isNightTransaction",
                "isHighValue",
                "transactionCount",
                "averageAmount",
                "previousMaximumAmount",
                "amountDeviation",
                "fraudLabel"
            ]
        ].head(10)
    )

    print(
        f"\nSaved to: {OUTPUT_FILE}"
    )

if __name__ == "__main__":
    main()
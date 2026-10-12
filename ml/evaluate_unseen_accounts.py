"""Unseen-account evaluation for the FraudLens fraud classifier.

20% of whole accounts are held out: every transaction of a held-out account is
absent from training. This answers a different question from the temporal split -
not "can the model score the future", but "can it score a customer it has never
seen", which is the situation an investigator faces when a new case arrives.

The account split is deterministic: accounts are sorted, then shuffled with a
fixed seed, so the same 24 accounts are held out on every run. ml_config
raises if any account ends up on both sides.

Historical features stay valid for held-out accounts because they are computed
from the account's own earlier rows only; a held-out account's first transaction
genuinely has no history, which is why isFirstTransaction exists.

This is a research prototype on synthetic data. Nothing here is production ready.
"""

from ml_config import (
    ACCOUNT_TEST_FRACTION,
    FEATURE_COLUMNS,
    SPLIT_RANDOM_SEED,
    TARGET_COLUMN,
    account_split,
    describe_split,
    fit_and_score,
    load_features,
)


def account_level_summary(test_df, probabilities, threshold=0.5):
    """How the held-out accounts fared, which a row-level report hides."""
    scored = test_df.copy()
    scored["predicted"] = probabilities >= threshold
    flagged = scored.groupby("accountId")["predicted"].sum()
    fraud_accounts = (
        scored.groupby("accountId")[TARGET_COLUMN].max().astype(bool)
    )
    clean_accounts = int((~fraud_accounts).sum())
    clean_flagged = int(
        sum(
            1 for account, is_clean in fraud_accounts.items()
            if not is_clean and flagged.get(account, 0) > 0
        )
    )
    detected = int(
        sum(
            1 for account, has_fraud in fraud_accounts.items()
            if has_fraud and flagged.get(account, 0) > 0
        )
    )
    print(f"\n===== ACCOUNT-LEVEL VIEW ({len(fraud_accounts)} held-out accounts) =====")
    print(f"Accounts containing at least one fraud: {int(fraud_accounts.sum())}")
    print(f"Of those, at least one transaction flagged: {detected}")
    print(f"Clean accounts with at least one flag (false alarms): {clean_flagged}")
    print(f"Accounts with no fraud at all: {clean_accounts}")


def main():
    print("Loading feature dataset...")
    df = load_features()
    print(f"Total transactions: {len(df)}")
    print(f"Accounts: {df['accountId'].nunique()}")

    train_df, test_df, split_info = account_split(
        df, test_fraction=ACCOUNT_TEST_FRACTION, seed=SPLIT_RANDOM_SEED
    )
    print("\n===== ACCOUNT SPLIT (unseen customers) =====")
    print(
        f"Training accounts: {split_info['train_accounts']}"
        f"  Held-out accounts: {split_info['test_accounts']}"
        f"  (seed {split_info['seed']})"
    )
    describe_split("Train (seen accounts)  ", train_df)
    describe_split("Test  (unseen accounts) ", test_df)
    print(f"Accounts in test: {test_df['accountId'].nunique()}")

    print("\nTraining Random Forest on seen accounts...")
    result = fit_and_score(train_df, test_df, FEATURE_COLUMNS, verbose=True)
    account_level_summary(test_df, result["probabilities"])
    print("\nReminder: synthetic data, research prototype, not a production model.")


if __name__ == "__main__":
    main()

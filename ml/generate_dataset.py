import csv
import random
from datetime import datetime, timedelta


NUM_TRANSACTIONS = 1000
NUM_ACCOUNTS = 50

RANDOM_SEED = 42

NORMAL_LOCATIONS = [
    "Mumbai",
    "Pune",
    "Nashik",
    "Thane",
    "Navi Mumbai"
]

UNUSUAL_LOCATIONS = [
    "Delhi",
    "Bangalore",
    "Hyderabad",
    "Kolkata",
    "Jaipur"
]

ALL_LOCATIONS = (
    NORMAL_LOCATIONS
    + UNUSUAL_LOCATIONS
)

TRANSACTION_TYPES = [
    "TRANSFER",
    "PAYMENT",
    "WITHDRAWAL",
    "DEPOSIT"
]


def generate_account_normal_transaction(
    transaction_id,
    account_id,
    base_date,
    typical_amount,
    typical_location,
    typical_hour_start,
    typical_hour_end
):
    """
    Generate a legitimate transaction.

    Some legitimate transactions are intentionally
    suspicious-looking so that fraud cannot be
    identified using a single feature.
    """

    behavior_type = random.choice([
        "normal",
        "high_value",
        "night",
        "unusual_location"
    ])

    amount = random.uniform(
        typical_amount * 0.5,
        typical_amount * 1.5
    )

    location = typical_location

    hour = random.randint(
        typical_hour_start,
        typical_hour_end
    )

    if behavior_type == "high_value":
        amount = random.uniform(
            typical_amount * 3,
            typical_amount * 8
        )

    # Legitimate night transaction
    elif behavior_type == "night":
        hour = random.choice([
            0, 1, 2, 3, 4, 5, 23
        ])

        amount = random.uniform(
            typical_amount * 0.7,
            typical_amount * 2
        )

    elif behavior_type == "unusual_location":
        location = random.choice(
            UNUSUAL_LOCATIONS
        )

        amount = random.uniform(
            typical_amount * 0.7,
            typical_amount * 3
        )

    # Small amount variation
    if random.random() < 0.15:
        amount = random.uniform(
            typical_amount * 0.3,
            typical_amount * 2
        )

    timestamp = base_date.replace(
        hour=hour,
        minute=random.randint(0, 59),
        second=random.randint(0, 59)
    )

    return {
        "transactionId": transaction_id,
        "accountId": account_id,
        "amount": round(amount, 2),
        "transactionType": random.choice(
            TRANSACTION_TYPES
        ),
        "location": location,
        "timestamp": timestamp.isoformat(),
        "fraudLabel": 0
    }


def generate_behavioral_fraud_transaction(
    transaction_id,
    account_id,
    base_date,
    typical_amount,
    typical_location
):
    """
    Generate fraud using overlapping behavioral
    patterns instead of one obvious rule.
    """

    fraud_pattern = random.choice([
        "subtle_amount",
        "moderate_amount",
        "location",
        "night",
        "velocity",
        "combined"
    ])

    amount = random.uniform(
        typical_amount * 0.8,
        typical_amount * 2
    )

    location = typical_location

    hour = random.randint(
        8,
        20
    )

    if fraud_pattern == "subtle_amount":

        amount = random.uniform(
            typical_amount * 1.5,
            typical_amount * 3
        )

    elif fraud_pattern == "moderate_amount":

        amount = random.uniform(
            typical_amount * 2,
            typical_amount * 5
        )

    elif fraud_pattern == "location":

        amount = random.uniform(
            typical_amount * 0.8,
            typical_amount * 2.5
        )

        location = random.choice(
            UNUSUAL_LOCATIONS
        )

    elif fraud_pattern == "night":

        amount = random.uniform(
            typical_amount * 0.8,
            typical_amount * 2.5
        )

        hour = random.choice([
            0, 1, 2, 3, 4, 5, 23
        ])

    elif fraud_pattern == "velocity":

        amount = random.uniform(
            typical_amount * 0.8,
            typical_amount * 3
        )

    elif fraud_pattern == "combined":

        amount = random.uniform(
            typical_amount * 2,
            typical_amount * 5
        )

        if random.random() < 0.5:
            location = random.choice(
                UNUSUAL_LOCATIONS
            )

        if random.random() < 0.5:
            hour = random.choice([
                0, 1, 2, 3, 4, 5, 23
            ])

    timestamp = base_date.replace(
        hour=hour,
        minute=random.randint(0, 59),
        second=random.randint(0, 59)
    )

    return {
        "transactionId": transaction_id,
        "accountId": account_id,
        "amount": round(amount, 2),
        "transactionType": random.choice(
            TRANSACTION_TYPES
        ),
        "location": location,
        "timestamp": timestamp.isoformat(),
        "fraudLabel": 1
    }


def generate_dataset():

    random.seed(
        RANDOM_SEED
    )

    transactions = []

    accounts = [
        f"ACC{str(i).zfill(3)}"
        for i in range(
            1,
            NUM_ACCOUNTS + 1
        )
    ]

    start_date = datetime(
        2026,
        1,
        1
    )

    fraud_accounts = set(
        random.sample(
            accounts,
            k=25
        )
    )

    transaction_counter = 1

    for account_id in accounts:

        typical_amount = random.uniform(
            2000,
            8000
        )

        typical_location = random.choice(
            NORMAL_LOCATIONS
        )

        typical_hour_start = random.randint(
            8,
            10
        )

        typical_hour_end = random.randint(
            18,
            21
        )

        account_transactions = random.randint(
            18,
            26
        )

        fraud_transaction_indices = set()

        if account_id in fraud_accounts:

            number_of_fraud_events = random.choice([
                4,
                5,
                6
            ])

            possible_indices = list(
                range(
                    5,
                    account_transactions
                )
            )

            fraud_transaction_indices = set(
                random.sample(
                    possible_indices,
                    min(
                        number_of_fraud_events,
                        len(possible_indices)
                    )
                )
            )

        account_start_date = (
            start_date
            + timedelta(
                days=random.randint(
                    0,
                    30
                )
            )
        )

        current_time = account_start_date

        for transaction_index in range(
            account_transactions
        ):

            transaction_id = (f"TX{str(transaction_counter).zfill(5)}")

            transaction_counter += 1

            time_gap = timedelta(
                hours=random.randint(
                    12,
                    120
                )
            )

            current_time += time_gap

            is_fraud = (
                transaction_index
                in fraud_transaction_indices
            )

            if is_fraud:

                transaction = (
                    generate_behavioral_fraud_transaction(
                        transaction_id,
                        account_id,
                        current_time,
                        typical_amount,
                        typical_location
                    )
                )

            else:

                transaction = (
                    generate_account_normal_transaction(
                        transaction_id,
                        account_id,
                        current_time,
                        typical_amount,
                        typical_location,
                        typical_hour_start,
                        typical_hour_end
                    )
                )

            transactions.append(transaction)

    return transactions


def save_dataset(transactions):

    output_file = ("ml/data/fraud_transactions.csv")

    fieldnames = [
        "transactionId",
        "accountId",
        "amount",
        "transactionType",
        "location",
        "timestamp",
        "fraudLabel"
    ]

    with open(
        output_file,
        "w",
        newline="",
        encoding="utf-8"
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames
        )

        writer.writeheader()
        writer.writerows(transactions)

    print("Dataset generated successfully.")
    print(f"Transactions: {len(transactions)}")
    print(f"Output: {output_file}")

if __name__ == "__main__":
    dataset = generate_dataset()
    save_dataset(dataset)
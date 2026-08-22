import csv
import random
from datetime import datetime, timedelta


NUM_TRANSACTIONS = 1000
NUM_ACCOUNTS = 50

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

TRANSACTION_TYPES = [
    "TRANSFER",
    "PAYMENT",
    "WITHDRAWAL",
    "DEPOSIT"
]


def generate_normal_transaction(
    transaction_id,
    account_id,
    base_date
):
    amount = round(random.uniform(500, 30000), 2)

    if random.random() < 0.85:
        hour = random.randint(7, 21)
    else:
        hour = random.randint(0, 23)

    timestamp = base_date.replace(
        hour=hour,
        minute=random.randint(0, 59),
        second=random.randint(0, 59)
    )

    if random.random() < 0.90:
        location = random.choice(NORMAL_LOCATIONS)
    else:
        location = random.choice(UNUSUAL_LOCATIONS)

    if random.random() < 0.05:
        amount = round(random.uniform(30000, 80000), 2)

    return {
        "transactionId": transaction_id,
        "accountId": account_id,
        "amount": amount,
        "transactionType": random.choice(TRANSACTION_TYPES),
        "location": location,
        "timestamp": timestamp.isoformat(),
        "fraudLabel": 0
    }

def generate_fraud_transaction(
    transaction_id,
    account_id,
    base_date
):
    amount = round(random.uniform(2000, 100000), 2)
    hour = random.randint(0, 23)
    location = random.choice(NORMAL_LOCATIONS)

    fraud_pattern = random.choice([
        "high_amount",
        "night",
        "unusual_location",
        "combined",
        "subtle"
    ])

    if fraud_pattern == "high_amount":
        amount = round(random.uniform(60000, 150000), 2)

    elif fraud_pattern == "night":
        hour = random.choice([
            0, 1, 2, 3, 4, 5, 23
        ])

    elif fraud_pattern == "unusual_location":
        location = random.choice(UNUSUAL_LOCATIONS)

    elif fraud_pattern == "combined":
        amount = round(random.uniform(40000, 120000), 2)

        hour = random.choice([
            0, 1, 2, 3, 4, 5, 23
        ])

        location = random.choice(UNUSUAL_LOCATIONS)

    elif fraud_pattern == "subtle":
        amount = round(random.uniform(5000, 25000), 2)
        hour = random.randint(7, 21)
        location = random.choice(NORMAL_LOCATIONS)

    timestamp = base_date.replace(
        hour=hour,
        minute=random.randint(0, 59),
        second=random.randint(0, 59)
    )

    return {
        "transactionId": transaction_id,
        "accountId": account_id,
        "amount": amount,
        "transactionType": random.choice(TRANSACTION_TYPES),
        "location": location,
        "timestamp": timestamp.isoformat(),
        "fraudLabel": 1
    }

def generate_account_normal_transaction(
    transaction_id,
    account_id,
    base_date,
    typical_amount,
    typical_location,
    typical_hour_start,
    typical_hour_end
):
    amount = round(
        random.uniform(
            typical_amount * 0.5,
            typical_amount * 1.5
        ),
        2
    )

    hour = random.randint(
        typical_hour_start,
        typical_hour_end
    )

    location = typical_location

    if random.random() < 0.10:
        location = random.choice(
            NORMAL_LOCATIONS
        )

    timestamp = base_date.replace(
        hour=hour,
        minute=random.randint(0, 59),
        second=random.randint(0, 59)
    )

    return {
        "transactionId": transaction_id,
        "accountId": account_id,
        "amount": amount,
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
    fraud_pattern = random.choice([
        "amount_anomaly",
        "location_anomaly",
        "night_anomaly",
        "combined_anomaly"
    ])

    amount = typical_amount
    hour = random.randint(8, 20)
    location = typical_location

    if fraud_pattern == "amount_anomaly":
        amount = random.uniform(
            typical_amount * 8,
            typical_amount * 20
        )

    elif fraud_pattern == "location_anomaly":
        amount = random.uniform(
            typical_amount * 1.5,
            typical_amount * 4
        )

        location = random.choice(
            UNUSUAL_LOCATIONS
        )

    elif fraud_pattern == "night_anomaly":
        amount = random.uniform(
            typical_amount * 1.5,
            typical_amount * 4
        )

        hour = random.choice([
            0, 1, 2, 3, 4, 5, 23
        ])

    elif fraud_pattern == "combined_anomaly":
        amount = random.uniform(
            typical_amount * 8,
            typical_amount * 20
        )

        hour = random.choice([
            0, 1, 2, 3, 4, 5, 23
        ])

        location = random.choice(
            UNUSUAL_LOCATIONS
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
        "fraudLabel": 1
    }

def generate_dataset():
    transactions = []

    accounts = [
        f"ACC{str(i).zfill(3)}"
        for i in range(1, NUM_ACCOUNTS + 1)
    ]

    start_date = datetime(2026, 1, 1)

    fraud_accounts = set(
        random.sample(
            accounts,
            k=25
        )
    )

    transaction_counter = 1

    for account_id in accounts:

        typical_amount = random.uniform(
            1000,
            8000
        )

        typical_location = random.choice(
            NORMAL_LOCATIONS
        )

        typical_hour_start = random.randint(
            8,
            11
        )

        typical_hour_end = random.randint(
            18,
            21
        )

        account_transactions = random.randint(
            15,
            30
        )

        fraud_transaction_indices = set()

        if account_id in fraud_accounts:
            number_of_fraud_events = random.choice([
                2,
                3,
                4
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

        for transaction_index in range(
            account_transactions
        ):

            transaction_id = (
                f"TX{str(transaction_counter).zfill(5)}"
            )

            transaction_counter += 1

            transaction_date = (
                start_date
                + timedelta(
                    days=random.randint(0, 180)
                )
            )

            transaction_date += timedelta(
                minutes=transaction_index * random.randint(
                    30,
                    180
                )
            )

            is_fraud = (
                transaction_index
                in fraud_transaction_indices
            )

            if is_fraud:
                transaction = generate_behavioral_fraud_transaction(
                    transaction_id,
                    account_id,
                    transaction_date,
                    typical_amount,
                    typical_location
                )
            else:
                transaction = generate_account_normal_transaction(
                    transaction_id,
                    account_id,
                    transaction_date,
                    typical_amount,
                    typical_location,
                    typical_hour_start,
                    typical_hour_end
                )

            transactions.append(transaction)

    return transactions

def save_dataset(transactions):
    output_file = "ml/data/fraud_transactions.csv"

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

    print(f"Dataset generated successfully.")
    print(f"Transactions: {len(transactions)}")
    print(f"Output: {output_file}")


if __name__ == "__main__":
    dataset = generate_dataset()
    save_dataset(dataset)
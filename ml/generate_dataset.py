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


def generate_normal_transaction(transaction_id, account_id, base_date):
    amount = round(random.uniform(500, 10000), 2)

    hour = random.randint(7, 21)

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
        "location": random.choice(NORMAL_LOCATIONS),
        "timestamp": timestamp.isoformat(),
        "fraudLabel": 0
    }


def generate_fraud_transaction(transaction_id, account_id, base_date):
    fraud_pattern = random.choice([
        "high_amount",
        "night",
        "unusual_location",
        "combined"
    ])

    amount = round(random.uniform(5000, 15000), 2)

    hour = random.randint(7, 21)

    location = random.choice(NORMAL_LOCATIONS)

    if fraud_pattern in ["high_amount", "combined"]:
        amount = round(random.uniform(50000, 200000), 2)

    if fraud_pattern in ["night", "combined"]:
        hour = random.choice([
            0, 1, 2, 3, 4, 5, 23
        ])

    if fraud_pattern in ["unusual_location", "combined"]:
        location = random.choice(UNUSUAL_LOCATIONS)

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


def generate_dataset():
    transactions = []

    accounts = [
        f"ACC{str(i).zfill(3)}"
        for i in range(1, NUM_ACCOUNTS + 1)
    ]

    start_date = datetime(2026, 1, 1)

    for i in range(1, NUM_TRANSACTIONS + 1):

        transaction_id = f"TX{str(i).zfill(5)}"

        account_id = random.choice(accounts)

        transaction_date = start_date + timedelta(
            days=random.randint(0, 180)
        )

        is_fraud = random.random() < 0.15

        if is_fraud:
            transaction = generate_fraud_transaction(
                transaction_id,
                account_id,
                transaction_date
            )
        else:
            transaction = generate_normal_transaction(
                transaction_id,
                account_id,
                transaction_date
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
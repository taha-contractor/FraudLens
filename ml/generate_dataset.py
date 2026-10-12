"""Synthetic transaction generator for the FraudLens ML research prototype.

Produces ml/data/fraud_transactions.csv, the raw input of the ML feature
pipeline. The script is standalone: it never touches the Node.js backend.

Design rules, enforced by ml/tests/test_generate_dataset.py:

1. No label/position coupling. Fraud episodes are placed uniformly over an
   account's whole history - including its very first episode - so a sequence
   position feature (transactionCount) cannot carry label information. The
   previous generator confined fraud to position >= 5, which made
   "transactionCount >= 5" a guaranteed necessary condition for fraud.
2. Realistic velocity. Activity is generated as *episodes*: one transaction, or
   a burst of several transactions minutes apart. Both legitimate accounts
   (payday clusters, travel bookings) and fraudulent ones (card testing, account
   draining) produce bursts, so velocity is a signal without being a rule. The
   previous generator spaced every transaction 12-120 hours apart, which left
   transactionsLastHour non-zero in 1 row out of 1109.
3. Fraud is not trivially predictable. Legitimate rows deliberately reproduce
   suspicious-looking behaviour (high value, night hours, unusual location,
   bursts) and fraudulent rows deliberately include ordinary amounts and
   ordinary hours. Every observable dimension of the two classes overlaps, so no
   single feature separates them.
4. Reproducibility. Every random draw comes from one random.Random instance
   created per run, so a given seed always produces the same dataset.
5. Timestamps strictly increase per account. A required hour is reached by
   advancing to the next occurrence of that hour instead of rewriting a
   timestamp in place, and every emitted row is checked against its predecessor.

Output columns are the ML-side contract, unchanged from the previous version:
transactionId, accountId, amount, transactionType, location, timestamp,
fraudLabel. The label is decided before any observable value is drawn and is
never written into a feature column. Timestamps are naive local times, read as
Asia/Kolkata (the timezone used by the backend analytics layer); no offset is
stored.
"""

import argparse
import csv
import random
from datetime import datetime, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"
OUTPUT_FILE = DATA_DIR / "fraud_transactions.csv"

RANDOM_SEED = 42
NUM_ACCOUNTS = 120

# Episodes per account (an episode is one transaction or one burst). Burst
# episodes add transactions, so an account's transaction count is a little
# higher than its episode count.
MIN_EPISODES_PER_ACCOUNT = 18
MAX_EPISODES_PER_ACCOUNT = 35

# Hours of quiet between two episodes of the same account.
MIN_EPISODE_GAP_HOURS = 12
MAX_EPISODE_GAP_HOURS = 120

# Minutes between the transactions of one burst episode.
MIN_BURST_GAP_MINUTES = 2
MAX_BURST_GAP_MINUTES = 15

# Chance that a legitimate episode is a burst, and its size.
LEGIT_BURST_PROBABILITY = 0.08
LEGIT_BURST_MIN_SIZE = 2
LEGIT_BURST_MAX_SIZE = 4

# History window. Accounts start at different moments so that a global temporal
# split cuts through the middle of every account's history instead of separating
# early-life from late-life behaviour.
HISTORY_START = datetime(2026, 1, 1, 6, 0, 0)
HISTORY_SPREAD_DAYS = 21

NORMAL_LOCATIONS = ["Mumbai", "Pune", "Nashik", "Thane", "Navi Mumbai"]
UNUSUAL_LOCATIONS = ["Delhi", "Bangalore", "Hyderabad", "Kolkata", "Jaipur"]
ALL_LOCATIONS = NORMAL_LOCATIONS + UNUSUAL_LOCATIONS

TRANSACTION_TYPES = ["TRANSFER", "PAYMENT", "WITHDRAWAL", "DEPOSIT"]

# Night hours under the backend definition (hour >= 22 or hour < 6).
NIGHT_HOURS = [0, 1, 2, 3, 4, 5, 23]

# Relative weight of each hour of the day for ordinary activity. Real banking is
# a daytime activity, so night is genuinely uncommon (~7% of hours) instead of an
# artefact of uniform time drift; the explicit night patterns below then create
# legitimate night look-alikes on purpose.
HOUR_WEIGHTS = [
    1, 1, 1, 1, 1, 1,          # 00-05
    3, 6, 9, 10,               # 06-09
    12, 12, 12, 12, 12, 12, 12, 12,  # 10-17
    11, 9, 8, 6, 4, 2,         # 18-23
]
ALL_HOURS = list(range(24))

# The analytics layer calls anything >= 50000 high value. Both classes are drawn
# across that boundary so that crossing it is never equivalent to being fraud.
HIGH_VALUE_LOOKALIKE_RANGE = (35000, 140000)
FRAUD_MODERATE_RANGE = (25000, 90000)

# Account roles: (name, weight, isolated fraud episodes, fraud burst episodes,
# fraud burst size). The mix keeps the overall fraud rate near 10% and leaves
# about a third of the accounts completely clean, which is what makes
# unseen-account evaluation meaningful.
ACCOUNT_ROLES = [
    ("clean", 0.30, (0, 0), (0, 0), (0, 0)),
    ("isolated", 0.33, (2, 3), (0, 0), (0, 0)),
    ("repeat", 0.22, (4, 7), (0, 0), (0, 0)),
    ("burst", 0.15, (0, 1), (1, 2), (4, 8)),
]

# Legitimate behaviour mix. "routine" is the account's ordinary pattern; the rest
# are the look-alikes that stop any single feature from being a fraud rule.
LEGIT_BEHAVIOURS = [
    ("routine", 0.55),
    ("high_value", 0.14),
    ("night", 0.11),
    ("unusual_location", 0.10),
    ("small_amount", 0.10),
]

# Behaviour of an isolated (non-burst) fraudulent transaction. Fraud patterns that
# are not explicitly anomalous are indistinguishable from routine activity.
FRAUD_BEHAVIOURS = [
    ("fraud_subtle_amount", 0.22),
    ("fraud_moderate_amount", 0.20),
    ("fraud_location", 0.16),
    ("fraud_night", 0.16),
    ("fraud_combined", 0.14),
    # A fraudulent transaction that looks entirely ordinary: the dataset does not
    # guarantee that every fraud is behaviourally anomalous.
    ("fraud_ordinary", 0.12),
]

# Behaviour inside a fraudulent burst.
FRAUD_BURST_KINDS = ["fraud_card_testing", "fraud_account_draining"]

# Location mix of an ordinary episode: home city, another normal city, and
# occasionally an unusual city, because people travel.
LOCATION_WEIGHTS = [("home", 0.75), ("normal", 0.20), ("unusual", 0.05)]

# transactionType mixes. Families share types, so type is never decisive alone.
TYPE_MIXES = {
    "everyday": [
        ("PAYMENT", 0.45),
        ("TRANSFER", 0.25),
        ("DEPOSIT", 0.20),
        ("WITHDRAWAL", 0.10),
    ],
    "transfer_heavy": [("TRANSFER", 0.50), ("WITHDRAWAL", 0.25), ("PAYMENT", 0.25)],
    "small_payment": [("PAYMENT", 0.70), ("TRANSFER", 0.30)],
    "card_testing": [("PAYMENT", 0.60), ("TRANSFER", 0.40)],
}

# Behaviour -> (type mix, amount kind, hour kind). One row per behaviour name, so
# the generator and the documentation agree on a single table. Hour kind "any"
# keeps whatever time the account clock has reached.
PATTERN_RULES = {
    # Legitimate.
    "routine": ("everyday", "typical", "any"),
    "high_value": ("transfer_heavy", "high_value_lookalike", "any"),
    "night": ("everyday", "typical", "night"),
    "unusual_location": ("everyday", "typical", "any"),
    "small_amount": ("small_payment", "small", "any"),
    # Fraudulent, isolated.
    "fraud_subtle_amount": ("everyday", "subtle", "any"),
    "fraud_moderate_amount": ("transfer_heavy", "moderate", "any"),
    "fraud_location": ("everyday", "typical", "any"),
    "fraud_night": ("transfer_heavy", "typical", "night"),
    "fraud_combined": ("transfer_heavy", "moderate", "night"),
    "fraud_ordinary": ("everyday", "typical", "any"),
    # Fraudulent, inside a burst.
    "fraud_card_testing": ("card_testing", "card_testing", "any"),
    "fraud_account_draining": ("transfer_heavy", "drain", "any"),
}

# Behaviour -> location kind. Kept separate because location is resolved once per
# episode (a burst happens in one place).
PATTERN_LOCATIONS = {
    "unusual_location": "unusual",
    "fraud_location": "unusual",
    "fraud_combined": "unusual",
    "fraud_card_testing": "unusual",
}

COLUMNS = [
    "transactionId",
    "accountId",
    "amount",
    "transactionType",
    "location",
    "timestamp",
    "fraudLabel",
]


def _weighted_choice(rng, options):
    """Pick a key from a [(key, weight)] list using the weights."""
    total = sum(weight for _, weight in options)
    pick = rng.uniform(0, total)
    accumulator = 0.0
    for key, weight in options:
        accumulator += weight
        if pick <= accumulator:
            return key
    return options[-1][0]


def _next_occurrence(cursor, hour):
    """First instant strictly after `cursor` whose local hour is `hour`."""
    hours_ahead = (hour - cursor.hour - 1) % 24 + 1
    return cursor + timedelta(hours=hours_ahead)


def _advance_to_hour(rng, cursor, hours, weights=None):
    """Move the clock forward to the next occurrence of a drawn hour.

    `hours` is the candidate set; `weights` applies to it when given. The clock is
    only ever moved forward, so a required hour can never reorder a history.
    """
    hour = rng.choices(hours, weights=weights, k=1)[0]
    return _next_occurrence(cursor, hour)


def _account_profile(rng):
    """Static behaviour of an account, drawn independently of its fraud role.

    Independence matters: if a home location or a typical amount decided whether
    an account had fraud, account-level proxies would leak the label.
    """
    return {
        "typical_amount": rng.uniform(1500, 9000),
        # A fifth of accounts legitimately bank away from their home city, so an
        # unusual location is not equivalent to fraud.
        "home_location": rng.choice(
            NORMAL_LOCATIONS if rng.random() < 0.80 else UNUSUAL_LOCATIONS
        ),
    }


def _plan_episodes(rng, role):
    """Return the account's episode plan in time order.

    Each episode is {"label", "pattern", "size"}. Fraud episodes are placed at
    positions sampled uniformly over the whole history, so position 0 can be
    fraudulent and no position is guaranteed legitimate.
    """
    _, _, isolated_range, burst_range, burst_size_range = role
    n_episodes = rng.randint(MIN_EPISODES_PER_ACCOUNT, MAX_EPISODES_PER_ACCOUNT)

    n_isolated = rng.randint(*isolated_range)
    n_bursts = rng.randint(*burst_range)
    n_isolated = min(n_isolated, n_episodes - n_bursts)

    fraud_positions = rng.sample(range(n_episodes), n_isolated + n_bursts)
    burst_positions = set(rng.sample(fraud_positions, n_bursts)) if n_bursts else set()
    isolated_positions = set(fraud_positions) - burst_positions

    episodes = []
    for position in range(n_episodes):
        if position in burst_positions:
            episodes.append({
                "label": 1,
                "pattern": rng.choice(FRAUD_BURST_KINDS),
                "size": rng.randint(*burst_size_range),
            })
        elif position in isolated_positions:
            episodes.append({
                "label": 1,
                "pattern": _weighted_choice(rng, FRAUD_BEHAVIOURS),
                "size": 1,
            })
        else:
            size = (
                rng.randint(LEGIT_BURST_MIN_SIZE, LEGIT_BURST_MAX_SIZE)
                if rng.random() < LEGIT_BURST_PROBABILITY
                else 1
            )
            episodes.append({
                "label": 0,
                "pattern": _weighted_choice(rng, LEGIT_BEHAVIOURS),
                "size": size,
            })
    return episodes


def _episode_location(rng, profile, pattern):
    """Choose the single location used by every transaction of one episode."""
    if PATTERN_LOCATIONS.get(pattern) == "unusual":
        return rng.choice(UNUSUAL_LOCATIONS)
    choice = _weighted_choice(rng, LOCATION_WEIGHTS)
    if choice == "home":
        return profile["home_location"]
    if choice == "normal":
        return rng.choice(NORMAL_LOCATIONS)
    return rng.choice(UNUSUAL_LOCATIONS)


def _episode_amount(rng, profile, kind, position, size):
    """Draw the amount of one transaction inside an episode."""
    typical = profile["typical_amount"]
    if kind == "typical":
        raw = rng.gauss(typical, 0.25 * typical)
    elif kind == "small":
        raw = rng.uniform(40, 400)
    elif kind == "high_value_lookalike":
        raw = rng.uniform(*HIGH_VALUE_LOOKALIKE_RANGE)
    elif kind == "subtle":
        raw = typical * rng.uniform(0.9, 1.6)
    elif kind == "moderate":
        raw = rng.uniform(*FRAUD_MODERATE_RANGE)
    elif kind == "card_testing":
        # Small probes, then one larger take at the end of the burst.
        raw = (
            rng.uniform(1000, 8000)
            if position == size - 1
            else rng.uniform(10, 150)
        )
    elif kind == "drain":
        # A shrinking share of one large pot.
        pot = typical * rng.uniform(3, 10)
        decay = max(0.1, 1.0 - 0.15 * position)
        raw = pot * decay * rng.uniform(0.55, 0.85)
    else:
        raise ValueError(f"unknown amount kind: {kind}")
    return round(max(10.0, raw), 2)


def _build_account_rows(rng, account_id, profile, episodes, started_at):
    """Materialise one account's episode plan into timestamped rows."""
    rows = []
    cursor = started_at

    for episode in episodes:
        pattern = episode["pattern"]
        type_key, amount_key, hour_key = PATTERN_RULES[pattern]
        size = episode["size"]

        # Quiet period before the episode.
        cursor += timedelta(
            hours=rng.uniform(MIN_EPISODE_GAP_HOURS, MAX_EPISODE_GAP_HOURS)
        )
        # An episode always starts at a plausible hour: night patterns pick a
        # night hour, everything else follows the daytime-weighted clock. Time is
        # only ever added, never rewritten in place, so the account clock stays
        # strictly increasing.
        cursor = _advance_to_hour(
            rng,
            cursor,
            NIGHT_HOURS if hour_key == "night" else ALL_HOURS,
            None if hour_key == "night" else HOUR_WEIGHTS,
        )
        location = _episode_location(rng, profile, pattern)

        for position in range(size):
            if position:
                # Burst members are minutes apart. An episode that starts inside
                # a night hour may run past the hour boundary; that is realistic
                # and is left alone rather than rewriting the clock backwards.
                cursor += timedelta(
                    minutes=rng.uniform(MIN_BURST_GAP_MINUTES, MAX_BURST_GAP_MINUTES)
                )
            timestamp = cursor.replace(microsecond=0)
            if rows and timestamp <= rows[-1]["timestamp"]:
                raise AssertionError(
                    f"{account_id}: clock did not advance at {timestamp}"
                )
            rows.append({
                "accountId": account_id,
                "amount": _episode_amount(rng, profile, amount_key, position, size),
                "transactionType": _weighted_choice(rng, TYPE_MIXES[type_key]),
                "location": location,
                "timestamp": timestamp,
                "fraudLabel": episode["label"],
            })
    return rows


def generate_dataset(seed=RANDOM_SEED, num_accounts=NUM_ACCOUNTS):
    """Return the full transaction list for one run of the generator."""
    rng = random.Random(seed)
    all_rows = []

    for account_number in range(1, num_accounts + 1):
        account_id = f"ACC{account_number:03d}"
        profile = _account_profile(rng)
        role_name = _weighted_choice(
            rng, [(name, weight) for name, weight, *_ in ACCOUNT_ROLES]
        )
        role = next(detail for detail in ACCOUNT_ROLES if detail[0] == role_name)
        episodes = _plan_episodes(rng, role)
        started_at = HISTORY_START + timedelta(
            days=rng.uniform(0, HISTORY_SPREAD_DAYS),
            hours=rng.uniform(0, 6),
        )
        all_rows.extend(
            _build_account_rows(rng, account_id, profile, episodes, started_at)
        )

    # Ids follow emission order: account order, then time order within an account.
    for index, row in enumerate(all_rows, start=1):
        row["transactionId"] = f"TX{index:05d}"
    return [{column: row[column] for column in COLUMNS} for row in all_rows]


def write_dataset(rows, output_file=OUTPUT_FILE):
    """Write the dataset, normalising timestamps to the ISO second format."""
    output_file = Path(output_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        for row in rows:
            record = dict(row)
            record["timestamp"] = row["timestamp"].isoformat(timespec="seconds")
            writer.writerow(record)


def _is_night(timestamp):
    return timestamp.hour >= 22 or timestamp.hour < 6


def _rate(subset, predicate):
    if not subset:
        return 0.0
    return sum(1 for row in subset if predicate(row)) / len(subset)


def summarise(rows):
    """Print the dataset properties this milestone has to report."""
    total = len(rows)
    fraud_rows = [row for row in rows if row["fraudLabel"] == 1]
    legit_rows = [row for row in rows if row["fraudLabel"] == 0]

    by_account = {}
    for row in rows:
        by_account.setdefault(row["accountId"], []).append(row)

    rapid = 0
    for members in by_account.values():
        members = sorted(members, key=lambda item: item["timestamp"])
        rapid += sum(
            1 for previous, current in zip(members, members[1:])
            if current["timestamp"] - previous["timestamp"] < timedelta(hours=2)
        )

    counts = [len(members) for members in by_account.values()]
    clean_accounts = sum(
        1 for members in by_account.values()
        if all(row["fraudLabel"] == 0 for row in members)
    )
    night_rate_legit = _rate(legit_rows, lambda row: _is_night(row["timestamp"]))
    night_rate_fraud = _rate(fraud_rows, lambda row: _is_night(row["timestamp"]))
    high_rate_legit = _rate(legit_rows, lambda row: row["amount"] >= 50000)
    high_rate_fraud = _rate(fraud_rows, lambda row: row["amount"] >= 50000)
    first_position_fraud = sum(
        1 for members in by_account.values()
        if sorted(members, key=lambda item: item["timestamp"])[0]["fraudLabel"] == 1
    )

    print(f"Accounts: {len(by_account)}")
    print(f"Transactions: {total}")
    print(
        f"Fraud: {len(fraud_rows)} ({len(fraud_rows) / total:.1%})"
        f"  Legitimate: {len(legit_rows)}"
    )
    print(f"Transactions per account: min {min(counts)} max {max(counts)}")
    print(f"Accounts with no fraud at all: {clean_accounts}")
    print(f"Accounts whose very first transaction is fraudulent: {first_position_fraud}")
    print(f"Rapid follow-ons (under 2 hours): {rapid}")
    print(f"Night rate legit/fraud: {night_rate_legit:.3f} / {night_rate_fraud:.3f}")
    print(
        f"High value (>= 50000) rate legit/fraud: "
        f"{high_rate_legit:.3f} / {high_rate_fraud:.3f}"
    )


def main():
    parser = argparse.ArgumentParser(
        description="Generate the synthetic FraudLens ML dataset."
    )
    parser.add_argument("--seed", type=int, default=RANDOM_SEED)
    parser.add_argument("--accounts", type=int, default=NUM_ACCOUNTS)
    parser.add_argument("--out", default=str(OUTPUT_FILE))
    args = parser.parse_args()

    print(f"Generating synthetic dataset (seed={args.seed})...")
    rows = generate_dataset(seed=args.seed, num_accounts=args.accounts)
    write_dataset(rows, args.out)
    summarise(rows)
    print(f"Saved to: {args.out}")


if __name__ == "__main__":
    main()

# FraudLens — ML Dataset, Features and Evaluation Protocol

## 1. Overview

This document describes the machine-learning side of FraudLens: the synthetic
transaction dataset, the features derived from it, and the protocol used to
evaluate a fraud classifier on it.

The purpose is a credible research foundation, not a shipped model. The dataset
is synthetic. The classifier is a scikit-learn Random Forest used as a reference
implementation. Nothing in this layer writes to MongoDB, and the Node.js backend
does not call it yet.

The Python layer is standalone:

```
generate_dataset.py  ->  ml/data/fraud_transactions.csv
feature_engineering.py -> ml/data/fraud_features.csv
train_model.py / evaluate_unseen_accounts.py / feature_ablation.py
audit_leakage.py      -> leakage and causality evidence
```

All scripts are run from the repository root.

```
python ml/generate_dataset.py
python ml/feature_engineering.py
python ml/audit_leakage.py
python ml/train_model.py
python ml/evaluate_unseen_accounts.py
python ml/feature_ablation.py
ml\.venv\Scripts\python.exe -m unittest discover -s ml/tests -t ml/tests
```

Environment used to produce the committed datasets: Python 3.13.7, pandas 3.0.5,
numpy 2.5.2, scikit-learn 1.9.0. Dataset and feature CSVs are generated artifacts
and are ignored by Git; they are rebuilt from the seed.

---

## 2. Dataset design

### 2.1 Schema

`ml/data/fraud_transactions.csv` is the ML-side contract, one row per transaction:

| Column | Meaning |
| --- | --- |
| `transactionId` | `TX00001`, sequential in emission order |
| `accountId` | `ACC001`, an account owns a contiguous block of rows |
| `amount` | Transaction amount, two decimals, single currency |
| `transactionType` | `TRANSFER`, `PAYMENT`, `WITHDRAWAL`, `DEPOSIT` |
| `location` | City name |
| `timestamp` | Naive local time, ISO seconds, read as Asia/Kolkata |
| `fraudLabel` | 1 = fraudulent, 0 = legitimate |

The field names deliberately match the FraudLens transaction schema so that a
later import from MongoDB does not need a translation layer. `status`,
`currency` and `caseId` are not modelled yet (see section 7).

### 2.2 Activity is generated as episodes

An account's history is a sequence of **episodes**. An episode is either a single
transaction, or a **burst** of several transactions that are 2–15 minutes apart.
Episodes are separated by 12–120 quiet hours.

| Episode kind | Size | Who produces it |
| --- | --- | --- |
| Single | 1 | Everyone |
| Legitimate burst | 2–4, 8% of legitimate episodes | Payday clusters, travel bookings |
| Fraud burst: card testing | 4–8 | Small probes, then one larger take |
| Fraud burst: account draining | 4–8 | A shrinking share of one large pot |

This is what makes the velocity features non-degenerate. In the previous
generator every transaction was 12–120 hours apart, so `transactionsLastHour` was
0 for 1108 of 1109 rows and carried no information.

### 2.3 Account roles

Roles decide only *how much* fraud an account experiences. They never decide its
home city or its typical amount, because an account-level proxy would leak the
label.

| Role | Weight | Isolated fraud episodes | Fraud bursts |
| --- | --- | --- | --- |
| clean | 0.30 | 0 | 0 |
| isolated | 0.33 | 2–3 | 0 |
| repeat | 0.22 | 4–7 | 0 |
| burst | 0.15 | 0–1 | 1–2 of size 4–8 |

About a third of accounts have no fraud at all, which is what makes the
unseen-account evaluation in section 6.2 meaningful.

### 2.4 Fraud placement

Fraud episodes are placed at positions sampled **uniformly over the whole
history**, including position 0.

The previous generator only allowed fraud from position 5 onwards. That made
`transactionCount >= 5` a guaranteed necessary condition for fraud: measured on
the old dataset, `P(fraud | position < 5) = 0.0`. Any model trained on it learned
a sequence-position rule that the generator had written in.

### 2.5 Behaviour patterns and deliberate overlap

Every observable of a transaction (amount, hour, location, type) is drawn from a
behaviour pattern. Legitimate patterns include suspicious-looking behaviour, and
fraudulent patterns include ordinary behaviour.

Legitimate mix: routine 55%, high_value 14%, night 11%, unusual_location 10%,
small_amount 10%.

Isolated fraud mix: subtle_amount 22%, moderate_amount 20%, location 16%,
night 16%, combined 14%, ordinary 12%.

Hour of day for ordinary activity is drawn from a daytime-weighted distribution,
so night is genuinely uncommon rather than an artefact of uniform time drift.

Measured overlap on the committed dataset (seed 42, 120 accounts):

| Dimension | Legitimate | Fraud |
| --- | --- | --- |
| Night rate (hour >= 22 or < 6) | 0.172 | 0.259 |
| Amount >= 50 000 | 0.126 | 0.131 |

Both classes contain high-value rows, night rows, unusual-location rows and
bursts. No single observable is a fraud rule.

### 2.6 Reproducibility

One `random.Random(seed)` instance drives every draw, so a seed reproduces the
dataset exactly. `--seed`, `--accounts` and `--out` are exposed on the command
line. The default seed is 42; regenerating it twice produces identical output
(3703 rows, same values).

---

## 3. Feature definitions

`feature_engineering.py` adds 18 documented features. Each one carries an
availability promise. `CURRENT` features describe the transaction being scored.
`HISTORY` features are built only from transactions that happened **strictly
before** it, on the same account. `FEATURE_DEFINITIONS` in the module is the
single source of truth; `ml_config.FEATURE_GROUPS` partitions the same list.

### 3.1 Current-transaction features (CURRENT)

| Feature | Definition |
| --- | --- |
| `amount` | Transaction amount. |
| `transactionHour` | Hour of day, 0–23, local time. |
| `isNightTransaction` | 1 when `transactionHour >= 22` or `< 6`. |
| `isHighValue` | 1 when `amount >= 50000`. Absolute rule, matching the analytics layer. |
| `transactionType` | Categorical. |
| `location` | Categorical. |

### 3.2 Historical features (HISTORY)

| Feature | Definition |
| --- | --- |
| `transactionCount` | Number of earlier transactions on this account. 0 for the first one. |
| `isFirstTransaction` | 1 when there is no earlier transaction, so history-dependent aggregates are knowingly empty. |
| `previousTotalAmount` | Sum of all earlier amounts on this account. |
| `averageAmount` | `previousTotalAmount / transactionCount`, 0 without history. |
| `previousMaximumAmount` | Largest earlier amount, 0 without history. |
| `amountDeviation` | `amount / averageAmount`, 0 without a positive average. |
| `exceedsPreviousMaximum` | 1 when the amount beats every earlier amount of the account. |
| `hoursSincePreviousTransaction` | Elapsed hours since the account's previous transaction. 0 for the first transaction; read with `isFirstTransaction`. |
| `locationNewForAccount` | 1 when this location never appeared earlier on the account. |
| `transactionsLastHour` | Earlier transactions of the account within the preceding hour. |
| `transactionsLast24Hours` | Earlier transactions of the account within the preceding 24 hours. |
| `amountLastHour` | Sum of the earlier amounts within the preceding hour. |

Windowed counts and sums are **exclusive of the transaction being scored**. The
`amountLastHour` of an account's first transaction is therefore 0 even when its
amount is large; an implementation that included the current row would inflate
velocity for exactly the transactions that need it most.

Rows are sorted by `(accountId, timestamp, transactionId)` before anything is
computed, so tied timestamps cannot reorder a history.

---

## 4. Leakage safeguards

Four independent checks, implemented in `ml_config.py` and asserted by the tests:

**1. Position independence.** `position_fraud_rates()` reports the fraud rate per
`transactionCount` band. Every populated band must contain both classes.
Measured on the committed dataset:

| Band | Rows | Fraud rate |
| --- | --- | --- |
| 0 | 120 | 0.1000 |
| 1–2 | 240 | 0.0833 |
| 3–4 | 240 | 0.1125 |
| 5–9 | 600 | 0.0967 |
| 10–19 | 1194 | 0.1214 |
| 20+ | 1309 | 0.0917 |

Base rate is 0.103. `transactionCount` used alone reaches AUC 0.494, which is
noise.

**2. Prefix stability.** Truncate the dataset at several cutoffs and recompute.
If any surviving row's features change, that feature used the future. All three
cutoffs (40%, 70%, 90% of the timeline) report zero violating features, and the
same check is run specifically for the temporal split, so training rows are not
recomputed differently in the presence of test rows.

**3. Single-feature separation.** `audit_feature_leakage()` computes the ROC-AUC
of each numeric feature used as the only score. Threshold: `max(AUC, 1-AUC) >=
0.85` is flagged. Measured maximum is `transactionsLastHour` at 0.584.

**4. Category purity.** A categorical value is flagged when it is near
-deterministic for one class (>= 98% with at least 20 rows). No category is
flagged. Weakly informative categories do exist and are printed by the audit:
`DEPOSIT` is 3.9% fraud against a 10.3% base rate, and unusual cities sit higher
than home cities (Kolkata 26.8%, Mumbai 7.0%). These are real signals, not rules.

`assert_feature_contract()` additionally refuses any feature list that contains
the target or an identifier column, and any feature without a documented
definition. `audit_leakage.py` prints all of this evidence.

---

## 5. Dataset produced by the committed configuration

| Property | Value |
| --- | --- |
| Accounts | 120 |
| Transactions | 3703 |
| Fraud | 382 (10.32%) |
| Legitimate | 3321 |
| Transactions per account | 18–48 |
| Accounts with no fraud | 45 |
| Accounts whose first transaction is fraudulent | 12 |
| Rapid follow-ons (under 2 hours) | 570 |
| Features | 18 (6 CURRENT, 12 HISTORY) |

---

## 6. Evaluation protocol

One classifier is used everywhere: `RandomForestClassifier(n_estimators=200,
class_weight="balanced", random_state=42)`. It is fixed in `ml_config` so that a
change in score reflects a change in data or features, not a different model.
Categorical columns are one-hot encoded by a preprocessor fitted on the training
side only, with `handle_unknown="ignore"`.

### 6.1 Temporal split

`train_model.py` sorts transactions by time and trains on the first 80%, scoring
the last 20%. A random row split is not used: it would let the model train on
transactions that happened after the one it is being tested on.

Measured with seed 42: split boundary `2026-03-24 10:11:25`; train 2962 rows with
311 fraud (10.50%), test 741 rows with 71 fraud (9.58%); 88 accounts appear on
both sides, which is expected — a customer's history spans the boundary.

Results at the default 0.5 threshold: ROC-AUC 0.7571, precision 0.9167 on the
fraud class, recall 0.1549.

### 6.2 Unseen-account split

`evaluate_unseen_accounts.py` holds out 20% of **whole accounts**, shuffled with a
fixed seed, so no account appears on both sides. This answers a different question:
can the model score a customer it has never seen, which is the situation when a new
case arrives.

Measured: 96 training accounts, 24 held-out; train 2924 rows with 287 fraud
(9.82%), test 779 rows with 95 fraud (12.20%). ROC-AUC 0.7440, precision 0.7000,
recall 0.1474. At account level, 12 of the 20 held-out accounts containing fraud
had at least one transaction flagged, and 1 of the 4 clean held-out accounts had a
false alarm.

### 6.3 Feature ablation

`feature_ablation.py` compares nested feature families on the temporal split.

| Feature set | Features | ROC-AUC | Precision | Recall | F1 |
| --- | --- | --- | --- | --- | --- |
| Basic | 6 | 0.7344 | 0.3125 | 0.3521 | 0.3311 |
| Basic + Behavioral | 14 | 0.6748 | 0.0000 | 0.0000 | 0.0000 |
| Basic + Behavioral + Velocity | 18 | 0.7618 | 0.8462 | 0.1549 | 0.2619 |

The families are not additive at a fixed 0.5 threshold: with behavioural features
the model stops predicting fraud at all while its ranking (AUC 0.6748) stays above
chance. Ranking metrics and the threshold must be read separately. This is treated
as a finding to investigate, not as an improvement to chase.

---

## 7. Limitations

**Synthetic only.** Every pattern comes from the generator's own tables. A model
trained here validates the pipeline, not real-world fraud.

**Not production ready.** No calibration, no probability threshold selection, no
class-imbalance strategy beyond `class_weight="balanced"`, no hyper-parameter
search, no drift monitoring.

**Low recall is the honest result.** Fraud is deliberately not separable by any
single rule, so the classifier catches few frauds at 0.5. No accuracy target was
set or optimised for.

**Naive timestamps.** Times are local (Asia/Kolkata) without an offset. A real
import from MongoDB stores UTC instants, so hour-of-day and night features must
be derived with the same timezone conversion the Node analytics layer uses.

**Single currency, no status.** Amounts are summed across the dataset without a
currency dimension, and there is no `PENDING`/`FAILED`/`REVERSED` status, so the
ML layer cannot yet apply the "completed transactions only" rule that the
analytics layer uses.

**Account-scoped history only.** There are no counterparty, merchant, device or
network features, so the "new destination" style of signal is not modelled.
`locationNewForAccount` is the only novelty feature.

**Small sample.** 3703 rows and 382 fraud examples are enough for a prototype and
not enough for reliable absolute scores; the deltas between runs of the same
configuration are larger than the third decimal place suggests.

**Unused local files.** `ml/data/train_identity.csv` and
`ml/data/train_transaction.csv` (IEEE-CIS style data) exist on disk, are ignored
by Git, and are not read by any script in this milestone.

**No backend integration.** Nothing is exposed through the API, no risk score is
persisted, and the `riskScore` / `riskLevel` / `modelPrediction` fields described
in the database design remain unwritten.

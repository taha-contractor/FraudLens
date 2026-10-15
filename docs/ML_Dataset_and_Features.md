# FraudLens — ML Dataset, Features and Evaluation

This document describes the machine-learning data and evaluation foundation of FraudLens:
the synthetic **PaySim** dataset, the 17 features derived from it, the evaluation protocol,
and the winning model's measured performance. Pipeline mechanics and reproduction
commands live in [`../ml/README.md`](../ml/README.md); this document is the reference for
*what* is modelled and *how* it is evaluated.

> **Everything here is synthetic.** The dataset is generated from the PaySim mobile-money
> simulator. The metrics validate the pipeline end-to-end; they are **not** real-world
> fraud-detection accuracy, and no number here should be presented as demonstrated
> performance on real financial crime.

The pipeline is implemented under `ml/src/` and its output — an XGBoost model at
`ml/artifacts/m5/winner_model.joblib` — **is served in production** by the FastAPI
[`ml-service/`](../ml-service/) and persisted per case by the Node backend. (Earlier
revisions of this document described a standalone Random-Forest toy that has since been
replaced; that content is no longer accurate.)

---

## 1. Dataset

### 1.1 Source (read-only)

The original PaySim download lives in `ml/data/raw/` and is treated as an **immutable
reference**: it is never modified, and all derived data is written under
`ml/data/processed/`. Raw and processed CSVs are **Git-ignored** (regenerable, large).

### 1.2 PaySim limitations (motivating the enhanced dataset)

The raw simulator has structural problems that make it a poor fraud-dataset on its own:

- **L1 — Fraud-type concentration.** Fraud labels exist only for `TRANSFER` and
  `CASH_OUT`, so a model can learn the artifact "fraud ⇒ type ∈ {TRANSFER, CASH_OUT}".
- **L2 — Near-absent account histories.** Origins are ~unique per transaction, so
  per-account velocity/history features cannot be derived; context is limited to reused
  destinations.
- **L3 — Balance inconsistency.** Post-transaction balances frequently violate the debit
  identity, so `oldbalance*`/`newbalance*` are unreliable as ground truth.
- **L4 — No transaction relationships.** No explicit linkage between related transactions
  (e.g. a fraud TRANSFER→CASH_OUT chain) and no stable recurring account identity.
- **L5 — Severe class imbalance** (~0.13%) with temporal prevalence shift.

### 1.3 Enhanced (generated) dataset

A reproducible, **config-driven synthetic generator** (`ml/src/generator/`) addresses these
by producing a population of accounts with **recurring, time-ordered histories**, explicit
legitimate and fraud **scenario** templates per transaction type, linked multi-step
**chains** under a shared `chain_id`, ledger-consistent balances, and fraud spread across
**all five types**. Full design and rationale:
[`../ml/reports/Enhanced_PaySim_Dataset_Design.md`](../ml/reports/Enhanced_PaySim_Dataset_Design.md).

- **Provenance is a separate table** (`provenance.csv`) that is never merged into the
  feature matrix, so *original-derived* and *generated* rows stay distinguishable (used in
  the diagnostics in §4.3).
- The **model feature matrix** is `ml/data/processed/model_matrix_v1.csv` — **8,362,620
  rows**, overall fraud rate **0.82%**.

---

## 2. Features (17, fixed order)

The model consumes exactly these 17 features, in this order
(`ml/artifacts/m5/feature_names.json`):

```
step, amount, oldbalanceOrg,
type_PAYMENT, type_CASH_IN, type_CASH_OUT, type_TRANSFER, type_DEBIT,
origin_txn_count_prev, origin_avg_amount_prev, origin_amount_dev_prev,
origin_time_since_prev_txn, origin_txn_last24h, origin_amount_last24h,
origin_unique_dests_last24h, dest_txn_count_prev, dest_unique_origins_prev
```

### 2.1 Current-transaction features

| Feature | Meaning |
|---|---|
| `step` | Day ordinal (time index) |
| `amount` | Transaction amount |
| `oldbalanceOrg` | Originator balance before the transaction |
| `type_*` (5) | One-hot over the PaySim taxonomy (PAYMENT, CASH_IN, CASH_OUT, TRANSFER, DEBIT) |

### 2.2 Historical / velocity features (strictly-prior causal)

Nine `origin_*` and `dest_*` features describe account history — prior transaction counts,
average amount, amount deviation, time since last transaction, last-24h counts/amounts,
and unique-counterparty novelty. They are computed by `ml/src/features/causal.py`
(`CausalFeatureBuilder`) with a **strictly-prior causal pass**: for each row, aggregates
use only records **strictly earlier** in time for that key — never the current row and
never any future row or label.

This single causal builder is the **source of truth reused online**: `ml-service` imports
it to reconstruct these nine features from the transactions the backend sends, so online
scoring cannot drift from training-time features. It also requires the caller to supply a
transaction's relevant prior history (the service replays it in causal order), not just the
row being scored.

### 2.3 Leakage safeguards

- **No identifiers/target in the matrix** — provenance and label columns are excluded.
- **Causal ordering** — the `(step, ts, uid)` key makes history computation lookahead-free.
- **Type one-hot integrity** — an unmappable transaction type is *not* silently defaulted;
  it is reported **unscored** (§5).

---

## 3. Evaluation protocol

Evaluation is **chronological** by `step`: train precedes validation precedes test, so no
model ever trains on the future. Selection is done **on validation only** (PR-AUC primary);
the test set is evaluated **exactly once**. Authoritative numbers:
`ml/reports/m5/experiment_manifest.json`, `final_test_report.json`, `finalize_summary.json`.

### 3.1 Splits

| Split | Rows | Max step | Fraud prevalence |
|---|---|---|---|
| Train | 5,924,380 | 500 | 0.63% |
| Validation | 426,935 | 620 | 2.09% |
| Test | 337,071 | — | 2.70% |

A 20% **unseen-destination holdout** (seed 42) measures generalization to counterparties
never seen during training.

### 3.2 Model selection

Multiple gradient-boosting candidates were compared on validation PR-AUC. The winner is
**`xgb_full`** (a single `XGBClassifier`); a soft-vote ensemble with HistGradientBoosting
improved validation PR-AUC by **less than 0.02**, so the simpler single model was chosen.

| Setting | Value |
|---|---|
| Winner | `xgb_full` (XGBClassifier) |
| Operating threshold | **0.95** |
| max_depth / learning_rate / n_estimators | 10 / 0.05 / 600 |
| scale_pos_weight | ~158.75 |
| early_stopping_rounds / seed | 50 / 42 |
| Full-train rows | 5,000,000 (cap) |
| Needs scaling | no |

---

## 4. Results (experimental, synthetic data)

### 4.1 Validation (selection)

PR-AUC **0.714**, ROC-AUC **0.991**, F1@threshold **0.631**.

### 4.2 Final held-out test (evaluated once)

| Metric | Value |
|---|---|
| PR-AUC | **0.648** |
| ROC-AUC | **0.985** |
| Precision @ 0.95 | 0.360 |
| Recall @ 0.95 | 0.920 |
| F1 @ 0.95 | 0.517 |
| Accuracy | 0.954 |
| False-positive rate | 0.045 |
| Flag rate | 6.9% |
| Confusion | TP 8,362 · FP 14,882 · FN 728 · TN 313,099 |

### 4.3 Generalization & diagnostics

- **Unseen-destination:** PR-AUC 0.594, ROC-AUC 0.990, precision 0.438, recall 0.719,
  F1 0.544.
- **By origin** (original-derived vs generated) and **by transaction type** are reported in
  `final_test_report.json`; e.g. `TRANSFER` is the best-separated type (precision 0.524,
  recall 0.976) and original-derived rows score with high precision (0.963) at lower recall
  (0.787). These breakdowns show the signal is not uniform across types/provenance.

The operating point deliberately favours **recall over precision** (0.95 threshold): it
catches most fraud at the cost of false alerts, consistent with an *investigation aid*
that a human reviews rather than an automated decision.

---

## 5. Serving & risk bands

The winning model is served by [`ml-service/`](../ml-service/README.md) and consumed by the
backend's risk-assessment workflow (`backend/src/services/risk-assessment.service.js`).
Scores map to risk bands on the frozen threshold:

- **HIGH** — `score ≥ 0.95`
- **MEDIUM** — `0.50 ≤ score < 0.95` (triage aid only, not a fraud determination)
- **LOW** — `score < 0.50`

**Never silently low-risk:** a transaction whose type cannot be mapped to the taxonomy (or
whose amount is non-numeric) is returned **unscored** (`risk_score: null`) with an explicit
reason; a genuine inference failure surfaces as an error. Scores are persisted with the
exact feature vector and model metadata on the transaction.

---

## 6. Limitations

- **Synthetic only** — patterns come from the generator's own tables; no real-world
  accuracy is established.
- **Artificial prevalence** — 0.82%–2.7% class ratios make precision/recall and flag rates
  dataset-specific; thresholds do not transfer to production.
- **Recall-favouring operating point** — high recall with modest precision at 0.95.
- **Feature availability at inference** — the nine history features require the transaction's
  prior history to be present; the backend supplies a bounded, case-scoped window
  (`ML_ASSESS_MAX_TRANSACTIONS`).
- **PaySim semantics** — `oldbalanceOrg` is optional in ingestion and defaults to `0.0` with
  an explicit gap flag when absent; `step` is derived from the timestamp's day.
- **No real fraud signals** — no IP, device fingerprint, geo-velocity or mule-graph features;
  a higher PR-AUC here does not prove real-world effectiveness.

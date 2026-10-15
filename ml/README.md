# FraudLens `ml/` — PaySim ML Pipeline

This directory is the **operational machine-learning pipeline** for FraudLens. It covers
the full path from an immutable raw dataset to a trained, evaluated XGBoost model whose
artifact is served by the separate [`ml-service/`](../ml-service/) inference API.

The pipeline is complete through model selection and evaluation (**milestones M1–M5**):
a winning XGBoost model exists at `artifacts/m5/winner_model.joblib`, and the FraudLens
backend **is integrated** with it through the FastAPI service. Risk scores are persisted
to MongoDB per case (see `backend/src/services/risk-assessment.service.js`).

> **PaySim is synthetic mobile-money data.** It must never be described as real banking
> data, and these metrics must never be presented as real-world fraud-detection accuracy.

## Scope

- **This directory is exclusively the PaySim pipeline.** The earlier India Benchmark V1
  research line (Phase 1) lived separately under `ml_experiments/`; that directory has
  been removed during repository cleanup, and its findings are preserved as a static
  summary in [`docs/ml-research/phase-1/README.md`](../docs/ml-research/phase-1/README.md).
  Do not mix that research's results with PaySim results — different data, different
  leakage profile, different provenance.

## Directory layout

```text
ml/
├── data/
│   ├── raw/            # Original PaySim download — immutable, read-only (gitignored)
│   ├── processed/      # Generated datasets + model feature matrix (gitignored)
│   │   ├── enhanced/         # validated pilot dataset
│   │   ├── enhanced_full/    # full-scale enhanced dataset + provenance
│   │   └── model_matrix_v1.csv  # 17-feature training matrix (8.36M rows)
│   └── splits/         # generated split assignments (gitignored)
├── src/
│   ├── data/           # read-only chunked PaySim loader
│   ├── generator/      # deterministic synthetic generator (config, accounts, scenarios,
│   │                   #   chains, emitter, provenance, validation gates, CSV pipeline/cli)
│   ├── features/       # strictly-prior causal feature builder, matrix assembly, splits, audit
│   ├── modeling/       # dataset, evaluation, model registry
│   ├── evaluation/     # metrics / protocols
│   ├── training/       # training helpers
│   └── inference/      # scoring helpers reused by ml-service
├── tests/              # Python unittest suite (M1–M5)
├── artifacts/
│   └── m5/             # winner_model.joblib + feature_names.json + winner_config.json
├── reports/
│   ├── Enhanced_PaySim_Dataset_Design.md
│   └── m5/             # experiment manifest, final test report, finalize summary, logs
├── *_m5.py             # M5 pipeline entry points (matrix, train/eval, finalize, validate)
└── README.md
```

Empty directories are held open with `.gitkeep`. **Large generated CSVs and the model
binary are intentionally Git-ignored** (see the repo `.gitignore`); the small feature/
config contracts (`feature_names.json`, `winner_config.json`) and JSON reports stay tracked.

## Dataset & provenance

- **Read-only source:** the original PaySim download in `data/raw/` is kept byte-for-byte
  and never modified; all derived data is written to `data/processed/`.
- **Enhanced dataset:** a reproducible, config-driven **synthetic generator**
  (`src/generator/`) reduces PaySim's known limitations (fraud concentrated in only two
  types, near-absent per-account history, balance inconsistencies, no linked chains) by
  generating accounts with recurring histories, explicit legitimate/fraud scenarios,
  linked chains, consistent balances, and dual feature policies. Design rationale and the
  full limitation analysis are in
  [`reports/Enhanced_PaySim_Dataset_Design.md`](reports/Enhanced_PaySim_Dataset_Design.md).
- **Provenance** is written to a **separate table** (`provenance.csv`) and never merged
  into the feature matrix, so generated rows remain distinguishable from original-derived
  rows (this split is used in the diagnostics below).
- Generated datasets and the model matrix are **regenerable from the seed** and are not
  committed. Reproduction does not require any dataset to be in Git.

## Feature contract (17 features, fixed order)

The model consumes exactly these 17 features, in this order (`artifacts/m5/feature_names.json`):

```
step, amount, oldbalanceOrg,
type_PAYMENT, type_CASH_IN, type_CASH_OUT, type_TRANSFER, type_DEBIT,
origin_txn_count_prev, origin_avg_amount_prev, origin_amount_dev_prev,
origin_time_since_prev_txn, origin_txn_last24h, origin_amount_last24h,
origin_unique_dests_last24h, dest_txn_count_prev, dest_unique_origins_prev
```

Historical/velocity features are built by the **strictly-prior causal pass**
(`src/features/causal.py`): for each row, aggregates use only records strictly earlier in
time for the relevant key (origin or destination). No future rows and no future labels
are ever visible — this is the property that lets the same builder be reused online by
`ml-service` without scoring drift. The order and definition are frozen; the inference
service reuses this exact implementation.

## Evaluation splits

Evaluation is **chronological** by `step` (train before validation before test), so no
model ever trains on the future. From `reports/m5/experiment_manifest.json`:

| Split | Rows | Max step | Fraud prevalence |
|---|---|---|---|
| Train | 5,924,380 | 500 | 0.63% |
| Validation | 426,935 | 620 | 2.09% |
| Test | 337,071 | — | 2.70% |

A 20% **unseen-destination holdout** (seed 42) additionally measures generalization to
counterparties never seen in training. Overall matrix prevalence is 0.82% (8,362,620 rows).

## Winning model

Selected on **validation PR-AUC only** (test evaluated exactly once). The winner is
**`xgb_full`** (a single `XGBClassifier`); a soft-vote ensemble with HistGradientBoosting
gained less than 0.02 PR-AUC, so the single model was chosen.

| Setting | Value |
|---|---|
| Winner | `xgb_full` (XGBClassifier) |
| Decision threshold | **0.95** (operating point) |
| max_depth / learning_rate / n_estimators | 10 / 0.05 / 600 |
| scale_pos_weight | ~158.75 |
| early_stopping_rounds / seed | 50 / 42 |
| Full-train rows | 5,000,000 (cap) |
| Needs scaling | no |

## Metrics (experimental, on synthetic PaySim)

**Validation** (selection): PR-AUC **0.714**, ROC-AUC **0.991**, F1@threshold 0.631.

**Final held-out test** (evaluated once, `reports/m5/final_test_report.json`):

| Metric | Value |
|---|---|
| PR-AUC | 0.648 |
| ROC-AUC | 0.985 |
| Precision @ 0.95 | 0.360 |
| Recall @ 0.95 | 0.920 |
| F1 @ 0.95 | 0.517 |
| Accuracy | 0.954 |
| Flag rate | 6.9% |

**Unseen-destination generalization:** PR-AUC 0.594, ROC-AUC 0.990, precision 0.438,
recall 0.719, F1 0.544.

Authoritative numbers live in `reports/m5/` (`final_test_report.json`,
`finalize_summary.json`, `experiment_manifest.json`); per-type and per-origin diagnostics
are in `final_test_report.json`.

## Limitations & honest framing

- **Synthetic only.** All patterns originate from the generator's own tables. These
  metrics validate the pipeline end-to-end; they do **not** establish real-world fraud
  detection accuracy.
- **Artificial prevalence.** The 0.82%–2.7% class ratios and the resulting precision/recall
  are dataset-specific; thresholds do not transfer to production.
- **High recall / modest precision.** At threshold 0.95 the model favours catching fraud
  over minimizing false alerts — an investigation aid, not an automatic decision.
- **Experimental ≠ demonstrated.** Everything above is measured on generated data; none of
  it should be presented as demonstrated performance on real financial crime.

## Reproducing the pipeline (does not require committing data)

All commands run from the repo root with the ML source on `PYTHONPATH`:

```powershell
$env:PYTHONPATH="ml/src"

# Run the pipeline test suite (M1-M5)
python -m unittest discover -s ml/tests -t ml/tests

# Rebuild the 17-feature model matrix from the enhanced dataset
python ml/build_matrix_m5.py

# Train + evaluate candidate models (Stage 1/2) and finalize the winner (M5)
python ml/train_eval_m5.py
python ml/finalize_m5.py        # writes artifacts/m5/ and reports/m5/

# Validate the full generated dataset
python ml/validate_full_dataset.py
```

The generated CSVs under `data/` and `winner_model.joblib` are Git-ignored; regenerate
them locally. `feature_names.json` and `winner_config.json` are committed and define the
served contract.

## How the inference service consumes the model

[`ml-service/`](../ml-service/) loads `artifacts/m5/winner_model.joblib` **once** at
startup and imports the causal builder from `ml/src` (`ML_SRC_PATH`). The Node backend
sends an already case-scoped set of transactions; the service replays them through the
same builder to reconstruct the 17 features, scores them, and returns a probability and
risk label per transaction. Because the service reuses `ml/src`, online features cannot
silently diverge from training-time features. See [`ml-service/README.md`](../ml-service/README.md).

# FraudLens Benchmark Harness — Methodology

> **Archive note.** This document describes the **India Benchmark V1** harness that lived
> in `ml_experiments/` (Phase 1). That directory — including `benchmark_lib.py`,
> `benchmark_models.py`, `test_benchmark_lib.py` and the benchmark dataset — has been
> **removed during repository cleanup**. The paths and module names below refer to that
> archived harness and are kept as a **methodology record** (split protocols,
> validation-only thresholding, ablation discipline, integrity checks) that informed the
> operational PaySim pipeline in [`ml/`](../ml/). The Phase-1 findings are summarized in
> [`ml-research/phase-1/README.md`](ml-research/phase-1/README.md). This document does
> **not** report current model results.

The archived harness was separate from the legacy flat scripts (`ml_config.py`,
`feature_engineering.py`, `train_model.py`, `evaluate_unseen_accounts.py`,
`feature_ablation.py`, `audit_leakage.py`) that preceded the current `ml/src/` pipeline;
those were also removed. The harness never imported them.

---

## 1. Dataset provenance and integrity

| Property | Value |
| --- | --- |
| File | `benchmark_transactions.csv` (India Benchmark V1; archived with `ml_experiments/`, consumed read-only) |
| Origin | Fully synthetic, India-based banking / digital-payments benchmark |
| Rows × columns | 20,000 × 34 |
| Target | `fraudLabel` — 12,000 legitimate (0) / 8,000 fraudulent (1) |
| Accounts | 1,000 (`ACC0001`–`ACC1000`), 7–34 transactions each |
| Currency | `INR` on every row (constant) |
| Window | Jan–Jun 2026; timestamps are ISO-8601 **UTC** with an explicit `Z` |
| Expected SHA-256 | `0240c060d03ca223a21112da71c0cdb15b347cfce1076ac366c4aaf40b516049` (4,345,868 bytes) |

`verify_checksum()` streams the file's SHA-256 and raises `SchemaError` on any
mismatch; `load_benchmark()` calls it by default. `verify_schema()` compares the
header to the exact 34-column `EXPECTED_HEADER` and refuses added, removed or
reordered columns, so a silently changed dataset stops the harness instead of
slipping through.

Provenance and validation detail for the dataset itself lives in
`ml/data/DATA_DICTIONARY.md` and `ml/data/DATASET_VALIDATION.md`. The 60:40 class
ratio is a controlled experimental choice and does **not** represent real-world
fraud prevalence.

## 2. Feature contract

Target: `fraudLabel`. Feature matrix: **27 columns**.

Excluded (in `NON_FEATURE_COLUMNS`) and why:

| Column | Reason |
| --- | --- |
| `transactionId` | surrogate key; also a time proxy (assigned in timestamp order) |
| `accountId` | identifier; kept on the frame only for the account-grouped split |
| `beneficiaryId` | high-cardinality payee identifier |
| `deviceId` | high-cardinality device identifier |
| `timestamp` | raw instant; used only to order rows, never a feature |
| `currency` | constant (`INR`) → zero information |
| `fraudLabel` | the target |

Included — numeric (22): `amount`, `transactionHour`, `dayOfWeek`, `isWeekend`,
`isNightTransaction`, `accountAgeDays`, `transactionsLastHour`,
`transactionsLast24Hours`, `amountLastHour`, `amountLast24Hours`,
`previousAverageAmount`, `previousMaximumAmount`, `amountDeviation`,
`previousTotalAmount`, `uniqueBeneficiariesLast24Hours`,
`beneficiaryTransactionCount`, `failedTransactionsLastHour`, `isNewBeneficiary`,
`isNewDevice`, `isNewLocation`, `isInternationalTransaction`, `balanceBefore`.

Included — categorical (5): `transactionType`, `channel`, `merchantCategory`,
`location`, `status`.

`FEATURE_COLUMNS ∪ NON_FEATURE_COLUMNS == EXPECTED_HEADER` (enforced by a test),
so no column is silently dropped from or added to the contract.

**Historical and calendar features are taken verbatim.** The dataset already
ships validated strictly-prior aggregates (`transactionsLastHour`,
`amountLastHour`, `previousAverageAmount`, `balanceBefore`, the `isNew*` flags,
etc.) and the calendar/night columns in **Indian Standard Time**. The harness uses
them as-is and never recomputes them from the UTC `timestamp`; recomputing
`transactionHour`/`isNightTransaction` from the UTC instant would contradict the
dataset's documented IST semantics (a fixed `+05:30`, no DST). The parsed UTC time
is kept only as a non-feature ordering key (`eventTimeUtc`).

Runtime assertions in `validate_feature_contract()`: the target exists and is
strictly binary; no identifier or the target appears in the feature list; every
feature is present; no missing cells reach an estimator; categoricals are
non-numeric and numerics are numeric. Violations raise `SchemaError`.

## 3. Split methodology

Splits are identical for every model within a protocol; only estimator
`random_state` changes across seeds.

**Chronological (train / validation / test = 60 / 20 / 20).** Rows are ordered by
`(eventTimeUtc, transactionId)` and cut at index `int(n·0.60)` and `int(n·0.80)`
(`int()` truncation, row-count based → deterministic). Ordering guarantees every
training instant precedes validation, which precedes test. Each partition must
contain both classes or `SplitError` is raised. On the frozen file: 12,000 rows
(4,725 fraud, 39.4%), 4,000 (1,584, 39.6%), 4,000 (1,691, 42.3%).

**Unseen-account (grouped, deterministic).** Account IDs are sorted, put into a
reproducible order via `np.random.RandomState(seed=42).permutation`, and split
60/20/20 **by whole accounts** (train 600 / validation 200 / test 200). No account
appears on two sides — enforced by an explicit overlap check that raises. A
held-out account contributes all of its rows, so the test side is genuinely
unseen. This is not a random row split.

`load_benchmark` / splits are exercised read-only in the tests; no model is fit on
the real dataset by the test suite.

## 4. Preprocessing rules

`make_preprocessor(scale_numerics)` builds a `ColumnTransformer`:

- **Numerics:** `StandardScaler` when `scale_numerics=True` (Logistic Regression,
  both SVMs, KNN), otherwise `"passthrough"` (tree / boosting models — no
  unnecessary scaling).
- **Categoricals:** `OneHotEncoder(handle_unknown="ignore")`. Low-cardinality
  fields only; identifiers are never encoded. Unknown categories in
  validation/test encode to an all-zero row rather than raising or leaking.
- Output stays **sparse**; nothing is densified. One-hot width is small (~80
  columns), so per-estimator memory is not a concern.

Every preprocessing step is fitted on **training data only**; validation and test
reuse the training-fitted transform (asserted by comparing scaler means in the
tests). Model pipelines are `Pipeline([preprocess, model])`, so a fold's fit never
sees another fold.

## 5. Model registry and dependency availability

Ten configurations run on installed packages (verified in `ml\.venv`):

| # | Model | Backend | Scaling | Score type |
| --- | --- | --- | --- | --- |
| 1 | Logistic Regression | scikit-learn 1.9.0 | yes | probability |
| 2 | Decision Tree | scikit-learn | no | probability |
| 3 | Random Forest (200) | scikit-learn | no | probability |
| 4 | Extra Trees (200) | scikit-learn | no | probability |
| 5 | XGBoost (200) | xgboost 3.4.1 | no | probability |
| 6 | LightGBM (200) | lightgbm 4.7.0 | no | probability |
| 7 | HistGradientBoosting | scikit-learn | no | probability |
| 8 | Linear SVM | scikit-learn `LinearSVC` | yes | decision_function |
| 9 | RBF SVM | scikit-learn `SVC(kernel='rbf')` | yes | decision_function |
| 10 | K-Nearest Neighbors (k=5) | scikit-learn | yes | probability |

Baseline hyperparameters are fixed and documented (e.g. `class_weight="balanced"`
where supported; XGBoost uses its default objective; `n_estimators=200`). No
hyperparameter search is performed. `build_registry()` returns only *unfitted*
pipelines.

**Unavailable, recorded not run:** CatBoost (`catboost` not installed) and
Explainable Boosting Machine (`interpret` not installed). They appear in
`UNAVAILABLE_MODELS` with the reason; nothing was installed to add them.

**Scoring.** `continuous_scores()` returns a continuous fraud score for ranking
metrics and thresholding: it uses `predict_proba` and selects the fraud column via
`pipeline.classes_` (label-order safe) when available, otherwise falls back to
`decision_function` (the SVM variants). An estimator with neither raises
`MetricError` — the harness never silently substitutes hard 0/1 labels for a
ranking score.

## 6. Metrics and threshold selection

`classification_metrics()` computes, with **fraud (label 1) as the positive
class**: precision, recall, F1, PR-AUC (`average_precision_score`), ROC-AUC
(`roc_auc_score`), accuracy, prevalence, and the confusion matrix plus explicit
true/false positives and **false positives / false negatives**. It also returns
**training time** and **inference time** (measured in the runner with
`time.perf_counter`). Ranking metrics use the continuous score, not thresholded
labels.

Undefined metrics are surfaced, not hidden: no predicted positives → precision
`nan` with a warning; no actual positives → recall `nan`; single-class truth →
ROC-AUC and PR-AUC `nan` with a warning. `nan` propagates into aggregates rather
than being masked as `0.0`.

**Threshold.** `select_threshold()` runs on **validation scores only** and returns
the cutoff maximising validation F1 (ties → lower threshold). This is a
**provisional comparison criterion**, not an operational threshold. The chosen
cutoff is then applied unchanged to the held-out test scores via
`apply_threshold()`. No threshold, feature or model choice is ever taken from test
labels. The runner reports the selected threshold and the validation
precision/recall/F1 next to the final test metrics.

## 7. Seed policy

Documented seeds `[0, 1, 2]` set estimator `random_state`; splits stay fixed across
them. Per-seed results are reported individually and also averaged — predictions
are never pooled across seeds or splits and described as one independent test.
Nine of the ten models accept a seed; **K-Nearest Neighbors is deterministic** and
is run once rather than padded with identical "seeds" (`SEED_POLICY`). A run's
effective configuration is what varies, not the data.

## 8. How to run (later, not part of this build)

```
ml\.venv\Scripts\python.exe ml/benchmark_models.py --protocol chronological
ml\.venv\Scripts\python.exe ml/benchmark_models.py --protocol account
ml\.venv\Scripts\python.exe ml/benchmark_models.py --protocol chronological --json
```

The comparison has **not** been executed as part of implementing the harness.

## 9. Testing

`ml/tests/test_benchmark_lib.py` (39 cases) covers feature/target separation,
identifier exclusion, chronological ordering and both-class presence, account
grouping with zero overlap and determinism, training-only preprocessing and
unknown-category handling, FP/FN correctness, PR-AUC/ROC-AUC and single-class
handling, validation-only threshold selection, `predict_proba` vs
`decision_function` scoring, registry contents and unavailable models, schema
change detection, and real-dataset checksum verification. Unit tests use small
in-memory fixtures; the only real-file access is read-only checksum/header.

Run:

```
ml\.venv\Scripts\python.exe -m unittest discover -s ml/tests -t ml/tests
```

## 10. Known limitations

- Synthetic, hand-patterned data; a strong score shows harness competence, not
  real-world fraud-detection performance. The 60:40 ratio is not production
  prevalence.
- The dataset's strongest single feature (`amountLastHour`, univariate AUC ~0.74)
  is velocity; a velocity-only configuration may simply fit the burst asymmetry
  baked in at generation.
- Fixed baselines and a provisional max-F1 threshold are a starting comparison
  basis, not a tuned or operational setting; thresholds tuned on 60:40 will not
  transfer to a real, far rarer positive class.
- One-hot on `location`/`merchantCategory` learns a product/geography prior
  (`NOT_APPLICABLE` is confounded with transaction type); `transactionId`/`accountId`
  are excluded so no identifier leaks in.
- IST calendar features are consumed, never recomputed; any consumer that re-derives
  them from UTC will get different values.
- Splits assume the single stored UTC offset; multi-currency or multi-region data
  is out of scope.

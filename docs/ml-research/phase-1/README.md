# FraudLens ML Research — Phase 1 Summary (India Benchmark V1)

Phase 1 covers the **India Benchmark V1** synthetic-dataset research line. This document
is a **static summary** of that completed, superseded research phase.

> **Archive note.** The Phase-1 working directory `ml_experiments/` (harness, experiments,
> raw results, data and virtual environment) was **removed during repository cleanup** and
> is no longer in the tree. The findings are preserved here, and the reusable evaluation
> methodology is documented in [`docs/Benchmark_Methodology.md`](../../Benchmark_Methodology.md).
> The **PaySim pipeline (Phase 2) is now the operational ML line** under
> [`ml/`](../../../ml/) — trained, evaluated and integrated with the backend — and its
> results are strictly separate from the India findings below. Do not mix the two result
> sets.

---

## 1. India Benchmark V1 dataset

| Property | Value |
|---|---|
| File | `benchmark_transactions.csv` (India Benchmark V1 release copy; archived with `ml_experiments/`) |
| SHA-256 | `0240c060d03ca223a21112da71c0cdb15b347cfce1076ac366c4aaf40b516049` |
| Size / shape | 4,345,868 bytes · 20,000 rows × 34 columns |
| Currency / window | INR · Jan–Jun 2026 |
| Accounts | 1,000 |
| Classes | 12,000 legitimate / 8,000 fraud (**60 / 40**, `fraudLabel`) |
| Model inputs | 27 features (22 numeric + 5 categorical); identifiers/target/currency excluded |
| History features | strictly-prior, per-account causal pass (velocity, amount history, balance) |

Synthetic and India-focused. It **overwrote an earlier US-shaped benchmark in place**
(SHA-256 `0cc8b99b…108ce`) that is **not recoverable from Git** (the CSV path is
Git-ignored); the release copy preserved the India file byte-for-byte. Full
detail: the India Benchmark data dictionary and validation report (archived with `ml_experiments/`).

## 2. Baseline model comparison (Phase 1, first benchmark)

10 runnable configurations, seeds 0/1/2, test metrics at each model's
**validation-selected max-F1 threshold**. CatBoost and Explainable Boosting Machine
were recorded **UNAVAILABLE** (backends not installed in the venv).

**Chronological protocol** (mean over seeds), ranked by PR-AUC:

| Model | PR-AUC | ROC-AUC | Precision | Recall | F1 |
|---|---|---|---|---|---|
| LightGBM | 0.806 | 0.852 | 0.718 | 0.730 | 0.724 |
| Random Forest | 0.804 | 0.848 | 0.723 | 0.737 | 0.729 |
| HistGradientBoosting | 0.804 | 0.850 | 0.733 | 0.713 | 0.722 |
| XGBoost | 0.797 | 0.838 | 0.736 | 0.679 | 0.707 |
| Extra Trees | 0.775 | 0.818 | 0.717 | 0.665 | 0.690 |
| RBF SVM | 0.744 | 0.788 | 0.651 | 0.708 | 0.678 |
| Logistic Regression | 0.740 | 0.788 | 0.669 | 0.682 | 0.675 |
| Linear SVM | 0.737 | 0.785 | 0.665 | 0.680 | 0.673 |
| K-Nearest Neighbors | 0.617 | 0.704 | 0.578 | 0.658 | 0.615 |
| Decision Tree | 0.564 | 0.683 | 0.669 | 0.575 | 0.618 |

**Unseen-account protocol** (mean over seeds): LightGBM 0.818 PR-AUC, HistGradientBoosting 0.811,
Random Forest 0.810 lead; the gradient-boosting family generalises best across unseen accounts.
Source: the Phase-1 baseline results (chronological / account JSON, archived with
`ml_experiments/`); method in [`docs/Benchmark_Methodology.md`](../../Benchmark_Methodology.md).

## 3. Experiment 2 — threshold analysis & feature ablation

Source: the Experiment 2 report (archived with `ml_experiments/`).

- **Operating points** (all chosen on validation only): max-F1; a high-precision point
  (max precision subject to recall ≥ 0.50); a high-recall point (max recall subject to
  precision ≥ 0.50). The floors are a symmetric reporting convention, not a business KPI;
  Pareto endpoints are reported when a floor is unreachable. High-precision trades away
  recall (test P ≈ 0.87–0.89 at R ≈ 0.42–0.49); high-recall floods alerts (R ≈ 0.96–0.98 at
  P ≈ 0.52–0.53).
- **Feature ablation** (PR-AUC drop vs the full 27-feature set, mean over seeds):
  - **B — remove velocity** (last-hour/last-24h counts & amounts): **−0.03 to −0.04** → velocity
    is the strongest designed signal.
  - **C — remove amount history**: −0.02 to −0.03 → moderate, overlaps velocity.
  - **E — core 16 features** (transaction attributes + a behavioural subset): retains ~93–96%
    of full ranking → signal is **not velocity-only**.
  - **D — no proxy ≡ A full**: code inspection found **no** identifier/target proxy among the 27
    features (max single-feature AUC 0.7433 < 0.95), so there was no shortcut to remove.
- Per-seed standard deviation was negligible (LightGBM/XGBoost ≈ 0.000; RF/HistGB 0.001–0.004).

## 4. Experiment 3 — combined generalization evaluation

Source: the Experiment 3 report and results JSON (archived with `ml_experiments/`).

One protocol testing **both** held-out axes at once: accounts mutually exclusive across
train/validation/test **and** strictly time-ordered (every train txn < every validation txn
< every test txn). Split seed 20261014. The strictly-prior, per-account features remain
valid under this split (no future information; held-out accounts' own earlier history is
legitimately observable at scoring time), so the historical-feature STOP gate did not trip.

- **Split:** train 7,041 (38.8% fraud) / validation 866 (43.3%) / test 848 (43.2%);
  accounts assigned 600/200/200; **0 overlap**; 11,245 rows dropped by the joint constraint.
- **Test results** (mean over seeds, validation-selected threshold):

| Model | Precision | Recall | F1 | PR-AUC | ROC-AUC | FP | FN | Threshold |
|---|---|---|---|---|---|---|---|---|
| LightGBM | 0.670 | 0.754 | 0.710 | 0.745 | 0.813 | 136 | 90 | 0.316 |
| HistGradientBoosting | 0.674 | 0.790 | **0.727** | **0.770** | 0.827 | 140 | 77 | 0.226 |
| Random Forest | 0.671 | 0.729 | 0.696 | 0.747 | 0.816 | 132 | 99 | 0.385 |

Under the combined protocol **HistGradientBoosting leads both PR-AUC and F1**, while LightGBM
and Random Forest fall to a near-tie; absolute scores drop versus the single-axis baselines
because the combined regime is stricter with far less effective training data.

## 5. HistGradientBoosting — provisional status

HistGradientBoosting is the **provisional front-runner** of Phase 1: it is the only finalist
that tops both ranking (PR-AUC) and threshold-dependent (F1) metrics under the hardest
protocol, and it was deterministic across seeds. On the single-axis baselines it was in a
three-way near-tie (0.804–0.818), so its lead is **protocol-dependent, not absolute**. It is
**provisional** — a baseline to beat in Phase 2, **not** a declared final model and **not**
integrated with the backend.

## 6. Dataset limitations & evaluation caveats

- **Prevalence is artificial** (40–43%): precision and alert counts are **not** transportable
  to production; only relative comparisons are meaningful.
- **Velocity-dominant** but demonstrably not velocity-only (Experiment 2).
- **One 6-month window, one generator seed, one dataset instance**: no distribution-shift,
  seasonality, adversarial-response or calibration conclusions; the grouped split used a
  single account draw.
- **Real fraud signals are absent** (IP, device fingerprint, geo-velocity, VPA/PSP, mule graphs).
- **A higher PR-AUC does not prove real-world effectiveness**; all findings are on synthetic data.

## 7. Why Phase 1 cannot pre-select the best PaySim model

The India findings are **dataset-specific evidence**, not a model-selection shortcut for PaySim:

1. **Different data and provenance.** PaySim is a distinct synthetic mobile-money generator with
   its own columns, scales, class ratio and — crucially — a **different feature-availability and
   leakage profile**. The India leakage audit (no proxies, strictly-prior history) does **not**
   transfer; PaySim must be audited independently before any training.
2. **Ranking is protocol-sensitive.** Even on the *same* India data the leader changed with the
   evaluation protocol (chronological → LightGBM/RF/HistGB near-tie; account → LightGBM;
   combined → HistGradientBoosting). A model "best" on India is not guaranteed best on PaySim.
3. **Prevalence/cost differ**, so India thresholds and operating points do not carry over.
4. **Hard rule (see [`ml/README.md`](../../../ml/README.md)):** previous benchmark results must **not** be mixed with,
   or presented as, PaySim results. Phase 1 is archived; the PaySim evaluation is independent, in `ml/`.

The correct use of Phase 1 is as a **methodology template** (split protocols, validation-only
thresholding, ablation discipline, combined holdout) and a **prior hypothesis** to test on PaySim —
never as a conclusion about PaySim.

---

## 8. Phase-1 artifacts (archived)

The Phase-1 working directory `ml_experiments/` — the benchmark harness and experiment
scripts (`benchmark_lib.py`, `benchmark_models.py`, `experiment_2.py`, `experiment_3.py`),
the `benchmark_results/` JSON and report files, the India dataset and its data
dictionary/validation reports, tests and virtual environment — has been **removed during
repository cleanup**. Its durable record is this summary plus
[`docs/Benchmark_Methodology.md`](../../Benchmark_Methodology.md). The numbers reported
above were produced from those artifacts and are retained here as a static historical
record.

Status: **Phase 2 (PaySim) is complete and integrated** — see
[`ml/README.md`](../../../ml/README.md).

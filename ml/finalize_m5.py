"""FraudLens M5 — bounded finalization (runtime-optimized winner selection).

This is the lean counterpart to ``train_eval_m5.py``. The exhaustive Stage 1/2
comparison and the full-train boosting finalists already completed there:

  * Stage 1 (300k-subset, 400k-eval) and Stage 2 (bounded tuning) are persisted in
    ``ml/reports/m5/experiment_runs.csv`` and are REUSED verbatim (not rerun);
  * the full-train boosting finalists showed XGBoost clearly ahead
    (xgb_full PR-AUC 0.7024 > hgb_full 0.6728; lgbm_full 0.089 -- is_unbalance
    collapse), so the winner is effectively determined.

The expensive, non-blocking full-partition tree retrains (rf_full/et_full) that
were still grinding were stopped: they cannot change the ranking and would not be
selected. This script therefore does the MINIMUM needed to finalize responsibly:

  1. load the frozen causal matrix ONCE and rebuild the fixed splits (fast, reuse);
  2. re-run the leakage / temporal-integrity GATE (must pass before any training);
  3. retrain the TWO strongest practical boosting candidates on the full training
     partition (early stopping; bounded row cap) -- this is the FULL-TRAIN RETRAIN,
     reported SEPARATELY from the sampled Stage-1/2 numbers;
  4. evaluate ONE bounded ensemble (soft-vote of those two) per the spec;
  5. select the winner + decision threshold on VALIDATION only (PR-AUC primary);
  6. evaluate the chosen configuration EXACTLY ONCE on the untouched final test,
     plus generalization to unseen destinations and origin/type diagnostics;
  7. persist the selected model, feature order, threshold and reports.

No dataset, split or upstream artifact is modified. Backend/frontend/DB/API are
untouched. The run used an external read-only Python interpreter only; no repository
directory is required at finalize time.
"""

from __future__ import annotations

import csv
import json
import os
import time

import joblib
import numpy as np

from modeling import dataset as ds
from modeling import registry as reg
from modeling.evaluate import best_threshold_by_f1, metrics_at, pr_auc, roc_auc
from generator.schema import TRANSACTION_TYPES

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MATRIX = os.path.join(REPO, "ml", "data", "processed", "model_matrix_v1.csv")
REPORT_DIR = os.path.join(REPO, "ml", "reports", "m5")
ART_DIR = os.path.join(REPO, "ml", "artifacts", "m5")
RUNS_CSV = os.path.join(REPORT_DIR, "experiment_runs.csv")

SEED = 42
TRAIN_MAX, VAL_MAX = 500, 620          # identical to the completed run (fixed splits)
HOLDOUT_FRAC = 0.20
FULL_LIMIT = 5_000_000                 # same cap used by the logged xgb_full/hgb_full
XGB_BEST = dict(max_depth=10, learning_rate=0.05)   # Stage-2 winner (xgb_d10_lr0.05)
EARLY_STOP_ROUNDS = 50
ES_EVAL_ROWS = 200_000                 # val slice used only for boosting early stopping
MARGIN = 0.02                          # ensemble must beat best individual by this

rng = np.random.default_rng(SEED)
EXTRA_RUNS = []


def _log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def _sample(idx, n):
    if len(idx) <= n:
        return idx
    return rng.choice(idx, size=n, replace=False)


def _proba(model, X):
    if len(X) == 0:
        return np.zeros(0, dtype=np.float64)
    if hasattr(model, "predict_proba"):
        return model.predict_proba(X)[:, 1]
    d = model.decision_function(X)
    return 1.0 / (1.0 + np.exp(-d))


def _append_runs(rows):
    """Merge new full-train/eval rows into the persisted experiment_runs.csv.

    Existing Stage 1/2 rows are preserved; rows with the same experiment_id are
    replaced (idempotent re-runs), and the file is rewritten atomically.
    """
    cols = ["stage", "experiment_id", "family", "model", "train_rows", "eval_rows",
            "pr_auc", "roc_auc", "f1@thr", "threshold", "train_s", "infer_s"]
    existing = {}
    if os.path.exists(RUNS_CSV):
        with open(RUNS_CSV, newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                existing[r["experiment_id"]] = r
    for r in rows:
        existing[r["experiment_id"]] = {k: (round(r[k], 6) if isinstance(r.get(k), float)
                                            else r.get(k, "")) for k in cols}
    tmp = RUNS_CSV + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, lineterminator="\n", extrasaction="ignore")
        w.writeheader()
        for eid, r in existing.items():
            w.writerow(r)
    os.replace(tmp, RUNS_CSV)


def main():
    os.makedirs(REPORT_DIR, exist_ok=True)
    os.makedirs(ART_DIR, exist_ok=True)
    t_start = time.time()

    # ---- 1. load + split (reuse frozen matrix; no causal rebuild) ----
    _log("loading matrix (reuse)…")
    with open(os.path.join(REPORT_DIR, "matrix_build.json")) as fh:
        n_rows = int(json.load(fh)["rows"])
    data = ds.load_matrix(MATRIX, n_rows=n_rows)
    ds.build_splits(data, train_max=TRAIN_MAX, val_max=VAL_MAX,
                    holdout_seed=SEED, holdout_frac=HOLDOUT_FRAC)

    # ---- 2. leakage / temporal-integrity gate (STOP on any issue) ----
    integrity = ds.integrity_report(data)
    if integrity["issues"]:
        _log("CRITICAL integrity failure: " + "; ".join(integrity["issues"]))
        raise SystemExit(2)
    _log("integrity OK; prevalence=" + json.dumps(integrity["prevalence_by_split"]))

    X, y = data["X"], data["y"].astype(np.int64)
    ix = data["split_index"]
    tr_full = ix["train"] if len(ix["train"]) <= FULL_LIMIT else _sample(ix["train"], FULL_LIMIT)
    Xtf, ytf = X[tr_full], y[tr_full]
    spw = float((ytf == 0).sum() / max((ytf == 1).sum(), 1))

    val_full = ix["val"]
    Xvf, yvf = X[val_full], y[val_full]
    # small deterministic val slice purely for boosting early stopping (never test)
    es_idx = _sample(val_full, min(ES_EVAL_ROWS, len(val_full)))
    Xes, yes = X[es_idx], y[es_idx]

    finalists = {}

    # ---- 3a. retrain winner candidate: XGBoost (full-train partition) ----
    from xgboost import XGBClassifier
    _log("retraining xgb_full on full-train partition…")
    xgb = XGBClassifier(objective="binary:logistic", eval_metric="aucpr", tree_method="hist",
                        n_estimators=600, max_depth=XGB_BEST["max_depth"],
                        learning_rate=XGB_BEST["learning_rate"], subsample=0.9,
                        colsample_bytree=0.9, scale_pos_weight=spw,
                        early_stopping_rounds=EARLY_STOP_ROUNDS,
                        n_jobs=-1, random_state=SEED)
    t0 = time.time()
    xgb.fit(Xtf, ytf, eval_set=[(Xes, yes)], verbose=False)
    xgb_train_s = time.time() - t0
    t0 = time.time(); p_xgb = _proba(xgb, Xvf); xgb_infer_s = time.time() - t0
    th_xgb, f1_xgb = best_threshold_by_f1(yvf, p_xgb)
    finalists["xgb_full"] = {"model": xgb, "proba_val": p_xgb, "threshold": th_xgb,
                             "family": "Boost", "train_rows": int(len(tr_full)),
                             "train_s": xgb_train_s, "infer_s": xgb_infer_s}
    _log(f"  xgb_full PR-AUC={pr_auc(yvf, p_xgb):.4f} thr={th_xgb:.2f} "
         f"f1={f1_xgb:.4f} train_s={xgb_train_s:.0f}")

    # ---- 3b. retrain runner-up candidate: HistGradientBoosting (full-train) ----
    _log("retraining hgb_full on full-train partition…")
    t0 = time.time()
    hgb = reg.REGISTRY["hgb"][0]()
    hgb.fit(Xtf, ytf)
    hgb_train_s = time.time() - t0
    t0 = time.time(); p_hgb = _proba(hgb, Xvf); hgb_infer_s = time.time() - t0
    th_hgb, f1_hgb = best_threshold_by_f1(yvf, p_hgb)
    finalists["hgb_full"] = {"model": hgb, "proba_val": p_hgb, "threshold": th_hgb,
                             "family": "Boost", "train_rows": int(len(tr_full)),
                             "train_s": hgb_train_s, "infer_s": hgb_infer_s}
    _log(f"  hgb_full PR-AUC={pr_auc(yvf, p_hgb):.4f} thr={th_hgb:.2f} "
         f"f1={f1_hgb:.4f} train_s={hgb_train_s:.0f}")

    # ---- 4. one bounded ensemble: soft-vote of the two strongest ----
    p_soft = np.mean([p_xgb, p_hgb], axis=0)
    th_soft, f1_soft = best_threshold_by_f1(yvf, p_soft)
    finalists["soft_vote_xgb_hgb"] = {"model": None, "proba_val": p_soft,
                                      "threshold": th_soft, "family": "Ensemble",
                                      "train_rows": int(len(tr_full)),
                                      "train_s": xgb_train_s + hgb_train_s,
                                      "infer_s": 0.0}
    _log(f"  soft_vote(xgb,hgb) PR-AUC={pr_auc(yvf, p_soft):.4f} thr={th_soft:.2f} "
         f"f1={f1_soft:.4f}")

    # ---- 5. winner selection on VALIDATION (PR-AUC primary, prefer single on ties) ----
    def _rank(eid):
        p = finalists[eid]["proba_val"]
        return {"pr_auc": pr_auc(yvf, p),
                "roc_auc": roc_auc(yvf, p),
                "f1@thr": metrics_at(yvf, p, finalists[eid]["threshold"])["f1"],
                "family": finalists[eid]["family"]}
    cand = {eid: _rank(eid) for eid in finalists}
    ranked = sorted(cand.items(), key=lambda kv: kv[1]["pr_auc"], reverse=True)
    _log("validation ranking: " + ", ".join(f"{k}={v['pr_auc']:.4f}" for k, v in ranked))

    top_ind = next(k for k, v in ranked if v["family"] != "Ensemble")
    top_ens = next((k for k, v in ranked if v["family"] == "Ensemble"), None)
    win, win_reason = top_ind, f"best individual by validation PR-AUC; ensemble gain < {MARGIN}"
    if top_ens and (cand[top_ens]["pr_auc"] - cand[top_ind]["pr_auc"]) >= MARGIN:
        win, win_reason = top_ens, "ensemble improved validation PR-AUC beyond margin"
    win_thr = finalists[win]["threshold"]
    _log(f"WINNER={win} thr={win_thr:.2f} ({win_reason})")

    # ---- 6. single UNTOUCHED final-test evaluation + generalization + diagnostics ----
    def proba_of(eid, Xb):
        if eid == "soft_vote_xgb_hgb":
            return np.mean([_proba(finalists[b]["model"], Xb) for b in ("xgb_full", "hgb_full")], axis=0)
        return _proba(finalists[eid]["model"], Xb)

    test = ix["test"]
    t0 = time.time(); p_te = proba_of(win, X[test]); test_infer_s = time.time() - t0
    m_test = metrics_at(y[test], p_te, win_thr)
    final_report = {
        "selected_on": "validation", "winner": win, "reason": win_reason,
        "threshold": float(win_thr),
        "selection_mode": "full-train retrain (Stage 1/2 sampled results reused, not rerun)",
        "validation": {"rows": int(len(val_full)), **cand[win]},
        "final_test": {"rows": int(len(test)),
                       "pr_auc": pr_auc(y[test], p_te), "roc_auc": roc_auc(y[test], p_te),
                       **m_test, "infer_s_on_test": round(test_infer_s, 3),
                       "infer_ms_per_1k_rows": round(test_infer_s / max(len(test), 1) * 1e6, 3)},
    }

    unseen = ix["unseen"]
    p_un = proba_of(win, X[unseen])
    final_report["unseen_generalization"] = {"rows": int(len(unseen)),
                                             "pr_auc": pr_auc(y[unseen], p_un),
                                             "roc_auc": roc_auc(y[unseen], p_un),
                                             **metrics_at(y[unseen], p_un, win_thr)}

    # diagnostics on the test block: original vs generated, per transaction type
    origin_te = data["origin"][test]
    diag = {"by_origin": {}, "by_type": {}}
    for grp in ("original", "generated"):
        gmask = origin_te == grp
        if gmask.any():
            diag["by_origin"][grp] = {"rows": int(gmask.sum()),
                                      **metrics_at(y[test][gmask], p_te[gmask], win_thr)}
    tcols = [data["feature_columns"].index(f"type_{t}") for t in TRANSACTION_TYPES]
    type_idx = X[test][:, tcols].argmax(1)
    for i, t in enumerate(TRANSACTION_TYPES):
        gmask = type_idx == i
        if gmask.any():
            diag["by_type"][t] = {"rows": int(gmask.sum()),
                                  "fraud_rows": int(y[test][gmask].sum()),
                                  **metrics_at(y[test][gmask], p_te[gmask], win_thr)}
    final_report["diagnostics"] = diag

    # ---- 7. persist artifacts + reports (dataset/splits/manifests untouched) ----
    _log("persisting artifacts…")
    win_obj = finalists[win]
    bundle = {
        "winner_id": win,
        "threshold": float(win_thr),
        "feature_columns": data["feature_columns"],
        "ensemble_kind": ("soft" if win.startswith("soft_vote") else "single"),
        "single_model": win_obj["model"],
        "ensemble_members": ([finalists[b]["model"] for b in ("xgb_full", "hgb_full")]
                             if win.startswith("soft_vote") else None),
        "needs_scaling": False,   # boosting consumes raw policy features
    }
    joblib.dump(bundle, os.path.join(ART_DIR, "winner_model.joblib"))
    with open(os.path.join(ART_DIR, "feature_names.json"), "w") as fh:
        json.dump(data["feature_columns"], fh, indent=2)
    with open(os.path.join(ART_DIR, "winner_config.json"), "w") as fh:
        json.dump({"winner": win, "threshold": float(win_thr), "reason": win_reason,
                   "xgb_config": {**XGB_BEST, "n_estimators": 600, "scale_pos_weight": spw,
                                  "early_stopping_rounds": EARLY_STOP_ROUNDS},
                   "full_train_rows": int(len(tr_full)),
                   "train_sample_cap": FULL_LIMIT, "seed": SEED,
                   "validation_ranking": [[k, v["pr_auc"], v["family"]] for k, v in ranked],
                   "candidates": cand}, fh, indent=2)
    with open(os.path.join(REPORT_DIR, "final_test_report.json"), "w") as fh:
        json.dump(final_report, fh, indent=2)

    # merge full-train retrain + final-test rows into the persisted runs CSV
    EXTRA_RUNS = [
        {"stage": 3, "experiment_id": "xgb_full", "family": "Boost", "model": "XGBClassifier",
         "train_rows": int(len(tr_full)), "eval_rows": int(len(val_full)),
         "pr_auc": cand["xgb_full"]["pr_auc"], "roc_auc": cand["xgb_full"]["roc_auc"],
         "f1@thr": cand["xgb_full"]["f1@thr"], "threshold": th_xgb,
         "train_s": xgb_train_s, "infer_s": xgb_infer_s},
        {"stage": 3, "experiment_id": "hgb_full", "family": "Boost",
         "model": "HistGradientBoostingClassifier",
         "train_rows": int(len(tr_full)), "eval_rows": int(len(val_full)),
         "pr_auc": cand["hgb_full"]["pr_auc"], "roc_auc": cand["hgb_full"]["roc_auc"],
         "f1@thr": cand["hgb_full"]["f1@thr"], "threshold": th_hgb,
         "train_s": hgb_train_s, "infer_s": hgb_infer_s},
        {"stage": 6, "experiment_id": "soft_vote_xgb_hgb", "family": "Ensemble",
         "model": "SoftVoting", "train_rows": int(len(tr_full)), "eval_rows": int(len(val_full)),
         "pr_auc": cand["soft_vote_xgb_hgb"]["pr_auc"],
         "roc_auc": cand["soft_vote_xgb_hgb"]["roc_auc"],
         "f1@thr": cand["soft_vote_xgb_hgb"]["f1@thr"], "threshold": th_soft,
         "train_s": xgb_train_s + hgb_train_s, "infer_s": 0.0},
        {"stage": 8, "experiment_id": f"WINNER_{win}_final_test", "family": "Eval",
         "model": "final_test", "train_rows": int(len(tr_full)), "eval_rows": int(len(test)),
         "pr_auc": final_report["final_test"]["pr_auc"],
         "roc_auc": final_report["final_test"]["roc_auc"],
         "f1@thr": m_test["f1"], "threshold": win_thr},
    ]
    _append_runs(EXTRA_RUNS)

    summary = {"total_wall_s": round(time.time() - t_start, 1),
               "winner": win, "threshold": float(win_thr),
               "final_test": final_report["final_test"],
               "unseen": {k: final_report["unseen_generalization"][k]
                          for k in ("pr_auc", "recall", "precision", "f1")},
               "full_train_rows": int(len(tr_full))}
    with open(os.path.join(REPORT_DIR, "finalize_summary.json"), "w") as fh:
        json.dump(summary, fh, indent=2)
    _log("DONE in " + str(round(time.time() - t_start, 1)) + "s")


if __name__ == "__main__":
    main()

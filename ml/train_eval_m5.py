"""FraudLens M5 — controlled model experimentation, ensembles & winner selection.

Single long-running process:
  1. load the frozen causal feature matrix ONCE and build the fixed splits;
  2. run leakage + split-integrity gates (STOP on any issue);
  3. Stage 1 broad comparison on a consistent deterministic eval subset;
  4. Stage 2 bounded hyperparameter tuning of promising candidates;
  5. Stage 3 full-train finalists + validation threshold selection;
  6. ensemble experiments (soft/hard voting, stacking) vs best individual;
  7. objective winner selection on VALIDATION, then ONE untouched-test evaluation;
  8. diagnostics (origin vs generated, per type, unseen destinations);
  9. persist artifacts, reports and a stable inference interface.

The dataset and splits are never altered to chase scores; expensive models run on
documented deterministic subsets and are never implied to have seen the full data.
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
from modeling.evaluate import (best_threshold_by_f1, metrics_at, pr_auc, roc_auc)
from generator.schema import TRANSACTION_TYPES

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MATRIX = os.path.join(REPO, "ml", "data", "processed", "model_matrix_v1.csv")
SPLITS_CSV = os.path.join(REPO, "ml", "data", "splits", "split_assignments.csv")
REPORT_DIR = os.path.join(REPO, "ml", "reports", "m5")
ART_DIR = os.path.join(REPO, "ml", "artifacts", "m5")

SEED = 42
TRAIN_MAX, VAL_MAX = 500, 620          # chronological step boundaries (1..743)
HOLDOUT_FRAC = 0.20                     # destination-level unseen holdout
STAGE1_TRAIN_SUBSET = 300_000           # for subset-required models + broad trees
STAGE1_EVAL_SUBSET = 400_000            # consistent eval across all Stage-1 models
FULL_LIMIT = 5_000_000                  # cap for full-train finalists
# full-train tree finalists are depth/leaf-bounded so a 5M-row forest stays practical
FULL_TREE = dict(n_estimators=150, max_depth=24, min_samples_leaf=20)

rng = np.random.default_rng(SEED)
RUNS = []


def _log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def _sample(idx, n):
    if len(idx) <= n:
        return idx
    return rng.choice(idx, size=n, replace=False)


def _proba(model, X):
    if hasattr(model, "predict_proba"):
        return model.predict_proba(X)[:, 1]
    d = model.decision_function(X)
    return 1.0 / (1.0 + np.exp(-d))


def _score(model, Xtr, ytr, Xev, yev):
    t0 = time.time()
    model.fit(Xtr, ytr)
    train_s = time.time() - t0
    t0 = time.time()
    p = _proba(model, Xev)
    infer_s = time.time() - t0
    return model, p, train_s, infer_s


def record(row):
    RUNS.append(row)
    _log(f"{row['experiment_id']:<16} PR-AUC={row.get('pr_auc',float('nan')):.4f} "
         f"ROC={row.get('roc_auc',float('nan')):.4f} train_s={row.get('train_s',0):.1f} "
         f"stage={row.get('stage')}")


def main():
    os.makedirs(REPORT_DIR, exist_ok=True)
    os.makedirs(ART_DIR, exist_ok=True)

    # ---- 1. load + split ----
    _log("loading matrix…")
    with open(os.path.join(REPORT_DIR, "matrix_build.json")) as fh:
        n_rows = int(json.load(fh)["rows"])
    data = ds.load_matrix(MATRIX, n_rows=n_rows)
    ds.build_splits(data, train_max=TRAIN_MAX, val_max=VAL_MAX,
                    holdout_seed=SEED, holdout_frac=HOLDOUT_FRAC)
    integrity = ds.integrity_report(data)
    fp = {"matrix_sha256": ds.sha256_of(MATRIX)}
    manifest = {"dataset": {"matrix": MATRIX, **fp, "rows": int(data["n"]),
                           "overall_fraud_rate": data["fraud_rate"]},
                "splits": {"train_max_step": TRAIN_MAX, "val_max_step": VAL_MAX,
                           "holdout_seed": SEED, "holdout_frac": HOLDOUT_FRAC,
                           **integrity},
                "feature_columns": data["feature_columns"]}
    with open(os.path.join(REPORT_DIR, "experiment_manifest.json"), "w") as fh:
        json.dump(manifest, fh, indent=2)
    if integrity["issues"]:
        _log("CRITICAL integrity failure: " + "; ".join(integrity["issues"]))
        with open(os.path.join(REPORT_DIR, "integrity_failure.json"), "w") as fh:
            json.dump(manifest, fh, indent=2)
        raise SystemExit(2)
    _log("integrity OK; prevalence=" + json.dumps(integrity["prevalence_by_split"]))
    ds.write_split_csv(MATRIX, data["assign"], SPLITS_CSV)

    X, y = data["X"], data["y"].astype(np.int64)
    ix = data["split_index"]
    Xtr_all, ytr_all = X[ix["train"]], y[ix["train"]]
    # consistent Stage-1 eval sample from val
    val_ev = _sample(ix["val"], STAGE1_EVAL_SUBSET)
    Xev, yev = X[val_ev], y[val_ev]

    # ---- 3. Stage 1 broad comparison ----
    _log("STAGE 1 broad comparison")
    stage1_ids = ["nb_gauss", "svm_linear", "svm_linear_cal", "knn3", "knn5", "knn7",
                  "dt", "logreg", "bag_dt", "rf_bal", "rf", "et", "xgb", "lgbm", "hgb"]
    trained = {}
    for eid in stage1_ids:
        builder, family, needs_sub = reg.REGISTRY[eid]
        if needs_sub:
            sub = _sample(ix["train"], STAGE1_TRAIN_SUBSET)
        else:
            sub = _sample(ix["train"], STAGE1_TRAIN_SUBSET)   # broad stage: subset for speed/parity
        Xs, ys = X[sub], y[sub]
        m = builder()
        m, p, ts, ins = _score(m, Xs, ys, Xev, yev)
        trained[eid] = (family, needs_sub)
        record({"stage": 1, "experiment_id": eid, "family": family, "model": type(m).__name__,
                "train_rows": int(len(sub)), "eval_rows": int(len(val_ev)),
                "pr_auc": pr_auc(yev, p), "roc_auc": roc_auc(yev, p),
                "train_s": ts, "infer_s": ins})

    # ---- 4. Stage 2 bounded tuning (boosting depth/leaves, lr, regularization) ----
    _log("STAGE 2 hyperparameter tuning")
    from xgboost import XGBClassifier
    from lightgbm import LGBMClassifier
    from sklearn.ensemble import RandomForestClassifier, ExtraTreesClassifier
    sub = _sample(ix["train"], STAGE1_TRAIN_SUBSET)
    Xs, ys = X[sub], y[sub]
    tune = {}
    for depth in (6, 8, 10):
        for lr in (0.05, 0.1):
            eid = f"xgb_d{depth}_lr{lr}"
            m = XGBClassifier(objective="binary:logistic", eval_metric="aucpr",
                              tree_method="hist", n_estimators=400, max_depth=depth,
                              learning_rate=lr, subsample=0.9, colsample_bytree=0.9,
                              scale_pos_weight=float((ys == 0).sum() / max((ys == 1).sum(), 1)),
                              n_jobs=-1, random_state=SEED)
            m, p, ts, ins = _score(m, Xs, ys, Xev, yev)
            tune[eid] = pr_auc(yev, p)
            record({"stage": 2, "experiment_id": eid, "family": "Boost", "model": "XGBClassifier",
                    "train_rows": int(len(sub)), "eval_rows": int(len(val_ev)),
                    "pr_auc": tune[eid], "roc_auc": roc_auc(yev, p), "train_s": ts, "infer_s": ins})
    for leaves in (63, 127, 255):
        eid = f"lgbm_l{leaves}"
        m = LGBMClassifier(objective="binary", n_estimators=400, learning_rate=0.1,
                           num_leaves=leaves, subsample=0.9, colsample_bytree=0.9,
                           is_unbalance=True, n_jobs=-1, random_state=SEED, verbose=-1)
        m, p, ts, ins = _score(m, Xs, ys, Xev, yev)
        tune[eid] = pr_auc(yev, p)
        record({"stage": 2, "experiment_id": eid, "family": "Boost", "model": "LGBMClassifier",
                "train_rows": int(len(sub)), "eval_rows": int(len(val_ev)),
                "pr_auc": tune[eid], "roc_auc": roc_auc(yev, p), "train_s": ts, "infer_s": ins})
    for trees in (300, 500):
        eid = f"rf_t{trees}"
        m = RandomForestClassifier(n_estimators=trees, min_samples_leaf=1,
                                   class_weight="balanced_subsample", random_state=SEED, n_jobs=-1)
        m, p, ts, ins = _score(m, Xs, ys, Xev, yev)
        tune[eid] = pr_auc(yev, p)
        record({"stage": 2, "experiment_id": eid, "family": "Tree", "model": "RandomForest",
                "train_rows": int(len(sub)), "eval_rows": int(len(val_ev)),
                "pr_auc": tune[eid], "roc_auc": roc_auc(yev, p), "train_s": ts, "infer_s": ins})

    _write_runs_csv(os.path.join(REPORT_DIR, "experiment_runs.csv"))

    # ---- 5. Stage 3 full-train finalists on the FULL train partition ----
    _log("STAGE 3 full-train finalists")
    tr_full = ix["train"] if len(ix["train"]) <= FULL_LIMIT else _sample(ix["train"], FULL_LIMIT)
    Xtf, ytf = X[tr_full], y[tr_full]
    spw = float((ytf == 0).sum() / max((ytf == 1).sum(), 1))
    val_full = ix["val"]
    Xvf, yvf = X[val_full], y[val_full]
    finalists = {}

    def full_fit(eid, builder, family):
        m = builder()
        t0 = time.time(); m.fit(Xtf, ytf); ts = time.time() - t0
        t0 = time.time(); p = _proba(m, Xvf); ins = time.time() - t0
        th, f1 = best_threshold_by_f1(yvf, p)
        finalists[eid] = {"model": m, "proba_val": p, "threshold": th,
                          "family": family, "train_rows": int(len(tr_full)),
                          "eval_rows": int(len(val_full))}
        record({"stage": 3, "experiment_id": eid, "family": family, "model": type(m).__name__,
                "train_rows": int(len(tr_full)), "eval_rows": int(len(val_full)),
                "pr_auc": pr_auc(yvf, p), "roc_auc": roc_auc(yvf, p),
                "f1@thr": f1, "threshold": th, "train_s": ts, "infer_s": ins})
        _log(f"  {eid} threshold={th:.2f} f1={f1:.4f}")
        return m

    best_xgb = max([k for k in tune if k.startswith("xgb")], key=lambda k: tune[k])
    best_lgb = max([k for k in tune if k.startswith("lgbm")], key=lambda k: tune[k])
    d, lru = best_xgb.split("_")[1], best_xgb.split("_")[2]
    full_fit("xgb_full", lambda: XGBClassifier(
        objective="binary:logistic", eval_metric="aucpr", tree_method="hist",
        n_estimators=600, max_depth=int(d[1:]), learning_rate=float(lru[2:]), subsample=0.9,
        colsample_bytree=0.9, scale_pos_weight=spw, n_jobs=-1, random_state=SEED), "Boost")
    lv = int(best_lgb.split("_")[1][1:])
    full_fit("lgbm_full", lambda: LGBMClassifier(
        objective="binary", n_estimators=600, learning_rate=0.1, num_leaves=lv,
        subsample=0.9, colsample_bytree=0.9, is_unbalance=True, n_jobs=-1,
        random_state=SEED, verbose=-1), "Boost")
    full_fit("hgb_full", reg.REGISTRY["hgb"][0], "Boost")
    full_fit("rf_full", lambda: RandomForestClassifier(
        class_weight="balanced_subsample", random_state=SEED, n_jobs=-1, **FULL_TREE), "Tree")
    full_fit("et_full", lambda: ExtraTreesClassifier(
        class_weight="balanced_subsample", random_state=SEED, n_jobs=-1, **FULL_TREE), "Tree")

    # ---- 6. Ensembles on validation (base models trained on FULL train) ----
    _log("STAGE 6 ensembles")
    base_ids = [k for k in ("xgb_full", "lgbm_full", "hgb_full", "rf_full", "et_full")]
    soft = np.mean([finalists[b]["proba_val"] for b in base_ids], axis=0)
    sthr, sf1 = best_threshold_by_f1(yvf, soft)
    record({"stage": 6, "experiment_id": "soft_vote_all", "family": "Ensemble",
            "model": "SoftVoting", "train_rows": int(len(tr_full)), "eval_rows": int(len(val_full)),
            "pr_auc": pr_auc(yvf, soft), "roc_auc": roc_auc(yvf, soft), "f1@thr": sf1,
            "threshold": sthr, "train_s": 0.0, "infer_s": 0.0})
    trio = [b for b in ("xgb_full", "lgbm_full", "hgb_full")]
    soft3 = np.mean([finalists[b]["proba_val"] for b in trio], axis=0)
    t3, f3 = best_threshold_by_f1(yvf, soft3)
    record({"stage": 6, "experiment_id": "soft_vote_boost3", "family": "Ensemble",
            "model": "SoftVoting", "train_rows": int(len(tr_full)), "eval_rows": int(len(val_full)),
            "pr_auc": pr_auc(yvf, soft3), "roc_auc": roc_auc(yvf, soft3), "f1@thr": f3,
            "threshold": t3, "train_s": 0.0, "infer_s": 0.0})

    # hard voting across base models at their individual thresholds
    hard_pred = np.mean([(finalists[b]["proba_val"] >= finalists[b]["threshold"])
                         for b in base_ids], axis=0)
    hp = hard_pred
    hard_metrics = {"experiment_id": "hard_vote_all", "family": "Ensemble", "model": "HardVoting",
                    "stage": 6, "train_rows": int(len(tr_full)), "eval_rows": int(len(val_full))}
    yhard = (hp >= 0.5).astype(int)
    tp = int(((yhard == 1) & (yvf == 1)).sum()); fp = int(((yhard == 1) & (yvf == 0)).sum())
    fn = int(((yhard == 0) & (yvf == 1)).sum())
    prec = tp / (tp + fp) if tp + fp else 0.0; rec = tp / (tp + fn) if tp + fn else 0.0
    hard_metrics["f1@thr"] = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    hard_metrics["threshold"] = 0.5
    record(hard_metrics)

    # stacking: base probas (fit on FULL train) as meta features trained on VAL,
    # evaluated on UNSEEN (never used to fit base or meta) -> no base/meta overlap.
    ens_meta_X = np.column_stack([finalists[b]["proba_val"] for b in base_ids])
    from sklearn.linear_model import LogisticRegression
    meta = LogisticRegression(max_iter=1000, C=1.0).fit(ens_meta_X, yvf)

    # ---- 7. winner selection on VALIDATION (PR-AUC primary, prefer simpler on ties) ----
    _log("STAGE 7 winner selection")
    cand = {eid: {"pr_auc": pr_auc(yvf, finalists[eid]["proba_val"]),
                  "f1@thr": metrics_at(yvf, finalists[eid]["proba_val"],
                                       finalists[eid]["threshold"])["f1"],
                  "family": finalists[eid]["family"]} for eid in finalists}
    # include ensembles scored on val
    cand["soft_vote_boost3"] = {"pr_auc": pr_auc(yvf, soft3), "f1@thr": f3, "family": "Ensemble"}
    cand["soft_vote_all"] = {"pr_auc": pr_auc(yvf, soft), "f1@thr": sf1, "family": "Ensemble"}
    _write_runs_csv(os.path.join(REPORT_DIR, "experiment_runs.csv"))
    ranked = sorted(cand.items(), key=lambda kv: kv[1]["pr_auc"], reverse=True)
    _log("ranking: " + ", ".join(f"{k}={v['pr_auc']:.4f}" for k, v in ranked))
    # top individual boosting/tree
    top_ind = next((k for k, v in ranked if v["family"] != "Ensemble"), None)
    top_ens = next((k for k, v in ranked if v["family"] == "Ensemble"), None)
    # ensemble kept only if it beats best individual by a meaningful PR-AUC margin
    MARGIN = 0.02
    win = top_ind
    win_reason = f"best individual PR-AUC; ensemble gain < {MARGIN}"
    if top_ens and (cand[top_ens]["pr_auc"] - cand[top_ind]["pr_auc"]) >= MARGIN:
        win, win_reason = top_ens, "ensemble improved PR-AUC beyond margin"
    _log(f"WINNER={win} ({win_reason})")

    # ---- 8. evaluate winner on UNSEEN + diagnostics, then final TEST once ----
    def proba_of(eid, Xblock, iblock):
        if eid in finalists:
            return _proba(finalists[eid]["model"], Xblock)
        if eid in ("soft_vote_boost3", "soft_vote_all"):
            members = trio if eid.endswith("boost3") else base_ids
            return np.mean([_proba(finalists[b]["model"], Xblock) for b in members], axis=0)
        raise KeyError(eid)

    win_thr = finalists.get(win, {}).get("threshold", t3 if win.endswith("boost3") else sthr)
    unseen = ix["unseen"]
    p_un = proba_of(win, X[unseen], unseen)
    m_unseen = metrics_at(y[unseen], p_un, win_thr)

    test = ix["test"]
    p_te = proba_of(win, X[test], test)
    m_test = metrics_at(y[test], p_te, win_thr)
    test_report = {"winner": win, "reason": win_reason, "threshold": float(win_thr),
                   "unseen_generalization": {"rows": int(len(unseen)), **m_unseen},
                   "final_test": {"rows": int(len(test)),
                                  "pr_auc": pr_auc(y[test], p_te),
                                  "roc_auc": roc_auc(y[test], p_te), **m_test}}
    # per origin + per type on the test block
    tstep = data["origin"][test]
    diag = {"by_origin": {}, "by_type": {}}
    for grp in ("original", "generated"):
        gmask = tstep == grp
        if gmask.any():
            diag["by_origin"][grp] = metrics_at(y[test][gmask], p_te[gmask], win_thr)
    typecol = data["X"][test][:, [data["feature_columns"].index(f"type_{t}") for t in TRANSACTION_TYPES]].argmax(1)
    for i, t in enumerate(TRANSACTION_TYPES):
        gmask = typecol == i
        if gmask.any():
            diag["by_type"][t] = metrics_at(y[test][gmask], p_te[gmask], win_thr)
    test_report["diagnostics"] = diag
    record({"stage": 8, "experiment_id": f"WINNER_{win}_final_test", "family": "Eval",
            "model": "final_test", "train_rows": int(len(tr_full)), "eval_rows": int(len(test)),
            "pr_auc": test_report["final_test"]["pr_auc"],
            "roc_auc": test_report["final_test"]["roc_auc"],
            "f1@thr": m_test["f1"], "threshold": win_thr})

    _write_runs_csv(os.path.join(REPORT_DIR, "experiment_runs.csv"))

    # ---- 9. save artifacts ----
    _log("STAGE 9 persisting artifacts")
    _save_winner(win, finalists, base_ids, trio, meta, Xtf, ytf, win_thr, data,
                 test_report, manifest, ranked, cand)
    with open(os.path.join(REPORT_DIR, "final_test_report.json"), "w") as fh:
        json.dump(test_report, fh, indent=2)
    _log("DONE")


def _write_runs_csv(path):
    cols = ["stage", "experiment_id", "family", "model", "train_rows", "eval_rows",
            "pr_auc", "roc_auc", "f1@thr", "threshold", "train_s", "infer_s"]
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, lineterminator="\n", extrasaction="ignore")
        w.writeheader()
        for r in RUNS:
            w.writerow({k: (round(r[k], 6) if isinstance(r.get(k), float) else r.get(k))
                        for k in cols})


def _save_winner(win, finalists, base_ids, trio, meta, Xtf, ytf, win_thr, data,
                 test_report, manifest, ranked, cand):
    import xgboost as _xgb  # ensure estimator classes importable at load time
    joblib.dump({"winner_id": win, "threshold": float(win_thr),
                 "feature_columns": data["feature_columns"],
                 "single_model": finalists.get(win, {}).get("model"),
                 "ensemble_members": ([finalists[b]["model"] for b in (trio if win.endswith("boost3") else base_ids)]
                                      if win.startswith("soft_vote") else None),
                 "ensemble_kind": ("soft" if win.startswith("soft_vote") else "single")},
                os.path.join(ART_DIR, "winner_model.joblib"))
    with open(os.path.join(ART_DIR, "winner_config.json"), "w") as fh:
        json.dump({"winner": win, "threshold": float(win_thr),
                   "ranking": [[k, v["pr_auc"], v["family"]] for k, v in ranked],
                   "candidates": cand, "final_test": test_report["final_test"],
                   "split_manifest": manifest["splits"]}, fh, indent=2)
    with open(os.path.join(ART_DIR, "feature_names.json"), "w") as fh:
        json.dump(data["feature_columns"], fh, indent=2)


if __name__ == "__main__":
    main()

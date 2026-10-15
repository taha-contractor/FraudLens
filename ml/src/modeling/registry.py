"""M5 model registry.

Factories for every required family. Trees/boosting consume raw features; the
distance/linear/naive-Bayes families are wrapped in a StandardScaler pipeline (fit on
the training subset only, so scaling never leaks). Imbalance is handled with
class_weight / scale_pos_weight / is_unbalance where appropriate.

Each entry maps an experiment id to (builder, family, needs_subset) where
``needs_subset`` flags algorithms that cannot reasonably take the full training
partition and therefore run on a documented deterministic subset.
"""

from __future__ import annotations

from sklearn.ensemble import (BaggingClassifier, ExtraTreesClassifier,
                              HistGradientBoostingClassifier, RandomForestClassifier)
from sklearn.linear_model import LogisticRegression, SGDClassifier
from sklearn.naive_bayes import GaussianNB
from sklearn.neighbors import KNeighborsClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import LinearSVC
from xgboost import XGBClassifier
from lightgbm import LGBMClassifier


def _scale(est):
    return Pipeline([("scaler", StandardScaler()), ("est", est)])


def _xgb(**kw):
    p = dict(objective="binary:logistic", eval_metric="aucpr", tree_method="hist",
             n_jobs=-1, random_state=42)
    p.update(kw)
    return XGBClassifier(**p)


def _lgbm(**kw):
    p = dict(objective="binary", n_jobs=-1, random_state=42, verbose=-1,
             force_col_create=1.0)
    p.update(kw)
    return LGBMClassifier(**p)


# experiment id -> (builder callable, family label, needs_subset)
REGISTRY = {
    "nb_gauss": (lambda: _scale(GaussianNB(var_smoothing=1e-6)), "NaiveBayes", True),
    "svm_linear": (lambda: _scale(SGDClassifier(loss="hinge", class_weight="balanced",
                                                max_iter=1000, random_state=42)), "LinearSVM", True),
    "svm_linear_cal": (lambda: _scale(LinearSVC(class_weight="balanced", C=0.1,
                                                max_iter=2000, random_state=42)), "LinearSVM", True),
    "knn3": (lambda: _scale(KNeighborsClassifier(n_neighbors=3, weights="distance", n_jobs=-1)), "KNN", True),
    "knn5": (lambda: _scale(KNeighborsClassifier(n_neighbors=5, weights="distance", n_jobs=-1)), "KNN", True),
    "knn7": (lambda: _scale(KNeighborsClassifier(n_neighbors=7, weights="distance", n_jobs=-1)), "KNN", True),
    "dt": (lambda: RandomForestClassifier(n_estimators=1, max_depth=16,
                                          min_samples_leaf=20, class_weight="balanced",
                                          random_state=42, n_jobs=1), "Tree", False),
    "rf": (lambda: RandomForestClassifier(n_estimators=200, max_depth=None,
                                          min_samples_leaf=2, class_weight="balanced",
                                          random_state=42, n_jobs=-1), "Tree", False),
    "rf_bal": (lambda: RandomForestClassifier(n_estimators=200, class_weight="balanced_subsample",
                                              random_state=42, n_jobs=-1), "Tree", False),
    "et": (lambda: ExtraTreesClassifier(n_estimators=200, max_depth=None,
                                       min_samples_leaf=2, class_weight="balanced",
                                       random_state=42, n_jobs=-1), "Tree", False),
    "bag_dt": (lambda: BaggingClassifier(n_estimators=50, random_state=42, n_jobs=-1), "Tree", False),
    "xgb": (lambda: _xgb(n_estimators=400, max_depth=8, learning_rate=0.1,
                         subsample=0.9, colsample_bytree=0.9, reg_lambda=1.0), "Boost", False),
    "lgbm": (lambda: _lgbm(n_estimators=400, learning_rate=0.1, num_leaves=127,
                           subsample=0.9, colsample_bytree=0.9), "Boost", False),
    "hgb": (lambda: HistGradientBoostingClassifier(max_iter=400, learning_rate=0.1,
                                                   max_leaf_nodes=127,
                                                   class_weight="balanced",
                                                   random_state=42), "Boost", False),
    "logreg": (lambda: _scale(LogisticRegression(max_iter=1000, class_weight="balanced",
                                                 C=1.0, random_state=42, solver="lbfgs")), "Linear", False),
}


def build(exp_id: str):
    return REGISTRY[exp_id][0]()


def family(exp_id: str) -> str:
    return REGISTRY[exp_id][1]


def needs_subset(exp_id: str) -> bool:
    return REGISTRY[exp_id][2]

"""Fraud-detection metrics (M5).

Accuracy is deliberately NOT the headline metric. Selection prioritises PR-AUC,
fraud recall, precision, F1 and the operational false-positive burden, all evaluated
at a threshold chosen on validation data only.
"""

from __future__ import annotations

import numpy as np
from sklearn.metrics import (average_precision_score, confusion_matrix, f1_score,
                             precision_score, recall_score, roc_auc_score)


def pr_auc(y_true, prob):
    return float(average_precision_score(y_true, prob)) if len(set(y_true)) > 1 else float("nan")


def roc_auc(y_true, prob):
    return float(roc_auc_score(y_true, prob)) if len(set(y_true)) > 1 else float("nan")


def metrics_at(y_true, prob, threshold: float) -> dict:
    y_true = np.asarray(y_true)
    pred = (np.asarray(prob) >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_true, pred, labels=[0, 1]).ravel()
    n = len(y_true)
    return {
        "threshold": float(threshold),
        "precision": float(precision_score(y_true, pred, zero_division=0)),
        "recall": float(recall_score(y_true, pred, zero_division=0)),
        "f1": float(f1_score(y_true, pred, zero_division=0)),
        "true_positives": int(tp),
        "false_positives": int(fp),
        "false_negatives": int(fn),
        "true_negatives": int(tn),
        "fpr": float(fp / (fp + tn)) if (fp + tn) else 0.0,
        "flag_rate": float((tp + fp) / n) if n else 0.0,
        "accuracy": float((tp + tn) / n) if n else 0.0,
    }


def best_threshold_by_f1(y_true, prob, grid=None) -> tuple:
    """Threshold on validation maximising F1 (documented, reproducible grid)."""
    y_true = np.asarray(y_true)
    prob = np.asarray(prob)
    if grid is None:
        grid = np.round(np.arange(0.01, 0.96, 0.01), 2)
    best_t, best_f1 = 0.5, -1.0
    for t in grid:
        m = metrics_at(y_true, prob, float(t))
        if m["f1"] > best_f1:
            best_f1, best_t = m["f1"], float(t)
    return best_t, best_f1

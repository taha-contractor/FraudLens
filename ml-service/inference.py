"""Model loading + causal, single-source-of-truth feature assembly for inference.

This module owns the exact 17-feature contract of the winning XGBoost model and
reproduces the nine causal history features by importing — never re-deriving —
the M4 :class:`features.causal.CausalFeatureBuilder`. A transaction is scored
only from history strictly earlier than it under the same causal clock used at
training time, so online scoring cannot leak or drift from the offline pipeline.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

import joblib
import numpy as np

import config

# The service reuses the trained feature pipeline verbatim. ml/src is placed on
# the path (ahead of this dir) so `features.causal` and its package imports
# resolve to the exact code that produced the artifact.
sys.path.insert(0, str(config.ML_SRC_PATH))
from features.causal import CausalFeatureBuilder, causal_key  # noqa: E402

# Fixed PaySim taxonomy the model was trained on (order is significant for the
# type_* one-hot columns; mirrors generator.schema.TRANSACTION_TYPES).
TRANSACTION_TYPES = ["PAYMENT", "CASH_IN", "CASH_OUT", "TRANSFER", "DEBIT"]

# Synonyms observed in generic ingestion so a reasonable pre-taxonomy type still
# maps to the model's five-way one-hot instead of silently defaulting.
_TYPE_SYNONYMS = {
    "ONLINEPAYMENT": "PAYMENT", "BILLPAY": "PAYMENT", "PURCHASE": "PAYMENT",
    "PAYMENT_OUT": "PAYMENT",
    "CASHIN": "CASH_IN", "DEPOSIT": "CASH_IN", "TOPUP": "CASH_IN",
    "CASHOUT": "CASH_OUT", "WITHDRAWAL": "CASH_OUT", "WITHDRAW": "CASH_OUT",
    "TRANSFER_OUT": "TRANSFER", "REMITTANCE": "TRANSFER",
}

_bundle: dict | None = None


class InferenceError(Exception):
    """A per-transaction, non-retryable scoring problem (missing/invalid input).

    Raised instead of silently returning a low-risk score, so the caller can
    surface an explicit UNSCORED assessment.
    """


def get_bundle() -> dict:
    """Load the winner artifact exactly once and cache it for the process."""
    global _bundle
    if _bundle is None:
        obj = joblib.load(config.MODEL_ARTIFACT_PATH)
        if not isinstance(obj, dict) or "single_model" not in obj:
            raise RuntimeError("winner_model.joblib is not a recognized model bundle")
        if obj.get("ensemble_kind") != "single":
            raise RuntimeError("this service supports the single-model bundle only")
        with open(config.FEATURE_NAMES_PATH) as fh:
            names = json.load(fh)
        if list(obj["feature_columns"]) != names:
            raise RuntimeError("bundle feature_columns disagree with feature_names.json")
        obj["feature_names"] = names
        obj["feature_index"] = {name: i for i, name in enumerate(names)}
        _bundle = obj
    return _bundle


def model_metadata() -> dict:
    b = get_bundle()
    return {
        "winner_id": b["winner_id"],
        "model_family": type(b["single_model"]).__name__,
        "threshold": float(b["threshold"]),
        "ensemble_kind": b["ensemble_kind"],
        "needs_scaling": bool(b["needs_scaling"]),
        "n_features": len(b["feature_names"]),
        "feature_names": b["feature_names"],
    }


def map_type(value) -> str | None:
    """Map a raw transaction type onto the model taxonomy, or None if unmappable."""
    if value is None:
        return None
    key = str(value).strip().upper()
    if key in TRANSACTION_TYPES:
        return key
    return _TYPE_SYNONYMS.get(key.replace("-", "_").replace(" ", "_"))


def _as_causal_row(txn: dict) -> dict:
    """Normalize one backend transaction into the causal builder's row schema.

    ``record_uid`` is the stable identity the backend sends (its Mongo _id); the
    builder only consumes nameOrig / nameDest / amount / step / event_ts.
    """
    ts = txn.get("timestamp")
    if not isinstance(ts, str):
        raise InferenceError("transaction is missing a valid timestamp")
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError as exc:
        raise InferenceError(f"unparseable timestamp: {ts!r}") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    epoch = int(dt.timestamp())
    # PaySim "step" is a 1-based day index; the model only consumes its day
    # resolution, so a UTC day ordinal reproduces the training-time semantics
    # (constant within a day, +1 across a day boundary).
    step = (dt.year - 1970) * 365 + dt.timetuple().tm_yday
    return {
        "record_uid": str(txn.get("record_uid") or txn.get("id")),
        "step": step,
        "event_ts": dt.strftime("%Y-%m-%d %H:%M:%S"),
        "type": txn.get("type"),
        "amount": txn.get("amount"),
        "nameOrig": str(txn.get("nameOrig") or txn.get("sourceAccountId")),
        "nameDest": str(txn.get("nameDest") or txn.get("destinationAccountId")),
        "ts_epoch": epoch,
    }


def _assemble(row: dict, hist: dict, mapped_type: str) -> np.ndarray:
    b = get_bundle()
    idx = b["feature_index"]
    vec = np.zeros(len(b["feature_names"]), dtype=np.float32)
    vec[idx["step"]] = float(row["step"])
    vec[idx["amount"]] = float(row["amount"])
    vec[idx["oldbalanceOrg"]] = float(row.get("oldbalanceOrg") or 0.0)
    vec[idx[f"type_{mapped_type}"]] = 1.0
    for name, value in hist.items():
        vec[idx[name]] = float(value)
    return vec


def score_transactions(transactions: list, targets: list | None = None) -> dict:
    """Replay a case's transactions in causal order and score the targets.

    ``transactions`` must be the case's full relevant history (any subset that
    contains every strictly-prior record of each target's origin/destination
    accounts). Each target's nine history features are computed by the reused
    CausalFeatureBuilder strictly from records earlier than it under the
    ``(step, ts, uid)`` causal key — never from the target itself or any future
    record — which is what prevents duplicate counting, cross-account
    contamination and lookahead.

    Returns ``{"assessments": {uid: {...}}, "model": {...}, "count": int}``.
    """
    b = get_bundle()
    model = b["single_model"]
    threshold = float(b["threshold"])

    rows = [_as_causal_row(t) for t in transactions]
    rows = [r for r in rows if r["record_uid"]]
    rows.sort(key=causal_key)  # exact causal ordering from ml/src

    target_set = {str(t) for t in targets} if targets else None
    want = {r["record_uid"] for r in rows} if target_set is None else target_set

    builder = CausalFeatureBuilder()
    assessments: dict = {}
    feature_names = b["feature_names"]
    for row in rows:
        hist = builder.add(row)  # strictly-prior features, then folded
        uid = row["record_uid"]
        if uid in want and uid not in assessments:
            mapped = map_type(row["type"])
            if mapped is None:
                assessments[uid] = _unscored(
                    row, feature_names, hist,
                    f"unsupported transactionType {row['type']!r}: not in the model taxonomy "
                    "(PAYMENT, CASH_IN, CASH_OUT, TRANSFER, DEBIT)",
                )
                continue
            try:
                amount = float(row["amount"])
            except (TypeError, ValueError):
                assessments[uid] = _unscored(row, feature_names, hist, "amount is not numeric")
                continue
            vec = _assemble(row, hist, mapped)
            proba = float(model.predict_proba(vec.reshape(1, -1))[0, 1])
            assessments[uid] = _assess(row, feature_names, hist, mapped, vec, proba, threshold)

    missing = want - set(assessments)
    for uid in missing:
        assessments[uid] = {
            "record_uid": uid, "status": "error", "error": "transaction not found in provided history",
        }
    return {"assessments": assessments, "model": model_metadata(), "count": len(assessments)}


def _assess(row, feature_names, hist, mapped_type, vec, proba, threshold) -> dict:
    return {
        "record_uid": row["record_uid"],
        "status": "scored",
        "risk_score": round(proba, 6),
        "threshold": threshold,
        "risk_classification": classify(proba, threshold),
        "model_prediction": bool(proba >= threshold),
        "mapped_type": mapped_type,
        "features": {name: float(vec[i]) for i, name in enumerate(feature_names)},
    }


def _unscored(row, feature_names, hist, reason) -> dict:
    """Explicit non-score: never a silent low-risk default. The caller must treat
    this as 'assessment unavailable', not as 'safe'."""
    return {
        "record_uid": row["record_uid"],
        "status": "unscored",
        "error": reason,
        "risk_score": None,
        "model_prediction": None,
        "mapped_type": None,
    }


def classify(score: float, threshold: float) -> str:
    """Explainable risk band. ``model_prediction`` is the strict threshold>= call;
    the middle band only aids triage and is not a fraud determination."""
    if score >= threshold:
        return "HIGH"
    if score >= 0.50:
        return "MEDIUM"
    return "LOW"

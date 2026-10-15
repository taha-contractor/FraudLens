"""Focused verification for the ML inference service (Phase 1).

Runs with the service venv (which has fastapi + xgboost + the reused ml/src
pipeline). Pure-stdlib asserts so no extra test framework is required:

    .venv/Scripts/python.exe run_tests.py
"""

from __future__ import annotations

import math

import numpy as np

import inference
from fastapi.testclient import TestClient
import app as service_app


def _base_txns():
    return [
        {"record_uid": "t1", "timestamp": "2026-01-01T10:00:00Z", "amount": 1000,
         "type": "TRANSFER", "sourceAccountId": "A", "destinationAccountId": "B", "oldbalanceOrg": 5000},
        {"record_uid": "t2", "timestamp": "2026-01-01T12:00:00Z", "amount": 2500,
         "type": "PAYMENT", "sourceAccountId": "A", "destinationAccountId": "C", "oldbalanceOrg": 4000},
        {"record_uid": "t3", "timestamp": "2026-01-02T09:00:00Z", "amount": 500000,
         "type": "CASH_OUT", "sourceAccountId": "A", "destinationAccountId": "D", "oldbalanceOrg": 1500},
    ]


def test_model_loads_once():
    a = inference.get_bundle()
    b = inference.get_bundle()
    assert a is b, "model must be loaded exactly once and cached"
    assert a["winner_id"] == "xgb_full"
    assert float(a["threshold"]) == 0.95
    assert len(a["feature_names"]) == 17


def test_feature_order_matches_contract():
    meta = inference.model_metadata()
    expected = ["step", "amount", "oldbalanceOrg", "type_PAYMENT", "type_CASH_IN",
                "type_CASH_OUT", "type_TRANSFER", "type_DEBIT", "origin_txn_count_prev",
                "origin_avg_amount_prev", "origin_amount_dev_prev", "origin_time_since_prev_txn",
                "origin_txn_last24h", "origin_amount_last24h", "origin_unique_dests_last24h",
                "dest_txn_count_prev", "dest_unique_origins_prev"]
    assert meta["feature_names"] == expected, meta["feature_names"]


def test_causality_strictly_prior_only():
    # t3 has two strictly-prior origin-A transactions -> count_prev == 2
    res = inference.score_transactions(_base_txns(), targets=["t3"])
    f = res["assessments"]["t3"]["features"]
    assert f["origin_txn_count_prev"] == 2.0
    assert f["dest_txn_count_prev"] == 0.0  # "D" never a destination before t3
    assert abs(f["origin_time_since_prev_txn"] - 21.0) < 1e-6  # 12:00 -> next day 09:00

    # t1 is the first record for A and B -> no prior history (proves no lookahead
    # and no self-counting)
    r1 = inference.score_transactions(_base_txns(), targets=["t1"])["assessments"]["t1"]
    assert r1["features"]["origin_txn_count_prev"] == 0.0
    assert r1["features"]["dest_unique_origins_prev"] == 0.0


def test_onehot_and_score_shape():
    a = inference.score_transactions(_base_txns(), targets=["t2"])["assessments"]["t2"]
    f = a["features"]
    onehot = sum(f[k] for k in ["type_PAYMENT", "type_CASH_IN", "type_CASH_OUT", "type_TRANSFER", "type_DEBIT"])
    assert onehot == 1.0 and f["type_PAYMENT"] == 1.0
    assert a["status"] == "scored" and 0.0 <= a["risk_score"] <= 1.0
    assert isinstance(a["model_prediction"], bool)
    assert not math.isnan(a["risk_score"])


def test_unsupported_type_is_unscored_not_lowrisk():
    bad = [{"record_uid": "x", "timestamp": "2026-01-01T00:00:00Z", "amount": 10,
            "type": "WIRE", "sourceAccountId": "A", "destinationAccountId": "B"}]
    a = inference.score_transactions(bad, targets=["x"])["assessments"]["x"]
    assert a["status"] == "unscored"
    assert a["risk_score"] is None and a["model_prediction"] is None


def test_account_history_isolation():
    # A different origin account must not inherit A's history
    txns = _base_txns() + [
        {"record_uid": "t4", "timestamp": "2026-01-02T10:00:00Z", "amount": 999,
         "type": "TRANSFER", "sourceAccountId": "Z", "destinationAccountId": "Q", "oldbalanceOrg": 1}]
    f4 = inference.score_transactions(txns, targets=["t4"])["assessments"]["t4"]["features"]
    assert f4["origin_txn_count_prev"] == 0.0  # Z has no prior txns


def test_http_endpoints():
    client = TestClient(service_app.app)
    assert client.get("/health").json()["status"] == "ok"
    model = client.get("/model").json()
    assert model["threshold"] == 0.95 and model["n_features"] == 17

    resp = client.post("/score", json={"transactions": _base_txns(), "targets": ["t3"]})
    assert resp.status_code == 200
    a = resp.json()["assessments"]["t3"]
    assert a["status"] == "scored"

    # invalid pydantic payload -> 422 (validated at the boundary)
    assert client.post("/score", json={"transactions": []}).status_code == 422


def test_batch_single_replay():
    res = inference.score_transactions(_base_txns())  # no targets -> score all
    assert set(res["assessments"]) == {"t1", "t2", "t3"}
    assert res["count"] == 3


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
            passed += 1
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL {t.__name__}: {exc}")
    print(f"\n{passed}/{len(tests)} ml-service tests passed")
    raise SystemExit(0 if passed == len(tests) else 1)

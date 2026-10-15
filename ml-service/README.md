# FraudLens ML Inference Service (`ml-service/`)

A thin, stateless **FastAPI** service that serves the winning XGBoost fraud model to the
FraudLens Node.js backend. It loads the model **exactly once** at startup, validates each
request, and reconstructs the model's 17 features by **reusing** the causal feature
builder from `ml/src` — never re-deriving it — so online scoring cannot drift from
training-time features.

The service holds **no database credentials** and makes **no authorization decisions**.
The backend supplies an already **case-scoped, authorized** transaction set, which keeps
case isolation entirely in the backend.

## Requirements

- **Python 3.13** (matches the environment that produced the artifact)
- Dependencies pinned in [`requirements.txt`](requirements.txt): FastAPI 0.143.2,
  Uvicorn 0.32.1, pydantic 2.10.4, scikit-learn 1.9.0, **XGBoost 3.4.1**, joblib 1.5.3,
  numpy 2.5.2 (httpx for tests). Exact versions are pinned because they guarantee
  `winner_model.joblib` deserializes correctly.

## Setup

```powershell
cd ml-service
python -m venv .venv
.venv\Scripts\activate                 # Unix: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                    # defaults are usually sufficient
```

## Running

```powershell
python run_server.py                   # binds 127.0.0.1:8100
python run_server.py 8100              # explicit port
```

Binds to `127.0.0.1` so the backend can reach it locally. For production, run behind a
proper ASGI server / reverse proxy and restrict network access.

## Configuration (`.env`, gitignored — never the backend's `.env`)

| Variable | Purpose | Default |
|---|---|---|
| `ML_SERVICE_PORT` | Port the backend talks to | `8100` |
| `MODEL_ARTIFACT_PATH` | Winner model artifact | `../ml/artifacts/m5/winner_model.joblib` |
| `FEATURE_NAMES_PATH` | Feature contract | `../ml/artifacts/m5/feature_names.json` |
| `ML_SRC_PATH` | Causal feature source of truth | `../ml/src` |
| `ML_SERVICE_TOKEN` | Optional shared secret | unset |
| `MONGODB_URI` / `MONGODB_DB` | Not used by this service (local tooling only) | unset |

## Model artifact requirement

The service requires `ml/artifacts/m5/winner_model.joblib` (a single-model bundle with a
`single_model` key and `ensemble_kind == "single"`) plus `feature_names.json`. If the
artifact is missing or its feature columns disagree with `feature_names.json`, the service
**raises** rather than serving. Regenerate the artifact with the M5 pipeline in
[`../ml/README.md`](../ml/README.md) (it is a large, Git-ignored binary).

## Endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `GET` | `/health` | none | Liveness: `{"status":"ok","service":"fraudlens-ml-inference"}` |
| `GET` | `/model` | none | Model metadata; `503` if the artifact cannot load |
| `POST` | `/score` | `X-ML-Token` (if `ML_SERVICE_TOKEN` set) | Score a case's transactions |

### `GET /model` response

```json
{
  "status": "ok",
  "winner_id": "xgb_full",
  "model_family": "XGBClassifier",
  "threshold": 0.95,
  "ensemble_kind": "single",
  "needs_scaling": false,
  "n_features": 17,
  "feature_names": ["step", "amount", "oldbalanceOrg", "type_PAYMENT", "..."]
}
```

## The 17-feature inference contract

Order is significant and frozen (from `feature_names.json`):

```
step, amount, oldbalanceOrg,
type_PAYMENT, type_CASH_IN, type_CASH_OUT, type_TRANSFER, type_DEBIT,
origin_txn_count_prev, origin_avg_amount_prev, origin_amount_dev_prev,
origin_time_since_prev_txn, origin_txn_last24h, origin_amount_last24h,
origin_unique_dests_last24h, dest_txn_count_prev, dest_unique_origins_prev
```

### Historical feature generation (causal replay)

The nine `origin_*` / `dest_*` history features are **not** sent by the caller. The
service rebuilds them by replaying the provided transactions through `CausalFeatureBuilder`
in strict causal order (`(step, ts, uid)`), computing each target's history **only from
records strictly earlier than it** — never the target itself, never any future record.
This is what prevents lookahead, duplicate counting, and cross-account contamination, and
it requires the caller to send the transaction's relevant prior history, not just the row.

### `POST /score` — request

```json
{
  "transactions": [
    {
      "record_uid": "665f...c1",
      "timestamp": "2026-03-01T10:15:00Z",
      "amount": 5000.0,
      "type": "TRANSFER",
      "oldbalanceOrg": 12000.0,
      "sourceAccountId": "C1234",
      "destinationAccountId": "M5678",
      "nameOrig": "C1234",
      "nameDest": "M5678"
    }
  ],
  "targets": ["665f...c1"]
}
```

- `transactions` — the case's relevant history (must include every strictly-prior record
  for each target's origin/destination). **Required**, min length 1.
- `targets` — subset of `record_uid`s to score; omit to score every provided transaction.
- `record_uid`, `timestamp` are required per transaction; `type`, `amount` drive scoring;
  `oldbalanceOrg` is optional (defaults to `0.0`); the identity fields are used for the
  causal key (`nameOrig`/`nameDest` fall back to `sourceAccountId`/`destinationAccountId`).

### `POST /score` — response

```json
{
  "assessments": {
    "665f...c1": {
      "record_uid": "665f...c1",
      "status": "scored",
      "risk_score": 0.0064,
      "threshold": 0.95,
      "risk_classification": "LOW",
      "model_prediction": false,
      "mapped_type": "TRANSFER",
      "features": { "step": 20605.0, "amount": 5000.0, "...": 0.0 }
    }
  },
  "model": { "winner_id": "xgb_full", "threshold": 0.95, "n_features": 17, "...": "..." },
  "count": 1
}
```

`risk_classification`: **HIGH** if `score >= 0.95`, **MEDIUM** if `>= 0.50`, else **LOW**.
`model_prediction` is the strict `score >= threshold` call. A prediction is an
investigation signal, **not** a fraud determination.

## Error behaviour when scoring is unavailable

The service **never** silently assigns a low-risk score.

- **Unscored (per transaction, HTTP 200):** an unmappable `type` (not one of PAYMENT,
  CASH_IN, CASH_OUT, TRANSFER, DEBIT after synonym mapping), or a non-numeric `amount`,
  returns `status: "unscored"` with `risk_score: null` and an explicit `error` reason. The
  caller must treat this as *assessment unavailable*, not *safe*.
- **Not found:** a `targets` id absent from the provided history returns
  `status: "error"`, `error: "transaction not found in provided history"`.
- **Bad request (400):** input that cannot be replayed at all (`InferenceError`, e.g. a
  missing/unparseable timestamp).
- **Server error (500):** a genuine inference failure — surfaced, not degraded.
- **Service unavailable (503):** `/model` when the artifact fails to load.

## Authentication

If `ML_SERVICE_TOKEN` is set, `POST /score` requires a matching `X-ML-Token` header;
otherwise requests with a wrong/missing token are rejected `401`. `/health` and `/model`
are unauthenticated. The backend sends the same shared secret. Keep the service bound to
localhost or otherwise network-restricted; do not expose it publicly without TLS.

## Tests

```powershell
cd ml-service
python run_tests.py                    # FastAPI TestClient, no live server needed
```

The backend also has an integration test that spawns this service for live scoring:
`cd backend && npm test` (see `backend/tests/risk-assessment.test.js`).

## Files

| File | Role |
|---|---|
| `app.py` | FastAPI app, request models, endpoints |
| `inference.py` | Model load (once), causal replay, 17-feature assembly, scoring |
| `config.py` | Local `.env` loader + resolved paths |
| `run_server.py` | Uvicorn entrypoint |
| `run_tests.py` | Focused service tests |

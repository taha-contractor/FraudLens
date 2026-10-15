"""FraudLens ML inference service (Phase 1).

A thin, maintainable FastAPI front-end over the winning XGBoost model. The model
is loaded exactly once at startup; every request is validated and scored through
the reused causal feature pipeline. The service holds no database credentials and
makes no authorization decisions — the Node backend supplies an already
case-scoped, authorized transaction set, which keeps case isolation intact.
"""

from __future__ import annotations

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

import config
import inference

app = FastAPI(title="FraudLens ML Inference Service", version="1.0.0")


class TransactionIn(BaseModel):
    """One transaction as projected by the backend, carrying the fields the
    causal pipeline and model require. IDs are opaque strings (Mongo _id)."""

    record_uid: str = Field(..., min_length=1, max_length=64)
    timestamp: str = Field(..., min_length=4, max_length=40)
    amount: float | None = None
    type: str | None = None
    oldbalanceOrg: float | None = None
    sourceAccountId: str | None = None
    destinationAccountId: str | None = None
    nameOrig: str | None = None
    nameDest: str | None = None


class ScoreRequest(BaseModel):
    transactions: list[TransactionIn] = Field(..., min_length=1)
    targets: list[str] | None = None  # omit to score every provided transaction


def _require_token(token: str | None) -> None:
    if config.ML_SERVICE_TOKEN and token != config.ML_SERVICE_TOKEN:
        raise HTTPException(status_code=401, detail="invalid ML service token")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "fraudlens-ml-inference"}


@app.get("/model")
def model_info() -> dict:
    try:
        return {"status": "ok", **inference.model_metadata()}
    except Exception as exc:  # artifact failed to load — report, never fake it
        raise HTTPException(status_code=503, detail=f"model unavailable: {exc}")


@app.post("/score")
def score(payload: ScoreRequest, x_ml_token: str | None = Header(default=None)) -> dict:
    _require_token(x_ml_token)
    try:
        return inference.score_transactions(
            [t.model_dump() for t in payload.transactions], payload.targets
        )
    except inference.InferenceError as exc:
        # Malformed input that cannot be replayed at all (not a per-row gap).
        raise HTTPException(status_code=400, detail=str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        # A genuine inference failure must surface, not degrade to a low score.
        raise HTTPException(status_code=500, detail=f"inference failed: {exc}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=config.PORT)

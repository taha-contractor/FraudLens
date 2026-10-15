# FraudLens

**An AI-Powered Multi-Model Financial Fraud Investigation System**

FraudLens is a full-stack platform for investigating financial fraud. It combines a
machine-learning risk model with a case-centred investigation workflow so that an
investigator can import transactions and documents, score transactions for fraud
risk, explore patterns, and record evidence-backed findings. The investigator always
remains the decision-maker: ML output is an *investigation signal*, never proof of
fraud.

This project is a B.Tech major project and is built to be modular, explainable and
achievable rather than a production banking system.

---

## Problem statement

Financial fraud investigations involve large volumes of transactions and documents.
Manually spotting suspicious activity across accounts, time windows and counterparties
is slow and error-prone, and purely automated scoring is not trustworthy without a
human reviewing the supporting evidence. FraudLens aims to assist — not replace — the
investigator by:

- scoring each transaction for fraud risk with a trained ML model plus explainable rules,
- organising all data into isolated **cases** so cross-case contamination cannot occur,
- surfacing suspicious transactions, account activity and timelines for review,
- providing an interface in which findings can be traced back to concrete evidence.

## Key features (implemented)

- **Case-scoped investigation** — every resource (transactions, accounts, documents,
  evidence, risk assessments) is tied to a `caseId` with server-enforced isolation.
- **Authentication** — JWT-based register/login, protected APIs.
- **Transaction management** — single create + CSV import, server-side filtered listing
  (never loads full datasets into the browser), per-transaction detail.
- **ML risk assessment** — transactions are projected to a Python FastAPI inference
  service and scored by the winning XGBoost model; scores, risk level and the exact
  feature vector are persisted in MongoDB.
- **Explainable signals** — a rule layer (e.g. high-value, night activity) runs alongside
  the model so alerts carry human-readable reasons.
- **Read-only analytics** — case summary, timeline (day/hour buckets), suspicious
  transactions and per-account activity.
- **Documents & evidence** — authenticated upload/storage (no public static mount) and
  evidence records linked to transactions/accounts.
- **React + Tailwind UI** — login, dashboard, transaction explorer, transaction details
  (with model score and features), cases, case workspace, risk analytics, and a model
  information screen.

## Planned (not yet implemented)

- **Retrieval-Augmented Generation (RAG)** over case documents/evidence.
- **LLM-assisted investigation** with controlled, case-scoped tools.
- **OCR** for scanned documents, entity resolution, relationship/fund-flow graphs,
  timeline auto-construction, and investigation report generation.
- A live **model-evaluation endpoint** (the UI Model Information screen currently shows
  saved evaluation metrics from an isolated, clearly-labelled reference module; the live
  metadata — winner, threshold, feature contract — already comes from the API).

---

## System architecture

```
 Investigator
      |
      v
 React + Tailwind frontend  (Vite, React Router, Axios, Recharts)
      |  HTTP /api/v1 (JWT)
      v
 Node.js + Express backend  (orchestration, auth, case isolation, persistence)
      |                    |
      v                    v
   MongoDB            Python FastAPI ML inference service
 (cases, txn,          (loads XGBoost winner once,
  risk, docs,          reuses the ml/src causal feature builder,
  evidence)            returns risk score + 17-feature vector)
                             ^
                             | reads (at startup)
                    ml/artifacts/m5/winner_model.joblib
```

- **Frontend** talks only to the Node backend over `/api/v1`.
- **Backend** owns authentication, case authorization and persistence. It projects an
  already case-scoped, authorized transaction set to the ML service for scoring.
- **ML service** is stateless and holds **no database credentials** and makes **no
  authorization decisions** — case isolation stays in the backend. It imports the exact
  `ml/src` causal feature builder so online scoring cannot drift from training features.

Full detail: [`docs/System_Architecture.md`](docs/System_Architecture.md),
[`docs/API_Architecture.md`](docs/API_Architecture.md),
[`docs/Database_design.md`](docs/Database_design.md).

## Technology stack

| Layer | Technology |
|---|---|
| Frontend | React 19, Vite, Tailwind CSS v4, React Router 7, Axios, Recharts |
| Backend | Node.js (ESM), Express 5, Mongoose 9 |
| Database | MongoDB (Atlas or local) |
| Auth | JWT (jsonwebtoken), bcryptjs |
| ML training | Python 3.13, pandas, scikit-learn, XGBoost |
| ML inference service | FastAPI, Uvicorn, joblib |
| Winning model | XGBoost (`XGBClassifier`), 17 features |

## Repository structure

```
FraudLens/
├── backend/          # Node.js + Express API, services, models, tests
├── frontend/         # React + Vite + Tailwind UI prototype
├── ml/               # Operational PaySim ML pipeline
│   ├── data/         #   raw/ (immutable PaySim) + processed/ + splits/ (generated, gitignored)
│   ├── src/          #   generator, features, modeling, data loaders
│   ├── tests/        #   Python unittest suite
│   ├── artifacts/    #   m5 winner_model.joblib + feature_names/winner_config (model gitignored)
│   ├── reports/      #   dataset design + M5 evaluation reports/manifests
│   └── README.md
├── ml-service/       # FastAPI inference service (consumes the winner model)
├── docs/             # Architecture, API, database, ML & milestone documentation
├── research/         # Literature survey, requirements, research plan
├── .gitignore
└── README.md
```

---

## Local setup

### Prerequisites

- **Node.js 18+** and npm (backend + frontend)
- **Python 3.13** (ML inference service)
- **MongoDB** — a local instance or a MongoDB Atlas connection string

### 1. Backend

```bash
cd backend
npm install
cp .env.example .env        # then set MONGODB_URI and a strong JWT_SECRET
npm run dev                 # or: npm start   (http://localhost:5000)
```

Key backend environment variables (see `backend/.env.example`):

| Variable | Purpose | Default |
|---|---|---|
| `PORT` | HTTP port | `5000` |
| `MONGODB_URI` | MongoDB connection string | (required) |
| `JWT_SECRET` / `JWT_EXPIRES_IN` | Auth signing | (set secret) / `1h` |
| `ML_SERVICE_URL` | ML inference service base URL | `http://127.0.0.1:8100` |
| `ML_SERVICE_TOKEN` | Optional shared secret (`X-ML-Token`) | unset |
| `ML_SERVICE_TIMEOUT_MS` | Request timeout | `15000` |

### 2. ML inference service

```bash
cd ml-service
python -m venv .venv
.venv\Scripts\activate                 # Windows (source .venv/bin/activate on Unix)
pip install -r requirements.txt
cp .env.example .env                    # defaults are usually sufficient
python run_server.py                    # binds 127.0.0.1:8100
```

The service loads `ml/artifacts/m5/winner_model.joblib` at startup and imports the
causal feature builder from `ml/src`. If the artifact is missing it reports the model as
**unavailable** rather than silently returning low-risk scores. Endpoints: `GET /health`,
`GET /model`, `POST /score`. See [`ml-service/README.md`](ml-service/README.md).

> If `ml/artifacts/m5/winner_model.joblib` is not present locally (it is a large
> generated artifact and is not committed to Git), reproduce it with the M5 pipeline in
> [`ml/README.md`](ml/README.md). Its small contract files (`feature_names.json`,
> `winner_config.json`) *are* committed.

### 3. Frontend

```bash
cd frontend
npm install
cp .env.example .env.local              # VITE_API_BASE_URL (default http://localhost:5000/api/v1)
npm run dev                             # Vite dev server (http://localhost:5173)
npm run build                           # production build -> dist/
```

### Running the whole application

1. Start the ML inference service (`:8100`).
2. Start the backend (`:5000`) — set `ML_SERVICE_URL` to match.
3. Start the frontend (`:5173` by default) — set `VITE_API_BASE_URL` to the backend.
4. Register/login in the UI, create a case, import transactions, and run a risk
   assessment.

## Transaction risk-assessment workflow

1. Transactions are created individually or imported from CSV into a **case**.
2. An assessment request (`POST /api/v1/cases/:caseId/transactions/assess`) collects the
   case's transactions and replays them through the causal feature builder **per case**,
   preserving the exact 17-feature training order.
3. The ML service returns a fraud probability per transaction; the backend maps it to a
   risk level using the frozen operating threshold **0.95** (HIGH at/above 0.95, MEDIUM
   at/above 0.50, otherwise LOW) and persists `riskScore`, `riskLevel` and model metadata.
4. Transactions whose type cannot be mapped to the model's taxonomy, or that are missing
   required fields, are returned **unscored** (`risk_score: null`) — never silently
   labelled low-risk.

The 17 features (fixed order):

```
step, amount, oldbalanceOrg,
type_PAYMENT, type_CASH_IN, type_CASH_OUT, type_TRANSFER, type_DEBIT,
origin_txn_count_prev, origin_avg_amount_prev, origin_amount_dev_prev,
origin_time_since_prev_txn, origin_txn_last24h, origin_amount_last24h,
origin_unique_dests_last24h, dest_txn_count_prev, dest_unique_origins_prev
```

## API overview (versioned under `/api/v1`)

| Area | Endpoints |
|---|---|
| Health | `GET /health` |
| Auth | `POST /auth/register`, `POST /auth/login`, `GET /auth/me` |
| Cases | `POST/GET /cases`, `GET/PATCH /cases/:caseId` |
| Accounts | `POST/GET /cases/:caseId/accounts`, `GET .../accounts/:accountId` |
| Transactions | `POST/GET /cases/:caseId/transactions`, `POST .../assess`, `POST .../:id/assess`, `GET .../:id/risk`, `GET .../:id` |
| Analytics | `GET /cases/:caseId/analytics/summary`, `/timeline`, `/suspicious`, `/accounts/:accountId/activity` |
| Documents | `POST/GET /cases/:caseId/documents`, `GET .../:id`, `GET .../:id/status` |
| Evidence | `POST/GET /cases/:caseId/evidence`, `GET .../:id` |
| Risk/model | `GET /risk/model` |

All responses use the envelope `{ success, data }` (errors: `{ success: false, error }`).

## Testing

```bash
# Backend (supertest + in-memory MongoDB)
cd backend && npm test

# ML inference service
cd ml-service && python run_tests.py

# ML pipeline (Python unittest; requires ml/src on PYTHONPATH)
$env:PYTHONPATH="ml/src"; python -m unittest discover -s ml/tests -t ml/tests

# Frontend production build (type/import sanity)
cd frontend && npm run build
```

## Known limitations

- **Synthetic data.** The dataset is generated from the PaySim mobile-money simulator.
  Metrics validate the *pipeline*, not real-world fraud detection accuracy; prevalence is
  artificial and thresholds are dataset-specific.
- **Precision/recall trade-off.** At the 0.95 threshold on the final held-out split the
  model achieves high recall (~0.92) with modest precision (~0.36) — see
  [`ml/README.md`](ml/README.md) and `ml/reports/m5/`.
- **Prototype UI.** Screens are functional against real endpoints; the Model Information
  evaluation-metrics block is an isolated reference module until an evaluation endpoint is
  added.
- **RAG/LLM/OCR** and advanced graph analytics are designed but not yet implemented.

## Roadmap

1. Model-evaluation endpoint to replace the UI reference module.
2. Document processing + OCR, evidence extraction.
3. Case-scoped RAG retrieval over documents and transactions.
4. LLM-assisted investigation with controlled, authorization-checked tools.
5. Relationship / fund-flow visualisation and timeline construction.
6. Investigation report generation and a human-review findings workflow.

## Documentation index

- [`docs/System_Architecture.md`](docs/System_Architecture.md) — full architecture
- [`docs/API_Architecture.md`](docs/API_Architecture.md) — API design
- [`docs/Database_design.md`](docs/Database_design.md) — data model
- [`docs/ML_Dataset_and_Features.md`](docs/ML_Dataset_and_Features.md) — dataset, features, evaluation
- [`docs/ml-research/phase-1/`](docs/ml-research/phase-1/) — earlier India Benchmark research summary
- [`ml/README.md`](ml/README.md) · [`ml-service/README.md`](ml-service/README.md) ·
  [`backend/README.md`](backend/README.md) · [`frontend/README.md`](frontend/README.md)

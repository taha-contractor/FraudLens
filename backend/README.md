# FraudLens Backend

The **Node.js + Express** application and API layer for FraudLens. It is the central
orchestration component: it owns authentication, **case-scoped authorization**, MongoDB
persistence, transaction import, read-only analytics, document/evidence handling, and the
integration with the Python ML inference service.

- Runtime: **Node.js 18+**, ES modules (`"type": "module"`)
- Framework: Express 5, Mongoose 9 (MongoDB)
- Auth: JWT (`jsonwebtoken`) + `bcryptjs`
- API base: **`/api/v1`**, response envelope `{ success, data }` (errors `{ success: false, error }`)

## Setup

```bash
cd backend
npm install
cp .env.example .env
```

### Environment (`.env`)

| Variable | Required | Purpose | Default |
|---|---|---|---|
| `PORT` | no | HTTP port | `5000` |
| `NODE_ENV` | no | Environment | `development` |
| `MONGODB_URI` | **yes** | MongoDB connection string | — |
| `JWT_SECRET` | **yes** | JWT signing secret (strong random) | — |
| `JWT_EXPIRES_IN` | no | Token lifetime | `1h` |
| `UPLOAD_STORAGE_DIR` | no | Private document directory | `./uploads` |
| `MAX_UPLOAD_SIZE_MB` | no | Upload size cap | `10` |
| `ANALYTICS_TIMEZONE` | no | Hour/night + timeline bucketing | `Asia/Kolkata` |
| `ANALYTICS_HIGH_VALUE_THRESHOLD` | no | HIGH_VALUE rule threshold | `50000` |
| `ANALYTICS_MAX_SCAN_TRANSACTIONS` | no | Scan bound for suspicious requests | `5000` |
| `ML_SERVICE_URL` | no | ML inference service base URL | `http://127.0.0.1:8100` |
| `ML_SERVICE_TOKEN` | no | Shared secret sent as `X-ML-Token` | unset |
| `ML_SERVICE_TIMEOUT_MS` | no | ML request timeout | `15000` |
| `ML_ASSESS_MAX_TRANSACTIONS` | no | Cap on transactions replayed per assess | `10000` |

Never commit real `MONGODB_URI` / `JWT_SECRET` values. `.env` is Git-ignored;
`.env.example` is the committed template.

## Running

```bash
npm run dev      # nodemon
npm start        # node server.js
```

## MongoDB

The connection is configured by `MONGODB_URI` (`src/config/database.js`). Collections are
case-centric (`cases`, `accounts`, `transactions`, `documents`, `evidence`, `users`, plus a
`riskAssessment` sub-document on transactions). See
[`../docs/Database_design.md`](../docs/Database_design.md).

## Authentication

- `POST /api/v1/auth/register`, `POST /api/v1/auth/login` issue a JWT `accessToken`.
- `GET /api/v1/auth/me` returns the current user.
- All case-scoped and risk routes require `Authorization: Bearer <token>`
  (`src/middleware/auth.middleware.js`).

## Case isolation

Every transaction/account/document/evidence/analytics route is mounted **under a case**:

```
/api/v1/cases/:caseId/accounts
/api/v1/cases/:caseId/transactions
/api/v1/cases/:caseId/documents
/api/v1/cases/:caseId/evidence
/api/v1/cases/:caseId/analytics
```

The `caseId` is validated and **authorization-checked in the service layer**, so a user
cannot read or write resources belonging to a case they are not permitted to access. The
ML service is stateless and never sees case authorization — the backend only forwards an
already case-scoped transaction set, which is what preserves isolation across scoring.

## API routes

| Area | Endpoints |
|---|---|
| Health | `GET /api/v1/health` |
| Auth | `POST /auth/register`, `POST /auth/login`, `GET /auth/me` |
| Cases | `POST /cases`, `GET /cases`, `GET /cases/:caseId`, `PATCH /cases/:caseId` |
| Accounts | `POST/GET /cases/:caseId/accounts`, `GET .../accounts/:accountId` |
| Transactions | `POST/GET /cases/:caseId/transactions`, `POST .../assess`, `POST .../:transactionId/assess`, `GET .../:transactionId/risk`, `GET .../:transactionId` |
| Analytics | `GET /cases/:caseId/analytics/summary`, `/timeline`, `/suspicious`, `/accounts/:accountId/activity` |
| Documents | `POST/GET /cases/:caseId/documents`, `GET .../:documentId`, `GET .../:documentId/status` |
| Evidence | `POST/GET /cases/:caseId/evidence`, `GET .../:evidenceId` |
| Risk / model | `GET /api/v1/risk/model` (case-independent model + service metadata) |

Uploads are stored privately and are **not** served via `express.static` — uploaded files
are reachable only through the authorization-checked document APIs.

## Risk-assessment integration

The transaction workflow calls the ML inference service (`ML_SERVICE_URL`) to score a
case's transactions:

- **Batch:** `POST /cases/:caseId/transactions/assess` — project the case's transactions to
  the service, which replays them through the causal feature builder and returns a score per
  transaction.
- **Single:** `POST /cases/:caseId/transactions/:transactionId/assess`.
- **Read:** `GET /cases/:caseId/transactions/:transactionId/risk`.

Key services: `src/services/ml-service.client.js` (HTTP client + shared-secret header),
`src/services/risk-assessment.service.js` (projection, persistence, dedup so a transaction
is not re-scored unnecessarily), controller `src/controllers/risk.controller.js`.

Persistence: `riskScore`, `riskLevel` (`HIGH`/`MEDIUM`/`LOW` at threshold **0.95** / 0.50),
`modelPrediction`, and the exact feature vector / model metadata are stored on the
transaction. The operating threshold and 17-feature order match the model contract in
[`../ml-service/README.md`](../ml-service/README.md). **A transaction whose type cannot be
mapped is stored as unscored (`risk_score: null`) — never silently as low-risk.** An ML
service failure surfaces as an error; it is never swallowed into a low score.

## Testing

```bash
cd backend
npm test               # node --test "tests/**/*.test.js" (supertest + mongodb-memory-server)
```

`tests/risk-assessment.test.js` includes **live-ML** integration subtests that spawn the
FastAPI service from `../ml-service` (using its `.venv`) and score over real HTTP. They are
skipped automatically if the ML service virtualenv is unavailable, so the suite passes
without Python installed.

## Notes for the hardening phase

CORS is currently fully open (`app.use(cors())`) for local development, and rate limiting
is not yet applied. These are tracked as future security-hardening work and are out of scope
for repository cleanup.

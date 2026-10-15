# FraudLens Frontend

The **React + Vite + Tailwind CSS** investigation UI for FraudLens. It is a functional
prototype that talks to the real Node backend over `/api/v1` — every screen is wired to
live endpoints, with one clearly-isolated reference module for data that has no endpoint
yet (see [Mock data](#mock-data)).

- React 19, React Router 7, Vite, Tailwind CSS v4 (CSS-first `@theme`)
- Axios (centralized API client), Recharts (charts)

## Requirements

- **Node.js 18+** and npm

## Setup

```bash
cd frontend
npm install
cp .env.example .env.local
```

### Environment

Vite exposes only `VITE_*` variables to the browser.

| Variable | Purpose | Default |
|---|---|---|
| `VITE_API_BASE_URL` | Backend API base URL | `http://localhost:5000/api/v1` |

## Running

```bash
npm run dev          # Vite dev server (default http://localhost:5173)
npm run build        # production build -> dist/
npm run preview      # preview the production build
```

> If port 5173 is busy, Vite uses the next free port (e.g. 5174); the dev server prints the
> actual URL.

## API integration

- `src/api/client.js` — a single Axios instance with the base URL and request/response
  interceptors. The JWT access token is stored in `localStorage` (`fraudlens.token`),
  attached as `Authorization: Bearer <token>` on every request, and a `401` clears the
  session and redirects to login.
- `src/api/endpoints.js` — one typed helper per backend endpoint. Responses use the
  `{ success, data }` envelope; helpers unwrap `data`. **On API failure the UI surfaces the
  error — it never silently falls back to mock data.**
- `src/hooks/useAsync.js` — loading / error / data / reload with a stale-call guard.

The API base URL defaults to the local backend; point `VITE_API_BASE_URL` elsewhere for a
deployed backend.

## Main UI routes

| Route | Screen |
|---|---|
| `/login` | Login |
| `/` | Dashboard (case stats, risk distribution, review queue, model at a glance) |
| `/transactions` | Transaction Explorer (server-side filtering + client search, risk badges) |
| `/transactions/:txnId` | Transaction Details (ML score, 17-feature vector, related transactions) |
| `/cases` | Cases list |
| `/cases/:caseId` | Case Workspace (Overview / Accounts / Documents / Evidence) |
| `/analytics` | Risk Analytics (timeline, rule signals, distribution) |
| `/model` | Model Information (live metadata + reference metrics) |

The Transaction Explorer filters and paginates **server-side** and, where a screen samples
(most-recent N), it is labelled as such — it never loads an entire large dataset into the
browser.

## Backend endpoints used

Auth (`/auth/*`), cases (`/cases`), accounts, transactions (`/cases/:caseId/transactions`,
`/assess`, `/risk`), analytics (`/summary`, `/timeline`, `/suspicious`, account activity),
documents, evidence, and `GET /risk/model` for live model metadata.

## Mock data

There is **no endpoint** yet that serves the model's offline **evaluation metrics**
(PR-AUC/ROC-AUC/precision/recall and dataset limitations). To keep the Model Information
screen complete, those figures live in a single isolated module:

- `src/mocks/prototypeData.js` — exports `MODEL_EVALUATION`, rendered on `/model` with an
  explicit **"Reference data · not computed live"** label. The numbers mirror the saved M5
  reports in `ml/reports/m5/`, but they are **not** fetched from the API at runtime.

This module is kept separate from the API layer and is **never** an API-failure fallback.
**Replacement plan:** add a read-only endpoint (e.g. `GET /api/v1/risk/evaluation`) that
serves the saved M5 report, then delete `src/mocks/prototypeData.js` and read `/model`'s
metrics from the API instead.

Everything else — model identity (`winner_id`, `model_family`, `threshold`, `n_features`,
`feature_names`) and all case/transaction/analytics data — comes from **real endpoints**.

## Troubleshooting

- **Login succeeds but screens are empty / bounce to login** — the token wasn't persisted;
  confirm the backend is running and `VITE_API_BASE_URL` is correct, and check the Network
  tab for a `401`.
- **CORS errors in the console** — the backend must run with CORS enabled (it does by
  default in development) and the browser origin must match; verify the base URL/port.
- **Charts/`/model` show the "unavailable" branch** — the backend or ML service may be
  down; `GET /risk/model` returns `available: false` gracefully rather than faking data.
- **Build failures** — run `npm run build`; Vite reports unresolved imports directly.

import { api, unwrap } from "./client.js";

/**
 * Backend endpoints, one function per call, paths exactly as implemented in
 * backend/src/routes (base /api/v1). Response shapes are the backend's
 * `data` envelopes, documented inline. Each returns a Promise that resolves to
 * the unwrapped `data` object (axios promise is unwrapped via .then, never on
 * the pending promise itself).
 */

// ── Auth ────────────────────────────────────────────────────────────────
export const auth = {
    // { user }
    register: (body) => api.post("/auth/register", body).then(unwrap),
    // { accessToken, user }
    login: (body) => api.post("/auth/login", body).then(unwrap),
    // { user }
    me: () => api.get("/auth/me").then(unwrap),
};

// ── Cases ───────────────────────────────────────────────────────────────
export const cases = {
    // { cases: Case[], count } — Case: {id, caseNumber, title, description, status, investigators, createdBy, createdAt, updatedAt}
    list: () => api.get("/cases").then(unwrap),
    // { case: Case }
    get: (caseId) => api.get(`/cases/${caseId}`).then(unwrap),
    create: (body) => api.post("/cases", body).then(unwrap),
    // { case: Case }
    update: (caseId, body) => api.patch(`/cases/${caseId}`, body).then(unwrap),
};

// ── Accounts (case-scoped) ──────────────────────────────────────────────
export const accounts = {
    // { accounts: Account[], count } — Account: {id, accountNumberMasked, accountType, currency, status, ...}
    list: (caseId) => api.get(`/cases/${caseId}/accounts`).then(unwrap),
};

// ── Transactions (case-scoped) ──────────────────────────────────────────
export const transactions = {
    // { transactions: Txn[], count } — Txn: {id, transactionId, amount, currency, transactionType,
    //   description, merchant, location, timestamp, status, sourceAccountId, destinationAccountId,
    //   riskScore?, riskLevel?, modelPrediction?, oldbalanceOrg?}
    // Filters: { accountId, transactionType, status, from, to, limit (<=1000) }
    list: (caseId, params) => api.get(`/cases/${caseId}/transactions`, { params }).then(unwrap),
    // { transaction: Txn } — :txnId is the Mongo resource id
    get: (caseId, txnId) => api.get(`/cases/${caseId}/transactions/${txnId}`).then(unwrap),
    create: (caseId, body) => api.post(`/cases/${caseId}/transactions`, body).then(unwrap),
};

// ── ML risk assessment (case-scoped) ────────────────────────────────────
export const risk = {
    // { assessment: { status: "scored"|"unscored", transactionId, riskScore?, riskLevel?,
    //   modelPrediction?, features?, mappedType?, threshold?, gaps?, model?, error?, assessedAt } }
    assessOne: (caseId, txnId) => api.post(`/cases/${caseId}/transactions/${txnId}/assess`).then(unwrap),
    // { assessed, scored, unscored, skipped, results[] } — one causal replay for the case
    assessCase: (caseId, body) => api.post(`/cases/${caseId}/transactions/assess`, body || {}).then(unwrap),
    // { transactionId, status, riskScore, riskLevel, modelPrediction, assessment|null }
    getForTransaction: (caseId, txnId) => api.get(`/cases/${caseId}/transactions/${txnId}/risk`).then(unwrap),
    // { available: boolean, model?: { winner_id, model_family, threshold, n_features, feature_names, ... }, reason? }
    modelInfo: () => api.get("/risk/model").then(unwrap),
};

// ── Analytics (case-scoped, read-only) ──────────────────────────────────
export const analytics = {
    // { summary: { totalTransactions, completedTransactions, ...Amounts, highValueTransactionCount,
    //   nightTransactionCount, distinctAccountCount, earliestTransaction, latestTransaction, definitions } }
    summary: (caseId, params) => api.get(`/cases/${caseId}/analytics/summary`, { params }).then(unwrap),
    // { timeline: { interval, bucketCount, buckets: [{start, transactionCount, completedCount, completedAmount, ...}] } }
    timeline: (caseId, params) => api.get(`/cases/${caseId}/analytics/timeline`, { params }).then(unwrap),
    // { suspicious: { count, signals: [{id, transactionId, ...amount, riskScore, reasons[]}], rules, interpretation } }
    suspicious: (caseId, params) => api.get(`/cases/${caseId}/analytics/suspicious`, { params }).then(unwrap),
    // { activity: {...per-account stats, account: Account} }
    accountActivity: (caseId, accountId, params) =>
        api.get(`/cases/${caseId}/analytics/accounts/${accountId}/activity`, { params }).then(unwrap),
};

// ── Documents & evidence (case-scoped) ──────────────────────────────────
export const documents = {
    // { documents: Doc[], count }
    list: (caseId, params) => api.get(`/cases/${caseId}/documents`, { params }).then(unwrap),
};

export const evidence = {
    // { evidence: Ev[], count }
    list: (caseId, params) => api.get(`/cases/${caseId}/evidence`, { params }).then(unwrap),
};

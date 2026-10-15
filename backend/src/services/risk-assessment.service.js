/**
 * Risk-assessment orchestration (ML inference milestone).
 *
 * Flow: authenticate -> case access check -> project the case's transactions ->
 * ask the ML inference service to score them causally -> persist the analytical
 * fields. Case isolation is preserved because the replay set is always filtered
 * by the authorized caseId, so an account's history never crosses cases. A model
 * score is a risk estimate for review, never a fraud determination.
 */

import Transaction from "../models/Transaction.js";
import ApiError from "../utils/ApiError.js";
import { getAccessibleCaseDoc } from "./case.service.js";
import * as mlClient from "./ml-service.client.js";
import { validateTransactionId } from "../validators/transaction.validator.js";

// Upper bound on transactions replayed per request. Investigation cases are
// bounded working sets, so this is a safety valve, not an approximation of
// history; when exceeded the caller is asked to scope the request smaller.
const MAX_REPLAY = Number(process.env.ML_ASSESS_MAX_TRANSACTIONS) || 10000;

function isoOrNull(v) {
    return v instanceof Date ? v.toISOString() : v ?? null;
}

/** Project one case transaction into the causal feature builder's input shape. */
function projectTxn(doc) {
    return {
        record_uid: doc._id.toString(),
        timestamp: doc.timestamp.toISOString(),
        amount: doc.amount,
        type: doc.transactionType,
        oldbalanceOrg: doc.oldbalanceOrg ?? null,
        sourceAccountId: String(doc.sourceAccountId),
        destinationAccountId: String(doc.destinationAccountId),
    };
}

async function loadReplaySet(caseId, transactionId) {
    const count = await Transaction.countDocuments({ caseId });
    if (count > MAX_REPLAY) {
        throw new ApiError(
            422,
            `Case has ${count} transactions, above the ${MAX_REPLAY} replay limit; scope the request smaller`
        );
    }
    const query = { caseId };
    if (transactionId) {
        if (!(await Transaction.exists({ _id: transactionId, caseId }))) {
            throw new ApiError(404, "Transaction not found in this case");
        }
        // Case-wide replay: the target's history is the case's prior
        // transactions, so the whole set is required (bounded by MAX_REPLAY).
        void transactionId;
    }
    const docs = await Transaction.find(query).sort({ timestamp: 1 }).lean();
    return docs.map(projectTxn);
}

function buildAssessment(a, model, gaps) {
    if (a.status !== "scored") {
        // Explicit failure. No risk fields are persisted and no low-risk default
        // is invented — the caller sees "unscored" with a reason.
        return {
            status: "unscored",
            error: a.error || "transaction could not be scored",
            assessedAt: new Date().toISOString(),
            model,
        };
    }
    return {
        status: "scored",
        riskScore: a.risk_score,
        riskLevel: a.risk_classification,
        modelPrediction: a.model_prediction,
        features: a.features,
        mappedType: a.mapped_type,
        threshold: a.threshold,
        gaps,
        model,
        assessedAt: new Date().toISOString(),
    };
}

async function persistAndShape(docId, caseId, assessment) {
    if (assessment.status === "scored") {
        await Transaction.updateOne(
            { _id: docId, caseId },
            {
                riskScore: assessment.riskScore,
                riskLevel: assessment.riskLevel,
                modelPrediction: assessment.modelPrediction,
                assessment,
            }
        );
    } else {
        await Transaction.updateOne({ _id: docId, caseId }, { assessment });
    }
    return { transactionId: docId, ...assessment };
}

/**
 * Score one transaction in an accessible case and persist its assessment.
 */
export async function assessTransaction(authenticatedUser, caseId, transactionId) {
    await getAccessibleCaseDoc(authenticatedUser, caseId);
    if (!validateTransactionId(transactionId)) {
        throw new ApiError(404, "Transaction not found in this case");
    }

    const transactions = await loadReplaySet(caseId, transactionId);
    const target = transactions.find((t) => t.record_uid === transactionId);
    const gaps = [];
    if (target && target.oldbalanceOrg === null) {
        gaps.push("oldbalanceOrg not supplied for this transaction; defaulted to 0.0");
    }

    const res = await mlClient.score(transactions, [transactionId]);
    const a = (res.assessments || {})[transactionId] || { status: "error", error: "no assessment returned" };
    const model = res.model || {};
    return persistAndShape(transactionId, caseId, buildAssessment(a, model, gaps));
}

/**
 * Score every unassessed transaction in an accessible case with ONE causal
 * replay (a single service call), avoiding repeated inference.
 */
export async function assessCase(authenticatedUser, caseId, { skipAssessed = true } = {}) {
    await getAccessibleCaseDoc(authenticatedUser, caseId);

    const transactions = await loadReplaySet(caseId);
    if (transactions.length === 0) {
        return { assessed: 0, scored: 0, unscored: 0, results: [] };
    }

    const res = await mlClient.score(transactions); // score all in one replay
    const model = res.model || {};
    const assessments = res.assessments || {};

    const meta = await Transaction.find({ caseId })
        .select("_id oldbalanceOrg riskScore assessment")
        .lean();

    const results = [];
    let scored = 0;
    let unscored = 0;
    let skipped = 0;
    for (const doc of meta) {
        const uid = doc._id.toString();
        if (skipAssessed && doc.riskScore !== undefined && doc.riskScore !== null) {
            skipped += 1;
            continue;
        }
        const a = assessments[uid];
        if (!a) continue;
        const gaps = [];
        if (doc.oldbalanceOrg === undefined || doc.oldbalanceOrg === null) {
            gaps.push("oldbalanceOrg not supplied for this transaction; defaulted to 0.0");
        }
        const assessment = buildAssessment(a, model, gaps);
        await Transaction.updateOne(
            { _id: doc._id, caseId },
            assessment.status === "scored"
                ? {
                      riskScore: assessment.riskScore,
                      riskLevel: assessment.riskLevel,
                      modelPrediction: assessment.modelPrediction,
                      assessment,
                  }
                : { assessment }
        );
        if (assessment.status === "scored") scored += 1;
        else unscored += 1;
        results.push({ transactionId: uid, status: assessment.status, riskScore: assessment.riskScore ?? null });
    }

    return { assessed: results.length, scored, unscored, skipped, results };
}

/**
 * Read the stored assessment for a transaction (computes nothing). Returns the
 * persisted analytical result, or the transaction's identity with status
 * "not_assessed" when no assessment exists yet.
 */
export async function getTransactionRisk(authenticatedUser, caseId, transactionId) {
    await getAccessibleCaseDoc(authenticatedUser, caseId);
    if (!validateTransactionId(transactionId)) {
        throw new ApiError(404, "Transaction not found in this case");
    }
    const doc = await Transaction.findOne({ _id: transactionId, caseId }).lean();
    if (!doc) throw new ApiError(404, "Transaction not found in this case");

    if (doc.riskScore === undefined || doc.riskScore === null) {
        return {
            transactionId,
            status: doc.assessment ? doc.assessment.status : "not_assessed",
            riskScore: null,
            riskLevel: null,
            modelPrediction: null,
            assessment: doc.assessment || null,
        };
    }
    return {
        transactionId,
        status: "scored",
        riskScore: doc.riskScore,
        riskLevel: doc.riskLevel,
        modelPrediction: doc.modelPrediction,
        assessment: doc.assessment || null,
    };
}

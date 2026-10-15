import {
    assessTransaction,
    assessCase,
    getTransactionRisk,
} from "../services/risk-assessment.service.js";
import * as mlClient from "../services/ml-service.client.js";

/**
 * POST /api/v1/cases/:caseId/transactions/:transactionId/assess
 * Score one transaction and persist its risk assessment.
 */
export const assessOne = async (req, res, next) => {
    try {
        const assessment = await assessTransaction(req.user, req.params.caseId, req.params.transactionId);
        res.status(200).json({ success: true, data: { assessment } });
    } catch (error) {
        next(error);
    }
};

/**
 * POST /api/v1/cases/:caseId/transactions/assess
 * Score the case in one causal replay. Optional body: { force: true } to
 * re-assess transactions that already carry a score.
 */
export const assessAll = async (req, res, next) => {
    try {
        const force = req.body && req.body.force === true;
        const result = await assessCase(req.user, req.params.caseId, { skipAssessed: !force });
        res.status(200).json({ success: true, data: result });
    } catch (error) {
        next(error);
    }
};

/**
 * GET /api/v1/cases/:caseId/transactions/:transactionId/risk
 * Return the persisted assessment for a transaction (computes nothing).
 */
export const risk = async (req, res, next) => {
    try {
        const data = await getTransactionRisk(req.user, req.params.caseId, req.params.transactionId);
        res.status(200).json({ success: true, data });
    } catch (error) {
        next(error);
    }
};

/**
 * GET /api/v1/risk/model
 * Model + service metadata for the Model Information screen. Reported live from
 * the inference service; on failure returns an explicit unavailable state
 * rather than fabricated metadata.
 */
export const modelInfo = async (req, res, next) => {
    try {
        const model = await mlClient.modelInfo();
        res.status(200).json({ success: true, data: { available: true, model } });
    } catch (error) {
        if (error.code === "ML_UNAVAILABLE") {
            res.status(200).json({ success: true, data: { available: false, reason: error.message } });
            return;
        }
        next(error);
    }
};

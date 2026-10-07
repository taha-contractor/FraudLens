import {
    validateTransactionCreation,
    validateTransactionListFilters,
    validateTransactionId,
} from "../validators/transaction.validator.js";
import {
    createTransaction,
    listTransactions,
    getTransactionById,
} from "../services/transaction.service.js";
import ApiError from "../utils/ApiError.js";

function assertValid(errors) {
    if (errors.length > 0) {
        const error = new ApiError(400, "Validation failed");
        error.details = errors;
        throw error;
    }
}

// Invalid or foreign ids resolve to 404 rather than 400: uniform, safe
// behavior that does not leak which resources exist elsewhere.
function assertTransactionId(transactionId) {
    if (!validateTransactionId(transactionId)) {
        throw new ApiError(404, "Transaction not found in this case");
    }
}

/**
 * POST /api/v1/cases/:caseId/transactions
 */
export const create = async (req, res, next) => {
    try {
        assertValid(validateTransactionCreation(req.body));
        const transaction = await createTransaction(req.user, req.params.caseId, req.body);
        res.status(201).json({
            success: true,
            message: "Transaction created successfully",
            data: { transaction },
        });
    } catch (error) {
        next(error);
    }
};

/**
 * GET /api/v1/cases/:caseId/transactions
 * Simple filters: accountId, transactionType, status, from, to, limit.
 */
export const list = async (req, res, next) => {
    try {
        assertValid(validateTransactionListFilters(req.query));
        const transactions = await listTransactions(req.user, req.params.caseId, req.query);
        res.status(200).json({
            success: true,
            data: { transactions, count: transactions.length },
        });
    } catch (error) {
        next(error);
    }
};

/**
 * GET /api/v1/cases/:caseId/transactions/:transactionId
 * :transactionId is the resource id (the external transactionId field is
 * also present in every response).
 */
export const getById = async (req, res, next) => {
    try {
        assertTransactionId(req.params.transactionId);
        const transaction = await getTransactionById(
            req.user,
            req.params.caseId,
            req.params.transactionId
        );
        res.status(200).json({ success: true, data: { transaction } });
    } catch (error) {
        next(error);
    }
};

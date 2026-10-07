import { validateAccountCreation, validateAccountId } from "../validators/account.validator.js";
import { ACCOUNT_STATUSES } from "../models/Account.js";
import { createAccount, listAccounts, getAccountById } from "../services/account.service.js";
import ApiError from "../utils/ApiError.js";

function assertValid(errors) {
    if (errors.length > 0) {
        const error = new ApiError(400, "Validation failed");
        error.details = errors;
        throw error;
    }
}

function assertAccountId(accountId) {
    if (!validateAccountId(accountId)) {
        throw new ApiError(404, "Account not found in this case");
    }
}

/**
 * POST /api/v1/cases/:caseId/accounts
 */
export const create = async (req, res, next) => {
    try {
        assertValid(validateAccountCreation(req.body));
        const account = await createAccount(req.user, req.params.caseId, req.body);
        res.status(201).json({
            success: true,
            message: "Account created successfully",
            data: { account },
        });
    } catch (error) {
        next(error);
    }
};

/**
 * GET /api/v1/cases/:caseId/accounts
 */
export const list = async (req, res, next) => {
    try {
        if (req.query.status !== undefined && !ACCOUNT_STATUSES.includes(req.query.status)) {
            throw new ApiError(400, `status filter must be one of: ${ACCOUNT_STATUSES.join(", ")}`);
        }
        const accounts = await listAccounts(req.user, req.params.caseId, {
            status: req.query.status,
        });
        res.status(200).json({
            success: true,
            data: { accounts, count: accounts.length },
        });
    } catch (error) {
        next(error);
    }
};

/**
 * GET /api/v1/cases/:caseId/accounts/:accountId
 */
export const getById = async (req, res, next) => {
    try {
        assertAccountId(req.params.accountId);
        const account = await getAccountById(req.user, req.params.caseId, req.params.accountId);
        res.status(200).json({ success: true, data: { account } });
    } catch (error) {
        next(error);
    }
};

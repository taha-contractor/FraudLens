import {
    validateSummaryQuery,
    validateTimelineQuery,
    validateSuspiciousQuery,
    validateAccountId,
    rejectAnalyticsBody,
} from "../validators/analytics.validator.js";
import {
    getCaseSummary as caseSummary,
    getAccountActivity as accountActivity,
    getTimeline as timeline,
    getSuspiciousTransactions as suspiciousTransactions,
} from "../services/analytics.service.js";
import ApiError from "../utils/ApiError.js";

/**
 * Thin analytics controllers: validate input, hand the authenticated user and
 * the route's caseId to the service, shape the response. Case authorization is
 * resolved in the service layer, never from client data.
 */

function assertValid(errors) {
    if (errors.length > 0) {
        const error = new ApiError(400, "Validation failed");
        error.details = errors;
        throw error;
    }
}

// Invalid or foreign ids resolve to 404 rather than 400: uniform behavior that
// does not leak which resources exist in other cases.
function assertAccountId(accountId) {
    if (!validateAccountId(accountId)) {
        throw new ApiError(404, "Account not found in this case");
    }
}

/**
 * GET /api/v1/cases/:caseId/analytics/summary
 */
export const getCaseSummary = async (req, res, next) => {
    try {
        assertValid(rejectAnalyticsBody(req.body));
        const { errors, ...range } = validateSummaryQuery(req.query);
        assertValid(errors);
        const summary = await caseSummary(req.user, req.params.caseId, range);
        res.status(200).json({ success: true, data: { summary } });
    } catch (error) {
        next(error);
    }
};

/**
 * GET /api/v1/cases/:caseId/analytics/accounts/:accountId/activity
 */
export const getAccountActivity = async (req, res, next) => {
    try {
        assertValid(rejectAnalyticsBody(req.body));
        assertAccountId(req.params.accountId);
        const { errors, ...range } = validateSummaryQuery(req.query);
        assertValid(errors);
        const activity = await accountActivity(
            req.user,
            req.params.caseId,
            req.params.accountId,
            range
        );
        res.status(200).json({ success: true, data: { activity } });
    } catch (error) {
        next(error);
    }
};

/**
 * GET /api/v1/cases/:caseId/analytics/timeline?interval=DAY|HOUR&from=&to=
 */
export const getTimeline = async (req, res, next) => {
    try {
        assertValid(rejectAnalyticsBody(req.body));
        const { errors, ...options } = validateTimelineQuery(req.query);
        assertValid(errors);
        const result = await timeline(req.user, req.params.caseId, options);
        res.status(200).json({ success: true, data: { timeline: result } });
    } catch (error) {
        next(error);
    }
};

/**
 * GET /api/v1/cases/:caseId/analytics/suspicious?limit=&minScore=&from=&to=
 * Computed on request; nothing is persisted.
 */
export const getSuspiciousTransactions = async (req, res, next) => {
    try {
        assertValid(rejectAnalyticsBody(req.body));
        const { errors, ...options } = validateSuspiciousQuery(req.query);
        assertValid(errors);
        const result = await suspiciousTransactions(req.user, req.params.caseId, options);
        res.status(200).json({ success: true, data: { suspicious: result } });
    } catch (error) {
        next(error);
    }
};

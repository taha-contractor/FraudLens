import mongoose from "mongoose";

/**
 * Input validation for the read-only analytics endpoints.
 * Returns an array of human-readable error strings (empty = valid), following
 * the same approach as the auth/case/account/transaction/document validators.
 *
 * Analytics endpoints are GET-only, but the rules below still reject a
 * client-supplied caseId: the case boundary always comes from the route.
 */

export const ANALYTICS_INTERVALS = Object.freeze(["DAY", "HOUR"]);

export const MAX_ANALYTICS_LIMIT = 1000;
const DEFAULT_SUSPICIOUS_LIMIT = 50;

function parseDate(value) {
    if (value === undefined || value === null || value === "") return null;
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? null : date;
}

/** Analytics never accepts a body; a caseId there is always a spoof attempt. */
export function rejectAnalyticsBody(body) {
    const errors = [];
    if (body && typeof body === "object" && Object.keys(body).length > 0) {
        if (body.caseId !== undefined) {
            errors.push("caseId cannot be supplied; it is taken from the route");
        }
        if (body.accountId !== undefined) {
            errors.push("accountId cannot be supplied; it is taken from the route");
        }
    }
    return errors;
}

export function validateAccountId(accountId) {
    return mongoose.isValidObjectId(accountId);
}

/** Shared from/to/limit validation used by every analytics endpoint. */
function validateRangeAndLimit(query, errors) {
    const from = parseDate(query.from);
    const to = parseDate(query.to);

    if (query.from !== undefined && query.from !== "" && from === null) {
        errors.push("from must be a valid date (ISO 8601)");
    }
    if (query.to !== undefined && query.to !== "" && to === null) {
        errors.push("to must be a valid date (ISO 8601)");
    }
    if (from && to && from.getTime() > to.getTime()) {
        errors.push("from must not be after to");
    }

    if (query.limit !== undefined) {
        const limit = Number(query.limit);
        if (!Number.isInteger(limit) || limit < 1) {
            errors.push("limit must be an integer of 1 or greater");
        } else if (limit > MAX_ANALYTICS_LIMIT) {
            errors.push(`limit must not exceed ${MAX_ANALYTICS_LIMIT}`);
        }
    }

    return { from, to };
}

export function validateTimelineQuery(query) {
    const errors = [];
    if (query.interval !== undefined && !ANALYTICS_INTERVALS.includes(query.interval)) {
        errors.push(`interval must be one of: ${ANALYTICS_INTERVALS.join(", ")}`);
    }
    const range = validateRangeAndLimit(query, errors);
    return { errors, ...range, interval: query.interval || "DAY" };
}

export function validateSuspiciousQuery(query) {
    const errors = [];
    const range = validateRangeAndLimit(query, errors);

    if (query.minScore !== undefined) {
        const minScore = Number(query.minScore);
        if (!Number.isFinite(minScore) || minScore < 0 || minScore > 1) {
            errors.push("minScore must be a number between 0 and 1");
        }
    }

    return {
        errors,
        ...range,
        limit: Number.isInteger(Number(query.limit)) ? Number(query.limit) : DEFAULT_SUSPICIOUS_LIMIT,
        minScore: query.minScore === undefined ? undefined : Number(query.minScore),
    };
}

export function validateSummaryQuery(query) {
    const errors = [];
    // The summary and the account activity endpoints accept only an optional
    // from/to window; malformed values are rejected rather than ignored.
    const range = validateRangeAndLimit(query, errors);
    return { errors, from: range.from, to: range.to };
}

import mongoose from "mongoose";
import { TRANSACTION_STATUSES } from "../models/Transaction.js";

/**
 * Input validation for transaction endpoints.
 * Returns an array of human-readable error strings (empty = valid).
 */

const MAX_TEXT_FIELD_LENGTH = 1000;

function parseTimestamp(value) {
    if (value === undefined || value === null || value === "") return null;
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? null : date;
}

export function validateTransactionCreation(body) {
    const errors = [];
    if (!body || typeof body !== "object") {
        return ["request body must be a JSON object"];
    }

    // caseId comes from the route + authorization context only.
    if (body.caseId !== undefined) {
        errors.push("caseId cannot be supplied; it is taken from the route");
    }
    for (const field of ["createdAt", "updatedAt", "_id", "id"]) {
        if (body[field] !== undefined) {
            errors.push(`${field} cannot be supplied`);
        }
    }
    // Analytical fields are reserved for later ML/analytics milestones.
    for (const field of ["riskScore", "riskLevel", "modelPrediction"]) {
        if (body[field] !== undefined) {
            errors.push(`${field} is set by the analytics layer, not by clients`);
        }
    }

    if (typeof body.transactionId !== "string" || body.transactionId.trim() === "") {
        errors.push("transactionId is required");
    } else if (body.transactionId.trim().length > 64) {
        errors.push("transactionId must not exceed 64 characters");
    }

    if (!mongoose.isValidObjectId(body.sourceAccountId)) {
        errors.push("sourceAccountId is required and must be a valid account id");
    }
    if (!mongoose.isValidObjectId(body.destinationAccountId)) {
        errors.push("destinationAccountId is required and must be a valid account id");
    }

    if (typeof body.amount !== "number" || !Number.isFinite(body.amount) || body.amount <= 0) {
        errors.push("amount is required and must be a positive number");
    }

    if (typeof body.currency !== "string" || !/^[A-Za-z]{3}$/.test(body.currency)) {
        errors.push("currency is required and must be a 3-letter code (e.g. INR)");
    }

    if (typeof body.transactionType !== "string" || body.transactionType.trim().length < 2) {
        errors.push("transactionType is required (minimum 2 characters)");
    }

    if (parseTimestamp(body.timestamp) === null) {
        errors.push("timestamp is required and must be a valid date (ISO 8601)");
    }

    if (body.status !== undefined && !TRANSACTION_STATUSES.includes(body.status)) {
        errors.push(`status must be one of: ${TRANSACTION_STATUSES.join(", ")}`);
    }

    for (const field of ["description", "merchant", "location"]) {
        if (body[field] !== undefined && typeof body[field] !== "string") {
            errors.push(`${field} must be a string`);
        } else if (typeof body[field] === "string" && body[field].length > MAX_TEXT_FIELD_LENGTH) {
            errors.push(`${field} must not exceed ${MAX_TEXT_FIELD_LENGTH} characters`);
        }
    }

    return errors;
}

export function validateTransactionListFilters(query) {
    const errors = [];

    if (query.accountId !== undefined && !mongoose.isValidObjectId(query.accountId)) {
        errors.push("accountId filter must be a valid account id");
    }
    if (query.from !== undefined && parseTimestamp(query.from) === null) {
        errors.push("from must be a valid date (ISO 8601)");
    }
    if (query.to !== undefined && parseTimestamp(query.to) === null) {
        errors.push("to must be a valid date (ISO 8601)");
    }
    if (query.status !== undefined && !TRANSACTION_STATUSES.includes(query.status)) {
        errors.push(`status filter must be one of: ${TRANSACTION_STATUSES.join(", ")}`);
    }

    return errors;
}

export function parseTimestampValue(value) {
    return parseTimestamp(value);
}

export function validateTransactionId(transactionId) {
    return mongoose.isValidObjectId(transactionId);
}

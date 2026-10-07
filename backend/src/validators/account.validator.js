import mongoose from "mongoose";
import { ACCOUNT_STATUSES } from "../models/Account.js";

/**
 * Input validation for account endpoints.
 * Returns an array of human-readable error strings (empty = valid),
 * following the same approach as auth/case validators.
 */

// A masked identifier must NOT contain long unmasked digit runs
// (potential full account numbers, Database_design.md §58).
const UNMASKED_DIGIT_RUN = /\d{7,}/;

function validateMaskedNumber(value, errors) {
    if (typeof value !== "string" || value.trim() === "") {
        errors.push("accountNumberMasked is required");
        return;
    }
    const trimmed = value.trim();
    if (trimmed.length < 4 || trimmed.length > 34) {
        errors.push("accountNumberMasked must be between 4 and 34 characters");
    } else if (UNMASKED_DIGIT_RUN.test(trimmed)) {
        errors.push(
            "accountNumberMasked appears to contain an unmasked account number; " +
            "store only a masked identifier (e.g. XXXXXXXX1234)"
        );
    }
}

function validateOptionalObjectId(value, field, errors) {
    if (value === undefined || value === null || value === "") return;
    if (!mongoose.isValidObjectId(value)) {
        errors.push(`${field} must be a valid user/entity id`);
    }
}

function validateNonClientFields(body, errors) {
    // caseId comes from the route + authorization context only.
    if (body.caseId !== undefined) {
        errors.push("caseId cannot be supplied; it is taken from the route");
    }
    for (const field of ["createdAt", "updatedAt", "_id", "id"]) {
        if (body[field] !== undefined) {
            errors.push(`${field} cannot be supplied`);
        }
    }
}

export function validateAccountCreation(body) {
    const errors = [];
    if (!body || typeof body !== "object") {
        return ["request body must be a JSON object"];
    }

    validateNonClientFields(body, errors);
    validateMaskedNumber(body.accountNumberMasked, errors);

    if (typeof body.accountType !== "string" || body.accountType.trim().length < 2) {
        errors.push("accountType is required (minimum 2 characters)");
    }

    if (typeof body.currency !== "string" || !/^[A-Za-z]{3}$/.test(body.currency)) {
        errors.push("currency is required and must be a 3-letter code (e.g. INR)");
    }

    if (body.status !== undefined && !ACCOUNT_STATUSES.includes(body.status)) {
        errors.push(`status must be one of: ${ACCOUNT_STATUSES.join(", ")}`);
    }

    validateOptionalObjectId(body.bankEntityId, "bankEntityId", errors);
    if (body.ownerEntityIds !== undefined) {
        if (!Array.isArray(body.ownerEntityIds)) {
            errors.push("ownerEntityIds must be an array of entity ids");
        } else {
            for (const id of body.ownerEntityIds) {
                if (!mongoose.isValidObjectId(id)) {
                    errors.push(`ownerEntityIds contains an invalid id: ${id}`);
                    break;
                }
            }
        }
    }

    return errors;
}

export function validateAccountId(accountId) {
    return mongoose.isValidObjectId(accountId);
}

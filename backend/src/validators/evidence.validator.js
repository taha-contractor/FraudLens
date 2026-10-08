import mongoose from "mongoose";
import {
    EVIDENCE_TYPES,
    EXTRACTION_METHODS,
    MAX_SOURCE_TEXT_CHARS,
} from "../models/Evidence.js";

/**
 * Input validation for evidence endpoints.
 * Returns an array of human-readable error strings (empty = valid).
 */

// Fields the backend controls. A client may never set them: caseId comes from
// the route, documentName from the referenced Document record, createdBy from
// the authenticated identity and timestamps from MongoDB.
const SERVER_CONTROLLED_FIELDS = [
    "caseId",
    "documentName",
    "createdBy",
    "createdAt",
    "updatedAt",
    "_id",
    "id",
];

const MAX_PAGE_NUMBER = 100000;
const MAX_SECTION_LENGTH = 200;

export function validateEvidenceCreation(body) {
    const errors = [];
    if (!body || typeof body !== "object") {
        return ["request body must be a JSON object"];
    }

    for (const field of SERVER_CONTROLLED_FIELDS) {
        if (body[field] !== undefined) {
            errors.push(`${field} is set by the server and cannot be supplied`);
        }
    }

    if (!mongoose.isValidObjectId(body.documentId)) {
        errors.push("documentId is required and must be a valid document id");
    }

    if (body.pageNumber === undefined) {
        errors.push("pageNumber is required");
    } else if (
        typeof body.pageNumber !== "number" ||
        !Number.isInteger(body.pageNumber) ||
        body.pageNumber < 1
    ) {
        errors.push("pageNumber must be an integer of 1 or greater");
    } else if (body.pageNumber > MAX_PAGE_NUMBER) {
        errors.push(`pageNumber must not exceed ${MAX_PAGE_NUMBER}`);
    }

    if (body.section !== undefined) {
        if (typeof body.section !== "string") {
            errors.push("section must be a string");
        } else if (body.section.trim() === "") {
            errors.push("section must not be blank");
        } else if (body.section.trim().length > MAX_SECTION_LENGTH) {
            errors.push(`section must not exceed ${MAX_SECTION_LENGTH} characters`);
        }
    }

    if (typeof body.sourceText !== "string" || body.sourceText.trim() === "") {
        errors.push("sourceText is required and must be a non-empty string");
    } else if (body.sourceText.length > MAX_SOURCE_TEXT_CHARS) {
        errors.push(`sourceText must not exceed ${MAX_SOURCE_TEXT_CHARS} characters`);
    }

    if (body.evidenceType !== undefined && !EVIDENCE_TYPES.includes(body.evidenceType)) {
        errors.push(`evidenceType must be one of: ${EVIDENCE_TYPES.join(", ")}`);
    }

    if (body.extractionMethod === undefined) {
        errors.push(`extractionMethod is required (one of: ${EXTRACTION_METHODS.join(", ")})`);
    } else if (!EXTRACTION_METHODS.includes(body.extractionMethod)) {
        errors.push(`extractionMethod must be one of: ${EXTRACTION_METHODS.join(", ")}`);
    }

    return errors;
}

export function validateEvidenceListFilters(query) {
    const errors = [];

    if (query.documentId !== undefined && !mongoose.isValidObjectId(query.documentId)) {
        errors.push("documentId filter must be a valid document id");
    }
    if (query.evidenceType !== undefined && !EVIDENCE_TYPES.includes(query.evidenceType)) {
        errors.push(`evidenceType filter must be one of: ${EVIDENCE_TYPES.join(", ")}`);
    }
    if (
        query.extractionMethod !== undefined &&
        !EXTRACTION_METHODS.includes(query.extractionMethod)
    ) {
        errors.push(`extractionMethod filter must be one of: ${EXTRACTION_METHODS.join(", ")}`);
    }
    if (query.pageNumber !== undefined) {
        const page = Number(query.pageNumber);
        if (!Number.isInteger(page) || page < 1) {
            errors.push("pageNumber filter must be an integer of 1 or greater");
        }
    }

    return errors;
}

export function validateEvidenceId(evidenceId) {
    return mongoose.isValidObjectId(evidenceId);
}

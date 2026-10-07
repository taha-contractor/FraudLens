import { DOCUMENT_PROCESSING_STATUSES, DOCUMENT_TYPES } from "../models/Document.js";
import { validateDocumentUploadFields, validateDocumentId } from "../validators/document.validator.js";
import {
    uploadDocument,
    listDocuments,
    getDocumentById,
    getProcessingStatus,
} from "../services/document.service.js";
import ApiError from "../utils/ApiError.js";

/**
 * Document controllers stay thin: validate input, call the service, shape the
 * response. Case authorization and case isolation live in the service layer.
 */

function assertValid(errors) {
    if (errors.length > 0) {
        const error = new ApiError(400, "Validation failed");
        error.details = errors;
        throw error;
    }
}

// Invalid or foreign ids resolve to 404: uniform, safe behavior that does not
// reveal whether the resource exists in another case.
function assertDocumentId(documentId) {
    if (!validateDocumentId(documentId)) {
        throw new ApiError(404, "Document not found in this case");
    }
}

function assertEnum(value, allowed, field) {
    if (value !== undefined && !allowed.includes(value)) {
        throw new ApiError(400, `${field} must be one of: ${allowed.join(", ")}`);
    }
}

/**
 * POST /api/v1/cases/:caseId/documents  (multipart/form-data, field "file")
 */
export const create = async (req, res, next) => {
    try {
        assertValid(validateDocumentUploadFields(req.body));
        const document = await uploadDocument(req.user, req.params.caseId, req.file, req.body);
        res.status(201).json({
            success: true,
            message: "Document uploaded successfully; processing started",
            data: { document },
        });
    } catch (error) {
        next(error);
    }
};

/**
 * GET /api/v1/cases/:caseId/documents
 * Metadata only - file contents are never returned here.
 */
export const list = async (req, res, next) => {
    try {
        assertEnum(req.query.status, DOCUMENT_PROCESSING_STATUSES, "status");
        assertEnum(req.query.documentType, DOCUMENT_TYPES, "documentType");

        const documents = await listDocuments(req.user, req.params.caseId, {
            status: req.query.status,
            documentType: req.query.documentType,
        });
        res.status(200).json({ success: true, data: { documents, count: documents.length } });
    } catch (error) {
        next(error);
    }
};

/**
 * GET /api/v1/cases/:caseId/documents/:documentId
 * Add ?include=text to also return the extracted text (opt-in, still
 * case-authorized). Without it the response is metadata only.
 */
export const getById = async (req, res, next) => {
    try {
        assertDocumentId(req.params.documentId);
        const includeText = req.query.include === "text";
        const document = await getDocumentById(req.user, req.params.caseId, req.params.documentId, {
            includeText,
        });
        res.status(200).json({ success: true, data: { document } });
    } catch (error) {
        next(error);
    }
};

/**
 * GET /api/v1/cases/:caseId/documents/:documentId/status
 */
export const status = async (req, res, next) => {
    try {
        assertDocumentId(req.params.documentId);
        const statusInfo = await getProcessingStatus(req.user, req.params.caseId, req.params.documentId);
        res.status(200).json({ success: true, data: { status: statusInfo } });
    } catch (error) {
        next(error);
    }
};

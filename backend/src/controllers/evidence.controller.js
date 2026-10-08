import {
    validateEvidenceCreation,
    validateEvidenceListFilters,
    validateEvidenceId,
} from "../validators/evidence.validator.js";
import {
    createEvidence,
    listEvidence,
    getEvidenceById,
} from "../services/evidence.service.js";
import ApiError from "../utils/ApiError.js";

/**
 * Evidence controllers stay thin: validate input, call the service, shape the
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
function assertEvidenceId(evidenceId) {
    if (!validateEvidenceId(evidenceId)) {
        throw new ApiError(404, "Evidence not found in this case");
    }
}

/**
 * POST /api/v1/cases/:caseId/evidence
 * Explicit evidence creation (v1): the source text is quoted from a document
 * that must already belong to this case.
 */
export const create = async (req, res, next) => {
    try {
        assertValid(validateEvidenceCreation(req.body));
        const evidence = await createEvidence(req.user, req.params.caseId, req.body);
        res.status(201).json({
            success: true,
            message: "Evidence created successfully",
            data: { evidence },
        });
    } catch (error) {
        next(error);
    }
};

/**
 * GET /api/v1/cases/:caseId/evidence
 * Filterable by documentId, evidenceType, extractionMethod, pageNumber, limit.
 */
export const list = async (req, res, next) => {
    try {
        // One validator covers every query filter (ids, enums, pageNumber).
        assertValid(validateEvidenceListFilters(req.query));

        const evidence = await listEvidence(req.user, req.params.caseId, req.query);
        res.status(200).json({ success: true, data: { evidence, count: evidence.length } });
    } catch (error) {
        next(error);
    }
};

/**
 * GET /api/v1/cases/:caseId/evidence/:evidenceId
 */
export const getById = async (req, res, next) => {
    try {
        assertEvidenceId(req.params.evidenceId);
        const evidence = await getEvidenceById(req.user, req.params.caseId, req.params.evidenceId);
        res.status(200).json({ success: true, data: { evidence } });
    } catch (error) {
        next(error);
    }
};

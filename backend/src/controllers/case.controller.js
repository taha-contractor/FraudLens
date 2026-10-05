import {
    validateCaseCreation,
    validateCaseUpdate,
    validateCaseId,
} from "../validators/case.validator.js";
import {
    createCase,
    getCasesForUser,
    getCaseById,
    updateCase,
} from "../services/case.service.js";
import ApiError from "../utils/ApiError.js";

function assertValid(errors) {
    if (errors.length > 0) {
        const error = new ApiError(400, "Validation failed");
        error.details = errors;
        throw error;
    }
}

function assertCaseId(caseId) {
    if (!validateCaseId(caseId)) {
        throw new ApiError(404, "Case not found");
    }
}

/**
 * POST /api/v1/cases
 */
export const create = async (req, res, next) => {
    try {
        assertValid(validateCaseCreation(req.body));
        const testCase = await createCase(req.user, req.body);
        res.status(201).json({
            success: true,
            message: "Case created successfully",
            data: { case: testCase },
        });
    } catch (error) {
        next(error);
    }
};

/**
 * GET /api/v1/cases
 */
export const list = async (req, res, next) => {
    try {
        const cases = await getCasesForUser(req.user);
        res.status(200).json({
            success: true,
            data: { cases, count: cases.length },
        });
    } catch (error) {
        next(error);
    }
};

/**
 * GET /api/v1/cases/:caseId
 */
export const getById = async (req, res, next) => {
    try {
        assertCaseId(req.params.caseId);
        const testCase = await getCaseById(req.user, req.params.caseId);
        res.status(200).json({ success: true, data: { case: testCase } });
    } catch (error) {
        next(error);
    }
};

/**
 * PATCH /api/v1/cases/:caseId
 */
export const update = async (req, res, next) => {
    try {
        assertCaseId(req.params.caseId);
        assertValid(validateCaseUpdate(req.body));
        const testCase = await updateCase(req.user, req.params.caseId, req.body);
        res.status(200).json({
            success: true,
            message: "Case updated successfully",
            data: { case: testCase },
        });
    } catch (error) {
        next(error);
    }
};

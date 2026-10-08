import Evidence from "../models/Evidence.js";
import Document from "../models/Document.js";
import ApiError from "../utils/ApiError.js";
import { getAccessibleCaseDoc } from "./case.service.js";

/**
 * Evidence business logic.
 * Same flow as cases/accounts/transactions/documents: authenticate -> case
 * access check -> resource scoped to that case.
 *
 * In v1 evidence is created explicitly through the API (no automatic
 * evidence-generation pipeline yet). Provenance is always server-controlled:
 * caseId comes from the route, documentName from the referenced Document
 * record and createdBy from the authenticated identity. No file content or
 * storage location is copied into an evidence record.
 */

/**
 * Loads the source document, restricted to the requested case.
 * A document owned by another case resolves to 404 with a generic message:
 * the response never reveals which case actually holds it.
 */
async function getSourceDocumentInCase(documentId, caseId) {
    const source = await Document.findOne({ _id: documentId, caseId });
    if (!source) {
        throw new ApiError(404, "Document not found in this case");
    }
    return source;
}

/**
 * Creates an evidence record inside an accessible case, citing one of that
 * case's documents.
 * @throws {ApiError} 404 unknown/foreign document, 400 page outside the document
 */
export async function createEvidence(authenticatedUser, caseId, data) {
    await getAccessibleCaseDoc(authenticatedUser, caseId);

    const source = await getSourceDocumentInCase(data.documentId, caseId);

    // pageNumber only makes sense against the real document. pageCount is unset
    // while a document is still PENDING/PROCESSING or FAILED, so the bound is
    // checked only when it is known.
    if (source.pageCount !== undefined && data.pageNumber > source.pageCount) {
        throw new ApiError(
            400,
            `pageNumber must be between 1 and ${source.pageCount} for this document`
        );
    }

    let evidence;
    try {
        evidence = await Evidence.create({
            caseId,
            // Taken from the found Document, so an id from another case can
            // never be attached to this one.
            documentId: source._id,
            documentName: source.fileName,
            pageNumber: data.pageNumber,
            section: data.section ? data.section.trim() : undefined,
            sourceText: data.sourceText.trim(),
            evidenceType: data.evidenceType || "DOCUMENT_TEXT",
            extractionMethod: data.extractionMethod,
            createdBy: authenticatedUser.id,
        });
    } catch (error) {
        if (error.name === "ValidationError") {
            throw new ApiError(400, "Invalid evidence data");
        }
        throw error;
    }

    return evidence.toJSON();
}

/**
 * Lists the evidence of an accessible case with simple filters:
 * documentId, evidenceType, extractionMethod, pageNumber, limit.
 */
export async function listEvidence(authenticatedUser, caseId, query = {}) {
    await getAccessibleCaseDoc(authenticatedUser, caseId);

    const filter = { caseId };
    if (query.documentId) filter.documentId = query.documentId;
    if (query.evidenceType) filter.evidenceType = query.evidenceType;
    if (query.extractionMethod) filter.extractionMethod = query.extractionMethod;
    if (query.pageNumber) filter.pageNumber = parseInt(query.pageNumber, 10);

    const limit = Math.min(parseInt(query.limit, 10) || 100, 1000);

    const records = await Evidence.find(filter)
        .sort({ createdAt: -1 })
        .limit(limit);

    return records.map((e) => e.toJSON());
}

/**
 * Loads one evidence record strictly within its case.
 * Evidence from another case yields 404 — changing caseId in the URL can never
 * reach another case's data.
 */
export async function getEvidenceById(authenticatedUser, caseId, evidenceId) {
    await getAccessibleCaseDoc(authenticatedUser, caseId);

    const evidence = await Evidence.findOne({ _id: evidenceId, caseId });
    if (!evidence) {
        throw new ApiError(404, "Evidence not found in this case");
    }
    return evidence.toJSON();
}

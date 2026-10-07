import crypto from "node:crypto";
import Document from "../models/Document.js";
import ApiError from "../utils/ApiError.js";
import { getAccessibleCaseDoc } from "./case.service.js";
import { saveDocumentFile, removeDocumentFile } from "./storage.service.js";
import { detectDocumentKind, sanitizeFileName } from "../validators/document.validator.js";
import { queueDocumentProcessing } from "./document-processing.service.js";

/**
 * Document business logic.
 * Request flow is always: authenticate (middleware) -> case access check ->
 * resource scoped to that case. Metadata (caseId, uploadedBy, checksum,
 * storageReference, processingStatus) is computed here, never taken from the
 * client, and the stored file lives in private storage keyed by the case.
 */

function toMetadata(doc) {
    // Document.toJSON() strips storageReference and all extracted content, so a
    // raw document can never leak a filesystem path or file text.
    return doc.toJSON();
}

function withExtractedText(doc) {
    const metadata = toMetadata(doc);
    metadata.extractedText = doc.extractedText;
    metadata.extractedPages = (doc.extractedPages || []).map((page) => ({
        pageNumber: page.pageNumber,
        text: page.text,
    }));
    return metadata;
}

/**
 * Stores an uploaded file for a case and starts processing.
 * @param {object} authenticatedUser req.user (role/id read from the DB)
 * @param {string} caseId from the route only
 * @param {{buffer: Buffer, originalname: string}} file from multer
 */
export async function uploadDocument(authenticatedUser, caseId, file, body = {}) {
    // Authorization happens before anything is written to storage.
    await getAccessibleCaseDoc(authenticatedUser, caseId);

    if (!file || !Buffer.isBuffer(file.buffer) || file.buffer.length === 0) {
        throw new ApiError(400, "A non-empty document file is required");
    }

    // Content sniffing is authoritative: a renamed executable is rejected even
    // though the client declared a PDF/TXT name and type.
    const kind = detectDocumentKind(file.buffer);
    if (!kind) {
        throw new ApiError(415, "Unsupported file type; only PDF and TXT documents are accepted");
    }

    const checksum = crypto.createHash("sha256").update(file.buffer).digest("hex");
    const storageReference = await saveDocumentFile({
        caseId,
        buffer: file.buffer,
        extension: kind.extension,
    });

    let doc;
    try {
        doc = await Document.create({
            caseId,
            fileName: sanitizeFileName(file.originalname),
            documentType: body.documentType || "GENERAL",
            mimeType: kind.mimeType,
            fileSize: file.buffer.length,
            storageReference,
            processingStatus: "PENDING",
            checksum,
            uploadedBy: authenticatedUser.id,
        });
    } catch (error) {
        // Do not leave an orphaned file behind if the metadata insert failed.
        await removeDocumentFile(storageReference);
        if (error.name === "ValidationError") {
            throw new ApiError(400, "Invalid document metadata");
        }
        if (error.code === 11000) {
            throw new ApiError(409, "This document already exists in the case");
        }
        throw error;
    }

    queueDocumentProcessing(doc._id);
    return toMetadata(doc);
}

/** Lists document metadata for an accessible case (never file contents). */
export async function listDocuments(authenticatedUser, caseId, { status, documentType } = {}) {
    await getAccessibleCaseDoc(authenticatedUser, caseId);

    const filter = { caseId };
    if (status) filter.processingStatus = status;
    if (documentType) filter.documentType = documentType;

    const documents = await Document.find(filter).sort({ createdAt: -1 });
    return documents.map(toMetadata);
}

/**
 * Loads one document strictly within its case.
 * A document from another case yields 404 - changing caseId in the URL can
 * never reach another case's data, and no metadata is leaked.
 */
export async function getDocumentById(authenticatedUser, caseId, documentId, { includeText = false } = {}) {
    await getAccessibleCaseDoc(authenticatedUser, caseId);

    const query = Document.findOne({ _id: documentId, caseId });
    if (includeText) query.select("+extractedText +extractedPages");

    const doc = await query;
    if (!doc) {
        throw new ApiError(404, "Document not found in this case");
    }
    return includeText ? withExtractedText(doc) : toMetadata(doc);
}

/** Processing status only - the cheap polling endpoint. */
export async function getProcessingStatus(authenticatedUser, caseId, documentId) {
    await getAccessibleCaseDoc(authenticatedUser, caseId);

    const doc = await Document.findOne(
        { _id: documentId, caseId },
        { fileName: 1, documentType: 1, mimeType: 1, fileSize: 1, pageCount: 1, processingStatus: 1, textExtractionStatus: 1, needsOcr: 1, extractionNote: 1, failureReason: 1, processedAt: 1, createdAt: 1, updatedAt: 1 }
    );
    if (!doc) {
        throw new ApiError(404, "Document not found in this case");
    }

    return {
        documentId: doc._id.toString(),
        fileName: doc.fileName,
        processingStatus: doc.processingStatus,
        textExtractionStatus: doc.textExtractionStatus,
        needsOcr: doc.needsOcr,
        pageCount: doc.pageCount,
        extractionNote: doc.extractionNote,
        failureReason: doc.failureReason,
        processedAt: doc.processedAt,
        createdAt: doc.createdAt,
        updatedAt: doc.updatedAt,
    };
}

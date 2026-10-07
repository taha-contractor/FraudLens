/**
 * Input validation and safe-handling rules for document uploads.
 * Returns arrays of human-readable error strings (empty = valid), following
 * the same approach as the auth/case/account/transaction validators.
 */

import mongoose from "mongoose";
import { DOCUMENT_TYPES } from "../models/Document.js";

// Fields the backend controls. A client may never set them (milestone §3).
const SERVER_CONTROLLED_FIELDS = [
    "caseId",
    "uploadedBy",
    "storageReference",
    "checksum",
    "processingStatus",
    "pageCount",
    "extractedText",
    "textExtractionStatus",
    "needsOcr",
    "failureReason",
    "processedAt",
    "createdAt",
    "updatedAt",
    "_id",
    "id",
];

export function validateDocumentUploadFields(body) {
    const errors = [];
    if (!body || typeof body !== "object") {
        // A multipart request may legitimately carry no text fields at all.
        return [];
    }

    for (const field of SERVER_CONTROLLED_FIELDS) {
        if (body[field] !== undefined) {
            errors.push(`${field} is set by the server and cannot be supplied`);
        }
    }

    if (body.documentType !== undefined) {
        if (typeof body.documentType !== "string" || !DOCUMENT_TYPES.includes(body.documentType)) {
            errors.push(`documentType must be one of: ${DOCUMENT_TYPES.join(", ")}`);
        }
    }

    return errors;
}

/**
 * Produces a safe *display* name from the client filename.
 * The result is never used to build a filesystem path - stored names are
 * generated server-side by the storage service.
 */
export function sanitizeFileName(originalName) {
    const raw = typeof originalName === "string" ? originalName : "";

    // Keep only the final path segment: strips "../../", "C:\\windows\\", NUL
    // and every other traversal / injection attempt in the filename.
    let name = raw.split(/[/\\]/).pop() || "";

    // Drop control characters and characters that are unsafe in filenames.
    name = name.replace(/[\u0000-\u001f\u007f<>:"|?*]/g, "");
    // Neutralize path separators and dot segments that survived.
    name = name.replace(/\.{2,}/g, ".").replace(/^[.\s]+/, "");
    // Collapse whitespace runs.
    name = name.replace(/\s+/g, " ").trim();

    if (name === "") return "document";
    if (name.length > 200) name = name.slice(0, 200);
    return name;
}

const PDF_MAGIC = "%PDF-";
const TEXT_SNIFF_LENGTH = 8192;

// Signatures of formats that must never be accepted or executed.
const BINARY_SIGNATURES = [
    [0x4d, 0x5a], // MZ  (Windows executable)
    [0x7f, 0x45, 0x4c, 0x46], // ELF
    [0x50, 0x4b, 0x03, 0x04], // ZIP/Office/JAR
    [0x89, 0x50, 0x4e, 0x47], // PNG
    [0xff, 0xd8, 0xff], // JPEG
];

function startsWithSignature(bytes, signature) {
    return signature.every((byte, index) => bytes[index] === byte);
}

/**
 * Determines the real document kind by inspecting the file's own bytes.
 * The client-declared MIME type and filename are never trusted for this
 * decision (they are only used as a hint for the response metadata).
 * @returns {{kind: "PDF"|"TXT", mimeType: string, extension: string}|null}
 */
export function detectDocumentKind(buffer) {
    if (!Buffer.isBuffer(buffer) || buffer.length === 0) return null;

    if (buffer.subarray(0, PDF_MAGIC.length).toString("latin1") === PDF_MAGIC) {
        return { kind: "PDF", mimeType: "application/pdf", extension: ".pdf" };
    }

    const sample = buffer.subarray(0, Math.min(buffer.length, TEXT_SNIFF_LENGTH));

    // Plain text never contains NUL bytes.
    if (sample.includes(0x00)) return null;
    if (BINARY_SIGNATURES.some((sig) => startsWithSignature(sample, sig))) return null;

    // Allow common whitespace, reject other non-printable control characters.
    let suspicious = 0;
    for (const byte of sample) {
        const isPrintable = (byte >= 0x20 && byte <= 0x7e) || byte === 0x09 || byte === 0x0a || byte === 0x0d;
        const isHighBit = byte >= 0x80; // possible UTF-8 content
        if (!isPrintable && !isHighBit) suspicious++;
    }
    if (suspicious > sample.length * 0.02) return null;

    return { kind: "TXT", mimeType: "text/plain", extension: ".txt" };
}

export function validateDocumentId(documentId) {
    return mongoose.isValidObjectId(documentId);
}

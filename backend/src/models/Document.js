import mongoose from "mongoose";

/**
 * Document processing pipeline statuses.
 *
 * Database_design.md §11 defines a longer lifecycle
 * (UPLOADED / VALIDATING / PROCESSING / OCR_COMPLETED / EXTRACTED / INDEXED / FAILED).
 * For this milestone the pipeline is intentionally collapsed to four states, and the
 * extraction outcome is carried separately in `textExtractionStatus`. The later
 * RAG/indexing milestone can extend the lifecycle (INDEXED) without breaking data.
 */
export const DOCUMENT_PROCESSING_STATUSES = Object.freeze([
    "PENDING",
    "PROCESSING",
    "COMPLETED",
    "FAILED",
]);

/** Outcome of the text-extraction step (design §11 EXTRACTED / OCR branch). */
export const DOCUMENT_TEXT_EXTRACTION_STATUSES = Object.freeze([
    "NOT_STARTED",
    "TEXT_EXTRACTED",
    "NO_SELECTABLE_TEXT",
]);

/** Investigation document categories (design §10 "document category"). */
export const DOCUMENT_TYPES = Object.freeze([
    "GENERAL",
    "BANK_STATEMENT",
    "LEDGER",
    "REPORT",
    "CORRESPONDENCE",
    "CONTRACT",
    "OTHER",
]);

const extractedPageSchema = new mongoose.Schema(
    {
        pageNumber: { type: Number, required: true, min: 1 },
        // Reached only through the parent `extractedPages` array, which is
        // excluded by default (see schema below + toJSON transform).
        text: { type: String, default: "" },
    },
    { _id: false }
);

const documentSchema = new mongoose.Schema(
    {
        caseId: {
            type: mongoose.Schema.Types.ObjectId,
            ref: "Case",
            required: true,
            immutable: true,
        },
        // Sanitized original name, for display only. It is never used as a
        // filesystem path - storageReference is generated server-side.
        fileName: {
            type: String,
            required: true,
            trim: true,
            maxlength: 255,
        },
        documentType: {
            type: String,
            enum: { values: DOCUMENT_TYPES, message: "Invalid documentType: {VALUE}" },
            default: "GENERAL",
        },
        mimeType: { type: String, required: true, maxlength: 100 },
        fileSize: {
            type: Number,
            required: true,
            min: [1, "fileSize must be greater than zero"],
        },
        // Opaque, backend-controlled location reference (design §10). Replacing
        // local disk with S3 later changes only the storage service.
        storageReference: { type: String, required: true, immutable: true, maxlength: 500 },
        processingStatus: {
            type: String,
            enum: { values: DOCUMENT_PROCESSING_STATUSES, message: "Invalid processingStatus: {VALUE}" },
            default: "PENDING",
        },
        pageCount: { type: Number, min: 0, default: undefined },
        // SHA-256 hex digest computed by the backend on the stored bytes.
        checksum: {
            type: String,
            required: true,
            immutable: true,
            lowercase: true,
            match: [/^[a-f0-9]{64}$/, "checksum must be a SHA-256 hex digest"],
        },
        uploadedBy: {
            type: mongoose.Schema.Types.ObjectId,
            ref: "User",
            required: true,
            immutable: true,
        },
        // --- processing results -------------------------------------------------
        // Extracted text is stored so the Evidence/RAG milestones can later turn
        // it into formal evidence without re-reading the file.
        extractedText: { type: String, default: undefined, select: false },
        extractedPages: { type: [extractedPageSchema], default: undefined, select: false },
        textExtractionStatus: {
            type: String,
            enum: {
                values: DOCUMENT_TEXT_EXTRACTION_STATUSES,
                message: "Invalid textExtractionStatus: {VALUE}",
            },
            default: "NOT_STARTED",
        },
        // Scanned / image-only PDFs: detected honestly, OCR handled later.
        needsOcr: { type: Boolean, default: false },
        extractionNote: { type: String, maxlength: 500, default: undefined },
        // Short, client-safe reason - never a stack trace or filesystem detail.
        failureReason: { type: String, maxlength: 300, default: undefined },
        processedAt: { type: Date, default: undefined },
    },
    { timestamps: true, versionKey: false }
);

// Query patterns from Database_design.md (§ Documents indexes).
documentSchema.index({ caseId: 1 });
documentSchema.index({ caseId: 1, documentType: 1 });
documentSchema.index({ caseId: 1, processingStatus: 1 });

documentSchema.set("toJSON", {
    transform: (doc, ret) => {
        ret.id = ret._id.toString();
        ret.caseId = ret.caseId.toString();
        ret.uploadedBy = ret.uploadedBy.toString();
        delete ret._id;
        delete ret.__v;
        // Internal storage location and extracted content are opt-in: stripping
        // them here means no response path can leak a path or file text by
        // returning a raw document.
        delete ret.storageReference;
        delete ret.extractedText;
        delete ret.extractedPages;
        return ret;
    },
});

export default mongoose.model("Document", documentSchema);

import mongoose from "mongoose";

/**
 * Evidence provenance vocabulary (Database_design.md §26).
 *
 * §26 also lists TRANSACTION / ACCOUNT_ACTIVITY / ENTITY_RECORD / RELATIONSHIP /
 * MODEL_SIGNAL / TIMELINE_EVENT / FUND_FLOW. Those sources are produced by later
 * analysis milestones, so v1 accepts only document-derived evidence; extending
 * this enum does not change any existing record.
 */
export const EVIDENCE_TYPES = Object.freeze([
    "DOCUMENT_TEXT",
    "DOCUMENT_TABLE",
    "DOCUMENT_METADATA",
]);

/** How the evidence was obtained (design §25 "extractionMethod"). */
export const EXTRACTION_METHODS = Object.freeze([
    "TEXT_EXTRACTION",
    "OCR",
    "MANUAL",
]);

/**
 * Upper bound for a single evidence passage. Evidence is a *quoted fragment*
 * with a citation, not a copy of the whole document, so the limit also keeps
 * every record comfortably inside the 100kb JSON body limit.
 */
export const MAX_SOURCE_TEXT_CHARS = 20000;

const evidenceSchema = new mongoose.Schema(
    {
        caseId: {
            type: mongoose.Schema.Types.ObjectId,
            ref: "Case",
            required: true,
            immutable: true,
        },
        // Source document. Belonging to the same case as caseId is enforced in
        // the service layer (Mongo cannot express a cross-collection check).
        documentId: {
            type: mongoose.Schema.Types.ObjectId,
            ref: "Document",
            required: true,
            immutable: true,
        },
        // Denormalized display name copied from the Document record by the
        // server, so a citation stays readable without an extra lookup. It is
        // never taken from the client and never a filesystem path.
        documentName: {
            type: String,
            required: true,
            trim: true,
            maxlength: 255,
            immutable: true,
        },
        pageNumber: {
            type: Number,
            required: true,
            min: [1, "pageNumber must be 1 or greater"],
            max: [100000, "pageNumber is unreasonably large"],
        },
        // Free-text locator inside the page ("Balance summary", "Clause 4").
        section: { type: String, trim: true, maxlength: 200, default: undefined },
        sourceText: {
            type: String,
            required: true,
            trim: true,
            maxlength: [
                MAX_SOURCE_TEXT_CHARS,
                `sourceText must not exceed ${MAX_SOURCE_TEXT_CHARS} characters`,
            ],
        },
        evidenceType: {
            type: String,
            enum: { values: EVIDENCE_TYPES, message: "Invalid evidenceType: {VALUE}" },
            default: "DOCUMENT_TEXT",
        },
        extractionMethod: {
            type: String,
            required: [true, "extractionMethod is required"],
            enum: { values: EXTRACTION_METHODS, message: "Invalid extractionMethod: {VALUE}" },
        },
        createdBy: {
            type: mongoose.Schema.Types.ObjectId,
            ref: "User",
            required: true,
            immutable: true,
        },
    },
    { timestamps: true, versionKey: false }
);

// Query patterns from Database_design.md (§ Indexing Strategy / Evidence).
evidenceSchema.index({ caseId: 1 });
evidenceSchema.index({ caseId: 1, documentId: 1 });
evidenceSchema.index({ caseId: 1, evidenceType: 1 });

evidenceSchema.set("toJSON", {
    transform: (doc, ret) => {
        ret.id = ret._id.toString();
        ret.caseId = ret.caseId.toString();
        ret.documentId = ret.documentId.toString();
        ret.createdBy = ret.createdBy.toString();
        delete ret._id;
        delete ret.__v;
        return ret;
    },
});

export default mongoose.model("Evidence", evidenceSchema);

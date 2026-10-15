import mongoose from "mongoose";

/**
 * Transaction statuses from Database_design.md §14.
 */
export const TRANSACTION_STATUSES = Object.freeze([
    "PENDING",
    "COMPLETED",
    "FAILED",
    "REVERSED",
    "CANCELLED",
]);

/**
 * Risk levels from Database_design.md §15.
 * riskScore / riskLevel / modelPrediction are analytical outputs and are
 * intentionally NOT client-settable in this milestone (ML comes later).
 */
export const TRANSACTION_RISK_LEVELS = Object.freeze(["LOW", "MEDIUM", "HIGH"]);

const transactionSchema = new mongoose.Schema(
    {
        caseId: {
            type: mongoose.Schema.Types.ObjectId,
            ref: "Case",
            required: true,
            immutable: true,
        },
        transactionId: {
            type: String,
            required: true,
            trim: true,
            maxlength: 64,
        },
        sourceAccountId: {
            type: mongoose.Schema.Types.ObjectId,
            ref: "Account",
            required: true,
        },
        destinationAccountId: {
            type: mongoose.Schema.Types.ObjectId,
            ref: "Account",
            required: true,
        },
        amount: {
            type: Number,
            required: true,
            validate: {
                validator: (v) => Number.isFinite(v) && v > 0,
                message: "amount must be a positive number",
            },
        },
        currency: {
            type: String,
            required: true,
            uppercase: true,
            minlength: 3,
            maxlength: 3,
        },
        transactionType: {
            type: String,
            required: true,
            trim: true,
            uppercase: true,
            minlength: 2,
            maxlength: 30,
        },
        description: {
            type: String,
            trim: true,
            maxlength: 1000,
            default: "",
        },
        merchant: {
            type: String,
            trim: true,
            maxlength: 200,
            default: "",
        },
        location: {
            type: String,
            trim: true,
            maxlength: 200,
            default: "",
        },
        timestamp: {
            type: Date,
            required: true,
        },
        status: {
            type: String,
            enum: { values: TRANSACTION_STATUSES, message: "Invalid status: {VALUE}" },
            default: "PENDING",
        },
        // Optional origin account balance immediately BEFORE the transaction.
        // The model's 17-feature contract includes oldbalanceOrg; generic
        // ingestion may not carry it, so it is optional and defaults to 0.0 at
        // scoring time (surfaced as a documented feature gap, never guessed).
        oldbalanceOrg: {
            type: Number,
            min: 0,
            default: undefined,
        },
        // Analytical fields — populated only by the ML inference milestone.
        riskScore: {
            type: Number,
            min: 0,
            max: 1,
            default: undefined,
        },
        riskLevel: {
            type: String,
            enum: { values: TRANSACTION_RISK_LEVELS, message: "Invalid riskLevel: {VALUE}" },
            default: undefined,
        },
        modelPrediction: {
            type: Boolean,
            default: undefined,
        },
        // Full assessment written by the ML milestone for explainability and
        // traceability (feature values, mapped type, threshold, provenance).
        // Not client-settable; paired with the risk fields above.
        assessment: {
            type: mongoose.Schema.Types.Mixed,
            default: undefined,
        },
    },
    { timestamps: true, versionKey: false }
);

// Query patterns from Database_design.md §49.
transactionSchema.index({ caseId: 1, transactionId: 1 }, { unique: true });
transactionSchema.index({ caseId: 1, timestamp: -1 });
transactionSchema.index({ caseId: 1, sourceAccountId: 1 });
transactionSchema.index({ caseId: 1, destinationAccountId: 1 });

transactionSchema.set("toJSON", {
    transform: (doc, ret) => {
        ret.id = ret._id.toString();
        ret.caseId = ret.caseId.toString();
        delete ret._id;
        delete ret.__v;
        // The full assessment (feature vectors, provenance) is heavy and only
        // relevant in the detail view; it is served by the risk endpoint.
        delete ret.assessment;
        return ret;
    },
});

export default mongoose.model("Transaction", transactionSchema);

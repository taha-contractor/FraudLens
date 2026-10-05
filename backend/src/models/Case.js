import mongoose from "mongoose";

/**
 * Case statuses used by FraudLens.
 * The Case is the central boundary of the platform; every investigation
 * resource will belong to exactly one case.
 */
export const CASE_STATUSES = Object.freeze([
    "OPEN",
    "UNDER_INVESTIGATION",
    "CLOSED",
    "ARCHIVED",
]);

const caseSchema = new mongoose.Schema(
    {
        caseNumber: {
            type: String,
            required: true,
            unique: true,
            trim: true,
        },
        title: {
            type: String,
            required: true,
            trim: true,
            minlength: 3,
            maxlength: 150,
        },
        description: {
            type: String,
            trim: true,
            maxlength: 5000,
            default: "",
        },
        status: {
            type: String,
            enum: { values: CASE_STATUSES, message: "Invalid status: {VALUE}" },
            default: "OPEN",
        },
        createdBy: {
            type: mongoose.Schema.Types.ObjectId,
            ref: "User",
            required: true,
            immutable: true,
        },
        investigators: {
            type: [{ type: mongoose.Schema.Types.ObjectId, ref: "User" }],
            default: [],
        },
    },
    { timestamps: true, versionKey: false }
);

// Query patterns from Database_design.md §49 (caseNumber, createdBy, investigators)
caseSchema.index({ createdBy: 1 });
caseSchema.index({ investigators: 1 });

caseSchema.set("toJSON", {
    transform: (doc, ret) => {
        ret.id = ret._id.toString();
        delete ret._id;
        delete ret.__v;
        return ret;
    },
});

export default mongoose.model("Case", caseSchema);

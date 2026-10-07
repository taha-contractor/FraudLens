import mongoose from "mongoose";

/**
 * Account statuses from Database_design.md §17.
 */
export const ACCOUNT_STATUSES = Object.freeze([
    "ACTIVE",
    "INACTIVE",
    "CLOSED",
    "UNKNOWN",
]);

const accountSchema = new mongoose.Schema(
    {
        caseId: {
            type: mongoose.Schema.Types.ObjectId,
            ref: "Case",
            required: true,
            immutable: true,
        },
        // Masked identifiers only (e.g. XXXXXXXX1234) — full account numbers
        // must never be stored (Database_design.md §16/§58).
        accountNumberMasked: {
            type: String,
            required: true,
            trim: true,
            uppercase: true,
            minlength: 4,
            maxlength: 34,
        },
        accountType: {
            type: String,
            required: true,
            trim: true,
            uppercase: true,
            minlength: 2,
            maxlength: 30,
        },
        bankEntityId: {
            type: mongoose.Schema.Types.ObjectId,
            ref: "Entity", // entity milestone comes later; reference only
            default: null,
        },
        ownerEntityIds: {
            type: [{ type: mongoose.Schema.Types.ObjectId, ref: "Entity" }],
            default: [],
        },
        currency: {
            type: String,
            required: true,
            uppercase: true,
            minlength: 3,
            maxlength: 3,
        },
        status: {
            type: String,
            enum: { values: ACCOUNT_STATUSES, message: "Invalid status: {VALUE}" },
            default: "ACTIVE",
        },
    },
    { timestamps: true, versionKey: false }
);

// Query patterns from Database_design.md §49.
accountSchema.index({ caseId: 1 });
accountSchema.index({ caseId: 1, accountNumberMasked: 1 }, { unique: true });

accountSchema.set("toJSON", {
    transform: (doc, ret) => {
        ret.id = ret._id.toString();
        ret.caseId = ret.caseId.toString();
        delete ret._id;
        delete ret.__v;
        return ret;
    },
});

export default mongoose.model("Account", accountSchema);

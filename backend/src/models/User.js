import mongoose from "mongoose";

/**
 * The four FraudLens platform roles. Keep in sync with RBAC usage;
 * authorization is always evaluated from the role stored in the database.
 */
export const USER_ROLES = Object.freeze(["ADMIN", "INVESTIGATOR", "REVIEWER", "AUDITOR"]);

const userSchema = new mongoose.Schema(
    {
        name: {
            type: String,
            required: true,
            trim: true,
            minlength: 2,
            maxlength: 100,
        },
        email: {
            type: String,
            required: true,
            unique: true,
            trim: true,
            lowercase: true,
            match: /^[^\s@]+@[^\s@]+\.[^\s@]+$/,
        },
        passwordHash: {
            type: String,
            required: true,
            select: false, // never returned by default queries
        },
        role: {
            type: String,
            enum: { values: USER_ROLES, message: "Invalid role: {VALUE}" },
            default: "INVESTIGATOR",
        },
        isActive: {
            type: Boolean,
            default: true,
        },
    },
    { timestamps: true, versionKey: false }
);

// Ensure passwordHash is stripped from every serialized response,
// even if a query explicitly selected it.
userSchema.set("toJSON", {
    transform: (doc, ret) => {
        ret.id = ret._id.toString();
        delete ret._id;
        delete ret.passwordHash;
        return ret;
    },
});

export default mongoose.model("User", userSchema);

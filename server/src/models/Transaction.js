import mongoose from "mongoose";

const transactionSchema = new mongoose.Schema(
    {
        transactionId: {
            type: String,
            required: true,
            unique: true,
            index: true
        },

        accountId: {
            type: String,
            required: true,
            index: true
        },

        amount: {
            type: Number,
            required: true,
            min: 0
        },

        transactionType: {
            type: String,
            required: true,
            enum: ["TRANSFER", "PAYMENT", "WITHDRAWAL", "DEPOSIT"]
        },

        merchant: {
            type: String,
            default: null
        },

        location: {
            type: String,
            default: null
        },

        timestamp: {
            type: Date,
            required: true
        },

        status: {
            type: String,
            enum: ["PENDING", "REVIEW", "CLEARED", "CONFIRMED_FRAUD"],
            default: "PENDING"
        },

        fraudProbability: {
            type: Number,
            default: null,
            min: 0,
            max: 1
        },

        riskLevel: {
            type: String,
            enum: ["LOW", "MEDIUM", "HIGH", "CRITICAL"],
            default: null
        },

        fraudPrediction: {
            type: Boolean,
            default: null
        }
    },
    {
        timestamps: true
    }
);

const Transaction = mongoose.model("Transaction", transactionSchema);

export default Transaction;
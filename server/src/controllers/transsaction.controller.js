import Transaction from "../models/Transaction.js";
import { analyzeTransaction } from "../services/fraud-analysis.service.js";
import fs from "fs/promises";
import {
    parseTransactionCSV,
    validateTransactionRecords,
    importTransactionsToDatabase
} from "../services/transaction-import.service.js";
// import { analyzeTransactionById } from "../services/fraud-analysis.service.js";

export const createTransaction = async (req, res) => {
    try {
        const transaction = await Transaction.create(req.body);
        res.status(201).json({
            success: true,
            message: "Transaction created successfully",
            data: transaction
        })
    } catch (error) {
        res.status(400).json({
            success: false,
            message: "Failed to create transaction",
            error: error.message
        });
    }
}

export const getTransaction = async (req, res) => {
    try {
        const transactions = await Transaction.find()
            .sort({ createdAt: -1 });

        res.status(200).json({
            success: true,
            count: transactions.length,
            data: transactions
        });
    } catch (error) {
        res.status(500).json({
            success: false,
            message: "Failed to fetch transactions",
            error: error.message
        });
    }
}

export const getTransactionById = async (req, res) => {
    try {
        const { id } = req.params;
        const transaction = await Transaction.findOne({ transactionId: id });

        if (!transaction) {
            return res.status(404).json({
                success: false,
                message: "Transaction not found"
            });
        }

        res.status(200).json({
            success: true,
            data: transaction
        });
    } catch (error) {
        res.status(500).json({
            success: false,
            message: "Failed to fetch transaction",
            error: error.message
        });
    }
}

export const importTransactions = async (req, res) => {
    try {
        if (!req.file) {
            return res.status(400).json({
                success: false,
                message: "CSV file is required"
            });
        }

        const records = await parseTransactionCSV(req.file.path);
        const { validRecords, invalidRecords } = validateTransactionRecords(records);
        const databaseResults = await importTransactionsToDatabase(validRecords);

        await fs.unlink(req.file.path);
        
        res.status(200).json({
            success: true,
            message: "CSV parsed successfully",
            summary: {
                validRecords: validRecords.length,
                invalidRecords: invalidRecords.length,
                totalRecords: records.length,
                inserted: databaseResults.inserted,
                duplicates: databaseResults.duplicates,
                failed: databaseResults.failed
            },
            invalidRecords,
            errors: databaseResults.errors
        });
    } catch (error) {
        res.status(400).json({
            success: false,
            message: "Failed to import transactions",
            error: error.message
        });
    }
};

export const analyzeTransactionById = async (res, req) => {
    try {
        const {id} = req.params;
        const transaction = await Transaction.findOne({
            transactionId: id
        });

        if (!transaction){
            return res.status(404).json({
                success: false,
                message: "Transaction not found"
            });
        }

        const analysis = await analyzeTransaction(transaction);
        res.status(200).json({
            success: true,
            data: analysis
        });
    } catch(error) {
        res.status(500).json({
            success:false,
            message: "Failed to analyze Transaction",
            error: error.message
        });
    }
};
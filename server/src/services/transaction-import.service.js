import fs from "fs/promises";
import { parse } from "csv-parse/sync";
import Transaction from "../models/Transaction.js";
import { log } from "console";

const REQUIRED_COLUMNS = [
    "transactionId",
    "accountId",
    "amount",
    "transactionType",
    "location",
    "timestamp"
];

const VALID_TRANSACTION_TYPES = [
    "TRANSFER",
    "WITHDRAWAL",
    "DEPOSIT",
    "PAYMENT"
];

export const parseTransactionCSV = async (filePath) => {
    const fileContent = await fs.readFile(filePath, "utf-8");

    const records = parse(fileContent, {
        columns: true,
        skip_empty_lines: true,
        trim: true
    });

    if (records.length === 0) {
        throw new Error("No records found in the CSV file");
    }

    const headers = Object.keys(records[0]);

    const missingColumns = REQUIRED_COLUMNS.filter(
        (column) => !headers.includes(column)
    );

    if (missingColumns.length > 0) {
        throw new Error(
            `Missing required columns: ${missingColumns.join(", ")}`
        );
    }

    return records;
};

export const validateTransactionRecords = (records) => {
    const validRecords = [];
    const invalidRecords = [];

    records.forEach((record, index) => {
        const rowNumber = index + 2;
        const errors = [];

        if (!record.transactionId) {
            errors.push("transactionId is required");
        }

        if (!record.accountId) {
            errors.push("accountId is required");
        }

        const amount = Number(record.amount);

        if (Number.isNaN(amount) || amount <= 0) {
            errors.push("amount must be a positive number");
        }

        if (!VALID_TRANSACTION_TYPES.includes(record.transactionType)) {
            errors.push(
                `transactionType must be one of: ${VALID_TRANSACTION_TYPES.join(
                    ", "
                )}`
            );
        }

        const timestamp = new Date(record.timestamp);

        if (Number.isNaN(timestamp.getTime())) {
            errors.push("timestamp is invalid");
        }

        if (errors.length > 0) {
            invalidRecords.push({
                row: rowNumber,
                transactionId: record.transactionId || null,
                errors
            });

            return;
        }

        validRecords.push({
            transactionId: record.transactionId,
            accountId: record.accountId,
            amount,
            transactionType: record.transactionType,
            merchant: record.merchant || null,
            location: record.location || null,
            timestamp
        });
    });

    return {
        validRecords,
        invalidRecords
    };
};

export const importTransactionsToDatabase = async (validRecords) => {
    const results = {
        inserted: 0,
        duplicates: 0,
        failed: 0,
        errors: []
    };

    for (const record of validRecords) {
        try {
            const createdTransaction = await Transaction.create(record);
            results.inserted++;
        } catch (error) {
            if (error.code === 11000) {
                results.duplicates++;
            } else {
                results.failed++;

                results.errors.push({
                    transactionId: record.transactionId,
                    error: error.message
                });
            }
        }
    }

    return results;
};
import Transaction from "../models/Transaction.js";
import Account from "../models/Account.js";
import ApiError from "../utils/ApiError.js";
import { getAccessibleCaseDoc } from "./case.service.js";
import { parseTimestampValue } from "../validators/transaction.validator.js";

/**
 * Transaction business logic.
 * Same flow as accounts: authenticate -> case access check -> resource
 * scoped to the case. Source and destination accounts are verified to
 * belong to the same case before a transaction is stored.
 * Analytical fields (riskScore/riskLevel/modelPrediction) are NOT written
 * here — the later ML/analytics milestones own them.
 */

/**
 * Verifies that every referenced account id exists within the given case.
 * Generic message: never reveals whether the id exists in another case.
 */
async function assertAccountsInCase(accountIds, caseId) {
    const distinct = [...new Set(accountIds.map((id) => String(id)))];
    const found = await Account.countDocuments({ _id: { $in: distinct }, caseId });
    if (found !== distinct.length) {
        throw new ApiError(400, "One or more referenced accounts do not exist in this case");
    }
}

/**
 * Creates a transaction inside an accessible case.
 * @throws {ApiError} 400 invalid accounts, 409 duplicate transactionId in case
 */
export async function createTransaction(authenticatedUser, caseId, data) {
    await getAccessibleCaseDoc(authenticatedUser, caseId);

    await assertAccountsInCase([data.sourceAccountId, data.destinationAccountId], caseId);

    let txnDoc;
    try {
        txnDoc = await Transaction.create({
            caseId,
            transactionId: data.transactionId.trim(),
            sourceAccountId: data.sourceAccountId,
            destinationAccountId: data.destinationAccountId,
            amount: data.amount,
            currency: data.currency,
            transactionType: data.transactionType.trim(),
            description: data.description || "",
            merchant: data.merchant || "",
            location: data.location || "",
            timestamp: parseTimestampValue(data.timestamp),
            status: data.status || "PENDING",
        });
    } catch (error) {
        if (error.code === 11000) {
            throw new ApiError(409, "A transaction with this transactionId already exists in this case");
        }
        if (error.name === "ValidationError") {
            throw new ApiError(400, "Invalid transaction data");
        }
        throw error;
    }

    return txnDoc.toJSON();
}

/**
 * Lists transactions of an accessible case with simple filters:
 * accountId (source or destination), transactionType, status, from, to, limit.
 */
export async function listTransactions(authenticatedUser, caseId, query = {}) {
    await getAccessibleCaseDoc(authenticatedUser, caseId);

    const filter = { caseId };

    if (query.accountId) {
        filter.$or = [
            { sourceAccountId: query.accountId },
            { destinationAccountId: query.accountId },
        ];
    }
    if (query.transactionType) {
        filter.transactionType = String(query.transactionType).toUpperCase();
    }
    if (query.status) {
        filter.status = query.status;
    }
    if (query.from || query.to) {
        filter.timestamp = {};
        if (query.from) filter.timestamp.$gte = parseTimestampValue(query.from);
        if (query.to) filter.timestamp.$lte = parseTimestampValue(query.to);
    }

    const limit = Math.min(parseInt(query.limit, 10) || 100, 1000);

    const transactions = await Transaction.find(filter)
        .sort({ timestamp: -1 })
        .limit(limit);

    return transactions.map((t) => t.toJSON());
}

/**
 * Loads one transaction strictly within its case.
 * A transaction from another case yields 404 — changing caseId in the URL
 * can never reach another case's data.
 */
export async function getTransactionById(authenticatedUser, caseId, transactionId) {
    await getAccessibleCaseDoc(authenticatedUser, caseId);

    const txnDoc = await Transaction.findOne({ _id: transactionId, caseId });
    if (!txnDoc) {
        throw new ApiError(404, "Transaction not found in this case");
    }
    return txnDoc.toJSON();
}

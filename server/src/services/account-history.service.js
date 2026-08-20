import Transaction from "../models/Transaction.js";

export const getAccountHistory = async (
    accountId,
    currentTransactionId = null
) => {
    const query = { accountId };
    if (currentTransactionId) {
        query.transactionId = { $ne: currentTransactionId };
    }
    const transactions = await Transaction.find(query).sort({ timestamp: -1 });
    return transactions;
}
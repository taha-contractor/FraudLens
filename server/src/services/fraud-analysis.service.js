import { getAccountHistory } from "./account-history.service.js";
import { getTransactionFeatures } from "./fraud-feature.service.js";

export const analyzeTransaction = async (transaction) => {
    const accountHistory = await getAccountHistory(
        transaction.accountId,
        transaction.transactionId
    );
    const features = getTransactionFeatures(
        transaction,
        accountHistory
    );
    return {
        transactionId: transaction.transactionId,
        features
    };
};
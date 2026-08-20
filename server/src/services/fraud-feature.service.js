export const getTransactionFeatures = (transaction, accountHistory=[]) => {
    const timestamp = new Date(transaction.timestamp);
    const hour = timestamp.getHours();
    const isNightTransaction = hour < 6 || hour > 22;
    const isHighValue = transaction.amount >= 50000;
    const transactionCount = accountHistory.length;
    const totalAmount = accountHistory.reduce((sum, item) => sum + item.amount, 0);
    const averageAmount = transactionCount > 0 ? totalAmount / transactionCount : 0;
    const maximumAmount = transactionCount > 0 ? Math.max(...accountHistory.map(item => item.amount)) : 0;
    const amountDeviation = averageAmount > 0 ? transaction.amount / averageAmount : 0;
    return {
        transactionId: transaction.transactionId,
        amount: transaction.amount,
        transactionHour: hour,
        isNightTransaction,
        isHighValue,
        transactionCount,
        averageAmount,
        maximumAmount,
        amountDeviation
    };
};
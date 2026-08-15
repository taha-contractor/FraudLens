import Transaction from "../models/Tramsaction.js";

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
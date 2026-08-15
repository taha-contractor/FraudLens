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
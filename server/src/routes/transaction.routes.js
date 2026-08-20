import express from "express";
import {
    createTransaction,
    getTransaction,
    getTransactionById,
    importTransactions,
    analyzeTransactionById
} from "../controllers/transsaction.controller.js";
import upload from "../middleware/upload.middleware.js";

const router = express.Router();

router.post("/", createTransaction);
router.get("/", getTransaction);
router.post(
    "/import",
    upload.single("file"),
    importTransactions
);
router.get("/analyze/:id", analyzeTransactionById);
router.get("/:id", getTransactionById);

export default router;
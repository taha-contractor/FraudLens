import express from "express";
import {
    createTransaction,
    getTransaction,
    getTransactionById,
    importTransactions
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
router.get("/:id", getTransactionById);

export default router;
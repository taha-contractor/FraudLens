import express from "express";
import {
    createTransaction,
    getTransaction,
    getTransactionById
} from "../controllers/tracsaction.controller.js";
const router = express.Router();

router.post("/", createTransaction);
router.get("/", getTransaction);
router.get("/:id", getTransactionById);

export default router;
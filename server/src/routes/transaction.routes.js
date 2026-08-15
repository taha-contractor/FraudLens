import express from "express";
import {createTransaction, getTransaction} from "../controllers/tracsaction.controller.js";
const router = express.Router();

router.post("/", createTransaction);
router.get("/", getTransaction);

export default router;
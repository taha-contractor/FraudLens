import express from "express";
import {createTransaction} from "../controllers/tracsaction.controller.js";
const router = express.Router();

router.post("/", createTransaction);

export default router;
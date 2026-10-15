import { Router } from "express";
import { authenticate } from "../middleware/auth.middleware.js";
import { modelInfo } from "../controllers/risk.controller.js";

// Case-independent risk/model endpoints.
const router = Router();

router.use(authenticate);

// Model + inference-service metadata for the Model Information screen.
router.get("/model", modelInfo);

export default router;

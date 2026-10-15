import { Router } from "express";
import { authenticate } from "../middleware/auth.middleware.js";
import { create, list, getById } from "../controllers/transaction.controller.js";
import { assessOne, assessAll, risk } from "../controllers/risk.controller.js";

// Nested under a case: req.params.caseId is provided by the mount path.
const router = Router({ mergeParams: true });

// All transaction routes require authentication; case authorization and
// case-scoped resource checks are enforced in the service layer.
router.use(authenticate);

router.post("/", create);
router.get("/", list);

// ML risk assessment. These run BEFORE the "/:transactionId" catch so the
// literal segments are not mistaken for a transaction id.
router.post("/assess", assessAll);
router.post("/:transactionId/assess", assessOne);
router.get("/:transactionId/risk", risk);

router.get("/:transactionId", getById);

export default router;

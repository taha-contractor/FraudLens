import { Router } from "express";
import { authenticate } from "../middleware/auth.middleware.js";
import { create, list, getById } from "../controllers/transaction.controller.js";

// Nested under a case: req.params.caseId is provided by the mount path.
const router = Router({ mergeParams: true });

// All transaction routes require authentication; case authorization and
// case-scoped resource checks are enforced in the service layer.
router.use(authenticate);

router.post("/", create);
router.get("/", list);
router.get("/:transactionId", getById);

export default router;

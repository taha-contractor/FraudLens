import { Router } from "express";
import { authenticate } from "../middleware/auth.middleware.js";
import {
    getCaseSummary,
    getAccountActivity,
    getTimeline,
    getSuspiciousTransactions,
} from "../controllers/analytics.controller.js";

// Nested under a case: req.params.caseId is provided by the mount path.
const router = Router({ mergeParams: true });

// All analytics routes require authentication; case authorization and
// case-scoped resource checks are enforced in the service layer.
router.use(authenticate);

// Read-only endpoints - analytics never creates, updates or deletes anything.
router.get("/summary", getCaseSummary);
router.get("/accounts/:accountId/activity", getAccountActivity);
router.get("/timeline", getTimeline);
router.get("/suspicious", getSuspiciousTransactions);

export default router;

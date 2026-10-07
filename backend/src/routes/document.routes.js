import { Router } from "express";
import { authenticate } from "../middleware/auth.middleware.js";
import { uploadDocument } from "../middleware/upload.middleware.js";
import { create, list, getById, status } from "../controllers/document.controller.js";

// Nested under a case: req.params.caseId is provided by the mount path.
const router = Router({ mergeParams: true });

// All document routes require authentication; case authorization and
// case-scoped resource checks are enforced in the service layer.
router.use(authenticate);

router.post("/", uploadDocument, create);
router.get("/", list);
router.get("/:documentId", getById);
router.get("/:documentId/status", status);

export default router;

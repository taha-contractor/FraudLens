import { Router } from "express";
import { authenticate } from "../middleware/auth.middleware.js";
import { create, list, getById, update } from "../controllers/case.controller.js";

const router = Router();

// Every case route requires authentication; case-level isolation
// (creator/investigator) is enforced in the service layer.
router.use(authenticate);

router.post("/", create);
router.get("/", list);
router.get("/:caseId", getById);
router.patch("/:caseId", update);

export default router;

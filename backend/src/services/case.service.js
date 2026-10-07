import mongoose from "mongoose";
import Case from "../models/Case.js";
import User from "../models/User.js";
import ApiError from "../utils/ApiError.js";

/**
 * Case business logic.
 * Case isolation is enforced here: a user may only access a case they
 * created or that lists them as an investigator. Controllers stay thin.
 */

/**
 * Generates the next human-readable case number: CASE-<year>-<seq>.
 * Sequence is per year, zero-padded to 3 digits (e.g. CASE-2026-007).
 */
async function generateCaseNumber() {
    const year = new Date().getFullYear();
    const prefix = `CASE-${year}-`;

    const latest = await Case.findOne({ caseNumber: { $regex: `^${prefix}` } })
        .sort({ caseNumber: -1 })
        .select("caseNumber")
        .lean();

    const lastSeq = latest ? parseInt(latest.caseNumber.slice(prefix.length), 10) || 0 : 0;
    return `${prefix}${String(lastSeq + 1).padStart(3, "0")}`;
}

/** Server-side case access rule: creator or listed investigator. */
function canAccess(caseDoc, userId) {
    if (caseDoc.createdBy.toString() === userId) return true;
    return caseDoc.investigators.some((id) => id.toString() === userId);
}

async function assertInvestigatorsExist(investigatorIds) {
    if (!investigatorIds || investigatorIds.length === 0) return;
    const distinct = [...new Set(investigatorIds.map(String))];
    const count = await User.countDocuments({ _id: { $in: distinct } });
    if (count !== distinct.length) {
        throw new ApiError(400, "One or more investigator ids do not match existing users");
    }
}

/**
 * Creates a case for the authenticated user.
 * createdBy is always taken from the authenticated identity — never the client.
 */
export async function createCase(authenticatedUser, { title, description = "", status, investigators = [] }) {
    await assertInvestigatorsExist(investigators);

    let caseDoc = null;
    // Retry briefly on rare caseNumber collisions (concurrent creates).
    for (let attempt = 0; attempt < 3 && !caseDoc; attempt++) {
        const caseNumber = await generateCaseNumber();
        try {
            caseDoc = await Case.create({
                caseNumber,
                title: title.trim(),
                description,
                status: status || "OPEN",
                createdBy: authenticatedUser.id,
                investigators,
            });
        } catch (error) {
            if (error.code === 11000 && attempt < 2) continue; // collision, regenerate
            if (error.code === 11000) {
                throw new ApiError(409, "Could not allocate a unique case number, please retry");
            }
            if (error.name === "ValidationError") {
                throw new ApiError(400, "Invalid case data");
            }
            throw error;
        }
    }

    return caseDoc.toJSON();
}

/** Lists only the cases the user is allowed to see (creator or investigator). */
export async function getCasesForUser(authenticatedUser) {
    const cases = await Case.find({
        $or: [{ createdBy: authenticatedUser.id }, { investigators: authenticatedUser.id }],
    }).sort({ createdAt: -1 });

    return cases.map((c) => c.toJSON());
}

/**
 * Loads a case document and enforces case isolation. Shared by the
 * account/transaction services so the access rule exists in exactly one place.
 * @throws {ApiError} 404 unknown case, 403 case belongs to another investigation
 */
export async function getAccessibleCaseDoc(authenticatedUser, caseId) {
    // A malformed caseId can never reach the database; treat it as unknown so
    // nested resources (accounts/transactions) fail safely with 404.
    if (!mongoose.isValidObjectId(caseId)) {
        throw new ApiError(404, "Case not found");
    }

    const caseDoc = await Case.findById(caseId);
    if (!caseDoc) {
        throw new ApiError(404, "Case not found");
    }
    if (!canAccess(caseDoc, authenticatedUser.id)) {
        // Same generic message whether the user is a stranger or the case
        // exists elsewhere — no case data is exposed.
        throw new ApiError(403, "You do not have access to this case");
    }
    return caseDoc;
}

/**
 * Loads one case and enforces case isolation.
 * @throws {ApiError} 404 unknown case, 403 case belongs to another investigation
 */
export async function getCaseById(authenticatedUser, caseId) {
    const caseDoc = await getAccessibleCaseDoc(authenticatedUser, caseId);
    return caseDoc.toJSON();
}

/**
 * Updates whitelisted fields on an accessible case.
 * caseNumber, createdBy and timestamps can never be modified through this path.
 */
export async function updateCase(authenticatedUser, caseId, updates) {
    const caseDoc = await getAccessibleCaseDoc(authenticatedUser, caseId);

    if (updates.investigators !== undefined) {
        await assertInvestigatorsExist(updates.investigators);
        caseDoc.investigators = updates.investigators;
    }
    if (updates.title !== undefined) caseDoc.title = updates.title.trim();
    if (updates.description !== undefined) caseDoc.description = updates.description;
    if (updates.status !== undefined) caseDoc.status = updates.status;

    try {
        await caseDoc.save();
    } catch (error) {
        if (error.name === "ValidationError") {
            throw new ApiError(400, "Invalid case data");
        }
        throw error;
    }

    return caseDoc.toJSON();
}

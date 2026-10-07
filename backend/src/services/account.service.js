import Account from "../models/Account.js";
import ApiError from "../utils/ApiError.js";
import { getAccessibleCaseDoc } from "./case.service.js";

/**
 * Account business logic.
 * Every request flow: authenticate (middleware) -> case access check (here,
 * via the shared case isolation rule) -> resource scoped to that case.
 * The caseId always comes from the route, never from the client.
 */

/**
 * Creates an account inside an accessible case.
 * @throws {ApiError} 409 when the masked identifier already exists in the case
 */
export async function createAccount(authenticatedUser, caseId, data) {
    await getAccessibleCaseDoc(authenticatedUser, caseId);

    let accountDoc;
    try {
        accountDoc = await Account.create({
            caseId,
            accountNumberMasked: data.accountNumberMasked.trim(),
            accountType: data.accountType.trim(),
            currency: data.currency,
            status: data.status || "ACTIVE",
            bankEntityId: data.bankEntityId || null,
            ownerEntityIds: data.ownerEntityIds || [],
        });
    } catch (error) {
        if (error.code === 11000) {
            throw new ApiError(409, "An account with this identifier already exists in this case");
        }
        if (error.name === "ValidationError") {
            throw new ApiError(400, "Invalid account data");
        }
        throw error;
    }

    return accountDoc.toJSON();
}

/** Lists accounts belonging to an accessible case. */
export async function listAccounts(authenticatedUser, caseId, { status } = {}) {
    await getAccessibleCaseDoc(authenticatedUser, caseId);

    const filter = { caseId };
    if (status) filter.status = status;

    const accounts = await Account.find(filter).sort({ createdAt: -1 });
    return accounts.map((a) => a.toJSON());
}

/**
 * Loads one account strictly within its case.
 * Lookup is scoped by { _id, caseId }: an account from another case yields
 * 404 here — cross-case access is impossible and existence is not leaked.
 */
export async function getAccountById(authenticatedUser, caseId, accountId) {
    await getAccessibleCaseDoc(authenticatedUser, caseId);

    const accountDoc = await Account.findOne({ _id: accountId, caseId });
    if (!accountDoc) {
        throw new ApiError(404, "Account not found in this case");
    }
    return accountDoc.toJSON();
}

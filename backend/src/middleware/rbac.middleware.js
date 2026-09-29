import ApiError from "../utils/ApiError.js";

/**
 * RBAC middleware factory.
 * Must be mounted AFTER authenticate so req.user is populated from the
 * database. Usage:
 *
 *   router.get("/x", authenticate, authorizeRoles("ADMIN", "INVESTIGATOR"), handler)
 *
 * @param {...string} roles - roles permitted to access the route
 */
export const authorizeRoles = (...roles) => (req, res, next) => {
    if (!req.user) {
        return next(new ApiError(401, "Authentication required"));
    }
    if (!roles.includes(req.user.role)) {
        return next(new ApiError(403, "You do not have permission to perform this action"));
    }
    next();
};

export default authorizeRoles;

import jwt from "jsonwebtoken";
import ApiError from "../utils/ApiError.js";
import { findUserById } from "../services/auth.service.js";

/**
 * Authentication middleware.
 * Validates the Bearer JWT, then re-loads the user from MongoDB so that
 * authorization is always based on the database state — never on claims
 * or role values supplied by the client.
 */
export const authenticate = async (req, res, next) => {
    try {
        const header = req.headers.authorization || "";
        const [scheme, token] = header.split(" ");

        if (!token || scheme?.toLowerCase() !== "bearer") {
            throw new ApiError(401, "Authentication required");
        }

        const secret = process.env.JWT_SECRET;
        if (!secret) {
            throw new Error("JWT_SECRET is not configured. Set it in backend/.env (see .env.example).");
        }

        let payload;
        try {
            payload = jwt.verify(token, secret);
        } catch (error) {
            throw new ApiError(
                401,
                error.name === "TokenExpiredError"
                    ? "Authentication token has expired"
                    : "Invalid authentication token"
            );
        }

        // Loads from DB: rejects deleted/inactive accounts even with a valid signature.
        const user = await findUserById(payload.sub);

        req.user = {
            id: user._id.toString(),
            name: user.name,
            email: user.email,
            role: user.role, // authoritative role from the database
        };

        next();
    } catch (error) {
        next(error);
    }
};

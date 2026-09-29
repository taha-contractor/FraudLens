import { validateRegistration, validateLogin } from "../validators/auth.validator.js";
import { registerUser, loginUser } from "../services/auth.service.js";
import ApiError from "../utils/ApiError.js";

function assertValid(errors) {
    if (errors.length > 0) {
        const error = new ApiError(400, "Validation failed");
        error.details = errors;
        throw error;
    }
}

/**
 * POST /api/v1/auth/register
 * Public registration. The role is never taken from the request body;
 * new accounts are provisioned as INVESTIGATOR by the service layer.
 */
export const register = async (req, res, next) => {
    try {
        assertValid(validateRegistration(req.body));
        const user = await registerUser(req.body);
        res.status(201).json({
            success: true,
            message: "User registered successfully",
            data: { user },
        });
    } catch (error) {
        next(error);
    }
};

/**
 * POST /api/v1/auth/login
 */
export const login = async (req, res, next) => {
    try {
        assertValid(validateLogin(req.body));
        const { accessToken, user } = await loginUser(req.body);
        res.status(200).json({
            success: true,
            message: "Login successful",
            data: { accessToken, user },
        });
    } catch (error) {
        next(error);
    }
};

/**
 * GET /api/v1/auth/me
 * Requires a valid Bearer token. Serves as the authenticated-identity
 * check endpoint; data comes from the database, not from the client.
 */
export const me = async (req, res) => {
    res.status(200).json({
        success: true,
        data: { user: req.user },
    });
};

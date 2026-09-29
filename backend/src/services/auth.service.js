import bcrypt from "bcryptjs";
import jwt from "jsonwebtoken";
import User from "../models/User.js";
import ApiError from "../utils/ApiError.js";
import { normalizeEmail } from "../validators/auth.validator.js";

const SALT_ROUNDS = Number(process.env.BCRYPT_SALT_ROUNDS) || 10;

// One-time dummy hash so unknown-email logins still cost a bcrypt compare
// (reduces account enumeration through response timing).
const DUMMY_HASH = bcrypt.hashSync("fraudlens-timing-equalizer", SALT_ROUNDS);

const GENERIC_AUTH_FAILURE = "Invalid email or password";

/**
 * Public registration always provisions an INVESTIGATOR.
 * Elevated roles (ADMIN/REVIEWER/AUDITOR) require a controlled
 * provisioning mechanism, never the public register endpoint.
 */
const DEFAULT_REGISTRATION_ROLE = "INVESTIGATOR";

function requireJwtConfig() {
    const secret = process.env.JWT_SECRET;
    if (!secret) {
        throw new Error("JWT_SECRET is not configured. Set it in backend/.env (see .env.example).");
    }
    return {
        secret,
        expiresIn: process.env.JWT_EXPIRES_IN || "1h",
    };
}

/** Minimal, safe user shape returned to clients. */
function toSafeUser(user) {
    return {
        id: user._id.toString(),
        name: user.name,
        email: user.email,
        role: user.role,
    };
}

export async function signToken(user) {
    const { secret, expiresIn } = requireJwtConfig();
    // Minimum identity information only: user id + role.
    return jwt.sign({ sub: user._id.toString(), role: user.role }, secret, { expiresIn });
}

/**
 * Creates a user with a securely hashed password.
 * Validation of the input shape happens in the validator layer.
 * @throws {ApiError} 409 when the email is already registered
 */
export async function registerUser({ name, email, password }) {
    const normalizedEmail = normalizeEmail(email);
    const passwordHash = await bcrypt.hash(password, SALT_ROUNDS);

    let user;
    try {
        user = await User.create({
            name: name.trim(),
            email: normalizedEmail,
            passwordHash,
            role: DEFAULT_REGISTRATION_ROLE,
        });
    } catch (error) {
        if (error.code === 11000) {
            // Unique index violation on email (race-safe duplicate protection).
            throw new ApiError(409, "An account with this email already exists");
        }
        if (error.name === "ValidationError") {
            throw new ApiError(400, "Invalid registration data");
        }
        throw error;
    }

    return toSafeUser(user);
}

/**
 * Authenticates credentials and issues a JWT access token.
 * Unknown email and wrong password produce the identical generic 401,
 * so the API never reveals whether an email exists.
 * @throws {ApiError} 401 invalid credentials, 403 inactive account
 */
export async function loginUser({ email, password }) {
    const normalizedEmail = normalizeEmail(email);
    const user = await User.findOne({ email: normalizedEmail }).select("+passwordHash");

    if (!user) {
        await bcrypt.compare(password, DUMMY_HASH);
        throw new ApiError(401, GENERIC_AUTH_FAILURE);
    }

    const passwordMatches = await bcrypt.compare(password, user.passwordHash);
    if (!passwordMatches) {
        throw new ApiError(401, GENERIC_AUTH_FAILURE);
    }

    if (!user.isActive) {
        throw new ApiError(403, "This account is inactive");
    }

    const accessToken = await signToken(user);
    return { accessToken, user: toSafeUser(user) };
}

/**
 * Loads a user by the id taken from a verified JWT.
 * @throws {ApiError} 401 when the account is missing or inactive
 */
export async function findUserById(userId) {
    let user;
    try {
        user = await User.findById(userId);
    } catch {
        throw new ApiError(401, "Invalid authentication token");
    }
    if (!user) {
        throw new ApiError(401, "Invalid authentication token");
    }
    if (!user.isActive) {
        throw new ApiError(401, "This account is inactive");
    }
    return user;
}

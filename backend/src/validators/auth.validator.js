/**
 * Minimal input validation for the auth endpoints.
 * Returns an array of human-readable error strings (empty = valid).
 */

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

const normalizeEmail = (email) => String(email).trim().toLowerCase();

function validateName(name, errors) {
    if (typeof name !== "string" || name.trim().length < 2) {
        errors.push("name is required and must be at least 2 characters");
    } else if (name.trim().length > 100) {
        errors.push("name must not exceed 100 characters");
    }
}

function validateEmailField(email, errors) {
    if (typeof email !== "string" || email.trim() === "") {
        errors.push("email is required");
    } else if (!EMAIL_RE.test(email.trim())) {
        errors.push("email is not a valid address");
    }
}

/**
 * Password policy: min 8 characters, at least one uppercase letter,
 * one lowercase letter and one digit.
 */
function validatePassword(password, errors) {
    if (typeof password !== "string" || password.length === 0) {
        errors.push("password is required");
        return;
    }
    if (password.length < 8) {
        errors.push("password must be at least 8 characters long");
    }
    if (!/[A-Z]/.test(password)) {
        errors.push("password must contain at least one uppercase letter");
    }
    if (!/[a-z]/.test(password)) {
        errors.push("password must contain at least one lowercase letter");
    }
    if (!/[0-9]/.test(password)) {
        errors.push("password must contain at least one digit");
    }
}

export function validateRegistration(body) {
    const errors = [];
    if (!body || typeof body !== "object") {
        return ["request body must be a JSON object"];
    }
    validateName(body.name, errors);
    validateEmailField(body.email, errors);
    validatePassword(body.password, errors);
    return errors;
}

export function validateLogin(body) {
    const errors = [];
    if (!body || typeof body !== "object") {
        return ["request body must be a JSON object"];
    }
    validateEmailField(body.email, errors);
    if (typeof body.password !== "string" || body.password.length === 0) {
        errors.push("password is required");
    }
    return errors;
}

export { normalizeEmail };

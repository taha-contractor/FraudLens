/**
 * 404 handler for unknown routes. Mounted after all application routes.
 */
export const notFoundHandler = (req, res, next) => {
    const error = new Error(`Route not found: ${req.method} ${req.originalUrl}`);
    error.statusCode = 404;
    error.expected = true;
    next(error);
};

/**
 * Centralized error handler. Must be the last middleware in the chain.
 * Expected errors (ApiError / 404) return their message; anything else
 * is logged server-side and reported as a generic 500 to clients.
 */
export const errorHandler = (err, req, res, next) => {
    const statusCode = err.statusCode || 500;
    const isExpected = err.expected === true || statusCode < 500;

    if (!isExpected) {
        console.error("[error] Unhandled error:", err);
    }

    const body = {
        success: false,
        error: {
            message: isExpected ? err.message : "Internal server error",
            statusCode,
        },
    };

    // Optional field-level validation details (kept within the same error shape).
    if (isExpected && Array.isArray(err.details) && err.details.length > 0) {
        body.error.details = err.details;
    }

    // Stack traces are only exposed in local development, and only for
    // unexpected errors — never for expected client-safe errors (400/401/403/404).
    if (process.env.NODE_ENV !== "production" && !isExpected && err.stack) {
        body.error.stack = err.stack;
    }

    res.status(statusCode).json(body);
};

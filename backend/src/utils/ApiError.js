/**
 * Operational API error with an HTTP status code.
 * Errors of this type are treated as "expected" by the error handler
 * and are safely returned to clients.
 */
export class ApiError extends Error {
    /**
     * @param {number} statusCode - HTTP status code
     * @param {string} message - client-safe error message
     */
    constructor(statusCode, message) {
        super(message);
        this.name = "ApiError";
        this.statusCode = statusCode;
        this.expected = true;
    }
}

export default ApiError;

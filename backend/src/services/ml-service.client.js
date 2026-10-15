/**
 * ML inference service client.
 *
 * The Node backend owns MongoDB, authorization and case isolation; it projects
 * an already case-scoped transaction set and asks the Python FastAPI service to
 * score it. This client never fabricates a score: any transport or service
 * failure is raised as MlServiceError so the caller records an explicit,
 * non-low-risk failure state rather than silently defaulting.
 */

const DEFAULT_URL = "http://127.0.0.1:8100";
const DEFAULT_TIMEOUT_MS = 15000;

function baseUrl() {
    return (process.env.ML_SERVICE_URL || DEFAULT_URL).replace(/\/$/, "");
}

function token() {
    return process.env.ML_SERVICE_TOKEN || "";
}

export class MlServiceError extends Error {
    constructor(message, { status, code } = {}) {
        super(message);
        this.name = "MlServiceError";
        this.status = status;
        this.code = code;
        // Surface to clients as a service-unavailable error (safe, expected)
        // rather than a generic 500 — never a silent low-risk default.
        this.statusCode = status && status >= 400 && status < 500 ? status : 503;
        this.expected = true;
    }
}

async function request(path, options = {}) {
    const timeout = Number(process.env.ML_SERVICE_TIMEOUT_MS) || DEFAULT_TIMEOUT_MS;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);
    const headers = { "content-type": "application/json" };
    if (token()) headers["x-ml-token"] = token();

    let response;
    try {
        response = await fetch(`${baseUrl()}${path}`, { ...options, headers, signal: controller.signal });
    } catch (error) {
        clearTimeout(timer);
        const reason = error.name === "AbortError" ? "timed out" : "unreachable";
        throw new MlServiceError(`ML inference service ${reason}`, { code: "ML_UNAVAILABLE" });
    }
    clearTimeout(timer);

    if (!response.ok) {
        let detail = "";
        try {
            const body = await response.json();
            detail = body?.detail || body?.error || "";
        } catch {
            /* non-JSON error body */
        }
        throw new MlServiceError(`ML inference service error (${response.status})${detail ? `: ${detail}` : ""}`, {
            status: response.status,
        });
    }
    return response.json();
}

export function health() {
    return request("/health");
}

export function modelInfo() {
    return request("/model");
}

/**
 * @param {Array<object>} transactions - case-projected rows for causal replay
 * @param {string[]} [targets] - record_uids to score (omit to score all)
 */
export function score(transactions, targets) {
    return request("/score", {
        method: "POST",
        body: JSON.stringify(targets && targets.length ? { transactions, targets } : { transactions }),
    });
}

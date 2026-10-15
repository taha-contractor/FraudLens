import axios from "axios";

/**
 * Centralized API client. Every network call in the app goes through this
 * module - components never build URLs or attach tokens themselves.
 *
 * Failure policy: a rejected request is thrown to the caller with a readable
 * message taken from the backend error envelope
 * ({ success: false, error: { message, statusCode, details? } }).
 * Mock data is NEVER substituted automatically; the caller decides whether to
 * show an error state (all normal screens) or explicitly use the isolated
 * prototype fixtures in src/mocks/ (demo mode only, clearly labeled).
 */

const BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:5000/api/v1";

const TOKEN_KEY = "fraudlens.token";

export const tokenStore = {
    get: () => localStorage.getItem(TOKEN_KEY),
    set: (t) => localStorage.setItem(TOKEN_KEY, t),
    clear: () => localStorage.removeItem(TOKEN_KEY),
};

export const api = axios.create({ baseURL: BASE_URL, timeout: 30000 });

api.interceptors.request.use((config) => {
    const token = tokenStore.get();
    if (token) config.headers.Authorization = `Bearer ${token}`;
    return config;
});

/** 401s invalidate the session so guards can redirect to login. */
api.interceptors.response.use(
    (res) => res,
    (error) => {
        if (error.response?.status === 401 && tokenStore.get()) {
            tokenStore.clear();
            window.dispatchEvent(new Event("fraudlens:unauthorized"));
        }
        throw error;
    }
);

/** Extract a human-readable message from an axios error (backend envelope). */
export function errorMessage(err) {
    if (err?.response?.data?.error?.message) {
        const details = err.response.data.error.details;
        if (Array.isArray(details) && details.length > 0) {
            return `${err.response.data.error.message}: ${details.map((d) => d.message || d).join("; ")}`;
        }
        return err.response.data.error.message;
    }
    if (err?.code === "ECONNABORTED") return "The request timed out.";
    if (err?.message === "Network Error" || !err?.response) {
        return "Cannot reach the FraudLens API. Check that the backend is running and VITE_API_BASE_URL is correct.";
    }
    return err?.message || "Unexpected error";
}

/** Unwrap the backend's { success, data } envelope. */
export function unwrap(res) {
    return res.data?.data ?? {};
}

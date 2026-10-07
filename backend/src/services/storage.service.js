import crypto from "node:crypto";
import path from "node:path";
import fs from "node:fs/promises";
import ApiError from "../utils/ApiError.js";

/**
 * Storage layer for uploaded investigation documents.
 *
 * Design intent (Database_design.md §10): MongoDB keeps only a
 * `storageReference`; the bytes live in private storage that is never served
 * publicly. This module is the single place that knows *how* files are stored,
 * so local disk can later be swapped for S3 / Azure Blob by re-implementing
 * save / read / remove without touching models, services or routes.
 *
 * A storage reference is an opaque, POSIX-style, storage-root-relative key of
 * the form "<caseId>/<generatedId>.<ext>". It is not a public URL and is not
 * returned by any API response.
 */

// Extensions the storage layer will ever write. Derived from the detected
// document kind, never from the client-supplied filename.
const ALLOWED_EXTENSIONS = new Set([".pdf", ".txt"]);

function getStorageRoot() {
    return path.resolve(process.env.UPLOAD_STORAGE_DIR || path.join(process.cwd(), "uploads"));
}

/**
 * Resolves a storage reference to an absolute path and guarantees the result
 * stays inside the storage root (path traversal protection).
 * @throws {ApiError} 400 for a malformed reference
 */
function resolveStoragePath(storageReference) {
    if (typeof storageReference !== "string" || storageReference.trim() === "") {
        throw new ApiError(400, "Invalid storage reference");
    }
    // Reject anything that looks like traversal or an absolute path before
    // touching the filesystem (belt and braces with the containment check).
    if (/(\.\.)|(^[/\\])|^[a-zA-Z]:/.test(storageReference)) {
        throw new ApiError(400, "Invalid storage reference");
    }

    const root = getStorageRoot();
    const target = path.resolve(root, storageReference);
    const rootWithSep = root.endsWith(path.sep) ? root : root + path.sep;
    if (target !== root && !target.startsWith(rootWithSep)) {
        // Message deliberately contains no path details.
        throw new ApiError(400, "Invalid storage reference");
    }
    return target;
}

/**
 * Persists a validated buffer under the case's private folder.
 * The stored name is generated server-side; the original name is never used
 * for the physical file.
 * @returns {Promise<string>} storage reference to store on the Document
 */
export async function saveDocumentFile({ caseId, buffer, extension }) {
    const ext = String(extension || "").toLowerCase();
    if (!ALLOWED_EXTENSIONS.has(ext)) {
        throw new ApiError(415, "Unsupported document format");
    }

    const storedName = `${crypto.randomUUID()}${ext}`;
    const storageReference = `${caseId}/${storedName}`;
    const absolutePath = resolveStoragePath(storageReference);

    await fs.mkdir(path.dirname(absolutePath), { recursive: true });
    // mode 0o600: private file, not world-readable.
    await fs.writeFile(absolutePath, buffer, { mode: 0o600 });

    return storageReference;
}

/** Reads the stored bytes for processing. */
export async function readDocumentFile(storageReference) {
    const absolutePath = resolveStoragePath(storageReference);
    try {
        return await fs.readFile(absolutePath);
    } catch (error) {
        if (error.code === "ENOENT") {
            throw new ApiError(404, "Stored file is missing");
        }
        throw new ApiError(500, "Could not read stored file");
    }
}

/**
 * Best-effort removal, used to avoid orphaned files when the metadata insert
 * fails. Document deletion as a feature is a later milestone.
 */
export async function removeDocumentFile(storageReference) {
    try {
        await fs.unlink(resolveStoragePath(storageReference));
        return true;
    } catch {
        return false;
    }
}

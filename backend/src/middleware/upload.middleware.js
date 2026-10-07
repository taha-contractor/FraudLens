import multer from "multer";
import ApiError from "../utils/ApiError.js";

/**
 * Multipart upload handling for investigation documents.
 *
 * Files are kept in memory only: the request is fully validated (access,
 * size, real content type) before anything is written to private storage, so
 * an unauthorized or malformed upload never touches the filesystem.
 * The uploads directory is deliberately NOT served as static content.
 */

const MAX_UPLOAD_SIZE_MB = Number(process.env.MAX_UPLOAD_SIZE_MB) || 10;
const MAX_UPLOAD_SIZE_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024;

// First-pass gate on the declared type/extension. The authoritative decision
// is byte sniffing in the document service, so a disguised executable is still
// rejected even if it passes this filter.
const ACCEPTED_HINTS = [".pdf", ".txt"];

const uploader = multer({
    storage: multer.memoryStorage(),
    limits: {
        fileSize: MAX_UPLOAD_SIZE_BYTES,
        files: 1,
        fields: 5,
        fieldSize: 8 * 1024,
    },
    fileFilter: (req, file, cb) => {
        const name = String(file.originalname || "").toLowerCase();
        const hasAcceptedHint = ACCEPTED_HINTS.some((ext) => name.endsWith(ext));
        const declaredOk = ["application/pdf", "text/plain"].includes(file.mimetype);

        if (!hasAcceptedHint || !declaredOk) {
            cb(new ApiError(415, "Unsupported file type; only PDF and TXT documents are accepted"));
            return;
        }
        cb(null, true);
    },
});

/** Accepts one file in the "file" form field and normalizes multer errors. */
export const uploadDocument = (req, res, next) => {
    uploader.single("file")(req, res, (error) => {
        if (!error) {
            if (!req.file) {
                next(new ApiError(400, "A document file is required in the 'file' form field"));
                return;
            }
            next();
            return;
        }

        if (error.name === "MulterError") {
            if (error.code === "LIMIT_FILE_SIZE") {
                next(new ApiError(413, `File too large; the limit is ${MAX_UPLOAD_SIZE_MB} MB`));
                return;
            }
            if (error.code === "LIMIT_UNEXPECTED_FILE") {
                next(new ApiError(400, "Unexpected upload field; send the document in the 'file' field"));
                return;
            }
            if (error.code === "LIMIT_FIELDS" || error.code === "LIMIT_FIELD_VALUE" || error.code === "LIMIT_FIELD_COUNT") {
                next(new ApiError(400, "Too many or oversized form fields"));
                return;
            }
            next(new ApiError(400, "Malformed multipart request"));
            return;
        }

        next(error);
    });
};

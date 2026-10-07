import Document from "../models/Document.js";
import ApiError from "../utils/ApiError.js";
import { readDocumentFile } from "./storage.service.js";
import { detectDocumentKind } from "../validators/document.validator.js";

/**
 * Document processing pipeline (milestone §7):
 *
 *   upload -> Document(PENDING) -> PROCESSING -> extract text -> COMPLETED
 *                                                  failure  -> FAILED
 *
 * Scope guard: this service only extracts text. It does NOT create embeddings,
 * does NOT build the RAG index and does NOT call any LLM - those belong to
 * later milestones. Extracted text (with page boundaries preserved) is stored
 * so the Evidence milestone can turn it into formal evidence.
 */

// Extracted text is stored for later evidence/RAG use; keep an upper bound so
// a single document cannot approach the 16 MB MongoDB document limit.
const MAX_STORED_TEXT_CHARS = 1_000_000;

// A PDF from which fewer than this many characters could be read is treated as
// scanned/image-only rather than as a successful extraction.
const MIN_TEXT_CHARS_FOR_EXTRACTION = 20;

let pdfJsModule;
async function loadPdfJs() {
    // Lazy import: keeps the (large) PDF engine out of the startup path.
    if (!pdfJsModule) {
        pdfJsModule = await import("pdfjs-dist/legacy/build/pdf.mjs");
    }
    return pdfJsModule;
}

/** Extracts selectable text page by page. Throws on structurally invalid PDFs. */
async function extractPdfText(buffer) {
    const { getDocument, VerbosityLevel } = await loadPdfJs();

    const loadingTask = getDocument({
        data: new Uint8Array(buffer),
        verbosity: VerbosityLevel.ERRORS,
        isEvalSupported: false,
        useSystemFonts: true,
    });
    const pdf = await loadingTask.promise;

    try {
        const pages = [];
        for (let pageNumber = 1; pageNumber <= pdf.numPages; pageNumber++) {
            const page = await pdf.getPage(pageNumber);
            const content = await page.getTextContent();
            pages.push({
                pageNumber,
                text: content.items.map((item) => item.str).join(" ").trim(),
            });
            await page.cleanup();
        }
        return { pageCount: pages.length, pages };
    } finally {
        // The loading task owns the worker/parser resources and must be
        // released even when extraction throws.
        await loadingTask.destroy();
    }
}

/** Decodes a text file defensively; never throws on odd encodings. */
function decodeTextFile(buffer) {
    try {
        return { text: new TextDecoder("utf-8", { fatal: true }).decode(buffer), encoding: "UTF-8" };
    } catch {
        // Not valid UTF-8: fall back to a byte-per-character decode so the
        // document still becomes searchable instead of failing outright.
        return { text: new TextDecoder("windows-1252").decode(buffer), encoding: "WINDOWS-1252" };
    }
}

function stripBom(text) {
    return text.charCodeAt(0) === 0xfeff ? text.slice(1) : text;
}

/** Short, client-safe reason. Never a stack trace, never a filesystem path. */
function safeFailureReason(error) {
    if (error instanceof ApiError) return error.message;
    if (error?.name === "InvalidPDFException") return "The file is not a valid PDF document";
    if (error?.name === "PasswordException") return "The PDF is password protected";
    return "Text extraction failed";
}

/**
 * Runs the processing pipeline for one stored document.
 * Safe to call from the request path (via queueDocumentProcessing) or later
 * from a worker/queue without changes.
 */
export async function processDocument(documentId) {
    const doc = await Document.findById(documentId);
    if (!doc) return null;

    try {
        doc.processingStatus = "PROCESSING";
        await doc.save();
    } catch (error) {
        // The document disappeared (e.g. tests/cleanup between queueing and
        // processing): nothing to report, and no failure to record.
        if (error?.name === "DocumentNotFoundError") return null;
        throw error;
    }

    try {
        const buffer = await readDocumentFile(doc.storageReference);
        const kind = detectDocumentKind(buffer)?.kind ?? "TXT";

        let pages = [];
        let pageCount = doc.pageCount;
        let note;

        if (kind === "PDF") {
            const result = await extractPdfText(buffer);
            pages = result.pages;
            pageCount = result.pageCount;
        } else {
            const { text, encoding } = decodeTextFile(stripBomBytes(buffer));
            pages = [{ pageNumber: 1, text: stripBom(text) }];
            pageCount = 1;
            note = `Decoded as ${encoding}`;
        }

        const combined = pages.map((p) => p.text).join("\n\n").trim();
        const hasSelectableText = combined.length >= MIN_TEXT_CHARS_FOR_EXTRACTION;

        doc.processingStatus = "COMPLETED";
        doc.pageCount = pageCount;
        // Scanned/image-only PDFs are reported honestly: the pipeline finished,
        // but nothing was extracted, so OCR is flagged as required.
        doc.textExtractionStatus = hasSelectableText ? "TEXT_EXTRACTED" : "NO_SELECTABLE_TEXT";
        doc.needsOcr = !hasSelectableText;
        doc.extractedText = hasSelectableText ? combined.slice(0, MAX_STORED_TEXT_CHARS) : undefined;
        doc.extractedPages = hasSelectableText
            ? pages.map((p) => ({ pageNumber: p.pageNumber, text: p.text.slice(0, MAX_STORED_TEXT_CHARS) }))
            : undefined;
        doc.extractionNote = hasSelectableText
            ? combined.length > MAX_STORED_TEXT_CHARS
                ? `Text truncated to ${MAX_STORED_TEXT_CHARS} characters`
                : note
            : "No selectable text found; the document appears to be scanned or image-only and needs OCR";
        doc.failureReason = undefined;
        doc.processedAt = new Date();
        await doc.save();

        return doc.toJSON();
    } catch (error) {
        if (error?.name === "DocumentNotFoundError") return null;

        doc.processingStatus = "FAILED";
        doc.textExtractionStatus = "NO_SELECTABLE_TEXT";
        doc.failureReason = safeFailureReason(error);
        doc.processedAt = new Date();
        try {
            await doc.save();
        } catch (saveError) {
            console.error("[document] Could not record processing failure:", saveError.message);
        }
        console.warn(
            `[document] processing failed for ${doc._id}: ${error?.name || "Error"} ${String(error?.message || "").slice(0, 200)}`
        );
        return doc.toJSON();
    }
}

function stripBomBytes(buffer) {
    // UTF-8 BOM (EF BB BF) would otherwise become U+FEFF in the decoded text.
    if (buffer.length >= 3 && buffer[0] === 0xef && buffer[1] === 0xbb && buffer[2] === 0xbf) {
        return buffer.subarray(3);
    }
    return buffer;
}

/**
 * Kicks off processing without delaying the upload response.
 * An in-process deferred task is enough for the prototype; swapping this for a
 * queue/worker later only changes this one call site.
 */
export function queueDocumentProcessing(documentId) {
    setImmediate(() => {
        processDocument(documentId).catch((error) => {
            console.error("[document] unexpected processing error:", error.message);
        });
    });
}

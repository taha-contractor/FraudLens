/**
 * Document upload + processing API test suite.
 * Runs against an isolated in-memory MongoDB instance and a temporary private
 * storage directory; nothing is written into the real uploads folder.
 */
import { test, before, after, beforeEach, describe } from "node:test";
import assert from "node:assert/strict";
import os from "node:os";
import path from "node:path";
import fs from "node:fs/promises";

process.env.NODE_ENV = "test";
process.env.JWT_SECRET = "test-only-secret-not-used-in-any-real-environment";
process.env.JWT_EXPIRES_IN = "1h";
process.env.BCRYPT_SALT_ROUNDS = "4";
// Small limit so the oversize test stays fast.
process.env.MAX_UPLOAD_SIZE_MB = "1";
process.env.UPLOAD_STORAGE_DIR = await fs.mkdtemp(path.join(os.tmpdir(), "fraudlens-test-uploads-"));

let request;
let app;
let User;
let Case;
let Document;
let mongoose;
let memoryServer;

before(async () => {
    ({ default: request } = await import("supertest"));
    ({ default: app } = await import("../src/app.js"));
    ({ default: User } = await import("../src/models/User.js"));
    ({ default: Case } = await import("../src/models/Case.js"));
    ({ default: Document } = await import("../src/models/Document.js"));
    ({ default: mongoose } = await import("mongoose"));

    const { MongoMemoryServer } = await import("mongodb-memory-server");
    memoryServer = await MongoMemoryServer.create();
    await mongoose.connect(memoryServer.getUri("fraudlens_test"));
});

after(async () => {
    await mongoose.disconnect();
    await memoryServer.stop();
    await fs.rm(process.env.UPLOAD_STORAGE_DIR, { recursive: true, force: true });
});

beforeEach(async () => {
    await User.deleteMany({});
    await Case.deleteMany({});
    await Document.deleteMany({});
});

const bearer = (token) => ({ Authorization: `Bearer ${token}` });

/** Builds a real PDF with selectable text (pdf-lib is a dev-only fixture tool). */
async function buildTextPdf(pagesContent) {
    const { PDFDocument, StandardFonts } = await import("pdf-lib");
    const pdf = await PDFDocument.create();
    const font = await pdf.embedFont(StandardFonts.Helvetica);
    for (const lines of pagesContent) {
        const page = pdf.addPage([600, 800]);
        lines.forEach((line, index) => page.drawText(line, { x: 50, y: 720 - index * 24, size: 12, font }));
    }
    return Buffer.from(await pdf.save());
}

/** A PDF page with no text at all - stands in for a scanned document. */
async function buildBlankPdf() {
    const { PDFDocument } = await import("pdf-lib");
    const pdf = await PDFDocument.create();
    pdf.addPage([600, 800]);
    return Buffer.from(await pdf.save());
}

async function setupUserWithCase(email) {
    await request(app)
        .post("/api/v1/auth/register")
        .send({ name: "Test User", email, password: "StrongPassword123" })
        .expect(201);
    const login = await request(app)
        .post("/api/v1/auth/login")
        .send({ email, password: "StrongPassword123" })
        .expect(200);
    const token = login.body.data.accessToken;

    const created = await request(app)
        .post("/api/v1/cases")
        .set(bearer(token))
        .send({ title: "Document Test Case" })
        .expect(201);

    return { token, user: login.body.data.user, caseId: created.body.data.case.id };
}

function upload(token, caseId, file, fields = {}) {
    const req = request(app)
        .post(`/api/v1/cases/${caseId}/documents`)
        .set(bearer(token));
    for (const [key, value] of Object.entries(fields)) req.field(key, value);
    return req.attach("file", file.buffer, file.options);
}

/** Polls the status endpoint until the pipeline reaches a terminal state. */
async function waitForProcessing(token, caseId, documentId, timeoutMs = 20000) {
    const deadline = Date.now() + timeoutMs;
    let last;
    while (Date.now() < deadline) {
        const res = await request(app)
            .get(`/api/v1/cases/${caseId}/documents/${documentId}/status`)
            .set(bearer(token))
            .expect(200);
        last = res.body.data.status;
        if (last.processingStatus === "COMPLETED" || last.processingStatus === "FAILED") return last;
        await new Promise((resolve) => setTimeout(resolve, 50));
    }
    throw new Error(`processing did not finish in time (last state: ${last?.processingStatus})`);
}

const TXT_FILE = {
    buffer: Buffer.from(
        "Account statement - UBO A/C XXXXXXXX4477\nDebit 9,80,000 to Shell Traders Pvt Ltd on 12 Jan 2026.\n",
        "utf8"
    ),
    options: { filename: "statement.txt", contentType: "text/plain" },
};

describe("POST /api/v1/cases/:caseId/documents", () => {
    test("authenticated user can upload a PDF -> 201 with PENDING status", async () => {
        const { token, caseId } = await setupUserWithCase("alice@example.com");
        const buffer = await buildTextPdf([["Suspicious transfer report", "Amount INR 500000 to shell entity"]]);

        const res = await upload(token, caseId, { buffer, options: { filename: "report.pdf", contentType: "application/pdf" } });
        assert.equal(res.status, 201);
        assert.equal(res.body.success, true);
        assert.equal(res.body.data.document.processingStatus, "PENDING");
        assert.equal(res.body.data.document.mimeType, "application/pdf");
    });

    test("authenticated user can upload a TXT document -> 201", async () => {
        const { token, caseId } = await setupUserWithCase("alice@example.com");
        const res = await upload(token, caseId, TXT_FILE);
        assert.equal(res.status, 201);
        assert.equal(res.body.data.document.mimeType, "text/plain");
    });

    test("document belongs to the correct case", async () => {
        const alice = await setupUserWithCase("alice@example.com");
        const bob = await setupUserWithCase("bob@example.com");

        const res = await upload(alice.token, alice.caseId, TXT_FILE);
        assert.equal(res.body.data.document.caseId, alice.caseId);

        const stored = await Document.findById(res.body.data.document.id);
        assert.equal(stored.caseId.toString(), alice.caseId);
        // Bob's own case holds nothing.
        assert.equal(await Document.countDocuments({ caseId: bob.caseId }), 0);
    });

    test("backend-controlled metadata is stored and storage path is not exposed", async () => {
        const { token, user, caseId } = await setupUserWithCase("alice@example.com");
        const res = await upload(token, caseId, TXT_FILE, { documentType: "BANK_STATEMENT" });
        const doc = res.body.data.document;

        assert.equal(doc.fileName, "statement.txt");
        assert.equal(doc.documentType, "BANK_STATEMENT");
        assert.equal(doc.fileSize, TXT_FILE.buffer.length);
        assert.match(doc.checksum, /^[a-f0-9]{64}$/);
        assert.equal(doc.uploadedBy, user.id);
        assert.ok(doc.createdAt);
        // Neither the storage location nor the file bytes are returned.
        assert.equal(doc.storageReference, undefined);
        assert.equal(doc.extractedText, undefined);

        const stored = await Document.findById(doc.id);
        assert.ok(stored.storageReference.startsWith(`${caseId}/`));
        assert.ok(stored.storageReference.endsWith(".txt"));
    });

    test("processing status is tracked through to COMPLETED", async () => {
        const { token, caseId } = await setupUserWithCase("alice@example.com");
        const res = await upload(token, caseId, TXT_FILE);
        const final = await waitForProcessing(token, caseId, res.body.data.document.id);

        assert.equal(final.processingStatus, "COMPLETED");
        assert.equal(final.textExtractionStatus, "TEXT_EXTRACTED");
        assert.equal(final.needsOcr, false);
        assert.ok(final.processedAt);
    });

    test("unauthenticated upload -> 401", async () => {
        const { caseId } = await setupUserWithCase("alice@example.com");
        const res = await request(app)
            .post(`/api/v1/cases/${caseId}/documents`)
            .attach("file", TXT_FILE.buffer, TXT_FILE.options);
        assert.equal(res.status, 401);
    });

    test("no case access -> 403, unknown case -> 404, malformed case id -> 404", async () => {
        const alice = await setupUserWithCase("alice@example.com");
        const bob = await setupUserWithCase("bob@example.com");

        const stranger = await upload(bob.token, alice.caseId, TXT_FILE);
        assert.equal(stranger.status, 403);

        const missing = await upload(alice.token, new mongoose.Types.ObjectId().toString(), TXT_FILE);
        assert.equal(missing.status, 404);

        const malformed = await upload(alice.token, "not-an-id", TXT_FILE);
        assert.equal(malformed.status, 404);
    });

    test("unsupported file types are rejected -> 415", async () => {
        const { token, caseId } = await setupUserWithCase("alice@example.com");

        // Clearly unsupported extension.
        const exe = await upload(token, caseId, {
            buffer: Buffer.from([0x4d, 0x5a, 0x90, 0x00, 0x03]),
            options: { filename: "payload.exe", contentType: "application/octet-stream" },
        });
        assert.equal(exe.status, 415);

        // Binary disguised as .txt with a text MIME type: content sniffing wins.
        const disguised = await upload(token, caseId, {
            buffer: Buffer.concat([Buffer.from([0x4d, 0x5a]), Buffer.alloc(2048, 0x00)]),
            options: { filename: "notes.txt", contentType: "text/plain" },
        });
        assert.equal(disguised.status, 415);
        assert.equal(await Document.countDocuments({ caseId }), 0);
    });

    test("oversized file is rejected -> 413", async () => {
        const { token, caseId } = await setupUserWithCase("alice@example.com");
        const res = await upload(token, caseId, {
            buffer: Buffer.alloc(1.5 * 1024 * 1024, 0x41),
            options: { filename: "huge.txt", contentType: "text/plain" },
        });
        assert.equal(res.status, 413);
        assert.equal(await Document.countDocuments({ caseId }), 0);
    });

    test("missing file -> 400", async () => {
        const { token, caseId } = await setupUserWithCase("alice@example.com");
        const res = await request(app)
            .post(`/api/v1/cases/${caseId}/documents`)
            .set(bearer(token))
            .field("documentType", "GENERAL");
        assert.equal(res.status, 400);
    });

    test("client cannot spoof server-controlled fields -> 400", async () => {
        const { token, caseId, user } = await setupUserWithCase("alice@example.com");
        const otherCase = new mongoose.Types.ObjectId().toString();

        const spoofedCase = await upload(token, caseId, TXT_FILE, { caseId: otherCase });
        assert.equal(spoofedCase.status, 400);
        assert.match(JSON.stringify(spoofedCase.body.error.details), /caseId/);

        const spoofedUploader = await upload(token, caseId, TXT_FILE, { uploadedBy: user.id });
        assert.equal(spoofedUploader.status, 400);

        for (const field of ["checksum", "storageReference", "processingStatus", "pageCount"]) {
            const res = await upload(token, caseId, TXT_FILE, { [field]: "1234" });
            assert.equal(res.status, 400, `${field} should not be client-settable`);
        }

        const badType = await upload(token, caseId, TXT_FILE, { documentType: "NOT_A_TYPE" });
        assert.equal(badType.status, 400);

        assert.equal(await Document.countDocuments({ caseId }), 0);
    });

    test("unsafe filename / path traversal is neutralized", async () => {
        const { token, caseId } = await setupUserWithCase("alice@example.com");

        // 1. Executable with a traversal-heavy path: rejected on the type gate.
        const exe = await upload(token, caseId, {
            buffer: Buffer.concat([Buffer.from([0x4d, 0x5a]), Buffer.alloc(64, 0x01)]),
            options: {
                filename: "../../../../Windows/System32/config/system.exe",
                contentType: "application/octet-stream",
            },
        });
        assert.equal(exe.status, 415);

        // 2. Real PDF arriving under a traversal filename: stored safely, and
        //    only the basename survives into the metadata.
        const pdfBuffer = await buildTextPdf([["Traversal test document with enough text to extract"]]);
        const ok = await upload(token, caseId, {
            buffer: pdfBuffer,
            options: {
                filename: "../../../../etc/passwd.pdf",
                contentType: "application/pdf",
            },
        });
        assert.equal(ok.status, 201);
        assert.equal(ok.body.data.document.fileName, "passwd.pdf");

        // 3. Encoded separators / dot segments cannot escape either.
        const encoded = await upload(token, caseId, {
            buffer: pdfBuffer,
            options: { filename: "..%5c..%5c..%5cetcpasswd.pdf", contentType: "application/pdf" },
        });
        assert.equal(encoded.status, 201);
        const encodedName = encoded.body.data.document.fileName;
        assert.ok(!encodedName.includes(".."), encodedName);
        assert.ok(!encodedName.includes("/"), encodedName);
        assert.ok(!encodedName.includes("\\"), encodedName);

        // Everything on disk lives under <storageRoot>/<caseId>/ with a
        // server-generated name; nothing was created outside the root.
        const caseDir = path.join(process.env.UPLOAD_STORAGE_DIR, caseId);
        const entries = await fs.readdir(caseDir);
        assert.equal(entries.length, 2);
        for (const entry of entries) {
            assert.match(entry, /^[0-9a-f-]{36}\.pdf$/);
        }
        // The storage root contains only case directories (named by ObjectId),
        // so no traversal-derived file could have escaped into it.
        const rootEntries = await fs.readdir(process.env.UPLOAD_STORAGE_DIR);
        for (const entry of rootEntries) {
            assert.match(entry, /^[a-f0-9]{24}$/);
        }

        // No document was created for the rejected executable.
        assert.equal(await Document.countDocuments({ caseId }), 2);
    });
});

describe("GET /api/v1/cases/:caseId/documents", () => {
    test("documents can be listed with metadata only", async () => {
        const { token, caseId } = await setupUserWithCase("alice@example.com");
        await upload(token, caseId, TXT_FILE);
        await upload(token, caseId, {
            buffer: Buffer.from("Second statement file with clearly extractable text content."),
            options: { filename: "second.txt", contentType: "text/plain" },
        });

        const res = await request(app)
            .get(`/api/v1/cases/${caseId}/documents`)
            .set(bearer(token))
            .expect(200);

        assert.equal(res.body.data.count, 2);
        for (const doc of res.body.data.documents) {
            assert.equal(doc.extractedText, undefined);
            assert.equal(doc.extractedPages, undefined);
            assert.equal(doc.storageReference, undefined);
        }
    });

    test("listing never returns another case's documents", async () => {
        const alice = await setupUserWithCase("alice@example.com");
        await upload(alice.token, alice.caseId, TXT_FILE);

        const second = await request(app)
            .post("/api/v1/cases")
            .set(bearer(alice.token))
            .send({ title: "Second Case" })
            .expect(201);

        const res = await request(app)
            .get(`/api/v1/cases/${second.body.data.case.id}/documents`)
            .set(bearer(alice.token))
            .expect(200);
        assert.equal(res.body.data.count, 0);
    });

    test("status filter is validated", async () => {
        const { token, caseId } = await setupUserWithCase("alice@example.com");
        const res = await request(app)
            .get(`/api/v1/cases/${caseId}/documents?status=NOPE`)
            .set(bearer(token));
        assert.equal(res.status, 400);
    });

    test("unauthenticated list -> 401, stranger list -> 403", async () => {
        const alice = await setupUserWithCase("alice@example.com");
        const bob = await setupUserWithCase("bob@example.com");
        await upload(alice.token, alice.caseId, TXT_FILE);

        await request(app).get(`/api/v1/cases/${alice.caseId}/documents`).expect(401);

        const res = await request(app)
            .get(`/api/v1/cases/${alice.caseId}/documents`)
            .set(bearer(bob.token))
            .expect(403);
        assert.equal(res.body.data, undefined);
    });
});

describe("GET /api/v1/cases/:caseId/documents/:documentId", () => {
    test("document can be retrieved", async () => {
        const { token, caseId } = await setupUserWithCase("alice@example.com");
        const created = await upload(token, caseId, TXT_FILE);
        const documentId = created.body.data.document.id;

        const res = await request(app)
            .get(`/api/v1/cases/${caseId}/documents/${documentId}`)
            .set(bearer(token))
            .expect(200);
        assert.equal(res.body.data.document.id, documentId);
        assert.equal(res.body.data.document.extractedText, undefined);
    });

    test("extracted text is available after successful processing", async () => {
        const { token, caseId } = await setupUserWithCase("alice@example.com");
        const pdfBuffer = await buildTextPdf([
            ["Account statement page one", "Credit 1000000 from Investor A"],
            ["Account statement page two", "Debit 950000 to Shell Traders"],
        ]);
        const created = await upload(token, caseId, {
            buffer: pdfBuffer,
            options: { filename: "statement.pdf", contentType: "application/pdf" },
        });
        const documentId = created.body.data.document.id;
        const final = await waitForProcessing(token, caseId, documentId);
        assert.equal(final.processingStatus, "COMPLETED");
        assert.equal(final.pageCount, 2);

        const res = await request(app)
            .get(`/api/v1/cases/${caseId}/documents/${documentId}?include=text`)
            .set(bearer(token))
            .expect(200);

        assert.match(res.body.data.document.extractedText, /Credit 1000000 from Investor A/);
        // Page boundaries are preserved for later evidence/RAG work.
        assert.equal(res.body.data.document.extractedPages.length, 2);
        assert.match(res.body.data.document.extractedPages[1].text, /Shell Traders/);
    });

    test("TXT content is extracted and stored", async () => {
        const { token, caseId } = await setupUserWithCase("alice@example.com");
        const created = await upload(token, caseId, TXT_FILE);
        await waitForProcessing(token, caseId, created.body.data.document.id);

        const res = await request(app)
            .get(`/api/v1/cases/${caseId}/documents/${created.body.data.document.id}?include=text`)
            .set(bearer(token))
            .expect(200);
        assert.match(res.body.data.document.extractedText, /Shell Traders Pvt Ltd/);
    });

    test("scanned / image-only PDF is reported as needing OCR, not as extracted", async () => {
        const { token, caseId } = await setupUserWithCase("alice@example.com");
        const created = await upload(token, caseId, {
            buffer: await buildBlankPdf(),
            options: { filename: "scan.pdf", contentType: "application/pdf" },
        });
        const final = await waitForProcessing(token, caseId, created.body.data.document.id);

        assert.equal(final.processingStatus, "COMPLETED");
        assert.equal(final.textExtractionStatus, "NO_SELECTABLE_TEXT");
        assert.equal(final.needsOcr, true);
        assert.match(final.extractionNote, /OCR/);

        const withText = await request(app)
            .get(`/api/v1/cases/${caseId}/documents/${created.body.data.document.id}?include=text`)
            .set(bearer(token))
            .expect(200);
        assert.equal(withText.body.data.document.extractedText, undefined);
    });

    test("failed processing results in FAILED with a safe reason", async () => {
        const { token, caseId } = await setupUserWithCase("alice@example.com");
        const created = await upload(token, caseId, {
            buffer: Buffer.from("%PDF-1.4\nbroken content that is not a real pdf\n"),
            options: { filename: "broken.pdf", contentType: "application/pdf" },
        });
        const final = await waitForProcessing(token, caseId, created.body.data.document.id);

        assert.equal(final.processingStatus, "FAILED");
        assert.ok(final.failureReason);
        // No stack traces or filesystem paths leak into the reason.
        assert.ok(!final.failureReason.includes("\\\\"));
        assert.ok(!final.failureReason.includes(process.env.UPLOAD_STORAGE_DIR));

        const stored = await Document.findById(created.body.data.document.id);
        assert.equal(stored.extractedText, undefined);
    });

    test("unauthorized user cannot access the document (403, no data)", async () => {
        const alice = await setupUserWithCase("alice@example.com");
        const bob = await setupUserWithCase("bob@example.com");
        const created = await upload(alice.token, alice.caseId, TXT_FILE);

        for (const url of [
            `/api/v1/cases/${alice.caseId}/documents/${created.body.data.document.id}`,
            `/api/v1/cases/${alice.caseId}/documents/${created.body.data.document.id}/status`,
        ]) {
            const res = await request(app).get(url).set(bearer(bob.token)).expect(403);
            assert.equal(res.body.data, undefined);
        }
    });

    test("document from Case A cannot be accessed through Case B -> 404", async () => {
        const alice = await setupUserWithCase("alice@example.com");
        const bob = await setupUserWithCase("bob@example.com");

        // Bob is a legitimate participant of a second case of Alice's.
        const shared = await request(app)
            .post("/api/v1/cases")
            .set(bearer(alice.token))
            .send({ title: "Shared Case", investigators: [bob.user.id] })
            .expect(201);

        const created = await upload(alice.token, alice.caseId, TXT_FILE);
        const documentId = created.body.data.document.id;

        for (const url of [
            `/api/v1/cases/${shared.body.data.case.id}/documents/${documentId}`,
            `/api/v1/cases/${shared.body.data.case.id}/documents/${documentId}/status`,
        ]) {
            const res = await request(app).get(url).set(bearer(bob.token)).expect(404);
            assert.equal(res.body.data, undefined);
        }
    });

    test("unknown or malformed document id -> 404", async () => {
        const { token, caseId } = await setupUserWithCase("alice@example.com");
        await request(app)
            .get(`/api/v1/cases/${caseId}/documents/not-an-id`)
            .set(bearer(token))
            .expect(404);
        await request(app)
            .get(`/api/v1/cases/${caseId}/documents/${new mongoose.Types.ObjectId()}/status`)
            .set(bearer(token))
            .expect(404);
    });
});

describe("GET /api/v1/cases/:caseId/documents/:documentId/status", () => {
    test("status can be retrieved and reflects the pipeline", async () => {
        const { token, caseId } = await setupUserWithCase("alice@example.com");
        const created = await upload(token, caseId, TXT_FILE);
        const documentId = created.body.data.document.id;

        const initial = await request(app)
            .get(`/api/v1/cases/${caseId}/documents/${documentId}/status`)
            .set(bearer(token))
            .expect(200);
        assert.ok(["PENDING", "PROCESSING", "COMPLETED"].includes(initial.body.data.status.processingStatus));

        const final = await waitForProcessing(token, caseId, documentId);
        assert.equal(final.processingStatus, "COMPLETED");
    });

    test("unauthenticated status -> 401", async () => {
        const { token, caseId } = await setupUserWithCase("alice@example.com");
        const created = await upload(token, caseId, TXT_FILE);
        await request(app)
            .get(`/api/v1/cases/${caseId}/documents/${created.body.data.document.id}/status`)
            .expect(401);
    });
});

describe("storage safety", () => {
    test("uploads directory is not publicly served", async () => {
        const { token, caseId } = await setupUserWithCase("alice@example.com");
        const created = await upload(token, caseId, TXT_FILE);
        const stored = await Document.findById(created.body.data.document.id);

        const attempts = [
            `/uploads/${stored.storageReference}`,
            `/api/v1/cases/${caseId}/files/${stored.storageReference}`,
        ];
        for (const url of attempts) {
            const res = await request(app).get(url).set(bearer(token));
            assert.equal(res.status, 404, `${url} must not serve stored files`);
        }
    });
});

/**
 * Evidence management API test suite.
 * Runs against an isolated in-memory MongoDB instance and a temporary private
 * storage directory (evidence itself never touches storage - it only cites a
 * document), so nothing is written into the real uploads folder.
 */
import { test, after, before, beforeEach, describe } from "node:test";
import assert from "node:assert/strict";
import os from "node:os";
import path from "node:path";
import fs from "node:fs/promises";

process.env.NODE_ENV = "test";
process.env.JWT_SECRET = "test-only-secret-not-used-in-any-real-environment";
process.env.JWT_EXPIRES_IN = "1h";
process.env.BCRYPT_SALT_ROUNDS = "4";
process.env.MAX_UPLOAD_SIZE_MB = "1";
process.env.UPLOAD_STORAGE_DIR = await fs.mkdtemp(path.join(os.tmpdir(), "fraudlens-test-evidence-"));

let request;
let app;
let User;
let Case;
let Document;
let Evidence;
let mongoose;
let memoryServer;

before(async () => {
    ({ default: request } = await import("supertest"));
    ({ default: app } = await import("../src/app.js"));
    ({ default: User } = await import("../src/models/User.js"));
    ({ default: Case } = await import("../src/models/Case.js"));
    ({ default: Document } = await import("../src/models/Document.js"));
    ({ default: Evidence } = await import("../src/models/Evidence.js"));
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
    await Evidence.deleteMany({});
});

const bearer = (token) => ({ Authorization: `Bearer ${token}` });

const SOURCE_TEXT = "Debit 9,80,000 to Shell Traders Pvt Ltd on 12 Jan 2026.";

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
        .send({ title: "Evidence Test Case" })
        .expect(201);

    return { token, user: login.body.data.user, caseId: created.body.data.case.id };
}

/** Polls the document status endpoint until the processing pipeline finishes. */
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

/** Uploads a TXT document and waits until it has been processed. */
async function createTextDocument(token, caseId, fileName = "statement.txt", text = SOURCE_TEXT) {
    const res = await request(app)
        .post(`/api/v1/cases/${caseId}/documents`)
        .set(bearer(token))
        .attach("file", Buffer.from(text, "utf8"), { filename: fileName, contentType: "text/plain" })
        .expect(201);
    const documentId = res.body.data.document.id;
    await waitForProcessing(token, caseId, documentId);
    return { id: documentId, fileName };
}

/** Uploads a multi-page PDF and waits until it has been processed. */
async function createMultiPagePdf(token, caseId, pages) {
    const buffer = await buildTextPdf(pages);
    const res = await request(app)
        .post(`/api/v1/cases/${caseId}/documents`)
        .set(bearer(token))
        .attach("file", buffer, { filename: "ledger.pdf", contentType: "application/pdf" })
        .expect(201);
    const documentId = res.body.data.document.id;
    const status = await waitForProcessing(token, caseId, documentId);
    return { id: documentId, fileName: "ledger.pdf", pageCount: status.pageCount };
}

function evidencePayload(documentId, overrides = {}) {
    return {
        documentId,
        pageNumber: 1,
        sourceText: SOURCE_TEXT,
        extractionMethod: "TEXT_EXTRACTION",
        ...overrides,
    };
}

function postEvidence(token, caseId, body) {
    return request(app).post(`/api/v1/cases/${caseId}/evidence`).set(bearer(token)).send(body);
}

function getEvidence(token, caseId, evidenceId) {
    return request(app).get(`/api/v1/cases/${caseId}/evidence/${evidenceId}`).set(bearer(token));
}

function listEvidence(token, caseId, query = "") {
    return request(app).get(`/api/v1/cases/${caseId}/evidence${query}`).set(bearer(token));
}

describe("POST /api/v1/cases/:caseId/evidence", () => {
    test("authenticated user can create evidence against a case document", async () => {
        const { token, caseId } = await setupUserWithCase("alice@example.com");
        const doc = await createTextDocument(token, caseId);

        const res = await postEvidence(token, caseId, evidencePayload(doc.id));

        assert.equal(res.status, 201);
        assert.equal(res.body.success, true);
        assert.equal(res.body.data.evidence.sourceText, SOURCE_TEXT);
        assert.equal(res.body.data.evidence.pageNumber, 1);
    });

    test("valid evidence is stored with server-controlled provenance", async () => {
        const { token, user, caseId } = await setupUserWithCase("alice@example.com");
        const doc = await createTextDocument(token, caseId);

        const res = await postEvidence(token, caseId, evidencePayload(doc.id, { section: "Debit summary" }));
        const evidence = res.body.data.evidence;

        assert.ok(evidence.id);
        assert.equal(evidence._id, undefined);
        assert.equal(evidence.caseId, caseId);
        assert.equal(evidence.documentId, doc.id);
        assert.equal(evidence.createdBy, user.id);
        assert.equal(evidence.section, "Debit summary");
        assert.equal(evidence.evidenceType, "DOCUMENT_TEXT"); // default for v1
        assert.equal(evidence.extractionMethod, "TEXT_EXTRACTION");
        assert.ok(evidence.createdAt && evidence.updatedAt);

        const stored = await Evidence.findById(evidence.id).lean();
        assert.equal(stored.caseId.toString(), caseId);
        assert.equal(stored.documentId.toString(), doc.id);
        assert.equal(stored.sourceText, SOURCE_TEXT);
    });

    test("documentName is populated from the referenced Document, not the client", async () => {
        const { token, caseId } = await setupUserWithCase("alice@example.com");
        const doc = await createTextDocument(token, caseId, "quarterly-statement.txt");

        const res = await postEvidence(token, caseId, evidencePayload(doc.id));

        assert.equal(res.body.data.evidence.documentName, "quarterly-statement.txt");

        // Stored without any client input, and re-read from the Document record.
        const stored = await Evidence.findById(res.body.data.evidence.id).lean();
        const source = await Document.findById(doc.id).lean();
        assert.equal(stored.documentName, source.fileName);
    });

    test("client cannot spoof caseId", async () => {
        const { token, caseId } = await setupUserWithCase("alice@example.com");
        const doc = await createTextDocument(token, caseId);

        const res = await postEvidence(token, caseId, evidencePayload(doc.id, { caseId }));

        assert.equal(res.status, 400);
        assert.equal(res.body.success, false);
        assert.ok(res.body.error.details.some((e) => e.includes("caseId")));
        assert.equal(await Evidence.countDocuments({}), 0);
    });

    test("client cannot spoof createdBy", async () => {
        const { token, caseId } = await setupUserWithCase("alice@example.com");
        const doc = await createTextDocument(token, caseId);
        const fakeUserId = new mongoose.Types.ObjectId();

        const res = await postEvidence(token, caseId, evidencePayload(doc.id, { createdBy: fakeUserId.toString() }));

        assert.equal(res.status, 400);
        assert.ok(res.body.error.details.some((e) => e.includes("createdBy")));
        assert.equal(await Evidence.countDocuments({}), 0);
    });

    test("client cannot spoof documentName", async () => {
        const { token, caseId } = await setupUserWithCase("alice@example.com");
        const doc = await createTextDocument(token, caseId);

        const res = await postEvidence(token, caseId, evidencePayload(doc.id, { documentName: "important-court-order.pdf" }));

        assert.equal(res.status, 400);
        assert.ok(res.body.error.details.some((e) => e.includes("documentName")));
        assert.equal(await Evidence.countDocuments({}), 0);
    });

    test("client cannot spoof timestamps or _id", async () => {
        const { token, caseId } = await setupUserWithCase("alice@example.com");
        const doc = await createTextDocument(token, caseId);

        for (const field of ["createdAt", "updatedAt", "_id", "id"]) {
            const res = await postEvidence(token, caseId, evidencePayload(doc.id, { [field]: "anything" }));
            assert.equal(res.status, 400, `${field} should be rejected`);
            assert.ok(res.body.error.details.some((e) => e.includes(field)));
        }
    });

    test("evidence must reference a document belonging to the same case", async () => {
        const alice = await setupUserWithCase("alice@example.com");
        const bob = await setupUserWithCase("bob@example.com");
        const bobsDocument = await createTextDocument(bob.token, bob.caseId);

        // Bob's document id used inside Alice's case: 404, nothing leaked.
        const res = await postEvidence(alice.token, alice.caseId, evidencePayload(bobsDocument.id));

        assert.equal(res.status, 404);
        assert.equal(res.body.error.message, "Document not found in this case");
        assert.equal(res.body.data, undefined);
        assert.equal(await Evidence.countDocuments({ caseId: alice.caseId }), 0);
    });

    test("unknown document id is rejected the same way as a foreign one", async () => {
        const { token, caseId } = await setupUserWithCase("alice@example.com");

        const res = await postEvidence(token, caseId, evidencePayload(new mongoose.Types.ObjectId().toString()));

        assert.equal(res.status, 404);
        assert.equal(res.body.error.message, "Document not found in this case");
    });

    test("caseId that the user cannot access is rejected with 403", async () => {
        const alice = await setupUserWithCase("alice@example.com");
        const stranger = await setupUserWithCase("mallory@example.com");
        const doc = await createTextDocument(alice.token, alice.caseId);

        const res = await postEvidence(stranger.token, alice.caseId, evidencePayload(doc.id));

        assert.equal(res.status, 403);
        assert.equal(res.body.data, undefined);
        assert.equal(await Evidence.countDocuments({ caseId: alice.caseId }), 0);
    });

    test("missing token is rejected with 401", async () => {
        const { token, caseId } = await setupUserWithCase("alice@example.com");
        const doc = await createTextDocument(token, caseId);

        const res = await request(app).post(`/api/v1/cases/${caseId}/evidence`).send(evidencePayload(doc.id));
        assert.equal(res.status, 401);
    });

    test("invalid pageNumber is rejected", async () => {
        const { token, caseId } = await setupUserWithCase("alice@example.com");
        const doc = await createTextDocument(token, caseId);

        for (const pageNumber of [0, -1, 1.5, "1", null, "abc"]) {
            const res = await postEvidence(token, caseId, evidencePayload(doc.id, { pageNumber }));
            assert.equal(res.status, 400, `pageNumber ${JSON.stringify(pageNumber)} should be rejected`);
            assert.ok(res.body.error.details.some((e) => e.includes("pageNumber")));
        }

        const missing = await postEvidence(token, caseId, {
            documentId: doc.id,
            sourceText: SOURCE_TEXT,
            extractionMethod: "MANUAL",
        });
        assert.equal(missing.status, 400);
        assert.ok(missing.body.error.details.some((e) => e.includes("pageNumber")));
        assert.equal(await Evidence.countDocuments({}), 0);
    });

    test("pageNumber beyond the document's real page count is rejected", async () => {
        const { token, caseId } = await setupUserWithCase("alice@example.com");
        const pdf = await createMultiPagePdf(token, caseId, [
            ["First page: credit 500000 from Investor A"],
            ["Second page: debit 420000 to Shell Traders"],
        ]);
        assert.equal(pdf.pageCount, 2);

        const tooHigh = await postEvidence(token, caseId, evidencePayload(pdf.id, { pageNumber: 3 }));
        assert.equal(tooHigh.status, 400);
        assert.match(tooHigh.body.error.details ? tooHigh.body.error.details.join(" ") : tooHigh.body.error.message, /pageNumber/);

        const lastPage = await postEvidence(token, caseId, evidencePayload(pdf.id, { pageNumber: 2 }));
        assert.equal(lastPage.status, 201);
    });

    test("invalid evidenceType is rejected", async () => {
        const { token, caseId } = await setupUserWithCase("alice@example.com");
        const doc = await createTextDocument(token, caseId);

        const res = await postEvidence(token, caseId, evidencePayload(doc.id, { evidenceType: "TRANSACTION" }));
        assert.equal(res.status, 400);
        assert.ok(res.body.error.details.some((e) => e.includes("evidenceType")));

        const valid = await postEvidence(token, caseId, evidencePayload(doc.id, { evidenceType: "DOCUMENT_TABLE" }));
        assert.equal(valid.status, 201);
        assert.equal(valid.body.data.evidence.evidenceType, "DOCUMENT_TABLE");
    });

    test("invalid or missing extractionMethod is rejected", async () => {
        const { token, caseId } = await setupUserWithCase("alice@example.com");
        const doc = await createTextDocument(token, caseId);

        const invalid = await postEvidence(token, caseId, evidencePayload(doc.id, { extractionMethod: "LLM_GUESS" }));
        assert.equal(invalid.status, 400);
        assert.ok(invalid.body.error.details.some((e) => e.includes("extractionMethod")));

        const { extractionMethod, ...withoutMethod } = evidencePayload(doc.id);
        const missing = await postEvidence(token, caseId, withoutMethod);
        assert.equal(missing.status, 400);
        assert.ok(missing.body.error.details.some((e) => e.includes("extractionMethod")));

        for (const method of ["TEXT_EXTRACTION", "OCR", "MANUAL"]) {
            const ok = await postEvidence(token, caseId, evidencePayload(doc.id, { extractionMethod: method }));
            assert.equal(ok.status, 201, `${method} should be accepted`);
        }
    });

    test("missing or blank sourceText is rejected", async () => {
        const { token, caseId } = await setupUserWithCase("alice@example.com");
        const doc = await createTextDocument(token, caseId);

        for (const sourceText of ["", "   ", 42, null]) {
            const res = await postEvidence(token, caseId, evidencePayload(doc.id, { sourceText }));
            assert.equal(res.status, 400, `sourceText ${JSON.stringify(sourceText)} should be rejected`);
            assert.ok(res.body.error.details.some((e) => e.includes("sourceText")));
        }

        const missing = await postEvidence(token, caseId, { documentId: doc.id, pageNumber: 1, extractionMethod: "MANUAL" });
        assert.equal(missing.status, 400);
        assert.equal(await Evidence.countDocuments({}), 0);
    });

    test("malformed documentId is handled safely", async () => {
        const { token, caseId } = await setupUserWithCase("alice@example.com");

        const res = await postEvidence(token, caseId, evidencePayload("not-an-id"));

        assert.equal(res.status, 400);
        assert.ok(res.body.error.details.some((e) => e.includes("documentId")));
        assert.equal(await Evidence.countDocuments({}), 0);
    });

    test("malformed caseId is handled safely with 404", async () => {
        const { token } = await setupUserWithCase("alice@example.com");

        const res = await postEvidence(token, "not-an-id", evidencePayload(new mongoose.Types.ObjectId().toString()));

        assert.equal(res.status, 404);
        assert.equal(res.body.error.message, "Case not found");
    });

    test("evidence never exposes internal storage paths", async () => {
        const { token, caseId } = await setupUserWithCase("alice@example.com");
        const doc = await createTextDocument(token, caseId);

        const created = await postEvidence(token, caseId, evidencePayload(doc.id));
        const listed = await listEvidence(token, caseId);
        const single = await getEvidence(token, caseId, created.body.data.evidence.id);

        for (const body of [created.body, listed.body, single.body]) {
            const serialized = JSON.stringify(body);
            assert.ok(!serialized.includes("storageReference"));
            assert.ok(!serialized.includes(process.env.UPLOAD_STORAGE_DIR));
            assert.ok(!serialized.includes("uploads"));
        }
    });
});

describe("GET /api/v1/cases/:caseId/evidence", () => {
    test("list is case-scoped and returns only that case's evidence", async () => {
        const alice = await setupUserWithCase("alice@example.com");
        const bob = await setupUserWithCase("bob@example.com");

        const aliceDoc = await createTextDocument(alice.token, alice.caseId, "alice.txt");
        const bobDoc = await createTextDocument(bob.token, bob.caseId, "bob.txt");

        await postEvidence(alice.token, alice.caseId, evidencePayload(aliceDoc.id, { sourceText: "Alice evidence one" }));
        await postEvidence(alice.token, alice.caseId, evidencePayload(aliceDoc.id, { sourceText: "Alice evidence two" }));
        await postEvidence(bob.token, bob.caseId, evidencePayload(bobDoc.id, { sourceText: "Bob evidence" }));

        const res = await listEvidence(alice.token, alice.caseId).expect(200);

        assert.equal(res.body.success, true);
        assert.equal(res.body.data.count, 2);
        assert.equal(res.body.data.evidence.length, 2);
        for (const evidence of res.body.data.evidence) {
            assert.equal(evidence.caseId, alice.caseId);
            assert.equal(evidence.documentId, aliceDoc.id);
            assert.ok(!evidence.sourceText.startsWith("Bob"));
        }
    });

    test("list returns lightweight fields and no document binary or text blobs", async () => {
        const { token, caseId } = await setupUserWithCase("alice@example.com");
        const doc = await createTextDocument(token, caseId);
        await postEvidence(token, caseId, evidencePayload(doc.id));

        const res = await listEvidence(token, caseId).expect(200);
        const [evidence] = res.body.data.evidence;

        assert.deepEqual(Object.keys(evidence).sort(), [
            "caseId",
            "createdAt",
            "createdBy",
            "documentId",
            "documentName",
            "evidenceType",
            "extractionMethod",
            "id",
            "pageNumber",
            "sourceText",
            "updatedAt",
        ]);
    });

    test("list supports documentId / evidenceType / extractionMethod / pageNumber filters", async () => {
        const { token, caseId } = await setupUserWithCase("alice@example.com");
        const pdf = await createMultiPagePdf(token, caseId, [
            ["Page one text about credits"],
            ["Page two text about debits"],
        ]);

        await postEvidence(token, caseId, evidencePayload(pdf.id, { pageNumber: 1, evidenceType: "DOCUMENT_TEXT" }));
        await postEvidence(token, caseId, evidencePayload(pdf.id, { pageNumber: 2, evidenceType: "DOCUMENT_TABLE", extractionMethod: "MANUAL" }));

        const byDocument = await listEvidence(token, caseId, `?documentId=${pdf.id}`).expect(200);
        assert.equal(byDocument.body.data.count, 2);

        const byType = await listEvidence(token, caseId, "?evidenceType=DOCUMENT_TABLE").expect(200);
        assert.equal(byType.body.data.count, 1);
        assert.equal(byType.body.data.evidence[0].pageNumber, 2);

        const byMethod = await listEvidence(token, caseId, "?extractionMethod=MANUAL").expect(200);
        assert.equal(byMethod.body.data.count, 1);

        const byPage = await listEvidence(token, caseId, "?pageNumber=1").expect(200);
        assert.equal(byPage.body.data.count, 1);

        const withLimit = await listEvidence(token, caseId, "?limit=1").expect(200);
        assert.equal(withLimit.body.data.count, 1);
    });

    test("invalid filter values are rejected with 400", async () => {
        const { token, caseId } = await setupUserWithCase("alice@example.com");

        const badType = await listEvidence(token, caseId, "?evidenceType=NOPE").expect(400);
        assert.ok(badType.body.error.message);

        const badDocument = await listEvidence(token, caseId, "?documentId=not-an-id").expect(400);
        assert.ok(badDocument.body.error.details.some((e) => e.includes("documentId")));

        const badPage = await listEvidence(token, caseId, "?pageNumber=zero").expect(400);
        assert.ok(badPage.body.error.details.some((e) => e.includes("pageNumber")));
    });

    test("a case the user is not part of yields 403 and no metadata", async () => {
        const alice = await setupUserWithCase("alice@example.com");
        const stranger = await setupUserWithCase("mallory@example.com");
        const doc = await createTextDocument(alice.token, alice.caseId);
        await postEvidence(alice.token, alice.caseId, evidencePayload(doc.id));

        const res = await listEvidence(stranger.token, alice.caseId);

        assert.equal(res.status, 403);
        assert.equal(res.body.data, undefined);
        assert.ok(!JSON.stringify(res.body).includes(SOURCE_TEXT));
    });

    test("missing token is rejected with 401", async () => {
        const { caseId } = await setupUserWithCase("alice@example.com");
        const res = await request(app).get(`/api/v1/cases/${caseId}/evidence`);
        assert.equal(res.status, 401);
    });

    test("malformed caseId is handled safely with 404", async () => {
        const { token } = await setupUserWithCase("alice@example.com");
        const res = await listEvidence(token, "not-an-id");
        assert.equal(res.status, 404);
        assert.equal(res.body.error.message, "Case not found");
    });
});

describe("GET /api/v1/cases/:caseId/evidence/:evidenceId", () => {
    test("get is case-scoped: owner retrieves the record with provenance", async () => {
        const { token, caseId } = await setupUserWithCase("alice@example.com");
        const doc = await createTextDocument(token, caseId, "evidence-source.txt");
        const created = await postEvidence(token, caseId, evidencePayload(doc.id, { section: "Para 3" }));
        const evidenceId = created.body.data.evidence.id;

        const res = await getEvidence(token, caseId, evidenceId).expect(200);

        assert.equal(res.body.data.evidence.id, evidenceId);
        assert.equal(res.body.data.evidence.documentName, "evidence-source.txt");
        assert.equal(res.body.data.evidence.pageNumber, 1);
        assert.equal(res.body.data.evidence.section, "Para 3");
        assert.equal(res.body.data.evidence.sourceText, SOURCE_TEXT);
    });

    test("evidence from another case is not reachable through that case", async () => {
        const alice = await setupUserWithCase("alice@example.com");
        const bob = await setupUserWithCase("bob@example.com");
        const doc = await createTextDocument(alice.token, alice.caseId);
        const created = await postEvidence(alice.token, alice.caseId, evidencePayload(doc.id));
        const evidenceId = created.body.data.evidence.id;

        const res = await getEvidence(bob.token, bob.caseId, evidenceId);

        assert.equal(res.status, 404);
        assert.equal(res.body.error.message, "Evidence not found in this case");
        assert.equal(res.body.data, undefined);
        assert.ok(!JSON.stringify(res.body).includes(SOURCE_TEXT));
    });

    test("a case the user is not part of yields 403", async () => {
        const alice = await setupUserWithCase("alice@example.com");
        const stranger = await setupUserWithCase("mallory@example.com");
        const doc = await createTextDocument(alice.token, alice.caseId);
        const created = await postEvidence(alice.token, alice.caseId, evidencePayload(doc.id));

        const res = await getEvidence(stranger.token, alice.caseId, created.body.data.evidence.id);

        assert.equal(res.status, 403);
        assert.equal(res.body.data, undefined);
    });

    test("malformed and unknown evidence ids are handled safely with 404", async () => {
        const { token, caseId } = await setupUserWithCase("alice@example.com");

        const malformed = await getEvidence(token, caseId, "not-an-id");
        assert.equal(malformed.status, 404);
        assert.equal(malformed.body.error.message, "Evidence not found in this case");

        const unknown = await getEvidence(token, caseId, new mongoose.Types.ObjectId().toString());
        assert.equal(unknown.status, 404);
    });

    test("missing token is rejected with 401", async () => {
        const { token, caseId } = await setupUserWithCase("alice@example.com");
        const doc = await createTextDocument(token, caseId);
        const created = await postEvidence(token, caseId, evidencePayload(doc.id));

        const res = await request(app).get(
            `/api/v1/cases/${caseId}/evidence/${created.body.data.evidence.id}`
        );
        assert.equal(res.status, 401);
    });
});

/**
 * ML risk-assessment integration test (Phase 1).
 *
 * Exercises the real Node -> Python inference path against a live uvicorn
 * service and an isolated in-memory MongoDB. If the ML service cannot be
 * reached, the suite skips its scoring assertions and reports why rather than
 * silently passing (mock is never substituted for a failed real API).
 */
import { test, before, after, beforeEach, describe } from "node:test";
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";

process.env.NODE_ENV = "test";
process.env.JWT_SECRET = "test-only-secret-not-used-in-any-real-environment";
process.env.JWT_EXPIRES_IN = "1h";
process.env.BCRYPT_SALT_ROUNDS = "4";

const ML_PORT = 8199;
process.env.ML_SERVICE_URL = `http://127.0.0.1:${ML_PORT}`;

let request, app, User, Case, Account, Transaction, mongoose, memoryServer;
let mlProcess = null;
let mlAvailable = false;

const here = path.dirname(fileURLToPath(import.meta.url));
const serviceDir = path.resolve(here, "..", "..", "ml-service");
const servicePython = path.join(serviceDir, ".venv", "Scripts", "python.exe");

async function waitForMl(timeoutMs = 25000) {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
        try {
            const res = await fetch(`${process.env.ML_SERVICE_URL}/health`);
            if (res.ok) return true;
        } catch {
            /* not up yet */
        }
        await new Promise((r) => setTimeout(r, 400));
    }
    return false;
}

async function startMlService() {
    try {
        mlProcess = spawn(servicePython, ["run_server.py", String(ML_PORT)], {
            cwd: serviceDir,
            stdio: ["ignore", "ignore", "pipe"],
        });
        mlProcess.on("error", (e) => console.log(`  ! ml spawn error: ${e.message}`));
        mlProcess.stderr.on("data", () => {}); // drain to avoid EPIPE on exit
        mlAvailable = await waitForMl();
    } catch (e) {
        console.log(`  ! ml service failed to start: ${e.message}`);
        mlAvailable = false;
    }
}

function stopMlService() {
    if (mlProcess && !mlProcess.killed) {
        // Windows: taskkill for a clean tree kill; ignore races.
        try {
            spawn("taskkill", ["/PID", String(mlProcess.pid), "/T", "/F"], { stdio: "ignore" });
        } catch {
            mlProcess.kill();
        }
    }
    mlProcess = null;
}

before(async () => {
    ({ default: request } = await import("supertest"));
    ({ default: app } = await import("../src/app.js"));
    ({ default: User } = await import("../src/models/User.js"));
    ({ default: Case } = await import("../src/models/Case.js"));
    ({ default: Account } = await import("../src/models/Account.js"));
    ({ default: Transaction } = await import("../src/models/Transaction.js"));
    ({ default: mongoose } = await import("mongoose"));
    const { MongoMemoryServer } = await import("mongodb-memory-server");
    memoryServer = await MongoMemoryServer.create();
    await mongoose.connect(memoryServer.getUri("fraudlens_test"));
    await startMlService();
});

after(async () => {
    stopMlService();
    await mongoose.disconnect();
    await memoryServer.stop();
});

beforeEach(async () => {
    await User.deleteMany({});
    await Case.deleteMany({});
    await Account.deleteMany({});
    await Transaction.deleteMany({});
});

const bearer = (token) => ({ Authorization: `Bearer ${token}` });

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
        .send({ title: "Risk Test Case" })
        .expect(201);
    return { token, user: login.body.data.user, caseId: created.body.data.case.id };
}

async function createAccount(token, caseId, masked) {
    const res = await request(app)
        .post(`/api/v1/cases/${caseId}/accounts`)
        .set(bearer(token))
        .send({ accountNumberMasked: masked, accountType: "SAVINGS", currency: "INR" })
        .expect(201);
    return res.body.data.account.id;
}

async function createPair(token, caseId) {
    const sourceAccountId = await createAccount(token, caseId, "XXXX1111");
    const destinationAccountId = await createAccount(token, caseId, "YYYY2222");
    return { sourceAccountId, destinationAccountId };
}

function payload(overrides = {}) {
    return {
        transactionId: "TXN-0001",
        amount: 5000,
        currency: "INR",
        transactionType: "TRANSFER",
        timestamp: "2026-01-15T10:30:00.000Z",
        ...overrides,
    };
}

describe("transaction analytical fields remain client-immutable", () => {
    test("assessment supplied by client is rejected -> 400", async () => {
        const { token, caseId } = await setupUserWithCase("alice@example.com");
        const accounts = await createPair(token, caseId);
        const res = await request(app)
            .post(`/api/v1/cases/${caseId}/transactions`)
            .set(bearer(token))
            .send(payload({ ...accounts, assessment: { riskScore: 1 } }))
            .expect(400);
        assert.match(JSON.stringify(res.body.error.details || []), /assessment is set by the analytics layer/);
    });

    test("oldbalanceOrg is accepted as an optional model input", async () => {
        const { token, caseId } = await setupUserWithCase("alice@example.com");
        const accounts = await createPair(token, caseId);
        const res = await request(app)
            .post(`/api/v1/cases/${caseId}/transactions`)
            .set(bearer(token))
            .send(payload({ ...accounts, oldbalanceOrg: 12345.67 }))
            .expect(201);
        assert.equal(res.body.data.transaction.oldbalanceOrg, 12345.67);
    });
});

describe("POST /transactions/:id/assess (live ML)", () => {
    test("scores a transaction and persists reserved analytical fields", async (t) => {
        if (!mlAvailable) return t.skip("ML service not running");
        const { token, caseId } = await setupUserWithCase("alice@example.com");
        const accounts = await createPair(token, caseId);
        const created = await request(app)
            .post(`/api/v1/cases/${caseId}/transactions`)
            .set(bearer(token))
            .send(payload(accounts))
            .expect(201);
        const id = created.body.data.transaction.id;

        const res = await request(app)
            .post(`/api/v1/cases/${caseId}/transactions/${id}/assess`)
            .set(bearer(token))
            .expect(200);

        assert.equal(res.body.success, true);
        const a = res.body.data.assessment;
        assert.equal(a.status, "scored");
        assert.ok(a.riskScore >= 0 && a.riskScore <= 1);
        assert.ok(["LOW", "MEDIUM", "HIGH"].includes(a.riskLevel));
        assert.equal(a.threshold, 0.95);
        assert.equal(a.mappedType, "TRANSFER"); // raw type mapped onto model taxonomy
        assert.ok(a.features && Object.keys(a.features).length === 17, "17-feature vector returned");

        // Persisted on the document via the established pattern
        const stored = await Transaction.findById(id).lean();
        assert.equal(typeof stored.riskScore, "number");
        assert.ok(["LOW", "MEDIUM", "HIGH"].includes(stored.riskLevel));
        assert.equal(typeof stored.modelPrediction, "boolean");
        assert.ok(stored.assessment, "full assessment persisted");

        // assessment is stripped from default serialization
        const listed = await request(app)
            .get(`/api/v1/cases/${caseId}/transactions`)
            .set(bearer(token))
            .expect(200);
        assert.equal(listed.body.data.transactions[0].assessment, undefined);
        assert.equal(typeof listed.body.data.transactions[0].riskScore, "number");
    });

    test("GET /transactions/:id/risk returns the persisted assessment", async (t) => {
        if (!mlAvailable) return t.skip("ML service not running");
        const { token, caseId } = await setupUserWithCase("carol@example.com");
        const accounts = await createPair(token, caseId);
        const created = await request(app)
            .post(`/api/v1/cases/${caseId}/transactions`)
            .set(bearer(token))
            .send(payload(accounts))
            .expect(201);
        const id = created.body.data.transaction.id;
        await request(app)
            .post(`/api/v1/cases/${caseId}/transactions/${id}/assess`)
            .set(bearer(token))
            .expect(200);

        const res = await request(app)
            .get(`/api/v1/cases/${caseId}/transactions/${id}/risk`)
            .set(bearer(token))
            .expect(200);
        assert.equal(res.body.data.status, "scored");
        assert.equal(res.body.data.transactionId, id);
    });

    test("batch case assessment scores all transactions in one replay", async (t) => {
        if (!mlAvailable) return t.skip("ML service not running");
        const { token, caseId } = await setupUserWithCase("dave@example.com");
        const accounts = await createPair(token, caseId);
        for (let i = 1; i <= 3; i++) {
            await request(app)
                .post(`/api/v1/cases/${caseId}/transactions`)
                .set(bearer(token))
                .send(payload({ ...accounts, transactionId: `TXN-000${i}`, amount: i * 1000 }))
                .expect(201);
        }
        const res = await request(app)
            .post(`/api/v1/cases/${caseId}/transactions/assess`)
            .set(bearer(token))
            .expect(200);
        assert.equal(res.body.data.assessed, 3);
        assert.equal(res.body.data.scored, 3);
        const scored = await Transaction.countDocuments({ caseId, riskScore: { $ne: null } });
        assert.equal(scored, 3);

        // second run skips already-scored (avoid repeated inference)
        const res2 = await request(app)
            .post(`/api/v1/cases/${caseId}/transactions/assess`)
            .set(bearer(token))
            .expect(200);
        assert.equal(res2.body.data.assessed, 0);
        assert.equal(res2.body.data.skipped, 3);
    });
});

describe("authorization and case isolation on risk endpoints", () => {
    test("unauthenticated assess -> 401", async () => {
        const { token, caseId } = await setupUserWithCase("erin@example.com");
        const accounts = await createPair(token, caseId);
        const created = await request(app)
            .post(`/api/v1/cases/${caseId}/transactions`)
            .set(bearer(token))
            .send(payload(accounts))
            .expect(201);
        await request(app)
            .post(`/api/v1/cases/${caseId}/transactions/${created.body.data.transaction.id}/assess`)
            .expect(401);
    });

    test("cross-case transaction id -> 404 (no leakage)", async () => {
        const { token, caseId } = await setupUserWithCase("frank@example.com");
        const accounts = await createPair(token, caseId);
        const created = await request(app)
            .post(`/api/v1/cases/${caseId}/transactions`)
            .set(bearer(token))
            .send(payload(accounts))
            .expect(201);
        const id = created.body.data.transaction.id;

        const other = await setupUserWithCase("grace@example.com");
        await request(app)
            .post(`/api/v1/cases/${other.caseId}/transactions/${id}/assess`)
            .set(bearer(other.token))
            .expect(404);
        await request(app)
            .get(`/api/v1/cases/${other.caseId}/transactions/${id}/risk`)
            .set(bearer(other.token))
            .expect(404);
    });
});

describe("GET /api/v1/risk/model", () => {
    test("returns live model metadata when the service is up", async () => {
        const { token } = await setupUserWithCase("heidi@example.com");
        const res = await request(app).get("/api/v1/risk/model").set(bearer(token)).expect(200);
        if (mlAvailable) {
            assert.equal(res.body.data.available, true);
            assert.equal(res.body.data.model.threshold, 0.95);
            assert.equal(res.body.data.model.n_features, 17);
            assert.equal(res.body.data.model.winner_id, "xgb_full");
        } else {
            assert.equal(res.body.data.available, false);
        }
    });

    test("unauthenticated -> 401", async () => {
        await request(app).get("/api/v1/risk/model").expect(401);
    });
});

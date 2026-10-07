/**
 * Transaction API test suite.
 * Runs against an isolated in-memory MongoDB instance.
 */
import { test, before, after, beforeEach, describe } from "node:test";
import assert from "node:assert/strict";

process.env.NODE_ENV = "test";
process.env.JWT_SECRET = "test-only-secret-not-used-in-any-real-environment";
process.env.JWT_EXPIRES_IN = "1h";
process.env.BCRYPT_SALT_ROUNDS = "4";

let request;
let app;
let User;
let Case;
let Account;
let Transaction;
let mongoose;
let memoryServer;

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
});

after(async () => {
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

/** Register + login a user, then create a case; returns tokens and ids. */
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
        .send({ title: "Transaction Test Case" })
        .expect(201);

    return { token, user: login.body.data.user, caseId: created.body.data.case.id };
}

/** Creates an account in the given case and returns its id. */
async function createAccount(token, caseId, masked) {
    const res = await request(app)
        .post(`/api/v1/cases/${caseId}/accounts`)
        .set(bearer(token))
        .send({
            accountNumberMasked: masked,
            accountType: "SAVINGS",
            currency: "INR",
        })
        .expect(201);
    return res.body.data.account.id;
}

async function createPair(token, caseId) {
    const sourceAccountId = await createAccount(token, caseId, "XXXX1111");
    const destinationAccountId = await createAccount(token, caseId, "YYYY2222");
    return { sourceAccountId, destinationAccountId };
}

function transactionPayload(overrides = {}) {
    return {
        transactionId: "TXN-0001",
        amount: 5000,
        currency: "INR",
        transactionType: "TRANSFER",
        timestamp: "2026-01-15T10:30:00.000Z",
        ...overrides,
    };
}

describe("POST /api/v1/cases/:caseId/transactions", () => {
    test("authenticated user can create a transaction -> 201", async () => {
        const { token, caseId } = await setupUserWithCase("alice@example.com");
        const { sourceAccountId, destinationAccountId } = await createPair(token, caseId);

        const res = await request(app)
            .post(`/api/v1/cases/${caseId}/transactions`)
            .set(bearer(token))
            .send(transactionPayload({ sourceAccountId, destinationAccountId }))
            .expect(201);

        assert.equal(res.body.success, true);
        assert.equal(res.body.data.transaction.transactionId, "TXN-0001");
        assert.equal(res.body.data.transaction.status, "PENDING");
    });

    test("transaction belongs to the correct case", async () => {
        const { token, caseId } = await setupUserWithCase("alice@example.com");
        const accounts = await createPair(token, caseId);

        const res = await request(app)
            .post(`/api/v1/cases/${caseId}/transactions`)
            .set(bearer(token))
            .send(transactionPayload(accounts))
            .expect(201);

        assert.equal(res.body.data.transaction.caseId, caseId);
        const stored = await Transaction.findById(res.body.data.transaction.id);
        assert.equal(stored.caseId.toString(), caseId);
    });

    test("analytical fields are not set by this milestone", async () => {
        const { token, caseId } = await setupUserWithCase("alice@example.com");
        const accounts = await createPair(token, caseId);

        const res = await request(app)
            .post(`/api/v1/cases/${caseId}/transactions`)
            .set(bearer(token))
            .send(transactionPayload(accounts))
            .expect(201);

        assert.equal(res.body.data.transaction.riskScore, undefined);
        assert.equal(res.body.data.transaction.riskLevel, undefined);
        assert.equal(res.body.data.transaction.modelPrediction, undefined);
    });

    test("unauthenticated user cannot create a transaction -> 401", async () => {
        const { token, caseId } = await setupUserWithCase("alice@example.com");
        const accounts = await createPair(token, caseId);

        await request(app)
            .post(`/api/v1/cases/${caseId}/transactions`)
            .send(transactionPayload(accounts))
            .expect(401);
    });

    test("no case access -> 403, unknown case -> 404, malformed case id -> 404", async () => {
        const alice = await setupUserWithCase("alice@example.com");
        const bob = await setupUserWithCase("bob@example.com");
        const accounts = await createPair(alice.token, alice.caseId);

        await request(app)
            .post(`/api/v1/cases/${alice.caseId}/transactions`)
            .set(bearer(bob.token))
            .send(transactionPayload(accounts))
            .expect(403);

        const missingCase = new mongoose.Types.ObjectId().toString();
        await request(app)
            .post(`/api/v1/cases/${missingCase}/transactions`)
            .set(bearer(alice.token))
            .send(transactionPayload(accounts))
            .expect(404);

        await request(app)
            .post(`/api/v1/cases/not-an-id/transactions`)
            .set(bearer(alice.token))
            .send(transactionPayload(accounts))
            .expect(404);
    });

    test("source account must exist -> 400", async () => {
        const { token, caseId } = await setupUserWithCase("alice@example.com");
        const { destinationAccountId } = await createPair(token, caseId);

        const res = await request(app)
            .post(`/api/v1/cases/${caseId}/transactions`)
            .set(bearer(token))
            .send(
                transactionPayload({
                    sourceAccountId: new mongoose.Types.ObjectId().toString(),
                    destinationAccountId,
                })
            )
            .expect(400);

        assert.match(res.body.error.message, /accounts do not exist/);
    });

    test("destination account must exist -> 400", async () => {
        const { token, caseId } = await setupUserWithCase("alice@example.com");
        const { sourceAccountId } = await createPair(token, caseId);

        await request(app)
            .post(`/api/v1/cases/${caseId}/transactions`)
            .set(bearer(token))
            .send(
                transactionPayload({
                    sourceAccountId,
                    destinationAccountId: new mongoose.Types.ObjectId().toString(),
                })
            )
            .expect(400);
    });

    test("source/destination accounts cannot belong to different cases -> 400", async () => {
        const alice = await setupUserWithCase("alice@example.com");
        const bob = await setupUserWithCase("bob@example.com");

        // Bob is added to Alice's second case so he is authorized there.
        const shared = await request(app)
            .post("/api/v1/cases")
            .set(bearer(alice.token))
            .send({ title: "Shared Case", investigators: [bob.user.id] })
            .expect(201);
        const sharedCaseId = shared.body.data.case.id;

        // Account that lives in the shared case (case B).
        const foreignAccount = await createAccount(bob.token, sharedCaseId, "ZZZZ9999");
        // Accounts that live in Alice's own case (case A).
        const { sourceAccountId } = await createPair(alice.token, alice.caseId);

        const res = await request(app)
            .post(`/api/v1/cases/${alice.caseId}/transactions`)
            .set(bearer(alice.token))
            .send(transactionPayload({ sourceAccountId, destinationAccountId: foreignAccount }))
            .expect(400);
        assert.match(res.body.error.message, /accounts do not exist/);

        const stored = await Transaction.countDocuments({ caseId: alice.caseId });
        assert.equal(stored, 0);
    });

    test("positive amount is required -> 400", async () => {
        const { token, caseId } = await setupUserWithCase("alice@example.com");
        const accounts = await createPair(token, caseId);

        for (const amount of [0, -500, "1000", "abc", null, undefined]) {
            const res = await request(app)
                .post(`/api/v1/cases/${caseId}/transactions`)
                .set(bearer(token))
                .send(transactionPayload({ ...accounts, amount }))
                .expect(400);
            assert.equal(res.body.success, false);
        }
    });

    test("invalid timestamp is rejected -> 400", async () => {
        const { token, caseId } = await setupUserWithCase("alice@example.com");
        const accounts = await createPair(token, caseId);

        for (const timestamp of ["not-a-date", "2026-13-45T99:99:99Z", "", null, undefined]) {
            await request(app)
                .post(`/api/v1/cases/${caseId}/transactions`)
                .set(bearer(token))
                .send(transactionPayload({ ...accounts, timestamp }))
                .expect(400);
        }
    });

    test("missing required fields are rejected -> 400", async () => {
        const { token, caseId } = await setupUserWithCase("alice@example.com");
        const accounts = await createPair(token, caseId);

        const badPayloads = [
            {}, // everything missing
            { ...accounts, amount: 100, currency: "INR", timestamp: "2026-01-01T00:00:00Z" }, // no transactionId
            { ...accounts, transactionId: "TXN-2", timestamp: "2026-01-01T00:00:00Z" }, // no amount/currency/type
            transactionPayload({ ...accounts, currency: "RUPEES" }), // bad currency
            transactionPayload({ ...accounts, transactionType: "T" }), // too short
            transactionPayload({ ...accounts, status: "NOT_A_STATUS" }), // bad status enum
        ];
        for (const payload of badPayloads) {
            const res = await request(app)
                .post(`/api/v1/cases/${caseId}/transactions`)
                .set(bearer(token))
                .send(payload)
                .expect(400);
            assert.equal(res.body.success, false);
        }
    });

    test("client cannot spoof caseId, timestamps or analytical fields -> 400", async () => {
        const { token, caseId } = await setupUserWithCase("alice@example.com");
        const accounts = await createPair(token, caseId);
        const otherCase = new mongoose.Types.ObjectId().toString();

        for (const payload of [
            transactionPayload({ ...accounts, caseId: otherCase }),
            transactionPayload({ ...accounts, createdAt: "2020-01-01T00:00:00.000Z" }),
            transactionPayload({ ...accounts, riskScore: 0.99 }),
            transactionPayload({ ...accounts, riskLevel: "HIGH" }),
            transactionPayload({ ...accounts, modelPrediction: true }),
        ]) {
            const res = await request(app)
                .post(`/api/v1/cases/${caseId}/transactions`)
                .set(bearer(token))
                .send(payload)
                .expect(400);
            assert.equal(res.body.error.details.length > 0, true);
        }
    });

    test("duplicate transactionId in the same case -> 409", async () => {
        const { token, caseId } = await setupUserWithCase("alice@example.com");
        const accounts = await createPair(token, caseId);

        await request(app)
            .post(`/api/v1/cases/${caseId}/transactions`)
            .set(bearer(token))
            .send(transactionPayload(accounts))
            .expect(201);

        const res = await request(app)
            .post(`/api/v1/cases/${caseId}/transactions`)
            .set(bearer(token))
            .send(transactionPayload(accounts))
            .expect(409);
        assert.equal(res.body.success, false);

        const count = await Transaction.countDocuments({ caseId });
        assert.equal(count, 1);
    });

    test("same transactionId in a different case is allowed (case-scoped uniqueness)", async () => {
        const alice = await setupUserWithCase("alice@example.com");
        const accounts = await createPair(alice.token, alice.caseId);

        const second = await request(app)
            .post("/api/v1/cases")
            .set(bearer(alice.token))
            .send({ title: "Second Case" })
            .expect(201);
        const secondCaseId = second.body.data.case.id;

        const secondAccounts = await createPair(alice.token, secondCaseId);

        await request(app)
            .post(`/api/v1/cases/${alice.caseId}/transactions`)
            .set(bearer(alice.token))
            .send(transactionPayload({ ...accounts, transactionId: "TXN-DUP" }))
            .expect(201);

        await request(app)
            .post(`/api/v1/cases/${secondCaseId}/transactions`)
            .set(bearer(alice.token))
            .send(transactionPayload({ ...secondAccounts, transactionId: "TXN-DUP" }))
            .expect(201);
    });
});

describe("GET /api/v1/cases/:caseId/transactions", () => {
    test("user can list transactions for an accessible case", async () => {
        const { token, caseId } = await setupUserWithCase("alice@example.com");
        const accounts = await createPair(token, caseId);

        await request(app)
            .post(`/api/v1/cases/${caseId}/transactions`)
            .set(bearer(token))
            .send(transactionPayload({ ...accounts, transactionId: "TXN-A" }))
            .expect(201);
        await request(app)
            .post(`/api/v1/cases/${caseId}/transactions`)
            .set(bearer(token))
            .send(transactionPayload({ ...accounts, transactionId: "TXN-B" }))
            .expect(201);

        const res = await request(app)
            .get(`/api/v1/cases/${caseId}/transactions`)
            .set(bearer(token))
            .expect(200);
        assert.equal(res.body.data.count, 2);
    });

    test("transactions of another case are never listed", async () => {
        const alice = await setupUserWithCase("alice@example.com");
        const accounts = await createPair(alice.token, alice.caseId);
        await request(app)
            .post(`/api/v1/cases/${alice.caseId}/transactions`)
            .set(bearer(alice.token))
            .send(transactionPayload(accounts))
            .expect(201);

        const second = await request(app)
            .post("/api/v1/cases")
            .set(bearer(alice.token))
            .send({ title: "Second Case" })
            .expect(201);

        const res = await request(app)
            .get(`/api/v1/cases/${second.body.data.case.id}/transactions`)
            .set(bearer(alice.token))
            .expect(200);
        assert.equal(res.body.data.count, 0);
    });

    test("simple filters: account, status, date range", async () => {
        const { token, caseId } = await setupUserWithCase("alice@example.com");
        const { sourceAccountId, destinationAccountId } = await createPair(token, caseId);
        const otherAccount = await createAccount(token, caseId, "ZZZZ0000");
        const otherPair = { sourceAccountId: otherAccount, destinationAccountId };

        await request(app)
            .post(`/api/v1/cases/${caseId}/transactions`)
            .set(bearer(token))
            .send(transactionPayload({ sourceAccountId, destinationAccountId, transactionId: "TXN-1", timestamp: "2026-01-05T00:00:00Z", status: "COMPLETED" }))
            .expect(201);
        await request(app)
            .post(`/api/v1/cases/${caseId}/transactions`)
            .set(bearer(token))
            .send(transactionPayload({ ...otherPair, transactionId: "TXN-2", timestamp: "2026-06-05T00:00:00Z", status: "FAILED" }))
            .expect(201);

        const byAccount = await request(app)
            .get(`/api/v1/cases/${caseId}/transactions?accountId=${sourceAccountId}`)
            .set(bearer(token))
            .expect(200);
        assert.equal(byAccount.body.data.count, 1);
        assert.equal(byAccount.body.data.transactions[0].transactionId, "TXN-1");

        const byStatus = await request(app)
            .get(`/api/v1/cases/${caseId}/transactions?status=FAILED`)
            .set(bearer(token))
            .expect(200);
        assert.equal(byStatus.body.data.count, 1);

        const byRange = await request(app)
            .get(`/api/v1/cases/${caseId}/transactions?from=2026-05-01T00:00:00Z&to=2026-12-31T00:00:00Z`)
            .set(bearer(token))
            .expect(200);
        assert.equal(byRange.body.data.count, 1);

        const badFilter = await request(app)
            .get(`/api/v1/cases/${caseId}/transactions?status=NOPE`)
            .set(bearer(token))
            .expect(400);
        assert.equal(badFilter.body.success, false);
    });

    test("unauthenticated list -> 401", async () => {
        const { caseId } = await setupUserWithCase("alice@example.com");
        await request(app).get(`/api/v1/cases/${caseId}/transactions`).expect(401);
    });
});

describe("GET /api/v1/cases/:caseId/transactions/:transactionId", () => {
    test("user can retrieve a transaction", async () => {
        const { token, caseId } = await setupUserWithCase("alice@example.com");
        const accounts = await createPair(token, caseId);
        const created = await request(app)
            .post(`/api/v1/cases/${caseId}/transactions`)
            .set(bearer(token))
            .send(transactionPayload(accounts))
            .expect(201);

        const res = await request(app)
            .get(`/api/v1/cases/${caseId}/transactions/${created.body.data.transaction.id}`)
            .set(bearer(token))
            .expect(200);
        assert.equal(res.body.data.transaction.id, created.body.data.transaction.id);
    });

    test("unauthorized user cannot access the transaction (no data exposed)", async () => {
        const alice = await setupUserWithCase("alice@example.com");
        const bob = await setupUserWithCase("bob@example.com");
        const accounts = await createPair(alice.token, alice.caseId);
        const created = await request(app)
            .post(`/api/v1/cases/${alice.caseId}/transactions`)
            .set(bearer(alice.token))
            .send(transactionPayload(accounts))
            .expect(201);

        const res = await request(app)
            .get(`/api/v1/cases/${alice.caseId}/transactions/${created.body.data.transaction.id}`)
            .set(bearer(bob.token))
            .expect(403);
        assert.equal(res.body.data, undefined);
    });

    test("transaction from Case A cannot be accessed through Case B -> 404", async () => {
        const alice = await setupUserWithCase("alice@example.com");
        const bob = await setupUserWithCase("bob@example.com");

        // Bob is authorized on a second case owned by Alice.
        const shared = await request(app)
            .post("/api/v1/cases")
            .set(bearer(alice.token))
            .send({ title: "Shared Case", investigators: [bob.user.id] })
            .expect(201);
        const bobCaseId = shared.body.data.case.id;

        const accounts = await createPair(alice.token, alice.caseId);
        const created = await request(app)
            .post(`/api/v1/cases/${alice.caseId}/transactions`)
            .set(bearer(alice.token))
            .send(transactionPayload(accounts))
            .expect(201);

        // Changing the caseId in the URL cannot reach another case's data.
        const res = await request(app)
            .get(`/api/v1/cases/${bobCaseId}/transactions/${created.body.data.transaction.id}`)
            .set(bearer(bob.token))
            .expect(404);
        assert.equal(res.body.data, undefined);
    });

    test("unknown or malformed transaction id -> 404", async () => {
        const { token, caseId } = await setupUserWithCase("alice@example.com");

        await request(app)
            .get(`/api/v1/cases/${caseId}/transactions/not-an-id`)
            .set(bearer(token))
            .expect(404);

        await request(app)
            .get(`/api/v1/cases/${caseId}/transactions/${new mongoose.Types.ObjectId()}`)
            .set(bearer(token))
            .expect(404);
    });
});

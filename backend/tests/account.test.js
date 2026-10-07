/**
 * Account API test suite.
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
let mongoose;
let memoryServer;

before(async () => {
    ({ default: request } = await import("supertest"));
    ({ default: app } = await import("../src/app.js"));
    ({ default: User } = await import("../src/models/User.js"));
    ({ default: Case } = await import("../src/models/Case.js"));
    ({ default: Account } = await import("../src/models/Account.js"));
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
        .send({ title: "Account Test Case" })
        .expect(201);

    return { token, user: login.body.data.user, caseId: created.body.data.case.id };
}

const accountPayload = {
    accountNumberMasked: "XXXXXXXX1234",
    accountType: "SAVINGS",
    currency: "INR",
};

describe("POST /api/v1/cases/:caseId/accounts", () => {
    test("authenticated user can create an account -> 201", async () => {
        const { token, caseId } = await setupUserWithCase("alice@example.com");

        const res = await request(app)
            .post(`/api/v1/cases/${caseId}/accounts`)
            .set(bearer(token))
            .send(accountPayload)
            .expect(201);

        assert.equal(res.body.success, true);
        assert.equal(res.body.data.account.accountNumberMasked, "XXXXXXXX1234");
    });

    test("account belongs to the correct case", async () => {
        const { token, caseId } = await setupUserWithCase("alice@example.com");
        const res = await request(app)
            .post(`/api/v1/cases/${caseId}/accounts`)
            .set(bearer(token))
            .send(accountPayload)
            .expect(201);

        assert.equal(res.body.data.account.caseId, caseId);
        const stored = await Account.findById(res.body.data.account.id);
        assert.equal(stored.caseId.toString(), caseId);
    });

    test("unauthenticated user cannot create an account -> 401", async () => {
        const { caseId } = await setupUserWithCase("alice@example.com");
        await request(app)
            .post(`/api/v1/cases/${caseId}/accounts`)
            .send(accountPayload)
            .expect(401);
    });

    test("no case access -> 403, unknown case -> 404", async () => {
        const alice = await setupUserWithCase("alice@example.com");
        const bob = await setupUserWithCase("bob@example.com");

        // Bob knows Alice's caseId but is not a participant.
        await request(app)
            .post(`/api/v1/cases/${alice.caseId}/accounts`)
            .set(bearer(bob.token))
            .send(accountPayload)
            .expect(403);

        const missingCase = new mongoose.Types.ObjectId().toString();
        await request(app)
            .post(`/api/v1/cases/${missingCase}/accounts`)
            .set(bearer(alice.token))
            .send(accountPayload)
            .expect(404);
    });

    test("client cannot spoof caseId or timestamps -> 400", async () => {
        const { token, caseId } = await setupUserWithCase("alice@example.com");
        const otherCase = new mongoose.Types.ObjectId().toString();

        for (const payload of [
            { ...accountPayload, caseId: otherCase },
            { ...accountPayload, createdAt: "2020-01-01T00:00:00.000Z" },
        ]) {
            await request(app)
                .post(`/api/v1/cases/${caseId}/accounts`)
                .set(bearer(token))
                .send(payload)
                .expect(400);
        }
    });

    test("invalid account data is rejected -> 400", async () => {
        const { token, caseId } = await setupUserWithCase("alice@example.com");
        const badPayloads = [
            {},
            { accountNumberMasked: "AB" }, // too short
            { accountNumberMasked: "1234567890" }, // unmasked account number
            { accountNumberMasked: "XXXX1234", accountType: "S" }, // type too short
            { accountNumberMasked: "XXXX1234", accountType: "SAVINGS", currency: "RUPEES" },
            { ...accountPayload, status: "NOT_A_STATUS" },
        ];
        for (const payload of badPayloads) {
            const res = await request(app)
                .post(`/api/v1/cases/${caseId}/accounts`)
                .set(bearer(token))
                .send(payload)
                .expect(400);
            assert.equal(res.body.success, false);
        }
    });

    test("duplicate masked identifier in same case -> 409", async () => {
        const { token, caseId } = await setupUserWithCase("alice@example.com");
        await request(app)
            .post(`/api/v1/cases/${caseId}/accounts`)
            .set(bearer(token))
            .send(accountPayload)
            .expect(201);

        await request(app)
            .post(`/api/v1/cases/${caseId}/accounts`)
            .set(bearer(token))
            .send(accountPayload)
            .expect(409);
    });
});

describe("GET /api/v1/cases/:caseId/accounts", () => {
    test("user can list accounts for an accessible case", async () => {
        const { token, caseId } = await setupUserWithCase("alice@example.com");
        await request(app)
            .post(`/api/v1/cases/${caseId}/accounts`)
            .set(bearer(token))
            .send(accountPayload)
            .expect(201);
        await request(app)
            .post(`/api/v1/cases/${caseId}/accounts`)
            .set(bearer(token))
            .send({ ...accountPayload, accountNumberMasked: "YYYY5678" })
            .expect(201);

        const res = await request(app)
            .get(`/api/v1/cases/${caseId}/accounts`)
            .set(bearer(token))
            .expect(200);
        assert.equal(res.body.data.count, 2);
    });

    test("accounts of another case are not listed", async () => {
        const alice = await setupUserWithCase("alice@example.com");
        // Alice's account must not appear in a case she shares with nobody else:
        // create a second case for her and check isolation between her own cases.
        const second = await request(app)
            .post("/api/v1/cases")
            .set(bearer(alice.token))
            .send({ title: "Second Case" })
            .expect(201);

        const res = await request(app)
            .get(`/api/v1/cases/${second.body.data.case.id}/accounts`)
            .set(bearer(alice.token))
            .expect(200);
        assert.equal(res.body.data.count, 0);
    });

    test("unauthenticated list -> 401", async () => {
        const { caseId } = await setupUserWithCase("alice@example.com");
        await request(app).get(`/api/v1/cases/${caseId}/accounts`).expect(401);
    });
});

describe("GET /api/v1/cases/:caseId/accounts/:accountId", () => {
    test("user can retrieve an account", async () => {
        const { token, caseId } = await setupUserWithCase("alice@example.com");
        const created = await request(app)
            .post(`/api/v1/cases/${caseId}/accounts`)
            .set(bearer(token))
            .send(accountPayload)
            .expect(201);

        const res = await request(app)
            .get(`/api/v1/cases/${caseId}/accounts/${created.body.data.account.id}`)
            .set(bearer(token))
            .expect(200);
        assert.equal(res.body.data.account.id, created.body.data.account.id);
    });

    test("unauthorized user cannot access the account (no data exposed)", async () => {
        const alice = await setupUserWithCase("alice@example.com");
        const bob = await setupUserWithCase("bob@example.com");
        const created = await request(app)
            .post(`/api/v1/cases/${alice.caseId}/accounts`)
            .set(bearer(alice.token))
            .send(accountPayload)
            .expect(201);

        // Bob has no access to Alice's case -> 403 before any account lookup.
        const res = await request(app)
            .get(`/api/v1/cases/${alice.caseId}/accounts/${created.body.data.account.id}`)
            .set(bearer(bob.token))
            .expect(403);
        assert.equal(res.body.data, undefined);
    });

    test("account from Case A cannot be retrieved through Case B -> 404", async () => {
        // Alice adds Bob to case 2, so Bob is authenticated for case 2 but
        // not case 1: he queries HIS OWN case with ALICE'S account id.
        const alice = await setupUserWithCase("alice@example.com");
        const bob = await setupUserWithCase("bob@example.com");

        // Make bob a participant of a second case owned by alice:
        const case2 = await request(app)
            .post("/api/v1/cases")
            .set(bearer(alice.token))
            .send({ title: "Shared Case", investigators: [bob.user.id] })
            .expect(201);

        // Alice's private account in case 1.
        const created = await request(app)
            .post(`/api/v1/cases/${alice.caseId}/accounts`)
            .set(bearer(alice.token))
            .send(accountPayload)
            .expect(201);

        // Bob queries it through his accessible case 2 -> 404, no leak.
        const res = await request(app)
            .get(`/api/v1/cases/${case2.body.data.case.id}/accounts/${created.body.data.account.id}`)
            .set(bearer(bob.token))
            .expect(404);
        assert.equal(res.body.data, undefined);
    });

    test("invalid ObjectId in URL is handled safely -> 404", async () => {
        const { token, caseId } = await setupUserWithCase("alice@example.com");
        await request(app)
            .get(`/api/v1/cases/${caseId}/accounts/not-an-id`)
            .set(bearer(token))
            .expect(404);
    });
});

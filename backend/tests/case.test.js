/**
 * Case Management v1 test suite.
 * Runs against an isolated in-memory MongoDB instance — the development
 * and production databases are never touched.
 */
import { test, before, after, beforeEach, describe } from "node:test";
import assert from "node:assert/strict";

// Test environment must be set BEFORE the app modules are imported.
process.env.NODE_ENV = "test";
process.env.JWT_SECRET = "test-only-secret-not-used-in-any-real-environment";
process.env.JWT_EXPIRES_IN = "1h";
process.env.BCRYPT_SALT_ROUNDS = "4"; // fast hashes for tests only

let request;
let app;
let User;
let Case;
let mongoose;
let memoryServer;

before(async () => {
    ({ default: request } = await import("supertest"));
    ({ default: app } = await import("../src/app.js"));
    ({ default: User } = await import("../src/models/User.js"));
    ({ default: Case } = await import("../src/models/Case.js"));
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
});

/** Registers a user via the public API and returns { token, user }. */
async function createUser(name, email, password = "StrongPassword123") {
    await request(app)
        .post("/api/v1/auth/register")
        .send({ name, email, password })
        .expect(201);
    const res = await request(app)
        .post("/api/v1/auth/login")
        .send({ email, password })
        .expect(200);
    return { token: res.body.data.accessToken, user: res.body.data.user };
}

const bearer = (token) => ({ Authorization: `Bearer ${token}` });

const casePayload = {
    title: "Suspicious Fund Transfer Investigation",
    description: "Investigation of unusual high-value transactions.",
};

describe("POST /api/v1/cases", () => {
    test("authenticated user can create a case -> 201", async () => {
        const { token } = await createUser("Creator One", "creator1@example.com");

        const res = await request(app)
            .post("/api/v1/cases")
            .set(bearer(token))
            .send(casePayload)
            .expect(201);

        assert.equal(res.body.success, true);
        assert.equal(res.body.data.case.title, casePayload.title);
    });

    test("case number is generated (CASE-<year>-NNN) and stored", async () => {
        const { token } = await createUser("Creator One", "creator1@example.com");
        const res = await request(app)
            .post("/api/v1/cases")
            .set(bearer(token))
            .send(casePayload)
            .expect(201);

        assert.match(res.body.data.case.caseNumber, /^CASE-\d{4}-\d{3}$/);
        const stored = await Case.findOne({ caseNumber: res.body.data.case.caseNumber });
        assert.ok(stored);
    });

    test("new case defaults to OPEN", async () => {
        const { token } = await createUser("Creator One", "creator1@example.com");
        const res = await request(app)
            .post("/api/v1/cases")
            .set(bearer(token))
            .send(casePayload)
            .expect(201);

        assert.equal(res.body.data.case.status, "OPEN");
    });

    test("createdBy is taken from the authenticated user, not the client", async () => {
        const creator = await createUser("Creator One", "creator1@example.com");
        const victim = await createUser("Victim", "victim@example.com");

        // Spoofing createdBy is rejected outright.
        await request(app)
            .post("/api/v1/cases")
            .set(bearer(creator.token))
            .send({ ...casePayload, createdBy: victim.user.id })
            .expect(400);

        // A normally created case belongs to the token owner.
        const res = await request(app)
            .post("/api/v1/cases")
            .set(bearer(creator.token))
            .send(casePayload)
            .expect(201);
        assert.equal(res.body.data.case.createdBy, creator.user.id);
    });

    test("unauthenticated user cannot create a case -> 401", async () => {
        await request(app).post("/api/v1/cases").send(casePayload).expect(401);
    });

    test("invalid case data is rejected -> 400", async () => {
        const { token } = await createUser("Creator One", "creator1@example.com");
        const badPayloads = [
            {}, // missing title
            { title: "x" }, // title too short
            { title: "Valid title", status: "NOT_A_STATUS" }, // invalid status
            { title: "Valid title", investigators: ["not-an-object-id"] }, // bad id
            { title: "Valid title", caseNumber: "CASE-2026-999" }, // client-generated number
        ];
        for (const payload of badPayloads) {
            const res = await request(app)
                .post("/api/v1/cases")
                .set(bearer(token))
                .send(payload)
                .expect(400);
            assert.equal(res.body.success, false);
        }
    });

    test("investigators must be existing users", async () => {
        const { token } = await createUser("Creator One", "creator1@example.com");
        const fakeId = new mongoose.Types.ObjectId().toString();
        await request(app)
            .post("/api/v1/cases")
            .set(bearer(token))
            .send({ ...casePayload, investigators: [fakeId] })
            .expect(400);
    });
});

describe("GET /api/v1/cases", () => {
    test("user sees only their accessible cases (created + assigned)", async () => {
        const alice = await createUser("Alice", "alice@example.com");
        const bob = await createUser("Bob", "bob@example.com");

        // Alice creates a case.
        const aliceCase = await request(app)
            .post("/api/v1/cases")
            .set(bearer(alice.token))
            .send(casePayload)
            .expect(201);

        // Bob creates a case that lists Alice as investigator.
        await request(app)
            .post("/api/v1/cases")
            .set(bearer(bob.token))
            .send({ ...casePayload, title: "Bob Case", investigators: [alice.user.id] })
            .expect(201);

        // A third user's private case.
        const carol = await createUser("Carol", "carol@example.com");
        await request(app).post("/api/v1/cases").set(bearer(carol.token)).send(casePayload).expect(201);

        const res = await request(app).get("/api/v1/cases").set(bearer(alice.token)).expect(200);
        assert.equal(res.body.data.count, 2); // own + assigned, not Carol's
        const titles = res.body.data.cases.map((c) => c.title);
        assert.ok(titles.includes(casePayload.title));
        assert.ok(titles.includes("Bob Case"));
    });

    test("unauthenticated list request -> 401", async () => {
        await request(app).get("/api/v1/cases").expect(401);
    });
});

describe("GET /api/v1/cases/:caseId", () => {
    test("owner can retrieve their case -> 200", async () => {
        const alice = await createUser("Alice", "alice@example.com");
        const created = await request(app)
            .post("/api/v1/cases")
            .set(bearer(alice.token))
            .send(casePayload)
            .expect(201);

        const res = await request(app)
            .get(`/api/v1/cases/${created.body.data.case.id}`)
            .set(bearer(alice.token))
            .expect(200);
        assert.equal(res.body.data.case.caseNumber, created.body.data.case.caseNumber);
    });

    test("assigned investigator can retrieve the case -> 200", async () => {
        const alice = await createUser("Alice", "alice@example.com");
        const bob = await createUser("Bob", "bob@example.com");
        const created = await request(app)
            .post("/api/v1/cases")
            .set(bearer(alice.token))
            .send({ ...casePayload, investigators: [bob.user.id] })
            .expect(201);

        await request(app)
            .get(`/api/v1/cases/${created.body.data.case.id}`)
            .set(bearer(bob.token))
            .expect(200);
    });

    test("unauthorized user cannot retrieve another user's case -> 403, no data exposed", async () => {
        const alice = await createUser("Alice", "alice@example.com");
        const stranger = await createUser("Stranger", "stranger@example.com");
        const created = await request(app)
            .post("/api/v1/cases")
            .set(bearer(alice.token))
            .send(casePayload)
            .expect(201);

        const res = await request(app)
            .get(`/api/v1/cases/${created.body.data.case.id}`)
            .set(bearer(stranger.token))
            .expect(403);

        assert.equal(res.body.success, false);
        assert.equal(res.body.data, undefined); // case data not leaked
    });

    test("non-existent case -> 404", async () => {
        const alice = await createUser("Alice", "alice@example.com");
        const missingId = new mongoose.Types.ObjectId().toString();
        await request(app).get(`/api/v1/cases/${missingId}`).set(bearer(alice.token)).expect(404);
    });
});

describe("PATCH /api/v1/cases/:caseId", () => {
    test("authorized user can update a case -> 200", async () => {
        const alice = await createUser("Alice", "alice@example.com");
        const created = await request(app)
            .post("/api/v1/cases")
            .set(bearer(alice.token))
            .send(casePayload)
            .expect(201);

        const res = await request(app)
            .patch(`/api/v1/cases/${created.body.data.case.id}`)
            .set(bearer(alice.token))
            .send({ status: "UNDER_INVESTIGATION", title: "Renamed Case" })
            .expect(200);

        assert.equal(res.body.data.case.status, "UNDER_INVESTIGATION");
        assert.equal(res.body.data.case.title, "Renamed Case");
        // caseNumber unchanged
        assert.equal(res.body.data.case.caseNumber, created.body.data.case.caseNumber);
    });

    test("unauthorized user cannot update another user's case -> 403", async () => {
        const alice = await createUser("Alice", "alice@example.com");
        const bob = await createUser("Bob", "bob@example.com");
        const created = await request(app)
            .post("/api/v1/cases")
            .set(bearer(alice.token))
            .send(casePayload)
            .expect(201);

        await request(app)
            .patch(`/api/v1/cases/${created.body.data.case.id}`)
            .set(bearer(bob.token))
            .send({ status: "CLOSED" })
            .expect(403);

        // Case state untouched.
        const stillOpen = await Case.findById(created.body.data.case.id);
        assert.equal(stillOpen.status, "OPEN");
    });

    test("createdBy and caseNumber cannot be modified -> 400", async () => {
        const alice = await createUser("Alice", "alice@example.com");
        const mallory = await createUser("Mallory", "mallory@example.com");
        const created = await request(app)
            .post("/api/v1/cases")
            .set(bearer(alice.token))
            .send(casePayload)
            .expect(201);

        for (const payload of [
            { createdBy: mallory.user.id },
            { caseNumber: "CASE-2026-001" },
            { createdAt: "2020-01-01T00:00:00.000Z" },
        ]) {
            await request(app)
                .patch(`/api/v1/cases/${created.body.data.case.id}`)
                .set(bearer(alice.token))
                .send(payload)
                .expect(400);
        }
    });

    test("invalid status is rejected -> 400", async () => {
        const alice = await createUser("Alice", "alice@example.com");
        const created = await request(app)
            .post("/api/v1/cases")
            .set(bearer(alice.token))
            .send(casePayload)
            .expect(201);

        await request(app)
            .patch(`/api/v1/cases/${created.body.data.case.id}`)
            .set(bearer(alice.token))
            .send({ status: "SOMETHING_ELSE" })
            .expect(400);
    });
});

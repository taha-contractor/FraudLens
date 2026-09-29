/**
 * Auth + RBAC test suite.
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
let mongoose;
let memoryServer;

before(async () => {
    ({ default: request } = await import("supertest"));
    ({ default: app } = await import("../src/app.js"));
    ({ default: User } = await import("../src/models/User.js"));
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
});

const validUser = {
    name: "Test User",
    email: "test@example.com",
    password: "StrongPassword123",
};

async function registerAndLogin(user = validUser) {
    await request(app).post("/api/v1/auth/register").send(user).expect(201);
    const res = await request(app)
        .post("/api/v1/auth/login")
        .send({ email: user.email, password: user.password })
        .expect(200);
    return res.body.data.accessToken;
}

describe("POST /api/v1/auth/register", () => {
    test("registers a valid user -> 201, no hash in response, INVESTIGATOR role", async () => {
        const res = await request(app)
            .post("/api/v1/auth/register")
            .send(validUser)
            .expect(201);

        assert.equal(res.body.success, true);
        assert.equal(res.body.data.user.email, validUser.email);
        assert.equal(res.body.data.user.role, "INVESTIGATOR");
        assert.ok(res.body.data.user.id);
        assert.equal(res.body.data.user.passwordHash, undefined);
        assert.equal(res.body.data.user.password, undefined);
    });

    test("duplicate email -> 409 (case-insensitive via normalization)", async () => {
        await request(app).post("/api/v1/auth/register").send(validUser).expect(201);
        const res = await request(app)
            .post("/api/v1/auth/register")
            .send({ ...validUser, email: "TEST@Example.COM" })
            .expect(409);
        assert.equal(res.body.success, false);
    });

    test("invalid input -> 400", async () => {
        const cases = [
            {}, // missing everything
            { name: "X", email: "not-an-email", password: "short" }, // all invalid
            { name: "No Pass", email: "ok@example.com" }, // missing password
            { name: "Weak", email: "weak@example.com", password: "alllowercase" }, // policy violation
        ];
        for (const payload of cases) {
            const res = await request(app).post("/api/v1/auth/register").send(payload).expect(400);
            assert.equal(res.body.success, false);
        }
    });

    test("password is stored hashed, never in plaintext", async () => {
        await request(app).post("/api/v1/auth/register").send(validUser).expect(201);
        const doc = await User.findOne({ email: validUser.email }).select("+passwordHash").lean();
        assert.ok(doc.passwordHash);
        assert.notEqual(doc.passwordHash, validUser.password);
        assert.match(doc.passwordHash, /^\$2[aby]\$/); // bcrypt format
    });

    test("public registration cannot self-assign ADMIN", async () => {
        const res = await request(app)
            .post("/api/v1/auth/register")
            .send({ ...validUser, role: "ADMIN" })
            .expect(201);
        assert.equal(res.body.data.user.role, "INVESTIGATOR");
    });
});

describe("POST /api/v1/auth/login", () => {
    test("valid credentials -> 200 with token and safe user info", async () => {
        await request(app).post("/api/v1/auth/register").send(validUser).expect(201);
        const res = await request(app)
            .post("/api/v1/auth/login")
            .send({ email: validUser.email, password: validUser.password })
            .expect(200);

        assert.equal(res.body.success, true);
        assert.ok(res.body.data.accessToken);
        assert.deepEqual(Object.keys(res.body.data.user).sort(), ["email", "id", "name", "role"]);
        assert.equal(res.body.data.user.passwordHash, undefined);
    });

    test("wrong password -> 401 with generic error", async () => {
        await request(app).post("/api/v1/auth/register").send(validUser).expect(201);
        const res = await request(app)
            .post("/api/v1/auth/login")
            .send({ email: validUser.email, password: "WrongPassword123" })
            .expect(401);
        assert.equal(res.body.error.message, "Invalid email or password");
    });

    test("unknown email -> 401, same generic error (no account enumeration)", async () => {
        const res = await request(app)
            .post("/api/v1/auth/login")
            .send({ email: "ghost@example.com", password: "StrongPassword123" })
            .expect(401);
        assert.equal(res.body.error.message, "Invalid email or password");
    });
});

describe("GET /api/v1/auth/me", () => {
    test("without token -> 401", async () => {
        await request(app).get("/api/v1/auth/me").expect(401);
    });

    test("with invalid token -> 401", async () => {
        await request(app).get("/api/v1/auth/me").set("Authorization", "Bearer not.a.jwt").expect(401);
    });

    test("with valid token -> 200 and safe user info", async () => {
        const token = await registerAndLogin();
        const res = await request(app)
            .get("/api/v1/auth/me")
            .set("Authorization", `Bearer ${token}`)
            .expect(200);

        assert.equal(res.body.success, true);
        assert.equal(res.body.data.user.email, validUser.email);
        assert.equal(res.body.data.user.passwordHash, undefined);
    });

    test("inactive user cannot use protected endpoint even with a valid token", async () => {
        const token = await registerAndLogin();
        await User.updateOne({ email: validUser.email }, { $set: { isActive: false } });
        await request(app).get("/api/v1/auth/me").set("Authorization", `Bearer ${token}`).expect(401);
    });

    test("inactive user cannot log in", async () => {
        await request(app).post("/api/v1/auth/register").send(validUser).expect(201);
        await User.updateOne({ email: validUser.email }, { $set: { isActive: false } });
        await request(app)
            .post("/api/v1/auth/login")
            .send({ email: validUser.email, password: validUser.password })
            .expect(403);
    });
});

describe("RBAC (authorizeRoles)", () => {
    let rbacApp;

    before(async () => {
        // Isolated sub-app reusing the REAL middleware chain, because the
        // main app's notFoundHandler is already registered at module load.
        const { default: express } = await import("express");
        const { authenticate } = await import("../src/middleware/auth.middleware.js");
        const { authorizeRoles } = await import("../src/middleware/rbac.middleware.js");
        const { errorHandler } = await import("../src/middleware/error.middleware.js");
        rbacApp = express();
        rbacApp.get("/admin-only", authenticate, authorizeRoles("ADMIN"), (req, res) => {
            res.status(200).json({ success: true, data: { allowed: true } });
        });
        rbacApp.use(errorHandler);
    });

    test("permitted role (ADMIN) -> 200", async () => {
        // Elevated roles are provisioned directly in the DB, never via public registration.
        const bcrypt = (await import("bcryptjs")).default;
        const admin = await User.create({
            name: "Admin User",
            email: "admin@example.com",
            passwordHash: await bcrypt.hash("StrongPassword123", 4),
            role: "ADMIN",
        });
        const token = await request(app)
            .post("/api/v1/auth/login")
            .send({ email: admin.email, password: "StrongPassword123" })
            .expect(200)
            .then((r) => r.body.data.accessToken);

        await request(rbacApp)
            .get("/admin-only")
            .set("Authorization", `Bearer ${token}`)
            .expect(200);
    });

    test("forbidden role (INVESTIGATOR) -> 403", async () => {
        const token = await registerAndLogin(); // registered as INVESTIGATOR
        const res = await request(rbacApp)
            .get("/admin-only")
            .set("Authorization", `Bearer ${token}`)
            .expect(403);
        assert.equal(res.body.success, false);
    });

    test("no token -> 401 (authentication before authorization)", async () => {
        await request(rbacApp).get("/admin-only").expect(401);
    });
});

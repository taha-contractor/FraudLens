/**
 * Financial analytics API test suite (Milestone 7A).
 * Runs against an isolated in-memory MongoDB instance. Analytics is read-only:
 * every test asserts on responses, and the suspicious endpoint is checked for
 * leaving no risk fields behind in the database.
 */
import { test, after, before, beforeEach, describe } from "node:test";
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
let transactionHour;
let isNightTransaction;
let isHighValue;

before(async () => {
    ({ default: request } = await import("supertest"));
    ({ default: app } = await import("../src/app.js"));
    ({ default: User } = await import("../src/models/User.js"));
    ({ default: Case } = await import("../src/models/Case.js"));
    ({ default: Account } = await import("../src/models/Account.js"));
    ({ default: Transaction } = await import("../src/models/Transaction.js"));
    ({ default: mongoose } = await import("mongoose"));
    ({ transactionHour, isNightTransaction, isHighValue } = await import(
        "../src/services/analytics.service.js"
    ));

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

async function registerAndLogin(email) {
    await request(app)
        .post("/api/v1/auth/register")
        .send({ name: "Test User", email, password: "StrongPassword123" })
        .expect(201);
    const login = await request(app)
        .post("/api/v1/auth/login")
        .send({ email, password: "StrongPassword123" })
        .expect(200);
    return login.body.data.accessToken;
}

async function createCase(token, title = "Analytics Test Case") {
    const res = await request(app)
        .post("/api/v1/cases")
        .set(bearer(token))
        .send({ title })
        .expect(201);
    return res.body.data.case.id;
}

async function createAccount(token, caseId, masked, currency = "INR") {
    const res = await request(app)
        .post(`/api/v1/cases/${caseId}/accounts`)
        .set(bearer(token))
        .send({
            accountNumberMasked: masked,
            accountType: "SAVINGS",
            currency,
        })
        .expect(201);
    return res.body.data.account.id;
}

/**
 * Six completed + four non-completed transactions spread over four IST days.
 * Timestamps are UTC; the IST equivalent is noted for each row so the expected
 * night/hour behaviour is verifiable by hand.
 */
function defaultTxns(accounts) {
    const { S, D, E } = accounts;
    return [
        // completed, IST 09:30 / 10:30 / 11:30 on 2026-01-10
        row("TXN-01", S, D, 1000, "COMPLETED", "2026-01-10T04:00:00.000Z"),
        row("TXN-02", S, D, 2000, "COMPLETED", "2026-01-10T05:00:00.000Z"),
        row("TXN-03", S, D, 3000, "COMPLETED", "2026-01-10T06:00:00.000Z"),
        // completed, IST 23:00 on 2026-01-12 -> night + high value + unusual amount
        row("TXN-04", S, D, 60000, "COMPLETED", "2026-01-12T17:30:00.000Z"),
        // completed, IST 00:30 on 2026-01-13 (UTC date is the 12th!) -> night
        row("TXN-10", E, S, 800, "COMPLETED", "2026-01-12T19:00:00.000Z"),
        // completed, IST 07:30 on 2026-01-13
        row("TXN-05", D, E, 500, "COMPLETED", "2026-01-13T02:00:00.000Z"),
        // non-completed rows must never move completed money
        row("TXN-06", S, D, 1500, "FAILED", "2026-01-13T03:00:00.000Z"),
        row("TXN-07", S, D, 2500, "PENDING", "2026-01-13T04:00:00.000Z"),
        row("TXN-08", D, S, 700, "REVERSED", "2026-01-14T05:00:00.000Z"),
        row("TXN-09", S, D, 900, "CANCELLED", "2026-01-14T06:00:00.000Z"),
    ];
}

function row(transactionId, sourceAccountId, destinationAccountId, amount, status, timestamp) {
    return {
        transactionId,
        sourceAccountId,
        destinationAccountId,
        amount,
        status,
        timestamp,
        currency: "INR",
        transactionType: "TRANSFER",
    };
}

/** Registers a user, creates one case with three accounts and the default dataset. */
async function seedFixture(email) {
    const token = await registerAndLogin(email);
    const caseId = await createCase(token);
    const accounts = {
        S: await createAccount(token, caseId, "AAAA1111"),
        D: await createAccount(token, caseId, "BBBB2222"),
        E: await createAccount(token, caseId, "CCCC3333"),
    };
    const docs = await Transaction.insertMany(
        defaultTxns(accounts).map((txn) => ({ ...txn, caseId }))
    );
    const byTransactionId = Object.fromEntries(docs.map((doc) => [doc.transactionId, doc]));
    return { token, caseId, accounts, byTransactionId };
}

const getAnalytics = (token, caseId, path, query = "") =>
    request(app)
        .get(`/api/v1/cases/${caseId}/analytics${path}${query}`)
        .set(bearer(token));

describe("analytics definitions (timezone + thresholds)", () => {
    test("transactionHour uses Asia/Kolkata (UTC+05:30)", () => {
        assert.equal(transactionHour(new Date("2026-01-12T17:29:00.000Z")), 22);
        assert.equal(transactionHour(new Date("2026-01-12T17:30:00.000Z")), 23);
        assert.equal(transactionHour(new Date("2026-01-12T18:30:00.000Z")), 0);
        assert.equal(transactionHour(new Date("2026-01-10T04:00:00.000Z")), 9);
    });

    test("isNightTransaction is hour >= 22 or hour < 6", () => {
        // IST boundaries: 22:00 starts the night, 06:00 ends it.
        assert.equal(isNightTransaction(new Date("2026-01-12T16:29:00.000Z")), false); // 21:59 IST
        assert.equal(isNightTransaction(new Date("2026-01-12T16:30:00.000Z")), true); // 22:00 IST
        assert.equal(isNightTransaction(new Date("2026-01-12T00:29:00.000Z")), true); // 05:59 IST
        assert.equal(isNightTransaction(new Date("2026-01-12T00:30:00.000Z")), false); // 06:00 IST
    });

    test("isHighValue uses the absolute 50000 threshold", () => {
        assert.equal(isHighValue(50000), true);
        assert.equal(isHighValue(49999.99), false);
    });
});

describe("GET /api/v1/cases/:caseId/analytics/summary", () => {
    test("returns correct counts, amounts, averages, max, range, night and high-value counts", async () => {
        const { token, caseId } = await seedFixture("alice@example.com");

        const res = await getAnalytics(token, caseId, "/summary").expect(200);
        const summary = res.body.data.summary;

        assert.equal(res.body.success, true);
        assert.equal(summary.totalTransactions, 10);
        assert.equal(summary.completedTransactions, 6);
        assert.equal(summary.pendingTransactions, 1);
        assert.equal(summary.failedTransactions, 1);
        assert.equal(summary.reversedTransactions, 1);
        assert.equal(summary.cancelledTransactions, 1);

        // COMPLETED only: 1000+2000+3000+60000+800+500
        assert.equal(summary.currency, "INR");
        assert.equal(summary.totalCompletedAmount, 67300);
        assert.equal(summary.averageCompletedAmount, 11216.67);
        assert.equal(summary.maximumCompletedAmount, 60000);
        assert.equal(summary.distinctAccountCount, 3);

        assert.equal(summary.earliestTransaction, "2026-01-10T04:00:00.000Z");
        assert.equal(summary.latestTransaction, "2026-01-14T06:00:00.000Z");

        assert.equal(summary.highValueTransactionCount, 1);
        assert.equal(summary.nightTransactionCount, 2);
        assert.equal(summary.currencyLimitation, null);
        assert.equal(summary.definitions.timezone, "Asia/Kolkata");
    });

    test("empty case returns zeroes without failing", async () => {
        const token = await registerAndLogin("alice@example.com");
        const caseId = await createCase(token);

        const res = await getAnalytics(token, caseId, "/summary").expect(200);
        const summary = res.body.data.summary;

        assert.equal(summary.totalTransactions, 0);
        assert.equal(summary.totalCompletedAmount, 0);
        assert.equal(summary.averageCompletedAmount, 0);
        assert.equal(summary.maximumCompletedAmount, null);
        assert.equal(summary.earliestTransaction, null);
        assert.equal(summary.latestTransaction, null);
        assert.equal(summary.distinctAccountCount, 0);
    });

    test("optional from/to window narrows the summary", async () => {
        const { token, caseId } = await seedFixture("alice@example.com");

        const res = await getAnalytics(
            token,
            caseId,
            "/summary",
            "?from=2026-01-12T00:00:00.000Z&to=2026-01-13T23:59:59.000Z"
        ).expect(200);
        const summary = res.body.data.summary;

        // TXN-04, TXN-10, TXN-05 completed + TXN-06 failed + TXN-07 pending
        assert.equal(summary.totalTransactions, 5);
        assert.equal(summary.completedTransactions, 3);
        assert.equal(summary.totalCompletedAmount, 61300);
        assert.equal(summary.nightTransactionCount, 2);
    });

    test("mixed currencies are never summed together", async () => {
        const token = await registerAndLogin("alice@example.com");
        const caseId = await createCase(token);
        const S = await createAccount(token, caseId, "AAAA1111");
        const D = await createAccount(token, caseId, "BBBB2222");
        await Transaction.insertMany([
            { ...row("TXN-01", S, D, 1000, "COMPLETED", "2026-03-01T04:00:00.000Z"), caseId },
            {
                ...row("TXN-02", S, D, 2000, "COMPLETED", "2026-03-02T04:00:00.000Z"),
                caseId,
                currency: "USD",
            },
        ]);

        const res = await getAnalytics(token, caseId, "/summary").expect(200);
        const summary = res.body.data.summary;

        assert.equal(summary.currency, null);
        assert.equal(summary.totalCompletedAmount, null);
        assert.equal(summary.averageCompletedAmount, null);
        assert.equal(summary.maximumCompletedAmount, null);
        assert.match(summary.currencyLimitation, /multiple|2 currencies/);
        assert.equal(summary.amountByCurrency.length, 2);
        assert.deepEqual(
            summary.amountByCurrency.map((entry) => [entry.currency, entry.totalAmount]),
            [
                ["INR", 1000],
                ["USD", 2000],
            ]
        );
    });

    test("unauthenticated -> 401, outsider -> 403, unknown/malformed case -> 404", async () => {
        const { token, caseId } = await seedFixture("alice@example.com");
        const outsiderToken = await registerAndLogin("mallory@example.com");

        await request(app).get(`/api/v1/cases/${caseId}/analytics/summary`).expect(401);
        await getAnalytics(outsiderToken, caseId, "/summary").expect(403);
        await request(app)
            .get(`/api/v1/cases/${new mongoose.Types.ObjectId()}/analytics/summary`)
            .set(bearer(token))
            .expect(404);
        await request(app)
            .get("/api/v1/cases/not-an-object-id/analytics/summary")
            .set(bearer(token))
            .expect(404);
    });

    test("a caseId supplied in the request body is rejected", async () => {
        const { token, caseId } = await seedFixture("alice@example.com");
        const otherCase = await createCase(token, "Second Case");

        const res = await request(app)
            .get(`/api/v1/cases/${caseId}/analytics/summary`)
            .set(bearer(token))
            .send({ caseId: otherCase })
            .expect(400);

        assert.deepEqual(res.body.error.details, [
            "caseId cannot be supplied; it is taken from the route",
        ]);
    });

    test("invalid from/to combinations are rejected safely", async () => {
        const { token, caseId } = await seedFixture("alice@example.com");

        const badDate = await getAnalytics(token, caseId, "/summary", "?from=yesterday").expect(400);
        assert.ok(badDate.body.error.details.includes("from must be a valid date (ISO 8601)"));

        const reversed = await getAnalytics(
            token,
            caseId,
            "/summary",
            "?from=2026-01-20T00:00:00.000Z&to=2026-01-10T00:00:00.000Z"
        ).expect(400);
        assert.ok(reversed.body.error.details.includes("from must not be after to"));
    });
});

describe("GET /api/v1/cases/:caseId/analytics/accounts/:accountId/activity", () => {
    test("separates outgoing and incoming completed activity", async () => {
        const { token, caseId, accounts } = await seedFixture("alice@example.com");

        const res = await getAnalytics(token, caseId, `/accounts/${accounts.S}/activity`).expect(200);
        const activity = res.body.data.activity;

        assert.equal(activity.account.id, accounts.S);
        assert.equal(activity.account.caseId, caseId);
        assert.equal(activity.transactionCount, 9);
        assert.equal(activity.completedOutgoingTransactions, 4); // TXN-01..04
        assert.equal(activity.completedIncomingTransactions, 1); // TXN-10
        assert.equal(activity.outgoingAmount, 66000);
        assert.equal(activity.incomingAmount, 800);
        assert.equal(activity.averageOutgoingAmount, 16500);
        assert.equal(activity.averageIncomingAmount, 800);
        assert.equal(activity.largestOutgoingTransaction, 60000);
        assert.equal(activity.largestIncomingTransaction, 800);
        assert.equal(activity.firstTransactionAt, "2026-01-10T04:00:00.000Z");
        assert.equal(activity.latestTransactionAt, "2026-01-14T06:00:00.000Z");
        assert.equal(activity.nightTransactionCount, 2);
        assert.equal(activity.highValueTransactionCount, 1);
    });

    test("outgoing and incoming roles are kept apart per account", async () => {
        const { token, caseId, accounts } = await seedFixture("alice@example.com");

        const res = await getAnalytics(token, caseId, `/accounts/${accounts.D}/activity`).expect(200);
        const activity = res.body.data.activity;

        assert.equal(activity.completedOutgoingTransactions, 1); // TXN-05
        assert.equal(activity.completedIncomingTransactions, 4); // TXN-01..04
        assert.equal(activity.outgoingAmount, 500);
        assert.equal(activity.incomingAmount, 66000);
        assert.equal(activity.largestIncomingTransaction, 60000);
    });

    test("from/to window filters account activity", async () => {
        const { token, caseId, accounts } = await seedFixture("alice@example.com");

        const res = await getAnalytics(
            token,
            caseId,
            `/accounts/${accounts.S}/activity`,
            "?from=2026-01-12T18:00:00.000Z"
        ).expect(200);
        const activity = res.body.data.activity;

        // TXN-04 (17:30Z) drops out, TXN-10 (19:00Z) stays
        assert.equal(activity.completedOutgoingTransactions, 0);
        assert.equal(activity.completedIncomingTransactions, 1);
        assert.equal(activity.outgoingAmount, 0);
        assert.equal(activity.incomingAmount, 800);
    });

    test("account from another case -> 404, malformed id -> 404", async () => {
        const alice = await seedFixture("alice@example.com");
        const bob = await seedFixture("bob@example.com");

        // bob's account id, inside alice's case -> not found (no leak)
        await getAnalytics(alice.token, alice.caseId, `/accounts/${bob.accounts.S}/activity`).expect(404);
        await getAnalytics(alice.token, alice.caseId, "/accounts/not-an-id/activity").expect(404);

        // and alice's account inside bob's case is equally unreachable
        await getAnalytics(bob.token, bob.caseId, `/accounts/${alice.accounts.S}/activity`).expect(404);
    });

    test("outsider gets 403 and unauthenticated gets 401", async () => {
        const { caseId, accounts } = await seedFixture("alice@example.com");
        const outsiderToken = await registerAndLogin("mallory@example.com");

        await request(app)
            .get(`/api/v1/cases/${caseId}/analytics/accounts/${accounts.S}/activity`)
            .expect(401);
        await getAnalytics(outsiderToken, caseId, `/accounts/${accounts.S}/activity`).expect(403);
    });
});

describe("GET /api/v1/cases/:caseId/analytics/timeline", () => {
    test("DAY buckets follow Asia/Kolkata day boundaries", async () => {
        const { token, caseId } = await seedFixture("alice@example.com");

        const res = await getAnalytics(token, caseId, "/timeline", "?interval=DAY").expect(200);
        const { buckets, interval, bucketCount } = res.body.data.timeline;

        assert.equal(interval, "DAY");
        assert.equal(bucketCount, 4);
        // 2026-01-10 IST starts at 2026-01-09T18:30Z
        assert.equal(buckets[0].start, "2026-01-09T18:30:00.000Z");
        assert.equal(buckets[0].transactionCount, 3);
        assert.equal(buckets[0].completedCount, 3);
        assert.equal(buckets[0].completedAmount, 6000);

        assert.equal(buckets[1].start, "2026-01-11T18:30:00.000Z");
        assert.equal(buckets[1].transactionCount, 1);
        assert.equal(buckets[1].completedAmount, 60000);

        // TXN-10 (2026-01-12T19:00Z) lands in the 13th IST day together with
        // TXN-05/06/07 -> proves the bucket key is local, not UTC.
        assert.equal(buckets[2].start, "2026-01-12T18:30:00.000Z");
        assert.equal(buckets[2].transactionCount, 4);
        assert.equal(buckets[2].completedCount, 2);
        assert.equal(buckets[2].completedAmount, 1300);
        assert.equal(buckets[2].failedCount, 1);

        assert.equal(buckets[3].start, "2026-01-13T18:30:00.000Z");
        assert.equal(buckets[3].transactionCount, 2);
        assert.equal(buckets[3].completedCount, 0);
        assert.equal(buckets[3].completedAmount, 0);
        assert.equal(buckets[3].reversedCount, 1);
        assert.equal(buckets[3].cancelledCount, 1);
    });

    test("HOUR buckets are finer and default to DAY when interval is omitted", async () => {
        const { token, caseId } = await seedFixture("alice@example.com");

        const hourly = await getAnalytics(token, caseId, "/timeline", "?interval=HOUR").expect(200);
        assert.equal(hourly.body.data.timeline.bucketCount, 10);
        assert.equal(hourly.body.data.timeline.buckets[0].start, "2026-01-10T03:30:00.000Z");
        assert.equal(hourly.body.data.timeline.buckets[0].completedAmount, 1000);

        const defaulted = await getAnalytics(token, caseId, "/timeline").expect(200);
        assert.equal(defaulted.body.data.timeline.interval, "DAY");
    });

    test("from/to filters the buckets", async () => {
        const { token, caseId } = await seedFixture("alice@example.com");

        const res = await getAnalytics(
            token,
            caseId,
            "/timeline",
            "?interval=DAY&from=2026-01-12T00:00:00.000Z&to=2026-01-13T23:59:59.000Z"
        ).expect(200);
        const { buckets, bucketCount, range } = res.body.data.timeline;

        assert.equal(bucketCount, 2);
        assert.equal(range.from, "2026-01-12T00:00:00.000Z");
        assert.equal(range.to, "2026-01-13T23:59:59.000Z");
        assert.equal(buckets.reduce((sum, b) => sum + b.transactionCount, 0), 5);
    });

    test("mixed currencies report per-currency bucket amounts instead of a combined total", async () => {
        const token = await registerAndLogin("alice@example.com");
        const caseId = await createCase(token);
        const S = await createAccount(token, caseId, "AAAA1111");
        const D = await createAccount(token, caseId, "BBBB2222");
        await Transaction.insertMany([
            { ...row("TXN-01", S, D, 1000, "COMPLETED", "2026-03-01T04:00:00.000Z"), caseId },
            {
                ...row("TXN-02", S, D, 2000, "COMPLETED", "2026-03-01T05:00:00.000Z"),
                caseId,
                currency: "USD",
            },
        ]);

        const res = await getAnalytics(token, caseId, "/timeline", "?interval=DAY").expect(200);
        const bucket = res.body.data.timeline.buckets[0];

        assert.equal(bucket.transactionCount, 2);
        assert.equal(bucket.completedCount, 2);
        assert.equal(bucket.completedAmount, null);
        assert.deepEqual(
            bucket.completedAmountByCurrency.map((entry) => [entry.currency, entry.total]),
            [
                ["INR", 1000],
                ["USD", 2000],
            ]
        );
        assert.match(res.body.data.timeline.currencyLimitation, /multiple currencies/);
    });

    test("interval, date and limit validation", async () => {
        const { token, caseId } = await seedFixture("alice@example.com");

        const badInterval = await getAnalytics(token, caseId, "/timeline", "?interval=WEEK").expect(400);
        assert.ok(
            badInterval.body.error.details.some((message) => message.startsWith("interval must be one of"))
        );

        await getAnalytics(token, caseId, "/timeline", "?interval=hour").expect(400);
        await getAnalytics(token, caseId, "/timeline", "?to=2026-13-45T99:00:00.000Z").expect(400);
        await getAnalytics(token, caseId, "/timeline", "?limit=0").expect(400);
        await getAnalytics(token, caseId, "/timeline", "?limit=1001").expect(400);
        await getAnalytics(token, caseId, "/timeline", "?limit=50").expect(200);
    });

    test("timeline is case-scoped: another case's transactions never appear", async () => {
        const token = await registerAndLogin("alice@example.com");
        const caseA = await createCase(token, "Case A");
        const caseB = await createCase(token, "Case B");
        const accountsA = {
            S: await createAccount(token, caseA, "AAAA1111"),
            D: await createAccount(token, caseA, "BBBB2222"),
        };
        const accountsB = {
            S: await createAccount(token, caseB, "DDDD4444"),
            D: await createAccount(token, caseB, "EEEE5555"),
        };
        await Transaction.insertMany([
            {
                ...row("TXN-01", accountsA.S, accountsA.D, 1000, "COMPLETED", "2026-04-01T04:00:00.000Z"),
                caseId: caseA,
            },
            {
                ...row("TXN-01", accountsB.S, accountsB.D, 999999, "COMPLETED", "2026-04-01T04:00:00.000Z"),
                caseId: caseB,
            },
        ]);

        const res = await getAnalytics(token, caseA, "/timeline", "?interval=DAY").expect(200);
        const bucket = res.body.data.timeline.buckets[0];

        assert.equal(res.body.data.timeline.bucketCount, 1);
        assert.equal(bucket.transactionCount, 1);
        assert.equal(bucket.completedAmount, 1000);

        // and the summary of case A must not see case B's money either
        const summary = (await getAnalytics(token, caseA, "/summary").expect(200)).body.data.summary;
        assert.equal(summary.totalCompletedAmount, 1000);
        assert.equal(summary.highValueTransactionCount, 0);
    });
});

describe("GET /api/v1/cases/:caseId/analytics/suspicious", () => {
    test("returns explainable signals ranked by rule weight, without claiming fraud", async () => {
        const { token, caseId } = await seedFixture("alice@example.com");

        const res = await getAnalytics(token, caseId, "/suspicious").expect(200);
        const suspicious = res.body.data.suspicious;

        assert.equal(suspicious.count, 2);
        const [top, second] = suspicious.signals;

        assert.equal(top.transactionId, "TXN-04");
        assert.equal(top.amount, 60000);
        assert.equal(top.riskScore, 0.85); // HIGH_VALUE + NIGHT + UNUSUAL_AMOUNT
        assert.deepEqual(top.reasons.map((reason) => reason.code), [
            "HIGH_VALUE",
            "NIGHT_TRANSACTION",
            "UNUSUAL_AMOUNT",
        ]);
        assert.deepEqual(top.reasons[0], {
            code: "HIGH_VALUE",
            label: "Transaction amount is unusually high",
            value: 60000,
        });
        assert.equal(top.reasons[1].value, 23); // IST hour
        assert.equal(second.transactionId, "TXN-10");
        assert.equal(second.riskScore, 0.15);
        assert.deepEqual(second.reasons.map((reason) => reason.code), ["NIGHT_TRANSACTION"]);

        // signals carry the ids needed for follow-up, and no fraud verdict
        assert.ok(top.id && top.sourceAccountId && top.destinationAccountId);
        assert.equal(top.fraud, undefined);
        assert.equal(top.isFraud, undefined);
        assert.match(suspicious.interpretation, /not fraud determinations/);
        assert.equal(suspicious.rules.length, 4);
        assert.equal(suspicious.analysis.completedTransactionsInCase, 6);
        assert.equal(suspicious.analysis.scannedTransactions, 6);
        assert.equal(suspicious.analysis.truncated, false);
        assert.equal(suspicious.analysis.signalledTransactions, 2);
    });

    test("HIGH_FREQUENCY fires on a burst of same-account transactions", async () => {
        const token = await registerAndLogin("alice@example.com");
        const caseId = await createCase(token);
        const S = await createAccount(token, caseId, "AAAA1111");
        const D = await createAccount(token, caseId, "BBBB2222");
        await Transaction.insertMany(
            [0, 10, 20, 30, 40].map((minutes, index) => ({
                ...row(
                    `TXN-0${index + 1}`,
                    S,
                    D,
                    100,
                    "COMPLETED",
                    new Date(Date.parse("2026-02-01T04:00:00.000Z") + minutes * 60000).toISOString()
                ),
                caseId,
            }))
        );

        const res = await getAnalytics(token, caseId, "/suspicious").expect(200);
        const { signals, count } = res.body.data.suspicious;

        assert.equal(count, 1);
        assert.equal(signals[0].transactionId, "TXN-05");
        assert.deepEqual(signals[0].reasons, [
            {
                code: "HIGH_FREQUENCY",
                label: "Unusually frequent activity for the paying account",
                value: 5,
            },
        ]);
        assert.equal(signals[0].riskScore, 0.3);
    });

    test("UNUSUAL_AMOUNT needs a baseline and compares strictly against earlier history", async () => {
        const token = await registerAndLogin("alice@example.com");
        const caseId = await createCase(token);
        const S = await createAccount(token, caseId, "AAAA1111");
        const D = await createAccount(token, caseId, "BBBB2222");
        await Transaction.insertMany([
            // stable history of 1000s, then one large outgoing payment
            { ...row("TXN-01", S, D, 1000, "COMPLETED", "2026-02-02T04:00:00.000Z"), caseId },
            { ...row("TXN-02", S, D, 1000, "COMPLETED", "2026-02-03T04:00:00.000Z"), caseId },
            { ...row("TXN-03", S, D, 1000, "COMPLETED", "2026-02-04T04:00:00.000Z"), caseId },
            { ...row("TXN-04", S, D, 4000, "COMPLETED", "2026-02-05T04:00:00.000Z"), caseId },
            // small payment arriving after the large one must not look unusual:
            // history is only ever the past, so a later small row never fires
            { ...row("TXN-05", S, D, 1200, "COMPLETED", "2026-02-06T04:00:00.000Z"), caseId },
        ]);

        const res = await getAnalytics(token, caseId, "/suspicious").expect(200);
        const { signals, count } = res.body.data.suspicious;

        assert.equal(count, 1);
        assert.equal(signals[0].transactionId, "TXN-04");
        assert.deepEqual(signals[0].reasons.map((reason) => reason.code), ["UNUSUAL_AMOUNT"]);
        assert.equal(signals[0].reasons[0].value, 4000);
    });

    test("limit and minScore narrow the dynamic result", async () => {
        const { token, caseId } = await seedFixture("alice@example.com");

        const limited = await getAnalytics(token, caseId, "/suspicious", "?limit=1").expect(200);
        assert.equal(limited.body.data.suspicious.signals.length, 1);
        assert.equal(limited.body.data.suspicious.count, 1);

        const filtered = await getAnalytics(
            token,
            caseId,
            "/suspicious",
            "?minScore=0.5"
        ).expect(200);
        assert.equal(filtered.body.data.suspicious.signals.length, 1);
        assert.equal(filtered.body.data.suspicious.signals[0].transactionId, "TXN-04");

        const none = await getAnalytics(token, caseId, "/suspicious", "?minScore=1").expect(200);
        assert.equal(none.body.data.suspicious.count, 0);
    });

    test("from/to window restricts which transactions are scanned", async () => {
        const { token, caseId } = await seedFixture("alice@example.com");

        const res = await getAnalytics(
            token,
            caseId,
            "/suspicious",
            "?from=2026-01-12T18:00:00.000Z"
        ).expect(200);
        const suspicious = res.body.data.suspicious;

        assert.equal(suspicious.analysis.completedTransactionsInCase, 2); // TXN-05, TXN-10
        assert.deepEqual(
            suspicious.signals.map((signal) => signal.transactionId),
            ["TXN-10"]
        );
    });

    test("nothing is written: risk fields stay absent in the database", async () => {
        const { token, caseId } = await seedFixture("alice@example.com");
        const beforeDocs = await Transaction.find({}).lean();
        const beforeUpdatedAt = beforeDocs.map((doc) => String(doc.updatedAt));

        await getAnalytics(token, caseId, "/suspicious").expect(200);
        await getAnalytics(token, caseId, "/summary").expect(200);
        await getAnalytics(token, caseId, "/timeline", "?interval=HOUR").expect(200);

        assert.equal(await Transaction.countDocuments({ riskScore: { $exists: true } }), 0);
        assert.equal(await Transaction.countDocuments({ riskLevel: { $exists: true } }), 0);
        assert.equal(await Transaction.countDocuments({ modelPrediction: { $exists: true } }), 0);

        const afterDocs = await Transaction.find({}).lean();
        assert.equal(afterDocs.length, beforeDocs.length);
        assert.deepEqual(afterDocs.map((doc) => String(doc.updatedAt)), beforeUpdatedAt);
    });

    test("validation: bad minScore, limit and dates -> 400", async () => {
        const { token, caseId } = await seedFixture("alice@example.com");

        await getAnalytics(token, caseId, "/suspicious", "?minScore=2").expect(400);
        await getAnalytics(token, caseId, "/suspicious", "?minScore=abc").expect(400);
        await getAnalytics(token, caseId, "/suspicious", "?limit=1001").expect(400);
        await getAnalytics(token, caseId, "/suspicious", "?limit=2.5").expect(400);
        await getAnalytics(token, caseId, "/suspicious", "?from=not-a-date").expect(400);

        const res = await getAnalytics(token, caseId, "/suspicious", "?minScore=5").expect(400);
        assert.ok(
            res.body.error.details.some((message) => message.startsWith("minScore must be a number"))
        );
    });

    test("cross-case and unauthenticated access are refused", async () => {
        const alice = await seedFixture("alice@example.com");
        const bob = await seedFixture("bob@example.com");
        const outsiderToken = await registerAndLogin("mallory@example.com");

        await request(app)
            .get(`/api/v1/cases/${alice.caseId}/analytics/suspicious`)
            .expect(401);
        await getAnalytics(outsiderToken, alice.caseId, "/suspicious").expect(403);

        // bob sees only his own case: his fixture has the same transaction ids
        const res = await getAnalytics(bob.token, bob.caseId, "/suspicious").expect(200);
        const bobAccountIds = Object.values(bob.accounts).map(String);
        assert.equal(res.body.data.suspicious.count, 2);
        for (const signal of res.body.data.suspicious.signals) {
            assert.ok(bobAccountIds.includes(signal.sourceAccountId));
            assert.ok(bobAccountIds.includes(signal.destinationAccountId));
        }

        // alice's own signals reference her accounts, never bob's
        const aliceRes = await getAnalytics(alice.token, alice.caseId, "/suspicious").expect(200);
        for (const signal of aliceRes.body.data.suspicious.signals) {
            assert.ok(!bobAccountIds.includes(signal.sourceAccountId));
        }
    });
});

describe("analytics routing and read-only surface", () => {
    test("analytics only exists under a case and accepts GET", async () => {
        const { token, caseId } = await seedFixture("alice@example.com");

        await getAnalytics(token, caseId, "/unknown-endpoint").expect(404);
        await request(app)
            .post(`/api/v1/cases/${caseId}/analytics/summary`)
            .set(bearer(token))
            .send({})
            .expect(404);
        await request(app).get("/api/v1/analytics/summary").set(bearer(token)).expect(404);
    });
});

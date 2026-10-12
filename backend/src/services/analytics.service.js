import mongoose from "mongoose";
import Transaction from "../models/Transaction.js";
import Account from "../models/Account.js";
import ApiError from "../utils/ApiError.js";
import { getAccessibleCaseDoc } from "./case.service.js";

/**
 * Read-only financial analytics for one case (Milestone 7A).
 *
 * Nothing here writes to the database: the analytics layer only reads
 * transactions that already belong to the authorized case. Risk fields
 * (riskScore/riskLevel/modelPrediction) are NOT persisted in this milestone -
 * the suspicious endpoint is calculated dynamically on every request.
 *
 * Analysis conventions (returned with every response so results are
 * interpretable without reading this file):
 *  - amounts and behavioral statistics use COMPLETED transactions only, so
 *    FAILED / REVERSED / CANCELLED / PENDING rows never inflate moved money;
 *  - counts that describe the case as a whole (status counts, date range,
 *    transaction count, involved accounts) use every status;
 *  - transactionHour / isNightTransaction use the configured investigation
 *    timezone (default Asia/Kolkata); the stored timestamps stay in UTC;
 *  - isHighValue uses the explainable absolute threshold for this milestone
 *    (the later ML milestone replaces it with a per-account relative one);
 *  - amounts are never summed across currencies.
 */

const REQUESTED_TIME_ZONE = process.env.ANALYTICS_TIMEZONE || "Asia/Kolkata";

function resolveTimeZone(candidate) {
    try {
        new Intl.DateTimeFormat("en-GB", { timeZone: candidate });
        return candidate;
    } catch {
        // An unusable env value must not break analytics: fall back to the
        // documented default instead of throwing at request time.
        return "Asia/Kolkata";
    }
}

export const ANALYTICS_TIME_ZONE = resolveTimeZone(REQUESTED_TIME_ZONE);

const HIGH_VALUE_THRESHOLD = Number(process.env.ANALYTICS_HIGH_VALUE_THRESHOLD) || 50000;
const FREQUENCY_WINDOW_MINUTES = 60;
const FREQUENCY_TRANSACTION_THRESHOLD = 5;
const UNUSUAL_AMOUNT_MULTIPLIER = 3;
const UNUSUAL_AMOUNT_MIN_BASELINE = 3;

// Upper bound on rows pulled for the dynamic suspicious-signal scan. Cases
// larger than this are analysed over their most recent transactions and the
// response says so explicitly (never silently partial).
const MAX_SCAN_TRANSACTIONS = Number(process.env.ANALYTICS_MAX_SCAN_TRANSACTIONS) || 5000;

const NIGHT_HOURS_LABEL = "hour >= 22 or hour < 6";

const FREQUENCY_CONDITION =
    `>= ${FREQUENCY_TRANSACTION_THRESHOLD} completed transactions by the source account ` +
    `within ${FREQUENCY_WINDOW_MINUTES} minutes (including this one)`;

const UNUSUAL_AMOUNT_CONDITION =
    `amount >= ${UNUSUAL_AMOUNT_MULTIPLIER}x the source account's previous average ` +
    `(requires >= ${UNUSUAL_AMOUNT_MIN_BASELINE} prior transactions in the same currency)`;

const SIGNAL_RULES = [
    {
        code: "HIGH_VALUE",
        label: "Transaction amount is unusually high",
        condition: `amount >= ${HIGH_VALUE_THRESHOLD}`,
        weight: 0.35,
    },
    {
        code: "NIGHT_TRANSACTION",
        label: "Transaction occurred during night hours",
        condition: `${NIGHT_HOURS_LABEL} (${ANALYTICS_TIME_ZONE})`,
        weight: 0.15,
    },
    {
        code: "HIGH_FREQUENCY",
        label: "Unusually frequent activity for the paying account",
        condition: FREQUENCY_CONDITION,
        weight: 0.3,
    },
    {
        code: "UNUSUAL_AMOUNT",
        label: "Amount far exceeds the paying account's previous average",
        condition: UNUSUAL_AMOUNT_CONDITION,
        weight: 0.35,
    },
];

const SIGNAL_DISCLAIMER =
    "These are investigation signals produced by explainable rules, not fraud determinations. " +
    "A score never replaces investigator review.";

const oid = (value) => new mongoose.Types.ObjectId(value);

const round2 = (value) => Math.round((Number(value) + Number.EPSILON) * 100) / 100;

const hourFormatter = new Intl.DateTimeFormat("en-GB", {
    timeZone: ANALYTICS_TIME_ZONE,
    hour: "2-digit",
    hourCycle: "h23",
});

/** Hour 0-23 in the investigation timezone (isNightTransaction: >= 22 or < 6). */
export function transactionHour(date) {
    const part = hourFormatter.formatToParts(date).find((p) => p.type === "hour");
    return Number.parseInt(part.value, 10);
}

export function isNightTransaction(date) {
    const hour = transactionHour(date);
    return hour >= 22 || hour < 6;
}

export function isHighValue(amount) {
    return Number(amount) >= HIGH_VALUE_THRESHOLD;
}

function rangeMatch(from, to) {
    if (!from && !to) return null;
    const range = {};
    if (from) range.$gte = from;
    if (to) range.$lte = to;
    return range;
}

// Aggregation output order is not guaranteed, so per-currency breakdowns are
// always sorted by currency code - stable responses are testable responses.
const byCurrencyCode = (a, b) => String(a.currency).localeCompare(String(b.currency));

/**
 * Amount statistics that refuse to add incompatible currencies together.
 * One currency -> flat totals; several -> flat totals stay null and the caller
 * exposes amountByCurrency plus an explicit currencyLimitation instead.
 */
function buildAmountStats(rows, { countKey, totalKey, maxKey }) {
    const sorted = [...rows].sort(byCurrencyCode);
    const currencies = sorted.map((row) => row.currency).filter(Boolean);

    if (currencies.length > 1) {
        return {
            currency: null,
            totalAmount: null,
            averageAmount: null,
            maximumAmount: null,
            amountByCurrency: sorted.map((row) => ({
                currency: row.currency,
                completedTransactions: row[countKey] || 0,
                totalAmount: round2(row[totalKey] || 0),
                averageAmount: row[countKey] ? round2((row[totalKey] || 0) / row[countKey]) : 0,
                maximumAmount: round2(row[maxKey] || 0),
            })),
            currencyLimitation:
                `This case contains ${currencies.length} currencies (${currencies.join(", ")}); ` +
                "amounts are reported per currency instead of a combined total.",
        };
    }

    const totalAmount = sorted.reduce((sum, row) => sum + (row[totalKey] || 0), 0);
    const totalCount = sorted.reduce((sum, row) => sum + (row[countKey] || 0), 0);
    const maximum = sorted.reduce((max, row) => Math.max(max, row[maxKey] ?? 0), 0);

    return {
        currency: currencies[0] || null,
        totalAmount: round2(totalAmount),
        averageAmount: totalCount ? round2(totalAmount / totalCount) : 0,
        maximumAmount: totalCount ? round2(maximum) : null,
        amountByCurrency: null,
        currencyLimitation: null,
    };
}

function definitionsBlock(extra = {}) {
    return {
        timezone: ANALYTICS_TIME_ZONE,
        nightHours: NIGHT_HOURS_LABEL,
        highValueThreshold: HIGH_VALUE_THRESHOLD,
        amountStatisticsBasis: "COMPLETED transactions only",
        ...extra,
    };
}

/**
 * A. Case summary.
 * @throws {ApiError} 404 unknown/malformed case, 403 non-participant
 */
export async function getCaseSummary(authenticatedUser, caseId, { from, to } = {}) {
    await getAccessibleCaseDoc(authenticatedUser, caseId);

    const match = { caseId: oid(caseId) };
    const range = rangeMatch(from, to);
    if (range) match.timestamp = range;

    const [statusRows, currencyRows, sourceAccounts, destinationAccounts] = await Promise.all([
        Transaction.aggregate([
            { $match: match },
            {
                $group: {
                    _id: "$status",
                    count: { $sum: 1 },
                    earliestTransaction: { $min: "$timestamp" },
                    latestTransaction: { $max: "$timestamp" },
                },
            },
        ]),
        Transaction.aggregate([
            { $match: { ...match, status: "COMPLETED" } },
            { $addFields: { hour: { $hour: { date: "$timestamp", timezone: ANALYTICS_TIME_ZONE } } } },
            {
                $group: {
                    _id: "$currency",
                    completedCount: { $sum: 1 },
                    totalAmount: { $sum: "$amount" },
                    maximumAmount: { $max: "$amount" },
                    highValueCount: {
                        $sum: { $cond: [{ $gte: ["$amount", HIGH_VALUE_THRESHOLD] }, 1, 0] },
                    },
                    nightCount: {
                        $sum: {
                            $cond: [{ $or: [{ $gte: ["$hour", 22] }, { $lt: ["$hour", 6] }] }, 1, 0],
                        },
                    },
                },
            },
        ]),
        Transaction.distinct("sourceAccountId", match),
        Transaction.distinct("destinationAccountId", match),
    ]);

    const byStatus = Object.fromEntries(statusRows.map((row) => [row._id ?? "UNKNOWN", row.count]));
    const totals = statusRows.reduce((sum, row) => sum + row.count, 0);
    const earliestCandidates = statusRows.map((row) => row.earliestTransaction).filter(Boolean);
    const latestCandidates = statusRows.map((row) => row.latestTransaction).filter(Boolean);

    const amounts = buildAmountStats(
        currencyRows.map((row) => ({
            currency: row._id,
            completedCount: row.completedCount,
            totalAmount: row.totalAmount,
            maximumAmount: row.maximumAmount,
        })),
        { countKey: "completedCount", totalKey: "totalAmount", maxKey: "maximumAmount" }
    );

    return {
        caseId,
        range: { from: from || null, to: to || null },
        totalTransactions: totals,
        completedTransactions: byStatus.COMPLETED || 0,
        pendingTransactions: byStatus.PENDING || 0,
        failedTransactions: byStatus.FAILED || 0,
        reversedTransactions: byStatus.REVERSED || 0,
        cancelledTransactions: byStatus.CANCELLED || 0,
        currency: amounts.currency,
        totalCompletedAmount: amounts.totalAmount,
        averageCompletedAmount: amounts.averageAmount,
        maximumCompletedAmount: amounts.maximumAmount,
        amountByCurrency: amounts.amountByCurrency,
        currencyLimitation: amounts.currencyLimitation,
        distinctAccountCount: new Set([
            ...sourceAccounts.map(String),
            ...destinationAccounts.map(String),
        ]).size,
        earliestTransaction: earliestCandidates.length
            ? new Date(Math.min(...earliestCandidates.map((d) => d.getTime())))
            : null,
        latestTransaction: latestCandidates.length
            ? new Date(Math.max(...latestCandidates.map((d) => d.getTime())))
            : null,
        highValueTransactionCount: currencyRows.reduce((sum, row) => sum + row.highValueCount, 0),
        nightTransactionCount: currencyRows.reduce((sum, row) => sum + row.nightCount, 0),
        definitions: definitionsBlock(),
    };
}

/** B. Account activity. The account must belong to the requested case. */
export async function getAccountActivity(authenticatedUser, caseId, accountId, { from, to } = {}) {
    await getAccessibleCaseDoc(authenticatedUser, caseId);

    const account = await Account.findOne({ _id: accountId, caseId });
    if (!account) {
        throw new ApiError(404, "Account not found in this case");
    }

    const accountOid = oid(account._id);
    const match = {
        caseId: oid(caseId),
        $or: [{ sourceAccountId: accountOid }, { destinationAccountId: accountOid }],
    };
    const range = rangeMatch(from, to);
    if (range) match.timestamp = range;

    const rows = await Transaction.aggregate([
        { $match: match },
        {
            $addFields: {
                hour: { $hour: { date: "$timestamp", timezone: ANALYTICS_TIME_ZONE } },
                direction: { $cond: [{ $eq: ["$sourceAccountId", accountOid] }, "OUT", "IN"] },
            },
        },
        {
            $group: {
                _id: { direction: "$direction", status: "$status", currency: "$currency" },
                count: { $sum: 1 },
                totalAmount: { $sum: "$amount" },
                maximumAmount: { $max: "$amount" },
                nightCount: {
                    $sum: { $cond: [{ $or: [{ $gte: ["$hour", 22] }, { $lt: ["$hour", 6] }] }, 1, 0] },
                },
                highValueCount: {
                    $sum: { $cond: [{ $gte: ["$amount", HIGH_VALUE_THRESHOLD] }, 1, 0] },
                },
                firstTransactionAt: { $min: "$timestamp" },
                latestTransactionAt: { $max: "$timestamp" },
            },
        },
    ]);

    const completed = rows.filter((row) => row._id.status === "COMPLETED");
    const side = (direction) =>
        completed
            .filter((row) => row._id.direction === direction)
            .map((row) => ({
                currency: row._id.currency,
                completedCount: row.count,
                totalAmount: row.totalAmount,
                maximumAmount: row.maximumAmount,
            }));

    const outgoingAmounts = buildAmountStats(side("OUT"), {
        countKey: "completedCount",
        totalKey: "totalAmount",
        maxKey: "maximumAmount",
    });
    const incomingAmounts = buildAmountStats(side("IN"), {
        countKey: "completedCount",
        totalKey: "totalAmount",
        maxKey: "maximumAmount",
    });

    const allTimestamps = rows.map((row) => row.firstTransactionAt).filter(Boolean);
    const lastTimestamps = rows.map((row) => row.latestTransactionAt).filter(Boolean);
    const countFor = (predicate) => rows.filter(predicate).reduce((sum, row) => sum + row.count, 0);

    return {
        caseId,
        account: account.toJSON(),
        range: { from: from || null, to: to || null },
        transactionCount: rows.reduce((sum, row) => sum + row.count, 0),
        completedOutgoingTransactions: countFor(
            (row) => row._id.direction === "OUT" && row._id.status === "COMPLETED"
        ),
        completedIncomingTransactions: countFor(
            (row) => row._id.direction === "IN" && row._id.status === "COMPLETED"
        ),
        outgoingAmount: outgoingAmounts.totalAmount,
        incomingAmount: incomingAmounts.totalAmount,
        averageOutgoingAmount: outgoingAmounts.averageAmount,
        averageIncomingAmount: incomingAmounts.averageAmount,
        largestOutgoingTransaction: outgoingAmounts.maximumAmount,
        largestIncomingTransaction: incomingAmounts.maximumAmount,
        outgoingCurrency: outgoingAmounts.currency,
        incomingCurrency: incomingAmounts.currency,
        outgoingAmountByCurrency: outgoingAmounts.amountByCurrency,
        incomingAmountByCurrency: incomingAmounts.amountByCurrency,
        currencyLimitation:
            [outgoingAmounts.currencyLimitation, incomingAmounts.currencyLimitation]
                .filter(Boolean)
                .join(" ") || null,
        firstTransactionAt: allTimestamps.length
            ? new Date(Math.min(...allTimestamps.map((d) => d.getTime())))
            : null,
        latestTransactionAt: lastTimestamps.length
            ? new Date(Math.max(...lastTimestamps.map((d) => d.getTime())))
            : null,
        nightTransactionCount: completed.reduce((sum, row) => sum + row.nightCount, 0),
        highValueTransactionCount: completed.reduce((sum, row) => sum + row.highValueCount, 0),
        definitions: definitionsBlock({
            directionBasis: "OUT = account is the source (paying); IN = account is the destination",
            firstAndLatestTransactionBasis: "all statuses",
        }),
    };
}

/** C. Bucketed timeline. interval = DAY | HOUR. */
export async function getTimeline(authenticatedUser, caseId, { interval = "DAY", from, to } = {}) {
    await getAccessibleCaseDoc(authenticatedUser, caseId);

    const match = { caseId: oid(caseId) };
    const range = rangeMatch(from, to);
    if (range) match.timestamp = range;

    const format = interval === "HOUR" ? "%Y-%m-%dT%H:00:00" : "%Y-%m-%dT00:00:00";

    const buckets = await Transaction.aggregate([
        { $match: match },
        {
            $addFields: {
                bucket: { $dateToString: { date: "$timestamp", timezone: ANALYTICS_TIME_ZONE, format } },
            },
        },
        {
            $group: {
                _id: { bucket: "$bucket", currency: "$currency" },
                transactionCount: { $sum: 1 },
                completedCount: { $sum: { $cond: [{ $eq: ["$status", "COMPLETED"] }, 1, 0] } },
                pendingCount: { $sum: { $cond: [{ $eq: ["$status", "PENDING"] }, 1, 0] } },
                failedCount: { $sum: { $cond: [{ $eq: ["$status", "FAILED"] }, 1, 0] } },
                reversedCount: { $sum: { $cond: [{ $eq: ["$status", "REVERSED"] }, 1, 0] } },
                cancelledCount: { $sum: { $cond: [{ $eq: ["$status", "CANCELLED"] }, 1, 0] } },
                completedAmount: {
                    $sum: { $cond: [{ $eq: ["$status", "COMPLETED"] }, "$amount", 0] },
                },
            },
        },
        {
            $group: {
                _id: "$_id.bucket",
                transactionCount: { $sum: "$transactionCount" },
                completedCount: { $sum: "$completedCount" },
                pendingCount: { $sum: "$pendingCount" },
                failedCount: { $sum: "$failedCount" },
                reversedCount: { $sum: "$reversedCount" },
                cancelledCount: { $sum: "$cancelledCount" },
                currencies: {
                    $push: {
                        currency: "$_id.currency",
                        completedAmount: {
                            $cond: [{ $gt: ["$completedCount", 0] }, "$completedAmount", null],
                        },
                    },
                },
            },
        },
        { $sort: { _id: 1 } },
        {
            $project: {
                _id: 0,
                start: {
                    $dateFromString: { dateString: "$_id", timezone: ANALYTICS_TIME_ZONE, format: "%Y-%m-%dT%H:%M:%S" },
                },
                transactionCount: 1,
                completedCount: 1,
                pendingCount: 1,
                failedCount: 1,
                reversedCount: 1,
                cancelledCount: 1,
                currencies: 1,
            },
        },
    ]);

    const multiCurrency = buckets.some((bucket) => bucket.currencies.length > 1);

    const timeline = buckets.map((entry) => {
        const amounts = entry.currencies
            .filter((item) => item.completedAmount !== null)
            .sort(byCurrencyCode);
        return {
            start: entry.start,
            interval,
            transactionCount: entry.transactionCount,
            completedCount: entry.completedCount,
            pendingCount: entry.pendingCount,
            failedCount: entry.failedCount,
            reversedCount: entry.reversedCount,
            cancelledCount: entry.cancelledCount,
            // Never summed across currencies: null with a per-currency breakdown.
            completedAmount:
                amounts.length === 0 ? 0 : amounts.length === 1 ? round2(amounts[0].completedAmount) : null,
            completedAmountByCurrency:
                amounts.length > 1
                    ? amounts.map((entry) => ({ currency: entry.currency, total: round2(entry.completedAmount) }))
                    : null,
        };
    });

    return {
        caseId,
        interval,
        range: { from: from || null, to: to || null },
        bucketCount: timeline.length,
        buckets: timeline,
        currencyLimitation: multiCurrency
            ? "This case contains multiple currencies; completedAmount is reported per currency, never combined."
            : null,
        definitions: definitionsBlock({
            bucketBasis: `buckets start at local midnight/hour in ${ANALYTICS_TIME_ZONE}; a bucket groups every status`,
        }),
    };
}

/**
 * D. Rule-based suspicious transaction signals.
 * Deterministic, explainable and computed on request - nothing is written.
 */
export async function getSuspiciousTransactions(
    authenticatedUser,
    caseId,
    { from, to, limit = 50, minScore } = {}
) {
    await getAccessibleCaseDoc(authenticatedUser, caseId);

    const match = { caseId: oid(caseId), status: "COMPLETED" };
    const range = rangeMatch(from, to);
    if (range) match.timestamp = range;

    const completedTotal = await Transaction.countDocuments(match);

    // Most recent slice, analysed in ascending order so baselines stay causal.
    const transactions = await Transaction.find(match)
        .sort({ timestamp: -1, _id: -1 })
        .limit(Math.min(MAX_SCAN_TRANSACTIONS, completedTotal))
        .lean();
    transactions.reverse();

    // Per paying-account, per-currency state: recent timestamps for the
    // frequency window plus the history that forms the amount baseline.
    const history = new Map();

    const signals = [];

    for (const txn of transactions) {
        const key = `${String(txn.sourceAccountId)}|${txn.currency}`;
        let state = history.get(key);
        if (!state) {
            state = { recent: [], priorCount: 0, priorSum: 0 };
            history.set(key, state);
        }

        const hour = transactionHour(txn.timestamp);
        const reasons = [];
        let score = 0;

        const addReason = (code, value) => {
            const rule = SIGNAL_RULES.find((entry) => entry.code === code);
            reasons.push({ code, label: rule.label, value });
            score += rule.weight;
        };

        if (isHighValue(txn.amount)) {
            addReason("HIGH_VALUE", round2(txn.amount));
        }

        if (hour >= 22 || hour < 6) {
            addReason("NIGHT_TRANSACTION", hour);
        }

        // Frequency window: prior completed transactions of this account (in
        // the same currency) within the last hour, plus the current one.
        const cutoff = new Date(txn.timestamp.getTime() - FREQUENCY_WINDOW_MINUTES * 60 * 1000);
        while (state.recent.length && state.recent[0] < cutoff) state.recent.shift();
        const windowCount = state.recent.length + 1;
        if (windowCount >= FREQUENCY_TRANSACTION_THRESHOLD) {
            addReason("HIGH_FREQUENCY", windowCount);
        }

        const previousAverage = state.priorCount > 0 ? state.priorSum / state.priorCount : 0;
        if (
            state.priorCount >= UNUSUAL_AMOUNT_MIN_BASELINE &&
            previousAverage > 0 &&
            txn.amount >= UNUSUAL_AMOUNT_MULTIPLIER * previousAverage
        ) {
            addReason("UNUSUAL_AMOUNT", round2(txn.amount));
        }

        // Only now does this transaction become part of the history for later
        // rows - guarantees every comparison looks strictly backwards.
        state.recent.push(txn.timestamp);
        state.priorCount += 1;
        state.priorSum += txn.amount;

        if (reasons.length === 0) continue;

        signals.push({
            id: txn._id.toString(),
            transactionId: txn.transactionId,
            timestamp: txn.timestamp,
            amount: round2(txn.amount),
            currency: txn.currency,
            transactionType: txn.transactionType,
            sourceAccountId: txn.sourceAccountId.toString(),
            destinationAccountId: txn.destinationAccountId.toString(),
            riskScore: round2(Math.min(1, score)),
            reasons,
        });
    }

    const filtered =
        minScore === undefined ? signals : signals.filter((row) => row.riskScore >= minScore);

    const ranked = filtered
        .sort((a, b) => b.riskScore - a.riskScore || b.timestamp - a.timestamp)
        .slice(0, limit);

    const currencies = new Set(transactions.map((txn) => txn.currency));

    return {
        caseId,
        range: { from: from || null, to: to || null },
        count: ranked.length,
        signals: ranked,
        analysis: {
            completedTransactionsInCase: completedTotal,
            scannedTransactions: transactions.length,
            signalledTransactions: filtered.length,
            truncated: completedTotal > transactions.length,
            basis: "COMPLETED transactions only; frequency and amount history use the source (paying) account",
        },
        rules: SIGNAL_RULES,
        interpretation: SIGNAL_DISCLAIMER,
        currencyNote:
            currencies.size > 1
                ? `The case contains ${currencies.size} currencies; baselines are kept per currency, but ` +
                  `HIGH_VALUE applies the single absolute threshold to every currency.`
                : null,
        definitions: definitionsBlock({
            riskScoreBasis: "sum of the matched rule weights, capped at 1; an ordering aid, not a probability",
        }),
    };
}

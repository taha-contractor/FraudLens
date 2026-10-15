import { useCallback, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { analytics, transactions as txApi, risk as riskApi } from "../api/endpoints.js";
import { useCases } from "../context/CaseContext.jsx";
import { useAsync } from "../hooks/useAsync.js";
import { NeedCase } from "../components/NeedCase.jsx";
import { Spinner } from "../components/LoadingState.jsx";
import { ErrorState } from "../components/ErrorState.jsx";
import { EmptyState } from "../components/EmptyState.jsx";
import { StatCard, RiskBadge, StatusBadge } from "../components/ui.jsx";
import { ActivityAreaChart, RiskPieChart } from "../components/charts.jsx";
import { formatAmount, formatCompactAmount, formatDateTime, shortId } from "../utils/format.js";

// Bounded sample used for the on-page risk distribution and review queue.
// Cases are bounded investigation working sets; we never load millions.
const SAMPLE_LIMIT = 500;

export default function Dashboard() {
    const { activeCase, activeCaseId } = useCases();
    const [assessing, setAssessing] = useState(false);
    const [assessMsg, setAssessMsg] = useState(null);

    const fetcher = useCallback(async () => {
        if (!activeCaseId) return null;
        const [summary, timeline, page, model] = await Promise.all([
            analytics.summary(activeCaseId),
            analytics.timeline(activeCaseId, { interval: "DAY" }),
            txApi.list(activeCaseId, { limit: SAMPLE_LIMIT }),
            riskApi.modelInfo().catch(() => ({ available: false })),
        ]);
        return {
            total: summary.summary,
            timeline: timeline.timeline,
            txns: page.transactions,
            model,
        };
    }, [activeCaseId]);

    const { data, loading, error, reload } = useAsync(fetcher, [activeCaseId]);

    const derived = useMemo(() => {
        if (!data) return null;
        const txns = data.txns || [];
        const dist = { HIGH: 0, MEDIUM: 0, LOW: 0, "Not assessed": 0 };
        for (const t of txns) {
            if (t.riskLevel && dist[t.riskLevel] !== undefined) dist[t.riskLevel] += 1;
            else dist["Not assessed"] += 1;
        }
        const highRisk = txns.filter((t) => t.riskLevel === "HIGH");
        const reviewQueue = txns
            .filter((t) => t.riskLevel === "HIGH" || t.riskLevel === "MEDIUM")
            .sort((a, b) => (b.riskScore || 0) - (a.riskScore || 0))
            .slice(0, 8);
        const recent = txns.slice(0, 8);
        return {
            dist,
            highRisk,
            reviewQueue,
            recent,
            sampled: txns.length,
            pieData: Object.entries(dist)
                .filter(([, v]) => v > 0)
                .map(([name, value]) => ({ name, value })),
        };
    }, [data]);

    async function assessCase() {
        setAssessing(true);
        setAssessMsg(null);
        try {
            const res = await riskApi.assessCase(activeCaseId, {});
            setAssessMsg(
                `Scored ${res.scored}, unscored ${res.unscored}, skipped (already assessed) ${res.skipped}.`
            );
            await reload();
        } catch (err) {
            setAssessMsg(err?.response?.data?.error?.message || "Assessment failed");
        } finally {
            setAssessing(false);
        }
    }

    if (!activeCaseId) return <NeedCase />;

    if (loading && !data) return <Spinner label="Loading case overview…" />;
    if (error) return <ErrorState message={error} onRetry={reload} />;
    if (!data) return null;

    const s = data.total;
    const threshold = data.model?.model?.threshold ?? 0.95;
    const buckets = (data.timeline?.buckets || []).map((b) => ({
        label: new Date(b.start).toLocaleDateString("en-GB", { day: "2-digit", month: "short" }),
        transactionCount: b.transactionCount,
    }));
    const anyScored = derived.dist.HIGH + derived.dist.MEDIUM + derived.dist.LOW > 0;

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex flex-wrap items-end justify-between gap-3">
                <div>
                    <h1 className="text-xl font-semibold">{activeCase?.title || "Case dashboard"}</h1>
                    <p className="text-sm text-mist-500">
                        {activeCase?.caseNumber} · status{" "}
                        <span className="text-mist-300">
                            {(activeCase?.status || "").replace(/_/g, " ").toLowerCase()}
                        </span>
                    </p>
                </div>
                <div className="flex items-center gap-2">
                    {data.model?.available ? (
                        <span className="badge bg-emerald-500/15 text-emerald-400">
                            Model live · {data.model.model.winner_id} · thr {threshold}
                        </span>
                    ) : (
                        <span className="badge bg-amber-500/15 text-amber-400">Model offline</span>
                    )}
                    <button type="button" className="btn-primary" onClick={assessCase} disabled={assessing}>
                        {assessing ? "Assessing…" : "Assess case risk"}
                    </button>
                </div>
            </div>

            {assessMsg && (
                <p className="rounded-lg border border-ink-700 bg-ink-850 px-3 py-2 text-sm text-mist-300">
                    {assessMsg}
                    <Link to="/transactions" className="ml-2 text-signal-500 hover:underline">
                        View transactions →
                    </Link>
                </p>
            )}

            {/* Count cards */}
            <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
                <StatCard label="Transactions" value={s.totalTransactions} sub={`${s.distinctAccountCount} accounts involved`} />
                <StatCard
                    label="Completed amount"
                    value={s.totalCompletedAmount !== null ? formatCompactAmount(s.totalCompletedAmount, s.currency) : "multi-currency"}
                    sub={s.totalCompletedAmount !== null ? `avg ${formatCompactAmount(s.averageCompletedAmount, s.currency)}` : "see analytics"}
                    tone="signal"
                />
                <StatCard label="High risk" value={derived.dist.HIGH} sub={`of ${derived.sampled} recent (≥ ${threshold})`} tone="danger" />
                <StatCard label="Not assessed" value={derived.dist["Not assessed"]} sub="run case assessment" tone={derived.dist["Not assessed"] ? "warn" : "default"} />
            </div>

            <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
                {/* Activity over time */}
                <div className="card lg:col-span-2">
                    <p className="card-title">Activity over time (daily)</p>
                    {buckets.length ? (
                        <ActivityAreaChart data={buckets} />
                    ) : (
                        <EmptyState title="No activity yet" message="This case has no transactions to chart." />
                    )}
                </div>

                {/* Risk distribution */}
                <div className="card">
                    <p className="card-title">Risk distribution</p>
                    {anyScored ? (
                        <>
                            <RiskPieChart data={derived.pieData} />
                            <p className="mt-2 text-center text-[11px] text-mist-500">
                                Across the {derived.sampled} most recent transactions
                            </p>
                        </>
                    ) : (
                        <EmptyState
                            title="No scores yet"
                            message="Assess the case to populate risk levels."
                        />
                    )}
                </div>
            </div>

            <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
                {/* Review queue */}
                <div className="card">
                    <div className="card-title flex items-center justify-between">
                        <span>Review queue</span>
                        <Link to="/transactions" className="text-[11px] normal-case text-signal-500 hover:underline">
                            open explorer
                        </Link>
                    </div>
                    {derived.reviewQueue.length ? (
                        <ul className="divide-y divide-ink-800">
                            {derived.reviewQueue.map((t) => (
                                <li key={t.id} className="flex items-center justify-between gap-3 py-2">
                                    <div className="min-w-0">
                                        <Link to={`/transactions/${t.id}?case=${activeCaseId}`} className="text-sm font-medium text-signal-500 hover:underline">
                                            {t.transactionId}
                                        </Link>
                                        <p className="truncate text-xs text-mist-500">
                                            {formatAmount(t.amount, t.currency)} · {shortId(t.sourceAccountId)}
                                        </p>
                                    </div>
                                    <RiskBadge level={t.riskLevel} score={t.riskScore} />
                                </li>
                            ))}
                        </ul>
                    ) : (
                        <EmptyState title="Queue is clear" message="No HIGH or MEDIUM transactions in the recent sample." />
                    )}
                </div>

                {/* Recent activity */}
                <div className="card">
                    <div className="card-title flex items-center justify-between">
                        <span>Recent transactions</span>
                        <span className="text-[11px] normal-case text-mist-500">
                            {formatDateTime(s.latestTransaction)}
                        </span>
                    </div>
                    {derived.recent.length ? (
                        <ul className="divide-y divide-ink-800">
                            {derived.recent.map((t) => (
                                <li key={t.id} className="flex items-center justify-between gap-3 py-2">
                                    <div className="min-w-0">
                                        <Link to={`/transactions/${t.id}?case=${activeCaseId}`} className="text-sm font-medium text-mist-100 hover:text-signal-500">
                                            {t.transactionId}
                                        </Link>
                                        <p className="truncate text-xs text-mist-500">
                                            {t.transactionType} · {formatDateTime(t.timestamp)}
                                        </p>
                                    </div>
                                    <div className="flex items-center gap-3">
                                        <StatusBadge status={t.status} />
                                        <span className="w-28 text-right text-sm tabular-nums">
                                            {formatAmount(t.amount, t.currency)}
                                        </span>
                                    </div>
                                </li>
                            ))}
                        </ul>
                    ) : (
                        <EmptyState title="No transactions" message="Add or import transactions to this case." />
                    )}
                </div>
            </div>

            <p className="text-xs text-mist-500">
                Definitions: night/high-value thresholds and timezone follow the analytics layer
                (high-value ≥ {formatAmount(s.definitions?.highValueThreshold)}, {s.definitions?.timezone}).
                Amounts use COMPLETED transactions only and are never summed across currencies.
            </p>
        </div>
    );
}

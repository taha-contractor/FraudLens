import { useCallback, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { analytics } from "../api/endpoints.js";
import { useCases } from "../context/CaseContext.jsx";
import { useAsync } from "../hooks/useAsync.js";
import { NeedCase } from "../components/NeedCase.jsx";
import { Spinner } from "../components/LoadingState.jsx";
import { ErrorState } from "../components/ErrorState.jsx";
import { EmptyState } from "../components/EmptyState.jsx";
import { StatCard } from "../components/ui.jsx";
import { ActivityAreaChart, AmountBarChart } from "../components/charts.jsx";
import { formatAmount, formatDateTime, formatPercent } from "../utils/format.js";

export default function Analytics() {
    const { activeCaseId } = useCases();
    const [interval, setInterval_] = useState("DAY");

    const fetcher = useCallback(async () => {
        if (!activeCaseId) return null;
        const [summary, timeline, suspicious] = await Promise.all([
            analytics.summary(activeCaseId),
            analytics.timeline(activeCaseId, { interval }),
            analytics.suspicious(activeCaseId, { limit: 25 }),
        ]);
        return { summary: summary.summary, timeline: timeline.timeline, suspicious: suspicious.suspicious };
    }, [activeCaseId, interval]);

    const { data, loading, error, reload } = useAsync(fetcher, [activeCaseId, interval]);

    const chart = useMemo(() => {
        if (!data) return { counts: [], amounts: [] };
        const fmt = (start) =>
            new Date(start).toLocaleDateString("en-GB",
                interval === "HOUR"
                    ? { day: "2-digit", month: "short", hour: "2-digit" }
                    : { day: "2-digit", month: "short" });
        const buckets = data.timeline.buckets || [];
        return {
            counts: buckets.map((b) => ({ label: fmt(b.start), transactionCount: b.transactionCount })),
            amounts: buckets
                .filter((b) => b.completedAmount !== null)
                .map((b) => ({ label: fmt(b.start), value: b.completedAmount })),
        };
    }, [data, interval]);

    if (!activeCaseId) return <NeedCase />;
    if (loading && !data) return <Spinner label="Crunching analytics…" />;
    if (error) return <ErrorState message={error} onRetry={reload} />;
    if (!data) return null;

    const s = data.summary;
    const susp = data.suspicious;

    return (
        <div className="space-y-6">
            <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                    <h1 className="text-xl font-semibold">Risk analytics</h1>
                    <p className="text-sm text-mist-500">
                        Rule-based signals for {s.distinctAccountCount} accounts · timezone {s.definitions?.timezone}
                    </p>
                </div>
                <div className="flex rounded-lg bg-ink-850 p-1 text-sm">
                    {["DAY", "HOUR"].map((iv) => (
                        <button
                            key={iv}
                            type="button"
                            onClick={() => setInterval_(iv)}
                            className={`rounded-md px-3 py-1 ${
                                interval === iv ? "bg-ink-700 font-medium text-mist-100" : "text-mist-500"
                            }`}
                        >
                            {iv}
                        </button>
                    ))}
                </div>
            </div>

            <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
                <StatCard label="Completed amount" value={s.totalCompletedAmount !== null ? formatAmount(s.totalCompletedAmount, s.currency) : "multi"} tone="signal" />
                <StatCard label="Average" value={s.totalCompletedAmount !== null ? formatAmount(s.averageCompletedAmount, s.currency) : "—"} />
                <StatCard label="High-value" value={s.highValueTransactionCount} sub={`≥ ${formatAmount(s.definitions?.highValueThreshold)}`} tone="warn" />
                <StatCard label="Night-time" value={s.nightTransactionCount} tone="danger" />
            </div>

            <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
                <div className="card">
                    <p className="card-title">Transaction volume ({interval.toLowerCase()})</p>
                    {chart.counts.length ? <ActivityAreaChart data={chart.counts} /> : <EmptyState title="No data" />}
                </div>
                <div className="card">
                    <p className="card-title">Completed amount ({interval.toLowerCase()})</p>
                    {chart.amounts.length ? (
                        <AmountBarChart data={chart.amounts} />
                    ) : (
                        <EmptyState title="No single-currency amounts" message={s.currencyLimitation || "No completed transactions."} />
                    )}
                </div>
            </div>

            {/* Rule-based suspicious signals */}
            <div className="card p-0">
                <div className="card-title flex flex-wrap items-center justify-between gap-2 px-4 pt-4">
                    <span>Rule-based suspicious signals</span>
                    <span className="text-[11px] normal-case text-mist-500">
                        {susp.analysis.scannedTransactions}/{susp.analysis.completedTransactionsInCase} scanned
                        {susp.analysis.truncated ? " (most recent slice)" : ""}
                    </span>
                </div>
                {susp.signals.length ? (
                    <table className="table-fl mt-2">
                        <thead>
                            <tr><th>Transaction</th><th>Amount</th><th>Score</th><th>Signals</th></tr>
                        </thead>
                        <tbody>
                            {susp.signals.map((row) => (
                                <tr key={row.id}>
                                    <td>
                                        <Link to={`/transactions/${row.id}?case=${activeCaseId}`} className="font-medium text-signal-500 hover:underline">
                                            {row.transactionId}
                                        </Link>
                                        <p className="text-xs text-mist-500">{formatDateTime(row.timestamp)}</p>
                                    </td>
                                    <td className="tabular-nums">{formatAmount(row.amount, row.currency)}</td>
                                    <td>
                                        <span className="font-semibold text-amber-400">{formatPercent(row.riskScore)}</span>
                                    </td>
                                    <td>
                                        <div className="flex flex-wrap gap-1">
                                            {row.reasons.map((r) => (
                                                <span key={r.code} className="badge bg-ink-800 text-mist-300" title={`${r.condition || ""}`}>
                                                    {r.code.replace(/_/g, " ")}
                                                </span>
                                            ))}
                                        </div>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                ) : (
                    <EmptyState title="No signals" message="No completed transactions tripped the rule set." />
                )}
                <p className="border-t border-ink-800 px-4 py-3 text-[11px] text-mist-500">
                    {susp.interpretation} Rule score is an ordering aid (sum of matched weights, capped at 1), not a
                    probability and not a model output.
                </p>
            </div>
        </div>
    );
}

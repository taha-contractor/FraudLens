import { useCallback, useMemo, useState } from "react";
import { transactions as txApi, accounts as accountApi } from "../api/endpoints.js";
import { useCases } from "../context/CaseContext.jsx";
import { useAsync } from "../hooks/useAsync.js";
import { NeedCase } from "../components/NeedCase.jsx";
import { SkeletonRows } from "../components/LoadingState.jsx";
import { ErrorState } from "../components/ErrorState.jsx";
import { EmptyState } from "../components/EmptyState.jsx";
import { TransactionTable } from "../components/TransactionTable.jsx";

const TYPES = ["", "PAYMENT", "CASH_IN", "CASH_OUT", "TRANSFER", "DEBIT"];
const STATUSES = ["", "PENDING", "COMPLETED", "FAILED", "REVERSED", "CANCELLED"];
const RISK_FILTERS = ["", "HIGH", "MEDIUM", "LOW", "NOT_ASSESSED"];

// Server window: the backend caps a single list at 1000 rows. The explorer
// loads a bounded window (never the whole case) and offers explicit "load
// more" growth. Client text/risk filters apply within that loaded window.
const PAGE_STEP = 200;
const MAX_WINDOW = 1000;

export default function TransactionExplorer() {
    const { activeCaseId } = useCases();
    const [filters, setFilters] = useState({ transactionType: "", status: "", accountId: "", from: "", to: "" });
    const [search, setSearch] = useState("");
    const [riskFilter, setRiskFilter] = useState("");
    const [limit, setLimit] = useState(PAGE_STEP);

    const set = (k) => (e) => {
        setFilters((f) => ({ ...f, [k]: e.target.value }));
        setLimit(PAGE_STEP); // filter change resets the loaded window
    };

    const query = useMemo(() => {
        const q = { limit };
        if (filters.transactionType) q.transactionType = filters.transactionType;
        if (filters.status) q.status = filters.status;
        if (filters.accountId) q.accountId = filters.accountId;
        if (filters.from) q.from = new Date(filters.from).toISOString();
        if (filters.to) q.to = new Date(filters.to).toISOString();
        return q;
    }, [filters, limit]);

    const fetcher = useCallback(async () => {
        if (!activeCaseId) return null;
        const [txns, accs] = await Promise.all([
            txApi.list(activeCaseId, query),
            accountApi.list(activeCaseId).catch(() => ({ accounts: [] })),
        ]);
        return { txns: txns.transactions, accounts: accs.accounts || [] };
    }, [activeCaseId, query]);

    const { data, loading, error, reload } = useAsync(fetcher, [activeCaseId, query]);

    const shown = useMemo(() => {
        const list = data?.txns || [];
        const s = search.trim().toLowerCase();
        return list.filter((t) => {
            if (riskFilter) {
                const lvl = t.riskLevel || "NOT_ASSESSED";
                if (lvl !== riskFilter) return false;
            }
            if (!s) return true;
            return (
                t.transactionId?.toLowerCase().includes(s) ||
                t.description?.toLowerCase().includes(s) ||
                t.merchant?.toLowerCase().includes(s) ||
                String(t.amount).includes(s)
            );
        });
    }, [data, search, riskFilter]);

    if (!activeCaseId) return <NeedCase />;

    const total = data?.txns?.length ?? 0;
    const canLoadMore = total >= limit && limit < MAX_WINDOW;

    return (
        <div className="space-y-4">
            <div>
                <h1 className="text-xl font-semibold">Transaction explorer</h1>
                <p className="text-sm text-mist-500">
                    Filtered server-side against the active case. Shows a bounded window of up to {limit} rows.
                </p>
            </div>

            {/* Filter bar */}
            <div className="card grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
                <input
                    className="input col-span-2 lg:col-span-1"
                    placeholder="Search id / merchant / amount"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                />
                <select className="input" value={filters.transactionType} onChange={set("transactionType")}>
                    {TYPES.map((t) => (
                        <option key={t} value={t}>{t ? t.replace(/_/g, " ") : "All types"}</option>
                    ))}
                </select>
                <select className="input" value={filters.status} onChange={set("status")}>
                    {STATUSES.map((s) => (
                        <option key={s} value={s}>{s ? s.replace(/_/g, " ") : "All statuses"}</option>
                    ))}
                </select>
                <select className="input" value={filters.accountId} onChange={set("accountId")}>
                    <option value="">All accounts</option>
                    {(data?.accounts || []).map((a) => (
                        <option key={a.id} value={a.id}>{a.accountNumberMasked}</option>
                    ))}
                </select>
                <select className="input" value={riskFilter} onChange={(e) => setRiskFilter(e.target.value)}>
                    {RISK_FILTERS.map((r) => (
                        <option key={r} value={r}>
                            {r ? `Risk: ${r.replace(/_/g, " ").toLowerCase()}` : "All risk"}
                        </option>
                    ))}
                </select>
                <div className="col-span-2 flex items-center gap-2 md:col-span-3 lg:col-span-1">
                    <input type="date" className="input w-full" value={filters.from} onChange={set("from")} aria-label="From" />
                    <input type="date" className="input w-full" value={filters.to} onChange={set("to")} aria-label="To" />
                </div>
            </div>

            {/* Results */}
            <div className="card p-0">
                {loading && !data ? (
                    <div className="p-4"><SkeletonRows rows={8} /></div>
                ) : error ? (
                    <div className="p-4"><ErrorState message={error} onRetry={reload} /></div>
                ) : shown.length === 0 ? (
                    <EmptyState
                        title="No matching transactions"
                        message="Adjust the filters or search. If the case has none yet, add or import transactions first."
                    />
                ) : (
                    <>
                        <TransactionTable caseId={activeCaseId} transactions={shown} dense />
                        <div className="flex items-center justify-between border-t border-ink-800 px-4 py-3 text-sm text-mist-500">
                            <span>
                                Showing {shown.length} of {total} loaded (window {limit})
                                {riskFilter || search ? " · filtered client-side within the window" : ""}
                            </span>
                            {canLoadMore && (
                                <button type="button" className="btn-ghost" onClick={() => setLimit((l) => Math.min(l + PAGE_STEP, MAX_WINDOW))} disabled={loading}>
                                    {loading ? "Loading…" : "Load more"}
                                </button>
                            )}
                        </div>
                    </>
                )}
            </div>
        </div>
    );
}

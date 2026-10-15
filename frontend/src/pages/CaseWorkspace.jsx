import { useCallback, useMemo, useState } from "react";
import { useParams, Link } from "react-router-dom";
import {
    cases as casesApi,
    accounts as accountApi,
    documents as documentApi,
    evidence as evidenceApi,
    analytics,
} from "../api/endpoints.js";
import { useCases } from "../context/CaseContext.jsx";
import { useAsync } from "../hooks/useAsync.js";
import { Spinner } from "../components/LoadingState.jsx";
import { ErrorState } from "../components/ErrorState.jsx";
import { EmptyState } from "../components/EmptyState.jsx";
import { StatusBadge } from "../components/ui.jsx";
import { formatDateTime, formatDate, shortId } from "../utils/format.js";

const TABS = ["Overview", "Accounts", "Documents", "Evidence"];

export default function CaseWorkspace() {
    const { caseId } = useParams();
    const { setActiveCaseId, activeCaseId } = useCases();
    const [tab, setTab] = useState("Overview");

    const fetcher = useCallback(async () => {
        const [caseRes, accRes, docRes, evRes, summaryRes] = await Promise.all([
            casesApi.get(caseId),
            accountApi.list(caseId).catch(() => ({ accounts: [] })),
            documentApi.list(caseId, {}).catch(() => ({ documents: [] })),
            evidenceApi.list(caseId, {}).catch(() => ({ evidence: [] })),
            analytics.summary(caseId).catch(() => ({ summary: null })),
        ]);
        return {
            case: caseRes.case,
            accounts: accRes.accounts || [],
            documents: docRes.documents || [],
            evidence: evRes.evidence || [],
            summary: summaryRes.summary,
        };
    }, [caseId]);

    const { data, loading, error, reload } = useAsync(fetcher, [caseId]);
    const isActive = activeCaseId === caseId;

    const statusCounts = useMemo(() => {
        if (!data?.summary) return null;
        const s = data.summary;
        return [
            ["Completed", s.completedTransactions, "text-emerald-400"],
            ["Pending", s.pendingTransactions, "text-amber-400"],
            ["Failed", s.failedTransactions, "text-red-400"],
            ["Reversed", s.reversedTransactions, "text-sky-400"],
            ["Cancelled", s.cancelledTransactions, "text-mist-500"],
        ];
    }, [data]);

    if (loading && !data) return <Spinner label="Loading case…" />;
    if (error) return <ErrorState message={error} onRetry={reload} />;
    if (!data) return null;

    const c = data.case;

    return (
        <div className="space-y-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                    <Link to="/cases" className="text-xs text-signal-500 hover:underline">← All cases</Link>
                    <h1 className="mt-1 text-xl font-semibold">{c.title}</h1>
                    <p className="text-sm text-mist-500">
                        {c.caseNumber} · <StatusBadge status={c.status} /> · created {formatDate(c.createdAt)}
                    </p>
                </div>
                <div className="flex gap-2">
                    {!isActive && (
                        <button type="button" className="btn-ghost" onClick={() => setActiveCaseId(caseId)}>
                            Set as active case
                        </button>
                    )}
                    <Link to="/transactions" className="btn-primary" onClick={() => setActiveCaseId(caseId)}>
                        Explore transactions
                    </Link>
                </div>
            </div>

            {c.description && <p className="text-sm text-mist-300">{c.description}</p>}

            {/* Tabs */}
            <div className="flex gap-1 border-b border-ink-800">
                {TABS.map((t) => (
                    <button
                        key={t}
                        type="button"
                        onClick={() => setTab(t)}
                        className={`px-4 py-2 text-sm transition-colors ${
                            tab === t
                                ? "border-b-2 border-signal-500 text-signal-500"
                                : "text-mist-500 hover:text-mist-300"
                        }`}
                    >
                        {t}
                    </button>
                ))}
            </div>

            {tab === "Overview" && (
                <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
                    <div className="card">
                        <p className="card-title">Case summary</p>
                        {data.summary ? (
                            <dl className="space-y-2 text-sm">
                                <Row label="Transactions" value={data.summary.totalTransactions} />
                                <Row label="Accounts involved" value={data.summary.distinctAccountCount} />
                                <Row label="High-value" value={data.summary.highValueTransactionCount} />
                                <Row label="Night-time" value={data.summary.nightTransactionCount} />
                                <Row label="First activity" value={formatDateTime(data.summary.earliestTransaction)} />
                                <Row label="Latest activity" value={formatDateTime(data.summary.latestTransaction)} />
                            </dl>
                        ) : (
                            <p className="text-sm text-mist-500">Summary unavailable.</p>
                        )}
                    </div>
                    <div className="card">
                        <p className="card-title">Status breakdown</p>
                        {statusCounts ? (
                            <ul className="space-y-2 text-sm">
                                {statusCounts.map(([label, v, tone]) => (
                                    <li key={label} className="flex items-center justify-between">
                                        <span className="text-mist-500">{label}</span>
                                        <span className={`tabular-nums font-medium ${tone}`}>{v}</span>
                                    </li>
                                ))}
                            </ul>
                        ) : (
                            <p className="text-sm text-mist-500">No data.</p>
                        )}
                    </div>
                    <div className="card">
                        <p className="card-title">Case data</p>
                        <dl className="space-y-2 text-sm">
                            <Row label="Documents" value={data.documents.length} />
                            <Row label="Evidence items" value={data.evidence.length} />
                            <Row label="Accounts" value={data.accounts.length} />
                            <Row label="Investigators" value={(c.investigators || []).length || "—"} />
                        </dl>
                    </div>
                </div>
            )}

            {tab === "Accounts" && (
                <div className="card p-0">
                    {data.accounts.length ? (
                        <table className="table-fl">
                            <thead>
                                <tr><th>Masked no.</th><th>Type</th><th>Currency</th><th>Status</th></tr>
                            </thead>
                            <tbody>
                                {data.accounts.map((a) => (
                                    <tr key={a.id}>
                                        <td className="font-medium">{a.accountNumberMasked}</td>
                                        <td className="text-mist-300">{a.accountType}</td>
                                        <td className="text-mist-300">{a.currency}</td>
                                        <td><StatusBadge status={a.status} /></td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    ) : (
                        <EmptyState title="No accounts" message="Add accounts to this case to link transactions." />
                    )}
                </div>
            )}

            {tab === "Documents" && (
                <div className="card p-0">
                    {data.documents.length ? (
                        <table className="table-fl">
                            <thead>
                                <tr><th>File</th><th>Processing</th><th>Pages</th><th>Uploaded</th></tr>
                            </thead>
                            <tbody>
                                {data.documents.map((d) => (
                                    <tr key={d.id}>
                                        <td className="font-medium">{d.fileName}</td>
                                        <td><StatusBadge status={d.processingStatus} /></td>
                                        <td className="text-mist-300">{d.pageCount ?? "—"}</td>
                                        <td className="text-mist-500">{formatDateTime(d.createdAt)}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    ) : (
                        <EmptyState title="No documents" message="Upload case documents to extract evidence." />
                    )}
                </div>
            )}

            {tab === "Evidence" && (
                <div className="card p-0">
                    {data.evidence.length ? (
                        <table className="table-fl">
                            <thead>
                                <tr><th>Type</th><th>Document</th><th>Page</th><th>Excerpt</th></tr>
                            </thead>
                            <tbody>
                                {data.evidence.map((e) => (
                                    <tr key={e.id}>
                                        <td className="font-medium">{(e.evidenceType || "").replace(/_/g, " ")}</td>
                                        <td className="text-mist-300">{e.documentName || shortId(e.documentId)}</td>
                                        <td className="text-mist-300">{e.pageNumber ?? "—"}</td>
                                        <td className="max-w-sm truncate text-mist-500" title={e.sourceText}>{e.sourceText}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    ) : (
                        <EmptyState title="No evidence" message="Evidence extracted from case documents appears here." />
                    )}
                </div>
            )}
        </div>
    );
}

function Row({ label, value }) {
    return (
        <div className="flex items-center justify-between">
            <dt className="text-mist-500">{label}</dt>
            <dd className="tabular-nums text-mist-100">{value}</dd>
        </div>
    );
}

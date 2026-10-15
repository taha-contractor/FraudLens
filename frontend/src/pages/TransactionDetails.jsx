import { useCallback, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import {
    transactions as txApi,
    risk as riskApi,
    accounts as accountApi,
    evidence as evidenceApi,
} from "../api/endpoints.js";
import { useCases } from "../context/CaseContext.jsx";
import { useAsync } from "../hooks/useAsync.js";
import { Spinner } from "../components/LoadingState.jsx";
import { ErrorState } from "../components/ErrorState.jsx";
import { EmptyState } from "../components/EmptyState.jsx";
import { StatCard, RiskBadge, StatusBadge } from "../components/ui.jsx";
import { TransactionTable } from "../components/TransactionTable.jsx";
import { formatAmount, formatDateTime, formatPercent, shortId } from "../utils/format.js";

export default function TransactionDetails() {
    const { txnId } = useParams();
    const [params] = useSearchParams();
    const { activeCaseId } = useCases();
    // Prefer the explicit ?case= link (deep links from other screens); fall
    // back to the active case. Case isolation is enforced server-side either
    // way — a foreign id resolves to 404, never another case's data.
    const caseId = params.get("case") || activeCaseId;
    const [assessing, setAssessing] = useState(false);
    const [assessError, setAssessError] = useState(null);

    const fetcher = useCallback(async () => {
        if (!caseId || !txnId) return null;
        const [txn, risk, accRes, evRes] = await Promise.all([
            txApi.get(caseId, txnId),
            riskApi.getForTransaction(caseId, txnId).catch(() => null),
            accountApi.list(caseId).catch(() => ({ accounts: [] })),
            evidenceApi.list(caseId, {}).catch(() => ({ evidence: [] })),
        ]);
        const t = txn.transaction;
        // Related transactions: same case, touching either account.
        const [fromSrc, fromDest] = await Promise.all([
            txApi.list(caseId, { accountId: t.sourceAccountId, limit: 60 }).catch(() => ({ transactions: [] })),
            t.destinationAccountId !== t.sourceAccountId
                ? txApi.list(caseId, { accountId: t.destinationAccountId, limit: 60 }).catch(() => ({ transactions: [] }))
                : Promise.resolve({ transactions: [] }),
        ]);
        const byId = new Map();
        for (const row of [...fromSrc.transactions, ...fromDest.transactions]) {
            if (row.id !== t.id) byId.set(row.id, row);
        }
        const related = [...byId.values()].sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp)).slice(0, 20);
        const accMap = Object.fromEntries((accRes.accounts || []).map((a) => [a.id, a]));
        const relatedEvidence = (evRes.evidence || []).filter((e) => e.transactionId === t.id);
        return { txn: t, risk, accMap, related, relatedEvidence, allEvidence: evRes.evidence || [] };
    }, [caseId, txnId]);

    const { data, loading, error, reload } = useAsync(fetcher, [caseId, txnId]);

    async function assess() {
        setAssessing(true);
        setAssessError(null);
        try {
            await riskApi.assessOne(caseId, txnId);
            await reload();
        } catch (err) {
            setAssessError(err?.response?.data?.error?.message || "Assessment failed");
        } finally {
            setAssessing(false);
        }
    }

    const featureRows = useMemo(() => {
        const f = data?.risk?.assessment?.features;
        if (!f) return [];
        return Object.entries(f).sort((a, b) => a[0].localeCompare(b[0]));
    }, [data]);

    if (!caseId) return <ErrorState title="No case selected" message="Open this transaction from a case screen." />;
    if (loading && !data) return <Spinner label="Loading transaction…" />;
    if (error) return <ErrorState message={error} onRetry={reload} />;
    if (!data) return null;

    const t = data.txn;
    const a = data.risk?.assessment;
    const status = data.risk?.status || (a ? a.status : "not_assessed");

    return (
        <div className="space-y-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                    <Link to="/transactions" className="text-xs text-signal-500 hover:underline">
                        ← Transaction explorer
                    </Link>
                    <h1 className="mt-1 text-xl font-semibold">{t.transactionId}</h1>
                    <p className="text-sm text-mist-500">
                        {t.transactionType} · {formatDateTime(t.timestamp)} · <StatusBadge status={t.status} />
                    </p>
                </div>
                <button type="button" className="btn-primary" onClick={assess} disabled={assessing}>
                    {assessing ? "Assessing…" : status === "scored" ? "Re-assess risk" : "Assess risk"}
                </button>
            </div>

            {assessError && <p className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-400">{assessError}</p>}

            <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
                {/* Attributes */}
                <div className="card lg:col-span-2">
                    <p className="card-title">Attributes</p>
                    <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm">
                        <Field label="Amount" value={formatAmount(t.amount, t.currency)} />
                        <Field label="Type" value={t.transactionType} />
                        <Field label="Status" value={<StatusBadge status={t.status} />} />
                        <Field label="Timestamp" value={formatDateTime(t.timestamp)} />
                        <Field label="Source account" value={<AccountLink caseId={caseId} id={t.sourceAccountId} map={data.accMap} />} />
                        <Field label="Destination account" value={<AccountLink caseId={caseId} id={t.destinationAccountId} map={data.accMap} />} />
                        {t.oldbalanceOrg !== undefined && t.oldbalanceOrg !== null && (
                            <Field label="Old balance (origin)" value={formatAmount(t.oldbalanceOrg, t.currency)} />
                        )}
                        {t.merchant && <Field label="Merchant" value={t.merchant} />}
                        {t.location && <Field label="Location" value={t.location} />}
                        {t.description && <Field label="Description" value={t.description} />}
                    </dl>
                </div>

                {/* Model risk */}
                <div className="card">
                    <p className="card-title">Model risk assessment</p>
                    {status === "scored" ? (
                        <div className="space-y-3">
                            <div className="flex items-center justify-between">
                                <RiskBadge level={t.riskLevel || a?.riskLevel} score={t.riskScore ?? a?.riskScore} />
                                <span className="text-2xl font-semibold tabular-nums">
                                    {formatPercent(t.riskScore ?? a?.riskScore)}
                                </span>
                            </div>
                            <div className="grid grid-cols-2 gap-2 text-xs text-mist-500">
                                <span>Threshold</span>
                                <span className="text-right text-mist-300">{a?.threshold ?? 0.95}</span>
                                <span>Prediction</span>
                                <span className="text-right text-mist-300">
                                    {a?.modelPrediction === true ? "flagged for review" : "not flagged"}
                                </span>
                                <span>Mapped type</span>
                                <span className="text-right text-mist-300">{a?.mappedType || "—"}</span>
                                <span>Assessed</span>
                                <span className="text-right text-mist-300">{formatDateTime(a?.assessedAt)}</span>
                            </div>
                            <p className="rounded-lg bg-ink-850 px-3 py-2 text-[11px] text-mist-500">
                                This is a model estimate to prioritize review — not a fraud determination.
                            </p>
                        </div>
                    ) : status === "unscored" ? (
                        <div className="space-y-2 text-sm">
                            <span className="badge bg-ink-800 text-mist-300 border border-ink-600">Unscored</span>
                            <p className="text-mist-300">{a?.error || "This transaction could not be scored."}</p>
                            <p className="text-[11px] text-mist-500">
                                No low-risk default was assigned. Resolve the input gap and re-assess.
                            </p>
                        </div>
                    ) : (
                        <EmptyState title="Not assessed" message="Run the assessment to score this transaction against the model." />
                    )}

                    {a?.gaps?.length > 0 && (
                        <div className="mt-3 rounded-lg border border-amber-500/20 bg-amber-500/5 p-2 text-[11px] text-amber-300">
                            <p className="font-semibold">Feature gaps</p>
                            <ul className="mt-1 list-disc pl-4">
                                {a.gaps.map((g, i) => (
                                    <li key={i}>{g}</li>
                                ))}
                            </ul>
                        </div>
                    )}
                </div>
            </div>

            {/* Feature vector */}
            {featureRows.length > 0 && (
                <div className="card">
                    <p className="card-title">Historical & model features ({featureRows.length})</p>
                    <div className="grid grid-cols-2 gap-x-8 gap-y-1 text-sm sm:grid-cols-3 lg:grid-cols-4">
                        {featureRows.map(([k, v]) => (
                            <div key={k} className="flex items-center justify-between border-b border-ink-800 py-1">
                                <span className="truncate text-mist-500" title={k}>{k}</span>
                                <span className="tabular-nums text-mist-100">
                                    {typeof v === "number" ? Number(v.toFixed(4)) : String(v)}
                                </span>
                            </div>
                        ))}
                    </div>
                    <p className="mt-2 text-[11px] text-mist-500">
                        History features are computed from prior transactions in this case only, using each
                        transaction's own timestamp — never from later activity or another case.
                    </p>
                </div>
            )}

            <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
                {/* Related transactions */}
                <div className="card lg:col-span-2 p-0">
                    <p className="card-title px-4 pt-4">Related transactions (same accounts)</p>
                    {data.related.length ? (
                        <div className="px-4 pb-2">
                            <TransactionTable caseId={caseId} transactions={data.related} dense />
                        </div>
                    ) : (
                        <div className="px-4 pb-4">
                            <EmptyState title="No related activity" message="No other transactions touch these accounts." />
                        </div>
                    )}
                </div>

                {/* Evidence & actions */}
                <div className="card">
                    <p className="card-title">Evidence & actions</p>
                    {data.relatedEvidence.length ? (
                        <ul className="space-y-2 text-sm">
                            {data.relatedEvidence.map((e) => (
                                <li key={e.id} className="rounded-lg bg-ink-850 px-3 py-2">
                                    <p className="font-medium text-mist-100">{e.evidenceType}</p>
                                    <p className="text-xs text-mist-500">{e.documentName || shortId(e.documentId)}</p>
                                </li>
                            ))}
                        </ul>
                    ) : (
                        <EmptyState
                            title="No linked evidence"
                            message={`${data.allEvidence.length} evidence item(s) exist in this case, none linked to this transaction.`}
                        />
                    )}
                    <Link to={`/cases/${caseId}`} className="btn-ghost mt-3 w-full justify-center">
                        Open case workspace
                    </Link>
                </div>
            </div>
        </div>
    );
}

function Field({ label, value }) {
    return (
        <div>
            <dt className="text-xs uppercase tracking-wide text-mist-500">{label}</dt>
            <dd className="mt-0.5 text-mist-100">{value}</dd>
        </div>
    );
}

function AccountLink({ id, map }) {
    const acc = map[id];
    return (
        <span title={id}>
            {acc ? acc.accountNumberMasked : shortId(id)}
            {acc?.currency ? ` · ${acc.currency}` : ""}
        </span>
    );
}

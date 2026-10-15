import { useCallback, useState } from "react";
import { useNavigate } from "react-router-dom";
import { cases as casesApi } from "../api/endpoints.js";
import { useCases } from "../context/CaseContext.jsx";
import { useAsync } from "../hooks/useAsync.js";
import { Spinner } from "../components/LoadingState.jsx";
import { ErrorState } from "../components/ErrorState.jsx";
import { EmptyState } from "../components/EmptyState.jsx";
import { formatDate } from "../utils/format.js";

const STATUS_TONE = {
    OPEN: "text-sky-400",
    UNDER_INVESTIGATION: "text-amber-400",
    CLOSED: "text-mist-500",
    ARCHIVED: "text-mist-500",
};

export default function Cases() {
    const { setActiveCaseId } = useCases();
    const navigate = useNavigate();
    const [creating, setCreating] = useState(false);
    const [form, setForm] = useState({ title: "", description: "" });
    const [busy, setBusy] = useState(false);
    const [formError, setFormError] = useState(null);

    const fetcher = useCallback(() => casesApi.list(), []);
    const { data, loading, error, reload } = useAsync(fetcher, []);
    const cases = data?.cases || [];

    function open(c, asActive) {
        if (asActive) setActiveCaseId(c.id);
        navigate(`/cases/${c.id}`);
    }

    async function createCase(e) {
        e.preventDefault();
        setBusy(true);
        setFormError(null);
        try {
            const { case: created } = await casesApi.create({
                title: form.title,
                description: form.description || undefined,
            });
            setForm({ title: "", description: "" });
            setCreating(false);
            await reload();
            open(created, true);
        } catch (err) {
            setFormError(err?.response?.data?.error?.message || "Could not create case");
        } finally {
            setBusy(false);
        }
    }

    return (
        <div className="space-y-4">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-xl font-semibold">Investigation cases</h1>
                    <p className="text-sm text-mist-500">Cases you created or are assigned to.</p>
                </div>
                <button type="button" className="btn-primary" onClick={() => setCreating((v) => !v)}>
                    {creating ? "Cancel" : "New case"}
                </button>
            </div>

            {creating && (
                <form onSubmit={createCase} className="card space-y-3">
                    <input
                        className="input w-full"
                        placeholder="Case title"
                        value={form.title}
                        onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
                        required
                        minLength={3}
                    />
                    <textarea
                        className="input w-full"
                        rows={2}
                        placeholder="Description (optional)"
                        value={form.description}
                        onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
                    />
                    {formError && <p className="text-sm text-red-400">{formError}</p>}
                    <button type="submit" className="btn-primary" disabled={busy}>
                        {busy ? "Creating…" : "Create case"}
                    </button>
                </form>
            )}

            {loading && !data ? (
                <Spinner label="Loading cases…" />
            ) : error ? (
                <ErrorState message={error} onRetry={reload} />
            ) : cases.length === 0 ? (
                <EmptyState title="No cases yet" message="Create a case to start importing transactions." />
            ) : (
                <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
                    {cases.map((c) => (
                        <div key={c.id} className="card flex flex-col">
                            <div className="flex items-start justify-between gap-2">
                                <div className="min-w-0">
                                    <p className="truncate font-semibold text-mist-100">{c.title}</p>
                                    <p className="text-xs text-mist-500">{c.caseNumber}</p>
                                </div>
                                <span className={`text-xs font-medium ${STATUS_TONE[c.status] || "text-mist-300"}`}>
                                    {(c.status || "").replace(/_/g, " ")}
                                </span>
                            </div>
                            {c.description && (
                                <p className="mt-2 line-clamp-2 text-sm text-mist-300">{c.description}</p>
                            )}
                            <p className="mt-2 text-xs text-mist-500">Created {formatDate(c.createdAt)}</p>
                            <div className="mt-3 flex gap-2">
                                <button type="button" className="btn-primary flex-1 justify-center" onClick={() => open(c, true)}>
                                    Set active & open
                                </button>
                                <button type="button" className="btn-ghost" onClick={() => open(c, false)}>
                                    Preview
                                </button>
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}

import { useCallback } from "react";
import { risk as riskApi } from "../api/endpoints.js";
import { useAsync } from "../hooks/useAsync.js";
import { Spinner } from "../components/LoadingState.jsx";
import { ErrorState } from "../components/ErrorState.jsx";
import { MODEL_EVALUATION } from "../mocks/prototypeData.js";

export default function ModelInfo() {
    const fetcher = useCallback(() => riskApi.modelInfo(), []);
    const { data, loading, error, reload } = useAsync(fetcher, []);

    if (loading && !data) return <Spinner label="Loading model metadata…" />;
    if (error) return <ErrorState message={error} onRetry={reload} />;
    if (!data) return null;

    const m = data.available ? data.model : null;

    return (
        <div className="space-y-6">
            <div className="flex items-center gap-3">
                <h1 className="text-xl font-semibold">Model information</h1>
                {data.available ? (
                    <span className="badge bg-emerald-500/15 text-emerald-400">Service live</span>
                ) : (
                    <span className="badge bg-amber-500/15 text-amber-400">Service offline</span>
                )}
            </div>

            {/* Live metadata (real, from the inference service) */}
            <div className="card">
                <p className="card-title">Deployed model (live from inference service)</p>
                {m ? (
                    <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm md:grid-cols-3">
                        <Item label="Winner id" value={m.winner_id} />
                        <Item label="Family" value={m.model_family} />
                        <Item label="Ensemble" value={m.ensemble_kind} />
                        <Item label="Decision threshold" value={m.threshold} tone="warn" />
                        <Item label="Features" value={m.n_features} />
                        <Item label="Needs scaling" value={m.needs_scaling ? "yes" : "no"} />
                    </dl>
                ) : (
                    <p className="text-sm text-mist-300">
                        The inference service is not reachable, so live metadata is unavailable.
                        {data.reason ? ` (${data.reason})` : ""} This is reported honestly rather than
                        substituted with static values.
                    </p>
                )}
            </div>

            {/* Feature contract */}
            {m?.feature_names && (
                <div className="card">
                    <p className="card-title">Feature order ({m.feature_names.length}) — exact training-time contract</p>
                    <ol className="grid grid-cols-1 gap-x-8 gap-y-1 text-sm sm:grid-cols-2 lg:grid-cols-3">
                        {m.feature_names.map((f, i) => (
                            <li key={f} className="flex gap-2 border-b border-ink-800 py-1">
                                <span className="w-6 text-right text-mist-500">{i + 1}</span>
                                <span className="text-mist-100">{f}</span>
                            </li>
                        ))}
                    </ol>
                    <p className="mt-3 text-[11px] text-mist-500">
                        The first 8 are direct transaction fields and type one-hot; the remaining 9 are causal
                        account-history features computed from strictly prior transactions.
                    </p>
                </div>
            )}

            {/* Reference evaluation metrics — ISOLATED MOCK, clearly labeled */}
            <div className="rounded-xl border border-dashed border-amber-500/30 bg-amber-500/[0.03] p-4">
                <div className="mb-3 flex items-center gap-2">
                    <p className="card-title mb-0">Evaluation metrics</p>
                    <span className="badge border border-amber-500/30 bg-amber-500/10 text-amber-300">
                        Reference data · not computed live
                    </span>
                </div>
                <p className="mb-3 text-xs text-mist-500">{MODEL_EVALUATION.label}</p>
                <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
                    {MODEL_EVALUATION.metrics.map((met) => (
                        <div key={met.name} className="card">
                            <p className="card-title mb-1">{met.name}</p>
                            <p className="text-2xl font-semibold tabular-nums text-mist-100">{met.value}</p>
                        </div>
                    ))}
                </div>

                <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
                    <div className="card">
                        <p className="card-title">Dataset</p>
                        <p className="text-sm text-mist-300">{MODEL_EVALUATION.dataset.description}</p>
                        <p className="mt-2 text-xs text-mist-500">
                            {MODEL_EVALUATION.dataset.frozen ? "Frozen for this milestone · not regenerated by the UI." : ""}
                        </p>
                    </div>
                    <div className="card">
                        <p className="card-title">Limitations</p>
                        <ul className="list-disc space-y-1 pl-5 text-sm text-mist-300">
                            {MODEL_EVALUATION.limitations.map((l, i) => (
                                <li key={i}>{l}</li>
                            ))}
                        </ul>
                    </div>
                </div>
            </div>

            <p className="text-xs text-mist-500">
                Metrics above come from a saved M5 experiment report via an isolated frontend fixture (no evaluation
                endpoint exists yet). They describe one held-out test set and are not a guarantee of real-world
                performance. Live model identity, threshold and feature contract above are read from the running
                inference service.
            </p>
        </div>
    );
}

function Item({ label, value, tone = "" }) {
    const toneClass = tone === "warn" ? "text-amber-400" : "text-mist-100";
    return (
        <div>
            <dt className="text-xs uppercase tracking-wide text-mist-500">{label}</dt>
            <dd className={`mt-0.5 font-medium tabular-nums ${toneClass}`}>{value ?? "—"}</dd>
        </div>
    );
}

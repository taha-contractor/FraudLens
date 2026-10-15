/**
 * Real API failures surface as explicit, readable errors. The UI never
 * silently falls back to fabricated data; retry re-runs the failed fetch.
 */
export function ErrorState({ title = "Something went wrong", message, onRetry }) {
    return (
        <div className="card mx-auto max-w-xl border-red-500/30">
            <div className="flex items-start gap-3">
                <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-red-500/15 text-red-400">
                    !
                </span>
                <div className="min-w-0">
                    <h3 className="font-semibold text-mist-100">{title}</h3>
                    <p className="mt-1 break-words text-sm text-mist-300">
                        {message || "The request could not be completed."}
                    </p>
                    {onRetry && (
                        <button type="button" className="btn-ghost mt-3" onClick={onRetry}>
                            Retry
                        </button>
                    )}
                </div>
            </div>
        </div>
    );
}

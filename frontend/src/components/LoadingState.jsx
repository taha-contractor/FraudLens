export function Spinner({ label = "Loading…" }) {
    return (
        <div className="flex items-center justify-center gap-3 py-10 text-mist-500">
            <span className="h-5 w-5 animate-spin rounded-full border-2 border-ink-600 border-t-signal-500" />
            <span className="text-sm">{label}</span>
        </div>
    );
}

export function SkeletonRows({ rows = 5 }) {
    return (
        <div className="space-y-2 py-2" aria-hidden>
            {Array.from({ length: rows }).map((_, i) => (
                <div key={i} className="h-9 animate-pulse rounded-lg bg-ink-850" />
            ))}
        </div>
    );
}

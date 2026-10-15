export function EmptyState({ title = "Nothing here yet", message, action }) {
    return (
        <div className="flex flex-col items-center justify-center gap-2 py-12 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-ink-850 text-mist-500 text-xl">
                ∅
            </div>
            <h3 className="font-semibold text-mist-300">{title}</h3>
            {message && <p className="max-w-md text-sm text-mist-500">{message}</p>}
            {action && <div className="mt-2">{action}</div>}
        </div>
    );
}

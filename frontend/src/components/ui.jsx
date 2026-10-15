import { formatPercent } from "../utils/format.js";

export function StatCard({ label, value, sub, tone = "default" }) {
    const tones = {
        default: "text-mist-100",
        danger: "text-red-400",
        warn: "text-amber-400",
        safe: "text-emerald-400",
        signal: "text-sky-400",
    };
    return (
        <div className="card">
            <p className="card-title mb-1">{label}</p>
            <p className={`text-2xl font-semibold tabular-nums ${tones[tone]}`}>{value}</p>
            {sub && <p className="mt-1 text-xs text-mist-500">{sub}</p>}
        </div>
    );
}

export function RiskBadge({ level, score }) {
    const map = {
        HIGH: "bg-red-500/15 text-red-400 border-red-500/30",
        MEDIUM: "bg-amber-500/15 text-amber-400 border-amber-500/30",
        LOW: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
        NOT_ASSESSED: "bg-ink-800 text-mist-500 border-ink-600",
        UNSCORED: "bg-ink-800 text-mist-300 border-ink-600",
    };
    const labels = {
        HIGH: "High",
        MEDIUM: "Medium",
        LOW: "Low",
        NOT_ASSESSED: "Not assessed",
        UNSCORED: "Unscored",
    };
    const key = map[level] ? level : "NOT_ASSESSED";
    return (
        <span className={`badge ${map[key]}`}>
            {labels[key]}
            {key !== "NOT_ASSESSED" && score !== undefined && score !== null
                ? ` · ${formatPercent(score)}`
                : ""}
        </span>
    );
}

export function StatusBadge({ status }) {
    const colors = {
        COMPLETED: "text-emerald-400",
        PENDING: "text-amber-400",
        FAILED: "text-red-400",
        REVERSED: "text-sky-400",
        CANCELLED: "text-mist-500",
    };
    return (
        <span className={`font-medium ${colors[status] || "text-mist-300"}`}>
            {status ? status.replace(/_/g, " ") : "—"}
        </span>
    );
}

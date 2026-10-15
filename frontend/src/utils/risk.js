/** Risk/status display metadata. Level colors mirror the backend classification
 *  (HIGH >= threshold 0.95, MEDIUM >= 0.50, else LOW). These are screening
 *  bands on a model estimate — never fraud determinations. */

export const RISK_LEVELS = {
    HIGH: { label: "High", badge: "bg-red-500/15 text-red-400 border border-red-500/30" },
    MEDIUM: { label: "Medium", badge: "bg-amber-500/15 text-amber-400 border border-amber-500/30" },
    LOW: { label: "Low", badge: "bg-emerald-500/15 text-emerald-400 border border-emerald-500/30" },
    NOT_ASSESSED: { label: "Not assessed", badge: "bg-ink-700 text-mist-500 border border-ink-600" },
    UNSCORED: { label: "Unscored", badge: "bg-ink-700 text-mist-300 border border-ink-600" },
};

export function riskMeta(level) {
    return RISK_LEVELS[level] || RISK_LEVELS.NOT_ASSESSED;
}

export function riskOf(txn) {
    if (txn?.riskLevel) return txn.riskLevel;
    if (txn?.riskScore !== undefined && txn?.riskScore !== null) return "NOT_ASSESSED";
    return "NOT_ASSESSED";
}

export const STATUS_COLORS = {
    COMPLETED: "text-emerald-400",
    PENDING: "text-amber-400",
    FAILED: "text-red-400",
    REVERSED: "text-sky-400",
    CANCELLED: "text-mist-500",
};

export const CASE_STATUS_LABELS = {
    OPEN: "Open",
    UNDER_INVESTIGATION: "Under investigation",
    CLOSED: "Closed",
    ARCHIVED: "Archived",
};

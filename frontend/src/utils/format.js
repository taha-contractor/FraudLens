/** Presentation helpers: deterministic, UI-only formatting. */

const amountFmt = new Intl.NumberFormat("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
});

export function formatAmount(value, currency = "") {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
    return `${amountFmt.format(Number(value))}${currency ? ` ${currency}` : ""}`;
}

export function formatCompactAmount(value, currency = "") {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
    const n = Number(value);
    const abs = Math.abs(n);
    const [scaled, suffix] =
        abs >= 1e9 ? [n / 1e9, "B"] : abs >= 1e6 ? [n / 1e6, "M"] : abs >= 1e3 ? [n / 1e3, "K"] : [n, ""];
    return `${scaled.toFixed(suffix ? 1 : 0)}${suffix}${currency ? ` ${currency}` : ""}`;
}

export function formatDateTime(value) {
    if (!value) return "—";
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return String(value);
    return d.toLocaleString("en-GB", { hour12: false });
}

export function formatDate(value) {
    if (!value) return "—";
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return String(value);
    return d.toLocaleDateString("en-GB");
}

export function formatPercent(score) {
    if (score === null || score === undefined) return "—";
    return `${(Number(score) * 100).toFixed(score >= 0.001 && score < 0.01 ? 2 : 0)}%`;
}

const ACCOUNT_SHORT = (id) => (id ? `…${String(id).slice(-6)}` : "—");

export function shortId(id) {
    return ACCOUNT_SHORT(id);
}

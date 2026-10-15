import { NavLink } from "react-router-dom";
import { useState } from "react";
import { useAuth } from "../context/AuthContext.jsx";
import { useCases } from "../context/CaseContext.jsx";

const NAV = [
    { to: "/", label: "Dashboard", end: true },
    { to: "/transactions", label: "Transactions" },
    { to: "/analytics", label: "Analytics" },
    { to: "/cases", label: "Cases" },
    { to: "/model", label: "Model" },
];

export function Layout({ children }) {
    const { user, logout } = useAuth();
    const { cases, activeCaseId, setActiveCaseId, loading } = useCases();
    const [menuOpen, setMenuOpen] = useState(false);

    return (
        <div className="flex min-h-screen">
            {/* Sidebar */}
            <aside className="hidden w-56 shrink-0 flex-col border-r border-ink-800 bg-ink-900 p-4 md:flex">
                <div className="mb-8 flex items-center gap-2">
                    <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-signal-500/15 text-signal-500 font-bold">
                        F
                    </span>
                    <div>
                        <p className="font-semibold leading-tight">FraudLens</p>
                        <p className="text-[11px] text-mist-500">Fraud investigation</p>
                    </div>
                </div>

                <nav className="flex flex-col gap-1">
                    {NAV.map((item) => (
                        <NavLink
                            key={item.to}
                            to={item.to}
                            end={item.end}
                            className={({ isActive }) =>
                                `rounded-lg px-3 py-2 text-sm transition-colors ${
                                    isActive
                                        ? "bg-signal-500/10 text-signal-500 font-medium"
                                        : "text-mist-300 hover:bg-ink-850 hover:text-mist-100"
                                }`
                            }
                        >
                            {item.label}
                        </NavLink>
                    ))}
                </nav>

                <div className="mt-auto rounded-lg border border-ink-800 bg-ink-850 p-3 text-xs text-mist-500">
                    Risk scores are model estimates used to prioritize review —
                    they never determine fraud by themselves.
                </div>
            </aside>

            {/* Main column */}
            <div className="flex min-w-0 flex-1 flex-col">
                {/* Top bar */}
                <header className="flex items-center gap-3 border-b border-ink-800 bg-ink-900/70 px-4 py-3">
                    {/* Mobile nav */}
                    <div className="flex gap-1 md:hidden">
                        {NAV.map((item) => (
                            <NavLink
                                key={item.to}
                                to={item.to}
                                end={item.end}
                                className={({ isActive }) =>
                                    `rounded-md px-2 py-1 text-xs ${
                                        isActive ? "bg-signal-500/15 text-signal-500" : "text-mist-300"
                                    }`
                                }
                            >
                                {item.label}
                            </NavLink>
                        ))}
                    </div>

                    {/* Active case selector */}
                    <label className="ml-auto flex items-center gap-2 text-xs text-mist-500 md:ml-0">
                        Case
                        <select
                            className="input max-w-56 py-1 text-sm"
                            value={activeCaseId || ""}
                            onChange={(e) => setActiveCaseId(e.target.value)}
                            disabled={loading || cases.length === 0}
                        >
                            {cases.length === 0 && <option value="">No cases yet</option>}
                            {cases.map((c) => (
                                <option key={c.id} value={c.id}>
                                    {c.caseNumber} — {c.title}
                                </option>
                            ))}
                        </select>
                    </label>

                    {/* User menu */}
                    <div className="relative">
                        <button
                            type="button"
                            className="btn-ghost"
                            onClick={() => setMenuOpen((v) => !v)}
                        >
                            <span className="flex h-6 w-6 items-center justify-center rounded-full bg-ink-700 text-xs font-semibold text-mist-300">
                                {(user?.name || "?").slice(0, 1).toUpperCase()}
                            </span>
                            <span className="hidden sm:inline">{user?.name}</span>
                        </button>
                        {menuOpen && (
                            <div className="absolute right-0 z-20 mt-1 w-44 rounded-lg border border-ink-700 bg-ink-850 p-1 shadow-xl">
                                <p className="px-3 py-2 text-xs text-mist-500">{user?.email}</p>
                                <button
                                    type="button"
                                    className="w-full rounded-md px-3 py-2 text-left text-sm text-red-400 hover:bg-ink-800"
                                    onClick={() => {
                                        setMenuOpen(false);
                                        logout();
                                    }}
                                >
                                    Sign out
                                </button>
                            </div>
                        )}
                    </div>
                </header>

                <main className="min-w-0 flex-1 overflow-x-hidden p-4 md:p-6">{children}</main>
            </div>
        </div>
    );
}

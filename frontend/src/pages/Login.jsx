import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext.jsx";
import { errorMessage } from "../api/client.js";

export default function Login() {
    const { login, register } = useAuth();
    const navigate = useNavigate();
    const location = useLocation();
    const [mode, setMode] = useState("login");
    const [form, setForm] = useState({ name: "", email: "", password: "" });
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState(null);

    const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

    async function onSubmit(e) {
        e.preventDefault();
        setBusy(true);
        setError(null);
        try {
            if (mode === "login") {
                await login(form.email, form.password);
            } else {
                await register(form.name, form.email, form.password);
            }
            navigate(location.state?.from?.pathname || "/", { replace: true });
        } catch (err) {
            setError(errorMessage(err));
        } finally {
            setBusy(false);
        }
    }

    return (
        <div className="flex min-h-screen items-center justify-center bg-ink-950 p-4">
            <div className="w-full max-w-sm">
                <div className="mb-8 flex flex-col items-center gap-2 text-center">
                    <span className="flex h-12 w-12 items-center justify-center rounded-xl bg-signal-500/15 text-signal-500 text-xl font-bold">
                        F
                    </span>
                    <h1 className="text-2xl font-semibold">FraudLens</h1>
                    <p className="text-sm text-mist-500">
                        AI-powered financial fraud investigation
                    </p>
                </div>

                <div className="card">
                    <div className="mb-4 flex rounded-lg bg-ink-850 p-1 text-sm">
                        {["login", "register"].map((m) => (
                            <button
                                key={m}
                                type="button"
                                className={`flex-1 rounded-md py-1.5 capitalize transition-colors ${
                                    mode === m
                                        ? "bg-ink-700 font-medium text-mist-100"
                                        : "text-mist-500 hover:text-mist-300"
                                }`}
                                onClick={() => setMode(m)}
                            >
                                {m === "login" ? "Sign in" : "Create account"}
                            </button>
                        ))}
                    </div>

                    <form onSubmit={onSubmit} className="space-y-3">
                        {mode === "register" && (
                            <input
                                className="input w-full"
                                placeholder="Full name"
                                value={form.name}
                                onChange={set("name")}
                                required
                                minLength={2}
                            />
                        )}
                        <input
                            className="input w-full"
                            type="email"
                            placeholder="Email"
                            value={form.email}
                            onChange={set("email")}
                            required
                        />
                        <input
                            className="input w-full"
                            type="password"
                            placeholder="Password"
                            value={form.password}
                            onChange={set("password")}
                            required
                            minLength={mode === "register" ? 8 : 1}
                        />
                        {error && (
                            <p className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-400">
                                {error}
                            </p>
                        )}
                        <button type="submit" className="btn-primary w-full justify-center" disabled={busy}>
                            {busy
                                ? "Please wait…"
                                : mode === "login"
                                ? "Sign in"
                                : "Create account"}
                        </button>
                    </form>
                </div>

                <p className="mt-6 text-center text-xs text-mist-500">
                    Prototype access screen · sessions use the real backend auth API
                </p>
            </div>
        </div>
    );
}

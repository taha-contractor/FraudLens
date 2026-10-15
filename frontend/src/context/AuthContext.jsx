import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { tokenStore } from "../api/client.js";
import { auth as authApi } from "../api/endpoints.js";

/**
 * Session state: token in localStorage, user in memory (re-verified against
 * GET /auth/me on load so a tampered/stale token cannot fake a session).
 */

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
    const [user, setUser] = useState(null);
    const [ready, setReady] = useState(false);

    useEffect(() => {
        let alive = true;
        (async () => {
            if (!tokenStore.get()) {
                setReady(true);
                return;
            }
            try {
                const { user: u } = await authApi.me();
                if (alive) setUser(u);
            } catch {
                tokenStore.clear();
            }
            if (alive) setReady(true);
        })();
        return () => {
            alive = false;
        };
    }, []);

    useEffect(() => {
        const onUnauthorized = () => setUser(null);
        window.addEventListener("fraudlens:unauthorized", onUnauthorized);
        return () => window.removeEventListener("fraudlens:unauthorized", onUnauthorized);
    }, []);

    const login = useCallback(async (email, password) => {
        const { accessToken, user: u } = await authApi.login({ email, password });
        tokenStore.set(accessToken);
        setUser(u);
        return u;
    }, []);

    const register = useCallback(async (name, email, password) => {
        await authApi.register({ name, email, password });
        return login(email, password);
    }, [login]);

    const logout = useCallback(() => {
        tokenStore.clear();
        setUser(null);
    }, []);

    const value = useMemo(
        () => ({ user, ready, login, register, logout }),
        [user, ready, login, register, logout]
    );

    return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
    const ctx = useContext(AuthContext);
    if (!ctx) throw new Error("useAuth outside AuthProvider");
    return ctx;
}

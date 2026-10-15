import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { cases as casesApi } from "../api/endpoints.js";
import { useAuth } from "./AuthContext.jsx";

/**
 * Loads the cases the user can access and remembers the active case.
 * The active caseId scopes the dashboard, explorer, analytics and case
 * screens; it is restored from localStorage on reload.
 */

const CaseContext = createContext(null);
const STORE_KEY = "fraudlens.activeCase";

export function CaseProvider({ children }) {
    const { user } = useAuth();
    const [cases, setCases] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [activeCaseId, setActiveCaseIdState] = useState(() => localStorage.getItem(STORE_KEY) || "");

    const reload = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const { cases: list } = await casesApi.list();
            setCases(list);
            // Drop a stale selection the user can no longer access.
            if (activeCaseId && !list.some((c) => c.id === activeCaseId)) {
                setActiveCaseId("");
            } else if (!activeCaseId && list.length > 0) {
                setActiveCaseId(list[0].id);
            }
        } catch (err) {
            setError(err?.response?.data?.error?.message || "Could not load cases");
        } finally {
            setLoading(false);
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [user, activeCaseId]);

    useEffect(() => {
        reload();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [user?.id]);

    const setActiveCaseId = useCallback((id) => {
        setActiveCaseIdState(id);
        if (id) localStorage.setItem(STORE_KEY, id);
        else localStorage.removeItem(STORE_KEY);
    }, []);

    const activeCase = useMemo(
        () => cases.find((c) => c.id === activeCaseId) || null,
        [cases, activeCaseId]
    );

    const value = useMemo(
        () => ({ cases, activeCase, activeCaseId, setActiveCaseId, loading, error, reloadCases: reload }),
        [cases, activeCase, activeCaseId, setActiveCaseId, loading, error, reload]
    );

    return <CaseContext.Provider value={value}>{children}</CaseContext.Provider>;
}

export function useCases() {
    const ctx = useContext(CaseContext);
    if (!ctx) throw new Error("useCases outside CaseProvider");
    return ctx;
}

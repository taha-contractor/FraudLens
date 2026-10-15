import { useCallback, useEffect, useRef, useState } from "react";
import { errorMessage } from "../api/client.js";

/**
 * Minimal fetch hook with explicit loading / error / data states and a
 * reload() for mutations. Ignores results of unmounted or superseded calls.
 * `fetcher` should be a stable callback (useCallback) in the caller.
 */
export function useAsync(fetcher, deps = []) {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const seq = useRef(0);

    const run = useCallback(async () => {
        const ticket = ++seq.current;
        setLoading(true);
        setError(null);
        try {
            const result = await fetcher();
            if (ticket === seq.current) setData(result);
            return result;
        } catch (err) {
            if (ticket === seq.current) setError(errorMessage(err));
            return undefined;
        } finally {
            if (ticket === seq.current) setLoading(false);
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, deps);

    useEffect(() => {
        run();
    }, [run]);

    return { data, loading, error, reload: run, setData };
}

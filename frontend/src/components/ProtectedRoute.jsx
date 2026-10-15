import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext.jsx";
import { Spinner } from "./LoadingState.jsx";

export function ProtectedRoute({ children }) {
    const { user, ready } = useAuth();
    const location = useLocation();

    if (!ready) return <Spinner label="Restoring session…" />;
    if (!user) return <Navigate to="/login" replace state={{ from: location }} />;
    return children;
}

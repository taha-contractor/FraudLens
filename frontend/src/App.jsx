import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider } from "./context/AuthContext.jsx";
import { CaseProvider } from "./context/CaseContext.jsx";
import { ProtectedRoute } from "./components/ProtectedRoute.jsx";
import { Layout } from "./components/Layout.jsx";
import Login from "./pages/Login.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import TransactionExplorer from "./pages/TransactionExplorer.jsx";
import TransactionDetails from "./pages/TransactionDetails.jsx";
import Cases from "./pages/Cases.jsx";
import CaseWorkspace from "./pages/CaseWorkspace.jsx";
import Analytics from "./pages/Analytics.jsx";
import ModelInfo from "./pages/ModelInfo.jsx";
import NotFound from "./pages/NotFound.jsx";

function Shell({ children }) {
    return (
        <ProtectedRoute>
            <CaseProvider>
                <Layout>{children}</Layout>
            </CaseProvider>
        </ProtectedRoute>
    );
}

export default function App() {
    return (
        <BrowserRouter>
            <AuthProvider>
                <Routes>
                    <Route path="/login" element={<Login />} />
                    <Route path="/" element={<Shell><Dashboard /></Shell>} />
                    <Route path="/transactions" element={<Shell><TransactionExplorer /></Shell>} />
                    <Route
                        path="/transactions/:txnId"
                        element={<Shell><TransactionDetails /></Shell>}
                    />
                    <Route path="/cases" element={<Shell><Cases /></Shell>} />
                    <Route path="/cases/:caseId" element={<Shell><CaseWorkspace /></Shell>} />
                    <Route path="/analytics" element={<Shell><Analytics /></Shell>} />
                    <Route path="/model" element={<Shell><ModelInfo /></Shell>} />
                    <Route path="/404" element={<Shell><NotFound /></Shell>} />
                    <Route path="*" element={<Navigate to="/404" replace />} />
                </Routes>
            </AuthProvider>
        </BrowserRouter>
    );
}

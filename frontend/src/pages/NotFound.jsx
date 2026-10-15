import { Link } from "react-router-dom";
import { EmptyState } from "../components/EmptyState.jsx";

export default function NotFound() {
    return (
        <EmptyState
            title="Page not found"
            message="The screen you requested does not exist."
            action={
                <Link to="/" className="btn-primary">
                    Back to dashboard
                </Link>
            }
        />
    );
}

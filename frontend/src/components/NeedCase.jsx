import { Link } from "react-router-dom";
import { EmptyState } from "./EmptyState.jsx";

/** Shared guard for case-scoped screens when the user has no case selected. */
export function NeedCase() {
    return (
        <EmptyState
            title="No investigation case selected"
            message="FraudLens scopes every transaction, score and analytic to one case at a time. Create or open a case to begin."
            action={
                <Link to="/cases" className="btn-primary">
                    Go to cases
                </Link>
            }
        />
    );
}

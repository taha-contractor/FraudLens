import { Link } from "react-router-dom";
import { RiskBadge, StatusBadge } from "./ui.jsx";
import { formatAmount, formatDateTime, shortId } from "../utils/format.js";

/**
 * Case-scoped transaction table. Rows are always links into the detail view.
 * Column set is fixed so explorer and workspace stay visually identical.
 */
export function TransactionTable({ caseId, transactions, dense = false }) {
    return (
        <div className="overflow-x-auto">
            <table className="table-fl">
                <thead>
                    <tr>
                        <th>Transaction</th>
                        <th>Time</th>
                        <th className="text-right">Amount</th>
                        <th>Type</th>
                        <th>From → To</th>
                        <th>Status</th>
                        <th>Risk</th>
                    </tr>
                </thead>
                <tbody>
                    {transactions.map((t) => (
                        <tr key={t.id}>
                            <td>
                                <Link
                                    to={`/transactions/${t.id}?case=${caseId}`}
                                    className="font-medium text-signal-500 hover:underline"
                                >
                                    {t.transactionId}
                                </Link>
                            </td>
                            <td className={`whitespace-nowrap text-mist-300 ${dense ? "text-xs" : ""}`}>
                                {formatDateTime(t.timestamp)}
                            </td>
                            <td className="text-right tabular-nums">
                                {formatAmount(t.amount, t.currency)}
                            </td>
                            <td className="text-mist-300">{t.transactionType}</td>
                            <td className="whitespace-nowrap text-xs text-mist-500">
                                {shortId(t.sourceAccountId)} → {shortId(t.destinationAccountId)}
                            </td>
                            <td>
                                <StatusBadge status={t.status} />
                            </td>
                            <td>
                                <RiskBadge level={t.riskLevel} score={t.riskScore} />
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}

/**
 * ISOLATED PROTOTYPE MOCKS
 * ------------------------
 * These are the ONLY fabricated values in the frontend. Each is used where a
 * real backend endpoint does not (yet) exist, is clearly labeled in the UI as
 * "reference / not computed live", and is trivially replaceable by a real call
 * because it is read in exactly one place.
 *
 * NOTHING here is a fallback for a failed API call. If a real endpoint errors,
 * the screens show an ErrorState — never these fixtures.
 *
 * Replace plan:
 *   - MODEL_EVALUATION → a future GET /api/v1/risk/evaluation that reads the
 *     saved M5 metric reports from ml/artifacts/m5/.
 */

// Source: ml winner reports (M5). Static reference figures, NOT live stats.
// Represented as held-out test-set results of one experiment; never as a
// guarantee of real-world performance.
export const MODEL_EVALUATION = {
    label: "Held-out test set (single M5 experiment) — reference figures, not live or guaranteed real-world performance",
    metrics: [
        { name: "PR-AUC (average precision)", value: 0.6476 },
        { name: "ROC-AUC", value: 0.9845 },
        { name: "Recall @ threshold", value: 0.92 },
        { name: "Precision @ threshold", value: 0.36 },
    ],
    dataset: {
        description:
            "Enhanced PaySim-derived fraud dataset (8,362,620 transactions) with causal account-history features.",
        frozen: true,
    },
    limitations: [
        "Figures come from one training experiment on a synthetic/derived dataset; they do not guarantee performance on live bank data.",
        "Precision at the 0.95 threshold is low relative to recall: the model is tuned to surface candidates for review, not to confirm fraud.",
        "Historical features require prior in-case activity; brand-new accounts score with weaker signal.",
        "A HIGH classification is a prioritization signal only and is never a fraud determination.",
    ],
};

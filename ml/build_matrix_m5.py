"""One-shot driver: build the M5 model matrix with bounded memory.

Writes ml/data/processed/model_matrix_v1.csv plus a small summary JSON, using an
external step-partition sort (bounded RAM). Kept as a script so it can be re-run
deterministically without a shell one-liner.
"""

import json
import os
import tempfile

from features.matrix import build_matrix

TX = os.path.join("ml", "data", "processed", "enhanced_full", "enhanced_transactions.csv")
OUT = os.path.join("ml", "data", "processed", "model_matrix_v1.csv")
SUMMARY = os.path.join("ml", "reports", "m5", "matrix_build.json")

if __name__ == "__main__":
    os.makedirs(os.path.dirname(SUMMARY), exist_ok=True)
    with tempfile.TemporaryDirectory() as work:
        summary = build_matrix(TX, OUT, work)
    with open(SUMMARY, "w") as fh:
        json.dump(summary, fh, indent=2)
    print(json.dumps(summary))

"""Runtime configuration for the FraudLens ML inference service.

Reads a small, service-local .env (never the backend's) so the inference
component can run as an independent process. Only non-sensitive settings and a
MongoDB connection string are required; the model artifact is loaded read-only.
"""

from __future__ import annotations

import os
from pathlib import Path

SERVICE_DIR = Path(__file__).resolve().parent
REPO_ROOT = SERVICE_DIR.parent


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader (KEY=VALUE lines) so the service has no hard
    dependency on python-dotenv. Existing process environment always wins."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(SERVICE_DIR / ".env")

# --- model artifact (read-only; produced by the M5 finalizer) ---------------
MODEL_ARTIFACT_PATH = os.environ.get(
    "MODEL_ARTIFACT_PATH", str(REPO_ROOT / "ml" / "artifacts" / "m5" / "winner_model.joblib")
)
FEATURE_NAMES_PATH = os.environ.get(
    "FEATURE_NAMES_PATH", str(REPO_ROOT / "ml" / "artifacts" / "m5" / "feature_names.json")
)

# --- feature pipeline source of truth (M4 causal builder) -------------------
# The service imports the exact ml/src implementation rather than re-deriving
# the feature math, so online scoring cannot drift from training-time features.
ML_SRC_PATH = os.environ.get("ML_SRC_PATH", str(REPO_ROOT / "ml" / "src"))

# --- data store -------------------------------------------------------------
MONGODB_URI = os.environ.get("MONGODB_URI", "")
MONGODB_DB = os.environ.get("MONGODB_DB", "")  # empty -> use the URI's default db

# --- service ----------------------------------------------------------------
PORT = int(os.environ.get("ML_SERVICE_PORT", "8100"))
# Optional shared secret; when set, /score requires a matching X-ML-Token header.
ML_SERVICE_TOKEN = os.environ.get("ML_SERVICE_TOKEN", "")

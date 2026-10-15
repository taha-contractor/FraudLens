"""Launch the ML inference service for integration testing.

    python run_server.py [port]

Binds to 127.0.0.1 so the Node backend can reach a live service during focused
tests without any global install or shell-specific uvicorn invocation.
"""

from __future__ import annotations

import sys

import uvicorn

import config
from app import app


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else config.PORT
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()

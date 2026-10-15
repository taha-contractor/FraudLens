"""Deterministic random-seed handling (M2).

Every random stream derives from one master seed via a stable label, so a run is
fully reproducible and independent of wall-clock time or hidden global state.
"""

from __future__ import annotations

import hashlib

import numpy as np


def seed_for(label: str, master_seed: int) -> int:
    """Stable 64-bit seed for a named component under a master seed."""
    key = f"{int(master_seed)}::{label}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(key).digest()[:8], "big")


def make_rng(label: str, master_seed: int) -> np.random.Generator:
    """Return a NumPy Generator pinned to (master_seed, label)."""
    return np.random.default_rng(seed_for(label, master_seed))


def stable_id(prefix: str, label: str, master_seed: int, width: int = 16) -> str:
    """Deterministic opaque id (no wall-clock); same inputs always give same id."""
    h = hashlib.sha256(f"{int(master_seed)}::{label}".encode("utf-8")).hexdigest()[:width]
    return f"{prefix}{h}"


def generation_run_id(master_seed: int, config_version: str) -> str:
    return stable_id("run-", f"cfg={config_version}", master_seed, width=16)

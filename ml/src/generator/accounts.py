"""AccountRegistry skeleton (M2): deterministic ids + a consistent ledger.

Implements only what is needed to be testable now — reproducible account identifiers
in PaySim's format and a balance ledger that keeps `newbalance = oldbalance ± amount`
by construction (fixes L3 for generated data). Full transaction *emission* over these
accounts is M3 and is intentionally not implemented here.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import rng


class AccountError(ValueError):
    pass


def make_account_ids(kind: str, n: int, master_seed: int, label: str | None = None) -> list:
    """Deterministic, collision-free list of PaySim-format ids ('C'/'M' + 10 digits).

    Draws candidate numbers from a seeded stream and *rejects* duplicates until ``n``
    unique ids are collected. The id space (1e9..1e10) is far larger than any
    configured population, so this converges quickly, yet it is required: naive
    batch sampling collides with high probability once populations reach the
    hundreds of thousands (birthday paradox). Deterministic for a given
    (kind, n, seed, label), so re-runs reproduce the exact account set.
    """
    if kind not in {"C", "M"}:
        raise AccountError(f"account kind must be 'C' or 'M', got {kind!r}")
    if n <= 0:
        raise AccountError("n must be positive")
    label = label or f"accounts:{kind}:{n}"
    g = rng.make_rng(label, master_seed)
    lo, hi = 1_000_000_000, 10_000_000_000
    if n > (hi - lo):
        raise AccountError(f"n={n} exceeds available id space")
    seen: set = set()
    ids: list = []
    while len(ids) < n:
        need = n - len(ids)
        for x in g.integers(lo, hi, size=need + max(64, need // 8)):
            xi = int(x)
            if xi not in seen:
                seen.add(xi)
                ids.append(f"{kind}{xi}")
                if len(ids) == n:
                    break
    return ids


@dataclass
class LedgerAccount:
    account_id: str
    balance: float = 0.0

    def _apply(self, delta: float, tolerance: float) -> tuple:
        old = self.balance
        self.balance = round(old + delta, 2)
        new = self.balance
        assert abs((new - (old + delta)) - 0.0) <= tolerance + 1e-9
        return old, new

    def debit(self, amount: float, tolerance: float = 0.01) -> tuple:
        if amount < 0:
            raise AccountError("amount must be >= 0")
        return self._apply(-amount, tolerance)

    def credit(self, amount: float, tolerance: float = 0.01) -> tuple:
        if amount < 0:
            raise AccountError("amount must be >= 0")
        return self._apply(+amount, tolerance)


@dataclass
class AccountRegistry:
    master_seed: int
    n_origin: int
    n_dest: int
    origins: dict = field(default_factory=dict)
    destinations: dict = field(default_factory=dict)

    def __post_init__(self):
        self.origins = {a.account_id: a for a in
                        (LedgerAccount(i) for i in make_account_ids("C", self.n_origin, self.master_seed,
                                                                    label=f"origins:{self.n_origin}"))}
        self.destinations = {a.account_id: a for a in
                             (LedgerAccount(i) for i in make_account_ids("M", self.n_dest, self.master_seed,
                                                                         label=f"dests:{self.n_dest}"))}

    def origin_ids(self):
        return list(self.origins)

    def dest_ids(self):
        return list(self.destinations)

    def get(self, account_id: str) -> LedgerAccount:
        if account_id in self.origins:
            return self.origins[account_id]
        if account_id in self.destinations:
            return self.destinations[account_id]
        raise AccountError(f"unknown account {account_id!r}")

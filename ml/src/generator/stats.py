"""Bounded-memory statistics accumulator for the streaming generator (M3 scale-up).

The full-scale path streams ~2M generated records exactly once, so the §10 dataset
gates and the manifest summary cannot be computed from an in-memory list. This module
accumulates *all* the aggregates those checks need in a single pass, holding only
counters that are **O(accounts + scenarios + chains)**, not O(rows). Peak memory is
therefore independent of ``generated_rows``.

The one O(rows) structure — an exact ``record_uid`` duplicate scan — is opt-in
(``track_uids=True``, used by the small list path / tests). The streaming path relies
on structural uniqueness instead: a standalone uid is derived from the unique pair
``(scenario_id, idx)`` and a chain uid from a unique ``chain_id``, so generated uids
cannot collide by construction. This is documented precisely as the residual limit.
"""

from __future__ import annotations

from .schema import TRANSACTION_TYPES


class GenStats:
    __slots__ = (
        "total", "fraud", "type_counts", "fraud_by_type", "legit_by_type",
        "scenario_counts", "chain_rows", "chains", "neg_amount", "neg_oldbalance",
        "neg_newbalance", "bad_balance", "missing_scenario", "missing_uid",
        "bad_labels", "cols", "tol", "track_uids", "_uids", "dup_uids",
        "uids_scanned",
    )

    def __init__(self, tol: float = 0.01, track_uids: bool = False):
        self.total = 0
        self.fraud = 0
        self.type_counts = {t: 0 for t in TRANSACTION_TYPES}
        self.fraud_by_type = {t: 0 for t in TRANSACTION_TYPES}
        self.legit_by_type = {t: 0 for t in TRANSACTION_TYPES}
        self.scenario_counts: dict = {}
        self.chain_rows = 0
        self.chains: dict = {}  # chain_id -> [count, label, consistent]
        self.neg_amount = 0
        self.neg_oldbalance = 0
        self.neg_newbalance = 0
        self.bad_balance = 0
        self.missing_scenario = 0
        self.missing_uid = 0
        self.bad_labels: set = set()
        self.cols = None
        self.tol = tol
        self.track_uids = track_uids
        self._uids: set = set() if track_uids else None
        self.dup_uids = 0
        self.uids_scanned = 0

    def add(self, r: dict) -> None:
        if self.cols is None:
            self.cols = set(r)
        self.total += 1
        t = r["type"]
        self.type_counts[t] = self.type_counts.get(t, 0) + 1

        f = r["is_fraud"]
        if f == 1:
            self.fraud += 1
            self.fraud_by_type[t] = self.fraud_by_type.get(t, 0) + 1
        elif f == 0:
            self.legit_by_type[t] = self.legit_by_type.get(t, 0) + 1
        else:
            self.bad_labels.add(f)

        sid = r["scenario_id"]
        self.scenario_counts[sid] = self.scenario_counts.get(sid, 0) + 1
        if not sid:
            self.missing_scenario += 1

        cid = r.get("chain_id")
        if cid:
            self.chain_rows += 1
            entry = self.chains.get(cid)
            if entry is None:
                self.chains[cid] = [1, f, True]
            else:
                entry[0] += 1
                if entry[1] != f:
                    entry[2] = False

        amt = r["amount"]
        if amt is None or amt < 0:
            self.neg_amount += 1
        ob, nb = r["oldbalanceOrg"], r["newbalanceOrig"]
        if ob is None or ob < 0:
            self.neg_oldbalance += 1
        if nb is None or nb < 0:
            self.neg_newbalance += 1
        if amt is not None and ob is not None and nb is not None:
            delta = amt if t == "CASH_IN" else -amt
            if abs(ob + delta - nb) > self.tol + 1e-9:
                self.bad_balance += 1

        uid = r["record_uid"]
        if not uid:
            self.missing_uid += 1
        if self.track_uids:
            self.uids_scanned += 1
            if uid in self._uids:
                self.dup_uids += 1
            else:
                self._uids.add(uid)

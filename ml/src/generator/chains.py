"""ChainBuilder (M3): linked multi-transaction fraud chains.

Each chain shares one deterministic ``chain_id`` and carries a single, consistent
fraud label, so a related sequence (e.g. funnel-in then drain) can never straddle an
evaluation partition undetected (blocks L4 chain leakage). Chains are the generator's
*synthetic scenarios*, not validated real-world laundering patterns.
"""

from __future__ import annotations

from . import rng

# Chain templates: (name, [(type, scenario_id, role)]) where role marks the mule side.
# Both templates flow value TRANSFER -> CASH_OUT, the two types that actually carry
# fraud in PaySim; keeping chains inside these heavy-fraud types means chain rows fit
# within those types' fraud budgets and never inflate a rare-fraud type (CASH_IN/PAYMENT).
TEMPLATES = [
    ("transfer_cashout", [("TRANSFER", "TRF-F1", "victim_to_mule"),
                          ("CASH_OUT", "COUT-F2", "mule_drain")]),
    ("velocity_cashout", [("TRANSFER", "TRF-F3", "victim_to_mule"),
                          ("CASH_OUT", "COUT-F1", "mule_drain")]),
]


def new_chain_id(master_seed: int, label: str) -> str:
    """Deterministic opaque chain id for a given run + sequence position."""
    return rng.stable_id("chain-", label, master_seed, width=16)


class ChainBuilder:
    def __init__(self, master_seed: int):
        self.master_seed = int(master_seed)

    def build(self, count: int, origin_ids, ext_ids, master_seed: int,
              step_start: int, step_end: int):
        """Return ``count`` linked chains as provisional transaction dicts.

        Each chain yields one provisional row per template step, all sharing a
        ``chain_id`` and labelled fraud (is_fraud=1). Amounts/ordering are set so the
        ledger replay flows the funds in before draining them.
        """
        seed = int(master_seed)
        rows = []
        for i in range(count):
            g = rng.make_rng(f"chain:{i}", seed)
            cid = new_chain_id(seed, f"chain{i}")
            name, steps = TEMPLATES[i % len(TEMPLATES)]
            victim = origin_ids[i % len(origin_ids)]
            mule = origin_ids[(i + 7) % len(origin_ids)]
            ext = ext_ids[i % len(ext_ids)]
            step = int(g.integers(step_start, step_end + 1))
            amount = round(float(g.lognormal(mean=float(rng.np.log(2000.0)), sigma=1.1)), 2)
            for pos, (t, sid, role) in enumerate(steps):
                if role == "victim_to_mule":
                    orig, dest = victim, mule
                elif role == "mule_in":
                    orig, dest = mule, ext
                else:  # mule_drain
                    orig, dest = mule, ext
                rows.append({
                    "idx": pos, "step": step, "sec": 100 + pos * 600,  # in-precedes-out within the day
                    "type": t, "amount": amount, "nameOrig": orig, "nameDest": dest,
                    "is_fraud": 1, "scenario_id": sid, "chain_id": cid, "drain": False,
                })
        return rows

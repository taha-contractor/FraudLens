"""ScenarioLibrary (M2): documented fraud + legitimate scenario *definitions*.

These are **configurable simulation assumptions**, not validated real-world fraud
typologies. Every transaction type has both legitimate controls (including
"unusual but legal" cases) and fraud scenarios, so unusual activity alone does not
determine the label (counters L1 and shortcut learning). Emission is M3.
"""

from __future__ import annotations

import dataclasses

from .schema import TRANSACTION_TYPES


class ScenarioError(ValueError):
    pass


@dataclasses.dataclass(frozen=True)
class Scenario:
    scenario_id: str
    transaction_type: str
    is_fraud: bool
    description: str
    weight: float = 0.0  # 0 = unset; wired in M3


BASE_SCENARIOS = [
    # PAYMENT
    Scenario("PAY-L1", "PAYMENT", False, "routine small retail payment"),
    Scenario("PAY-L2", "PAYMENT", False, "recurring payment to a saved merchant"),
    Scenario("PAY-L3", "PAYMENT", False, "legitimate first-time high-value purchase (unusual but legal)"),
    Scenario("PAY-F1", "PAYMENT", True, "account-takeover payment to an atypical merchant"),
    Scenario("PAY-F2", "PAYMENT", True, "rapid payment burst following dormancy"),
    # CASH_IN
    Scenario("CIN-L1", "CASH_IN", False, "periodic salary / agent top-up deposit"),
    Scenario("CIN-L2", "CASH_IN", False, "legitimate cluster of large business deposits"),
    Scenario("CIN-F1", "CASH_IN", True, "structuring: many sub-threshold deposits into one account"),
    Scenario("CIN-F2", "CASH_IN", True, "funnel-in to a mule immediately before a drain (chain head)"),
    # CASH_OUT
    Scenario("COUT-L1", "CASH_OUT", False, "scheduled ATM/agent withdrawal within normal pattern"),
    Scenario("COUT-L2", "CASH_OUT", False, "legitimate large cash-out backed by prior balance build-up"),
    Scenario("COUT-F1", "CASH_OUT", True, "full-balance drain to zero"),
    Scenario("COUT-F2", "CASH_OUT", True, "rapid cash-out right after an inbound deposit (layering)"),
    Scenario("COUT-F3", "CASH_OUT", True, "many cash-outs converging on one agent/mule"),
    # TRANSFER
    Scenario("TRF-L1", "TRANSFER", False, "P2P transfer to a long-standing beneficiary"),
    Scenario("TRF-L2", "TRANSFER", False, "legitimate first transfer to a new beneficiary with steady balance"),
    Scenario("TRF-F1", "TRANSFER", True, "first transfer to a brand-new beneficiary then immediate cash-out"),
    Scenario("TRF-F2", "TRANSFER", True, "high-value balance-drain transfer"),
    Scenario("TRF-F3", "TRANSFER", True, "transfer-velocity spike in a short window"),
    # DEBIT
    Scenario("DEB-L1", "DEBIT", False, "recurring subscription / auto-debit"),
    Scenario("DEB-L2", "DEBIT", False, "legitimate utility debit with varying amount"),
    Scenario("DEB-F1", "DEBIT", True, "unauthorized recurring debit after credential theft"),
    Scenario("DEB-F2", "DEBIT", True, "anomalous merchant debit inconsistent with history"),
]


class ScenarioLibrary:
    def __init__(self, scenarios=None):
        self.scenarios = list(scenarios if scenarios is not None else BASE_SCENARIOS)
        self.by_id = {s.scenario_id: s for s in self.scenarios}

    def for_type(self, transaction_type: str, fraud: bool | None = None):
        out = [s for s in self.scenarios if s.transaction_type == transaction_type]
        if fraud is not None:
            out = [s for s in out if s.is_fraud == fraud]
        return out

    def for_all_legit(self):
        return [s for s in self.scenarios if not s.is_fraud]

    def validate(self) -> "ScenarioLibrary":
        ids = [s.scenario_id for s in self.scenarios]
        if len(ids) != len(set(ids)):
            raise ScenarioError("duplicate scenario_id detected")
        if len(ids) != len(self.by_id):
            raise ScenarioError("scenario_id map size mismatch")
        for t in TRANSACTION_TYPES:
            if not self.for_type(t, fraud=False):
                raise ScenarioError(f"type {t} has no legitimate scenario")
            if not self.for_type(t, fraud=True):
                raise ScenarioError(f"type {t} has no fraud scenario (L1 must be fixed for all types)")
        for s in self.scenarios:
            if s.transaction_type not in TRANSACTION_TYPES:
                raise ScenarioError(f"scenario {s.scenario_id} has invalid type {s.transaction_type}")
            if s.weight < 0:
                raise ScenarioError(f"scenario {s.scenario_id} has negative weight")
        return self

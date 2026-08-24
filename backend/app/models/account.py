from enum import Enum


class AccountType(str, Enum):
    CURRENT = "CURRENT"
    SAVINGS = "SAVINGS"
    BROKERAGE = "BROKERAGE"
    OTHER = "OTHER"


class AccountStatus(str, Enum):
    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"

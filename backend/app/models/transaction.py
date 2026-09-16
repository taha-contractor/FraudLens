from enum import Enum


class TransactionType(str, Enum):
    TRANSFER = "TRANSFER"
    PAYMENT = "PAYMENT"
    WITHDRAWAL = "WITHDRAWAL"
    DEPOSIT = "DEPOSIT"
    OTHER = "OTHER"


class TransactionStatus(str, Enum):
    PENDING = "PENDING"
    REVIEW = "REVIEW"
    CLEARED = "CLEARED"
    CONFIRMED_FRAUD = "CONFIRMED_FRAUD"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

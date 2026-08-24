from enum import Enum
from datetime import datetime, timezone


class CaseStatus(str, Enum):
    ACTIVE = "ACTIVE"
    PROCESSING = "PROCESSING"
    READY = "READY"
    UNDER_INVESTIGATION = "UNDER_INVESTIGATION"
    CLOSED = "CLOSED"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)

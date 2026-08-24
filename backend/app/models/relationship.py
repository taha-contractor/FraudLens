from enum import Enum


class RelationshipSource(str, Enum):
    DOCUMENT = "DOCUMENT"
    TRANSACTION = "TRANSACTION"
    USER = "USER"
    SYSTEM = "SYSTEM"


class RelationshipType(str, Enum):
    OWNS = "OWNS"
    CONTROLS = "CONTROLS"
    ASSOCIATED_WITH = "ASSOCIATED_WITH"
    HAS_ACCOUNT = "HAS_ACCOUNT"
    DIRECTOR_OF = "DIRECTOR_OF"
    EMPLOYEE_OF = "EMPLOYEE_OF"
    SUBSIDIARY_OF = "SUBSIDIARY_OF"
    RELATED_TO = "RELATED_TO"
    OTHER = "OTHER"

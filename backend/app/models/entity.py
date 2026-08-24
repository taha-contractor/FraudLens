from enum import Enum


class EntityType(str, Enum):
    PERSON = "PERSON"
    COMPANY = "COMPANY"
    BANK = "BANK"
    ORGANIZATION = "ORGANIZATION"
    OTHER = "OTHER"

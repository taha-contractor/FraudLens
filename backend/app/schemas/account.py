from typing import Optional, Any, Dict
from datetime import datetime
from pydantic import BaseModel, Field, field_validator
from app.models.account import AccountType, AccountStatus


class AccountCreate(BaseModel):
    accountId: str = Field(..., description="Unique account identifier")
    caseId: str = Field(..., description="Associated case identifier")
    accountNumber: Optional[str] = Field(default=None, description="Optional account number string")
    accountType: AccountType = Field(default=AccountType.CURRENT, description="Type of account")
    bankEntityId: Optional[str] = Field(default=None, description="Reference to BANK entity")
    ownerEntityId: Optional[str] = Field(default=None, description="Reference to owner entity")
    currency: str = Field(default="INR", description="Account currency")
    openingDate: Optional[datetime] = Field(default=None, description="Optional account opening date")
    closingDate: Optional[datetime] = Field(default=None, description="Optional account closing date")
    status: AccountStatus = Field(default=AccountStatus.ACTIVE, description="Status of account")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Flexible metadata")

    @field_validator("accountId", "caseId")
    @classmethod
    def trim_ids(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("id fields cannot be empty or blank")
        return v.strip()


class AccountResponse(BaseModel):
    accountId: str
    caseId: str
    accountNumber: Optional[str] = None
    accountType: AccountType
    bankEntityId: Optional[str] = None
    ownerEntityId: Optional[str] = None
    currency: str = "INR"
    openingDate: Optional[datetime] = None
    closingDate: Optional[datetime] = None
    status: AccountStatus
    metadata: Dict[str, Any] = {}
    createdAt: datetime
    updatedAt: datetime

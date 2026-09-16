from typing import Optional, Any, Dict
from datetime import datetime
from pydantic import BaseModel, Field, field_validator
from app.models.transaction import TransactionType, TransactionStatus, RiskLevel


class TransactionCreate(BaseModel):
    transactionId: str = Field(..., description="Unique transaction identifier")
    caseId: str = Field(..., description="Associated case identifier")
    accountId: Optional[str] = Field(default=None, description="Source account ID")
    destinationAccountId: Optional[str] = Field(default=None, description="Destination account ID")
    amount: float = Field(..., ge=0, description="Transaction amount (min 0)")
    currency: str = Field(default="INR", description="Transaction currency")
    transactionType: TransactionType = Field(..., description="Type of transaction")
    merchant: Optional[str] = Field(default=None, description="Merchant name")
    location: Optional[str] = Field(default=None, description="Transaction location")
    timestamp: datetime = Field(..., description="Transaction timestamp")
    status: TransactionStatus = Field(default=TransactionStatus.PENDING, description="Transaction status")
    fraudProbability: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Fraud probability (0.0 to 1.0)")
    riskLevel: Optional[RiskLevel] = Field(default=None, description="Assessed risk level")
    fraudPrediction: Optional[bool] = Field(default=None, description="ML prediction flag")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Flexible metadata")

    @field_validator("transactionId", "caseId")
    @classmethod
    def trim_ids(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("id fields cannot be empty or blank")
        return v.strip()


class TransactionResponse(BaseModel):
    transactionId: str
    caseId: str
    accountId: Optional[str] = None
    destinationAccountId: Optional[str] = None
    amount: float
    currency: str = "INR"
    transactionType: TransactionType
    merchant: Optional[str] = None
    location: Optional[str] = None
    timestamp: datetime
    status: TransactionStatus
    fraudProbability: Optional[float] = None
    riskLevel: Optional[RiskLevel] = None
    fraudPrediction: Optional[bool] = None
    metadata: Dict[str, Any] = {}
    createdAt: datetime
    updatedAt: datetime

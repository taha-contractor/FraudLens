from typing import Optional, Generic, TypeVar
from datetime import datetime
from pydantic import BaseModel, Field, field_validator
from app.models.case import CaseStatus

T = TypeVar("T")


class APIResponse(BaseModel, Generic[T]):
    success: bool = True
    message: str
    data: Optional[T] = None


class CaseCreate(BaseModel):
    caseId: str = Field(..., description="Unique case identifier")
    title: str = Field(..., description="Title of the case")
    description: str = Field(default="", description="Description of the case")
    status: CaseStatus = Field(default=CaseStatus.ACTIVE, description="Current status of the case")

    @field_validator("title")
    @classmethod
    def trim_title(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("title cannot be empty or blank")
        return v.strip()

    @field_validator("caseId")
    @classmethod
    def trim_case_id(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("caseId cannot be empty or blank")
        return v.strip()


class CaseUpdate(BaseModel):
    title: Optional[str] = Field(default=None, description="Title of the case")
    description: Optional[str] = Field(default=None, description="Description of the case")
    status: Optional[CaseStatus] = Field(default=None, description="Current status of the case")

    @field_validator("title")
    @classmethod
    def trim_title(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            if not v.strip():
                raise ValueError("title cannot be empty or blank")
            return v.strip()
        return v


class CaseResponse(BaseModel):
    caseId: str
    title: str
    description: str
    status: CaseStatus
    createdAt: datetime
    updatedAt: datetime

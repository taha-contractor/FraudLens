from typing import Optional, Generic, TypeVar, List, Any, Dict
from datetime import datetime
from pydantic import BaseModel, Field, field_validator
from app.models.entity import EntityType

T = TypeVar("T")


class ListAPIResponse(BaseModel, Generic[T]):
    success: bool = True
    message: str
    count: int
    data: List[T] = []


class EntityCreate(BaseModel):
    entityId: str = Field(..., description="Unique entity identifier")
    caseId: str = Field(..., description="Associated case identifier")
    entityType: EntityType = Field(..., description="Type of the entity")
    name: str = Field(..., description="Name of the entity")
    aliases: List[str] = Field(default_factory=list, description="List of entity aliases")
    description: str = Field(default="", description="Description of the entity")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional flexible metadata")

    @field_validator("name")
    @classmethod
    def trim_name(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("name cannot be empty or blank")
        return v.strip()

    @field_validator("entityId", "caseId")
    @classmethod
    def trim_ids(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("id fields cannot be empty or blank")
        return v.strip()


class EntityResponse(BaseModel):
    entityId: str
    caseId: str
    entityType: EntityType
    name: str
    aliases: List[str] = []
    description: str = ""
    metadata: Dict[str, Any] = {}
    createdAt: datetime
    updatedAt: datetime

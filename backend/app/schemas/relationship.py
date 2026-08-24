from typing import Optional, Any, Dict, List
from datetime import datetime
from pydantic import BaseModel, Field, field_validator
from app.models.relationship import RelationshipSource, RelationshipType


class RelationshipCreate(BaseModel):
    relationshipId: str = Field(..., description="Unique relationship identifier")
    caseId: str = Field(..., description="Associated case identifier")
    sourceEntityId: str = Field(..., description="Source entity ID")
    relationshipType: RelationshipType = Field(..., description="Type of relationship")
    targetEntityId: str = Field(..., description="Target entity ID")
    source: RelationshipSource = Field(default=RelationshipSource.SYSTEM, description="Source of relationship data")
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Confidence score between 0.0 and 1.0")
    evidence: List[Dict[str, Any]] = Field(default_factory=list, description="Extensible evidence objects")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Flexible metadata")

    @field_validator("relationshipId", "caseId", "sourceEntityId", "targetEntityId")
    @classmethod
    def trim_ids(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("id fields cannot be empty or blank")
        return v.strip()


class RelationshipResponse(BaseModel):
    relationshipId: str
    caseId: str
    sourceEntityId: str
    relationshipType: RelationshipType
    targetEntityId: str
    source: RelationshipSource
    confidence: Optional[float] = None
    evidence: List[Dict[str, Any]] = []
    metadata: Dict[str, Any] = {}
    createdAt: datetime
    updatedAt: datetime

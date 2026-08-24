from typing import Optional
from fastapi import APIRouter, HTTPException, status, Depends
from pymongo.errors import DuplicateKeyError

from app.core.database import (
    get_relationships_collection,
    get_entities_collection,
    get_cases_collection,
)
from app.models.case import utc_now
from app.schemas.relationship import (
    RelationshipCreate,
    RelationshipResponse,
)
from app.schemas.entity import ListAPIResponse
from app.schemas.case import APIResponse

router = APIRouter(prefix="/api/relationships", tags=["Relationships"])


def format_doc(doc: dict) -> dict:
    if doc:
        doc = dict(doc)
        doc.pop("_id", None)
    return doc


@router.post("", response_model=APIResponse[RelationshipResponse], status_code=status.HTTP_201_CREATED)
async def create_relationship(
    rel_in: RelationshipCreate,
    relationships_col=Depends(get_relationships_collection),
    entities_col=Depends(get_entities_collection),
    cases_col=Depends(get_cases_collection)
):
    # 1. Verify case existence
    case = await cases_col.find_one({"caseId": rel_in.caseId})
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case with caseId '{rel_in.caseId}' not found"
        )

    # 2. Check duplicate relationshipId
    existing = await relationships_col.find_one({"relationshipId": rel_in.relationshipId})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Relationship with relationshipId '{rel_in.relationshipId}' already exists"
        )

    # 3. Verify sourceEntityId
    source_entity = await entities_col.find_one({
        "entityId": rel_in.sourceEntityId,
        "caseId": rel_in.caseId
    })
    if not source_entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source entity '{rel_in.sourceEntityId}' not found in case '{rel_in.caseId}'"
        )

    # 4. Verify targetEntityId
    target_entity = await entities_col.find_one({
        "entityId": rel_in.targetEntityId,
        "caseId": rel_in.caseId
    })
    if not target_entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Target entity '{rel_in.targetEntityId}' not found in case '{rel_in.caseId}'"
        )

    now = utc_now()
    rel_doc = {
        "relationshipId": rel_in.relationshipId,
        "caseId": rel_in.caseId,
        "sourceEntityId": rel_in.sourceEntityId,
        "relationshipType": rel_in.relationshipType.value if hasattr(rel_in.relationshipType, "value") else rel_in.relationshipType,
        "targetEntityId": rel_in.targetEntityId,
        "source": rel_in.source.value if hasattr(rel_in.source, "value") else rel_in.source,
        "confidence": rel_in.confidence,
        "evidence": rel_in.evidence,
        "metadata": rel_in.metadata,
        "createdAt": now,
        "updatedAt": now,
    }

    try:
        await relationships_col.insert_one(rel_doc)
    except DuplicateKeyError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Relationship with relationshipId '{rel_in.relationshipId}' already exists"
        )

    saved = await relationships_col.find_one({"relationshipId": rel_in.relationshipId})
    return APIResponse(
        success=True,
        message="Relationship created successfully",
        data=format_doc(saved)
    )


@router.get("", response_model=ListAPIResponse[RelationshipResponse])
async def get_relationships(
    caseId: Optional[str] = None,
    relationships_col=Depends(get_relationships_collection),
    cases_col=Depends(get_cases_collection)
):
    query = {}
    if caseId:
        case = await cases_col.find_one({"caseId": caseId})
        if not case:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Case with caseId '{caseId}' not found"
            )
        query["caseId"] = caseId

    cursor = relationships_col.find(query)
    relationships = []
    async for doc in cursor:
        relationships.append(format_doc(doc))

    return ListAPIResponse(
        success=True,
        message="Relationships retrieved successfully",
        count=len(relationships),
        data=relationships
    )

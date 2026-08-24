from typing import Optional
from fastapi import APIRouter, HTTPException, status, Depends
from pymongo.errors import DuplicateKeyError

from app.core.database import get_entities_collection, get_cases_collection
from app.models.case import utc_now
from app.schemas.entity import (
    EntityCreate,
    EntityResponse,
    ListAPIResponse,
)
from app.schemas.case import APIResponse

router = APIRouter(prefix="/api/entities", tags=["Entities"])


def format_doc(doc: dict) -> dict:
    if doc:
        doc = dict(doc)
        doc.pop("_id", None)
    return doc


@router.post("", response_model=APIResponse[EntityResponse], status_code=status.HTTP_201_CREATED)
async def create_entity(
    entity_in: EntityCreate,
    entities_col=Depends(get_entities_collection),
    cases_col=Depends(get_cases_collection)
):
    # 1. Verify case existence
    case = await cases_col.find_one({"caseId": entity_in.caseId})
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case with caseId '{entity_in.caseId}' not found"
        )

    # 2. Check duplicate entityId
    existing = await entities_col.find_one({"entityId": entity_in.entityId})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Entity with entityId '{entity_in.entityId}' already exists"
        )

    now = utc_now()
    entity_doc = {
        "entityId": entity_in.entityId,
        "caseId": entity_in.caseId,
        "entityType": entity_in.entityType.value if hasattr(entity_in.entityType, "value") else entity_in.entityType,
        "name": entity_in.name,
        "aliases": entity_in.aliases,
        "description": entity_in.description,
        "metadata": entity_in.metadata,
        "createdAt": now,
        "updatedAt": now,
    }

    try:
        await entities_col.insert_one(entity_doc)
    except DuplicateKeyError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Entity with entityId '{entity_in.entityId}' already exists"
        )

    saved = await entities_col.find_one({"entityId": entity_in.entityId})
    return APIResponse(
        success=True,
        message="Entity created successfully",
        data=format_doc(saved)
    )


@router.get("", response_model=ListAPIResponse[EntityResponse])
async def get_entities(
    caseId: Optional[str] = None,
    entities_col=Depends(get_entities_collection),
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

    cursor = entities_col.find(query)
    entities = []
    async for doc in cursor:
        entities.append(format_doc(doc))

    return ListAPIResponse(
        success=True,
        message="Entities retrieved successfully",
        count=len(entities),
        data=entities
    )


@router.get("/{entityId}", response_model=APIResponse[EntityResponse])
async def get_entity_by_id(
    entityId: str,
    entities_col=Depends(get_entities_collection)
):
    doc = await entities_col.find_one({"entityId": entityId})
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Entity with entityId '{entityId}' not found"
        )

    return APIResponse(
        success=True,
        message="Entity retrieved successfully",
        data=format_doc(doc)
    )

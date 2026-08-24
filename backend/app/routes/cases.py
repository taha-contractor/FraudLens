from typing import List
from fastapi import APIRouter, HTTPException, status, Depends
from pymongo.errors import DuplicateKeyError

from app.core.database import get_cases_collection
from app.models.case import utc_now
from app.schemas.case import (
    CaseCreate,
    CaseUpdate,
    CaseResponse,
    APIResponse,
)

router = APIRouter(prefix="/api/cases", tags=["Cases"])


def format_case_doc(doc: dict) -> dict:
    """Helper to sanitize MongoDB document for CaseResponse schema."""
    if doc and "_id" in doc:
        doc.pop("_id", None)
    return doc


@router.post("", response_model=APIResponse[CaseResponse], status_code=status.HTTP_201_CREATED)
async def create_case(case_in: CaseCreate, collection=Depends(get_cases_collection)):
    # Check if caseId already exists
    existing = await collection.find_one({"caseId": case_in.caseId})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Case with caseId '{case_in.caseId}' already exists"
        )

    now = utc_now()
    case_doc = {
        "caseId": case_in.caseId,
        "title": case_in.title,
        "description": case_in.description,
        "status": case_in.status.value if hasattr(case_in.status, "value") else case_in.status,
        "createdAt": now,
        "updatedAt": now,
    }

    try:
        await collection.insert_one(case_doc)
    except DuplicateKeyError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Case with caseId '{case_in.caseId}' already exists"
        )

    saved_doc = await collection.find_one({"caseId": case_in.caseId})
    formatted = format_case_doc(saved_doc)

    return APIResponse(
        success=True,
        message="Case created successfully",
        data=formatted
    )


@router.get("", response_model=APIResponse[List[CaseResponse]])
async def get_all_cases(collection=Depends(get_cases_collection)):
    cursor = collection.find({})
    cases = []
    async for doc in cursor:
        cases.append(format_case_doc(doc))

    return APIResponse(
        success=True,
        message="Cases retrieved successfully",
        data=cases
    )


@router.get("/{caseId}", response_model=APIResponse[CaseResponse])
async def get_case_by_id(caseId: str, collection=Depends(get_cases_collection)):
    doc = await collection.find_one({"caseId": caseId})
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case with caseId '{caseId}' not found"
        )

    return APIResponse(
        success=True,
        message="Case retrieved successfully",
        data=format_case_doc(doc)
    )


@router.patch("/{caseId}", response_model=APIResponse[CaseResponse])
async def update_case(
    caseId: str,
    case_update: CaseUpdate,
    collection=Depends(get_cases_collection)
):
    doc = await collection.find_one({"caseId": caseId})
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case with caseId '{caseId}' not found"
        )

    update_data = case_update.model_dump(exclude_unset=True)
    if not update_data:
        return APIResponse(
            success=True,
            message="No fields to update",
            data=format_case_doc(doc)
        )

    if "status" in update_data and hasattr(update_data["status"], "value"):
        update_data["status"] = update_data["status"].value

    update_data["updatedAt"] = utc_now()

    await collection.update_one({"caseId": caseId}, {"$set": update_data})

    updated_doc = await collection.find_one({"caseId": caseId})

    return APIResponse(
        success=True,
        message="Case updated successfully",
        data=format_case_doc(updated_doc)
    )

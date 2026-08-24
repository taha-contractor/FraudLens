from typing import Optional
from fastapi import APIRouter, HTTPException, status, Depends
from pymongo.errors import DuplicateKeyError

from app.core.database import (
    get_accounts_collection,
    get_entities_collection,
    get_cases_collection,
)
from app.models.case import utc_now
from app.schemas.account import (
    AccountCreate,
    AccountResponse,
)
from app.schemas.entity import ListAPIResponse
from app.schemas.case import APIResponse

router = APIRouter(prefix="/api/accounts", tags=["Accounts"])


def format_doc(doc: dict) -> dict:
    if doc:
        doc = dict(doc)
        doc.pop("_id", None)
    return doc


@router.post("", response_model=APIResponse[AccountResponse], status_code=status.HTTP_201_CREATED)
async def create_account(
    account_in: AccountCreate,
    accounts_col=Depends(get_accounts_collection),
    entities_col=Depends(get_entities_collection),
    cases_col=Depends(get_cases_collection)
):
    # 1. Verify case existence
    case = await cases_col.find_one({"caseId": account_in.caseId})
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case with caseId '{account_in.caseId}' not found"
        )

    # 2. Check duplicate accountId
    existing = await accounts_col.find_one({"accountId": account_in.accountId})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Account with accountId '{account_in.accountId}' already exists"
        )

    # 3. Verify ownerEntityId if provided
    if account_in.ownerEntityId:
        owner = await entities_col.find_one({
            "entityId": account_in.ownerEntityId,
            "caseId": account_in.caseId
        })
        if not owner:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Owner entity '{account_in.ownerEntityId}' not found in case '{account_in.caseId}'"
            )

    # 4. Verify bankEntityId if provided
    if account_in.bankEntityId:
        bank = await entities_col.find_one({
            "entityId": account_in.bankEntityId,
            "caseId": account_in.caseId
        })
        if not bank:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Bank entity '{account_in.bankEntityId}' not found in case '{account_in.caseId}'"
            )

    now = utc_now()
    account_doc = {
        "accountId": account_in.accountId,
        "caseId": account_in.caseId,
        "accountNumber": account_in.accountNumber,
        "accountType": account_in.accountType.value if hasattr(account_in.accountType, "value") else account_in.accountType,
        "bankEntityId": account_in.bankEntityId,
        "ownerEntityId": account_in.ownerEntityId,
        "currency": account_in.currency,
        "openingDate": account_in.openingDate,
        "closingDate": account_in.closingDate,
        "status": account_in.status.value if hasattr(account_in.status, "value") else account_in.status,
        "metadata": account_in.metadata,
        "createdAt": now,
        "updatedAt": now,
    }

    try:
        await accounts_col.insert_one(account_doc)
    except DuplicateKeyError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Account with accountId '{account_in.accountId}' already exists"
        )

    saved = await accounts_col.find_one({"accountId": account_in.accountId})
    return APIResponse(
        success=True,
        message="Account created successfully",
        data=format_doc(saved)
    )


@router.get("", response_model=ListAPIResponse[AccountResponse])
async def get_accounts(
    caseId: Optional[str] = None,
    accounts_col=Depends(get_accounts_collection),
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

    cursor = accounts_col.find(query)
    accounts = []
    async for doc in cursor:
        accounts.append(format_doc(doc))

    return ListAPIResponse(
        success=True,
        message="Accounts retrieved successfully",
        count=len(accounts),
        data=accounts
    )


@router.get("/{accountId}", response_model=APIResponse[AccountResponse])
async def get_account_by_id(
    accountId: str,
    accounts_col=Depends(get_accounts_collection)
):
    doc = await accounts_col.find_one({"accountId": accountId})
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account with accountId '{accountId}' not found"
        )

    return APIResponse(
        success=True,
        message="Account retrieved successfully",
        data=format_doc(doc)
    )

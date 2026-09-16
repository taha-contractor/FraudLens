from typing import Optional
from fastapi import APIRouter, HTTPException, status, Depends
from pymongo.errors import DuplicateKeyError

from app.core.database import (
    get_transactions_collection,
    get_accounts_collection,
    get_cases_collection,
)
from app.models.case import utc_now
from app.schemas.transaction import (
    TransactionCreate,
    TransactionResponse,
)
from app.schemas.entity import ListAPIResponse
from app.schemas.case import APIResponse

router = APIRouter(prefix="/api/transactions", tags=["Transactions"])


def format_doc(doc: dict) -> dict:
    if doc:
        doc = dict(doc)
        doc.pop("_id", None)
    return doc


@router.post("", response_model=APIResponse[TransactionResponse], status_code=status.HTTP_201_CREATED)
async def create_transaction(
    tx_in: TransactionCreate,
    tx_col=Depends(get_transactions_collection),
    accounts_col=Depends(get_accounts_collection),
    cases_col=Depends(get_cases_collection)
):
    # 1. Verify case existence
    case = await cases_col.find_one({"caseId": tx_in.caseId})
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case with caseId '{tx_in.caseId}' not found"
        )

    # 2. Check duplicate transactionId
    existing = await tx_col.find_one({"transactionId": tx_in.transactionId})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Transaction with transactionId '{tx_in.transactionId}' already exists"
        )

    # 3. Verify source accountId if supplied (must belong to same caseId)
    if tx_in.accountId:
        acc = await accounts_col.find_one({
            "accountId": tx_in.accountId,
            "caseId": tx_in.caseId
        })
        if not acc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Source account '{tx_in.accountId}' not found in case '{tx_in.caseId}'"
            )

    # 4. Verify destinationAccountId if supplied (must belong to same caseId)
    if tx_in.destinationAccountId:
        dest_acc = await accounts_col.find_one({
            "accountId": tx_in.destinationAccountId,
            "caseId": tx_in.caseId
        })
        if not dest_acc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Destination account '{tx_in.destinationAccountId}' not found in case '{tx_in.caseId}'"
            )

    now = utc_now()
    tx_doc = {
        "transactionId": tx_in.transactionId,
        "caseId": tx_in.caseId,
        "accountId": tx_in.accountId,
        "destinationAccountId": tx_in.destinationAccountId,
        "amount": tx_in.amount,
        "currency": tx_in.currency,
        "transactionType": tx_in.transactionType.value if hasattr(tx_in.transactionType, "value") else tx_in.transactionType,
        "merchant": tx_in.merchant,
        "location": tx_in.location,
        "timestamp": tx_in.timestamp,
        "status": tx_in.status.value if hasattr(tx_in.status, "value") else tx_in.status,
        "fraudProbability": tx_in.fraudProbability,
        "riskLevel": tx_in.riskLevel.value if (tx_in.riskLevel and hasattr(tx_in.riskLevel, "value")) else tx_in.riskLevel,
        "fraudPrediction": tx_in.fraudPrediction,
        "metadata": tx_in.metadata,
        "createdAt": now,
        "updatedAt": now,
    }

    try:
        await tx_col.insert_one(tx_doc)
    except DuplicateKeyError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Transaction with transactionId '{tx_in.transactionId}' already exists"
        )

    saved = await tx_col.find_one({"transactionId": tx_in.transactionId})
    return APIResponse(
        success=True,
        message="Transaction created successfully",
        data=format_doc(saved)
    )


@router.get("", response_model=ListAPIResponse[TransactionResponse])
async def get_transactions(
    caseId: Optional[str] = None,
    tx_col=Depends(get_transactions_collection),
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

    cursor = tx_col.find(query).sort("timestamp", -1)
    transactions = []
    async for doc in cursor:
        transactions.append(format_doc(doc))

    return ListAPIResponse(
        success=True,
        message="Transactions retrieved successfully",
        count=len(transactions),
        data=transactions
    )


@router.get("/{transactionId}", response_model=APIResponse[TransactionResponse])
async def get_transaction_by_id(
    transactionId: str,
    tx_col=Depends(get_transactions_collection)
):
    doc = await tx_col.find_one({"transactionId": transactionId})
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transaction with transactionId '{transactionId}' not found"
        )

    return APIResponse(
        success=True,
        message="Transaction retrieved successfully",
        data=format_doc(doc)
    )

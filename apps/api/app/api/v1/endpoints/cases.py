import math
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pymongo.asynchronous.database import AsyncDatabase

from app.core.dependencies import get_current_user_id, get_db
from app.models.case import CaseDocument, CaseStatus
from app.schemas.case import (
    CaseCreateRequest,
    CaseListResponse,
    CaseResponse,
    PaginationMeta,
)
from app.schemas.common import APIResponse

router = APIRouter(prefix="/cases", tags=["cases"])


@router.post("", response_model=APIResponse[CaseResponse], status_code=status.HTTP_201_CREATED)
async def create_case(
    payload: CaseCreateRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncDatabase = Depends(get_db),
):
    """Creates a new incident analysis Case scoped strictly to the current user."""
    doc = CaseDocument(
        user_id=user_id,
        title=payload.title,
        description=payload.description or "",
        tags=payload.tags or [],
        metadata=payload.metadata or {},
    )

    doc_dict = doc.model_dump()
    await db.cases.insert_one(doc_dict)

    response_data = CaseResponse(**doc_dict)
    return APIResponse(data=response_data)


@router.get("", response_model=APIResponse[CaseListResponse])
async def list_cases(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    status: Optional[CaseStatus] = Query(None, description="Filter by case status"),
    user_id: str = Depends(get_current_user_id),
    db: AsyncDatabase = Depends(get_db),
):
    """Retrieves a paginated list of cases belonging to the current user."""
    query: dict = {"user_id": user_id}
    if status is not None:
        query["status"] = status.value

    total = await db.cases.count_documents(query)
    pages = math.ceil(total / limit) if total > 0 else 0

    cursor = (
        db.cases.find(query)
        .sort([("created_at", -1), ("_id", -1)])
        .skip((page - 1) * limit)
        .limit(limit)
    )

    items = []
    async for row in cursor:
        items.append(CaseResponse(**row))

    pagination = PaginationMeta(
        page=page,
        limit=limit,
        total=total,
        pages=pages,
    )

    return APIResponse(data=CaseListResponse(items=items, pagination=pagination))


@router.get("/{case_id}", response_model=APIResponse[CaseResponse])
async def get_case(
    case_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncDatabase = Depends(get_db),
):
    """Retrieves an existing case by ID, enforcing user isolation."""
    case_row = await db.cases.find_one({"case_id": case_id, "user_id": user_id})
    if not case_row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case '{case_id}' was not found",
        )

    return APIResponse(data=CaseResponse(**case_row))

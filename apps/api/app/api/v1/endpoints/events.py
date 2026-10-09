import math
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pymongo.asynchronous.database import AsyncDatabase

from app.core.dependencies import get_current_user_id, get_db
from app.schemas.case import PaginationMeta
from app.schemas.common import APIResponse
from app.schemas.event import EventListResponse, EventResponse

router = APIRouter(prefix="/cases/{case_id}", tags=["events"])


async def _verify_case_ownership(case_id: str, user_id: str, db: AsyncDatabase) -> dict:
    """Verifies that the target case exists and belongs strictly to the authenticated user."""
    case_row = await db.cases.find_one({"case_id": case_id, "user_id": user_id})
    if not case_row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case '{case_id}' was not found",
        )
    return case_row


@router.get("/events", response_model=APIResponse[EventListResponse])
async def list_case_events(
    case_id: str,
    evidence_id: Optional[str] = Query(None, description="Optional filter by specific evidence document"),
    decision_state: Optional[str] = Query(None, description="Filter by decision state: 'VALIDATED' or 'REVIEW_NEEDED'"),
    event_type: Optional[str] = Query(None, description="Filter by canonical event type e.g. ORDER_PLACED"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    user_id: str = Depends(get_current_user_id),
    db: AsyncDatabase = Depends(get_db),
):
    """Retrieves paginated extracted events across the entire case, with optional evidence and state filtering."""
    await _verify_case_ownership(case_id, user_id, db)

    query: dict = {"case_id": case_id, "user_id": user_id}
    if evidence_id:
        query["evidence_id"] = evidence_id
    if decision_state:
        query["decision_state"] = decision_state
    if event_type:
        query["event_type"] = event_type

    total = await db.events.count_documents(query)
    pages = math.ceil(total / limit) if total > 0 else 0

    cursor = (
        db.events.find(query)
        .sort([("created_at", -1), ("_id", -1)])
        .skip((page - 1) * limit)
        .limit(limit)
    )

    items = []
    async for row in cursor:
        items.append(EventResponse(**row))

    pagination = PaginationMeta(page=page, limit=limit, total=total, pages=pages)
    return APIResponse(data=EventListResponse(items=items, pagination=pagination))


@router.get("/evidence/{evidence_id}/events", response_model=APIResponse[EventListResponse])
async def list_evidence_specific_events(
    case_id: str,
    evidence_id: str,
    decision_state: Optional[str] = Query(None, description="Filter by decision state: 'VALIDATED' or 'REVIEW_NEEDED'"),
    event_type: Optional[str] = Query(None, description="Filter by canonical event type e.g. ORDER_PLACED"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    user_id: str = Depends(get_current_user_id),
    db: AsyncDatabase = Depends(get_db),
):
    """Retrieves paginated extracted events originating strictly from a specific evidence asset."""
    await _verify_case_ownership(case_id, user_id, db)

    # Verify evidence asset exists in this case
    evi_row = await db.evidence.find_one({"evidence_id": evidence_id, "case_id": case_id, "user_id": user_id})
    if not evi_row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evidence '{evidence_id}' was not found in case '{case_id}'",
        )

    query: dict = {"case_id": case_id, "evidence_id": evidence_id, "user_id": user_id}
    if decision_state:
        query["decision_state"] = decision_state
    if event_type:
        query["event_type"] = event_type

    total = await db.events.count_documents(query)
    pages = math.ceil(total / limit) if total > 0 else 0

    cursor = (
        db.events.find(query)
        .sort([("created_at", -1), ("_id", -1)])
        .skip((page - 1) * limit)
        .limit(limit)
    )

    items = []
    async for row in cursor:
        items.append(EventResponse(**row))

    pagination = PaginationMeta(page=page, limit=limit, total=total, pages=pages)
    return APIResponse(data=EventListResponse(items=items, pagination=pagination))

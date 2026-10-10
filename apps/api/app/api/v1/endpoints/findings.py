from fastapi import APIRouter, Depends, HTTPException, status
from pymongo.asynchronous.database import AsyncDatabase

from app.core.dependencies import get_current_user_id, get_db
from app.schemas.common import APIResponse
from app.schemas.finding import FindingListResponse
from app.schemas.review import (
    FindingReviewCreateRequest,
    FindingReviewHistoryResponse,
    FindingReviewListResponse,
    FindingReviewResponse,
)
from app.services.finding_service import FindingService
from app.services.review_service import ReviewService

router = APIRouter(prefix="/cases/{case_id}", tags=["findings"])


async def _verify_case_ownership(case_id: str, user_id: str, db: AsyncDatabase) -> dict:
    """Verifies that the target case exists and belongs strictly to the authenticated user."""
    case_row = await db.cases.find_one({"case_id": case_id, "user_id": user_id})
    if not case_row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case '{case_id}' was not found",
        )
    return case_row


@router.get("/findings", response_model=APIResponse[FindingListResponse])
async def get_case_findings(
    case_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncDatabase = Depends(get_db),
):
    """Computes on-demand, source-grounded findings across active evidence documents for the case.

    Strictly enforces case ownership and active-processing-version isolation.
    """
    await _verify_case_ownership(case_id, user_id, db)
    findings_data = await FindingService.compute_case_findings(
        case_id=case_id,
        user_id=user_id,
        db=db,
    )
    return APIResponse(data=findings_data)


@router.get("/reviews", response_model=APIResponse[FindingReviewListResponse])
async def list_case_reviews(
    case_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncDatabase = Depends(get_db),
):
    """Lists human review decisions recorded for the specified case."""
    reviews_data = await ReviewService.list_case_reviews(
        case_id=case_id,
        user_id=user_id,
        db=db,
    )
    return APIResponse(data=reviews_data)


@router.post(
    "/findings/{finding_id}/review",
    response_model=APIResponse[FindingReviewResponse],
    status_code=status.HTTP_200_OK,
)
async def record_finding_review(
    case_id: str,
    finding_id: str,
    payload: FindingReviewCreateRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncDatabase = Depends(get_db),
):
    """Adjudicates a finding with a human review decision.

    Guarantees:
    - Reviewer identity is verified from authenticated token/principal.
    - Tenant isolation: only the case owner can adjudicate findings.
    - Finding must belong to the specified case.
    - Dismissal must include a reason.
    - Idempotent repeated submissions prevent duplicate active reviews.
    - Revision history is durably preserved.
    - ML model confidence and extracted evidence are never modified.
    """
    review_record = await ReviewService.record_finding_review(
        case_id=case_id,
        finding_id=finding_id,
        reviewer_id=user_id,
        request=payload,
        db=db,
    )
    return APIResponse(data=review_record)


@router.get(
    "/findings/{finding_id}/reviews",
    response_model=APIResponse[FindingReviewHistoryResponse],
)
async def get_finding_review_history(
    case_id: str,
    finding_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncDatabase = Depends(get_db),
):
    """Retrieves full decision history and audit trail for a specific finding."""
    history_data = await ReviewService.get_finding_review_history(
        case_id=case_id,
        finding_id=finding_id,
        user_id=user_id,
        db=db,
    )
    return APIResponse(data=history_data)

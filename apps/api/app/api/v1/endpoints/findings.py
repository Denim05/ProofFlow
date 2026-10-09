from fastapi import APIRouter, Depends, HTTPException, status
from pymongo.asynchronous.database import AsyncDatabase

from app.core.dependencies import get_current_user_id, get_db
from app.schemas.common import APIResponse
from app.schemas.finding import FindingListResponse
from app.services.finding_service import FindingService

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

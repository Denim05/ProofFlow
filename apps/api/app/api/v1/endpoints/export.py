import re
from fastapi import APIRouter, Depends, HTTPException, Response, status
from pymongo.asynchronous.database import AsyncDatabase

from app.core.dependencies import get_current_user_id, get_db
from app.core.rate_limiter import rate_limit_dossier_pdf
from app.schemas.dossier import DossierResponse
from app.services.dossier_service import DossierService

router = APIRouter(prefix="/cases/{case_id}/export", tags=["export"])


def _sanitize_filename_component(name: str) -> str:
    """Sanitizes user input to form a secure, ASCII-safe download filename."""
    cleaned = re.sub(r"[^a-zA-Z0-9_\-]", "_", name).strip("_")
    return cleaned or "case"


async def _verify_case_ownership(case_id: str, user_id: str, db: AsyncDatabase) -> dict:
    """Verifies that the target case exists and belongs strictly to the authenticated user."""
    case_row = await db.cases.find_one({"case_id": case_id, "user_id": user_id})
    if not case_row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case '{case_id}' was not found",
        )
    return case_row


@router.get("/json", response_model=DossierResponse)
async def export_case_dossier_json(
    case_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncDatabase = Depends(get_db),
):
    """Generates and exports an authoritative, machine-readable JSON dispute dossier.

    Enforces case ownership, consistent data snapshotting, and strict exclusion of internal credentials.
    """
    await _verify_case_ownership(case_id, user_id, db)

    try:
        dossier = await DossierService.build_dossier_data(case_id, user_id, db)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    safe_id = _sanitize_filename_component(case_id)
    filename = f"proofflow_dossier_{safe_id}.json"

    json_bytes = dossier.model_dump_json(indent=2).encode("utf-8")

    return Response(
        content=json_bytes,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store, no-cache, must-revalidate",
        },
    )


@router.get("/pdf", dependencies=[Depends(rate_limit_dossier_pdf)])
async def export_case_dossier_pdf(
    case_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncDatabase = Depends(get_db),
):
    """Generates and streams a publication-grade, evidence-grounded PDF dispute dossier.

    Renders document inventory, chronological timeline, cross-examination findings with source citations,
    human review decision history, and mandatory evidence-review disclosures.
    """
    await _verify_case_ownership(case_id, user_id, db)

    try:
        dossier = await DossierService.build_dossier_data(case_id, user_id, db)
        pdf_bytes = DossierService.generate_dossier_pdf(dossier)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    safe_id = _sanitize_filename_component(case_id)
    filename = f"proofflow_dossier_{safe_id}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store, no-cache, must-revalidate",
        },
    )

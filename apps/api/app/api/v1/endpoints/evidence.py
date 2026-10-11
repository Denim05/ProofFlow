import math
import os
import re
from typing import Optional
from urllib.parse import quote
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from pymongo.asynchronous.database import AsyncDatabase

from app.core.dependencies import get_current_user_id, get_db
from app.models.case import CaseStatus
from app.models.common import utc_now
from app.models.evidence import (
    EvidenceDocument,
    EvidenceStatus,
    generate_evidence_id,
)
from app.schemas.case import PaginationMeta
from app.schemas.common import APIResponse
from app.schemas.evidence import (
    EvidenceListResponse,
    EvidenceResponse,
    EvidenceUploadResponse,
)
from app.services.evidence_processor import (
    ProcessingJob,
    evidence_processing_service,
)
from app.core.rate_limiter import rate_limit_evidence_upload
from app.services.storage import storage_service

router = APIRouter(prefix="/cases/{case_id}/evidence", tags=["evidence"])


async def _verify_case_ownership(case_id: str, user_id: str, db: AsyncDatabase) -> dict:
    """Verifies that the target case exists and belongs strictly to the authenticated user."""
    case_row = await db.cases.find_one({"case_id": case_id, "user_id": user_id})
    if not case_row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case '{case_id}' was not found",
        )
    return case_row


@router.post(
    "",
    response_model=APIResponse[EvidenceUploadResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit_evidence_upload)],
)
async def upload_evidence(
    case_id: str,
    file: UploadFile,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user_id),
    db: AsyncDatabase = Depends(get_db),
):
    """Securely streams and ingests an evidence file into the specified case.

    Enforces streaming size limits, magic byte signature matching, SHA-256 deduplication,
    atomic private storage, and asynchronous background extraction dispatch.
    """
    await _verify_case_ownership(case_id, user_id, db)

    evidence_id = generate_evidence_id()
    orig_filename = file.filename or "uploaded_evidence"

    # Stream file to disk and validate signature
    rel_path, media_type, file_size, sha256_hash = await storage_service.save_upload_stream(
        upload_file=file,
        case_id=case_id,
        evidence_id=evidence_id,
    )

    # Check for duplicate upload in the same case
    existing = await db.evidence.find_one(
        {"case_id": case_id, "user_id": user_id, "sha256_hash": sha256_hash}
    )
    if existing:
        existing_rel_path = existing.get("storage_relative_path")
        file_present = False
        if existing_rel_path:
            try:
                full_existing_path = storage_service._resolve_safe_path(existing_rel_path)
                file_present = os.path.exists(full_existing_path)
            except Exception:
                file_present = False

        file_restored = False
        if file_present:
            # File already safely on disk; delete redundant file and return existing record
            storage_service.remove_evidence_file(rel_path)
        else:
            # Physical file is missing from disk (e.g. Render Free redeployment / ephemeral disk reset).
            # Safely restore the physical file by promoting the verified upload into the existing record's path.
            target_rel_path = existing_rel_path or f"{case_id}/{existing['evidence_id']}.bin"
            full_target_path = storage_service._resolve_safe_path(target_rel_path)
            full_new_path = storage_service._resolve_safe_path(rel_path)
            os.makedirs(os.path.dirname(full_target_path), exist_ok=True)
            os.replace(full_new_path, full_target_path)
            file_restored = True

            await db.evidence.update_one(
                {"evidence_id": existing["evidence_id"]},
                {
                    "$set": {
                        "storage_relative_path": target_rel_path,
                        "updated_at": utc_now(),
                    }
                },
            )

            # If existing evidence was previously FAILED or INTERRUPTED, re-dispatch extraction
            if existing.get("status") in [
                EvidenceStatus.FAILED.value,
                EvidenceStatus.INTERRUPTED.value,
            ]:
                claimed = await db.evidence.find_one_and_update(
                    {
                        "evidence_id": existing["evidence_id"],
                        "status": existing["status"],
                    },
                    {
                        "$set": {
                            "status": EvidenceStatus.QUEUED.value,
                            "error_code": None,
                            "error_message": None,
                            "updated_at": utc_now(),
                        },
                        "$inc": {"retry_count": 1},
                    },
                    return_document=True,
                )
                if claimed:
                    existing["status"] = EvidenceStatus.QUEUED.value
                    job = ProcessingJob(
                        evidence_id=claimed["evidence_id"],
                        case_id=claimed["case_id"],
                        user_id=claimed["user_id"],
                        storage_relative_path=target_rel_path,
                        original_filename=claimed["original_filename"],
                        media_type=claimed["media_type"],
                        sha256_hash=claimed["sha256_hash"],
                        retry_count=claimed.get("retry_count", 1),
                    )
                    background_tasks.add_task(evidence_processing_service.run_job, job, db)

        upload_data = EvidenceUploadResponse(
            evidence_id=existing["evidence_id"],
            case_id=existing["case_id"],
            original_filename=existing["original_filename"],
            media_type=existing["media_type"],
            file_size_bytes=existing["file_size_bytes"],
            sha256_hash=existing["sha256_hash"],
            status=existing["status"],
            is_duplicate=True,
            file_restored=file_restored,
            created_at=existing["created_at"],
        )
        return APIResponse(data=upload_data)

    doc = EvidenceDocument(
        evidence_id=evidence_id,
        case_id=case_id,
        user_id=user_id,
        original_filename=orig_filename,
        media_type=media_type,
        file_size_bytes=file_size,
        sha256_hash=sha256_hash,
        storage_relative_path=rel_path,
        status=EvidenceStatus.QUEUED,
    )

    doc_dict = doc.model_dump()
    try:
        await db.evidence.insert_one(doc_dict)
    except Exception as exc:
        # Determine if error is a duplicate key race on (case_id, sha256_hash)
        is_dup_race = "duplicate key" in str(exc).lower() or getattr(exc, "code", None) == 11000

        if is_dup_race:
            # Deterministic resolution: return existing winner document
            winner = await db.evidence.find_one(
                {"case_id": case_id, "user_id": user_id, "sha256_hash": sha256_hash}
            )
            if winner:
                winner_rel_path = winner.get("storage_relative_path")
                file_present = False
                if winner_rel_path:
                    try:
                        full_winner_path = storage_service._resolve_safe_path(winner_rel_path)
                        file_present = os.path.exists(full_winner_path)
                    except Exception:
                        file_present = False

                file_restored = False
                if file_present:
                    storage_service.remove_evidence_file(rel_path)
                else:
                    target_rel_path = winner_rel_path or f"{case_id}/{winner['evidence_id']}.bin"
                    full_target_path = storage_service._resolve_safe_path(target_rel_path)
                    full_new_path = storage_service._resolve_safe_path(rel_path)
                    os.makedirs(os.path.dirname(full_target_path), exist_ok=True)
                    os.replace(full_new_path, full_target_path)
                    file_restored = True
                    await db.evidence.update_one(
                        {"evidence_id": winner["evidence_id"]},
                        {"$set": {"storage_relative_path": target_rel_path, "updated_at": utc_now()}},
                    )

                upload_data = EvidenceUploadResponse(
                    evidence_id=winner["evidence_id"],
                    case_id=winner["case_id"],
                    original_filename=winner["original_filename"],
                    media_type=winner["media_type"],
                    file_size_bytes=winner["file_size_bytes"],
                    sha256_hash=winner["sha256_hash"],
                    status=winner["status"],
                    is_duplicate=True,
                    file_restored=file_restored,
                    created_at=winner["created_at"],
                )
                return APIResponse(data=upload_data)

        # Protect against orphaned evidence files on non-race insertion errors
        other_ref = await db.evidence.find_one({"storage_relative_path": rel_path})
        if not other_ref:
            storage_service.remove_evidence_file(rel_path)

        raise exc

    # Transition parent case to PROCESSING upon evidence upload
    await db.cases.update_one(
        {"case_id": case_id},
        {"$set": {"status": CaseStatus.PROCESSING.value, "updated_at": utc_now()}},
    )

    # Dispatch background extraction job
    job = ProcessingJob(
        evidence_id=evidence_id,
        case_id=case_id,
        user_id=user_id,
        storage_relative_path=rel_path,
        original_filename=orig_filename,
        media_type=media_type,
        sha256_hash=sha256_hash,
    )
    background_tasks.add_task(evidence_processing_service.run_job, job, db)

    response_data = EvidenceUploadResponse(
        evidence_id=doc.evidence_id,
        case_id=doc.case_id,
        original_filename=doc.original_filename,
        media_type=doc.media_type,
        file_size_bytes=doc.file_size_bytes,
        sha256_hash=doc.sha256_hash,
        status=doc.status,
        is_duplicate=False,
        created_at=doc.created_at,
    )
    return APIResponse(data=response_data)


@router.get("", response_model=APIResponse[EvidenceListResponse])
async def list_case_evidence(
    case_id: str,
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    status_filter: Optional[EvidenceStatus] = Query(None, alias="status", description="Filter by status"),
    user_id: str = Depends(get_current_user_id),
    db: AsyncDatabase = Depends(get_db),
):
    """Retrieves paginated evidence records belonging to the specified case."""
    await _verify_case_ownership(case_id, user_id, db)

    query: dict = {"case_id": case_id, "user_id": user_id}
    if status_filter is not None:
        query["status"] = status_filter.value

    total = await db.evidence.count_documents(query)
    pages = math.ceil(total / limit) if total > 0 else 0

    cursor = (
        db.evidence.find(query)
        .sort([("created_at", -1), ("_id", -1)])
        .skip((page - 1) * limit)
        .limit(limit)
    )

    items = []
    async for row in cursor:
        items.append(EvidenceResponse(**row))

    pagination = PaginationMeta(page=page, limit=limit, total=total, pages=pages)
    return APIResponse(data=EvidenceListResponse(items=items, pagination=pagination))


@router.get("/{evidence_id}", response_model=APIResponse[EvidenceResponse])
async def get_evidence_detail(
    case_id: str,
    evidence_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncDatabase = Depends(get_db),
):
    """Retrieves detailed processing status and extraction summary for an evidence asset."""
    await _verify_case_ownership(case_id, user_id, db)

    row = await db.evidence.find_one(
        {"evidence_id": evidence_id, "case_id": case_id, "user_id": user_id}
    )
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evidence '{evidence_id}' was not found in case '{case_id}'",
        )

    return APIResponse(data=EvidenceResponse(**row))


@router.post("/{evidence_id}/retry", response_model=APIResponse[EvidenceResponse], status_code=status.HTTP_202_ACCEPTED)
async def retry_evidence_processing(
    case_id: str,
    evidence_id: str,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user_id),
    db: AsyncDatabase = Depends(get_db),
):
    """Retries processing for an evidence asset that failed or was interrupted."""
    await _verify_case_ownership(case_id, user_id, db)

    row = await db.evidence.find_one(
        {"evidence_id": evidence_id, "case_id": case_id, "user_id": user_id}
    )
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evidence '{evidence_id}' was not found",
        )

    allowed_retry_statuses = [
        EvidenceStatus.FAILED.value,
        EvidenceStatus.INTERRUPTED.value,
        EvidenceStatus.REVIEW_NEEDED.value,
    ]

    claimed = await db.evidence.find_one_and_update(
        {
            "evidence_id": evidence_id,
            "case_id": case_id,
            "user_id": user_id,
            "status": {"$in": allowed_retry_statuses},
        },
        {
            "$set": {
                "status": EvidenceStatus.QUEUED.value,
                "error_code": None,
                "error_message": None,
                "updated_at": utc_now(),
            },
            "$inc": {"retry_count": 1},
        },
        return_document=True,
    )

    if not claimed:
        row = await db.evidence.find_one(
            {"evidence_id": evidence_id, "case_id": case_id, "user_id": user_id}
        )
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Evidence '{evidence_id}' was not found",
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot retry evidence with status '{row['status']}'. Allowed statuses: {allowed_retry_statuses}",
        )

    # Transition parent case to PROCESSING upon retry dispatch
    await db.cases.update_one(
        {"case_id": case_id},
        {"$set": {"status": CaseStatus.PROCESSING.value, "updated_at": utc_now()}},
    )

    job = ProcessingJob(
        evidence_id=evidence_id,
        case_id=case_id,
        user_id=user_id,
        storage_relative_path=claimed["storage_relative_path"],
        original_filename=claimed["original_filename"],
        media_type=claimed["media_type"],
        sha256_hash=claimed["sha256_hash"],
        retry_count=claimed.get("retry_count", 1),
    )
    background_tasks.add_task(evidence_processing_service.run_job, job, db)

    return APIResponse(data=EvidenceResponse(**claimed))


@router.get("/{evidence_id}/download")
async def download_evidence(
    case_id: str,
    evidence_id: str,
    inline: bool = Query(
        False,
        description="Whether to serve file inline for in-browser preview or as attachment for download",
    ),
    user_id: str = Depends(get_current_user_id),
    db: AsyncDatabase = Depends(get_db),
):
    """Securely streams binary evidence content with strict authentication and case ownership verification.

    Sets RFC-compliant Content-Disposition (inline for preview, attachment for download)
    and validates path security against directory traversal. Handles ephemeral file disappearance
    gracefully on Render Free deployments.
    """
    await _verify_case_ownership(case_id, user_id, db)

    row = await db.evidence.find_one(
        {"evidence_id": evidence_id, "case_id": case_id, "user_id": user_id}
    )
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evidence '{evidence_id}' was not found in case '{case_id}'",
        )

    storage_relative_path = row.get("storage_relative_path")
    if not storage_relative_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Storage path record for evidence '{evidence_id}' is missing.",
        )

    # Strictly verify storage path belongs to the requested case
    if not storage_relative_path.startswith(f"{case_id}/"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Evidence storage path does not belong to the requested case.",
        )

    try:
        content = storage_service.read_evidence_bytes(storage_relative_path)
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "Evidence file is not available on disk. On Render Free hosting, local storage "
                "is ephemeral and cleared on container restarts. Please re-upload this evidence "
                "file to view or process it."
            ),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to read evidence file: {exc}",
        )

    media_type = row.get("media_type") or "application/octet-stream"
    orig_filename = row.get("original_filename") or f"{evidence_id}.bin"

    # RFC 6266 / RFC 5987 safe filename encoding
    ascii_clean = re.sub(r'[\r\n"\\;]', "_", orig_filename).strip()
    ascii_clean = ascii_clean.encode("ascii", "replace").decode("ascii") or "evidence"
    encoded_filename = quote(orig_filename)

    disposition_type = "inline" if inline else "attachment"
    content_disposition = (
        f'{disposition_type}; filename="{ascii_clean}"; filename*=UTF-8\'\'{encoded_filename}'
    )

    headers = {
        "Content-Disposition": content_disposition,
        "Content-Type": media_type,
        "Content-Length": str(len(content)),
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
    }

    return Response(content=content, media_type=media_type, headers=headers)


@router.get("/{evidence_id}/preview")
async def preview_evidence(
    case_id: str,
    evidence_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncDatabase = Depends(get_db),
):
    """Convenience alias for inline evidence preview."""
    return await download_evidence(case_id, evidence_id, inline=True, user_id=user_id, db=db)

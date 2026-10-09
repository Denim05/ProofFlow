import math
from typing import Optional
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from pymongo.asynchronous.database import AsyncDatabase

from app.core.dependencies import get_current_user_id, get_db
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


@router.post("", response_model=APIResponse[EvidenceUploadResponse], status_code=status.HTTP_201_CREATED)
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
        # File already uploaded to this case; delete redundant file and return existing record
        storage_service.remove_evidence_file(rel_path)
        upload_data = EvidenceUploadResponse(
            evidence_id=existing["evidence_id"],
            case_id=existing["case_id"],
            original_filename=existing["original_filename"],
            media_type=existing["media_type"],
            file_size_bytes=existing["file_size_bytes"],
            sha256_hash=existing["sha256_hash"],
            status=existing["status"],
            is_duplicate=True,
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
    await db.evidence.insert_one(doc_dict)

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
    if row["status"] not in allowed_retry_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot retry evidence with status '{row['status']}'. Allowed statuses: {allowed_retry_statuses}",
        )

    new_retry_count = row.get("retry_count", 0) + 1
    await db.evidence.update_one(
        {"evidence_id": evidence_id},
        {
            "$set": {
                "status": EvidenceStatus.QUEUED.value,
                "retry_count": new_retry_count,
                "error_code": None,
                "error_message": None,
                "updated_at": utc_now(),
            }
        },
    )

    job = ProcessingJob(
        evidence_id=evidence_id,
        case_id=case_id,
        user_id=user_id,
        storage_relative_path=row["storage_relative_path"],
        original_filename=row["original_filename"],
        media_type=row["media_type"],
        sha256_hash=row["sha256_hash"],
        retry_count=new_retry_count,
    )
    background_tasks.add_task(evidence_processing_service.run_job, job, db)

    updated_row = await db.evidence.find_one({"evidence_id": evidence_id})
    return APIResponse(data=EvidenceResponse(**updated_row))

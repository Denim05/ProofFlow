from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from app.models.evidence import EvidenceStatus, MLProcessingMode
from app.schemas.case import PaginationMeta


# Verified SHA-256 example digest of non-empty reference document ("ProofFlow Sample Evidence Document")
SAMPLE_DOC_SHA256 = "78d2be9209581cf244d2d46e2978ffc7be2199b9cf98579ad04113ab1e041eb9"


class EvidenceUploadResponse(BaseModel):
    """Payload returned immediately after an evidence file is securely accepted."""

    evidence_id: str
    case_id: str
    original_filename: str
    media_type: str
    file_size_bytes: int
    sha256_hash: str = Field(
        ...,
        pattern=r"^[A-Fa-f0-9]{64}$",
        description="Cryptographic SHA-256 digest of exact uploaded file bytes",
        json_schema_extra={"example": SAMPLE_DOC_SHA256},
    )
    status: EvidenceStatus
    is_duplicate: bool = False
    created_at: datetime


class EvidenceResponse(BaseModel):
    """Detailed response model for an evidence asset."""

    evidence_id: str
    case_id: str
    original_filename: str
    media_type: str
    file_size_bytes: int
    sha256_hash: str = Field(
        ...,
        pattern=r"^[A-Fa-f0-9]{64}$",
        description="Cryptographic SHA-256 digest of exact uploaded file bytes",
        json_schema_extra={"example": SAMPLE_DOC_SHA256},
    )
    status: EvidenceStatus
    processing_mode: MLProcessingMode
    processing_version: int
    active_processing_version: Optional[int] = None
    extraction_summary: Optional[Dict[str, Any]] = None
    error_code: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class EvidenceListResponse(BaseModel):
    """Paginated response model for evidence lists."""

    items: List[EvidenceResponse]
    pagination: PaginationMeta

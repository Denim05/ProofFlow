from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from app.models.evidence import EvidenceStatus, MLProcessingMode
from app.schemas.case import PaginationMeta


class EvidenceUploadResponse(BaseModel):
    """Payload returned immediately after an evidence file is securely accepted."""

    evidence_id: str
    case_id: str
    original_filename: str
    media_type: str
    file_size_bytes: int
    sha256_hash: str
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
    sha256_hash: str
    status: EvidenceStatus
    processing_mode: MLProcessingMode
    processing_version: int
    extraction_summary: Optional[Dict[str, Any]] = None
    error_code: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class EvidenceListResponse(BaseModel):
    """Paginated response model for evidence lists."""

    items: List[EvidenceResponse]
    pagination: PaginationMeta

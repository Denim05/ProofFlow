from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional
import uuid
from pydantic import BaseModel, Field


class EvidenceStatus(str, Enum):
    UPLOADED = "UPLOADED"
    QUEUED = "QUEUED"
    EXTRACTING = "EXTRACTING"
    STRUCTURING = "STRUCTURING"
    ANALYZING = "ANALYZING"
    READY = "READY"
    REVIEW_NEEDED = "REVIEW_NEEDED"
    FAILED = "FAILED"
    INTERRUPTED = "INTERRUPTED"


class MLProcessingMode(str, Enum):
    NEURAL_DEBERTA_GPU = "NEURAL_DEBERTA_GPU"
    NEURAL_DEBERTA_CPU = "NEURAL_DEBERTA_CPU"
    DETERMINISTIC_FALLBACK = "DETERMINISTIC_FALLBACK"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"


def generate_evidence_id() -> str:
    """Generates a URL-safe prefixed unique identifier for evidence."""
    return f"evi_{uuid.uuid4().hex[:24]}"


class EvidenceDocument(BaseModel):
    """Database representation of an ingested evidence asset in MongoDB."""

    evidence_id: str = Field(default_factory=generate_evidence_id)
    case_id: str
    user_id: str
    original_filename: str = Field(..., min_length=1, max_length=255)
    media_type: str = Field(..., description="Verified MIME type e.g. application/pdf, image/png")
    file_size_bytes: int = Field(..., ge=1)
    sha256_hash: str = Field(..., pattern=r"^[A-Fa-f0-9]{64}$")
    storage_relative_path: str = Field(..., min_length=1)
    status: EvidenceStatus = Field(default=EvidenceStatus.QUEUED)
    processing_mode: MLProcessingMode = Field(default=MLProcessingMode.DETERMINISTIC_FALLBACK)
    processing_version: int = Field(default=1, ge=1, description="Increments on each successful reprocessing to version event sets")
    active_processing_version: Optional[int] = Field(default=None, description="Authoritative active version visible to event queries")
    current_run_id: Optional[str] = Field(default=None, description="Unique run identifier of the in-flight or active processing execution")
    job_id: Optional[str] = None
    retry_count: int = Field(default=0, ge=0)
    heartbeat_at: Optional[datetime] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    extraction_summary: Optional[Dict[str, Any]] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = {
        "use_enum_values": True,
        "populate_by_name": True,
    }

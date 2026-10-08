from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class EvidenceType(str, Enum):
    PDF = "PDF"
    IMAGE = "IMAGE"
    EMAIL = "EMAIL"
    CHAT_SCREENSHOT = "CHAT_SCREENSHOT"
    BANK_STATEMENT = "BANK_STATEMENT"
    RECEIPT = "RECEIPT"
    TEXT = "TEXT"


class EvidenceStatus(str, Enum):
    UPLOADED = "UPLOADED"
    QUEUED = "QUEUED"
    EXTRACTING = "EXTRACTING"
    STRUCTURING = "STRUCTURING"
    ANALYZING = "ANALYZING"
    READY = "READY"
    FAILED = "FAILED"
    REVIEW_NEEDED = "REVIEW_NEEDED"


class EvidenceIngestionMetadata(BaseModel):
    """Metadata schema for immutable raw evidence assets."""

    evidence_id: str = Field(..., description="Unique prefixed ID: evi_[a-z0-9]{24}")
    case_id: str = Field(..., description="Parent case identifier")
    user_id: str = Field(..., description="Tenant owner identifier")
    filename: str = Field(..., min_length=1, max_length=255)
    file_size_bytes: int = Field(..., ge=1, description="Size in bytes, must be non-zero")
    mime_type: str = Field(..., description="Verified MIME type e.g. application/pdf, image/png")
    sha256_hash: str = Field(
        ...,
        pattern=r"^[A-Fa-f0-9]{64}$",
        description="Cryptographic SHA-256 digest for tamper verification",
    )
    storage_path: str = Field(..., min_length=1, description="Internal private object storage key")
    declared_type: Optional[EvidenceType] = None
    status: EvidenceStatus = Field(default=EvidenceStatus.UPLOADED)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = {
        "use_enum_values": True,
        "populate_by_name": True,
    }

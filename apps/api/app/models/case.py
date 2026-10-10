from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel, Field


class CaseStatus(str, Enum):
    PROCESSING = "PROCESSING"
    READY = "READY"
    REVIEW_NEEDED = "REVIEW_NEEDED"
    ARCHIVED = "ARCHIVED"


def generate_case_id() -> str:
    """Generates a URL-safe prefixed unique identifier for a case."""
    return f"case_{uuid.uuid4().hex[:24]}"


class CaseDocument(BaseModel):
    """Database representation of an incident Case in MongoDB."""

    case_id: str = Field(default_factory=generate_case_id)
    user_id: str
    title: str = Field(..., min_length=3, max_length=160)
    description: str = Field(default="", max_length=2000)
    status: CaseStatus = Field(default=CaseStatus.READY)
    tags: List[str] = Field(default_factory=list)
    evidence_count: int = Field(default=0, ge=0)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = {
        "use_enum_values": True,
        "populate_by_name": True,
    }

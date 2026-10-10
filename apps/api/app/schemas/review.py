from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


class ReviewDecision(str, Enum):
    """Supported human adjudication decision states for cross-examination findings."""

    CONFIRMED_INCONSISTENCY = "CONFIRMED_INCONSISTENCY"
    RESOLVED = "RESOLVED"
    DISMISSED = "DISMISSED"


class FindingReviewCreateRequest(BaseModel):
    """Client request payload to adjudicate a finding."""

    decision: ReviewDecision = Field(
        ...,
        description="Human adjudication decision: CONFIRMED_INCONSISTENCY, RESOLVED, or DISMISSED.",
    )
    reason: Optional[str] = Field(
        None,
        description="Justification or explanation for the adjudication. Mandatory for DISMISSED.",
    )

    @field_validator("reason")
    @classmethod
    def validate_dismissal_reason(cls, v: Optional[str], info) -> Optional[str]:
        decision = info.data.get("decision")
        if decision == ReviewDecision.DISMISSED:
            if not v or not v.strip():
                raise ValueError("A meaningful dismissal reason is mandatory when dismissing a finding.")
            if len(v.strip()) < 3:
                raise ValueError("Dismissal reason must be at least 3 characters long.")
        return v.strip() if v else None


class FindingReviewResponse(BaseModel):
    """Persisted adjudication record for a finding."""

    review_id: str
    case_id: str
    finding_id: str
    reviewer_id: str
    decision: ReviewDecision
    reason: Optional[str] = None
    version: int = 1
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class FindingReviewListResponse(BaseModel):
    """Collection envelope for case review records."""

    items: List[FindingReviewResponse]
    total: int
    case_id: str


class FindingReviewHistoryResponse(BaseModel):
    """Audit trail envelope of all decisions made on a specific finding."""

    items: List[FindingReviewResponse]
    total: int
    finding_id: str
    case_id: str

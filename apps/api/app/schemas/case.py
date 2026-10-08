from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator
from app.models.case import CaseStatus


class CaseCreateRequest(BaseModel):
    """Payload for creating a new Case."""

    title: str = Field(..., min_length=3, max_length=160, description="Incident case title")
    description: Optional[str] = Field(default="", max_length=2000, description="Detailed case narrative")
    tags: Optional[List[str]] = Field(default_factory=list, description="Categorization tags")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Arbitrary domain metadata")

    @field_validator("title")
    @classmethod
    def strip_title(cls, v: str) -> str:
        stripped = v.strip()
        if len(stripped) < 3:
            raise ValueError("Title must contain at least 3 non-whitespace characters")
        return stripped

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, tags: Optional[List[str]]) -> List[str]:
        if not tags:
            return []
        if len(tags) > 10:
            raise ValueError("A maximum of 10 tags is permitted")
        clean = []
        for tag in tags:
            t = tag.strip().lower()
            if len(t) > 30:
                raise ValueError("Tag length cannot exceed 30 characters")
            if t and t not in clean:
                clean.append(t)
        return clean


class CaseResponse(BaseModel):
    """Public representation of a Case."""

    case_id: str
    user_id: str
    title: str
    description: str
    status: CaseStatus
    tags: List[str]
    evidence_count: int
    metadata: Dict[str, Any]
    created_at: datetime
    updated_at: datetime


class PaginationMeta(BaseModel):
    page: int = Field(ge=1)
    limit: int = Field(ge=1, le=100)
    total: int = Field(ge=0)
    pages: int = Field(ge=0)


class CaseListResponse(BaseModel):
    items: List[CaseResponse]
    pagination: PaginationMeta

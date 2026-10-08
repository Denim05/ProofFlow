from datetime import datetime, timezone
from typing import Any, Generic, List, Optional, TypeVar
from pydantic import BaseModel, Field

DataT = TypeVar("DataT")


class ErrorDetail(BaseModel):
    field: Optional[str] = None
    issue: str


class ErrorPayload(BaseModel):
    code: str
    message: str
    details: List[ErrorDetail] = Field(default_factory=list)


class APIResponse(BaseModel, Generic[DataT]):
    """Standardized ProofFlow API response envelope."""

    success: bool = True
    data: Optional[DataT] = None
    error: Optional[ErrorPayload] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

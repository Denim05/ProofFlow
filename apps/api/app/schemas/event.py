from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, field_validator
from app.schemas.case import PaginationMeta


class EventResponse(BaseModel):
    """Payload representing an extracted, source-grounded event."""

    event_id: str
    case_id: str
    evidence_id: str
    processing_version: int = 1
    processing_run_id: Optional[str] = None
    is_active: bool = True
    event_type: str
    decision_state: str
    review_reasons: List[str] = []
    trigger_raw_text: str
    char_start: int
    char_end: int
    page_number: Optional[int] = None
    bounding_box: Optional[List[float]] = None
    actor: Optional[str] = None
    temporal_information: Optional[str] = None
    amount_currency: Optional[str] = None
    amount_value: Optional[Decimal] = None
    order_reference: Optional[str] = None
    transaction_reference: Optional[str] = None
    polarity: str = "POSITIVE"
    modality: str = "ASSERTED"
    tense: str = "PAST"
    model_confidence: float = 1.0
    model_metadata: Dict[str, Any] = {}
    created_at: datetime

    @field_validator("amount_value", mode="before")
    @classmethod
    def parse_amount_value(cls, v: Any) -> Optional[Decimal]:
        if v is None:
            return None
        if hasattr(v, "to_decimal"):
            return v.to_decimal()
        if isinstance(v, Decimal):
            return v
        return Decimal(str(v))


class EventListResponse(BaseModel):
    """Paginated response model for extracted event queries."""

    items: List[EventResponse]
    pagination: PaginationMeta

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from app.schemas.case import PaginationMeta


class EventResponse(BaseModel):
    """Payload representing an extracted, source-grounded event."""

    event_id: str
    case_id: str
    evidence_id: str
    event_type: str
    decision_state: str
    review_reasons: List[str] = []
    trigger_raw_text: str
    char_start: int
    char_end: int
    page_number: Optional[int] = None
    bounding_box: Optional[List[float]] = None
    actor: Optional[str] = None
    amount_currency: Optional[str] = None
    amount_value: Optional[Decimal] = None
    order_reference: Optional[str] = None
    transaction_reference: Optional[str] = None
    polarity: str
    modality: str
    tense: str
    model_confidence: float
    model_metadata: Dict[str, Any] = {}
    created_at: datetime


class EventListResponse(BaseModel):
    """Paginated response model for extracted event queries."""

    items: List[EventResponse]
    pagination: PaginationMeta

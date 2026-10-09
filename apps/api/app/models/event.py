from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel, Field


def generate_event_id() -> str:
    """Generates a URL-safe prefixed unique identifier for an event."""
    return f"evt_{uuid.uuid4().hex[:24]}"


class EventDocument(BaseModel):
    """Database representation of an extracted event record in MongoDB."""

    event_id: str = Field(default_factory=generate_event_id)
    case_id: str
    evidence_id: str
    user_id: str
    processing_version: int = Field(default=1, ge=1, description="Version of the extraction run that generated this event")
    event_type: str = Field(..., description="Canonical ProofFlow EventType name")
    decision_state: str = Field(..., description="'VALIDATED' or 'REVIEW_NEEDED'")
    review_reasons: List[str] = Field(default_factory=list)

    # Trigger provenance (never fabricated)
    trigger_raw_text: str
    char_start: int = Field(..., ge=0)
    char_end: int = Field(..., ge=0)
    page_number: Optional[int] = None
    bounding_box: Optional[List[float]] = None  # [x0, y0, x1, y1] on target page, or None

    # Arguments
    actor: Optional[str] = None
    participants: Dict[str, str] = Field(default_factory=dict)
    temporal_information: Optional[str] = None
    amount_currency: Optional[str] = None
    amount_value: Optional[Decimal] = None
    order_reference: Optional[str] = None
    transaction_reference: Optional[str] = None

    # Linguistic nuances
    polarity: str = "POSITIVE"
    modality: str = "ASSERTED"
    tense: str = "PAST"

    # Model classification confidence and traceability
    model_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    model_metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = {
        "use_enum_values": True,
        "populate_by_name": True,
    }

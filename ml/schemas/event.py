from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Union
import uuid
from pydantic import BaseModel, Field, model_validator
from ml.schemas.entity import MonetaryValue, RelativeTimeResolution
from ml.schemas.model_metadata import ModelMetadata
from ml.schemas.source_reference import SourceReference


class EventTaxonomyVersion(str, Enum):
    V1_0 = "1.0.0"


class EventCategory(str, Enum):
    COMMERCE = "COMMERCE"
    ORDER_DELIVERY = "ORDER_DELIVERY"
    COMMUNICATION = "COMMUNICATION"
    DISPUTE = "DISPUTE"


class EventType(str, Enum):
    # Commerce
    ORDER_PLACED = "ORDER_PLACED"
    PAYMENT_MADE = "PAYMENT_MADE"
    PAYMENT_FAILED = "PAYMENT_FAILED"
    REFUND_REQUESTED = "REFUND_REQUESTED"
    REFUND_INITIATED = "REFUND_INITIATED"
    REFUND_COMPLETED = "REFUND_COMPLETED"
    REFUND_FAILED = "REFUND_FAILED"

    # Order / Delivery
    ORDER_CANCELLED = "ORDER_CANCELLED"
    ITEM_SHIPPED = "ITEM_SHIPPED"
    ORDER_SHIPPED = "ORDER_SHIPPED"  # Backward compatibility alias
    DELIVERY_ATTEMPTED = "DELIVERY_ATTEMPTED"
    ITEM_DELIVERED = "ITEM_DELIVERED"
    ORDER_DELIVERED = "ORDER_DELIVERED"  # Backward compatibility alias
    ITEM_RECEIVED = "ITEM_RECEIVED"      # Backward compatibility alias
    RETURN_REQUESTED = "RETURN_REQUESTED"
    RETURN_INITIATED = "RETURN_INITIATED" # Backward compatibility alias
    RETURN_PICKED_UP = "RETURN_PICKED_UP"
    RETURN_COMPLETED = "RETURN_COMPLETED"

    # Communication
    MESSAGE_SENT = "MESSAGE_SENT"
    MESSAGE_RECEIVED = "MESSAGE_RECEIVED"
    SUPPORT_CONTACTED = "SUPPORT_CONTACTED"
    SUPPORT_RESPONSE = "SUPPORT_RESPONSE"

    # Dispute / Legacy
    REFUND_APPROVED = "REFUND_APPROVED"
    REFUND_PROCESSED = "REFUND_PROCESSED"
    REFUND_RECEIVED = "REFUND_RECEIVED"
    DISPUTE_OPENED = "DISPUTE_OPENED"
    CHARGEBACK_REQUESTED = "CHARGEBACK_REQUESTED"


class EventPolarity(str, Enum):
    """Whether the event occurred positively or was explicitly negated/denied."""
    POSITIVE = "POSITIVE"
    NEGATED = "NEGATED"


class EventModality(str, Enum):
    """Epistemic modality of the event mention."""
    ASSERTED = "ASSERTED"       # Factually claimed / stated as happened
    CONDITIONAL = "CONDITIONAL" # Dependent on an unverified condition ("if approved")
    UNCERTAIN = "UNCERTAIN"     # Modal hedge ("may", "might", "possibly")
    PLANNED = "PLANNED"         # Scheduled / intended future action ("will complete")


class EventTense(str, Enum):
    """Grammatical or temporal orientation of the event."""
    PAST = "PAST"
    PRESENT = "PRESENT"
    FUTURE = "FUTURE"


class EventTrigger(BaseModel):
    """Verbatim textual trigger span anchoring the event in the source document."""
    raw_text: str = Field(..., min_length=1)
    char_start: int = Field(..., ge=0)
    char_end: int = Field(..., ge=0)
    source_reference: SourceReference


class Event(BaseModel):
    """Structured, source-grounded representation of an extracted incident event.

    Invariants:
    1. MISSING != UNKNOWN != FALSE. Missing arguments are never fabricated.
    2. Every event trigger and argument has source provenance back to EvidenceText.
    3. Monetary values use exact Decimal (MonetaryValue).
    4. Polarity, Modality, and Tense are preserved explicitly.
    """

    event_id: str = Field(default_factory=lambda: f"evt_{uuid.uuid4().hex[:24]}")
    case_id: str
    event_type: EventType
    trigger: Optional[EventTrigger] = None
    source_reference: SourceReference

    # Arguments
    actor: Optional[str] = None
    participants: Dict[str, str] = Field(default_factory=dict)
    temporal_information: Optional[Union[str, RelativeTimeResolution, Dict[str, Any]]] = None
    amount: Optional[MonetaryValue] = None
    transaction_reference: Optional[str] = None
    order_reference: Optional[str] = None

    # Epistemic & Temporal Nuances
    polarity: EventPolarity = EventPolarity.POSITIVE
    modality: EventModality = EventModality.ASSERTED
    tense: EventTense = EventTense.PAST

    # Quality & Provenance
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    attributes: Dict[str, Any] = Field(default_factory=dict)
    model_metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Backward compatibility slots for Track 0/1 consumers
    timestamp: Optional[datetime] = None
    order_id: Optional[str] = None
    transaction_id: Optional[str] = None
    refund_id: Optional[str] = None
    tracking_number: Optional[str] = None
    carrier: Optional[str] = None
    extraction_metadata: Optional[ModelMetadata] = None
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def sync_legacy_fields(cls, values: Any) -> Any:
        if isinstance(values, dict):
            # Sync transaction_reference <-> transaction_id
            if "transaction_id" in values and "transaction_reference" not in values:
                values["transaction_reference"] = values["transaction_id"]
            elif "transaction_reference" in values and "transaction_id" not in values:
                values["transaction_id"] = values["transaction_reference"]

            # Sync order_reference <-> order_id
            if "order_id" in values and "order_reference" not in values:
                values["order_reference"] = values["order_id"]
            elif "order_reference" in values and "order_id" not in values:
                values["order_id"] = values["order_reference"]

            # Sync extraction_metadata <-> model_metadata
            if "extraction_metadata" in values and values["extraction_metadata"]:
                meta = values["extraction_metadata"]
                if isinstance(meta, ModelMetadata):
                    values["confidence"] = values.get("confidence", meta.extraction_confidence)
                    values["model_metadata"] = values.get("model_metadata", meta.model_dump())
            elif "confidence" not in values:
                values["confidence"] = 1.0
        return values


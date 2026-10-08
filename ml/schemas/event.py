from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from ml.schemas.entity import MonetaryValue
from ml.schemas.model_metadata import ModelMetadata
from ml.schemas.source_reference import SourceReference


class EventType(str, Enum):
    ORDER_PLACED = "ORDER_PLACED"
    PAYMENT_MADE = "PAYMENT_MADE"
    ORDER_SHIPPED = "ORDER_SHIPPED"
    ORDER_DELIVERED = "ORDER_DELIVERED"
    ITEM_RECEIVED = "ITEM_RECEIVED"
    RETURN_INITIATED = "RETURN_INITIATED"
    REFUND_REQUESTED = "REFUND_REQUESTED"
    REFUND_APPROVED = "REFUND_APPROVED"
    REFUND_PROCESSED = "REFUND_PROCESSED"
    REFUND_RECEIVED = "REFUND_RECEIVED"
    DISPUTE_OPENED = "DISPUTE_OPENED"
    CHARGEBACK_REQUESTED = "CHARGEBACK_REQUESTED"


class Event(BaseModel):
    """Event representation. Optional slots remain None when absent in evidence.

    Invariant: MISSING != UNKNOWN != FALSE. Models must never hallucinate missing arguments.
    """

    event_id: str
    case_id: str
    event_type: EventType
    source_reference: SourceReference
    extraction_metadata: ModelMetadata

    # Flexible optional argument slots
    timestamp: Optional[datetime] = None
    order_id: Optional[str] = None
    transaction_id: Optional[str] = None
    refund_id: Optional[str] = None
    tracking_number: Optional[str] = None
    amount: Optional[MonetaryValue] = None
    carrier: Optional[str] = None
    participants: Optional[Dict[str, str]] = Field(default_factory=dict)
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)

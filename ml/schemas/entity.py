from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field
from ml.schemas.model_metadata import ModelMetadata
from ml.schemas.source_reference import SourceReference


class EntityType(str, Enum):
    PERSON = "PERSON"
    ORGANIZATION = "ORGANIZATION"
    PRODUCT = "PRODUCT"
    ORDER_ID = "ORDER_ID"
    TRANSACTION_ID = "TRANSACTION_ID"
    REFUND_ID = "REFUND_ID"
    TRACKING_NUMBER = "TRACKING_NUMBER"
    CARRIER = "CARRIER"
    MONETARY_AMOUNT = "MONETARY_AMOUNT"
    DATE = "DATE"
    TIME = "TIME"
    DATETIME = "DATETIME"
    RELATIVE_TIME = "RELATIVE_TIME"
    SHIPPING_ADDRESS = "SHIPPING_ADDRESS"
    PAYMENT_METHOD = "PAYMENT_METHOD"
    ITEM_CONDITION = "ITEM_CONDITION"


class MonetaryValue(BaseModel):
    value: float
    currency: str = Field(default="USD", description="ISO-4217 Currency Code (e.g. USD, EUR, INR)")


class RelativeTimeResolution(BaseModel):
    raw_text: str
    reference_anchor: Optional[Dict[str, Any]] = None
    computed_value: Optional[str] = None
    resolution_status: str = Field(
        ...,
        description="RESOLVED_WITH_ANCHOR, UNRESOLVED_NO_ANCHOR, or AMBIGUOUS_ANCHOR",
    )
    resolution_confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class Entity(BaseModel):
    """Structured representation of an extracted entity mention with strict evidence provenance."""

    entity_id: str
    case_id: str
    label: EntityType
    text: str
    normalized_value: Optional[Union[MonetaryValue, RelativeTimeResolution, str, float, int]] = None
    source_reference: SourceReference
    extraction_metadata: ModelMetadata

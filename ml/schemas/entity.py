from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Union
import uuid
from pydantic import BaseModel, Field, model_validator
from ml.schemas.model_metadata import ModelMetadata
from ml.schemas.source_reference import SourceReference


class EntityType(str, Enum):
    PERSON = "PERSON"
    ORGANIZATION = "ORGANIZATION"
    PRODUCT = "PRODUCT"
    ORDER_ID = "ORDER_ID"
    TRANSACTION_ID = "TRANSACTION_ID"
    INVOICE_ID = "INVOICE_ID"
    REFUND_ID = "REFUND_ID"
    TRACKING_NUMBER = "TRACKING_NUMBER"
    CARRIER = "CARRIER"
    MONETARY_AMOUNT = "MONETARY_AMOUNT"
    DATE = "DATE"
    TIME = "TIME"
    DATETIME = "DATETIME"
    RELATIVE_TIME = "RELATIVE_TIME"
    PHONE_NUMBER = "PHONE_NUMBER"
    EMAIL = "EMAIL"
    ADDRESS = "ADDRESS"
    SHIPPING_ADDRESS = "SHIPPING_ADDRESS"
    PAYMENT_METHOD = "PAYMENT_METHOD"
    ITEM_CONDITION = "ITEM_CONDITION"
    URL = "URL"


class MonetaryValue(BaseModel):
    """Exact decimal representation of currency amounts to prevent binary float inaccuracies."""
    value: Decimal = Field(..., description="Exact decimal monetary amount")
    currency: str = Field(default="USD", description="ISO-4217 Currency Code (e.g. USD, EUR, INR)")


class PhoneNumberValue(BaseModel):
    """Structured phone number preserving local number when country context is ungrounded."""
    raw_number: str
    country_code: Optional[str] = Field(None, description="ISO country code or dialing prefix if grounded; UNKNOWN if unanchored")
    e164_formatted: Optional[str] = Field(None, description="Full E.164 representation ONLY if country context is verified")


class RelativeTimeResolution(BaseModel):
    raw_text: str
    reference_anchor: Optional[Dict[str, Any]] = None
    computed_value: Optional[str] = None
    resolution_status: str = Field(
        ...,
        description="RESOLVED_WITH_ANCHOR, UNRESOLVED_NO_ANCHOR, or AMBIGUOUS_ANCHOR",
    )
    resolution_confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class EntityMention(BaseModel):
    """Structured representation of an extracted entity mention with strict evidence provenance."""

    entity_id: str = Field(default_factory=lambda: f"ent_{uuid.uuid4().hex[:24]}")
    case_id: str
    evidence_id: str
    entity_type: EntityType
    raw_value: str = Field(..., min_length=1)
    normalized_value: Optional[
        Union[MonetaryValue, PhoneNumberValue, RelativeTimeResolution, Dict[str, Any], str, int, Decimal]
    ] = None
    extraction_confidence: float = Field(..., ge=0.0, le=1.0)
    extraction_method: str = Field(
        default="DETERMINISTIC_REGEX",
        description="DETERMINISTIC_REGEX | PRETRAINED_NLP | HYBRID",
    )
    source_reference: SourceReference
    model_metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def validate_source_provenance(self) -> "EntityMention":
        if not self.source_reference.evidence_id:
            raise ValueError("source_reference must contain a valid evidence_id.")
        return self


class Entity(EntityMention):
    """Backward-compatible alias for EntityMention supporting legacy label/text fields."""

    label: Optional[EntityType] = None
    text: Optional[str] = None
    extraction_metadata: Optional[ModelMetadata] = None

    @model_validator(mode="before")
    @classmethod
    def populate_aliases(cls, values: Any) -> Any:
        if isinstance(values, dict):
            if "label" in values and "entity_type" not in values:
                values["entity_type"] = values["label"]
            elif "entity_type" in values and "label" not in values:
                values["label"] = values["entity_type"]
            if "text" in values and "raw_value" not in values:
                values["raw_value"] = values["text"]
            elif "raw_value" in values and "text" not in values:
                values["text"] = values["raw_value"]
            if "extraction_metadata" in values:
                meta = values["extraction_metadata"]
                if isinstance(meta, ModelMetadata):
                    values["extraction_confidence"] = values.get("extraction_confidence", meta.extraction_confidence)
                    values["model_metadata"] = values.get("model_metadata", meta.model_dump())
            elif "extraction_confidence" not in values:
                values["extraction_confidence"] = 1.0
            if "evidence_id" not in values and "source_reference" in values:
                sref = values["source_reference"]
                if isinstance(sref, SourceReference):
                    values["evidence_id"] = sref.evidence_id
                elif isinstance(sref, dict) and "evidence_id" in sref:
                    values["evidence_id"] = sref["evidence_id"]
        return values


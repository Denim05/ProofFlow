from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field
from ml.schemas.entity import MonetaryValue
from ml.schemas.event import EventType
from ml.schemas.model_metadata import ModelMetadata
from ml.schemas.source_reference import SourceReference


class SpeakerRole(str, Enum):
    CUSTOMER = "CUSTOMER"
    MERCHANT = "MERCHANT"
    CARRIER = "CARRIER"
    FINANCIAL_INSTITUTION = "FINANCIAL_INSTITUTION"
    PLATFORM_MEDIATOR = "PLATFORM_MEDIATOR"


class Modality(str, Enum):
    SUBJECTIVE_ASSERTION = "SUBJECTIVE_ASSERTION"
    TRANSACTION_RECORD = "TRANSACTION_RECORD"
    OFFICIAL_COMMUNICATION = "OFFICIAL_COMMUNICATION"


class EpistemicStatus(str, Enum):
    UNVERIFIED_STATEMENT = "UNVERIFIED_STATEMENT"
    VERIFIED_SYSTEM_LOG = "VERIFIED_SYSTEM_LOG"


class Claim(BaseModel):
    """Atomic Claim representation strictly distinguishing subjective assertions from system records."""

    claim_id: str
    case_id: str
    speaker: Dict[str, Any] = Field(..., description="Identity and SpeakerRole of asserting party")
    modality: Modality
    epistemic_status: EpistemicStatus
    subject: str
    predicate: str
    object: Optional[str] = None
    amount: Optional[MonetaryValue] = None
    event_reference: Optional[EventType] = None
    temporal_expression: Optional[str] = None
    source_reference: SourceReference
    extraction_metadata: ModelMetadata

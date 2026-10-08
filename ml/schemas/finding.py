from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field
from ml.schemas.model_metadata import ModelMetadata
from ml.schemas.source_reference import SourceReference


class InconsistencyTier(str, Enum):
    TIER_A_DETERMINISTIC = "TIER_A_DETERMINISTIC"
    TIER_B_SEMANTIC_NLI = "TIER_B_SEMANTIC_NLI"
    TIER_C_TEMPORAL = "TIER_C_TEMPORAL"


class ConflictState(str, Enum):
    DIRECT_CONTRADICTION = "DIRECT_CONTRADICTION"
    POTENTIAL_CONFLICT = "POTENTIAL_CONFLICT"
    CONTEXTUALLY_COMPATIBLE = "CONTEXTUALLY_COMPATIBLE"
    INSUFFICIENT_CONTEXT = "INSUFFICIENT_CONTEXT"


class CoverageState(str, Enum):
    PRESENT_IN_UPLOADED_EVIDENCE = "PRESENT_IN_UPLOADED_EVIDENCE"
    NOT_FOUND_IN_UPLOADED_EVIDENCE = "NOT_FOUND_IN_UPLOADED_EVIDENCE"
    INSUFFICIENT_COVERAGE = "INSUFFICIENT_COVERAGE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNKNOWN = "UNKNOWN"


class FindingType(str, Enum):
    POTENTIAL_INCONSISTENCY = "POTENTIAL_INCONSISTENCY"
    MISSING_EVIDENCE_ADVISORY = "MISSING_EVIDENCE_ADVISORY"
    TIMELINE_SEQUENCE_NOTE = "TIMELINE_SEQUENCE_NOTE"


class Finding(BaseModel):
    """User-facing grounded Finding.

    Strict Invariant: Every factual finding MUST preserve at least one valid source reference.
    """

    finding_id: str
    case_id: str
    finding_type: FindingType
    title: str = Field(..., max_length=160)
    summary: str = Field(..., max_length=2000)
    inconsistency_tier: Optional[InconsistencyTier] = None
    conflict_state: Optional[ConflictState] = None
    coverage_state: Optional[CoverageState] = None
    severity: str = Field(default="MEDIUM", description="LOW, MEDIUM, or HIGH")
    evidence_references: List[SourceReference] = Field(
        ...,
        min_length=1,
        description="Mandatory evidence citations. Findings without references cannot be persisted.",
    )
    model_metadata: ModelMetadata

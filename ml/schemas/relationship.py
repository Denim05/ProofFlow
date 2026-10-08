from enum import Enum
from typing import List
from pydantic import BaseModel, Field
from ml.schemas.model_metadata import ModelMetadata


class RelationshipType(str, Enum):
    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"
    TEMPORALLY_PRECEDES = "TEMPORALLY_PRECEDES"
    COREFERS_TO = "COREFERS_TO"
    DERIVED_FROM = "DERIVED_FROM"


class Relationship(BaseModel):
    """Directed semantic or temporal link between claims, events, or entities."""

    relationship_id: str
    case_id: str
    source_id: str = Field(..., description="ID of source entity, event, or claim")
    target_id: str = Field(..., description="ID of target entity, event, or claim")
    relationship_type: RelationshipType
    evidence_ids: List[str] = Field(..., min_length=1, description="List of parent evidence IDs supporting the relationship")
    rationale: str = Field(..., description="Explanation of why relationship exists")
    model_metadata: ModelMetadata

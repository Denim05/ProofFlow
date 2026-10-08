from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field


class ModelMetadata(BaseModel):
    """Provenance and confidence metadata for an AI/ML extraction or reasoning task."""

    model_name: str = Field(..., description="Canonical identifier of the model or rule engine")
    model_version: str = Field(..., description="Semantic version or checkpoint digest of the model")
    extraction_confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Model extraction/classification certainty. Crucial: Model confidence != Truth confidence.",
    )
    confidence_definition: str = Field(
        default="Extraction confidence measures parsing/classification certainty, NOT factual truth or authenticity.",
        description="Explicit contractual clarification of the confidence metric.",
    )
    execution_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when model inference occurred",
    )

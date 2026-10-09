import os
from typing import List
from pydantic import BaseModel, Field


class MLEnvironmentSettings(BaseModel):
    """Typed runtime and deployment settings for ML components."""

    model_name: str = Field(
        default_factory=lambda: os.getenv("MODEL_NAME", "microsoft/deberta-v3-base"),
        description="Transformer backbone identifier",
    )
    model_version: str = Field(
        default_factory=lambda: os.getenv("MODEL_VERSION", "1.0.0"),
        description="Trained model artifact version",
    )
    model_path: str = Field(
        default_factory=lambda: os.getenv("MODEL_PATH", "ml/checkpoints/deberta_v3_event"),
        description="Path to serialized model weights and checkpoint directory",
    )
    model_device: str = Field(
        default_factory=lambda: os.getenv("MODEL_DEVICE", "cuda"),
        description="Target compute device (cuda, cpu, or auto)",
    )
    ml_environment: str = Field(
        default_factory=lambda: os.getenv("ML_ENVIRONMENT", "development"),
        description="Runtime environment mode (development, staging, production)",
    )


class EventExtractionConfig(BaseModel):
    """Configuration for deterministic event detection, cue parsing, and argument binding."""

    taxonomy_version: str = Field(default="1.0.0", description="Semantic event taxonomy version")

    # Maximum character distance around event trigger to bind argument entities
    max_argument_char_distance: int = Field(
        default=300,
        ge=50,
        le=2000,
        description="Character window to search for proximal argument entities if not bounded by sentence",
    )

    # Lexical cues for epistemic, temporal, and polarity analysis
    negation_cues: List[str] = Field(
        default_factory=lambda: [
            "not", "never", "no", "unsuccessful", "failed to", "wasn't", "weren't",
            "did not", "didn't", "denied", "rejected", "cannot", "could not", "cancelled",
        ]
    )

    future_cues: List[str] = Field(
        default_factory=lambda: [
            "will be", "will", "scheduled to", "expected to", "tomorrow", "shall be",
            "going to", "planned for", "soon",
        ]
    )

    conditional_cues: List[str] = Field(
        default_factory=lambda: [
            "if", "provided that", "subject to", "once approved", "conditional on",
            "upon receipt", "in case of", "pending approval", "pending",
        ]
    )

    modal_cues: List[str] = Field(
        default_factory=lambda: [
            "may", "might", "could", "possibly", "potential", "estimated",
            "tentatively", "perhaps", "likely", "supposed to",
        ]
    )


# Default singletons
ml_env_settings = MLEnvironmentSettings()
event_config = EventExtractionConfig()


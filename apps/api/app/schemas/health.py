from datetime import datetime, timezone
from pydantic import BaseModel, Field


class HealthStatus(BaseModel):
    """Health check payload representation."""

    status: str = Field(..., description="Overall service status: healthy or degraded")
    database: str = Field(..., description="Database connection status: connected or disconnected")
    service: str = Field(default="ProofFlow API")
    version: str = Field(default="0.1.0")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

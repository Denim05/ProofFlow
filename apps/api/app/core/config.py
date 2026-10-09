from typing import List, Optional, Union
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration validated with Pydantic Settings.

    Reads environment variables from system environment and root .env file.
    Fails validation if production environment lacks secure secrets.
    """

    MONGODB_URI: str = "mongodb://localhost:27017"
    MONGODB_DATABASE: str = "proofflow_dev"
    API_SECRET_KEY: str = "dev_insecure_secret_key_change_in_production"
    ENVIRONMENT: str = "development"

    # Connection pooling and timeouts
    MONGODB_MAX_POOL_SIZE: int = 50
    MONGODB_MIN_POOL_SIZE: int = 5
    MONGODB_SERVER_SELECTION_TIMEOUT_MS: int = 5000

    # CORS configuration
    CORS_ORIGINS: Union[List[str], str] = ["http://localhost:3000"]

    # Service info
    SERVICE_NAME: str = "ProofFlow API"
    SERVICE_VERSION: str = "0.1.0"

    # Evidence storage settings
    EVIDENCE_STORAGE_DIR: str = "storage/evidence"
    TEMP_STORAGE_DIR: str = "storage/temp"
    MAX_EVIDENCE_FILE_SIZE_BYTES: int = 25 * 1024 * 1024  # 25 MB

    # Asynchronous job timeouts
    JOB_HEARTBEAT_TIMEOUT_SECONDS: int = 600  # 10 minutes
    JOB_MAX_TIMEOUT_SECONDS: int = 1800  # 30 minutes

    # Authentication & JWT verification settings
    CLERK_ISSUER: Optional[str] = None
    CLERK_JWKS_URL: Optional[str] = None
    CLERK_AUDIENCE: Optional[str] = None
    CLERK_AUTHORIZED_PARTIES: Union[List[str], str] = []
    ALLOW_DEV_AUTH_BYPASS: bool = False
    AUTH_JWKS_CACHE_TTL_SECONDS: int = 300
    AUTH_JWKS_TIMEOUT_SECONDS: int = 10

    model_config = SettingsConfigDict(
        env_file=(".env", "../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: Union[List[str], str]) -> List[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("CLERK_AUTHORIZED_PARTIES", mode="before")
    @classmethod
    def parse_authorized_parties(cls, value: Union[List[str], str, None]) -> List[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [p.strip() for p in value.split(",") if p.strip()]
        return value

    @model_validator(mode="after")
    def derive_jwks_url(self) -> "Settings":
        if self.CLERK_ISSUER and not self.CLERK_JWKS_URL:
            self.CLERK_JWKS_URL = f"{self.CLERK_ISSUER.rstrip('/')}/.well-known/jwks.json"
        return self

    @model_validator(mode="after")
    def validate_production_requirements(self) -> "Settings":
        if self.ENVIRONMENT.lower() == "production":
            if not self.MONGODB_URI or "localhost" in self.MONGODB_URI:
                raise ValueError("Production environment requires a valid non-local MONGODB_URI.")
            if (
                not self.API_SECRET_KEY
                or self.API_SECRET_KEY == "dev_insecure_secret_key_change_in_production"
            ):
                raise ValueError("Production environment requires a secure API_SECRET_KEY.")
            if self.ALLOW_DEV_AUTH_BYPASS:
                raise ValueError("Production environment strictly prohibits ALLOW_DEV_AUTH_BYPASS.")
            if not self.CLERK_ISSUER:
                raise ValueError("Production environment requires a valid non-empty CLERK_ISSUER.")
            if not self.CLERK_JWKS_URL:
                raise ValueError("Production environment requires a valid non-empty CLERK_JWKS_URL.")
            if "localhost" in self.CLERK_ISSUER.lower() or "localhost" in self.CLERK_JWKS_URL.lower():
                raise ValueError("Production environment prohibits localhost CLERK_ISSUER and CLERK_JWKS_URL.")
        return self


settings = Settings()

import pytest
from app.core.config import Settings


def test_default_config_loading():
    """Verify that default settings instantiate with expected values in development mode."""
    cfg = Settings(ENVIRONMENT="development")
    assert cfg.ENVIRONMENT == "development"
    assert cfg.MONGODB_DATABASE == "proofflow_dev"
    assert "http://localhost:3000" in cfg.CORS_ORIGINS
    assert cfg.MONGODB_MAX_POOL_SIZE == 50
    assert cfg.MONGODB_MIN_POOL_SIZE == 5
    assert cfg.MONGODB_SERVER_SELECTION_TIMEOUT_MS == 5000


def test_cors_origins_parsing_from_string():
    """Verify that comma-separated CORS_ORIGINS string is parsed into a list."""
    cfg = Settings(CORS_ORIGINS="http://localhost:3000, https://proofflow.app")
    assert cfg.CORS_ORIGINS == ["http://localhost:3000", "https://proofflow.app"]


def test_production_fails_without_secure_secrets():
    """Verify that production mode strictly requires valid remote URI and non-default secret key."""
    with pytest.raises(ValueError, match="Production environment requires a valid non-local MONGODB_URI"):
        Settings(
            ENVIRONMENT="production",
            MONGODB_URI="mongodb://localhost:27017",
            API_SECRET_KEY="secure_prod_key",
        )

    with pytest.raises(ValueError, match="Production environment requires a secure API_SECRET_KEY"):
        Settings(
            ENVIRONMENT="production",
            MONGODB_URI="mongodb+srv://user:pass@cluster.mongodb.net",
            API_SECRET_KEY="dev_insecure_secret_key_change_in_production",
        )


def test_production_succeeds_with_valid_config():
    """Verify that production mode succeeds with compliant configuration."""
    cfg = Settings(
        ENVIRONMENT="production",
        MONGODB_URI="mongodb+srv://user:pass@cluster.mongodb.net",
        API_SECRET_KEY="super_secure_production_secret_key_12345",
    )
    assert cfg.ENVIRONMENT == "production"
    assert cfg.MONGODB_DATABASE == "proofflow_dev"

import json
import os
from typing import Any, Dict, List, Set
from pydantic import BaseModel, Field

try:
    from pydantic_settings import BaseSettings, SettingsConfigDict
    _HAS_PYDANTIC_SETTINGS = True
except ImportError:
    BaseSettings = None  # type: ignore
    SettingsConfigDict = None  # type: ignore
    _HAS_PYDANTIC_SETTINGS = False


def _load_env_overrides(prefix: str = "EXTRACTION_") -> Dict[str, Any]:
    """Explicit configuration adapter that parses environment variables matching prefix."""
    overrides: Dict[str, Any] = {}
    for key, val in os.environ.items():
        if key.startswith(prefix):
            field_name = key[len(prefix):].lower()
            # Attempt to parse json (numbers, booleans, arrays, objects)
            try:
                parsed = json.loads(val)
                overrides[field_name] = parsed
            except (json.JSONDecodeError, ValueError):
                if "," in val:
                    overrides[field_name] = [item.strip() for item in val.split(",") if item.strip()]
                else:
                    overrides[field_name] = val
    return overrides


class _FallbackExtractionConfig(BaseModel):
    """Explicit fallback configuration adapter when pydantic_settings is not installed.

    Loads and type-casts environment variables prefixed with EXTRACTION_ to guarantee
    identical runtime behavior and validation without silent default degradation.
    """

    min_native_char_density: float = 0.0001
    min_alphanumeric_ratio: float = 0.45
    min_dictionary_word_ratio: float = 0.35
    min_acceptable_ocr_confidence: float = 0.55
    max_glyph_substitution_rate: float = 0.05
    max_file_size_bytes: int = 50 * 1024 * 1024
    allowed_mime_types: Set[str] = {
        "application/pdf",
        "image/png",
        "image/jpeg",
        "image/jpg",
        "image/webp",
        "image/tiff",
        "text/plain",
    }
    rasterize_dpi: int = 300

    def __init__(self, **data: Any):
        env_overrides = _load_env_overrides("EXTRACTION_")
        merged = {**env_overrides, **data}
        super().__init__(**merged)


if _HAS_PYDANTIC_SETTINGS:
    class ExtractionConfig(BaseSettings):
        """Configurable extraction quality thresholds and limits."""

        min_native_char_density: float = 0.0001
        min_alphanumeric_ratio: float = 0.45
        min_dictionary_word_ratio: float = 0.35
        min_acceptable_ocr_confidence: float = 0.55
        max_glyph_substitution_rate: float = 0.05
        max_file_size_bytes: int = 50 * 1024 * 1024
        allowed_mime_types: Set[str] = {
            "application/pdf",
            "image/png",
            "image/jpeg",
            "image/jpg",
            "image/webp",
            "image/tiff",
            "text/plain",
        }
        rasterize_dpi: int = 300

        model_config = SettingsConfigDict(
            env_prefix="EXTRACTION_",
            extra="ignore",
        )
else:
    ExtractionConfig = _FallbackExtractionConfig  # type: ignore


extraction_config = ExtractionConfig()

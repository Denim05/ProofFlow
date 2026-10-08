from typing import List, Set
from pydantic_settings import BaseSettings, SettingsConfigDict


class ExtractionConfig(BaseSettings):
    """Configurable extraction quality thresholds and limits.

    These values represent initial empirical candidate parameters, NOT universal production truths.
    """

    # Quality decision candidate thresholds
    min_native_char_density: float = 0.0001
    min_alphanumeric_ratio: float = 0.45
    min_dictionary_word_ratio: float = 0.35
    min_acceptable_ocr_confidence: float = 0.55
    max_glyph_substitution_rate: float = 0.05

    # File safety parameters
    max_file_size_bytes: int = 50 * 1024 * 1024  # 50 MB
    allowed_mime_types: Set[str] = {
        "application/pdf",
        "image/png",
        "image/jpeg",
        "image/jpg",
        "image/webp",
        "image/tiff",
        "text/plain",
    }

    # DPI for rasterizing PDF pages when OCR fallback is triggered
    rasterize_dpi: int = 300

    model_config = SettingsConfigDict(
        env_prefix="EXTRACTION_",
        extra="ignore",
    )


extraction_config = ExtractionConfig()

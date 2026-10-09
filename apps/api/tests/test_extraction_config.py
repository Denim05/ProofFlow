import os
import pytest
from ml.extraction.config import (
    ExtractionConfig,
    _FallbackExtractionConfig,
    _load_env_overrides,
)


def test_extraction_config_defaults():
    """Verifies default values and field types are properly configured."""
    cfg = ExtractionConfig()
    assert cfg.min_native_char_density == 0.0001
    assert cfg.min_alphanumeric_ratio == 0.45
    assert cfg.min_dictionary_word_ratio == 0.35
    assert cfg.min_acceptable_ocr_confidence == 0.55
    assert cfg.max_glyph_substitution_rate == 0.05
    assert cfg.max_file_size_bytes == 50 * 1024 * 1024
    assert "application/pdf" in cfg.allowed_mime_types
    assert cfg.rasterize_dpi == 300


def test_fallback_adapter_defaults():
    """Verifies fallback adapter initializes identical defaults without external dependencies."""
    cfg = _FallbackExtractionConfig()
    assert cfg.min_native_char_density == 0.0001
    assert cfg.min_alphanumeric_ratio == 0.45
    assert cfg.min_dictionary_word_ratio == 0.35
    assert cfg.min_acceptable_ocr_confidence == 0.55
    assert cfg.max_glyph_substitution_rate == 0.05
    assert cfg.max_file_size_bytes == 50 * 1024 * 1024
    assert "application/pdf" in cfg.allowed_mime_types
    assert cfg.rasterize_dpi == 300


def test_fallback_adapter_env_overrides(monkeypatch):
    """Verifies fallback adapter correctly loads and parses EXTRACTION_ environment variables."""
    monkeypatch.setenv("EXTRACTION_MIN_NATIVE_CHAR_DENSITY", "0.005")
    monkeypatch.setenv("EXTRACTION_MIN_ALPHANUMERIC_RATIO", "0.60")
    monkeypatch.setenv("EXTRACTION_MAX_FILE_SIZE_BYTES", "10485760")
    monkeypatch.setenv("EXTRACTION_RASTERIZE_DPI", "150")
    monkeypatch.setenv("EXTRACTION_ALLOWED_MIME_TYPES", '["application/pdf", "image/png"]')

    overrides = _load_env_overrides("EXTRACTION_")
    assert overrides["min_native_char_density"] == 0.005
    assert overrides["min_alphanumeric_ratio"] == 0.60
    assert overrides["max_file_size_bytes"] == 10485760
    assert overrides["rasterize_dpi"] == 150
    assert overrides["allowed_mime_types"] == ["application/pdf", "image/png"]

    cfg = _FallbackExtractionConfig()
    assert cfg.min_native_char_density == 0.005
    assert cfg.min_alphanumeric_ratio == 0.60
    assert cfg.max_file_size_bytes == 10485760
    assert cfg.rasterize_dpi == 150
    assert cfg.allowed_mime_types == {"application/pdf", "image/png"}


def test_fallback_adapter_comma_separated_env_overrides(monkeypatch):
    """Verifies comma-separated strings for sets/lists are handled cleanly in fallback adapter."""
    monkeypatch.setenv("EXTRACTION_ALLOWED_MIME_TYPES", "application/pdf, text/plain")
    cfg = _FallbackExtractionConfig()
    assert cfg.allowed_mime_types == {"application/pdf", "text/plain"}

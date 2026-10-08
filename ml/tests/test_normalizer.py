import pytest
from ml.extraction.normalizer import TextNormalizer


def test_normalizer_unicode_nfc_and_zero_width():
    # Raw string with zero-width space and Windows CRLF
    raw = "Invoice Total:\u200b $10,000\r\nDue Date: 2026-10-01"
    norm, offset_map = TextNormalizer.normalize_with_offsets(raw)

    assert "\u200b" not in norm
    assert "\r" not in norm
    assert "Invoice Total: $10,000\nDue Date: 2026-10-01" in norm
    assert len(offset_map) > 0


def test_normalizer_span_mapping():
    raw = "Total:\u200b $500\r\nTax: $50"
    norm, _ = TextNormalizer.normalize_with_offsets(raw)

    # In norm, find "$500"
    norm_start = norm.index("$500")
    norm_end = norm_start + len("$500")

    raw_start, raw_end = TextNormalizer.map_span_to_raw(norm_start, norm_end, raw, norm)
    # The raw slice should correspond to "$500"
    assert raw[raw_start:raw_end] == "$500"


def test_normalizer_empty_string():
    norm, offset_map = TextNormalizer.normalize_with_offsets("")
    assert norm == ""
    assert offset_map == []

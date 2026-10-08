import re
from typing import List, Tuple
from ml.extraction.config import ExtractionConfig, extraction_config
from ml.schemas.evidence_text import ExtractionQualityMetrics, ExtractionQualityState, TextSpan

COMMON_DISPUTE_WORDS = {
    "the", "and", "to", "of", "a", "in", "for", "is", "on", "that", "by", "this",
    "order", "invoice", "payment", "refund", "total", "amount", "date", "customer",
    "account", "transaction", "balance", "card", "delivery", "shipping", "tax", "due",
    "receipt", "bank", "statement", "credit", "debit", "charge", "id", "status"
}


class QualityAssessor:
    """Evaluates extraction quality and assigns empirical decision states (PASS, OCR_RECOMMENDED, REVIEW_NEEDED)."""

    def __init__(self, config: ExtractionConfig = extraction_config):
        self.config = config

    def assess_page(
        self,
        raw_text: str,
        spans: List[TextSpan],
        page_area: float = 1.0,
        has_raster_images: bool = False,
        is_native_pdf: bool = True,
    ) -> Tuple[ExtractionQualityMetrics, ExtractionQualityState]:
        """Calculates measurable quality metrics and assigns a decision state based on candidate parameters."""
        char_count = len(raw_text)
        words = [w.strip() for w in re.split(r"\s+", raw_text) if w.strip()]
        word_count = len(words)

        # Alphanumeric ratio
        alphanumeric_chars = sum(1 for c in raw_text if c.isalnum())
        alnum_ratio = (alphanumeric_chars / char_count) if char_count > 0 else 0.0

        # Lexical dictionary word ratio
        recognized_words = sum(1 for w in words if w.lower() in COMMON_DISPUTE_WORDS)
        dict_word_ratio = (recognized_words / word_count) if word_count > 0 else 0.0

        # Mean token confidence
        if spans:
            mean_conf = sum(s.extraction_confidence for s in spans) / len(spans)
        else:
            mean_conf = 1.0 if is_native_pdf and char_count > 0 else 0.0

        # Replacement / garbage character count
        glyph_sub_count = raw_text.count("\ufffd") + raw_text.count("\x00")
        glyph_sub_rate = (glyph_sub_count / char_count) if char_count > 0 else 0.0

        # Detection of scanned / image-only page in PDF
        char_density = (char_count / page_area) if page_area > 0 else 0.0
        is_scanned = is_native_pdf and (char_count == 0 or (char_density < self.config.min_native_char_density and has_raster_images))

        metrics = ExtractionQualityMetrics(
            raw_character_count=char_count,
            word_count=word_count,
            alphanumeric_ratio=round(alnum_ratio, 4),
            dictionary_word_ratio=round(dict_word_ratio, 4),
            mean_token_confidence=round(mean_conf, 4),
            suspected_glyph_substitution_count=glyph_sub_count,
            has_raster_images=has_raster_images,
            is_scanned_page=is_scanned,
        )

        # Decision State Triage
        # 1. Native PDF with zero text or image-only content triggers OCR fallback
        if is_native_pdf and is_scanned:
            return metrics, ExtractionQualityState.OCR_RECOMMENDED

        # 2. Native PDF with severe garbage character rate or corrupt fonts triggers OCR fallback
        if is_native_pdf and glyph_sub_rate > self.config.max_glyph_substitution_rate:
            return metrics, ExtractionQualityState.OCR_RECOMMENDED

        # 3. Low token confidence (OCR output) or low alphanumeric ratio triggers REVIEW_NEEDED
        if mean_conf < self.config.min_acceptable_ocr_confidence or alnum_ratio < self.config.min_alphanumeric_ratio:
            return metrics, ExtractionQualityState.REVIEW_NEEDED

        # 4. Normal legible content
        return metrics, ExtractionQualityState.PASS

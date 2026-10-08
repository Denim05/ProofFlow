from ml.extraction.quality_assessor import QualityAssessor
from ml.schemas.evidence_text import ExtractionQualityState, TextSpan


def test_quality_assessor_pass_on_legible_text():
    assessor = QualityAssessor()
    text = "Order Confirmation: Payment of INR 10,000 received for order #98421 on 2026-10-01."
    spans = [
        TextSpan(raw_text="Order", raw_char_start=0, raw_char_end=5, extraction_confidence=0.98),
        TextSpan(raw_text="Confirmation:", raw_char_start=6, raw_char_end=19, extraction_confidence=0.99),
    ]
    metrics, state = assessor.assess_page(text, spans, page_area=500000.0, has_raster_images=False, is_native_pdf=True)

    assert state == ExtractionQualityState.PASS
    assert metrics.alphanumeric_ratio > 0.60
    assert metrics.is_scanned_page is False


def test_quality_assessor_ocr_recommended_on_scanned_page():
    assessor = QualityAssessor()
    # Scanned page has 0 raw native text but has embedded raster image
    text = ""
    spans = []
    metrics, state = assessor.assess_page(text, spans, page_area=500000.0, has_raster_images=True, is_native_pdf=True)

    assert state == ExtractionQualityState.OCR_RECOMMENDED
    assert metrics.is_scanned_page is True


def test_quality_assessor_review_needed_on_low_token_confidence():
    assessor = QualityAssessor()
    text = "TXN-O09I82"
    # Token confidence below threshold (e.g. 0.40)
    spans = [
        TextSpan(raw_text="TXN-O09I82", raw_char_start=0, raw_char_end=10, extraction_confidence=0.40),
    ]
    metrics, state = assessor.assess_page(text, spans, page_area=50000.0, has_raster_images=False, is_native_pdf=False)

    assert state == ExtractionQualityState.REVIEW_NEEDED
    assert metrics.mean_token_confidence < 0.50

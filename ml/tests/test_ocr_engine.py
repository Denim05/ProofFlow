import pytest
from PIL import Image
from ml.extraction.ocr_engine import PaddleOCRExtractor, TesseractExtractor
from ml.schemas.evidence_text import PageExtractionMethod


def test_tesseract_extractor_with_mock_tokens():
    mock_tokens = [
        {"word": "TXN-009182", "confidence": 0.95, "box": [100.0, 200.0, 300.0, 250.0], "line_no": 1, "block_no": 1},
        {"word": "INR", "confidence": 0.99, "box": [310.0, 200.0, 350.0, 250.0], "line_no": 1, "block_no": 1},
        {"word": "10000", "confidence": 0.98, "box": [360.0, 200.0, 450.0, 250.0], "line_no": 1, "block_no": 1},
    ]

    extractor = TesseractExtractor()
    img = Image.new("RGB", (400, 100), color=(255, 255, 255))
    layout = extractor.extract_page(img, page_number=1, mock_data=mock_tokens)

    assert layout.extraction_method == PageExtractionMethod.OCR_TESSERACT_BASELINE
    assert "TXN-009182" in layout.raw_page_text
    assert len(layout.blocks) > 0
    span = layout.blocks[0].lines[0].spans[0]
    assert span.raw_text == "TXN-009182"
    assert span.extraction_confidence == 0.95
    assert span.bounding_box == [100.0, 200.0, 300.0, 250.0]


def test_paddle_ocr_extractor_with_mock_tokens():
    mock_tokens = [
        {"word": "REFUND", "confidence": 0.92, "box": [50.0, 50.0, 150.0, 80.0], "line_no": 0, "block_no": 0},
        {"word": "APPROVED", "confidence": 0.91, "box": [160.0, 50.0, 280.0, 80.0], "line_no": 0, "block_no": 0},
    ]

    extractor = PaddleOCRExtractor()
    img = Image.new("RGB", (300, 100), color=(255, 255, 255))
    layout = extractor.extract_page(img, page_number=1, mock_data=mock_tokens)

    assert layout.extraction_method == PageExtractionMethod.OCR_PADDLE_CANDIDATE
    assert "REFUND APPROVED" in layout.raw_page_text

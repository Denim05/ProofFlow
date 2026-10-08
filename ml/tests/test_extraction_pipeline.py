import pytest
import pymupdf
from PIL import Image
import io

from ml.extraction.pipeline import ExtractionPipeline
from ml.schemas.evidence import EvidenceStatus, EvidenceType
from ml.schemas.evidence_text import ExtractionQualityState, PageExtractionMethod


def test_pipeline_file_validation():
    pipeline = ExtractionPipeline()

    # Zero byte file rejection
    with pytest.raises(ValueError, match="empty"):
        pipeline.validate_file(b"", "empty.pdf", "application/pdf")

    # Magic byte mismatch rejection (text claiming to be PDF)
    with pytest.raises(ValueError, match="magic bytes do not match"):
        pipeline.validate_file(b"This is not a PDF", "fake.pdf", "application/pdf")

    # Valid PDF magic bytes
    valid_pdf_header = b"%PDF-1.4\n%test\n"
    sha = pipeline.validate_file(valid_pdf_header, "test.pdf", "application/pdf")
    assert len(sha) == 64


def test_pipeline_multipage_with_page_level_fallback():
    """Verify multi-page PDF handles Page 1 (Native) and Page 2 (Scanned -> OCR) independently."""
    doc = pymupdf.open()

    # Page 1: Digital text
    p1 = doc.new_page(width=500, height=700)
    p1.insert_text((50, 50), "Page 1 Digital Invoice Text", fontsize=12)

    # Page 2: Blank text with embedded raster image (scanned receipt)
    p2 = doc.new_page(width=500, height=700)
    # Generate in-memory PNG image to insert
    img = Image.new("RGB", (200, 200), color=(200, 200, 200))
    img_buf = io.BytesIO()
    img.save(img_buf, format="PNG")
    p2.insert_image(pymupdf.Rect(50, 50, 250, 250), stream=img_buf.getvalue())

    # Page 3: Digital text
    p3 = doc.new_page(width=500, height=700)
    p3.insert_text((50, 50), "Page 3 Settlement Notes", fontsize=12)

    pdf_bytes = doc.tobytes()
    doc.close()

    mock_ocr = [
        {"word": "SCANNED_RECEIPT_ITEM", "confidence": 0.90, "box": [100.0, 100.0, 300.0, 150.0], "line_no": 1, "block_no": 1}
    ]

    pipeline = ExtractionPipeline()
    meta, evidence_text = pipeline.process_evidence(
        evidence_id="evi_multipage_001",
        case_id="case_multipage_001",
        user_id="usr_tester",
        file_bytes=pdf_bytes,
        filename="hybrid_invoice.pdf",
        mime_type="application/pdf",
        declared_type=EvidenceType.PDF,
        mock_ocr_tokens=mock_ocr,
    )

    assert meta.status == EvidenceStatus.STRUCTURING
    assert len(evidence_text.pages) == 3

    # Page 1: Native PDF
    assert evidence_text.pages[0].extraction_method == PageExtractionMethod.NATIVE_PDF
    assert evidence_text.pages[0].quality_state == ExtractionQualityState.PASS
    assert "Page 1 Digital Invoice" in evidence_text.pages[0].raw_page_text

    # Page 2: OCR Fallback (triggered due to scanned image)
    assert evidence_text.pages[1].extraction_method == PageExtractionMethod.OCR_TESSERACT_BASELINE
    assert "SCANNED_RECEIPT_ITEM" in evidence_text.pages[1].raw_page_text

    # Page 3: Native PDF
    assert evidence_text.pages[2].extraction_method == PageExtractionMethod.NATIVE_PDF
    assert evidence_text.pages[2].quality_state == ExtractionQualityState.PASS
    assert "Page 3 Settlement" in evidence_text.pages[2].raw_page_text


def test_pipeline_image_processing():
    img = Image.new("RGB", (300, 100), color=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    png_bytes = buf.getvalue()

    mock_ocr = [
        {"word": "WHATSAPP_CHAT_MSG", "confidence": 0.88, "box": [50.0, 20.0, 250.0, 60.0], "line_no": 0, "block_no": 0}
    ]

    pipeline = ExtractionPipeline()
    meta, evidence_text = pipeline.process_evidence(
        evidence_id="evi_img_001",
        case_id="case_img_001",
        user_id="usr_tester",
        file_bytes=png_bytes,
        filename="chat_screen.png",
        mime_type="image/png",
        declared_type=EvidenceType.CHAT_SCREENSHOT,
        mock_ocr_tokens=mock_ocr,
    )

    assert len(evidence_text.pages) == 1
    assert "WHATSAPP_CHAT_MSG" in evidence_text.full_raw_text
    assert evidence_text.pages[0].extraction_method == PageExtractionMethod.OCR_TESSERACT_BASELINE

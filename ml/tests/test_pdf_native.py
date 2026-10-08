import pymupdf
from ml.extraction.pdf_native import PyMuPDFExtractor
from ml.schemas.evidence_text import ExtractionQualityState, PageExtractionMethod


def test_pymupdf_extractor_native_pdf():
    # Create in-memory synthetic PDF
    doc = pymupdf.open()
    page = doc.new_page(width=600, height=800)
    page.insert_text((50, 100), "INVOICE #ORD-98421", fontsize=14)
    page.insert_text((50, 130), "Total: INR 10,000", fontsize=12)
    pdf_bytes = doc.tobytes()
    doc.close()

    extractor = PyMuPDFExtractor()
    assert extractor.is_available() is True

    layout = extractor.extract_page(pdf_bytes, page_number=1)

    assert layout.page_number == 1
    assert layout.width == 600.0
    assert layout.height == 800.0
    assert layout.extraction_method == PageExtractionMethod.NATIVE_PDF
    assert layout.quality_state == ExtractionQualityState.PASS
    assert "INVOICE #ORD-98421" in layout.raw_page_text
    assert len(layout.blocks) > 0

    # Verify normalized bounding boxes are within [0..1000]
    for block in layout.blocks:
        for line in block.lines:
            for span in line.spans:
                assert span.bounding_box is not None
                assert 0.0 <= span.bounding_box[0] <= 1000.0
                assert 0.0 <= span.bounding_box[1] <= 1000.0
                assert 0.0 <= span.bounding_box[2] <= 1000.0
                assert 0.0 <= span.bounding_box[3] <= 1000.0

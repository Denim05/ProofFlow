import hashlib
import io
import os
from typing import List, Optional, Tuple
import pymupdf
from PIL import Image

from ml.extraction.config import ExtractionConfig, extraction_config
from ml.extraction.ocr_engine import PaddleOCRExtractor, TesseractExtractor
from ml.extraction.pdf_native import PyMuPDFExtractor
from ml.extraction.preprocessor import ImagePreprocessor
from ml.schemas.evidence import EvidenceIngestionMetadata, EvidenceStatus, EvidenceType
from ml.schemas.evidence_text import (
    EvidenceText,
    ExtractionQualityMetrics,
    ExtractionQualityState,
    PageExtractionMethod,
    PageLayout,
)

MAGIC_SIGNATURES = {
    "application/pdf": [b"%PDF"],
    "image/png": [b"\x89PNG\r\n\x1a\n"],
    "image/jpeg": [b"\xff\xd8\xff"],
    "image/jpg": [b"\xff\xd8\xff"],
    "image/webp": [b"RIFF"],
}


class ExtractionPipeline:
    """Orchestrates secure file validation, native extraction, and page-level OCR fallback.

    NOTE: Production deployment must execute untrusted evidence processing in an isolated sandbox/container with resource limits.
    """

    def __init__(self, config: ExtractionConfig = extraction_config):
        self.config = config
        self.native_extractor = PyMuPDFExtractor()
        self.paddle_ocr = PaddleOCRExtractor()
        self.tesseract_ocr = TesseractExtractor()

    def validate_file(self, file_bytes: bytes, filename: str, declared_mime: str) -> str:
        """Validates file size, non-zero length, and magic byte signatures."""
        if not file_bytes or len(file_bytes) == 0:
            raise ValueError("File is empty (0 bytes).")

        if len(file_bytes) > self.config.max_file_size_bytes:
            raise ValueError(f"File size exceeds permitted maximum of {self.config.max_file_size_bytes} bytes.")

        # Check declared MIME type
        if declared_mime not in self.config.allowed_mime_types:
            raise ValueError(f"MIME type '{declared_mime}' is not permitted.")

        # Magic byte check for binary formats
        if declared_mime in MAGIC_SIGNATURES:
            signatures = MAGIC_SIGNATURES[declared_mime]
            matched = any(file_bytes.startswith(sig) for sig in signatures)
            if not matched:
                raise ValueError(
                    f"File header magic bytes do not match declared MIME type '{declared_mime}'."
                )

        sha256 = hashlib.sha256(file_bytes).hexdigest()
        return sha256

    def process_evidence(
        self,
        evidence_id: str,
        case_id: str,
        user_id: str,
        file_bytes: bytes,
        filename: str,
        mime_type: str,
        declared_type: Optional[EvidenceType] = None,
        storage_path: str = "internal://storage",
        **kwargs,
    ) -> Tuple[EvidenceIngestionMetadata, EvidenceText]:
        """Processes untrusted evidence into verified ingestion metadata and canonical EvidenceText."""
        sha256 = self.validate_file(file_bytes, filename, mime_type)

        ingestion_metadata = EvidenceIngestionMetadata(
            evidence_id=evidence_id,
            case_id=case_id,
            user_id=user_id,
            filename=filename,
            file_size_bytes=len(file_bytes),
            mime_type=mime_type,
            sha256_hash=sha256,
            storage_path=storage_path,
            declared_type=declared_type,
            status=EvidenceStatus.EXTRACTING,
        )

        pages: List[PageLayout] = []

        if mime_type == "application/pdf":
            pages = self._process_pdf_with_page_fallback(file_bytes, **kwargs)
        else:
            # Image formats
            pages = self._process_image_evidence(file_bytes, **kwargs)

        # Aggregate overall quality metrics
        overall_state = ExtractionQualityState.PASS
        if any(p.quality_state == ExtractionQualityState.REVIEW_NEEDED for p in pages):
            overall_state = ExtractionQualityState.REVIEW_NEEDED
        elif all(p.quality_state == ExtractionQualityState.PASS for p in pages):
            overall_state = ExtractionQualityState.PASS

        total_chars = sum(p.quality_metrics.raw_character_count for p in pages)
        total_words = sum(p.quality_metrics.word_count for p in pages)
        avg_alnum = sum(p.quality_metrics.alphanumeric_ratio for p in pages) / len(pages) if pages else 0.0
        avg_conf = sum(p.quality_metrics.mean_token_confidence for p in pages) / len(pages) if pages else 0.0

        overall_metrics = ExtractionQualityMetrics(
            raw_character_count=total_chars,
            word_count=total_words,
            alphanumeric_ratio=round(avg_alnum, 4),
            mean_token_confidence=round(avg_conf, 4),
            is_scanned_page=any(p.quality_metrics.is_scanned_page for p in pages),
        )

        full_raw = "\n\n".join(p.raw_page_text for p in pages)
        full_norm = "\n\n".join(p.normalized_page_text for p in pages)

        evidence_text = EvidenceText(
            evidence_id=evidence_id,
            case_id=case_id,
            full_raw_text=full_raw,
            full_normalized_text=full_norm,
            pages=pages,
            overall_quality_state=overall_state,
            quality_metrics=overall_metrics,
            model_metadata={
                "pipeline_version": "v0.2.0-extraction-foundation",
                "primary_pdf_engine": "PyMuPDF",
                "candidate_ocr": "PaddleOCR",
                "baseline_ocr": "Tesseract",
            },
        )

        # Update metadata status
        ingestion_metadata.status = (
            EvidenceStatus.REVIEW_NEEDED
            if overall_state == ExtractionQualityState.REVIEW_NEEDED
            else EvidenceStatus.STRUCTURING
        )

        return ingestion_metadata, evidence_text

    def _process_pdf_with_page_fallback(self, file_bytes: bytes, **kwargs) -> List[PageLayout]:
        """Page-level extraction applying native PDF extraction with granular per-page OCR fallback."""
        try:
            doc = pymupdf.open(stream=file_bytes, filetype="pdf")
        except Exception as exc:
            raise ValueError(f"Corrupted or malformed PDF file: {str(exc)}")

        if doc.is_encrypted:
            raise ValueError("PDF is password-protected or encrypted. Unencrypted document required.")

        pages: List[PageLayout] = []

        try:
            for idx, page in enumerate(doc):
                page_no = idx + 1
                # Step 1: Attempt native vector extraction
                native_layout = self.native_extractor._extract_page_layout(page, page_no)

                # Step 2: Inspect page-level quality state
                if native_layout.quality_state == ExtractionQualityState.OCR_RECOMMENDED:
                    # Page is scanned or contains sparse/corrupted digital font stream
                    # Rasterize page to high-DPI image and invoke candidate OCR
                    ocr_layout = self._rasterize_and_ocr(page, page_no, **kwargs)
                    if ocr_layout:
                        pages.append(ocr_layout)
                    else:
                        # Fallback to native with REVIEW_NEEDED if OCR engine is unavailable
                        native_layout.quality_state = ExtractionQualityState.REVIEW_NEEDED
                        pages.append(native_layout)
                else:
                    pages.append(native_layout)

            return pages
        finally:
            doc.close()

    def _rasterize_and_ocr(self, page: pymupdf.Page, page_no: int, **kwargs) -> Optional[PageLayout]:
        """Rasterizes a single PDF page at 300 DPI and invokes OCR."""
        zoom = self.config.rasterize_dpi / 72.0
        mat = pymupdf.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img_bytes = pix.tobytes("png")

        # Select OCR engine: PaddleOCR preferred, fallback to Tesseract
        if kwargs.get("mock_ocr_tokens"):
            return self.tesseract_ocr.extract_page(img_bytes, page_number=page_no, mock_data=kwargs["mock_ocr_tokens"])

        if self.paddle_ocr.is_available():
            return self.paddle_ocr.extract_page(img_bytes, page_number=page_no)
        elif self.tesseract_ocr.is_available():
            return self.tesseract_ocr.extract_page(img_bytes, page_number=page_no)

        return None

    def _process_image_evidence(self, file_bytes: bytes, **kwargs) -> List[PageLayout]:
        """Processes raster image evidence (screenshots, receipts) through preprocessor and OCR."""
        processed_img = ImagePreprocessor.apply_pipeline(file_bytes)

        if kwargs.get("mock_ocr_tokens"):
            layout = self.tesseract_ocr.extract_page(processed_img, page_number=1, mock_data=kwargs["mock_ocr_tokens"])
            return [layout]

        if self.paddle_ocr.is_available():
            layout = self.paddle_ocr.extract_page(processed_img, page_number=1)
            return [layout]
        elif self.tesseract_ocr.is_available():
            layout = self.tesseract_ocr.extract_page(processed_img, page_number=1)
            return [layout]

        # If no OCR engine is available at runtime, mark as REVIEW_NEEDED with empty blocks
        raise RuntimeError("No OCR engine available in environment to process image evidence.")

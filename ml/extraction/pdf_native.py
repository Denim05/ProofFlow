from typing import List, Union
import pymupdf
from ml.extraction.base import BaseExtractor
from ml.extraction.normalizer import TextNormalizer
from ml.extraction.quality_assessor import QualityAssessor
from ml.schemas.evidence_text import (
    PageExtractionMethod,
    PageLayout,
    TextBlock,
    TextLine,
    TextSpan,
)


class PyMuPDFExtractor(BaseExtractor):
    """Primary layout-aware digital PDF extractor using PyMuPDF.

    Extracts text tokens with normalized spatial coordinates ([0..1000]) and layout blocks.
    """

    def __init__(self, quality_assessor: QualityAssessor = None):
        self.assessor = quality_assessor or QualityAssessor()

    def is_available(self) -> bool:
        return True

    def extract_page(
        self,
        document_source: Union[str, bytes],
        page_number: int = 1,
        **kwargs,
    ) -> PageLayout:
        """Extracts text layout and tokens from a specific 1-indexed PDF page."""
        doc = self._open_document(document_source)
        try:
            if page_number < 1 or page_number > len(doc):
                raise IndexError(f"Page number {page_number} out of bounds (1..{len(doc)})")

            page = doc[page_number - 1]
            return self._extract_page_layout(page, page_number)
        finally:
            doc.close()

    def extract_document(
        self,
        document_source: Union[str, bytes],
        **kwargs,
    ) -> List[PageLayout]:
        """Extracts layouts for all pages in the PDF document."""
        doc = self._open_document(document_source)
        layouts = []
        try:
            for idx, page in enumerate(doc):
                layouts.append(self._extract_page_layout(page, idx + 1))
            return layouts
        finally:
            doc.close()

    def _open_document(self, source: Union[str, bytes]) -> pymupdf.Document:
        if isinstance(source, bytes):
            return pymupdf.open(stream=source, filetype="pdf")
        return pymupdf.open(source)

    def _extract_page_layout(self, page: pymupdf.Page, page_number: int) -> PageLayout:
        width = float(page.rect.width)
        height = float(page.rect.height)
        page_area = width * height

        # Check for presence of embedded raster images on page
        image_list = page.get_images(full=True)
        has_raster = len(image_list) > 0

        # Extract words: (x0, y0, x1, y1, word, block_no, line_no, word_no)
        raw_words = page.get_text("words")

        # Group words by block and line
        blocks_dict = {}
        all_spans: List[TextSpan] = []
        char_cursor = 0

        for item in raw_words:
            x0, y0, x1, y1, word, block_no, line_no, word_no = item
            # Normalize to 0..1000 coordinate space
            norm_box = [
                round((x0 / width) * 1000.0, 1),
                round((y0 / height) * 1000.0, 1),
                round((x1 / width) * 1000.0, 1),
                round((y1 / height) * 1000.0, 1),
            ]

            span = TextSpan(
                raw_text=word,
                raw_char_start=char_cursor,
                raw_char_end=char_cursor + len(word),
                bounding_box=norm_box,
                extraction_confidence=1.0,  # Native vector stream has full recognition certainty
            )
            all_spans.append(span)
            char_cursor += len(word) + 1  # accounts for space

            if block_no not in blocks_dict:
                blocks_dict[block_no] = {}
            if line_no not in blocks_dict[block_no]:
                blocks_dict[block_no][line_no] = []
            blocks_dict[block_no][line_no].append(span)

        # Assemble layout hierarchy
        blocks: List[TextBlock] = []
        for b_idx in sorted(blocks_dict.keys()):
            lines: List[TextLine] = []
            for l_idx in sorted(blocks_dict[b_idx].keys()):
                spans_in_line = blocks_dict[b_idx][l_idx]
                line_str = " ".join(s.raw_text for s in spans_in_line)
                lines.append(
                    TextLine(
                        line_index=l_idx,
                        raw_text=line_str,
                        spans=spans_in_line,
                    )
                )
            block_text = "\n".join(ln.raw_text for ln in lines)
            blocks.append(
                TextBlock(
                    block_index=b_idx,
                    block_type="paragraph",
                    lines=lines,
                    raw_text=block_text,
                )
            )

        raw_page_text = page.get_text()

        # Compute quality assessment metrics and decision state
        metrics, quality_state = self.assessor.assess_page(
            raw_text=raw_page_text,
            spans=all_spans,
            page_area=page_area,
            has_raster_images=has_raster,
            is_native_pdf=True,
        )

        # Apply bidirectional normalization
        norm_page_text, offset_map = TextNormalizer.normalize_with_offsets(raw_page_text)

        return PageLayout(
            page_number=page_number,
            width=width,
            height=height,
            extraction_method=PageExtractionMethod.NATIVE_PDF,
            quality_state=quality_state,
            quality_metrics=metrics,
            blocks=blocks,
            raw_page_text=raw_page_text,
            normalized_page_text=norm_page_text,
            offset_mapping=offset_map,
        )

import io
from typing import List, Optional, Union
from PIL import Image
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


class TesseractExtractor(BaseExtractor):
    """Baseline OCR extractor using Tesseract (pytesseract)."""

    def __init__(self, quality_assessor: QualityAssessor = None):
        self.assessor = quality_assessor or QualityAssessor()
        self._available = None

    def is_available(self) -> bool:
        if self._available is not None:
            return self._available
        try:
            import pytesseract
            # Check version to verify executable presence
            pytesseract.get_tesseract_version()
            self._available = True
        except Exception:
            self._available = False
        return self._available

    def extract_page(
        self,
        document_source: Union[str, bytes, Image.Image],
        page_number: int = 1,
        **kwargs,
    ) -> PageLayout:
        if not self.is_available() and not kwargs.get("mock_data"):
            raise RuntimeError(
                "Tesseract executable is not available in the runtime environment. "
                "Ensure tesseract is installed on PATH or configure alternative extractor."
            )

        # Allow passing mock data for deterministic hermetic unit tests
        if kwargs.get("mock_data"):
            return self._build_layout_from_ocr_tokens(
                kwargs["mock_data"], page_number, 1000.0, 1000.0, PageExtractionMethod.OCR_TESSERACT_BASELINE
            )

        import pytesseract

        img = self._load_image(document_source)
        width, height = float(img.width), float(img.height)

        # Run pytesseract image_to_data
        data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)

        ocr_tokens = []
        n_boxes = len(data["text"])
        for i in range(n_boxes):
            word = data["text"][i].strip()
            conf = float(data["conf"][i])
            if not word or conf < 0:
                continue

            x = data["left"][i]
            y = data["top"][i]
            w = data["width"][i]
            h = data["height"][i]

            norm_box = [
                round((x / width) * 1000.0, 1),
                round((y / height) * 1000.0, 1),
                round(((x + w) / width) * 1000.0, 1),
                round(((y + h) / height) * 1000.0, 1),
            ]
            ocr_tokens.append({
                "word": word,
                "confidence": max(0.0, min(1.0, conf / 100.0)),
                "box": norm_box,
                "line_no": data["line_num"][i],
                "block_no": data["block_num"][i],
            })

        return self._build_layout_from_ocr_tokens(
            ocr_tokens, page_number, width, height, PageExtractionMethod.OCR_TESSERACT_BASELINE
        )

    def extract_document(
        self,
        document_source: Union[str, bytes, Image.Image],
        **kwargs,
    ) -> List[PageLayout]:
        return [self.extract_page(document_source, page_number=1, **kwargs)]

    def _load_image(self, source: Union[str, bytes, Image.Image]) -> Image.Image:
        if isinstance(source, Image.Image):
            return source
        if isinstance(source, bytes):
            return Image.open(io.BytesIO(source))
        return Image.open(source)

    def _build_layout_from_ocr_tokens(
        self,
        tokens: List[dict],
        page_number: int,
        width: float,
        height: float,
        method: PageExtractionMethod,
    ) -> PageLayout:
        blocks_dict = {}
        all_spans: List[TextSpan] = []
        char_cursor = 0

        for t in tokens:
            word = t["word"]
            span = TextSpan(
                raw_text=word,
                raw_char_start=char_cursor,
                raw_char_end=char_cursor + len(word),
                bounding_box=t["box"],
                extraction_confidence=t["confidence"],
            )
            all_spans.append(span)
            char_cursor += len(word) + 1

            b_no = t.get("block_no", 0)
            l_no = t.get("line_no", 0)
            if b_no not in blocks_dict:
                blocks_dict[b_no] = {}
            if l_no not in blocks_dict[b_no]:
                blocks_dict[b_no][l_no] = []
            blocks_dict[b_no][l_no].append(span)

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
                        line_confidence=sum(s.extraction_confidence for s in spans_in_line) / len(spans_in_line),
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

        raw_page_text = "\n".join(b.raw_text for b in blocks)
        metrics, quality_state = self.assessor.assess_page(
            raw_text=raw_page_text,
            spans=all_spans,
            page_area=width * height,
            has_raster_images=True,
            is_native_pdf=False,
        )
        norm_page_text, offset_map = TextNormalizer.normalize_with_offsets(raw_page_text)

        return PageLayout(
            page_number=page_number,
            width=width,
            height=height,
            extraction_method=method,
            quality_state=quality_state,
            quality_metrics=metrics,
            blocks=blocks,
            raw_page_text=raw_page_text,
            normalized_page_text=norm_page_text,
            offset_mapping=offset_map,
        )


class PaddleOCRExtractor(BaseExtractor):
    """Candidate OCR extractor using PaddleOCR."""

    def __init__(self, quality_assessor: QualityAssessor = None):
        self.assessor = quality_assessor or QualityAssessor()
        self._engine = None
        self._available = None

    def is_available(self) -> bool:
        if self._available is not None:
            return self._available
        try:
            import paddleocr
            self._available = True
        except Exception:
            self._available = False
        return self._available

    def extract_page(
        self,
        document_source: Union[str, bytes, Image.Image],
        page_number: int = 1,
        **kwargs,
    ) -> PageLayout:
        if not self.is_available() and not kwargs.get("mock_data"):
            raise RuntimeError(
                "PaddleOCR is not available in the current environment. "
                "Install paddlepaddle and paddleocr to enable candidate OCR."
            )

        if kwargs.get("mock_data"):
            # Mock support for deterministic unit tests
            tess = TesseractExtractor(self.assessor)
            return tess._build_layout_from_ocr_tokens(
                kwargs["mock_data"], page_number, 1000.0, 1000.0, PageExtractionMethod.OCR_PADDLE_CANDIDATE
            )

        from paddleocr import PaddleOCR
        if self._engine is None:
            self._engine = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)

        # Process image with PaddleOCR
        img = TesseractExtractor(self.assessor)._load_image(document_source)
        width, height = float(img.width), float(img.height)

        # Convert PIL Image to format acceptable by PaddleOCR (numpy array or file path)
        import numpy as np
        img_np = np.array(img)

        result = self._engine.ocr(img_np, cls=True)
        ocr_tokens = []
        if result and result[0]:
            for idx, line in enumerate(result[0]):
                box_coords, (text_str, conf) = line
                # box_coords: [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
                xs = [pt[0] for pt in box_coords]
                ys = [pt[1] for pt in box_coords]
                norm_box = [
                    round((min(xs) / width) * 1000.0, 1),
                    round((min(ys) / height) * 1000.0, 1),
                    round((max(xs) / width) * 1000.0, 1),
                    round((max(ys) / height) * 1000.0, 1),
                ]
                ocr_tokens.append({
                    "word": text_str.strip(),
                    "confidence": float(conf),
                    "box": norm_box,
                    "line_no": idx,
                    "block_no": 0,
                })

        tess = TesseractExtractor(self.assessor)
        return tess._build_layout_from_ocr_tokens(
            ocr_tokens, page_number, width, height, PageExtractionMethod.OCR_PADDLE_CANDIDATE
        )

    def extract_document(
        self,
        document_source: Union[str, bytes, Image.Image],
        **kwargs,
    ) -> List[PageLayout]:
        return [self.extract_page(document_source, page_number=1, **kwargs)]

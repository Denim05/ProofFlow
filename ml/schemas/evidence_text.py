from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel, Field


class PageExtractionMethod(str, Enum):
    NATIVE_PDF = "NATIVE_PDF"
    OCR_PADDLE_CANDIDATE = "OCR_PADDLE_CANDIDATE"
    OCR_TESSERACT_BASELINE = "OCR_TESSERACT_BASELINE"
    HYBRID_MERGED = "HYBRID_MERGED"


class ExtractionQualityState(str, Enum):
    PASS = "PASS"
    OCR_RECOMMENDED = "OCR_RECOMMENDED"
    REVIEW_NEEDED = "REVIEW_NEEDED"


class TextSpan(BaseModel):
    """Atomic text token or word with spatial page coordinates."""

    raw_text: str
    raw_char_start: int = Field(..., ge=0)
    raw_char_end: int = Field(..., ge=0)
    bounding_box: Optional[List[float]] = Field(
        None,
        min_length=4,
        max_length=4,
        description="Coordinates [x0, y0, x1, y1] normalized to page dimensions [0..1000]",
    )
    extraction_confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Recognition confidence score, NOT factual truth or authenticity.",
    )


class OffsetMapEntry(BaseModel):
    """Maps a normalized character index range back to its raw character index range."""

    norm_start: int = Field(..., ge=0)
    norm_end: int = Field(..., ge=0)
    raw_start: int = Field(..., ge=0)
    raw_end: int = Field(..., ge=0)


class TextLine(BaseModel):
    line_index: int = Field(..., ge=0)
    raw_text: str
    spans: List[TextSpan] = Field(default_factory=list)
    bounding_box: Optional[List[float]] = None
    line_confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class TextBlock(BaseModel):
    block_index: int = Field(..., ge=0)
    block_type: str = Field(
        default="paragraph",
        description="paragraph | table_cell | header | list_item",
    )
    lines: List[TextLine] = Field(default_factory=list)
    raw_text: str
    bounding_box: Optional[List[float]] = None


class ExtractionQualityMetrics(BaseModel):
    """Empirical quality metrics informing extraction state decisions."""

    raw_character_count: int = Field(default=0, ge=0)
    word_count: int = Field(default=0, ge=0)
    alphanumeric_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    dictionary_word_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    mean_token_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    suspected_glyph_substitution_count: int = Field(default=0, ge=0)
    has_raster_images: bool = False
    is_scanned_page: bool = False


class PageLayout(BaseModel):
    """Per-page layout hierarchy preserving distinct extraction method provenance."""

    page_number: int = Field(..., ge=1)
    width: float = Field(..., ge=0.0)
    height: float = Field(..., ge=0.0)
    extraction_method: PageExtractionMethod
    quality_state: ExtractionQualityState
    quality_metrics: Optional[ExtractionQualityMetrics] = None
    blocks: List[TextBlock] = Field(default_factory=list)
    raw_page_text: str
    normalized_page_text: str
    offset_mapping: List[OffsetMapEntry] = Field(default_factory=list)


class EvidenceText(BaseModel):
    """Canonical, unmasked extracted text artifact preserving spatial and temporal provenance."""

    text_id: str = Field(default_factory=lambda: f"txt_{uuid.uuid4().hex[:24]}")
    evidence_id: str
    case_id: str
    full_raw_text: str
    full_normalized_text: str
    pages: List[PageLayout] = Field(default_factory=list)
    overall_quality_state: ExtractionQualityState
    quality_metrics: ExtractionQualityMetrics
    model_metadata: Dict[str, Any]
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = {
        "use_enum_values": True,
        "populate_by_name": True,
    }

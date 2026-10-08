from typing import List, Optional
from pydantic import BaseModel, Field


class SourceReference(BaseModel):
    """Reusable source grounding reference mapping an AI-derived object to raw evidence."""

    evidence_id: str = Field(..., description="Unique identifier of the parent evidence item")
    page_number: Optional[int] = Field(None, ge=1, description="Page index (1-indexed) if document has pages")
    char_start: Optional[int] = Field(None, ge=0, description="Starting character offset in text stream")
    char_end: Optional[int] = Field(None, ge=0, description="Ending character offset in text stream")
    bounding_box: Optional[List[float]] = Field(
        None,
        min_length=4,
        max_length=4,
        description="Bounding coordinates [x0, y0, x1, y1] on visual media or PDF page",
    )
    raw_snippet: Optional[str] = Field(None, description="Exact textual excerpt extracted from the source")
    source_type: Optional[str] = Field(
        None,
        description="Format medium: PDF, IMAGE, WHATSAPP_CHAT, EMAIL, BANK_STATEMENT, RECEIPT",
    )

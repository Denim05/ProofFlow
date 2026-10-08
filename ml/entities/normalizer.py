from decimal import Decimal
import re
from typing import Any, Dict, List, Optional, Tuple
from ml.entities.config import EntityExtractorConfig, entity_config
from ml.entities.deterministic import RawEntitySpan
from ml.schemas.entity import (
    EntityType,
    MonetaryValue,
    PhoneNumberValue,
    RelativeTimeResolution,
)
from ml.schemas.evidence_text import EvidenceText, PageLayout, TextSpan
from ml.schemas.source_reference import SourceReference


class EntityNormalizer:
    """Normalizes raw extracted entity values into lossless, safe canonical formats."""

    def __init__(self, config: EntityExtractorConfig = entity_config):
        self.config = config

    def normalize(
        self,
        span: RawEntitySpan,
        country_context: Optional[str] = None,
    ) -> Optional[Any]:
        """Normalizes an extracted span based on entity type without destructive assumptions."""
        etype = span.entity_type
        raw = span.raw_value.strip()

        # 1. Monetary Amount -> Exact Decimal
        if etype == EntityType.MONETARY_AMOUNT:
            return self._normalize_money(span)

        # 2. Phone Number -> Grounded E.164 or Local Number
        elif etype == EntityType.PHONE_NUMBER:
            return self._normalize_phone(span, country_context)

        # 3. Date -> ISO-8601 (or None if ambiguous)
        elif etype == EntityType.DATE:
            if span.metadata.get("is_ambiguous"):
                # NEVER guess when ambiguous!
                return {
                    "ambiguous": True,
                    "candidate_dates": span.metadata.get("candidate_dates", []),
                }
            return span.metadata.get("iso_date", raw)

        # 4. Time
        elif etype == EntityType.TIME:
            return span.metadata.get("norm_time", raw)

        # 5. Relative Time
        elif etype == EntityType.RELATIVE_TIME:
            return span.metadata.get("relative_resolution")

        # 6. Structured IDs (Transaction, Order, Invoice, Refund)
        elif etype in (
            EntityType.TRANSACTION_ID,
            EntityType.ORDER_ID,
            EntityType.INVOICE_ID,
            EntityType.REFUND_ID,
        ):
            clean_id = span.metadata.get("clean_id")
            if not clean_id:
                # Strip prefix label and punctuation
                parts = re.split(r"[\-_:\s#]+", raw)
                clean_id = parts[-1] if len(parts) > 1 else raw
            return clean_id.strip().upper()

        # 7. Email
        elif etype == EntityType.EMAIL:
            return raw.lower()

        # 8. URL
        elif etype == EntityType.URL:
            return raw.strip()

        # 9. Person / Organization / Address
        elif etype in (EntityType.PERSON, EntityType.ORGANIZATION, EntityType.ADDRESS):
            # Clean extra whitespace
            return " ".join(raw.split())

        return raw

    def _normalize_money(self, span: RawEntitySpan) -> MonetaryValue:
        raw = span.raw_value
        meta = span.metadata

        curr_raw = meta.get("currency_raw", "")
        num_raw = meta.get("amount_raw", "")

        if not curr_raw or not num_raw:
            # Fallback parse from raw text
            for k, code in self.config.currency_map.items():
                if k.lower() in raw.lower():
                    curr_raw = k
                    break
            # Extract digits and punctuation
            clean_num = re.sub(r"[^\d.,]", "", raw)
            num_raw = clean_num

        # Resolve ISO currency
        currency_code = self.config.currency_map.get(curr_raw.lower().strip(), "USD")

        # Clean number formatting (Western 100,000.00 or Indian 1,00,000.00)
        clean_digits = num_raw.replace(",", "").replace(" ", "").strip()
        try:
            dec_value = Decimal(clean_digits)
        except Exception:
            dec_value = Decimal("0.00")

        return MonetaryValue(value=dec_value, currency=currency_code)

    def _normalize_phone(
        self,
        span: RawEntitySpan,
        country_context: Optional[str] = None,
    ) -> PhoneNumberValue:
        raw = span.raw_value
        meta = span.metadata
        digits = meta.get("digits_only", re.sub(r"\D", "", raw))
        country_prefix = meta.get("country_prefix")

        # Case A: Explicit international prefix on number (e.g. +91 9876543210 or +1 5551234567)
        if span.raw_value.startswith("+") and country_prefix:
            e164 = f"+{digits}"
            return PhoneNumberValue(
                raw_number=raw,
                country_code=f"+{country_prefix}",
                e164_formatted=e164,
            )

        # Case B: Grounded via document context (e.g. context specifies "IN" or "+91")
        if country_context in ("IN", "+91", "India") and len(digits) == 10:
            return PhoneNumberValue(
                raw_number=raw,
                country_code="+91",
                e164_formatted=f"+91{digits}",
            )
        elif country_context in ("US", "+1", "USA") and len(digits) == 10:
            return PhoneNumberValue(
                raw_number=raw,
                country_code="+1",
                e164_formatted=f"+1{digits}",
            )

        # Case C: Country context unknown / unanchored
        # Safety Mandate: NEVER guess E.164 without grounded country context!
        return PhoneNumberValue(
            raw_number=raw,
            country_code="UNKNOWN",
            e164_formatted=None,
        )


class SpatialProvenanceMapper:
    """Binds character offset spans in EvidenceText to physical pages and bounding boxes."""

    @staticmethod
    def map_span_to_provenance(
        evidence_text: EvidenceText,
        char_start: int,
        char_end: int,
        raw_snippet: str,
    ) -> SourceReference:
        """Finds the page number and spatial bounding box corresponding to character offsets."""
        evidence_id = evidence_text.evidence_id

        # Determine which page contains these character offsets
        # by checking pages and cumulative text offset
        curr_offset = 0
        target_page: Optional[PageLayout] = None
        rel_start = char_start
        rel_end = char_end

        for page in evidence_text.pages:
            page_len = len(page.raw_page_text)
            if curr_offset <= char_start <= curr_offset + page_len:
                target_page = page
                rel_start = char_start - curr_offset
                rel_end = char_end - curr_offset
                break
            # Add 2 for inter-page newline separation "\n\n"
            curr_offset += page_len + 2

        if target_page is None:
            # Fallback to first page if offsets cannot be segmented
            target_page = evidence_text.pages[0] if evidence_text.pages else None
            page_no = 1
        else:
            page_no = target_page.page_number

        # Find intersecting spans on the target page
        intersecting_boxes: List[List[float]] = []
        if target_page:
            for block in target_page.blocks:
                for line in block.lines:
                    for span in line.spans:
                        s_start = getattr(span, "raw_char_start", getattr(span, "char_start", 0))
                        s_end = getattr(span, "raw_char_end", getattr(span, "char_end", 0))
                        if max(s_start, rel_start) < min(s_end, rel_end) and span.bounding_box:
                            intersecting_boxes.append(span.bounding_box)

        # Union bounding boxes
        union_bbox: Optional[List[float]] = None
        if intersecting_boxes:
            x0 = min(b[0] for b in intersecting_boxes)
            y0 = min(b[1] for b in intersecting_boxes)
            x1 = max(b[2] for b in intersecting_boxes)
            y1 = max(b[3] for b in intersecting_boxes)
            union_bbox = [round(x0, 1), round(y0, 1), round(x1, 1), round(y1, 1)]

        return SourceReference(
            evidence_id=evidence_id,
            page_number=page_no,
            char_start=char_start,
            char_end=char_end,
            bounding_box=union_bbox,
            raw_snippet=raw_snippet,
            source_type="PDF" if evidence_text.pages else "IMAGE",
        )

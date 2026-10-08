import re
from typing import Any, Dict, List, Optional, Tuple
from ml.entities.config import EntityExtractorConfig, entity_config
from ml.schemas.entity import EntityType


class RawEntitySpan:
    """Intermediate extracted entity candidate prior to normalization and spatial grounding."""

    def __init__(
        self,
        entity_type: EntityType,
        raw_value: str,
        char_start: int,
        char_end: int,
        confidence: float = 1.0,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.entity_type = entity_type
        self.raw_value = raw_value
        self.char_start = char_start
        self.char_end = char_end
        self.confidence = confidence
        self.metadata = metadata or {}


class DeterministicExtractor:
    """Linear-time, offline pattern-matching extractors for structured domain entities."""

    def __init__(self, config: EntityExtractorConfig = entity_config):
        self.config = config
        self._compile_patterns()

    def _compile_patterns(self):
        # 1. Email pattern
        self.email_re = re.compile(
            r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,7}\b"
        )

        # 2. URL pattern
        self.url_re = re.compile(
            r"\bhttps?://[A-Za-z0-9.\-]+(?::\d+)?(?:/[^\s<>'\"`]*)*",
            re.IGNORECASE,
        )

        # 3. Monetary Amount pattern
        # Matches: [Symbol/Code] [Digits with commas] [.optional cents] OR [Digits] [Symbol/Code]
        currency_keys = [re.escape(k) for k in self.config.currency_map.keys()]
        curr_group = "|".join(sorted(currency_keys, key=len, reverse=True))

        # Matches: ₹ 2,499.50, INR 10,000, $45.50, 100 USD, Rs. 500
        self.money_prefix_re = re.compile(
            rf"(?<![A-Za-z0-9])(?P<curr>{curr_group})\s*(?P<num>\d{{1,3}}(?:[,\s]\d{{2,3}})*(?:\.\d{{1,4}})?|\d+(?:\.\d{{1,4}})?)\b",
            re.IGNORECASE,
        )
        self.money_suffix_re = re.compile(
            rf"(?<![A-Za-z0-9])(?P<num>\d{{1,3}}(?:[,\s]\d{{2,3}})*(?:\.\d{{1,4}})?|\d+(?:\.\d{{1,4}})?)\s*(?P<curr>{curr_group})(?![A-Za-z0-9])",
            re.IGNORECASE,
        )

        # 4. Domain Identifiers: Transaction, Order, Invoice, Refund
        txn_p = "|".join(self.config.txn_prefixes)
        self.txn_re = re.compile(
            rf"\b(?:{txn_p})[\-_:\s#]+([A-Za-z0-9]{{5,32}})\b",
            re.IGNORECASE,
        )
        # Standalone banking UTR: 12-16 uppercase alphanumeric characters starting with letters
        self.utr_re = re.compile(
            r"\b(UTR[A-Za-z0-9]{10,20})\b",
            re.IGNORECASE,
        )

        order_p = "|".join(self.config.order_prefixes)
        self.order_re = re.compile(
            rf"\b(?:{order_p})[\-_:\s#]+([A-Za-z0-9]{{4,24}})\b",
            re.IGNORECASE,
        )

        inv_p = "|".join(self.config.invoice_prefixes)
        self.inv_re = re.compile(
            rf"\b(?:{inv_p})[\-_:\s#]+([A-Za-z0-9]{{4,24}})\b",
            re.IGNORECASE,
        )

        ref_p = "|".join(self.config.refund_prefixes)
        self.ref_re = re.compile(
            rf"\b(?:{ref_p})[\-_:\s#]+([A-Za-z0-9]{{4,24}})\b",
            re.IGNORECASE,
        )

        # 5. Case H OCR Resilience: Candidate transaction matching with glyph substitutions
        # E.g. TXN-O09I82 where 'O' is substituted for '0', 'I' for '1'
        self.txn_ocr_confused_re = re.compile(
            r"\b(TXN[\-_:\s#]+[A-Za-z0-9]{5,20})\b",
            re.IGNORECASE,
        )

        # 6. Phone Numbers: Bounded local and international numbers
        # Matches e.g. +91 98765 43210, +1-555-123-4567, 9876543210
        self.phone_re = re.compile(
            r"(?<!\w)(?:\+(?P<intl>\d{1,3})[\s\-]?)?(?:\(?\d{2,4}\)?[\s\-]?)?\d{3,5}[\s\-]?\d{3,5}(?!\w)"
        )

    def extract_spans(self, text: str) -> List[RawEntitySpan]:
        """Extracts deterministic entity spans from text while enforcing length caps for ReDoS safety."""
        if not text:
            return []

        # Bound block text length to prevent exponential backtracking
        capped_text = text[: self.config.max_block_char_length]
        spans: List[RawEntitySpan] = []

        # 1. Emails
        for m in self.email_re.finditer(capped_text):
            spans.append(
                RawEntitySpan(
                    entity_type=EntityType.EMAIL,
                    raw_value=m.group(0),
                    char_start=m.start(),
                    char_end=m.end(),
                    confidence=1.0,
                    metadata={"pattern": "rfc5322_email"},
                )
            )

        # 2. URLs
        for m in self.url_re.finditer(capped_text):
            url_str = m.group(0).rstrip(".,;:!?)")
            spans.append(
                RawEntitySpan(
                    entity_type=EntityType.URL,
                    raw_value=url_str,
                    char_start=m.start(),
                    char_end=m.start() + len(url_str),
                    confidence=1.0,
                    metadata={"pattern": "http_url"},
                )
            )

        # 3. Monetary Amounts (Prefix & Suffix)
        for m in self.money_prefix_re.finditer(capped_text):
            spans.append(
                RawEntitySpan(
                    entity_type=EntityType.MONETARY_AMOUNT,
                    raw_value=m.group(0),
                    char_start=m.start(),
                    char_end=m.end(),
                    confidence=0.98,
                    metadata={
                        "currency_raw": m.group("curr"),
                        "amount_raw": m.group("num"),
                    },
                )
            )
        for m in self.money_suffix_re.finditer(capped_text):
            # Avoid duplicate if prefix already covered this span
            if not any(s.char_start <= m.start() and s.char_end >= m.end() for s in spans):
                spans.append(
                    RawEntitySpan(
                        entity_type=EntityType.MONETARY_AMOUNT,
                        raw_value=m.group(0),
                        char_start=m.start(),
                        char_end=m.end(),
                        confidence=0.98,
                        metadata={
                            "currency_raw": m.group("curr"),
                            "amount_raw": m.group("num"),
                        },
                    )
                )

        # 4. Domain Identifiers
        # Invoices
        for m in self.inv_re.finditer(capped_text):
            spans.append(
                RawEntitySpan(
                    entity_type=EntityType.INVOICE_ID,
                    raw_value=m.group(0),
                    char_start=m.start(),
                    char_end=m.end(),
                    confidence=0.95,
                    metadata={"clean_id": m.group(1)},
                )
            )

        # Refunds
        for m in self.ref_re.finditer(capped_text):
            spans.append(
                RawEntitySpan(
                    entity_type=EntityType.REFUND_ID,
                    raw_value=m.group(0),
                    char_start=m.start(),
                    char_end=m.end(),
                    confidence=0.95,
                    metadata={"clean_id": m.group(1)},
                )
            )

        # Orders
        for m in self.order_re.finditer(capped_text):
            spans.append(
                RawEntitySpan(
                    entity_type=EntityType.ORDER_ID,
                    raw_value=m.group(0),
                    char_start=m.start(),
                    char_end=m.end(),
                    confidence=0.95,
                    metadata={"clean_id": m.group(1)},
                )
            )

        # Transactions
        for m in self.txn_re.finditer(capped_text):
            clean_id = m.group(1)
            has_suspected_substitution = False
            conf = 0.95
            if self.config.enable_ocr_confusion_resilience:
                if re.search(r"\d", clean_id) and re.search(r"[OIl]", clean_id):
                    has_suspected_substitution = True
                    conf -= self.config.ocr_substitution_confidence_penalty

            spans.append(
                RawEntitySpan(
                    entity_type=EntityType.TRANSACTION_ID,
                    raw_value=m.group(0),
                    char_start=m.start(),
                    char_end=m.end(),
                    confidence=round(conf, 2),
                    metadata={
                        "clean_id": clean_id,
                        "is_ambiguous": has_suspected_substitution,
                        "candidate_ocr_variant": has_suspected_substitution,
                    },
                )
            )
        for m in self.utr_re.finditer(capped_text):
            if not any(s.char_start <= m.start() and s.char_end >= m.end() for s in spans):
                spans.append(
                    RawEntitySpan(
                        entity_type=EntityType.TRANSACTION_ID,
                        raw_value=m.group(0),
                        char_start=m.start(),
                        char_end=m.end(),
                        confidence=0.95,
                        metadata={"clean_id": m.group(1)},
                    )
                )

        # Case H candidate check for noisy OCR
        if self.config.enable_ocr_confusion_resilience:
            for m in self.txn_ocr_confused_re.finditer(capped_text):
                # Only consider if not already matched by strict txn_re
                if not any(s.char_start <= m.start() and s.char_end >= m.end() for s in spans):
                    val = m.group(1)
                    # Check if string contains suspected OCR glyph confusion (e.g. 'O' or 'I' where digits expected)
                    has_suspected_substitution = bool(re.search(r"[OIl|]", val))
                    conf = 0.90
                    if has_suspected_substitution:
                        conf -= self.config.ocr_substitution_confidence_penalty
                    spans.append(
                        RawEntitySpan(
                            entity_type=EntityType.TRANSACTION_ID,
                            raw_value=m.group(0),
                            char_start=m.start(),
                            char_end=m.end(),
                            confidence=round(conf, 2),
                            metadata={
                                "is_ambiguous": has_suspected_substitution,
                                "candidate_ocr_variant": True,
                            },
                        )
                    )

        # 5. Phone Numbers
        for m in self.phone_re.finditer(capped_text):
            raw_ph = m.group(0).strip()
            # Filter out strings with fewer than 7 digits or sequences that overlap with other spans
            digits_only = re.sub(r"\D", "", raw_ph)
            if 7 <= len(digits_only) <= 15:
                # Ensure it doesn't overlap with already extracted monetary or ID spans
                if not any(max(s.char_start, m.start()) < min(s.char_end, m.end()) for s in spans):
                    intl = m.group("intl")
                    spans.append(
                        RawEntitySpan(
                            entity_type=EntityType.PHONE_NUMBER,
                            raw_value=raw_ph,
                            char_start=m.start(),
                            char_end=m.end(),
                            confidence=0.90 if intl else 0.80,
                            metadata={
                                "digits_only": digits_only,
                                "has_international_prefix": bool(intl),
                                "country_prefix": intl,
                            },
                        )
                    )

        return spans

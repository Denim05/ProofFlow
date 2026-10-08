from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class EntityExtractorConfig(BaseModel):
    """Configuration settings for deterministic extractors, pattern libraries, and NLP settings.

    NOTE: Pattern thresholds and candidate settings are parameterized here for empirical tuning
    rather than embedded as hard-coded constants.
    """

    # Maximum characters processed per block to prevent ReDoS on malicious or degenerate input
    max_block_char_length: int = Field(default=15000, ge=100)

    # NLP settings
    enable_nlp: bool = Field(default=True, description="Enable statistical NLP extraction if available")
    nlp_model_name: str = Field(default="mock", description="'mock' for hermetic tests, or local model e.g. 'en_core_web_sm'")

    # Currency mappings (normalized to ISO-4217 code)
    currency_map: Dict[str, str] = Field(
        default_factory=lambda: {
            "₹": "INR",
            "rs": "INR",
            "rs.": "INR",
            "inr": "INR",
            "$": "USD",
            "usd": "USD",
            "€": "EUR",
            "eur": "EUR",
            "£": "GBP",
            "gbp": "GBP",
            "cad": "CAD",
            "aud": "AUD",
            "jpy": "JPY",
            "¥": "JPY",
        }
    )

    # Known business and payment identifier prefixes
    txn_prefixes: List[str] = Field(
        default_factory=lambda: ["TXN", "TRX", "UTR", "UPI", "TRANS", "TRANSACTION", "PAY"]
    )
    order_prefixes: List[str] = Field(
        default_factory=lambda: ["ORD", "ORDER", "OD", "PO"]
    )
    invoice_prefixes: List[str] = Field(
        default_factory=lambda: ["INV", "INVOICE", "BILL"]
    )
    refund_prefixes: List[str] = Field(
        default_factory=lambda: ["RFD", "REFUND", "RET"]
    )

    # Candidate ambiguity tolerances for Case H OCR resilience
    # Allows localized character class variation (e.g., 'O' for '0') while reducing token confidence
    enable_ocr_confusion_resilience: bool = Field(
        default=True,
        description="Enables candidate regex variants tolerant of OCR glyph confusion in identifiers",
    )
    ocr_substitution_confidence_penalty: float = Field(
        default=0.20,
        ge=0.0,
        le=1.0,
        description="Confidence deduction when candidate OCR glyph confusion is detected",
    )


# Default singleton configuration
entity_config = EntityExtractorConfig()

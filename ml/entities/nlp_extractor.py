import re
from typing import List, Optional
from ml.entities.base import BaseNLPExtractor
from ml.entities.deterministic import RawEntitySpan
from ml.schemas.entity import EntityType


class MockNLPExtractor(BaseNLPExtractor):
    """Hermetic, offline mock NLP extractor for test environments.

    Recognizes standard contextual names, merchants, and institutions without
    external model downloads or network dependencies.
    """

    def __init__(self, custom_entities: Optional[List[dict]] = None):
        self.custom_entities = custom_entities or []
        # Predefined mock recognition dictionary for deterministic evaluation
        self._mock_orgs = [
            "Acme Corp", "Acme Store", "Amazon", "Flipkart", "PayPal", "Stripe",
            "State Bank of India", "HDFC Bank", "ICICI Bank", "Chase Bank", "FedEx", "DHL",
            "Example Store", "Example Store Support", "Store Support", "Customer Support",
        ]
        self._mock_persons = [
            "John Doe", "Jane Smith", "Alice Johnson", "Bob Miller", "Rahul Sharma", "Priya Patel",
            "Customer",
        ]
        # Structured postal address heuristic (requires street/road/building keyword + digits/PIN)
        self._address_re = re.compile(
            r"\b\d{1,4}[,\s]+[A-Za-z0-9\s,\-]+(?:Street|St|Road|Rd|Avenue|Ave|Lane|Ln|Nagar|Colony|Sector\s*\d+)[,\s]+[A-Za-z\s]+(?:\d{5,6})?\b",
            re.IGNORECASE,
        )

    def extract_nlp_entities(self, text: str) -> List[RawEntitySpan]:
        spans: List[RawEntitySpan] = []

        # 1. Custom injected mock entities (for test control)
        for item in self.custom_entities:
            val = item["text"]
            etype = item["type"]
            for m in re.finditer(re.escape(val), text):
                spans.append(
                    RawEntitySpan(
                        entity_type=etype,
                        raw_value=m.group(0),
                        char_start=m.start(),
                        char_end=m.end(),
                        confidence=item.get("confidence", 0.95),
                        metadata={"source": "custom_mock_nlp"},
                    )
                )

        # 2. Known organizations
        for org in self._mock_orgs:
            for m in re.finditer(rf"\b{re.escape(org)}\b", text, re.IGNORECASE):
                if not any(s.char_start <= m.start() and s.char_end >= m.end() for s in spans):
                    spans.append(
                        RawEntitySpan(
                            entity_type=EntityType.ORGANIZATION,
                            raw_value=m.group(0),
                            char_start=m.start(),
                            char_end=m.end(),
                            confidence=0.92,
                            metadata={"source": "mock_nlp_dictionary"},
                        )
                    )

        # 3. Known persons
        for person in self._mock_persons:
            for m in re.finditer(rf"\b{re.escape(person)}\b", text, re.IGNORECASE):
                if not any(s.char_start <= m.start() and s.char_end >= m.end() for s in spans):
                    spans.append(
                        RawEntitySpan(
                            entity_type=EntityType.PERSON,
                            raw_value=m.group(0),
                            char_start=m.start(),
                            char_end=m.end(),
                            confidence=0.90,
                            metadata={"source": "mock_nlp_dictionary"},
                        )
                    )

        # 4. Structured Address (explicitly NOT matching bare cities/countries!)
        for m in self._address_re.finditer(text):
            if not any(s.char_start <= m.start() and s.char_end >= m.end() for s in spans):
                spans.append(
                    RawEntitySpan(
                        entity_type=EntityType.ADDRESS,
                        raw_value=m.group(0).strip(),
                        char_start=m.start(),
                        char_end=m.end(),
                        confidence=0.88,
                        metadata={"source": "address_structured_heuristic"},
                    )
                )

        return spans


class SpacyNLPExtractor(BaseNLPExtractor):
    """Optional runtime adapter for locally installed spaCy models.

    CRITICAL: Does NOT download models at runtime. If the model is not found,
    it raises a clear RuntimeError or falls back safely.
    """

    def __init__(self, model_name: str = "en_core_web_sm"):
        self.model_name = model_name
        self._nlp = None

    def _get_nlp(self):
        if self._nlp is None:
            try:
                import spacy
                self._nlp = spacy.load(self.model_name)
            except Exception as e:
                raise RuntimeError(
                    f"Local spaCy model '{self.model_name}' could not be loaded: {str(e)}. "
                    "In test environments, use MockNLPExtractor."
                )
        return self._nlp

    def extract_nlp_entities(self, text: str) -> List[RawEntitySpan]:
        nlp = self._get_nlp()
        doc = nlp(text)
        spans: List[RawEntitySpan] = []

        type_map = {
            "PERSON": EntityType.PERSON,
            "ORG": EntityType.ORGANIZATION,
        }

        for ent in doc.ents:
            if ent.label_ in type_map:
                spans.append(
                    RawEntitySpan(
                        entity_type=type_map[ent.label_],
                        raw_value=ent.text,
                        char_start=ent.start_char,
                        char_end=ent.end_char,
                        confidence=0.85,
                        metadata={"spacy_label": ent.label_},
                    )
                )
            # Note: GPE, LOC, and FAC are intentionally NOT converted to ADDRESS here
            # to prevent standalone cities/countries from being mislabeled as physical addresses.

        return spans

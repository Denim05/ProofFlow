from abc import ABC, abstractmethod
from typing import List
from ml.entities.deterministic import RawEntitySpan


class BaseEntityExtractor(ABC):
    """Abstract interface for entity extraction engines."""

    @abstractmethod
    def extract_spans(self, text: str) -> List[RawEntitySpan]:
        """Extracts entity spans from a text block."""
        pass


class BaseNLPExtractor(ABC):
    """Abstract interface for statistical or pretrained NLP named-entity recognition."""

    @abstractmethod
    def extract_nlp_entities(self, text: str) -> List[RawEntitySpan]:
        """Extracts contextual entities (Person, Organization, Address) from text."""
        pass

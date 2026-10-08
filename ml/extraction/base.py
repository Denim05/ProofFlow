from abc import ABC, abstractmethod
from typing import List, Union
from ml.schemas.evidence_text import PageLayout


class BaseExtractor(ABC):
    """Abstract interface for all document and OCR extractors."""

    @abstractmethod
    def extract_page(
        self,
        document_source: Union[str, bytes],
        page_number: int = 1,
        **kwargs,
    ) -> PageLayout:
        """Extracts a single page layout with spatial token coordinates."""
        pass

    @abstractmethod
    def extract_document(
        self,
        document_source: Union[str, bytes],
        **kwargs,
    ) -> List[PageLayout]:
        """Extracts all pages from a multi-page document."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Verifies runtime availability of the underlying engine."""
        pass

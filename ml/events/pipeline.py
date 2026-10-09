from typing import Any, Dict, List, Optional
from ml.entities.pipeline import EntityExtractionPipeline
from ml.events.config import EventExtractionConfig, event_config
from ml.events.detector import EventDetector
from ml.events.extractor import EventArgumentExtractor
from ml.schemas.entity import EntityMention
from ml.schemas.event import Event
from ml.schemas.evidence_text import EvidenceText


class EventExtractionPipeline:
    """End-to-end pipeline transforming EvidenceText and EntityMentions into structured Events."""

    def __init__(
        self,
        config: EventExtractionConfig = event_config,
        entity_pipeline: Optional[EntityExtractionPipeline] = None,
    ):
        self.config = config
        self.detector = EventDetector(config)
        self.argument_extractor = EventArgumentExtractor(config)
        self.entity_pipeline = entity_pipeline or EntityExtractionPipeline()

    def process_evidence(
        self,
        evidence_text: EvidenceText,
        entities: Optional[List[EntityMention]] = None,
        document_anchor: Optional[Dict[str, Any]] = None,
        country_context: Optional[str] = None,
    ) -> List[Event]:
        """Extracts structured, source-grounded Events from EvidenceText."""
        if not evidence_text or not evidence_text.full_raw_text:
            return []

        # 1. Extract entities if not already provided
        if entities is None:
            entities = self.entity_pipeline.process_evidence_text(
                evidence_text=evidence_text,
                document_anchor=document_anchor,
                country_context=country_context,
            )

        # 2. Detect event candidate triggers with polarity & modality analysis
        candidates = self.detector.detect_candidates(evidence_text.full_raw_text)

        # 3. Bind proximal entities to each event candidate
        events: List[Event] = []
        for candidate in candidates:
            event = self.argument_extractor.bind_arguments_to_event(
                candidate=candidate,
                evidence_text=evidence_text,
                entities=entities,
            )
            events.append(event)

        return events

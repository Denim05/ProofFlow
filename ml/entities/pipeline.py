from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from ml.entities.base import BaseNLPExtractor
from ml.entities.config import EntityExtractorConfig, entity_config
from ml.entities.deterministic import DeterministicExtractor, RawEntitySpan
from ml.entities.nlp_extractor import MockNLPExtractor, SpacyNLPExtractor
from ml.entities.normalizer import EntityNormalizer, SpatialProvenanceMapper
from ml.entities.temporal import TemporalExtractor
from ml.schemas.entity import EntityMention, EntityType
from ml.schemas.evidence_text import EvidenceText


class EntityExtractionPipeline:
    """Orchestrates deterministic, temporal, and NLP entity extraction with strict spatial grounding."""

    def __init__(
        self,
        config: EntityExtractorConfig = entity_config,
        nlp_extractor: Optional[BaseNLPExtractor] = None,
    ):
        self.config = config
        self.deterministic_extractor = DeterministicExtractor(config)
        self.temporal_extractor = TemporalExtractor()
        self.normalizer = EntityNormalizer(config)

        if nlp_extractor is not None:
            self.nlp_extractor = nlp_extractor
        elif config.nlp_model_name == "mock":
            self.nlp_extractor = MockNLPExtractor()
        else:
            try:
                self.nlp_extractor = SpacyNLPExtractor(config.nlp_model_name)
            except Exception:
                # Safe fallback to mock in test/offline environments
                self.nlp_extractor = MockNLPExtractor()

    def process_evidence_text(
        self,
        evidence_text: EvidenceText,
        document_anchor: Optional[Dict[str, Any]] = None,
        country_context: Optional[str] = None,
    ) -> List[EntityMention]:
        """Extracts all structured entity mentions from canonical EvidenceText."""
        text = evidence_text.full_raw_text
        if not text:
            return []

        # 1. Deterministic extractions (Highest Priority)
        det_spans = self.deterministic_extractor.extract_spans(text)
        temp_spans = self.temporal_extractor.extract_temporal_spans(text, document_anchor)

        all_det_spans = det_spans + temp_spans

        # 2. Statistical NLP extractions (Lower Priority)
        nlp_spans: List[RawEntitySpan] = []
        if self.config.enable_nlp and self.nlp_extractor:
            nlp_spans = self.nlp_extractor.extract_nlp_entities(text)

        # 3. Span Overlap & Conflict Resolution
        resolved_spans = self._resolve_overlaps(all_det_spans, nlp_spans)

        # 4. Normalization and Spatial Provenance Mapping
        mentions: List[EntityMention] = []
        for span in resolved_spans:
            normalized_val = self.normalizer.normalize(span, country_context)

            source_ref = SpatialProvenanceMapper.map_span_to_provenance(
                evidence_text=evidence_text,
                char_start=span.char_start,
                char_end=span.char_end,
                raw_snippet=span.raw_value,
            )

            # Determine method tag
            method = (
                "DETERMINISTIC_REGEX"
                if span in all_det_spans
                else "PRETRAINED_NLP"
            )

            mention = EntityMention(
                entity_id=f"ent_{uuid.uuid4().hex[:24]}",
                case_id=evidence_text.case_id,
                evidence_id=evidence_text.evidence_id,
                entity_type=span.entity_type,
                raw_value=span.raw_value,
                normalized_value=normalized_val,
                extraction_confidence=span.confidence,
                extraction_method=method,
                source_reference=source_ref,
                model_metadata={
                    "extractor_type": method,
                    "span_metadata": span.metadata,
                },
                created_at=datetime.now(timezone.utc),
            )
            mentions.append(mention)

        return mentions

    def _resolve_overlaps(
        self,
        deterministic_spans: List[RawEntitySpan],
        nlp_spans: List[RawEntitySpan],
    ) -> List[RawEntitySpan]:
        """Resolves overlapping spans by giving absolute priority to deterministic matches."""
        # Sort deterministic spans by start position, then by span length descending
        sorted_det = sorted(
            deterministic_spans,
            key=lambda s: (s.char_start, -(s.char_end - s.char_start)),
        )

        final_spans: List[RawEntitySpan] = []
        for s in sorted_det:
            # Check overlap with already accepted deterministic spans
            if not any(max(s.char_start, ex.char_start) < min(s.char_end, ex.char_end) for ex in final_spans):
                final_spans.append(s)

        # Filter NLP spans: keep only those that do NOT collide with any deterministic span
        for nlp in nlp_spans:
            collides = any(
                max(nlp.char_start, det.char_start) < min(nlp.char_end, det.char_end)
                for det in final_spans
            )
            if not collides:
                # Also ensure no collision with another accepted NLP span
                if not any(
                    max(nlp.char_start, ex.char_start) < min(nlp.char_end, ex.char_end)
                    for ex in final_spans
                ):
                    final_spans.append(nlp)

        # Sort all final accepted spans by character start position
        return sorted(final_spans, key=lambda s: s.char_start)

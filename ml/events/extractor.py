from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from ml.entities.normalizer import SpatialProvenanceMapper
from ml.events.config import EventExtractionConfig, event_config
from ml.events.detector import EventCandidate
from ml.schemas.entity import EntityMention, EntityType, MonetaryValue
from ml.schemas.event import Event, EventTrigger
from ml.schemas.evidence_text import EvidenceText


class EventArgumentExtractor:
    """Binds proximal Track 3 EntityMentions to detected event candidates."""

    def __init__(self, config: EventExtractionConfig = event_config):
        self.config = config

    def bind_arguments_to_event(
        self,
        candidate: EventCandidate,
        evidence_text: EvidenceText,
        entities: List[EntityMention],
    ) -> Event:
        """Constructs a fully grounded Event by associating nearby entities to candidate slots."""
        # 1. Build trigger provenance
        trigger_ref = SpatialProvenanceMapper.map_span_to_provenance(
            evidence_text=evidence_text,
            char_start=candidate.char_start,
            char_end=candidate.char_end,
            raw_snippet=candidate.trigger_text,
        )
        trigger = EventTrigger(
            raw_text=candidate.trigger_text,
            char_start=candidate.char_start,
            char_end=candidate.char_end,
            source_reference=trigger_ref,
        )

        # 2. Filter entities within context sentence or max character distance
        proximal_entities = self._find_proximal_entities(candidate, entities)

        # 3. Bind slots based on proximity to trigger
        amount_mention = self._find_closest(candidate, proximal_entities, [EntityType.MONETARY_AMOUNT])
        order_mention = self._find_closest(candidate, proximal_entities, [EntityType.ORDER_ID])
        txn_mention = self._find_closest(candidate, proximal_entities, [EntityType.TRANSACTION_ID])
        refund_mention = self._find_closest(candidate, proximal_entities, [EntityType.REFUND_ID])
        temporal_mention = self._find_closest(
            candidate,
            proximal_entities,
            [EntityType.DATE, EntityType.DATETIME],
        )
        if not temporal_mention:
            temporal_mention = self._find_closest(
                candidate,
                proximal_entities,
                [EntityType.TIME, EntityType.RELATIVE_TIME],
            )

        # Actors and participants
        actor_mention = self._find_closest(candidate, proximal_entities, [EntityType.PERSON, EntityType.ORGANIZATION])
        participants_dict = {}
        for ent in proximal_entities:
            if ent.entity_type in (EntityType.PERSON, EntityType.ORGANIZATION) and ent != actor_mention:
                participants_dict[ent.raw_value] = ent.entity_type.value

        # Normalize amount slot
        bound_amount: Optional[MonetaryValue] = None
        if amount_mention and isinstance(amount_mention.normalized_value, MonetaryValue):
            bound_amount = amount_mention.normalized_value

        # Normalize temporal slot
        temporal_val: Optional[Any] = None
        if temporal_mention:
            temporal_val = temporal_mention.normalized_value or temporal_mention.raw_value

        # Attributes dictionary for argument traceability
        argument_provenance = {}
        if amount_mention:
            argument_provenance["amount_entity_id"] = amount_mention.entity_id
        if order_mention:
            argument_provenance["order_entity_id"] = order_mention.entity_id
        if txn_mention:
            argument_provenance["transaction_entity_id"] = txn_mention.entity_id
        if temporal_mention:
            argument_provenance["temporal_entity_id"] = temporal_mention.entity_id

        return Event(
            event_id=f"evt_{uuid.uuid4().hex[:24]}",
            case_id=evidence_text.case_id,
            event_type=candidate.event_type,
            trigger=trigger,
            source_reference=trigger_ref,
            actor=actor_mention.raw_value if actor_mention else None,
            participants=participants_dict,
            temporal_information=temporal_val,
            amount=bound_amount,
            transaction_reference=txn_mention.raw_value if txn_mention else None,
            order_reference=order_mention.raw_value if order_mention else None,
            refund_id=refund_mention.raw_value if refund_mention else None,
            polarity=candidate.polarity,
            modality=candidate.modality,
            tense=candidate.tense,
            confidence=candidate.confidence,
            attributes={
                "context_sentence": candidate.context_sentence,
                "argument_provenance": argument_provenance,
            },
            model_metadata={
                "extractor": "DeterministicEventExtractor",
                "taxonomy_version": self.config.taxonomy_version,
            },
            created_at=datetime.now(timezone.utc),
        )

    def _find_proximal_entities(
        self,
        candidate: EventCandidate,
        entities: List[EntityMention],
    ) -> List[EntityMention]:
        """Finds entities residing in the same sentence or within max character window."""
        proximal: List[EntityMention] = []
        for ent in entities:
            e_start = ent.source_reference.char_start
            e_end = ent.source_reference.char_end
            if e_start is None:
                continue

            # Prioritize entities inside the exact context sentence
            in_sentence = (
                candidate.context_start <= e_start <= candidate.context_end
                or candidate.context_start <= e_end <= candidate.context_end
            )
            # Or within bounded character distance
            dist = min(abs(e_start - candidate.char_end), abs(e_end - candidate.char_start))
            if in_sentence or dist <= self.config.max_argument_char_distance:
                proximal.append(ent)
        return proximal

    def _find_closest(
        self,
        candidate: EventCandidate,
        entities: List[EntityMention],
        types: List[EntityType],
    ) -> Optional[EntityMention]:
        """Finds closest entity matching desired types."""
        matching = [e for e in entities if e.entity_type in types and e.source_reference.char_start is not None]
        if not matching:
            return None

        # For conversational speakers / actors, prefer the entity preceding the candidate trigger
        if any(t in (EntityType.PERSON, EntityType.ORGANIZATION) for t in types):
            preceding = [e for e in matching if e.source_reference.char_end <= candidate.char_start]
            if preceding:
                return max(preceding, key=lambda e: e.source_reference.char_end)

        # Sort by distance from trigger midpoint
        trig_mid = (candidate.char_start + candidate.char_end) / 2.0
        return min(
            matching,
            key=lambda e: abs(((e.source_reference.char_start + e.source_reference.char_end) / 2.0) - trig_mid),
        )

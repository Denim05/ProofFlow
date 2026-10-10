from decimal import Decimal
import pytest

from ml.entities.pipeline import EntityExtractionPipeline
from ml.events.ensemble import (
    EnsembleDecisionState,
    HybridEventCascade,
    NeuralEventPrediction,
)
from ml.schemas.entity import EntityMention, EntityType, MonetaryValue
from ml.schemas.event import EventModality, EventPolarity, EventTense, EventType
from ml.schemas.evidence_text import EvidenceText
from ml.schemas.source_reference import SourceReference
from ml.tests.test_event_pipeline import create_sample_evidence_text


def test_formatted_amount_grounding_verification():
    """Verifies that currency-formatted amounts such as 'INR 2,499.00' are verified without false review warnings."""
    cascade = HybridEventCascade()
    raw_text = "The customer paid INR 2,499.00 for order PF-1001 on 5 October 2026."
    evi_text = create_sample_evidence_text(raw_text)

    entity_pipeline = EntityExtractionPipeline()
    entities = entity_pipeline.process_evidence_text(evi_text)

    results = cascade.process_evidence(evi_text, entities)
    event_results = [r for r in results if r.event is not None]

    assert len(event_results) >= 1
    payment_event = next((r for r in event_results if r.event.event_type == EventType.PAYMENT_MADE), None)
    assert payment_event is not None
    assert payment_event.event.amount is not None
    assert payment_event.event.amount.value == Decimal("2499.00")
    # Verify no spurious review reason about 2499.00 not found verbatim
    assert not any("2499" in r for r in payment_event.review_reasons)


def test_textual_date_grounding_verification():
    """Verifies that textual date '5 October 2026' is verified via entity provenance without spurious warnings."""
    cascade = HybridEventCascade()
    raw_text = "The customer paid INR 2,499.00 for order PF-1001 on 5 October 2026."
    evi_text = create_sample_evidence_text(raw_text)

    entity_pipeline = EntityExtractionPipeline()
    entities = entity_pipeline.process_evidence_text(evi_text)

    results = cascade.process_evidence(evi_text, entities)
    event_results = [r for r in results if r.event is not None]

    payment_event = next((r for r in event_results if r.event.event_type == EventType.PAYMENT_MADE), None)
    assert payment_event is not None
    assert payment_event.event.temporal_information is not None
    # Temporal info normalized to 2026-10-05 must not trigger "not found verbatim" warning
    assert not any("Temporal information" in r for r in payment_event.review_reasons)


def test_disclaimer_sentence_rejection():
    """Ensures disclaimer statements stating 'should not be treated as proof' are rejected and never create affirmative delivery events."""
    cascade = HybridEventCascade()
    raw_text = (
        "Order PF-1001 was delivered on 7 October 2026.\n"
        "This simulated status should not be treated as proof that a real package was delivered."
    )
    evi_text = create_sample_evidence_text(raw_text)

    entity_pipeline = EntityExtractionPipeline()
    entities = entity_pipeline.process_evidence_text(evi_text)

    results = cascade.process_evidence(evi_text, entities)
    active_events = [r for r in results if r.event is not None and r.decision_state in (EnsembleDecisionState.VALIDATED, EnsembleDecisionState.REVIEW_NEEDED)]

    # Only the genuine delivery sentence should produce an event, not the disclaimer
    assert len(active_events) == 1
    assert active_events[0].event.event_type == EventType.ITEM_DELIVERED
    assert "simulated status" not in active_events[0].event.attributes.get("context_sentence", "")


def test_delivery_event_same_document_consolidation():
    """Consolidates headline/summary delivery mention with full delivery sentence into one canonical event with corroborating provenance."""
    cascade = HybridEventCascade()
    raw_text = (
        "Tracking Summary\n"
        "Status: Marked delivered\n\n"
        "Courier record confirms order PF-1001 was marked delivered on 7 October 2026 at 14:20."
    )
    evi_text = create_sample_evidence_text(raw_text)

    entity_pipeline = EntityExtractionPipeline()
    entities = entity_pipeline.process_evidence_text(evi_text)

    results = cascade.process_evidence(evi_text, entities)
    delivered_events = [r for r in results if r.event is not None and r.event.event_type == EventType.ITEM_DELIVERED]

    # Must be consolidated into exactly 1 canonical event
    assert len(delivered_events) == 1
    canonical = delivered_events[0].event
    assert canonical.order_reference == "PF-1001"
    # Secondary mention must be preserved in corroborating_mentions
    corroborating = canonical.attributes.get("corroborating_mentions", [])
    assert len(corroborating) >= 1
    assert any("Marked delivered" in m["context_sentence"] for m in corroborating)


def test_distinct_events_not_merged():
    """Distinct events with conflicting orders or different dates must remain separate."""
    cascade = HybridEventCascade()
    raw_text = (
        "Package for order PF-1001 was delivered on 5 October 2026.\n"
        "Package for order PF-2002 was delivered on 7 October 2026."
    )
    evi_text = create_sample_evidence_text(raw_text)

    entity_pipeline = EntityExtractionPipeline()
    entities = entity_pipeline.process_evidence_text(evi_text)

    results = cascade.process_evidence(evi_text, entities)
    delivered_events = [r for r in results if r.event is not None and r.event.event_type == EventType.ITEM_DELIVERED]

    # Two distinct orders -> must NOT be merged
    assert len(delivered_events) == 2
    orders = {e.event.order_reference for e in delivered_events}
    assert "PF-1001" in orders
    assert "PF-2002" in orders


def test_deterministic_fallback_diagnostic():
    """Checks that fallback reason is recorded and accessible when neural checkpoint is absent."""
    cascade = HybridEventCascade()
    assert cascade._model is None
    assert cascade.fallback_reason is not None
    assert "active" in cascade.fallback_reason.lower() or "not found" in cascade.fallback_reason.lower()

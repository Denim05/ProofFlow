"""Unit tests for Track 4B DeBERTa + Deterministic Hybrid Event Cascade.

Verifies deterministic validation, source grounding, lifecycle boundary guards,
modality/negation preservation, monetary/entity validation, and compound sentence detection
using mocked neural predictions (no GPU required, runnable in apps/api/.venv).
"""

from decimal import Decimal
from typing import Any, Dict, List, Optional
import pytest

from ml.events.ensemble import (
    EnsembleDecisionState,
    EnsembleValidationResult,
    HybridEnsembleConfig,
    HybridEventCascade,
    NeuralEventPrediction,
)
from ml.schemas.entity import EntityMention, EntityType, MonetaryValue
from ml.schemas.event import EventModality, EventPolarity, EventTense, EventType
from ml.schemas.evidence_text import EvidenceText
from ml.schemas.source_reference import SourceReference
from ml.tests.test_event_pipeline import create_sample_evidence_text


def make_mock_cascade(predicted_type: str, confidence: float = 0.95) -> HybridEventCascade:
    def _mock_pred(sentence: str) -> NeuralEventPrediction:
        return NeuralEventPrediction(
            predicted_event_type=predicted_type,
            model_confidence=confidence,
            model_name="microsoft/deberta-v3-base-test-mock",
            model_version="1.0.0",
            checkpoint_version="3.0.0-canonical-18",
            source_text=sentence,
        )

    return HybridEventCascade(mock_predictor=_mock_pred)


# Test 1: Valid neural event
def test_valid_neural_event():
    text = "Customer placed an order ORD-99120 for Electronics on 2026-08-10."
    evidence = create_sample_evidence_text(text)
    cascade = make_mock_cascade("ORDER_PLACED", confidence=0.92)

    results = cascade.process_evidence(evidence)
    assert len(results) == 1
    res = results[0]

    assert res.decision_state == EnsembleDecisionState.VALIDATED
    assert res.grounding_verified is True
    assert res.event is not None
    assert res.event.event_type == EventType.ORDER_PLACED
    assert res.event.confidence == 0.92
    assert res.event.model_metadata["model_confidence"] == 0.92
    assert "authenticity" not in res.event.model_metadata


# Test 2: Invalid source grounding
def test_invalid_source_grounding():
    evidence = create_sample_evidence_text("Short text.")
    cascade = make_mock_cascade("ORDER_PLACED", confidence=0.90)

    # Manually pass a candidate with source_text not in raw text
    bogus_pred = NeuralEventPrediction(
        predicted_event_type="ORDER_PLACED",
        model_confidence=0.90,
        source_text="This sentence never appeared in EvidenceText anywhere.",
        source_reference=SourceReference(evidence_id="evi_doc_pipeline", page_number=1, source_type="PDF"),
    )
    res = cascade.validate_candidate(bogus_pred, evidence, [], sentence_start=0, sentence_end=20)

    assert res.decision_state == EnsembleDecisionState.REVIEW_NEEDED
    assert res.grounding_verified is False
    assert any("does not exist verbatim" in err for err in res.validation_errors)


# Test 3: Invalid trigger span
def test_invalid_trigger_span():
    evidence = create_sample_evidence_text("Order was placed yesterday.")
    cascade = make_mock_cascade("ORDER_PLACED", confidence=0.88)

    bogus_pred = NeuralEventPrediction(
        predicted_event_type="ORDER_PLACED",
        model_confidence=0.88,
        source_text="Order was placed yesterday.",
        source_reference=SourceReference(evidence_id="evi_doc_pipeline", page_number=1, source_type="PDF"),
    )
    # Trigger offsets out of bounds
    res = cascade.validate_candidate(bogus_pred, evidence, [], sentence_start=500, sentence_end=600)

    assert res.decision_state in (EnsembleDecisionState.REVIEW_NEEDED, EnsembleDecisionState.REJECTED)
    assert res.grounding_verified is False
    assert any("Invalid trigger offsets" in err or "mismatch" in err for err in res.validation_errors)


# Test 4: Negated event
def test_negated_event():
    text = "The refund was not completed due to banking rejection."
    evidence = create_sample_evidence_text(text)
    cascade = make_mock_cascade("REFUND_COMPLETED", confidence=0.85)

    results = cascade.process_evidence(evidence)
    assert len(results) == 1
    res = results[0]

    assert res.event is not None
    assert res.event.polarity == EventPolarity.NEGATED
    assert res.decision_state in (EnsembleDecisionState.VALIDATED, EnsembleDecisionState.REVIEW_NEEDED)


# Test 5: Future event
def test_future_event():
    text = "The replacement parts will be shipped tomorrow morning."
    evidence = create_sample_evidence_text(text)
    cascade = make_mock_cascade("ITEM_SHIPPED", confidence=0.90)

    results = cascade.process_evidence(evidence)
    assert len(results) == 1
    res = results[0]

    assert res.event is not None
    assert res.event.modality == EventModality.PLANNED
    assert res.event.tense == EventTense.FUTURE


# Test 6: Conditional event
def test_conditional_event():
    text = "If approved by merchant, the refund will be completed for Order ORD-33100."
    evidence = create_sample_evidence_text(text)
    cascade = make_mock_cascade("REFUND_COMPLETED", confidence=0.89)

    results = cascade.process_evidence(evidence)
    assert len(results) == 1
    res = results[0]

    assert res.event is not None
    assert res.event.modality == EventModality.CONDITIONAL


# Test 7: Payment made
def test_payment_made():
    text = "Paid $450.00 via Visa card on 2026-09-15."
    evidence = create_sample_evidence_text(text)
    cascade = make_mock_cascade("PAYMENT_MADE", confidence=0.96)

    # Attach entity
    s_idx = text.index("$450.00")
    e_idx = s_idx + len("$450.00")
    entities = [
        EntityMention(
            entity_id="ent_amt",
            case_id="case_202",
            evidence_id="evi_doc_pipeline",
            extraction_confidence=1.0,
            entity_type=EntityType.MONETARY_AMOUNT,
            raw_value="$450.00",
            char_start=s_idx,
            char_end=e_idx,
            normalized_value=MonetaryValue(value=Decimal("450.00"), currency="USD"),
            source_reference=SourceReference(
                evidence_id="evi_doc_pipeline",
                page_number=1,
                char_start=s_idx,
                char_end=e_idx,
                source_type="PDF",
            ),
        )
    ]

    results = cascade.process_evidence(evidence, entities=entities)
    res = results[0]

    assert res.decision_state == EnsembleDecisionState.VALIDATED
    assert res.event is not None
    assert res.event.event_type == EventType.PAYMENT_MADE
    assert isinstance(res.event.amount.value, Decimal)
    assert res.event.amount.value == Decimal("450.00")


# Test 8: Payment failed
def test_payment_failed():
    text = "Payment failed for transaction TXN-99120 due to insufficient funds."
    evidence = create_sample_evidence_text(text)
    cascade = make_mock_cascade("PAYMENT_FAILED", confidence=0.94)

    results = cascade.process_evidence(evidence)
    res = results[0]

    assert res.decision_state == EnsembleDecisionState.VALIDATED
    assert res.event is not None
    assert res.event.event_type == EventType.PAYMENT_FAILED


# Test 9: Refund requested
def test_refund_requested():
    text = "Buyer requested a refund of $85.00 for damaged goods on 2026-09-12."
    evidence = create_sample_evidence_text(text)
    cascade = make_mock_cascade("REFUND_REQUESTED", confidence=0.93)

    results = cascade.process_evidence(evidence)
    res = results[0]

    assert res.decision_state == EnsembleDecisionState.VALIDATED
    assert res.event is not None
    assert res.event.event_type == EventType.REFUND_REQUESTED


# Test 10: Refund initiated
def test_refund_initiated():
    text = "Merchant initiated refund of $199.99 for booking ORD-33019."
    evidence = create_sample_evidence_text(text)
    cascade = make_mock_cascade("REFUND_INITIATED", confidence=0.92)

    results = cascade.process_evidence(evidence)
    res = results[0]

    assert res.decision_state == EnsembleDecisionState.VALIDATED
    assert res.event is not None
    assert res.event.event_type == EventType.REFUND_INITIATED


# Test 11: Refund completed
def test_refund_completed():
    text = "Refund completed successfully for Order ORD-55120 on 2026-10-01."
    evidence = create_sample_evidence_text(text)
    cascade = make_mock_cascade("REFUND_COMPLETED", confidence=0.95)

    results = cascade.process_evidence(evidence)
    res = results[0]

    assert res.decision_state == EnsembleDecisionState.VALIDATED
    assert res.event is not None
    assert res.event.event_type == EventType.REFUND_COMPLETED


# Test 12: Shipped vs delivered ambiguity
def test_shipped_vs_delivered_ambiguity():
    text = "Courier accepted parcel at downtown drop box location."
    evidence = create_sample_evidence_text(text)
    # Neural model incorrectly classifies drop box handover as ITEM_DELIVERED
    cascade = make_mock_cascade("ITEM_DELIVERED", confidence=0.82)

    results = cascade.process_evidence(evidence)
    res = results[0]

    assert res.lifecycle_guard_triggered is True
    assert res.decision_state == EnsembleDecisionState.REVIEW_NEEDED
    assert any("lifecycle verification" in r for r in res.review_reasons)


# Test 13: Return lifecycle ambiguity
def test_return_lifecycle_ambiguity():
    text = "Returned parcel arrived back at vendor distribution center."
    evidence = create_sample_evidence_text(text)
    # Neural model predicts RETURN_PICKED_UP on warehouse return arrival
    cascade = make_mock_cascade("RETURN_PICKED_UP", confidence=0.80)

    results = cascade.process_evidence(evidence)
    res = results[0]

    assert res.lifecycle_guard_triggered is True
    assert res.decision_state == EnsembleDecisionState.REVIEW_NEEDED
    assert any("RETURN_COMPLETED" in r or "warehouse" in r for r in res.review_reasons)


# Test 14: Compound sentence
def test_compound_sentence():
    text = "Customer placed order ORD-11 and paid $50."
    evidence = create_sample_evidence_text(text)
    cascade = make_mock_cascade("ORDER_PLACED", confidence=0.85)

    results = cascade.process_evidence(evidence)
    res = results[0]

    assert res.is_compound_sentence is True
    assert res.decision_state == EnsembleDecisionState.REVIEW_NEEDED
    assert any("Compound sentence detected" in r for r in res.review_reasons)


# Test 15: NO_EVENT
def test_no_event():
    text = "The cotton shirt features a modern cut with button-down collar."
    evidence = create_sample_evidence_text(text)
    cascade = make_mock_cascade("NO_EVENT", confidence=0.99)

    results = cascade.process_evidence(evidence)
    res = results[0]

    assert res.decision_state == EnsembleDecisionState.VALIDATED
    assert res.event is None


# Test 16: Missing source reference
def test_missing_source_reference():
    evidence = create_sample_evidence_text("Order placed today.")
    cascade = make_mock_cascade("ORDER_PLACED", confidence=0.90)

    pred = NeuralEventPrediction(
        predicted_event_type="ORDER_PLACED",
        model_confidence=0.90,
        source_text="Order placed today.",
        source_reference=None,  # Missing!
    )
    res = cascade.validate_candidate(pred, evidence, [], sentence_start=0, sentence_end=19)

    assert res.decision_state == EnsembleDecisionState.REVIEW_NEEDED
    assert res.grounding_verified is False
    assert any("Missing required SourceReference" in err for err in res.validation_errors)


# Test 17: Invalid monetary value
def test_invalid_monetary_value():
    text = "Payment received of $100.00."
    evidence = create_sample_evidence_text(text)
    cascade = make_mock_cascade("PAYMENT_MADE", confidence=0.90)

    # Create an entity mention with float value instead of Decimal
    s_idx = text.index("$100.00")
    e_idx = s_idx + len("$100.00")
    bad_entity = EntityMention(
        entity_id="ent_bad",
        case_id="case_202",
        evidence_id="evi_doc_pipeline",
        extraction_confidence=1.0,
        entity_type=EntityType.MONETARY_AMOUNT,
        raw_value="$100.00",
        char_start=s_idx,
        char_end=e_idx,
        normalized_value=MonetaryValue(value=Decimal("100.00"), currency="USD"),
        source_reference=SourceReference(
            evidence_id="evi_doc_pipeline",
            page_number=1,
            char_start=s_idx,
            char_end=e_idx,
            source_type="PDF",
        ),
    )
    # Monkey-patch value to float to test defensive check
    bad_entity.normalized_value.value = 100.0  # type: ignore

    results = cascade.process_evidence(evidence, entities=[bad_entity])
    res = results[0]

    assert any("must be exact Decimal" in err for err in res.validation_errors)


# Test 18: Invalid transaction ID
def test_invalid_transaction_id():
    text = "Payment of $50 settled for order."
    evidence = create_sample_evidence_text(text)
    cascade = make_mock_cascade("PAYMENT_MADE", confidence=0.90)

    # Candidate with transaction ID not in source text
    pred = NeuralEventPrediction(
        predicted_event_type="PAYMENT_MADE",
        model_confidence=0.90,
        source_text=text,
        source_reference=SourceReference(evidence_id="evi_doc_pipeline", page_number=1, source_type="PDF"),
    )
    # Create entity with fabricated ID
    fake_txn_entity = EntityMention(
        entity_id="ent_fake",
        case_id="case_202",
        evidence_id="evi_doc_pipeline",
        extraction_confidence=1.0,
        entity_type=EntityType.TRANSACTION_ID,
        raw_value="TXN-FABRICATED-99999",
        char_start=0,
        char_end=7,
        source_reference=SourceReference(
            evidence_id="evi_doc_pipeline",
            page_number=1,
            char_start=0,
            char_end=7,
            source_type="PDF",
        ),
    )

    res = cascade.validate_candidate(pred, evidence, entities=[fake_txn_entity], sentence_start=0, sentence_end=len(text))

    assert any("is not grounded in source text" in err for err in res.validation_errors)

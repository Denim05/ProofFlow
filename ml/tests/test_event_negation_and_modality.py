from ml.events.detector import EventDetector
from ml.schemas.event import EventModality, EventPolarity, EventTense, EventType


def test_positive_asserted_event():
    detector = EventDetector()
    text = "Refund completed successfully."
    candidates = detector.detect_candidates(text)
    assert len(candidates) == 1
    assert candidates[0].event_type == EventType.REFUND_COMPLETED
    assert candidates[0].polarity == EventPolarity.POSITIVE
    assert candidates[0].modality == EventModality.ASSERTED
    assert candidates[0].tense == EventTense.PAST


def test_negated_event_handling():
    detector = EventDetector()
    # "Refund was not completed" -> must be flagged as NEGATED
    text = "The refund was not completed due to bank rejection."
    candidates = detector.detect_candidates(text)
    assert len(candidates) == 1
    assert candidates[0].event_type == EventType.REFUND_COMPLETED
    assert candidates[0].polarity == EventPolarity.NEGATED
    assert candidates[0].modality == EventModality.ASSERTED


def test_future_planned_event():
    detector = EventDetector()
    text = "The refund will be completed tomorrow by customer operations."
    candidates = detector.detect_candidates(text)
    assert len(candidates) == 1
    assert candidates[0].event_type == EventType.REFUND_COMPLETED
    assert candidates[0].polarity == EventPolarity.POSITIVE
    assert candidates[0].modality == EventModality.PLANNED
    assert candidates[0].tense == EventTense.FUTURE


def test_conditional_event():
    detector = EventDetector()
    text = "If approved by seller, the refund will be completed."
    candidates = detector.detect_candidates(text)
    assert len(candidates) == 1
    assert candidates[0].event_type == EventType.REFUND_COMPLETED
    assert candidates[0].polarity == EventPolarity.POSITIVE
    assert candidates[0].modality == EventModality.CONDITIONAL


def test_uncertain_modal_event():
    detector = EventDetector()
    text = "Support stated that the package may be delivered by tomorrow."
    candidates = detector.detect_candidates(text)
    assert len(candidates) == 1
    assert candidates[0].event_type == EventType.ITEM_DELIVERED
    assert candidates[0].polarity == EventPolarity.POSITIVE
    assert candidates[0].modality == EventModality.UNCERTAIN

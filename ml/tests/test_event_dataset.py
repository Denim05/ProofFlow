from ml.events.data.event_dataset import (
    ALL_EVENT_CLASSES,
    LABEL2ID,
    RAW_SAMPLES,
    expand_dataset,
    split_dataset,
)
from ml.schemas.event import EventType


def test_event_dataset_classes_cover_taxonomy():
    for et in EventType:
        assert et.value in ALL_EVENT_CLASSES
    assert "NO_EVENT" in ALL_EVENT_CLASSES
    assert len(ALL_EVENT_CLASSES) == len(EventType) + 1


def test_event_dataset_generation_and_splits():
    full = expand_dataset(RAW_SAMPLES, target_size=100, seed=42)
    assert len(full) == 100

    train, val, test = split_dataset(full, train_ratio=0.7, val_ratio=0.15, test_ratio=0.15, seed=42)
    assert len(train) > 0
    assert len(val) > 0
    assert len(test) > 0
    assert len(train) + len(val) + len(test) == 100

    # Ensure all samples have valid text and event_type
    for s in full:
        assert "text" in s and len(s["text"]) > 0
        assert s["event_type"] in ALL_EVENT_CLASSES
        assert s["polarity"] in ["POSITIVE", "NEGATED"]
        assert s["modality"] in ["ASSERTED", "CONDITIONAL", "UNCERTAIN", "PLANNED"]

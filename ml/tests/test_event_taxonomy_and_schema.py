from decimal import Decimal
from ml.schemas.entity import MonetaryValue
from ml.schemas.event import (
    Event,
    EventCategory,
    EventModality,
    EventPolarity,
    EventTense,
    EventTrigger,
    EventType,
    EventTaxonomyVersion,
)
from ml.schemas.source_reference import SourceReference


def test_event_taxonomy_categories():
    assert EventTaxonomyVersion.V1_0 == "1.0.0"
    assert EventType.ORDER_PLACED.value == "ORDER_PLACED"
    assert EventType.REFUND_COMPLETED.value == "REFUND_COMPLETED"
    assert EventType.ITEM_SHIPPED.value == "ITEM_SHIPPED"
    assert EventType.SUPPORT_CONTACTED.value == "SUPPORT_CONTACTED"


def test_event_schema_with_provenance_and_decimal():
    ref = SourceReference(evidence_id="evi_doc_99", page_number=1, source_type="PDF")
    trigger = EventTrigger(
        raw_text="refund completed",
        char_start=10,
        char_end=26,
        source_reference=ref,
    )
    money = MonetaryValue(value=Decimal("4500.50"), currency="INR")

    event = Event(
        case_id="case_101",
        event_type=EventType.REFUND_COMPLETED,
        trigger=trigger,
        source_reference=ref,
        amount=money,
        order_reference="ORD-88210",
        polarity=EventPolarity.POSITIVE,
        modality=EventModality.ASSERTED,
        tense=EventTense.PAST,
        confidence=0.98,
    )

    assert event.event_type == EventType.REFUND_COMPLETED
    assert event.trigger.raw_text == "refund completed"
    assert event.source_reference.evidence_id == "evi_doc_99"
    assert isinstance(event.amount.value, Decimal)
    # Verify backward-compatibility mapping
    assert event.order_id == "ORD-88210"


def test_canonical_18_taxonomy_mapping():
    from ml.events.taxonomy_mapping import (
        CANONICAL_18_EVENT_TYPES,
        TAXONOMY_MAPPINGS,
        TaxonomyLabelCategory,
        map_to_canonical,
        is_canonical_event,
    )

    # 18 canonical events
    assert len(CANONICAL_18_EVENT_TYPES) == 18
    for c in CANONICAL_18_EVENT_TYPES:
        assert is_canonical_event(c)
        assert map_to_canonical(c) == c

    # 4 Compatibility aliases
    assert map_to_canonical("ORDER_SHIPPED") == "ITEM_SHIPPED"
    assert map_to_canonical("ORDER_DELIVERED") == "ITEM_DELIVERED"
    assert map_to_canonical("ITEM_RECEIVED") == "ITEM_DELIVERED"
    assert map_to_canonical("RETURN_INITIATED") == "RETURN_REQUESTED"

    # 5 Legacy dispute labels must not be forced
    for legacy_label in [
        "REFUND_APPROVED",
        "REFUND_PROCESSED",
        "REFUND_RECEIVED",
        "DISPUTE_OPENED",
        "CHARGEBACK_REQUESTED",
    ]:
        rule = TAXONOMY_MAPPINGS[legacy_label]
        assert rule.category == TaxonomyLabelCategory.LEGACY_DISPUTE
        assert rule.canonical_event_type is None
        assert map_to_canonical(legacy_label) is None


def test_v3_canonical_dataset_manifest_invariants():
    import json
    import os

    manifest_path = "ml/events/data/v3/dataset_manifest.json"
    assert os.path.exists(manifest_path), "v3 dataset manifest missing!"

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    assert manifest["dataset_version"] == "3.0.0-canonical-18"
    assert manifest["taxonomy_version"] == "1.0.0-canonical-18"
    assert manifest["summary"]["total_samples"] == 683
    assert manifest["summary"]["canonical_and_negative_samples"] == 573
    assert manifest["summary"]["unmapped_legacy_dispute_samples"] == 110
    assert manifest["summary"]["canonical_classes_count"] == 18
    assert manifest["summary"]["total_classifier_targets"] == 19

    # Zero leakage invariants
    leakage = manifest["leakage_verification"]
    assert leakage["exact_duplicates_train_val"] == 0
    assert leakage["exact_duplicates_train_test"] == 0
    assert leakage["exact_duplicates_val_test"] == 0


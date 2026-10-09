from decimal import Decimal
from ml.entities.pipeline import EntityExtractionPipeline
from ml.events.detector import EventCandidate
from ml.events.extractor import EventArgumentExtractor
from ml.schemas.entity import MonetaryValue
from ml.schemas.event import EventType
from ml.schemas.evidence_text import (
    EvidenceText,
    ExtractionQualityMetrics,
    ExtractionQualityState,
    PageExtractionMethod,
    PageLayout,
    TextBlock,
    TextLine,
    TextSpan,
)


def create_sample_evidence_text(raw_text: str) -> EvidenceText:
    span = TextSpan(
        span_index=0,
        raw_text=raw_text,
        normalized_text=raw_text,
        bounding_box=[100.0, 100.0, 500.0, 200.0],
        raw_char_start=0,
        raw_char_end=len(raw_text),
        extraction_confidence=1.0,
    )
    line = TextLine(line_index=0, raw_text=raw_text, spans=[span], line_confidence=1.0)
    block = TextBlock(block_index=0, block_type="paragraph", lines=[line], raw_text=raw_text)
    page = PageLayout(
        page_number=1,
        width=595.0,
        height=842.0,
        extraction_method=PageExtractionMethod.NATIVE_PDF,
        quality_state=ExtractionQualityState.PASS,
        blocks=[block],
        raw_page_text=raw_text,
        normalized_page_text=raw_text,
    )
    return EvidenceText(
        text_id="txt_sample",
        evidence_id="evi_doc_42",
        case_id="case_101",
        full_raw_text=raw_text,
        full_normalized_text=raw_text,
        pages=[page],
        overall_quality_state=ExtractionQualityState.PASS,
        quality_metrics=ExtractionQualityMetrics(raw_character_count=len(raw_text)),
        model_metadata={"pipeline": "test"},
    )


def test_bind_all_proximal_arguments():
    text = "Payment received of INR 10,000.00 for Order ORD-99210 on 2026-10-07. Transaction TXN-88120 settled."
    evi_text = create_sample_evidence_text(text)
    entity_pipeline = EntityExtractionPipeline()
    entities = entity_pipeline.process_evidence_text(evi_text)

    candidate = EventCandidate(
        event_type=EventType.PAYMENT_MADE,
        trigger_text="Payment received",
        char_start=0,
        char_end=16,
        context_sentence=text,
        context_start=0,
        context_end=len(text),
    )

    extractor = EventArgumentExtractor()
    event = extractor.bind_arguments_to_event(candidate, evi_text, entities)

    assert event.event_type == EventType.PAYMENT_MADE
    assert event.amount is not None
    assert isinstance(event.amount.value, Decimal)
    assert event.amount.value == Decimal("10000.00")
    assert event.order_reference == "ORD-99210"
    assert event.transaction_reference == "TXN-88120"
    assert event.temporal_information == "2026-10-07"
    assert "amount_entity_id" in event.attributes["argument_provenance"]


def test_preserve_missing_arguments_never_invented():
    text = "Package delivered at customer door."
    evi_text = create_sample_evidence_text(text)
    entity_pipeline = EntityExtractionPipeline()
    entities = entity_pipeline.process_evidence_text(evi_text)

    candidate = EventCandidate(
        event_type=EventType.ITEM_DELIVERED,
        trigger_text="delivered",
        char_start=8,
        char_end=17,
        context_sentence=text,
        context_start=0,
        context_end=len(text),
    )

    extractor = EventArgumentExtractor()
    event = extractor.bind_arguments_to_event(candidate, evi_text, entities)

    assert event.event_type == EventType.ITEM_DELIVERED
    # Invariant: MISSING != UNKNOWN != FALSE. Must remain None!
    assert event.order_reference is None
    assert event.amount is None
    assert event.transaction_reference is None

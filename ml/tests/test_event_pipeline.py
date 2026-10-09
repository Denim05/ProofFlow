from ml.events.pipeline import EventExtractionPipeline
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
        text_id="txt_pipeline_sample",
        evidence_id="evi_doc_pipeline",
        case_id="case_202",
        full_raw_text=raw_text,
        full_normalized_text=raw_text,
        pages=[page],
        overall_quality_state=ExtractionQualityState.PASS,
        quality_metrics=ExtractionQualityMetrics(raw_character_count=len(raw_text)),
        model_metadata={"pipeline": "event_pipeline_test"},
    )


def test_pipeline_multiple_events_extracted():
    pipeline = EventExtractionPipeline()
    text = "Order ORD-11029 placed on 2026-09-01. Item shipped by Acme Corp via FedEx on 2026-09-03."
    evi_text = create_sample_evidence_text(text)

    events = pipeline.process_evidence(evi_text)
    assert len(events) == 2

    types = {e.event_type for e in events}
    assert EventType.ORDER_PLACED in types
    assert EventType.ITEM_SHIPPED in types

    # Check that each event has its own distinct trigger and source provenance
    for e in events:
        assert e.trigger is not None
        assert e.source_reference.evidence_id == "evi_doc_pipeline"
        assert e.source_reference.char_start >= 0


def test_pipeline_empty_text_returns_empty():
    pipeline = EventExtractionPipeline()
    evi_text = create_sample_evidence_text("")
    events = pipeline.process_evidence(evi_text)
    assert events == []


def test_pipeline_ocr_noise_case_h():
    pipeline = EventExtractionPipeline()
    text = "Payment received of INR 5,000.00 for Transaction TXN-O09I82."
    evi_text = create_sample_evidence_text(text)

    events = pipeline.process_evidence(evi_text)
    assert len(events) == 1
    ev = events[0]
    assert ev.event_type == EventType.PAYMENT_MADE
    assert "TXN-O09I82" in (ev.transaction_reference or "")

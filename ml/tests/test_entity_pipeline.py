from decimal import Decimal
from ml.entities.nlp_extractor import MockNLPExtractor
from ml.entities.pipeline import EntityExtractionPipeline
from ml.schemas.entity import EntityMention, EntityType, MonetaryValue
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
    """Helper to create EvidenceText with realistic layout blocks and bounding boxes."""
    span1 = TextSpan(
        span_index=0,
        raw_text=raw_text,
        normalized_text=raw_text,
        bounding_box=[100.0, 150.0, 450.0, 180.0],
        raw_char_start=0,
        raw_char_end=len(raw_text),
        extraction_confidence=0.99,
    )
    line = TextLine(line_index=0, raw_text=raw_text, spans=[span1], line_confidence=0.99)
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
        text_id="txt_sample_01",
        evidence_id="evi_doc_01",
        case_id="case_101",
        full_raw_text=raw_text,
        full_normalized_text=raw_text,
        pages=[page],
        overall_quality_state=ExtractionQualityState.PASS,
        quality_metrics=ExtractionQualityMetrics(raw_character_count=len(raw_text)),
        model_metadata={"engine": "test"},
    )


def test_pipeline_extracts_and_grounds_entities():
    pipeline = EntityExtractionPipeline()
    text = "Order ORD-9921 issued by Acme Corp on 2026-10-07 for INR 5,000.00."
    evi_text = create_sample_evidence_text(text)

    mentions = pipeline.process_evidence_text(evi_text)
    assert len(mentions) >= 4

    types = {m.entity_type for m in mentions}
    assert EntityType.ORDER_ID in types
    assert EntityType.ORGANIZATION in types
    assert EntityType.DATE in types
    assert EntityType.MONETARY_AMOUNT in types

    # Verify strict provenance invariant
    for m in mentions:
        assert isinstance(m, EntityMention)
        assert m.source_reference.evidence_id == "evi_doc_01"
        assert m.source_reference.page_number == 1
        assert m.source_reference.char_start >= 0
        assert m.source_reference.char_end <= len(text)
        assert m.source_reference.bounding_box is not None


def test_pipeline_preserves_duplicate_mentions():
    """Duplicate entity mentions in evidence must remain separate to preserve provenance."""
    pipeline = EntityExtractionPipeline()
    text = "Initial notice for Order ORD-9921. Reminder regarding Order ORD-9921."
    evi_text = create_sample_evidence_text(text)

    mentions = pipeline.process_evidence_text(evi_text)
    order_mentions = [m for m in mentions if m.entity_type == EntityType.ORDER_ID]
    assert len(order_mentions) == 2
    assert order_mentions[0].entity_id != order_mentions[1].entity_id
    assert order_mentions[0].source_reference.char_start != order_mentions[1].source_reference.char_start


def test_pipeline_deterministic_priority_over_nlp():
    """Deterministic patterns must take precedence when overlapping with broad NLP entities."""
    # Custom mock NLP extractor that tags the whole phrase as an Organization
    mock_nlp = MockNLPExtractor(
        custom_entities=[{"text": "Order ORD-9921", "type": EntityType.ORGANIZATION}]
    )
    pipeline = EntityExtractionPipeline(nlp_extractor=mock_nlp)
    text = "Reference: Order ORD-9921."
    evi_text = create_sample_evidence_text(text)

    mentions = pipeline.process_evidence_text(evi_text)
    # Deterministic ORDER_ID must win over NLP ORGANIZATION on the overlapping span
    assert any(m.entity_type == EntityType.ORDER_ID and "ORD-9921" in m.raw_value for m in mentions)
    assert not any(m.entity_type == EntityType.ORGANIZATION and "Order ORD-9921" in m.raw_value for m in mentions)


def test_pipeline_case_h_ocr_ambiguity():
    """Case H noisy transaction ID should be extracted and flagged with ambiguity."""
    pipeline = EntityExtractionPipeline()
    text = "Payment: Transaction ID: TXN-O09I82 Amount: INR 1,000.00."
    evi_text = create_sample_evidence_text(text)

    mentions = pipeline.process_evidence_text(evi_text)
    txn = next(m for m in mentions if m.entity_type == EntityType.TRANSACTION_ID)
    assert "TXN-O09I82" in txn.raw_value
    assert txn.model_metadata.get("span_metadata", {}).get("is_ambiguous") is True

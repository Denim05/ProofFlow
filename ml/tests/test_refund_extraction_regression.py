import pytest
from datetime import datetime, timezone
from decimal import Decimal
from typing import List

from ml.extraction.pipeline import ExtractionPipeline
from ml.entities.pipeline import EntityExtractionPipeline
from ml.events.ensemble import HybridEventCascade, EnsembleDecisionState
from ml.schemas.event import EventType, EventPolarity, EventModality
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
from app.services.finding_service import FindingService
from tests.conftest import FakeAsyncDatabase


SAMPLE_CONVERSATION_TEXT = (
    "PROOFLOW – SYNTHETIC EVIDENCE\n"
    "Customer Support Conversation\n"
    "Reference: Order PF-1001 / Conversation SUP-TEST-1001\n"
    "Date: 8 October 2026\n"
    "09:15 – Customer\n"
    "The headset package arrived damaged. I would like to request a\n"
    "refund for order PF-1001.\n"
    "09:42 – Example Store Support\n"
    "We received your refund request. It is under review. No refund\n"
    "approval or payment date has been confirmed.\n"
    "Record details\n"
    "This transcript is fictional and documents a simulated customer claim and support response.\n"
    "It does not independently establish the condition of the item or the outcome of the refund request.\n"
)


def _build_synthetic_evidence_text(text: str, evidence_id: str = "evi_support_03") -> EvidenceText:
    """Constructs a grounded EvidenceText object from raw text."""
    span = TextSpan(
        raw_text=text,
        raw_char_start=0,
        raw_char_end=len(text),
        bounding_box=[10.0, 10.0, 500.0, 700.0],
        extraction_confidence=1.0,
    )
    line = TextLine(
        line_index=0,
        raw_text=text,
        spans=[span],
        bounding_box=[10.0, 10.0, 500.0, 700.0],
        line_confidence=1.0,
    )
    block = TextBlock(
        block_index=0,
        block_type="paragraph",
        raw_text=text,
        bounding_box=[10.0, 10.0, 500.0, 700.0],
        lines=[line],
    )
    page = PageLayout(
        page_number=1,
        width=595.0,
        height=842.0,
        extraction_method=PageExtractionMethod.NATIVE_PDF,
        quality_state=ExtractionQualityState.PASS,
        blocks=[block],
        raw_page_text=text,
        normalized_page_text=text,
    )
    return EvidenceText(
        text_id=f"txt_{evidence_id}",
        evidence_id=evidence_id,
        case_id="case_test_1001",
        full_raw_text=text,
        full_normalized_text=text,
        pages=[page],
        overall_quality_state=ExtractionQualityState.PASS,
        quality_metrics=ExtractionQualityMetrics(raw_character_count=len(text)),
        model_metadata={"pipeline": "regression_test"},
    )


def test_refund_request_and_support_status_extraction():
    """Verifies REFUND_REQUESTED and REFUND_UNDER_REVIEW extraction with distinct actors."""
    ev_text = _build_synthetic_evidence_text(SAMPLE_CONVERSATION_TEXT)
    entity_pipeline = EntityExtractionPipeline()
    entities = entity_pipeline.process_evidence_text(ev_text)

    cascade = HybridEventCascade()
    results = cascade.process_evidence(ev_text, entities)
    event_results = [r for r in results if r.event is not None]

    assert len(event_results) == 2, f"Expected 2 events, got {len(event_results)}: {[r.event.event_type for r in event_results]}"

    # 1. Customer's Refund Request
    req_res = next((r for r in event_results if r.event.event_type == EventType.REFUND_REQUESTED), None)
    assert req_res is not None, "REFUND_REQUESTED event missing"
    assert req_res.decision_state == EnsembleDecisionState.VALIDATED
    ev_req = req_res.event
    assert "request a" in ev_req.trigger.raw_text and "refund" in ev_req.trigger.raw_text
    assert ev_req.actor == "Customer"
    assert ev_req.order_reference == "PF-1001"
    assert str(ev_req.temporal_information) == "2026-10-08"
    assert ev_req.polarity == EventPolarity.POSITIVE
    assert ev_req.modality == EventModality.ASSERTED
    # Corroborating mention from support acknowledgement
    assert len(ev_req.attributes.get("corroborating_mentions", [])) >= 1

    # 2. Store Support's Review Status
    rev_res = next((r for r in event_results if r.event.event_type == EventType.REFUND_UNDER_REVIEW), None)
    assert rev_res is not None, "REFUND_UNDER_REVIEW event missing"
    assert rev_res.decision_state == EnsembleDecisionState.VALIDATED
    ev_rev = rev_res.event
    assert "under review" in ev_rev.trigger.raw_text
    assert ev_rev.actor in ("Example Store Support", "Example Store")
    assert ev_rev.order_reference == "PF-1001"
    assert str(ev_rev.temporal_information) == "2026-10-08"
    assert ev_rev.polarity == EventPolarity.POSITIVE

    # 3. Disclaimers and negative statements must NOT produce affirmative events
    extracted_types = {r.event.event_type for r in event_results}
    assert EventType.REFUND_APPROVED not in extracted_types
    assert EventType.REFUND_COMPLETED not in extracted_types
    assert EventType.PAYMENT_MADE not in extracted_types


def test_source_quote_and_provenance_preservation():
    """Verifies trigger quotes match raw text verbatim and offsets are strictly valid."""
    ev_text = _build_synthetic_evidence_text(SAMPLE_CONVERSATION_TEXT)
    entity_pipeline = EntityExtractionPipeline()
    entities = entity_pipeline.process_evidence_text(ev_text)

    cascade = HybridEventCascade()
    results = cascade.process_evidence(ev_text, entities)
    event_results = [r for r in results if r.event is not None]

    raw_text = ev_text.full_raw_text
    for r in event_results:
        ev = r.event
        c_start = ev.trigger.char_start
        c_end = ev.trigger.char_end
        assert 0 <= c_start < c_end <= len(raw_text)
        verbatim_substring = raw_text[c_start:c_end]
        assert verbatim_substring == ev.trigger.raw_text
        assert ev.source_reference is not None
        assert ev.source_reference.page_number == 1


def test_documents_with_no_valid_event_remain_event_free():
    """Documents containing only disclaimers or non-action statements produce zero events and clear diagnostics."""
    disclaimer_text = (
        "TERMS AND CONDITIONS\n"
        "This simulated document does not constitute proof of delivery or purchase.\n"
        "For testing and demonstration purposes only.\n"
        "All references are fictional and do not establish any real-world dispute outcome.\n"
    )
    ev_text = _build_synthetic_evidence_text(disclaimer_text, evidence_id="evi_disclaimer_only")
    entity_pipeline = EntityExtractionPipeline()
    entities = entity_pipeline.process_evidence_text(ev_text)

    cascade = HybridEventCascade()
    results = cascade.process_evidence(ev_text, entities)
    event_results = [r for r in results if r.event is not None]

    assert len(event_results) == 0, "Disclaimers must produce zero events without fabricating facts"


@pytest.mark.asyncio
async def test_reprocessing_and_versioning_without_duplicates():
    """Ensures reprocessing creates new processing version events without duplicate active events."""
    from app.services.evidence_processor import EvidenceProcessingService, ProcessingJob
    from app.models.evidence import EvidenceStatus

    fake_db = FakeAsyncDatabase()
    case_id = "case_test_versioning"
    user_id = "user_versioning"
    evidence_id = "evi_versioning_01"

    await fake_db.cases.insert_one({
        "case_id": case_id,
        "user_id": user_id,
        "title": "Versioning Test Case",
        "status": "PROCESSING",
        "evidence_count": 1,
    })

    await fake_db.evidence.insert_one({
        "evidence_id": evidence_id,
        "case_id": case_id,
        "user_id": user_id,
        "original_filename": "support_conversation.pdf",
        "media_type": "application/pdf",
        "file_size_bytes": len(SAMPLE_CONVERSATION_TEXT),
        "sha256_hash": "a" * 64,
        "status": EvidenceStatus.QUEUED.value,
        "active_processing_version": None,
        "processing_version": 0,
    })

    # Stage 1: Initial Processing (Version 1)
    # Mock storage_service read
    from app.services.storage import storage_service
    orig_read = storage_service.read_evidence_bytes
    storage_service.read_evidence_bytes = lambda path: SAMPLE_CONVERSATION_TEXT.encode("utf-8")

    proc_service = EvidenceProcessingService()
    # Mock extraction pipeline to return our structured text
    proc_service.extraction_pipeline.process_evidence = (
        lambda **kwargs: (None, _build_synthetic_evidence_text(SAMPLE_CONVERSATION_TEXT, evidence_id))
    )

    try:
        job_v1 = ProcessingJob(
            evidence_id=evidence_id,
            case_id=case_id,
            user_id=user_id,
            storage_relative_path="dummy",
            original_filename="support_conversation.pdf",
            media_type="application/pdf",
            sha256_hash="a" * 64,
            retry_count=0,
        )
        await proc_service.run_job(job_v1, fake_db)

        evi_v1 = await fake_db.evidence.find_one({"evidence_id": evidence_id})
        assert evi_v1["active_processing_version"] == 1
        assert evi_v1["status"] == "READY"

        v1_events = [doc async for doc in fake_db.events.find({"evidence_id": evidence_id, "is_active": True})]
        assert len(v1_events) == 2

        # Stage 2: Reprocessing (Version 2)
        await fake_db.evidence.update_one(
            {"evidence_id": evidence_id},
            {"$set": {"status": EvidenceStatus.QUEUED.value}},
        )

        job_v2 = ProcessingJob(
            evidence_id=evidence_id,
            case_id=case_id,
            user_id=user_id,
            storage_relative_path="dummy",
            original_filename="support_conversation.pdf",
            media_type="application/pdf",
            sha256_hash="a" * 64,
            retry_count=1,
        )
        await proc_service.run_job(job_v2, fake_db)

        evi_v2 = await fake_db.evidence.find_one({"evidence_id": evidence_id})
        assert evi_v2["active_processing_version"] == 2

        # Only Version 2 events must be active
        v2_active_events = [doc async for doc in fake_db.events.find({
            "evidence_id": evidence_id,
            "processing_version": 2,
            "is_active": True,
        })]
        assert len(v2_active_events) == 2

        # Prior version 1 events should be purged so no duplicate or stale events remain
        v1_remaining = [doc async for doc in fake_db.events.find({
            "evidence_id": evidence_id,
            "processing_version": 1,
        })]
        assert len(v1_remaining) == 0

        # Total events for this evidence should exactly equal target version count
        all_events = [doc async for doc in fake_db.events.find({
            "evidence_id": evidence_id,
        })]
        assert len(all_events) == 2
    finally:
        storage_service.read_evidence_bytes = orig_read


@pytest.mark.asyncio
async def test_cross_examination_when_refund_evidence_present_and_missing():
    """Verifies Cross-Examination findings generation behavior with and without refund evidence."""
    fake_db = FakeAsyncDatabase()
    case_id = "case_pf_1001_findings"
    user_id = "user_cross_exam"

    # Base evidence: Order confirmation & Delivery status
    await fake_db.cases.insert_one({"case_id": case_id, "user_id": user_id, "title": "PF-1001"})
    await fake_db.evidence.insert_one({
        "evidence_id": "evi_01_order",
        "case_id": case_id,
        "user_id": user_id,
        "original_filename": "ProofFlow_Evidence_01_Order_Confirmation.pdf",
        "active_processing_version": 1,
        "status": "READY",
    })
    await fake_db.evidence.insert_one({
        "evidence_id": "evi_02_delivery",
        "case_id": case_id,
        "user_id": user_id,
        "original_filename": "ProofFlow_Evidence_02_Delivery_Status.pdf",
        "active_processing_version": 1,
        "status": "READY",
    })

    # Order Placed (Oct 5) & Item Delivered (Oct 7)
    await fake_db.events.insert_one({
        "event_id": "evt_order_placed",
        "case_id": case_id,
        "evidence_id": "evi_01_order",
        "user_id": user_id,
        "processing_version": 1,
        "is_active": True,
        "event_type": "ORDER_PLACED",
        "decision_state": "VALIDATED",
        "trigger_raw_text": "Order confirmed",
        "order_reference": "PF-1001",
        "temporal_information": "2026-10-05",
        "amount_currency": "INR",
        "amount_value": Decimal("2499.00"),
        "polarity": "POSITIVE",
        "modality": "ASSERTED",
        "created_at": datetime.now(timezone.utc),
    })
    await fake_db.events.insert_one({
        "event_id": "evt_item_delivered",
        "case_id": case_id,
        "evidence_id": "evi_02_delivery",
        "user_id": user_id,
        "processing_version": 1,
        "is_active": True,
        "event_type": "ITEM_DELIVERED",
        "decision_state": "VALIDATED",
        "trigger_raw_text": "Delivered",
        "order_reference": "PF-1001",
        "temporal_information": "2026-10-07",
        "amount_currency": "INR",
        "amount_value": Decimal("2499.00"),
        "polarity": "POSITIVE",
        "modality": "ASSERTED",
        "created_at": datetime.now(timezone.utc),
    })

    # Scenario A: Refund Evidence is MISSING
    findings_missing = await FindingService.compute_case_findings(case_id, user_id, fake_db)
    refund_findings = [f for f in findings_missing.items if "Transaction Reference" in f.title]
    assert len(refund_findings) == 0, "Without refund claims, no unconfirmed refund transaction should be flagged"

    # Scenario B: Refund Evidence is AVAILABLE (Evidence 03 with REFUND_REQUESTED)
    await fake_db.evidence.insert_one({
        "evidence_id": "evi_03_refund",
        "case_id": case_id,
        "user_id": user_id,
        "original_filename": "ProofFlow_Evidence_03_Refund_Support_Conversation.pdf",
        "active_processing_version": 1,
        "status": "READY",
    })
    await fake_db.events.insert_one({
        "event_id": "evt_refund_requested",
        "case_id": case_id,
        "evidence_id": "evi_03_refund",
        "user_id": user_id,
        "processing_version": 1,
        "is_active": True,
        "event_type": "REFUND_REQUESTED",
        "decision_state": "VALIDATED",
        "trigger_raw_text": "request a refund",
        "order_reference": "PF-1001",
        "actor": "Customer",
        "temporal_information": "2026-10-08",
        "polarity": "POSITIVE",
        "modality": "ASSERTED",
        "created_at": datetime.now(timezone.utc),
    })

    findings_present = await FindingService.compute_case_findings(case_id, user_id, fake_db)
    unconfirmed_tx = next((f for f in findings_present.items if "Unconfirmed Transaction Reference" in f.title), None)
    assert unconfirmed_tx is not None, "Cross-Examination must detect unconfirmed refund transaction advisory when claim exists without settlement"
    assert "PF-1001" in unconfirmed_tx.title
    assert unconfirmed_tx.finding_type == "MISSING_EVIDENCE_ADVISORY"
    assert len(unconfirmed_tx.citations) >= 1
    assert unconfirmed_tx.citations[0].evidence_id == "evi_03_refund"

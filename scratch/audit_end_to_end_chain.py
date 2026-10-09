"""Audit script testing the programmatic chain from ExtractionPipeline to EntityExtractionPipeline to HybridEventCascade."""

import io
import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.abspath("."))

from ml.extraction.pipeline import ExtractionPipeline
from ml.entities.pipeline import EntityExtractionPipeline
from ml.events.ensemble import HybridEventCascade, EnsembleDecisionState
from ml.schemas.evidence import EvidenceType

def test_programmatic_chain():
    print("\n--- AUDIT: PROGRAMMATIC PIPELINE CHAIN ---")
    # 1. Sample document text
    sample_text = (
        "Order Confirmation\n\n"
        "Customer placed an order ORD-77889 for Laptop on 2026-09-01.\n"
        "Paid $1250.00 via Visa credit card on 2026-09-01.\n"
        "Merchant initiated refund of $1250.00 for order ORD-77889 on 2026-09-05.\n"
    )

    # In our tests, PyMuPDF can generate a minimal PDF in memory to test native extraction
    import pymupdf
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 72), sample_text)
    pdf_bytes = doc.tobytes()
    doc.close()

    # Step 1: ExtractionPipeline (Track 2)
    extraction_pipe = ExtractionPipeline()
    ingestion_meta, evidence_text = extraction_pipe.process_evidence(
        evidence_id="evi_audit_001",
        case_id="case_audit_999",
        user_id="usr_audit_01",
        file_bytes=pdf_bytes,
        filename="order_confirmation.pdf",
        mime_type="application/pdf",
        declared_type=EvidenceType.RECEIPT,
    )
    print(f"[STAGE 1] ExtractionPipeline: Success! Extracted {len(evidence_text.pages)} pages, {len(evidence_text.full_raw_text)} chars.")
    assert evidence_text.evidence_id == "evi_audit_001"
    assert evidence_text.case_id == "case_audit_999"

    # Step 2: EntityExtractionPipeline (Track 3)
    entity_pipe = EntityExtractionPipeline()
    entities = entity_pipe.process_evidence_text(evidence_text)
    print(f"[STAGE 2] EntityExtractionPipeline: Success! Extracted {len(entities)} entity mentions.")
    for e in entities:
        print(f"  - Entity: {e.entity_type.value} = '{e.raw_value}' (span [{e.source_reference.char_start}:{e.source_reference.char_end}])")

    # Step 3: HybridEventCascade (Track 4B)
    cascade = HybridEventCascade()
    results = cascade.process_evidence(evidence_text, entities=entities)
    print(f"[STAGE 3] HybridEventCascade: Processed {len(results)} sentences/candidates.")

    validated_events = [r.event for r in results if r.decision_state == EnsembleDecisionState.VALIDATED and r.event is not None]
    review_events = [r for r in results if r.decision_state == EnsembleDecisionState.REVIEW_NEEDED]

    print(f"  -> Validated events: {len(validated_events)}")
    for ev in validated_events:
        amt_str = f"{ev.amount.currency} {ev.amount.value}" if ev.amount else "None"
        print(f"     * [{ev.event_type.value}] trigger='{ev.trigger.raw_text}' amt={amt_str} order={ev.order_reference} span=[{ev.trigger.char_start}:{ev.trigger.char_end}]")
        assert ev.case_id == "case_audit_999"
        assert ev.source_reference.evidence_id == "evi_audit_001"

    print(f"  -> Review needed candidates: {len(review_events)}")
    for r in review_events:
        print(f"     * [{r.neural_prediction.predicted_event_type if r.neural_prediction else 'Unknown'}] reasons={r.review_reasons}")

    print("\n[AUDIT] Programmatic chain audit: COMPLETE.")

if __name__ == "__main__":
    test_programmatic_chain()

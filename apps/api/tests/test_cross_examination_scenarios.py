import pytest
from datetime import datetime, timezone
from decimal import Decimal
from bson import Decimal128
from httpx import AsyncClient

from tests.conftest import FakeAsyncDatabase
from app.services.finding_service import FindingService
from app.schemas.finding import FindingListResponse
from ml.schemas.finding import ConflictState, FindingType


MOCK_USER = "dev-user"


async def setup_case(fake_db: FakeAsyncDatabase, case_id: str, user_id: str = MOCK_USER):
    await fake_db.cases.insert_one({
        "case_id": case_id,
        "user_id": user_id,
        "title": f"Case {case_id}",
        "description": "Cross-examination test case",
        "status": "PROCESSING",
        "evidence_count": 0,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    })


async def setup_evidence_doc(
    fake_db: FakeAsyncDatabase,
    case_id: str,
    evidence_id: str,
    filename: str,
    status: str = "READY",
    active_version: int = 1,
    events_extracted: int = 1,
    diagnostic: str = None,
    user_id: str = MOCK_USER,
):
    extraction_summary = {
        "page_count": 1,
        "character_count": 500,
        "quality_state": "PASS" if status == "READY" else "REVIEW_NEEDED",
        "entities_extracted": 2,
        "events_extracted": events_extracted,
        "processing_version": active_version,
    }
    if diagnostic:
        extraction_summary["diagnostic"] = diagnostic

    await fake_db.evidence.insert_one({
        "evidence_id": evidence_id,
        "case_id": case_id,
        "user_id": user_id,
        "original_filename": filename,
        "media_type": "application/pdf",
        "file_size_bytes": 1200,
        "sha256_hash": "a" * 64,
        "status": status,
        "processing_version": active_version,
        "active_processing_version": active_version,
        "extraction_summary": extraction_summary,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    })


async def insert_event(
    fake_db: FakeAsyncDatabase,
    case_id: str,
    evidence_id: str,
    event_id: str,
    event_type: str,
    actor: str,
    order_ref: str = None,
    temporal_info: str = None,
    amount_currency: str = None,
    amount_value: Decimal = None,
    trigger_text: str = "trigger phrase",
    decision_state: str = "VALIDATED",
    polarity: str = "POSITIVE",
    modality: str = "ASSERTED",
    page_number: int = 1,
    char_start: int = 10,
    char_end: int = 25,
    user_id: str = MOCK_USER,
):
    doc = {
        "event_id": event_id,
        "case_id": case_id,
        "evidence_id": evidence_id,
        "user_id": user_id,
        "processing_version": 1,
        "is_active": True,
        "event_type": event_type,
        "decision_state": decision_state,
        "trigger_raw_text": trigger_text,
        "char_start": char_start,
        "char_end": char_end,
        "page_number": page_number,
        "actor": actor,
        "order_reference": order_ref,
        "temporal_information": temporal_info,
        "amount_currency": amount_currency,
        "amount_value": Decimal128(str(amount_value)) if amount_value is not None else None,
        "polarity": polarity,
        "modality": modality,
        "model_confidence": 0.95,
        "created_at": datetime.now(timezone.utc),
    }
    await fake_db.events.insert_one(doc)


# --------------------------------------------------------------------------
# Scenario A: Order placed + delivery delivered + damage claim + review
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scenario_a_order_delivery_and_refund_under_review(fake_db: FakeAsyncDatabase):
    """Scenario A:
    Order placed (merchant) + delivered (courier) + customer reports damage/refund + merchant reviews.
    Must distinguish actor statements and flag pending refund settlement without false accusations.
    """
    case_id = "case_scen_a"
    await setup_case(fake_db, case_id)
    await setup_evidence_doc(fake_db, case_id, "evi_order", "Order_Confirmation.pdf")
    await setup_evidence_doc(fake_db, case_id, "evi_delivery", "Delivery_Tracking.pdf")
    await setup_evidence_doc(fake_db, case_id, "evi_support", "Customer_Support_Transcript.pdf")

    # 1. Order Placed
    await insert_event(
        fake_db, case_id, "evi_order", "evt_01",
        event_type="ORDER_PLACED",
        actor="Acme Store",
        order_ref="PF-1001",
        temporal_info="2026-10-05",
        amount_currency="INR",
        amount_value=Decimal("2499.00"),
        trigger_text="Order confirmed",
    )
    # 2. Delivered
    await insert_event(
        fake_db, case_id, "evi_delivery", "evt_02",
        event_type="ITEM_DELIVERED",
        actor="FastCourier",
        order_ref="PF-1001",
        temporal_info="2026-10-07",
        amount_currency="INR",
        amount_value=Decimal("2499.00"),
        trigger_text="Delivered to front door",
    )
    # 3. Customer refund request (damage claim)
    await insert_event(
        fake_db, case_id, "evi_support", "evt_03",
        event_type="REFUND_REQUESTED",
        actor="Customer",
        order_ref="PF-1001",
        temporal_info="2026-10-08",
        trigger_text="I would like to request a refund",
    )
    # 4. Support review status
    await insert_event(
        fake_db, case_id, "evi_support", "evt_04",
        event_type="REFUND_UNDER_REVIEW",
        actor="Acme Store Support",
        order_ref="PF-1001",
        temporal_info="2026-10-08",
        trigger_text="It is under review",
    )

    findings: FindingListResponse = await FindingService.compute_case_findings(case_id, MOCK_USER, fake_db)

    # Must produce missing settlement advisory for the refund claim
    missing_settlement = next((f for f in findings.items if "PF-1001" in f.title and f.finding_type == "MISSING_EVIDENCE_ADVISORY"), None)
    assert missing_settlement is not None, "Pending refund claim must produce an unconfirmed settlement advisory"
    assert "contradiction" not in missing_settlement.summary.lower() or "not proof of a contradiction" in missing_settlement.summary.lower()
    assert missing_settlement.conflict_state == "POTENTIAL_CONFLICT"

    # Must NOT produce false contradictions between delivery and request
    contradictions = [f for f in findings.items if f.conflict_state == "DIRECT_CONTRADICTION"]
    assert len(contradictions) == 0, "No direct contradiction should be inferred from normal claim progression"


# --------------------------------------------------------------------------
# Scenario B: Customer requests refund, but no evidence of approval or payment
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scenario_b_customer_refund_without_approval_or_payment(fake_db: FakeAsyncDatabase):
    """Scenario B:
    Customer requests refund, but there is no evidence of approval or payment.
    Must produce missing evidence advisory, NOT proof of fraud or contradiction.
    """
    case_id = "case_scen_b"
    await setup_case(fake_db, case_id)
    await setup_evidence_doc(fake_db, case_id, "evi_claim", "Customer_Claim.pdf")

    await insert_event(
        fake_db, case_id, "evi_claim", "evt_claim",
        event_type="REFUND_REQUESTED",
        actor="Customer",
        order_ref="PF-1001",
        temporal_info="2026-10-08",
        trigger_text="requesting a full refund",
    )

    findings = await FindingService.compute_case_findings(case_id, MOCK_USER, fake_db)
    assert len(findings.items) == 1
    f = findings.items[0]
    assert f.finding_type == "MISSING_EVIDENCE_ADVISORY"
    assert "PF-1001" in f.title
    assert len(f.citations) == 1
    assert f.citations[0].evidence_id == "evi_claim"
    assert f.citations[0].trigger_raw_text == "requesting a full refund"
    # Never describe model confidence as probability of fraud or truth
    assert "fraud" not in f.summary.lower()
    assert "authentic" not in f.summary.lower()


# --------------------------------------------------------------------------
# Scenario C: Merchant confirms refund approval, with no payment evidence
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scenario_c_merchant_confirms_approval_without_payment(fake_db: FakeAsyncDatabase):
    """Scenario C:
    Merchant confirms refund approval, but there is no payment evidence.
    Must produce advisory that settlement/payout confirmation is pending/missing.
    """
    case_id = "case_scen_c"
    await setup_case(fake_db, case_id)
    await setup_evidence_doc(fake_db, case_id, "evi_order", "Order.pdf")
    await setup_evidence_doc(fake_db, case_id, "evi_approval", "Store_Approval_Notice.pdf")

    await insert_event(
        fake_db, case_id, "evi_order", "evt_order",
        event_type="ORDER_PLACED",
        actor="Store",
        order_ref="PF-1001",
        temporal_info="2026-10-05",
        amount_currency="INR",
        amount_value=Decimal("1500.00"),
        trigger_text="Order confirmed",
    )
    await insert_event(
        fake_db, case_id, "evi_approval", "evt_approval",
        event_type="REFUND_APPROVED",
        actor="Store Support",
        order_ref="PF-1001",
        temporal_info="2026-10-09",
        amount_currency="INR",
        amount_value=Decimal("1500.00"),
        trigger_text="Your refund request has been approved",
    )

    findings = await FindingService.compute_case_findings(case_id, MOCK_USER, fake_db)
    # Must identify that approved refund has no payment/settlement confirmation
    advisories = [f for f in findings.items if f.finding_type == "MISSING_EVIDENCE_ADVISORY" and "PF-1001" in f.title]
    assert len(advisories) >= 1, "Approved refund lacking payment settlement evidence must be flagged as unconfirmed settlement advisory"
    adv = advisories[0]
    assert adv.conflict_state == "POTENTIAL_CONFLICT"
    assert "approval" in adv.title.lower() or "settlement" in adv.title.lower() or "unconfirmed" in adv.title.lower()


# --------------------------------------------------------------------------
# Scenario D: Merchant confirms refund payment, with grounded amount and date
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scenario_d_merchant_confirms_refund_payment(fake_db: FakeAsyncDatabase):
    """Scenario D:
    Customer requests refund and merchant confirms payment with grounded amount and date.
    All claims are corroborated; no unconfirmed advisory should remain.
    """
    case_id = "case_scen_d"
    await setup_case(fake_db, case_id)
    await setup_evidence_doc(fake_db, case_id, "evi_order", "Order_Doc.pdf")
    await setup_evidence_doc(fake_db, case_id, "evi_req", "Customer_Email.pdf")
    await setup_evidence_doc(fake_db, case_id, "evi_payout", "Bank_Refund_Receipt.pdf")

    # Order Placed (Oct 5)
    await insert_event(
        fake_db, case_id, "evi_order", "evt_d1",
        event_type="ORDER_PLACED",
        actor="Store",
        order_ref="PF-1001",
        temporal_info="2026-10-05",
        amount_currency="INR",
        amount_value=Decimal("2499.00"),
        trigger_text="Order confirmed",
    )
    # Refund Requested (Oct 8)
    await insert_event(
        fake_db, case_id, "evi_req", "evt_d2",
        event_type="REFUND_REQUESTED",
        actor="Customer",
        order_ref="PF-1001",
        temporal_info="2026-10-08",
        trigger_text="request a refund",
    )
    # Refund Completed / Paid (Oct 10)
    await insert_event(
        fake_db, case_id, "evi_payout", "evt_d3",
        event_type="REFUND_COMPLETED",
        actor="Payment Gateway",
        order_ref="PF-1001",
        temporal_info="2026-10-10",
        amount_currency="INR",
        amount_value=Decimal("2499.00"),
        trigger_text="Refund completed successfully to original payment method",
    )

    findings = await FindingService.compute_case_findings(case_id, MOCK_USER, fake_db)
    # Fully corroborated sequence: refund request is confirmed by refund completion
    missing_corrob = [f for f in findings.items if f.finding_type == "MISSING_EVIDENCE_ADVISORY"]
    assert len(missing_corrob) == 0, "Corroborated refund payment must not leave missing corroboration advisories"
    assert findings.total == 0, "Concordant lifecycle events must produce zero conflicting findings"


# --------------------------------------------------------------------------
# Scenario E: Evidence documents disagree on an order reference, date, or amount
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scenario_e1_amount_disagreement(fake_db: FakeAsyncDatabase):
    """Scenario E1:
    Evidence documents disagree on the monetary amount for the same order reference.
    """
    case_id = "case_scen_e1"
    await setup_case(fake_db, case_id)
    await setup_evidence_doc(fake_db, case_id, "evi_order", "Order_Doc.pdf")
    await setup_evidence_doc(fake_db, case_id, "evi_invoice", "Invoice_Doc.pdf")

    await insert_event(
        fake_db, case_id, "evi_order", "evt_e1_1",
        event_type="ORDER_PLACED",
        actor="Store",
        order_ref="PF-1001",
        amount_currency="USD",
        amount_value=Decimal("100.00"),
        trigger_text="Total $100.00",
    )
    await insert_event(
        fake_db, case_id, "evi_invoice", "evt_e1_2",
        event_type="PAYMENT_MADE",
        actor="Customer",
        order_ref="PF-1001",
        amount_currency="USD",
        amount_value=Decimal("80.00"),
        trigger_text="Paid $80.00",
    )

    findings = await FindingService.compute_case_findings(case_id, MOCK_USER, fake_db)
    amount_diff = next((f for f in findings.items if "Amount Divergence" in f.title), None)
    assert amount_diff is not None
    assert amount_diff.field_diff is not None
    assert "100.00" in amount_diff.field_diff.value_a or "100.00" in amount_diff.field_diff.value_b
    assert "80.00" in amount_diff.field_diff.value_a or "80.00" in amount_diff.field_diff.value_b
    assert len(amount_diff.citations) == 2


@pytest.mark.asyncio
async def test_scenario_e2_date_disagreement_on_same_milestone(fake_db: FakeAsyncDatabase):
    """Scenario E2:
    Evidence documents disagree on the date for the same order milestone.
    """
    case_id = "case_scen_e2"
    await setup_case(fake_db, case_id)
    await setup_evidence_doc(fake_db, case_id, "evi_receipt", "Receipt.pdf")
    await setup_evidence_doc(fake_db, case_id, "evi_ticket", "Support_Ticket.pdf")

    # Document A states item delivered Oct 7
    await insert_event(
        fake_db, case_id, "evi_receipt", "evt_e2_1",
        event_type="ITEM_DELIVERED",
        actor="Courier",
        order_ref="PF-1001",
        temporal_info="2026-10-07",
        trigger_text="Delivered October 7 2026",
    )
    # Document B asserts item delivered Oct 12
    await insert_event(
        fake_db, case_id, "evi_ticket", "evt_e2_2",
        event_type="ITEM_DELIVERED",
        actor="Customer",
        order_ref="PF-1001",
        temporal_info="2026-10-12",
        trigger_text="Package arrived October 12 2026",
    )

    findings = await FindingService.compute_case_findings(case_id, MOCK_USER, fake_db)
    date_diff = next((f for f in findings.items if "Date Discrepancy" in f.title or "Temporal" in f.title), None)
    assert date_diff is not None, "Divergent dates for the same milestone across evidence must produce a date discrepancy finding"
    assert date_diff.field_diff is not None or "2026-10-07" in date_diff.summary
    assert len(date_diff.citations) == 2


@pytest.mark.asyncio
async def test_scenario_e3_order_reference_disagreement(fake_db: FakeAsyncDatabase):
    """Scenario E3:
    Evidence documents in the same case cite conflicting order references without common ID.
    """
    case_id = "case_scen_e3"
    await setup_case(fake_db, case_id)
    await setup_evidence_doc(fake_db, case_id, "evi_doc_a", "Contract_A.pdf")
    await setup_evidence_doc(fake_db, case_id, "evi_doc_b", "Invoice_B.pdf")

    await insert_event(
        fake_db, case_id, "evi_doc_a", "evt_e3_1",
        event_type="ORDER_PLACED",
        actor="Buyer",
        order_ref="ORD-1001",
        trigger_text="Purchase Order ORD-1001",
    )
    await insert_event(
        fake_db, case_id, "evi_doc_b", "evt_e3_2",
        event_type="ORDER_PLACED",
        actor="Seller",
        order_ref="ORD-9999",
        trigger_text="Sales Order ORD-9999",
    )

    findings = await FindingService.compute_case_findings(case_id, MOCK_USER, fake_db)
    ref_diff = next((f for f in findings.items if "Order Reference" in f.title or "Reference Mismatch" in f.title or "Divergent" in f.title), None)
    assert ref_diff is not None, "Conflicting order references in the same case must produce an advisory or inconsistency finding"
    assert len(ref_diff.citations) == 2


# --------------------------------------------------------------------------
# Scenario F: Evidence is missing, unreadable, or produces zero validated events
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scenario_f_unreadable_or_zero_event_evidence(fake_db: FakeAsyncDatabase):
    """Scenario F:
    Case contains an evidence document that produced zero events or needs review due to scan quality.
    Must clearly report an extraction advisory without confusing it with contradictory proof.
    """
    case_id = "case_scen_f"
    await setup_case(fake_db, case_id)
    await setup_evidence_doc(fake_db, case_id, "evi_valid", "Valid_Order.pdf", status="READY", events_extracted=1)
    await setup_evidence_doc(
        fake_db, case_id, "evi_blank", "Terms_and_Conditions_Disclaimer.pdf",
        status="READY", events_extracted=0,
        diagnostic="Document text consists of non-affirmative disclaimers; no validated real-world lifecycle events were asserted.",
    )
    await setup_evidence_doc(
        fake_db, case_id, "evi_blurry", "Blurry_Scan_Receipt.pdf",
        status="REVIEW_NEEDED", events_extracted=0,
        diagnostic="OCR quality below confidence threshold; manual review recommended.",
    )

    await insert_event(
        fake_db, case_id, "evi_valid", "evt_f1",
        event_type="ORDER_PLACED",
        actor="Store",
        order_ref="PF-1001",
        trigger_text="Order confirmed",
    )

    findings = await FindingService.compute_case_findings(case_id, MOCK_USER, fake_db)
    # Must report extraction advisories for evi_blank and evi_blurry
    extraction_advisories = [f for f in findings.items if f.finding_type == "MISSING_EVIDENCE_ADVISORY" and ("Zero" in f.title or "Review" in f.title or "Extraction" in f.title)]
    assert len(extraction_advisories) >= 2, "Unreadable or zero-event evidence must produce extraction advisories"
    for adv in extraction_advisories:
        assert adv.conflict_state in ("INSUFFICIENT_CONTEXT", "POTENTIAL_CONFLICT")
        assert len(adv.citations) == 1
        assert "contradiction" not in adv.summary.lower() or "not proof of a contradiction" in adv.summary.lower()

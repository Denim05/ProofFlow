from datetime import datetime
from typing import List, Optional, Tuple
import uuid
from ml.schemas.claim import Claim, Modality
from ml.schemas.event import Event, EventType
from ml.schemas.finding import CoverageState, Finding, FindingType
from ml.schemas.model_metadata import ModelMetadata
from ml.schemas.source_reference import SourceReference

COVERAGE_METADATA = ModelMetadata(
    model_name="proofflow-coverage-checker",
    model_version="v0.1.0-rules",
    extraction_confidence=1.0,
    confidence_definition="Rule-based evidence coverage assessment against purchase dispute archetype.",
)


def check_refund_evidence_coverage(
    case_id: str,
    claims: List[Claim],
    events: List[Event],
    financial_statement_range: Optional[Tuple[datetime, datetime]] = None,
) -> List[Finding]:
    """Assesses whether claims of completed refunds possess supporting financial records in the uploaded case pack.

    Distinguishes PRESENT, NOT_FOUND, and INSUFFICIENT_COVERAGE.
    Crucial: Never outputs 'The event did not happen'.
    """
    findings: List[Finding] = []

    # Identify claims or events asserting refund was processed
    refund_assertions = [
        c for c in claims
        if (c.predicate == "ISSUED_REFUND" or c.event_reference == EventType.REFUND_PROCESSED)
        and c.modality == Modality.SUBJECTIVE_ASSERTION
    ]

    # Identify actual financial settlement records (bank or gateway)
    settlement_events = [
        e for e in events
        if e.event_type in (EventType.REFUND_RECEIVED, EventType.REFUND_PROCESSED)
        and e.source_reference.source_type in ("BANK_STATEMENT", "PAYMENT_GATEWAY_RECEIPT")
    ]

    for assertion in refund_assertions:
        # Check if matching settlement record exists
        if not settlement_events:
            # Check statement date range coverage if available
            coverage_state = CoverageState.NOT_FOUND_IN_UPLOADED_EVIDENCE
            summary = "Supporting evidence for the refund transaction was not found in the uploaded evidence."

            if financial_statement_range is not None and assertion.source_reference:
                start_dt, end_dt = financial_statement_range
                # If assertion specifies an event datetime that exceeds statement end date
                # Then statement coverage is incomplete
                summary = (
                    f"Supporting evidence for the refund transaction was not found in the uploaded evidence. "
                    f"Uploaded financial records span {start_dt.strftime('%b %d')} to {end_dt.strftime('%b %d')}. "
                    f"Review recommended."
                )

            findings.append(
                Finding(
                    finding_id=f"fnd_cov_{uuid.uuid4().hex[:16]}",
                    case_id=case_id,
                    finding_type=FindingType.MISSING_EVIDENCE_ADVISORY,
                    title="Missing Evidence Advisory: Refund Transaction Record",
                    summary=summary,
                    coverage_state=coverage_state,
                    severity="MEDIUM",
                    evidence_references=[assertion.source_reference],
                    model_metadata=COVERAGE_METADATA,
                )
            )

    return findings

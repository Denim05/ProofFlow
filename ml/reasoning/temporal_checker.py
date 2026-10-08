from datetime import datetime
from typing import List, Optional
import uuid
from ml.schemas.event import Event, EventType
from ml.schemas.finding import ConflictState, Finding, FindingType, InconsistencyTier
from ml.schemas.model_metadata import ModelMetadata

TEMPORAL_METADATA = ModelMetadata(
    model_name="proofflow-temporal-checker",
    model_version="v0.1.0-rules",
    extraction_confidence=1.0,
    confidence_definition="Deterministic temporal constraint solver over verified ISO timestamps.",
)

# Canonical temporal order rules: (earlier_event, later_event)
EXPECTED_PRECEDENCE = [
    (EventType.ORDER_PLACED, EventType.ORDER_SHIPPED),
    (EventType.ORDER_SHIPPED, EventType.ORDER_DELIVERED),
    (EventType.REFUND_REQUESTED, EventType.REFUND_PROCESSED),
    (EventType.REFUND_PROCESSED, EventType.REFUND_RECEIVED),
]


def check_temporal_consistency(case_id: str, events: List[Event]) -> List[Finding]:
    """Evaluates temporal sequence ordering between events with known timestamps.

    Never infers ordering when timestamps are absent or unresolved.
    """
    findings: List[Finding] = []

    # Map events by event_type (only those with resolved timestamps)
    events_with_time = [e for e in events if e.timestamp is not None]

    for earlier_type, later_type in EXPECTED_PRECEDENCE:
        earlier_matches = [e for e in events_with_time if e.event_type == earlier_type]
        later_matches = [e for e in events_with_time if e.event_type == later_type]

        for e_early in earlier_matches:
            for e_late in later_matches:
                # If the "later" event occurred strictly before the "earlier" event
                if e_late.timestamp < e_early.timestamp:
                    findings.append(
                        Finding(
                            finding_id=f"fnd_tmp_{uuid.uuid4().hex[:16]}",
                            case_id=case_id,
                            finding_type=FindingType.POTENTIAL_INCONSISTENCY,
                            title="Potential Inconsistency: Temporal Sequence Violation",
                            summary=(
                                f"{later_type.value} recorded at {e_late.timestamp.isoformat()} "
                                f"precedes {earlier_type.value} recorded at {e_early.timestamp.isoformat()}."
                            ),
                            inconsistency_tier=InconsistencyTier.TIER_C_TEMPORAL,
                            conflict_state=ConflictState.DIRECT_CONTRADICTION,
                            severity="HIGH",
                            evidence_references=[
                                e_early.source_reference,
                                e_late.source_reference,
                            ],
                            model_metadata=TEMPORAL_METADATA,
                        )
                    )

    return findings

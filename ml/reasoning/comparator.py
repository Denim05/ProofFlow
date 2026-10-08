from typing import List, Optional
import uuid
from ml.schemas.finding import ConflictState, Finding, FindingType, InconsistencyTier
from ml.schemas.model_metadata import ModelMetadata
from ml.schemas.source_reference import SourceReference

COMPARATOR_METADATA = ModelMetadata(
    model_name="proofflow-deterministic-comparator",
    model_version="v0.1.0-rules",
    extraction_confidence=1.0,
    confidence_definition="Rule-based deterministic comparator. Exact mathematical and string equality.",
)


def compare_monetary_amounts(
    case_id: str,
    amount_a: float,
    currency_a: str,
    ref_a: SourceReference,
    label_a: str,
    amount_b: float,
    currency_b: str,
    ref_b: SourceReference,
    label_b: str,
    epsilon: float = 0.01,
) -> Optional[Finding]:
    """Compares two monetary amounts with currency safety and returns a Finding if discrepancy detected."""
    curr_a = currency_a.strip().upper()
    curr_b = currency_b.strip().upper()

    # Currency mismatch advisory
    if curr_a != curr_b:
        return Finding(
            finding_id=f"fnd_cmp_{uuid.uuid4().hex[:16]}",
            case_id=case_id,
            finding_type=FindingType.POTENTIAL_INCONSISTENCY,
            title="Potential Inconsistency: Currency Mismatch",
            summary=f"{label_a} is denominated in {curr_a} while {label_b} is in {curr_b}. Direct comparison requires exchange rate verification.",
            inconsistency_tier=InconsistencyTier.TIER_A_DETERMINISTIC,
            conflict_state=ConflictState.POTENTIAL_CONFLICT,
            severity="MEDIUM",
            evidence_references=[ref_a, ref_b],
            model_metadata=COMPARATOR_METADATA,
        )

    diff = round(abs(amount_a - amount_b), 2)
    if diff > epsilon:
        higher_label = label_a if amount_a > amount_b else label_b
        lower_label = label_b if amount_a > amount_b else label_a
        return Finding(
            finding_id=f"fnd_cmp_{uuid.uuid4().hex[:16]}",
            case_id=case_id,
            finding_type=FindingType.POTENTIAL_INCONSISTENCY,
            title="Potential Inconsistency: Amount Discrepancy",
            summary=f"{higher_label} ({curr_a} {max(amount_a, amount_b):,.2f}) differs from {lower_label} ({curr_b} {min(amount_a, amount_b):,.2f}) by {curr_a} {diff:,.2f}.",
            inconsistency_tier=InconsistencyTier.TIER_A_DETERMINISTIC,
            conflict_state=ConflictState.DIRECT_CONTRADICTION,
            severity="HIGH",
            evidence_references=[ref_a, ref_b],
            model_metadata=COMPARATOR_METADATA,
        )

    return None


def compare_identifiers(
    case_id: str,
    id_a: str,
    ref_a: SourceReference,
    label_a: str,
    id_b: str,
    ref_b: SourceReference,
    label_b: str,
) -> Optional[Finding]:
    """Compares two business identifiers (order ID, tracking number, transaction ID)."""
    clean_a = id_a.strip().replace(" ", "").replace("-", "").upper()
    clean_b = id_b.strip().replace(" ", "").replace("-", "").upper()

    if clean_a != clean_b:
        return Finding(
            finding_id=f"fnd_cmp_{uuid.uuid4().hex[:16]}",
            case_id=case_id,
            finding_type=FindingType.POTENTIAL_INCONSISTENCY,
            title="Potential Inconsistency: Identifier Mismatch",
            summary=f"{label_a} '{id_a}' does not match {label_b} '{id_b}'.",
            inconsistency_tier=InconsistencyTier.TIER_A_DETERMINISTIC,
            conflict_state=ConflictState.DIRECT_CONTRADICTION,
            severity="HIGH",
            evidence_references=[ref_a, ref_b],
            model_metadata=COMPARATOR_METADATA,
        )

    return None

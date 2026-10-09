import hashlib
import re
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Set, Tuple
from pymongo.asynchronous.database import AsyncDatabase

from app.schemas.finding import (
    EvidenceCitation,
    FieldDifference,
    FindingListResponse,
    FindingResponse,
)
from ml.schemas.finding import ConflictState, FindingType
from ml.schemas.model_metadata import ModelMetadata

REASONING_METADATA = ModelMetadata(
    model_name="proofflow-reasoning-engine",
    model_version="v0.2.0-grounded",
    extraction_confidence=1.0,
    confidence_definition="Source-grounded deterministic and temporal reasoning engine over active evidence extractions.",
)

AMBIGUOUS_REFERENCES = {
    "N/A",
    "NA",
    "NONE",
    "NULL",
    "REF",
    "ID",
    "ORDER",
    "PO",
    "TXN",
    "UNKNOWN",
}

# Canonical temporal order rules: (earlier_event_type, later_event_type)
EXPECTED_PRECEDENCE = [
    ("ORDER_PLACED", "ORDER_SHIPPED"),
    ("ORDER_PLACED", "ITEM_SHIPPED"),
    ("ORDER_SHIPPED", "ORDER_DELIVERED"),
    ("ORDER_SHIPPED", "ITEM_DELIVERED"),
    ("ITEM_SHIPPED", "ORDER_DELIVERED"),
    ("ITEM_SHIPPED", "ITEM_DELIVERED"),
    ("REFUND_REQUESTED", "REFUND_PROCESSED"),
    ("REFUND_REQUESTED", "REFUND_COMPLETED"),
    ("REFUND_PROCESSED", "REFUND_RECEIVED"),
    ("REFUND_COMPLETED", "REFUND_RECEIVED"),
]


def normalize_reference(ref: Optional[str]) -> Optional[str]:
    """Normalizes business references (order IDs, tracking numbers, transaction IDs).

    Guards against short or ambiguous matching tokens.
    """
    if not ref:
        return None
    stripped = ref.strip().upper()
    clean = re.sub(r"[\s\-_]", "", stripped)
    if len(clean) < 3 or stripped in AMBIGUOUS_REFERENCES:
        return None
    return clean


def parse_explicit_timestamp(val: Any) -> Optional[datetime]:
    """Strictly parses explicit ISO datetime without falling back to ingestion/creation times."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    if isinstance(val, str):
        trimmed = val.strip()
        if not trimmed:
            return None
        # Must resemble ISO-8601 date or datetime
        try:
            return datetime.fromisoformat(trimmed.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None
    return None


def generate_finding_id(
    case_id: str,
    finding_type: str,
    discriminator: str,
    event_ids: List[str],
) -> str:
    """Computes a deterministic, collision-resistant finding ID."""
    sorted_ids = sorted(event_ids)
    raw_key = f"{case_id}|{finding_type}|{discriminator}|{'|'.join(sorted_ids)}"
    digest = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:16]
    return f"fnd_{digest}"


def build_citation(
    event: Dict[str, Any],
    evidence_name_map: Dict[str, str],
) -> EvidenceCitation:
    """Builds a verified source citation directly from event provenance."""
    evidence_id = event.get("evidence_id", "")
    page_no = event.get("page_number")
    if page_no is not None and (not isinstance(page_no, int) or page_no < 1):
        page_no = None

    c_start = event.get("char_start")
    if c_start is not None and (not isinstance(c_start, int) or c_start < 0):
        c_start = None

    c_end = event.get("char_end")
    if c_end is not None and (not isinstance(c_end, int) or c_end < 0):
        c_end = None

    # Zero-length default offsets mean offsets were not recorded
    if c_start == 0 and c_end == 0:
        c_start = None
        c_end = None

    # Never fabricate trigger raw text
    trigger_text = event.get("trigger_raw_text") or "[No textual trigger span recorded]"

    return EvidenceCitation(
        evidence_id=evidence_id,
        original_filename=evidence_name_map.get(evidence_id, evidence_id),
        page_number=page_no,
        char_start=c_start,
        char_end=c_end,
        trigger_raw_text=trigger_text,
        event_id=event.get("event_id"),
    )


class FindingService:
    """On-demand findings service executing conservative reasoning over active case extractions."""

    @staticmethod
    async def compute_case_findings(
        case_id: str,
        user_id: str,
        db: AsyncDatabase,
    ) -> FindingListResponse:
        """Computes authoritative, source-grounded findings for a given case.

        Invariants:
        1. Only events from exact active processing versions are included.
        2. In-flight and superseded processing runs are excluded.
        3. Missing or malformed version metadata fails safely.
        4. All findings cite real source evidence; provenance is never fabricated.
        5. Cross-document comparisons require distinct evidence IDs.
        6. Conservative comparison semantics: differing amounts, polarity, and temporal inversions
           are classified as POTENTIAL_CONFLICT or INSUFFICIENT_CONTEXT. Never described as fraud or falsity.
        7. Missing corroboration is flagged as MISSING_EVIDENCE_ADVISORY, not proof of falsity.
        8. Temporal reasoning uses strictly explicit event timestamps.
        9. Output is deterministically deduplicated and ordered.
        """
        # 1. Fetch active evidence documents for case
        evidence_cursor = db.evidence.find(
            {"case_id": case_id, "user_id": user_id},
            {"evidence_id": 1, "original_filename": 1, "active_processing_version": 1, "status": 1},
        )
        evidence_name_map: Dict[str, str] = {}
        active_version_map: Dict[str, int] = {}
        active_pairs: List[Dict[str, Any]] = []

        async for doc in evidence_cursor:
            evi_id = doc.get("evidence_id")
            if not evi_id or not isinstance(evi_id, str):
                continue

            evidence_name_map[evi_id] = doc.get("original_filename") or evi_id

            # Active version must be a valid positive integer
            active_ver = doc.get("active_processing_version")
            if not isinstance(active_ver, int) or active_ver <= 0:
                continue

            active_pairs.append({
                "evidence_id": evi_id,
                "processing_version": active_ver,
            })
            active_version_map[evi_id] = active_ver

        if not active_pairs:
            return FindingListResponse(items=[], total=0, case_id=case_id)

        # 2. Query active events strictly matching active processing versions
        events_query: Dict[str, Any] = {
            "case_id": case_id,
            "user_id": user_id,
            "is_active": True,
            "$or": active_pairs,
        }

        events_cursor = db.events.find(events_query).sort([("created_at", 1), ("_id", 1)])
        events: List[Dict[str, Any]] = []
        async for row in events_cursor:
            row_evi_id = row.get("evidence_id")
            row_ver = row.get("processing_version")
            # Strict defense-in-depth: confirm event version matches active_version_map
            if (
                row_evi_id in active_version_map
                and isinstance(row_ver, int)
                and row_ver == active_version_map[row_evi_id]
            ):
                events.append(row)

        if not events:
            return FindingListResponse(items=[], total=0, case_id=case_id)

        findings: List[FindingResponse] = []
        seen_finding_ids: Set[str] = set()

        # 3. Reference-based cross-document comparisons (Monetary & Polarity)
        # Group events by normalized order_reference or transaction_reference
        ref_groups: Dict[str, Dict[str, Any]] = {}
        for ev in events:
            norm_order = normalize_reference(ev.get("order_reference"))
            norm_txn = normalize_reference(ev.get("transaction_reference"))

            if norm_order:
                if norm_order not in ref_groups:
                    ref_groups[norm_order] = {
                        "display_ref": ev.get("order_reference", "").strip(),
                        "items": [],
                    }
                ref_groups[norm_order]["items"].append(ev)
            elif norm_txn:
                if norm_txn not in ref_groups:
                    ref_groups[norm_txn] = {
                        "display_ref": ev.get("transaction_reference", "").strip(),
                        "items": [],
                    }
                ref_groups[norm_txn]["items"].append(ev)

        for norm_key, group_data in ref_groups.items():
            display_ref = group_data["display_ref"]
            group_events = group_data["items"]
            if len(group_events) < 2:
                continue

            for i in range(len(group_events)):
                for j in range(i + 1, len(group_events)):
                    ev_a = group_events[i]
                    ev_b = group_events[j]

                    # INVARIANT: Only compare events originating from DISTINCT evidence documents
                    if ev_a.get("evidence_id") == ev_b.get("evidence_id"):
                        continue

                    evi_id_a = ev_a.get("evidence_id", "")
                    evi_id_b = ev_b.get("evidence_id", "")
                    source_a = evidence_name_map.get(evi_id_a, evi_id_a)
                    source_b = evidence_name_map.get(evi_id_b, evi_id_b)
                    page_a_suffix = f" (p. {ev_a.get('page_number')})" if ev_a.get("page_number") else ""
                    page_b_suffix = f" (p. {ev_b.get('page_number')})" if ev_b.get("page_number") else ""

                    # --- A. Monetary Comparisons ---
                    amt_a_raw = ev_a.get("amount_value")
                    amt_b_raw = ev_b.get("amount_value")
                    if amt_a_raw is not None and amt_b_raw is not None:
                        try:
                            val_a = float(amt_a_raw.to_decimal()) if hasattr(amt_a_raw, "to_decimal") else float(amt_a_raw)
                            val_b = float(amt_b_raw.to_decimal()) if hasattr(amt_b_raw, "to_decimal") else float(amt_b_raw)
                        except (ValueError, TypeError):
                            val_a = None
                            val_b = None

                        if val_a is not None and val_b is not None:
                            curr_a = (ev_a.get("amount_currency") or "").strip().upper()
                            curr_b = (ev_b.get("amount_currency") or "").strip().upper()

                            # Currency mismatch
                            if curr_a and curr_b and curr_a != curr_b:
                                f_id = generate_finding_id(
                                    case_id,
                                    "CURRENCY_MISMATCH",
                                    norm_key,
                                    [ev_a["event_id"], ev_b["event_id"]],
                                )
                                if f_id not in seen_finding_ids:
                                    seen_finding_ids.add(f_id)
                                    findings.append(
                                        FindingResponse(
                                            finding_id=f_id,
                                            case_id=case_id,
                                            finding_type=FindingType.POTENTIAL_INCONSISTENCY.value,
                                            title=f"Potential Inconsistency: Currency Denomination Mismatch on Reference {display_ref}",
                                            summary=(
                                                f"Reference '{display_ref}' is denominated in {curr_a} in {source_a} "
                                                f"and in {curr_b} in {source_b}. Direct numeric comparison requires "
                                                f"exchange rate verification."
                                            ),
                                            severity="MEDIUM",
                                            conflict_state=ConflictState.POTENTIAL_CONFLICT.value,
                                            citations=[
                                                build_citation(ev_a, evidence_name_map),
                                                build_citation(ev_b, evidence_name_map),
                                            ],
                                            field_diff=FieldDifference(
                                                field="Currency Denomination",
                                                value_a=f"{curr_a} {val_a:,.2f}",
                                                source_a=f"{source_a}{page_a_suffix}",
                                                value_b=f"{curr_b} {val_b:,.2f}",
                                                source_b=f"{source_b}{page_b_suffix}",
                                            ),
                                            model_confidence=min(
                                                float(ev_a.get("model_confidence", 1.0)),
                                                float(ev_b.get("model_confidence", 1.0)),
                                            ),
                                            model_name=REASONING_METADATA.model_name,
                                        )
                                    )
                            elif abs(val_a - val_b) > 0.01:
                                # Numerical discrepancy in same (or unspecified) currency
                                type_a = ev_a.get("event_type", "")
                                type_b = ev_b.get("event_type", "")
                                symbol = curr_a or curr_b or "$"

                                # Check extraction certainty
                                state_a = ev_a.get("decision_state")
                                state_b = ev_b.get("decision_state")
                                is_uncertain = state_a == "REVIEW_NEEDED" or state_b == "REVIEW_NEEDED"

                                if is_uncertain:
                                    f_id = generate_finding_id(
                                        case_id,
                                        "MONETARY_DISCREPANCY_UNCERTAIN",
                                        norm_key,
                                        [ev_a["event_id"], ev_b["event_id"]],
                                    )
                                    if f_id not in seen_finding_ids:
                                        seen_finding_ids.add(f_id)
                                        diff_val = abs(val_a - val_b)
                                        findings.append(
                                            FindingResponse(
                                                finding_id=f_id,
                                                case_id=case_id,
                                                finding_type=FindingType.POTENTIAL_INCONSISTENCY.value,
                                                title=f"Uncertain Comparison: Amount Divergence on Reference {display_ref}",
                                                summary=(
                                                    f"Extracted amounts differ by {symbol}{diff_val:,.2f} ({symbol}{val_a:,.2f} vs {symbol}{val_b:,.2f}), "
                                                    f"but extraction certainty is flagged for review. Manual verification is advised before evaluating inconsistency."
                                                ),
                                                severity="LOW",
                                                conflict_state=ConflictState.INSUFFICIENT_CONTEXT.value,
                                                citations=[
                                                    build_citation(ev_a, evidence_name_map),
                                                    build_citation(ev_b, evidence_name_map),
                                                ],
                                                field_diff=FieldDifference(
                                                    field="Amount",
                                                    value_a=f"{symbol}{val_a:,.2f}",
                                                    source_a=f"{source_a}{page_a_suffix}",
                                                    value_b=f"{symbol}{val_b:,.2f}",
                                                    source_b=f"{source_b}{page_b_suffix}",
                                                ),
                                                model_confidence=min(
                                                    float(ev_a.get("model_confidence", 0.5)),
                                                    float(ev_b.get("model_confidence", 0.5)),
                                                ),
                                                model_name=REASONING_METADATA.model_name,
                                            )
                                        )
                                else:
                                    # Conservative semantics: numeric differences alone must NOT establish
                                    # a direct contradiction without mutual exclusivity. We emit POTENTIAL_CONFLICT.
                                    f_id = generate_finding_id(
                                        case_id,
                                        "MONETARY_DISCREPANCY_POTENTIAL",
                                        norm_key,
                                        [ev_a["event_id"], ev_b["event_id"]],
                                    )
                                    if f_id not in seen_finding_ids:
                                        seen_finding_ids.add(f_id)
                                        diff_val = abs(val_a - val_b)
                                        clean_type_a = type_a.replace("_", " ")
                                        clean_type_b = type_b.replace("_", " ")
                                        stage_note = (
                                            "Differing stages allow for partial payments, adjustments, or fee structures."
                                            if type_a != type_b
                                            else "Differing line items, tax inclusions, revisions, or partial milestones may account for this divergence."
                                        )
                                        findings.append(
                                            FindingResponse(
                                                finding_id=f_id,
                                                case_id=case_id,
                                                finding_type=FindingType.POTENTIAL_INCONSISTENCY.value,
                                                title=f"Potential Inconsistency: Amount Divergence on Reference {display_ref}",
                                                summary=(
                                                    f"{clean_type_a} ({symbol}{val_a:,.2f} in {source_a}) differs from "
                                                    f"{clean_type_b} ({symbol}{val_b:,.2f} in {source_b}) by {symbol}{diff_val:,.2f}. "
                                                    f"{stage_note}"
                                                ),
                                                severity="MEDIUM",
                                                conflict_state=ConflictState.POTENTIAL_CONFLICT.value,
                                                citations=[
                                                    build_citation(ev_a, evidence_name_map),
                                                    build_citation(ev_b, evidence_name_map),
                                                ],
                                                field_diff=FieldDifference(
                                                    field="Amount",
                                                    value_a=f"{symbol}{val_a:,.2f}",
                                                    source_a=f"{source_a}{page_a_suffix}",
                                                    value_b=f"{symbol}{val_b:,.2f}",
                                                    source_b=f"{source_b}{page_b_suffix}",
                                                ),
                                                model_confidence=min(
                                                    float(ev_a.get("model_confidence", 1.0)),
                                                    float(ev_b.get("model_confidence", 1.0)),
                                                ),
                                                model_name=REASONING_METADATA.model_name,
                                            )
                                        )

                    # --- B. Polarity Comparisons ---
                    pol_a = ev_a.get("polarity")
                    pol_b = ev_b.get("polarity")
                    type_a = ev_a.get("event_type")
                    type_b = ev_b.get("event_type")
                    if type_a == type_b and pol_a and pol_b and pol_a != pol_b:
                        f_id = generate_finding_id(
                            case_id,
                            "POLARITY_CONFLICT",
                            norm_key,
                            [ev_a["event_id"], ev_b["event_id"]],
                        )
                        if f_id not in seen_finding_ids:
                            seen_finding_ids.add(f_id)
                            event_clean_name = type_a.replace("_", " ")
                            findings.append(
                                FindingResponse(
                                    finding_id=f_id,
                                    case_id=case_id,
                                    finding_type=FindingType.POTENTIAL_INCONSISTENCY.value,
                                    title=f"Potential Inconsistency: Opposing Assertion on {event_clean_name} ({display_ref})",
                                    summary=(
                                        f"One document asserts this milestone positively, while another document "
                                        f"asserts negative polarity for reference '{display_ref}'. "
                                        f"This indicates divergent factual claims regarding whether this event occurred."
                                    ),
                                    severity="MEDIUM",
                                    conflict_state=ConflictState.POTENTIAL_CONFLICT.value,
                                    citations=[
                                        build_citation(ev_a, evidence_name_map),
                                        build_citation(ev_b, evidence_name_map),
                                    ],
                                    field_diff=FieldDifference(
                                        field="Assertion Polarity",
                                        value_a=pol_a,
                                        source_a=f"{source_a}{page_a_suffix}",
                                        value_b=pol_b,
                                        source_b=f"{source_b}{page_b_suffix}",
                                    ),
                                    model_confidence=min(
                                        float(ev_a.get("model_confidence", 1.0)),
                                        float(ev_b.get("model_confidence", 1.0)),
                                    ),
                                    model_name=REASONING_METADATA.model_name,
                                )
                            )

        # 4. Missing Corroboration Analysis (e.g., PAYMENT_SENT without confirmation)
        outgoing_tx_types = {"PAYMENT_SENT", "PAYMENT_MADE", "REFUND_REQUESTED"}
        confirmation_types = {"PAYMENT_CONFIRMED", "REFUND_ISSUED", "REFUND_PROCESSED", "REFUND_COMPLETED"}

        for ev in events:
            ev_type = ev.get("event_type", "")
            if ev_type in outgoing_tx_types:
                norm_ref = normalize_reference(ev.get("order_reference")) or normalize_reference(ev.get("transaction_reference"))
                if not norm_ref:
                    continue

                display_ref = (ev.get("order_reference") or ev.get("transaction_reference") or "").strip()
                has_corroboration = False
                for other in events:
                    if other.get("evidence_id") == ev.get("evidence_id"):
                        continue
                    if other.get("event_type") in confirmation_types:
                        other_ref = normalize_reference(other.get("order_reference")) or normalize_reference(other.get("transaction_reference"))
                        if other_ref == norm_ref:
                            has_corroboration = True
                            break

                if not has_corroboration:
                    f_id = generate_finding_id(
                        case_id,
                        "MISSING_CORROBORATION",
                        norm_ref,
                        [ev["event_id"]],
                    )
                    if f_id not in seen_finding_ids:
                        seen_finding_ids.add(f_id)
                        findings.append(
                            FindingResponse(
                                finding_id=f_id,
                                case_id=case_id,
                                finding_type=FindingType.MISSING_EVIDENCE_ADVISORY.value,
                                title=f"Unconfirmed Transaction Reference ({display_ref})",
                                summary=(
                                    f"An outgoing transaction is asserted in evidence, but no corresponding settlement "
                                    f"or confirmation document is present in the case. This indicates an uncorroborated "
                                    f"claim or documentation gap, not proof of falsity."
                                ),
                                severity="MEDIUM",
                                conflict_state=ConflictState.POTENTIAL_CONFLICT.value,
                                citations=[build_citation(ev, evidence_name_map)],
                                model_confidence=float(ev.get("model_confidence", 0.90)),
                                model_name=REASONING_METADATA.model_name,
                            )
                        )

        # 5. Temporal Consistency Analysis over strictly explicit timestamps
        timestamped_events: List[Tuple[Dict[str, Any], datetime]] = []
        for ev in events:
            raw_ts = ev.get("temporal_information") or ev.get("timestamp")
            parsed_ts = parse_explicit_timestamp(raw_ts)
            if parsed_ts is not None:
                timestamped_events.append((ev, parsed_ts))

        for earlier_type, later_type in EXPECTED_PRECEDENCE:
            earlier_matches = [t for t in timestamped_events if t[0].get("event_type") == earlier_type]
            later_matches = [t for t in timestamped_events if t[0].get("event_type") == later_type]

            for ev_early, ts_early in earlier_matches:
                for ev_late, ts_late in later_matches:
                    # Enforce distinct evidence documents
                    if ev_early.get("evidence_id") == ev_late.get("evidence_id"):
                        continue

                    # Enforce reference match if references exist on both
                    ref_early = normalize_reference(ev_early.get("order_reference")) or normalize_reference(ev_early.get("transaction_reference"))
                    ref_late = normalize_reference(ev_late.get("order_reference")) or normalize_reference(ev_late.get("transaction_reference"))

                    if ref_early and ref_late and ref_early != ref_late:
                        # Refer to different orders; not a sequence violation
                        continue

                    # If later event strictly precedes the earlier event in explicit time
                    if ts_late < ts_early:
                        ref_discriminator = ref_early or ref_late or "CASE_SCOPE"
                        f_id = generate_finding_id(
                            case_id,
                            f"TEMPORAL_VIOLATION_{earlier_type}_{later_type}",
                            ref_discriminator,
                            [ev_early["event_id"], ev_late["event_id"]],
                        )
                        if f_id not in seen_finding_ids:
                            seen_finding_ids.add(f_id)
                            clean_early = earlier_type.replace("_", " ")
                            clean_late = later_type.replace("_", " ")
                            findings.append(
                                FindingResponse(
                                    finding_id=f_id,
                                    case_id=case_id,
                                    finding_type=FindingType.POTENTIAL_INCONSISTENCY.value,
                                    title=f"Potential Inconsistency: Temporal Sequence Anomaly ({ref_discriminator})",
                                    summary=(
                                        f"{clean_late} recorded at {ts_late.isoformat()} precedes "
                                        f"{clean_early} recorded at {ts_early.isoformat()} for reference '{ref_discriminator}'. "
                                        f"Differing timezones, retrospective logging, or batch entry delays may account for this chronological inversion."
                                    ),
                                    severity="MEDIUM",
                                    conflict_state=ConflictState.POTENTIAL_CONFLICT.value,
                                    citations=[
                                        build_citation(ev_early, evidence_name_map),
                                        build_citation(ev_late, evidence_name_map),
                                    ],
                                    model_confidence=min(
                                        float(ev_early.get("model_confidence", 1.0)),
                                        float(ev_late.get("model_confidence", 1.0)),
                                    ),
                                    model_name=REASONING_METADATA.model_name,
                                )
                            )

        # 6. Sort deterministically by severity (HIGH > MEDIUM > LOW) then finding_id
        severity_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        findings.sort(key=lambda f: (severity_order.get(f.severity, 3), f.finding_id))

        return FindingListResponse(
            items=findings,
            total=len(findings),
            case_id=case_id,
        )

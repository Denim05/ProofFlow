import hashlib
import io
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import pymupdf
from pymongo.asynchronous.database import AsyncDatabase

from app.models.common import utc_now
from app.schemas.case import CaseResponse
from app.schemas.dossier import (
    DossierCitationItem,
    DossierDocumentInventoryItem,
    DossierEventItem,
    DossierEvidenceGapItem,
    DossierFieldDiffItem,
    DossierFindingItem,
    DossierMethodology,
    DossierResponse,
)
from app.schemas.finding import FindingResponse
from app.schemas.review import FindingReviewResponse
from app.services.finding_service import FindingService


class DossierService:
    """Orchestrates authoritative case data snapshotting and multi-format dossier export (JSON & PDF)."""

    @classmethod
    async def build_dossier_data(
        cls,
        case_id: str,
        user_id: str,
        db: AsyncDatabase,
    ) -> DossierResponse:
        """Collects authoritative, consistent case data snapshot for the dispute dossier."""
        # 1. Fetch Case
        case_row = await db.cases.find_one({"case_id": case_id, "user_id": user_id})
        if not case_row:
            raise ValueError(f"Case '{case_id}' was not found for user '{user_id}'")

        cleaned_case_dict = {
            "description": "",
            "status": "READY",
            "tags": [],
            "evidence_count": 0,
            "metadata": {},
            **case_row,
        }
        case_res = CaseResponse(**cleaned_case_dict)

        # 2. Fetch Evidence
        evidence_cursor = db.evidence.find({"case_id": case_id, "user_id": user_id}).sort("created_at", 1)
        evidence_list: List[dict] = []
        evidence_name_map: Dict[str, str] = {}
        inventory_items: List[DossierDocumentInventoryItem] = []

        async for row in evidence_cursor:
            evidence_list.append(row)
            evidence_name_map[row["evidence_id"]] = row.get("original_filename", row["evidence_id"])
            inventory_items.append(
                DossierDocumentInventoryItem(
                    evidence_id=row["evidence_id"],
                    original_filename=row.get("original_filename", "unnamed_evidence"),
                    media_type=row.get("media_type", "application/octet-stream"),
                    file_size_bytes=row.get("file_size_bytes", 0),
                    sha256_hash=row.get("sha256_hash", "0" * 64),
                    status=row.get("status", "UNKNOWN"),
                    uploaded_at=row.get("created_at", utc_now()),
                    active_processing_version=row.get("active_processing_version"),
                )
            )

        # 3. Fetch Active Events
        events_cursor = db.events.find(
            {"case_id": case_id, "user_id": user_id, "is_active": True}
        ).sort("created_at", 1)
        events_items: List[DossierEventItem] = []

        async for ev in events_cursor:
            evi_id = ev.get("evidence_id", "")
            source_doc = evidence_name_map.get(evi_id, evi_id)

            # Determine stated event date if extracted, or explicitly indicate unstated
            stated_date = ev.get("metadata", {}).get("stated_date") or ev.get("temporal_text")
            events_items.append(
                DossierEventItem(
                    event_id=ev["event_id"],
                    evidence_id=evi_id,
                    source_document=source_doc,
                    event_type=ev.get("event_type", "UNKNOWN"),
                    decision_state=ev.get("decision_state", "VALIDATED"),
                    order_reference=ev.get("order_reference"),
                    transaction_reference=ev.get("transaction_reference"),
                    amount_value=ev.get("amount_value"),
                    amount_currency=ev.get("amount_currency"),
                    polarity=ev.get("polarity", "POSITIVE"),
                    modality=ev.get("modality", "ASSERTED"),
                    tense=ev.get("tense", "PAST"),
                    trigger_raw_text=ev.get("trigger_raw_text", ""),
                    char_start=ev.get("char_start"),
                    char_end=ev.get("char_end"),
                    page_number=ev.get("page_number"),
                    stated_event_date=stated_date,
                    document_upload_time=ev.get("created_at", utc_now()),
                )
            )

        # 4. Compute Findings & Fetch Reviews
        findings_list_res = await FindingService.compute_case_findings(case_id, user_id, db)
        findings_items: List[DossierFindingItem] = []
        all_human_reviews: List[FindingReviewResponse] = []

        # Fetch all human reviews across the case
        reviews_cursor = db.finding_reviews.find({"case_id": case_id}).sort("created_at", -1)
        finding_reviews_map: Dict[str, List[FindingReviewResponse]] = {}

        async for rev_doc in reviews_cursor:
            rev_obj = FindingReviewResponse(**rev_doc)
            all_human_reviews.append(rev_obj)
            f_id = rev_obj.finding_id
            if f_id not in finding_reviews_map:
                finding_reviews_map[f_id] = []
            finding_reviews_map[f_id].append(rev_obj)

        for finding in findings_list_res.items:
            history = finding_reviews_map.get(finding.finding_id, [])
            # Sort history by version descending
            history.sort(key=lambda r: r.version, reverse=True)

            active_rev = next((r for r in history if r.is_active), None) or finding.active_review
            adjudication_status = active_rev.decision if active_rev else "UNREVIEWED"

            citations = [
                DossierCitationItem(
                    evidence_id=c.evidence_id,
                    original_filename=c.original_filename,
                    page_number=c.page_number,
                    char_start=c.char_start,
                    char_end=c.char_end,
                    trigger_raw_text=c.trigger_raw_text,
                    event_id=c.event_id,
                )
                for c in finding.citations
            ]

            field_diff = None
            if finding.field_diff:
                field_diff = DossierFieldDiffItem(
                    field=finding.field_diff.field,
                    value_a=finding.field_diff.value_a,
                    source_a=finding.field_diff.source_a,
                    value_b=finding.field_diff.value_b,
                    source_b=finding.field_diff.source_b,
                )

            findings_items.append(
                DossierFindingItem(
                    finding_id=finding.finding_id,
                    finding_type=finding.finding_type,
                    title=finding.title,
                    summary=finding.summary,
                    severity=finding.severity,
                    conflict_state=finding.conflict_state,
                    citations=citations,
                    field_diff=field_diff,
                    model_confidence=finding.model_confidence,
                    model_name=finding.model_name,
                    created_at=finding.created_at,
                    adjudication_status=adjudication_status,
                    active_review=active_rev,
                    review_history=history,
                )
            )

        # 5. Synthesize Evidence Gaps & Unresolved Questions
        evidence_gaps: List[DossierEvidenceGapItem] = []

        # Gap detection from findings
        for f in findings_items:
            if f.finding_type == "MISSING_EVIDENCE_ADVISORY":
                evidence_gaps.append(
                    DossierEvidenceGapItem(
                        gap_type="MISSING_CORROBORATION",
                        description=f.summary,
                        related_reference=f.title.split("(")[-1].replace(")", "") if "(" in f.title else None,
                        affected_evidence_ids=[c.evidence_id for c in f.citations],
                    )
                )

        # Gap detection from evidence statuses
        for evi in inventory_items:
            if evi.status in ["FAILED", "REVIEW_NEEDED", "INTERRUPTED"]:
                evidence_gaps.append(
                    DossierEvidenceGapItem(
                        gap_type="PROCESSING_ANOMALY",
                        description=f"Evidence document '{evi.original_filename}' is in state {evi.status} and may contain incomplete extractions.",
                        affected_evidence_ids=[evi.evidence_id],
                    )
                )

        if not inventory_items:
            evidence_gaps.append(
                DossierEvidenceGapItem(
                    gap_type="DOCUMENT_UNAVAILABLE",
                    description="No evidence documents have been uploaded to this case.",
                    affected_evidence_ids=[],
                )
            )

        # 6. Generate Objective Executive Summary
        confirmed_count = sum(1 for f in findings_items if f.adjudication_status == "CONFIRMED_INCONSISTENCY")
        resolved_count = sum(1 for f in findings_items if f.adjudication_status == "RESOLVED")
        dismissed_count = sum(1 for f in findings_items if f.adjudication_status == "DISMISSED")
        unreviewed_count = sum(1 for f in findings_items if f.adjudication_status == "UNREVIEWED")

        exec_summary = (
            f"This dispute dossier compiles documentary evidence and cross-examination findings for Case '{case_res.case_id}' "
            f"('{case_res.title}'). The submitted record comprises {len(inventory_items)} evidence document(s) yielding "
            f"{len(events_items)} verified event assertion(s). Automated reasoning identified {len(findings_items)} potential "
            f"inconsistency or documentation advisory findings. Human review records indicate {confirmed_count} confirmed inconsistency(ies), "
            f"{resolved_count} resolved matter(s), {dismissed_count} dismissed item(s), and {unreviewed_count} pending review. "
            f"All citations refer to exact source document passages. This dossier organizes evidence and does not constitute a legal "
            f"finding of fault or liability."
        )

        # 7. Compute Manifest Hash
        manifest_input = f"{case_id}::{case_res.updated_at.isoformat()}::" + "::".join(
            sorted([item.sha256_hash for item in inventory_items])
        )
        manifest_hash = hashlib.sha256(manifest_input.encode("utf-8")).hexdigest()

        return DossierResponse(
            report_version="1.0.0",
            generated_at=utc_now(),
            manifest_hash=manifest_hash,
            case=case_res,
            executive_summary=exec_summary,
            document_inventory=inventory_items,
            events_timeline=events_items,
            findings=findings_items,
            human_reviews=all_human_reviews,
            evidence_gaps=evidence_gaps,
            methodology=DossierMethodology(),
        )

    @classmethod
    def generate_dossier_pdf(cls, dossier: DossierResponse) -> bytes:
        """Renders a comprehensive, publication-grade PDF dispute dossier using PyMuPDF."""
        doc = pymupdf.open()

        page_w = 612.0  # Standard US Letter Width (points)
        page_h = 792.0  # Standard US Letter Height (points)
        margin_x = 45.0
        margin_y = 50.0
        content_w = page_w - (margin_x * 2)

        # Color Palette
        col_primary = (0.08, 0.12, 0.22)   # Deep Navy
        col_accent = (0.15, 0.35, 0.65)    # Brand Blue
        col_text = (0.15, 0.18, 0.22)      # Charcoal
        col_muted = (0.42, 0.46, 0.52)     # Muted Grey
        col_border = (0.82, 0.85, 0.88)    # Border Grey
        col_bg_light = (0.96, 0.97, 0.98)  # Light panel fill
        col_amber = (0.82, 0.45, 0.05)     # Amber warning
        col_emerald = (0.05, 0.55, 0.30)   # Emerald success
        col_slate = (0.35, 0.38, 0.45)     # Slate dismiss

        current_page = [doc.new_page(width=page_w, height=page_h)]
        cursor_y = [margin_y]

        def get_page():
            return current_page[0]

        def new_page():
            current_page[0] = doc.new_page(width=page_w, height=page_h)
            cursor_y[0] = margin_y
            draw_running_header()

        def draw_running_header():
            p = get_page()
            p.draw_line(
                pymupdf.Point(margin_x, margin_y - 12),
                pymupdf.Point(margin_x + content_w, margin_y - 12),
                color=col_border,
                width=0.75,
            )
            p.insert_text(
                (margin_x, margin_y - 16),
                f"ProofFlow Dispute Dossier — Case: {dossier.case.case_id}",
                fontsize=8,
                color=col_muted,
            )
            date_str = dossier.generated_at.strftime("%Y-%m-%d %H:%M UTC")
            p.insert_text(
                (margin_x + content_w - 110, margin_y - 16),
                date_str,
                fontsize=8,
                color=col_muted,
            )

        def ensure_space(height_needed: float):
            if cursor_y[0] + height_needed > (page_h - margin_y - 30):
                new_page()

        # -------------------------------------------------------------
        # 1. COVER PAGE / HEADER
        # -------------------------------------------------------------
        p = get_page()
        # Top banner decorative block
        p.draw_rect(pymupdf.Rect(margin_x, cursor_y[0], margin_x + content_w, cursor_y[0] + 6), color=col_accent, fill=col_accent)
        cursor_y[0] += 16

        # Subtitle and Title
        p.insert_text((margin_x, cursor_y[0] + 10), "PROOFFLOW EVIDENCE REASONING SYSTEM", fontsize=9, color=col_accent)
        cursor_y[0] += 16
        p.insert_text((margin_x, cursor_y[0] + 16), "DISPUTE EVIDENCE DOSSIER", fontsize=20, color=col_primary)
        cursor_y[0] += 30

        # Case Metadata Panel
        box_top = cursor_y[0]
        box_h = 74.0
        p.draw_rect(pymupdf.Rect(margin_x, box_top, margin_x + content_w, box_top + box_h), color=col_border, fill=col_bg_light)

        p.insert_text((margin_x + 12, box_top + 18), f"Case Reference: {dossier.case.case_id}", fontsize=10, color=col_primary)
        p.insert_text((margin_x + 12, box_top + 34), f"Case Title: {dossier.case.title[:60]}", fontsize=10, color=col_text)
        p.insert_text((margin_x + 12, box_top + 50), f"Case Status: {dossier.case.status}", fontsize=9, color=col_accent)

        gen_str = dossier.generated_at.strftime("%Y-%m-%d %H:%M:%S UTC")
        p.insert_text((margin_x + 280, box_top + 18), f"Report Version: {dossier.report_version}", fontsize=9, color=col_muted)
        p.insert_text((margin_x + 280, box_top + 34), f"Generated: {gen_str}", fontsize=9, color=col_muted)
        p.insert_text((margin_x + 280, box_top + 50), f"Manifest SHA: {dossier.manifest_hash[:16]}...", fontsize=8, color=col_muted)
        cursor_y[0] += box_h + 18

        # -------------------------------------------------------------
        # 2. EXECUTIVE NOTICE & SUMMARY
        # -------------------------------------------------------------
        p.insert_text((margin_x, cursor_y[0] + 12), "1. Executive Summary & Objective Notice", fontsize=13, color=col_primary)
        cursor_y[0] += 20

        # Mandatory Disclaimers Callout
        disclaimer_box_top = cursor_y[0]
        disclaimer_rect = pymupdf.Rect(margin_x, disclaimer_box_top, margin_x + content_w, disclaimer_box_top + 46)
        p.draw_rect(disclaimer_rect, color=(0.88, 0.70, 0.40), fill=(0.99, 0.98, 0.94))
        disclaimer_text = (
            "NOTICE: ProofFlow is an evidence organization and verification workspace, not a judicial or legal decision "
            "engine. Statements in this report reflect algorithmic extraction from submitted documents and recorded human "
            "adjudications. No statement constitutes an accusation of fraud or finding of legal liability."
        )
        p.insert_textbox(
            pymupdf.Rect(margin_x + 8, disclaimer_box_top + 6, margin_x + content_w - 8, disclaimer_box_top + 42),
            disclaimer_text,
            fontsize=8,
            color=(0.55, 0.35, 0.05),
        )
        cursor_y[0] += 56

        # Executive Summary Paragraph
        summary_rect = pymupdf.Rect(margin_x, cursor_y[0], margin_x + content_w, cursor_y[0] + 50)
        p.insert_textbox(summary_rect, dossier.executive_summary, fontsize=9, color=col_text)
        cursor_y[0] += 58

        # Summary Metrics Chips
        chips_y = cursor_y[0]
        chips = [
            ("Documents", str(len(dossier.document_inventory))),
            ("Events", str(len(dossier.events_timeline))),
            ("Findings", str(len(dossier.findings))),
            ("Adjudications", str(len(dossier.human_reviews))),
        ]
        chip_w = content_w / 4.0
        for i, (label, val) in enumerate(chips):
            cx = margin_x + (i * chip_w)
            p.draw_rect(pymupdf.Rect(cx, chips_y, cx + chip_w - 6, chips_y + 36), color=col_border, fill=col_bg_light)
            p.insert_text((cx + 10, chips_y + 14), label, fontsize=8, color=col_muted)
            p.insert_text((cx + 10, chips_y + 28), val, fontsize=12, color=col_primary)
        cursor_y[0] += 48

        # -------------------------------------------------------------
        # 3. DOCUMENT INVENTORY
        # -------------------------------------------------------------
        ensure_space(100)
        p = get_page()
        p.insert_text((margin_x, cursor_y[0] + 12), "2. Evidence Document Inventory", fontsize=13, color=col_primary)
        cursor_y[0] += 20

        # Table Header
        tbl_y = cursor_y[0]
        p.draw_rect(pymupdf.Rect(margin_x, tbl_y, margin_x + content_w, tbl_y + 18), color=col_border, fill=col_primary)
        p.insert_text((margin_x + 6, tbl_y + 12), "Filename", fontsize=8, color=(1, 1, 1))
        p.insert_text((margin_x + 180, tbl_y + 12), "Document ID", fontsize=8, color=(1, 1, 1))
        p.insert_text((margin_x + 290, tbl_y + 12), "Size / Status", fontsize=8, color=(1, 1, 1))
        p.insert_text((margin_x + 380, tbl_y + 12), "SHA-256 Digest", fontsize=8, color=(1, 1, 1))
        cursor_y[0] += 18

        if not dossier.document_inventory:
            ensure_space(24)
            p = get_page()
            p.insert_text((margin_x + 6, cursor_y[0] + 14), "No evidence documents submitted in this case.", fontsize=9, color=col_muted)
            cursor_y[0] += 24
        else:
            for item in dossier.document_inventory:
                ensure_space(20)
                p = get_page()
                row_y = cursor_y[0]
                p.draw_rect(pymupdf.Rect(margin_x, row_y, margin_x + content_w, row_y + 18), color=col_border, fill=(1, 1, 1))
                p.insert_text((margin_x + 6, row_y + 12), item.original_filename[:32], fontsize=8, color=col_text)
                p.insert_text((margin_x + 180, row_y + 12), item.evidence_id[:16], fontsize=7, color=col_muted)
                size_kb = f"{item.file_size_bytes / 1024:.1f} KB" if item.file_size_bytes else "0 KB"
                p.insert_text((margin_x + 290, row_y + 12), f"{size_kb} • {item.status}", fontsize=8, color=col_text)
                p.insert_text((margin_x + 380, row_y + 12), f"{item.sha256_hash[:18]}...", fontsize=7, color=col_muted)
                cursor_y[0] += 18
        cursor_y[0] += 16

        # -------------------------------------------------------------
        # 4. CHRONOLOGICAL EVENT TIMELINE
        # -------------------------------------------------------------
        ensure_space(100)
        p = get_page()
        p.insert_text((margin_x, cursor_y[0] + 12), "3. Chronological Event Timeline", fontsize=13, color=col_primary)
        cursor_y[0] += 20

        if not dossier.events_timeline:
            ensure_space(24)
            p = get_page()
            p.insert_text((margin_x + 6, cursor_y[0] + 14), "No events extracted or established from submitted evidence.", fontsize=9, color=col_muted)
            cursor_y[0] += 24
        else:
            # Timeline Header Table
            tbl_y = cursor_y[0]
            p.draw_rect(pymupdf.Rect(margin_x, tbl_y, margin_x + content_w, tbl_y + 18), color=col_border, fill=col_primary)
            p.insert_text((margin_x + 6, tbl_y + 12), "Event Type", fontsize=8, color=(1, 1, 1))
            p.insert_text((margin_x + 140, tbl_y + 12), "Stated Date / Upload Time", fontsize=8, color=(1, 1, 1))
            p.insert_text((margin_x + 280, tbl_y + 12), "Reference & Amount", fontsize=8, color=(1, 1, 1))
            p.insert_text((margin_x + 420, tbl_y + 12), "Source Document", fontsize=8, color=(1, 1, 1))
            cursor_y[0] += 18

            for ev in dossier.events_timeline:
                ensure_space(38)
                p = get_page()
                row_y = cursor_y[0]
                p.draw_rect(pymupdf.Rect(margin_x, row_y, margin_x + content_w, row_y + 36), color=col_border, fill=(1, 1, 1))

                # Event Type & polarity
                p.insert_text((margin_x + 6, row_y + 12), ev.event_type[:22], fontsize=8, color=col_primary)
                p.insert_text((margin_x + 6, row_y + 24), f"Status: {ev.polarity}", fontsize=7, color=col_muted)

                # Date breakdown
                stated_txt = ev.stated_event_date if ev.stated_event_date else "Date not stated in doc"
                upload_txt = ev.document_upload_time.strftime("%Y-%m-%d")
                p.insert_text((margin_x + 140, row_y + 12), f"Stated: {stated_txt[:24]}", fontsize=7, color=col_text)
                p.insert_text((margin_x + 140, row_y + 24), f"Uploaded: {upload_txt}", fontsize=7, color=col_muted)

                # Reference & Amount
                ref = ev.order_reference or ev.transaction_reference or "N/A"
                amt = f"{ev.amount_currency or '$'}{ev.amount_value:,.2f}" if ev.amount_value is not None else "No amount"
                p.insert_text((margin_x + 280, row_y + 12), f"Ref: {ref[:18]}", fontsize=8, color=col_text)
                p.insert_text((margin_x + 280, row_y + 24), amt, fontsize=7, color=col_muted)

                # Source doc and quote snippet
                doc_name = ev.source_document[:20]
                quote = f'"{ev.trigger_raw_text[:28]}..."' if ev.trigger_raw_text else ""
                p.insert_text((margin_x + 420, row_y + 12), doc_name, fontsize=7, color=col_text)
                p.insert_text((margin_x + 420, row_y + 24), quote, fontsize=6, color=col_muted)

                cursor_y[0] += 36
        cursor_y[0] += 16

        # -------------------------------------------------------------
        # 5. CROSS-EXAMINATION FINDINGS & GROUNDED CITATIONS
        # -------------------------------------------------------------
        ensure_space(100)
        p = get_page()
        p.insert_text((margin_x, cursor_y[0] + 12), "4. Cross-Examination Findings & Source Citations", fontsize=13, color=col_primary)
        cursor_y[0] += 20

        if not dossier.findings:
            ensure_space(24)
            p = get_page()
            p.insert_text((margin_x + 6, cursor_y[0] + 14), "No inconsistencies or discrepancies detected across active evidence.", fontsize=9, color=col_muted)
            cursor_y[0] += 24
        else:
            for idx, finding in enumerate(dossier.findings, 1):
                # Calculate needed space for finding box
                cites_count = len(finding.citations)
                diff_height = 28 if finding.field_diff else 0
                box_height = 70 + (cites_count * 24) + diff_height

                ensure_space(box_height + 10)
                p = get_page()
                f_top = cursor_y[0]

                # Border card
                p.draw_rect(pymupdf.Rect(margin_x, f_top, margin_x + content_w, f_top + box_height), color=col_border, fill=(1, 1, 1))

                # Finding Title & Badges
                p.insert_text((margin_x + 10, f_top + 16), f"Finding #{idx}: {finding.title[:55]}", fontsize=9, color=col_primary)

                # Status pill
                status_color = (
                    col_amber if finding.adjudication_status == "CONFIRMED_INCONSISTENCY"
                    else col_emerald if finding.adjudication_status == "RESOLVED"
                    else col_slate if finding.adjudication_status == "DISMISSED"
                    else col_muted
                )
                p.insert_text(
                    (margin_x + content_w - 140, f_top + 16),
                    f"[{finding.adjudication_status.replace('_', ' ')}]",
                    fontsize=8,
                    color=status_color,
                )

                # Summary Text
                p.insert_textbox(
                    pymupdf.Rect(margin_x + 10, f_top + 22, margin_x + content_w - 10, f_top + 50),
                    finding.summary,
                    fontsize=8,
                    color=col_text,
                )

                current_card_y = f_top + 54

                # Field Diff Comparison if present
                if finding.field_diff:
                    diff_rect = pymupdf.Rect(margin_x + 10, current_card_y, margin_x + content_w - 10, current_card_y + 22)
                    p.draw_rect(diff_rect, color=col_border, fill=col_bg_light)
                    diff_text = f"Field Diff ({finding.field_diff.field}): {finding.field_diff.source_a} = '{finding.field_diff.value_a}' vs {finding.field_diff.source_b} = '{finding.field_diff.value_b}'"
                    p.insert_text((margin_x + 14, current_card_y + 14), diff_text[:95], fontsize=7, color=col_primary)
                    current_card_y += 26

                # Grounded Evidence Citations
                for cite in finding.citations:
                    page_str = f"Page {cite.page_number}" if cite.page_number else "Page N/A"
                    char_str = f"chars [{cite.char_start}:{cite.char_end}]" if cite.char_start is not None else ""
                    quote_str = f'"{cite.trigger_raw_text}"' if cite.trigger_raw_text else "No quotation extracted"
                    cite_line = f"Citation: {cite.original_filename} ({page_str} {char_str}) -> {quote_str}"
                    p.insert_text((margin_x + 14, current_card_y + 12), cite_line[:100], fontsize=7, color=col_muted)
                    current_card_y += 18

                cursor_y[0] += box_height + 12
        cursor_y[0] += 10

        # -------------------------------------------------------------
        # 6. HUMAN ADJUDICATION & DECISION AUDIT TRAIL
        # -------------------------------------------------------------
        ensure_space(100)
        p = get_page()
        p.insert_text((margin_x, cursor_y[0] + 12), "5. Human Adjudication & Audit Log", fontsize=13, color=col_primary)
        cursor_y[0] += 20

        if not dossier.human_reviews:
            ensure_space(24)
            p = get_page()
            p.insert_text((margin_x + 6, cursor_y[0] + 14), "No human reviews or adjudications have been recorded for this case.", fontsize=9, color=col_muted)
            cursor_y[0] += 24
        else:
            tbl_y = cursor_y[0]
            p.draw_rect(pymupdf.Rect(margin_x, tbl_y, margin_x + content_w, tbl_y + 18), color=col_border, fill=col_primary)
            p.insert_text((margin_x + 6, tbl_y + 12), "Decision & Version", fontsize=8, color=(1, 1, 1))
            p.insert_text((margin_x + 150, tbl_y + 12), "Reviewer & Date", fontsize=8, color=(1, 1, 1))
            p.insert_text((margin_x + 290, tbl_y + 12), "Justification / Audit Note", fontsize=8, color=(1, 1, 1))
            cursor_y[0] += 18

            for rev in dossier.human_reviews:
                ensure_space(32)
                p = get_page()
                row_y = cursor_y[0]
                p.draw_rect(pymupdf.Rect(margin_x, row_y, margin_x + content_w, row_y + 30), color=col_border, fill=(1, 1, 1))

                active_label = " [Active]" if rev.is_active else " [Superseded]"
                p.insert_text((margin_x + 6, row_y + 12), f"{rev.decision} (v{rev.version})", fontsize=8, color=col_primary)
                p.insert_text((margin_x + 6, row_y + 24), active_label, fontsize=7, color=col_muted)

                p.insert_text((margin_x + 150, row_y + 12), f"By: {rev.reviewer_id[:18]}", fontsize=8, color=col_text)
                p.insert_text((margin_x + 150, row_y + 24), rev.created_at.strftime("%Y-%m-%d %H:%M"), fontsize=7, color=col_muted)

                reason_txt = rev.reason if rev.reason else "No written rationale provided."
                p.insert_textbox(
                    pymupdf.Rect(margin_x + 290, row_y + 4, margin_x + content_w - 6, row_y + 26),
                    reason_txt,
                    fontsize=7,
                    color=col_text,
                )
                cursor_y[0] += 30
        cursor_y[0] += 16

        # -------------------------------------------------------------
        # 7. EVIDENCE GAPS & UNRESOLVED QUESTIONS
        # -------------------------------------------------------------
        ensure_space(90)
        p = get_page()
        p.insert_text((margin_x, cursor_y[0] + 12), "6. Evidence Gaps & Documentation Questions", fontsize=13, color=col_primary)
        cursor_y[0] += 20

        if not dossier.evidence_gaps:
            ensure_space(24)
            p = get_page()
            p.insert_text((margin_x + 6, cursor_y[0] + 14), "No uncorroborated transactions or documentation gaps flagged.", fontsize=9, color=col_muted)
            cursor_y[0] += 24
        else:
            for gap in dossier.evidence_gaps:
                ensure_space(28)
                p = get_page()
                gap_y = cursor_y[0]
                p.draw_rect(pymupdf.Rect(margin_x, gap_y, margin_x + content_w, gap_y + 24), color=col_border, fill=col_bg_light)
                p.insert_text((margin_x + 8, gap_y + 14), f"• [{gap.gap_type}] {gap.description[:95]}", fontsize=8, color=col_text)
                cursor_y[0] += 26
        cursor_y[0] += 16

        # -------------------------------------------------------------
        # 8. METHODOLOGY & AUDIT STANDARDS
        # -------------------------------------------------------------
        ensure_space(80)
        p = get_page()
        p.insert_text((margin_x, cursor_y[0] + 12), "7. Methodology, System Profile & Limitations", fontsize=13, color=col_primary)
        cursor_y[0] += 20

        meth_rect = pymupdf.Rect(margin_x, cursor_y[0], margin_x + content_w, cursor_y[0] + 60)
        p.draw_rect(meth_rect, color=col_border, fill=col_bg_light)
        meth_txt = (
            f"Engine: {dossier.methodology.system_name} (v{dossier.methodology.system_version})\n"
            f"Standard: {dossier.methodology.report_standard}\n"
            "Processing: Deterministic rule verification, exact text quotation offsets, SHA-256 evidence digests.\n"
            "Verification: Human reviewers must independently inspect referenced citations prior to financial or legal action."
        )
        p.insert_textbox(pymupdf.Rect(margin_x + 8, cursor_y[0] + 6, margin_x + content_w - 8, cursor_y[0] + 54), meth_txt, fontsize=7, color=col_muted)
        cursor_y[0] += 66

        # -------------------------------------------------------------
        # RUNNING FOOTERS & PAGE NUMBERS (All Pages)
        # -------------------------------------------------------------
        total_pages = len(doc)
        for idx, pg in enumerate(doc, 1):
            footer_y = page_h - margin_y + 18
            pg.draw_line(
                pymupdf.Point(margin_x, footer_y - 10),
                pymupdf.Point(margin_x + content_w, footer_y - 10),
                color=col_border,
                width=0.5,
            )
            pg.insert_text(
                (margin_x, footer_y),
                "ProofFlow Evidence Organization & Review Tool • Human Verification Required",
                fontsize=7,
                color=col_muted,
            )
            pg.insert_text(
                (margin_x + content_w - 60, footer_y),
                f"Page {idx} of {total_pages}",
                fontsize=7,
                color=col_muted,
            )

        return doc.tobytes()

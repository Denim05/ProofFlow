from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.schemas.case import CaseResponse
from app.schemas.review import FindingReviewResponse


class DossierDocumentInventoryItem(BaseModel):
    """Metadata record for an evidence document included in the dossier."""
    evidence_id: str
    original_filename: str
    media_type: str
    file_size_bytes: int
    sha256_hash: str
    status: str
    uploaded_at: datetime
    active_processing_version: Optional[int] = None


class DossierEventItem(BaseModel):
    """Extracted chronological event record with provenance details."""
    event_id: str
    evidence_id: str
    source_document: str
    event_type: str
    decision_state: str
    order_reference: Optional[str] = None
    transaction_reference: Optional[str] = None
    amount_value: Optional[float] = None
    amount_currency: Optional[str] = None
    polarity: str = "POSITIVE"
    modality: str = "ASSERTED"
    tense: str = "PAST"
    trigger_raw_text: str = ""
    char_start: Optional[int] = None
    char_end: Optional[int] = None
    page_number: Optional[int] = None
    stated_event_date: Optional[str] = None
    document_upload_time: datetime


class DossierCitationItem(BaseModel):
    """Grounding citation for a cross-examination finding."""
    evidence_id: str
    original_filename: str
    page_number: Optional[int] = None
    char_start: Optional[int] = None
    char_end: Optional[int] = None
    trigger_raw_text: str = ""
    event_id: Optional[str] = None


class DossierFieldDiffItem(BaseModel):
    """Side-by-side field difference asserted across documents."""
    field: str
    value_a: str
    source_a: str
    value_b: str
    source_b: str


class DossierFindingItem(BaseModel):
    """Cross-examination finding accompanied by machine provenance and human adjudication."""
    finding_id: str
    finding_type: str
    title: str
    summary: str
    severity: str
    conflict_state: str
    citations: List[DossierCitationItem] = Field(default_factory=list)
    field_diff: Optional[DossierFieldDiffItem] = None
    model_confidence: float
    model_name: str = "proofflow-reasoning-engine"
    created_at: datetime
    adjudication_status: str = "UNREVIEWED"
    active_review: Optional[FindingReviewResponse] = None
    review_history: List[FindingReviewResponse] = Field(default_factory=list)


class DossierEvidenceGapItem(BaseModel):
    """Unresolved documentation question or corroboration gap."""
    gap_type: str
    description: str
    related_reference: Optional[str] = None
    affected_evidence_ids: List[str] = Field(default_factory=list)


class DossierMethodology(BaseModel):
    """Methodology, processing assumptions, and mandatory disclaimer."""
    system_name: str = "ProofFlow Evidence Reasoning Engine"
    system_version: str = "1.0.0"
    report_standard: str = "ProofFlow Evidence Dossier v1"
    disclaimer: str = (
        "This dossier is generated programmatically from submitted evidence documents "
        "and recorded human reviews. ProofFlow is an evidence organization and review tool, "
        "not a legal decision engine. No statement in this document constitutes a judicial "
        "finding, accusation of fraud, or determination of contractual fault."
    )
    limitations: List[str] = Field(
        default_factory=lambda: [
            "Extraction fidelity depends on scan clarity and document completeness.",
            "Event chronology reflects stated dates in source text or is marked as unstated.",
            "Cross-document inconsistencies identify conflicting assertions, not intent.",
            "Human adjudications are separate from machine extractions and preserve reviewer notes.",
        ]
    )


class DossierResponse(BaseModel):
    """Comprehensive dispute dossier package."""
    report_version: str = "1.0.0"
    generated_at: datetime
    manifest_hash: str
    case: CaseResponse
    executive_summary: str
    document_inventory: List[DossierDocumentInventoryItem] = Field(default_factory=list)
    events_timeline: List[DossierEventItem] = Field(default_factory=list)
    findings: List[DossierFindingItem] = Field(default_factory=list)
    human_reviews: List[FindingReviewResponse] = Field(default_factory=list)
    evidence_gaps: List[DossierEvidenceGapItem] = Field(default_factory=list)
    methodology: DossierMethodology = Field(default_factory=DossierMethodology)
    metadata: Dict[str, Any] = Field(default_factory=dict)

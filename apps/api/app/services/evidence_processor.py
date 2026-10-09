from datetime import datetime, timezone
from decimal import Decimal
import os
from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel, Field
from pymongo.asynchronous.database import AsyncDatabase

from app.core.logging import logger
from app.models.common import utc_now
from app.models.event import EventDocument
from app.models.evidence import EvidenceStatus, MLProcessingMode
from app.services.storage import storage_service
from ml.entities.pipeline import EntityExtractionPipeline
from ml.events.ensemble import EnsembleDecisionState, HybridEventCascade
from ml.extraction.pipeline import ExtractionPipeline
from ml.schemas.evidence_text import ExtractionQualityState


class ProcessingJob(BaseModel):
    """Serializable payload for background processing tasks."""

    job_id: str = Field(default_factory=lambda: f"job_{uuid.uuid4().hex[:24]}")
    evidence_id: str
    case_id: str
    user_id: str
    storage_relative_path: str
    original_filename: str
    media_type: str
    sha256_hash: str
    retry_count: int = 0
    enqueued_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class EvidenceProcessingService:
    """Coordinates evidence text extraction, entity extraction, and hybrid event analysis."""

    def __init__(self, mock_event_predictor=None):
        self.extraction_pipeline = ExtractionPipeline()
        self.entity_pipeline = EntityExtractionPipeline()
        self.event_cascade = HybridEventCascade(mock_predictor=mock_event_predictor)

    def detect_processing_mode(self) -> MLProcessingMode:
        """Accurately detects whether DeBERTa GPU, DeBERTa CPU, or deterministic fallback is running."""
        if self.event_cascade.mock_predictor is not None:
            return MLProcessingMode.DETERMINISTIC_FALLBACK

        if self.event_cascade._model is not None and self.event_cascade._device is not None:
            if self.event_cascade._device.type == "cuda":
                return MLProcessingMode.NEURAL_DEBERTA_GPU
            return MLProcessingMode.NEURAL_DEBERTA_CPU

        return MLProcessingMode.DETERMINISTIC_FALLBACK

    async def run_job(self, job: ProcessingJob, db: AsyncDatabase) -> None:
        """Executes full document extraction, entity normalization, and event extraction."""
        # 1. Atomic state claim to enforce idempotency
        claimed = await db.evidence.find_one_and_update(
            {
                "evidence_id": job.evidence_id,
                "status": {
                    "$in": [
                        EvidenceStatus.QUEUED.value,
                        EvidenceStatus.FAILED.value,
                        EvidenceStatus.INTERRUPTED.value,
                    ]
                },
            },
            {
                "$set": {
                    "status": EvidenceStatus.EXTRACTING.value,
                    "job_id": job.job_id,
                    "retry_count": job.retry_count,
                    "heartbeat_at": utc_now(),
                    "updated_at": utc_now(),
                }
            },
            return_document=True,
        )

        if not claimed:
            logger.info("Job %s skipped: evidence %s already active or terminal.", job.job_id, job.evidence_id)
            return

        current_version = claimed.get("processing_version", 1)
        target_version = current_version + (1 if job.retry_count > 0 else 0)
        mode = self.detect_processing_mode()

        try:
            # 2. Read raw binary content
            file_bytes = storage_service.read_evidence_bytes(job.storage_relative_path)

            # 3. Stage 1: Extraction Pipeline (Track 2)
            _, evidence_text = self.extraction_pipeline.process_evidence(
                evidence_id=job.evidence_id,
                case_id=job.case_id,
                user_id=job.user_id,
                file_bytes=file_bytes,
                filename=job.original_filename,
                mime_type=job.media_type,
                storage_path=job.storage_relative_path,
            )

            # Update status to STRUCTURING
            await db.evidence.update_one(
                {"evidence_id": job.evidence_id},
                {
                    "$set": {
                        "status": EvidenceStatus.STRUCTURING.value,
                        "heartbeat_at": utc_now(),
                        "updated_at": utc_now(),
                    }
                },
            )

            # 4. Stage 2: Entity Mention Extraction (Track 3)
            entities = self.entity_pipeline.process_evidence_text(evidence_text)

            # Update status to ANALYZING
            await db.evidence.update_one(
                {"evidence_id": job.evidence_id},
                {
                    "$set": {
                        "status": EvidenceStatus.ANALYZING.value,
                        "heartbeat_at": utc_now(),
                        "updated_at": utc_now(),
                    }
                },
            )

            # 5. Stage 3: Hybrid Event Cascade (Track 4B)
            validation_results = self.event_cascade.process_evidence(evidence_text, entities=entities)

            # 6. Versioned Event Staging
            staged_events: List[Dict[str, Any]] = []
            has_review_needed_events = False

            for res in validation_results:
                if res.event is None:
                    continue

                ev = res.event
                if res.decision_state == EnsembleDecisionState.REVIEW_NEEDED:
                    has_review_needed_events = True

                # Extract bounding box safely without fabrication
                bbox = None
                page_no = None
                if ev.source_reference:
                    bbox = ev.source_reference.bounding_box
                    page_no = ev.source_reference.page_number

                # Normalize amount safely
                amt_curr = ev.amount.currency if ev.amount else None
                amt_val = Decimal(str(ev.amount.value)) if ev.amount else None

                etype_val = getattr(ev.event_type, "value", str(ev.event_type))
                dstate_val = getattr(res.decision_state, "value", str(res.decision_state))
                pol_val = getattr(ev.polarity, "value", str(ev.polarity))
                mod_val = getattr(ev.modality, "value", str(ev.modality))
                tense_val = getattr(ev.tense, "value", str(ev.tense))

                event_doc = EventDocument(
                    event_id=ev.event_id,
                    case_id=job.case_id,
                    evidence_id=job.evidence_id,
                    user_id=job.user_id,
                    processing_version=target_version,
                    event_type=etype_val,
                    decision_state=dstate_val,
                    review_reasons=res.review_reasons,
                    trigger_raw_text=ev.trigger.raw_text if ev.trigger else ev.attributes.get("context_sentence", ""),
                    char_start=ev.trigger.char_start if ev.trigger else 0,
                    char_end=ev.trigger.char_end if ev.trigger else 0,
                    page_number=page_no,
                    bounding_box=bbox,
                    actor=ev.actor,
                    participants=ev.participants,
                    temporal_information=str(ev.temporal_information) if ev.temporal_information else None,
                    amount_currency=amt_curr,
                    amount_value=amt_val,
                    order_reference=ev.order_reference,
                    transaction_reference=ev.transaction_reference,
                    polarity=pol_val,
                    modality=mod_val,
                    tense=tense_val,
                    model_confidence=ev.confidence,
                    model_metadata=ev.model_metadata,
                )
                staged_events.append(event_doc.model_dump())

            # Commit staged events atomically
            if staged_events:
                await db.events.insert_many(staged_events)

            # Purge superseded older version events for this evidence asset only after success
            if target_version > current_version:
                await db.events.delete_many(
                    {
                        "evidence_id": job.evidence_id,
                        "processing_version": {"$lt": target_version},
                    }
                )

            # 7. Final status resolution
            q_state = getattr(evidence_text.overall_quality_state, "value", str(evidence_text.overall_quality_state))
            is_review_needed = (
                q_state == ExtractionQualityState.REVIEW_NEEDED.value
                or has_review_needed_events
            )
            final_status = EvidenceStatus.REVIEW_NEEDED if is_review_needed else EvidenceStatus.READY

            extraction_summary = {
                "page_count": len(evidence_text.pages),
                "character_count": len(evidence_text.full_raw_text),
                "quality_state": q_state,
                "entities_extracted": len(entities),
                "events_extracted": len(staged_events),
                "processing_version": target_version,
            }

            await db.evidence.update_one(
                {"evidence_id": job.evidence_id},
                {
                    "$set": {
                        "status": getattr(final_status, "value", str(final_status)),
                        "processing_mode": getattr(mode, "value", str(mode)),
                        "processing_version": target_version,
                        "extraction_summary": extraction_summary,
                        "heartbeat_at": utc_now(),
                        "updated_at": utc_now(),
                    }
                },
            )

            # Update parent case evidence counter if this was first successful run
            if claimed.get("status") in (EvidenceStatus.QUEUED.value, EvidenceStatus.UPLOADED.value):
                await db.cases.update_one(
                    {"case_id": job.case_id},
                    {"$inc": {"evidence_count": 1}, "$set": {"updated_at": utc_now()}},
                )

            logger.info(
                "Job %s completed for evidence %s: status=%s, mode=%s, events=%d",
                job.job_id,
                job.evidence_id,
                getattr(final_status, "value", str(final_status)),
                getattr(mode, "value", str(mode)),
                len(staged_events),
            )

        except Exception as exc:
            logger.error("Processing failure on evidence %s: %s", job.evidence_id, str(exc), exc_info=True)
            await db.evidence.update_one(
                {"evidence_id": job.evidence_id},
                {
                    "$set": {
                        "status": EvidenceStatus.FAILED.value,
                        "error_code": "EXTRACTION_FAILURE",
                        "error_message": "An error occurred during evidence text or event extraction.",
                        "heartbeat_at": utc_now(),
                        "updated_at": utc_now(),
                    }
                },
            )


evidence_processing_service = EvidenceProcessingService()

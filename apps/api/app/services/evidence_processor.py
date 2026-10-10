from datetime import datetime, timezone
from decimal import Decimal
import os
from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel, Field
from pymongo.asynchronous.database import AsyncDatabase

from app.core.logging import logger
from app.models.case import CaseStatus
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
            return MLProcessingMode.NEURAL_DEBERTA_CPU

        if hasattr(self.event_cascade, "_model") and self.event_cascade._model is not None and getattr(self.event_cascade, "_device", None) is not None:
            if self.event_cascade._device.type == "cuda":
                return MLProcessingMode.NEURAL_DEBERTA_GPU
            return MLProcessingMode.NEURAL_DEBERTA_CPU

        reason = getattr(
            self.event_cascade,
            "fallback_reason",
            "Neural checkpoint or PyTorch/Transformers runtime unavailable.",
        )
        logger.info("ML runtime running in DETERMINISTIC_FALLBACK mode: %s", reason)
        return MLProcessingMode.DETERMINISTIC_FALLBACK

    async def sync_case_state(self, case_id: str, db: AsyncDatabase) -> None:
        """Recalculates evidence counts and resolves parent case status based on all case evidence items."""
        cursor = db.evidence.find({"case_id": case_id})
        all_evidence = []
        async for doc in cursor:
            all_evidence.append(doc)

        if not all_evidence:
            await db.cases.update_one(
                {"case_id": case_id},
                {"$set": {"evidence_count": 0, "status": CaseStatus.READY.value, "updated_at": utc_now()}},
            )
            return

        evidence_count = len(all_evidence)

        in_flight_statuses = {
            EvidenceStatus.QUEUED.value,
            EvidenceStatus.EXTRACTING.value,
            EvidenceStatus.STRUCTURING.value,
            EvidenceStatus.ANALYZING.value,
        }
        review_or_failed_statuses = {
            EvidenceStatus.REVIEW_NEEDED.value,
            EvidenceStatus.FAILED.value,
            EvidenceStatus.INTERRUPTED.value,
        }

        statuses = [e.get("status") for e in all_evidence]
        if any(s in in_flight_statuses for s in statuses):
            resolved_case_status = CaseStatus.PROCESSING.value
        elif any(s in review_or_failed_statuses for s in statuses):
            resolved_case_status = CaseStatus.REVIEW_NEEDED.value
        else:
            resolved_case_status = CaseStatus.READY.value

        await db.cases.update_one(
            {"case_id": case_id},
            {
                "$set": {
                    "evidence_count": evidence_count,
                    "status": resolved_case_status,
                    "updated_at": utc_now(),
                }
            },
        )

    async def run_job(self, job: ProcessingJob, db: AsyncDatabase) -> None:
        """Executes full document extraction, entity normalization, and event extraction."""
        # 1. Unique run identifier and atomic state claim
        run_id = f"run_{uuid.uuid4().hex[:20]}"
        claimed = await db.evidence.find_one_and_update(
            {
                "evidence_id": job.evidence_id,
                "status": {
                    "$in": [
                        EvidenceStatus.QUEUED.value,
                        EvidenceStatus.FAILED.value,
                        EvidenceStatus.INTERRUPTED.value,
                        EvidenceStatus.REVIEW_NEEDED.value,
                    ]
                },
            },
            {
                "$set": {
                    "status": EvidenceStatus.EXTRACTING.value,
                    "job_id": job.job_id,
                    "current_run_id": run_id,
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

        prior_active_version = claimed.get("active_processing_version")
        target_version = (prior_active_version + 1) if prior_active_version is not None else 1
        mode = self.detect_processing_mode()

        activation_committed = False
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
                {"evidence_id": job.evidence_id, "current_run_id": run_id},
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
                {"evidence_id": job.evidence_id, "current_run_id": run_id},
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
                    processing_run_id=run_id,
                    is_active=True,
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
                    )
                doc_dict = event_doc.model_dump()
                if doc_dict.get("amount_value") is not None:
                    from bson import Decimal128
                    doc_dict["amount_value"] = Decimal128(str(doc_dict["amount_value"]))
                staged_events.append(doc_dict)

            # 1. Commit staged events under unique run_id and target_version
            if staged_events:
                await db.events.insert_many(staged_events)

            # 2. Final status resolution
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

            if not staged_events:
                raw_text_stripped = evidence_text.full_raw_text.strip()
                if not raw_text_stripped:
                    diagnostic = "Document text is empty; no textual content available for event extraction."
                else:
                    from ml.events.detector import DISCLAIMER_PATTERNS
                    import re

                    has_disclaimer = any(
                        re.search(pat, raw_text_stripped.lower())
                        for pat in DISCLAIMER_PATTERNS
                    )
                    if has_disclaimer:
                        diagnostic = (
                            "Document text consists of non-affirmative disclaimers or simulated statements; "
                            "no validated real-world lifecycle events were asserted."
                        )
                    else:
                        diagnostic = (
                            "No recognized event triggers or verifiable business action statements identified in source text."
                        )
                extraction_summary["diagnostic"] = diagnostic

            # 3. Atomically switch evidence document's active version conditioned on ownership and expected prior version
            version_filter = {"$in": [None, 0]} if prior_active_version is None else prior_active_version
            switch_filter = {
                "evidence_id": job.evidence_id,
                "current_run_id": run_id,
                "active_processing_version": version_filter,
            }
            switch_update = {
                "$set": {
                    "active_processing_version": target_version,
                    "processing_version": target_version,
                    "status": getattr(final_status, "value", str(final_status)),
                    "processing_mode": getattr(mode, "value", str(mode)),
                    "extraction_summary": extraction_summary,
                    "heartbeat_at": utc_now(),
                    "updated_at": utc_now(),
                }
            }
            switch_res = await db.evidence.update_one(switch_filter, switch_update)
            if switch_res.modified_count == 0:
                # Pointer switch failed: rollback staged events for this run
                if staged_events:
                    await db.events.delete_many(
                        {"evidence_id": job.evidence_id, "processing_run_id": run_id}
                    )
                raise RuntimeError(
                    f"Atomic pointer switch failed for evidence {job.evidence_id} run {run_id}"
                )

            # Mark activation as committed: subsequent maintenance tasks cannot invalidate this run
            activation_committed = True

            # 4. Old-version cleanup is a recoverable maintenance task.
            # Failure must never roll back newly active events or mark an active run as failed.
            try:
                await db.events.delete_many(
                    {
                        "evidence_id": job.evidence_id,
                        "processing_version": {"$lt": target_version},
                    }
                )
            except Exception as cleanup_err:
                logger.warning(
                    "Recoverable maintenance warning: Failed to purge superseded events for evidence %s: %s",
                    job.evidence_id,
                    str(cleanup_err),
                )

            # Idempotently sync case evidence counter and status
            try:
                await self.sync_case_state(job.case_id, db)
            except Exception as case_err:
                logger.warning("Non-fatal case state sync warning for evidence %s: %s", job.evidence_id, str(case_err))

            logger.info(
                "Job %s completed for evidence %s: status=%s, mode=%s, events=%d, active_version=%d",
                job.job_id,
                job.evidence_id,
                getattr(final_status, "value", str(final_status)),
                getattr(mode, "value", str(mode)),
                len(staged_events),
                target_version,
            )

        except Exception as exc:
            if activation_committed:
                # Activation has already committed successfully!
                # Never roll back active events or mark the document as FAILED.
                logger.warning(
                    "Post-activation maintenance warning for evidence %s run %s: %s",
                    job.evidence_id,
                    run_id,
                    str(exc),
                )
                return

            logger.error(
                "Processing failure on evidence %s run %s before activation: %s",
                job.evidence_id,
                run_id,
                str(exc),
                exc_info=True,
            )
            # Safe rollback: purge staged events ONLY for this specific run_id
            try:
                await db.events.delete_many(
                    {"evidence_id": job.evidence_id, "processing_run_id": run_id}
                )
            except Exception as rollback_err:
                logger.warning("Failed to clean up staged events on error: %s", str(rollback_err))

            await db.evidence.update_one(
                {
                    "evidence_id": job.evidence_id,
                    "current_run_id": run_id,
                },
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
            try:
                await self.sync_case_state(job.case_id, db)
            except Exception as case_err:
                logger.warning("Non-fatal case state sync warning after failure for evidence %s: %s", job.evidence_id, str(case_err))

    async def recover_interrupted_jobs(
        self,
        db: AsyncDatabase,
        timeout_seconds: int = 300,
    ) -> int:
        """Scans for in-flight jobs exceeding heartbeat timeout, atomically claims them, and cleans up uncommitted staged events."""
        from datetime import timedelta

        cutoff = utc_now() - timedelta(seconds=timeout_seconds)
        cursor = db.evidence.find(
            {
                "status": {
                    "$in": [
                        EvidenceStatus.EXTRACTING.value,
                        EvidenceStatus.STRUCTURING.value,
                        EvidenceStatus.ANALYZING.value,
                    ]
                },
                "heartbeat_at": {"$lt": cutoff},
            }
        )
        recovered_count = 0
        async for doc in cursor:
            evi_id = doc["evidence_id"]
            stale_run_id = doc.get("current_run_id")

            # Conditional atomic claim of stale job:
            claim_filter: Dict[str, Any] = {
                "evidence_id": evi_id,
                "status": doc["status"],
                "heartbeat_at": doc["heartbeat_at"],
            }
            if stale_run_id:
                claim_filter["current_run_id"] = stale_run_id

            claim_update = {
                "$set": {
                    "status": EvidenceStatus.INTERRUPTED.value,
                    "error_code": "JOB_INTERRUPTED",
                    "error_message": f"Processing heartbeat timed out after {timeout_seconds}s.",
                    "updated_at": utc_now(),
                }
            }
            claim_res = await db.evidence.update_one(claim_filter, claim_update)
            if claim_res.modified_count == 1:
                # Successfully claimed: delete staged events ONLY for the specific stale run being recovered
                if stale_run_id:
                    await db.events.delete_many(
                        {"evidence_id": evi_id, "processing_run_id": stale_run_id}
                    )
                else:
                    await db.events.delete_many(
                        {"evidence_id": evi_id, "processing_version": {"$ne": doc.get("active_processing_version")}}
                    )
                recovered_count += 1
                logger.warning("Recovered interrupted job for evidence %s run %s", evi_id, stale_run_id)
        return recovered_count


evidence_processing_service = EvidenceProcessingService()

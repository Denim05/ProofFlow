import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import HTTPException, status
from pymongo.asynchronous.database import AsyncDatabase

from app.schemas.review import (
    FindingReviewCreateRequest,
    FindingReviewHistoryResponse,
    FindingReviewListResponse,
    FindingReviewResponse,
    ReviewDecision,
)
from app.services.finding_service import FindingService


async def verify_case_ownership(case_id: str, user_id: str, db: AsyncDatabase) -> Dict[str, Any]:
    """Verifies that the target case exists and belongs strictly to the authenticated tenant."""
    case_row = await db.cases.find_one({"case_id": case_id, "user_id": user_id})
    if not case_row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case '{case_id}' was not found",
        )
    return case_row


class ReviewService:
    """Service handling finding reviews, human-in-the-loop adjudications, and audit history."""

    @staticmethod
    async def record_finding_review(
        case_id: str,
        finding_id: str,
        reviewer_id: str,
        request: FindingReviewCreateRequest,
        db: AsyncDatabase,
    ) -> FindingReviewResponse:
        """Records an adjudication decision for a case finding.

        Invariants:
        1. Reviewer identity is derived from authenticated server-side principal.
        2. Case ownership / tenant isolation is enforced.
        3. Finding must belong to the case (active ML finding or existing case review record).
        4. Dismissal requires non-empty reason.
        5. Repeated identical submissions are idempotent (no duplicate active records).
        6. Revisions preserve decision history by marking prior records inactive and incrementing version.
        7. ML confidence scores and extractions are never mutated.
        """
        # 1. Enforce tenant isolation on case
        await verify_case_ownership(case_id=case_id, user_id=reviewer_id, db=db)

        # 2. Validate that finding belongs to the case
        current_findings = await FindingService.compute_case_findings(
            case_id=case_id,
            user_id=reviewer_id,
            db=db,
        )
        is_active_ml_finding = any(f.finding_id == finding_id for f in current_findings.items)

        existing_case_review = await db.finding_reviews.find_one(
            {"case_id": case_id, "finding_id": finding_id}
        )

        if not is_active_ml_finding and not existing_case_review:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Finding '{finding_id}' was not found in case '{case_id}'",
            )

        now = datetime.now(timezone.utc)
        normalized_reason = request.reason.strip() if request.reason else None

        # 3. Defensive check: dismissal must contain reason
        if request.decision == ReviewDecision.DISMISSED and not normalized_reason:
            raise HTTPException(
                status_code=422,
                detail="A meaningful dismissal reason is mandatory when dismissing a finding.",
            )

        # 4. Check for active review on this (case_id, finding_id)
        active_rev = await db.finding_reviews.find_one(
            {"case_id": case_id, "finding_id": finding_id, "is_active": True}
        )

        if active_rev:
            # Idempotency check: identical decision and reason
            if (
                active_rev.get("decision") == request.decision.value
                and active_rev.get("reason") == normalized_reason
            ):
                return FindingReviewResponse(
                    review_id=active_rev["review_id"],
                    case_id=active_rev["case_id"],
                    finding_id=active_rev["finding_id"],
                    reviewer_id=active_rev["reviewer_id"],
                    decision=ReviewDecision(active_rev["decision"]),
                    reason=active_rev.get("reason"),
                    version=active_rev.get("version", 1),
                    is_active=True,
                    created_at=active_rev["created_at"],
                    updated_at=active_rev["updated_at"],
                )

            # Decision or reason changed: supersede previous active records
            await db.finding_reviews.update_many(
                {"case_id": case_id, "finding_id": finding_id, "is_active": True},
                {"$set": {"is_active": False, "updated_at": now}},
            )
            next_version = active_rev.get("version", 1) + 1
        else:
            # First decision or recovering from previous inactive history
            past_reviews_cursor = db.finding_reviews.find(
                {"case_id": case_id, "finding_id": finding_id}
            ).sort([("version", -1)])
            highest_ver = 0
            async for past_r in past_reviews_cursor:
                v = past_r.get("version", 0)
                if v > highest_ver:
                    highest_ver = v
            next_version = highest_ver + 1

        review_id = f"rev_{uuid.uuid4().hex[:16]}"
        new_doc = {
            "review_id": review_id,
            "case_id": case_id,
            "finding_id": finding_id,
            "user_id": reviewer_id,
            "reviewer_id": reviewer_id,
            "decision": request.decision.value,
            "reason": normalized_reason,
            "version": next_version,
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        }

        await db.finding_reviews.insert_one(new_doc)

        return FindingReviewResponse(
            review_id=review_id,
            case_id=case_id,
            finding_id=finding_id,
            reviewer_id=reviewer_id,
            decision=request.decision,
            reason=normalized_reason,
            version=next_version,
            is_active=True,
            created_at=now,
            updated_at=now,
        )

    @staticmethod
    async def list_case_reviews(
        case_id: str,
        user_id: str,
        db: AsyncDatabase,
    ) -> FindingReviewListResponse:
        """Lists active and historical review records for a case."""
        await verify_case_ownership(case_id=case_id, user_id=user_id, db=db)

        cursor = db.finding_reviews.find(
            {"case_id": case_id, "is_active": True}
        ).sort([("created_at", -1)])

        items: List[FindingReviewResponse] = []
        async for doc in cursor:
            items.append(
                FindingReviewResponse(
                    review_id=doc["review_id"],
                    case_id=doc["case_id"],
                    finding_id=doc["finding_id"],
                    reviewer_id=doc["reviewer_id"],
                    decision=ReviewDecision(doc["decision"]),
                    reason=doc.get("reason"),
                    version=doc.get("version", 1),
                    is_active=doc.get("is_active", True),
                    created_at=doc["created_at"],
                    updated_at=doc["updated_at"],
                )
            )

        return FindingReviewListResponse(
            items=items,
            total=len(items),
            case_id=case_id,
        )

    @staticmethod
    async def get_finding_review_history(
        case_id: str,
        finding_id: str,
        user_id: str,
        db: AsyncDatabase,
    ) -> FindingReviewHistoryResponse:
        """Retrieves complete decision history for a specific finding."""
        await verify_case_ownership(case_id=case_id, user_id=user_id, db=db)

        # Validate that the finding belongs to this case
        current_findings = await FindingService.compute_case_findings(
            case_id=case_id,
            user_id=user_id,
            db=db,
        )
        is_active_ml_finding = any(f.finding_id == finding_id for f in current_findings.items)

        cursor = db.finding_reviews.find(
            {"case_id": case_id, "finding_id": finding_id}
        ).sort([("version", -1), ("created_at", -1)])

        items: List[FindingReviewResponse] = []
        async for doc in cursor:
            items.append(
                FindingReviewResponse(
                    review_id=doc["review_id"],
                    case_id=doc["case_id"],
                    finding_id=doc["finding_id"],
                    reviewer_id=doc["reviewer_id"],
                    decision=ReviewDecision(doc["decision"]),
                    reason=doc.get("reason"),
                    version=doc.get("version", 1),
                    is_active=doc.get("is_active", True),
                    created_at=doc["created_at"],
                    updated_at=doc["updated_at"],
                )
            )

        if not items and not is_active_ml_finding:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Finding '{finding_id}' was not found in case '{case_id}'",
            )

        return FindingReviewHistoryResponse(
            items=items,
            total=len(items),
            finding_id=finding_id,
            case_id=case_id,
        )

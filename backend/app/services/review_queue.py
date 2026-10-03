"""
Review Queue Service — full inspection audit trail with supervisor visibility.

Purpose:
    All completed inspections (PASS, FAIL, REVIEW) are routed here so supervisors
    can see every inspection and optionally override AI decisions.
    RETAKE is excluded as it is an image quality issue, not a product decision.

Policy (documented):
    - PASS, FAIL, and REVIEW decisions all create a pending review record.
    - Image quality failures (Decision.RETAKE) do NOT enter the queue.
    - A review record is created ONCE per inspection (unique FK on inspection_id).
    - Supervisor can: ACCEPT (human_decision=PASS) or REJECT (human_decision=FAIL).
    - The original AI decision is always preserved in ai_decision for auditability.
    - Analytics operational reject rate should use human_decision once reviewed,
      while retaining ai_decision for auditability.

Final decision policy for analytics:
    - If review_status = 'pending': use ai_decision
    - If review_status = 'accepted': human_decision = PASS
    - If review_status = 'rejected': human_decision = FAIL
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.db.models import (
    Inspection, InspectionReview, Decision, ReviewStatus,
    OperationalSeverity, QualityCheckStatus
)
from app.core.logging import get_logger

logger = get_logger(__name__)


async def maybe_enqueue_review(
    inspection_id: uuid.UUID,
    ai_decision: Decision,
    db: AsyncSession,
) -> Optional[InspectionReview]:
    """
    Enqueue any completed inspection (PASS, FAIL, REVIEW) for supervisor visibility.

    Policy:
    - RETAKE decisions are NOT enqueued — they are image quality issues,
      not product quality issues.
    - All other decisions (PASS, FAIL, REVIEW) create a pending review record.
    - This is idempotent: if a record already exists, returns the existing record.

    Returns the created/existing InspectionReview or None if not queued.
    """
    if ai_decision == Decision.RETAKE:
        return None

    # Check for existing record (idempotent)
    existing = await db.execute(
        select(InspectionReview).where(InspectionReview.inspection_id == inspection_id)
    )
    existing_review = existing.scalar_one_or_none()
    if existing_review is not None:
        logger.debug(f"[ReviewQueue] Review already exists for inspection {inspection_id}")
        return existing_review

    review = InspectionReview(
        id=uuid.uuid4(),
        inspection_id=inspection_id,
        ai_decision=ai_decision,
        review_status=ReviewStatus.pending,
        queued_at=datetime.utcnow(),
    )
    db.add(review)
    logger.info(f"[ReviewQueue] Enqueued inspection {inspection_id} (decision={ai_decision.value}) for supervisor review")
    return review


async def submit_review_decision(
    inspection_id: uuid.UUID,
    action: str,
    note: Optional[str],
    db: AsyncSession,
) -> InspectionReview:
    """
    Record a supervisor's Accept or Reject decision.

    action: 'accept' → human_decision=PASS, review_status=accepted
            'reject' → human_decision=FAIL, review_status=rejected

    Raises ValueError for unknown actions or already-reviewed inspections.
    Raises LookupError if no review record exists.
    """
    result = await db.execute(
        select(InspectionReview).where(InspectionReview.inspection_id == inspection_id)
    )
    review = result.scalar_one_or_none()
    if review is None:
        raise LookupError(f"No review record found for inspection {inspection_id}")

    # Duplicate action handling: if already reviewed, return existing state
    # rather than raising a hard error — idempotent from supervisor perspective.
    if review.review_status != ReviewStatus.pending:
        logger.info(
            f"[ReviewQueue] Inspection {inspection_id} already reviewed "
            f"({review.review_status}); ignoring duplicate action"
        )
        return review

    action_lower = action.lower().strip()
    if action_lower in ("accept", "accepted"):
        review.human_decision = Decision.PASS
        review.review_status = ReviewStatus.accepted
    elif action_lower in ("reject", "rejected"):
        review.human_decision = Decision.FAIL
        review.review_status = ReviewStatus.rejected
    else:
        raise ValueError(f"Unknown review action '{action}'. Use 'accept' or 'reject'.")

    review.reviewed_at = datetime.utcnow()
    if note:
        review.note = note[:1000]  # cap length

    logger.info(
        f"[ReviewQueue] Inspection {inspection_id} reviewed: "
        f"action={action_lower} human_decision={review.human_decision}"
    )
    return review


async def get_pending_reviews(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    product_id: Optional[str] = None,
) -> dict:
    """
    Return paginated pending review records with inspection details.
    """
    from sqlalchemy.orm import selectinload

    conditions = [InspectionReview.review_status == ReviewStatus.pending]

    # Count
    count_q = select(func.count(InspectionReview.id)).where(*conditions)
    total = (await db.execute(count_q)).scalar() or 0

    # Fetch with inspection eagerly loaded
    q = (
        select(InspectionReview)
        .options(
            selectinload(InspectionReview.inspection).selectinload(Inspection.product),
            selectinload(InspectionReview.inspection).selectinload(Inspection.defects),
        )
        .where(*conditions)
        .order_by(InspectionReview.queued_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    rows = (await db.execute(q)).scalars().all()
    return {
        "items": rows,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": ((total - 1) // page_size + 1) if total > 0 else 1,
    }

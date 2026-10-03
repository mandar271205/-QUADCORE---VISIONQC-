"""
Review Queue API endpoints.

Supervisor-facing endpoints for human-in-the-loop review of REVIEW-decision inspections.

Endpoints:
    GET  /reviews              - List pending reviews (paginated)
    GET  /reviews/{id}         - Get single review by inspection_id
    POST /reviews/{id}/decision - Submit Accept or Reject decision
    GET  /reviews/count        - Count of pending reviews (for dashboard badge)

IMPORTANT: No provider/engine details are exposed in any response.
"""
import uuid
import json
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from pydantic import BaseModel

from app.db.session import get_db
from app.db.models import (
    Inspection, InspectionReview, Decision, ReviewStatus,
    OperationalSeverity, QualityCheckStatus
)
from app.services.review_queue import (
    get_pending_reviews, submit_review_decision
)
from app.core.logging import get_logger

router = APIRouter()
logger = get_logger(__name__)


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class ReviewDecisionRequest(BaseModel):
    action: str                 # 'accept' or 'reject'
    note: Optional[str] = None  # optional supervisor note


class ReviewProductSummary(BaseModel):
    id: str
    name: str


class ReviewDefectSummary(BaseModel):
    type: str
    description: Optional[str] = None
    severity: str


class PendingReviewItem(BaseModel):
    review_id: str
    inspection_id: str
    queued_at: datetime
    product: Optional[ReviewProductSummary] = None
    # AI decision information
    ai_decision: Decision
    anomaly_score: float
    confidence: float
    threshold: float
    operational_severity: OperationalSeverity
    heatmap_url: Optional[str] = None
    original_image_url: Optional[str] = None
    conformity_summary: Optional[str] = None
    defects: List[ReviewDefectSummary] = []
    quality_check_status: QualityCheckStatus = QualityCheckStatus.not_run
    quality_message: Optional[str] = None
    batch_id: Optional[str] = None
    shift: Optional[str] = None
    # Review state
    review_status: ReviewStatus
    reviewed_at: Optional[datetime] = None
    human_decision: Optional[Decision] = None
    note: Optional[str] = None


class PendingReviewListResponse(BaseModel):
    items: List[PendingReviewItem]
    total: int
    page: int
    page_size: int
    total_pages: int


class ReviewCountResponse(BaseModel):
    pending: int


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/count", response_model=ReviewCountResponse)
async def get_review_count(db: AsyncSession = Depends(get_db)):
    """Get count of pending reviews — for dashboard badge."""
    result = await db.execute(
        select(func.count(InspectionReview.id))
        .where(InspectionReview.review_status == ReviewStatus.pending)
    )
    count = result.scalar() or 0
    return ReviewCountResponse(pending=count)


@router.get("", response_model=PendingReviewListResponse)
async def list_reviews(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None, description="pending|accepted|rejected"),
    db: AsyncSession = Depends(get_db),
):
    """List reviews with full inspection context."""
    conditions = []
    if status:
        try:
            conditions.append(InspectionReview.review_status == ReviewStatus(status))
        except ValueError:
            pass
    else:
        conditions.append(InspectionReview.review_status == ReviewStatus.pending)

    # Count
    count_q = select(func.count(InspectionReview.id))
    if conditions:
        count_q = count_q.where(*conditions)
    total = (await db.execute(count_q)).scalar() or 0

    # Fetch with inspection eager-loaded
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

    items = []
    for rev in rows:
        insp = rev.inspection
        if not insp:
            continue

        # Parse quality issues
        quality_message = None
        raw_qi = getattr(insp, 'quality_issues', None)
        if raw_qi:
            try:
                issues = json.loads(raw_qi)
                if issues:
                    quality_message = f"Image quality issues: {', '.join(issues)}"
            except Exception:
                pass

        defect_list = []
        for d in (insp.defects or []):
            defect_list.append(ReviewDefectSummary(
                type=d.type,
                description=d.description,
                severity=d.severity.value if hasattr(d.severity, 'value') else str(d.severity),
            ))

        items.append(PendingReviewItem(
            review_id=str(rev.id),
            inspection_id=str(rev.inspection_id),
            queued_at=rev.queued_at,
            product=ReviewProductSummary(
                id=str(insp.product.id),
                name=insp.product.name,
            ) if insp.product else None,
            ai_decision=rev.ai_decision,
            anomaly_score=insp.anomaly_score,
            confidence=insp.confidence,
            threshold=insp.threshold,
            operational_severity=getattr(insp, 'operational_severity', OperationalSeverity.UNKNOWN),
            heatmap_url=insp.heatmap_url,
            original_image_url=insp.original_image_url,
            conformity_summary=getattr(insp, 'conformity_summary', None),
            defects=defect_list,
            quality_check_status=getattr(insp, 'quality_check_status', QualityCheckStatus.not_run),
            quality_message=quality_message,
            batch_id=getattr(insp, 'batch_id', None),
            shift=getattr(insp, 'shift', None),
            review_status=rev.review_status,
            reviewed_at=rev.reviewed_at,
            human_decision=rev.human_decision,
            note=rev.note,
        ))

    return PendingReviewListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=((total - 1) // page_size + 1) if total > 0 else 1,
    )


@router.post("/{inspection_id}/decision", response_model=PendingReviewItem)
async def submit_review(
    inspection_id: uuid.UUID,
    body: ReviewDecisionRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Submit a supervisor review decision for an inspection.

    action: 'accept' → PASS (product is OK)
            'reject' → FAIL (product should be rejected)
    """
    try:
        review = await submit_review_decision(inspection_id, body.action, body.note, db)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    await db.commit()
    await db.refresh(review)

    # Reload with inspection
    result = await db.execute(
        select(InspectionReview)
        .options(
            selectinload(InspectionReview.inspection).selectinload(Inspection.product),
            selectinload(InspectionReview.inspection).selectinload(Inspection.defects),
        )
        .where(InspectionReview.inspection_id == inspection_id)
    )
    rev = result.scalar_one_or_none()
    if not rev:
        raise HTTPException(status_code=404, detail="Review not found after commit.")

    insp = rev.inspection
    return PendingReviewItem(
        review_id=str(rev.id),
        inspection_id=str(rev.inspection_id),
        queued_at=rev.queued_at,
        product=ReviewProductSummary(
            id=str(insp.product.id),
            name=insp.product.name,
        ) if insp and insp.product else None,
        ai_decision=rev.ai_decision,
        anomaly_score=insp.anomaly_score if insp else 0.0,
        confidence=insp.confidence if insp else 0.0,
        threshold=insp.threshold if insp else 0.55,
        operational_severity=getattr(insp, 'operational_severity', OperationalSeverity.UNKNOWN) if insp else OperationalSeverity.UNKNOWN,
        heatmap_url=insp.heatmap_url if insp else None,
        original_image_url=insp.original_image_url if insp else None,
        conformity_summary=getattr(insp, 'conformity_summary', None) if insp else None,
        defects=[
            ReviewDefectSummary(
                type=d.type,
                description=d.description,
                severity=d.severity.value if hasattr(d.severity, 'value') else str(d.severity),
            )
            for d in (insp.defects or [])
        ] if insp else [],
        review_status=rev.review_status,
        reviewed_at=rev.reviewed_at,
        human_decision=rev.human_decision,
        note=rev.note,
    )

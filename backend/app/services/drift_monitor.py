"""
Drift Monitoring Service — detects when production observations increasingly differ
from the established product baseline.

CRITICAL PRINCIPLES:
    1. Drift does NOT auto-retrain. Drift suspicion must be reviewed by a supervisor.
    2. Minimum evidence required: MIN_INSPECTIONS_FOR_DRIFT before non-Stable
       status is reported.
    3. We do NOT compare against a "true normal" distribution (no ML drift detector).
       We use operational metrics — rejection rate, average anomaly score, review rate —
       to detect statistical divergence from the product's own historical baseline.

Documented policy:

    Drift status is computed over the RECENT window (default: last 7 days)
    compared to a BASELINE window (prior 30 days).

    Each signal is marked as "worsening" if it exceeds a relative tolerance:
        - rejection_rate:      recent > baseline * 1.5 AND increase > 0.05 absolute
        - average_anomaly_score: recent > baseline + 0.10 absolute
        - review_rate:         recent > baseline * 1.5 AND increase > 0.05 absolute
        - override_rate:       recent > baseline * 1.5 AND increase > 0.05 absolute
          (override rate = inspections where human overrode AI / all reviewed)

    Final status:
        worsening_count = 0:            Stable
        worsening_count in [1, 2]:      Watch
        worsening_count >= 3
          OR rejection_rate > 2× baseline: DriftSuspected

    Minimum evidence guard:
        recent_inspection_count < MIN_INSPECTIONS_FOR_DRIFT → Stable
        (not enough data; do NOT raise false alarms)

    Drift DOES NOT retrain automatically. The supervisor must:
        1. Review drift alert
        2. Collect/verify new GOOD references
        3. Run Learn Normal
        4. Activate new profile version
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, date, timedelta
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case

from app.db.models import (
    Inspection, InspectionReview, Decision, DriftSnapshot, ReviewStatus
)
from app.core.logging import get_logger

logger = get_logger(__name__)

# Documented thresholds
MIN_INSPECTIONS_FOR_DRIFT = 20      # minimum recent inspections before non-Stable report
RECENT_WINDOW_DAYS = 7              # recent period
BASELINE_WINDOW_DAYS = 30           # baseline period (must be > recent)
REJECTION_RATE_RELATIVE_FACTOR = 1.5   # recent must be 1.5× baseline
REJECTION_RATE_ABSOLUTE_MIN = 0.05    # must also increase by at least 5pp
ANOMALY_SCORE_ABSOLUTE_DELTA = 0.10   # absolute increase in avg anomaly score
REVIEW_RATE_RELATIVE_FACTOR = 1.5
REVIEW_RATE_ABSOLUTE_MIN = 0.05
OVERRIDE_RATE_RELATIVE_FACTOR = 1.5
OVERRIDE_RATE_ABSOLUTE_MIN = 0.05
DRIFT_SUSPECTED_THRESHOLD = 3           # worsening signals needed for DriftSuspected
DRIFT_SEVERE_REJECTION_FACTOR = 2.0    # rejection 2× baseline → DriftSuspected immediately


async def compute_drift(
    product_id: uuid.UUID,
    db: AsyncSession,
    window_days: int = RECENT_WINDOW_DAYS,
    baseline_days: int = BASELINE_WINDOW_DAYS,
) -> DriftSnapshot:
    """
    Compute drift status for a product and persist a snapshot.

    Returns the newly stored DriftSnapshot.
    """
    now = datetime.utcnow()
    recent_start = now - timedelta(days=window_days)
    baseline_start = now - timedelta(days=baseline_days)

    # ── Fetch recent metrics ────────────────────────────────────────────────
    recent_metrics = await _get_inspection_metrics(
        product_id, recent_start, now, db
    )
    baseline_metrics = await _get_inspection_metrics(
        product_id, baseline_start, recent_start, db
    )

    recent_count = recent_metrics["count"]
    worsening_signals: list[str] = []

    # Guard: minimum evidence
    if recent_count < MIN_INSPECTIONS_FOR_DRIFT:
        drift_status = "stable"
        logger.info(
            f"[Drift] Product {product_id}: recent_count={recent_count} < "
            f"{MIN_INSPECTIONS_FOR_DRIFT} → Stable (insufficient data)"
        )
    else:
        # ── Compare signals ────────────────────────────────────────────────
        worsening_signals = _find_worsening_signals(recent_metrics, baseline_metrics)

        # Determine status
        n_worsening = len(worsening_signals)
        r_reject = recent_metrics["rejection_rate"]
        b_reject = baseline_metrics["rejection_rate"]
        severe_rejection = b_reject > 0 and r_reject > b_reject * DRIFT_SEVERE_REJECTION_FACTOR

        if n_worsening >= DRIFT_SUSPECTED_THRESHOLD or severe_rejection:
            drift_status = "drift_suspected"
        elif n_worsening >= 1:
            drift_status = "watch"
        else:
            drift_status = "stable"

        logger.info(
            f"[Drift] Product {product_id}: status={drift_status} "
            f"worsening={worsening_signals} recent_count={recent_count}"
        )

    snapshot = DriftSnapshot(
        id=uuid.uuid4(),
        product_id=product_id,
        computed_at=now,
        window_days=window_days,
        inspection_count=recent_count,
        rejection_rate=recent_metrics["rejection_rate"],
        average_anomaly_score=recent_metrics["avg_anomaly_score"],
        review_rate=recent_metrics["review_rate"],
        override_rate=recent_metrics["override_rate"],
        drift_status=drift_status,
        worsening_signals=json.dumps(worsening_signals) if worsening_signals else None,
    )
    db.add(snapshot)
    await db.commit()
    await db.refresh(snapshot)
    return snapshot


async def get_latest_drift(
    product_id: uuid.UUID,
    db: AsyncSession,
) -> Optional[DriftSnapshot]:
    """Return the most recent drift snapshot for a product."""
    result = await db.execute(
        select(DriftSnapshot)
        .where(DriftSnapshot.product_id == product_id)
        .order_by(DriftSnapshot.computed_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_all_drift_status(db: AsyncSession) -> list[dict]:
    """
    Return the latest drift status for all products that have a snapshot.
    Used for dashboard 'Products to Watch' card.
    """
    # Get max computed_at per product
    subq = (
        select(
            DriftSnapshot.product_id,
            func.max(DriftSnapshot.computed_at).label("max_at"),
        )
        .group_by(DriftSnapshot.product_id)
        .subquery()
    )
    result = await db.execute(
        select(DriftSnapshot)
        .join(
            subq,
            (DriftSnapshot.product_id == subq.c.product_id)
            & (DriftSnapshot.computed_at == subq.c.max_at),
        )
        .where(DriftSnapshot.drift_status != "stable")
    )
    rows = result.scalars().all()
    return [
        {
            "product_id": str(r.product_id),
            "drift_status": r.drift_status,
            "computed_at": r.computed_at.isoformat(),
            "worsening_signals": json.loads(r.worsening_signals) if r.worsening_signals else [],
            "inspection_count": r.inspection_count,
            "rejection_rate": r.rejection_rate,
        }
        for r in rows
    ]


# ── Private helpers ────────────────────────────────────────────────────────────


async def _get_inspection_metrics(
    product_id: uuid.UUID,
    start: datetime,
    end: datetime,
    db: AsyncSession,
) -> dict:
    """Compute operational metrics for a product in a time window."""
    insp_result = await db.execute(
        select(
            func.count(Inspection.id).label("total"),
            func.sum(case((Inspection.decision == Decision.FAIL, 1), else_=0)).label("failed"),
            func.sum(case((Inspection.decision == Decision.REVIEW, 1), else_=0)).label("review"),
            func.avg(Inspection.anomaly_score).label("avg_score"),
        ).where(
            Inspection.product_id == product_id,
            Inspection.created_at >= start,
            Inspection.created_at < end,
            # Exclude RETAKE decisions from product metrics
            Inspection.decision != Decision.RETAKE,
        )
    )
    row = insp_result.first()
    total = int(row.total or 0)
    failed = int(row.failed or 0)
    review = int(row.review or 0)
    avg_score = float(row.avg_score or 0.0)

    rejection_rate = failed / total if total > 0 else 0.0
    review_rate = review / total if total > 0 else 0.0

    # Override rate: reviewed inspections where human disagreed with AI
    override_result = await db.execute(
        select(
            func.count(InspectionReview.id).label("reviewed"),
            func.sum(
                case(
                    (InspectionReview.human_decision != InspectionReview.ai_decision, 1),
                    else_=0,
                )
            ).label("overridden"),
        )
        .join(Inspection, InspectionReview.inspection_id == Inspection.id)
        .where(
            Inspection.product_id == product_id,
            Inspection.created_at >= start,
            Inspection.created_at < end,
            InspectionReview.review_status != ReviewStatus.pending,
        )
    )
    or_row = override_result.first()
    reviewed = int(or_row.reviewed or 0)
    overridden = int(or_row.overridden or 0)
    override_rate = overridden / reviewed if reviewed > 0 else 0.0

    return {
        "count": total,
        "rejection_rate": round(rejection_rate, 4),
        "avg_anomaly_score": round(avg_score, 4),
        "review_rate": round(review_rate, 4),
        "override_rate": round(override_rate, 4),
    }


def _find_worsening_signals(recent: dict, baseline: dict) -> list[str]:
    """Compare recent vs baseline metrics and return list of worsening signal names."""
    worsening = []

    # Rejection rate
    r = recent["rejection_rate"]
    b = baseline["rejection_rate"]
    if b > 0 and r > b * REJECTION_RATE_RELATIVE_FACTOR and (r - b) > REJECTION_RATE_ABSOLUTE_MIN:
        worsening.append("rejection_rate")
    elif b == 0 and r > REJECTION_RATE_ABSOLUTE_MIN:
        worsening.append("rejection_rate")

    # Average anomaly score
    r = recent["avg_anomaly_score"]
    b = baseline["avg_anomaly_score"]
    if r > b + ANOMALY_SCORE_ABSOLUTE_DELTA:
        worsening.append("avg_anomaly_score")

    # Review rate
    r = recent["review_rate"]
    b = baseline["review_rate"]
    if b > 0 and r > b * REVIEW_RATE_RELATIVE_FACTOR and (r - b) > REVIEW_RATE_ABSOLUTE_MIN:
        worsening.append("review_rate")
    elif b == 0 and r > REVIEW_RATE_ABSOLUTE_MIN:
        worsening.append("review_rate")

    # Override rate
    r = recent["override_rate"]
    b = baseline["override_rate"]
    if b > 0 and r > b * OVERRIDE_RATE_RELATIVE_FACTOR and (r - b) > OVERRIDE_RATE_ABSOLUTE_MIN:
        worsening.append("override_rate")
    elif b == 0 and r > OVERRIDE_RATE_ABSOLUTE_MIN:
        worsening.append("override_rate")

    return worsening

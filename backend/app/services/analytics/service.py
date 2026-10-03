"""
Extended analytics service with trend metrics, severity distribution,
review/override rates, hotspot aggregation, and drift monitoring.

All calculations are from REAL persisted inspection data.
No fake/fabricated analytics.
"""
from datetime import datetime, date, timedelta
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case
from app.db.models import (
    Inspection, InspectionReview, Product, Decision,
    OperationalSeverity, ReviewStatus
)
from app.schemas.analytics import (
    TodayAnalytics, AnalyticsResponse, DailyStats, ProductDistribution
)
from app.core.logging import get_logger

logger = get_logger(__name__)


async def get_today_analytics(db: AsyncSession) -> TodayAnalytics:
    """Get today's inspection statistics."""
    today = date.today()
    start = datetime.combine(today, datetime.min.time())
    end = datetime.combine(today, datetime.max.time())

    result = await db.execute(
        select(
            func.count(Inspection.id).label("total"),
            func.sum(case((Inspection.decision == Decision.PASS, 1), else_=0)).label("passed"),
            func.sum(case((Inspection.decision == Decision.FAIL, 1), else_=0)).label("failed"),
            func.sum(case((Inspection.decision == Decision.REVIEW, 1), else_=0)).label("review"),
            func.sum(case((Inspection.decision == Decision.RETAKE, 1), else_=0)).label("retake"),
            func.avg(Inspection.anomaly_score).label("avg_score"),
            func.avg(Inspection.processing_time_ms).label("avg_time"),
        ).where(
            Inspection.created_at >= start,
            Inspection.created_at <= end,
        )
    )
    row = result.first()

    total = int(row.total or 0)
    passed = int(row.passed or 0)
    failed = int(row.failed or 0)
    review = int(row.review or 0)
    retake = int(row.retake or 0)
    avg_score = float(row.avg_score or 0.0)
    avg_time = float(row.avg_time or 0.0)
    # Reject rate excludes RETAKE (image quality failures are not product defects)
    inspected = total - retake
    rejection_rate = (failed / inspected * 100) if inspected > 0 else 0.0

    # Pending reviews count
    pending_result = await db.execute(
        select(func.count(InspectionReview.id))
        .where(InspectionReview.review_status == ReviewStatus.pending)
    )
    pending_reviews = int((pending_result.scalar() or 0))

    return TodayAnalytics(
        total=total,
        passed=passed,
        failed=failed,
        review=review,
        rejection_rate=round(rejection_rate, 2),
        average_anomaly_score=round(avg_score, 4),
        average_processing_time_ms=round(avg_time, 1),
        pending_reviews=pending_reviews,
        retake=retake,
    )


async def get_range_analytics(
    db: AsyncSession,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    product_id: Optional[str] = None,
) -> AnalyticsResponse:
    """Get analytics for a date range."""
    if not date_from:
        date_from = date.today() - timedelta(days=30)
    if not date_to:
        date_to = date.today()

    start = datetime.combine(date_from, datetime.min.time())
    end = datetime.combine(date_to, datetime.max.time())

    conditions = [Inspection.created_at >= start, Inspection.created_at <= end]
    if product_id:
        try:
            import uuid as _uuid
            conditions.append(Inspection.product_id == _uuid.UUID(product_id))
        except ValueError:
            pass

    # Daily breakdown
    day_expr = func.date(Inspection.created_at)
    daily_result = await db.execute(
        select(
            day_expr.label("day"),
            func.count(Inspection.id).label("total"),
            func.sum(case((Inspection.decision == Decision.PASS, 1), else_=0)).label("passed"),
            func.sum(case((Inspection.decision == Decision.FAIL, 1), else_=0)).label("failed"),
            func.sum(case((Inspection.decision == Decision.REVIEW, 1), else_=0)).label("review"),
            func.sum(case((Inspection.decision == Decision.RETAKE, 1), else_=0)).label("retake"),
            func.avg(Inspection.anomaly_score).label("avg_score"),
            func.avg(Inspection.processing_time_ms).label("avg_time"),
        ).where(*conditions).group_by(day_expr).order_by(day_expr)
    )

    daily_stats = []
    total = passed = failed = review = retake_total = 0
    score_sum = time_sum = 0.0

    for row in daily_result.fetchall():
        d_total = int(row.total or 0)
        d_passed = int(row.passed or 0)
        d_failed = int(row.failed or 0)
        d_review = int(row.review or 0)
        d_retake = int(row.retake or 0)
        # Reject rate excludes retakes
        d_inspected = d_total - d_retake
        d_rate = (d_failed / d_inspected * 100) if d_inspected > 0 else 0.0

        daily_stats.append(DailyStats(
            date=str(row.day),
            total=d_total,
            passed=d_passed,
            failed=d_failed,
            review=d_review,
            rejection_rate=round(d_rate, 2),
            average_anomaly_score=round(float(row.avg_score or 0), 4),
            average_processing_time_ms=round(float(row.avg_time or 0), 1),
        ))
        total += d_total
        passed += d_passed
        failed += d_failed
        review += d_review
        retake_total += d_retake
        score_sum += float(row.avg_score or 0) * d_total
        time_sum += float(row.avg_time or 0) * d_total

    inspected_total = total - retake_total
    overall_rate = (failed / inspected_total * 100) if inspected_total > 0 else 0.0
    avg_score = (score_sum / total) if total > 0 else 0.0
    avg_time = (time_sum / total) if total > 0 else 0.0
    review_rate = (review / inspected_total * 100) if inspected_total > 0 else 0.0

    # Product distribution
    prod_result = await db.execute(
        select(
            Inspection.product_id,
            Product.name,
            func.count(Inspection.id).label("total"),
            func.sum(case((Inspection.decision == Decision.FAIL, 1), else_=0)).label("failed"),
            func.sum(case((Inspection.decision == Decision.REVIEW, 1), else_=0)).label("review"),
        ).outerjoin(Product, Inspection.product_id == Product.id)
        .where(*conditions)
        .group_by(Inspection.product_id, Product.name)
    )

    product_dist = []
    for row in prod_result.fetchall():
        product_dist.append(ProductDistribution(
            product_id=str(row.product_id) if row.product_id else None,
            product_name=row.name or "Unknown",
            total=int(row.total or 0),
            failed=int(row.failed or 0),
        ))

    # Severity distribution
    sev_result = await db.execute(
        select(
            Inspection.operational_severity,
            func.count(Inspection.id).label("count"),
        )
        .where(*conditions)
        .group_by(Inspection.operational_severity)
    )
    severity_dist = {
        row.operational_severity: int(row.count or 0)
        for row in sev_result.fetchall()
        if row.operational_severity is not None
    }

    # Override rate (human decisions that differ from AI)
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
            Inspection.created_at >= start,
            Inspection.created_at <= end,
            InspectionReview.review_status != ReviewStatus.pending,
        )
    )
    ov_row = override_result.first()
    reviewed_total = int(ov_row.reviewed or 0)
    overridden_total = int(ov_row.overridden or 0)
    override_rate = (overridden_total / reviewed_total * 100) if reviewed_total > 0 else 0.0

    return AnalyticsResponse(
        daily_stats=daily_stats,
        total_inspections=total,
        total_passed=passed,
        total_failed=failed,
        total_review=review,
        overall_rejection_rate=round(overall_rate, 2),
        average_anomaly_score=round(avg_score, 4),
        average_processing_time_ms=round(avg_time, 1),
        product_distribution=product_dist,
        review_rate=round(review_rate, 2),
        override_rate=round(override_rate, 2),
        severity_distribution=severity_dist,
        total_retake=retake_total,
    )

"""
Analytics service - aggregates inspection data for dashboards and charts.
"""
from datetime import datetime, date, timedelta
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, cast, Date, case
from app.db.models import Inspection, Product, Decision
from app.schemas.analytics import TodayAnalytics, AnalyticsResponse, DailyStats, ProductDistribution
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
    avg_score = float(row.avg_score or 0.0)
    avg_time = float(row.avg_time or 0.0)
    rejection_rate = (failed / total * 100) if total > 0 else 0.0

    return TodayAnalytics(
        total=total,
        passed=passed,
        failed=failed,
        review=review,
        rejection_rate=round(rejection_rate, 2),
        average_anomaly_score=round(avg_score, 4),
        average_processing_time_ms=round(avg_time, 1),
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

    # Build base query
    conditions = [Inspection.created_at >= start, Inspection.created_at <= end]
    if product_id:
        conditions.append(Inspection.product_id == product_id)

    # Daily breakdown
    day_expr = func.date(Inspection.created_at)
    daily_result = await db.execute(
        select(
            day_expr.label("day"),
            func.count(Inspection.id).label("total"),
            func.sum(case((Inspection.decision == Decision.PASS, 1), else_=0)).label("passed"),
            func.sum(case((Inspection.decision == Decision.FAIL, 1), else_=0)).label("failed"),
            func.sum(case((Inspection.decision == Decision.REVIEW, 1), else_=0)).label("review"),
            func.avg(Inspection.anomaly_score).label("avg_score"),
            func.avg(Inspection.processing_time_ms).label("avg_time"),
        ).where(*conditions).group_by(day_expr).order_by(day_expr)
    )

    daily_stats = []
    total = passed = failed = review = 0
    score_sum = time_sum = 0.0

    for row in daily_result.fetchall():
        d_total = int(row.total or 0)
        d_passed = int(row.passed or 0)
        d_failed = int(row.failed or 0)
        d_review = int(row.review or 0)
        d_rate = (d_failed / d_total * 100) if d_total > 0 else 0.0

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
        score_sum += float(row.avg_score or 0) * d_total
        time_sum += float(row.avg_time or 0) * d_total

    overall_rate = (failed / total * 100) if total > 0 else 0.0
    avg_score = (score_sum / total) if total > 0 else 0.0
    avg_time = (time_sum / total) if total > 0 else 0.0

    # Product distribution
    prod_result = await db.execute(
        select(
            Inspection.product_id,
            Product.name,
            func.count(Inspection.id).label("total"),
            func.sum(case((Inspection.decision == Decision.FAIL, 1), else_=0)).label("failed"),
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
    )

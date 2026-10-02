from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from datetime import date

from app.db.session import get_db
from app.schemas.analytics import TodayAnalytics, AnalyticsResponse
from app.services.analytics.service import get_today_analytics, get_range_analytics

router = APIRouter()


@router.get("/today", response_model=TodayAnalytics)
async def today_analytics(db: AsyncSession = Depends(get_db)):
    """Get today's inspection statistics."""
    return await get_today_analytics(db)


@router.get("", response_model=AnalyticsResponse)
async def range_analytics(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    product_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Get analytics for a custom date range."""
    return await get_range_analytics(db, date_from, date_to, product_id)

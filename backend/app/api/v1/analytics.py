"""
Extended Analytics API.
All data comes from real persisted inspection records.
No fabricated metrics.
"""
import uuid
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from datetime import date

from app.db.session import get_db
from app.schemas.analytics import (
    TodayAnalytics, AnalyticsResponse,
    HotspotResponse, DriftAllResponse, DriftStatusItem,
    ProfileVersionListResponse, ProfileVersionItem,
)
from app.services.analytics.service import get_today_analytics, get_range_analytics
from app.services.hotspot_analytics import get_hotspot_data
from app.services.drift_monitor import compute_drift, get_latest_drift, get_all_drift_status
from app.services.profile_versioning import list_profile_versions, get_active_profile_version
from app.core.logging import get_logger

router = APIRouter()
logger = get_logger(__name__)


@router.get("/today", response_model=TodayAnalytics)
async def today_analytics(db: AsyncSession = Depends(get_db)):
    """Get today's inspection statistics including pending review count."""
    return await get_today_analytics(db)


@router.get("", response_model=AnalyticsResponse)
async def range_analytics(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    product_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Get analytics for a custom date range with severity, review, override metrics."""
    return await get_range_analytics(db, date_from, date_to, product_id)


@router.get("/hotspots", response_model=HotspotResponse)
async def product_hotspots(
    product_id: str = Query(..., description="Product UUID to get hotspot data for"),
    days: int = Query(30, ge=1, le=365, description="Number of days to look back"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get spatial defect hotspot data for a specific product.
    
    Returns a normalized NxN grid showing which regions of the product
    are most frequently affected by detected anomalies.
    
    Only uses legitimate bounding-box localization data from actual defect records.
    Returns insufficient_data status when fewer than 5 inspections have spatial data.
    """
    try:
        prod_uuid = uuid.UUID(product_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid product_id format.")
    
    data = await get_hotspot_data(prod_uuid, db, days=days)
    return HotspotResponse(**data)


@router.get("/drift", response_model=DriftAllResponse)
async def all_drift_status(db: AsyncSession = Depends(get_db)):
    """
    Get the latest drift status for all products with Watch or DriftSuspected status.
    
    Used for the dashboard 'Products to Watch' card.
    Only includes products with non-Stable drift status.
    """
    items = await get_all_drift_status(db)
    return DriftAllResponse(
        items=[DriftStatusItem(**item) for item in items]
    )


@router.post("/drift/{product_id}/compute")
async def compute_product_drift(
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Trigger drift computation for a specific product.
    
    Requires minimum 20 inspections in the recent window.
    Does NOT auto-retrain. Reports drift status only.
    """
    snapshot = await compute_drift(product_id, db)
    return {
        "product_id": str(snapshot.product_id),
        "drift_status": snapshot.drift_status,
        "computed_at": snapshot.computed_at.isoformat(),
        "inspection_count": snapshot.inspection_count,
        "rejection_rate": snapshot.rejection_rate,
        "average_anomaly_score": snapshot.average_anomaly_score,
        "review_rate": snapshot.review_rate,
        "override_rate": snapshot.override_rate,
        "worsening_signals": snapshot.worsening_signals,
        "note": (
            "Drift monitoring uses operational metrics only. "
            "Drift does NOT trigger automatic retraining."
        ),
    }


@router.get("/drift/{product_id}", response_model=dict)
async def get_product_drift(
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get the latest drift snapshot for a specific product."""
    snapshot = await get_latest_drift(product_id, db)
    if not snapshot:
        return {
            "product_id": str(product_id),
            "drift_status": "stable",
            "message": "No drift snapshots computed yet for this product.",
        }
    return {
        "product_id": str(snapshot.product_id),
        "drift_status": snapshot.drift_status,
        "computed_at": snapshot.computed_at.isoformat(),
        "inspection_count": snapshot.inspection_count,
        "rejection_rate": snapshot.rejection_rate,
        "average_anomaly_score": snapshot.average_anomaly_score,
        "review_rate": snapshot.review_rate,
        "override_rate": snapshot.override_rate,
        "worsening_signals": snapshot.worsening_signals,
        "window_days": snapshot.window_days,
    }


@router.get("/profile-versions/{product_id}", response_model=ProfileVersionListResponse)
async def get_profile_versions(
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Get all profile versions for a product.
    
    Returns version history with the active version flagged.
    Historical inspections are associated with the profile version
    that was active when they were performed.
    """
    versions = await list_profile_versions(product_id, db)
    active = await get_active_profile_version(product_id, db)
    
    items = [
        ProfileVersionItem(
            id=str(v.id),
            product_id=str(v.product_id),
            version_number=v.version_number,
            is_active=v.is_active,
            reference_image_count=v.reference_image_count,
            threshold_snapshot=v.threshold_snapshot,
            model_status_snapshot=v.model_status_snapshot,
            change_reason=v.change_reason,
            created_at=v.created_at.isoformat(),
            parent_version_id=str(v.parent_version_id) if v.parent_version_id else None,
        )
        for v in versions
    ]
    
    return ProfileVersionListResponse(
        items=items,
        active_version=active.version_number if active else None,
    )

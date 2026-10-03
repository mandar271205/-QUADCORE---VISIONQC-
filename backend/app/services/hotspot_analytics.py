"""
Hotspot Analytics Service — aggregates legitimate localization data across inspections.

CRITICAL PRINCIPLE:
    Only include localization sources that legitimately support spatial aggregation.
    A VLM text statement like "wrong color" does NOT provide a pixel heatmap.

    We aggregate from DEFECT REGIONS only when they are:
    1. Genuine bounding-box coordinates from VLM region detection
    2. OR pixel-space data from ML anomaly maps (stored as heatmap_url)

    We do NOT use heatmap_url alone for spatial aggregation because the uploaded
    image may not have a legitimate anomaly map (could be an empty blue heatmap
    generated for a PASS result).

    Aggregation is ALWAYS product/SKU specific. Different products must NEVER
    be mixed into one spatial map.

Minimum evidence policy:
    MIN_DEFECT_REGIONS_FOR_HOTSPOT = 5
    If fewer than this many inspections have valid region data for the product,
    return status='insufficient_data' instead of fabricating hotspots.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Optional, List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.db.models import Inspection, Defect, Decision
from app.core.logging import get_logger

logger = get_logger(__name__)

MIN_DEFECT_REGIONS_FOR_HOTSPOT = 5   # minimum number of region-bearing inspections
HOTSPOT_GRID_SIZE = 10               # NxN grid for normalized region aggregation


async def get_hotspot_data(
    product_id: uuid.UUID,
    db: AsyncSession,
    days: int = 30,
    min_evidence: int = MIN_DEFECT_REGIONS_FOR_HOTSPOT,
) -> dict:
    """
    Aggregate defect region data into a normalized hotspot grid for a product.

    Returns:
        {
            status: 'ok' | 'insufficient_data',
            product_id: str,
            grid_size: int,
            grid: [[float]] (NxN normalized frequency grid),
            contributing_inspections: int,
            total_regions: int,
            date_range: {from: str, to: str},
            message: str  (if insufficient_data)
        }

    Grid cells contain fraction 0.0–1.0 of how often that spatial region
    contained a defect (normalized to grid max).
    """
    now = datetime.utcnow()
    start = now - timedelta(days=days)

    # Query inspections with defects that have region data
    result = await db.execute(
        select(Defect).join(Inspection, Defect.inspection_id == Inspection.id).where(
            and_(
                Inspection.product_id == product_id,
                Inspection.created_at >= start,
                # Only include FAIL and REVIEW — PASS defects are noise
                Inspection.decision.in_([Decision.FAIL.value, Decision.REVIEW.value]),
                Defect.region_x.isnot(None),
                Defect.region_y.isnot(None),
                Defect.region_width.isnot(None),
                Defect.region_height.isnot(None),
            )
        )
    )
    defects = result.scalars().all()

    # Find unique contributing inspections
    contributing_inspection_ids = {d.inspection_id for d in defects}
    n_contributing = len(contributing_inspection_ids)
    n_regions = len(defects)

    if n_contributing < min_evidence:
        logger.info(
            f"[Hotspot] Product {product_id}: only {n_contributing} contributing "
            f"inspections (need {min_evidence}) → insufficient_data"
        )
        return {
            "status": "insufficient_data",
            "product_id": str(product_id),
            "contributing_inspections": n_contributing,
            "total_regions": n_regions,
            "min_evidence_required": min_evidence,
            "message": (
                f"Not enough localization data yet "
                f"({n_contributing} inspection{'s' if n_contributing != 1 else ''} "
                f"with region data, need at least {min_evidence})."
            ),
            "date_range": {
                "from": start.date().isoformat(),
                "to": now.date().isoformat(),
            },
        }

    # Build normalized grid
    grid = _build_grid(defects, HOTSPOT_GRID_SIZE)

    return {
        "status": "ok",
        "product_id": str(product_id),
        "grid_size": HOTSPOT_GRID_SIZE,
        "grid": grid,
        "contributing_inspections": n_contributing,
        "total_regions": n_regions,
        "date_range": {
            "from": start.date().isoformat(),
            "to": now.date().isoformat(),
        },
    }


def _build_grid(defects, grid_size: int) -> List[List[float]]:
    """
    Build a normalized NxN frequency grid from defect regions.
    Region coordinates are normalized [0,1].
    Returns grid where each cell is frequency 0.0–1.0.
    """
    import numpy as np

    grid = np.zeros((grid_size, grid_size), dtype=np.float32)

    for defect in defects:
        # Normalize region to grid coordinates
        x = float(defect.region_x or 0.0)
        y = float(defect.region_y or 0.0)
        w = float(defect.region_width or 0.0)
        h = float(defect.region_height or 0.0)

        # Clamp to valid range
        x = max(0.0, min(1.0, x))
        y = max(0.0, min(1.0, y))
        w = max(0.0, min(1.0 - x, w))
        h = max(0.0, min(1.0 - y, h))

        # Map to grid cells (entire region contributes)
        x1 = int(x * grid_size)
        y1 = int(y * grid_size)
        x2 = min(grid_size - 1, int((x + w) * grid_size))
        y2 = min(grid_size - 1, int((y + h) * grid_size))

        grid[y1:y2 + 1, x1:x2 + 1] += 1.0

    # Normalize to [0, 1]
    max_val = float(np.max(grid))
    if max_val > 0:
        grid = grid / max_val

    return grid.tolist()

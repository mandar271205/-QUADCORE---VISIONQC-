"""
Inspections API endpoints.
Handles image upload, inspection execution, history, and detail retrieval.
IMPORTANT: Provider/engine details are NEVER returned in any public response.
"""
import uuid
import time
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.db.session import get_db
from app.db.models import (
    Inspection, Defect, InspectionRuntime, Product, Decision, ClientType, Severity
)
from app.schemas.inspection import (
    InspectionResponse, InspectionListResponse, InspectionListItem,
    ProductSummaryInInspection
)
from app.schemas.defects import DefectResponse, DefectRegion
from app.services.inspection_router import inspection_router
from app.services.vlm.base import ProductContext
from app.services.heatmap.generator import (
    generate_heatmap_from_anomaly_map,
    generate_heatmap_from_regions,
    generate_empty_heatmap,
)
from app.services.heatmap.masks import validate_and_preprocess
from app.services.storage.supabase import storage_service
from app.core.exceptions import (
    InvalidImageError, ImageTooLargeError, AllProvidersFailedError, visionqc_exception_to_http
)
from app.core.logging import get_logger

router = APIRouter()
logger = get_logger(__name__)


@router.post("", response_model=InspectionResponse, status_code=status.HTTP_201_CREATED)
async def create_inspection(
    image: UploadFile = File(...),
    product_id: Optional[str] = Form(None),
    client_type: str = Form("web"),
    inspection_mode: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Run a quality inspection on the uploaded image.
    Mobile clients always use VLM-only mode regardless of inspection_mode.
    """
    start_time = time.time()
    inspection_id = uuid.uuid4()

    # Validate content type
    if image.content_type not in ("image/jpeg", "image/png", "image/webp"):
        raise HTTPException(status_code=422, detail="Unsupported image format. Use JPEG, PNG, or WebP.")

    try:
        image_bytes = await image.read()
    except Exception:
        raise HTTPException(status_code=422, detail="Could not read uploaded image.")

    # Preprocess
    try:
        original_bytes, inference_bytes = validate_and_preprocess(image_bytes, image.content_type)
    except (InvalidImageError, ImageTooLargeError) as e:
        raise visionqc_exception_to_http(e)

    # Load product context
    product = None
    product_context = ProductContext(threshold=0.55)

    if product_id:
        try:
            prod_uuid = uuid.UUID(product_id)
            result = await db.execute(select(Product).where(Product.id == prod_uuid))
            product = result.scalar_one_or_none()
            if product:
                product_context = ProductContext(
                    product_id=str(product.id),
                    product_name=product.name,
                    product_description=product.description,
                    threshold=product.threshold,
                )
        except Exception:
            pass

    # Validate client_type
    try:
        ct = ClientType(client_type)
    except ValueError:
        ct = ClientType.web

    # Run inspection
    runtime_started = datetime.utcnow()
    try:
        result = await inspection_router.run(
            image_bytes=inference_bytes,
            product_context=product_context,
            mode_override=inspection_mode,
            client_type=ct.value,
        )
    except (AllProvidersFailedError, Exception) as e:
        logger.error(f"Inspection failed for {inspection_id}: {type(e).__name__}: {e}")
        raise HTTPException(
            status_code=503,
            detail="Inspection could not be completed. Please try again."
        )

    runtime_completed = datetime.utcnow()
    processing_time_ms = int((time.time() - start_time) * 1000)

    # Generate heatmap
    heatmap_bytes = None
    try:
        if result.anomaly_map is not None:
            # ML or demo mode: use native anomaly map
            import io, numpy as np
            from PIL import Image
            buf = io.BytesIO(result.anomaly_map)
            arr = np.array(Image.open(buf)).astype(np.float32) / 255.0
            heatmap_bytes, _ = generate_heatmap_from_anomaly_map(arr, original_bytes)
        elif result.defects and any(
            d.get("region") for d in result.defects if isinstance(d, dict)
        ):
            # VLM with regions
            regions = [d["region"] for d in result.defects if isinstance(d, dict) and d.get("region")]
            heatmap_bytes, _ = generate_heatmap_from_regions(regions, original_bytes)
        else:
            heatmap_bytes, _ = generate_empty_heatmap(original_bytes)
    except Exception as e:
        logger.warning(f"Heatmap generation failed: {e}")
        try:
            heatmap_bytes, _ = generate_empty_heatmap(original_bytes)
        except Exception:
            pass

    # Upload images to storage
    original_url = None
    heatmap_url = None
    try:
        original_url = await storage_service.upload_original(original_bytes, str(inspection_id))
        if heatmap_bytes:
            heatmap_url = await storage_service.upload_heatmap(heatmap_bytes, str(inspection_id))
    except Exception as e:
        logger.warning(f"Storage upload failed (non-fatal): {e}")

    # Persist inspection
    threshold_used = product_context.threshold
    db_inspection = Inspection(
        id=inspection_id,
        product_id=product.id if product else None,
        client_type=ct,
        decision=result.decision,
        anomaly_score=result.anomaly_score,
        confidence=result.confidence,
        threshold=threshold_used,
        original_image_url=original_url,
        heatmap_url=heatmap_url,
        processing_time_ms=processing_time_ms,
    )
    db.add(db_inspection)

    # Persist defects
    defect_responses = []
    for d in result.defects:
        if not isinstance(d, dict):
            continue
        severity_str = d.get("severity", "medium")
        try:
            sev = Severity(severity_str)
        except ValueError:
            sev = Severity.medium

        region = d.get("region")
        db_defect = Defect(
            inspection_id=inspection_id,
            type=d.get("type", "unknown"),
            description=d.get("description"),
            severity=sev,
            region_x=region.get("x") if region else None,
            region_y=region.get("y") if region else None,
            region_width=region.get("width") if region else None,
            region_height=region.get("height") if region else None,
        )
        db.add(db_defect)

        defect_region = None
        if region:
            defect_region = DefectRegion(
                x=region.get("x", 0),
                y=region.get("y", 0),
                width=region.get("width", 0),
                height=region.get("height", 0),
            )
        defect_responses.append(DefectResponse(
            type=d.get("type", "unknown"),
            description=d.get("description"),
            severity=sev,
            region=defect_region,
        ))

    # Persist runtime (internal debug - never returned)
    db_runtime = InspectionRuntime(
        inspection_id=inspection_id,
        engine_type=result.engine_type,
        provider=result.provider,
        engine_name=result.provider,
        started_at=runtime_started,
        completed_at=runtime_completed,
        latency_ms=result.latency_ms,
        success=True,
    )
    db.add(db_runtime)

    await db.commit()

    return InspectionResponse(
        inspection_id=inspection_id,
        product=ProductSummaryInInspection(id=product.id, name=product.name) if product else None,
        decision=result.decision,
        anomaly_score=result.anomaly_score,
        confidence=result.confidence,
        threshold=threshold_used,
        heatmap_url=heatmap_url,
        original_image_url=original_url,
        defects=defect_responses,
        summary=result.summary,
        processing_time_ms=processing_time_ms,
        created_at=db_inspection.created_at or datetime.utcnow(),
    )


@router.get("", response_model=InspectionListResponse)
async def list_inspections(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    product_id: Optional[str] = Query(None),
    decision: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    conditions = []

    if product_id:
        try:
            conditions.append(Inspection.product_id == uuid.UUID(product_id))
        except ValueError:
            pass

    if decision:
        try:
            conditions.append(Inspection.decision == Decision(decision.upper()))
        except ValueError:
            pass

    if date_from:
        try:
            conditions.append(Inspection.created_at >= datetime.fromisoformat(date_from))
        except ValueError:
            pass

    if date_to:
        try:
            conditions.append(Inspection.created_at <= datetime.fromisoformat(date_to))
        except ValueError:
            pass

    # Count
    count_q = select(func.count(Inspection.id))
    if conditions:
        count_q = count_q.where(*conditions)
    total_result = await db.execute(count_q)
    total = total_result.scalar() or 0

    # Fetch page
    q = (
        select(Inspection)
        .options(selectinload(Inspection.product))
        .order_by(Inspection.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    if conditions:
        q = q.where(*conditions)

    result = await db.execute(q)
    inspections = result.scalars().all()

    items = []
    for insp in inspections:
        items.append(InspectionListItem(
            inspection_id=insp.id,
            product=(
                ProductSummaryInInspection(id=insp.product.id, name=insp.product.name)
                if insp.product else None
            ),
            decision=insp.decision,
            anomaly_score=insp.anomaly_score,
            confidence=insp.confidence,
            threshold=insp.threshold,
            heatmap_url=insp.heatmap_url,
            original_image_url=insp.original_image_url,
            processing_time_ms=insp.processing_time_ms,
            created_at=insp.created_at,
        ))

    return InspectionListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=((total - 1) // page_size + 1) if total > 0 else 1,
    )


@router.get("/{inspection_id}", response_model=InspectionResponse)
async def get_inspection(inspection_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Inspection)
        .options(selectinload(Inspection.product), selectinload(Inspection.defects))
        .where(Inspection.id == inspection_id)
    )
    insp = result.scalar_one_or_none()
    if not insp:
        raise HTTPException(status_code=404, detail="Inspection not found.")

    defect_responses = []
    for d in insp.defects:
        region = None
        if d.region_x is not None:
            region = DefectRegion(
                x=d.region_x,
                y=d.region_y or 0,
                width=d.region_width or 0,
                height=d.region_height or 0,
            )
        defect_responses.append(DefectResponse(
            type=d.type,
            description=d.description,
            severity=d.severity,
            region=region,
        ))

    return InspectionResponse(
        inspection_id=insp.id,
        product=(
            ProductSummaryInInspection(id=insp.product.id, name=insp.product.name)
            if insp.product else None
        ),
        decision=insp.decision,
        anomaly_score=insp.anomaly_score,
        confidence=insp.confidence,
        threshold=insp.threshold,
        heatmap_url=insp.heatmap_url,
        original_image_url=insp.original_image_url,
        defects=defect_responses,
        summary="",
        processing_time_ms=insp.processing_time_ms,
        created_at=insp.created_at,
    )


@router.delete("/{inspection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_inspection(inspection_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Inspection).where(Inspection.id == inspection_id))
    insp = result.scalar_one_or_none()
    if not insp:
        raise HTTPException(status_code=404, detail="Inspection not found.")
    await db.delete(insp)
    await db.commit()

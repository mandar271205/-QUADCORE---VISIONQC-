"""
Inspections API endpoints.
Handles image upload, inspection execution, history, and detail retrieval.
IMPORTANT: Provider/engine details are NEVER returned in any public response.
"""
import asyncio
import json
import uuid
import time
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload, joinedload

from app.db.session import get_db
from app.db.models import (
    Inspection, Defect, InspectionRuntime, Product, Decision, ClientType, Severity,
    OperationalSeverity, QualityCheckStatus, InspectionReview, ReviewStatus
)
from app.schemas.inspection import (
    InspectionResponse, InspectionListResponse, InspectionListItem,
    ProductSummaryInInspection
)
from app.schemas.defects import DefectResponse, DefectRegion
from app.services.inspection_router import inspection_router, resolve_inspection_mode
from app.services.vlm.base import ProductContext
from app.services.heatmap.generator import (
    generate_heatmap_from_anomaly_map,
    generate_heatmap_from_regions,
    generate_empty_heatmap,
)
from app.services.heatmap.masks import validate_and_preprocess
from app.services.storage.supabase import storage_service
from app.services.image_quality_gate import image_quality_gate
from app.services.severity import compute_severity
from app.services.review_queue import maybe_enqueue_review
from app.services.profile_versioning import get_active_profile_version
from app.core.exceptions import (
    InvalidImageError, ImageTooLargeError, AllProvidersFailedError, visionqc_exception_to_http
)
from app.core.logging import get_logger
from app.core.config import settings

router = APIRouter()
logger = get_logger(__name__)


def _prepare_heatmap(result, original_bytes: bytes):
    """CPU image work runs in a worker thread, keeping other requests responsive."""
    # Calibrate defects against visual evidence
    from app.services.heatmap.generator import calibrate_defects
    decision_val = result.decision.value if hasattr(result.decision, "value") else str(result.decision)
    calibrated_defects = calibrate_defects(result.defects, original_bytes, decision=decision_val)

    # Generate heatmap
    heatmap_bytes = None
    try:
        if result.engine_type != "vlm" and result.anomaly_map is not None:
            # ML or demo mode: use native anomaly map
            import io, numpy as np
            from PIL import Image
            buf = io.BytesIO(result.anomaly_map)
            arr = np.array(Image.open(buf)).astype(np.float32) / 255.0
            heatmap_bytes, _ = generate_heatmap_from_anomaly_map(arr, original_bytes, include_overlay=False)
            if result.roi_region:
                from PIL import ImageDraw
                annotated=Image.open(io.BytesIO(heatmap_bytes)).convert('RGB')
                region=result.roi_region
                w,h=annotated.size
                box=(region['x']*w,region['y']*h,
                     (region['x']+region['width'])*w-1,(region['y']+region['height'])*h-1)
                ImageDraw.Draw(annotated).rectangle(box,outline=(0,255,0),width=max(2,min(w,h)//200))
                annotated_bytes=io.BytesIO();annotated.save(annotated_bytes,format='PNG')
                heatmap_bytes=annotated_bytes.getvalue()
        elif result.decision != Decision.PASS and calibrated_defects:
            # VLM with regions
            regions = [d["region"] for d in calibrated_defects if isinstance(d, dict) and d.get("region")]
            heatmap_bytes, _ = generate_heatmap_from_regions(regions, original_bytes, include_overlay=False)
        else:
            heatmap_bytes, _ = generate_empty_heatmap(original_bytes)
    except Exception as e:
        logger.warning(f"Heatmap generation failed: {e}")
        try:
            heatmap_bytes, _ = generate_empty_heatmap(original_bytes)
        except Exception:
            pass

    return calibrated_defects, heatmap_bytes


async def _prepare_and_upload(result, original_bytes: bytes, inspection_id: str):
    # Start storing the original while the heatmap is calculated; upload the
    # heatmap as soon as it is ready. Failure of either upload preserves the other.
    async def heatmap_upload():
        defects, heatmap = await asyncio.to_thread(_prepare_heatmap, result, original_bytes)
        url = None
        if heatmap:
            try:
                url = await storage_service.upload_heatmap(heatmap, inspection_id)
            except Exception as error:
                logger.warning("Heatmap upload failed (non-fatal): %s", type(error).__name__)
        return defects, url

    original, prepared = await asyncio.gather(
        storage_service.upload_original(original_bytes, inspection_id),
        heatmap_upload(),
        return_exceptions=True,
    )
    if isinstance(prepared, BaseException):
        raise prepared
    if isinstance(original, BaseException):
        logger.warning("Original upload failed (non-fatal): %s", type(original).__name__)
        original = None
    defects, heatmap_url = prepared
    return defects, original, heatmap_url


@router.post("", response_model=InspectionResponse, status_code=status.HTTP_201_CREATED)
async def create_inspection(
    image: UploadFile = File(...),
    product_id: Optional[str] = Form(None),
    client_type: str = Form("web"),
    inspection_mode: Optional[str] = Form(None),
    batch_id: Optional[str] = Form(None),
    shift: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Run a quality inspection on the uploaded image.
    
    Image Quality Gate runs first. If the image is clearly unusable (blurry,
    dark, overexposed, etc.), a RETAKE outcome is returned immediately WITHOUT
    running AI inspection. A RETAKE is NOT a product defect.
    
    Mobile uses the configured mode when MOBILE_USE_ML is enabled; otherwise VLM-only.
    """
    start_time = time.perf_counter()
    inspection_id = uuid.uuid4()

    # Validate content type
    if image.content_type not in ("image/jpeg", "image/png", "image/webp"):
        raise HTTPException(status_code=422, detail="Unsupported image format. Use JPEG, PNG, or WebP.")

    try:
        image_bytes = await image.read()
    except Exception:
        raise HTTPException(status_code=422, detail="Could not read uploaded image.")

    # Resolve product/profile before preprocessing so Member 1 receives a
    # lossless PNG even in model-primary and parallel modes.
    effective_mode = resolve_inspection_mode(inspection_mode, client_type)
    product = None
    product_context = ProductContext(threshold=0.55)

    if product_id:
        try:
            prod_uuid = uuid.UUID(product_id)
            query = select(Product).where(Product.id == prod_uuid)
            if effective_mode != 'model_only':
                query = query.options(selectinload(Product.reference_images))
            result = await db.execute(query)
            product = result.scalar_one_or_none()
            if product:
                # Pre-populate reference_images so VLM reference path uses them
                ref_urls = [
                    ri.storage_url
                    for ri in (product.reference_images if effective_mode != 'model_only' else [])
                    if ri.is_active and ri.storage_url
                ]
                product_context = ProductContext(
                    product_id=str(product.id),
                    product_name=product.name,
                    product_description=product.description,
                    threshold=product.threshold,
                    reference_images=ref_urls,
                )
        except Exception:
            pass

        if product is None:
            raise HTTPException(status_code=422, detail='Select an existing product for inspection.')

    selected_ml_engine = None
    if product is not None and not settings.DEMO_MODE:
        from app.services.ml.registry import MLRegistry
        selected_ml_engine = MLRegistry.get(str(product.id))

    try:
        ml_only = effective_mode == 'model_only'
        member1_profile = bool(getattr(selected_ml_engine, 'is_member1', False))
        preserve_member1_pixels = member1_profile and effective_mode in (
            'model_primary', 'parallel_first_valid'
        )
        original_bytes, inference_bytes = await asyncio.to_thread(
            validate_and_preprocess,
            image_bytes,
            image.content_type,
            lossless_inference=ml_only or preserve_member1_pixels,
        )
    except (InvalidImageError, ImageTooLargeError) as e:
        raise visionqc_exception_to_http(e)

    # Validate client_type (needed before quality gate RETAKE path)
    try:
        ct = ClientType(client_type)
    except ValueError:
        ct = ClientType.web

    # ── Image Quality Gate ───────────────────────────────────────────────────
    # Runs BEFORE expensive AI inspection. Poor images get RETAKE, not FAIL.
    quality_result = None
    qc_status = QualityCheckStatus.not_run
    if not settings.DEMO_MODE:
        quality_result = image_quality_gate.check(original_bytes)
        qc_status = QualityCheckStatus(quality_result.status) if quality_result.status in (
            'good', 'uncertain', 'poor'
        ) else QualityCheckStatus.not_run

        if quality_result.status == 'poor':
            # Do NOT run inspection. Return RETAKE outcome immediately.
            logger.info(
                f"[QualityGate] Poor image quality (score={quality_result.quality_score:.3f}, "
                f"issues={quality_result.issues}) — returning RETAKE, no inspection run"
            )
            processing_time_ms = int((time.time() - start_time) * 1000)

            # Persist as RETAKE inspection (NOT a product defect)
            upload_url = None
            try:
                upload_url = await storage_service.upload_original(original_bytes, str(inspection_id))
            except Exception:
                pass

            db_inspection = Inspection(
                id=inspection_id,
                product_id=product.id if product else None,
                client_type=ct,
                decision=Decision.RETAKE,
                anomaly_score=0.0,
                confidence=0.0,
                threshold=product_context.threshold,
                original_image_url=upload_url,
                heatmap_url=None,
                processing_time_ms=processing_time_ms,
                operational_severity=OperationalSeverity.UNKNOWN,
                quality_check_status=qc_status,
                quality_score=quality_result.quality_score,
                quality_issues=json.dumps(quality_result.issues) if quality_result.issues else None,
                batch_id=batch_id,
                shift=shift,
            )
            db.add(db_inspection)
            await db.commit()

            return InspectionResponse(
                inspection_id=inspection_id,
                product=ProductSummaryInInspection(id=product.id, name=product.name) if product else None,
                decision=Decision.RETAKE,
                anomaly_score=0.0,
                confidence=0.0,
                threshold=product_context.threshold,
                heatmap_url=None,
                original_image_url=upload_url,
                defects=[],
                summary=quality_result.message,
                processing_time_ms=processing_time_ms,
                created_at=db_inspection.created_at or datetime.utcnow(),
                operational_severity=OperationalSeverity.UNKNOWN,
                quality_check_status=qc_status,
                quality_score=quality_result.quality_score,
                quality_issues=quality_result.issues,
                quality_message=quality_result.message,
                batch_id=batch_id,
                shift=shift,
            )

    if not settings.DEMO_MODE and effective_mode == 'model_only':
        if product is None or selected_ml_engine is None:
            raise HTTPException(status_code=422, detail='Select a product with a trained inspection profile. Attach a matching profile on its product page.')

    # Get active profile version for auditability (non-blocking)
    active_profile_version = None
    if product is not None:
        try:
            active_profile_version = await get_active_profile_version(product.id, db)
        except Exception:
            pass

    # Run inspection
    runtime_started = datetime.utcnow()
    try:
        result = await inspection_router.run(
            image_bytes=inference_bytes,
            product_context=product_context,
            mode_override=inspection_mode,
            client_type=ct.value,
            # Pass model_status for inspection-while-training routing decision
            model_status=product.model_status.value if product else None,
        )
    except (AllProvidersFailedError, Exception) as e:
        logger.error(f"Inspection failed for {inspection_id}: {type(e).__name__}: {e}")
        raise HTTPException(
            status_code=503,
            detail="Inspection could not be completed. Please try again."
        )

    runtime_completed = datetime.utcnow()

    calibrated_defects, original_url, heatmap_url = await _prepare_and_upload(
        result, original_bytes, str(inspection_id)
    )
    # Persist the duration through image processing and storage. The returned
    # duration below also includes the database commit.
    processing_time_ms = int((time.perf_counter() - start_time) * 1000)

    # Persist inspection
    threshold_used = result.threshold if result.threshold is not None else product_context.threshold

    # Compute operational severity from actual engine evidence
    operational_severity = compute_severity(
        decision=result.decision,
        anomaly_score=result.anomaly_score,
        threshold=threshold_used,
        confidence=result.confidence,
        defect_count=len(result.defects),
    )

    # Build conformity summary (supervisor-facing, no internal engine names)
    conformity_summary = result.summary if result.summary else None

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
        operational_severity=operational_severity,
        quality_check_status=qc_status if quality_result else QualityCheckStatus.not_run,
        quality_score=quality_result.quality_score if quality_result else None,
        quality_issues=json.dumps(quality_result.issues) if (quality_result and quality_result.issues) else None,
        conformity_summary=conformity_summary,
        batch_id=batch_id,
        shift=shift,
        profile_version_id=active_profile_version.id if active_profile_version else None,
    )
    db.add(db_inspection)

    # Persist defects
    defect_responses = []
    for d in calibrated_defects:
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
        engine_name=f"{result.provider} [{result.winning_reason}]"[:255] if result.winning_reason else result.provider,
        started_at=runtime_started,
        completed_at=runtime_completed,
        latency_ms=result.latency_ms,
        success=True,
        error_message=json.dumps({"winning_reason": result.winning_reason, "parallel_provenance": result.parallel_provenance, "vlm_reference_path_used": result.vlm_reference_path_used, "model_status_at_inspection": result.model_status_at_inspection}) if (result.parallel_provenance or result.vlm_reference_path_used or result.winning_reason) else None,
    )
    db.add(db_runtime)

    # ── Human Review Queue ──────────────────────────────────────────────────
    # REVIEW decisions are enqueued; PASS/FAIL/RETAKE are NOT
    review_record = await maybe_enqueue_review(inspection_id, result.decision, db)

    await db.commit()
    processing_time_ms = int((time.perf_counter() - start_time) * 1000)
    logger.info("Inspection %s completed in %dms", inspection_id, processing_time_ms)

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
        operational_severity=operational_severity,
        quality_check_status=qc_status if quality_result else QualityCheckStatus.not_run,
        quality_score=quality_result.quality_score if quality_result else None,
        quality_issues=quality_result.issues if quality_result else None,
        quality_message=quality_result.message if quality_result else None,
        conformity_summary=conformity_summary,
        batch_id=batch_id,
        shift=shift,
        review_status=review_record.review_status if review_record else None,
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
        .options(
            selectinload(Inspection.product),
            selectinload(Inspection.review),
        )
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
        rev = insp.review
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
            operational_severity=getattr(insp, 'operational_severity', OperationalSeverity.UNKNOWN),
            quality_check_status=getattr(insp, 'quality_check_status', QualityCheckStatus.not_run),
            batch_id=getattr(insp, 'batch_id', None),
            shift=getattr(insp, 'shift', None),
            review_status=rev.review_status if rev else None,
            human_decision=rev.human_decision if rev else None,
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
        .options(
            selectinload(Inspection.product),
            selectinload(Inspection.defects),
            selectinload(Inspection.review),
        )
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

    rev = insp.review
    import json as _json
    quality_issues_parsed = None
    raw_qi = getattr(insp, 'quality_issues', None)
    if raw_qi:
        try:
            quality_issues_parsed = _json.loads(raw_qi)
        except Exception:
            pass

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
        summary=getattr(insp, 'conformity_summary', '') or '',
        processing_time_ms=insp.processing_time_ms,
        created_at=insp.created_at,
        operational_severity=getattr(insp, 'operational_severity', OperationalSeverity.UNKNOWN),
        quality_check_status=getattr(insp, 'quality_check_status', QualityCheckStatus.not_run),
        quality_score=getattr(insp, 'quality_score', None),
        quality_issues=quality_issues_parsed,
        conformity_summary=getattr(insp, 'conformity_summary', None),
        batch_id=getattr(insp, 'batch_id', None),
        shift=getattr(insp, 'shift', None),
        review_status=rev.review_status if rev else None,
        human_decision=rev.human_decision if rev else None,
    )


@router.delete("/{inspection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_inspection(inspection_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Inspection).where(Inspection.id == inspection_id))
    insp = result.scalar_one_or_none()
    if not insp:
        raise HTTPException(status_code=404, detail="Inspection not found.")
    await db.delete(insp)
    await db.commit()

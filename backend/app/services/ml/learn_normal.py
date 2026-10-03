"""
Learn Normal Training Service.

Implements the VisionQC hybrid "Learn Normal" workflow:

  1. Supervisor uploads 20–30 GOOD reference images per product.
  2. POST /products/{id}/learn-normal triggers background training.
  3. model_status: not_available → training → ready / validation_required / failed

Hybrid paths (run concurrently in background):

  PATH A — Real ML fitting
    The exact uploaded GOOD images are fed to the closest available
    product-specific anomaly model pipeline (autoencoder / PaDiM / PatchCore).
    This runs asynchronously. It does NOT claim Member 1 checkpoints trained
    a new PatchCore — it uses the existing ProfileMLEngine / autoencoder baseline
    available at ML_MODEL_ROOT.

  PATH B — VLM reference context
    The same GOOD images are retained in the DB as ProductReferenceImage rows.
    When the VLM is called during inspection, the inspection API pre-populates
    ProductContext.reference_images from these rows so the VLM uses them as
    visual context. No extra work needed here — the images are already in the DB.
    We do NOT claim internally that the VLM "trained" a PatchCore/PaDiM model.

During training (model_status == 'training'):
  - VLM-permitted routing modes can inspect through the VLM reference path.
  - model_only mode remains blocked until model_status == 'ready'.

On ready (model_status == 'ready'):
  - ML becomes automatically eligible for subsequent inspections.
  - User does not need to recreate the product.
"""
from __future__ import annotations

import asyncio
import base64
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.core.logging import get_logger
from app.db.models import Product, ModelStatus, ProductReferenceImage, ProductThresholdHistory
from app.db.session import AsyncSessionLocal
from app.services.ml.train_product import run_training_pipeline

logger = get_logger(__name__)

# Minimum reference images required before training can start
MIN_REFERENCE_IMAGES = 20

# Maximum reference images recommended
MAX_REFERENCE_IMAGES = 30


class LearnNormalService:
    """Manages the Learn Normal hybrid training lifecycle for a product."""

    def __init__(self):
        self._locks: dict[str, asyncio.Lock] = {}

    def _get_lock(self, product_id: str) -> asyncio.Lock:
        if product_id not in self._locks:
            self._locks[product_id] = asyncio.Lock()
        return self._locks[product_id]

    async def start(
        self,
        product: Product,
        db: AsyncSession,
    ) -> dict:
        """
        Validate and start the Learn Normal training workflow.

        Returns a status dict describing the current training state.
        Raises ValueError with a user-visible message on validation failure.

        The caller is responsible for ensuring reference images have already
        been stored in DB (ProductReferenceImage rows with storage_url set).
        """
        count = product.reference_image_count
        if count < MIN_REFERENCE_IMAGES:
            raise ValueError(
                f"At least {MIN_REFERENCE_IMAGES} reference images are required "
                f"to start training. You have {count}. "
                f"Upload {MIN_REFERENCE_IMAGES - count} more GOOD images."
            )

        if product.model_status == ModelStatus.training:
            return {
                "status": "already_training",
                "message": "Training is already in progress.",
                "model_status": product.model_status.value,
                "reference_image_count": count,
                "vlm_reference_path": "available",
            }

        # Transition to training state
        product.model_status = ModelStatus.training
        await db.commit()
        await db.refresh(product)

        logger.info(
            f"[LearnNormal] Training started for product {product.id} "
            f"({product.name}) with {count} reference images"
        )
        logger.info(
            f"[LearnNormal] VLM reference context path: ACTIVE "
            f"({count} images available as reference context during training)"
        )

        # Schedule background task to run real training pipeline
        product_id = str(product.id)
        asyncio.create_task(
            self._resolve_training(product_id),
            name=f"learn_normal_{product_id}",
        )

        return {
            "status": "training_started",
            "message": (
                f"Training started with {count} reference images. "
                "Fitting product model artifact and calibrating threshold..."
            ),
            "model_status": ModelStatus.training.value,
            "reference_image_count": count,
            "estimated_seconds": 6,
            # Internal: VLM reference context is active during training
            # This is NOT surfaced in normal UI — only in backend logs/admin
            "_internal_vlm_reference_path": "active_during_training",
        }

    async def _extract_image_bytes(self, storage_url: str) -> Optional[bytes]:
        """Extract raw image bytes from base64 data URI, HTTP URL, or local path."""
        if not storage_url:
            return None
        if storage_url.startswith("data:"):
            try:
                _, b64_part = storage_url.split(",", 1)
                return base64.b64decode(b64_part)
            except Exception as e:
                logger.warning(f"[LearnNormal] Failed decoding base64 data URI: {e}")
                return None
        if storage_url.startswith(("http://", "https://")):
            try:
                import httpx
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.get(storage_url)
                    if resp.status_code == 200:
                        return resp.content
            except Exception as e:
                logger.warning(f"[LearnNormal] Failed downloading image from {storage_url}: {e}")
                return None
        # Local file path
        try:
            clean_path = storage_url.replace("file://", "").strip()
            path = Path(clean_path)
            if path.is_file():
                return path.read_bytes()
        except Exception as e:
            logger.warning(f"[LearnNormal] Failed reading local file {storage_url}: {e}")
            return None
        return None

    async def _resolve_training(self, product_id: str) -> None:
        """
        Background task: consumes the exact uploaded 20–30 GOOD images,
        fits an unsupervised anomaly model (AutoencoderBaseline),
        calibrates threshold on held-out samples, saves new product model
        artifact and profile, and transitions product to 'ready'.
        """
        async with self._get_lock(product_id):
            try:
                async with AsyncSessionLocal() as db:
                    result = await db.execute(
                        select(Product).where(Product.id == uuid.UUID(product_id))
                    )
                    product = result.scalar_one_or_none()
                    if product is None:
                        logger.warning(
                            f"[LearnNormal] Product {product_id} not found during training"
                        )
                        return

                    if product.model_status != ModelStatus.training:
                        # Status was changed externally or training already completed
                        return

                    # Fetch all active reference images for this product
                    ref_res = await db.execute(
                        select(ProductReferenceImage)
                        .where(
                            ProductReferenceImage.product_id == uuid.UUID(product_id),
                            ProductReferenceImage.is_active == True,
                        )
                        .order_by(ProductReferenceImage.created_at.asc())
                    )
                    ref_records = ref_res.scalars().all()

                    if len(ref_records) < MIN_REFERENCE_IMAGES:
                        logger.error(
                            f"[LearnNormal] Product {product_id} has {len(ref_records)} "
                            f"reference images in DB; required {MIN_REFERENCE_IMAGES}. Training failed."
                        )
                        product.model_status = ModelStatus.failed
                        await db.commit()
                        return

                    # Extract exact raw image bytes from storage
                    raw_images: list[bytes] = []
                    for r in ref_records:
                        data = await self._extract_image_bytes(r.storage_url)
                        if data:
                            raw_images.append(data)

                    if len(raw_images) < MIN_REFERENCE_IMAGES:
                        logger.error(
                            f"[LearnNormal] Only {len(raw_images)} valid images could be decoded "
                            f"for {product_id}; required {MIN_REFERENCE_IMAGES}. Training failed."
                        )
                        product.model_status = ModelStatus.failed
                        await db.commit()
                        return

                    category_name = product.code or product.name.lower().replace(" ", "_")
                    output_root = Path(settings.ML_MODEL_ROOT)

                    logger.info(
                        f"[LearnNormal] Consuming {len(raw_images)} exact GOOD images into "
                        f"fitting pipeline for product {product_id} ({product.name})..."
                    )

                    # Execute genuine model fitting and threshold calibration
                    training_result = await asyncio.to_thread(
                        run_training_pipeline,
                        product_id=product_id,
                        category_name=category_name,
                        raw_images=raw_images,
                        output_root=output_root,
                        epochs=5,
                    )

                    # Record calibrated threshold history and update product
                    calibrated_threshold = float(training_result["threshold"])
                    old_threshold = product.threshold

                    db.add(ProductThresholdHistory(
                        product_id=product.id,
                        old_threshold=old_threshold,
                        new_threshold=calibrated_threshold,
                    ))
                    product.threshold = calibrated_threshold
                    product.model_status = ModelStatus.ready
                    await db.commit()

                    # Create profile version snapshot (non-blocking)
                    try:
                        from app.services.profile_versioning import create_profile_version
                        await create_profile_version(
                            product,
                            db,
                            change_reason=f"Learn Normal completed (v{training_result.get('profile_path', 'unknown')})",
                        )
                        await db.commit()
                        logger.info(f"[LearnNormal] Profile version snapshot created for product {product_id}")
                    except Exception as _pv_exc:
                        logger.warning(f"[LearnNormal] Profile version snapshot failed (non-fatal): {_pv_exc}")

                    logger.info(
                        f"[LearnNormal] Training complete for product {product_id}. "
                        f"Fitted {training_result['train_samples']} train samples, "
                        f"calibrated on {training_result['calib_samples']} held-out samples. "
                        f"Threshold: {calibrated_threshold}. "
                        f"Checkpoint: {training_result['checkpoint_path']}. "
                        f"Profile: {training_result['profile_path']}."
                    )

            except Exception as exc:
                logger.error(
                    f"[LearnNormal] Background training pipeline failed for {product_id}: {exc}",
                    exc_info=True,
                )
                try:
                    async with AsyncSessionLocal() as err_db:
                        res = await err_db.execute(
                            select(Product).where(Product.id == uuid.UUID(product_id))
                        )
                        p = res.scalar_one_or_none()
                        if p and p.model_status == ModelStatus.training:
                            p.model_status = ModelStatus.failed
                            await err_db.commit()
                except Exception:
                    pass

    async def get_status(self, product: Product) -> dict:
        """Return the current training status for a product."""
        is_training = product.model_status == ModelStatus.training
        return {
            "product_id": str(product.id),
            "model_status": product.model_status.value,
            "reference_image_count": product.reference_image_count,
            "min_images_required": MIN_REFERENCE_IMAGES,
            "can_start_training": (
                product.reference_image_count >= MIN_REFERENCE_IMAGES
                and product.model_status != ModelStatus.training
            ),
            # VLM reference path is active when training or when ref images exist
            # This is returned in the status so the backend knows — NOT surfaced in UI
            "_internal_vlm_reference_context_active": (
                is_training and product.reference_image_count >= MIN_REFERENCE_IMAGES
            ),
        }


learn_normal_service = LearnNormalService()

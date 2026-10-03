import asyncio
import io
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.db.session import get_db
from app.db.models import Product, ProductReferenceImage, ProductThresholdHistory
from app.schemas.products import (
    ProductCreate, ProductUpdate, ProductResponse,
    ThresholdUpdate, ReferenceImageResponse, ProfileAssignment
)
from app.services.storage.supabase import storage_service
from app.services.heatmap.masks import validate_and_preprocess
from app.core.exceptions import ProductNotFoundError, visionqc_exception_to_http
from app.core.logging import get_logger

router = APIRouter()
logger = get_logger(__name__)


@router.get('/trained-profiles')
async def trained_profiles():
    from app.services.ml.catalog import public_profiles
    return public_profiles()


@router.post('/{product_id}/learn-normal', status_code=status.HTTP_202_ACCEPTED)
async def learn_normal(product_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """
    Start the Learn Normal training workflow for a product.

    Requires at least 20 GOOD reference images to have been uploaded first.
    The endpoint returns immediately (HTTP 202); training continues in the background.
    Poll GET /products/{id}/learn-normal/status or GET /products/{id} to track
    model_status transitions:  not_available → training → ready / validation_required.
    """
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if product is None:
        raise HTTPException(404, 'Product not found.')
    from app.services.ml.learn_normal import learn_normal_service
    try:
        return await learn_normal_service.start(product, db)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@router.get('/{product_id}/learn-normal/status')
async def learn_normal_status(product_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """
    Return the current training status for a product.

    Clients should poll this endpoint (or GET /products/{id}) to track progress.
    """
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if product is None:
        raise HTTPException(404, 'Product not found.')
    from app.services.ml.learn_normal import learn_normal_service, MIN_REFERENCE_IMAGES
    return await learn_normal_service.get_status(product)


@router.put('/{product_id}/model-profile', response_model=ProductResponse)
async def assign_profile(product_id: uuid.UUID, body: ProfileAssignment,
                         db: AsyncSession = Depends(get_db)):
    from app.services.ml.catalog import register_profile
    from app.db.models import ModelStatus
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if product is None:
        raise HTTPException(404, 'Product not found.')
    try:
        register_profile(str(product_id), body.profile_id)
    except ValueError as error:
        raise HTTPException(422, str(error))
    db.add(ProductThresholdHistory(product_id=product.id, old_threshold=product.threshold,
                                   new_threshold=.5))
    product.threshold = .5
    product.model_status = ModelStatus.ready
    await db.commit()
    await db.refresh(product)
    return product


@router.get("", response_model=List[ProductResponse])
async def list_products(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Product).order_by(Product.created_at.desc()))
    return result.scalars().all()


@router.post("", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product(body: ProductCreate, db: AsyncSession = Depends(get_db)):
    product = Product(
        name=body.name,
        code=body.code,
        description=body.description,
        threshold=body.threshold,
    )
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return product


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(product_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")
    return product


@router.patch("/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: uuid.UUID,
    body: ProductUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")

    update_data = body.model_dump(exclude_none=True)
    for key, value in update_data.items():
        setattr(product, key, value)

    await db.commit()
    await db.refresh(product)
    return product


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(product_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")
    await db.delete(product)
    await db.commit()


@router.put("/{product_id}/threshold", response_model=ProductResponse)
@router.patch("/{product_id}/threshold", response_model=ProductResponse)
async def update_threshold(
    product_id: uuid.UUID,
    body: ThresholdUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")

    # Record history
    history = ProductThresholdHistory(
        product_id=product.id,
        old_threshold=product.threshold,
        new_threshold=body.threshold,
    )
    db.add(history)
    product.threshold = body.threshold

    await db.commit()
    await db.refresh(product)
    return product


VALID_IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.webp')


@router.post(
    "/{product_id}/reference-images/zip",
    response_model=List[ReferenceImageResponse],
    status_code=status.HTTP_201_CREATED,
)
async def upload_reference_images_zip(
    product_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Extract and add all valid images from a ZIP archive as product reference images.
    Supports subdirectories, filters out system/hidden files, and commits all at once.
    """
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")

    zip_bytes = await file.read()
    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except Exception as e:
        logger.warning(f"Failed to open zip file for product {product_id}: {e}")
        raise HTTPException(status_code=422, detail="Invalid or corrupted ZIP archive.")

    with zf:
        valid_names = [
            name for name in zf.namelist()
            if name.lower().endswith(VALID_IMAGE_EXTENSIONS)
            and not name.startswith("__MACOSX")
            and not Path(name).name.startswith(".")
            and not name.endswith("/")
        ]

        if not valid_names:
            raise HTTPException(
                status_code=422,
                detail="No valid image files (JPG, PNG, WEBP) found in the ZIP archive.",
            )

        valid_names.sort()

        now = datetime.utcnow()
        sem = asyncio.Semaphore(5)

        async def process_image_entry(name: str):
            async with sem:
                try:
                    img_data = zf.read(name)
                    ext = Path(name).suffix.lower()
                    mime = "image/png" if ext == ".png" else "image/webp" if ext == ".webp" else "image/jpeg"
                    original_bytes, _ = validate_and_preprocess(img_data, mime)
                    storage_url = await storage_service.upload_reference_image(
                        original_bytes, str(product_id)
                    )
                    return ProductReferenceImage(
                        id=uuid.uuid4(),
                        product_id=product.id,
                        storage_url=storage_url,
                        is_active=True,
                        created_at=now,
                    )
                except Exception as e:
                    logger.warning(f"Skipping invalid image '{name}' in zip: {e}")
                    return None

        tasks = [process_image_entry(name) for name in valid_names]
        results = await asyncio.gather(*tasks)
        uploaded_records = [r for r in results if r is not None]

        for rec in uploaded_records:
            db.add(rec)

        if not uploaded_records:
            raise HTTPException(
                status_code=422,
                detail="Could not extract any valid images from the ZIP archive.",
            )

        product.reference_image_count = product.reference_image_count + len(uploaded_records)
        await db.commit()

        logger.info(f"Successfully uploaded {len(uploaded_records)} reference images from zip for product {product_id}")
        return uploaded_records


@router.post(
    "/{product_id}/reference-images",
    response_model=ReferenceImageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_reference_image(
    product_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")

    # Seamlessly support zip uploaded to single image endpoint
    is_zip = (
        (file.filename and file.filename.lower().endswith(".zip"))
        or file.content_type in ("application/zip", "application/x-zip-compressed", "multipart/x-zip")
    )
    if is_zip:
        records = await upload_reference_images_zip(product_id, file, db)
        return records[0]

    # Validate content type
    if file.content_type not in ("image/jpeg", "image/png", "image/webp"):
        raise HTTPException(status_code=422, detail="Unsupported image format.")

    image_bytes = await file.read()
    original_bytes, _ = validate_and_preprocess(image_bytes, file.content_type)

    # Upload to storage
    storage_url = await storage_service.upload_reference_image(
        original_bytes, str(product_id)
    )

    # Save to DB
    ref_image = ProductReferenceImage(
        product_id=product.id,
        storage_url=storage_url,
        is_active=True,
    )
    db.add(ref_image)
    product.reference_image_count = product.reference_image_count + 1
    await db.commit()
    await db.refresh(ref_image)
    return ref_image


@router.get("/{product_id}/reference-images", response_model=List[ReferenceImageResponse])
async def list_reference_images(
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ProductReferenceImage)
        .where(
            ProductReferenceImage.product_id == product_id,
            ProductReferenceImage.is_active == True,
        )
        .order_by(ProductReferenceImage.created_at.desc())
    )
    return result.scalars().all()


@router.delete(
    "/{product_id}/reference-images/{image_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_reference_image(
    product_id: uuid.UUID,
    image_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ProductReferenceImage).where(
            ProductReferenceImage.id == image_id,
            ProductReferenceImage.product_id == product_id,
        )
    )
    ref_image = result.scalar_one_or_none()
    if not ref_image:
        raise HTTPException(status_code=404, detail="Reference image not found.")

    ref_image.is_active = False  # Soft delete

    # Update product count
    prod_result = await db.execute(select(Product).where(Product.id == product_id))
    product = prod_result.scalar_one_or_none()
    if product and product.reference_image_count > 0:
        product.reference_image_count -= 1

    await db.commit()

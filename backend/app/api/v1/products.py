"""Products CRUD API endpoints."""
import uuid
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

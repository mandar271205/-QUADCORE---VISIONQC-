"""
Profile Versioning Service — creates and manages product inspection profile versions.

Policy:
    A new profile version is created when:
    1. Learn Normal completes successfully (model trained)
    2. (Future) Reference set is replaced

    Only ONE version is active per product at any time.
    When a new version is activated, the previous version is deactivated.

    If creating a new profile version fails, the existing active version is
    preserved. We do NOT silently replace a valid profile with a broken one.

    Historical inspections retain their profile_version_id for auditability.
    They are NOT retroactively updated when a new version is activated.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.db.models import Product, ProductProfileVersion
from app.core.logging import get_logger

logger = get_logger(__name__)


async def get_active_profile_version(
    product_id: uuid.UUID,
    db: AsyncSession,
) -> Optional[ProductProfileVersion]:
    """Return the currently active profile version for a product, or None."""
    result = await db.execute(
        select(ProductProfileVersion)
        .where(
            ProductProfileVersion.product_id == product_id,
            ProductProfileVersion.is_active == True,
        )
        .order_by(ProductProfileVersion.version_number.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def create_profile_version(
    product: Product,
    db: AsyncSession,
    *,
    change_reason: str = "Learn Normal completed",
) -> ProductProfileVersion:
    """
    Create a new profile version for a product and deactivate the previous one.

    This should be called AFTER a successful Learn Normal or reference rebuild.
    If the training failed, do NOT call this — preserve the last valid version.

    Returns the new (active) profile version.
    """
    # Find the current active version to chain from
    current_active = await get_active_profile_version(product.id, db)
    next_version_number = 1
    parent_version_id = None

    if current_active:
        next_version_number = current_active.version_number + 1
        parent_version_id = current_active.id
        # Deactivate the current version
        await db.execute(
            update(ProductProfileVersion)
            .where(
                ProductProfileVersion.product_id == product.id,
                ProductProfileVersion.is_active == True,
            )
            .values(is_active=False)
        )
        logger.info(
            f"[ProfileVersioning] Deactivated version {current_active.version_number} "
            f"for product {product.id}"
        )

    new_version = ProductProfileVersion(
        id=uuid.uuid4(),
        product_id=product.id,
        version_number=next_version_number,
        is_active=True,
        reference_image_count=product.reference_image_count,
        threshold_snapshot=product.threshold,
        model_status_snapshot=product.model_status.value,
        change_reason=change_reason,
        parent_version_id=parent_version_id,
        created_at=datetime.utcnow(),
    )
    db.add(new_version)
    logger.info(
        f"[ProfileVersioning] Created version {next_version_number} "
        f"for product {product.id} (reason: {change_reason})"
    )
    return new_version


async def list_profile_versions(
    product_id: uuid.UUID,
    db: AsyncSession,
) -> list[ProductProfileVersion]:
    """Return all profile versions for a product, newest first."""
    result = await db.execute(
        select(ProductProfileVersion)
        .where(ProductProfileVersion.product_id == product_id)
        .order_by(ProductProfileVersion.version_number.desc())
    )
    return list(result.scalars().all())

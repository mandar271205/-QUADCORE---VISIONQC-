from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from uuid import UUID
from app.db.models import ModelStatus


class ProductCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    code: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    threshold: float = Field(default=0.55, ge=0.0, le=1.0)


class ProductUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    code: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    threshold: Optional[float] = Field(None, ge=0.0, le=1.0)


class ProductResponse(BaseModel):
    id: UUID
    name: str
    code: str
    description: Optional[str]
    threshold: float
    model_status: ModelStatus
    reference_image_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProductSummary(BaseModel):
    id: UUID
    name: str
    code: str
    threshold: float
    model_status: ModelStatus
    reference_image_count: int

    model_config = {"from_attributes": True}


class ThresholdUpdate(BaseModel):
    threshold: float = Field(..., ge=0.0, le=1.0)


class ReferenceImageResponse(BaseModel):
    id: UUID
    product_id: UUID
    storage_url: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}

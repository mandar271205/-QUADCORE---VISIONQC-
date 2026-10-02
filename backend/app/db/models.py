"""
SQLAlchemy models for VisionQC.
Compatible with SQLite (local development) and PostgreSQL / Supabase (production).
"""
import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import (
    Column,
    String,
    Text,
    Float,
    Integer,
    Boolean,
    DateTime,
    ForeignKey,
    Enum,
    Uuid,
)
from sqlalchemy.orm import relationship

from app.db.base import Base


class ModelStatus(str, PyEnum):
    not_available = "not_available"
    training = "training"
    ready = "ready"
    validation_required = "validation_required"


class ClientType(str, PyEnum):
    web = "web"
    mobile = "mobile"


class Decision(str, PyEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    REVIEW = "REVIEW"


class Severity(str, PyEnum):
    low = "low"
    medium = "medium"
    high = "high"


class Product(Base):
    __tablename__ = "products"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    code = Column(String(100), nullable=False, unique=True, index=True)
    description = Column(Text, nullable=True)
    threshold = Column(Float, nullable=False, default=0.55)
    model_status = Column(
        Enum(ModelStatus, name="model_status_enum", native_enum=False),
        nullable=False,
        default=ModelStatus.not_available,
    )
    reference_image_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    inspections = relationship("Inspection", back_populates="product", cascade="all, delete-orphan")
    reference_images = relationship("ProductReferenceImage", back_populates="product", cascade="all, delete-orphan")
    threshold_history = relationship("ProductThresholdHistory", back_populates="product", cascade="all, delete-orphan")


class Inspection(Base):
    __tablename__ = "inspections"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id = Column(Uuid(as_uuid=True), ForeignKey("products.id", ondelete="SET NULL"), nullable=True, index=True)
    client_type = Column(
        Enum(ClientType, name="client_type_enum", native_enum=False),
        nullable=False,
        default=ClientType.web,
    )
    decision = Column(
        Enum(Decision, name="decision_enum", native_enum=False),
        nullable=False,
        index=True,
    )
    anomaly_score = Column(Float, nullable=False)
    confidence = Column(Float, nullable=False)
    threshold = Column(Float, nullable=False, default=0.55)
    original_image_url = Column(Text, nullable=True)
    heatmap_url = Column(Text, nullable=True)
    processing_time_ms = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, index=True)

    product = relationship("Product", back_populates="inspections")
    defects = relationship("Defect", back_populates="inspection", cascade="all, delete-orphan")
    runtime = relationship("InspectionRuntime", back_populates="inspection", uselist=False, cascade="all, delete-orphan")


class Defect(Base):
    __tablename__ = "defects"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    inspection_id = Column(Uuid(as_uuid=True), ForeignKey("inspections.id", ondelete="CASCADE"), nullable=False, index=True)
    type = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    severity = Column(
        Enum(Severity, name="severity_enum", native_enum=False),
        nullable=False,
        default=Severity.medium,
    )
    region_x = Column(Float, nullable=True)
    region_y = Column(Float, nullable=True)
    region_width = Column(Float, nullable=True)
    region_height = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    inspection = relationship("Inspection", back_populates="defects")


class InspectionRuntime(Base):
    __tablename__ = "inspection_runtime"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    inspection_id = Column(Uuid(as_uuid=True), ForeignKey("inspections.id", ondelete="CASCADE"), nullable=False)
    engine_type = Column(String(100), nullable=True)
    provider = Column(String(100), nullable=True)
    engine_name = Column(String(255), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    latency_ms = Column(Integer, nullable=True)
    success = Column(Boolean, nullable=False, default=True)
    error_code = Column(String(100), nullable=True)
    error_message = Column(Text, nullable=True)

    inspection = relationship("Inspection", back_populates="runtime")


class ProductReferenceImage(Base):
    __tablename__ = "product_reference_images"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id = Column(Uuid(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    storage_url = Column(Text, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    product = relationship("Product", back_populates="reference_images")


class ProductThresholdHistory(Base):
    __tablename__ = "product_threshold_history"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id = Column(Uuid(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    old_threshold = Column(Float, nullable=False)
    new_threshold = Column(Float, nullable=False)
    changed_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    product = relationship("Product", back_populates="threshold_history")

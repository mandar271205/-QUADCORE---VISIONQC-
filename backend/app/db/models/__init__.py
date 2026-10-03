"""ORM mappings matching docs/supabase_bootstrap.sql (previously absent from Git)."""
import enum
import uuid
from datetime import datetime
from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base


class ModelStatus(str, enum.Enum):
    not_available = "not_available"
    training = "training"
    ready = "ready"
    validation_required = "validation_required"


class ClientType(str, enum.Enum):
    web = "web"
    mobile = "mobile"


class Decision(str, enum.Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    REVIEW = "REVIEW"


class Severity(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"


class Product(Base):
    __tablename__ = "products"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    code: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    threshold: Mapped[float] = mapped_column(Float, default=0.55)
    model_status: Mapped[ModelStatus] = mapped_column(Enum(ModelStatus, name="model_status_enum", native_enum=False), default=ModelStatus.not_available)
    reference_image_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    inspections: Mapped[list["Inspection"]] = relationship(back_populates="product")
    reference_images: Mapped[list["ProductReferenceImage"]] = relationship(cascade="all, delete-orphan")
    threshold_history: Mapped[list["ProductThresholdHistory"]] = relationship(cascade="all, delete-orphan")


class Inspection(Base):
    __tablename__ = "inspections"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"), index=True)
    client_type: Mapped[ClientType] = mapped_column(Enum(ClientType, name="client_type_enum", native_enum=False), default=ClientType.web)
    decision: Mapped[Decision] = mapped_column(Enum(Decision, name="decision_enum", native_enum=False), index=True)
    anomaly_score: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    threshold: Mapped[float] = mapped_column(Float, default=0.55)
    original_image_url: Mapped[str | None] = mapped_column(Text)
    heatmap_url: Mapped[str | None] = mapped_column(Text)
    processing_time_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    product: Mapped[Product | None] = relationship(back_populates="inspections")
    defects: Mapped[list["Defect"]] = relationship(cascade="all, delete-orphan")
    runtime: Mapped[list["InspectionRuntime"]] = relationship(cascade="all, delete-orphan")


class Defect(Base):
    __tablename__ = "defects"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    inspection_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("inspections.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    severity: Mapped[Severity] = mapped_column(Enum(Severity, name="severity_enum", native_enum=False), default=Severity.medium)
    region_x: Mapped[float | None] = mapped_column(Float)
    region_y: Mapped[float | None] = mapped_column(Float)
    region_width: Mapped[float | None] = mapped_column(Float)
    region_height: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class InspectionRuntime(Base):
    __tablename__ = "inspection_runtime"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    inspection_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("inspections.id", ondelete="CASCADE"))
    engine_type: Mapped[str | None] = mapped_column(String(100))
    provider: Mapped[str | None] = mapped_column(String(100))
    engine_name: Mapped[str | None] = mapped_column(String(255))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)


class ProductReferenceImage(Base):
    __tablename__ = "product_reference_images"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    storage_url: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class ProductThresholdHistory(Base):
    __tablename__ = "product_threshold_history"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    old_threshold: Mapped[float] = mapped_column(Float)
    new_threshold: Mapped[float] = mapped_column(Float)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

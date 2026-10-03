"""ORM mappings for VisionQC — Adaptive Inspection Loop edition."""
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
    RETAKE = "RETAKE"  # image-quality failure — NOT a product defect


class Severity(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"


class OperationalSeverity(str, enum.Enum):
    """Operational severity of an inspected unit's deviation.

    Separate from Decision — answers 'how substantial is the deviation?'
    not 'what should happen to this unit?'

    Policy (documented):
        PASS decision              → NONE
        REVIEW with score close    → MINOR (distance < 0.10 from threshold)
        REVIEW with score moderate → MODERATE (distance 0.10-0.20)
        FAIL with score < 0.70     → MODERATE
        FAIL with score >= 0.70    → CRITICAL
        Insufficient evidence      → UNKNOWN
    """
    NONE = "NONE"          # PASS — no meaningful deviation
    MINOR = "MINOR"        # small deviation, review warranted
    MODERATE = "MODERATE"  # meaningful deviation
    CRITICAL = "CRITICAL"  # severe deviation
    UNKNOWN = "UNKNOWN"    # insufficient evidence to determine severity


class ReviewStatus(str, enum.Enum):
    """Status of a human review on a REVIEW-decision inspection."""
    pending = "pending"
    accepted = "accepted"   # supervisor confirmed product is OK
    rejected = "rejected"   # supervisor confirmed product should be rejected


class QualityCheckStatus(str, enum.Enum):
    """Outcome of the image quality gate (NOT product conformity)."""
    good = "good"
    uncertain = "uncertain"
    poor = "poor"
    not_run = "not_run"  # gate was not executed (e.g., demo mode)


class Product(Base):
    __tablename__ = "products"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    code: Mapped[str] = mapped_column(String(100), unique=True)
    # barcode/QR payload for auto profile selection (Feature 6)
    barcode: Mapped[str | None] = mapped_column(String(255), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    threshold: Mapped[float] = mapped_column(Float, default=0.55)
    model_status: Mapped[ModelStatus] = mapped_column(Enum(ModelStatus, name="model_status_enum", native_enum=False), default=ModelStatus.not_available)
    reference_image_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    inspections: Mapped[list["Inspection"]] = relationship(back_populates="product")
    reference_images: Mapped[list["ProductReferenceImage"]] = relationship(cascade="all, delete-orphan")
    threshold_history: Mapped[list["ProductThresholdHistory"]] = relationship(cascade="all, delete-orphan")
    profile_versions: Mapped[list["ProductProfileVersion"]] = relationship(cascade="all, delete-orphan", back_populates="product")


class Inspection(Base):
    __tablename__ = "inspections"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"), index=True)
    client_type: Mapped[ClientType] = mapped_column(Enum(ClientType, name="client_type_enum", native_enum=False), default=ClientType.web)
    decision: Mapped[Decision] = mapped_column(
        Enum(Decision, name="decision_enum", native_enum=False,
             values_callable=lambda x: [e.value for e in x]),
        index=True
    )
    anomaly_score: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    threshold: Mapped[float] = mapped_column(Float, default=0.55)
    original_image_url: Mapped[str | None] = mapped_column(Text)
    heatmap_url: Mapped[str | None] = mapped_column(Text)
    processing_time_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    # ── Adaptive Inspection Loop additions ───────────────────────────────
    # Operational severity (Phase C) — separate from Decision
    operational_severity: Mapped[OperationalSeverity] = mapped_column(
        Enum(OperationalSeverity, name="operational_severity_enum", native_enum=False),
        default=OperationalSeverity.UNKNOWN,
    )
    # Image quality gate outcome (Phase B) — not a product defect
    quality_check_status: Mapped[QualityCheckStatus] = mapped_column(
        Enum(QualityCheckStatus, name="quality_check_status_enum", native_enum=False),
        default=QualityCheckStatus.not_run,
    )
    quality_score: Mapped[float | None] = mapped_column(Float)  # 0-1; None if not run
    quality_issues: Mapped[str | None] = mapped_column(Text)   # JSON list of issue labels
    # Conformity summary from VLM (supervisor-visible)
    conformity_summary: Mapped[str | None] = mapped_column(Text)
    # Batch/shift metadata (Phase 7)
    batch_id: Mapped[str | None] = mapped_column(String(100), index=True)
    shift: Mapped[str | None] = mapped_column(String(50), index=True)
    # Profile version at time of inspection (Phase H)
    profile_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("product_profile_versions.id", ondelete="SET NULL"), nullable=True
    )
    product: Mapped[Product | None] = relationship(back_populates="inspections")
    defects: Mapped[list["Defect"]] = relationship(cascade="all, delete-orphan")
    runtime: Mapped[list["InspectionRuntime"]] = relationship(cascade="all, delete-orphan")
    review: Mapped["InspectionReview | None"] = relationship(
        back_populates="inspection", cascade="all, delete-orphan", uselist=False
    )


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


# ── NEW: Adaptive Inspection Loop Models ────────────────────────────────────


class InspectionReview(Base):
    """
    Human-in-the-loop review record for REVIEW-decision inspections.

    Separates the AI decision from the final supervisor decision.
    Analytics should use human_decision for operational reject-rate once
    a review is completed; ai_decision is preserved for auditability.
    """
    __tablename__ = "inspection_reviews"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    inspection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("inspections.id", ondelete="CASCADE"), unique=True, index=True
    )
    ai_decision: Mapped[Decision] = mapped_column(
        Enum(Decision, name="decision_enum", native_enum=False,
             values_callable=lambda x: [e.value for e in x]),
    )
    human_decision: Mapped[Decision | None] = mapped_column(
        Enum(Decision, name="decision_enum", native_enum=False,
             values_callable=lambda x: [e.value for e in x]),
        nullable=True
    )
    review_status: Mapped[ReviewStatus] = mapped_column(
        Enum(ReviewStatus, name="review_status_enum", native_enum=False),
        default=ReviewStatus.pending,
        index=True,
    )
    note: Mapped[str | None] = mapped_column(Text)  # optional supervisor note
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    inspection: Mapped["Inspection"] = relationship(back_populates="review")


class ProductProfileVersion(Base):
    """
    Versioned record of a product's inspection profile.

    A new version is created when:
    - Learn Normal completes successfully
    - References are materially replaced (future)
    - Threshold is changed via policy (future)

    Only one version should be active per product at any time.
    Historical inspections retain their profile_version_id for auditability.
    """
    __tablename__ = "product_profile_versions"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    reference_image_count: Mapped[int] = mapped_column(Integer, default=0)
    threshold_snapshot: Mapped[float] = mapped_column(Float, default=0.55)
    model_status_snapshot: Mapped[str] = mapped_column(String(50), default="not_available")
    # Human-readable description of what changed
    change_reason: Mapped[str | None] = mapped_column(String(255))
    # Link to parent version for history chain
    parent_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("product_profile_versions.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    product: Mapped["Product"] = relationship(back_populates="profile_versions")


class DriftSnapshot(Base):
    """
    Periodic drift monitoring snapshot for a product.

    Calculated by the analytics service — NOT stored during every inspection.
    Only stored when the drift service is called.

    Policy (documented in drift service):
        Stable       → all signals within baseline
        Watch        → 1-2 signals worsening
        DriftSuspected → 3+ signals worsening OR rejection rate > 2× baseline

    Minimum evidence: 20 inspections in the window before a non-Stable status
    is reported.
    """
    __tablename__ = "drift_snapshots"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    window_days: Mapped[int] = mapped_column(Integer, default=7)
    inspection_count: Mapped[int] = mapped_column(Integer, default=0)
    rejection_rate: Mapped[float] = mapped_column(Float, default=0.0)
    average_anomaly_score: Mapped[float] = mapped_column(Float, default=0.0)
    review_rate: Mapped[float] = mapped_column(Float, default=0.0)
    override_rate: Mapped[float] = mapped_column(Float, default=0.0)
    # Drift status: 'stable' | 'watch' | 'drift_suspected'
    drift_status: Mapped[str] = mapped_column(String(30), default="stable", index=True)
    # JSON blob of which signals are worsening
    worsening_signals: Mapped[str | None] = mapped_column(Text)

from pydantic import BaseModel
from typing import List, Optional, Dict
from datetime import date


class TodayAnalytics(BaseModel):
    total: int
    passed: int
    failed: int
    review: int
    rejection_rate: float
    average_anomaly_score: float
    average_processing_time_ms: float
    # Adaptive Inspection Loop additions
    pending_reviews: int = 0        # pending human reviews in queue
    retake: int = 0                 # image quality failures (not product defects)


class DailyStats(BaseModel):
    date: str  # YYYY-MM-DD
    total: int
    passed: int
    failed: int
    review: int
    rejection_rate: float
    average_anomaly_score: float
    average_processing_time_ms: float


class ProductDistribution(BaseModel):
    product_id: Optional[str]
    product_name: str
    total: int
    failed: int


class AnalyticsResponse(BaseModel):
    daily_stats: List[DailyStats]
    total_inspections: int
    total_passed: int
    total_failed: int
    total_review: int
    overall_rejection_rate: float
    average_anomaly_score: float
    average_processing_time_ms: float
    product_distribution: List[ProductDistribution]
    # Adaptive Inspection Loop additions
    review_rate: float = 0.0        # % of non-retake inspections routed to REVIEW
    override_rate: float = 0.0      # % of reviewed inspections where human overrode AI
    severity_distribution: Dict[str, int] = {}  # severity_label → count
    total_retake: int = 0           # image quality failures in range


class HotspotResponse(BaseModel):
    status: str                     # 'ok' | 'insufficient_data'
    product_id: str
    grid_size: Optional[int] = None
    grid: Optional[List[List[float]]] = None
    contributing_inspections: int = 0
    total_regions: int = 0
    min_evidence_required: Optional[int] = None
    date_range: Optional[dict] = None
    message: Optional[str] = None


class DriftStatusItem(BaseModel):
    product_id: str
    drift_status: str               # 'stable' | 'watch' | 'drift_suspected'
    computed_at: str
    worsening_signals: List[str] = []
    inspection_count: int
    rejection_rate: float


class DriftAllResponse(BaseModel):
    items: List[DriftStatusItem]


class ProfileVersionItem(BaseModel):
    id: str
    product_id: str
    version_number: int
    is_active: bool
    reference_image_count: int
    threshold_snapshot: float
    model_status_snapshot: str
    change_reason: Optional[str] = None
    created_at: str
    parent_version_id: Optional[str] = None


class ProfileVersionListResponse(BaseModel):
    items: List[ProfileVersionItem]
    active_version: Optional[int] = None

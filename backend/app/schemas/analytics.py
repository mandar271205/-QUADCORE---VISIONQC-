from pydantic import BaseModel
from typing import List, Optional
from datetime import date


class TodayAnalytics(BaseModel):
    total: int
    passed: int
    failed: int
    review: int
    rejection_rate: float
    average_anomaly_score: float
    average_processing_time_ms: float


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

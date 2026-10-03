from pydantic import BaseModel, Field
from typing import Optional, List
from uuid import UUID
from datetime import datetime
from app.db.models import Decision, ClientType
from app.schemas.defects import DefectResponse
from app.schemas.common import UTCResponse


class InspectionRequest(BaseModel):
    product_id: Optional[UUID] = None
    client_type: ClientType = ClientType.web
    inspection_mode: Optional[str] = None  # override backend config


class ProductSummaryInInspection(BaseModel):
    id: UUID
    name: str

    model_config = {"from_attributes": True}


class InspectionResponse(UTCResponse):
    """Public API response - NO provider/engine info."""
    inspection_id: UUID
    product: Optional[ProductSummaryInInspection] = None
    decision: Decision
    anomaly_score: float
    confidence: float
    threshold: float
    heatmap_url: Optional[str] = None
    original_image_url: Optional[str] = None
    defects: List[DefectResponse] = []
    summary: str = ""
    processing_time_ms: int
    created_at: datetime

    model_config = {"from_attributes": True}


class InspectionListItem(UTCResponse):
    inspection_id: UUID
    product: Optional[ProductSummaryInInspection] = None
    decision: Decision
    anomaly_score: float
    confidence: float
    threshold: float
    heatmap_url: Optional[str] = None
    original_image_url: Optional[str] = None
    processing_time_ms: int
    created_at: datetime

    model_config = {"from_attributes": True}


class InspectionListResponse(BaseModel):
    items: List[InspectionListItem]
    total: int
    page: int
    page_size: int
    total_pages: int


# Internal schema - NEVER exposed in public API
class InternalInspectionResult(BaseModel):
    """Result from an inspection engine - internal only."""
    decision: Decision
    anomaly_score: float = Field(..., ge=0.0, le=1.0)
    confidence: float = Field(..., ge=0.0, le=1.0)
    defects: List[dict] = []
    summary: str = ""
    anomaly_map: Optional[bytes] = None          # raw heatmap bytes if available
    engine_type: str = "vlm"                      # internal
    provider: str = "unknown"                     # internal
    latency_ms: int = 0                           # internal
    raw_response: Optional[str] = None            # internal debug
    roi_region: Optional[dict] = None             # internal; drawn into heatmap
    threshold: Optional[float] = None             # internal; native model threshold
    # Parallel/hybrid provenance — internal debug only, NEVER in public API responses
    winning_reason: Optional[str] = None          # why this result was chosen
    parallel_provenance: Optional[List[dict]] = None  # [{engine, latency_ms, status}]
    vlm_reference_path_used: bool = False         # VLM inspection used reference images
    model_status_at_inspection: Optional[str] = None  # product model_status snapshot

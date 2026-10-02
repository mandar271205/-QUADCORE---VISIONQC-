"""
ML Inspection Engine Base Class.
This is the adapter interface that the ML team will implement.

When trained models are ready, the ML team creates a concrete subclass here.
The frontend and API never change.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
import numpy as np


@dataclass
class MLInspectionResult:
    """
    Result from a trained ML inspection model.
    
    The ML team must return this structure from their engine.
    """
    anomaly_score: float                     # 0.0–1.0 display scale, not defect probability
    confidence: Optional[float] = None       # optional, 0.0–1.0
    anomaly_map: Optional[np.ndarray] = None # 2D heatmap array, same size as input or smaller
    defects: list = field(default_factory=list)
    latency_ms: int = 0
    model_name: str = "unknown"              # internal debug only
    roi_region: Optional[dict] = None        # normalized product box, internal


class BaseMLEngine(ABC):
    """
    Abstract interface for trained ML inspection engines.
    
    ═══════════════════════════════════════════════════════════════════
    🔧 ML TEAM INTEGRATION POINT
    ═══════════════════════════════════════════════════════════════════
    
    To integrate a trained model, create a new file in:
        backend/app/services/ml/
    
    And subclass this class:
    
        class PatchCoreEngine(BaseMLEngine):
            async def inspect(self, image_bytes, product_id) -> MLInspectionResult:
                ...
            async def load_model(self, product_id: str) -> bool:
                ...
            def is_model_available(self, product_id: str) -> bool:
                ...
    
    Then register it in MLRegistry (registry.py).
    DO NOT modify any FastAPI routes, schemas, or frontend code.
    ═══════════════════════════════════════════════════════════════════
    """

    @abstractmethod
    async def inspect(
        self,
        image_bytes: bytes,
        product_id: Optional[str] = None,
    ) -> MLInspectionResult:
        """Run inference on image bytes.
        
        Args:
            image_bytes: Validated image bytes (lossless PNG for model-only inference)
            product_id: UUID string for product-specific model loading
            
        Returns:
            MLInspectionResult with normalized anomaly_score
        """
        ...

    @abstractmethod
    def is_model_available(self, product_id: Optional[str] = None) -> bool:
        """Returns True if this engine has a trained model for the given product."""
        ...

    @abstractmethod
    async def load_model(self, product_id: str) -> bool:
        """Load model weights for a given product. Returns success status."""
        ...

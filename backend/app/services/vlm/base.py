from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
from app.db.models import Decision


@dataclass
class ProductContext:
    """Context passed to inspection engines for product-aware inspection."""
    product_id: Optional[str] = None
    product_name: Optional[str] = None
    product_description: Optional[str] = None
    threshold: float = 0.55
    reference_images: list = field(default_factory=list)


@dataclass
class VLMInspectionResult:
    """Raw result from a VLM provider - internal only."""
    decision: Decision
    anomaly_score: float
    confidence: float
    defects: list
    summary: str
    provider: str                           # internal - never exposed
    latency_ms: int
    raw_response: Optional[str] = None     # internal debug
    anomaly_regions: list = field(default_factory=list)  # raw bounding boxes


class BaseVLMEngine(ABC):
    """Abstract base for all VLM inspection providers.
    
    All concrete providers must implement inspect().
    Provider names and model details stay here - never leaked to frontend.
    """

    @abstractmethod
    async def inspect(
        self,
        image_bytes: bytes,
        product_context: ProductContext,
    ) -> VLMInspectionResult:
        """Run VLM inspection on image bytes.
        
        Args:
            image_bytes: Raw JPEG/PNG/WebP bytes
            product_context: Product-specific context for guided inspection
            
        Returns:
            VLMInspectionResult with structured result
        """
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this provider is configured and available."""
        ...

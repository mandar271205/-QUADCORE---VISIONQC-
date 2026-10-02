"""
Future ML Model Placeholder.

═══════════════════════════════════════════════════════════════
🔧 ML TEAM: REPLACE THIS FILE WITH YOUR TRAINED MODEL ADAPTER
═══════════════════════════════════════════════════════════════

Integration contract:
    Your engine must subclass BaseMLEngine and return MLInspectionResult.
    Then register it in registry.py.

Example models to integrate here:
    - PatchCore  (anomaly detection via patch feature comparison)
    - PaDiM      (patch distribution modeling)
    - EfficientAD (efficient anomaly detection)
    - Autoencoder (reconstruction-based anomaly detection)

For each model, create a separate file:
    backend/app/services/ml/patchcore.py
    backend/app/services/ml/padim.py
    backend/app/services/ml/efficientad.py
    backend/app/services/ml/autoencoder.py

Each file should implement BaseMLEngine and return MLInspectionResult.

The anomaly_map field (np.ndarray, float32, 0-1 normalized) will be
automatically converted to a heatmap PNG by the HeatmapGenerator.

NO changes needed in:
    - FastAPI routes
    - Pydantic schemas
    - React web application
    - React Native mobile application
═══════════════════════════════════════════════════════════════
"""
from typing import Optional
from app.services.ml.base import BaseMLEngine, MLInspectionResult
from app.core.logging import get_logger

logger = get_logger(__name__)


class FutureMLEngine(BaseMLEngine):
    """
    Placeholder for future trained ML models.
    
    Replace this with your actual model implementation.
    """

    def is_model_available(self, product_id: Optional[str] = None) -> bool:
        # TODO: Check if trained model weights exist for this product
        return False

    async def load_model(self, product_id: str) -> bool:
        # TODO: Load model weights from ML_MODEL_ROOT
        logger.info(f"[FutureML] load_model called for product {product_id} - not implemented yet")
        return False

    async def inspect(
        self,
        image_bytes: bytes,
        product_id: Optional[str] = None,
    ) -> MLInspectionResult:
        # TODO: Run actual model inference
        raise NotImplementedError(
            "FutureMLEngine is a placeholder. "
            "Replace with your trained model implementation."
        )

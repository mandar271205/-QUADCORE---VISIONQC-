"""
Mock ML Engine for development and testing.
Produces deterministic results based on image hash.
Used when DEMO_MODE=true or ML_ENABLED=false.
"""
import hashlib
import time
import numpy as np
from typing import Optional
from app.services.ml.base import BaseMLEngine, MLInspectionResult
from app.core.logging import get_logger

logger = get_logger(__name__)


class MockMLEngine(BaseMLEngine):
    """
    Deterministic mock ML engine.
    Results are based on image hash - same image always gives same result.
    Used for DEMO_MODE and development testing.
    """

    def is_model_available(self, product_id: Optional[str] = None) -> bool:
        return True

    async def load_model(self, product_id: str) -> bool:
        return True

    async def inspect(
        self,
        image_bytes: bytes,
        product_id: Optional[str] = None,
    ) -> MLInspectionResult:
        start = time.time()

        # Deterministic: same image → same result every time
        image_hash = hashlib.sha256(image_bytes).hexdigest()
        seed = int(image_hash[:8], 16)
        rng = np.random.default_rng(seed)

        # 70% PASS, 20% FAIL, 10% REVIEW distribution
        roll = rng.random()
        if roll < 0.70:
            anomaly_score = float(rng.uniform(0.05, 0.45))
            confidence = float(rng.uniform(0.82, 0.97))
        elif roll < 0.90:
            anomaly_score = float(rng.uniform(0.62, 0.95))
            confidence = float(rng.uniform(0.75, 0.92))
        else:
            anomaly_score = float(rng.uniform(0.48, 0.62))
            confidence = float(rng.uniform(0.55, 0.72))

        # Generate synthetic anomaly map
        h, w = 64, 64
        anomaly_map = np.zeros((h, w), dtype=np.float32)

        if anomaly_score > 0.45:
            # Place 1-3 anomaly regions
            num_regions = rng.integers(1, 4)
            for _ in range(num_regions):
                cy = int(rng.uniform(0.1, 0.9) * h)
                cx = int(rng.uniform(0.1, 0.9) * w)
                radius = int(rng.uniform(3, 12))
                y_grid, x_grid = np.ogrid[:h, :w]
                dist = np.sqrt((y_grid - cy) ** 2 + (x_grid - cx) ** 2)
                strength = float(rng.uniform(0.5, 1.0)) * anomaly_score
                anomaly_map += strength * np.exp(-dist**2 / (2 * radius**2))

        anomaly_map = np.clip(anomaly_map, 0.0, 1.0)

        latency_ms = int((time.time() - start) * 1000) + rng.integers(50, 300)

        defects = []
        if anomaly_score > 0.55:
            defects = [
                {
                    "type": "surface_irregularity",
                    "description": "Anomalous surface region detected during inspection.",
                    "severity": "high" if anomaly_score > 0.8 else "medium",
                    "region": {
                        "x": float(rng.uniform(0.2, 0.7)),
                        "y": float(rng.uniform(0.2, 0.7)),
                        "width": float(rng.uniform(0.1, 0.3)),
                        "height": float(rng.uniform(0.1, 0.3)),
                    },
                }
            ]

        logger.debug(f"[MockML] score={anomaly_score:.3f} confidence={confidence:.3f}")

        return MLInspectionResult(
            anomaly_score=anomaly_score,
            confidence=confidence,
            anomaly_map=anomaly_map,
            defects=defects,
            latency_ms=int(latency_ms),
            model_name="mock",
        )

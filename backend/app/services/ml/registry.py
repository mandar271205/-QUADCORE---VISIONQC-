"""
ML Engine Registry.
Maps product IDs to their available ML engines.
"""
from typing import Optional
from app.services.ml.base import BaseMLEngine
from app.services.ml.mock import MockMLEngine
from app.services.ml.future_model import FutureMLEngine
from app.services.ml.profile_engine import ProfileMLEngine
from app.services.ml.member1_engine import Member1PatchCoreEngine
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class MLRegistry:
    """
    Registry for trained ML inspection engines per product.
    
    ═══════════════════════════════════════════════════════════
    🔧 ML TEAM: Register your trained engine here
    ═══════════════════════════════════════════════════════════
    
    After implementing your engine (e.g. PatchCoreEngine), add it:
    
        from app.services.ml.patchcore import PatchCoreEngine
        
        REGISTERED_ENGINES = [
            PatchCoreEngine(),
            FutureMLEngine(),
        ]
    
    The router will automatically use it when ML_ENABLED=true.
    ═══════════════════════════════════════════════════════════
    """

    # TODO ML TEAM: Register your trained engine here
    _engines: list[BaseMLEngine] = [
        Member1PatchCoreEngine(),
        ProfileMLEngine(),
        FutureMLEngine(),
    ]

    @classmethod
    def get(cls, product_id: Optional[str] = None) -> Optional[BaseMLEngine]:
        """Get the best available ML engine for a given product."""
        if settings.DEMO_MODE:
            return MockMLEngine()

        for engine in cls._engines:
            if getattr(engine, "is_member1", False):
                if not settings.ML_M1_ENABLED:
                    continue
            elif not settings.ML_ENABLED:
                continue
            if engine.is_model_available(product_id):
                return engine

        logger.debug(f"[MLRegistry] No trained model available for product {product_id}")
        return None

    @classmethod
    def get_mock(cls) -> MockMLEngine:
        """Always returns the mock engine."""
        return MockMLEngine()

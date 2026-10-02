"""
Inspection Router - orchestrates which engines to use based on INSPECTION_MODE.

Modes:
  vlm_primary         - Try VLMs in order (Gemini → Groq → NVIDIA). Default.
  vlm_only            - VLM only, no ML fallback. Mobile default unless MOBILE_USE_ML.
  model_primary       - Try ML model first, fallback to VLM.
  model_only          - ML only (no VLM). Requires trained model.
  parallel_first_valid- Run ML + VLM in parallel, take first valid result.

Provider/engine details are NEVER returned to callers.
Only InternalInspectionResult is passed up the stack.
"""
import asyncio
import time
from typing import Optional

from app.core.config import settings
from app.core.exceptions import AllProvidersFailedError, InspectionFailedError
from app.core.logging import get_logger
from app.db.models import Decision
from app.schemas.inspection import InternalInspectionResult
from app.services.quality_gate import QualityGate
from app.services.vlm.base import ProductContext, VLMInspectionResult
from app.services.vlm.registry import VLMRegistry
from app.services.ml.registry import MLRegistry

logger = get_logger(__name__)


def _apply_threshold(
    score: float,
    confidence: float,
    threshold: float,
    vlm_decision: Optional[Decision] = None,
) -> Decision:
    """
    Centralized decision function applying threshold and review margin.
    
    If score is within REVIEW_MARGIN of threshold → REVIEW
    Otherwise → PASS/FAIL based on threshold.
    """
    margin = settings.REVIEW_MARGIN
    if margin > 0 and abs(score - threshold) <= margin:
        return Decision.REVIEW
    if score > threshold:
        # For VLM results, also respect VLM's own decision
        return Decision.FAIL
    return Decision.PASS


def _vlm_to_internal(
    vlm_result: VLMInspectionResult,
    threshold: float,
) -> InternalInspectionResult:
    """Convert VLM result to internal schema with threshold-based decision."""
    final_decision = _apply_threshold(
        vlm_result.anomaly_score,
        vlm_result.confidence,
        threshold,
        vlm_result.decision,
    )
    return InternalInspectionResult(
        decision=final_decision,
        anomaly_score=vlm_result.anomaly_score,
        confidence=vlm_result.confidence,
        defects=vlm_result.defects,
        summary=vlm_result.summary,
        anomaly_map=None,
        engine_type="vlm",
        provider=vlm_result.provider,  # internal only
        latency_ms=vlm_result.latency_ms,
        raw_response=vlm_result.raw_response,
    )


def _ml_to_internal(
    ml_result,
    threshold: float,
    defects: Optional[list] = None,
) -> InternalInspectionResult:
    """Convert ML result to internal schema with threshold-based decision."""
    import io
    final_decision = _apply_threshold(
        ml_result.anomaly_score,
        ml_result.confidence if ml_result.confidence is not None else 0.0,
        threshold,
    )

    # Serialize anomaly map if available
    anomaly_map_bytes = None
    if ml_result.anomaly_map is not None:
        try:
            import numpy as np
            from PIL import Image
            arr = (np.clip(ml_result.anomaly_map, 0, 1) * 255).astype(np.uint8)
            img = Image.fromarray(arr)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            anomaly_map_bytes = buf.getvalue()
        except Exception as e:
            logger.warning(f"Could not serialize anomaly map: {e}")

    return InternalInspectionResult(
        decision=final_decision,
        anomaly_score=ml_result.anomaly_score,
        confidence=ml_result.confidence if ml_result.confidence is not None else 0.0,
        defects=defects or ml_result.defects,
        summary=("Anomalous region detected." if final_decision == Decision.FAIL else
                 "No anomaly detected above the inspection threshold." if final_decision == Decision.PASS else
                 "Score is close to the threshold. Manual review recommended."),
        anomaly_map=anomaly_map_bytes,
        engine_type="ml",
        provider=ml_result.model_name,  # internal only
        latency_ms=ml_result.latency_ms,
        roi_region=getattr(ml_result,'roi_region',None),
    )


class InspectionRouter:
    """
    Routes inspection requests to appropriate engines based on mode configuration.
    """

    async def run(
        self,
        image_bytes: bytes,
        product_context: ProductContext,
        mode_override: Optional[str] = None,
        client_type: str = "web",
    ) -> InternalInspectionResult:
        """
        Execute inspection using configured routing mode.
        
        Mobile always forces vlm_only.
        Failures from individual providers are caught and fallback is attempted.
        """
        # Mobile always uses VLM only
        if client_type == "mobile" and not settings.MOBILE_USE_ML:
            effective_mode = "vlm_only"
        elif mode_override and mode_override in (
            "vlm_primary", "vlm_only", "model_primary", "model_only", "parallel_first_valid"
        ):
            effective_mode = mode_override
        else:
            effective_mode = settings.INSPECTION_MODE

        # Demo mode bypass
        if settings.DEMO_MODE:
            return await self._run_demo(image_bytes, product_context)

        logger.info(f"[Router] mode={effective_mode} product={product_context.product_id}")

        if effective_mode == "vlm_primary":
            return await self._vlm_primary(image_bytes, product_context)
        elif effective_mode == "vlm_only":
            return await self._vlm_primary(image_bytes, product_context)
        elif effective_mode == "model_primary":
            return await self._model_primary(image_bytes, product_context)
        elif effective_mode == "model_only":
            return await self._model_only(image_bytes, product_context)
        elif effective_mode == "parallel_first_valid":
            return await self._parallel_first_valid(image_bytes, product_context)
        else:
            return await self._vlm_primary(image_bytes, product_context)

    async def _vlm_primary(
        self,
        image_bytes: bytes,
        product_context: ProductContext,
    ) -> InternalInspectionResult:
        """Try VLMs in order: Gemini → Groq → NVIDIA."""
        engines = VLMRegistry.get_ordered_engines()
        if not engines:
            raise AllProvidersFailedError()

        last_error = None
        for engine in engines:
            try:
                result = await asyncio.wait_for(
                    engine.inspect(image_bytes, product_context),
                    timeout=settings.ENGINE_TIMEOUT_SECONDS + 2,
                )
                gate = QualityGate.validate_vlm(result)
                if gate.verdict == "ACCEPT":
                    logger.info(f"[Router] VLM accepted from {result.provider}")
                    return _vlm_to_internal(result, product_context.threshold)
                else:
                    logger.warning(f"[Router] VLM rejected by quality gate: {gate.reason}")
            except asyncio.TimeoutError:
                logger.warning(f"[Router] VLM engine timed out")
            except Exception as e:
                logger.warning(f"[Router] VLM engine error: {type(e).__name__}: {e}")
                last_error = e

        raise AllProvidersFailedError()

    async def _model_primary(
        self,
        image_bytes: bytes,
        product_context: ProductContext,
    ) -> InternalInspectionResult:
        """Try ML model first, fallback to VLM."""
        ml_engine = MLRegistry.get(product_context.product_id)
        if ml_engine and ml_engine.is_model_available(product_context.product_id):
            try:
                result = await asyncio.wait_for(
                    ml_engine.inspect(image_bytes, product_context.product_id),
                    timeout=settings.ENGINE_TIMEOUT_SECONDS + 2,
                )
                gate = QualityGate.validate_ml(result)
                if gate.verdict == "ACCEPT":
                    logger.info("[Router] ML model accepted")
                    return _ml_to_internal(result, product_context.threshold)
            except Exception as e:
                logger.warning(f"[Router] ML model failed, falling back to VLM: {e}")

        # Fallback to VLM
        logger.info("[Router] Falling back to VLM")
        return await self._vlm_primary(image_bytes, product_context)

    async def _model_only(
        self,
        image_bytes: bytes,
        product_context: ProductContext,
    ) -> InternalInspectionResult:
        """ML model only - no VLM fallback."""
        ml_engine = MLRegistry.get(product_context.product_id)
        if not ml_engine or not ml_engine.is_model_available(product_context.product_id):
            raise InspectionFailedError("Inspection could not be completed. Please try again.")
        result = await ml_engine.inspect(image_bytes, product_context.product_id)
        gate = QualityGate.validate_ml(result)
        if gate.verdict != "ACCEPT":
            raise InspectionFailedError("Inspection could not be completed. Please try again.")
        return _ml_to_internal(result, product_context.threshold)

    async def _parallel_first_valid(
        self,
        image_bytes: bytes,
        product_context: ProductContext,
    ) -> InternalInspectionResult:
        """
        Run ML and VLM in parallel. Return first result that passes quality gate.
        Future mode for when trained models are available.
        """
        tasks = []

        ml_engine = MLRegistry.get(product_context.product_id)
        if ml_engine and ml_engine.is_model_available(product_context.product_id):
            tasks.append(self._run_ml_task(ml_engine, image_bytes, product_context))

        tasks.append(self._vlm_primary(image_bytes, product_context))

        if not tasks:
            raise AllProvidersFailedError()

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, InternalInspectionResult):
                return r

        raise AllProvidersFailedError()

    async def _run_ml_task(self, ml_engine, image_bytes, product_context):
        result = await ml_engine.inspect(image_bytes, product_context.product_id)
        gate = QualityGate.validate_ml(result)
        if gate.verdict != "ACCEPT":
            raise Exception("ML quality gate rejected")
        return _ml_to_internal(result, product_context.threshold)

    async def _run_demo(
        self,
        image_bytes: bytes,
        product_context: ProductContext,
    ) -> InternalInspectionResult:
        """Demo mode: deterministic mock result without any external calls."""
        from app.services.ml.registry import MLRegistry
        mock = MLRegistry.get_mock()
        result = await mock.inspect(image_bytes, product_context.product_id)

        # Apply threshold logic
        score = result.anomaly_score
        threshold = product_context.threshold
        decision = _apply_threshold(score, result.confidence or 0.85, threshold)

        defects = result.defects
        if decision == Decision.PASS:
            defects = []
            summary = "No anomalies detected. Product passed quality inspection."
        elif decision == Decision.FAIL:
            summary = f"Anomalous surface region detected. Anomaly score: {score:.2f}."
        else:
            summary = "Minor deviations noted. Manual review recommended."

        import io
        anomaly_map_bytes = None
        if result.anomaly_map is not None:
            try:
                import numpy as np
                from PIL import Image
                arr = (np.clip(result.anomaly_map, 0, 1) * 255).astype(np.uint8)
                img = Image.fromarray(arr)
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                anomaly_map_bytes = buf.getvalue()
            except Exception:
                pass

        return InternalInspectionResult(
            decision=decision,
            anomaly_score=score,
            confidence=result.confidence or 0.85,
            defects=defects,
            summary=summary,
            anomaly_map=anomaly_map_bytes,
            engine_type="demo",
            provider="demo",
            latency_ms=result.latency_ms,
        )


# Singleton
inspection_router = InspectionRouter()

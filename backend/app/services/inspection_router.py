"""
Inspection Router — orchestrates hybrid ML + VLM inspection.

Routing modes:
  vlm_primary         - Try VLMs in order (Gemini → Groq → NVIDIA). Default.
  vlm_only            - VLM only, no ML. Mobile default unless MOBILE_USE_ML.
  model_primary       - Try ML first; VLM fallback on unavailable/error/timeout.
  model_only          - ML only (no VLM). Requires trained model.
  parallel_first_valid- Launch ML + VLM concurrently; first VALID result wins.

Hybrid "Learn Normal" behavior:
  - While model_status == training AND mode permits VLM → inspection continues
    via reference-aware VLM path (uses uploaded GOOD reference images as context).
  - When ML becomes ready → it automatically participates in subsequent inspections.
  - model_only always refuses VLM fallback regardless of training status.

PROVENANCE RULES:
  - engine_type / provider are truthful internal fields persisted to InspectionRuntime.
  - winning_reason / parallel_provenance are internal audit fields.
  - None of these fields appear in any public API response (InspectionResponse).
  - The normal UI never receives or displays engine/provider names.
"""
from __future__ import annotations

import asyncio
import time
from typing import Optional

from app.core.config import settings
from app.core.exceptions import AllProvidersFailedError, InspectionFailedError
from app.core.logging import get_logger
from app.db.models import Decision, ModelStatus
from app.schemas.inspection import InternalInspectionResult
from app.services.quality_gate import QualityGate
from app.services.vlm.base import ProductContext, VLMInspectionResult
from app.services.vlm.registry import VLMRegistry
from app.services.ml.registry import MLRegistry

logger = get_logger(__name__)

# How close to the threshold triggers REVIEW decision
_REVIEW_MARGIN = None  # uses settings.REVIEW_MARGIN


def resolve_inspection_mode(mode_override: Optional[str], client_type: str) -> str:
    """Use the same route for preprocessing, profile checks and inference."""
    if client_type == 'mobile' and not settings.MOBILE_USE_ML:
        return 'vlm_only'
    if mode_override in ('vlm_primary', 'vlm_only', 'model_primary', 'model_only', 'parallel_first_valid'):
        return mode_override
    return settings.INSPECTION_MODE


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
        return Decision.FAIL
    return Decision.PASS


def _vlm_to_internal(
    vlm_result: VLMInspectionResult,
    threshold: float,
    *,
    winning_reason: str = "vlm_result",
    parallel_provenance: Optional[list] = None,
    vlm_reference_path_used: bool = False,
    model_status_at_inspection: Optional[str] = None,
) -> InternalInspectionResult:
    """Convert VLM result to internal schema with threshold-based decision."""
    final_decision = _apply_threshold(
        vlm_result.anomaly_score,
        vlm_result.confidence,
        threshold,
        vlm_result.decision,
    )
    # Build anomaly_map from VLM regions if present, else None
    anomaly_map_bytes = _vlm_regions_to_map(vlm_result)

    return InternalInspectionResult(
        decision=final_decision,
        anomaly_score=vlm_result.anomaly_score,
        confidence=vlm_result.confidence,
        defects=vlm_result.defects,
        summary=vlm_result.summary,
        anomaly_map=anomaly_map_bytes,
        engine_type="vlm",
        provider=vlm_result.provider,           # internal only
        latency_ms=vlm_result.latency_ms,
        raw_response=vlm_result.raw_response,
        winning_reason=winning_reason,
        parallel_provenance=parallel_provenance,
        vlm_reference_path_used=vlm_reference_path_used,
        model_status_at_inspection=model_status_at_inspection,
    )


def _vlm_regions_to_map(vlm_result: VLMInspectionResult) -> Optional[bytes]:
    """
    If a VLM result contains anomaly_regions (bounding boxes), convert them
    to a normalized float heatmap PNG for the heatmap pipeline.
    Returns None when no defensible localization is available.
    """
    regions = getattr(vlm_result, 'anomaly_regions', None)
    if not regions:
        return None
    try:
        import io
        import numpy as np
        from PIL import Image
        # Build 64×64 map from normalized bounding boxes
        H, W = 64, 64
        amap = np.zeros((H, W), dtype=np.float32)
        for r in regions:
            x1 = int(r.get('x', 0) * W)
            y1 = int(r.get('y', 0) * H)
            x2 = int((r.get('x', 0) + r.get('width', 0)) * W)
            y2 = int((r.get('y', 0) + r.get('height', 0)) * H)
            weight = float(r.get('confidence', 1.0))
            amap[y1:y2, x1:x2] = np.maximum(amap[y1:y2, x1:x2], weight)
        arr = (np.clip(amap, 0, 1) * 255).astype(np.uint8)
        buf = io.BytesIO()
        Image.fromarray(arr).save(buf, format='PNG')
        return buf.getvalue()
    except Exception:
        return None


def _ml_to_internal(
    ml_result,
    threshold: float,
    defects: Optional[list] = None,
    *,
    winning_reason: str = "ml_result",
    parallel_provenance: Optional[list] = None,
    model_status_at_inspection: Optional[str] = None,
) -> InternalInspectionResult:
    """Convert ML result to internal schema with threshold-based decision."""
    import io
    final_decision = _apply_threshold(
        ml_result.anomaly_score,
        ml_result.confidence if ml_result.confidence is not None else 0.0,
        threshold,
    )
    native_verdict = getattr(ml_result, "native_verdict", None)
    if native_verdict in (Decision.PASS.value, Decision.FAIL.value):
        final_decision = Decision(native_verdict)
    result_threshold = getattr(ml_result, "threshold", None)

    # Serialize anomaly map if available
    anomaly_map_bytes = None
    if ml_result.anomaly_map is not None:
        try:
            import numpy as np
            from PIL import Image
            anomaly_map = np.asarray(ml_result.anomaly_map, dtype=np.float32)
            if native_verdict is not None:
                low, high = float(np.min(anomaly_map)), float(np.max(anomaly_map))
                anomaly_map = ((anomaly_map - low) / (high - low)
                               if high > low else np.zeros_like(anomaly_map))
            arr = (np.clip(anomaly_map, 0, 1) * 255).astype(np.uint8)
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
        summary=(
            "Anomalous region detected." if final_decision == Decision.FAIL else
            "No anomaly detected above the inspection threshold." if final_decision == Decision.PASS else
            "Score is close to the threshold. Manual review recommended."
        ),
        anomaly_map=anomaly_map_bytes,
        engine_type="ml",
        provider=ml_result.model_name,          # internal only
        latency_ms=ml_result.latency_ms,
        roi_region=getattr(ml_result, 'roi_region', None),
        threshold=result_threshold,
        winning_reason=winning_reason,
        parallel_provenance=parallel_provenance,
        model_status_at_inspection=model_status_at_inspection,
    )


class InspectionRouter:
    """
    Routes inspection requests to appropriate engines based on mode configuration.

    Normal UI NEVER receives engine_type, provider, winning_reason, or parallel_provenance.
    These are internal-only fields persisted to InspectionRuntime for auditability.
    """

    async def run(
        self,
        image_bytes: bytes,
        product_context: ProductContext,
        mode_override: Optional[str] = None,
        client_type: str = "web",
        model_status: Optional[str] = None,
    ) -> InternalInspectionResult:
        """
        Execute inspection using configured routing mode.

        model_status: current Product.model_status value — used to decide whether
        inspection-while-training is allowed via VLM reference path.
        """
        effective_mode = resolve_inspection_mode(mode_override, client_type)

        # Demo mode bypass
        if settings.DEMO_MODE:
            return await self._run_demo(image_bytes, product_context, model_status=model_status)

        logger.info(
            f"[Router] mode={effective_mode} product={product_context.product_id} "
            f"model_status={model_status}"
        )

        # ── Inspection-while-training ──────────────────────────────────────
        # If ML is still training AND mode permits VLM, use the VLM reference path.
        # model_only NEVER allows this — preserve its strict semantics.
        if (
            model_status == ModelStatus.training.value
            and effective_mode not in ('model_only',)
            and effective_mode in ('vlm_primary', 'vlm_only', 'model_primary', 'parallel_first_valid')
        ):
            logger.info(
                f"[Router] ML status=training — routing via VLM reference path "
                f"(mode={effective_mode})"
            )
            return await self._vlm_reference_path(
                image_bytes, product_context,
                reason="vlm_reference_path_while_training",
                model_status_snapshot=model_status,
            )

        if effective_mode == "vlm_primary":
            return await self._vlm_primary(image_bytes, product_context, model_status_snapshot=model_status)
        elif effective_mode == "vlm_only":
            return await self._vlm_primary(image_bytes, product_context, model_status_snapshot=model_status)
        elif effective_mode == "model_primary":
            return await self._model_primary(image_bytes, product_context, model_status_snapshot=model_status)
        elif effective_mode == "model_only":
            return await self._model_only(image_bytes, product_context, model_status_snapshot=model_status)
        elif effective_mode == "parallel_first_valid":
            return await self._parallel_first_valid(image_bytes, product_context, model_status_snapshot=model_status)
        else:
            return await self._vlm_primary(image_bytes, product_context, model_status_snapshot=model_status)

    # ── VLM reference path (used while ML is training) ─────────────────────

    async def _vlm_reference_path(
        self,
        image_bytes: bytes,
        product_context: ProductContext,
        *,
        reason: str = "vlm_reference_path",
        model_status_snapshot: Optional[str] = None,
    ) -> InternalInspectionResult:
        """
        Run VLM inspection enriched with reference images as visual context.

        The product_context.reference_images list is pre-populated by the
        inspections API from the DB before calling the router. This gives the VLM
        access to the uploaded GOOD images as reference context.

        Truthful internal label: engine_type='vlm', provider=<actual provider>.
        NOT labelled as ML training — do not falsify provenance.
        """
        engines = VLMRegistry.get_ordered_engines()
        if not engines:
            raise AllProvidersFailedError()

        for engine in engines:
            try:
                result = await asyncio.wait_for(
                    engine.inspect(image_bytes, product_context),
                    timeout=settings.ENGINE_TIMEOUT_SECONDS + 2,
                )
                gate = QualityGate.validate_vlm(result)
                if gate.verdict == "ACCEPT":
                    logger.info(
                        f"[Router] VLM reference path accepted from {result.provider} "
                        f"(ref_images={len(product_context.reference_images)})"
                    )
                    return _vlm_to_internal(
                        result, product_context.threshold,
                        winning_reason=reason,
                        vlm_reference_path_used=len(product_context.reference_images) > 0,
                        model_status_at_inspection=model_status_snapshot,
                    )
            except asyncio.TimeoutError:
                logger.warning("[Router] VLM reference path engine timed out")
            except Exception as e:
                logger.warning(f"[Router] VLM reference path engine error: {e}")

        raise AllProvidersFailedError()

    # ── Standard modes ─────────────────────────────────────────────────────

    async def _vlm_primary(
        self,
        image_bytes: bytes,
        product_context: ProductContext,
        *,
        model_status_snapshot: Optional[str] = None,
    ) -> InternalInspectionResult:
        """Try VLMs in order: Gemini → Groq → NVIDIA."""
        engines = VLMRegistry.get_ordered_engines()
        if not engines:
            logger.error("[Router] No external VLM API keys configured")
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
                    return _vlm_to_internal(
                        result, product_context.threshold,
                        winning_reason="vlm_accepted",
                        vlm_reference_path_used=len(product_context.reference_images) > 0,
                        model_status_at_inspection=model_status_snapshot,
                    )
                else:
                    logger.warning(f"[Router] VLM rejected by quality gate: {gate.reason}")
            except asyncio.TimeoutError:
                logger.warning("[Router] VLM engine timed out")
            except Exception as e:
                logger.warning(f"[Router] VLM engine error: {type(e).__name__}: {e}")
                last_error = e

        raise AllProvidersFailedError()

    async def _model_primary(
        self,
        image_bytes: bytes,
        product_context: ProductContext,
        *,
        model_status_snapshot: Optional[str] = None,
    ) -> InternalInspectionResult:
        """Try ML model first, fallback to VLM."""
        ml_engine = MLRegistry.get(product_context.product_id)
        if ml_engine and ml_engine.is_model_available(product_context.product_id):
            try:
                result = await asyncio.wait_for(
                    ml_engine.inspect(image_bytes, product_context.product_id),
                    timeout=self._ml_timeout(ml_engine),
                )
                gate = QualityGate.validate_ml(result)
                if gate.verdict == "ACCEPT":
                    logger.info("[Router] ML model accepted (model_primary)")
                    return _ml_to_internal(
                        result, product_context.threshold,
                        winning_reason="ml_primary_accepted",
                        model_status_at_inspection=model_status_snapshot,
                    )
            except Exception as e:
                logger.warning(f"[Router] ML model failed, falling back to VLM: {e}")

        logger.info("[Router] Falling back to VLM (model_primary)")
        return await self._vlm_primary(
            image_bytes, product_context,
            model_status_snapshot=model_status_snapshot,
        )

    async def _model_only(
        self,
        image_bytes: bytes,
        product_context: ProductContext,
        *,
        model_status_snapshot: Optional[str] = None,
    ) -> InternalInspectionResult:
        """ML model only — no VLM fallback under any circumstances."""
        ml_engine = MLRegistry.get(product_context.product_id)
        if not ml_engine or not ml_engine.is_model_available(product_context.product_id):
            raise InspectionFailedError("Inspection could not be completed. Please try again.")
        try:
            result = await asyncio.wait_for(
                ml_engine.inspect(image_bytes, product_context.product_id),
                timeout=self._ml_timeout(ml_engine),
            )
        except asyncio.TimeoutError as error:
            logger.warning("[Router] ML-only model timed out")
            raise InspectionFailedError("Inspection could not be completed. Please try again.") from error
        gate = QualityGate.validate_ml(result)
        if gate.verdict != "ACCEPT":
            raise InspectionFailedError("Inspection could not be completed. Please try again.")
        return _ml_to_internal(
            result, product_context.threshold,
            winning_reason="ml_only_accepted",
            model_status_at_inspection=model_status_snapshot,
        )

    async def _parallel_first_valid(
        self,
        image_bytes: bytes,
        product_context: ProductContext,
        *,
        model_status_snapshot: Optional[str] = None,
    ) -> InternalInspectionResult:
        """
        Launch ML and VLM concurrently. Return first result that passes
        its engine-specific quality gate.

        Implementation uses asyncio.create_task + asyncio.wait(FIRST_COMPLETED)
        so both engines genuinely start simultaneously. The loser is cancelled.

        INVALID results do NOT win — a fast invalid result is discarded and
        we wait for the other engine's result.

        On ML/VLM disagreement (both complete and disagree by > threshold margin):
        we prefer REVIEW to mask false certainty.

        Score spaces are NOT compared numerically — they are independent.
        """
        provenance: list[dict] = []
        tasks: dict[asyncio.Task, str] = {}  # task → engine label

        ml_engine = MLRegistry.get(product_context.product_id)
        if ml_engine and ml_engine.is_model_available(product_context.product_id):
            ml_task = asyncio.create_task(
                self._run_ml_task(ml_engine, image_bytes, product_context),
                name="parallel_ml",
            )
            tasks[ml_task] = "ml"

        vlm_task = asyncio.create_task(
            self._run_vlm_task(image_bytes, product_context),
            name="parallel_vlm",
        )
        tasks[vlm_task] = "vlm"

        if not tasks:
            raise AllProvidersFailedError()

        pending = set(tasks)
        winner: Optional[InternalInspectionResult] = None
        winner_label: Optional[str] = None
        runner_up: Optional[InternalInspectionResult] = None

        # Bounded decision window: wait for both within ENGINE_TIMEOUT_SECONDS
        deadline = settings.ENGINE_TIMEOUT_SECONDS + 2

        while pending and winner is None:
            done, pending = await asyncio.wait(
                pending,
                return_when=asyncio.FIRST_COMPLETED,
                timeout=deadline,
            )

            if not done:
                # deadline expired — no results yet
                break

            for finished in done:
                label = tasks[finished]
                try:
                    result: InternalInspectionResult = finished.result()
                    provenance.append({
                        "engine": label,
                        "latency_ms": result.latency_ms,
                        "status": "valid",
                        "provider": result.provider,
                    })
                    if winner is None:
                        winner = result
                        winner_label = label
                    else:
                        # Both completed; check for disagreement
                        runner_up = result
                except Exception as exc:
                    provenance.append({
                        "engine": label,
                        "latency_ms": 0,
                        "status": f"invalid:{type(exc).__name__}",
                    })
                    logger.debug(f"[Router] Parallel {label} invalid: {exc}")

        # Cancel remaining tasks
        for t in pending:
            t.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(t), timeout=0.5)
            except Exception:
                pass

        if winner is None:
            raise AllProvidersFailedError()

        # Disagreement handling: if both engines returned AND they disagree on
        # PASS vs FAIL (with neither being REVIEW), escalate to REVIEW.
        if runner_up is not None:
            w_decision = winner.decision
            r_decision = runner_up.decision
            if (
                {w_decision, r_decision} == {Decision.PASS, Decision.FAIL}
                and w_decision != Decision.REVIEW
                and r_decision != Decision.REVIEW
            ):
                logger.info(
                    f"[Router] ML/VLM disagreement: "
                    f"{winner_label}={w_decision} vs other={r_decision} → REVIEW"
                )
                # Preserve winning result but escalate decision
                winner = winner.model_copy(update={
                    "decision": Decision.REVIEW,
                    "winning_reason": f"parallel_disagreement_escalated_to_review "
                                     f"({winner_label}={w_decision} vs other={r_decision})",
                    "parallel_provenance": provenance,
                    "model_status_at_inspection": model_status_snapshot,
                })
                return winner

        winning_reason = (
            f"parallel_first_valid_{winner_label}_won"
            if runner_up is None
            else f"parallel_first_valid_{winner_label}_won_consensus"
        )
        winner = winner.model_copy(update={
            "winning_reason": winning_reason,
            "parallel_provenance": provenance,
            "model_status_at_inspection": model_status_snapshot,
        })
        return winner

    # ── Task helpers ────────────────────────────────────────────────────────

    async def _run_ml_task(
        self,
        ml_engine,
        image_bytes: bytes,
        product_context: ProductContext,
    ) -> InternalInspectionResult:
        """Run ML engine and validate; raises on invalid."""
        result = await asyncio.wait_for(
            ml_engine.inspect(image_bytes, product_context.product_id),
            timeout=self._ml_timeout(ml_engine),
        )
        gate = QualityGate.validate_ml(result)
        if gate.verdict != "ACCEPT":
            raise ValueError(f"ML quality gate rejected: {gate.reason}")
        return _ml_to_internal(result, product_context.threshold, winning_reason="parallel_ml_valid")

    async def _run_vlm_task(
        self,
        image_bytes: bytes,
        product_context: ProductContext,
    ) -> InternalInspectionResult:
        """Run VLM engines in fallback order and validate; raises on all-failed."""
        engines = VLMRegistry.get_ordered_engines()
        for engine in engines:
            try:
                result = await asyncio.wait_for(
                    engine.inspect(image_bytes, product_context),
                    timeout=settings.ENGINE_TIMEOUT_SECONDS + 2,
                )
                gate = QualityGate.validate_vlm(result)
                if gate.verdict == "ACCEPT":
                    return _vlm_to_internal(
                        result, product_context.threshold,
                        winning_reason="parallel_vlm_valid",
                        vlm_reference_path_used=len(product_context.reference_images) > 0,
                    )
            except Exception:
                continue
        raise AllProvidersFailedError()

    @staticmethod
    def _ml_timeout(ml_engine) -> int:
        if getattr(ml_engine, "is_member1", False):
            return max(1, settings.ML_M1_WORKER_STARTUP_TIMEOUT) + max(1, settings.ML_M1_REQUEST_TIMEOUT)
        return settings.ENGINE_TIMEOUT_SECONDS + 2

    # ── Demo mode ───────────────────────────────────────────────────────────

    async def _run_demo(
        self,
        image_bytes: bytes,
        product_context: ProductContext,
        *,
        model_status: Optional[str] = None,
    ) -> InternalInspectionResult:
        """Demo mode: deterministic mock result without any external calls."""
        mock = MLRegistry.get_mock()
        result = await mock.inspect(image_bytes, product_context.product_id)

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
            winning_reason="demo_mode",
            model_status_at_inspection=model_status,
        )


# Singleton
inspection_router = InspectionRouter()

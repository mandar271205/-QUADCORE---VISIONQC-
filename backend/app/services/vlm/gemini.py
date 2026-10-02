"""
Google Gemini Vision Language Model Engine.
Uses the official google-generativeai SDK.
Provider details never escape this module.
"""
import json
import time
import base64
from typing import Optional
from app.services.vlm.base import BaseVLMEngine, ProductContext, VLMInspectionResult
from app.prompts.inspection import build_product_context_prompt
from app.core.config import settings
from app.core.logging import get_logger
from app.db.models import Decision

logger = get_logger(__name__)

PROVIDER_NAME = "gemini"   # internal only


class GeminiVisionEngine(BaseVLMEngine):
    """Google Gemini multimodal inspection engine."""

    def __init__(self):
        self._client = None
        self._model_name = settings.GOOGLE_VLM_MODEL

    def _get_client(self):
        if self._client is None:
            import google.generativeai as genai
            genai.configure(api_key=settings.GOOGLE_API_KEY)
            self._client = genai.GenerativeModel(self._model_name)
        return self._client

    def is_available(self) -> bool:
        return bool(settings.GOOGLE_API_KEY)

    async def inspect(
        self,
        image_bytes: bytes,
        product_context: ProductContext,
    ) -> VLMInspectionResult:
        start = time.time()
        prompt = build_product_context_prompt(product_context)

        try:
            import google.generativeai as genai
            from google.generativeai.types import HarmCategory, HarmBlockThreshold

            client = self._get_client()

            # Build image part
            image_part = {
                "mime_type": "image/jpeg",
                "data": base64.b64encode(image_bytes).decode("utf-8"),
            }

            response = await _run_gemini_async(client, prompt, image_part)
            latency_ms = int((time.time() - start) * 1000)

            raw_text = response.text.strip()
            # Strip markdown code fences if present
            if raw_text.startswith("```"):
                raw_text = raw_text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

            parsed = json.loads(raw_text)
            return _parse_vlm_response(parsed, PROVIDER_NAME, latency_ms, raw_text)

        except json.JSONDecodeError as e:
            logger.warning(f"[{PROVIDER_NAME}] JSON parse error: {e}")
            raise
        except Exception as e:
            logger.error(f"[{PROVIDER_NAME}] Inspection failed: {type(e).__name__}")
            raise


async def _run_gemini_async(client, prompt: str, image_part: dict):
    """Run Gemini in a thread pool to avoid blocking the event loop."""
    import asyncio
    loop = asyncio.get_event_loop()

    def _call():
        return client.generate_content(
            [prompt, image_part],
            generation_config={"response_mime_type": "application/json"},
        )

    return await asyncio.wait_for(
        loop.run_in_executor(None, _call),
        timeout=settings.ENGINE_TIMEOUT_SECONDS,
    )


def _parse_vlm_response(
    data: dict,
    provider: str,
    latency_ms: int,
    raw_response: str,
) -> VLMInspectionResult:
    decision_str = str(data.get("decision", "REVIEW")).upper()
    try:
        decision = Decision[decision_str]
    except KeyError:
        decision = Decision.REVIEW

    anomaly_score = float(data.get("anomaly_score", 0.5))
    anomaly_score = max(0.0, min(1.0, anomaly_score))

    confidence = float(data.get("confidence", 0.7))
    confidence = max(0.0, min(1.0, confidence))

    defects = data.get("defects", [])
    if not isinstance(defects, list):
        defects = []

    summary = str(data.get("summary", ""))

    return VLMInspectionResult(
        decision=decision,
        anomaly_score=anomaly_score,
        confidence=confidence,
        defects=defects,
        summary=summary,
        provider=provider,
        latency_ms=latency_ms,
        raw_response=raw_response,
        anomaly_regions=[d.get("region") for d in defects if d.get("region")],
    )

"""
Groq Vision Language Model Engine.
Secondary VLM provider. Provider details never escape this module.
"""
import json
import time
import base64
import asyncio
from app.services.vlm.base import BaseVLMEngine, ProductContext, VLMInspectionResult
from app.services.vlm.gemini import _parse_vlm_response
from app.prompts.inspection import build_product_context_prompt
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

PROVIDER_NAME = "groq"  # internal only


class GroqVisionEngine(BaseVLMEngine):
    """Groq vision model inspection engine."""

    def __init__(self):
        self._client = None
        self._client_key = None

    async def _get_client(self):
        # Reuse the HTTP connection pool across inspections. Async requests are
        # cancellable, so timed-out calls do not occupy a background thread.
        key = (settings.GROQ_API_KEY, settings.ENGINE_TIMEOUT_SECONDS)
        if self._client is None or self._client_key != key:
            await self.close()
            from groq import AsyncGroq
            self._client = AsyncGroq(
                api_key=settings.GROQ_API_KEY,
                timeout=settings.ENGINE_TIMEOUT_SECONDS,
                max_retries=0,
            )
            self._client_key = key
        return self._client

    async def close(self):
        if self._client is not None:
            client, self._client = self._client, None
            self._client_key = None
            await client.close()

    def is_available(self) -> bool:
        return bool(settings.GROQ_API_KEY)

    async def inspect(
        self,
        image_bytes: bytes,
        product_context: ProductContext,
    ) -> VLMInspectionResult:
        start = time.time()
        prompt = build_product_context_prompt(product_context)
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")

        try:
            client = await self._get_client()
            response = await asyncio.wait_for(
                client.chat.completions.create(
                    model=settings.GROQ_VLM_MODEL,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "image_url",
                                    "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                                },
                                {"type": "text", "text": prompt},
                            ],
                        }
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.1,
                    max_tokens=1024,
                ),
                timeout=settings.ENGINE_TIMEOUT_SECONDS,
            )

            latency_ms = int((time.time() - start) * 1000)
            raw_text = response.choices[0].message.content or "{}"
            logger.info(f"[{PROVIDER_NAME}] raw response: {raw_text}")
            parsed = json.loads(raw_text)
            return _parse_vlm_response(parsed, PROVIDER_NAME, latency_ms, raw_text)

        except json.JSONDecodeError as e:
            logger.warning(f"[{PROVIDER_NAME}] JSON parse error: {e}")
            raise
        except Exception as e:
            logger.error(f"[{PROVIDER_NAME}] Inspection failed: {type(e).__name__}")
            raise

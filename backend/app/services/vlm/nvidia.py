"""
NVIDIA NIM Multimodal Engine.
Uses OpenAI-compatible API. Provider details never escape this module.
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

PROVIDER_NAME = "nvidia"  # internal only


class NvidiaVisionEngine(BaseVLMEngine):
    """NVIDIA NIM multimodal inspection engine (OpenAI-compatible)."""

    def is_available(self) -> bool:
        return bool(settings.NVIDIA_API_KEY)

    async def inspect(
        self,
        image_bytes: bytes,
        product_context: ProductContext,
    ) -> VLMInspectionResult:
        start = time.time()
        prompt = build_product_context_prompt(product_context)
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")

        try:
            from openai import OpenAI
            client = OpenAI(
                api_key=settings.NVIDIA_API_KEY,
                base_url=settings.NVIDIA_BASE_URL,
            )

            def _call():
                return client.chat.completions.create(
                    model=settings.NVIDIA_VLM_MODEL,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/jpeg;base64,{image_b64}",
                                        "detail": "high",
                                    },
                                },
                                {"type": "text", "text": prompt},
                            ],
                        }
                    ],
                    temperature=0.1,
                    max_tokens=1024,
                )

            loop = asyncio.get_event_loop()
            response = await asyncio.wait_for(
                loop.run_in_executor(None, _call),
                timeout=settings.ENGINE_TIMEOUT_SECONDS,
            )

            latency_ms = int((time.time() - start) * 1000)
            raw_text = response.choices[0].message.content or "{}"

            # Clean potential markdown fences
            clean_text = raw_text.strip()
            if "```json" in clean_text:
                clean_text = clean_text.split("```json", 1)[1].split("```", 1)[0].strip()
            elif clean_text.startswith("```"):
                clean_text = clean_text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

            parsed = None
            try:
                parsed = json.loads(clean_text)
            except Exception:
                start_idx = clean_text.find("{")
                end_idx = clean_text.rfind("}")
                if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                    try:
                        parsed = json.loads(clean_text[start_idx : end_idx + 1])
                    except Exception:
                        pass

            if not isinstance(parsed, dict):
                # Fallback parser for conversational response format
                upper_text = clean_text.upper()
                decision = "PASS" if "**PASS**" in upper_text or "DECISION IS: PASS" in upper_text or "\nPASS\n" in upper_text else "FAIL" if "**FAIL**" in upper_text or "FAIL" in upper_text else "REVIEW"
                score = 0.05 if decision == "PASS" else 0.85 if decision == "FAIL" else 0.50
                parsed = {
                    "decision": decision,
                    "anomaly_score": score,
                    "confidence": 0.90,
                    "defects": [],
                    "summary": clean_text[:300].strip(),
                }

            return _parse_vlm_response(parsed, PROVIDER_NAME, latency_ms, raw_text)

        except Exception as e:
            logger.error(f"[{PROVIDER_NAME}] Inspection failed: {type(e).__name__}: {e}")
            raise

"""Adapter for explicitly bound Member 1 PatchCore product categories."""
import asyncio
import json
import time
import uuid
from pathlib import Path
from typing import Optional

from app.core.config import settings
from app.services.ml.base import BaseMLEngine, MLInspectionResult
from app.services.ml.member1_artifacts import is_member1_definition
from app.services.ml.member1_worker.client import member1_worker


class Member1PatchCoreEngine(BaseMLEngine):
    is_member1 = True

    def _path(self, product_id: Optional[str]) -> Path | None:
        try:
            return Path(settings.ML_MODEL_ROOT).expanduser().resolve() / f"{uuid.UUID(product_id)}.json"
        except (ValueError, TypeError, AttributeError):
            return None

    def _definition(self, product_id: Optional[str]) -> dict | None:
        path = self._path(product_id)
        if not settings.ML_M1_ENABLED or path is None or not path.is_file():
            return None
        try:
            definition = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return None
        return definition if isinstance(definition, dict) and is_member1_definition(definition) else None

    def is_model_available(self, product_id: Optional[str] = None) -> bool:
        return self._definition(product_id) is not None

    async def load_model(self, product_id: str) -> bool:
        definition = self._definition(product_id)
        if definition is None:
            return False
        result = await member1_worker.load_category(definition["category"])
        return (result.get("category") == definition["category"]
                and result.get("model_contract") == "Patchcore"
                and bool(result.get("checkpoint_loaded"))
                and self._valid_threshold(result.get("threshold")))

    async def inspect(
        self,
        image_bytes: bytes,
        product_id: Optional[str] = None,
    ) -> MLInspectionResult:
        definition = self._definition(product_id)
        if definition is None:
            raise ValueError("A valid Member 1 category profile is required")
        started = time.perf_counter()
        result = await member1_worker.inspect(definition["category"], image_bytes)
        score = float(result["anomaly_score"])
        threshold = float(result["threshold"])
        verdict = result["verdict"]
        label = result.get("pred_label")
        if (result.get("category") != definition["category"]
                or result.get("model_contract") != "Patchcore"
                or not result.get("checkpoint_loaded")
                or verdict not in ("PASS", "FAIL")
                or label not in (0, 1)
                or verdict != ("FAIL" if label == 1 else "PASS")
                or not self._valid_threshold(threshold)
                or not 0.0 <= score <= 1.0):
            raise ValueError("Member 1 returned an invalid native verdict")
        return MLInspectionResult(
            anomaly_score=score,
            confidence=None,
            anomaly_map=result["anomaly_map"],
            latency_ms=int(result.get("latency_ms", (time.perf_counter() - started) * 1000)),
            model_name=f"member1_patchcore_{definition['category']}",
            threshold=threshold,
            native_verdict=verdict,
        )

    @staticmethod
    def _valid_threshold(value) -> bool:
        try:
            threshold = float(value)
        except (TypeError, ValueError):
            return False
        return 0.0 <= threshold <= 1.0

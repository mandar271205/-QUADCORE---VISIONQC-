"""Saved baseline profiles plugged into the existing BaseMLEngine contract."""
import asyncio
import io
import json
import threading
import time
import uuid
from pathlib import Path
from typing import Optional
import numpy as np
from PIL import Image
from app.core.config import settings
from app.services.ml.base import BaseMLEngine, MLInspectionResult
from app.services.ml.factory import model_class, load_patchcore
from app.services.ml.shared.result import normalize_score


class ProfileMLEngine(BaseMLEngine):
    """Product UUID -> profile JSON in ML_MODEL_ROOT; weights loaded only on demand."""
    def __init__(self):
        self._profiles: dict = {}
        self._lock = threading.RLock()

    def _path(self, product_id: Optional[str]) -> Path | None:
        try:
            return Path(settings.ML_MODEL_ROOT)/f'{uuid.UUID(product_id)}.json'
        except (ValueError, TypeError, AttributeError):
            return None

    def _definition(self, product_id: Optional[str]) -> tuple[dict,Path] | None:
        path = self._path(product_id)
        if path is None or not path.is_file():
            return None
        definition = json.loads(path.read_text())
        checkpoint = (path.parent/definition['checkpoint']).resolve()
        if not checkpoint.is_relative_to(path.parent.resolve()):
            raise ValueError('Profile checkpoint must be inside ML_MODEL_ROOT')
        if definition['model'] not in ('autoencoder','padim','patchcore','ensemble') or not checkpoint.is_file():
            return None
        return definition, checkpoint

    def is_model_available(self, product_id: Optional[str] = None) -> bool:
        try:
            return self._definition(product_id) is not None
        except (ValueError, KeyError, OSError):
            return False

    def _load(self, product_id: str):
        pair = self._definition(product_id)
        if pair is None:
            raise FileNotFoundError(f'No saved ML profile for {product_id}')
        definition, checkpoint = pair
        stamp = (self._path(product_id).stat().st_mtime_ns, checkpoint.stat().st_mtime_ns)
        cached = self._profiles.get(product_id)
        if cached is None or cached[0] != stamp:
            import torch
            torch.set_num_threads(max(1, settings.ML_TORCH_THREADS))
            if definition['model'] == 'patchcore' and definition.get('adapter'):
                model = load_patchcore(definition['adapter'],checkpoint,settings.ML_DEVICE)
            else:
                model = model_class(definition['model']).load(checkpoint,settings.ML_DEVICE)
            extractor = None
            if definition.get('roi') == 'opencv':
                from app.services.ml.roi import OpenCVROIExtractor
                extractor = OpenCVROIExtractor()
            elif definition.get('roi') == 'yolo':
                from app.services.ml.roi import YOLOROIExtractor
                weights = (self._path(product_id).parent/definition['roi_weights']).resolve()
                if not weights.is_relative_to(self._path(product_id).parent.resolve()):
                    raise ValueError('ROI weights must be inside ML_MODEL_ROOT')
                extractor = YOLOROIExtractor(weights)
            elif definition.get('roi') is not None:
                raise ValueError('Unknown ROI extractor')
            if product_id not in self._profiles and len(self._profiles) >= max(1, settings.ML_CACHE_SIZE):
                self._profiles.pop(next(iter(self._profiles)))
            self._profiles[product_id] = stamp, model, extractor
        return self._profiles[product_id][1:]

    async def load_model(self, product_id: str) -> bool:
        def load():
            with self._lock:
                self._load(product_id)
            return True
        return await asyncio.to_thread(load)

    def _inspect(self, image_bytes: bytes, product_id: str) -> MLInspectionResult:
        with self._lock:
            model, extractor = self._load(product_id)
            started = time.perf_counter()
            source = image_bytes
            roi = None
            if extractor:
                with Image.open(io.BytesIO(image_bytes)) as image:
                    original = np.asarray(image.convert('RGB'))
                roi = extractor.extract(original)
                if roi is None:
                    raise ValueError('No product ROI found; no automatic PASS')
                buffer = io.BytesIO()
                Image.fromarray(roi.crop(original)).save(buffer,format='PNG')
                source = buffer.getvalue()
            result, anomaly_map = model.predict(source)
            # Preserve score semantics for QualityGate's existing 0..1 contract.
            display_map = anomaly_map/(anomaly_map+model.threshold)
            if roi:
                import cv2
                x1,y1,x2,y2 = roi.bbox
                projected = np.zeros(original.shape[:2],dtype=np.float32)
                projected[y1:y2,x1:x2] = cv2.resize(display_map,(x2-x1,y2-y1))
                display_map = projected
            return MLInspectionResult(anomaly_score=normalize_score(result.anomaly_score,result.threshold),
                                      confidence=None,anomaly_map=display_map,
                                      latency_ms=round((time.perf_counter()-started)*1000),model_name=model.name,
                                      roi_region=({'x':x1/original.shape[1],'y':y1/original.shape[0],
                                                   'width':(x2-x1)/original.shape[1],'height':(y2-y1)/original.shape[0]}
                                                  if roi else None))

    async def inspect(self, image_bytes: bytes, product_id: Optional[str] = None) -> MLInspectionResult:
        if product_id is None:
            raise ValueError('A product-specific trained profile is required')
        return await asyncio.to_thread(self._inspect,image_bytes,product_id)

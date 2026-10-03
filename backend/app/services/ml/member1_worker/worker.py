"""Long-lived Member 1 PatchCore worker. stdout is reserved for protocol JSON."""
from __future__ import annotations

import json
import os
import sys
import time
from collections import OrderedDict
from pathlib import Path

import numpy as np

PROTOCOL_VERSION = 1
CATEGORIES = ("bottle", "cable", "capsule", "metal_nut", "screw", "transistor")
BASE = Path(os.environ["VISIONQC_M1_MODEL_ROOT"]).resolve()
WORK_ROOT = Path(os.environ["VISIONQC_M1_WORK_ROOT"]).resolve()
MAX_CACHE = max(1, int(os.environ.get("VISIONQC_M1_CACHE_SIZE", "2")))
MODELS: OrderedDict[str, tuple[object, Path]] = OrderedDict()

# Anomalib's helper is the source of truth for model loading and thresholds.
sys.path.insert(0, str(BASE))
import predict_patchcore as predictor  # noqa: E402


def _inside_work_root(value: str) -> Path:
    path = Path(value).resolve()
    if not path.is_relative_to(WORK_ROOT):
        raise ValueError("request path is outside the configured worker work directory")
    return path


def _get_model(category: str):
    if category not in CATEGORIES:
        raise ValueError("unsupported category")
    cached = MODELS.pop(category, None)
    if cached is None:
        model, checkpoint = predictor.load_patchcore(category)
    else:
        model, checkpoint = cached
    MODELS[category] = (model, checkpoint)
    while len(MODELS) > MAX_CACHE:
        MODELS.popitem(last=False)
    return model, checkpoint


def _scalar(value):
    return predictor.to_scalar(value)


def _handle(request: dict) -> dict:
    if request.get("version") != PROTOCOL_VERSION:
        raise ValueError("unsupported protocol version")
    action = request.get("action")
    if action == "hello":
        import anomalib
        return {
            "protocol_version": PROTOCOL_VERSION,
            "runtime_version": str(getattr(anomalib, "__version__", "unknown")),
            "python_version": sys.version.split()[0],
            "categories": [category for category in CATEGORIES
                           if (BASE / "outputs" / "checkpoints" / category /
                               f"patchcore_{category}.ckpt").is_file()],
        }
    if action == "shutdown":
        return {"shutdown": True}
    if action not in ("load", "inspect"):
        raise ValueError("unsupported action")

    category = request.get("category")
    model, checkpoint = _get_model(category)
    threshold = predictor.get_threshold(model)
    if threshold is None or not np.isfinite(float(threshold)):
        raise ValueError("checkpoint has no finite native decision threshold")
    threshold = float(threshold)
    if action == "load":
        return {
            "category": category,
            "checkpoint_loaded": checkpoint.is_file(),
            "threshold": threshold,
            "model_contract": type(model).__name__,
        }

    image_path = _inside_work_root(request["image_path"])
    anomaly_map_path = _inside_work_root(request["anomaly_map_path"])
    if not image_path.is_file():
        raise FileNotFoundError("input image is unavailable")

    from anomalib.engine import Engine

    started = time.perf_counter()
    predictions = Engine(
        enable_progress_bar=False,
        enable_model_summary=False,
        logger=False,
    ).predict(model=model, data_path=str(image_path), return_predictions=True)
    latency_ms = round((time.perf_counter() - started) * 1000)
    if not predictions:
        raise RuntimeError("anomalib returned no predictions")
    prediction = predictions[0]
    score = float(_scalar(prediction.pred_score))
    label = int(_scalar(prediction.pred_label))
    anomaly_map = np.asarray(
        prediction.anomaly_map.detach().cpu().numpy(), dtype=np.float32
    ).squeeze()
    if anomaly_map.ndim != 2 or not np.isfinite(anomaly_map).all():
        raise ValueError("anomalib returned an invalid anomaly map")
    if not np.isfinite(score) or not 0.0 <= score <= 1.0:
        raise ValueError("anomalib returned an invalid image score")
    if label not in (0, 1):
        raise ValueError("anomalib returned an invalid predicted label")
    anomaly_map_path.parent.mkdir(parents=True, exist_ok=True)
    np.save(anomaly_map_path, anomaly_map, allow_pickle=False)
    return {
        "category": category,
        "anomaly_score": score,
        "threshold": threshold,
        "pred_label": label,
        "verdict": "FAIL" if label == 1 else "PASS",
        "latency_ms": latency_ms,
        "anomaly_map_path": str(anomaly_map_path),
        "model_contract": type(model).__name__,
        "checkpoint_loaded": checkpoint.is_file(),
    }


def main() -> int:
    for line in sys.stdin:
        request_id = None
        try:
            request = json.loads(line)
            request_id = request.get("request_id")
            result = _handle(request)
            response = {"version": PROTOCOL_VERSION, "request_id": request_id,
                        "ok": True, "result": result}
            shutdown = request.get("action") == "shutdown"
        except Exception as error:  # keep stdout protocol-only and paths private
            response = {"version": PROTOCOL_VERSION, "request_id": request_id,
                        "ok": False, "error": type(error).__name__}
            shutdown = False
        sys.stdout.write(json.dumps(response, allow_nan=False) + "\n")
        sys.stdout.flush()
        if shutdown:
            break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

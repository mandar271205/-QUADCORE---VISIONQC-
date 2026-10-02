"""Common model lifecycle for baselines and Member 1's future PatchCore adapter."""
from abc import ABC, abstractmethod
from dataclasses import asdict
from pathlib import Path
import time
import numpy as np
from app.services.ml.shared.config import ExperimentConfig
from app.services.ml.shared.data import validate_good
from app.services.ml.shared.preprocessing import read_rgb
from app.services.ml.shared.result import Prediction, calibrate


class Baseline(ABC):
    name: str

    def __init__(self, config: ExperimentConfig, category: str):
        self.config, self.category = config, category
        self.threshold: float | None = None
        self.provenance: dict = {}
        self.training_paths: set[Path] = set()

    @abstractmethod
    def fit(self, paths: list[Path]) -> None: ...

    @abstractmethod
    def infer(self, rgb: np.ndarray) -> tuple[float, np.ndarray, np.ndarray | None]: ...

    @abstractmethod
    def save(self, path: Path) -> None: ...

    @classmethod
    @abstractmethod
    def load(cls, path: Path, device: str = "cpu") -> "Baseline": ...

    def calibrate(self, paths: list[Path]) -> None:
        validate_good(paths)
        if self.training_paths & {p.resolve() for p in paths}:
            raise ValueError("Calibration images must be held out from training")
        self.threshold = calibrate([self.infer(read_rgb(p, self.config.image_size))[0]
                                    for p in paths], self.config.percentile)

    def metadata(self) -> dict:
        if self.threshold is None:
            raise RuntimeError("Calibrate on held-out GOOD images before saving")
        return {"config": asdict(self.config), "category": self.category,
                "threshold": self.threshold, "model": self.name, "provenance": self.provenance}

    def predict(self, source: Path | bytes, heatmap_path: Path | None = None):
        if self.threshold is None:
            raise RuntimeError("Model has no calibrated threshold")
        start = time.perf_counter()
        rgb = read_rgb(source, self.config.image_size)
        score, anomaly_map, reconstruction = self.infer(rgb)
        # Inference implementations synchronize accelerators before returning.
        latency = (time.perf_counter() - start) * 1000
        anomaly_map = np.asarray(anomaly_map, dtype=np.float32)
        if anomaly_map.shape != rgb.shape[:2] or not np.isfinite(anomaly_map).all():
            raise ValueError("Anomaly map must be finite and match shared preprocessing")
        result = Prediction(self.provenance.get('dataset', 'mvtec_ad'), self.category, self.name, score,
                            self.threshold, str(heatmap_path) if heatmap_path else None, latency)
        if heatmap_path:
            from app.services.ml.shared.visualization import save_outputs
            save_outputs(rgb, anomaly_map, reconstruction, heatmap_path, self.threshold)
        return result, anomaly_map

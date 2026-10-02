"""Raw-score experiment contract, separate from the normalized public API."""
from dataclasses import dataclass, asdict
import math
import numpy as np


@dataclass
class Prediction:
    dataset: str
    category: str
    model: str
    anomaly_score: float
    threshold: float
    heatmap_path: str | None
    latency_ms: float

    def __post_init__(self) -> None:
        if not all(math.isfinite(v) for v in (self.anomaly_score, self.threshold, self.latency_ms)):
            raise ValueError("Prediction values must be finite")
        if self.anomaly_score < 0 or self.threshold <= 0 or self.latency_ms < 0:
            raise ValueError("Scores/latency must be nonnegative and threshold positive")

    @property
    def verdict(self) -> str:
        return "FAIL" if self.anomaly_score > self.threshold else "PASS"

    def to_dict(self) -> dict:
        return {**asdict(self), "verdict": self.verdict}


def calibrate(scores: list[float], percentile: float = 99) -> float:
    values = np.asarray(scores, dtype=float)
    if not len(values) or not np.isfinite(values).all() or (values < 0).any():
        raise ValueError("Calibration requires finite normal scores")
    if not 0 < percentile <= 100:
        raise ValueError("Invalid percentile")
    return float(max(float(np.percentile(values, percentile)), np.finfo(np.float32).eps))


def normalize_score(score: float, threshold: float) -> float:
    """Monotonic display scale: calibrated threshold maps to 0.5; NOT probability."""
    if not math.isfinite(score) or score < 0 or not math.isfinite(threshold) or threshold <= 0:
        raise ValueError("Invalid raw score/threshold")
    return score / (score + threshold)

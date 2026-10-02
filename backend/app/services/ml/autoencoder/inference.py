"""Inference never retrains; checkpoint includes threshold and configuration."""
from pathlib import Path
import torch
import numpy as np
from app.services.ml.autoencoder.model import ConvAutoencoder
from app.services.ml.autoencoder.trainer import train
from app.services.ml.shared.baseline import Baseline
from app.services.ml.shared.config import ExperimentConfig
from app.services.ml.shared.preprocessing import tensor, seed_everything


class AutoencoderBaseline(Baseline):
    name = "autoencoder"

    def __init__(self, config: ExperimentConfig, category: str):
        super().__init__(config, category)
        seed_everything(config.seed)
        self.model = ConvAutoencoder().to(config.device)
        self.fitted = False
        self.history: list[float] = []

    def fit(self, paths: list[Path]) -> None:
        self.history = train(self.model, paths, self.config)
        self.training_paths = {p.resolve() for p in paths}
        self.fitted = True
        self.threshold = None

    def infer(self, rgb: np.ndarray):
        if not self.fitted:
            raise RuntimeError("Autoencoder is not trained")
        self.model.eval()
        with torch.inference_mode():
            x = tensor(rgb, self.config.device)
            reconstruction = self.model(x)
            anomaly_map = (x - reconstruction).square().mean(dim=1)[0].cpu().numpy()
            restored = reconstruction[0].cpu().numpy().transpose(1, 2, 0)
        return float(anomaly_map.mean()), anomaly_map, restored

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        torch.save({**self.metadata(), "state_dict": self.model.state_dict(),
                    "history": self.history}, path)

    @classmethod
    def load(cls, path: Path, device: str = "cpu"):
        checkpoint = torch.load(path, map_location=device, weights_only=True)
        if checkpoint["model"] != cls.name:
            raise ValueError("Wrong checkpoint model")
        config = ExperimentConfig(**{**checkpoint["config"], "device": device})
        instance = cls(config, checkpoint["category"])
        instance.model.load_state_dict(checkpoint["state_dict"])
        instance.model.eval()
        instance.fitted = True
        instance.threshold = checkpoint["threshold"]
        instance.history = checkpoint["history"]
        instance.provenance = checkpoint.get("provenance", {})
        return instance

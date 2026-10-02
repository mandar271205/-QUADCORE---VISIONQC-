"""Anomalib 2.3.0 PaDiM lifecycle, with explicit normal-only fitting."""
from dataclasses import replace
from importlib.metadata import version
from pathlib import Path
import numpy as np
from app.services.ml.shared.baseline import Baseline
from app.services.ml.shared.config import ExperimentConfig
from app.services.ml.shared.data import validate_good
from app.services.ml.shared.preprocessing import read_rgb, tensor, seed_everything


class PadimBaseline(Baseline):
    name = "padim"

    def __init__(self, config: ExperimentConfig, category: str, *, initialize_pretrained: bool = True, n_features: int = 100):
        super().__init__(config, category)
        if version("anomalib") != "2.3.0":
            raise RuntimeError("Install requirements-ml.txt: this adapter is tested with Anomalib 2.3.0")
        import torch
        from anomalib.models import Padim
        seed_everything(config.seed)
        self.n_features = n_features
        # Loading restores the saved pretrained backbone without a network download.
        self.model = Padim(backbone="resnet18", layers=["layer1", "layer2", "layer3"],
                           pre_trained=initialize_pretrained, n_features=n_features, pre_processor=False,
                           post_processor=False, evaluator=False, visualizer=False).model.to(config.device)
        self.mean = torch.tensor([.485, .456, .406], device=config.device).view(1, 3, 1, 1)
        self.std = torch.tensor([.229, .224, .225], device=config.device).view(1, 3, 1, 1)
        self.fitted = False
        self.pretrained = initialize_pretrained

    def _input(self, rgb: np.ndarray):
        return (tensor(rgb, self.config.device) - self.mean) / self.std

    def fit(self, paths: list[Path]) -> None:
        import torch
        validate_good(paths)
        if len(paths) < 2:
            raise ValueError("PaDiM requires at least two GOOD observations")
        self.training_paths = {p.resolve() for p in paths}
        seed_everything(self.config.seed)
        self.model.memory_bank = []
        self.model.train()
        self.model.feature_extractor.eval()
        with torch.no_grad():
            for offset in range(0, len(paths), self.config.batch_size):
                batch = torch.cat([self._input(read_rgb(p, self.config.image_size))
                                   for p in paths[offset:offset + self.config.batch_size]])
                self.model(batch)
            self.model.fit()
        self.model.eval()
        self.fitted = True
        self.threshold = None

    def infer(self, rgb: np.ndarray):
        import torch
        if not self.fitted:
            raise RuntimeError("PaDiM distribution is not fitted")
        with torch.inference_mode():
            prediction = self.model(self._input(rgb))
            anomaly_map = prediction.anomaly_map[0, 0].cpu().numpy()
            score = float(prediction.pred_score.reshape(-1)[0].cpu())
        return score, anomaly_map, None

    def save(self, path: Path) -> None:
        import torch
        path.parent.mkdir(parents=True, exist_ok=True)
        torch.save({**self.metadata(), "state_dict": self.model.state_dict(),
                    "anomalib_version": version("anomalib"), "pretrained": self.pretrained, "n_features": self.n_features,
                    "normalization": "ImageNet mean/std after shared RGB resize"}, path)

    @classmethod
    def load(cls, path: Path, device: str = "cpu"):
        import torch
        checkpoint = torch.load(path, map_location=device, weights_only=True)
        if checkpoint["model"] != cls.name or checkpoint["anomalib_version"] != "2.3.0":
            raise ValueError("Incompatible PaDiM checkpoint")
        config = replace(ExperimentConfig(**checkpoint["config"]), device=device)
        instance = cls(config, checkpoint["category"], initialize_pretrained=False, n_features=checkpoint.get("n_features", 100))
        instance.model.load_state_dict(checkpoint["state_dict"])
        instance.model.eval()
        instance.fitted = True
        instance.pretrained = checkpoint["pretrained"]
        instance.threshold = checkpoint["threshold"]
        instance.provenance = checkpoint.get("provenance", {})
        return instance

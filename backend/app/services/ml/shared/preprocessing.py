"""Shared RGB resize; masks use nearest-neighbor to preserve binary labels."""
from pathlib import Path
import io
import random
import numpy as np
from PIL import Image


def read_rgb(source: Path | bytes, size: int) -> np.ndarray:
    with Image.open(io.BytesIO(source) if isinstance(source, bytes) else source) as image:
        return np.asarray(image.convert("RGB").resize((size, size), Image.Resampling.BILINEAR),
                          dtype=np.float32) / 255.0


def read_mask(path: Path, size: int) -> np.ndarray:
    with Image.open(path) as image:
        return np.asarray(image.convert("L").resize((size, size), Image.Resampling.NEAREST)) > 0


def seed_everything(seed: int) -> None:
    import torch
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.use_deterministic_algorithms(True)


def tensor(rgb: np.ndarray, device: str):
    import torch
    return torch.from_numpy(rgb.transpose(2, 0, 1).copy()).unsqueeze(0).to(device)

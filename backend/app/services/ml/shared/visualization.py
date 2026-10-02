"""Reuse the backend heatmap renderer and preserve raw maps for analysis."""
import io
from pathlib import Path
import numpy as np
from PIL import Image
from app.services.heatmap.generator import generate_heatmap_from_anomaly_map


def save_outputs(rgb: np.ndarray, anomaly_map: np.ndarray, reconstruction: np.ndarray | None,
                 destination: Path, threshold: float) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    buffer = io.BytesIO()
    Image.fromarray((rgb * 255).astype(np.uint8)).save(buffer, format="PNG")
    # A shared threshold-relative scale, not independent per-image min/max scaling.
    scaled = anomaly_map / (anomaly_map + threshold)
    png, overlay = generate_heatmap_from_anomaly_map(scaled, buffer.getvalue())
    destination.write_bytes(png)
    destination.with_name(destination.stem + "_overlay.png").write_bytes(overlay)
    np.save(destination.with_suffix(".npy"), anomaly_map)
    if reconstruction is not None:
        Image.fromarray((np.clip(reconstruction, 0, 1) * 255).astype(np.uint8)).save(
            destination.with_name(destination.stem + "_reconstruction.png"))

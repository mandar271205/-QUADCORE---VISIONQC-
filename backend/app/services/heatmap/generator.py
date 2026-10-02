"""
Heatmap generator for VisionQC.
Converts ML anomaly maps and VLM bounding regions into consistent heatmap images.
The frontend always shows the same visualization regardless of inspection source.
"""
import io
import numpy as np
from typing import Optional
from PIL import Image
import cv2
from app.core.logging import get_logger

logger = get_logger(__name__)


def generate_heatmap_from_anomaly_map(
    anomaly_map: np.ndarray,
    original_image_bytes: bytes,
    alpha: float = 0.5,
) -> tuple[bytes, bytes]:
    """
    Generate heatmap PNG and overlay from a native ML anomaly map.
    
    Args:
        anomaly_map: 2D float32 array (0-1 normalized)
        original_image_bytes: Original image bytes
        alpha: Overlay blend alpha
        
    Returns:
        (heatmap_png_bytes, overlay_png_bytes)
    """
    original_pil = Image.open(io.BytesIO(original_image_bytes)).convert("RGB")
    orig_w, orig_h = original_pil.size

    # Normalize to 0-255
    normalized = np.clip(anomaly_map, 0.0, 1.0)
    normalized_uint8 = (normalized * 255).astype(np.uint8)

    # Resize to match original image
    heatmap_resized = cv2.resize(normalized_uint8, (orig_w, orig_h), interpolation=cv2.INTER_LINEAR)

    # Apply colormap (JET: blue=normal, red=anomaly)
    heatmap_colored = cv2.applyColorMap(heatmap_resized, cv2.COLORMAP_JET)
    heatmap_rgb = cv2.cvtColor(heatmap_colored, cv2.COLOR_BGR2RGB)
    heatmap_pil = Image.fromarray(heatmap_rgb)

    # Generate raw heatmap PNG
    heatmap_bytes = _pil_to_bytes(heatmap_pil)

    # Generate overlay
    overlay_pil = Image.blend(original_pil, heatmap_pil, alpha=alpha)
    overlay_bytes = _pil_to_bytes(overlay_pil)

    return heatmap_bytes, overlay_bytes


def generate_heatmap_from_regions(
    regions: list[dict],
    original_image_bytes: bytes,
    alpha: float = 0.5,
    gaussian_sigma: float = 0.08,
) -> tuple[bytes, bytes]:
    """
    Generate heatmap from VLM bounding box regions.
    Uses Gaussian falloff from region center to create soft probability field.
    
    Args:
        regions: List of {"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0} (normalized)
        original_image_bytes: Original image bytes
        alpha: Overlay blend alpha
        gaussian_sigma: Controls spread of Gaussian (as fraction of image size)
        
    Returns:
        (heatmap_png_bytes, overlay_png_bytes)
    """
    original_pil = Image.open(io.BytesIO(original_image_bytes)).convert("RGB")
    orig_w, orig_h = original_pil.size

    # Build probability field
    prob_map = np.zeros((orig_h, orig_w), dtype=np.float32)

    y_grid, x_grid = np.mgrid[0:orig_h, 0:orig_w]
    y_norm = y_grid / orig_h
    x_norm = x_grid / orig_w

    for region in regions:
        if not region:
            continue
        rx = float(region.get("x", 0))
        ry = float(region.get("y", 0))
        rw = float(region.get("width", 0))
        rh = float(region.get("height", 0))

        # Gaussian center
        cx = rx + rw / 2.0
        cy = ry + rh / 2.0

        # Sigma proportional to region size
        sigma_x = max(rw * 0.6, gaussian_sigma)
        sigma_y = max(rh * 0.6, gaussian_sigma)

        gaussian = np.exp(
            -(((x_norm - cx) ** 2) / (2 * sigma_x ** 2))
            - (((y_norm - cy) ** 2) / (2 * sigma_y ** 2))
        )
        prob_map += gaussian

    if prob_map.max() > 0:
        prob_map = prob_map / prob_map.max()

    # Apply light Gaussian blur for smooth edges
    prob_map_uint8 = (prob_map * 255).astype(np.uint8)
    blur_size = max(3, int(min(orig_w, orig_h) * 0.04) | 1)  # must be odd
    prob_map_blurred = cv2.GaussianBlur(prob_map_uint8, (blur_size, blur_size), 0)

    # Colormap
    heatmap_colored = cv2.applyColorMap(prob_map_blurred, cv2.COLORMAP_JET)
    heatmap_rgb = cv2.cvtColor(heatmap_colored, cv2.COLOR_BGR2RGB)
    heatmap_pil = Image.fromarray(heatmap_rgb)

    heatmap_bytes = _pil_to_bytes(heatmap_pil)
    overlay_pil = Image.blend(original_pil, heatmap_pil, alpha=alpha)
    overlay_bytes = _pil_to_bytes(overlay_pil)

    return heatmap_bytes, overlay_bytes


def generate_empty_heatmap(original_image_bytes: bytes) -> tuple[bytes, bytes]:
    """Generate a clean (no anomaly) heatmap for PASS results."""
    original_pil = Image.open(io.BytesIO(original_image_bytes)).convert("RGB")
    orig_w, orig_h = original_pil.size

    # Solid blue = no anomaly
    zero_map = np.zeros((orig_h, orig_w), dtype=np.uint8)
    heatmap_colored = cv2.applyColorMap(zero_map, cv2.COLORMAP_JET)
    heatmap_rgb = cv2.cvtColor(heatmap_colored, cv2.COLOR_BGR2RGB)
    heatmap_pil = Image.fromarray(heatmap_rgb)

    heatmap_bytes = _pil_to_bytes(heatmap_pil)
    overlay_pil = Image.blend(original_pil, heatmap_pil, alpha=0.3)
    overlay_bytes = _pil_to_bytes(overlay_pil)

    return heatmap_bytes, overlay_bytes


def _pil_to_bytes(img: Image.Image, format: str = "PNG") -> bytes:
    buf = io.BytesIO()
    img.save(buf, format=format)
    buf.seek(0)
    return buf.read()

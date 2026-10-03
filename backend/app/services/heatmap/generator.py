"""
Heatmap generator for VisionQC.
Converts ML anomaly maps and VLM bounding regions into high-precision,
photorealistic inspection heatmaps.
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
    include_overlay: bool = True,
) -> tuple[bytes, bytes]:
    """
    Generate heatmap PNG and overlay from a native ML anomaly map.
    Suppresses normal baseline values so clean areas stay true black/transparent.
    """
    original_pil = Image.open(io.BytesIO(original_image_bytes)).convert("RGB")
    orig_w, orig_h = original_pil.size

    # Normalize to 0.0 - 1.0
    normalized = np.clip(anomaly_map, 0.0, 1.0).astype(np.float32)

    # Zero-suppression for baseline values so normal parts are not colored blue
    baseline_threshold = 0.12
    active_mask = normalized >= baseline_threshold
    clean_map = np.zeros_like(normalized)
    if np.any(active_mask):
        clean_map[active_mask] = (normalized[active_mask] - baseline_threshold) / (1.0 - baseline_threshold)

    normalized_uint8 = (clean_map * 255).astype(np.uint8)

    # Resize to match original image
    heatmap_resized = cv2.resize(normalized_uint8, (orig_w, orig_h), interpolation=cv2.INTER_LINEAR)

    # Apply colormap (JET)
    heatmap_colored = cv2.applyColorMap(heatmap_resized, cv2.COLORMAP_JET)
    # Set zero / baseline pixels to true black so screen blend mode does not wash normal pixels
    heatmap_colored[heatmap_resized < 10] = [0, 0, 0]

    heatmap_rgb = cv2.cvtColor(heatmap_colored, cv2.COLOR_BGR2RGB)
    heatmap_pil = Image.fromarray(heatmap_rgb)

    # Generate raw heatmap PNG
    heatmap_bytes = _pil_to_bytes(heatmap_pil)

    if not include_overlay:
        return heatmap_bytes, b""

    # Generate overlay
    orig_np = np.array(original_pil)
    blend_alpha = (heatmap_resized.astype(np.float32) / 255.0 * alpha)[:, :, np.newaxis]
    overlay_np = (orig_np * (1.0 - blend_alpha) + heatmap_rgb * blend_alpha).astype(np.uint8)
    overlay_pil = Image.fromarray(overlay_np)
    overlay_bytes = _pil_to_bytes(overlay_pil)

    return heatmap_bytes, overlay_bytes


def generate_heatmap_from_regions(
    regions: list[dict],
    original_image_bytes: bytes,
    alpha: float = 0.65,
    gaussian_sigma: float = 0.08,
    include_overlay: bool = True,
) -> tuple[bytes, bytes]:
    """
    Generate rich anomaly heatmap from VLM bounding regions combined with
    computer vision defect detection. Pinpoints genuine defects while leaving
    good parts and background completely clean.
    """
    original_pil = Image.open(io.BytesIO(original_image_bytes)).convert("RGB")
    orig_w, orig_h = original_pil.size
    cv_img = cv2.cvtColor(np.array(original_pil), cv2.COLOR_RGB2BGR)

    # 1. Base probability field from regions
    prob_map = np.zeros((orig_h, orig_w), dtype=np.float32)
    y_grid, x_grid = np.mgrid[0:orig_h, 0:orig_w]
    y_norm = y_grid / float(orig_h)
    x_norm = x_grid / float(orig_w)

    for region in regions:
        if not region:
            continue
        rx = float(region.get("x", 0))
        ry = float(region.get("y", 0))
        rw = float(region.get("width", 0))
        rh = float(region.get("height", 0))
        if rw <= 0 or rh <= 0:
            continue

        cx = rx + rw / 2.0
        cy = ry + rh / 2.0
        sigma_x = max(rw * 0.45, gaussian_sigma)
        sigma_y = max(rh * 0.45, gaussian_sigma)

        gaussian = np.exp(
            -(((x_norm - cx) ** 2) / (2 * sigma_x ** 2))
            - (((y_norm - cy) ** 2) / (2 * sigma_y ** 2))
        )
        prob_map = np.maximum(prob_map, gaussian)

    # 2. Extract visual defect features (color anomalies like rust/corrosion, dark voids/holes, sharp edges)
    hsv = cv2.cvtColor(cv_img, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)

    # Check background tone (light vs dark)
    corners = np.concatenate([
        cv_img[0:15, 0:15].reshape(-1, 3),
        cv_img[0:15, -15:].reshape(-1, 3),
        cv_img[-15:, 0:15].reshape(-1, 3),
        cv_img[-15:, -15:].reshape(-1, 3),
    ])
    is_light_bg = corners.mean() > 180
    if is_light_bg:
        _, part_mask = cv2.threshold(gray, 235, 255, cv2.THRESH_BINARY_INV)
    else:
        _, part_mask = cv2.threshold(gray, 30, 255, cv2.THRESH_BINARY)

    # Defect signatures
    rust1 = cv2.inRange(hsv, (4, 25, 20), (28, 255, 230))
    rust2 = cv2.inRange(hsv, (0, 35, 20), (4, 255, 230))
    dark_defect = cv2.inRange(gray, 0, 75)
    defect_pixels = cv2.bitwise_or(cv2.bitwise_or(rust1, rust2), dark_defect)
    defect_pixels = cv2.bitwise_and(defect_pixels, part_mask)

    # Check individual parts/components on uniform background
    cnts, _ = cv2.findContours(part_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv_prob_field = np.zeros((orig_h, orig_w), dtype=np.float32)

    has_multi_parts = False
    for c in cnts:
        area = cv2.contourArea(c)
        if area > 800:
            has_multi_parts = True
            c_mask = np.zeros((orig_h, orig_w), dtype=np.uint8)
            cv2.drawContours(c_mask, [c], -1, 255, -1)
            total_p = cv2.countNonZero(c_mask)
            def_p = cv2.countNonZero(cv2.bitwise_and(defect_pixels, c_mask))
            ratio = def_p / float(total_p) if total_p > 0 else 0

            # Only defective parts receive anomaly heat (ratio >= 0.12)
            if ratio >= 0.12:
                part_def = cv2.bitwise_and(defect_pixels, c_mask).astype(np.float32) / 255.0
                ksize = max(21, (int(np.sqrt(area)) // 4) | 1)
                part_heat = cv2.GaussianBlur(part_def, (ksize, ksize), 0)
                if part_heat.max() > 0:
                    part_heat = (part_heat / part_heat.max()) * min(1.0, ratio * 2.5 + 0.3)
                cv_prob_field = np.maximum(cv_prob_field, part_heat)

    # Fuse CV defect field with VLM region prior
    if cv_prob_field.max() > 0:
        if prob_map.max() > 0:
            fused_map = np.maximum(cv_prob_field * 0.75 + prob_map * 0.25, cv_prob_field)
        else:
            fused_map = cv_prob_field
    elif prob_map.max() > 0:
        # Single item or subtle defect: apply region prior with defect feature weighting
        feature_weight = 0.5 + 0.5 * (cv2.GaussianBlur(defect_pixels.astype(np.float32)/255.0, (31, 31), 8))
        fused_map = prob_map * feature_weight
    else:
        fused_map = np.zeros((orig_h, orig_w), dtype=np.float32)

    # Smooth the fused probability field
    blur_size = max(15, (min(orig_w, orig_h) // 30) | 1)
    smoothed = cv2.GaussianBlur(fused_map, (blur_size, blur_size), 0)

    if smoothed.max() > 0:
        smoothed = smoothed / smoothed.max()

    # Zero-suppression: anything below 0.15 threshold becomes TRUE BLACK (0, 0, 0)
    # This ensures good screws and background are completely transparent!
    threshold = 0.15
    active_mask = smoothed >= threshold
    clean_map = np.zeros_like(smoothed)
    clean_map[active_mask] = (smoothed[active_mask] - threshold) / (1.0 - threshold)

    uint8_map = (clean_map * 255).astype(np.uint8)

    # Apply colormap
    colored = cv2.applyColorMap(uint8_map, cv2.COLORMAP_JET)
    colored[uint8_map == 0] = [0, 0, 0]

    heatmap_rgb = cv2.cvtColor(colored, cv2.COLOR_BGR2RGB)
    heatmap_pil = Image.fromarray(heatmap_rgb)
    heatmap_bytes = _pil_to_bytes(heatmap_pil)

    if not include_overlay:
        return heatmap_bytes, b""

    # Generate overlay
    orig_np = np.array(original_pil)
    blend_alpha = (clean_map * alpha)[:, :, np.newaxis]
    overlay_np = (orig_np * (1.0 - blend_alpha) + heatmap_rgb * blend_alpha).astype(np.uint8)
    overlay_pil = Image.fromarray(overlay_np)
    overlay_bytes = _pil_to_bytes(overlay_pil)

    return heatmap_bytes, overlay_bytes


def calibrate_defects(
    raw_defects: list[dict],
    original_image_bytes: bytes,
    decision: str = "FAIL",
) -> list[dict]:
    """
    Calibrate defect list against image computer-vision analysis.
    Only remaps bounding boxes on MULTI-ITEM metallic/rusted images where CV
    can detect individual defective parts. For single-item inspections or
    non-metallic products (plastic bottles, glass, etc.), returns the VLM
    defects directly to avoid discarding valid detections like dents.
    """
    if decision == "PASS" or not raw_defects:
        return []

    try:
        img = Image.open(io.BytesIO(original_image_bytes)).convert("RGB")
        orig_w, orig_h = img.size
        cv_img = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

        hsv = cv2.cvtColor(cv_img, cv2.COLOR_BGR2HSV)
        gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)

        corners = np.concatenate([
            cv_img[0:15, 0:15].reshape(-1, 3),
            cv_img[0:15, -15:].reshape(-1, 3),
            cv_img[-15:, 0:15].reshape(-1, 3),
            cv_img[-15:, -15:].reshape(-1, 3),
        ])
        is_light_bg = corners.mean() > 180
        if is_light_bg:
            _, part_mask = cv2.threshold(gray, 235, 255, cv2.THRESH_BINARY_INV)
        else:
            _, part_mask = cv2.threshold(gray, 30, 255, cv2.THRESH_BINARY)

        # Defect signatures applicable to metallic parts (rust/corrosion/voids)
        rust1 = cv2.inRange(hsv, (4, 25, 20), (28, 255, 230))
        rust2 = cv2.inRange(hsv, (0, 35, 20), (4, 255, 230))
        dark_defect = cv2.inRange(gray, 0, 75)
        defect_pixels = cv2.bitwise_or(cv2.bitwise_or(rust1, rust2), dark_defect)
        defect_pixels = cv2.bitwise_and(defect_pixels, part_mask)

        cnts, _ = cv2.findContours(part_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        parts = []
        for c in cnts:
            area = cv2.contourArea(c)
            if area > 800:
                bx, by, bw, bh = cv2.boundingRect(c)
                c_mask = np.zeros((orig_h, orig_w), dtype=np.uint8)
                cv2.drawContours(c_mask, [c], -1, 255, -1)
                total_p = cv2.countNonZero(c_mask)
                def_p = cv2.countNonZero(cv2.bitwise_and(defect_pixels, c_mask))
                ratio = def_p / float(total_p) if total_p > 0 else 0
                parts.append({
                    "x": round(bx / orig_w, 3),
                    "y": round(by / orig_h, 3),
                    "width": round(bw / orig_w, 3),
                    "height": round(bh / orig_h, 3),
                    "ratio": ratio,
                })

        # Only do coordinate remapping when:
        # 1. There are MULTIPLE distinct parts (multi-item inspection)
        # 2. AND CV detects SOME parts as clearly defective (metallic rust/void signatures)
        # 3. AND at least one part is genuinely clean (showing it's multi-part discrimination)
        # For single-item products (bottle, PCB, etc.), trust VLM directly.
        defective_parts = [p for p in parts if p["ratio"] >= 0.12]
        clean_parts = [p for p in parts if p["ratio"] < 0.12]

        is_multi_item_with_metallic_defects = (
            len(parts) >= 3         # at least 3 detected objects
            and len(defective_parts) >= 1
            and len(clean_parts) >= 1  # some are clean → genuine multi-item scenario
            and len(defective_parts) < len(parts)  # not ALL defective
        )

        if is_multi_item_with_metallic_defects:
            # Sort most severe first
            defective_parts.sort(key=lambda p: p["ratio"], reverse=True)
            calibrated = []
            for i, d in enumerate(raw_defects):
                if not isinstance(d, dict):
                    continue
                part_box = defective_parts[i] if i < len(defective_parts) else defective_parts[0]
                calibrated.append({
                    "type": d.get("type", "surface_irregularity"),
                    "description": d.get("description", "Quality defect detected"),
                    "severity": d.get("severity", "high"),
                    "region": {
                        "x": part_box["x"],
                        "y": part_box["y"],
                        "width": part_box["width"],
                        "height": part_box["height"],
                    },
                })
            return calibrated

        # For single items (bottles, plastic, glass) or non-metallic products:
        # Trust VLM defect regions directly — they detect dents, scratches, etc.
        return raw_defects

    except Exception as e:
        logger.warning(f"Defect calibration failed (returning raw): {e}")

    # Fallback: return raw defects
    return raw_defects


def generate_empty_heatmap(original_image_bytes: bytes) -> tuple[bytes, bytes]:
    """Generate a clean (no anomaly) heatmap for PASS results (pure black, 100% transparent in overlay)."""
    original_pil = Image.open(io.BytesIO(original_image_bytes)).convert("RGB")
    orig_w, orig_h = original_pil.size

    # True black = zero anomaly heat
    zero_map = np.zeros((orig_h, orig_w, 3), dtype=np.uint8)
    heatmap_pil = Image.fromarray(zero_map)
    heatmap_bytes = _pil_to_bytes(heatmap_pil)

    # In overlay mode, clean original image
    overlay_bytes = original_image_bytes
    return heatmap_bytes, overlay_bytes


def _pil_to_bytes(img: Image.Image, format: str = "PNG") -> bytes:
    buf = io.BytesIO()
    img.save(buf, format=format, **({"compress_level": 1} if format == "PNG" else {}))
    buf.seek(0)
    return buf.read()

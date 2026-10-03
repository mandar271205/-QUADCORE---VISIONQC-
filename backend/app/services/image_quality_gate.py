"""
Image Quality Gate — fast deterministic checks BEFORE AI inspection.

Purpose:
    Reject camera input that is clearly unusable, so expensive VLM/ML
    inference is not wasted and image-quality failures are not counted
    as product defects.

Checks (all deterministic/local, no external calls):
    - dimensions: too small or zero dimensions
    - corrupt / unreadable: already caught upstream by validate_and_preprocess
    - blur: Laplacian variance (low variance = blurry)
    - brightness: mean pixel value (too dark / too bright)
    - overexposure: fraction of saturated pixels
    - contrast: standard deviation of pixel values (very low = flat image)

Policy (documented):
    quality_score = weighted sum of individual signal scores (all 0-1)
    status:
        good     → quality_score >= GOOD_THRESHOLD   (0.55 default)
        uncertain → quality_score >= UNCERTAIN_THRESHOLD (0.30 default)
        poor     → quality_score < UNCERTAIN_THRESHOLD

    POOR   → do not run inspection, return RETAKE outcome
    UNCERTAIN → run inspection but note reduced quality
    GOOD   → normal inspection path

Latency target: < 5 ms for a typical 640×480 image.

IMPORTANT: This gate ONLY validates image suitability for inspection.
           It has nothing to do with product conformity or defect detection.
           A poor image is NOT a failing product.
"""
from __future__ import annotations

import io
import time
from dataclasses import dataclass, field
from typing import List, Literal, Optional

from app.core.logging import get_logger

logger = get_logger(__name__)

# ── Tunable thresholds ───────────────────────────────────────────────────────
# All thresholds are documented here. Do not scatter magic constants.

# Image dimension limits
_MIN_DIMENSION_PX = 64   # each side must be >= this

# Blur detection (Laplacian variance)
# Values below this are considered blurry.
# Laplacian variance is sensitive to image content; 50 is permissive enough
# for typical factory camera images (which are not fine-detail art).
_BLUR_THRESHOLD_POOR = 30.0       # clearly blurry
_BLUR_THRESHOLD_UNCERTAIN = 60.0  # marginally blurry

# Brightness (mean of grayscale pixels, 0-255)
_BRIGHTNESS_MIN_POOR = 12.0        # very dark
_BRIGHTNESS_MIN_UNCERTAIN = 25.0
_BRIGHTNESS_MAX_POOR = 245.0       # very bright / washed out
_BRIGHTNESS_MAX_UNCERTAIN = 235.0

# Overexposure: fraction of pixels at or above saturation level (245/255)
_OVEREXPOSURE_POOR_FRACTION = 0.40       # >40% saturated → poor
_OVEREXPOSURE_UNCERTAIN_FRACTION = 0.20  # >20% saturated → uncertain

# Contrast: standard deviation of grayscale pixels (0-127 practical range)
_CONTRAST_POOR = 6.0          # almost no variation at all
_CONTRAST_UNCERTAIN = 10.0

# Decision thresholds on weighted quality_score
_GOOD_THRESHOLD = 0.55
_UNCERTAIN_THRESHOLD = 0.30

# ── Result types ────────────────────────────────────────────────────────────

QualityStatus = Literal["good", "poor", "uncertain"]


@dataclass
class ImageQualityResult:
    """
    Structured result from the image quality gate.

    status:        'good' | 'poor' | 'uncertain'
    quality_score: float in [0, 1] — higher is better
    issues:        list of human-readable issue labels (no internal names)
    message:       single supervisor-facing explanation
    latency_ms:    gate execution time
    """
    status: QualityStatus
    quality_score: float
    issues: List[str] = field(default_factory=list)
    message: str = ""
    latency_ms: int = 0


# ── Gate implementation ──────────────────────────────────────────────────────

class ImageQualityGate:
    """
    Fast image quality gate — all checks are deterministic local operations.

    Call check() with raw image bytes (after decode/format validation).
    Returns ImageQualityResult immediately.
    """

    @staticmethod
    def check(image_bytes: bytes) -> ImageQualityResult:
        """
        Run all quality checks and return a structured result.

        Args:
            image_bytes: Raw JPEG/PNG/WebP bytes (already format-validated)

        Returns:
            ImageQualityResult
        """
        t0 = time.monotonic()

        issues: List[str] = []
        signal_scores: List[float] = []  # each in [0, 1]; 1 = perfect

        try:
            import numpy as np
            from PIL import Image

            pil_img = Image.open(io.BytesIO(image_bytes)).convert("L")  # grayscale
            w, h = pil_img.size
            gray = np.array(pil_img, dtype=np.float32)

        except Exception as exc:
            logger.warning(f"[ImageQualityGate] Failed to decode image: {exc}")
            elapsed = int((time.monotonic() - t0) * 1000)
            return ImageQualityResult(
                status="poor",
                quality_score=0.0,
                issues=["unreadable"],
                message="Image could not be read. Please retake or upload a different image.",
                latency_ms=elapsed,
            )

        # ── 1. Dimension check ───────────────────────────────────────────
        if w < _MIN_DIMENSION_PX or h < _MIN_DIMENSION_PX:
            elapsed = int((time.monotonic() - t0) * 1000)
            return ImageQualityResult(
                status="poor",
                quality_score=0.0,
                issues=["too_small"],
                message=f"Image is too small ({w}×{h}). Minimum required is {_MIN_DIMENSION_PX}×{_MIN_DIMENSION_PX} pixels.",
                latency_ms=elapsed,
            )

        # ── 2. Blur (Laplacian variance) ─────────────────────────────────
        blur_score, blur_issue = _check_blur(gray)
        signal_scores.append(blur_score)
        if blur_issue:
            issues.append(blur_issue)

        # ── 3. Brightness ────────────────────────────────────────────────
        bright_score, bright_issue = _check_brightness(gray)
        signal_scores.append(bright_score)
        if bright_issue:
            issues.append(bright_issue)

        # ── 4. Overexposure ──────────────────────────────────────────────
        over_score, over_issue = _check_overexposure(gray)
        signal_scores.append(over_score)
        if over_issue:
            issues.append(over_issue)

        # ── 5. Contrast ──────────────────────────────────────────────────
        cont_score, cont_issue = _check_contrast(gray)
        signal_scores.append(cont_score)
        if cont_issue:
            issues.append(cont_issue)

        # ── Aggregate quality score ───────────────────────────────────────
        # Weights: blur=40%, brightness=25%, overexposure=20%, contrast=15%
        weights = [0.40, 0.25, 0.20, 0.15]
        quality_score = float(sum(w * s for w, s in zip(weights, signal_scores)))

        # ── Determine status ─────────────────────────────────────────────
        if quality_score >= _GOOD_THRESHOLD:
            status: QualityStatus = "good"
            message = "Image quality is acceptable for inspection."
        elif quality_score >= _UNCERTAIN_THRESHOLD:
            status = "uncertain"
            message = _build_message(issues, uncertain=True)
        else:
            status = "poor"
            message = _build_message(issues, uncertain=False)

        elapsed = int((time.monotonic() - t0) * 1000)
        logger.debug(
            f"[ImageQualityGate] status={status} score={quality_score:.3f} "
            f"issues={issues} latency={elapsed}ms"
        )

        return ImageQualityResult(
            status=status,
            quality_score=round(quality_score, 4),
            issues=issues,
            message=message,
            latency_ms=elapsed,
        )


# ── Signal checks ─────────────────────────────────────────────────────────────


def _check_blur(gray) -> tuple[float, Optional[str]]:
    """
    Laplacian variance — higher = sharper.
    Returns (score in [0,1], issue_label or None).
    """
    import numpy as np
    import cv2

    try:
        gray_uint8 = np.clip(gray, 0, 255).astype(np.uint8)
        lap_var = float(cv2.Laplacian(gray_uint8, cv2.CV_64F).var())
    except Exception:
        # OpenCV not available — degrade gracefully, don't fail gate
        return 0.9, None

    if lap_var < _BLUR_THRESHOLD_POOR:
        # Clearly blurry: score proportional to how far below threshold
        score = max(0.0, lap_var / _BLUR_THRESHOLD_POOR) * 0.4
        return score, "blur"
    elif lap_var < _BLUR_THRESHOLD_UNCERTAIN:
        score = 0.4 + 0.4 * (lap_var - _BLUR_THRESHOLD_POOR) / (
            _BLUR_THRESHOLD_UNCERTAIN - _BLUR_THRESHOLD_POOR
        )
        return score, "blur"
    else:
        # Sigmoid-like approach to 1.0
        score = min(1.0, 0.8 + 0.2 * min(1.0, (lap_var - _BLUR_THRESHOLD_UNCERTAIN) / 100.0))
        return score, None


def _check_brightness(gray) -> tuple[float, Optional[str]]:
    """
    Mean pixel value check (0-255).
    Returns (score in [0,1], issue_label or None).
    """
    import numpy as np
    mean_brightness = float(np.mean(gray))

    if mean_brightness < _BRIGHTNESS_MIN_POOR or mean_brightness > _BRIGHTNESS_MAX_POOR:
        issue = "underexposed" if mean_brightness < _BRIGHTNESS_MIN_POOR else "overexposed"
        return 0.0, issue
    elif mean_brightness < _BRIGHTNESS_MIN_UNCERTAIN or mean_brightness > _BRIGHTNESS_MAX_UNCERTAIN:
        issue = "underexposed" if mean_brightness < _BRIGHTNESS_MIN_UNCERTAIN else "overexposed"
        # Partial score
        if mean_brightness < _BRIGHTNESS_MIN_UNCERTAIN:
            score = 0.3 + 0.4 * (mean_brightness - _BRIGHTNESS_MIN_POOR) / (
                _BRIGHTNESS_MIN_UNCERTAIN - _BRIGHTNESS_MIN_POOR
            )
        else:
            score = 0.3 + 0.4 * (1.0 - (mean_brightness - _BRIGHTNESS_MAX_UNCERTAIN) / (
                _BRIGHTNESS_MAX_POOR - _BRIGHTNESS_MAX_UNCERTAIN
            ))
        return max(0.0, min(0.7, score)), issue
    else:
        # Good brightness range: 25–235
        # Score peaks at middle of ideal range (around 128)
        center = 128.0
        spread = 100.0
        score = 1.0 - min(1.0, abs(mean_brightness - center) / spread) * 0.15
        return score, None


def _check_overexposure(gray) -> tuple[float, Optional[str]]:
    """
    Fraction of pixels near saturation (>=245).
    Returns (score in [0,1], issue_label or None).
    """
    import numpy as np
    saturated_fraction = float(np.mean(gray >= 245.0))

    if saturated_fraction >= _OVEREXPOSURE_POOR_FRACTION:
        score = max(0.0, 1.0 - saturated_fraction)
        return score * 0.3, "overexposed"
    elif saturated_fraction >= _OVEREXPOSURE_UNCERTAIN_FRACTION:
        score = 0.5 + 0.4 * (1.0 - (saturated_fraction - _OVEREXPOSURE_UNCERTAIN_FRACTION) / (
            _OVEREXPOSURE_POOR_FRACTION - _OVEREXPOSURE_UNCERTAIN_FRACTION
        ))
        return score, "overexposed"
    else:
        return 1.0, None


def _check_contrast(gray) -> tuple[float, Optional[str]]:
    """
    Standard deviation of grayscale — measures tonal range.
    Returns (score in [0,1], issue_label or None).
    """
    import numpy as np
    std_dev = float(np.std(gray))

    if std_dev < _CONTRAST_POOR:
        score = max(0.0, std_dev / _CONTRAST_POOR) * 0.3
        return score, "low_contrast"
    elif std_dev < _CONTRAST_UNCERTAIN:
        score = 0.3 + 0.5 * (std_dev - _CONTRAST_POOR) / (
            _CONTRAST_UNCERTAIN - _CONTRAST_POOR
        )
        return score, "low_contrast"
    else:
        return 1.0, None


# ── Message builder ──────────────────────────────────────────────────────────

_ISSUE_LABELS = {
    "blur": "Image is too blurry for reliable inspection.",
    "underexposed": "Image is too dark for reliable inspection.",
    "overexposed": "Image is too bright or overexposed.",
    "low_contrast": "Image has insufficient contrast.",
    "too_small": "Image dimensions are too small.",
    "unreadable": "Image could not be read.",
}


def _build_message(issues: List[str], *, uncertain: bool) -> str:
    if not issues:
        if uncertain:
            return "Image quality is marginal. Inspection may be less reliable."
        return "Image quality is poor. Please retake the image."

    descriptions = [_ISSUE_LABELS.get(i, i) for i in issues[:2]]  # max 2 to keep concise
    base = " ".join(descriptions)
    if uncertain:
        return f"{base} Inspection will proceed but reliability may be reduced."
    return f"{base} Please retake the image."


# ── Module-level singleton ───────────────────────────────────────────────────
image_quality_gate = ImageQualityGate()

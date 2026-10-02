"""
Image preprocessing utilities.
Handles EXIF orientation, RGB conversion, size validation, and inference copies.
"""
import io
from PIL import Image, ImageOps
from app.core.config import settings
from app.core.exceptions import InvalidImageError, ImageTooLargeError
from app.core.logging import get_logger

logger = get_logger(__name__)

ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_INFERENCE_DIMENSION = 1024  # max side for inference copy


def validate_and_preprocess(
    image_bytes: bytes,
    content_type: str | None = None,
    lossless_inference: bool = False,
) -> tuple[bytes, bytes]:
    """
    Validate and preprocess an uploaded image.
    
    Returns:
        (original_bytes, inference_bytes)
        - original_bytes: EXIF-corrected original (kept for storage)
        - inference_bytes: Downscaled JPEG for AI inference
    """
    # Size check
    if len(image_bytes) > settings.MAX_UPLOAD_BYTES:
        raise ImageTooLargeError(settings.MAX_UPLOAD_MB)

    # Open and validate
    try:
        pil_img = Image.open(io.BytesIO(image_bytes))
        pil_img.verify()  # raises if corrupt
    except Exception:
        raise InvalidImageError("Image file is corrupt or unreadable.")

    # Re-open after verify (verify closes the file)
    try:
        pil_img = Image.open(io.BytesIO(image_bytes))
    except Exception:
        raise InvalidImageError()

    # EXIF orientation correction
    pil_img = ImageOps.exif_transpose(pil_img)

    # Convert to RGB
    if pil_img.mode not in ("RGB", "L"):
        pil_img = pil_img.convert("RGB")
    elif pil_img.mode == "L":
        pil_img = pil_img.convert("RGB")

    # Save as corrected original (JPEG for storage efficiency)
    original_buf = io.BytesIO()
    pil_img.save(original_buf, format="JPEG", quality=92)
    original_bytes = original_buf.getvalue()

    # Create inference copy (downscaled if needed)
    inference_img = pil_img.copy()
    w, h = inference_img.size
    if not lossless_inference and max(w, h) > MAX_INFERENCE_DIMENSION:
        scale = MAX_INFERENCE_DIMENSION / max(w, h)
        new_w = int(w * scale)
        new_h = int(h * scale)
        inference_img = inference_img.resize((new_w, new_h), Image.LANCZOS)
        logger.debug(f"Image downscaled from {w}x{h} to {new_w}x{new_h} for inference")

    inference_buf = io.BytesIO()
    if lossless_inference:
        inference_img.save(inference_buf, format="PNG")
    else:
        inference_img.save(inference_buf, format="JPEG", quality=88)
    inference_bytes = inference_buf.getvalue()

    return original_bytes, inference_bytes

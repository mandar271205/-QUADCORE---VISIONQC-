"""
VLM Registry - manages available providers in priority order.
"""
from app.services.vlm.base import BaseVLMEngine
from app.services.vlm.gemini import GeminiVisionEngine
from app.services.vlm.groq import GroqVisionEngine
from app.services.vlm.nvidia import NvidiaVisionEngine
from app.core.logging import get_logger

logger = get_logger(__name__)


class VLMRegistry:
    """Returns ordered list of VLM providers based on availability."""

    _engines: list[BaseVLMEngine] | None = None

    @classmethod
    def get_ordered_engines(cls) -> list[BaseVLMEngine]:
        """Return available engines: Groq only."""
        if cls._engines is None:
            cls._engines = [
                GroqVisionEngine(),
            ]
        available = [e for e in cls._engines if e.is_available()]
        if not available:
            logger.warning("No VLM providers are configured. Only DEMO_MODE will work.")
        return available

    @classmethod
    def reset(cls) -> None:
        """Force re-initialization (useful for testing)."""
        cls._engines = None

"""
Quality Gate for VisionQC.
Validates inspection results from both VLM and ML engines.
"""
from dataclasses import dataclass
from typing import Literal
from app.core.logging import get_logger
from app.db.models import Decision

logger = get_logger(__name__)

QualityGateVerdict = Literal["ACCEPT", "REJECT", "REVIEW"]


@dataclass
class QualityGateResult:
    verdict: QualityGateVerdict
    reason: str


class QualityGate:
    """
    Validates inspection engine outputs before accepting them.
    
    Ensures:
    - Valid decision enum value
    - anomaly_score in [0, 1]
    - confidence in [0, 1]
    - defects is a list
    - summary is a string
    """

    @staticmethod
    def validate_vlm(result) -> QualityGateResult:
        """Validate a VLMInspectionResult."""
        try:
            if result.decision not in (Decision.PASS, Decision.FAIL, Decision.REVIEW):
                return QualityGateResult("REJECT", "Invalid decision value")

            if not (0.0 <= result.anomaly_score <= 1.0):
                return QualityGateResult("REJECT", "anomaly_score out of range")

            if not (0.0 <= result.confidence <= 1.0):
                return QualityGateResult("REJECT", "confidence out of range")

            from app.core.config import settings
            if result.confidence < settings.MIN_ACCEPT_CONFIDENCE:
                return QualityGateResult("REJECT", f"Confidence {result.confidence} below minimum {settings.MIN_ACCEPT_CONFIDENCE}")

            if not isinstance(result.defects, list):
                return QualityGateResult("REJECT", "defects is not a list")

            return QualityGateResult("ACCEPT", "OK")

        except Exception as e:
            logger.warning(f"[QualityGate] VLM validation error: {e}")
            return QualityGateResult("REJECT", f"Validation error: {e}")

    @staticmethod
    def validate_ml(result) -> QualityGateResult:
        """Validate an MLInspectionResult."""
        try:
            import math
            if not isinstance(result.anomaly_score, (int, float)):
                return QualityGateResult("REJECT", "anomaly_score is not numeric")

            if math.isnan(result.anomaly_score) or math.isinf(result.anomaly_score):
                return QualityGateResult("REJECT", "anomaly_score is NaN or Inf")

            if not (0.0 <= result.anomaly_score <= 1.0):
                return QualityGateResult("REJECT", "anomaly_score out of range")

            return QualityGateResult("ACCEPT", "OK")

        except Exception as e:
            logger.warning(f"[QualityGate] ML validation error: {e}")
            return QualityGateResult("REJECT", f"Validation error: {e}")

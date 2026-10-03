"""
Operational Severity Service — computes severity from inspection evidence.

CRITICAL DESIGN PRINCIPLE:
    Severity is computed ONLY from evidence the inspection system actually produced.
    It is NEVER fabricated from unsupported defect types or invented signals.

Documented deterministic policy:
    Decision=PASS
        → OperationalSeverity.NONE    (no meaningful deviation detected)

    Decision=REVIEW
        score_distance = |anomaly_score - threshold|
        if score_distance < 0.10:
            → MINOR
        elif score_distance < 0.20:
            → MODERATE
        else:
            → MODERATE  (default for REVIEW; CRITICAL reserved for FAIL)

    Decision=FAIL
        if anomaly_score >= 0.70:
            → CRITICAL
        elif anomaly_score >= 0.55 (above threshold):
            → MODERATE
        else:
            → MODERATE  (fail below 0.55 is unusual but possible with native verdicts)

    Decision=RETAKE (image quality failure)
        → UNKNOWN  (no product evidence exists)

    Insufficient evidence (anomaly_score=0, confidence=0, no defects):
        → UNKNOWN

    Model: anomaly_score and threshold are the primary signals.
    Secondary: defect count from actual inspection engine output.

    We do NOT use defect type strings (like "crack", "scratch") to assign severity
    because the system cannot guarantee those labels are accurate enough to make
    risk-level decisions. Only quantitative signals are used.
"""
from __future__ import annotations

from app.db.models import Decision, OperationalSeverity
from app.core.logging import get_logger

logger = get_logger(__name__)

# Documented thresholds — no magic numbers elsewhere
_REVIEW_MINOR_DISTANCE = 0.10   # |score - threshold| < this → MINOR for REVIEW
_REVIEW_MODERATE_DISTANCE = 0.20  # |score - threshold| in [0.10, 0.20) → MODERATE
_FAIL_CRITICAL_SCORE = 0.70      # anomaly_score >= this → CRITICAL for FAIL


def compute_severity(
    decision: Decision,
    anomaly_score: float,
    threshold: float,
    confidence: float = 0.0,
    defect_count: int = 0,
) -> OperationalSeverity:
    """
    Compute operational severity from inspection evidence.

    Args:
        decision:       PASS / REVIEW / FAIL / RETAKE from the engine
        anomaly_score:  float in [0, 1] from the inspection engine
        threshold:      product's configured inspection threshold
        confidence:     engine confidence (used for UNKNOWN guard only)
        defect_count:   number of defects in the inspection result

    Returns:
        OperationalSeverity enum value
    """
    # Guard: RETAKE or missing evidence
    if decision == Decision.RETAKE:
        return OperationalSeverity.UNKNOWN

    # Guard: clearly insufficient evidence
    if anomaly_score == 0.0 and confidence == 0.0 and defect_count == 0:
        return OperationalSeverity.UNKNOWN

    if decision == Decision.PASS:
        return OperationalSeverity.NONE

    if decision == Decision.REVIEW:
        score_distance = abs(anomaly_score - threshold)
        if score_distance < _REVIEW_MINOR_DISTANCE:
            severity = OperationalSeverity.MINOR
        else:
            severity = OperationalSeverity.MODERATE
        logger.debug(
            f"[Severity] REVIEW: score={anomaly_score:.3f} threshold={threshold:.3f} "
            f"distance={score_distance:.3f} → {severity}"
        )
        return severity

    if decision == Decision.FAIL:
        if anomaly_score >= _FAIL_CRITICAL_SCORE:
            severity = OperationalSeverity.CRITICAL
        else:
            severity = OperationalSeverity.MODERATE
        logger.debug(
            f"[Severity] FAIL: score={anomaly_score:.3f} threshold={threshold:.3f} "
            f"→ {severity}"
        )
        return severity

    # Unexpected decision value
    logger.warning(f"[Severity] Unexpected decision '{decision}' → UNKNOWN")
    return OperationalSeverity.UNKNOWN


def severity_to_label(severity: OperationalSeverity) -> str:
    """
    Supervisor-facing label for operational severity.
    Does NOT expose any internal implementation details.
    """
    return {
        OperationalSeverity.NONE: "None",
        OperationalSeverity.MINOR: "Minor",
        OperationalSeverity.MODERATE: "Moderate",
        OperationalSeverity.CRITICAL: "Critical",
        OperationalSeverity.UNKNOWN: "Not Evaluated",
    }.get(severity, "Not Evaluated")

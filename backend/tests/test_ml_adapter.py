import pytest
import io
from PIL import Image
from app.services.ml.base import BaseMLEngine, MLInspectionResult
from app.services.ml.mock import MockMLEngine
from app.services.quality_gate import QualityGate
from app.services.vlm.base import VLMInspectionResult
from app.db.models import Decision


def _create_sample_image() -> bytes:
    img = Image.new("RGB", (100, 100), color=(128, 128, 128))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


@pytest.mark.asyncio
async def test_mock_ml_engine_contract():
    engine = MockMLEngine()
    assert isinstance(engine, BaseMLEngine)

    img_bytes = _create_sample_image()
    result = await engine.inspect(img_bytes)

    assert isinstance(result, MLInspectionResult)
    assert 0.0 <= result.anomaly_score <= 1.0
    assert 0.0 <= result.confidence <= 1.0
    assert result.latency_ms >= 0
    assert result.anomaly_map is not None
    assert result.anomaly_map.shape == (64, 64)


def test_quality_gate_accept():
    good_result = VLMInspectionResult(
        decision=Decision.PASS,
        anomaly_score=0.2,
        confidence=0.92,
        defects=[],
        summary="Optimal surface finish detected.",
        provider="gemini",
        latency_ms=120,
    )
    gate = QualityGate.validate_vlm(good_result)
    assert gate.verdict == "ACCEPT"


def test_quality_gate_reject_low_confidence():
    low_conf_result = VLMInspectionResult(
        decision=Decision.PASS,
        anomaly_score=0.2,
        confidence=0.45,  # below MIN_ACCEPT_CONFIDENCE (0.70)
        defects=[],
        summary="Unclear reading.",
        provider="gemini",
        latency_ms=120,
    )
    gate = QualityGate.validate_vlm(low_conf_result)
    assert gate.verdict == "REJECT"
    assert "confidence" in gate.reason.lower()

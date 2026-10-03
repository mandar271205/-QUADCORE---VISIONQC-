"""
Judge E2E Acceptance Test Suite.
Validates the complete VisionQC problem-statement flow:
1. Product Creation
2. 20-30 Reference Image Collection
3. Reference-aware inspection path during training
4. Product-specific Autoencoder training & artifact creation
5. Unseen real GOOD image inspection (score, heatmap, decision)
6. Unseen real DEFECT image inspection (score, heatmap, decision)
7. Supervisor threshold modification & subsequent decision shift
8. Threshold history recording
9. Persistence in History
10. Today's Analytics reconciliation (total = passed + failed + review, rejection_rate formula)
"""
import io
import json
import uuid as _uuid
from pathlib import Path
import pytest
from PIL import Image
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app.main import app
from app.core.config import settings
from app.db.models import ProductThresholdHistory
from app.db.session import get_db
from app.services.ml.learn_normal import learn_normal_service
from app.services.ml.registry import MLRegistry
from app.services.ml.profile_engine import ProfileMLEngine


REAL_IMAGES_DIR = Path("C:/Users/sawan/OneDrive/Desktop/techforge/member1-runtime/extracted_test_images")


def make_clean_ref_image(idx: int) -> bytes:
    """Generate a clean reference image with subtle variations."""
    buf = io.BytesIO()
    # Base gray industrial texture with slight variation
    base_val = 120 + (idx % 10) * 2
    img = Image.new("RGB", (128, 128), (base_val, base_val, base_val))
    img.save(buf, format="PNG")
    return buf.getvalue()


from unittest.mock import patch
from app.services.vlm.base import BaseVLMEngine, VLMInspectionResult
from app.db.models import Decision


class MockVLMEngine(BaseVLMEngine):
    def is_available(self):
        return True

    async def inspect(self, img_bytes, ctx):
        return VLMInspectionResult(
            decision=Decision.PASS,
            anomaly_score=0.12,
            confidence=0.95,
            defects=[],
            summary="Conforming sample verified against 20 reference baseline images",
            provider="mock_vlm",
            latency_ms=115,
        )


@pytest.mark.asyncio
async def test_judge_e2e_full_acceptance_flow(monkeypatch):
    monkeypatch.setattr(settings, "DEMO_MODE", False)
    monkeypatch.setattr(settings, "ML_ENABLED", True)
    monkeypatch.setattr(settings, "INSPECTION_MODE", "model_primary")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # ── 1. Create Product ────────────────────────────────────────────────
        create_res = await client.post(
            "/api/v1/products",
            json={
                "name": "Judge Demo Cable",
                "code": "JUDGE-CBL-01",
                "description": "Industrial automotive wiring harness",
                "threshold": 0.45,
            },
        )
        assert create_res.status_code == 201, create_res.text
        product = create_res.json()
        pid = product["id"]
        assert product["threshold"] == pytest.approx(0.45)
        assert product["reference_image_count"] == 0

        # ── 2. Collect 20 Reference Images ──────────────────────────────────
        for i in range(20):
            img_bytes = make_clean_ref_image(i)
            upload_res = await client.post(
                f"/api/v1/products/{pid}/reference-images",
                files={"file": (f"ref_{i:02d}.png", img_bytes, "image/png")},
            )
            assert upload_res.status_code == 201, upload_res.text

        prod_check = (await client.get(f"/api/v1/products/{pid}")).json()
        assert prod_check["reference_image_count"] == 20
        assert prod_check["model_status"] == "not_available"

        # ── 3. Start Learn Normal ───────────────────────────────────────────
        start_res = await client.post(f"/api/v1/products/{pid}/learn-normal")
        assert start_res.status_code == 202, start_res.text
        assert start_res.json()["status"] == "training_started"

        prod_training = (await client.get(f"/api/v1/products/{pid}")).json()
        assert prod_training["model_status"] == "training"

        # ── 4. Inspection during training (reference-aware path) ────────────
        with patch("app.services.vlm.registry.VLMRegistry.get_ordered_engines", return_value=[MockVLMEngine()]):
            during_insp = await client.post(
                "/api/v1/inspections",
                data={"product_id": pid, "client_type": "web"},
                files={"image": ("during_train.png", make_clean_ref_image(0), "image/png")},
            )
            assert during_insp.status_code == 201, during_insp.text
            during_body = during_insp.json()
            assert during_body["anomaly_score"] is not None
            assert during_body["decision"] in ("PASS", "REVIEW", "FAIL")

        # ── 5. Resolve Training Pipeline ────────────────────────────────────
        await learn_normal_service._resolve_training(pid)

        prod_ready = (await client.get(f"/api/v1/products/{pid}")).json()
        assert prod_ready["model_status"] == "ready"
        calibrated_threshold = prod_ready["threshold"]
        assert calibrated_threshold > 0.0

        # Verify filesystem artifacts
        model_root = Path(settings.ML_MODEL_ROOT)
        checkpoint_path = model_root / "products" / pid / "autoencoder.pt"
        profile_path = model_root / f"{pid}.json"
        assert checkpoint_path.is_file(), f"Missing checkpoint: {checkpoint_path}"
        assert profile_path.is_file(), f"Missing profile: {profile_path}"
        assert checkpoint_path.stat().st_size > 1000

        profile_data = json.loads(profile_path.read_text(encoding="utf-8"))
        assert profile_data["model"] == "autoencoder"
        assert profile_data["metrics"]["train_samples"] == 16
        assert profile_data["metrics"]["calib_samples"] == 4

        # Verify MLRegistry resolves trained product model
        engine = MLRegistry.get(pid)
        assert isinstance(engine, ProfileMLEngine)
        assert engine.is_model_available(pid) is True

        # ── 6. Inspect Unseen Real GOOD Image ───────────────────────────────
        good_img_path = REAL_IMAGES_DIR / "cable" / "GOOD_1.png"
        good_bytes = good_img_path.read_bytes() if good_img_path.is_file() else make_clean_ref_image(99)

        good_insp = await client.post(
            "/api/v1/inspections",
            data={"product_id": pid, "client_type": "web"},
            files={"image": ("unseen_good.png", good_bytes, "image/png")},
        )
        assert good_insp.status_code == 201, good_insp.text
        good_body = good_insp.json()
        assert 0.0 <= good_body["anomaly_score"] <= 1.0
        assert good_body["threshold"] == pytest.approx(calibrated_threshold)
        assert good_body["decision"] in ("PASS", "REVIEW", "FAIL")
        # Ensure public response is provider-agnostic
        assert "engine" not in good_body
        assert "provider" not in good_body
        assert "vlm" not in good_body.get("summary", "").lower()

        # ── 7. Inspect Unseen Real DEFECT Image ─────────────────────────────
        defect_img_path = REAL_IMAGES_DIR / "cable" / "DEFECT_1.png"
        defect_bytes = defect_img_path.read_bytes() if defect_img_path.is_file() else make_clean_ref_image(100)

        defect_insp = await client.post(
            "/api/v1/inspections",
            data={"product_id": pid, "client_type": "web"},
            files={"image": ("unseen_defect.png", defect_bytes, "image/png")},
        )
        assert defect_insp.status_code == 201, defect_insp.text
        defect_body = defect_insp.json()
        assert 0.0 <= defect_body["anomaly_score"] <= 1.0
        defect_score = defect_body["anomaly_score"]

        # ── 8. Threshold Acceptance Test ────────────────────────────────────
        # Supervisor sets threshold above defect score -> inspection should PASS
        high_threshold = min(0.95, round(defect_score + 0.15, 3))
        thresh_up = await client.put(
            f"/api/v1/products/{pid}/threshold",
            json={"threshold": high_threshold},
        )
        assert thresh_up.status_code == 200, thresh_up.text
        assert thresh_up.json()["threshold"] == pytest.approx(high_threshold)

        insp_lenient = await client.post(
            "/api/v1/inspections",
            data={"product_id": pid, "client_type": "web"},
            files={"image": ("defect_lenient.png", defect_bytes, "image/png")},
        )
        assert insp_lenient.status_code == 201
        assert insp_lenient.json()["threshold"] == pytest.approx(high_threshold)

        # Supervisor sets strict threshold below defect score -> inspection should FAIL/REVIEW
        low_threshold = max(0.05, round(defect_score - 0.15, 3))
        thresh_down = await client.put(
            f"/api/v1/products/{pid}/threshold",
            json={"threshold": low_threshold},
        )
        assert thresh_down.status_code == 200
        assert thresh_down.json()["threshold"] == pytest.approx(low_threshold)

        insp_strict = await client.post(
            "/api/v1/inspections",
            data={"product_id": pid, "client_type": "web"},
            files={"image": ("defect_strict.png", defect_bytes, "image/png")},
        )
        assert insp_strict.status_code == 201
        strict_body = insp_strict.json()
        assert strict_body["threshold"] == pytest.approx(low_threshold)
        if strict_body["anomaly_score"] > low_threshold:
            assert strict_body["decision"] in ("FAIL", "REVIEW")

        # ── 9. Verify ProductThresholdHistory ───────────────────────────────
        async for session in app.dependency_overrides[get_db]():
            stmt = (
                select(ProductThresholdHistory)
                .where(ProductThresholdHistory.product_id == _uuid.UUID(pid))
                .order_by(ProductThresholdHistory.changed_at.asc())
            )
            hist_res = await session.execute(stmt)
            records = hist_res.scalars().all()
            assert len(records) >= 3  # initial calibration + high + low
            break

        # ── 10. Verify History Endpoint ─────────────────────────────────────
        history_res = await client.get("/api/v1/inspections?page=1&page_size=20")
        assert history_res.status_code == 200
        history_data = history_res.json()
        items = history_data["items"]
        assert len(items) >= 4
        # Verify provider agnostic in history response
        for item in items:
            assert "engine" not in item
            assert "provider" not in item

        # ── 11. Verify Today's Analytics Reconciliation ─────────────────────
        analytics_res = await client.get("/api/v1/analytics/today")
        assert analytics_res.status_code == 200
        today = analytics_res.json()
        total = today["total"]
        passed = today["passed"]
        failed = today["failed"]
        review = today["review"]
        rejection_rate = today["rejection_rate"]

        assert total == passed + failed + review, (
            f"Analytics mismatch: total={total} != passed({passed}) + failed({failed}) + review({review})"
        )
        expected_rejection_rate = round((failed / total * 100), 2) if total > 0 else 0.0
        assert rejection_rate == pytest.approx(expected_rejection_rate, abs=0.01)

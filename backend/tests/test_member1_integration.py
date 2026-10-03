"""Member 1 stays explicitly bound and isolated from Member 2 inference."""
import asyncio
import json
import uuid

import numpy as np
import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.core.exceptions import InspectionFailedError
from app.db.models import Decision
from app.main import app
from app.services.inspection_router import InspectionRouter, _ml_to_internal
from app.services.ml.member1_engine import Member1PatchCoreEngine
from app.services.ml.member1_worker.client import Member1WorkerClient
from app.services.ml.profile_engine import ProfileMLEngine
from app.services.ml.registry import MLRegistry

CATEGORIES = ("bottle", "cable", "capsule", "metal_nut", "screw", "transistor")


def make_member1_root(root):
    (root / "outputs" / "checkpoints").mkdir(parents=True)
    categories = {}
    for category in CATEGORIES:
        folder = root / "outputs" / "checkpoints" / category
        folder.mkdir()
        checkpoint = f"outputs/checkpoints/{category}/patchcore_{category}.ckpt"
        (root / checkpoint).write_bytes(b"fixture checkpoint; never loaded by these tests")
        categories[category] = {
            "model": "PatchCore", "backbone": "wide_resnet50_2",
            "checkpoint": checkpoint,
        }
    (root / "model_manifest.json").write_text(json.dumps({
        "primary_model": "PatchCore",
        "supported_categories": list(CATEGORIES),
        "patchcore": categories,
    }))


@pytest.mark.asyncio
async def test_member1_profiles_bind_explicit_category_without_member2(monkeypatch, tmp_path):
    model_root = tmp_path / "member2-models"
    m1_root = tmp_path / "member1-mount"
    model_root.mkdir()
    make_member1_root(m1_root)
    monkeypatch.setattr(settings, "ML_MODEL_ROOT", str(model_root))
    monkeypatch.setattr(settings, "ML_M1_MODEL_ROOT", str(m1_root))
    monkeypatch.setattr(settings, "ML_ENABLED", False)
    monkeypatch.setattr(settings, "ML_M1_ENABLED", True)
    monkeypatch.setattr(settings, "DEMO_MODE", False)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        profiles = (await client.get("/api/v1/products/trained-profiles")).json()
        assert [item["category"] for item in profiles] == list(CATEGORIES)
        assert all(item["id"].startswith("member1/mvtec_ad/") for item in profiles)
        product = (await client.post("/api/v1/products", json={
            "name": "Explicit cable fixture", "code": "M1-CABLE",
        })).json()
        assignment = await client.put(
            f"/api/v1/products/{product['id']}/model-profile",
            json={"profile_id": "member1/mvtec_ad/cable"},
        )
        assert assignment.status_code == 200, assignment.text

    definition = json.loads((model_root / f"{product['id']}.json").read_text())
    assert definition == {
        "model": "member1_patchcore", "dataset": "mvtec_ad", "category": "cable",
    }
    engine = MLRegistry.get(product["id"])
    assert isinstance(engine, Member1PatchCoreEngine)
    assert engine.is_model_available(product["id"])
    assert not ProfileMLEngine().is_model_available(product["id"])
    assert MLRegistry.get(str(uuid.uuid4())) is None

    # Rebinding the same product to Member 2 replaces the canonical UUID
    # definition, so the stale Member 1 category cannot win registry routing.
    (model_root / "member2.ckpt").write_bytes(b"fixture checkpoint")
    other_product_id = str(uuid.uuid4())
    (model_root / f"{other_product_id}.json").write_text(json.dumps({
        "model": "patchcore", "checkpoint": "member2.ckpt",
    }))
    assert MLRegistry.get(other_product_id) is None  # Member 2 toggle remains independent.
    profile = {
        "id": "mvtec_ad/cable", "label": "Cable", "dataset": "mvtec_ad",
        "category": "cable", "metrics": {"f2": 0.9},
        "definition": {"model": "patchcore", "checkpoint": "member2.ckpt"},
    }
    (model_root / "catalog.json").write_text(json.dumps({profile["id"]: profile}))
    monkeypatch.setattr(settings, "ML_ENABLED", True)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        switched = await client.put(
            f"/api/v1/products/{product['id']}/model-profile",
            json={"profile_id": "mvtec_ad/cable"},
        )
        assert switched.status_code == 200, switched.text
    assert isinstance(MLRegistry.get(product["id"]), ProfileMLEngine)


def test_member1_artifact_validation_rejects_traversal_and_missing_files(monkeypatch, tmp_path):
    from app.services.ml.member1_artifacts import member1_checkpoint
    make_member1_root(tmp_path)
    monkeypatch.setattr(settings, "ML_M1_MODEL_ROOT", str(tmp_path))
    assert member1_checkpoint("bottle") is not None
    assert member1_checkpoint("../outside") is None
    (tmp_path / "model_manifest.json").write_text(json.dumps({
        "primary_model": "PatchCore",
        "supported_categories": ["bottle"],
        "patchcore": {"bottle": {"model": "PatchCore", "checkpoint": "../../outside.ckpt"}},
    }))
    assert member1_checkpoint("bottle") is None


def test_native_verdict_and_threshold_are_preserved_for_member1():
    from app.services.ml.base import MLInspectionResult
    result = MLInspectionResult(
        anomaly_score=0.91,
        anomaly_map=np.array([[0.0, 2.0], [4.0, 8.0]], dtype=np.float32),
        threshold=0.73,
        native_verdict="PASS",
    )
    internal = _ml_to_internal(result, threshold=0.5)
    assert internal.decision == Decision.PASS
    assert internal.anomaly_score == 0.91
    assert internal.threshold == 0.73
    assert internal.anomaly_map is not None


def test_worker_environment_does_not_forward_application_secrets(monkeypatch, tmp_path):
    monkeypatch.setenv("GOOGLE_API_KEY", "must-not-cross-runtime-boundary")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "must-not-cross-runtime-boundary")
    client = Member1WorkerClient()
    child_env = client._safe_environment("python", tmp_path)
    assert "GOOGLE_API_KEY" not in child_env
    assert "SUPABASE_SERVICE_ROLE_KEY" not in child_env
    assert child_env["VISIONQC_M1_MODEL_ROOT"] == str(tmp_path.resolve())
    assert child_env["TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD"] == "1"
    assert child_env["HF_HUB_OFFLINE"] == "1"
    assert child_env["TRANSFORMERS_OFFLINE"] == "1"


@pytest.mark.asyncio
async def test_readiness_reports_member_mounts_without_starting_worker(monkeypatch, tmp_path):
    from app.api.v1 import system

    member1_root = tmp_path / "member1"
    member2_root = tmp_path / "member2-models"
    experiments_root = tmp_path / "member2-experiments"
    make_member1_root(member1_root)
    member2_root.mkdir()
    experiments_root.mkdir()

    async def healthy_database():
        return True

    monkeypatch.setattr(system, "check_db_health", healthy_database)
    monkeypatch.setattr(system.storage_service, "is_available", lambda: False)
    monkeypatch.setattr(settings, "DEMO_MODE", False)
    monkeypatch.setattr(settings, "INSPECTION_MODE", "model_only")
    monkeypatch.setattr(settings, "ML_M1_ENABLED", True)
    monkeypatch.setattr(settings, "ML_M1_MODEL_ROOT", str(member1_root))
    monkeypatch.setattr(settings, "ML_MODEL_ROOT", str(member2_root))
    monkeypatch.setattr(settings, "ML_EXPERIMENT_ROOT", str(experiments_root))
    monkeypatch.setattr(settings, "ML_ENABLED", False)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        status = (await client.get("/api/v1/system/status")).json()
    assert status["member1_runtime"]["configured"] is True
    assert status["member1_runtime"]["available_categories"] == list(CATEGORIES)
    assert status["member1_runtime"]["worker_alive"] is False
    assert status["member2_runtime"]["model_root_mounted"] is True
    assert status["member2_runtime"]["experiment_root_mounted"] is True


@pytest.mark.asyncio
async def test_model_only_applies_timeout_without_vlm_fallback(monkeypatch):
    class SlowEngine:
        is_member1 = True

        def is_model_available(self, product_id=None):
            return True

        async def inspect(self, image_bytes, product_id=None):
            await asyncio.sleep(1)

    from app.services.inspection_router import InspectionRouter
    from app.services.vlm.base import ProductContext
    monkeypatch.setattr(MLRegistry, "get", lambda _product_id: SlowEngine())
    router = InspectionRouter()
    monkeypatch.setattr(router, "_ml_timeout", lambda _engine: 0.01)
    with pytest.raises(InspectionFailedError):
        await router._model_only(b"frame", ProductContext(product_id="fixture"))


@pytest.mark.asyncio
async def test_worker_timeout_kills_process_before_protocol_reuse(monkeypatch):
    class FakeProcess:
        returncode = None

        def kill(self):
            self.returncode = -9

        async def wait(self):
            return self.returncode

    client = Member1WorkerClient()
    process = FakeProcess()
    client._process = process
    client._runtime_info = {"runtime_version": "fixture"}

    async def stalled_exchange(_payload):
        await asyncio.sleep(1)

    monkeypatch.setattr(client, "_exchange_locked", stalled_exchange)
    with pytest.raises(asyncio.TimeoutError):
        await client._request({"action": "inspect"}, timeout=0.01)
    assert process.returncode == -9
    assert not client.is_running

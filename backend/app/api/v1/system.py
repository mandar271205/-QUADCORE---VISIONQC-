import asyncio
from fastapi import APIRouter
from app.db.session import check_db_health
from app.services.storage.supabase import check_storage_health
from app.services.storage.supabase import storage_service
from app.core.config import settings
from pathlib import Path
from app.services.ml.member1_artifacts import available_member1_categories
from app.services.ml.member1_worker.client import member1_worker

router = APIRouter()


@router.get("/status")
async def system_status():
    """
    Generic system status endpoint.
    Never exposes provider names, API keys, or internal engine details.
    """
    async def storage_health():
        return not storage_service.is_available() or await check_storage_health()

    db_ok, storage_ok = await asyncio.gather(check_db_health(), storage_health())
    from app.services.ml.registry import MLRegistry
    from app.services.vlm.registry import VLMRegistry
    profile_paths = set(Path(settings.ML_MODEL_ROOT).glob('*.json'))
    ml_ok = any(MLRegistry.get(path.stem) is not None for path in profile_paths)
    vlm_available = bool(VLMRegistry.get_ordered_engines())
    member1_categories = available_member1_categories()
    member1_runtime = member1_worker.runtime_info if member1_worker.is_running else None
    try:
        from app.services.ml.catalog import public_profiles
        member2_catalog_available = any(
            not profile['id'].startswith('member1/') for profile in public_profiles()
        )
    except (OSError, ValueError, TypeError):
        member2_catalog_available = False
    member2_models_mounted = Path(settings.ML_MODEL_ROOT).is_dir()
    member2_experiments_mounted = Path(settings.ML_EXPERIMENT_ROOT).is_dir()
    if settings.INSPECTION_MODE == 'model_only':
        engine_ok = ml_ok
    elif settings.INSPECTION_MODE == 'vlm_only' or settings.INSPECTION_MODE == 'vlm_primary':
        engine_ok = vlm_available
    else:
        engine_ok = ml_ok or vlm_available
    inspection_available = db_ok and (settings.DEMO_MODE or engine_ok)

    return {
        "inspection_available": inspection_available,
        "database_available": db_ok,
        "storage_available": storage_ok,
        "vlm_available": vlm_available,
        "member1_runtime": {
            "enabled": settings.ML_M1_ENABLED,
            "configured": bool(member1_categories),
            "available_categories": member1_categories,
            "worker_alive": member1_worker.is_running,
            "runtime_version": member1_runtime.get("runtime_version") if member1_runtime else None,
            "python_version": member1_runtime.get("python_version") if member1_runtime else None,
        },
        "member2_runtime": {
            "enabled": settings.ML_ENABLED,
            "catalog_available": member2_catalog_available,
            "model_root_mounted": member2_models_mounted,
            "experiment_root_mounted": member2_experiments_mounted,
        },
    }

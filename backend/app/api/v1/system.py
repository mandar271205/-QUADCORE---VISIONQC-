from fastapi import APIRouter
from app.db.session import check_db_health
from app.services.storage.supabase import check_storage_health
from app.services.storage.supabase import storage_service
from app.core.config import settings
from pathlib import Path

router = APIRouter()


@router.get("/status")
async def system_status():
    """
    Generic system status endpoint.
    Never exposes provider names, API keys, or internal engine details.
    """
    db_ok = await check_db_health()
    storage_ok = not storage_service.is_available() or await check_storage_health()
    from app.services.ml.registry import MLRegistry
    from app.services.vlm.registry import VLMRegistry
    ml_ok = settings.ML_ENABLED and any(MLRegistry.get(path.stem) is not None
                                       for path in Path(settings.ML_MODEL_ROOT).glob('*.json'))
    if settings.INSPECTION_MODE == 'model_only':
        engine_ok = ml_ok
    elif settings.INSPECTION_MODE == 'vlm_only' or settings.INSPECTION_MODE == 'vlm_primary':
        engine_ok = bool(VLMRegistry.get_ordered_engines())
    else:
        engine_ok = ml_ok or bool(VLMRegistry.get_ordered_engines())
    inspection_available = db_ok and (settings.DEMO_MODE or engine_ok)

    return {
        "inspection_available": inspection_available,
        "database_available": db_ok,
        "storage_available": storage_ok,
    }

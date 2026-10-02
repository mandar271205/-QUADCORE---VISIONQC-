from fastapi import APIRouter
from app.db.session import check_db_health
from app.services.storage.supabase import check_storage_health

router = APIRouter()


@router.get("/status")
async def system_status():
    """
    Generic system status endpoint.
    Never exposes provider names, API keys, or internal engine details.
    """
    db_ok = await check_db_health()
    storage_ok = await check_storage_health()
    inspection_available = db_ok  # At minimum we need DB

    return {
        "inspection_available": inspection_available,
        "database_available": db_ok,
        "storage_available": storage_ok,
    }

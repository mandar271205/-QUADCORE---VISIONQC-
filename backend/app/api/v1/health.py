from fastapi import APIRouter
from app.db.session import check_db_health

router = APIRouter()


@router.get("/health")
async def health_check():
    """Basic health check endpoint."""
    db_ok = await check_db_health()
    return {
        "status": "ok",
        "database": "connected" if db_ok else "unreachable",
    }


@router.get("/ready")
async def ready_check():
    """Readiness probe endpoint for Kubernetes / orchestration."""
    db_ok = await check_db_health()
    return {
        "status": "ready" if db_ok else "degraded",
        "database": "connected" if db_ok else "unreachable",
    }


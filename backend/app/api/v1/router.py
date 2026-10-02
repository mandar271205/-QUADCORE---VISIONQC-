from fastapi import APIRouter
from app.api.v1 import health, products, inspections, analytics, system, experiments

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(health.router, tags=["Health"])
api_router.include_router(products.router, prefix="/products", tags=["Products"])
api_router.include_router(inspections.router, prefix="/inspections", tags=["Inspections"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["Analytics"])
api_router.include_router(system.router, prefix="/system", tags=["System"])
api_router.include_router(experiments.router, prefix="/experiments", tags=["Experiments"])

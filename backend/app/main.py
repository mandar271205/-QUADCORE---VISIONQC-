"""
VisionQC FastAPI Application Entry Point.
"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.logging import setup_logging, get_logger
from app.core.exceptions import VisionQCException, visionqc_exception_to_http
from app.api.v1.router import api_router

# Setup logging first
setup_logging()
logger = get_logger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(
        title="VisionQC API",
        description="AI-Powered Visual Quality Inspection System",
        version="1.0.0",
        docs_url="/docs" if settings.APP_ENV == "development" else None,
        redoc_url="/redoc" if settings.APP_ENV == "development" else None,
    )

    # CORS - allow frontend and Expo Go
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Restrict in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Global exception handlers
    @app.exception_handler(VisionQCException)
    async def visionqc_exception_handler(request: Request, exc: VisionQCException):
        http_exc = visionqc_exception_to_http(exc)
        return JSONResponse(
            status_code=http_exc.status_code,
            content={"detail": http_exc.detail},
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        logger.error(f"Unhandled exception: {type(exc).__name__}: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"detail": "An unexpected error occurred. Please try again."},
        )

    # Include API routes
    app.include_router(api_router)

    # Root health endpoints
    from app.api.v1.health import router as health_router
    app.include_router(health_router, tags=["Health"])

    @app.on_event("startup")
    async def startup():
        logger.info(f"VisionQC starting | env={settings.APP_ENV} | mode={settings.INSPECTION_MODE} | demo={settings.DEMO_MODE}")
        try:
            from app.db.session import engine
            from app.db.base import Base
            import app.db.models  # noqa
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("Database tables initialized successfully.")
        except Exception as e:
            logger.warning(f"Database initialization notice: {e}")

    @app.on_event("shutdown")
    async def shutdown():
        from app.services.ml.member1_worker.client import member1_worker
        await member1_worker.shutdown()
        from app.services.vlm.registry import VLMRegistry
        await VLMRegistry.close()
        logger.info("VisionQC shutting down")

    return app


app = create_app()

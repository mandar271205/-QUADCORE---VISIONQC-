from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Create async engine with fallback
db_url = settings.DATABASE_URL.strip() if settings.DATABASE_URL else "sqlite+aiosqlite:///./visionqc.db"

if db_url.startswith("sqlite"):
    engine = create_async_engine(
        db_url,
        echo=settings.APP_ENV == "development",
        connect_args={"check_same_thread": False},
    )
else:
    engine = create_async_engine(
        db_url,
        echo=settings.APP_ENV == "development",
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        pool_recycle=300,
        pool_timeout=15,
        connect_args={
            "statement_cache_size": 0,
            "prepared_statement_cache_size": 0,
        },
    )

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncSession:
    """FastAPI dependency to get a DB session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def check_db_health() -> bool:
    """Check if database is reachable."""
    try:
        async with AsyncSessionLocal() as session:
            from sqlalchemy import text
            await session.execute(text("SELECT 1"))
            await session.close()
        return True
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return False

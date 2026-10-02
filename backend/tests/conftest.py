"""Isolated SQLite database for API tests; never touch a configured production DB."""
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.db.base import Base
from app.db.session import get_db
from app.main import app as application
import app.db.models  # noqa: F401


@pytest_asyncio.fixture(autouse=True)
async def isolated_database(tmp_path, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, 'DEMO_MODE', True)
    monkeypatch.setattr(settings, 'ML_ENABLED', False)
    monkeypatch.setattr(settings, 'INSPECTION_MODE', 'vlm_primary')
    # Tests must never depend on live Supabase Storage.
    # Empty credentials intentionally exercise the local base64 fallback.
    monkeypatch.setattr(settings, 'SUPABASE_URL', '')
    monkeypatch.setattr(settings, 'SUPABASE_SERVICE_ROLE_KEY', '')
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async def test_db():
        async with session_factory() as session:
            yield session

    application.dependency_overrides[get_db] = test_db
    yield
    application.dependency_overrides.pop(get_db, None)
    await engine.dispose()

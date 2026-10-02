import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_today_analytics():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/analytics/today")
        assert res.status_code == 200
        data = res.json()
        assert "total" in data
        assert "passed" in data
        assert "failed" in data
        assert "review" in data
        assert "rejection_rate" in data
        assert "average_anomaly_score" in data
        assert "average_processing_time_ms" in data


@pytest.mark.asyncio
async def test_range_analytics():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/analytics")
        assert res.status_code == 200
        data = res.json()
        assert "daily_stats" in data
        assert "total_inspections" in data
        assert "product_distribution" in data

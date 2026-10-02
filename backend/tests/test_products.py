import pytest
import uuid
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_product_crud():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        unique_code = f"SKU-{uuid.uuid4().hex[:6].upper()}"

        # Create product
        payload = {
            "name": "Precision Bearing Housing",
            "code": unique_code,
            "description": "CNC machined aircraft aluminum bearing casing",
            "threshold": 0.42,
        }
        res = await client.post("/api/v1/products", json=payload)
        assert res.status_code == 201
        product = res.json()
        assert product["name"] == payload["name"]
        assert product["code"] == unique_code
        assert product["threshold"] == 0.42

        product_id = product["id"]

        # Get product by ID
        get_res = await client.get(f"/api/v1/products/{product_id}")
        assert get_res.status_code == 200
        assert get_res.json()["id"] == product_id

        # Update threshold
        patch_res = await client.patch(
            f"/api/v1/products/{product_id}/threshold",
            json={"threshold": 0.38}
        )
        assert patch_res.status_code == 200
        assert patch_res.json()["threshold"] == 0.38

        # List products
        list_res = await client.get("/api/v1/products")
        assert list_res.status_code == 200
        items = list_res.json()
        assert any(p["id"] == product_id for p in items)

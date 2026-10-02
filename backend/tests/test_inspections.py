import pytest
import io
from PIL import Image
from httpx import AsyncClient, ASGITransport
from app.main import app


def _create_sample_image() -> io.BytesIO:
    img = Image.new("RGB", (120, 120), color=(200, 150, 100))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)
    return buf


@pytest.mark.asyncio
async def test_create_and_get_inspection():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create inspection via multipart form upload
        img_file = _create_sample_image()
        files = {"image": ("test_part.jpg", img_file, "image/jpeg")}
        data = {"client_type": "web"}

        response = await client.post("/api/v1/inspections", data=data, files=files)
        assert response.status_code == 201
        res_data = response.json()

        assert "inspection_id" in res_data
        assert res_data["decision"] in ["PASS", "FAIL", "REVIEW"]
        assert 0.0 <= res_data["anomaly_score"] <= 1.0
        assert "confidence" in res_data
        assert "summary" in res_data

        inspection_id = res_data["inspection_id"]

        # Fetch inspection by ID
        get_res = await client.get(f"/api/v1/inspections/{inspection_id}")
        assert get_res.status_code == 200
        get_data = get_res.json()
        assert get_data["inspection_id"] == inspection_id

        # Query inspection history list
        list_res = await client.get("/api/v1/inspections?page=1&page_size=10")
        assert list_res.status_code == 200
        list_data = list_res.json()
        assert list_data["total"] >= 1
        assert len(list_data["items"]) >= 1

        # Delete inspection
        del_res = await client.delete(f"/api/v1/inspections/{inspection_id}")
        assert del_res.status_code in (200, 204)

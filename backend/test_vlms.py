import asyncio
import os
import sys

# Add backend directory to sys.path so we can import app
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.config import settings
from app.services.vlm.base import ProductContext
from app.services.vlm.registry import VLMRegistry

async def test_vlms():
    print(f"GOOGLE_VLM_MODEL: {settings.GOOGLE_VLM_MODEL}")
    print(f"GROQ_VLM_MODEL: {settings.GROQ_VLM_MODEL}")
    print(f"NVIDIA_VLM_MODEL: {settings.NVIDIA_VLM_MODEL}")
    
    # 1. Create a dummy image (a valid small JPEG)
    import io
    from PIL import Image
    img = Image.new("RGB", (100, 100), color="blue")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    image_bytes = buf.getvalue()
    
    product_context = ProductContext(
        product_id="test-product-123",
        product_name="Blue Square",
        product_description="A perfect blue square without any spots or anomalies.",
        threshold=0.55
    )
    
    engines = VLMRegistry.get_ordered_engines()
    print(f"\nFound {len(engines)} configured engines.")
    
    for engine in engines:
        provider = engine.__class__.__name__
        print(f"\n--- Testing {provider} ---")
        try:
            result = await engine.inspect(image_bytes, product_context)
            print(f"Success! Provider: {result.provider}")
            print(f"Latency: {result.latency_ms} ms")
            print(f"Decision: {result.decision}")
            print(f"Anomaly Score: {result.anomaly_score}")
            print(f"Summary: {result.summary}")
            if result.defects:
                print(f"Defects: {len(result.defects)}")
        except Exception as e:
            print(f"FAILED! Error: {type(e).__name__} - {str(e)}")

if __name__ == "__main__":
    asyncio.run(test_vlms())

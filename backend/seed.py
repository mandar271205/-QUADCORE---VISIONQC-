"""
Seed script for VisionQC.
Populates the database with realistic industrial products and past inspection runs.
"""
import asyncio
import uuid
import random
from datetime import datetime, timedelta, timezone

from app.db.session import engine, AsyncSessionLocal
from app.db.base import Base
from app.db.models import (
    Product,
    Inspection,
    Defect,
    InspectionRuntime,
    ModelStatus,
    Decision,
    ClientType,
    Severity,
)

SAMPLE_PRODUCTS = [
    {
        "name": "SMT PCB Controller Board",
        "code": "PCB-SMT-8800",
        "description": "High-density multi-layer surface mount printed circuit board assembly.",
        "threshold": 0.45,
    },
    {
        "name": "CNC Machined Bearing Housing",
        "code": "CNC-BEAR-420",
        "description": "Precision aerospace aluminum alloy 7075 bearing sleeve with tight bore tolerance.",
        "threshold": 0.40,
    },
    {
        "name": "Stamped Sheet Metal Bracket",
        "code": "STMP-AUTO-110",
        "description": "Automotive structural chassis mounting bracket with anti-corrosion galvanized coating.",
        "threshold": 0.55,
    },
    {
        "name": "Injection Molded Enclosure",
        "code": "PLAS-ENC-902",
        "description": "Polycarbonate/ABS optical-grade industrial enclosure with snap-fit hinges.",
        "threshold": 0.48,
    },
]

DEFECT_TYPES = [
    ("Surface Scratch", "Superficial linear abrasion on polished face", Severity.low),
    ("Solder Bridge", "Short circuit bridge between IC leads pin 14 and 15", Severity.high),
    ("Micro-crack", "Sub-millimeter fracture along stress concentration radius", Severity.high),
    ("Burr on Edge", "Excess flashing/burr exceeding 0.15mm chamfer limit", Severity.medium),
    ("Porosity Void", "Gas entrapment micro-void on upper die surface", Severity.medium),
    ("Component Misalignment", "Passive capacitor 0402 rotated 12 degrees out of tolerance", Severity.medium),
    ("Coating Delamination", "Blistering and adhesion loss along peripheral seam", Severity.high),
]


async def seed_database():
    print("[Seed] Initializing database schema...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        # Check if already seeded
        from sqlalchemy import select
        existing = await session.execute(select(Product))
        if existing.scalars().first():
            print("[Seed] Database already contains products. Skipping initial seed.")
            return

        print("[Seed] Creating industrial products...")
        product_objs = []
        for p_data in SAMPLE_PRODUCTS:
            prod = Product(
                id=uuid.uuid4(),
                name=p_data["name"],
                code=p_data["code"],
                description=p_data["description"],
                threshold=p_data["threshold"],
                model_status=ModelStatus.ready,
                reference_image_count=random.randint(5, 12),
            )
            session.add(prod)
            product_objs.append(prod)

        await session.commit()
        for p in product_objs:
            await session.refresh(p)

        print("[Seed] Generating historical inspections...")
        now = datetime.now(timezone.utc)

        # Generate inspections over past 7 days
        for day_offset in range(7, -1, -1):
            day_date = now - timedelta(days=day_offset)
            num_inspections = random.randint(12, 28)

            for _ in range(num_inspections):
                product = random.choice(product_objs)
                hour = random.randint(6, 21)
                minute = random.randint(0, 59)
                inspected_time = day_date.replace(hour=hour, minute=minute)

                # Determine outcome
                r = random.random()
                if r < 0.78:  # 78% Pass
                    decision = Decision.PASS
                    anomaly_score = round(random.uniform(0.04, product.threshold - 0.08), 3)
                    confidence = round(random.uniform(0.88, 0.99), 2)
                    num_defects = 0
                elif r < 0.90:  # 12% Review
                    decision = Decision.REVIEW
                    anomaly_score = round(
                        random.uniform(product.threshold - 0.04, product.threshold + 0.04), 3
                    )
                    confidence = round(random.uniform(0.70, 0.84), 2)
                    num_defects = 1
                else:  # 10% Fail
                    decision = Decision.FAIL
                    anomaly_score = round(random.uniform(product.threshold + 0.06, 0.95), 3)
                    confidence = round(random.uniform(0.85, 0.98), 2)
                    num_defects = random.randint(1, 3)

                client = random.choice([ClientType.web, ClientType.web, ClientType.mobile])
                latency = random.randint(28, 95)

                inspection = Inspection(
                    id=uuid.uuid4(),
                    product_id=product.id,
                    client_type=client,
                    decision=decision,
                    anomaly_score=anomaly_score,
                    confidence=confidence,
                    threshold=product.threshold,
                    original_image_url="https://images.unsplash.com/photo-1581092160607-ee22621dd758?auto=format&fit=crop&w=600&q=80",
                    heatmap_url="https://images.unsplash.com/photo-1581092160607-ee22621dd758?auto=format&fit=crop&w=600&q=80",
                    processing_time_ms=latency,
                    created_at=inspected_time,
                )
                session.add(inspection)

                # Add runtime telemetry
                runtime = InspectionRuntime(
                    id=uuid.uuid4(),
                    inspection_id=inspection.id,
                    engine_type="vlm" if client == ClientType.mobile else "ml",
                    provider="mock_industrial_ensemble",
                    latency_ms=latency,
                    success=True,
                    started_at=inspected_time,
                    completed_at=inspected_time + timedelta(milliseconds=latency),
                )
                session.add(runtime)

                # Add defects if rejected or review
                for _ in range(num_defects):
                    d_type, d_desc, d_sev = random.choice(DEFECT_TYPES)
                    defect = Defect(
                        id=uuid.uuid4(),
                        inspection_id=inspection.id,
                        type=d_type,
                        description=d_desc,
                        severity=d_sev,
                        region_x=random.randint(50, 400),
                        region_y=random.randint(50, 400),
                        region_width=random.randint(20, 80),
                        region_height=random.randint(20, 80),
                        created_at=inspected_time,
                    )
                    session.add(defect)

        await session.commit()
        print("[Seed] Successfully seeded 4 products and 100+ historical quality inspection records.")


if __name__ == "__main__":
    asyncio.run(seed_database())

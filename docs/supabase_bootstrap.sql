-- ============================================================
-- VisionQC Supabase SQL Bootstrap
-- Run this in your Supabase SQL Editor to create all tables.
-- This is equivalent to running: alembic upgrade head
-- ============================================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Enums
DO $$ BEGIN
    CREATE TYPE model_status_enum AS ENUM ('not_available', 'training', 'ready', 'validation_required');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE client_type_enum AS ENUM ('web', 'mobile');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE decision_enum AS ENUM ('PASS', 'FAIL', 'REVIEW');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE severity_enum AS ENUM ('low', 'medium', 'high');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- Products table
CREATE TABLE IF NOT EXISTS products (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    code VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    threshold FLOAT NOT NULL DEFAULT 0.55,
    model_status model_status_enum NOT NULL DEFAULT 'not_available',
    reference_image_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Inspections table
CREATE TABLE IF NOT EXISTS inspections (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    product_id UUID REFERENCES products(id) ON DELETE SET NULL,
    client_type client_type_enum NOT NULL DEFAULT 'web',
    decision decision_enum NOT NULL,
    anomaly_score FLOAT NOT NULL,
    confidence FLOAT NOT NULL,
    threshold FLOAT NOT NULL DEFAULT 0.55,
    original_image_url TEXT,
    heatmap_url TEXT,
    processing_time_ms INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Defects table
CREATE TABLE IF NOT EXISTS defects (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    inspection_id UUID NOT NULL REFERENCES inspections(id) ON DELETE CASCADE,
    type VARCHAR(255) NOT NULL,
    description TEXT,
    severity severity_enum NOT NULL DEFAULT 'medium',
    region_x FLOAT,
    region_y FLOAT,
    region_width FLOAT,
    region_height FLOAT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Inspection runtime (internal debug - never returned to frontend)
CREATE TABLE IF NOT EXISTS inspection_runtime (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    inspection_id UUID NOT NULL REFERENCES inspections(id) ON DELETE CASCADE,
    engine_type VARCHAR(100),
    provider VARCHAR(100),
    engine_name VARCHAR(255),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    latency_ms INTEGER,
    success BOOLEAN NOT NULL DEFAULT TRUE,
    error_code VARCHAR(100),
    error_message TEXT
);

-- Product reference images
CREATE TABLE IF NOT EXISTS product_reference_images (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    storage_url TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Product threshold history
CREATE TABLE IF NOT EXISTS product_threshold_history (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    old_threshold FLOAT NOT NULL,
    new_threshold FLOAT NOT NULL,
    changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS ix_inspections_created_at ON inspections(created_at DESC);
CREATE INDEX IF NOT EXISTS ix_inspections_product_id ON inspections(product_id);
CREATE INDEX IF NOT EXISTS ix_inspections_decision ON inspections(decision);
CREATE INDEX IF NOT EXISTS ix_defects_inspection_id ON defects(inspection_id);
CREATE INDEX IF NOT EXISTS ix_product_ref_images_product_id ON product_reference_images(product_id);

-- Updated_at trigger for products
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

DROP TRIGGER IF EXISTS update_products_updated_at ON products;
CREATE TRIGGER update_products_updated_at
    BEFORE UPDATE ON products
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================================
-- Supabase Storage Buckets
-- ============================================================
-- Create the visionqc storage bucket (run separately if needed):
-- In Supabase Dashboard → Storage → New Bucket → "visionqc" (public)
-- Or via API:

-- INSERT INTO storage.buckets (id, name, public)
-- VALUES ('visionqc', 'visionqc', true)
-- ON CONFLICT DO NOTHING;

COMMIT;

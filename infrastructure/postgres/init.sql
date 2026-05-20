-- Ablage-System PostgreSQL Initialization Script
-- Creates database schema and initial configuration

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- For text search
CREATE EXTENSION IF NOT EXISTS "unaccent";  -- For German text normalization
CREATE EXTENSION IF NOT EXISTS "vector";   -- pgvector for RAG embeddings

-- Create custom types
DO $$ BEGIN
    CREATE TYPE processing_status AS ENUM (
        'pending', 'queued', 'processing', 'completed', 'failed', 'cancelled'
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE ocr_backend AS ENUM (
        'auto', 'deepseek', 'got_ocr', 'surya', 'surya_gpu'
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE document_type AS ENUM (
        'invoice', 'contract', 'receipt', 'form', 'letter', 'report', 'other'
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- Create indexes for better query performance
-- These will be created after tables are created via Alembic

-- Create text search configuration for German
-- Note: CREATE TEXT SEARCH CONFIGURATION doesn't support IF NOT EXISTS
DO $$ BEGIN
    CREATE TEXT SEARCH CONFIGURATION german_text (COPY = german);
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

ALTER TEXT SEARCH CONFIGURATION german_text
    ALTER MAPPING FOR asciiword, word
    WITH unaccent, german_stem;

-- Create function for updating updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create function for German text normalization
CREATE OR REPLACE FUNCTION normalize_german_text(input_text TEXT)
RETURNS TEXT AS $$
BEGIN
    -- Normalize German umlauts and special characters
    RETURN unaccent(lower(trim(input_text)));
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- NOTE: get_processing_stats function moved to Alembic migration
-- because it depends on documents table which doesn't exist yet

-- NOTE: Materialized view for document_stats is created via Alembic migration
-- after the documents table exists. Do not create it here as it would fail.

-- Grant permissions
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO ablage_admin;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO ablage_admin;
GRANT ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public TO ablage_admin;

-- NOTE: Default tags are now seeded via Alembic migration 003_seed_data.py
-- This ensures proper execution order after tables are created.

-- Create initial admin user (password: admin123 - CHANGE IN PRODUCTION!)
-- Note: This should be handled by application initialization instead
-- INSERT INTO users (id, email, username, hashed_password, full_name, is_active, is_superuser, created_at, updated_at)
-- VALUES (
--     gen_random_uuid(),
--     'admin@ablage-system.local',
--     'admin',
--     '$2b$12$...', -- Proper bcrypt hash should be here
--     'System Administrator',
--     true,
--     true,
--     NOW(),
--     NOW()
-- );

-- NOTE: COMMENT ON TABLE statements moved to Alembic migrations
-- because tables don't exist yet in init.sql

-- Notify that initialization is complete
DO $$
BEGIN
    RAISE NOTICE 'Ablage-System database initialization complete!';
    RAISE NOTICE 'Remember to:';
    RAISE NOTICE '1. Run Alembic migrations to create tables';
    RAISE NOTICE '2. Create admin user via API';
    RAISE NOTICE '3. Refresh materialized views periodically';
    RAISE NOTICE '4. Set up regular VACUUM and ANALYZE jobs';
END $$;

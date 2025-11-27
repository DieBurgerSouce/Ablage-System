-- Ablage-System PostgreSQL Initialization Script
-- Creates database schema and initial configuration

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- For text search
CREATE EXTENSION IF NOT EXISTS "unaccent";  -- For German text normalization

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
CREATE TEXT SEARCH CONFIGURATION IF NOT EXISTS german_text (COPY = german);
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

-- Create function to calculate document processing statistics
CREATE OR REPLACE FUNCTION get_processing_stats(
    start_date TIMESTAMP WITH TIME ZONE DEFAULT NOW() - INTERVAL '30 days',
    end_date TIMESTAMP WITH TIME ZONE DEFAULT NOW()
)
RETURNS TABLE (
    total_documents BIGINT,
    completed_documents BIGINT,
    failed_documents BIGINT,
    avg_processing_time_ms NUMERIC,
    success_rate NUMERIC,
    total_pages BIGINT,
    avg_confidence NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        COUNT(*) AS total_documents,
        COUNT(*) FILTER (WHERE status = 'completed') AS completed_documents,
        COUNT(*) FILTER (WHERE status = 'failed') AS failed_documents,
        AVG(processing_duration_ms) FILTER (WHERE status = 'completed')::NUMERIC AS avg_processing_time_ms,
        CASE 
            WHEN COUNT(*) > 0 
            THEN (COUNT(*) FILTER (WHERE status = 'completed')::NUMERIC / COUNT(*)::NUMERIC * 100)
            ELSE 0
        END AS success_rate,
        SUM(page_count) AS total_pages,
        AVG(ocr_confidence) FILTER (WHERE status = 'completed')::NUMERIC AS avg_confidence
    FROM documents
    WHERE created_at BETWEEN start_date AND end_date;
END;
$$ LANGUAGE plpgsql;

-- Create materialized view for quick stats (refresh periodically)
CREATE MATERIALIZED VIEW IF NOT EXISTS document_stats AS
SELECT
    DATE(created_at) as date,
    COUNT(*) as documents_processed,
    AVG(processing_duration_ms) as avg_processing_time,
    COUNT(*) FILTER (WHERE status = 'completed') as successful,
    COUNT(*) FILTER (WHERE status = 'failed') as failed,
    COUNT(DISTINCT owner_id) as unique_users,
    COUNT(*) FILTER (WHERE has_umlauts = true) as german_documents,
    AVG(german_validation_score) as avg_german_score
FROM documents
GROUP BY DATE(created_at)
WITH NO DATA;

-- Create index on materialized view
CREATE UNIQUE INDEX IF NOT EXISTS idx_document_stats_date ON document_stats(date);

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

-- Performance tuning comments
COMMENT ON TABLE documents IS 'Main document storage table - partitioning by created_at recommended for large datasets';
COMMENT ON TABLE processing_jobs IS 'Async job tracking - consider archiving old completed jobs';
COMMENT ON TABLE system_metrics IS 'Time-series metrics - consider using TimescaleDB for better performance';

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

-- Ablage-System PostgreSQL Initialization
-- Database initialization script for docker-compose PostgreSQL service
-- Created: 2024-11-25

-- Enable required extensions
-- Note: Extensions must be enabled by superuser (postgres)

-- Enable UUID generation (for document IDs)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Enable pgcrypto for encryption functions
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Enable pg_trgm for fuzzy text search (German text)
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Enable unaccent for accent-insensitive search
CREATE EXTENSION IF NOT EXISTS "unaccent";

-- Optional: Enable pgvector for embeddings (if used later)
-- CREATE EXTENSION IF NOT EXISTS "vector";

-- Set timezone to Berlin (German locale)
SET timezone = 'Europe/Berlin';

-- Create application-specific configuration
ALTER DATABASE ablage_ocr SET timezone TO 'Europe/Berlin';
ALTER DATABASE ablage_ocr SET lc_collate TO 'de_DE.UTF-8';
ALTER DATABASE ablage_ocr SET lc_ctype TO 'de_DE.UTF-8';

-- Log completion
DO $$
BEGIN
    RAISE NOTICE 'Ablage-System database initialized successfully';
    RAISE NOTICE 'Extensions enabled: uuid-ossp, pgcrypto, pg_trgm, unaccent';
    RAISE NOTICE 'Locale: de_DE.UTF-8, Timezone: Europe/Berlin';
END $$;

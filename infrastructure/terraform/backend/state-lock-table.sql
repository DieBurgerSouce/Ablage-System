-- =============================================================================
-- Terraform State Locking Table for PostgreSQL
-- Ablage-System OCR Infrastructure
-- =============================================================================
--
-- This table provides state locking for Terraform when using MinIO (S3-compatible)
-- as the backend storage. Since MinIO doesn't support DynamoDB-style locking,
-- we use PostgreSQL for distributed lock management.
--
-- Usage:
--   psql -h localhost -U ablage_admin -d ablage_system -f state-lock-table.sql
--
-- =============================================================================

-- Create the locks table
CREATE TABLE IF NOT EXISTS terraform_locks (
    id VARCHAR(255) PRIMARY KEY,
    info JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP + INTERVAL '1 hour')
);

-- Index for faster lookups and cleanup
CREATE INDEX IF NOT EXISTS idx_terraform_locks_created
ON terraform_locks(created_at);

CREATE INDEX IF NOT EXISTS idx_terraform_locks_expires
ON terraform_locks(expires_at);

-- Function to update timestamp on modification
CREATE OR REPLACE FUNCTION update_terraform_lock_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to auto-update timestamp
DROP TRIGGER IF EXISTS trigger_terraform_lock_timestamp ON terraform_locks;
CREATE TRIGGER trigger_terraform_lock_timestamp
    BEFORE UPDATE ON terraform_locks
    FOR EACH ROW
    EXECUTE FUNCTION update_terraform_lock_timestamp();

-- Function to acquire a lock (returns true if acquired, false if already locked)
CREATE OR REPLACE FUNCTION terraform_acquire_lock(
    p_lock_id VARCHAR(255),
    p_info JSONB,
    p_timeout_seconds INTEGER DEFAULT 300
) RETURNS BOOLEAN AS $$
DECLARE
    v_acquired BOOLEAN := FALSE;
BEGIN
    -- First, clean up expired locks
    DELETE FROM terraform_locks
    WHERE expires_at < CURRENT_TIMESTAMP;

    -- Try to insert a new lock
    BEGIN
        INSERT INTO terraform_locks (id, info, expires_at)
        VALUES (
            p_lock_id,
            p_info,
            CURRENT_TIMESTAMP + (p_timeout_seconds || ' seconds')::INTERVAL
        );
        v_acquired := TRUE;
    EXCEPTION WHEN unique_violation THEN
        -- Lock already exists, check if it's expired
        UPDATE terraform_locks
        SET info = p_info,
            expires_at = CURRENT_TIMESTAMP + (p_timeout_seconds || ' seconds')::INTERVAL
        WHERE id = p_lock_id
        AND expires_at < CURRENT_TIMESTAMP;

        IF FOUND THEN
            v_acquired := TRUE;
        END IF;
    END;

    RETURN v_acquired;
END;
$$ LANGUAGE plpgsql;

-- Function to release a lock
CREATE OR REPLACE FUNCTION terraform_release_lock(
    p_lock_id VARCHAR(255)
) RETURNS BOOLEAN AS $$
BEGIN
    DELETE FROM terraform_locks WHERE id = p_lock_id;
    RETURN FOUND;
END;
$$ LANGUAGE plpgsql;

-- Function to check if locked
CREATE OR REPLACE FUNCTION terraform_is_locked(
    p_lock_id VARCHAR(255)
) RETURNS TABLE (
    is_locked BOOLEAN,
    lock_info JSONB,
    locked_at TIMESTAMP WITH TIME ZONE,
    expires_at TIMESTAMP WITH TIME ZONE
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        TRUE as is_locked,
        tl.info as lock_info,
        tl.created_at as locked_at,
        tl.expires_at
    FROM terraform_locks tl
    WHERE tl.id = p_lock_id
    AND tl.expires_at > CURRENT_TIMESTAMP;

    IF NOT FOUND THEN
        RETURN QUERY SELECT FALSE, NULL::JSONB, NULL::TIMESTAMP WITH TIME ZONE, NULL::TIMESTAMP WITH TIME ZONE;
    END IF;
END;
$$ LANGUAGE plpgsql;

-- Grant permissions to ablage_admin user
GRANT ALL PRIVILEGES ON TABLE terraform_locks TO ablage_admin;
GRANT EXECUTE ON FUNCTION terraform_acquire_lock TO ablage_admin;
GRANT EXECUTE ON FUNCTION terraform_release_lock TO ablage_admin;
GRANT EXECUTE ON FUNCTION terraform_is_locked TO ablage_admin;

-- Create a scheduled job to clean up expired locks (requires pg_cron extension)
-- If pg_cron is not available, use external cron or Ansible task
-- SELECT cron.schedule('cleanup-terraform-locks', '*/5 * * * *',
--     $$DELETE FROM terraform_locks WHERE expires_at < CURRENT_TIMESTAMP$$);

COMMENT ON TABLE terraform_locks IS 'Distributed locking table for Terraform state management with MinIO backend';
COMMENT ON FUNCTION terraform_acquire_lock IS 'Attempts to acquire a lock, returns TRUE if successful';
COMMENT ON FUNCTION terraform_release_lock IS 'Releases a lock, returns TRUE if lock existed';
COMMENT ON FUNCTION terraform_is_locked IS 'Checks if a lock exists and returns lock details';

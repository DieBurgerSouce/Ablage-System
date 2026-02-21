"""Tabellen-Partitionierung Infrastruktur (Phase 1.2).

Revision ID: 239
Revises: 238
Create Date: 2026-02-20

Erstellt die Partitionierungs-Infrastruktur fuer hochvolumige Tabellen:
- partition_management: Tracking-Tabelle fuer alle Partitionen
- create_time_partition(): Funktion zum Erstellen neuer Partitionen
- archive_old_partitions(): Funktion zum Archivieren alter Partitionen
- update_partition_row_counts(): Funktion zum Aktualisieren der Zeilenanzahl
- Schatten-Tabellen mit RANGE-Partitionierung auf created_at
- Dual-Write-Trigger fuer nahtlose Migration

Partitionierte Tabellen:
- audit_logs_partitioned (quartalsweise)
- document_access_logs_partitioned (monatlich)
- document_lineage_events_partitioned (quartalsweise)
- event_log_partitioned (monatlich)

STRATEGIE: Nicht-destruktiv (Shadow-Table-Pattern)
- Originaltabellen bleiben unangetastet
- Neue partitionierte Schatten-Tabellen werden parallel erstellt
- Dual-Write-Trigger schreiben in beide Tabellen
- Hintergrund-Migration verschiebt Altdaten via Celery
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "239"
down_revision = "238"
branch_labels = None
depends_on = None


# ============================================================
# Tabellen-Konfiguration fuer Partitionierung
# ============================================================
PARTITIONED_TABLES = [
    {
        "table": "audit_logs",
        "partition_column": "created_at",
        "interval": "quarterly",
    },
    {
        "table": "document_access_logs",
        "partition_column": "accessed_at",
        "interval": "monthly",
    },
    {
        "table": "document_lineage_events",
        "partition_column": "created_at",
        "interval": "quarterly",
    },
    {
        "table": "event_log",
        "partition_column": "created_at",
        "interval": "monthly",
    },
]


def upgrade() -> None:
    # ==================================================================
    # 1. Partition Management Tracking-Tabelle
    # ==================================================================
    op.execute("""
        CREATE TABLE IF NOT EXISTS partition_management (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            table_name VARCHAR(100) NOT NULL,
            partition_name VARCHAR(150) NOT NULL,
            range_start TIMESTAMP WITH TIME ZONE NOT NULL,
            range_end TIMESTAMP WITH TIME ZONE NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
            row_count BIGINT DEFAULT 0,
            size_bytes BIGINT DEFAULT 0,
            is_archived BOOLEAN DEFAULT FALSE,
            archived_at TIMESTAMP WITH TIME ZONE,
            CONSTRAINT uq_partition_management_name UNIQUE (partition_name)
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_partition_mgmt_table
            ON partition_management (table_name)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_partition_mgmt_archived
            ON partition_management (table_name, is_archived)
    """)

    op.execute("""
        COMMENT ON TABLE partition_management IS
            'Verwaltung und Tracking aller Tabellen-Partitionen (Phase 1.2)'
    """)

    # ==================================================================
    # 2. Hilfsfunktion: Partition erstellen
    # ==================================================================
    op.execute("""
        CREATE OR REPLACE FUNCTION create_time_partition(
            p_table_name TEXT,
            p_start DATE,
            p_end DATE
        ) RETURNS TEXT AS $$
        DECLARE
            v_partition_name TEXT;
        BEGIN
            v_partition_name := p_table_name || '_p' || to_char(p_start, 'YYYY_MM');

            EXECUTE format(
                'CREATE TABLE IF NOT EXISTS %I PARTITION OF %I
                 FOR VALUES FROM (%L) TO (%L)',
                v_partition_name,
                p_table_name,
                p_start::timestamp with time zone,
                p_end::timestamp with time zone
            );

            INSERT INTO partition_management (
                table_name, partition_name, range_start, range_end
            )
            VALUES (
                p_table_name, v_partition_name,
                p_start::timestamp with time zone,
                p_end::timestamp with time zone
            )
            ON CONFLICT (partition_name) DO NOTHING;

            RETURN v_partition_name;
        END;
        $$ LANGUAGE plpgsql
    """)

    op.execute("""
        COMMENT ON FUNCTION create_time_partition(TEXT, DATE, DATE) IS
            'Erstellt eine neue Zeitbereichs-Partition und registriert sie in partition_management'
    """)

    # ==================================================================
    # 3. Hilfsfunktion: Alte Partitionen archivieren (detach)
    # ==================================================================
    op.execute("""
        CREATE OR REPLACE FUNCTION archive_old_partitions(
            p_table_name TEXT,
            p_older_than INTERVAL DEFAULT '2 years'
        ) RETURNS INTEGER AS $$
        DECLARE
            v_part RECORD;
            v_archived_count INTEGER := 0;
        BEGIN
            FOR v_part IN
                SELECT partition_name, range_end
                FROM partition_management
                WHERE table_name = p_table_name
                  AND is_archived = FALSE
                  AND range_end < (NOW() - p_older_than)
                ORDER BY range_end ASC
            LOOP
                -- Partition abtrennen (Daten bleiben erhalten, aber
                -- werden nicht mehr in Abfragen beruecksichtigt)
                BEGIN
                    EXECUTE format(
                        'ALTER TABLE %I DETACH PARTITION %I CONCURRENTLY',
                        p_table_name,
                        v_part.partition_name
                    );
                EXCEPTION WHEN OTHERS THEN
                    -- Fallback ohne CONCURRENTLY fuer aeltere PG-Versionen
                    EXECUTE format(
                        'ALTER TABLE %I DETACH PARTITION %I',
                        p_table_name,
                        v_part.partition_name
                    );
                END;

                UPDATE partition_management
                SET is_archived = TRUE,
                    archived_at = NOW()
                WHERE partition_name = v_part.partition_name;

                v_archived_count := v_archived_count + 1;
            END LOOP;

            RETURN v_archived_count;
        END;
        $$ LANGUAGE plpgsql
    """)

    op.execute("""
        COMMENT ON FUNCTION archive_old_partitions(TEXT, INTERVAL) IS
            'Archiviert (detached) Partitionen aelter als das angegebene Intervall'
    """)

    # ==================================================================
    # 4. Hilfsfunktion: Partition-Statistiken aktualisieren
    # ==================================================================
    op.execute("""
        CREATE OR REPLACE FUNCTION update_partition_row_counts(
            p_table_name TEXT DEFAULT NULL
        ) RETURNS INTEGER AS $$
        DECLARE
            v_part RECORD;
            v_count BIGINT;
            v_size BIGINT;
            v_updated INTEGER := 0;
        BEGIN
            FOR v_part IN
                SELECT partition_name
                FROM partition_management
                WHERE is_archived = FALSE
                  AND (p_table_name IS NULL OR table_name = p_table_name)
            LOOP
                BEGIN
                    EXECUTE format(
                        'SELECT count(*) FROM %I',
                        v_part.partition_name
                    ) INTO v_count;

                    EXECUTE format(
                        'SELECT pg_total_relation_size(%L)',
                        v_part.partition_name
                    ) INTO v_size;

                    UPDATE partition_management
                    SET row_count = v_count,
                        size_bytes = COALESCE(v_size, 0)
                    WHERE partition_name = v_part.partition_name;

                    v_updated := v_updated + 1;
                EXCEPTION WHEN undefined_table THEN
                    -- Partition existiert nicht mehr, als archiviert markieren
                    UPDATE partition_management
                    SET is_archived = TRUE,
                        archived_at = NOW()
                    WHERE partition_name = v_part.partition_name;
                END;
            END LOOP;

            RETURN v_updated;
        END;
        $$ LANGUAGE plpgsql
    """)

    op.execute("""
        COMMENT ON FUNCTION update_partition_row_counts(TEXT) IS
            'Aktualisiert row_count und size_bytes fuer alle aktiven Partitionen'
    """)

    # ==================================================================
    # 5. Partitionierte Schatten-Tabellen erstellen
    # ==================================================================

    # --- 5a. audit_logs_partitioned ---
    op.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs_partitioned (
            id UUID NOT NULL DEFAULT gen_random_uuid(),
            user_id UUID,
            company_id UUID,
            action VARCHAR(100) NOT NULL,
            resource_type VARCHAR(50),
            resource_id UUID,
            ip_address VARCHAR(45),
            user_agent VARCHAR(255),
            request_method VARCHAR(10),
            request_path VARCHAR(255),
            success BOOLEAN NOT NULL DEFAULT TRUE,
            error_message VARCHAR(2000),
            audit_metadata JSONB DEFAULT '{}'::jsonb,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            sequence_number BIGINT,
            integrity_hash VARCHAR(64),
            previous_hash VARCHAR(64),
            PRIMARY KEY (id, created_at)
        ) PARTITION BY RANGE (created_at)
    """)

    op.execute("""
        COMMENT ON TABLE audit_logs_partitioned IS
            'Partitionierte Version von audit_logs (quartalsweise, Phase 1.2)'
    """)

    # Indexes fuer audit_logs_partitioned
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_audit_logs_part_user_id
            ON audit_logs_partitioned (user_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_audit_logs_part_created_at
            ON audit_logs_partitioned (created_at)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_audit_logs_part_action
            ON audit_logs_partitioned (action)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_audit_logs_part_company_created
            ON audit_logs_partitioned (company_id, created_at)
    """)

    # --- 5b. document_access_logs_partitioned ---
    op.execute("""
        CREATE TABLE IF NOT EXISTS document_access_logs_partitioned (
            id UUID NOT NULL DEFAULT gen_random_uuid(),
            document_id UUID NOT NULL,
            user_id UUID,
            company_id UUID NOT NULL,
            access_type VARCHAR(30) NOT NULL,
            access_reason VARCHAR(255),
            ip_address VARCHAR(45),
            user_agent VARCHAR(500),
            request_id VARCHAR(36),
            success BOOLEAN NOT NULL DEFAULT TRUE,
            error_message VARCHAR(500),
            bytes_transferred BIGINT,
            accessed_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            access_metadata JSONB DEFAULT '{}'::jsonb,
            sequence_number BIGINT,
            PRIMARY KEY (id, accessed_at)
        ) PARTITION BY RANGE (accessed_at)
    """)

    op.execute("""
        COMMENT ON TABLE document_access_logs_partitioned IS
            'Partitionierte Version von document_access_logs (monatlich, Phase 1.2)'
    """)

    # Indexes fuer document_access_logs_partitioned
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_doc_access_part_document_id
            ON document_access_logs_partitioned (document_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_doc_access_part_user_id
            ON document_access_logs_partitioned (user_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_doc_access_part_company_id
            ON document_access_logs_partitioned (company_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_doc_access_part_accessed_at
            ON document_access_logs_partitioned (accessed_at)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_doc_access_part_access_type
            ON document_access_logs_partitioned (access_type)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_doc_access_part_doc_time
            ON document_access_logs_partitioned (document_id, accessed_at)
    """)

    # --- 5c. document_lineage_events_partitioned ---
    op.execute("""
        CREATE TABLE IF NOT EXISTS document_lineage_events_partitioned (
            id UUID NOT NULL DEFAULT gen_random_uuid(),
            document_id UUID NOT NULL,
            event_type VARCHAR(50) NOT NULL,
            event_data JSONB DEFAULT '{}'::jsonb,
            duration_ms INTEGER,
            confidence FLOAT,
            user_id UUID,
            company_id UUID NOT NULL,
            source_service VARCHAR(100),
            correlation_id UUID,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            PRIMARY KEY (id, created_at)
        ) PARTITION BY RANGE (created_at)
    """)

    op.execute("""
        COMMENT ON TABLE document_lineage_events_partitioned IS
            'Partitionierte Version von document_lineage_events (quartalsweise, Phase 1.2)'
    """)

    # Indexes fuer document_lineage_events_partitioned
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_lineage_part_document_id
            ON document_lineage_events_partitioned (document_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_lineage_part_event_type
            ON document_lineage_events_partitioned (event_type)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_lineage_part_created_at
            ON document_lineage_events_partitioned (created_at)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_lineage_part_company_created
            ON document_lineage_events_partitioned (company_id, created_at)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_lineage_part_doc_created
            ON document_lineage_events_partitioned (document_id, created_at)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_lineage_part_correlation
            ON document_lineage_events_partitioned (correlation_id)
    """)

    # --- 5d. event_log_partitioned ---
    op.execute("""
        CREATE TABLE IF NOT EXISTS event_log_partitioned (
            id UUID NOT NULL DEFAULT gen_random_uuid(),
            event_id UUID NOT NULL,
            event_type VARCHAR(100) NOT NULL,
            source VARCHAR(100) NOT NULL,
            correlation_id UUID,
            user_id UUID,
            space_id UUID,
            payload JSONB NOT NULL,
            processed BOOLEAN NOT NULL DEFAULT FALSE,
            processed_at TIMESTAMP WITH TIME ZONE,
            handler_count INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            PRIMARY KEY (id, created_at)
        ) PARTITION BY RANGE (created_at)
    """)

    op.execute("""
        COMMENT ON TABLE event_log_partitioned IS
            'Partitionierte Version von event_log (monatlich, Phase 1.2)'
    """)

    # Indexes fuer event_log_partitioned
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_event_log_part_event_id
            ON event_log_partitioned (event_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_event_log_part_event_type
            ON event_log_partitioned (event_type)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_event_log_part_source
            ON event_log_partitioned (source)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_event_log_part_created_at
            ON event_log_partitioned (created_at)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_event_log_part_correlation
            ON event_log_partitioned (correlation_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_event_log_part_unprocessed
            ON event_log_partitioned (event_type, created_at)
            WHERE processed = false
    """)

    # ==================================================================
    # 6. Initiale Partitionen erstellen (12 Monate zurueck + 3 voraus)
    # ==================================================================
    # Quartalsweise Tabellen: audit_logs, document_lineage_events
    op.execute("""
        DO $$
        DECLARE
            v_start DATE;
            v_end DATE;
            v_quarter_start DATE;
            v_tbl TEXT;
            v_tables TEXT[] := ARRAY[
                'audit_logs_partitioned',
                'document_lineage_events_partitioned'
            ];
        BEGIN
            FOREACH v_tbl IN ARRAY v_tables LOOP
                -- 12 Monate zurueck = 4 Quartale + aktuelles + 1 voraus
                v_quarter_start := date_trunc('quarter', NOW() - INTERVAL '12 months');

                WHILE v_quarter_start <= date_trunc('quarter', NOW() + INTERVAL '3 months') LOOP
                    v_start := v_quarter_start;
                    v_end := v_quarter_start + INTERVAL '3 months';

                    PERFORM create_time_partition(v_tbl, v_start, v_end);

                    v_quarter_start := v_quarter_start + INTERVAL '3 months';
                END LOOP;
            END LOOP;
        END $$
    """)

    # Monatliche Tabellen: document_access_logs, event_log
    op.execute("""
        DO $$
        DECLARE
            v_start DATE;
            v_end DATE;
            v_month_start DATE;
            v_tbl TEXT;
            v_tables TEXT[] := ARRAY[
                'document_access_logs_partitioned',
                'event_log_partitioned'
            ];
        BEGIN
            FOREACH v_tbl IN ARRAY v_tables LOOP
                -- 12 Monate zurueck + 3 voraus
                v_month_start := date_trunc('month', NOW() - INTERVAL '12 months');

                WHILE v_month_start <= date_trunc('month', NOW() + INTERVAL '3 months') LOOP
                    v_start := v_month_start;
                    v_end := v_month_start + INTERVAL '1 month';

                    PERFORM create_time_partition(v_tbl, v_start, v_end);

                    v_month_start := v_month_start + INTERVAL '1 month';
                END LOOP;
            END LOOP;
        END $$
    """)

    # ==================================================================
    # 7. Dual-Write-Trigger: Neue Zeilen in beide Tabellen schreiben
    # ==================================================================

    # --- 7a. audit_logs Dual-Write ---
    op.execute("""
        CREATE OR REPLACE FUNCTION trg_audit_logs_dual_write()
        RETURNS TRIGGER AS $$
        BEGIN
            INSERT INTO audit_logs_partitioned (
                id, user_id, company_id, action, resource_type, resource_id,
                ip_address, user_agent, request_method, request_path,
                success, error_message, audit_metadata, created_at,
                sequence_number, integrity_hash, previous_hash
            ) VALUES (
                NEW.id, NEW.user_id, NEW.company_id, NEW.action,
                NEW.resource_type, NEW.resource_id,
                NEW.ip_address, NEW.user_agent, NEW.request_method,
                NEW.request_path, NEW.success, NEW.error_message,
                NEW.audit_metadata, NEW.created_at,
                NEW.sequence_number, NEW.integrity_hash, NEW.previous_hash
            )
            ON CONFLICT (id, created_at) DO NOTHING;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)

    op.execute("""
        CREATE TRIGGER trg_audit_logs_to_partitioned
        AFTER INSERT ON audit_logs
        FOR EACH ROW
        EXECUTE FUNCTION trg_audit_logs_dual_write()
    """)

    # --- 7b. document_access_logs Dual-Write ---
    op.execute("""
        CREATE OR REPLACE FUNCTION trg_document_access_logs_dual_write()
        RETURNS TRIGGER AS $$
        BEGIN
            INSERT INTO document_access_logs_partitioned (
                id, document_id, user_id, company_id, access_type,
                access_reason, ip_address, user_agent, request_id,
                success, error_message, bytes_transferred, accessed_at,
                access_metadata, sequence_number
            ) VALUES (
                NEW.id, NEW.document_id, NEW.user_id, NEW.company_id,
                NEW.access_type, NEW.access_reason,
                NEW.ip_address, NEW.user_agent, NEW.request_id,
                NEW.success, NEW.error_message, NEW.bytes_transferred,
                NEW.accessed_at, NEW.access_metadata, NEW.sequence_number
            )
            ON CONFLICT (id, accessed_at) DO NOTHING;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)

    op.execute("""
        CREATE TRIGGER trg_document_access_logs_to_partitioned
        AFTER INSERT ON document_access_logs
        FOR EACH ROW
        EXECUTE FUNCTION trg_document_access_logs_dual_write()
    """)

    # --- 7c. document_lineage_events Dual-Write ---
    op.execute("""
        CREATE OR REPLACE FUNCTION trg_document_lineage_events_dual_write()
        RETURNS TRIGGER AS $$
        BEGIN
            INSERT INTO document_lineage_events_partitioned (
                id, document_id, event_type, event_data, duration_ms,
                confidence, user_id, company_id, source_service,
                correlation_id, created_at
            ) VALUES (
                NEW.id, NEW.document_id, NEW.event_type, NEW.event_data,
                NEW.duration_ms, NEW.confidence,
                NEW.user_id, NEW.company_id, NEW.source_service,
                NEW.correlation_id, NEW.created_at
            )
            ON CONFLICT (id, created_at) DO NOTHING;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)

    op.execute("""
        CREATE TRIGGER trg_document_lineage_events_to_partitioned
        AFTER INSERT ON document_lineage_events
        FOR EACH ROW
        EXECUTE FUNCTION trg_document_lineage_events_dual_write()
    """)

    # --- 7d. event_log Dual-Write ---
    op.execute("""
        CREATE OR REPLACE FUNCTION trg_event_log_dual_write()
        RETURNS TRIGGER AS $$
        BEGIN
            INSERT INTO event_log_partitioned (
                id, event_id, event_type, source, correlation_id,
                user_id, space_id, payload, processed, processed_at,
                handler_count, created_at
            ) VALUES (
                NEW.id, NEW.event_id, NEW.event_type, NEW.source,
                NEW.correlation_id, NEW.user_id, NEW.space_id,
                NEW.payload, NEW.processed, NEW.processed_at,
                NEW.handler_count, NEW.created_at
            )
            ON CONFLICT (id, created_at) DO NOTHING;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)

    op.execute("""
        CREATE TRIGGER trg_event_log_to_partitioned
        AFTER INSERT ON event_log
        FOR EACH ROW
        EXECUTE FUNCTION trg_event_log_dual_write()
    """)


def downgrade() -> None:
    # ==================================================================
    # Trigger und Trigger-Funktionen entfernen
    # ==================================================================
    op.execute("DROP TRIGGER IF EXISTS trg_event_log_to_partitioned ON event_log")
    op.execute("DROP FUNCTION IF EXISTS trg_event_log_dual_write()")

    op.execute(
        "DROP TRIGGER IF EXISTS trg_document_lineage_events_to_partitioned "
        "ON document_lineage_events"
    )
    op.execute("DROP FUNCTION IF EXISTS trg_document_lineage_events_dual_write()")

    op.execute(
        "DROP TRIGGER IF EXISTS trg_document_access_logs_to_partitioned "
        "ON document_access_logs"
    )
    op.execute("DROP FUNCTION IF EXISTS trg_document_access_logs_dual_write()")

    op.execute("DROP TRIGGER IF EXISTS trg_audit_logs_to_partitioned ON audit_logs")
    op.execute("DROP FUNCTION IF EXISTS trg_audit_logs_dual_write()")

    # ==================================================================
    # Partitionierte Tabellen entfernen (CASCADE entfernt auch Partitionen)
    # ==================================================================
    op.execute("DROP TABLE IF EXISTS event_log_partitioned CASCADE")
    op.execute("DROP TABLE IF EXISTS document_lineage_events_partitioned CASCADE")
    op.execute("DROP TABLE IF EXISTS document_access_logs_partitioned CASCADE")
    op.execute("DROP TABLE IF EXISTS audit_logs_partitioned CASCADE")

    # ==================================================================
    # Hilfsfunktionen entfernen
    # ==================================================================
    op.execute("DROP FUNCTION IF EXISTS update_partition_row_counts(TEXT)")
    op.execute("DROP FUNCTION IF EXISTS archive_old_partitions(TEXT, INTERVAL)")
    op.execute("DROP FUNCTION IF EXISTS create_time_partition(TEXT, DATE, DATE)")

    # ==================================================================
    # Management-Tabelle entfernen
    # ==================================================================
    op.execute("DROP TABLE IF EXISTS partition_management CASCADE")

"""Add ERP connections tables.

Revision ID: 074_add_erp_connections
Revises: 073_add_tax_advisor_access
Create Date: 2026-01-02

ERP-Integrations-Infrastruktur:
- erp_connections: ERP-Verbindungskonfiguration pro Firma
- erp_sync_history: Sync-Historie und Logs
- erp_field_mappings: Feld-Mapping-Konfiguration
- erp_conflicts: Konflikt-Queue fuer manuelle Aufloesung
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "074"
down_revision = "073"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ==========================================================================
    # ERP Connections - Haupttabelle fuer Verbindungskonfiguration
    # ==========================================================================
    op.create_table(
        "erp_connections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),

        # Verbindungsdetails
        sa.Column("erp_type", sa.String(50), nullable=False),  # odoo, lexware, sap
        sa.Column("name", sa.String(255), nullable=False),  # Anzeigename
        sa.Column("url", sa.String(500), nullable=False),  # API-URL
        sa.Column("database_name", sa.String(255), nullable=True),  # DB-Name (Odoo)

        # Credentials (verschluesselt gespeichert)
        sa.Column("username", sa.String(255), nullable=False),
        sa.Column("encrypted_api_key", sa.Text(), nullable=False),  # Fernet-verschluesselt
        sa.Column("encryption_key_id", sa.String(100), nullable=True),  # Key-Referenz

        # Sync-Einstellungen
        sa.Column("sync_direction", sa.String(20), nullable=False, server_default="bidirectional"),
        sa.Column("sync_interval_minutes", sa.Integer(), nullable=False, server_default="15"),
        sa.Column("enabled_entities", postgresql.JSONB(), nullable=False, server_default="[]"),

        # Rate Limiting
        sa.Column("max_requests_per_minute", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("batch_size", sa.Integer(), nullable=False, server_default="100"),

        # Retry-Einstellungen
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("retry_delay_seconds", sa.Integer(), nullable=False, server_default="5"),

        # Timeouts
        sa.Column("connect_timeout_seconds", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("read_timeout_seconds", sa.Integer(), nullable=False, server_default="60"),

        # Status
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("connection_status", sa.String(30), nullable=False, server_default="disconnected"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_successful_connection", sa.DateTime(timezone=True), nullable=True),

        # Sync-Status
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_full_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_scheduled_sync", sa.DateTime(timezone=True), nullable=True),

        # Metadaten
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
    )

    # Indizes fuer erp_connections
    op.create_index("ix_erp_connections_company_id", "erp_connections", ["company_id"])
    op.create_index("ix_erp_connections_erp_type", "erp_connections", ["erp_type"])
    op.create_index("ix_erp_connections_is_active", "erp_connections", ["is_active"])
    op.create_index("ix_erp_connections_next_sync", "erp_connections", ["next_scheduled_sync"])

    # ==========================================================================
    # ERP Sync History - Protokoll aller Sync-Vorgaenge
    # ==========================================================================
    op.create_table(
        "erp_sync_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("connection_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("erp_connections.id", ondelete="CASCADE"), nullable=False),

        # Sync-Details
        sa.Column("sync_type", sa.String(20), nullable=False),  # full, delta, manual
        sa.Column("entity", sa.String(50), nullable=False),  # customer, supplier, invoice
        sa.Column("direction", sa.String(20), nullable=False),  # push, pull, bidirectional

        # Ergebnis
        sa.Column("status", sa.String(20), nullable=False),  # running, success, failed, partial
        sa.Column("records_synced", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_created", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_updated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_deleted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_failed", sa.Integer(), nullable=False, server_default="0"),

        # Konflikte
        sa.Column("conflicts_detected", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("conflicts_resolved", sa.Integer(), nullable=False, server_default="0"),

        # Timing
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),

        # Fehlerdetails
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("error_details", postgresql.JSONB(), nullable=True),
        sa.Column("failed_records", postgresql.JSONB(), nullable=True),  # IDs der fehlgeschlagenen Records

        # Metadaten
        sa.Column("triggered_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("task_id", sa.String(100), nullable=True),  # Celery Task ID
    )

    # Indizes fuer erp_sync_history
    op.create_index("ix_erp_sync_history_connection_id", "erp_sync_history", ["connection_id"])
    op.create_index("ix_erp_sync_history_entity", "erp_sync_history", ["entity"])
    op.create_index("ix_erp_sync_history_status", "erp_sync_history", ["status"])
    op.create_index("ix_erp_sync_history_started_at", "erp_sync_history", ["started_at"])
    op.create_index("ix_erp_sync_history_connection_entity", "erp_sync_history", ["connection_id", "entity"])

    # ==========================================================================
    # ERP Field Mappings - Feld-Mapping pro Verbindung/Entitaet
    # ==========================================================================
    op.create_table(
        "erp_field_mappings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("connection_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("erp_connections.id", ondelete="CASCADE"), nullable=False),

        # Mapping-Definition
        sa.Column("entity", sa.String(50), nullable=False),  # customer, invoice, etc.
        sa.Column("local_field", sa.String(100), nullable=False),  # Feld im Ablage-System
        sa.Column("remote_field", sa.String(100), nullable=False),  # Feld im ERP
        sa.Column("direction", sa.String(20), nullable=False, server_default="bidirectional"),

        # Transformation
        sa.Column("transformer", sa.String(50), nullable=True),  # date, currency, lookup, custom
        sa.Column("transformer_config", postgresql.JSONB(), nullable=True),  # Transformer-Optionen

        # Validierung
        sa.Column("required", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("default_value", sa.Text(), nullable=True),

        # Metadaten
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # Indizes fuer erp_field_mappings
    op.create_index("ix_erp_field_mappings_connection_entity", "erp_field_mappings", ["connection_id", "entity"])
    op.create_index("ix_erp_field_mappings_is_active", "erp_field_mappings", ["is_active"])

    # Unique constraint: Ein Mapping pro local_field/entity/connection
    op.create_unique_constraint(
        "uq_erp_field_mappings_unique",
        "erp_field_mappings",
        ["connection_id", "entity", "local_field"]
    )

    # ==========================================================================
    # ERP Conflicts - Queue fuer Sync-Konflikte
    # ==========================================================================
    op.create_table(
        "erp_conflicts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("connection_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("erp_connections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sync_history_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("erp_sync_history.id", ondelete="SET NULL"), nullable=True),

        # Konflikt-Details
        sa.Column("entity", sa.String(50), nullable=False),
        sa.Column("local_id", sa.String(100), nullable=False),  # ID im Ablage-System
        sa.Column("remote_id", sa.String(100), nullable=False),  # ID im ERP

        # Daten
        sa.Column("local_data", postgresql.JSONB(), nullable=False),
        sa.Column("remote_data", postgresql.JSONB(), nullable=False),
        sa.Column("diff", postgresql.JSONB(), nullable=True),  # Berechnete Differenzen

        # Zeitstempel
        sa.Column("local_modified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("remote_modified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),

        # Aufloesung
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),  # pending, resolved, ignored
        sa.Column("resolution", sa.String(30), nullable=True),  # local_wins, remote_wins, merged, manual
        sa.Column("resolved_data", postgresql.JSONB(), nullable=True),  # Finales Resultat
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("resolution_notes", sa.Text(), nullable=True),

        # Prioritaet
        sa.Column("priority", sa.String(20), nullable=False, server_default="normal"),  # low, normal, high, critical
    )

    # Indizes fuer erp_conflicts
    op.create_index("ix_erp_conflicts_connection_id", "erp_conflicts", ["connection_id"])
    op.create_index("ix_erp_conflicts_entity", "erp_conflicts", ["entity"])
    op.create_index("ix_erp_conflicts_status", "erp_conflicts", ["status"])
    op.create_index("ix_erp_conflicts_priority", "erp_conflicts", ["priority"])
    op.create_index("ix_erp_conflicts_detected_at", "erp_conflicts", ["detected_at"])
    op.create_index("ix_erp_conflicts_pending", "erp_conflicts", ["connection_id", "status"], postgresql_where=sa.text("status = 'pending'"))

    # ==========================================================================
    # ERP Entity Mappings - Verknuepfung lokaler Entitaeten mit ERP-IDs
    # ==========================================================================
    op.create_table(
        "erp_entity_mappings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("connection_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("erp_connections.id", ondelete="CASCADE"), nullable=False),

        # Entitaets-Verknuepfung
        sa.Column("entity_type", sa.String(50), nullable=False),  # customer, supplier, invoice
        sa.Column("local_id", postgresql.UUID(as_uuid=True), nullable=False),  # ID im Ablage-System
        sa.Column("remote_id", sa.String(100), nullable=False),  # ID im ERP

        # Sync-Status
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("local_version", sa.Integer(), nullable=False, server_default="1"),  # Optimistic Locking
        sa.Column("remote_version", sa.String(100), nullable=True),  # ERP-seitige Version

        # Checksums fuer Delta-Sync
        sa.Column("local_checksum", sa.String(64), nullable=True),  # SHA-256
        sa.Column("remote_checksum", sa.String(64), nullable=True),

        # Metadaten
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # Indizes fuer erp_entity_mappings
    op.create_index("ix_erp_entity_mappings_connection_entity", "erp_entity_mappings", ["connection_id", "entity_type"])
    op.create_index("ix_erp_entity_mappings_local_id", "erp_entity_mappings", ["local_id"])
    op.create_index("ix_erp_entity_mappings_remote_id", "erp_entity_mappings", ["remote_id"])

    # Unique constraint: Eine Verknuepfung pro local_id/entity/connection
    op.create_unique_constraint(
        "uq_erp_entity_mappings_local",
        "erp_entity_mappings",
        ["connection_id", "entity_type", "local_id"]
    )

    # Unique constraint: Eine Verknuepfung pro remote_id/entity/connection
    op.create_unique_constraint(
        "uq_erp_entity_mappings_remote",
        "erp_entity_mappings",
        ["connection_id", "entity_type", "remote_id"]
    )


def downgrade() -> None:
    # Drop tables in reverse order of creation (children before parents)
    # Note: Indexes and constraints are automatically dropped with their tables

    # 1. erp_entity_mappings (depends on erp_connections)
    op.drop_constraint("uq_erp_entity_mappings_remote", "erp_entity_mappings", type_="unique")
    op.drop_constraint("uq_erp_entity_mappings_local", "erp_entity_mappings", type_="unique")
    op.drop_table("erp_entity_mappings")

    # 2. erp_conflicts (depends on erp_connections + erp_sync_history)
    op.drop_table("erp_conflicts")

    # 3. erp_field_mappings (depends on erp_connections)
    op.drop_constraint("uq_erp_field_mappings_unique", "erp_field_mappings", type_="unique")
    op.drop_table("erp_field_mappings")

    # 4. erp_sync_history (depends on erp_connections)
    op.drop_table("erp_sync_history")

    # 5. erp_connections (parent - no ERP dependencies)
    op.drop_table("erp_connections")

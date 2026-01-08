"""Add email and folder import tables.

Revision ID: 076_add_email_folder_import
Revises: 075_add_user_dashboards
Create Date: 2026-01-02

E-Mail/Ordner-Import-Infrastruktur:
- email_import_configs: IMAP Server-Konfigurationen
- folder_import_configs: Hotfolder-Konfigurationen
- import_rules: Filter- und Routing-Regeln
- import_logs: Import-Historie mit Status-Tracking
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "076"
down_revision = "075"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add email and folder import tables."""

    # Check dialect
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        uuid_type = postgresql.UUID(as_uuid=True)
        json_type = postgresql.JSONB
        uuid_default = sa.text("gen_random_uuid()")
    else:
        uuid_type = sa.String(36)
        json_type = sa.JSON
        uuid_default = None

    # =========================================================================
    # 1. EMAIL_IMPORT_CONFIGS - IMAP Server-Konfigurationen
    # =========================================================================
    op.create_table(
        "email_import_configs",
        sa.Column("id", uuid_type, primary_key=True, server_default=uuid_default),
        sa.Column("user_id", uuid_type, nullable=False),
        sa.Column("company_id", uuid_type, nullable=True),

        # Konfigurationsname
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),

        # IMAP Server-Einstellungen
        sa.Column("imap_server", sa.String(255), nullable=False),
        sa.Column("imap_port", sa.Integer, default=993),
        sa.Column("use_ssl", sa.Boolean, default=True),
        sa.Column("use_starttls", sa.Boolean, default=False),

        # Verschluesselte Credentials (AES-256-GCM)
        sa.Column("username_encrypted", sa.String(500), nullable=False),
        sa.Column("password_encrypted", sa.String(500), nullable=False),

        # IMAP-Ordner
        sa.Column("imap_folder", sa.String(255), default="INBOX"),
        sa.Column("processed_folder", sa.String(255), nullable=True),
        sa.Column("error_folder", sa.String(255), nullable=True),

        # Sync-Einstellungen
        sa.Column("sync_interval_minutes", sa.Integer, default=15),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_uid", sa.BigInteger, default=0),

        # Filter-Einstellungen
        sa.Column("filter_from_addresses", json_type, default=list),
        sa.Column("filter_subject_patterns", json_type, default=list),
        sa.Column("filter_attachment_types", json_type, default=list),

        # Verarbeitungs-Optionen
        sa.Column("extract_attachments_only", sa.Boolean, default=True),
        sa.Column("include_email_body_as_document", sa.Boolean, default=False),
        sa.Column("auto_classify", sa.Boolean, default=True),
        sa.Column("auto_ocr", sa.Boolean, default=True),
        sa.Column("default_folder_id", uuid_type, nullable=True),

        # Status
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("connection_status", sa.String(50), default="pending"),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("error_count", sa.Integer, default=0),

        # Statistiken
        sa.Column("total_emails_processed", sa.Integer, default=0),
        sa.Column("total_documents_created", sa.Integer, default=0),

        # Audit
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column("created_by_id", uuid_type, nullable=True),

        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        # NOTE: default_folder_id ohne FK - folders Tabelle existiert nicht
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
    )

    op.create_index("ix_email_import_configs_user_id", "email_import_configs", ["user_id"])
    op.create_index("ix_email_import_configs_company_id", "email_import_configs", ["company_id"])
    op.create_index("ix_email_import_configs_is_active", "email_import_configs", ["is_active"])

    # Unique constraint: Ein Name pro User
    op.create_unique_constraint(
        "uq_email_import_configs_user_name",
        "email_import_configs",
        ["user_id", "name"]
    )

    # =========================================================================
    # 2. FOLDER_IMPORT_CONFIGS - Hotfolder-Konfigurationen
    # =========================================================================
    op.create_table(
        "folder_import_configs",
        sa.Column("id", uuid_type, primary_key=True, server_default=uuid_default),
        sa.Column("user_id", uuid_type, nullable=False),
        sa.Column("company_id", uuid_type, nullable=True),

        # Konfigurationsname
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),

        # Ordner-Einstellungen
        sa.Column("watch_path", sa.String(1000), nullable=False),
        sa.Column("is_network_path", sa.Boolean, default=False),
        sa.Column("network_credentials_encrypted", sa.String(500), nullable=True),

        # Verhalten
        sa.Column("recursive", sa.Boolean, default=False),
        sa.Column("include_patterns", json_type, default=["*.pdf", "*.jpg", "*.png", "*.tiff"]),
        sa.Column("exclude_patterns", json_type, default=["*.tmp", "~*", "._*"]),

        # Verarbeitung nach Import
        sa.Column("move_after_processing", sa.Boolean, default=True),
        sa.Column("processed_subfolder", sa.String(255), default="processed"),
        sa.Column("error_subfolder", sa.String(255), default="error"),
        sa.Column("delete_after_processing", sa.Boolean, default=False),

        # Import-Optionen
        sa.Column("auto_classify", sa.Boolean, default=True),
        sa.Column("auto_ocr", sa.Boolean, default=True),
        sa.Column("default_folder_id", uuid_type, nullable=True),
        sa.Column("preserve_filename", sa.Boolean, default=True),

        # Polling (Backup fuer Watchdog)
        sa.Column("poll_interval_seconds", sa.Integer, default=60),
        sa.Column("last_poll_at", sa.DateTime(timezone=True), nullable=True),

        # Status
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("watcher_status", sa.String(50), default="stopped"),
        sa.Column("last_error", sa.Text, nullable=True),

        # Statistiken
        sa.Column("files_processed_today", sa.Integer, default=0),
        sa.Column("total_files_processed", sa.Integer, default=0),
        sa.Column("total_documents_created", sa.Integer, default=0),

        # Audit
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column("created_by_id", uuid_type, nullable=True),

        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        # NOTE: default_folder_id ohne FK - folders Tabelle existiert nicht
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
    )

    op.create_index("ix_folder_import_configs_user_id", "folder_import_configs", ["user_id"])
    op.create_index("ix_folder_import_configs_company_id", "folder_import_configs", ["company_id"])
    op.create_index("ix_folder_import_configs_is_active", "folder_import_configs", ["is_active"])

    # Unique constraint: Ein Pfad pro User
    op.create_unique_constraint(
        "uq_folder_import_configs_user_path",
        "folder_import_configs",
        ["user_id", "watch_path"]
    )

    # =========================================================================
    # 3. IMPORT_RULES - Filter- und Routing-Regeln
    # =========================================================================
    op.create_table(
        "import_rules",
        sa.Column("id", uuid_type, primary_key=True, server_default=uuid_default),
        sa.Column("user_id", uuid_type, nullable=False),

        # Regel-Identitaet
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("priority", sa.Integer, default=100),

        # Quelle (auf welche Configs diese Regel angewendet wird)
        sa.Column("applies_to_email_configs", json_type, default=list),
        sa.Column("applies_to_folder_configs", json_type, default=list),
        sa.Column("applies_to_all", sa.Boolean, default=False),

        # Bedingungen (JSON-Struktur fuer flexible Matching)
        # Format:
        # {
        #   "operator": "AND" | "OR",
        #   "rules": [
        #     {"field": "sender_email", "operator": "contains", "value": "@lieferant.de"},
        #     {"field": "subject", "operator": "regex", "value": "Rechnung.*\\d{6}"},
        #   ]
        # }
        sa.Column("conditions", json_type, nullable=False, default=dict),

        # Aktionen
        # Format:
        # {
        #   "assign_folder_id": "uuid",
        #   "assign_tags": ["uuid1", "uuid2"],
        #   "assign_document_type": "invoice",
        #   "skip_ocr": false,
        #   "priority_ocr": true,
        #   "notify_users": ["uuid1"],
        # }
        sa.Column("actions", json_type, nullable=False, default=dict),

        # Status
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("match_count", sa.Integer, default=0),
        sa.Column("last_matched_at", sa.DateTime(timezone=True), nullable=True),

        # Audit
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),

        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )

    op.create_index("ix_import_rules_user_id", "import_rules", ["user_id"])
    op.create_index("ix_import_rules_priority", "import_rules", ["priority"])
    op.create_index("ix_import_rules_is_active", "import_rules", ["is_active"])

    # =========================================================================
    # 4. IMPORT_LOGS - Import-Historie mit Status-Tracking
    # =========================================================================
    op.create_table(
        "import_logs",
        sa.Column("id", uuid_type, primary_key=True, server_default=uuid_default),
        sa.Column("user_id", uuid_type, nullable=False),

        # Quell-Referenz
        sa.Column("source_type", sa.String(20), nullable=False),  # 'email' oder 'folder'
        sa.Column("email_config_id", uuid_type, nullable=True),
        sa.Column("folder_config_id", uuid_type, nullable=True),

        # Import-Batch-Info
        sa.Column("batch_id", uuid_type, nullable=False),
        sa.Column("celery_task_id", sa.String(100), nullable=True),

        # Email-spezifische Details
        sa.Column("email_uid", sa.BigInteger, nullable=True),
        sa.Column("email_message_id", sa.String(255), nullable=True),
        sa.Column("email_from", sa.String(255), nullable=True),
        sa.Column("email_subject", sa.String(500), nullable=True),
        sa.Column("email_date", sa.DateTime(timezone=True), nullable=True),

        # Folder-spezifische Details
        sa.Column("original_path", sa.String(1000), nullable=True),
        sa.Column("original_filename", sa.String(255), nullable=True),
        sa.Column("file_modified_at", sa.DateTime(timezone=True), nullable=True),

        # Verarbeitungs-Ergebnis
        sa.Column("status", sa.String(50), nullable=False),  # pending, processing, completed, failed, skipped
        sa.Column("document_id", uuid_type, nullable=True),
        sa.Column("file_hash", sa.String(64), nullable=True),  # SHA256 fuer Deduplizierung
        sa.Column("file_size", sa.Integer, nullable=True),
        sa.Column("mime_type", sa.String(100), nullable=True),

        # Regel-Matching
        sa.Column("matched_rule_id", uuid_type, nullable=True),
        sa.Column("applied_actions", json_type, default=dict),

        # Fehler-Tracking
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("error_code", sa.String(50), nullable=True),
        sa.Column("retry_count", sa.Integer, default=0),

        # Timing
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processing_duration_ms", sa.Integer, nullable=True),

        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["email_config_id"], ["email_import_configs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["folder_config_id"], ["folder_import_configs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["matched_rule_id"], ["import_rules.id"], ondelete="SET NULL"),
    )

    op.create_index("ix_import_logs_user_id", "import_logs", ["user_id"])
    op.create_index("ix_import_logs_batch_id", "import_logs", ["batch_id"])
    op.create_index("ix_import_logs_status", "import_logs", ["status"])
    op.create_index("ix_import_logs_source_type", "import_logs", ["source_type"])
    op.create_index("ix_import_logs_started_at", "import_logs", ["started_at"])
    op.create_index("ix_import_logs_email_config_id", "import_logs", ["email_config_id"])
    op.create_index("ix_import_logs_folder_config_id", "import_logs", ["folder_config_id"])
    op.create_index("ix_import_logs_file_hash", "import_logs", ["file_hash"])


def downgrade() -> None:
    """Remove email and folder import tables."""

    # Drop tables in reverse order (wegen Foreign Keys)
    op.drop_table("import_logs")
    op.drop_table("import_rules")
    op.drop_table("folder_import_configs")
    op.drop_table("email_import_configs")

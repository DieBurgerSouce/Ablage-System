"""Add GoBD Compliance tables for revision-safe archiving.

Revision ID: 107_add_gobd_compliance_tables
Revises: 106_add_bpmn_process_engine
Create Date: 2026-01-19

GoBD-konforme Archivierung mit:
- Audit Chain: Blockchain-aehnliche Hash-Kette fuer Nachvollziehbarkeit
- Retention Policies: Aufbewahrungsfristen pro Dokumentkategorie
- Integrity Checks: Protokollierung von Integritaetspruefungen
- TSA Config: RFC 3161 Zeitstempel-Provider Konfiguration
- Deletion Requests: Workflow fuer Loeschfreigaben

GoBD = Grundsaetze zur ordnungsmaessigen Fuehrung und Aufbewahrung
       von Buechern, Aufzeichnungen und Unterlagen in elektronischer
       Form sowie zum Datenzugriff
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "107_add_gobd_compliance_tables"
down_revision = "106_add_bpmn_process_engine"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ==========================================================================
    # GoBD Audit Chain - Blockchain-like event chain
    # ==========================================================================
    op.create_table(
        "gobd_audit_chain",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        # Chain linkage
        sa.Column(
            "sequence_number",
            sa.Integer(),
            nullable=False,
            comment="Lueckenlose Sequenznummer (startet bei 1)"
        ),
        sa.Column(
            "previous_hash",
            sa.String(128),
            nullable=True,
            comment="SHA-256 Hash des vorherigen Eintrags (NULL fuer Genesis)"
        ),
        sa.Column(
            "content_hash",
            sa.String(128),
            nullable=False,
            comment="SHA-256 Hash des Ereignis-Inhalts"
        ),
        sa.Column(
            "combined_hash",
            sa.String(128),
            nullable=False,
            comment="SHA-256(previous_hash + content_hash)"
        ),
        # Event details
        sa.Column(
            "event_type",
            sa.String(50),
            nullable=False,
            comment="Typ des Ereignisses (AuditChainEventType)"
        ),
        sa.Column(
            "event_data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
            comment="Ereignis-Payload (keine PII!)"
        ),
        # References
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="SET NULL"),
            nullable=True
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
            comment="Benutzer der das Ereignis ausgeloest hat"
        ),
        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False
        ),
        # RFC 3161 Timestamp
        sa.Column(
            "tsa_timestamp",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="RFC 3161 Zeitstempel von TSA"
        ),
        sa.Column(
            "tsa_token",
            sa.Text(),
            nullable=True,
            comment="Base64-encoded TSA Response Token"
        ),
        sa.Column(
            "tsa_provider",
            sa.String(100),
            nullable=True,
            comment="Name des TSA-Providers"
        ),
        # Verification
        sa.Column("is_verified", sa.Boolean(), nullable=False, default=True),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verification_error", sa.Text(), nullable=True),
        # Constraints
        sa.UniqueConstraint("company_id", "sequence_number", name="uq_audit_chain_company_sequence"),
        sa.CheckConstraint(
            "(sequence_number = 1 AND previous_hash IS NULL) OR (sequence_number > 1 AND previous_hash IS NOT NULL)",
            name="ck_audit_chain_genesis"
        ),
        comment="GoBD Audit-Chain: Blockchain-aehnliche verkettete Ereignis-Protokollierung"
    )

    # Indexes for audit chain
    op.create_index("ix_audit_chain_company_seq", "gobd_audit_chain", ["company_id", "sequence_number"])
    op.create_index("ix_audit_chain_combined_hash", "gobd_audit_chain", ["combined_hash"])
    op.create_index("ix_audit_chain_event_type", "gobd_audit_chain", ["event_type"])
    op.create_index("ix_audit_chain_document_id", "gobd_audit_chain", ["document_id"])
    op.create_index("ix_audit_chain_created_at", "gobd_audit_chain", ["created_at"])

    # ==========================================================================
    # Retention Policies - Aufbewahrungsfristen pro Dokumentkategorie
    # ==========================================================================
    op.create_table(
        "gobd_retention_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False
        ),
        # Policy definition
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "document_category",
            sa.String(50),
            nullable=False,
            comment="Dokumentkategorie: invoice, contract, etc."
        ),
        # Retention period
        sa.Column(
            "retention_years",
            sa.Integer(),
            nullable=False,
            default=10,
            comment="Aufbewahrungsdauer in Jahren"
        ),
        sa.Column(
            "legal_basis",
            sa.String(255),
            nullable=True,
            comment="Gesetzliche Grundlage: §147 AO, §257 HGB, etc."
        ),
        # Warnings
        sa.Column(
            "warning_days_before",
            sa.Integer(),
            nullable=False,
            default=180,
            comment="Tage vor Ablauf fuer erste Warnung"
        ),
        sa.Column(
            "critical_days_before",
            sa.Integer(),
            nullable=False,
            default=30,
            comment="Tage vor Ablauf fuer kritische Warnung"
        ),
        # Auto-actions
        sa.Column(
            "auto_delete_after_expiry",
            sa.Boolean(),
            nullable=False,
            default=False,
            comment="Automatisch loeschen nach Ablauf (GEFAEHRLICH!)"
        ),
        sa.Column(
            "require_approval_for_delete",
            sa.Boolean(),
            nullable=False,
            default=True,
            comment="Freigabe vor Loeschung erforderlich"
        ),
        sa.Column(
            "approval_roles",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
            comment="Rollen die Loeschung freigeben koennen"
        ),
        # Notifications
        sa.Column("notify_on_warning", sa.Boolean(), nullable=False, default=True),
        sa.Column(
            "notification_recipients",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
            comment="User-IDs oder Rollen fuer Benachrichtigungen"
        ),
        # Status
        sa.Column("is_active", sa.Boolean(), nullable=False, default=True),
        # Audit
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column(
            "created_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True
        ),
        # Constraints
        sa.UniqueConstraint("company_id", "document_category", name="uq_retention_policy_category"),
        comment="GoBD Aufbewahrungsrichtlinien pro Dokumentkategorie"
    )

    op.create_index("ix_retention_policies_company", "gobd_retention_policies", ["company_id"])
    op.create_index("ix_retention_policies_category", "gobd_retention_policies", ["document_category"])

    # ==========================================================================
    # Archive Integrity Checks - Protokollierung von Integritaetspruefungen
    # ==========================================================================
    op.create_table(
        "gobd_archive_integrity_checks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        # References
        sa.Column(
            "archive_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("document_archives.id", ondelete="CASCADE"),
            nullable=False
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False
        ),
        # Check details
        sa.Column(
            "check_type",
            sa.String(50),
            nullable=False,
            default="scheduled",
            comment="scheduled, manual, repair_verification"
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            default="pending"
        ),
        # Hash comparison
        sa.Column("expected_hash", sa.String(128), nullable=False),
        sa.Column("actual_hash", sa.String(128), nullable=True),
        sa.Column("hash_match", sa.Boolean(), nullable=True),
        # TSA verification
        sa.Column("tsa_verified", sa.Boolean(), nullable=True),
        sa.Column("tsa_verification_error", sa.Text(), nullable=True),
        # Timing
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        # Error details
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("error_details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        # Triggered user
        sa.Column(
            "triggered_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True
        ),
        comment="GoBD Integritaetspruefungen fuer Dokument-Archive"
    )

    op.create_index("ix_integrity_checks_archive", "gobd_archive_integrity_checks", ["archive_id"])
    op.create_index("ix_integrity_checks_company", "gobd_archive_integrity_checks", ["company_id"])
    op.create_index("ix_integrity_checks_status", "gobd_archive_integrity_checks", ["status"])
    op.create_index("ix_integrity_checks_started_at", "gobd_archive_integrity_checks", ["started_at"])

    # ==========================================================================
    # TSA Config - RFC 3161 Zeitstempel-Provider Konfiguration
    # ==========================================================================
    op.create_table(
        "gobd_tsa_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False
        ),
        # Provider info
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "provider_type",
            sa.String(50),
            nullable=False,
            default="rfc3161",
            comment="rfc3161, qualified_eidas"
        ),
        # Endpoint config
        sa.Column("endpoint_url", sa.String(500), nullable=False),
        sa.Column(
            "auth_type",
            sa.String(20),
            nullable=False,
            default="none",
            comment="none, basic, certificate"
        ),
        sa.Column(
            "credentials_vault_key",
            sa.String(255),
            nullable=True,
            comment="Key im Vault fuer Credentials"
        ),
        # Certificate info
        sa.Column("issuer_certificate", sa.Text(), nullable=True),
        sa.Column("certificate_chain", sa.Text(), nullable=True),
        sa.Column("certificate_expires_at", sa.DateTime(timezone=True), nullable=True),
        # Settings
        sa.Column("timeout_seconds", sa.Integer(), nullable=False, default=30),
        sa.Column("retry_count", sa.Integer(), nullable=False, default=3),
        sa.Column("is_default", sa.Boolean(), nullable=False, default=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, default=True),
        # Statistics
        sa.Column("total_requests", sa.Integer(), nullable=False, default=0),
        sa.Column("successful_requests", sa.Integer(), nullable=False, default=0),
        sa.Column("failed_requests", sa.Integer(), nullable=False, default=0),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        # Audit
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        comment="RFC 3161 TSA-Provider Konfiguration fuer qualifizierte Zeitstempel"
    )

    op.create_index("ix_tsa_configs_company", "gobd_tsa_configs", ["company_id"])
    op.create_index("ix_tsa_configs_is_default", "gobd_tsa_configs", ["company_id", "is_default"])

    # ==========================================================================
    # Retention Deletion Requests - Workflow fuer Loeschfreigaben
    # ==========================================================================
    op.create_table(
        "gobd_retention_deletion_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        # References
        sa.Column(
            "archive_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("document_archives.id", ondelete="CASCADE"),
            nullable=False
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False
        ),
        # Request details
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("retention_expired_at", sa.DateTime(timezone=True), nullable=False),
        # Status
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            default="pending",
            comment="pending, approved, rejected, executed"
        ),
        # Request
        sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "requested_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True
        ),
        # Approval
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "approved_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True
        ),
        sa.Column("approval_comment", sa.Text(), nullable=True),
        # Rejection
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "rejected_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True
        ),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        # Execution
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("execution_log", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        comment="GoBD Loeschanfragen fuer abgelaufene Dokumente"
    )

    op.create_index("ix_deletion_requests_archive", "gobd_retention_deletion_requests", ["archive_id"])
    op.create_index("ix_deletion_requests_company", "gobd_retention_deletion_requests", ["company_id"])
    op.create_index("ix_deletion_requests_status", "gobd_retention_deletion_requests", ["status"])


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_index("ix_deletion_requests_status", table_name="gobd_retention_deletion_requests")
    op.drop_index("ix_deletion_requests_company", table_name="gobd_retention_deletion_requests")
    op.drop_index("ix_deletion_requests_archive", table_name="gobd_retention_deletion_requests")
    op.drop_table("gobd_retention_deletion_requests")

    op.drop_index("ix_tsa_configs_is_default", table_name="gobd_tsa_configs")
    op.drop_index("ix_tsa_configs_company", table_name="gobd_tsa_configs")
    op.drop_table("gobd_tsa_configs")

    op.drop_index("ix_integrity_checks_started_at", table_name="gobd_archive_integrity_checks")
    op.drop_index("ix_integrity_checks_status", table_name="gobd_archive_integrity_checks")
    op.drop_index("ix_integrity_checks_company", table_name="gobd_archive_integrity_checks")
    op.drop_index("ix_integrity_checks_archive", table_name="gobd_archive_integrity_checks")
    op.drop_table("gobd_archive_integrity_checks")

    op.drop_index("ix_retention_policies_category", table_name="gobd_retention_policies")
    op.drop_index("ix_retention_policies_company", table_name="gobd_retention_policies")
    op.drop_table("gobd_retention_policies")

    op.drop_index("ix_audit_chain_created_at", table_name="gobd_audit_chain")
    op.drop_index("ix_audit_chain_document_id", table_name="gobd_audit_chain")
    op.drop_index("ix_audit_chain_event_type", table_name="gobd_audit_chain")
    op.drop_index("ix_audit_chain_combined_hash", table_name="gobd_audit_chain")
    op.drop_index("ix_audit_chain_company_seq", table_name="gobd_audit_chain")
    op.drop_table("gobd_audit_chain")

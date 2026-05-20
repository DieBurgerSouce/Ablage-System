# -*- coding: utf-8 -*-
"""Add GDPR Consent Management Tables.

PHASE 7: Compliance & Audit - GDPR Erweiterungen

Neue Tabellen:
- gdpr_consent_scopes: Granulare Einwilligungen pro User/Scope
- gdpr_consent_versions: Versionierte Consent-Texte
- gdpr_data_subject_requests: Betroffenenrechte-Anfragen (Art. 15-20 DSGVO)
- gdpr_data_exports: Datenexport-Logs fuer Portabilitaet

Revision ID: 113_add_gdpr_consent
Revises: 112_add_business_rules
Create Date: 2026-01-21
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "113_add_gdpr_consent"
down_revision: Union[str, None] = "112_add_business_rules"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ==========================================================================
    # GDPR Consent Versions - Versionierte Consent-Texte
    # ==========================================================================
    op.create_table(
        "gdpr_consent_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("scope", sa.String(100), nullable=False),
        sa.Column("version", sa.String(50), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("full_text", sa.Text, nullable=False),
        sa.Column("text_hash", sa.String(64), nullable=False),  # SHA-256
        sa.Column("language", sa.String(10), nullable=False, server_default="de"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        # Unique constraint: Ein Scope kann nur eine aktive Version haben
        sa.UniqueConstraint("scope", "version", name="uq_gdpr_consent_versions_scope_version"),
    )

    # Index fuer aktive Versionen
    op.create_index(
        "ix_gdpr_consent_versions_scope_active",
        "gdpr_consent_versions",
        ["scope", "is_active"],
        postgresql_where=sa.text("is_active = true"),
    )

    # ==========================================================================
    # GDPR Consent Scopes - Granulare Einwilligungen
    # ==========================================================================
    op.create_table(
        "gdpr_consent_scopes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=True),
        # Scope: personal_data, financial_data, document_processing, analytics, marketing
        sa.Column("scope", sa.String(100), nullable=False),
        sa.Column("consent_given", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("consent_version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("gdpr_consent_versions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("consent_text_hash", sa.String(64), nullable=True),  # SHA-256 des akzeptierten Textes
        # Zeitstempel
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        # Methode der Einwilligung
        sa.Column("consent_method", sa.String(50), nullable=True),  # web_form, api, paper, verbal
        sa.Column("ip_address", sa.String(45), nullable=True),  # IPv4/IPv6
        sa.Column("user_agent", sa.String(500), nullable=True),
        # Audit
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        # Multi-Tenant RLS
        sa.Index("ix_gdpr_consent_scopes_company_id", "company_id"),
    )

    # Indexes
    op.create_index("ix_gdpr_consent_scopes_user_id", "gdpr_consent_scopes", ["user_id"])
    op.create_index("ix_gdpr_consent_scopes_scope", "gdpr_consent_scopes", ["scope"])
    op.create_index(
        "ix_gdpr_consent_scopes_user_scope_active",
        "gdpr_consent_scopes",
        ["user_id", "scope"],
        postgresql_where=sa.text("withdrawn_at IS NULL"),
    )

    # ==========================================================================
    # GDPR Data Subject Requests - Betroffenenrechte-Anfragen
    # ==========================================================================
    op.create_table(
        "gdpr_data_subject_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="SET NULL"), nullable=True),
        # Request Type: access (Art.15), erasure (Art.17), rectification (Art.16),
        #               portability (Art.20), restriction (Art.18), objection (Art.21)
        sa.Column("request_type", sa.String(50), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        # Status: pending, in_progress, completed, rejected, cancelled
        # Antragsdaten
        sa.Column("requester_email", sa.String(255), nullable=False),
        sa.Column("requester_name", sa.String(255), nullable=True),
        sa.Column("verification_token", sa.String(255), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        # Details
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("affected_data_categories", postgresql.JSONB, nullable=True),  # ["personal", "financial", ...]
        sa.Column("rectification_details", postgresql.JSONB, nullable=True),  # Fuer Art. 16
        # Bearbeitung
        sa.Column("assigned_to_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("response_notes", sa.Text, nullable=True),
        sa.Column("rejection_reason", sa.Text, nullable=True),
        # Ergebnis
        sa.Column("export_file_path", sa.String(500), nullable=True),  # Fuer Portabilitaet
        sa.Column("export_format", sa.String(20), nullable=True),  # json, csv, xml
        # Zeitstempel (DSGVO: 30 Tage Frist)
        sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=False),  # requested_at + 30 Tage
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        # Audit
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Indexes
    op.create_index("ix_gdpr_dsr_user_id", "gdpr_data_subject_requests", ["user_id"])
    op.create_index("ix_gdpr_dsr_company_id", "gdpr_data_subject_requests", ["company_id"])
    op.create_index("ix_gdpr_dsr_status", "gdpr_data_subject_requests", ["status"])
    op.create_index("ix_gdpr_dsr_request_type", "gdpr_data_subject_requests", ["request_type"])
    op.create_index("ix_gdpr_dsr_due_date", "gdpr_data_subject_requests", ["due_date"])
    op.create_index(
        "ix_gdpr_dsr_pending_overdue",
        "gdpr_data_subject_requests",
        ["due_date", "status"],
        postgresql_where=sa.text("status IN ('pending', 'in_progress')"),
    )

    # ==========================================================================
    # GDPR Data Exports - Datenexport-Logs
    # ==========================================================================
    op.create_table(
        "gdpr_data_exports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="SET NULL"), nullable=True),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("gdpr_data_subject_requests.id", ondelete="SET NULL"), nullable=True),
        # Export-Details
        sa.Column("export_type", sa.String(50), nullable=False),  # full, partial, category
        sa.Column("data_categories", postgresql.JSONB, nullable=False),  # ["documents", "comments", ...]
        sa.Column("format", sa.String(20), nullable=False, server_default="json"),
        sa.Column("file_path", sa.String(500), nullable=True),
        sa.Column("file_size_bytes", sa.BigInteger, nullable=True),
        sa.Column("file_hash", sa.String(64), nullable=True),  # SHA-256
        # Status
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        # Status: pending, processing, completed, failed, expired, downloaded
        sa.Column("error_message", sa.Text, nullable=True),
        # Download-Tracking
        sa.Column("download_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_downloaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),  # 7 Tage default
        # Zeitstempel
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Indexes
    op.create_index("ix_gdpr_exports_user_id", "gdpr_data_exports", ["user_id"])
    op.create_index("ix_gdpr_exports_company_id", "gdpr_data_exports", ["company_id"])
    op.create_index("ix_gdpr_exports_request_id", "gdpr_data_exports", ["request_id"])
    op.create_index("ix_gdpr_exports_status", "gdpr_data_exports", ["status"])
    op.create_index(
        "ix_gdpr_exports_expired",
        "gdpr_data_exports",
        ["expires_at", "status"],
        postgresql_where=sa.text("status = 'completed'"),
    )

    # ==========================================================================
    # GDPR Consent History - Audit Trail fuer Einwilligungsaenderungen
    # ==========================================================================
    op.create_table(
        "gdpr_consent_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("consent_scope_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("gdpr_consent_scopes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        # Aenderung
        sa.Column("action", sa.String(50), nullable=False),  # granted, withdrawn, updated, expired
        sa.Column("previous_value", sa.Boolean, nullable=True),
        sa.Column("new_value", sa.Boolean, nullable=False),
        sa.Column("consent_version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("gdpr_consent_versions.id", ondelete="SET NULL"), nullable=True),
        # Kontext
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column("reason", sa.Text, nullable=True),
        # Zeitstempel
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Indexes
    op.create_index("ix_gdpr_consent_history_consent_scope_id", "gdpr_consent_history", ["consent_scope_id"])
    op.create_index("ix_gdpr_consent_history_user_id", "gdpr_consent_history", ["user_id"])
    op.create_index("ix_gdpr_consent_history_action", "gdpr_consent_history", ["action"])
    op.create_index("ix_gdpr_consent_history_created_at", "gdpr_consent_history", ["created_at"])


def downgrade() -> None:
    op.drop_table("gdpr_consent_history")
    op.drop_table("gdpr_data_exports")
    op.drop_table("gdpr_data_subject_requests")
    op.drop_table("gdpr_consent_scopes")
    op.drop_table("gdpr_consent_versions")

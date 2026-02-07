"""Add consent management tables

Vision 2.0 Feature: Datenschutz-by-Design
- consent_records: Einwilligungsverwaltung (DSGVO Art. 6, 7)
- data_processing_agreements: AVV nach Art. 28
- consent_audit_logs: Vollstaendiger Audit-Trail
- retention_policies: Datenminimierung

Revision ID: 143_consent_mgmt
Revises: 142_add_process_events
Create Date: 2026-01-29
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '143_consent_mgmt'
down_revision: Union[str, None] = '142_add_process_events'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ==========================================================================
    # consent_records - Einwilligungsverwaltung
    # ==========================================================================
    op.create_table(
        'consent_records',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),

        # Betroffene Person/Firma
        sa.Column('entity_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('business_entities.id', ondelete='CASCADE'),
                  nullable=True, index=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='CASCADE'),
                  nullable=True, index=True),

        # Einwilligungs-Details
        sa.Column('consent_type', sa.String(50), nullable=False, index=True),
        sa.Column('status', sa.String(20), nullable=False, default='pending', index=True),
        sa.Column('legal_basis', sa.String(30), nullable=False, default='consent'),

        # Wer hat eingewilligt
        sa.Column('grantor_name', sa.String(200), nullable=True),
        sa.Column('grantor_role', sa.String(100), nullable=True),
        sa.Column('grantor_email', sa.String(254), nullable=True),

        # Zeitstempel
        sa.Column('requested_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('granted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('denied_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('withdrawn_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),

        # Quelle und Nachweis
        sa.Column('source', sa.String(30), nullable=False, default='web_form'),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('user_agent', sa.String(500), nullable=True),

        # Dokumentation
        sa.Column('document_reference', sa.String(255), nullable=True),
        sa.Column('document_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('documents.id', ondelete='SET NULL'),
                  nullable=True),

        # Scope der Einwilligung
        sa.Column('scope', postgresql.JSONB, default={}),
        sa.Column('conditions', sa.Text, nullable=True),
        sa.Column('restrictions', postgresql.JSONB, default=[]),

        # Version
        sa.Column('version', sa.Integer, default=1),
        sa.Column('previous_version_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('consent_records.id', ondelete='SET NULL'),
                  nullable=True),

        # Widerruf-Details
        sa.Column('withdrawal_reason', sa.Text, nullable=True),
        sa.Column('withdrawal_method', sa.String(50), nullable=True),

        # Notizen
        sa.Column('notes', sa.Text, nullable=True),

        # Multi-Tenant
        sa.Column('company_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('companies.id', ondelete='CASCADE'),
                  nullable=False, index=True),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(),
                  onupdate=sa.func.now()),
    )

    # Indexes fuer consent_records
    op.create_index(
        'ix_consent_records_entity_type',
        'consent_records',
        ['entity_id', 'consent_type']
    )
    op.create_index(
        'ix_consent_records_company_status',
        'consent_records',
        ['company_id', 'status']
    )

    # ==========================================================================
    # data_processing_agreements - AVV nach Art. 28
    # ==========================================================================
    op.create_table(
        'data_processing_agreements',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),

        # Vertragsparteien
        sa.Column('controller_name', sa.String(255), nullable=False),
        sa.Column('processor_name', sa.String(255), nullable=False),
        sa.Column('processor_entity_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('business_entities.id', ondelete='SET NULL'),
                  nullable=True, index=True),

        # Vertragsnummer und Titel
        sa.Column('agreement_number', sa.String(50), nullable=True, unique=True),
        sa.Column('title', sa.String(255), nullable=False),

        # Zeitraum
        sa.Column('effective_date', sa.Date, nullable=False),
        sa.Column('expiration_date', sa.Date, nullable=True),
        sa.Column('auto_renewal', sa.Boolean, default=False),

        # Gegenstand der Verarbeitung
        sa.Column('subject_matter', sa.Text, nullable=True),
        sa.Column('processing_purposes', postgresql.JSONB, default=[]),
        sa.Column('data_categories', postgresql.JSONB, default=[]),
        sa.Column('data_subjects', postgresql.JSONB, default=[]),

        # TOM
        sa.Column('tom_reference', sa.String(255), nullable=True),
        sa.Column('tom_document_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('documents.id', ondelete='SET NULL'),
                  nullable=True),

        # Subunternehmer
        sa.Column('subprocessor_allowed', sa.Boolean, default=False),
        sa.Column('subprocessors', postgresql.JSONB, default=[]),

        # Internationale Uebermittlung
        sa.Column('international_transfer', sa.Boolean, default=False),
        sa.Column('transfer_mechanisms', postgresql.JSONB, default=[]),

        # Kontakt
        sa.Column('processor_dpo_name', sa.String(200), nullable=True),
        sa.Column('processor_dpo_email', sa.String(254), nullable=True),

        # Status
        sa.Column('status', sa.String(30), nullable=False, default='active'),

        # Dokumentation
        sa.Column('agreement_document_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('documents.id', ondelete='SET NULL'),
                  nullable=True),

        # Kuendigungsdetails
        sa.Column('terminated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('termination_reason', sa.Text, nullable=True),

        # Notizen
        sa.Column('notes', sa.Text, nullable=True),

        # Multi-Tenant
        sa.Column('company_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('companies.id', ondelete='CASCADE'),
                  nullable=False, index=True),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(),
                  onupdate=sa.func.now()),
    )

    # Index fuer DPA
    op.create_index(
        'ix_dpa_company_status',
        'data_processing_agreements',
        ['company_id', 'status']
    )

    # ==========================================================================
    # consent_audit_logs - Audit-Trail
    # ==========================================================================
    op.create_table(
        'consent_audit_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),

        # Referenz zur Einwilligung
        sa.Column('consent_record_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('consent_records.id', ondelete='CASCADE'),
                  nullable=False, index=True),

        # Aktion
        sa.Column('action', sa.String(30), nullable=False, index=True),

        # Wer hat die Aktion ausgefuehrt
        sa.Column('performed_by_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='SET NULL'),
                  nullable=True),
        sa.Column('performed_by_name', sa.String(200), nullable=True),
        sa.Column('performed_by_role', sa.String(100), nullable=True),

        # Zeitstempel
        sa.Column('performed_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),

        # Details zur Aktion
        sa.Column('old_value', postgresql.JSONB, default={}),
        sa.Column('new_value', postgresql.JSONB, default={}),
        sa.Column('changes', postgresql.JSONB, default={}),

        # Technische Details
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('user_agent', sa.String(500), nullable=True),

        # Notizen/Begruendung
        sa.Column('reason', sa.Text, nullable=True),

        # Multi-Tenant
        sa.Column('company_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('companies.id', ondelete='CASCADE'),
                  nullable=False, index=True),
    )

    # Index fuer Audit Logs
    op.create_index(
        'ix_consent_audit_company_time',
        'consent_audit_logs',
        ['company_id', 'performed_at']
    )

    # ==========================================================================
    # retention_policies - Datenminimierung
    # ==========================================================================
    op.create_table(
        'retention_policies',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),

        # Richtlinien-Details
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text, nullable=True),

        # Was wird betroffen
        sa.Column('document_type', sa.String(50), nullable=True),
        sa.Column('data_category', sa.String(50), nullable=True),

        # Aufbewahrungsdauer
        sa.Column('retention_days', sa.Integer, nullable=False),

        # Rechtsgrundlage
        sa.Column('legal_basis', sa.String(255), nullable=True),

        # Aktion nach Ablauf
        sa.Column('action_after_expiry', sa.String(30), default='archive'),

        # Ausnahmen
        sa.Column('exceptions', postgresql.JSONB, default=[]),

        # Benachrichtigung vor Loeschung
        sa.Column('notify_days_before', sa.Integer, default=30),
        sa.Column('notify_emails', postgresql.JSONB, default=[]),

        # Status
        sa.Column('is_active', sa.Boolean, default=True),

        # Multi-Tenant
        sa.Column('company_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('companies.id', ondelete='CASCADE'),
                  nullable=False, index=True),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(),
                  onupdate=sa.func.now()),

        # Unique Constraint
        sa.UniqueConstraint('company_id', 'name', name='uq_retention_policy_name'),
    )


def downgrade() -> None:
    op.drop_table('retention_policies')
    op.drop_table('consent_audit_logs')
    op.drop_table('data_processing_agreements')
    op.drop_table('consent_records')

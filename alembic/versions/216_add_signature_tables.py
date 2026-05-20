"""Add QES/eIDAS signature tables

Revision ID: 216_add_signature_tables
Revises: 215_add_document_integrity_tables
Create Date: 2026-02-13

Adds signature management tables for eIDAS-compliant electronic signatures:
- signature_requests: Signaturanfragen
- signature_entries: Einzelne Signaturen
- signature_audit_logs: Audit-Trail
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '216_add_signature_tables'
down_revision: str = '215_add_document_integrity_tables'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(tablename: str) -> bool:
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT 1 FROM pg_tables WHERE schemaname='public' AND tablename=:t"
    ), {"t": tablename})
    return result.fetchone() is not None


def upgrade() -> None:
    """Create signature tables."""

    if not _table_exists('signature_requests'):
        op.create_table(
            'signature_requests',
            sa.Column('id', sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column('document_id', sa.dialects.postgresql.UUID(as_uuid=True),
                       sa.ForeignKey('documents.id', ondelete='CASCADE'), nullable=False),
            sa.Column('company_id', sa.dialects.postgresql.UUID(as_uuid=True),
                       sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),
            sa.Column('title', sa.String(255), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('signature_level', sa.String(20), nullable=False, server_default='advanced'),
            sa.Column('provider', sa.String(20), nullable=False, server_default='internal'),
            sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
            sa.Column('requested_by', sa.dialects.postgresql.UUID(as_uuid=True),
                       sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('requested_at', sa.DateTime(timezone=True), nullable=False,
                       server_default=sa.func.now()),
            sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('signing_order_required', sa.Boolean(), nullable=False, server_default='false'),
            sa.Column('metadata_json', sa.dialects.postgresql.JSONB(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                       server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False,
                       server_default=sa.func.now()),
            sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index('ix_signature_requests_document_id', 'signature_requests', ['document_id'])
        op.create_index('ix_signature_requests_status', 'signature_requests', ['status'])
        op.create_index('ix_signature_requests_company_id', 'signature_requests', ['company_id'])

    if not _table_exists('signature_entries'):
        op.create_table(
            'signature_entries',
            sa.Column('id', sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column('signature_request_id', sa.dialects.postgresql.UUID(as_uuid=True),
                       sa.ForeignKey('signature_requests.id', ondelete='CASCADE'), nullable=False),
            sa.Column('company_id', sa.dialects.postgresql.UUID(as_uuid=True),
                       sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),
            sa.Column('signer_id', sa.dialects.postgresql.UUID(as_uuid=True),
                       sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('signer_email', sa.String(255), nullable=False),
            sa.Column('signer_name', sa.String(255), nullable=False),
            sa.Column('signing_order', sa.Integer(), nullable=False, server_default='1'),
            sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
            sa.Column('signed_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('rejected_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('rejection_reason', sa.Text(), nullable=True),
            sa.Column('certificate_issuer', sa.String(255), nullable=True),
            sa.Column('certificate_serial', sa.String(255), nullable=True),
            sa.Column('signature_hash', sa.String(128), nullable=True),
            sa.Column('provider_reference', sa.String(255), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                       server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False,
                       server_default=sa.func.now()),
        )
        op.create_index('ix_signature_entries_request_id', 'signature_entries',
                         ['signature_request_id'])
        op.create_index('ix_signature_entries_signer_email', 'signature_entries',
                         ['signer_email'])
        op.create_index('ix_signature_entries_company_id', 'signature_entries',
                         ['company_id'])

    if not _table_exists('signature_audit_logs'):
        op.create_table(
            'signature_audit_logs',
            sa.Column('id', sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column('signature_request_id', sa.dialects.postgresql.UUID(as_uuid=True),
                       sa.ForeignKey('signature_requests.id', ondelete='CASCADE'), nullable=False),
            sa.Column('company_id', sa.dialects.postgresql.UUID(as_uuid=True),
                       sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),
            sa.Column('action', sa.String(50), nullable=False),
            sa.Column('performed_by', sa.dialects.postgresql.UUID(as_uuid=True),
                       sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('performed_at', sa.DateTime(timezone=True), nullable=False,
                       server_default=sa.func.now()),
            sa.Column('ip_address', sa.String(45), nullable=True),
            sa.Column('user_agent', sa.String(500), nullable=True),
            sa.Column('details_json', sa.dialects.postgresql.JSONB(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                       server_default=sa.func.now()),
        )
        op.create_index('ix_signature_audit_request_id', 'signature_audit_logs',
                         ['signature_request_id'])
        op.create_index('ix_signature_audit_company_id', 'signature_audit_logs',
                         ['company_id'])


def downgrade() -> None:
    """Drop signature tables in reverse order."""
    op.drop_table('signature_audit_logs')
    op.drop_table('signature_entries')
    op.drop_table('signature_requests')

"""Add Document Versioning and Digital Signatures for Vision 2026.

Revision ID: 136_add_document_versioning_signatures
Revises: 135_add_project_management
Create Date: 2026-01-28

Vision 2026 Feature: Dokumenten-Versionierung & Digitale Signaturen
- DocumentVersion: Track document file changes with hash verification
- DocumentSignature: Electronic and qualified digital signatures
- SignatureRequest: Signature workflow management

Extends existing GoBD compliance infrastructure.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers, used by Alembic
revision = '136_add_document_versioning_signatures'
down_revision = '135_add_project_management'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create document versioning and signature tables."""

    # ============================================================================
    # 1. DOCUMENT VERSION TABLE
    # ============================================================================
    op.create_table(
        'document_versions',
        # Primary Key
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),

        # Document Reference
        sa.Column('document_id', UUID(as_uuid=True), sa.ForeignKey('documents.id', ondelete='CASCADE'), nullable=False),

        # Multi-Tenant
        sa.Column('company_id', UUID(as_uuid=True), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),

        # Version Info
        sa.Column('version_number', sa.Integer, nullable=False),
        sa.Column('is_current', sa.Boolean, nullable=False, server_default='false'),

        # File Info
        sa.Column('file_path', sa.String(500), nullable=False),
        sa.Column('file_hash', sa.String(128), nullable=False),  # SHA-256
        sa.Column('hash_algorithm', sa.String(20), nullable=False, server_default='SHA-256'),
        sa.Column('file_size', sa.BigInteger, nullable=True),
        sa.Column('mime_type', sa.String(100), nullable=True),

        # Version Metadata
        sa.Column('change_type', sa.String(50), nullable=False, server_default='edit'),
        sa.Column('change_summary', sa.Text, nullable=True),

        # Previous Version Link (for chain verification)
        sa.Column('previous_version_id', UUID(as_uuid=True), sa.ForeignKey('document_versions.id', ondelete='SET NULL'), nullable=True),

        # Created By
        sa.Column('created_by_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),

        # Audit
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),

        # Constraints
        sa.UniqueConstraint('document_id', 'version_number', name='uq_document_version'),
        sa.CheckConstraint(
            "change_type IN ('initial', 'edit', 'correction', 'annotation', 'ocr_update', 'merge', 'split', 'restore')",
            name='ck_version_change_type'
        ),
    )

    # Indexes for document_versions
    op.create_index('ix_doc_versions_document_id', 'document_versions', ['document_id'])
    op.create_index('ix_doc_versions_company_id', 'document_versions', ['company_id'])
    op.create_index('ix_doc_versions_is_current', 'document_versions', ['document_id', 'is_current'])
    op.create_index('ix_doc_versions_created_at', 'document_versions', ['created_at'])
    op.create_index('ix_doc_versions_file_hash', 'document_versions', ['file_hash'])

    # ============================================================================
    # 2. DOCUMENT SIGNATURE TABLE
    # ============================================================================
    op.create_table(
        'document_signatures',
        # Primary Key
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),

        # Document/Version Reference
        sa.Column('document_id', UUID(as_uuid=True), sa.ForeignKey('documents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('version_id', UUID(as_uuid=True), sa.ForeignKey('document_versions.id', ondelete='SET NULL'), nullable=True),

        # Multi-Tenant
        sa.Column('company_id', UUID(as_uuid=True), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),

        # Signer Info
        sa.Column('signer_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('signer_name', sa.String(255), nullable=False),
        sa.Column('signer_email', sa.String(255), nullable=True),
        sa.Column('signer_role', sa.String(100), nullable=True),

        # Signature Type
        sa.Column('signature_type', sa.String(50), nullable=False, server_default='electronic'),

        # Signature Data (encrypted in app layer)
        sa.Column('signature_data', sa.Text, nullable=True),  # Encrypted
        sa.Column('signature_image', sa.Text, nullable=True),  # Base64 image (optional)

        # Certificate Info (for qualified signatures)
        sa.Column('certificate_issuer', sa.String(255), nullable=True),
        sa.Column('certificate_serial', sa.String(100), nullable=True),
        sa.Column('certificate_valid_from', sa.DateTime(timezone=True), nullable=True),
        sa.Column('certificate_valid_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('certificate_info', JSONB, nullable=False, server_default='{}'),

        # Timestamp Authority
        sa.Column('tsa_timestamp', sa.DateTime(timezone=True), nullable=True),
        sa.Column('tsa_token', sa.Text, nullable=True),

        # Position on document
        sa.Column('page_number', sa.Integer, nullable=True),
        sa.Column('position', JSONB, nullable=True),  # {x, y, width, height}

        # Verification
        sa.Column('verification_status', sa.String(50), nullable=False, server_default='pending'),
        sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('verification_details', JSONB, nullable=False, server_default='{}'),

        # Validity
        sa.Column('valid_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_revoked', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revocation_reason', sa.Text, nullable=True),

        # Audit
        sa.Column('signed_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),

        # Constraints
        sa.CheckConstraint(
            "signature_type IN ('electronic', 'advanced', 'qualified', 'timestamp', 'witness')",
            name='ck_signature_type'
        ),
        sa.CheckConstraint(
            "verification_status IN ('pending', 'valid', 'invalid', 'expired', 'revoked')",
            name='ck_verification_status'
        ),
    )

    # Indexes for document_signatures
    op.create_index('ix_doc_signatures_document_id', 'document_signatures', ['document_id'])
    op.create_index('ix_doc_signatures_version_id', 'document_signatures', ['version_id'])
    op.create_index('ix_doc_signatures_company_id', 'document_signatures', ['company_id'])
    op.create_index('ix_doc_signatures_signer_id', 'document_signatures', ['signer_id'])
    op.create_index('ix_doc_signatures_status', 'document_signatures', ['verification_status'])
    op.create_index('ix_doc_signatures_type', 'document_signatures', ['signature_type'])
    op.create_index('ix_doc_signatures_signed_at', 'document_signatures', ['signed_at'])

    # ============================================================================
    # 3. SIGNATURE REQUEST TABLE (Workflow)
    # ============================================================================
    op.create_table(
        'signature_requests',
        # Primary Key
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),

        # Document Reference
        sa.Column('document_id', UUID(as_uuid=True), sa.ForeignKey('documents.id', ondelete='CASCADE'), nullable=False),

        # Multi-Tenant
        sa.Column('company_id', UUID(as_uuid=True), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),

        # Requester
        sa.Column('requester_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),

        # Request Details
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('message', sa.Text, nullable=True),
        sa.Column('signature_type', sa.String(50), nullable=False, server_default='electronic'),

        # Signers (ordered list)
        sa.Column('signers', JSONB, nullable=False, server_default='[]'),
        # Format: [{"email": "...", "name": "...", "order": 1, "status": "pending", "signed_at": null}]

        # Status
        sa.Column('status', sa.String(50), nullable=False, server_default='pending'),
        sa.Column('current_signer_index', sa.Integer, nullable=False, server_default='0'),
        sa.Column('total_signers', sa.Integer, nullable=False),

        # Deadline & Reminders
        sa.Column('deadline', sa.DateTime(timezone=True), nullable=True),
        sa.Column('reminder_days', JSONB, nullable=False, server_default='[7, 3, 1]'),
        sa.Column('last_reminder_sent', sa.DateTime(timezone=True), nullable=True),

        # Completion
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('cancellation_reason', sa.Text, nullable=True),

        # Access Token (for external signers)
        sa.Column('access_token', sa.String(255), nullable=True, unique=True),
        sa.Column('token_expires_at', sa.DateTime(timezone=True), nullable=True),

        # Audit
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),

        # Constraints
        sa.CheckConstraint(
            "status IN ('draft', 'pending', 'in_progress', 'partially_signed', 'completed', 'expired', 'cancelled')",
            name='ck_sig_request_status'
        ),
    )

    # Indexes for signature_requests
    op.create_index('ix_sig_requests_document_id', 'signature_requests', ['document_id'])
    op.create_index('ix_sig_requests_company_id', 'signature_requests', ['company_id'])
    op.create_index('ix_sig_requests_requester_id', 'signature_requests', ['requester_id'])
    op.create_index('ix_sig_requests_status', 'signature_requests', ['status'])
    op.create_index('ix_sig_requests_deadline', 'signature_requests', ['deadline'])
    op.create_index('ix_sig_requests_token', 'signature_requests', ['access_token'])


def downgrade() -> None:
    """Remove document versioning and signature tables."""

    # Drop signature_requests
    op.drop_index('ix_sig_requests_token', 'signature_requests')
    op.drop_index('ix_sig_requests_deadline', 'signature_requests')
    op.drop_index('ix_sig_requests_status', 'signature_requests')
    op.drop_index('ix_sig_requests_requester_id', 'signature_requests')
    op.drop_index('ix_sig_requests_company_id', 'signature_requests')
    op.drop_index('ix_sig_requests_document_id', 'signature_requests')
    op.drop_table('signature_requests')

    # Drop document_signatures
    op.drop_index('ix_doc_signatures_signed_at', 'document_signatures')
    op.drop_index('ix_doc_signatures_type', 'document_signatures')
    op.drop_index('ix_doc_signatures_status', 'document_signatures')
    op.drop_index('ix_doc_signatures_signer_id', 'document_signatures')
    op.drop_index('ix_doc_signatures_company_id', 'document_signatures')
    op.drop_index('ix_doc_signatures_version_id', 'document_signatures')
    op.drop_index('ix_doc_signatures_document_id', 'document_signatures')
    op.drop_table('document_signatures')

    # Drop document_versions
    op.drop_index('ix_doc_versions_file_hash', 'document_versions')
    op.drop_index('ix_doc_versions_created_at', 'document_versions')
    op.drop_index('ix_doc_versions_is_current', 'document_versions')
    op.drop_index('ix_doc_versions_company_id', 'document_versions')
    op.drop_index('ix_doc_versions_document_id', 'document_versions')
    op.drop_table('document_versions')

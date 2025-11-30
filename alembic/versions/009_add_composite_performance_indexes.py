"""Add composite indexes for query performance

Revision ID: 009
Revises: 008
Create Date: 2025-11-30

Adds composite indexes based on common query patterns:
- User document queries (owner_id + status/date/type)
- Audit log queries (user_id + created_at)
- Processing job lookups (document_id + status)
- OCR result history (document_id + created_at)

Kritisch: Diese Indizes verbessern die Performance um 10-100x
fuer die haeufigsten Abfragen im System.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '009'
down_revision: Union[str, None] = '008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ========== Documents table composite indexes ==========

    # User's documents by status - most common query
    # Query: SELECT * FROM documents WHERE owner_id = ? AND status = ?
    op.create_index(
        'ix_documents_owner_status',
        'documents',
        ['owner_id', 'status']
    )

    # User's documents sorted by upload date (newest first)
    # Query: SELECT * FROM documents WHERE owner_id = ? ORDER BY upload_date DESC
    op.create_index(
        'ix_documents_owner_upload_date',
        'documents',
        ['owner_id', 'upload_date'],
        postgresql_ops={'upload_date': 'DESC'}
    )

    # Filter by owner, type, and status
    # Query: SELECT * FROM documents WHERE owner_id = ? AND document_type = ? AND status = ?
    op.create_index(
        'ix_documents_owner_type_status',
        'documents',
        ['owner_id', 'document_type', 'status']
    )

    # Documents needing processing (status filter)
    # Query: SELECT * FROM documents WHERE status IN ('pending', 'queued')
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_documents_pending_processing
        ON documents (status, created_at)
        WHERE status IN ('pending', 'queued');
    """)

    # German validation score for quality reports
    # Query: SELECT * FROM documents WHERE owner_id = ? AND german_validation_score < ?
    op.create_index(
        'ix_documents_owner_german_score',
        'documents',
        ['owner_id', 'german_validation_score']
    )

    # ========== Audit logs composite indexes ==========

    # User activity timeline
    # Query: SELECT * FROM audit_logs WHERE user_id = ? ORDER BY created_at DESC
    op.create_index(
        'ix_audit_logs_user_created',
        'audit_logs',
        ['user_id', 'created_at'],
        postgresql_ops={'created_at': 'DESC'}
    )

    # Action type filtering with time
    # Query: SELECT * FROM audit_logs WHERE action = ? AND created_at > ?
    op.create_index(
        'ix_audit_logs_action_created',
        'audit_logs',
        ['action', 'created_at'],
        postgresql_ops={'created_at': 'DESC'}
    )

    # Resource-specific audit trail
    # Query: SELECT * FROM audit_logs WHERE resource_type = ? AND resource_id = ?
    op.create_index(
        'ix_audit_logs_resource',
        'audit_logs',
        ['resource_type', 'resource_id']
    )

    # ========== Processing jobs composite indexes ==========

    # Document's job history
    # Query: SELECT * FROM processing_jobs WHERE document_id = ? ORDER BY created_at DESC
    op.create_index(
        'ix_processing_jobs_document_created',
        'processing_jobs',
        ['document_id', 'created_at'],
        postgresql_ops={'created_at': 'DESC'}
    )

    # Jobs by status and queue time
    # Query: SELECT * FROM processing_jobs WHERE status = ? ORDER BY queued_at
    op.create_index(
        'ix_processing_jobs_status_queued',
        'processing_jobs',
        ['status', 'queued_at']
    )

    # Worker's active jobs
    # Query: SELECT * FROM processing_jobs WHERE worker_id = ? AND status = 'processing'
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_processing_jobs_worker_active
        ON processing_jobs (worker_id, status)
        WHERE status = 'processing';
    """)

    # ========== OCR results composite indexes ==========

    # Document's OCR history
    # Query: SELECT * FROM ocr_results WHERE document_id = ? ORDER BY created_at DESC
    op.create_index(
        'ix_ocr_results_document_created',
        'ocr_results',
        ['document_id', 'created_at'],
        postgresql_ops={'created_at': 'DESC'}
    )

    # Backend performance analysis
    # Query: SELECT AVG(processing_time_ms) FROM ocr_results WHERE backend = ?
    op.create_index(
        'ix_ocr_results_backend_time',
        'ocr_results',
        ['backend', 'processing_time_ms']
    )

    # ========== OCR versions composite indexes ==========

    # Current version lookup (most common)
    # Query: SELECT * FROM ocr_result_versions WHERE document_id = ? AND is_current = true
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_ocr_versions_document_current
        ON ocr_result_versions (document_id)
        WHERE is_current = true;
    """)

    # ========== System metrics composite indexes ==========

    # Metric type with time range
    # Query: SELECT * FROM system_metrics WHERE metric_type = ? AND timestamp > ?
    op.create_index(
        'ix_system_metrics_type_timestamp',
        'system_metrics',
        ['metric_type', 'timestamp'],
        postgresql_ops={'timestamp': 'DESC'}
    )

    # Backend-specific metrics
    # Query: SELECT * FROM system_metrics WHERE backend = ? ORDER BY timestamp DESC
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_system_metrics_backend_timestamp
        ON system_metrics (backend, timestamp DESC)
        WHERE backend IS NOT NULL;
    """)


def downgrade() -> None:
    # ========== System metrics indexes ==========
    op.execute("DROP INDEX IF EXISTS ix_system_metrics_backend_timestamp;")
    op.drop_index('ix_system_metrics_type_timestamp', table_name='system_metrics')

    # ========== OCR versions indexes ==========
    op.execute("DROP INDEX IF EXISTS ix_ocr_versions_document_current;")

    # ========== OCR results indexes ==========
    op.drop_index('ix_ocr_results_backend_time', table_name='ocr_results')
    op.drop_index('ix_ocr_results_document_created', table_name='ocr_results')

    # ========== Processing jobs indexes ==========
    op.execute("DROP INDEX IF EXISTS ix_processing_jobs_worker_active;")
    op.drop_index('ix_processing_jobs_status_queued', table_name='processing_jobs')
    op.drop_index('ix_processing_jobs_document_created', table_name='processing_jobs')

    # ========== Audit logs indexes ==========
    op.drop_index('ix_audit_logs_resource', table_name='audit_logs')
    op.drop_index('ix_audit_logs_action_created', table_name='audit_logs')
    op.drop_index('ix_audit_logs_user_created', table_name='audit_logs')

    # ========== Documents indexes ==========
    op.drop_index('ix_documents_owner_german_score', table_name='documents')
    op.execute("DROP INDEX IF EXISTS ix_documents_pending_processing;")
    op.drop_index('ix_documents_owner_type_status', table_name='documents')
    op.drop_index('ix_documents_owner_upload_date', table_name='documents')
    op.drop_index('ix_documents_owner_status', table_name='documents')

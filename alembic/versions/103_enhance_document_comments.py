"""Enhance DocumentComment with Multi-Tenant Support and Field Reference.

Revision ID: 103_enhance_document_comments
Revises: 102_task_reminder_fields
Create Date: 2026-01-17

Collaboration-Suite Erweiterung:
- company_id fuer Multi-Tenant Isolation
- field_reference fuer Inline-Kommentare auf Feldern
- deleted_at/deleted_by_id fuer Soft Delete mit Timestamp
- Index auf company_id + document_id fuer schnelle Queries

Strategy:
1. Spalten als nullable hinzufuegen
2. company_id aus verknuepftem Document backfuellen
3. NOT NULL Constraint setzen
4. Indexes erstellen
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers
revision = '103_enhance_document_comments'
down_revision = '102_task_reminder_fields'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Erweitert document_comments mit Multi-Tenant und Soft-Delete Support."""

    # 1. Neue Spalten hinzufuegen (nullable fuer Backfill)
    op.add_column(
        'document_comments',
        sa.Column(
            'company_id',
            postgresql.UUID(as_uuid=True),
            nullable=True,  # Temporaer nullable fuer Backfill
            comment='Multi-Tenant: Firmenzugehoerigkeit'
        )
    )

    op.add_column(
        'document_comments',
        sa.Column(
            'field_reference',
            sa.String(100),
            nullable=True,
            comment='Feld-Referenz fuer Inline-Kommentare (z.B. "invoice_number", "total_amount")'
        )
    )

    op.add_column(
        'document_comments',
        sa.Column(
            'deleted_at',
            sa.DateTime(timezone=True),
            nullable=True,
            comment='Timestamp des Soft Delete'
        )
    )

    op.add_column(
        'document_comments',
        sa.Column(
            'deleted_by_id',
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment='User der den Kommentar geloescht hat'
        )
    )

    # 2. Backfill company_id aus verknuepftem Document
    op.execute("""
        UPDATE document_comments dc
        SET company_id = d.company_id
        FROM documents d
        WHERE dc.document_id = d.id
        AND dc.company_id IS NULL
    """)

    # 3. NOT NULL Constraint setzen (nachdem alle Daten gefuellt sind)
    op.alter_column(
        'document_comments',
        'company_id',
        nullable=False
    )

    # 4. Foreign Keys hinzufuegen
    op.create_foreign_key(
        'fk_doc_comment_company',
        'document_comments',
        'companies',
        ['company_id'],
        ['id'],
        ondelete='CASCADE'
    )

    op.create_foreign_key(
        'fk_doc_comment_deleted_by',
        'document_comments',
        'users',
        ['deleted_by_id'],
        ['id'],
        ondelete='SET NULL'
    )

    # 5. Indexes fuer Performance
    op.create_index(
        'ix_doc_comment_company',
        'document_comments',
        ['company_id']
    )

    op.create_index(
        'ix_doc_comment_company_document',
        'document_comments',
        ['company_id', 'document_id']
    )

    op.create_index(
        'ix_doc_comment_field_reference',
        'document_comments',
        ['document_id', 'field_reference'],
        postgresql_where=sa.text("field_reference IS NOT NULL")
    )

    op.create_index(
        'ix_doc_comment_deleted_at',
        'document_comments',
        ['deleted_at'],
        postgresql_where=sa.text("deleted_at IS NOT NULL")
    )


def downgrade() -> None:
    """Entfernt die neuen Spalten und Indexes."""

    # Indexes entfernen
    op.drop_index('ix_doc_comment_deleted_at', table_name='document_comments')
    op.drop_index('ix_doc_comment_field_reference', table_name='document_comments')
    op.drop_index('ix_doc_comment_company_document', table_name='document_comments')
    op.drop_index('ix_doc_comment_company', table_name='document_comments')

    # Foreign Keys entfernen
    op.drop_constraint('fk_doc_comment_deleted_by', 'document_comments', type_='foreignkey')
    op.drop_constraint('fk_doc_comment_company', 'document_comments', type_='foreignkey')

    # Spalten entfernen
    op.drop_column('document_comments', 'deleted_by_id')
    op.drop_column('document_comments', 'deleted_at')
    op.drop_column('document_comments', 'field_reference')
    op.drop_column('document_comments', 'company_id')

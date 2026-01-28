# -*- coding: utf-8 -*-
"""Add Document Annotations tables

Revision ID: 131
Revises: 130
Create Date: 2026-01-28

Tabellen:
- document_annotations: Kommentare, Markierungen und Zeichnungen auf Dokumenten

Features:
- Annotation Types: comment, highlight, drawing, shape, text
- SVG-basierte Zeichnungen für Freihand-Markierungen
- Position-Tracking für präzise Platzierung
- Threaded Comments (Parent-Child Hierarchie)
- User-Mentions (@username) Support
- Resolved-Status für Follow-up Tracking
- Multi-Page Support für PDF-Dokumente

Feinpoliert und durchdacht - Deutsche Präzision.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '131'
down_revision = '130'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ==========================================================================
    # Document Annotations - Kommentare und Markierungen
    # ==========================================================================
    op.create_table(
        'document_annotations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),

        # Verknüpfungen
        sa.Column('document_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('documents.id', ondelete='CASCADE'),
                  nullable=False,
                  comment='Verknüpftes Dokument'),
        sa.Column('company_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('companies.id', ondelete='CASCADE'),
                  nullable=False,
                  comment='Multi-Tenant Company'),
        sa.Column('user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='CASCADE'),
                  nullable=False,
                  comment='Ersteller der Annotation'),

        # Annotation-Typ
        sa.Column('annotation_type', sa.String(20), nullable=False,
                  comment='comment, highlight, drawing, shape, text'),

        # Inhalte
        sa.Column('content', sa.Text, nullable=True,
                  comment='Text-Inhalt (für Kommentare)'),
        sa.Column('svg_data', sa.Text, nullable=True,
                  comment='SVG-Daten für Zeichnungen/Formen'),

        # Position auf Dokument
        sa.Column('page', sa.Integer, nullable=False, server_default='1',
                  comment='Seitennummer (1-basiert)'),
        sa.Column('position', postgresql.JSONB, nullable=False,
                  server_default='{}',
                  comment='Position: {x, y, width, height} in Prozent oder Pixeln'),

        # Styling
        sa.Column('color', sa.String(20), nullable=True,
                  comment='Farbe (hex oder named color)'),

        # Threading (für Kommentare)
        sa.Column('parent_annotation_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('document_annotations.id', ondelete='CASCADE'),
                  nullable=True,
                  comment='Parent-Annotation für Threads'),

        # Mentions
        sa.Column('mentioned_user_ids', postgresql.JSONB, nullable=False,
                  server_default='[]',
                  comment='Array von User-IDs die erwähnt wurden'),

        # Resolution-Tracking
        sa.Column('is_resolved', sa.Boolean, nullable=False, server_default='false',
                  comment='True wenn Kommentar als gelöst markiert'),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True,
                  comment='Zeitpunkt der Auflösung'),
        sa.Column('resolved_by_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='SET NULL'),
                  nullable=True,
                  comment='User der die Annotation aufgelöst hat'),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(),
                  comment='Erstellungszeitpunkt'),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(),
                  onupdate=sa.func.now(),
                  comment='Zeitpunkt der letzten Änderung'),
    )

    # Performance-Indexes
    op.create_index(
        'ix_annotations_document_page',
        'document_annotations',
        ['document_id', 'page'],
        postgresql_using='btree'
    )
    op.create_index(
        'ix_annotations_company_created',
        'document_annotations',
        ['company_id', 'created_at'],
        postgresql_using='btree'
    )
    op.create_index(
        'ix_annotations_parent',
        'document_annotations',
        ['parent_annotation_id'],
        postgresql_using='btree',
        postgresql_where=sa.text('parent_annotation_id IS NOT NULL')
    )

    # ==========================================================================
    # RLS Policies für Multi-Tenant Isolation
    # ==========================================================================

    op.execute("ALTER TABLE document_annotations ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY document_annotations_company_isolation
        ON document_annotations
        FOR ALL
        USING (company_id = current_setting('app.current_company_id', true)::uuid)
    """)


def downgrade() -> None:
    # Drop RLS policy
    op.execute(
        "DROP POLICY IF EXISTS document_annotations_company_isolation "
        "ON document_annotations"
    )

    # Disable RLS
    op.execute("ALTER TABLE document_annotations DISABLE ROW LEVEL SECURITY")

    # Drop table
    op.drop_table('document_annotations')

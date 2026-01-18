"""Add DocumentAccessLog for GoBD compliance.

Revision ID: 101_gobd_access_log
Revises: 100_add_shipment_tracking
Create Date: 2026-01-17

GoBD-Anforderung: Nachvollziehbarkeit
- Protokolliert jeden Dokumentzugriff
- Immutable Table (keine Updates/Deletes)
- Sequenznummer für Lückendetektion
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = '101_gobd_access_log'
down_revision = '100_add_shipment_tracking'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create document_access_logs table
    op.create_table(
        'document_access_logs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('document_id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=True),
        sa.Column('company_id', sa.UUID(), nullable=False),
        sa.Column('access_type', sa.String(30), nullable=False,
                  comment='Art des Zugriffs: view, download, export, etc.'),
        sa.Column('access_reason', sa.String(255), nullable=True,
                  comment='Optionaler Grund/Kontext des Zugriffs'),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('user_agent', sa.String(500), nullable=True),
        sa.Column('request_id', sa.String(36), nullable=True,
                  comment='Korrelations-ID zur Request-Verfolgung'),
        sa.Column('success', sa.Boolean(), nullable=False, default=True),
        sa.Column('error_message', sa.String(500), nullable=True),
        sa.Column('bytes_transferred', sa.BigInteger(), nullable=True,
                  comment='Uebertragene Bytes (bei Download/Export)'),
        sa.Column('accessed_at', sa.DateTime(timezone=True),
                  server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('access_metadata', postgresql.JSONB(astext_type=sa.Text()),
                  nullable=True, default={},
                  comment='Zusaetzliche Kontext-Infos (Format, Export-Typ, etc.)'),
        sa.Column('sequence_number', sa.BigInteger(), nullable=True, unique=True,
                  comment='Aufsteigende Sequenz fuer Lueckendetektion'),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        comment='GoBD-konformes Dokumenten-Zugriffsprotokoll'
    )

    # Create indexes for efficient querying
    op.create_index(
        'ix_document_access_logs_document_id',
        'document_access_logs', ['document_id']
    )
    op.create_index(
        'ix_document_access_logs_user_id',
        'document_access_logs', ['user_id']
    )
    op.create_index(
        'ix_document_access_logs_company_id',
        'document_access_logs', ['company_id']
    )
    op.create_index(
        'ix_document_access_logs_accessed_at',
        'document_access_logs', ['accessed_at']
    )
    op.create_index(
        'ix_document_access_logs_access_type',
        'document_access_logs', ['access_type']
    )
    op.create_index(
        'ix_document_access_logs_sequence',
        'document_access_logs', ['sequence_number']
    )
    # Composite index for document audit trail queries
    op.create_index(
        'ix_document_access_logs_doc_time',
        'document_access_logs', ['document_id', 'accessed_at']
    )

    # Create sequence for sequence_number (PostgreSQL)
    op.execute("""
        CREATE SEQUENCE IF NOT EXISTS document_access_log_seq
        START WITH 1
        INCREMENT BY 1
        NO CYCLE;
    """)

    # Create trigger to auto-assign sequence_number
    op.execute("""
        CREATE OR REPLACE FUNCTION set_document_access_log_sequence()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.sequence_number := nextval('document_access_log_seq');
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER trg_document_access_log_sequence
        BEFORE INSERT ON document_access_logs
        FOR EACH ROW
        EXECUTE FUNCTION set_document_access_log_sequence();
    """)

    # GoBD Immutability: Prevent UPDATE and DELETE (PostgreSQL)
    op.execute("""
        CREATE OR REPLACE FUNCTION prevent_access_log_modification()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'GoBD-Compliance: document_access_logs ist immutable. UPDATE/DELETE nicht erlaubt.';
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER trg_prevent_access_log_update
        BEFORE UPDATE ON document_access_logs
        FOR EACH ROW
        EXECUTE FUNCTION prevent_access_log_modification();
    """)

    op.execute("""
        CREATE TRIGGER trg_prevent_access_log_delete
        BEFORE DELETE ON document_access_logs
        FOR EACH ROW
        EXECUTE FUNCTION prevent_access_log_modification();
    """)


def downgrade() -> None:
    # Remove triggers
    op.execute("DROP TRIGGER IF EXISTS trg_prevent_access_log_delete ON document_access_logs;")
    op.execute("DROP TRIGGER IF EXISTS trg_prevent_access_log_update ON document_access_logs;")
    op.execute("DROP TRIGGER IF EXISTS trg_document_access_log_sequence ON document_access_logs;")

    # Remove functions
    op.execute("DROP FUNCTION IF EXISTS prevent_access_log_modification();")
    op.execute("DROP FUNCTION IF EXISTS set_document_access_log_sequence();")

    # Remove sequence
    op.execute("DROP SEQUENCE IF EXISTS document_access_log_seq;")

    # Remove indexes
    op.drop_index('ix_document_access_logs_doc_time', table_name='document_access_logs')
    op.drop_index('ix_document_access_logs_sequence', table_name='document_access_logs')
    op.drop_index('ix_document_access_logs_access_type', table_name='document_access_logs')
    op.drop_index('ix_document_access_logs_accessed_at', table_name='document_access_logs')
    op.drop_index('ix_document_access_logs_company_id', table_name='document_access_logs')
    op.drop_index('ix_document_access_logs_user_id', table_name='document_access_logs')
    op.drop_index('ix_document_access_logs_document_id', table_name='document_access_logs')

    # Drop table
    op.drop_table('document_access_logs')

"""
Streckengeschäft - Soft-Delete Support
Add soft-delete columns to classification tables for GDPR compliance

Revision ID: streckengeschaeft_002
Create Date: 2024-12-29
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = 'streckengeschaeft_002'
down_revision = 'streckengeschaeft_001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ==========================================================================
    # SOFT-DELETE COLUMNS für Klassifikationen
    # ==========================================================================

    # Soft-Delete für drop_shipment_classifications
    op.add_column(
        'drop_shipment_classifications',
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default='false')
    )
    op.add_column(
        'drop_shipment_classifications',
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        'drop_shipment_classifications',
        sa.Column('deleted_by', sa.UUID(), nullable=True)
    )

    # Index für effiziente Abfragen nicht-gelöschter Datensätze
    op.create_index(
        'ix_classifications_not_deleted',
        'drop_shipment_classifications',
        ['is_deleted', 'created_at'],
        postgresql_where=sa.text("is_deleted = false")
    )

    # Index für ZM-Reporting (nur nicht-gelöschte, ZM-relevante)
    op.create_index(
        'ix_classifications_zm_period',
        'drop_shipment_classifications',
        ['zm_relevant', 'created_at'],
        postgresql_where=sa.text("is_deleted = false AND zm_relevant = true")
    )

    # ==========================================================================
    # AUDIT LOG IMMUTABILITY (via Trigger)
    # ==========================================================================

    # Funktion die bei Update eine Exception wirft
    op.execute("""
        CREATE OR REPLACE FUNCTION prevent_audit_log_update()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'Audit log records are immutable and cannot be modified';
        END;
        $$ LANGUAGE plpgsql;
    """)

    # Trigger um Updates auf classification_audit_log zu verhindern
    op.execute("""
        DO $$ BEGIN
            CREATE TRIGGER tr_audit_log_immutable
            BEFORE UPDATE ON classification_audit_log
            FOR EACH ROW
            EXECUTE FUNCTION prevent_audit_log_update();
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)


def downgrade() -> None:
    # Trigger und Funktion entfernen
    op.execute("DROP TRIGGER IF EXISTS tr_audit_log_immutable ON classification_audit_log")
    op.execute("DROP FUNCTION IF EXISTS prevent_audit_log_update()")

    # Indexes entfernen
    op.drop_index('ix_classifications_zm_period', table_name='drop_shipment_classifications')
    op.drop_index('ix_classifications_not_deleted', table_name='drop_shipment_classifications')

    # Spalten entfernen
    op.drop_column('drop_shipment_classifications', 'deleted_by')
    op.drop_column('drop_shipment_classifications', 'deleted_at')
    op.drop_column('drop_shipment_classifications', 'is_deleted')

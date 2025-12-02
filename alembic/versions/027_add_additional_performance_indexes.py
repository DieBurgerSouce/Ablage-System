"""Add additional performance indexes for query optimization.

Revision ID: 027_add_additional_performance_indexes
Revises: 026_add_backup_notification_featureflag
Create Date: 2024-12-03

Performance-kritische Indexes für:
- Status + Soft-Delete Queries (aktive Dokumente)
- Embedding-basierte Suche (Modell + Timestamp)
- Owner-Date-Range-Queries (Benutzer-Dashboard, Reports)

Diese Indexes optimieren die häufigsten Query-Patterns
aus der Codebase-Analyse.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "027_add_additional_performance_indexes"
down_revision = "026_add_backup_notification_featureflag"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add additional performance indexes."""

    # =========================================================================
    # DOCUMENTS TABLE INDEXES - Additional
    # =========================================================================

    # 1. Status + Soft-Delete Filter
    # Optimiert: WHERE status = X AND deleted_at IS NULL
    # Häufig für Dashboard-Queries und aktive Dokument-Listen
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_documents_status_not_deleted
        ON documents (status, deleted_at)
        WHERE deleted_at IS NULL
    """)

    # 2. Embedding Model + Update Timestamp
    # Optimiert: Suche nach Dokumenten mit bestimmtem Embedding-Modell
    # und Sortierung nach Aktualisierungszeit
    op.create_index(
        "ix_documents_embedding_model_updated",
        "documents",
        ["embedding_model", "embedding_updated_at"],
        if_not_exists=True
    )

    # 3. Owner + Created Date Range
    # Optimiert: Benutzer-spezifische Zeitraum-Abfragen
    # Dashboard-Statistiken, Reports, GDPR-Exports
    op.create_index(
        "ix_documents_owner_created_range",
        "documents",
        ["owner_id", "created_at"],
        if_not_exists=True
    )


def downgrade() -> None:
    """Remove additional performance indexes."""

    op.drop_index(
        "ix_documents_owner_created_range",
        table_name="documents",
        if_exists=True
    )
    op.drop_index(
        "ix_documents_embedding_model_updated",
        table_name="documents",
        if_exists=True
    )
    op.execute("DROP INDEX IF EXISTS ix_documents_status_not_deleted")

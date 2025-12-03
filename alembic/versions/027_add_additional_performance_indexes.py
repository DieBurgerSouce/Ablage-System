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

HINWEIS: Diese Migration prüft Spalten-Existenz vor Index-Erstellung.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "027_add_additional_performance_indexes"
down_revision = "026_add_backup_notification_featureflag"
branch_labels = None
depends_on = None


def column_exists(conn, table_name: str, column_name: str) -> bool:
    """Prüft ob eine Spalte in einer Tabelle existiert."""
    result = conn.execute(sa.text("""
        SELECT EXISTS (
            SELECT FROM information_schema.columns
            WHERE table_name = :table_name AND column_name = :column_name
        )
    """), {"table_name": table_name, "column_name": column_name})
    return result.scalar()


def upgrade() -> None:
    """Add additional performance indexes."""
    conn = op.get_bind()

    # =========================================================================
    # DOCUMENTS TABLE INDEXES - Additional
    # =========================================================================

    # 1. Status + Soft-Delete Filter
    # Optimiert: WHERE status = X AND deleted_at IS NULL
    # Häufig für Dashboard-Queries und aktive Dokument-Listen
    if column_exists(conn, "documents", "status") and column_exists(conn, "documents", "deleted_at"):
        op.execute("""
            CREATE INDEX IF NOT EXISTS ix_documents_status_not_deleted
            ON documents (status, deleted_at)
            WHERE deleted_at IS NULL
        """)
    elif column_exists(conn, "documents", "status"):
        # Fallback: Nur Status-Index wenn deleted_at nicht existiert
        op.execute("""
            CREATE INDEX IF NOT EXISTS ix_documents_status_not_deleted
            ON documents (status)
        """)

    # 2. Embedding Model + Update Timestamp
    # Optimiert: Suche nach Dokumenten mit bestimmtem Embedding-Modell
    # und Sortierung nach Aktualisierungszeit
    if column_exists(conn, "documents", "embedding_model") and column_exists(conn, "documents", "embedding_updated_at"):
        op.execute("""
            CREATE INDEX IF NOT EXISTS ix_documents_embedding_model_updated
            ON documents (embedding_model, embedding_updated_at)
        """)

    # 3. Owner + Created Date Range
    # Optimiert: Benutzer-spezifische Zeitraum-Abfragen
    # Dashboard-Statistiken, Reports, GDPR-Exports
    if column_exists(conn, "documents", "owner_id") and column_exists(conn, "documents", "created_at"):
        op.execute("""
            CREATE INDEX IF NOT EXISTS ix_documents_owner_created_range
            ON documents (owner_id, created_at)
        """)


def downgrade() -> None:
    """Remove additional performance indexes."""

    op.execute("DROP INDEX IF EXISTS ix_documents_owner_created_range")
    op.execute("DROP INDEX IF EXISTS ix_documents_embedding_model_updated")
    op.execute("DROP INDEX IF EXISTS ix_documents_status_not_deleted")

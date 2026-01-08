"""Add quick classification fields to documents.

Revision ID: 039_add_quick_classification
Revises: 038_enhance_tags_for_admin_management
Create Date: 2024-12-13

Quick Classification ermoeglicht schnelle Dokumenten-Klassifizierung (2-5 Sekunden)
BEVOR das vollstaendige OCR laeuft. Dadurch kann der Tag (Eingangsrechnung/Ausgangsrechnung)
sofort in der Upload-Ansicht angezeigt werden.

Neue Felder:
- quick_classification_status: pending | processing | completed | failed
- quick_classification_result: JSONB mit direction, confidence, reason, tag_assigned
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "039"
down_revision = "038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add quick classification fields to documents table."""

    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # =========================================================================
    # ADD QUICK CLASSIFICATION STATUS
    # =========================================================================
    op.add_column(
        "documents",
        sa.Column(
            "quick_classification_status",
            sa.String(20),
            nullable=False,
            server_default="pending",
            comment="Status der schnellen Klassifizierung: pending, processing, completed, failed"
        )
    )

    # =========================================================================
    # ADD QUICK CLASSIFICATION RESULT (JSONB)
    # =========================================================================
    if is_postgres:
        op.add_column(
            "documents",
            sa.Column(
                "quick_classification_result",
                postgresql.JSONB(),
                nullable=True,
                comment="Ergebnis: {direction, confidence, reason, tag_assigned, user_overridden}"
            )
        )
    else:
        # SQLite fallback
        op.add_column(
            "documents",
            sa.Column(
                "quick_classification_result",
                sa.JSON(),
                nullable=True
            )
        )

    # =========================================================================
    # ADD INDEX FOR QUICK CLASSIFICATION STATUS
    # =========================================================================
    op.create_index(
        "ix_documents_quick_classification_status",
        "documents",
        ["quick_classification_status"]
    )


def downgrade() -> None:
    """Remove quick classification fields."""

    op.drop_index("ix_documents_quick_classification_status", table_name="documents")
    op.drop_column("documents", "quick_classification_result")
    op.drop_column("documents", "quick_classification_status")

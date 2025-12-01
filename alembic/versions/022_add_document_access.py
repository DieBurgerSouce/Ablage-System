"""Add document_access table for sharing.

Revision ID: 022_add_document_access
Revises: 021_add_rbac
Create Date: 2024-12-01

Ermöglicht:
- Dokumente mit anderen Benutzern teilen
- Verschiedene Zugriffsebenen (view, comment, edit, manage)
- Zeitlich begrenzte Shares
- Audit-Trail wer geteilt hat
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "022_add_document_access"
down_revision = "021_add_rbac"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create document_access table for document sharing."""

    # Create document_access table
    op.create_table(
        "document_access",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False
        ),
        sa.Column(
            "granted_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True
        ),
        sa.Column(
            "access_level",
            sa.String(20),
            nullable=False,
            server_default="view"
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("can_share", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("share_note", sa.String(500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False
        ),
    )

    # Indexes
    op.create_index(
        "ix_document_access_user_document",
        "document_access",
        ["user_id", "document_id"],
        unique=True
    )
    op.create_index(
        "ix_document_access_document_id",
        "document_access",
        ["document_id"]
    )
    op.create_index(
        "ix_document_access_user_id",
        "document_access",
        ["user_id"]
    )
    op.create_index(
        "ix_document_access_expires_at",
        "document_access",
        ["expires_at"]
    )

    # Add check constraint for access_level
    op.execute("""
        ALTER TABLE document_access
        ADD CONSTRAINT ck_document_access_level
        CHECK (access_level IN ('view', 'comment', 'edit', 'manage'))
    """)


def downgrade() -> None:
    """Remove document_access table."""

    # Remove check constraint
    op.execute("ALTER TABLE document_access DROP CONSTRAINT IF EXISTS ck_document_access_level")

    # Drop indexes
    op.drop_index("ix_document_access_expires_at", table_name="document_access")
    op.drop_index("ix_document_access_user_id", table_name="document_access")
    op.drop_index("ix_document_access_document_id", table_name="document_access")
    op.drop_index("ix_document_access_user_document", table_name="document_access")

    # Drop table
    op.drop_table("document_access")

"""add_mention_notifications

Revision ID: 227
Revises: 226
Create Date: 2026-02-15

Erstellt mention_notifications Tabelle fuer @mention-Benachrichtigungen
in Kommentaren und Antworten.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "227"
down_revision = "226"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mention_notifications",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "mentioned_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "mentioning_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_type", sa.String(50), nullable=False),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("is_read", sa.Boolean(), server_default="false"),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
    )

    op.create_index(
        "ix_mention_notif_company_id",
        "mention_notifications",
        ["company_id"],
    )
    op.create_index(
        "ix_mention_notif_mentioned_user",
        "mention_notifications",
        ["mentioned_user_id", "is_read"],
    )
    op.create_index(
        "ix_mention_notif_document_id",
        "mention_notifications",
        ["document_id"],
    )
    op.create_index(
        "ix_mention_notif_created_at",
        "mention_notifications",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_mention_notif_created_at", table_name="mention_notifications")
    op.drop_index("ix_mention_notif_document_id", table_name="mention_notifications")
    op.drop_index("ix_mention_notif_mentioned_user", table_name="mention_notifications")
    op.drop_index("ix_mention_notif_company_id", table_name="mention_notifications")
    op.drop_table("mention_notifications")

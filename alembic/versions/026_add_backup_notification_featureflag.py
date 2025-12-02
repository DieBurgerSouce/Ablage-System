"""Add BackupRecord, Notification, and FeatureFlag tables.

Revision ID: 026_add_backup_notification_featureflag
Revises: 025_add_rls_policies
Create Date: 2024-12-02

Neue Tabellen fuer:
- BackupRecord: Backup-Verlauf und -Tracking
- Notification: Benutzer-Benachrichtigungen (In-App und E-Mail)
- FeatureFlag: Feature Flags fuer A/B Testing und Rollouts
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON

# revision identifiers, used by Alembic.
revision = "026_add_backup_notification_featureflag"
down_revision = "025_add_rls_policies"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create backup_records, notifications, and feature_flags tables."""

    # =========================================================================
    # BACKUP_RECORDS TABLE
    # =========================================================================
    op.create_table(
        "backup_records",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("backup_type", sa.String(20), nullable=False, default="full"),
        sa.Column("status", sa.String(20), nullable=False, default="pending"),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("size_bytes", sa.BigInteger, nullable=True),
        sa.Column("storage_path", sa.String(500), nullable=True),
        sa.Column("remote_path", sa.String(500), nullable=True),
        sa.Column("checksum", sa.String(64), nullable=True),
        sa.Column("retention_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("backup_metadata", JSON, default=dict),
        sa.Column(
            "triggered_by_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Indexes fuer backup_records
    op.create_index(
        "ix_backup_records_type_status",
        "backup_records",
        ["backup_type", "status"]
    )
    op.create_index(
        "ix_backup_records_started_at",
        "backup_records",
        ["started_at"]
    )
    op.create_index(
        "ix_backup_records_retention",
        "backup_records",
        ["retention_until"]
    )

    # =========================================================================
    # NOTIFICATIONS TABLE
    # =========================================================================
    op.create_table(
        "notifications",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False
        ),
        sa.Column("notification_type", sa.String(30), nullable=False, default="info"),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("reference_type", sa.String(50), nullable=True),
        sa.Column("reference_id", UUID(as_uuid=True), nullable=True),
        sa.Column("read", sa.Boolean, default=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("email_sent", sa.Boolean, default=False),
        sa.Column("email_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("data", JSON, default=dict),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Indexes fuer notifications
    op.create_index(
        "ix_notifications_user_read",
        "notifications",
        ["user_id", "read"]
    )
    op.create_index(
        "ix_notifications_user_created",
        "notifications",
        ["user_id", "created_at"]
    )
    op.create_index(
        "ix_notifications_expires",
        "notifications",
        ["expires_at"]
    )

    # =========================================================================
    # FEATURE_FLAGS TABLE
    # =========================================================================
    op.create_table(
        "feature_flags",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("key", sa.String(100), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("enabled", sa.Boolean, default=False),
        sa.Column("rollout_percentage", sa.Integer, default=0),
        sa.Column("target_tiers", JSON, default=list),
        sa.Column("target_users", JSON, default=list),
        sa.Column("variants", JSON, default=dict),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("config", JSON, default=dict),
        sa.Column(
            "created_by_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True
        ),
        sa.Column(
            "updated_by_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Indexes fuer feature_flags
    op.create_index(
        "ix_feature_flags_key",
        "feature_flags",
        ["key"]
    )
    op.create_index(
        "ix_feature_flags_enabled",
        "feature_flags",
        ["enabled"]
    )


def downgrade() -> None:
    """Drop backup_records, notifications, and feature_flags tables."""

    # Drop feature_flags
    op.drop_index("ix_feature_flags_enabled", table_name="feature_flags")
    op.drop_index("ix_feature_flags_key", table_name="feature_flags")
    op.drop_table("feature_flags")

    # Drop notifications
    op.drop_index("ix_notifications_expires", table_name="notifications")
    op.drop_index("ix_notifications_user_created", table_name="notifications")
    op.drop_index("ix_notifications_user_read", table_name="notifications")
    op.drop_table("notifications")

    # Drop backup_records
    op.drop_index("ix_backup_records_retention", table_name="backup_records")
    op.drop_index("ix_backup_records_started_at", table_name="backup_records")
    op.drop_index("ix_backup_records_type_status", table_name="backup_records")
    op.drop_table("backup_records")

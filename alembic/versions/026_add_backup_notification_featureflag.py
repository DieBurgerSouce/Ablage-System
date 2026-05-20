"""Add BackupRecord, Notification enhancements, and FeatureFlag tables.

Revision ID: 026_add_backup_notification_featureflag
Revises: 025_add_rls_policies
Create Date: 2024-12-02

Neue Tabellen fuer:
- BackupRecord: Backup-Verlauf und -Tracking
- FeatureFlag: Feature Flags fuer A/B Testing und Rollouts

Erweiterungen:
- Notifications: Zusaetzliche Spalten (email_sent, data, expires_at)

NOTE: notifications table wird bereits in Migration 021 erstellt.
Diese Migration fuegt nur zusaetzliche Spalten hinzu.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON

# revision identifiers, used by Alembic.
revision = "026"
down_revision = "025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create backup_records, feature_flags tables and enhance notifications."""

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
    # NOTIFICATIONS TABLE - Add missing columns (table created in migration 021)
    # =========================================================================
    # Fuege zusaetzliche Spalten hinzu, die in 021 fehlen
    op.execute("""
        DO $$
        BEGIN
            -- notification_type (maps to 'type' from 021, add if needed as alias)
            IF NOT EXISTS (SELECT FROM information_schema.columns WHERE table_name = 'notifications' AND column_name = 'notification_type') THEN
                ALTER TABLE notifications ADD COLUMN notification_type VARCHAR(30);
                UPDATE notifications SET notification_type = type WHERE notification_type IS NULL;
            END IF;

            -- reference_type (maps to 'entity_type' from 021)
            IF NOT EXISTS (SELECT FROM information_schema.columns WHERE table_name = 'notifications' AND column_name = 'reference_type') THEN
                ALTER TABLE notifications ADD COLUMN reference_type VARCHAR(50);
                UPDATE notifications SET reference_type = entity_type WHERE reference_type IS NULL AND entity_type IS NOT NULL;
            END IF;

            -- reference_id (maps to 'entity_id' from 021)
            IF NOT EXISTS (SELECT FROM information_schema.columns WHERE table_name = 'notifications' AND column_name = 'reference_id') THEN
                ALTER TABLE notifications ADD COLUMN reference_id UUID;
                UPDATE notifications SET reference_id = entity_id WHERE reference_id IS NULL AND entity_id IS NOT NULL;
            END IF;

            -- email_sent (new column)
            IF NOT EXISTS (SELECT FROM information_schema.columns WHERE table_name = 'notifications' AND column_name = 'email_sent') THEN
                ALTER TABLE notifications ADD COLUMN email_sent BOOLEAN DEFAULT false;
            END IF;

            -- email_sent_at (new column)
            IF NOT EXISTS (SELECT FROM information_schema.columns WHERE table_name = 'notifications' AND column_name = 'email_sent_at') THEN
                ALTER TABLE notifications ADD COLUMN email_sent_at TIMESTAMP WITH TIME ZONE;
            END IF;

            -- data (new column)
            IF NOT EXISTS (SELECT FROM information_schema.columns WHERE table_name = 'notifications' AND column_name = 'data') THEN
                ALTER TABLE notifications ADD COLUMN data JSON;
            END IF;

            -- expires_at (new column)
            IF NOT EXISTS (SELECT FROM information_schema.columns WHERE table_name = 'notifications' AND column_name = 'expires_at') THEN
                ALTER TABLE notifications ADD COLUMN expires_at TIMESTAMP WITH TIME ZONE;
            END IF;
        END $$;
    """)

    # Create indexes if not exist
    op.execute("CREATE INDEX IF NOT EXISTS ix_notifications_user_created ON notifications (user_id, created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_notifications_expires ON notifications (expires_at)")

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
    """Drop backup_records, feature_flags tables and notification enhancements."""

    # Drop feature_flags
    op.drop_index("ix_feature_flags_enabled", table_name="feature_flags")
    op.drop_index("ix_feature_flags_key", table_name="feature_flags")
    op.drop_table("feature_flags")

    # Drop notifications enhancements (table itself created in migration 021)
    op.execute("DROP INDEX IF EXISTS ix_notifications_expires")
    op.execute("DROP INDEX IF EXISTS ix_notifications_user_created")
    op.execute("""
        DO $$
        BEGIN
            -- Drop added columns (keep table, created in 021)
            IF EXISTS (SELECT FROM information_schema.columns WHERE table_name = 'notifications' AND column_name = 'expires_at') THEN
                ALTER TABLE notifications DROP COLUMN expires_at;
            END IF;
            IF EXISTS (SELECT FROM information_schema.columns WHERE table_name = 'notifications' AND column_name = 'data') THEN
                ALTER TABLE notifications DROP COLUMN data;
            END IF;
            IF EXISTS (SELECT FROM information_schema.columns WHERE table_name = 'notifications' AND column_name = 'email_sent_at') THEN
                ALTER TABLE notifications DROP COLUMN email_sent_at;
            END IF;
            IF EXISTS (SELECT FROM information_schema.columns WHERE table_name = 'notifications' AND column_name = 'email_sent') THEN
                ALTER TABLE notifications DROP COLUMN email_sent;
            END IF;
            IF EXISTS (SELECT FROM information_schema.columns WHERE table_name = 'notifications' AND column_name = 'reference_id') THEN
                ALTER TABLE notifications DROP COLUMN reference_id;
            END IF;
            IF EXISTS (SELECT FROM information_schema.columns WHERE table_name = 'notifications' AND column_name = 'reference_type') THEN
                ALTER TABLE notifications DROP COLUMN reference_type;
            END IF;
            IF EXISTS (SELECT FROM information_schema.columns WHERE table_name = 'notifications' AND column_name = 'notification_type') THEN
                ALTER TABLE notifications DROP COLUMN notification_type;
            END IF;
        END $$;
    """)

    # Drop backup_records
    op.drop_index("ix_backup_records_retention", table_name="backup_records")
    op.drop_index("ix_backup_records_started_at", table_name="backup_records")
    op.drop_index("ix_backup_records_type_status", table_name="backup_records")
    op.drop_table("backup_records")

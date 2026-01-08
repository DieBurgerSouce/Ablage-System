"""Add collaboration models (comments, activities, notifications)

Revision ID: 070_add_collaboration
Revises: 069_add_privat_document_soft_delete_fields
Create Date: 2024-12-31

Adds:
- document_comments: Kommentare zu Dokumenten
- document_activities: Aktivitaetsverlauf
- user_notifications: Benutzer-Benachrichtigungen
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "070"
down_revision = "069"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create collaboration tables (comments, activities, notifications).

    IDEMPOTENT: Prueft ob Tabellen existieren bevor sie erstellt werden.
    """
    op.execute("""
        DO $$
        BEGIN
            -- ==================== DOCUMENT COMMENTS ====================
            IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'document_comments') THEN
                CREATE TABLE document_comments (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    parent_id UUID REFERENCES document_comments(id) ON DELETE CASCADE,
                    content TEXT NOT NULL,
                    mentions JSONB DEFAULT '[]',
                    reactions JSONB DEFAULT '[]',
                    is_edited BOOLEAN DEFAULT false,
                    is_deleted BOOLEAN DEFAULT false,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );
            END IF;

            -- Indices fuer document_comments
            CREATE INDEX IF NOT EXISTS ix_doc_comment_document ON document_comments(document_id);
            CREATE INDEX IF NOT EXISTS ix_doc_comment_user ON document_comments(user_id);
            CREATE INDEX IF NOT EXISTS ix_doc_comment_parent ON document_comments(parent_id);
            CREATE INDEX IF NOT EXISTS ix_doc_comment_created ON document_comments(created_at);

            -- ==================== DOCUMENT ACTIVITIES ====================
            IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'document_activities') THEN
                CREATE TABLE document_activities (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
                    activity_type VARCHAR(50) NOT NULL,
                    description VARCHAR(500) NOT NULL,
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
            END IF;

            -- Indices fuer document_activities
            CREATE INDEX IF NOT EXISTS ix_doc_activity_document ON document_activities(document_id);
            CREATE INDEX IF NOT EXISTS ix_doc_activity_user ON document_activities(user_id);
            CREATE INDEX IF NOT EXISTS ix_doc_activity_type ON document_activities(activity_type);
            CREATE INDEX IF NOT EXISTS ix_doc_activity_created ON document_activities(created_at);

            -- ==================== USER NOTIFICATIONS ====================
            IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'user_notifications') THEN
                CREATE TABLE user_notifications (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    from_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
                    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
                    notification_type VARCHAR(50) NOT NULL,
                    title VARCHAR(200) NOT NULL,
                    message TEXT NOT NULL,
                    action_url VARCHAR(500),
                    is_read BOOLEAN DEFAULT false,
                    read_at TIMESTAMPTZ,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
            END IF;

            -- Indices fuer user_notifications
            CREATE INDEX IF NOT EXISTS ix_notification_user ON user_notifications(user_id);
            CREATE INDEX IF NOT EXISTS ix_notification_unread ON user_notifications(user_id, is_read);
            CREATE INDEX IF NOT EXISTS ix_notification_created ON user_notifications(created_at);

        END $$;
    """)


def downgrade() -> None:
    """Remove collaboration tables.

    IDEMPOTENT: Prueft ob Tabellen existieren bevor sie gedroppt werden.
    """
    op.execute("""
        DO $$
        BEGIN
            -- user_notifications Indices und Tabelle
            DROP INDEX IF EXISTS ix_notification_created;
            DROP INDEX IF EXISTS ix_notification_unread;
            DROP INDEX IF EXISTS ix_notification_user;
            DROP TABLE IF EXISTS user_notifications CASCADE;

            -- document_activities Indices und Tabelle
            DROP INDEX IF EXISTS ix_doc_activity_created;
            DROP INDEX IF EXISTS ix_doc_activity_type;
            DROP INDEX IF EXISTS ix_doc_activity_user;
            DROP INDEX IF EXISTS ix_doc_activity_document;
            DROP TABLE IF EXISTS document_activities CASCADE;

            -- document_comments Indices und Tabelle
            DROP INDEX IF EXISTS ix_doc_comment_created;
            DROP INDEX IF EXISTS ix_doc_comment_parent;
            DROP INDEX IF EXISTS ix_doc_comment_user;
            DROP INDEX IF EXISTS ix_doc_comment_document;
            DROP TABLE IF EXISTS document_comments CASCADE;
        END $$;
    """)

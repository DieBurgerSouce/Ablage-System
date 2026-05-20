"""Add user preferences column.

Revision ID: 053_add_user_preferences
Revises: 052_add_chat_session_sharing
Create Date: 2024-12-18

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "053"
down_revision = "052"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add preferences column to users table
    op.add_column(
        'users',
        sa.Column('preferences', postgresql.JSONB(astext_type=sa.Text()), nullable=True)
    )


def downgrade() -> None:
    # Remove preferences column from users table
    op.drop_column('users', 'preferences')

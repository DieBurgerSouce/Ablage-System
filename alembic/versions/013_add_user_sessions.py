"""Add UserSession table for session tracking.

Revision ID: 013_add_user_sessions
Revises: 012_add_data_export_table
Create Date: 2024-11-30

Implements: Session Management for Security - tracks active sessions per user.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers
revision = '013_add_user_sessions'
down_revision = '012_add_data_export_table'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create user_sessions table for session tracking."""
    op.create_table(
        'user_sessions',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column(
            'user_id',
            UUID(as_uuid=True),
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=False
        ),
        sa.Column('token_jti', sa.String(64), unique=True, nullable=False),
        sa.Column('device_name', sa.String(100), nullable=True),
        sa.Column('device_type', sa.String(50), nullable=True),
        sa.Column('ip_address', sa.String(45), nullable=False),
        sa.Column('user_agent', sa.String(500), nullable=True),
        sa.Column('location', sa.String(100), nullable=True),
        sa.Column(
            'last_activity_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now()
        ),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now()
        ),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('is_current', sa.Boolean(), default=False),
        sa.Column('revoked', sa.Boolean(), default=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    )

    # Indexes for efficient queries
    op.create_index(
        'ix_user_sessions_user_id',
        'user_sessions',
        ['user_id']
    )
    op.create_index(
        'ix_user_sessions_token_jti',
        'user_sessions',
        ['token_jti']
    )
    op.create_index(
        'ix_user_sessions_expires_at',
        'user_sessions',
        ['expires_at']
    )
    # Partial index for active sessions
    op.create_index(
        'ix_user_sessions_active',
        'user_sessions',
        ['user_id', 'revoked'],
        postgresql_where=sa.text('revoked = false')
    )


def downgrade() -> None:
    """Remove user_sessions table."""
    op.drop_index('ix_user_sessions_active', table_name='user_sessions')
    op.drop_index('ix_user_sessions_expires_at', table_name='user_sessions')
    op.drop_index('ix_user_sessions_token_jti', table_name='user_sessions')
    op.drop_index('ix_user_sessions_user_id', table_name='user_sessions')
    op.drop_table('user_sessions')

"""Add email verification fields to users table.

Revision ID: 014_add_email_verification
Revises: 013_add_user_sessions
Create Date: 2024-11-30

Implements: Email verification for security compliance.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = '014_add_email_verification'
down_revision = '013_add_user_sessions'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add email verification fields to users table."""
    # Add verification status
    op.add_column(
        'users',
        sa.Column('email_verified', sa.Boolean(), server_default='false', nullable=False)
    )
    op.add_column(
        'users',
        sa.Column('email_verified_at', sa.DateTime(timezone=True), nullable=True)
    )

    # Create email_verification_tokens table
    op.create_table(
        'email_verification_tokens',
        sa.Column('id', sa.UUID(), primary_key=True),
        sa.Column(
            'user_id',
            sa.UUID(),
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=False
        ),
        sa.Column('token_hash', sa.String(128), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('token_type', sa.String(20), nullable=False),  # 'verification' or 'email_change'
        sa.Column('new_email', sa.String(255), nullable=True),  # For email change requests
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now()
        ),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ip_address', sa.String(45), nullable=True),
    )

    # Indexes
    op.create_index(
        'ix_email_verification_tokens_user_id',
        'email_verification_tokens',
        ['user_id']
    )
    op.create_index(
        'ix_email_verification_tokens_token_hash',
        'email_verification_tokens',
        ['token_hash']
    )
    op.create_index(
        'ix_email_verification_tokens_expires_at',
        'email_verification_tokens',
        ['expires_at']
    )


def downgrade() -> None:
    """Remove email verification fields."""
    op.drop_index('ix_email_verification_tokens_expires_at', table_name='email_verification_tokens')
    op.drop_index('ix_email_verification_tokens_token_hash', table_name='email_verification_tokens')
    op.drop_index('ix_email_verification_tokens_user_id', table_name='email_verification_tokens')
    op.drop_table('email_verification_tokens')
    op.drop_column('users', 'email_verified_at')
    op.drop_column('users', 'email_verified')

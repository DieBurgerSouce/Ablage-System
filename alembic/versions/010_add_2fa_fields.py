"""Add Two-Factor Authentication (2FA) fields to users table

Revision ID: 010
Revises: 009
Create Date: 2025-11-30

Adds TOTP-based 2FA support with:
- totp_secret: Secret key for TOTP generation (encrypted in DB)
- totp_enabled: Flag if 2FA is active
- totp_backup_codes: JSON array of hashed backup codes
- totp_setup_at: Timestamp when 2FA was enabled

SECURITY: Diese Migration fuegt kritische Sicherheitsfelder hinzu.
Nach Migration sollten alle bestehenden User totp_enabled=False haben.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '010'
down_revision: Union[str, None] = '009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # TOTP Secret - Base32 encoded, max 32 chars
    # SECURITY: Should be encrypted at application level
    op.add_column(
        'users',
        sa.Column('totp_secret', sa.String(32), nullable=True)
    )

    # 2FA enabled flag - default False for existing users
    op.add_column(
        'users',
        sa.Column('totp_enabled', sa.Boolean(), nullable=False, server_default='false')
    )

    # Backup codes - JSON array of SHA-256 hashed codes
    op.add_column(
        'users',
        sa.Column('totp_backup_codes', sa.JSON(), nullable=True)
    )

    # Timestamp when 2FA was set up
    op.add_column(
        'users',
        sa.Column('totp_setup_at', sa.DateTime(timezone=True), nullable=True)
    )

    # Index for quick lookup of 2FA-enabled users (e.g., for security reports)
    op.create_index(
        'ix_users_totp_enabled',
        'users',
        ['totp_enabled'],
        postgresql_where=sa.text('totp_enabled = true')
    )


def downgrade() -> None:
    # Drop index first
    op.drop_index('ix_users_totp_enabled', table_name='users')

    # Drop columns in reverse order
    op.drop_column('users', 'totp_setup_at')
    op.drop_column('users', 'totp_backup_codes')
    op.drop_column('users', 'totp_enabled')
    op.drop_column('users', 'totp_secret')

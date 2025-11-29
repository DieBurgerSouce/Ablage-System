"""Add admin console models

Revision ID: 008
Revises: 007
Create Date: 2025-11-29

Adds admin console tables and extends User model for:
- AdminAction: Audit trail for admin operations
- RateLimitOverride: Custom rate limits per user
- User model extensions: tier, rate limits, deactivation tracking
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '008'
down_revision: Union[str, None] = '007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ========== Extend users table with admin console fields ==========

    # Tier and rate limit management
    op.add_column('users', sa.Column('tier', sa.String(20), server_default='free'))
    op.add_column('users', sa.Column('rate_limit_hourly', sa.Integer, nullable=True))
    op.add_column('users', sa.Column('rate_limit_daily', sa.Integer, nullable=True))

    # User management fields
    op.add_column('users', sa.Column('last_activity_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('password_reset_required', sa.Boolean, server_default='false'))
    op.add_column('users', sa.Column('deactivated_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('deactivated_by_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('users', sa.Column('notes', sa.Text, nullable=True))

    # Add foreign key for deactivated_by
    op.create_foreign_key(
        'fk_users_deactivated_by',
        'users', 'users',
        ['deactivated_by_id'], ['id'],
        ondelete='SET NULL'
    )

    # Add index for tier queries
    op.create_index('ix_users_tier', 'users', ['tier'])
    op.create_index('ix_users_is_active', 'users', ['is_active'])

    # ========== Create admin_actions table ==========
    op.create_table(
        'admin_actions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('admin_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('target_user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),

        # Action details
        sa.Column('action', sa.String(100), nullable=False),
        sa.Column('action_details', postgresql.JSONB, server_default='{}'),

        # Request context
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('user_agent', sa.String(255), nullable=True),

        # Timestamp
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('NOW()')),
    )

    # Indexes for admin_actions
    op.create_index('ix_admin_actions_admin_id', 'admin_actions', ['admin_id'])
    op.create_index('ix_admin_actions_target_user_id', 'admin_actions', ['target_user_id'])
    op.create_index('ix_admin_actions_created_at', 'admin_actions', ['created_at'])
    op.create_index('ix_admin_actions_action', 'admin_actions', ['action'])

    # Compound index for admin activity reports
    op.create_index(
        'ix_admin_actions_admin_time',
        'admin_actions',
        ['admin_id', 'created_at']
    )

    # ========== Create rate_limit_overrides table ==========
    op.create_table(
        'rate_limit_overrides',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), unique=True, nullable=False),

        # Rate limit values
        sa.Column('ocr_hourly', sa.Integer, nullable=True),
        sa.Column('ocr_daily', sa.Integer, nullable=True),
        sa.Column('batch_hourly', sa.Integer, nullable=True),
        sa.Column('api_per_minute', sa.Integer, nullable=True),

        # Validity period
        sa.Column('valid_from', sa.DateTime(timezone=True),
                  server_default=sa.text('NOW()')),
        sa.Column('valid_until', sa.DateTime(timezone=True), nullable=True),

        # Audit trail
        sa.Column('created_by_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('NOW()')),
        sa.Column('reason', sa.String(500), nullable=True),
    )

    # Indexes for rate_limit_overrides
    op.create_index('ix_rate_limit_overrides_user_id', 'rate_limit_overrides', ['user_id'])
    op.create_index('ix_rate_limit_overrides_valid_until', 'rate_limit_overrides', ['valid_until'])

    # Partial index for active overrides (no expiration or future expiration)
    op.execute("""
        CREATE INDEX ix_rate_limit_overrides_active
        ON rate_limit_overrides (user_id)
        WHERE valid_until IS NULL OR valid_until > NOW();
    """)

    # ========== Create view for effective rate limits ==========
    op.execute("""
        CREATE OR REPLACE VIEW user_effective_rate_limits AS
        SELECT
            u.id as user_id,
            u.email,
            u.tier,
            -- Effective OCR hourly limit (override > user custom > tier default)
            COALESCE(
                rlo.ocr_hourly,
                u.rate_limit_hourly,
                CASE u.tier
                    WHEN 'admin' THEN 10000
                    WHEN 'premium' THEN 100
                    ELSE 10
                END
            ) as effective_ocr_hourly,
            -- Effective OCR daily limit
            COALESCE(
                rlo.ocr_daily,
                u.rate_limit_daily,
                CASE u.tier
                    WHEN 'admin' THEN 100000
                    WHEN 'premium' THEN 1000
                    ELSE 50
                END
            ) as effective_ocr_daily,
            -- Effective batch hourly limit
            COALESCE(
                rlo.batch_hourly,
                CASE u.tier
                    WHEN 'admin' THEN 1000
                    WHEN 'premium' THEN 50
                    ELSE 5
                END
            ) as effective_batch_hourly,
            -- Effective API per minute limit
            COALESCE(
                rlo.api_per_minute,
                CASE u.tier
                    WHEN 'admin' THEN 1000
                    WHEN 'premium' THEN 100
                    ELSE 20
                END
            ) as effective_api_per_minute,
            -- Override metadata
            rlo.id IS NOT NULL as has_override,
            rlo.valid_until as override_valid_until,
            rlo.reason as override_reason
        FROM users u
        LEFT JOIN rate_limit_overrides rlo
            ON u.id = rlo.user_id
            AND (rlo.valid_until IS NULL OR rlo.valid_until > NOW());
    """)


def downgrade() -> None:
    # ========== Drop view ==========
    op.execute("DROP VIEW IF EXISTS user_effective_rate_limits;")

    # ========== Drop rate_limit_overrides ==========
    op.execute("DROP INDEX IF EXISTS ix_rate_limit_overrides_active;")
    op.drop_index('ix_rate_limit_overrides_valid_until')
    op.drop_index('ix_rate_limit_overrides_user_id')
    op.drop_table('rate_limit_overrides')

    # ========== Drop admin_actions ==========
    op.drop_index('ix_admin_actions_admin_time')
    op.drop_index('ix_admin_actions_action')
    op.drop_index('ix_admin_actions_created_at')
    op.drop_index('ix_admin_actions_target_user_id')
    op.drop_index('ix_admin_actions_admin_id')
    op.drop_table('admin_actions')

    # ========== Remove user columns ==========
    op.drop_index('ix_users_is_active')
    op.drop_index('ix_users_tier')
    op.drop_constraint('fk_users_deactivated_by', 'users', type_='foreignkey')
    op.drop_column('users', 'notes')
    op.drop_column('users', 'deactivated_by_id')
    op.drop_column('users', 'deactivated_at')
    op.drop_column('users', 'password_reset_required')
    op.drop_column('users', 'last_activity_at')
    op.drop_column('users', 'rate_limit_daily')
    op.drop_column('users', 'rate_limit_hourly')
    op.drop_column('users', 'tier')

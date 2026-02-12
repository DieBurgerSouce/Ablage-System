"""Add calendar sync fields to CompanySettings

Revision ID: 214_add_calendar_sync_fields
Revises: 213
Create Date: 2026-02-11

Adds calendar synchronization fields to CompanySettings:
- calendar_sync: Sync configuration (provider, URL, categories)
- calendar_oauth_tokens: Encrypted OAuth tokens per provider
- calendar_sync_state: Sync state mapping {uid: external_event_id}
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '214_add_calendar_sync_fields'
down_revision: str = '213'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add calendar sync fields to company_settings."""
    # Add calendar_sync column
    op.add_column(
        'company_settings',
        sa.Column(
            'calendar_sync',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment='Sync-Konfiguration (Provider, URL, Kategorien)'
        )
    )

    # Add calendar_oauth_tokens column
    op.add_column(
        'company_settings',
        sa.Column(
            'calendar_oauth_tokens',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment='Verschlüsselte OAuth-Tokens nach Provider'
        )
    )

    # Add calendar_sync_state column
    op.add_column(
        'company_settings',
        sa.Column(
            'calendar_sync_state',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment='Sync-State Mapping {uid: external_event_id}'
        )
    )


def downgrade() -> None:
    """Remove calendar sync fields from company_settings."""
    op.drop_column('company_settings', 'calendar_sync_state')
    op.drop_column('company_settings', 'calendar_oauth_tokens')
    op.drop_column('company_settings', 'calendar_sync')

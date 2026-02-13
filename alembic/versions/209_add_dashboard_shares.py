"""Add Dashboard Shares and Audit.

Revision ID: 209_add_dashboard_shares
Revises: 208_add_notification_templates
Create Date: 2026-02-08

Features:
- dashboard_shares table for persistent dashboard sharing
- dashboard_share_audits table for complete audit trail
- Support for view/edit permissions
- Optional expiry dates
- Soft-delete via is_active flag
- Unique constraint on (dashboard_id, shared_with_user_id)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '209_add_dashboard_shares'
down_revision: str = '208_add_notification_templates'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(conn: sa.Connection, tablename: str) -> bool:
    result = conn.execute(sa.text(
        "SELECT 1 FROM pg_tables WHERE schemaname='public' AND tablename=:t"
    ), {"t": tablename})
    return result.fetchone() is not None


def upgrade() -> None:
    """Add dashboard_shares and dashboard_share_audits tables."""
    conn = op.get_bind()

    if not _table_exists(conn, 'dashboard_shares'):
        op.create_table(
            'dashboard_shares',
            sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, comment='Eindeutige ID der Freigabe'),
            sa.Column('dashboard_id', postgresql.UUID(as_uuid=True), nullable=False, comment='ID des geteilten Dashboards (user_dashboards.id)'),
            sa.Column('shared_with_user_id', postgresql.UUID(as_uuid=True), nullable=False, comment='Benutzer mit dem das Dashboard geteilt wurde'),
            sa.Column('shared_by_user_id', postgresql.UUID(as_uuid=True), nullable=False, comment='Benutzer der das Dashboard geteilt hat'),
            sa.Column('permission', sa.String(length=10), nullable=False, server_default='view', comment='Berechtigungsstufe: view oder edit'),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true', comment='Ist die Freigabe aktiv? (Soft Delete)'),
            sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True, comment='Optional: Ablaufdatum der Freigabe'),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()'), comment='Zeitpunkt der Freigabe'),
            sa.ForeignKeyConstraint(['shared_by_user_id'], ['users.id'], ondelete='RESTRICT'),
            sa.ForeignKeyConstraint(['shared_with_user_id'], ['users.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('dashboard_id', 'shared_with_user_id', name='uq_dashboard_share_user'),
        )
        op.create_index('ix_dashboard_shares_dashboard_id', 'dashboard_shares', ['dashboard_id'])
        op.create_index('ix_dashboard_shares_shared_with_user_id', 'dashboard_shares', ['shared_with_user_id'])
        op.create_index('ix_dashboard_shares_active', 'dashboard_shares', ['dashboard_id', 'is_active'])
        op.create_index('ix_dashboard_shares_expires', 'dashboard_shares', ['expires_at'])

    if not _table_exists(conn, 'dashboard_share_audits'):
        op.create_table(
            'dashboard_share_audits',
            sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, comment='Eindeutige Audit-ID'),
            sa.Column('dashboard_share_id', postgresql.UUID(as_uuid=True), nullable=True, comment='Referenz zur Freigabe (kann NULL sein bei Loeschung)'),
            sa.Column('dashboard_id', postgresql.UUID(as_uuid=True), nullable=False, comment='Dashboard-ID (immer gesetzt)'),
            sa.Column('action', sa.String(length=30), nullable=False, comment='Aktion: shared, unshared, permission_changed'),
            sa.Column('performed_by_id', postgresql.UUID(as_uuid=True), nullable=False, comment='Benutzer der die Aktion durchgefuehrt hat'),
            sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='Zusaetzliche Details zur Aktion (alte/neue Werte, etc.)'),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()'), comment='Zeitpunkt der Aktion'),
            sa.ForeignKeyConstraint(['dashboard_share_id'], ['dashboard_shares.id'], ondelete='SET NULL'),
            sa.ForeignKeyConstraint(['performed_by_id'], ['users.id'], ondelete='RESTRICT'),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index('ix_dashboard_share_audits_dashboard', 'dashboard_share_audits', ['dashboard_id'])
        op.create_index('ix_dashboard_share_audits_action', 'dashboard_share_audits', ['action'])
        op.create_index('ix_dashboard_share_audits_created', 'dashboard_share_audits', ['created_at'])


def downgrade() -> None:
    """Remove dashboard_shares and dashboard_share_audits tables."""
    op.drop_index('ix_dashboard_share_audits_created', table_name='dashboard_share_audits')
    op.drop_index('ix_dashboard_share_audits_action', table_name='dashboard_share_audits')
    op.drop_index('ix_dashboard_share_audits_dashboard', table_name='dashboard_share_audits')
    op.drop_table('dashboard_share_audits')

    op.drop_index('ix_dashboard_shares_expires', table_name='dashboard_shares')
    op.drop_index('ix_dashboard_shares_active', table_name='dashboard_shares')
    op.drop_index('ix_dashboard_shares_shared_with_user_id', table_name='dashboard_shares')
    op.drop_index('ix_dashboard_shares_dashboard_id', table_name='dashboard_shares')
    op.drop_table('dashboard_shares')

"""Add Job Queue Management Permissions

Revision ID: 067_add_job_queue_permissions
Revises: 066_fix_search_analytics_query
Create Date: 2025-12-30

Neue Berechtigungen fuer Enterprise Job Queue Management:
- job_queue:read - Queue-Status und Jobs anzeigen
- job_queue:manage - Jobs verwalten (cancel, retry, pause, resume, priority)
- job_queue:clear - Queues leeren (kritische Operation)
- job_queue:force_kill - Force Kill von Jobs (kritische Operation)

Zusaetzlich: User Settings Erweiterung fuer Notification Preferences
"""
from typing import Sequence, Union
import uuid

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "067"
down_revision: Union[str, None] = "066"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Fuege Job Queue Permissions hinzu und erweitere User Settings.
    """
    # ==================== JOB QUEUE PERMISSIONS ====================
    permissions_table = sa.table(
        'permissions',
        sa.column('id', postgresql.UUID),
        sa.column('name', sa.String),
        sa.column('description', sa.String),
        sa.column('resource_type', sa.String),
        sa.column('action', sa.String),
        sa.column('is_system', sa.Boolean),
    )

    # Neue Job Queue Permissions
    job_queue_permissions = [
        {
            'id': str(uuid.uuid4()),
            'name': 'job_queue:read',
            'description': 'Job-Queue-Status und Jobs anzeigen',
            'resource_type': 'job_queue',
            'action': 'read',
            'is_system': True
        },
        {
            'id': str(uuid.uuid4()),
            'name': 'job_queue:manage',
            'description': 'Jobs verwalten (Abbrechen, Wiederholen, Pausieren, Fortsetzen, Prioritaet)',
            'resource_type': 'job_queue',
            'action': 'manage',
            'is_system': True
        },
        {
            'id': str(uuid.uuid4()),
            'name': 'job_queue:clear',
            'description': 'Queues leeren - Kritische Operation mit Bestaetigung',
            'resource_type': 'job_queue',
            'action': 'clear',
            'is_system': True
        },
        {
            'id': str(uuid.uuid4()),
            'name': 'job_queue:force_kill',
            'description': 'Force Kill von Jobs - Kritische Operation',
            'resource_type': 'job_queue',
            'action': 'force_kill',
            'is_system': True
        },
    ]

    # Permissions einfuegen
    permission_ids = {}
    for perm in job_queue_permissions:
        permission_ids[perm['name']] = perm['id']
        op.execute(
            permissions_table.insert().values(**perm)
        )

    # ==================== ROLE-PERMISSION ZUWEISUNGEN ====================
    # Hole existierende Rolle IDs
    conn = op.get_bind()

    # Admin-Rolle
    admin_result = conn.execute(
        sa.text("SELECT id FROM roles WHERE name = 'admin'")
    ).fetchone()

    # Manager-Rolle
    manager_result = conn.execute(
        sa.text("SELECT id FROM roles WHERE name = 'manager'")
    ).fetchone()

    # Analyst-Rolle
    analyst_result = conn.execute(
        sa.text("SELECT id FROM roles WHERE name = 'analyst'")
    ).fetchone()

    role_permissions_table = sa.table(
        'role_permissions',
        sa.column('role_id', postgresql.UUID),
        sa.column('permission_id', postgresql.UUID),
    )

    # Admin: ALLE Job Queue Permissions
    if admin_result:
        admin_id = str(admin_result[0])
        for perm_name, perm_id in permission_ids.items():
            op.execute(
                role_permissions_table.insert().values(
                    role_id=admin_id,
                    permission_id=perm_id
                )
            )

    # Manager: read und manage (NICHT clear/force_kill - zu kritisch)
    if manager_result:
        manager_id = str(manager_result[0])
        manager_perms = ['job_queue:read', 'job_queue:manage']
        for perm_name in manager_perms:
            if perm_name in permission_ids:
                op.execute(
                    role_permissions_table.insert().values(
                        role_id=manager_id,
                        permission_id=permission_ids[perm_name]
                    )
                )

    # Analyst: nur read
    if analyst_result:
        analyst_id = str(analyst_result[0])
        analyst_perms = ['job_queue:read']
        for perm_name in analyst_perms:
            if perm_name in permission_ids:
                op.execute(
                    role_permissions_table.insert().values(
                        role_id=analyst_id,
                        permission_id=permission_ids[perm_name]
                    )
                )

    # ==================== USER NOTIFICATION SETTINGS ====================
    # Fuege JSONB-Spalte fuer Job Queue Notification Preferences hinzu
    # Conditional: Nur wenn user_preferences Tabelle existiert
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'user_preferences') THEN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'user_preferences' AND column_name = 'job_queue_notifications'
                ) THEN
                    ALTER TABLE user_preferences ADD COLUMN job_queue_notifications JSONB
                    DEFAULT '{"enabled": true, "on_completion": true, "on_failure": true, "on_queue_full": false}';
                    COMMENT ON COLUMN user_preferences.job_queue_notifications IS 'Notification-Einstellungen fuer Job Queue Events';
                END IF;
            END IF;
        END $$;
    """)


def downgrade() -> None:
    """
    Entferne Job Queue Permissions und User Settings.
    """
    conn = op.get_bind()

    # Entferne Notification Settings Spalte (conditional)
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'user_preferences' AND column_name = 'job_queue_notifications'
            ) THEN
                ALTER TABLE user_preferences DROP COLUMN job_queue_notifications;
            END IF;
        END $$;
    """)

    # Entferne Role-Permission Zuweisungen
    permission_names = [
        'job_queue:read',
        'job_queue:manage',
        'job_queue:clear',
        'job_queue:force_kill'
    ]

    for perm_name in permission_names:
        # Hole Permission ID
        perm_result = conn.execute(
            sa.text("SELECT id FROM permissions WHERE name = :name"),
            {"name": perm_name}
        ).fetchone()

        if perm_result:
            perm_id = str(perm_result[0])
            # Loesche Role-Permission Zuweisungen
            conn.execute(
                sa.text("DELETE FROM role_permissions WHERE permission_id = :perm_id"),
                {"perm_id": perm_id}
            )
            # Loesche Permission
            conn.execute(
                sa.text("DELETE FROM permissions WHERE id = :perm_id"),
                {"perm_id": perm_id}
            )

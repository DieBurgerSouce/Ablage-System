"""Add Personal/HR Module Permissions

Revision ID: 068_add_personal_permissions
Revises: 067_add_job_queue_permissions
Create Date: 2025-12-30

Enterprise-Grade Berechtigungen fuer Personal/HR-Modul:

Mitarbeiter (employees):
- employees:read - Mitarbeiterdaten lesen (PII maskiert)
- employees:read_pii - Mitarbeiterdaten inkl. PII lesen (IBAN, Steuer-ID, etc.)
- employees:write - Mitarbeiter erstellen und bearbeiten
- employees:delete - Mitarbeiter loeschen (Soft-Delete)
- employees:manage - Vollzugriff auf Mitarbeiterverwaltung
- employees:export - Mitarbeiterdaten exportieren (GDPR Art. 20)

Abteilungen (departments):
- departments:read - Abteilungen anzeigen
- departments:write - Abteilungen erstellen und bearbeiten
- departments:delete - Abteilungen loeschen
- departments:manage - Vollzugriff auf Abteilungsverwaltung

Stellen (positions):
- positions:read - Stellen anzeigen (ohne Gehalt)
- positions:read_salary - Gehaltsrahmen anzeigen
- positions:write - Stellen erstellen und bearbeiten
- positions:delete - Stellen loeschen
- positions:manage - Vollzugriff auf Stellenverwaltung

Rollen-Zuweisungen:
- admin: Alle Permissions
- hr_manager: Alle ausser :manage
- hr_user: read, read_pii, write
- manager: read (eigene Abteilung)
- user: keine
"""
from typing import Sequence, Union
import uuid

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '068_add_personal_permissions'
down_revision: Union[str, None] = '067_add_job_queue_permissions'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Fuege Personal/HR Module Permissions hinzu.
    """
    # ==================== PERSONAL MODULE PERMISSIONS ====================
    permissions_table = sa.table(
        'permissions',
        sa.column('id', postgresql.UUID),
        sa.column('name', sa.String),
        sa.column('description', sa.String),
        sa.column('resource_type', sa.String),
        sa.column('action', sa.String),
        sa.column('is_system', sa.Boolean),
    )

    # Neue Personal Module Permissions
    personal_permissions = [
        # ==================== EMPLOYEES ====================
        {
            'id': str(uuid.uuid4()),
            'name': 'employees:read',
            'description': 'Mitarbeiterdaten lesen (PII maskiert)',
            'resource_type': 'employees',
            'action': 'read',
            'is_system': True
        },
        {
            'id': str(uuid.uuid4()),
            'name': 'employees:read_pii',
            'description': 'Mitarbeiterdaten inkl. PII lesen (IBAN, Steuer-ID, SSN, etc.)',
            'resource_type': 'employees',
            'action': 'read_pii',
            'is_system': True
        },
        {
            'id': str(uuid.uuid4()),
            'name': 'employees:write',
            'description': 'Mitarbeiter erstellen und bearbeiten',
            'resource_type': 'employees',
            'action': 'write',
            'is_system': True
        },
        {
            'id': str(uuid.uuid4()),
            'name': 'employees:delete',
            'description': 'Mitarbeiter loeschen (Soft-Delete)',
            'resource_type': 'employees',
            'action': 'delete',
            'is_system': True
        },
        {
            'id': str(uuid.uuid4()),
            'name': 'employees:manage',
            'description': 'Vollzugriff auf Mitarbeiterverwaltung',
            'resource_type': 'employees',
            'action': 'manage',
            'is_system': True
        },
        {
            'id': str(uuid.uuid4()),
            'name': 'employees:export',
            'description': 'Mitarbeiterdaten exportieren (GDPR Art. 20 Datenportabilitaet)',
            'resource_type': 'employees',
            'action': 'export',
            'is_system': True
        },
        # ==================== DEPARTMENTS ====================
        {
            'id': str(uuid.uuid4()),
            'name': 'departments:read',
            'description': 'Abteilungen anzeigen',
            'resource_type': 'departments',
            'action': 'read',
            'is_system': True
        },
        {
            'id': str(uuid.uuid4()),
            'name': 'departments:write',
            'description': 'Abteilungen erstellen und bearbeiten',
            'resource_type': 'departments',
            'action': 'write',
            'is_system': True
        },
        {
            'id': str(uuid.uuid4()),
            'name': 'departments:delete',
            'description': 'Abteilungen loeschen',
            'resource_type': 'departments',
            'action': 'delete',
            'is_system': True
        },
        {
            'id': str(uuid.uuid4()),
            'name': 'departments:manage',
            'description': 'Vollzugriff auf Abteilungsverwaltung',
            'resource_type': 'departments',
            'action': 'manage',
            'is_system': True
        },
        # ==================== POSITIONS ====================
        {
            'id': str(uuid.uuid4()),
            'name': 'positions:read',
            'description': 'Stellen anzeigen (ohne Gehaltsrahmen)',
            'resource_type': 'positions',
            'action': 'read',
            'is_system': True
        },
        {
            'id': str(uuid.uuid4()),
            'name': 'positions:read_salary',
            'description': 'Gehaltsrahmen anzeigen',
            'resource_type': 'positions',
            'action': 'read_salary',
            'is_system': True
        },
        {
            'id': str(uuid.uuid4()),
            'name': 'positions:write',
            'description': 'Stellen erstellen und bearbeiten',
            'resource_type': 'positions',
            'action': 'write',
            'is_system': True
        },
        {
            'id': str(uuid.uuid4()),
            'name': 'positions:delete',
            'description': 'Stellen loeschen',
            'resource_type': 'positions',
            'action': 'delete',
            'is_system': True
        },
        {
            'id': str(uuid.uuid4()),
            'name': 'positions:manage',
            'description': 'Vollzugriff auf Stellenverwaltung',
            'resource_type': 'positions',
            'action': 'manage',
            'is_system': True
        },
    ]

    # Permissions einfuegen
    permission_ids = {}
    for perm in personal_permissions:
        permission_ids[perm['name']] = perm['id']
        op.execute(
            permissions_table.insert().values(**perm)
        )

    # ==================== ROLE-PERMISSION ZUWEISUNGEN ====================
    conn = op.get_bind()

    role_permissions_table = sa.table(
        'role_permissions',
        sa.column('role_id', postgresql.UUID),
        sa.column('permission_id', postgresql.UUID),
    )

    # Hole existierende Rollen
    admin_result = conn.execute(
        sa.text("SELECT id FROM roles WHERE name = 'admin'")
    ).fetchone()

    hr_manager_result = conn.execute(
        sa.text("SELECT id FROM roles WHERE name = 'hr_manager'")
    ).fetchone()

    hr_user_result = conn.execute(
        sa.text("SELECT id FROM roles WHERE name = 'hr_user'")
    ).fetchone()

    manager_result = conn.execute(
        sa.text("SELECT id FROM roles WHERE name = 'manager'")
    ).fetchone()

    # Admin: ALLE Personal Permissions
    if admin_result:
        admin_id = str(admin_result[0])
        for perm_name, perm_id in permission_ids.items():
            op.execute(
                role_permissions_table.insert().values(
                    role_id=admin_id,
                    permission_id=perm_id
                )
            )

    # HR Manager: Alles ausser :manage (um versehentliches Loeschen zu vermeiden)
    if hr_manager_result:
        hr_manager_id = str(hr_manager_result[0])
        hr_manager_perms = [
            'employees:read', 'employees:read_pii', 'employees:write',
            'employees:delete', 'employees:export',
            'departments:read', 'departments:write', 'departments:delete',
            'positions:read', 'positions:read_salary', 'positions:write', 'positions:delete',
        ]
        for perm_name in hr_manager_perms:
            if perm_name in permission_ids:
                op.execute(
                    role_permissions_table.insert().values(
                        role_id=hr_manager_id,
                        permission_id=permission_ids[perm_name]
                    )
                )

    # HR User: Lesen (inkl. PII) und Bearbeiten
    if hr_user_result:
        hr_user_id = str(hr_user_result[0])
        hr_user_perms = [
            'employees:read', 'employees:read_pii', 'employees:write',
            'departments:read',
            'positions:read', 'positions:read_salary',
        ]
        for perm_name in hr_user_perms:
            if perm_name in permission_ids:
                op.execute(
                    role_permissions_table.insert().values(
                        role_id=hr_user_id,
                        permission_id=permission_ids[perm_name]
                    )
                )

    # Manager: Nur Lesen (fuer eigene Abteilung - Einschraenkung via Business Logic)
    if manager_result:
        manager_id = str(manager_result[0])
        manager_perms = [
            'employees:read',  # Ohne PII!
            'departments:read',
            'positions:read',  # Ohne Gehalt!
        ]
        for perm_name in manager_perms:
            if perm_name in permission_ids:
                op.execute(
                    role_permissions_table.insert().values(
                        role_id=manager_id,
                        permission_id=permission_ids[perm_name]
                    )
                )


def downgrade() -> None:
    """
    Entferne Personal Module Permissions.
    """
    conn = op.get_bind()

    # Liste aller Personal Permissions
    permission_names = [
        # Employees
        'employees:read',
        'employees:read_pii',
        'employees:write',
        'employees:delete',
        'employees:manage',
        'employees:export',
        # Departments
        'departments:read',
        'departments:write',
        'departments:delete',
        'departments:manage',
        # Positions
        'positions:read',
        'positions:read_salary',
        'positions:write',
        'positions:delete',
        'positions:manage',
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

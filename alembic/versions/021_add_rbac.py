"""Add Role-Based Access Control (RBAC)

Revision ID: 021
Revises: 020
Create Date: 2025-12-01

Security Features:
- Role-Based Access Control (RBAC) für Enterprise Multi-User Deployment
- Permissions mit Resource-Type und Action (z.B. documents:read)
- System-Rollen: admin, manager, analyst, viewer
- Granulare Berechtigungsverwaltung
"""
from typing import Sequence, Union
import uuid

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '021'
down_revision: Union[str, None] = '020_gdpr_processing'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Erstelle RBAC Tabellen und System-Rollen.
    """
    # ==================== PERMISSIONS ====================
    op.create_table(
        'permissions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(100), unique=True, nullable=False),
        sa.Column('description', sa.String(255), nullable=True),
        sa.Column('resource_type', sa.String(50), nullable=False),
        sa.Column('action', sa.String(50), nullable=False),
        sa.Column('is_system', sa.Boolean(), default=False, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Indexes für permissions
    op.create_index('ix_permissions_name', 'permissions', ['name'])
    op.create_index('ix_permissions_resource_action', 'permissions', ['resource_type', 'action'])

    # ==================== ROLES ====================
    op.create_table(
        'roles',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(50), unique=True, nullable=False),
        sa.Column('display_name', sa.String(100), nullable=False),
        sa.Column('description', sa.String(500), nullable=True),
        sa.Column('priority', sa.Integer(), default=0, nullable=False),
        sa.Column('is_system', sa.Boolean(), default=False, nullable=False),
        sa.Column('is_active', sa.Boolean(), default=True, nullable=False),
        sa.Column('color', sa.String(7), default='#6B7280', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )

    # Indexes für roles
    op.create_index('ix_roles_name', 'roles', ['name'])
    op.create_index('ix_roles_priority', 'roles', ['priority'])

    # ==================== ROLE_PERMISSIONS (Association) ====================
    op.create_table(
        'role_permissions',
        sa.Column('role_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('roles.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('permission_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('permissions.id', ondelete='CASCADE'), primary_key=True),
    )

    op.create_index('ix_role_permissions_role_id', 'role_permissions', ['role_id'])
    op.create_index('ix_role_permissions_permission_id', 'role_permissions', ['permission_id'])

    # ==================== USER_ROLES (Association) ====================
    op.create_table(
        'user_roles',
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('role_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('roles.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('assigned_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('assigned_by_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
    )

    op.create_index('ix_user_roles_user_id', 'user_roles', ['user_id'])
    op.create_index('ix_user_roles_role_id', 'user_roles', ['role_id'])

    # ==================== SEED: System Permissions ====================
    permissions_table = sa.table(
        'permissions',
        sa.column('id', postgresql.UUID),
        sa.column('name', sa.String),
        sa.column('description', sa.String),
        sa.column('resource_type', sa.String),
        sa.column('action', sa.String),
        sa.column('is_system', sa.Boolean),
    )

    # Define all system permissions
    permissions_data = [
        # Documents
        {'name': 'documents:read', 'description': 'Dokumente lesen und anzeigen', 'resource_type': 'documents', 'action': 'read'},
        {'name': 'documents:write', 'description': 'Dokumente erstellen und bearbeiten', 'resource_type': 'documents', 'action': 'write'},
        {'name': 'documents:delete', 'description': 'Dokumente löschen', 'resource_type': 'documents', 'action': 'delete'},
        {'name': 'documents:manage', 'description': 'Dokumente vollständig verwalten', 'resource_type': 'documents', 'action': 'manage'},
        # Users
        {'name': 'users:read', 'description': 'Benutzer anzeigen', 'resource_type': 'users', 'action': 'read'},
        {'name': 'users:write', 'description': 'Benutzer erstellen und bearbeiten', 'resource_type': 'users', 'action': 'write'},
        {'name': 'users:delete', 'description': 'Benutzer löschen', 'resource_type': 'users', 'action': 'delete'},
        {'name': 'users:manage', 'description': 'Benutzer vollständig verwalten (inkl. Rollen)', 'resource_type': 'users', 'action': 'manage'},
        # Roles
        {'name': 'roles:read', 'description': 'Rollen anzeigen', 'resource_type': 'roles', 'action': 'read'},
        {'name': 'roles:write', 'description': 'Rollen erstellen und bearbeiten', 'resource_type': 'roles', 'action': 'write'},
        {'name': 'roles:delete', 'description': 'Rollen löschen', 'resource_type': 'roles', 'action': 'delete'},
        {'name': 'roles:manage', 'description': 'Rollen vollständig verwalten', 'resource_type': 'roles', 'action': 'manage'},
        # Webhooks
        {'name': 'webhooks:read', 'description': 'Webhooks anzeigen', 'resource_type': 'webhooks', 'action': 'read'},
        {'name': 'webhooks:write', 'description': 'Webhooks erstellen und bearbeiten', 'resource_type': 'webhooks', 'action': 'write'},
        {'name': 'webhooks:delete', 'description': 'Webhooks löschen', 'resource_type': 'webhooks', 'action': 'delete'},
        {'name': 'webhooks:manage', 'description': 'Webhooks vollständig verwalten', 'resource_type': 'webhooks', 'action': 'manage'},
        # API Keys
        {'name': 'api_keys:read', 'description': 'API-Schlüssel anzeigen', 'resource_type': 'api_keys', 'action': 'read'},
        {'name': 'api_keys:write', 'description': 'API-Schlüssel erstellen', 'resource_type': 'api_keys', 'action': 'write'},
        {'name': 'api_keys:delete', 'description': 'API-Schlüssel löschen', 'resource_type': 'api_keys', 'action': 'delete'},
        {'name': 'api_keys:manage', 'description': 'API-Schlüssel vollständig verwalten', 'resource_type': 'api_keys', 'action': 'manage'},
        # Audit Logs
        {'name': 'audit_logs:read', 'description': 'Audit-Logs lesen', 'resource_type': 'audit_logs', 'action': 'read'},
        {'name': 'audit_logs:manage', 'description': 'Audit-Logs verwalten und exportieren', 'resource_type': 'audit_logs', 'action': 'manage'},
        # System
        {'name': 'system:read', 'description': 'Systemstatus anzeigen', 'resource_type': 'system', 'action': 'read'},
        {'name': 'system:manage', 'description': 'System konfigurieren', 'resource_type': 'system', 'action': 'manage'},
        # Backups
        {'name': 'backups:read', 'description': 'Backups anzeigen', 'resource_type': 'backups', 'action': 'read'},
        {'name': 'backups:write', 'description': 'Backups erstellen', 'resource_type': 'backups', 'action': 'write'},
        {'name': 'backups:manage', 'description': 'Backups vollständig verwalten (inkl. Wiederherstellung)', 'resource_type': 'backups', 'action': 'manage'},
        # OCR
        {'name': 'ocr:read', 'description': 'OCR-Status anzeigen', 'resource_type': 'ocr', 'action': 'read'},
        {'name': 'ocr:write', 'description': 'OCR-Verarbeitung starten', 'resource_type': 'ocr', 'action': 'write'},
        {'name': 'ocr:manage', 'description': 'OCR vollständig verwalten', 'resource_type': 'ocr', 'action': 'manage'},
        # Search
        {'name': 'search:read', 'description': 'Suche verwenden', 'resource_type': 'search', 'action': 'read'},
        {'name': 'search:manage', 'description': 'Such-Analytics verwalten', 'resource_type': 'search', 'action': 'manage'},
    ]

    # Insert permissions with generated UUIDs
    permission_ids = {}
    for perm in permissions_data:
        perm_id = str(uuid.uuid4())
        permission_ids[perm['name']] = perm_id
        op.execute(
            permissions_table.insert().values(
                id=perm_id,
                name=perm['name'],
                description=perm['description'],
                resource_type=perm['resource_type'],
                action=perm['action'],
                is_system=True
            )
        )

    # ==================== SEED: System Roles ====================
    roles_table = sa.table(
        'roles',
        sa.column('id', postgresql.UUID),
        sa.column('name', sa.String),
        sa.column('display_name', sa.String),
        sa.column('description', sa.String),
        sa.column('priority', sa.Integer),
        sa.column('is_system', sa.Boolean),
        sa.column('is_active', sa.Boolean),
        sa.column('color', sa.String),
    )

    # Define system roles
    admin_id = str(uuid.uuid4())
    manager_id = str(uuid.uuid4())
    analyst_id = str(uuid.uuid4())
    viewer_id = str(uuid.uuid4())

    roles_data = [
        {
            'id': admin_id,
            'name': 'admin',
            'display_name': 'Administrator',
            'description': 'Voller Zugriff auf alle Funktionen des Systems',
            'priority': 100,
            'color': '#DC2626'  # Red
        },
        {
            'id': manager_id,
            'name': 'manager',
            'display_name': 'Manager',
            'description': 'Kann Benutzer und Dokumente verwalten',
            'priority': 75,
            'color': '#F59E0B'  # Amber
        },
        {
            'id': analyst_id,
            'name': 'analyst',
            'display_name': 'Analyst',
            'description': 'Kann Dokumente verarbeiten und analysieren',
            'priority': 50,
            'color': '#3B82F6'  # Blue
        },
        {
            'id': viewer_id,
            'name': 'viewer',
            'display_name': 'Betrachter',
            'description': 'Kann Dokumente nur anzeigen',
            'priority': 10,
            'color': '#6B7280'  # Gray
        },
    ]

    for role in roles_data:
        op.execute(
            roles_table.insert().values(
                id=role['id'],
                name=role['name'],
                display_name=role['display_name'],
                description=role['description'],
                priority=role['priority'],
                is_system=True,
                is_active=True,
                color=role['color']
            )
        )

    # ==================== SEED: Role-Permission Mappings ====================
    role_permissions_table = sa.table(
        'role_permissions',
        sa.column('role_id', postgresql.UUID),
        sa.column('permission_id', postgresql.UUID),
    )

    # Admin: ALL permissions
    admin_perms = list(permission_ids.keys())

    # Manager: Documents, Users (no delete), Webhooks, API Keys, OCR, Search, Audit read
    manager_perms = [
        'documents:read', 'documents:write', 'documents:delete', 'documents:manage',
        'users:read', 'users:write',
        'webhooks:read', 'webhooks:write', 'webhooks:delete',
        'api_keys:read', 'api_keys:write', 'api_keys:delete',
        'audit_logs:read',
        'ocr:read', 'ocr:write',
        'search:read',
        'backups:read',
    ]

    # Analyst: Documents (full), OCR, Search
    analyst_perms = [
        'documents:read', 'documents:write', 'documents:delete',
        'webhooks:read',
        'api_keys:read', 'api_keys:write',
        'ocr:read', 'ocr:write',
        'search:read',
    ]

    # Viewer: Read-only access
    viewer_perms = [
        'documents:read',
        'ocr:read',
        'search:read',
    ]

    # Insert role-permission mappings
    role_perm_mappings = [
        (admin_id, admin_perms),
        (manager_id, manager_perms),
        (analyst_id, analyst_perms),
        (viewer_id, viewer_perms),
    ]

    for role_id, perms in role_perm_mappings:
        for perm_name in perms:
            if perm_name in permission_ids:
                op.execute(
                    role_permissions_table.insert().values(
                        role_id=role_id,
                        permission_id=permission_ids[perm_name]
                    )
                )


def downgrade() -> None:
    """
    Entferne RBAC Tabellen.
    """
    # Drop association tables first
    op.drop_index('ix_user_roles_role_id', table_name='user_roles')
    op.drop_index('ix_user_roles_user_id', table_name='user_roles')
    op.drop_table('user_roles')

    op.drop_index('ix_role_permissions_permission_id', table_name='role_permissions')
    op.drop_index('ix_role_permissions_role_id', table_name='role_permissions')
    op.drop_table('role_permissions')

    # Drop main tables
    op.drop_index('ix_roles_priority', table_name='roles')
    op.drop_index('ix_roles_name', table_name='roles')
    op.drop_table('roles')

    op.drop_index('ix_permissions_resource_action', table_name='permissions')
    op.drop_index('ix_permissions_name', table_name='permissions')
    op.drop_table('permissions')

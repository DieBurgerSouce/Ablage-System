"""Seed default RBAC roles and permissions.

Seeds the standard roles (admin, manager, user, viewer, tax_advisor)
with appropriate permissions if they don't already exist.

Revision ID: 259
Revises: 258
Create Date: 2026-03-09
"""
import uuid

from alembic import op
from sqlalchemy import text

revision = "259"
down_revision = "258"
branch_labels = None
depends_on = None

# Resource types and actions for permission matrix
RESOURCE_TYPES = [
    "documents", "users", "roles", "webhooks",
    "api_keys", "audit_logs", "system", "backups", "ocr", "search",
]

ACTIONS = ["read", "write", "delete", "manage"]

# Role definitions
ROLES = {
    "admin": {
        "display_name": "Administrator",
        "description": "Vollzugriff auf alle Systemfunktionen",
        "priority": 100,
        "color": "#DC2626",
        "permissions": [(r, a) for r in RESOURCE_TYPES for a in ACTIONS],
    },
    "manager": {
        "display_name": "Abteilungsleiter",
        "description": "Abteilungsweite Verwaltung von Dokumenten und Benutzern",
        "priority": 75,
        "color": "#2563EB",
        "permissions": [
            *[(r, a) for r in ["documents", "ocr", "search"] for a in ACTIONS],
            ("users", "read"), ("users", "write"),
            ("roles", "read"),
            ("audit_logs", "read"),
            ("webhooks", "read"), ("webhooks", "write"),
        ],
    },
    "user": {
        "display_name": "Benutzer",
        "description": "Standard-Dokumentenoperationen (Erstellen, Bearbeiten, Loeschen)",
        "priority": 50,
        "color": "#059669",
        "permissions": [
            *[(r, a) for r in ["documents", "ocr", "search"] for a in ["read", "write", "delete"]],
            ("webhooks", "read"),
        ],
    },
    "viewer": {
        "display_name": "Nur-Lesen",
        "description": "Schreibgeschuetzter Zugriff auf Dokumente und Suche",
        "priority": 10,
        "color": "#6B7280",
        "permissions": [
            ("documents", "read"),
            ("search", "read"),
            ("ocr", "read"),
        ],
    },
    "tax_advisor": {
        "display_name": "Steuerberater",
        "description": "Zeitlich begrenzter externer Zugriff (GoBD-konform)",
        "priority": 30,
        "color": "#7C3AED",
        "permissions": [
            ("documents", "read"),
            ("search", "read"),
            ("ocr", "read"),
            ("audit_logs", "read"),
        ],
    },
}


def _table_exists(conn, table_name: str) -> bool:
    result = conn.execute(
        text("SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = :t"),
        {"t": table_name},
    ).fetchone()
    return result is not None


def upgrade() -> None:
    conn = op.get_bind()

    # Skip if tables don't exist yet
    if not _table_exists(conn, "roles") or not _table_exists(conn, "permissions"):
        return

    # Step 1: Create all permissions that don't exist yet
    for resource_type in RESOURCE_TYPES:
        for action in ACTIONS:
            perm_name = f"{resource_type}:{action}"
            exists = conn.execute(
                text("SELECT 1 FROM permissions WHERE name = :name"),
                {"name": perm_name},
            ).fetchone()

            if not exists:
                perm_id = str(uuid.uuid4())
                conn.execute(
                    text(
                        """INSERT INTO permissions (id, name, description, resource_type, action, is_system)
                           VALUES (:id, :name, :desc, :rt, :act, true)"""
                    ),
                    {
                        "id": perm_id,
                        "name": perm_name,
                        "desc": f"{action.capitalize()}-Berechtigung fuer {resource_type}",
                        "rt": resource_type,
                        "act": action,
                    },
                )

    # Step 2: Create roles and assign permissions
    for role_name, role_def in ROLES.items():
        exists = conn.execute(
            text("SELECT id FROM roles WHERE name = :name"),
            {"name": role_name},
        ).fetchone()

        if exists:
            role_id = str(exists[0])
        else:
            role_id = str(uuid.uuid4())
            conn.execute(
                text(
                    """INSERT INTO roles (id, name, display_name, description, priority, is_system, is_active, color)
                       VALUES (:id, :name, :dn, :desc, :pri, true, true, :color)"""
                ),
                {
                    "id": role_id,
                    "name": role_name,
                    "dn": role_def["display_name"],
                    "desc": role_def["description"],
                    "pri": role_def["priority"],
                    "color": role_def["color"],
                },
            )

        # Assign permissions to role (skip existing)
        if not _table_exists(conn, "role_permissions"):
            continue

        for resource_type, action in role_def["permissions"]:
            perm_name = f"{resource_type}:{action}"
            perm_row = conn.execute(
                text("SELECT id FROM permissions WHERE name = :name"),
                {"name": perm_name},
            ).fetchone()
            if not perm_row:
                continue

            perm_id = str(perm_row[0])
            link_exists = conn.execute(
                text(
                    "SELECT 1 FROM role_permissions WHERE role_id = :rid AND permission_id = :pid"
                ),
                {"rid": role_id, "pid": perm_id},
            ).fetchone()

            if not link_exists:
                conn.execute(
                    text(
                        "INSERT INTO role_permissions (role_id, permission_id) VALUES (:rid, :pid)"
                    ),
                    {"rid": role_id, "pid": perm_id},
                )


def downgrade() -> None:
    conn = op.get_bind()

    for role_name in ROLES:
        role_row = conn.execute(
            text("SELECT id FROM roles WHERE name = :name AND is_system = true"),
            {"name": role_name},
        ).fetchone()

        if role_row:
            role_id = str(role_row[0])
            conn.execute(
                text("DELETE FROM role_permissions WHERE role_id = :rid"),
                {"rid": role_id},
            )
            conn.execute(
                text("DELETE FROM roles WHERE id = :id"),
                {"id": role_id},
            )

    conn.execute(text("DELETE FROM permissions WHERE is_system = true"))

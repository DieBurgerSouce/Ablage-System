"""F-15: documents-RLS-Escapes entfernen (DoD-8 — ohne Kontext 0 Zeilen).

Die permissiven documents-Policies enthielten Escapes, die die Mandanten-
trennung auf der Leseseite aushebelten:
  - documents_owner_select/update/delete USING:
        ... OR current_setting('app.current_user_id', true) IS NULL
        ... OR current_setting('app.current_user_id', true) = ''
    -> eine Query OHNE gesetzten User-Kontext sah ALLE Dokumente.
  - documents_tenant_isolation USING:
        ... OR company_id IS NULL
    -> NULL-Company-Dokumente waren tenant-uebergreifend sichtbar.

Voraussetzung (F-16, bereits umgesetzt): Alle Background-Worker setzen jetzt
beim Oeffnen der DB-Session RLS-Kontext bzw. -Bypass (get_worker_session_context),
lasen also NICHT mehr ueber diese Escapes. Erst dadurch ist das Entfernen sicher.

Nach dieser Migration:
  - kontextlose App-Rolle liest 0 documents-Zeilen (DoD-8),
  - User-Kontext sieht eigene/Company-Dokumente,
  - Worker-Bypass (is_rls_bypass_enabled()) sieht alles.

Nur die USING-Klauseln (Lesepfad) werden geaendert; WITH CHECK bleibt unberuehrt
(INSERTs der Ersteller laufen ueber gesetzten Company-Kontext bzw. Bypass, plus
documents_insert WITH CHECK true). PostgreSQL-only; idempotent (ALTER POLICY auf
im Head 271 vorhandene Policies). Rueckbau via downgrade (Escapes wiederherstellen).
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "272"
down_revision = "271"
branch_labels = None
depends_on = None


# USING ohne Escapes (Zielzustand)
_OWNER_USING_HARDENED = (
    "(owner_id)::text = current_setting('app.current_user_id', true) "
    "OR current_setting('app.is_admin', true) = 'true'"
)
# USING mit Escapes (Ausgangszustand — fuer downgrade)
_OWNER_USING_LEGACY = (
    "(owner_id)::text = current_setting('app.current_user_id', true) "
    "OR current_setting('app.current_user_id', true) IS NULL "
    "OR current_setting('app.current_user_id', true) = '' "
    "OR current_setting('app.is_admin', true) = 'true'"
)
_TENANT_USING_HARDENED = (
    "is_rls_bypass_enabled() OR company_id = get_current_company_id()"
)
_TENANT_USING_LEGACY = (
    "is_rls_bypass_enabled() OR company_id IS NULL "
    "OR company_id = get_current_company_id()"
)

_OWNER_POLICIES = (
    "documents_owner_select",
    "documents_owner_update",
    "documents_owner_delete",
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    for policy in _OWNER_POLICIES:
        op.execute(
            f"ALTER POLICY {policy} ON documents USING ({_OWNER_USING_HARDENED})"
        )
    # tenant_isolation: nur USING (Lesepfad); WITH CHECK bleibt (INSERT unberuehrt)
    op.execute(
        f"ALTER POLICY documents_tenant_isolation ON documents "
        f"USING ({_TENANT_USING_HARDENED})"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    for policy in _OWNER_POLICIES:
        op.execute(
            f"ALTER POLICY {policy} ON documents USING ({_OWNER_USING_LEGACY})"
        )
    op.execute(
        f"ALTER POLICY documents_tenant_isolation ON documents "
        f"USING ({_TENANT_USING_LEGACY})"
    )

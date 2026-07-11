"""RLS-Restrunde Teil 2: documents-INSERT-Mandantentrennung (3-Policy-Verbund).

Design + Empirie: docs/reviews/2026-07_rls_274_design.md (VORBEREITET —
Anwendung via GATE wie 272/273).

Ist-Zustand: INSERT auf documents ist erlaubt, wenn IRGENDEINE permissive
WITH-CHECK passt — ``documents_insert`` hatte ``WITH CHECK (true)`` (offene
Scheunentuer) und ``documents_tenant_isolation`` einen ``company_id IS
NULL``-Zweig. Empirisch belegt (2026-07-11): 0 NULL-company-Zeilen im
Bestand, KEIN legitimer Produzent (Privat-Suite schreibt in die eigene
Tabelle PrivatDocument; Import/Mirror/Upload setzen company_id immer).

Aenderungen:
1. DROP POLICY ``documents_insert`` — ersatzlos; INSERT wird vollstaendig
   von den beiden ALL-Policies gedeckt (bypass ∨ company-match ∨ admin).
2. ``documents_tenant_isolation`` WITH CHECK -> bypass ∨ company-match
   (NULL-Zweig raus; USING wurde bereits in 272 gehaertet und bleibt
   unberuehrt — ALTER POLICY aendert nur die angegebene Klausel).
3. ``documents_company_isolation`` bleibt unveraendert.

Resultierende INSERT-Matrix: Worker-Bypass OK · eigener Company-Kontext OK ·
Admin OK · kontextlos ABGELEHNT · NULL-company ABGELEHNT · fremde company
ABGELEHNT. UPDATE-new-row unterliegt denselben WITH CHECKs (gewollt).

Vorbedingung (im selben Branch erledigt): kontextlose documents-Writer auf
get_worker_session_context umgestellt (import_wa_we, active_learning_tasks);
Worker-Pipeline nutzt seit F-16 durchgehend Bypass-/Company-Kontext.

PostgreSQL-only; downgrade stellt den Ausgangszustand exakt wieder her.
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "274"
down_revision = "273"
branch_labels = None
depends_on = None


_TENANT_CHECK_HARDENED = (
    "is_rls_bypass_enabled() OR company_id = get_current_company_id()"
)
_TENANT_CHECK_LEGACY = (
    "is_rls_bypass_enabled() OR company_id IS NULL "
    "OR company_id = get_current_company_id()"
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("DROP POLICY IF EXISTS documents_insert ON documents")
    op.execute(
        "ALTER POLICY documents_tenant_isolation ON documents "
        f"WITH CHECK ({_TENANT_CHECK_HARDENED})"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(
        "CREATE POLICY documents_insert ON documents "
        "FOR INSERT WITH CHECK (true)"
    )
    op.execute(
        "ALTER POLICY documents_tenant_isolation ON documents "
        f"WITH CHECK ({_TENANT_CHECK_LEGACY})"
    )

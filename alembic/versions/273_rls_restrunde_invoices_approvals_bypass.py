"""RLS-Restrunde Teil 1 (mechanisch): F-15-Klasse-Escapes + Bypass-Konsistenz.

Baut exakt auf dem 272er-Muster auf (VORBEREITET — Anwendung via GATE durch
Ben: ``alembic upgrade head`` + Live-Verifikation nach DoD-8-Schema).

Befund (read-only pg_policies-Audit 2026-07-11,
docs/reviews/2026-07_rls_restrunde_audit.md):

1. ``invoices``: ``invoices_company_isolation`` UND ``invoices_tenant_isolation``
   enthalten in USING den Escape ``company_id IS NULL`` -> NULL-Company-
   Rechnungen sind tenant-uebergreifend lesbar. Vorbedingung geprueft:
   **0 Zeilen** mit ``company_id IS NULL`` (2026-07-11) -> Entfernen
   versteckt nichts.
2. ``approval_requests``: dito in ``approval_requests_tenant_isolation``.
3. ``companies.company_access_policy``: KEINE ``is_rls_bypass_enabled()``-
   Klausel -> Worker-Bypass-Sessions lesen 0 companies (live bestaetigt);
   jeder kuenftige Worker-Codepfad, der companies liest, faellt still auf
   0 Zeilen. Bypass-Klausel ergaenzen (Konsistenz mit Kern-Tabellen).
4. ``document_versions.tenant_isolation_document_versions``: dito ohne
   Bypass-Klausel.

Wie bei 272 werden NUR USING-Klauseln geaendert; explizite WITH-CHECK-
Klauseln bleiben unberuehrt (die ``documents_insert``-Verschaerfung ist
BEWUSST NICHT Teil dieser Migration — permissiver 3-Policy-Verbund,
eigenes Design-Paket, siehe Audit-Doku Punkt 2).

PostgreSQL-only; Rueckbau via downgrade (Originalzustand exakt wie im
Audit erfasst). ALTER POLICY setzt vorhandene Policies voraus (Bestand
im Head 272 per Audit belegt).
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "273"
down_revision = "272"
branch_labels = None
depends_on = None


# --- invoices ---------------------------------------------------------------
_INVOICES_COMPANY_USING_HARDENED = "company_id = get_current_company_id()"
_INVOICES_COMPANY_USING_LEGACY = (
    "company_id IS NULL OR company_id = get_current_company_id()"
)
_INVOICES_TENANT_USING_HARDENED = (
    "is_rls_bypass_enabled() OR company_id = get_current_company_id()"
)
_INVOICES_TENANT_USING_LEGACY = (
    "is_rls_bypass_enabled() OR company_id IS NULL "
    "OR company_id = get_current_company_id()"
)

# --- approval_requests -------------------------------------------------------
_APPROVALS_TENANT_USING_HARDENED = (
    "is_rls_bypass_enabled() OR company_id = get_current_company_id()"
)
_APPROVALS_TENANT_USING_LEGACY = (
    "is_rls_bypass_enabled() OR company_id IS NULL "
    "OR company_id = get_current_company_id()"
)

# --- companies ----------------------------------------------------------------
_COMPANIES_ACCESS_BASE = (
    "id IN (SELECT user_companies.company_id FROM user_companies "
    "WHERE user_companies.user_id = "
    "(current_setting('app.current_user_id', true))::uuid) "
    "OR (current_setting('app.is_admin', true))::boolean = true"
)
_COMPANIES_ACCESS_HARDENED = f"is_rls_bypass_enabled() OR {_COMPANIES_ACCESS_BASE}"

# --- document_versions ---------------------------------------------------------
_DOCVERSIONS_TENANT_BASE = (
    "company_id = (NULLIF(current_setting('app.current_company_id', true), ''))::uuid"
)
_DOCVERSIONS_TENANT_HARDENED = (
    f"is_rls_bypass_enabled() OR {_DOCVERSIONS_TENANT_BASE}"
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    # 1) invoices: NULL-Escapes aus dem Lesepfad (WITH CHECK unberuehrt)
    op.execute(
        "ALTER POLICY invoices_company_isolation ON invoices "
        f"USING ({_INVOICES_COMPANY_USING_HARDENED})"
    )
    op.execute(
        "ALTER POLICY invoices_tenant_isolation ON invoices "
        f"USING ({_INVOICES_TENANT_USING_HARDENED})"
    )

    # 2) approval_requests: NULL-Escape aus dem Lesepfad
    op.execute(
        "ALTER POLICY approval_requests_tenant_isolation ON approval_requests "
        f"USING ({_APPROVALS_TENANT_USING_HARDENED})"
    )

    # 3) companies: Worker-Bypass-Klausel ergaenzen (Policy hat KEIN explizites
    #    WITH CHECK -> USING gilt auch fuer Schreibpfade; Bypass = System-Sync)
    op.execute(
        "ALTER POLICY company_access_policy ON companies "
        f"USING ({_COMPANIES_ACCESS_HARDENED})"
    )

    # 4) document_versions: Worker-Bypass-Klausel ergaenzen
    op.execute(
        "ALTER POLICY tenant_isolation_document_versions ON document_versions "
        f"USING ({_DOCVERSIONS_TENANT_HARDENED})"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute(
        "ALTER POLICY invoices_company_isolation ON invoices "
        f"USING ({_INVOICES_COMPANY_USING_LEGACY})"
    )
    op.execute(
        "ALTER POLICY invoices_tenant_isolation ON invoices "
        f"USING ({_INVOICES_TENANT_USING_LEGACY})"
    )
    op.execute(
        "ALTER POLICY approval_requests_tenant_isolation ON approval_requests "
        f"USING ({_APPROVALS_TENANT_USING_LEGACY})"
    )
    op.execute(
        "ALTER POLICY company_access_policy ON companies "
        f"USING ({_COMPANIES_ACCESS_BASE})"
    )
    op.execute(
        "ALTER POLICY tenant_isolation_document_versions ON document_versions "
        f"USING ({_DOCVERSIONS_TENANT_BASE})"
    )

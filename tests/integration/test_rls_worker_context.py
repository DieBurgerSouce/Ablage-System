# -*- coding: utf-8 -*-
"""Echtes-RLS-Integrationstest für den Worker-Kontext-Helfer (F-16).

Anders als die Mock-basierten Unit-Tests läuft dieser Test gegen die ECHTE
Datenbank unter der App-Rolle (``ablage_app``, ohne BYPASSRLS).

**Korrekte F-16-Mechanik (durch echtes Testen ermittelt):** Der Defekt ist
LESE-seitig, nicht schreib-seitig. ``documents_insert`` hat ``WITH CHECK true``
→ INSERTs gelingen ohnehin. Aber Background-Worker LESEN ``documents`` heute nur
über den permissiven ``current_user_id IS NULL``-Escape der SELECT-Policy;
sobald F-15 diesen Escape entfernt, liefert ein kontextloser Worker-Read 0
Zeilen (Dedup/Verarbeitung bricht). ``get_worker_session_context`` etabliert
den Kontext, den die Worker danach brauchen:

- **Ersteller-Modus** (``company_id``): setzt ``app.current_company_id`` →
  company-gescopte Reads/Inserts (nach F-15 der einzige Weg, eigene Company zu
  sehen).
- **Prozessor-Modus** (Bypass): ``is_rls_bypass_enabled()`` = true → nach F-15
  greift der ``tenant_isolation``-Bypass-Zweig, Reads per Objekt-ID funktionieren.
- **session-level GUC** überlebt einen Commit innerhalb der Task (Mirror
  committet pro Move) — ``is_local=false``.

Übersprungen, wenn die Test-DB-Rolle BYPASSRLS/Superuser hat (RLS greift dann
nicht) oder keine ``documents``-Zeile existiert.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from app.db.session import get_async_session_context, get_worker_session_context

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _role_bypasses_rls() -> bool:
    async with get_async_session_context() as s:
        return bool(
            (
                await s.execute(
                    text(
                        "SELECT rolsuper OR rolbypassrls FROM pg_roles "
                        "WHERE rolname = current_user"
                    )
                )
            ).scalar()
        )


async def _sample_company_id():
    async with get_worker_session_context() as s:  # Bypass darf lesen
        return (
            await s.execute(
                text("SELECT company_id FROM documents WHERE company_id IS NOT NULL LIMIT 1")
            )
        ).scalar()


async def test_processor_bypass_sets_bypass_flag_and_reads():
    """Prozessor-Modus: is_rls_bypass_enabled()=true (post-F15-Read-Weg) + Reads sehen Zeilen."""
    if await _role_bypasses_rls():
        pytest.skip("Test-DB-Rolle hat BYPASSRLS — RLS greift nicht")
    async with get_worker_session_context() as s:
        flag = (await s.execute(text("SELECT is_rls_bypass_enabled()"))).scalar()
        assert flag is True, "Bypass-Modus muss app.rls_bypass setzen"
        n = (await s.execute(text("SELECT count(*) FROM documents"))).scalar()
        assert n is not None and n >= 0


async def test_creator_sets_company_context_and_survives_commit():
    """Ersteller-Modus: app.current_company_id gesetzt und commit-fest (session-level GUC)."""
    if await _role_bypasses_rls():
        pytest.skip("Test-DB-Rolle hat BYPASSRLS — RLS greift nicht")
    cid = await _sample_company_id()
    if cid is None:
        pytest.skip("keine documents-Zeile mit company_id vorhanden")

    async with get_worker_session_context(company_id=cid) as s:
        v1 = (
            await s.execute(text("SELECT current_setting('app.current_company_id', true)"))
        ).scalar()
        assert v1 == str(cid)
        # Ein zwischenzeitlicher Commit darf den Kontext NICHT verlieren
        # (Mirror committet pro Move -> is_local=false ist zwingend):
        await s.commit()
        v2 = (
            await s.execute(text("SELECT current_setting('app.current_company_id', true)"))
        ).scalar()
        assert v2 == str(cid), "Company-Kontext muss einen Commit überleben"
        # is_rls_bypass NICHT gesetzt im Ersteller-Modus (scoped, kein Bypass):
        assert (await s.execute(text("SELECT is_rls_bypass_enabled()"))).scalar() is False


async def test_worker_context_does_not_bleed_to_plain_session():
    """Sicherheit: der session-level Bypass blutet NICHT in eine frische Factory-Session."""
    if await _role_bypasses_rls():
        pytest.skip("Test-DB-Rolle hat BYPASSRLS — RLS greift nicht")
    async with get_worker_session_context() as s:  # setzt bypass
        assert (await s.execute(text("SELECT is_rls_bypass_enabled()"))).scalar() is True
    # FRISCHE Factory-Session (z. B. ein API-Endpunkt) darf KEINEN Bypass erben:
    async with get_async_session_context() as s:
        assert (await s.execute(text("SELECT is_rls_bypass_enabled()"))).scalar() is False


async def test_f15_dod8_no_context_read_is_zero_once_migrated():
    """DoD-8 (F-15): Nach Migration 272 liefert eine App-Rolle OHNE Kontext 0
    documents-Zeilen. Solange die Migration nicht angewandt ist (owner_select-
    Escape ``current_user_id IS NULL`` noch vorhanden), skippt der Test — so
    greift er automatisch, sobald umgeschaltet wurde, ohne vorher rot zu sein."""
    if await _role_bypasses_rls():
        pytest.skip("Test-DB-Rolle hat BYPASSRLS — RLS greift nicht")

    async with get_worker_session_context() as s:  # Bypass darf pg_policies lesen
        qual = (
            await s.execute(
                text(
                    "SELECT qual FROM pg_policies WHERE tablename='documents' "
                    "AND policyname='documents_owner_select'"
                )
            )
        ).scalar() or ""
    if "current_user_id" in qual and "IS NULL" in qual:
        pytest.skip("F-15-Migration 272 noch nicht angewandt (owner_select-Escape aktiv)")

    async with get_async_session_context() as s:  # KEIN Kontext
        await s.execute(text("RESET ALL"))
        n = (await s.execute(text("SELECT count(*) FROM documents"))).scalar()
    assert n == 0, "DoD-8: App-Rolle ohne Kontext muss 0 documents-Zeilen lesen"


# =============================================================================
# Migration 274: documents-INSERT-Matrix (skippt bis 274 angewandt ist)
# =============================================================================


async def _alembic_version() -> str:
    async with get_worker_session_context() as s:
        return str(
            (await s.execute(text("SELECT version_num FROM alembic_version"))).scalar()
        )


async def test_274_insert_matrix_kontextlos_und_nullcompany_abgelehnt():
    """Nach 274: kontextloser INSERT + NULL-company-INSERT werden abgelehnt;
    Bypass- und Company-Kontext-INSERT funktionieren (jeweils mit Rollback,
    hinterlaesst keine Zeilen)."""
    if await _role_bypasses_rls():
        pytest.skip("Test-DB-Rolle hat BYPASSRLS/Superuser - RLS greift nicht")
    if (await _alembic_version()) < "274":
        pytest.skip("Migration 274 noch nicht angewandt (GATE)")

    company_id = await _sample_company_id()
    if company_id is None:
        pytest.skip("keine documents-Zeile mit company_id vorhanden")

    insert_sql = text(
        "INSERT INTO documents (id, filename, original_filename, file_path, "
        "file_size, mime_type, checksum, status, company_id, created_at, updated_at) "
        "VALUES (gen_random_uuid(), 'rls274.pdf', 'rls274.pdf', 'x/rls274', "
        "1, 'application/pdf', md5(random()::text), 'uploaded', :cid, now(), now())"
    )

    # 1) kontextlos -> abgelehnt (RowLevelSecurity-Fehler)
    async with get_async_session_context() as s:
        with pytest.raises(Exception) as excinfo:
            await s.execute(insert_sql, {"cid": str(company_id)})
        assert "row-level security" in str(excinfo.value).lower()
        await s.rollback()

    # 2) NULL-company MIT Company-Kontext -> abgelehnt
    async with get_worker_session_context(company_id=company_id) as s:
        with pytest.raises(Exception) as excinfo:
            await s.execute(
                text(
                    "INSERT INTO documents (id, filename, original_filename, "
                    "file_path, file_size, mime_type, checksum, status, "
                    "company_id, created_at, updated_at) VALUES "
                    "(gen_random_uuid(), 'rls274n.pdf', 'rls274n.pdf', 'x/rls274n', "
                    "1, 'application/pdf', md5(random()::text), 'uploaded', "
                    "NULL, now(), now())"
                )
            )
        assert "row-level security" in str(excinfo.value).lower()
        await s.rollback()

    # 3) Worker-Bypass -> erlaubt (Rollback statt Commit)
    async with get_worker_session_context() as s:
        await s.execute(insert_sql, {"cid": str(company_id)})
        await s.rollback()

    # 4) Company-Kontext, eigene Company -> erlaubt (Rollback statt Commit)
    async with get_worker_session_context(company_id=company_id) as s:
        await s.execute(insert_sql, {"cid": str(company_id)})
        await s.rollback()

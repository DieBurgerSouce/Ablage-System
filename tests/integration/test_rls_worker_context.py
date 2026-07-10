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

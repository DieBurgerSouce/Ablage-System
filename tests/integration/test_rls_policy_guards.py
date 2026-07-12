# -*- coding: utf-8 -*-
"""Regressionstests F-P2-006/F-P2-008 (Perception-Audit 2026-07-12).

F-P2-008: RLS-Policies dürfen app.-GUCs NIE ungeguarded casten. Zwei
fragile Alt-Signaturen führten zu HTTP 500 statt deny-by-default:
  1. (current_setting('app.x'::text, true))::TYP   -> ''::uuid crasht
  2. (current_setting('app.x'::text))::TYP          -> fehlt missing_ok:
     crasht schon bei nie gesetztem GUC
Kanonisch ist (NULLIF(current_setting('app.x'::text, true), ''::text))::TYP.
Repairs: scripts/db/repair_rls_guc_casts_20260712.sql (25 Policies) +
repair_rls_guc_casts_round2_20260712.sql (4 Policies, u. a. smart_inbox_items).

F-P2-006: documents.status ist varchar — invalide Werte (Test-Artefakt
'uploaded') crashten JEDE Dokumentliste der Firma via Pydantic-ValueError.
Repair: scripts/db/repair_legacy_document_status_20260712.sql.

Beide Tests laufen gegen die echte Datenbank (Backend-Container) und
frieren den reparierten Zustand ein.
"""
import pytest
from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

UNGUARDED_POLICY_SQL = text(r"""
    SELECT c.relname || '.' || p.polname
    FROM pg_policy p
    JOIN pg_class c ON c.oid = p.polrelid
    WHERE
        -- Signatur 1: mit missing_ok, aber ohne NULLIF-Guard
        coalesce(pg_get_expr(p.polqual, p.polrelid), '')
            ~ '\(current_setting\(''app\.[a-z_]+''::text, true\)\)::(boolean|uuid)'
        OR coalesce(pg_get_expr(p.polwithcheck, p.polrelid), '')
            ~ '\(current_setting\(''app\.[a-z_]+''::text, true\)\)::(boolean|uuid)'
        -- Signatur 2: ganz ohne missing_ok
        OR coalesce(pg_get_expr(p.polqual, p.polrelid), '')
            ~ 'current_setting\(''app\.[a-z_]+''::text\)'
        OR coalesce(pg_get_expr(p.polwithcheck, p.polrelid), '')
            ~ 'current_setting\(''app\.[a-z_]+''::text\)'
    ORDER BY 1
""")

VALID_DOCUMENT_STATUS = (
    "pending", "queued", "processing", "completed", "failed", "cancelled",
)


@pytest.mark.asyncio
async def test_keine_rls_policy_mit_ungeguardetem_guc_cast():
    """Jede Policy muss das NULLIF+missing_ok-Guard-Muster nutzen (F-P2-008)."""
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with maker() as session:
            result = await session.execute(UNGUARDED_POLICY_SQL)
            offen = [row[0] for row in result.fetchall()]
            assert offen == [], (
                "RLS-Policies mit ungeguardetem app.-GUC-Cast gefunden "
                f"(crashen bei fehlendem/leerem Kontext mit 500): {offen} — "
                "Guard-Muster siehe scripts/db/repair_rls_guc_casts_round2_20260712.sql"
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_documents_status_nur_gueltige_enum_werte():
    """Invalide status-Werte crashen jede Dokumentliste der Firma (F-P2-006)."""
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with maker() as session:
            result = await session.execute(
                text(
                    "SELECT DISTINCT status FROM documents "
                    "WHERE status IS NULL OR status NOT IN :valide"
                ).bindparams(bindparam("valide", expanding=True)),
                {"valide": list(VALID_DOCUMENT_STATUS)},
            )
            invalide = [row[0] for row in result.fetchall()]
            assert invalide == [], (
                f"documents.status enthält invalide Werte {invalide} — jede "
                "Listen-/Suchantwort der betroffenen Firma wird zum 500 "
                "(Repair: scripts/db/repair_legacy_document_status_20260712.sql)"
            )
    finally:
        await engine.dispose()

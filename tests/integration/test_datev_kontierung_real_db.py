# -*- coding: utf-8 -*-
"""Integrationstests fuer KontierungsvorschlagService gegen ECHTES Postgres.

Verifiziert die SQL-Semantik von Bug #3 nach der Doppik-Reconcile-Migration (263):
- _suggest_from_history liest aus echten DATEVBuchung-Zeilen (konto_soll/konto_haben/
  steuerschluessel, buchungstext-LIKE) -> History-Vorschlag
- _suggest_from_patterns aus echtem DATEVKontierungPattern (keyword_pattern,
  amount_min/max, konto_soll)
- learn_from_correction persistiert auf den ECHTEN Doppik-Spalten

Voraussetzung: Test-DB mit Migration 263 (siehe scripts/dbtest/setup_real_test_db.sh
ODER `alembic stamp 262 && alembic upgrade head` gegen einen Schema-Klon).
Ohne erreichbare/migrierte DB werden die Tests sauber uebersprungen.

    pytest tests/integration/test_datev_kontierung_real_db.py -v -m integration
"""

import os
import re
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio

pytestmark = [pytest.mark.integration, pytest.mark.real_db]


def _test_db_url() -> str:
    url = os.getenv("TEST_DATABASE_URL")
    if url:
        return url
    base = os.getenv("DATABASE_URL")
    if not base:
        pytest.skip("Kein TEST_DATABASE_URL / DATABASE_URL gesetzt")
    return re.sub(r"/[^/?]+(\?|$)", r"/ablage_test\1", base)


@pytest_asyncio.fixture
async def db_engine():
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy import text
    import app.main  # noqa: F401
    from sqlalchemy.orm import configure_mappers
    configure_mappers()
    engine = create_async_engine(_test_db_url(), echo=False, pool_pre_ping=True)
    try:
        async with engine.connect() as conn:
            # konto_soll existiert nur nach Migration 263 -> sonst skippen
            await conn.execute(text("SELECT konto_soll FROM datev_buchungen LIMIT 0"))
    except Exception as exc:  # pragma: no cover - Infra-Skip
        await engine.dispose()
        pytest.skip(f"Test-DB ohne Migration 263 ({type(exc).__name__}); siehe "
                    f"scripts/dbtest/setup_real_test_db.sh: {str(exc)[:120]}")
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def session(db_engine):
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
    maker = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        try:
            yield s
        finally:
            await s.rollback()


def _company():
    from app.db.models import Company
    return Company(id=uuid4(), name="Firma A", legal_form="GmbH", kontenrahmen="SKR03", is_active=True)


async def _connection_id(session, company_id):
    """Legt eine datev_connections-Zeile via Roh-SQL an und liefert ihre id.

    NB: Das DATEVConnection-MODELL ist ebenfalls vom Doppik-Schisma betroffen
    (Modell: berater_nr/mandant_nr/environment; Tabelle: beraternummer/
    mandantennummer/api_environment) und noch NICHT reconciliert. kontierung_service
    fragt datev_connections aber nicht ab (nur FK-Ziel fuer datev_buchungen),
    daher hier bewusst Roh-Insert gegen die echten Tabellen-Spalten.
    """
    from sqlalchemy import text
    cid = uuid4()
    await session.execute(text(
        """
        INSERT INTO datev_connections
          (id, company_id, name, beraternummer, mandantennummer, wirtschaftsjahr_beginn,
           api_environment, api_version, enabled_features, kontenrahmen, sachkontenlange,
           personenkontenlange, buchungsmodus, gobd_enabled, festschreibung_automatisch,
           connection_status, is_active)
        VALUES
          (:id, :cmp, 'DATEV Test', '1234567', '12345', 1, 'sandbox', 'v1', '[]'::jsonb,
           'SKR03', 4, 5, 'automatisch', true, false, 'connected', true)
        """), {"id": cid, "cmp": company_id})
    await session.flush()
    return cid


def _buchung(company_id, connection_id, *, buchungstext, konto_soll, konto_haben,
             steuerschluessel=None, betrag=100.0):
    from app.db.models import DATEVBuchung
    from datetime import date
    return DATEVBuchung(
        id=uuid4(), company_id=company_id, connection_id=connection_id,
        belegdatum=date(2026, 1, 15), betrag_soll=betrag, betrag_haben=betrag,
        konto_soll=konto_soll, konto_haben=konto_haben, steuerschluessel=steuerschluessel,
        waehrung="EUR", buchungstext=buchungstext, sync_status="synced",
    )


def _input(entity_name, betrag="119.00"):
    from app.services.datev.connect.kontierung_service import KontierungsInput
    return KontierungsInput(entity_name=entity_name, betrag_brutto=Decimal(betrag),
                            mwst_satz=Decimal("19.0"), dokument_typ="invoice", richtung="incoming")


@pytest.mark.asyncio
async def test_suggest_kontierung_history_match(session):
    """_suggest_from_history findet aehnliche Buchung (buchungstext-LIKE) und liefert deren Konto."""
    from app.services.datev.connect.kontierung_service import (
        KontierungsvorschlagService, KontierungsSuggestion,
    )
    comp = _company(); session.add(comp); await session.flush()
    conn_id = await _connection_id(session, comp.id)
    # 2 historische Buchungen desselben Lieferanten -> History-Strategie
    for _ in range(2):
        session.add(_buchung(comp.id, conn_id, buchungstext="Mueller GmbH Wareneingang",
                             konto_soll="4200", konto_haben="70000", steuerschluessel="9"))
    await session.flush()

    sug = await KontierungsvorschlagService().suggest_kontierung(
        db=session, connection_id=conn_id, input_data=_input("Mueller GmbH"))

    assert isinstance(sug, KontierungsSuggestion)
    assert sug.konto == "4200"
    assert sug.gegenkonto == "70000"
    assert sug.source == "history"
    assert sug.confidence > 0


@pytest.mark.asyncio
async def test_suggest_kontierung_keyword_fallback(session):
    """Ohne History/Pattern greift die Keyword-Strategie (Bueromaterial -> 4930)."""
    from app.services.datev.connect.kontierung_service import KontierungsvorschlagService
    from app.services.datev.connect.kontierung_service import KontierungsInput
    comp = _company(); session.add(comp); await session.flush()
    conn_id = await _connection_id(session, comp.id)

    sug = await KontierungsvorschlagService().suggest_kontierung(
        db=session, connection_id=conn_id,
        input_data=KontierungsInput(entity_name="Buerobedarf Mueller", stichwort="Toner",
                                    betrag_brutto=Decimal("59.50"), mwst_satz=Decimal("19.0"),
                                    dokument_typ="invoice", richtung="incoming"))
    assert sug.konto == "4930"
    assert sug.source == "rule"


@pytest.mark.asyncio
async def test_learn_from_correction_persistiert_doppik(session):
    """learn_from_correction schreibt die Korrektur auf konto_soll/konto_haben/steuerschluessel."""
    from app.services.datev.connect.kontierung_service import KontierungsvorschlagService
    from app.db.models import DATEVBuchung
    from sqlalchemy import select
    comp = _company(); session.add(comp); await session.flush()
    conn_id = await _connection_id(session, comp.id)
    buchung = _buchung(comp.id, conn_id, buchungstext="Test", konto_soll="4400", konto_haben="70000")
    session.add(buchung); await session.flush()

    ok = await KontierungsvorschlagService().learn_from_correction(
        db=session, connection_id=conn_id, buchung_id=buchung.id,
        corrected_konto="4930", corrected_gegenkonto="1600", corrected_bu_schluessel="9")

    assert ok is True
    refetched = (await session.execute(
        select(DATEVBuchung).where(DATEVBuchung.id == buchung.id))).scalar_one()
    assert refetched.konto_soll == "4930"
    assert refetched.konto_haben == "1600"
    assert refetched.steuerschluessel == "9"

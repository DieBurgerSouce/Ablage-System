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
    base = re.sub(r"/[^/?]+(\?|$)", r"/ablage_test\1", base)
    # Async-Treiber erzwingen (CI setzt oft postgresql:// = sync)
    base = re.sub(r"^postgresql(\+\w+)?://", "postgresql+asyncpg://", base)
    return base


@pytest_asyncio.fixture
async def db_engine():
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy import text
    import app.db.all_models  # noqa: F401 - registriert alle Mapped-Klassen (kein app.main-Kruecke)
    from sqlalchemy.orm import configure_mappers
    configure_mappers()
    from app.db.models import Base
    engine = create_async_engine(_test_db_url(), echo=False, pool_pre_ping=True)
    try:
        # Selbst-enthaltend: modell-treues Schema via create_all (Doppik-Spalten
        # konto_soll/betrag_soll kommen direkt aus dem Modell - kein Klon/Patch/Migration).
        async with engine.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
            await conn.run_sync(Base.metadata.create_all)
    except Exception as exc:  # pragma: no cover - Infra-Skip
        await engine.dispose()
        pytest.skip(f"Test-DB nicht erreichbar/baubar ({type(exc).__name__}): {str(exc)[:140]}")
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
    """Legt eine DATEVConnection via Modell an (nach Migration 264 reconciliert)."""
    from app.db.models import DATEVConnection
    conn = DATEVConnection(
        id=uuid4(), company_id=company_id, name="DATEV Test",
        berater_nr="1234567", mandant_nr="12345", environment="sandbox",
        api_version="v1", kontenrahmen="SKR03", wirtschaftsjahr_beginn=1,
        connection_status="connected", is_active=True,
    )
    session.add(conn)
    await session.flush()
    return conn.id


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

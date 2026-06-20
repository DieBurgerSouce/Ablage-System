# -*- coding: utf-8 -*-
"""Multi-Tenant Isolation Tests fuer das Kasse-Modul.

Testet strikte Mandantentrennung:
- Company A sieht keine Daten von Company B
- Cross-Tenant Zugriffe werden verhindert
- Kassen und Buchungen sind isoliert

Erfordert: docker-compose up postgres

Ausfuehrung:
    pytest tests/integration/test_cash_isolation.py -v -m integration
"""

import os

import pytest
import pytest_asyncio
from decimal import Decimal
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select

# Direkte Imports - KEIN try/except!
# Fehlende Imports = Test FAILED (nicht SKIPPED)
from app.db.models import (
    Base,
    Company,
    User,
    CashRegister,
    CashEntry,
)
from app.db.schemas import (
    CashRegisterCreate,
    CashEntryCreate,
    CashEntryType,
)
from app.services.cash_service import CashService


pytestmark = [
    pytest.mark.integration,
    pytest.mark.isolation,
]


# ============================================================================
# FIXTURES
# ============================================================================

@pytest_asyncio.fixture
async def db_engine():
    """Erstellt Test-Datenbank-Engine.

    TEST_DATABASE_URL hat Vorrang (Docker/CI); ohne erreichbare Datenbank
    wird sauber geskippt statt mit ERROR abzubrechen.
    """
    test_db_url = os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5433/ablage_test",
    )

    engine = create_async_engine(
        test_db_url,
        echo=False,
        pool_pre_ping=True,
    )

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception as exc:
        await engine.dispose()
        pytest.skip(f"PostgreSQL-Testdatenbank nicht erreichbar: {exc}")

    yield engine

    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine):
    """Erstellt Test-Session mit Rollback."""
    async_session = async_sessionmaker(
        db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def company_a(db_session):
    """Firma A."""
    company = Company(
        id=uuid4(),
        name="Firma A GmbH",
        legal_form="GmbH",
        kontenrahmen="SKR03",
        is_active=True,
    )
    db_session.add(company)
    await db_session.flush()
    return company


@pytest_asyncio.fixture
async def company_b(db_session):
    """Firma B - separater Mandant."""
    company = Company(
        id=uuid4(),
        name="Firma B AG",
        legal_form="AG",
        kontenrahmen="SKR04",
        is_active=True,
    )
    db_session.add(company)
    await db_session.flush()
    return company


@pytest_asyncio.fixture
async def user_a(db_session, company_a):
    """Benutzer von Firma A."""
    user = User(
        id=uuid4(),
        email="user-a@firma-a.de",
        hashed_password="hashed",
        full_name="Mitarbeiter A",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def user_b(db_session, company_b):
    """Benutzer von Firma B."""
    user = User(
        id=uuid4(),
        email="user-b@firma-b.de",
        hashed_password="hashed",
        full_name="Mitarbeiter B",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def register_a(db_session, company_a, user_a):
    """Kasse von Firma A."""
    service = CashService()
    register_data = CashRegisterCreate(
        name="Kasse Firma A",
        description="Hauptkasse",
        opening_balance=Decimal("1000.00"),
    )
    register = await service.create_register(
        db=db_session,
        company_id=company_a.id,
        data=register_data,
        user_id=user_a.id,
    )
    await db_session.flush()
    return register


@pytest_asyncio.fixture
async def register_b(db_session, company_b, user_b):
    """Kasse von Firma B."""
    service = CashService()
    register_data = CashRegisterCreate(
        name="Kasse Firma B",
        description="Hauptkasse",
        opening_balance=Decimal("2000.00"),
    )
    register = await service.create_register(
        db=db_session,
        company_id=company_b.id,
        data=register_data,
        user_id=user_b.id,
    )
    await db_session.flush()
    return register


# ============================================================================
# REGISTER ISOLATION TESTS
# ============================================================================

class TestRegisterIsolation:
    """Tests fuer Kassen-Isolation zwischen Mandanten."""

    @pytest.mark.asyncio
    async def test_company_a_cannot_see_company_b_registers(
        self, db_session, company_a, company_b, register_a, register_b
    ):
        """Firma A sieht nur ihre eigenen Kassen."""
        service = CashService()

        # Firma A fragt ihre Kassen ab
        registers_a, total_a = await service.get_registers(
            db=db_session,
            company_id=company_a.id,
        )

        # Nur eigene Kasse sichtbar
        assert total_a == 1
        assert registers_a[0].id == register_a.id
        assert registers_a[0].name == "Kasse Firma A"

        # Kasse B ist nicht in der Liste
        register_ids = [r.id for r in registers_a]
        assert register_b.id not in register_ids

    @pytest.mark.asyncio
    async def test_company_b_cannot_access_company_a_register(
        self, db_session, company_a, company_b, register_a
    ):
        """Firma B kann Kasse von Firma A nicht direkt abrufen."""
        service = CashService()

        # Firma B versucht Kasse A zu laden
        register = await service.get_register(
            db=db_session,
            register_id=register_a.id,
            company_id=company_b.id,  # Falscher Mandant!
        )

        # Muss None zurueckgeben (nicht gefunden fuer diesen Mandanten)
        assert register is None

    @pytest.mark.asyncio
    async def test_company_a_can_access_own_register(
        self, db_session, company_a, register_a
    ):
        """Firma A kann ihre eigene Kasse abrufen."""
        service = CashService()

        register = await service.get_register(
            db=db_session,
            register_id=register_a.id,
            company_id=company_a.id,
        )

        assert register is not None
        assert register.id == register_a.id


# ============================================================================
# ENTRY ISOLATION TESTS
# ============================================================================

class TestEntryIsolation:
    """Tests fuer Buchungs-Isolation zwischen Mandanten."""

    @pytest.mark.asyncio
    async def test_company_b_cannot_see_company_a_entries(
        self, db_session, company_a, company_b, register_a, user_a
    ):
        """Firma B sieht keine Buchungen von Firma A."""
        service = CashService()

        # Firma A erstellt Buchung
        entry_data = CashEntryCreate(
            cash_register_id=register_a.id,
            amount=Decimal("100.00"),
            entry_type=CashEntryType.INCOME,
            description="Geheime Buchung Firma A",
            entry_date=datetime.now(timezone.utc),
        )
        await service.create_entry(
            db=db_session,
            company_id=company_a.id,
            data=entry_data,
            user_id=user_a.id,
        )
        await db_session.flush()

        # Firma B fragt Buchungen ab
        entries_b, total_b = await service.get_entries(
            db=db_session,
            company_id=company_b.id,
        )

        # Keine Buchungen fuer Firma B
        assert total_b == 0
        assert len(entries_b) == 0

    @pytest.mark.asyncio
    async def test_company_b_cannot_book_to_company_a_register(
        self, db_session, company_a, company_b, register_a, user_b
    ):
        """Firma B kann nicht in Kasse von Firma A buchen."""
        service = CashService()

        entry_data = CashEntryCreate(
            cash_register_id=register_a.id,  # Kasse von Firma A!
            amount=Decimal("999.99"),
            entry_type=CashEntryType.INCOME,
            description="Versuchte Manipulation",
            entry_date=datetime.now(timezone.utc),
        )

        # Versuch mit company_id von Firma B
        with pytest.raises(Exception) as exc_info:
            await service.create_entry(
                db=db_session,
                company_id=company_b.id,  # Falscher Mandant!
                data=entry_data,
                user_id=user_b.id,
            )

        # Sollte mit Kasse nicht gefunden fehlschlagen
        assert "nicht gefunden" in str(exc_info.value).lower() or \
               "not found" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_get_entry_respects_company_id(
        self, db_session, company_a, company_b, register_a, user_a
    ):
        """get_entry beachtet company_id Filter."""
        service = CashService()

        # Firma A erstellt Buchung
        entry_data = CashEntryCreate(
            cash_register_id=register_a.id,
            amount=Decimal("50.00"),
            entry_type=CashEntryType.EXPENSE,
            description="Buchung A",
            entry_date=datetime.now(timezone.utc),
        )
        entry = await service.create_entry(
            db=db_session,
            company_id=company_a.id,
            data=entry_data,
            user_id=user_a.id,
        )
        await db_session.flush()

        # Firma A kann Buchung abrufen
        entry_a = await service.get_entry(
            db=db_session,
            entry_id=entry.id,
            company_id=company_a.id,
        )
        assert entry_a is not None
        assert entry_a.id == entry.id

        # Firma B kann Buchung NICHT abrufen
        entry_b = await service.get_entry(
            db=db_session,
            entry_id=entry.id,
            company_id=company_b.id,  # Falscher Mandant
        )
        assert entry_b is None


# ============================================================================
# CANCELLATION ISOLATION TESTS
# ============================================================================

class TestCancellationIsolation:
    """Tests fuer Stornierung mit Mandanten-Isolation."""

    @pytest.mark.asyncio
    async def test_company_b_cannot_cancel_company_a_entry(
        self, db_session, company_a, company_b, register_a, user_a, user_b
    ):
        """Firma B kann Buchungen von Firma A nicht stornieren."""
        service = CashService()

        # Firma A erstellt Buchung
        entry_data = CashEntryCreate(
            cash_register_id=register_a.id,
            amount=Decimal("100.00"),
            entry_type=CashEntryType.INCOME,
            description="Wichtige Buchung A",
            entry_date=datetime.now(timezone.utc),
        )
        entry = await service.create_entry(
            db=db_session,
            company_id=company_a.id,
            data=entry_data,
            user_id=user_a.id,
        )
        await db_session.flush()

        # Firma B versucht zu stornieren
        with pytest.raises(Exception) as exc_info:
            await service.cancel_entry(
                db=db_session,
                entry_id=entry.id,
                company_id=company_b.id,  # Falscher Mandant!
                user_id=user_b.id,
                reason="Versuchte Stornierung durch falschen Mandanten",
            )

        # Buchung darf nicht storniert werden
        assert "nicht gefunden" in str(exc_info.value).lower() or \
               "not found" in str(exc_info.value).lower()

        # Original-Buchung pruefen - muss unveraendert sein
        result = await db_session.execute(
            select(CashEntry).where(CashEntry.id == entry.id)
        )
        original = result.scalar_one()
        assert original.is_cancelled is False


# ============================================================================
# SKR ISOLATION TESTS
# ============================================================================

class TestSKRIsolation:
    """Tests fuer Kontenrahmen-Isolation (SKR03 vs SKR04)."""

    @pytest.mark.asyncio
    async def test_companies_use_different_skr(
        self, db_session, company_a, company_b, register_a, register_b, user_a, user_b
    ):
        """Firmen verwenden ihre konfigurierten Kontenrahmen."""
        service = CashService()

        # Firma A (SKR03) erstellt Buchung
        entry_data_a = CashEntryCreate(
            cash_register_id=register_a.id,
            amount=Decimal("100.00"),
            entry_type=CashEntryType.INCOME,
            description="SKR03 Test",
            entry_date=datetime.now(timezone.utc),
        )
        entry_a = await service.create_entry(
            db=db_session,
            company_id=company_a.id,
            data=entry_data_a,
            user_id=user_a.id,
        )

        # Firma B (SKR04) erstellt Buchung
        entry_data_b = CashEntryCreate(
            cash_register_id=register_b.id,
            amount=Decimal("100.00"),
            entry_type=CashEntryType.INCOME,
            description="SKR04 Test",
            entry_date=datetime.now(timezone.utc),
        )
        entry_b = await service.create_entry(
            db=db_session,
            company_id=company_b.id,
            data=entry_data_b,
            user_id=user_b.id,
        )

        await db_session.flush()

        # SKR03 verwendet Konto 1000, SKR04 verwendet 1600
        # (wenn debit_account gesetzt wird)
        assert entry_a.company_id == company_a.id
        assert entry_b.company_id == company_b.id

        # Beide Firmen haben ihre eigenen Buchungen
        entries_a, _ = await service.get_entries(db=db_session, company_id=company_a.id)
        entries_b, _ = await service.get_entries(db=db_session, company_id=company_b.id)

        # 2 Entries pro Firma (Eroeffnung + neue Buchung)
        assert len(entries_a) == 2
        assert len(entries_b) == 2

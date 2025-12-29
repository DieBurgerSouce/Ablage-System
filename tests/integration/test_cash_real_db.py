# -*- coding: utf-8 -*-
"""Echte Integration-Tests fuer das Kasse-Modul mit PostgreSQL.

Diese Tests nutzen echte Datenbankoperationen und validieren:
- Persistierung von Eintraegen
- Saldo-Berechnung
- Entry-Nummer-Vergabe
- GoBD-Compliance (APPEND-ONLY)

Erfordert: docker-compose up postgres

Ausfuehrung:
    pytest tests/integration/test_cash_real_db.py -v -m integration
"""

import pytest
import pytest_asyncio
from decimal import Decimal
from datetime import date, datetime, timezone
from uuid import uuid4
import asyncio

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select, text

# Direkte Imports - KEIN try/except!
# Fehlende Imports = Test FAILED (nicht SKIPPED)
from app.db.models import (
    Base,
    Company,
    User,
    CashRegister,
    CashEntry,
    CashCategory,
    CashCount,
)
from app.db.schemas import (
    CashRegisterCreate,
    CashEntryCreate,
    CashEntryType,
    CashCountCreate,
)
from app.services.cash_service import CashService


pytestmark = [
    pytest.mark.integration,
]


# ============================================================================
# FIXTURES
# ============================================================================

@pytest_asyncio.fixture
async def db_engine():
    """Erstellt Test-Datenbank-Engine mit PostgreSQL."""
    # Nutze Test-Datenbank-URL
    # Bei Docker: postgresql+asyncpg://postgres:postgres@localhost:5433/ablage_test
    test_db_url = "postgresql+asyncpg://postgres:postgres@localhost:5433/ablage_test"

    engine = create_async_engine(
        test_db_url,
        echo=False,
        pool_pre_ping=True,
    )

    # Tabellen erstellen falls nicht vorhanden
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine):
    """Erstellt Test-Session mit Rollback nach jedem Test."""
    async_session = async_sessionmaker(
        db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def test_company(db_session):
    """Erstellt Test-Firma."""
    company = Company(
        id=uuid4(),
        name="Test GmbH",
        legal_form="GmbH",
        kontenrahmen="SKR03",
        is_active=True,
    )
    db_session.add(company)
    await db_session.flush()
    return company


@pytest_asyncio.fixture
async def test_user(db_session, test_company):
    """Erstellt Test-Benutzer."""
    user = User(
        id=uuid4(),
        email="test@example.com",
        hashed_password="hashed",
        full_name="Test User",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def cash_service():
    """CashService Instanz."""
    return CashService()


@pytest_asyncio.fixture
async def test_register(db_session, test_company, cash_service, test_user):
    """Erstellt Test-Kasse mit Eroeffnungsbuchung."""
    register_data = CashRegisterCreate(
        name="Hauptkasse",
        description="Test-Kasse",
        opening_balance=Decimal("500.00"),
    )

    register = await cash_service.create_register(
        db=db_session,
        company_id=test_company.id,
        data=register_data,
        user_id=test_user.id,
    )
    await db_session.flush()
    return register


# ============================================================================
# ECHTE PERSISTIERUNG TESTS
# ============================================================================

class TestCashEntryPersistence:
    """Tests fuer echte Datenpersistierung."""

    @pytest.mark.asyncio
    async def test_entry_persisted_to_database(
        self, db_session, test_company, test_register, cash_service, test_user
    ):
        """Entry wird wirklich in DB gespeichert."""
        entry_data = CashEntryCreate(
            cash_register_id=test_register.id,
            amount=Decimal("100.00"),
            entry_type=CashEntryType.INCOME,
            description="Test-Einnahme",
            entry_date=datetime.now(timezone.utc),
        )

        entry = await cash_service.create_entry(
            db=db_session,
            company_id=test_company.id,
            data=entry_data,
            user_id=test_user.id,
        )
        await db_session.flush()

        # Frischer Query - nicht aus Session-Cache
        result = await db_session.execute(
            select(CashEntry).where(CashEntry.id == entry.id)
        )
        persisted = result.scalar_one()

        assert persisted.amount == Decimal("100.00")
        assert persisted.description == "Test-Einnahme"
        assert persisted.entry_number == 2  # Nach Eroeffnungsbuchung

    @pytest.mark.asyncio
    async def test_balance_updated_after_entry(
        self, db_session, test_company, test_register, cash_service, test_user
    ):
        """Saldo wird korrekt aktualisiert."""
        initial_balance = Decimal(str(test_register.current_balance))

        entry_data = CashEntryCreate(
            cash_register_id=test_register.id,
            amount=Decimal("50.00"),
            entry_type=CashEntryType.INCOME,
            description="Einnahme",
            entry_date=datetime.now(timezone.utc),
        )

        await cash_service.create_entry(
            db=db_session,
            company_id=test_company.id,
            data=entry_data,
            user_id=test_user.id,
        )
        await db_session.flush()

        # Register neu laden
        result = await db_session.execute(
            select(CashRegister).where(CashRegister.id == test_register.id)
        )
        updated_register = result.scalar_one()

        expected_balance = initial_balance + Decimal("50.00")
        assert Decimal(str(updated_register.current_balance)) == expected_balance

    @pytest.mark.asyncio
    async def test_entry_number_sequential(
        self, db_session, test_company, test_register, cash_service, test_user
    ):
        """Entry-Nummern sind sequentiell und lueckenlos."""
        # 3 Eintraege erstellen
        for i in range(3):
            entry_data = CashEntryCreate(
                cash_register_id=test_register.id,
                amount=Decimal("10.00"),
                entry_type=CashEntryType.INCOME,
                description=f"Entry {i+1}",
                entry_date=datetime.now(timezone.utc),
            )
            await cash_service.create_entry(
                db=db_session,
                company_id=test_company.id,
                data=entry_data,
                user_id=test_user.id,
            )

        await db_session.flush()

        # Alle Entries laden
        result = await db_session.execute(
            select(CashEntry)
            .where(CashEntry.cash_register_id == test_register.id)
            .order_by(CashEntry.entry_number)
        )
        entries = result.scalars().all()

        numbers = [e.entry_number for e in entries]
        # 1 (Eroeffnung) + 3 neue = 4 Entries
        assert numbers == [1, 2, 3, 4]


class TestCashEntryCancellation:
    """Tests fuer GoBD-konforme Stornierung."""

    @pytest.mark.asyncio
    async def test_cancellation_creates_counter_entry(
        self, db_session, test_company, test_register, cash_service, test_user
    ):
        """Stornierung erstellt Gegenbuchung (APPEND-ONLY)."""
        # Entry erstellen
        entry_data = CashEntryCreate(
            cash_register_id=test_register.id,
            amount=Decimal("100.00"),
            entry_type=CashEntryType.EXPENSE,
            description="Ausgabe zum Stornieren",
            entry_date=datetime.now(timezone.utc),
        )

        entry = await cash_service.create_entry(
            db=db_session,
            company_id=test_company.id,
            data=entry_data,
            user_id=test_user.id,
        )
        await db_session.flush()

        # Stornieren
        cancel_entry = await cash_service.cancel_entry(
            db=db_session,
            entry_id=entry.id,
            company_id=test_company.id,
            user_id=test_user.id,
            reason="Test-Stornierung",
        )
        await db_session.flush()

        # Original ist als storniert markiert
        result = await db_session.execute(
            select(CashEntry).where(CashEntry.id == entry.id)
        )
        original = result.scalar_one()
        assert original.is_cancelled is True

        # Gegenbuchung existiert
        assert cancel_entry is not None
        assert cancel_entry.amount == -Decimal("100.00")  # Umgekehrtes Vorzeichen
        assert "Storno" in cancel_entry.description


class TestCashCount:
    """Tests fuer Kassensturz."""

    @pytest.mark.asyncio
    async def test_cash_count_with_difference(
        self, db_session, test_company, test_register, cash_service, test_user
    ):
        """Kassensturz mit Differenz erstellt Ausgleichsbuchung."""
        # Register-Saldo: 500 EUR
        # Gezaehlt: 480 EUR -> Differenz -20 EUR

        count_data = CashCountCreate(
            cash_register_id=test_register.id,
            counted_amount=Decimal("480.00"),
            count_date=datetime.now(timezone.utc),
            notes="Test-Kassensturz",
            # Minimal-Zaehlung
            notes_50_euro=9,
            coins_2_euro=10,
            coins_1_euro=10,
        )

        cash_count = await cash_service.perform_cash_count(
            db=db_session,
            company_id=test_company.id,
            data=count_data,
            user_id=test_user.id,
        )
        await db_session.flush()

        assert cash_count.expected_amount == Decimal("500.00")
        assert cash_count.counted_amount == Decimal("480.00")
        assert cash_count.difference == Decimal("-20.00")
        assert cash_count.adjustment_entry_id is not None  # Ausgleichsbuchung erstellt


# ============================================================================
# GOBD COMPLIANCE TESTS
# ============================================================================

class TestGoBDCompliance:
    """Tests fuer GoBD-konforme Kassenbuchfuehrung."""

    @pytest.mark.asyncio
    async def test_no_update_possible(
        self, db_session, test_company, test_register, cash_service, test_user
    ):
        """Direkte UPDATEs auf Entries sind durch Trigger verboten."""
        entry_data = CashEntryCreate(
            cash_register_id=test_register.id,
            amount=Decimal("100.00"),
            entry_type=CashEntryType.INCOME,
            description="Test",
            entry_date=datetime.now(timezone.utc),
        )

        entry = await cash_service.create_entry(
            db=db_session,
            company_id=test_company.id,
            data=entry_data,
            user_id=test_user.id,
        )
        await db_session.flush()

        # Versuch direkt zu aendern sollte fehlschlagen (PostgreSQL Trigger)
        try:
            await db_session.execute(
                text(f"""
                    UPDATE cash_entries
                    SET amount = 9999
                    WHERE id = '{entry.id}'
                """)
            )
            await db_session.commit()
            # Wenn wir hier ankommen, hat der Trigger nicht gegriffen
            pytest.fail("UPDATE sollte durch Trigger verhindert werden")
        except Exception as e:
            # Erwarteter Fehler - Trigger hat UPDATE verhindert
            assert "GoBD" in str(e) or "cannot" in str(e).lower()
            await db_session.rollback()

    @pytest.mark.asyncio
    async def test_no_delete_possible(
        self, db_session, test_company, test_register, cash_service, test_user
    ):
        """Direkte DELETEs auf Entries sind durch Trigger verboten."""
        entry_data = CashEntryCreate(
            cash_register_id=test_register.id,
            amount=Decimal("100.00"),
            entry_type=CashEntryType.INCOME,
            description="Test",
            entry_date=datetime.now(timezone.utc),
        )

        entry = await cash_service.create_entry(
            db=db_session,
            company_id=test_company.id,
            data=entry_data,
            user_id=test_user.id,
        )
        await db_session.flush()

        # Versuch direkt zu loeschen sollte fehlschlagen
        try:
            await db_session.execute(
                text(f"DELETE FROM cash_entries WHERE id = '{entry.id}'")
            )
            await db_session.commit()
            pytest.fail("DELETE sollte durch Trigger verhindert werden")
        except Exception as e:
            assert "GoBD" in str(e) or "cannot" in str(e).lower()
            await db_session.rollback()

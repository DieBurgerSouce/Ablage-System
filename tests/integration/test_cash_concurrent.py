# -*- coding: utf-8 -*-
"""Concurrent Access Tests fuer das Kasse-Modul.

Testet Thread-Safety und Race Conditions:
- Parallele Entry-Erstellung ohne doppelte Nummern
- Parallele Kassensturz-Operationen
- Lock-Mechanismus bei hoher Last

Erfordert: docker-compose up postgres

Ausfuehrung:
    pytest tests/integration/test_cash_concurrent.py -v -m integration
"""

import os

import pytest
import pytest_asyncio
from decimal import Decimal
from datetime import datetime, timezone
from uuid import uuid4
import asyncio
from typing import List

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
    pytest.mark.concurrent,
]


# ============================================================================
# FIXTURES
# ============================================================================

@pytest_asyncio.fixture
async def db_engine():
    """Erstellt Test-Datenbank-Engine mit PostgreSQL.

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
        pool_size=20,  # Genug Connections fuer parallele Tests
        max_overflow=10,
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
async def session_factory(db_engine):
    """Session Factory fuer parallele Sessions."""
    return async_sessionmaker(
        db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


@pytest_asyncio.fixture
async def test_company(session_factory):
    """Erstellt Test-Firma."""
    async with session_factory() as session:
        company = Company(
            id=uuid4(),
            name="Concurrent Test GmbH",
            legal_form="GmbH",
            kontenrahmen="SKR03",
            is_active=True,
        )
        session.add(company)
        await session.commit()
        return company


@pytest_asyncio.fixture
async def test_user(session_factory, test_company):
    """Erstellt Test-Benutzer."""
    async with session_factory() as session:
        user = User(
            id=uuid4(),
            email="concurrent-test@example.com",
            hashed_password="hashed",
            full_name="Concurrent Test User",
            is_active=True,
        )
        session.add(user)
        await session.commit()
        return user


@pytest_asyncio.fixture
async def test_register(session_factory, test_company, test_user):
    """Erstellt Test-Kasse."""
    async with session_factory() as session:
        service = CashService()
        register_data = CashRegisterCreate(
            name="Concurrent Test Kasse",
            description="Fuer Parallel-Tests",
            opening_balance=Decimal("1000.00"),
        )
        register = await service.create_register(
            db=session,
            company_id=test_company.id,
            data=register_data,
            user_id=test_user.id,
        )
        await session.commit()
        return register


# ============================================================================
# CONCURRENT ENTRY TESTS
# ============================================================================

class TestConcurrentEntryCreation:
    """Tests fuer parallele Buchungserstellung."""

    @pytest.mark.asyncio
    async def test_parallel_entries_unique_numbers(
        self, session_factory, test_company, test_register, test_user
    ):
        """10 parallele Buchungen haben alle eindeutige Entry-Nummern."""
        num_entries = 10
        results: List[CashEntry] = []
        errors: List[Exception] = []

        async def create_entry_task(index: int) -> CashEntry:
            """Erstellt einen Entry in eigener Session."""
            async with session_factory() as session:
                service = CashService()
                entry_data = CashEntryCreate(
                    cash_register_id=test_register.id,
                    amount=Decimal("10.00"),
                    entry_type=CashEntryType.INCOME,
                    description=f"Parallel-Entry-{index}",
                    entry_date=datetime.now(timezone.utc),
                )
                entry = await service.create_entry(
                    db=session,
                    company_id=test_company.id,
                    data=entry_data,
                    user_id=test_user.id,
                )
                await session.commit()
                return entry

        # Alle Tasks gleichzeitig starten
        tasks = [create_entry_task(i) for i in range(num_entries)]
        task_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Ergebnisse auswerten
        for result in task_results:
            if isinstance(result, Exception):
                errors.append(result)
            else:
                results.append(result)

        # Keine Fehler erwartet
        assert len(errors) == 0, f"Fehler bei parallelen Entries: {errors}"

        # Alle Entries erfolgreich
        assert len(results) == num_entries

        # Entry-Nummern pruefen - alle muessen eindeutig sein
        entry_numbers = [e.entry_number for e in results]
        unique_numbers = set(entry_numbers)

        assert len(entry_numbers) == len(unique_numbers), \
            f"Doppelte Entry-Nummern gefunden! {entry_numbers}"

        # Nummern muessen sequentiell sein (2-11 nach Eroeffnung mit Nr. 1)
        expected_numbers = set(range(2, num_entries + 2))
        assert unique_numbers == expected_numbers, \
            f"Entry-Nummern nicht sequentiell: erwartet {expected_numbers}, bekommen {unique_numbers}"

    @pytest.mark.asyncio
    async def test_parallel_entries_balance_consistent(
        self, session_factory, test_company, test_register, test_user
    ):
        """Saldo bleibt nach parallelen Buchungen konsistent."""
        num_entries = 5
        amount_per_entry = Decimal("20.00")
        initial_balance = Decimal("1000.00")  # Opening balance

        async def create_entry_task(index: int):
            async with session_factory() as session:
                service = CashService()
                entry_data = CashEntryCreate(
                    cash_register_id=test_register.id,
                    amount=amount_per_entry,
                    entry_type=CashEntryType.INCOME,
                    description=f"Balance-Test-{index}",
                    entry_date=datetime.now(timezone.utc),
                )
                await service.create_entry(
                    db=session,
                    company_id=test_company.id,
                    data=entry_data,
                    user_id=test_user.id,
                )
                await session.commit()

        # Parallel ausfuehren
        tasks = [create_entry_task(i) for i in range(num_entries)]
        await asyncio.gather(*tasks)

        # Endgueltige Balance pruefen
        async with session_factory() as session:
            result = await session.execute(
                select(CashRegister).where(CashRegister.id == test_register.id)
            )
            register = result.scalar_one()

            expected_balance = initial_balance + (amount_per_entry * num_entries)
            actual_balance = Decimal(str(register.current_balance))

            assert actual_balance == expected_balance, \
                f"Balance inkonsistent: erwartet {expected_balance}, bekommen {actual_balance}"

    @pytest.mark.asyncio
    async def test_high_load_no_deadlocks(
        self, session_factory, test_company, test_register, test_user
    ):
        """25 parallele Buchungen verursachen keine Deadlocks."""
        num_entries = 25
        completed = 0
        errors = []

        async def create_entry_task(index: int):
            nonlocal completed
            try:
                async with session_factory() as session:
                    service = CashService()
                    entry_data = CashEntryCreate(
                        cash_register_id=test_register.id,
                        amount=Decimal("5.00"),
                        entry_type=CashEntryType.INCOME if index % 2 == 0 else CashEntryType.EXPENSE,
                        description=f"High-Load-{index}",
                        entry_date=datetime.now(timezone.utc),
                    )
                    await service.create_entry(
                        db=session,
                        company_id=test_company.id,
                        data=entry_data,
                        user_id=test_user.id,
                    )
                    await session.commit()
                    completed += 1
            except Exception as e:
                errors.append((index, str(e)))

        # Alle gleichzeitig
        tasks = [create_entry_task(i) for i in range(num_entries)]
        await asyncio.gather(*tasks)

        # Alle sollten erfolgreich sein
        assert len(errors) == 0, f"Fehler unter Last: {errors}"
        assert completed == num_entries


class TestConcurrentCashCount:
    """Tests fuer parallele Kassensturz-Operationen."""

    @pytest.mark.asyncio
    async def test_parallel_counts_isolated(
        self, session_factory, test_company, test_user
    ):
        """Parallele Kassenstuerze auf verschiedenen Kassen sind isoliert."""
        # Zwei separate Kassen erstellen
        registers = []
        for i in range(2):
            async with session_factory() as session:
                service = CashService()
                register_data = CashRegisterCreate(
                    name=f"Parallel-Kasse-{i}",
                    description=f"Fuer Parallel-Test {i}",
                    opening_balance=Decimal("500.00"),
                )
                register = await service.create_register(
                    db=session,
                    company_id=test_company.id,
                    data=register_data,
                    user_id=test_user.id,
                )
                await session.commit()
                registers.append(register)

        # Parallele Buchungen auf beiden Kassen
        async def book_on_register(register_id, index):
            async with session_factory() as session:
                service = CashService()
                entry_data = CashEntryCreate(
                    cash_register_id=register_id,
                    amount=Decimal("50.00"),
                    entry_type=CashEntryType.INCOME,
                    description=f"Isolation-Test-{index}",
                    entry_date=datetime.now(timezone.utc),
                )
                await service.create_entry(
                    db=session,
                    company_id=test_company.id,
                    data=entry_data,
                    user_id=test_user.id,
                )
                await session.commit()

        # 5 Buchungen pro Kasse, parallel
        tasks = []
        for reg in registers:
            for i in range(5):
                tasks.append(book_on_register(reg.id, i))

        await asyncio.gather(*tasks)

        # Beide Kassen sollten 750 EUR haben (500 + 5*50)
        async with session_factory() as session:
            for reg in registers:
                result = await session.execute(
                    select(CashRegister).where(CashRegister.id == reg.id)
                )
                updated = result.scalar_one()
                assert Decimal(str(updated.current_balance)) == Decimal("750.00")

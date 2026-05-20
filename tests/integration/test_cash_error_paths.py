# -*- coding: utf-8 -*-
"""Error-Path Tests fuer das Kasse-Modul.

Diese Tests validieren das korrekte Fehlerverhalten:
- Ungueltige Eingaben werden abgelehnt
- Deaktivierte Kategorien koennen nicht verwendet werden
- Doppelte Stornierungen werden verhindert
- GoBD-Constraints werden eingehalten

WICHTIG: Kein Import-Skip Pattern! Tests sollen FAILED statt SKIPPED sein.
"""

import pytest
import pytest_asyncio
from decimal import Decimal
from datetime import date, datetime, timezone, timedelta
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch

# Direkte Imports - KEIN try/except! Fehler = Test FAILED
from app.db.schemas import (
    CashRegisterCreate,
    CashEntryCreate,
    CashEntryCancelRequest,
    CashEntryType,
)
from app.services.cash_service import CashService


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def cash_service():
    """CashService-Instanz fuer Tests."""
    return CashService()


@pytest.fixture
def mock_db():
    """Mock AsyncSession."""
    return AsyncMock()


@pytest.fixture
def valid_entry_data():
    """Gueltige Buchungsdaten als Basis."""
    return CashEntryCreate(
        cash_register_id=uuid4(),
        entry_type=CashEntryType.EXPENSE,
        entry_date=datetime.now(timezone.utc),
        amount=-50.00,
        description="Test-Buchung fuer Error-Path Tests",
        tax_rate=19.0,
    )


# ============================================================================
# VALIDIERUNG: DEAKTIVIERTE KATEGORIEN
# ============================================================================

@pytest.mark.asyncio
async def test_create_entry_with_inactive_category_raises_error(
    cash_service,
    mock_db,
):
    """Deaktivierte Kategorie muss ValueError werfen."""
    # Arrange
    company_id = uuid4()
    user_id = uuid4()

    # Mock: Kasse existiert
    mock_register = MagicMock()
    mock_register.id = uuid4()
    mock_register.company_id = company_id
    mock_register.current_balance = Decimal("1000.00")
    mock_register.is_active = True

    # Mock: Kategorie ist DEAKTIVIERT
    mock_category = MagicMock()
    mock_category.id = uuid4()
    mock_category.name = "Deaktivierte Kategorie"
    mock_category.is_active = False  # DEAKTIVIERT!

    async def mock_execute(stmt):
        result = MagicMock()
        # Unterscheide Queries anhand des Statements
        stmt_str = str(stmt)
        if "cash_registers" in stmt_str.lower():
            result.scalar_one_or_none.return_value = mock_register
        elif "cash_categories" in stmt_str.lower():
            result.scalar_one_or_none.return_value = mock_category
        else:
            result.scalar_one_or_none.return_value = None
        return result

    mock_db.execute = mock_execute

    entry_data = CashEntryCreate(
        cash_register_id=mock_register.id,
        category_id=mock_category.id,
        entry_type=CashEntryType.EXPENSE,
        entry_date=datetime.now(timezone.utc),
        amount=-50.00,
        description="Buchung mit deaktivierter Kategorie",
    )

    # Act & Assert
    with pytest.raises(ValueError) as exc_info:
        await cash_service.create_entry(
            db=mock_db,
            company_id=company_id,
            data=entry_data,
            user_id=user_id,
        )

    assert "deaktiviert" in str(exc_info.value).lower()


# ============================================================================
# VALIDIERUNG: BUCHUNGSDATUM IN ZUKUNFT
# ============================================================================

@pytest.mark.asyncio
async def test_create_entry_with_future_date_raises_error(
    cash_service,
    mock_db,
):
    """Buchungsdatum in der Zukunft muss ValueError werfen (GoBD!)."""
    # Arrange
    company_id = uuid4()
    user_id = uuid4()
    register_id = uuid4()

    future_date = datetime.now(timezone.utc) + timedelta(days=1)

    # Act & Assert - Validierung erfolgt im Pydantic Schema
    with pytest.raises(ValueError) as exc_info:
        CashEntryCreate(
            cash_register_id=register_id,
            entry_type=CashEntryType.EXPENSE,
            entry_date=future_date,
            amount=-50.00,
            description="Buchung in der Zukunft",
        )

    assert "zukunft" in str(exc_info.value).lower()


# ============================================================================
# VALIDIERUNG: BETRAG = 0
# ============================================================================

@pytest.mark.asyncio
async def test_create_entry_with_zero_amount_raises_error(
    cash_service,
    mock_db,
):
    """Betrag 0 muss ValueError werfen."""
    # Arrange
    register_id = uuid4()

    # Act & Assert - Validierung im Schema
    with pytest.raises(ValueError) as exc_info:
        CashEntryCreate(
            cash_register_id=register_id,
            entry_type=CashEntryType.EXPENSE,
            entry_date=datetime.now(timezone.utc),
            amount=0,  # UNGUELTIG!
            description="Buchung mit Betrag 0",
        )

    assert "0" in str(exc_info.value) or "darf nicht" in str(exc_info.value).lower()


# ============================================================================
# VALIDIERUNG: KASSE NICHT GEFUNDEN
# ============================================================================

@pytest.mark.asyncio
async def test_create_entry_with_nonexistent_register_raises_error(
    cash_service,
    mock_db,
):
    """Nicht existierende Kasse muss ValueError werfen."""
    # Arrange
    company_id = uuid4()
    user_id = uuid4()
    nonexistent_register_id = uuid4()

    async def mock_execute(stmt):
        result = MagicMock()
        result.scalar_one_or_none.return_value = None  # Kasse existiert nicht
        return result

    mock_db.execute = mock_execute

    entry_data = CashEntryCreate(
        cash_register_id=nonexistent_register_id,
        entry_type=CashEntryType.EXPENSE,
        entry_date=datetime.now(timezone.utc),
        amount=-50.00,
        description="Buchung auf nicht existierende Kasse",
    )

    # Act & Assert
    with pytest.raises(ValueError) as exc_info:
        await cash_service.create_entry(
            db=mock_db,
            company_id=company_id,
            data=entry_data,
            user_id=user_id,
        )

    assert "nicht gefunden" in str(exc_info.value).lower()


# ============================================================================
# VALIDIERUNG: KATEGORIE NICHT GEFUNDEN
# ============================================================================

@pytest.mark.asyncio
async def test_create_entry_with_nonexistent_category_raises_error(
    cash_service,
    mock_db,
):
    """Nicht existierende Kategorie muss ValueError werfen."""
    # Arrange
    company_id = uuid4()
    user_id = uuid4()

    mock_register = MagicMock()
    mock_register.id = uuid4()
    mock_register.company_id = company_id
    mock_register.current_balance = Decimal("1000.00")
    mock_register.is_active = True

    nonexistent_category_id = uuid4()

    async def mock_execute(stmt):
        result = MagicMock()
        stmt_str = str(stmt).lower()
        if "cash_registers" in stmt_str:
            result.scalar_one_or_none.return_value = mock_register
        elif "cash_categories" in stmt_str:
            result.scalar_one_or_none.return_value = None  # Kategorie existiert nicht
        else:
            result.scalar_one_or_none.return_value = None
        return result

    mock_db.execute = mock_execute

    entry_data = CashEntryCreate(
        cash_register_id=mock_register.id,
        category_id=nonexistent_category_id,
        entry_type=CashEntryType.EXPENSE,
        entry_date=datetime.now(timezone.utc),
        amount=-50.00,
        description="Buchung mit nicht existierender Kategorie",
    )

    # Act & Assert
    with pytest.raises(ValueError) as exc_info:
        await cash_service.create_entry(
            db=mock_db,
            company_id=company_id,
            data=entry_data,
            user_id=user_id,
        )

    assert "kategorie" in str(exc_info.value).lower()
    assert "nicht gefunden" in str(exc_info.value).lower()


# ============================================================================
# VALIDIERUNG: BEWIRTUNGSKOSTEN OHNE DATEN
# ============================================================================

@pytest.mark.asyncio
async def test_entertainment_entry_without_data_raises_error():
    """Bewirtungsbuchung ohne entertainment_data muss ValueError werfen."""
    register_id = uuid4()

    # Act & Assert - Validierung im Schema via model_validator
    with pytest.raises(ValueError) as exc_info:
        CashEntryCreate(
            cash_register_id=register_id,
            entry_type=CashEntryType.ENTERTAINMENT,  # Bewirtung!
            entry_date=datetime.now(timezone.utc),
            amount=-100.00,
            description="Bewirtung ohne Daten",
            entertainment_data=None,  # FEHLT!
        )

    assert "bewirtung" in str(exc_info.value).lower()


# ============================================================================
# VALIDIERUNG: BESCHREIBUNG ZU KURZ
# ============================================================================

def test_entry_with_short_description_raises_error():
    """Beschreibung mit weniger als 3 Zeichen muss ValueError werfen."""
    register_id = uuid4()

    with pytest.raises(ValueError):
        CashEntryCreate(
            cash_register_id=register_id,
            entry_type=CashEntryType.EXPENSE,
            entry_date=datetime.now(timezone.utc),
            amount=-50.00,
            description="AB",  # Nur 2 Zeichen - zu kurz!
        )


# ============================================================================
# VALIDIERUNG: MAX AMOUNT UEBERSCHRITTEN
# ============================================================================

def test_entry_with_excessive_amount_raises_error():
    """Betrag ueber Maximum muss ValueError werfen."""
    register_id = uuid4()

    # Das Maximum ist jetzt 9999999999999.99 (13 Stellen vor Komma)
    with pytest.raises(ValueError):
        CashEntryCreate(
            cash_register_id=register_id,
            entry_type=CashEntryType.EXPENSE,
            entry_date=datetime.now(timezone.utc),
            amount=-99999999999999.99,  # 14 Stellen - zu gross!
            description="Unrealistisch hoher Betrag",
        )


# ============================================================================
# VALIDIERUNG: STEUERSATZ UNGUELTIG
# ============================================================================

def test_entry_with_negative_tax_rate_raises_error():
    """Negativer Steuersatz muss ValueError werfen."""
    register_id = uuid4()

    with pytest.raises(ValueError):
        CashEntryCreate(
            cash_register_id=register_id,
            entry_type=CashEntryType.EXPENSE,
            entry_date=datetime.now(timezone.utc),
            amount=-50.00,
            description="Test mit negativem Steuersatz",
            tax_rate=-5.0,  # UNGUELTIG!
        )


def test_entry_with_excessive_tax_rate_raises_error():
    """Steuersatz ueber 100% muss ValueError werfen."""
    register_id = uuid4()

    with pytest.raises(ValueError):
        CashEntryCreate(
            cash_register_id=register_id,
            entry_type=CashEntryType.EXPENSE,
            entry_date=datetime.now(timezone.utc),
            amount=-50.00,
            description="Test mit zu hohem Steuersatz",
            tax_rate=150.0,  # UNGUELTIG!
        )

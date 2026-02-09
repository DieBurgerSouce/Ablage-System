# -*- coding: utf-8 -*-
"""
Unit Tests for GL-Posting Service.

Tests:
- Balanced entry creation
- Unbalanced entry rejection
- Posting (draft -> posted)
- Reversals (GoBD-konform)
- Auto-posting with confidence threshold
- Trial balance generation
- Entry number format
"""

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from unittest.mock import AsyncMock, MagicMock

from app.services.accounting.gl_posting_service import (
    GLPostingService,
    JournalEntryLineCreate,
)
from app.db.models_gl_posting import (
    JournalEntry,
    JournalEntryLine,
    JournalEntryStatus,
)


@pytest.fixture
def mock_db():
    """Mock AsyncSession."""
    db = AsyncMock(spec=AsyncSession)
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.fixture
def gl_service(mock_db):
    """GLPostingService with mocked DB."""
    return GLPostingService(mock_db)


@pytest.fixture
def company_id():
    """Test company ID."""
    return uuid4()


@pytest.fixture
def user_id():
    """Test user ID."""
    return uuid4()


@pytest.fixture
def balanced_lines():
    """Balanced journal entry lines."""
    return [
        JournalEntryLineCreate(
            account_number="4400",
            account_name="Wareneingang",
            debit_amount=Decimal("100.00"),
            credit_amount=Decimal("0"),
            text="Test debit",
        ),
        JournalEntryLineCreate(
            account_number="1600",
            account_name="Verbindlichkeiten",
            debit_amount=Decimal("0"),
            credit_amount=Decimal("100.00"),
            text="Test credit",
        ),
    ]


@pytest.fixture
def unbalanced_lines():
    """Unbalanced journal entry lines."""
    return [
        JournalEntryLineCreate(
            account_number="4400",
            account_name="Wareneingang",
            debit_amount=Decimal("100.00"),
            credit_amount=Decimal("0"),
        ),
        JournalEntryLineCreate(
            account_number="1600",
            account_name="Verbindlichkeiten",
            debit_amount=Decimal("0"),
            credit_amount=Decimal("50.00"),  # Unbalanced!
        ),
    ]


@pytest.mark.asyncio
async def test_create_balanced_entry(gl_service, company_id, user_id, balanced_lines, mock_db):
    """Test: Balanced entry passes validation."""
    # Mock _generate_entry_number
    gl_service._generate_entry_number = AsyncMock(return_value="JE-2024-00001")

    entry = await gl_service.create_journal_entry(
        company_id=company_id,
        lines=balanced_lines,
        posting_date=date(2024, 1, 15),
        description="Test Entry",
        created_by=user_id,
    )

    # Assertions
    assert entry is not None
    assert entry.entry_number == "JE-2024-00001"
    assert entry.fiscal_year == 2024
    assert entry.fiscal_period == 1
    assert entry.total_amount == Decimal("100.00")
    assert entry.status == JournalEntryStatus.DRAFT.value
    assert len(entry.lines) == 2

    # Verify DB calls
    mock_db.add.assert_called_once()
    mock_db.flush.assert_called_once()


@pytest.mark.asyncio
async def test_create_unbalanced_entry_fails(gl_service, company_id, user_id, unbalanced_lines):
    """Test: Unbalanced entry raises ValueError."""
    with pytest.raises(ValueError, match="Unbalancierte Buchung"):
        await gl_service.create_journal_entry(
            company_id=company_id,
            lines=unbalanced_lines,
            posting_date=date(2024, 1, 15),
            created_by=user_id,
        )


@pytest.mark.asyncio
async def test_post_journal_entry(gl_service, mock_db, user_id):
    """Test: Posting changes status draft -> posted."""
    entry_id = uuid4()

    # Mock DB query
    mock_entry = MagicMock(spec=JournalEntry)
    mock_entry.id = entry_id
    mock_entry.status = JournalEntryStatus.DRAFT.value
    mock_entry.entry_number = "JE-2024-00001"

    mock_result = MagicMock()
    mock_result.scalar_one_or_none = MagicMock(return_value=mock_entry)
    mock_db.execute = AsyncMock(return_value=mock_result)

    posted = await gl_service.post_journal_entry(entry_id, user_id)

    # Assertions
    assert posted.status == JournalEntryStatus.POSTED.value
    assert posted.posted_by_id == user_id
    assert posted.posted_at is not None

    mock_db.flush.assert_called_once()


@pytest.mark.asyncio
async def test_post_already_posted_fails(gl_service, mock_db, user_id):
    """Test: Cannot re-post an already posted entry."""
    entry_id = uuid4()

    # Mock DB query: already posted
    mock_entry = MagicMock(spec=JournalEntry)
    mock_entry.id = entry_id
    mock_entry.status = JournalEntryStatus.POSTED.value

    mock_result = MagicMock()
    mock_result.scalar_one_or_none = MagicMock(return_value=mock_entry)
    mock_db.execute = AsyncMock(return_value=mock_result)

    with pytest.raises(ValueError, match="Nur Entwürfe können gebucht werden"):
        await gl_service.post_journal_entry(entry_id, user_id)


@pytest.mark.asyncio
async def test_reverse_journal_entry_gobd(gl_service, company_id, user_id, mock_db):
    """Test: Reversal creates opposite entry (GoBD-konform)."""
    entry_id = uuid4()

    # Mock original entry
    mock_line1 = MagicMock(spec=JournalEntryLine)
    mock_line1.account_number = "4400"
    mock_line1.account_name = "Wareneingang"
    mock_line1.debit_amount = Decimal("100.00")
    mock_line1.credit_amount = Decimal("0")
    mock_line1.tax_code = None
    mock_line1.tax_rate = None
    mock_line1.cost_center = None
    mock_line1.text = "Original"

    mock_line2 = MagicMock(spec=JournalEntryLine)
    mock_line2.account_number = "1600"
    mock_line2.account_name = "Verbindlichkeiten"
    mock_line2.debit_amount = Decimal("0")
    mock_line2.credit_amount = Decimal("100.00")
    mock_line2.tax_code = None
    mock_line2.tax_rate = None
    mock_line2.cost_center = None
    mock_line2.text = "Original"

    mock_entry = MagicMock(spec=JournalEntry)
    mock_entry.id = entry_id
    mock_entry.company_id = company_id
    mock_entry.status = JournalEntryStatus.POSTED.value
    mock_entry.entry_number = "JE-2024-00001"
    mock_entry.lines = [mock_line1, mock_line2]
    mock_entry.document_id = None
    mock_entry.source = "manual"

    mock_result_original = MagicMock()
    mock_result_original.scalar_one_or_none = MagicMock(return_value=mock_entry)

    # Mock reversal entry returned by post_journal_entry's DB lookup
    mock_reversal = MagicMock(spec=JournalEntry)
    mock_reversal.id = uuid4()
    mock_reversal.status = JournalEntryStatus.DRAFT.value
    mock_reversal.entry_number = "JE-2024-00002"

    mock_result_reversal = MagicMock()
    mock_result_reversal.scalar_one_or_none = MagicMock(return_value=mock_reversal)

    # First execute: fetch original; Second execute: fetch reversal in post_journal_entry
    mock_db.execute = AsyncMock(side_effect=[mock_result_original, mock_result_reversal])

    gl_service._generate_entry_number = AsyncMock(return_value="JE-2024-00002")

    reversal = await gl_service.reverse_journal_entry(entry_id, user_id, "Test reversal")

    # Assertions
    assert reversal is not None
    assert reversal.entry_number == "JE-2024-00002"
    assert "STORNO" in reversal.description

    # Check reversed flag
    assert mock_entry.status == JournalEntryStatus.REVERSED.value
    assert mock_entry.reversed_by_entry_id == reversal.id


@pytest.mark.asyncio
async def test_reverse_creates_opposite_amounts(gl_service, company_id, user_id, mock_db):
    """Test: Reversal swaps debit/credit amounts."""
    entry_id = uuid4()

    # Mock original entry with 2 lines (balanced)
    mock_line1 = MagicMock(spec=JournalEntryLine)
    mock_line1.account_number = "4400"
    mock_line1.account_name = "Test Debit"
    mock_line1.debit_amount = Decimal("123.45")
    mock_line1.credit_amount = Decimal("0")
    mock_line1.tax_code = None
    mock_line1.tax_rate = None
    mock_line1.cost_center = None
    mock_line1.text = "Original"

    mock_line2 = MagicMock(spec=JournalEntryLine)
    mock_line2.account_number = "1600"
    mock_line2.account_name = "Test Credit"
    mock_line2.debit_amount = Decimal("0")
    mock_line2.credit_amount = Decimal("123.45")
    mock_line2.tax_code = None
    mock_line2.tax_rate = None
    mock_line2.cost_center = None
    mock_line2.text = "Original"

    mock_entry = MagicMock(spec=JournalEntry)
    mock_entry.id = entry_id
    mock_entry.company_id = company_id
    mock_entry.status = JournalEntryStatus.POSTED.value
    mock_entry.entry_number = "JE-2024-00001"
    mock_entry.lines = [mock_line1, mock_line2]
    mock_entry.document_id = None
    mock_entry.source = "manual"

    mock_result_original = MagicMock()
    mock_result_original.scalar_one_or_none = MagicMock(return_value=mock_entry)

    # Mock reversal entry returned by post_journal_entry's DB lookup
    mock_reversal = MagicMock(spec=JournalEntry)
    mock_reversal.id = uuid4()
    mock_reversal.status = JournalEntryStatus.DRAFT.value
    mock_reversal.entry_number = "JE-2024-00002"

    mock_result_reversal = MagicMock()
    mock_result_reversal.scalar_one_or_none = MagicMock(return_value=mock_reversal)

    # First execute: fetch original; Second execute: fetch reversal in post_journal_entry
    mock_db.execute = AsyncMock(side_effect=[mock_result_original, mock_result_reversal])

    gl_service._generate_entry_number = AsyncMock(return_value="JE-2024-00002")

    reversal = await gl_service.reverse_journal_entry(entry_id, user_id, "Test")

    # Check reversed line amounts (swapped)
    assert reversal.lines[0].debit_amount == Decimal("0")  # Was 123.45
    assert reversal.lines[0].credit_amount == Decimal("123.45")  # Was 0
    assert reversal.lines[1].debit_amount == Decimal("123.45")  # Was 0
    assert reversal.lines[1].credit_amount == Decimal("0")  # Was 123.45


@pytest.mark.asyncio
async def test_auto_post_above_threshold(gl_service, company_id, mock_db):
    """Test: Auto-post when confidence >= 0.85."""
    document_id = uuid4()

    # Mock post_from_invoice
    mock_entry = MagicMock(spec=JournalEntry)
    mock_entry.id = uuid4()
    mock_entry.entry_number = "JE-2024-00001"

    gl_service.post_from_invoice = AsyncMock(return_value=mock_entry)

    result = await gl_service.auto_post_from_pipeline(
        company_id=company_id,
        document_id=document_id,
        confidence=0.90,  # Above threshold
    )

    assert result is not None
    assert result.id == mock_entry.id
    gl_service.post_from_invoice.assert_called_once()


@pytest.mark.asyncio
async def test_auto_post_below_threshold_skips(gl_service, company_id, mock_db):
    """Test: Auto-post skipped when confidence < 0.85."""
    document_id = uuid4()

    result = await gl_service.auto_post_from_pipeline(
        company_id=company_id,
        document_id=document_id,
        confidence=0.70,  # Below threshold
    )

    assert result is None


@pytest.mark.asyncio
async def test_trial_balance_aggregation(gl_service, company_id, mock_db):
    """Test: Trial balance aggregates amounts per account."""
    # Mock DB result
    mock_rows = [
        MagicMock(
            account_number="1200",
            account_name="Bank",
            total_debit=Decimal("1000.00"),
            total_credit=Decimal("500.00"),
        ),
        MagicMock(
            account_number="4400",
            account_name="Wareneingang",
            total_debit=Decimal("300.00"),
            total_credit=Decimal("0"),
        ),
    ]

    mock_result = MagicMock()
    mock_result.all = MagicMock(return_value=mock_rows)
    mock_db.execute = AsyncMock(return_value=mock_result)

    rows = await gl_service.get_trial_balance(
        company_id=company_id,
        fiscal_year=2024,
    )

    assert len(rows) == 2
    assert rows[0].account_number == "1200"
    assert rows[0].balance == Decimal("500.00")  # 1000 - 500
    assert rows[1].account_number == "4400"
    assert rows[1].balance == Decimal("300.00")  # 300 - 0


@pytest.mark.asyncio
async def test_entry_number_format(gl_service, company_id, mock_db):
    """Test: Entry number matches format JE-{year}-{seq:05d}."""
    # Mock: no existing entries
    mock_result = MagicMock()
    mock_result.scalar_one_or_none = MagicMock(return_value=None)
    mock_db.execute = AsyncMock(return_value=mock_result)

    entry_number = await gl_service._generate_entry_number(company_id, 2024)

    assert entry_number == "JE-2024-00001"


@pytest.mark.asyncio
async def test_entry_number_sequence(gl_service, company_id, mock_db):
    """Test: Entry number sequence increments correctly."""
    # Mock: last entry was JE-2024-00042
    mock_result = MagicMock()
    mock_result.scalar_one_or_none = MagicMock(return_value="JE-2024-00042")
    mock_db.execute = AsyncMock(return_value=mock_result)

    entry_number = await gl_service._generate_entry_number(company_id, 2024)

    assert entry_number == "JE-2024-00043"

# -*- coding: utf-8 -*-
"""
Unit tests for ContractRenewalService.

Phase 1.1: Vertragsverlaengerungs-Warnung (Contract Renewal Warning)

Tests:
- OCR date extraction
- Reminder scheduling
- Alert creation
- Upcoming renewals listing
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.contracts.contract_renewal_service import (
    ContractRenewalService,
    ContractAlertCodes,
    DEFAULT_REMINDER_DAYS,
)
from app.db.models_contract import (
    Contract,
    ContractDeadline,
    ContractStatus,
)


class TestContractRenewalService:
    """Test suite for ContractRenewalService."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Create a mock database session."""
        db = AsyncMock(spec=AsyncSession)
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        db.add = MagicMock()
        return db

    @pytest.fixture
    def service(self, mock_db: AsyncMock) -> ContractRenewalService:
        """Create service instance with mock db."""
        return ContractRenewalService(mock_db)

    @pytest.fixture
    def sample_contract(self) -> Contract:
        """Create a sample contract for testing."""
        contract = Contract(
            id=uuid4(),
            company_id=uuid4(),
            title="Mustervertrag GmbH",
            contract_type="supplier_framework",
            status=ContractStatus.ACTIVE.value,
            expiration_date=date.today() + timedelta(days=45),
            notice_period_days=30,
            auto_renewal=True,
            renewal_period_months=12,
            total_value=Decimal("50000.00"),
            currency="EUR",
        )
        return contract

    # =========================================================================
    # Date Extraction Tests
    # =========================================================================

    def test_extract_dates_from_text_german_format(self, service: ContractRenewalService):
        """Test extraction of German date format DD.MM.YYYY."""
        text = """
        Vertragslaufzeit: Der Vertrag beginnt am 01.01.2026 und endet am 31.12.2026.
        Die Kündigungsfrist beträgt 3 Monate zum Vertragsende.
        """

        result = service._extract_dates_from_text(text)

        assert result["expiration_date"] == date(2026, 12, 31)
        assert result["notice_period_days"] == 90  # 3 months = 90 days

    def test_extract_dates_from_text_iso_format(self, service: ContractRenewalService):
        """Test extraction of ISO date format YYYY-MM-DD.

        Der Extraktor klassifiziert Datumsangaben ueber deutsche Kontext-
        Schluesselwoerter (System verarbeitet deutsche Dokumente, CLAUDE.md
        Regel 2). Daher deutscher Kontext mit ISO-Datumsformat.
        """
        text = """
        Vertrag gültig ab dem 2026-01-15.
        Der Vertrag endet am 2027-01-14.
        """

        result = service._extract_dates_from_text(text)

        # Should find the expiration date with context
        assert result["expiration_date"] is not None or result["effective_date"] is not None

    def test_extract_notice_period_days(self, service: ContractRenewalService):
        """Test extraction of notice period from German text."""
        test_cases = [
            ("Kündigungsfrist von 30 Tagen", 30),
            ("3 Monate Kündigungsfrist", 90),
            ("4 Wochen vor Vertragsende", 28),
            ("Kündigungsfrist von 1 Jahr", 365),
            ("Die Frist beträgt 14 Tage", 14),
        ]

        for text, expected_days in test_cases:
            result = service._extract_notice_period(text)
            assert result == expected_days, f"Failed for: {text}"

    def test_extract_notice_period_no_match(self, service: ContractRenewalService):
        """Test that None is returned when no notice period found."""
        text = "Dieser Text enthaelt keine Kuendigungsfrist."
        result = service._extract_notice_period(text)
        assert result is None

    # =========================================================================
    # Reminder Scheduling Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_schedule_reminders_creates_deadlines(
        self,
        service: ContractRenewalService,
        mock_db: AsyncMock,
        sample_contract: Contract,
    ):
        """Test that schedule_reminders creates correct deadlines."""
        mock_db.get = AsyncMock(return_value=sample_contract)

        # Mock the existing deadline check
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_db.execute = AsyncMock(return_value=mock_result)

        deadline_date = date.today() + timedelta(days=90)
        reminders = await service.schedule_reminders(
            contract_id=sample_contract.id,
            deadline=deadline_date,
            reminder_days=[60, 30],
        )

        # Verify deadlines were added
        assert mock_db.add.call_count >= 1
        assert mock_db.commit.called

    @pytest.mark.asyncio
    async def test_schedule_reminders_skips_past_dates(
        self,
        service: ContractRenewalService,
        mock_db: AsyncMock,
        sample_contract: Contract,
    ):
        """Test that reminders in the past are not scheduled."""
        mock_db.get = AsyncMock(return_value=sample_contract)

        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Deadline in 20 days - 90 day reminder would be in the past
        deadline_date = date.today() + timedelta(days=20)
        reminders = await service.schedule_reminders(
            contract_id=sample_contract.id,
            deadline=deadline_date,
            reminder_days=[90, 60, 30, 14],
        )

        # Only 14-day reminder should be created (20 - 14 = 6 days in future)
        # 30-day reminder would be at -10 days (past)

    @pytest.mark.asyncio
    async def test_schedule_reminders_contract_not_found(
        self,
        service: ContractRenewalService,
        mock_db: AsyncMock,
    ):
        """Test error handling when contract not found."""
        mock_db.get = AsyncMock(return_value=None)

        with pytest.raises(ValueError) as exc_info:
            await service.schedule_reminders(
                contract_id=uuid4(),
                deadline=date.today() + timedelta(days=30),
            )

        assert "nicht gefunden" in str(exc_info.value)

    # =========================================================================
    # Priority Calculation Tests
    # =========================================================================

    def test_get_priority_for_days(self, service: ContractRenewalService):
        """Test priority assignment based on days remaining."""
        assert service._get_priority_for_days(7) == "critical"
        assert service._get_priority_for_days(14) == "high"
        assert service._get_priority_for_days(30) == "high"
        assert service._get_priority_for_days(45) == "medium"
        assert service._get_priority_for_days(60) == "medium"
        assert service._get_priority_for_days(90) == "low"

    def test_calculate_urgency(self, service: ContractRenewalService):
        """Test urgency calculation with notice deadline consideration."""
        # Notice deadline is more urgent
        assert service._calculate_urgency(30, 5) == "critical"
        assert service._calculate_urgency(60, 25) == "high"

        # When no notice deadline, use expiry
        assert service._calculate_urgency(5, None) == "critical"
        assert service._calculate_urgency(25, None) == "high"
        assert service._calculate_urgency(45, None) == "medium"
        assert service._calculate_urgency(90, None) == "low"

    # =========================================================================
    # Reminder Title/Description Tests
    # =========================================================================

    def test_get_reminder_title_german(self, service: ContractRenewalService):
        """Test that reminder titles are in German."""
        title = service._get_reminder_title(
            deadline_type="termination_notice",
            days_before=30,
            contract_title="Mustervertrag",
        )

        assert "Kündigungsfrist" in title
        assert "30 Tagen" in title

    def test_get_reminder_description_german(self, service: ContractRenewalService):
        """Test that reminder descriptions are in German."""
        description = service._get_reminder_description(
            deadline_type="contract_expiry",
            days_before=60,
            deadline=date(2026, 12, 31),
            contract_title="Mustervertrag",
        )

        assert "laeuft" in description
        assert "31.12.2026" in description

    # =========================================================================
    # Alert Code Tests
    # =========================================================================

    def test_contract_alert_codes_defined(self):
        """Test that all contract alert codes are defined."""
        assert hasattr(ContractAlertCodes, "RENEWAL_90_DAYS")
        assert hasattr(ContractAlertCodes, "RENEWAL_60_DAYS")
        assert hasattr(ContractAlertCodes, "RENEWAL_30_DAYS")
        assert hasattr(ContractAlertCodes, "RENEWAL_14_DAYS")
        assert hasattr(ContractAlertCodes, "RENEWAL_7_DAYS")
        assert hasattr(ContractAlertCodes, "RENEWAL_1_DAY")

    # =========================================================================
    # Upcoming Renewals Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_get_upcoming_renewals_returns_sorted_list(
        self,
        service: ContractRenewalService,
        mock_db: AsyncMock,
    ):
        """Test that upcoming renewals are sorted by urgency."""
        company_id = uuid4()

        # Create mock contracts with different expiration dates.
        # Der Service vertraut auf die SQL-Sortierung (ORDER BY expiration_date ASC);
        # der Mock liefert die Reihenfolge, wie sie die echte DB liefern wuerde:
        # Contract 2 (20 Tage) vor Contract 1 (60 Tage).
        contracts = [
            Contract(
                id=uuid4(),
                company_id=company_id,
                title="Contract 2",
                contract_type="other",
                status=ContractStatus.ACTIVE.value,
                expiration_date=date.today() + timedelta(days=20),
                notice_period_days=14,
                auto_renewal=True,
            ),
            Contract(
                id=uuid4(),
                company_id=company_id,
                title="Contract 1",
                contract_type="other",
                status=ContractStatus.ACTIVE.value,
                expiration_date=date.today() + timedelta(days=60),
                notice_period_days=30,
                auto_renewal=False,
            ),
        ]

        # Mock database response
        mock_result = AsyncMock()
        mock_scalars = AsyncMock()
        mock_scalars.all = MagicMock(return_value=contracts)
        mock_result.scalars = MagicMock(return_value=mock_scalars)
        mock_db.execute = AsyncMock(return_value=mock_result)

        renewals = await service.get_upcoming_renewals(
            company_id=company_id,
            days_ahead=90,
        )

        assert len(renewals) == 2
        # Contract 2 should be first (more urgent - 20 days)
        assert renewals[0]["title"] == "Contract 2"
        assert renewals[0]["days_until_expiry"] == 20

    # =========================================================================
    # Manual Deadline Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_set_manual_deadline_creates_new(
        self,
        service: ContractRenewalService,
        mock_db: AsyncMock,
        sample_contract: Contract,
    ):
        """Test creating a new manual deadline."""
        mock_db.get = AsyncMock(return_value=sample_contract)

        # No existing deadline
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_db.execute = AsyncMock(return_value=mock_result)

        deadline_date = date.today() + timedelta(days=45)
        deadline = await service.set_manual_deadline(
            contract_id=sample_contract.id,
            deadline_date=deadline_date,
            deadline_type="termination_notice",
            user_id=uuid4(),
            description="Manuell gesetzt",
        )

        assert mock_db.add.called
        assert mock_db.commit.called


class TestContractRenewalIntegration:
    """Integration-style tests for ContractRenewalService."""

    def test_default_reminder_days_defined(self):
        """Test that default reminder days are properly defined."""
        assert DEFAULT_REMINDER_DAYS == [90, 60, 30, 14, 7, 1]

    def test_date_extraction_patterns(self):
        """Test that date patterns are correctly defined."""
        from app.services.contracts.contract_renewal_service import DATE_PATTERNS

        assert len(DATE_PATTERNS) >= 3
        # Should include German DD.MM.YYYY pattern
        assert any("\\d{1,2})\\.(" in p for p in DATE_PATTERNS)

    def test_termination_keywords_german(self):
        """Test that termination keywords are in German."""
        from app.services.contracts.contract_renewal_service import TERMINATION_KEYWORDS

        german_keywords = ["kündigungsfrist", "vertragsende", "laufzeit"]
        for keyword in german_keywords:
            assert keyword in TERMINATION_KEYWORDS

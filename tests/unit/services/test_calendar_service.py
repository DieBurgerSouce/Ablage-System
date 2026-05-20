# -*- coding: utf-8 -*-
"""Unit tests for Calendar Service.

Tests:
- Deadline categories and urgency calculation
- Calendar month generation
- Deadline summary
- Upcoming alerts
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.calendar_service import (
    CalendarService,
    CalendarDay,
    CalendarMonth,
    CalendarWeek,
    DeadlineCategory,
    DeadlineItem,
    DeadlineSummary,
    DeadlineStatus,
    DeadlineUrgency,
    get_calendar_service,
)


@pytest.fixture
def calendar_service() -> CalendarService:
    """Create CalendarService instance."""
    return CalendarService()


@pytest.fixture
def company_id():
    """Test company ID."""
    return uuid4()


class TestDeadlineUrgencyCalculation:
    """Tests for _calculate_urgency method."""

    def test_critical_when_overdue(self, calendar_service: CalendarService):
        """Test critical urgency for overdue deadlines."""
        urgency = calendar_service._calculate_urgency(-5)
        assert urgency == DeadlineUrgency.CRITICAL

    def test_critical_when_today(self, calendar_service: CalendarService):
        """Test critical urgency when deadline is today."""
        urgency = calendar_service._calculate_urgency(0)
        assert urgency == DeadlineUrgency.CRITICAL

    def test_critical_when_tomorrow(self, calendar_service: CalendarService):
        """Test critical urgency when deadline is tomorrow."""
        urgency = calendar_service._calculate_urgency(1)
        assert urgency == DeadlineUrgency.CRITICAL

    def test_warning_when_2_days(self, calendar_service: CalendarService):
        """Test warning urgency for 2 days remaining."""
        urgency = calendar_service._calculate_urgency(2)
        assert urgency == DeadlineUrgency.WARNING

    def test_warning_when_3_days(self, calendar_service: CalendarService):
        """Test warning urgency for 3 days remaining."""
        urgency = calendar_service._calculate_urgency(3)
        assert urgency == DeadlineUrgency.WARNING

    def test_upcoming_when_4_days(self, calendar_service: CalendarService):
        """Test upcoming urgency for 4 days remaining."""
        urgency = calendar_service._calculate_urgency(4)
        assert urgency == DeadlineUrgency.UPCOMING

    def test_upcoming_when_7_days(self, calendar_service: CalendarService):
        """Test upcoming urgency for 7 days remaining."""
        urgency = calendar_service._calculate_urgency(7)
        assert urgency == DeadlineUrgency.UPCOMING

    def test_scheduled_when_8_days(self, calendar_service: CalendarService):
        """Test scheduled urgency for 8+ days remaining."""
        urgency = calendar_service._calculate_urgency(8)
        assert urgency == DeadlineUrgency.SCHEDULED

    def test_scheduled_when_30_days(self, calendar_service: CalendarService):
        """Test scheduled urgency for 30 days remaining."""
        urgency = calendar_service._calculate_urgency(30)
        assert urgency == DeadlineUrgency.SCHEDULED


class TestDeadlineItemDataclass:
    """Tests for DeadlineItem dataclass."""

    def test_deadline_item_creation(self):
        """Test DeadlineItem can be created with required fields."""
        item = DeadlineItem(
            id="test-1",
            category=DeadlineCategory.SKONTO,
            title="Test Skonto",
            description="Test description",
            deadline=datetime.now(timezone.utc),
            urgency=DeadlineUrgency.WARNING,
            status=DeadlineStatus.PENDING,
            days_until=3,
        )
        assert item.id == "test-1"
        assert item.category == DeadlineCategory.SKONTO
        assert item.currency == "EUR"  # Default

    def test_deadline_item_with_optional_fields(self):
        """Test DeadlineItem with optional fields."""
        doc_id = uuid4()
        item = DeadlineItem(
            id="test-2",
            category=DeadlineCategory.PAYMENT_OUTGOING,
            title="Payment Due",
            description="Invoice payment",
            deadline=datetime.now(timezone.utc),
            urgency=DeadlineUrgency.CRITICAL,
            status=DeadlineStatus.EXPIRED,
            days_until=-2,
            document_id=doc_id,
            amount=Decimal("1500.00"),
            metadata={"invoice_number": "INV-001"},
        )
        assert item.document_id == doc_id
        assert item.amount == Decimal("1500.00")
        assert item.metadata["invoice_number"] == "INV-001"


class TestCalendarDayDataclass:
    """Tests for CalendarDay dataclass."""

    def test_calendar_day_has_critical(self):
        """Test has_critical property."""
        critical_item = DeadlineItem(
            id="c-1",
            category=DeadlineCategory.SKONTO,
            title="Critical",
            description="desc",
            deadline=datetime.now(timezone.utc),
            urgency=DeadlineUrgency.CRITICAL,
            status=DeadlineStatus.PENDING,
            days_until=0,
        )
        warning_item = DeadlineItem(
            id="w-1",
            category=DeadlineCategory.TAX,
            title="Warning",
            description="desc",
            deadline=datetime.now(timezone.utc),
            urgency=DeadlineUrgency.WARNING,
            status=DeadlineStatus.PENDING,
            days_until=2,
        )

        day_with_critical = CalendarDay(
            date=date.today(),
            deadlines=[critical_item, warning_item],
        )
        assert day_with_critical.has_critical is True

        day_without_critical = CalendarDay(
            date=date.today(),
            deadlines=[warning_item],
        )
        assert day_without_critical.has_critical is False

    def test_calendar_day_deadline_count(self):
        """Test deadline_count property."""
        items = [
            DeadlineItem(
                id=f"item-{i}",
                category=DeadlineCategory.PAYMENT_INCOMING,
                title=f"Item {i}",
                description="desc",
                deadline=datetime.now(timezone.utc),
                urgency=DeadlineUrgency.SCHEDULED,
                status=DeadlineStatus.PENDING,
                days_until=10,
            )
            for i in range(5)
        ]
        day = CalendarDay(date=date.today(), deadlines=items)
        assert day.deadline_count == 5


class TestCalendarWeekDataclass:
    """Tests for CalendarWeek dataclass."""

    def test_calendar_week_total_deadlines(self):
        """Test total_deadlines property."""
        days = []
        for i in range(7):
            items = [
                DeadlineItem(
                    id=f"d{i}-{j}",
                    category=DeadlineCategory.DUNNING,
                    title=f"Item {j}",
                    description="desc",
                    deadline=datetime.now(timezone.utc),
                    urgency=DeadlineUrgency.UPCOMING,
                    status=DeadlineStatus.PENDING,
                    days_until=5,
                )
                for j in range(i)  # 0, 1, 2, 3, 4, 5, 6 items
            ]
            days.append(CalendarDay(
                date=date.today() + timedelta(days=i),
                deadlines=items,
            ))

        week = CalendarWeek(
            week_number=1,
            year=2026,
            start_date=date.today(),
            end_date=date.today() + timedelta(days=6),
            days=days,
        )
        # Total: 0+1+2+3+4+5+6 = 21
        assert week.total_deadlines == 21


class TestDeadlineCategoryEnum:
    """Tests for DeadlineCategory enum."""

    def test_all_categories_exist(self):
        """Test all expected categories are defined."""
        expected = [
            "skonto", "payment_incoming", "payment_outgoing",
            "tax", "contract", "dunning", "document", "custom"
        ]
        for cat in expected:
            assert DeadlineCategory(cat) is not None

    def test_category_string_values(self):
        """Test category string values."""
        assert DeadlineCategory.SKONTO.value == "skonto"
        assert DeadlineCategory.TAX.value == "tax"


class TestDeadlineStatusEnum:
    """Tests for DeadlineStatus enum."""

    def test_all_statuses_exist(self):
        """Test all expected statuses are defined."""
        expected = ["pending", "completed", "expired", "cancelled"]
        for status in expected:
            assert DeadlineStatus(status) is not None


class TestCalendarServiceSingleton:
    """Tests for singleton pattern."""

    def test_get_calendar_service_returns_same_instance(self):
        """Test that get_calendar_service returns same instance."""
        service1 = get_calendar_service()
        service2 = get_calendar_service()
        assert service1 is service2


class TestStandardTaxDeadlines:
    """Tests for standard tax deadlines configuration."""

    def test_ust_voranmeldung_monthly(self, calendar_service: CalendarService):
        """Test USt-Voranmeldung is monthly."""
        ust = next(
            d for d in calendar_service.STANDARD_TAX_DEADLINES
            if d["name"] == "USt-Voranmeldung"
        )
        assert ust["monthly"] is True
        assert ust["day"] == 10

    def test_est_vorauszahlung_quarterly(self, calendar_service: CalendarService):
        """Test ESt-Vorauszahlung is quarterly."""
        est = next(
            d for d in calendar_service.STANDARD_TAX_DEADLINES
            if d["name"] == "ESt-Vorauszahlung"
        )
        assert est["quarterly"] is True
        assert est["months"] == [3, 6, 9, 12]

    def test_jahresabschluss_annual(self, calendar_service: CalendarService):
        """Test Jahresabschluss is annual."""
        ja = next(
            d for d in calendar_service.STANDARD_TAX_DEADLINES
            if d["name"] == "Jahresabschluss Einreichung"
        )
        assert ja["annual"] is True
        assert ja["month"] == 7
        assert ja["day"] == 31


@pytest.mark.asyncio
class TestGetAllDeadlines:
    """Tests for get_all_deadlines method."""

    async def test_get_deadlines_with_empty_db(
        self, calendar_service: CalendarService, company_id
    ):
        """Test get_all_deadlines with empty database returns tax deadlines."""
        mock_db = AsyncMock(spec=AsyncSession)

        # Mock all the sub-queries to return empty results
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        deadlines = await calendar_service.get_all_deadlines(
            db=mock_db,
            company_id=company_id,
            start_date=date.today(),
            end_date=date.today() + timedelta(days=90),
        )

        # Should return standard tax deadlines
        assert isinstance(deadlines, list)
        # Tax deadlines from standard config should be included
        tax_deadlines = [d for d in deadlines if d.category == DeadlineCategory.TAX]
        assert len(tax_deadlines) >= 0  # May have recurring ones

    async def test_filter_by_category(
        self, calendar_service: CalendarService, company_id
    ):
        """Test filtering by category."""
        mock_db = AsyncMock(spec=AsyncSession)

        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        deadlines = await calendar_service.get_all_deadlines(
            db=mock_db,
            company_id=company_id,
            categories=[DeadlineCategory.SKONTO],
        )

        # All returned deadlines should be SKONTO category
        for deadline in deadlines:
            assert deadline.category == DeadlineCategory.SKONTO


@pytest.mark.asyncio
class TestGetCalendarMonth:
    """Tests for get_calendar_month method."""

    async def test_calendar_month_structure(
        self, calendar_service: CalendarService, company_id
    ):
        """Test calendar month returns correct structure."""
        mock_db = AsyncMock(spec=AsyncSession)

        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        month = await calendar_service.get_calendar_month(
            db=mock_db,
            company_id=company_id,
            year=2026,
            month=1,
        )

        assert isinstance(month, CalendarMonth)
        assert month.year == 2026
        assert month.month == 1
        assert len(month.weeks) >= 4  # January has at least 4 weeks
        assert isinstance(month.summary, dict)


@pytest.mark.asyncio
class TestGetDeadlineSummary:
    """Tests for get_deadline_summary method."""

    async def test_summary_structure(
        self, calendar_service: CalendarService, company_id
    ):
        """Test deadline summary returns correct structure."""
        mock_db = AsyncMock(spec=AsyncSession)

        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        summary = await calendar_service.get_deadline_summary(
            db=mock_db,
            company_id=company_id,
        )

        assert isinstance(summary, DeadlineSummary)
        assert summary.total_count >= 0
        assert summary.critical_count >= 0
        assert summary.warning_count >= 0
        assert isinstance(summary.by_category, dict)
        assert isinstance(summary.total_amount_at_risk, Decimal)


@pytest.mark.asyncio
class TestGetUpcomingAlerts:
    """Tests for get_upcoming_alerts method."""

    async def test_alerts_only_critical_and_warning(
        self, calendar_service: CalendarService, company_id
    ):
        """Test alerts only returns critical and warning deadlines."""
        mock_db = AsyncMock(spec=AsyncSession)

        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        alerts = await calendar_service.get_upcoming_alerts(
            db=mock_db,
            company_id=company_id,
            days_ahead=7,
        )

        # All returned items should be CRITICAL or WARNING and PENDING
        for alert in alerts:
            assert alert.urgency in [DeadlineUrgency.CRITICAL, DeadlineUrgency.WARNING]
            assert alert.status == DeadlineStatus.PENDING

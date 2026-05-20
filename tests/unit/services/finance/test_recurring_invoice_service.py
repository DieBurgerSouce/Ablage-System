# -*- coding: utf-8 -*-
"""
Unit-Tests fuer RecurringInvoiceService.

Testet:
- CRUD-Operationen (Create, List, Get, Update)
- Muster-Erkennung (detect_recurring_invoices)
- Fehlende Rechnungen (check_missing_invoices)
- Preisaenderungen (check_price_changes)
- Soll/Ist-Bericht (get_soll_ist_report)
- Manuelle Zuordnung (manual_match_document)
- Interne Hilfsmethoden (_classify_interval, _calculate_next_expected_date)
- Singleton-Pattern (get_recurring_invoice_service)

Feinpoliert und durchdacht - Enterprise Abo-Verwaltung Service Tests.
"""

import pytest
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import List, Optional
from unittest.mock import AsyncMock, Mock, MagicMock, patch, PropertyMock

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.finance.recurring_invoice_service import (
    RecurringInvoiceService,
    RecurringInvoiceCreateRequest,
    RecurringInvoiceUpdateRequest,
    MatchInvoiceRequest,
    DetectedPattern,
    MissingInvoiceInfo,
    PriceChangeInfo,
    SollIstRow,
    SollIstReport,
    get_recurring_invoice_service,
)
from app.db.models_recurring_invoice import (
    RecurringInvoice,
    RecurringInvoiceOccurrence,
    RecurringInvoiceStatus,
    RecurringIntervalType,
    DetectionMethod,
    OccurrenceStatus,
    OccurrenceMatchMethod,
)


# ========================= Test-Konstanten =========================

TEST_USER_UUID = uuid.UUID("00000000-0000-0000-0000-000000000001")
TEST_COMPANY_UUID = uuid.UUID("00000000-0000-0000-0000-000000000002")
TEST_VENDOR_ENTITY_UUID = uuid.UUID("00000000-0000-0000-0000-000000000003")
TEST_DOCUMENT_UUID = uuid.UUID("00000000-0000-0000-0000-000000000004")
TEST_RECURRING_UUID = uuid.UUID("00000000-0000-0000-0000-000000000005")
TEST_OCCURRENCE_UUID = uuid.UUID("00000000-0000-0000-0000-000000000006")

pytestmark = [pytest.mark.unit]


# ========================= Helper =========================


def _make_mock_recurring(
    recurring_id: uuid.UUID = TEST_RECURRING_UUID,
    company_id: uuid.UUID = TEST_COMPANY_UUID,
    status: RecurringInvoiceStatus = RecurringInvoiceStatus.ACTIVE,
    vendor_name: str = "Testfirma GmbH",
    expected_amount: Decimal = Decimal("99.99"),
    interval_months: int = 1,
    next_expected_date: Optional[date] = None,
    occurrences: Optional[List[Mock]] = None,
) -> Mock:
    """Erstellt ein Mock-RecurringInvoice Objekt."""
    r = Mock(spec=RecurringInvoice)
    r.id = recurring_id
    r.company_id = company_id
    r.vendor_entity_id = TEST_VENDOR_ENTITY_UUID
    r.vendor_name = vendor_name
    r.interval_type = RecurringIntervalType.MONTHLY
    r.interval_months = interval_months
    r.expected_amount = expected_amount
    r.currency = "EUR"
    r.tolerance_percent = 5.0
    r.first_seen_date = date(2025, 6, 1)
    r.last_seen_date = date(2026, 1, 15)
    r.next_expected_date = next_expected_date or date(2026, 2, 15)
    r.cancellation_deadline = date(2026, 12, 31)
    r.notice_period_days = 30
    r.auto_renewal = True
    r.detection_confidence = 0.95
    r.detection_method = DetectionMethod.AUTO
    r.match_count = 8
    r.price_history = []
    r.last_price_change_date = None
    r.price_change_percent = None
    r.status = status
    r.price_increase_alerted = False
    r.missing_invoice_alerted = False
    r.category = "Software"
    r.description = "Test-Abo"
    r.document_type = "Rechnung"
    r.reference_pattern = None
    r.created_at = datetime(2025, 6, 1, 10, 0, 0, tzinfo=timezone.utc)
    r.updated_at = datetime(2026, 1, 15, 14, 30, 0, tzinfo=timezone.utc)
    r.occurrences = occurrences if occurrences is not None else []
    return r


def _make_mock_occurrence(
    occurrence_id: uuid.UUID = TEST_OCCURRENCE_UUID,
    recurring_id: uuid.UUID = TEST_RECURRING_UUID,
    status: OccurrenceStatus = OccurrenceStatus.MATCHED,
    expected_date: date = date(2026, 1, 15),
    actual_date: Optional[date] = date(2026, 1, 14),
    actual_amount: Optional[Decimal] = Decimal("99.99"),
) -> Mock:
    """Erstellt ein Mock-RecurringInvoiceOccurrence Objekt."""
    o = Mock(spec=RecurringInvoiceOccurrence)
    o.id = occurrence_id
    o.recurring_invoice_id = recurring_id
    o.document_id = TEST_DOCUMENT_UUID
    o.invoice_tracking_id = None
    o.expected_date = expected_date
    o.actual_date = actual_date
    o.expected_amount = Decimal("99.99")
    o.actual_amount = actual_amount
    o.amount_deviation = Decimal("0.00")
    o.status = status
    o.match_confidence = 0.95
    o.matched_at = datetime(2026, 1, 14, 12, 0, 0, tzinfo=timezone.utc)
    o.matched_by = OccurrenceMatchMethod.AUTO
    o.period_start = date(2026, 1, 1)
    o.period_end = date(2026, 1, 31)
    o.notes = None
    o.created_at = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    return o


# ========================= Fixtures =========================


@pytest.fixture
def service() -> RecurringInvoiceService:
    """Erstelle RecurringInvoiceService-Instanz."""
    return RecurringInvoiceService()


@pytest.fixture
def mock_db() -> AsyncMock:
    """Erstelle Mock-Datenbank-Session."""
    db = AsyncMock(spec=AsyncSession)
    return db


# ========================= Singleton Tests =========================


class TestSingleton:
    """Tests fuer das Singleton-Pattern des Service."""

    def test_get_recurring_invoice_service_returns_instance(self) -> None:
        """get_recurring_invoice_service sollte eine Instanz zurueckgeben."""
        svc = get_recurring_invoice_service()
        assert isinstance(svc, RecurringInvoiceService)

    def test_get_recurring_invoice_service_is_singleton(self) -> None:
        """Wiederholte Aufrufe sollten dieselbe Instanz zurueckgeben."""
        svc1 = get_recurring_invoice_service()
        svc2 = get_recurring_invoice_service()
        assert svc1 is svc2


# ========================= Create Tests =========================


class TestCreateRecurringInvoice:
    """Tests fuer create_recurring_invoice."""

    @pytest.mark.asyncio
    async def test_create_recurring_invoice(
        self, service: RecurringInvoiceService, mock_db: AsyncMock
    ) -> None:
        """Sollte wiederkehrende Rechnung mit gueltigen Daten erstellen."""
        # Mock: db.add, db.commit, db.refresh
        created_recurring = _make_mock_recurring()
        created_recurring.detection_method = DetectionMethod.MANUAL
        created_recurring.detection_confidence = 1.0
        created_recurring.status = RecurringInvoiceStatus.ACTIVE

        # db.refresh setzt den Mock als Seiteneffekt
        async def mock_refresh(obj: RecurringInvoice) -> None:
            pass

        mock_db.refresh = AsyncMock(side_effect=mock_refresh)

        request = RecurringInvoiceCreateRequest(
            company_id=TEST_COMPANY_UUID,
            vendor_name="Testfirma GmbH",
            interval_type=RecurringIntervalType.MONTHLY,
            expected_amount=Decimal("99.99"),
            interval_months=1,
            currency="EUR",
            tolerance_percent=5.0,
            auto_renewal=True,
            category="Software",
        )

        result = await service.create_recurring_invoice(mock_db, request)

        # Pruefe dass db.add aufgerufen wurde
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()

        # Pruefe das erstellte Objekt (erster Arg von db.add)
        added_obj = mock_db.add.call_args[0][0]
        assert added_obj.vendor_name == "Testfirma GmbH"
        assert added_obj.company_id == TEST_COMPANY_UUID
        assert added_obj.expected_amount == Decimal("99.99")
        assert added_obj.interval_type == RecurringIntervalType.MONTHLY
        assert added_obj.currency == "EUR"
        assert added_obj.category == "Software"

    @pytest.mark.asyncio
    async def test_create_recurring_invoice_sets_detection_method_manual(
        self, service: RecurringInvoiceService, mock_db: AsyncMock
    ) -> None:
        """Sollte detection_method=MANUAL und confidence=1.0 setzen."""
        request = RecurringInvoiceCreateRequest(
            company_id=TEST_COMPANY_UUID,
            vendor_name="Manuell GmbH",
            interval_type=RecurringIntervalType.YEARLY,
            expected_amount=Decimal("1200.00"),
        )

        await service.create_recurring_invoice(mock_db, request)

        added_obj = mock_db.add.call_args[0][0]
        assert added_obj.detection_method == DetectionMethod.MANUAL
        assert added_obj.detection_confidence == 1.0
        assert added_obj.status == RecurringInvoiceStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_create_recurring_invoice_optional_fields(
        self, service: RecurringInvoiceService, mock_db: AsyncMock
    ) -> None:
        """Sollte optionale Felder korrekt setzen."""
        request = RecurringInvoiceCreateRequest(
            company_id=TEST_COMPANY_UUID,
            vendor_name="Optional GmbH",
            interval_type=RecurringIntervalType.QUARTERLY,
            expected_amount=Decimal("300.00"),
            vendor_entity_id=TEST_VENDOR_ENTITY_UUID,
            first_seen_date=date(2025, 1, 1),
            next_expected_date=date(2026, 4, 1),
            cancellation_deadline=date(2026, 12, 31),
            notice_period_days=90,
            auto_renewal=False,
            category="Versicherung",
            description="Quartals-Versicherung",
            document_type="Beitragsbescheid",
            reference_pattern=r"VS-\d{6}",
        )

        await service.create_recurring_invoice(mock_db, request)

        added_obj = mock_db.add.call_args[0][0]
        assert added_obj.vendor_entity_id == TEST_VENDOR_ENTITY_UUID
        assert added_obj.first_seen_date == date(2025, 1, 1)
        assert added_obj.cancellation_deadline == date(2026, 12, 31)
        assert added_obj.notice_period_days == 90
        assert added_obj.auto_renewal is False
        assert added_obj.reference_pattern == r"VS-\d{6}"


# ========================= List Tests =========================


class TestListRecurringInvoices:
    """Tests fuer list_recurring_invoices."""

    @pytest.mark.asyncio
    async def test_list_recurring_invoices(
        self, service: RecurringInvoiceService, mock_db: AsyncMock
    ) -> None:
        """Sollte paginierte Liste zurueckgeben."""
        mock_recurring = _make_mock_recurring()

        # Mock fuer die Haupt-Query (items)
        mock_items_result = Mock()
        mock_items_result.scalars.return_value.all.return_value = [mock_recurring]

        # Mock fuer die Count-Query (total)
        mock_count_result = Mock()
        mock_count_result.scalar.return_value = 1

        # Zwei execute-Aufrufe: erst count, dann items
        mock_db.execute = AsyncMock(
            side_effect=[mock_count_result, mock_items_result]
        )

        items, total = await service.list_recurring_invoices(
            mock_db,
            company_id=TEST_COMPANY_UUID,
            page=0,
            page_size=25,
        )

        assert total == 1
        assert len(items) == 1
        assert items[0].vendor_name == "Testfirma GmbH"

    @pytest.mark.asyncio
    async def test_list_with_status_filter(
        self, service: RecurringInvoiceService, mock_db: AsyncMock
    ) -> None:
        """Sollte nach Status filtern koennen."""
        mock_count_result = Mock()
        mock_count_result.scalar.return_value = 0

        mock_items_result = Mock()
        mock_items_result.scalars.return_value.all.return_value = []

        mock_db.execute = AsyncMock(
            side_effect=[mock_count_result, mock_items_result]
        )

        items, total = await service.list_recurring_invoices(
            mock_db,
            company_id=TEST_COMPANY_UUID,
            status_filter=RecurringInvoiceStatus.CANCELLED,
            page=0,
            page_size=25,
        )

        assert total == 0
        assert len(items) == 0
        # Zwei execute-Aufrufe (count + items)
        assert mock_db.execute.call_count == 2


# ========================= Get Detail Tests =========================


class TestGetRecurringInvoice:
    """Tests fuer get_recurring_invoice."""

    @pytest.mark.asyncio
    async def test_get_recurring_invoice_detail(
        self, service: RecurringInvoiceService, mock_db: AsyncMock
    ) -> None:
        """Sollte RecurringInvoice mit Occurrences zurueckgeben."""
        occurrence = _make_mock_occurrence()
        recurring = _make_mock_recurring(occurrences=[occurrence])

        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = recurring
        mock_db.execute.return_value = mock_result

        result = await service.get_recurring_invoice(mock_db, TEST_RECURRING_UUID)

        assert result is not None
        assert result.id == TEST_RECURRING_UUID
        assert result.vendor_name == "Testfirma GmbH"
        assert len(result.occurrences) == 1

    @pytest.mark.asyncio
    async def test_get_recurring_invoice_not_found(
        self, service: RecurringInvoiceService, mock_db: AsyncMock
    ) -> None:
        """Sollte None bei unbekannter ID zurueckgeben."""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await service.get_recurring_invoice(
            mock_db, uuid.UUID("99999999-9999-9999-9999-999999999999")
        )

        assert result is None


# ========================= Update Tests =========================


class TestUpdateRecurringInvoice:
    """Tests fuer update_recurring_invoice."""

    @pytest.mark.asyncio
    async def test_update_recurring_invoice(
        self, service: RecurringInvoiceService, mock_db: AsyncMock
    ) -> None:
        """Sollte Felder aktualisieren und zurueckgeben."""
        existing = _make_mock_recurring()
        mock_db.get = AsyncMock(return_value=existing)

        request = RecurringInvoiceUpdateRequest(
            status=RecurringInvoiceStatus.PAUSED,
            expected_amount=Decimal("120.00"),
            description="Aktualisiert",
            category="IT-Infrastruktur",
        )

        result = await service.update_recurring_invoice(
            mock_db, TEST_RECURRING_UUID, request
        )

        # Pruefe dass Felder gesetzt wurden
        assert result.status == RecurringInvoiceStatus.PAUSED
        assert result.expected_amount == Decimal("120.00")
        assert result.description == "Aktualisiert"
        assert result.category == "IT-Infrastruktur"
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_recurring_invoice_not_found(
        self, service: RecurringInvoiceService, mock_db: AsyncMock
    ) -> None:
        """Sollte ValueError bei unbekannter ID werfen."""
        mock_db.get = AsyncMock(return_value=None)

        request = RecurringInvoiceUpdateRequest(
            status=RecurringInvoiceStatus.CANCELLED,
        )

        with pytest.raises(ValueError, match="nicht gefunden"):
            await service.update_recurring_invoice(
                mock_db, TEST_RECURRING_UUID, request
            )

    @pytest.mark.asyncio
    async def test_update_only_provided_fields(
        self, service: RecurringInvoiceService, mock_db: AsyncMock
    ) -> None:
        """Sollte nur explizit gesetzte Felder aktualisieren."""
        existing = _make_mock_recurring()
        existing.status = RecurringInvoiceStatus.ACTIVE
        existing.category = "Original"
        mock_db.get = AsyncMock(return_value=existing)

        # Nur tolerance_percent aendern
        request = RecurringInvoiceUpdateRequest(
            tolerance_percent=10.0,
        )

        result = await service.update_recurring_invoice(
            mock_db, TEST_RECURRING_UUID, request
        )

        # tolerance_percent sollte geaendert sein
        assert result.tolerance_percent == 10.0
        # Andere Felder sollten unveraendert bleiben
        assert result.status == RecurringInvoiceStatus.ACTIVE
        assert result.category == "Original"


# ========================= Detection Tests =========================


class TestDetectRecurringInvoices:
    """Tests fuer detect_recurring_invoices."""

    @pytest.mark.asyncio
    async def test_detect_recurring_invoices_empty(
        self, service: RecurringInvoiceService, mock_db: AsyncMock
    ) -> None:
        """Sollte leere Liste bei keinen Rechnungen zurueckgeben."""
        mock_result = Mock()
        mock_result.all.return_value = []
        mock_db.execute.return_value = mock_result

        patterns = await service.detect_recurring_invoices(
            mock_db,
            company_id=TEST_COMPANY_UUID,
            min_occurrences=3,
            lookback_months=12,
        )

        assert patterns == []

    @pytest.mark.asyncio
    async def test_detect_recurring_invoices_with_pattern(
        self, service: RecurringInvoiceService, mock_db: AsyncMock
    ) -> None:
        """Sollte Muster bei regelmaessigen Rechnungen erkennen."""
        # Erstelle 4 monatliche Rechnungen vom selben Lieferanten
        rows = []
        for i in range(4):
            inv = Mock()
            inv.invoice_date = date(2025, 7 + i, 15)
            inv.amount = 99.99

            doc = Mock()
            doc.document_metadata = {"vendor_name": "Hosting GmbH"}

            rows.append((inv, doc))

        mock_result = Mock()
        mock_result.all.return_value = rows
        mock_db.execute.return_value = mock_result

        patterns = await service.detect_recurring_invoices(
            mock_db,
            company_id=TEST_COMPANY_UUID,
            min_occurrences=3,
            lookback_months=12,
        )

        # Mindestens ein Muster sollte erkannt werden (bei 30-Tage Intervallen)
        assert len(patterns) >= 1
        pattern = patterns[0]
        assert pattern.vendor_name == "Hosting GmbH"
        assert pattern.occurrences_found == 4
        assert pattern.interval_type == RecurringIntervalType.MONTHLY
        assert pattern.confidence > 0.5

    @pytest.mark.asyncio
    async def test_detect_insufficient_occurrences(
        self, service: RecurringInvoiceService, mock_db: AsyncMock
    ) -> None:
        """Sollte Lieferanten mit zu wenig Vorkommen ignorieren."""
        rows = []
        for i in range(2):  # Nur 2, min_occurrences=3
            inv = Mock()
            inv.invoice_date = date(2025, 7 + i, 15)
            inv.amount = 50.00

            doc = Mock()
            doc.document_metadata = {"vendor_name": "Seltener Lieferant"}

            rows.append((inv, doc))

        mock_result = Mock()
        mock_result.all.return_value = rows
        mock_db.execute.return_value = mock_result

        patterns = await service.detect_recurring_invoices(
            mock_db,
            company_id=TEST_COMPANY_UUID,
            min_occurrences=3,
        )

        assert len(patterns) == 0


# ========================= Interval Classification Tests =========================


class TestClassifyInterval:
    """Tests fuer _classify_interval Hilfsmethode."""

    def test_monthly_interval(self) -> None:
        """~30 Tage sollte als MONTHLY erkannt werden."""
        interval_type, months = RecurringInvoiceService._classify_interval(30)
        assert interval_type == RecurringIntervalType.MONTHLY
        assert months == 1

    def test_bimonthly_interval(self) -> None:
        """~60 Tage sollte als MONTHLY/2 erkannt werden."""
        interval_type, months = RecurringInvoiceService._classify_interval(60)
        assert interval_type == RecurringIntervalType.MONTHLY
        assert months == 2

    def test_quarterly_interval(self) -> None:
        """~90 Tage sollte als QUARTERLY erkannt werden."""
        interval_type, months = RecurringInvoiceService._classify_interval(90)
        assert interval_type == RecurringIntervalType.QUARTERLY
        assert months == 3

    def test_half_yearly_interval(self) -> None:
        """~180 Tage sollte als HALF_YEARLY erkannt werden."""
        interval_type, months = RecurringInvoiceService._classify_interval(182)
        assert interval_type == RecurringIntervalType.HALF_YEARLY
        assert months == 6

    def test_yearly_interval(self) -> None:
        """~365 Tage sollte als YEARLY erkannt werden."""
        interval_type, months = RecurringInvoiceService._classify_interval(365)
        assert interval_type == RecurringIntervalType.YEARLY
        assert months == 12

    def test_unrecognized_interval(self) -> None:
        """Unbekannte Intervalle sollten None zurueckgeben."""
        interval_type, months = RecurringInvoiceService._classify_interval(45)
        assert interval_type is None
        assert months == 0

    def test_interval_boundary_monthly_lower(self) -> None:
        """25 Tage = untere Grenze fuer monatlich."""
        interval_type, _ = RecurringInvoiceService._classify_interval(25)
        assert interval_type == RecurringIntervalType.MONTHLY

    def test_interval_boundary_monthly_upper(self) -> None:
        """35 Tage = obere Grenze fuer monatlich."""
        interval_type, _ = RecurringInvoiceService._classify_interval(35)
        assert interval_type == RecurringIntervalType.MONTHLY


# ========================= Next Expected Date Tests =========================


class TestCalculateNextExpectedDate:
    """Tests fuer _calculate_next_expected_date Hilfsmethode."""

    def test_monthly_advance(self) -> None:
        """Monatliches Intervall sollte 1 Monat vorruecken."""
        result = RecurringInvoiceService._calculate_next_expected_date(
            date(2026, 1, 15), interval_months=1
        )
        assert result == date(2026, 2, 15)

    def test_quarterly_advance(self) -> None:
        """Vierteljaehrliches Intervall sollte 3 Monate vorruecken."""
        result = RecurringInvoiceService._calculate_next_expected_date(
            date(2026, 1, 15), interval_months=3
        )
        assert result == date(2026, 4, 15)

    def test_yearly_advance(self) -> None:
        """Jaehrliches Intervall sollte 12 Monate vorruecken."""
        result = RecurringInvoiceService._calculate_next_expected_date(
            date(2025, 6, 10), interval_months=12
        )
        assert result == date(2026, 6, 10)

    def test_year_rollover(self) -> None:
        """Sollte korrekten Jahreswechsel berechnen."""
        result = RecurringInvoiceService._calculate_next_expected_date(
            date(2026, 11, 15), interval_months=3
        )
        assert result == date(2027, 2, 15)

    def test_day_clamping(self) -> None:
        """Sollte Tag auf 28 begrenzen fuer sichere Datumsberechnung."""
        result = RecurringInvoiceService._calculate_next_expected_date(
            date(2026, 1, 31), interval_months=1
        )
        # Tag wird auf 28 geklemmt
        assert result.day == 28
        assert result.month == 2


# ========================= Missing Invoices Tests =========================


class TestCheckMissingInvoices:
    """Tests fuer check_missing_invoices."""

    @pytest.mark.asyncio
    async def test_check_missing_invoices(
        self, service: RecurringInvoiceService, mock_db: AsyncMock
    ) -> None:
        """Sollte ueberfaellige Rechnungen finden."""
        # Abo mit ueberfaelligem next_expected_date (mehr als 5 Tage)
        overdue_abo = _make_mock_recurring(
            next_expected_date=date.today() - timedelta(days=10),
        )

        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [overdue_abo]
        mock_db.execute.return_value = mock_result

        missing = await service.check_missing_invoices(mock_db, TEST_COMPANY_UUID)

        assert len(missing) == 1
        assert missing[0].vendor_name == "Testfirma GmbH"
        assert missing[0].days_overdue >= 10

    @pytest.mark.asyncio
    async def test_check_missing_invoices_ignores_recent(
        self, service: RecurringInvoiceService, mock_db: AsyncMock
    ) -> None:
        """Sollte Abos ignorieren, die weniger als 5 Tage ueberfaellig sind."""
        # Abo erst 3 Tage ueberfaellig
        recent_abo = _make_mock_recurring(
            next_expected_date=date.today() - timedelta(days=3),
        )

        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [recent_abo]
        mock_db.execute.return_value = mock_result

        missing = await service.check_missing_invoices(mock_db, TEST_COMPANY_UUID)

        assert len(missing) == 0

    @pytest.mark.asyncio
    async def test_check_missing_invoices_empty(
        self, service: RecurringInvoiceService, mock_db: AsyncMock
    ) -> None:
        """Sollte leere Liste bei keinen ueberfaelligen Abos zurueckgeben."""
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        missing = await service.check_missing_invoices(mock_db, TEST_COMPANY_UUID)

        assert missing == []


# ========================= Price Changes Tests =========================


class TestCheckPriceChanges:
    """Tests fuer check_price_changes."""

    @pytest.mark.asyncio
    async def test_check_price_changes(
        self, service: RecurringInvoiceService, mock_db: AsyncMock
    ) -> None:
        """Sollte nicht-alertierte Preisaenderungen finden."""
        abo = _make_mock_recurring()
        abo.price_increase_alerted = False
        abo.last_price_change_date = date(2026, 1, 1)
        abo.price_change_percent = 15.0
        abo.price_history = [
            {
                "date": "2026-01-01",
                "old_amount": 89.99,
                "new_amount": 99.99,
                "change_percent": 11.1,
            }
        ]

        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [abo]
        mock_db.execute.return_value = mock_result

        changes = await service.check_price_changes(mock_db, TEST_COMPANY_UUID)

        assert len(changes) == 1
        assert changes[0].vendor_name == "Testfirma GmbH"
        assert changes[0].change_percent == 11.1
        assert changes[0].change_date == date(2026, 1, 1)

    @pytest.mark.asyncio
    async def test_check_price_changes_no_history(
        self, service: RecurringInvoiceService, mock_db: AsyncMock
    ) -> None:
        """Sollte Abos ohne price_history ueberspringen."""
        abo = _make_mock_recurring()
        abo.price_history = []

        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [abo]
        mock_db.execute.return_value = mock_result

        changes = await service.check_price_changes(mock_db, TEST_COMPANY_UUID)

        assert len(changes) == 0


# ========================= Soll/Ist Report Tests =========================


class TestGetSollIstReport:
    """Tests fuer get_soll_ist_report."""

    @pytest.mark.asyncio
    async def test_get_soll_ist_report(
        self, service: RecurringInvoiceService, mock_db: AsyncMock
    ) -> None:
        """Sollte Soll/Ist-Bericht mit Zeilen generieren."""
        occurrence = _make_mock_occurrence(
            expected_date=date(2026, 1, 15),
            actual_date=date(2026, 1, 14),
            actual_amount=Decimal("99.99"),
        )
        occurrence.status = OccurrenceStatus.MATCHED

        abo = _make_mock_recurring(occurrences=[occurrence])
        abo.first_seen_date = date(2025, 1, 1)
        abo.next_expected_date = date(2026, 1, 15)

        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [abo]
        mock_db.execute.return_value = mock_result

        report = await service.get_soll_ist_report(
            mock_db,
            company_id=TEST_COMPANY_UUID,
            year=2026,
            month=1,
        )

        assert report.company_id == TEST_COMPANY_UUID
        assert report.year == 2026
        assert report.month == 1
        assert report.generated_at == date.today()
        assert len(report.rows) == 1
        assert report.rows[0].vendor_name == "Testfirma GmbH"
        assert report.matched_count == 1

    @pytest.mark.asyncio
    async def test_get_soll_ist_report_empty(
        self, service: RecurringInvoiceService, mock_db: AsyncMock
    ) -> None:
        """Sollte leeren Bericht bei keinen Abos generieren."""
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        report = await service.get_soll_ist_report(
            mock_db,
            company_id=TEST_COMPANY_UUID,
            year=2026,
            month=1,
        )

        assert report.company_id == TEST_COMPANY_UUID
        assert len(report.rows) == 0
        assert report.total_expected == Decimal("0")
        assert report.total_actual == Decimal("0")
        assert report.missing_count == 0
        assert report.matched_count == 0


# ========================= Manual Match Tests =========================


class TestManualMatchDocument:
    """Tests fuer manual_match_document."""

    @pytest.mark.asyncio
    async def test_manual_match_document(
        self, service: RecurringInvoiceService, mock_db: AsyncMock
    ) -> None:
        """Sollte Occurrence mit MANUAL-Methode erstellen."""
        recurring = _make_mock_recurring()
        recurring.match_count = 5
        mock_db.get = AsyncMock(return_value=recurring)

        result = await service.manual_match_document(
            mock_db, TEST_RECURRING_UUID, TEST_DOCUMENT_UUID
        )

        # Pruefe dass db.add aufgerufen wurde
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()

        # Pruefe das erstellte Occurrence-Objekt
        added_obj = mock_db.add.call_args[0][0]
        assert added_obj.recurring_invoice_id == TEST_RECURRING_UUID
        assert added_obj.document_id == TEST_DOCUMENT_UUID
        assert added_obj.matched_by == OccurrenceMatchMethod.MANUAL
        assert added_obj.match_confidence == 1.0
        assert added_obj.status == OccurrenceStatus.MATCHED

        # Pruefe Abo-Aktualisierung
        assert recurring.match_count == 6
        assert recurring.last_seen_date == date.today()

    @pytest.mark.asyncio
    async def test_manual_match_document_not_found(
        self, service: RecurringInvoiceService, mock_db: AsyncMock
    ) -> None:
        """Sollte ValueError bei unbekannter Recurring-ID werfen."""
        mock_db.get = AsyncMock(return_value=None)

        with pytest.raises(ValueError, match="nicht gefunden"):
            await service.manual_match_document(
                mock_db,
                uuid.UUID("99999999-9999-9999-9999-999999999999"),
                TEST_DOCUMENT_UUID,
            )

    @pytest.mark.asyncio
    async def test_manual_match_updates_next_expected_date(
        self, service: RecurringInvoiceService, mock_db: AsyncMock
    ) -> None:
        """Sollte next_expected_date nach manueller Zuordnung aktualisieren."""
        recurring = _make_mock_recurring()
        recurring.interval_months = 1
        recurring.match_count = 3
        mock_db.get = AsyncMock(return_value=recurring)

        await service.manual_match_document(
            mock_db, TEST_RECURRING_UUID, TEST_DOCUMENT_UUID
        )

        # next_expected_date sollte 1 Monat in der Zukunft liegen
        expected_next = RecurringInvoiceService._calculate_next_expected_date(
            date.today(), 1
        )
        assert recurring.next_expected_date == expected_next


# ========================= Extract Vendor Name Tests =========================


class TestExtractVendorName:
    """Tests fuer _extract_vendor_name Hilfsmethode."""

    def test_extract_vendor_name_from_vendor_name_field(self) -> None:
        """Sollte vendor_name aus document_metadata lesen."""
        doc = Mock()
        doc.document_metadata = {"vendor_name": "Testlieferant AG"}
        result = RecurringInvoiceService._extract_vendor_name(doc)
        assert result == "Testlieferant AG"

    def test_extract_vendor_name_from_sender_name(self) -> None:
        """Sollte sender_name als Fallback nutzen."""
        doc = Mock()
        doc.document_metadata = {"sender_name": "Absender GmbH"}
        result = RecurringInvoiceService._extract_vendor_name(doc)
        assert result == "Absender GmbH"

    def test_extract_vendor_name_from_absender(self) -> None:
        """Sollte absender-Feld als Fallback nutzen."""
        doc = Mock()
        doc.document_metadata = {"absender": "Deutscher Lieferant"}
        result = RecurringInvoiceService._extract_vendor_name(doc)
        assert result == "Deutscher Lieferant"

    def test_extract_vendor_name_missing_metadata(self) -> None:
        """Sollte None bei fehlenden Metadaten zurueckgeben."""
        doc = Mock()
        doc.document_metadata = {}
        result = RecurringInvoiceService._extract_vendor_name(doc)
        assert result is None

    def test_extract_vendor_name_none_metadata(self) -> None:
        """Sollte None bei None-Metadaten zurueckgeben."""
        doc = Mock()
        doc.document_metadata = None
        result = RecurringInvoiceService._extract_vendor_name(doc)
        assert result is None

    def test_extract_vendor_name_empty_string(self) -> None:
        """Sollte None bei leerem String zurueckgeben."""
        doc = Mock()
        doc.document_metadata = {"vendor_name": "   "}
        result = RecurringInvoiceService._extract_vendor_name(doc)
        assert result is None

    def test_extract_vendor_name_strips_whitespace(self) -> None:
        """Sollte Whitespace trimmen."""
        doc = Mock()
        doc.document_metadata = {"vendor_name": "  Trimmed Name  "}
        result = RecurringInvoiceService._extract_vendor_name(doc)
        assert result == "Trimmed Name"


# ========================= Determine Occurrence Status Tests =========================


class TestDetermineOccurrenceStatus:
    """Tests fuer _determine_occurrence_status."""

    def test_matched_within_tolerance(self) -> None:
        """Betrag innerhalb 5% Toleranz und puenktlich -> MATCHED."""
        status = RecurringInvoiceService._determine_occurrence_status(
            expected_amount=Decimal("100.00"),
            actual_amount=Decimal("100.00"),
            expected_date=date(2026, 1, 15),
            actual_date=date(2026, 1, 15),
        )
        assert status == OccurrenceStatus.MATCHED

    def test_late_arrival(self) -> None:
        """Betrag OK aber >15 Tage verspaetet -> LATE."""
        status = RecurringInvoiceService._determine_occurrence_status(
            expected_amount=Decimal("100.00"),
            actual_amount=Decimal("100.00"),
            expected_date=date(2026, 1, 1),
            actual_date=date(2026, 1, 20),
        )
        assert status == OccurrenceStatus.LATE

    def test_overpaid(self) -> None:
        """Deutlich ueberzahlt -> OVERPAID."""
        status = RecurringInvoiceService._determine_occurrence_status(
            expected_amount=Decimal("100.00"),
            actual_amount=Decimal("120.00"),
            expected_date=date(2026, 1, 15),
            actual_date=date(2026, 1, 15),
        )
        assert status == OccurrenceStatus.OVERPAID

    def test_underpaid(self) -> None:
        """Deutlich unterzahlt -> UNDERPAID."""
        status = RecurringInvoiceService._determine_occurrence_status(
            expected_amount=Decimal("100.00"),
            actual_amount=Decimal("80.00"),
            expected_date=date(2026, 1, 15),
            actual_date=date(2026, 1, 15),
        )
        assert status == OccurrenceStatus.UNDERPAID

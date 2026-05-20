# -*- coding: utf-8 -*-
"""
Unit-Tests fuer Recurring Invoices (Abo-Verwaltung) API Endpoints.

Testet:
- GET /recurring-invoices - Paginierte Liste
- GET /recurring-invoices/{id} - Detail mit Occurrences
- POST /recurring-invoices - Manuelle Erstellung
- PATCH /recurring-invoices/{id} - Aktualisierung
- POST /recurring-invoices/detect - Muster-Erkennung
- GET /recurring-invoices/missing - Fehlende Rechnungen
- GET /recurring-invoices/price-changes - Preisaenderungen
- GET /recurring-invoices/soll-ist - Soll/Ist-Vergleich
- POST /recurring-invoices/{id}/match - Manuelle Zuordnung
- Fehlerbehandlung (404, 403, 400)

Feinpoliert und durchdacht - Enterprise Abo-Verwaltung Tests.
"""

import pytest
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import List, Optional
from unittest.mock import AsyncMock, Mock, MagicMock, patch
from uuid import UUID

from fastapi import HTTPException

from app.api.v1.recurring_invoices import (
    RecurringInvoiceCreateSchema,
    RecurringInvoiceUpdateSchema,
    ManualMatchSchema,
    _build_recurring_response,
    _build_occurrence_response,
    list_recurring_invoices,
    get_recurring_invoice,
    create_recurring_invoice,
    update_recurring_invoice,
    detect_recurring_invoices,
    get_missing_invoices,
    get_price_changes,
    get_soll_ist_report,
    manual_match_document,
)
from app.db.models_recurring_invoice import (
    RecurringInvoiceStatus,
    RecurringIntervalType,
    DetectionMethod,
    OccurrenceStatus,
    OccurrenceMatchMethod,
)


# ========================= Test-Konstanten =========================

TEST_USER_UUID = UUID("00000000-0000-0000-0000-000000000001")
TEST_COMPANY_UUID = UUID("00000000-0000-0000-0000-000000000002")
TEST_VENDOR_ENTITY_UUID = UUID("00000000-0000-0000-0000-000000000003")
TEST_DOCUMENT_UUID = UUID("00000000-0000-0000-0000-000000000004")
TEST_RECURRING_UUID = UUID("00000000-0000-0000-0000-000000000005")
TEST_OCCURRENCE_UUID = UUID("00000000-0000-0000-0000-000000000006")
TEST_INVOICE_TRACKING_UUID = UUID("00000000-0000-0000-0000-000000000007")

pytestmark = [pytest.mark.unit, pytest.mark.api]


# ========================= Helper =========================


def _make_mock_recurring(
    recurring_id: UUID = TEST_RECURRING_UUID,
    company_id: UUID = TEST_COMPANY_UUID,
    status: RecurringInvoiceStatus = RecurringInvoiceStatus.ACTIVE,
    vendor_name: str = "Testfirma GmbH",
    occurrences: Optional[List[Mock]] = None,
) -> Mock:
    """Erstellt ein Mock-RecurringInvoice Objekt."""
    r = Mock()
    r.id = recurring_id
    r.company_id = company_id
    r.vendor_entity_id = TEST_VENDOR_ENTITY_UUID
    r.vendor_name = vendor_name
    r.interval_type = RecurringIntervalType.MONTHLY
    r.interval_months = 1
    r.expected_amount = Decimal("99.99")
    r.currency = "EUR"
    r.tolerance_percent = 5.0
    r.first_seen_date = date(2025, 6, 1)
    r.last_seen_date = date(2026, 1, 15)
    r.next_expected_date = date(2026, 2, 15)
    r.cancellation_deadline = date(2026, 12, 31)
    r.notice_period_days = 30
    r.auto_renewal = True
    r.detection_confidence = 0.95
    r.detection_method = DetectionMethod.AUTO
    r.match_count = 8
    r.price_history = [
        {"date": "2025-12-01", "amount": 89.99, "change_percent": 11.1},
    ]
    r.last_price_change_date = date(2025, 12, 1)
    r.price_change_percent = 11.1
    r.status = status
    r.price_increase_alerted = False
    r.missing_invoice_alerted = False
    r.category = "Software"
    r.description = "Monatliches Abo fuer Testsoftware"
    r.document_type = "Rechnung"
    r.reference_pattern = r"INV-\d{4}-\d+"
    r.created_at = datetime(2025, 6, 1, 10, 0, 0, tzinfo=timezone.utc)
    r.updated_at = datetime(2026, 1, 15, 14, 30, 0, tzinfo=timezone.utc)
    r.occurrences = occurrences if occurrences is not None else []
    return r


def _make_mock_occurrence(
    occurrence_id: UUID = TEST_OCCURRENCE_UUID,
    recurring_id: UUID = TEST_RECURRING_UUID,
    status: OccurrenceStatus = OccurrenceStatus.MATCHED,
) -> Mock:
    """Erstellt ein Mock-RecurringInvoiceOccurrence Objekt."""
    o = Mock()
    o.id = occurrence_id
    o.recurring_invoice_id = recurring_id
    o.document_id = TEST_DOCUMENT_UUID
    o.invoice_tracking_id = TEST_INVOICE_TRACKING_UUID
    o.expected_date = date(2026, 1, 15)
    o.actual_date = date(2026, 1, 14)
    o.expected_amount = Decimal("99.99")
    o.actual_amount = Decimal("99.99")
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


def _make_mock_user(
    user_id: UUID = TEST_USER_UUID,
    company_id: UUID = TEST_COMPANY_UUID,
) -> Mock:
    """Erstellt ein Mock-User Objekt."""
    user = Mock()
    user.id = user_id
    user.company_id = company_id
    user.email = "test@example.com"
    user.is_active = True
    return user


def _make_mock_request() -> Mock:
    """Erstellt ein Mock-Request Objekt (fuer rate limiter)."""
    request = Mock()
    request.client = Mock()
    request.client.host = "127.0.0.1"
    request.state = Mock()
    return request


# ========================= Fixtures =========================


@pytest.fixture
def mock_recurring() -> Mock:
    """Standard Mock-RecurringInvoice."""
    return _make_mock_recurring()


@pytest.fixture
def mock_occurrence() -> Mock:
    """Standard Mock-Occurrence."""
    return _make_mock_occurrence()


@pytest.fixture
def mock_user() -> Mock:
    """Standard Mock-User."""
    return _make_mock_user()


@pytest.fixture
def mock_db() -> AsyncMock:
    """Erstellt Mock-DB-Session."""
    return AsyncMock()


@pytest.fixture
def mock_request() -> Mock:
    """Erstellt Mock-Request."""
    return _make_mock_request()


# ========================= Helper-Funktionen Tests =========================


class TestBuildRecurringResponse:
    """Tests fuer _build_recurring_response Helper."""

    def test_build_response_maps_all_fields(self, mock_recurring: Mock) -> None:
        """Sollte alle Felder korrekt aus dem Model mappen."""
        response = _build_recurring_response(mock_recurring)
        assert response.id == TEST_RECURRING_UUID
        assert response.company_id == TEST_COMPANY_UUID
        assert response.vendor_name == "Testfirma GmbH"
        assert response.interval_type == RecurringIntervalType.MONTHLY
        assert response.interval_months == 1
        assert response.expected_amount == 99.99
        assert response.currency == "EUR"
        assert response.status == RecurringInvoiceStatus.ACTIVE
        assert response.match_count == 8
        assert response.detection_confidence == 0.95
        assert response.detection_method == DetectionMethod.AUTO
        assert response.category == "Software"

    def test_build_response_handles_none_values(self) -> None:
        """Sollte None-Werte korrekt als Defaults behandeln."""
        r = _make_mock_recurring()
        r.expected_amount = None
        r.currency = None
        r.tolerance_percent = None
        r.auto_renewal = None
        r.detection_confidence = None
        r.match_count = None
        r.price_history = None
        r.price_increase_alerted = None
        r.missing_invoice_alerted = None

        response = _build_recurring_response(r)
        assert response.expected_amount == 0.0
        assert response.currency == "EUR"
        assert response.tolerance_percent == 5.0
        assert response.auto_renewal is True
        assert response.detection_confidence == 0.0
        assert response.match_count == 0
        assert response.price_history == []
        assert response.price_increase_alerted is False
        assert response.missing_invoice_alerted is False

    def test_build_response_price_history_dicts(self) -> None:
        """Sollte price_history dict-Eintraege korrekt mappen."""
        r = _make_mock_recurring()
        r.price_history = [
            {"date": "2025-12-01", "amount": 89.99, "change_percent": 11.1},
            {"date": "2026-01-01", "amount": 99.99, "change_percent": 0.0},
        ]
        response = _build_recurring_response(r)
        assert len(response.price_history) == 2


class TestBuildOccurrenceResponse:
    """Tests fuer _build_occurrence_response Helper."""

    def test_build_occurrence_maps_all_fields(self, mock_occurrence: Mock) -> None:
        """Sollte Occurrence-Felder korrekt mappen."""
        response = _build_occurrence_response(mock_occurrence)
        assert response.id == TEST_OCCURRENCE_UUID
        assert response.recurring_invoice_id == TEST_RECURRING_UUID
        assert response.document_id == TEST_DOCUMENT_UUID
        assert response.expected_date == date(2026, 1, 15)
        assert response.actual_date == date(2026, 1, 14)
        assert response.expected_amount == 99.99
        assert response.actual_amount == 99.99
        assert response.status == OccurrenceStatus.MATCHED
        assert response.match_confidence == 0.95
        assert response.matched_by == OccurrenceMatchMethod.AUTO

    def test_build_occurrence_handles_none_amounts(self) -> None:
        """Sollte None bei actual_amount und amount_deviation korrekt behandeln."""
        o = _make_mock_occurrence()
        o.actual_amount = None
        o.amount_deviation = None
        o.expected_amount = None

        response = _build_occurrence_response(o)
        assert response.actual_amount is None
        assert response.amount_deviation is None
        assert response.expected_amount == 0.0


# ========================= List Endpoint Tests =========================


class TestListRecurringInvoices:
    """Tests fuer GET /recurring-invoices."""

    @pytest.mark.asyncio
    @patch("app.api.v1.recurring_invoices.get_recurring_invoice_service")
    @patch("app.api.v1.recurring_invoices.limiter")
    async def test_list_recurring_invoices_success(
        self,
        mock_limiter: Mock,
        mock_get_service: Mock,
        mock_user: Mock,
        mock_db: AsyncMock,
        mock_request: Mock,
        mock_recurring: Mock,
    ) -> None:
        """GET / sollte paginierte Liste zurueckgeben."""
        mock_service = AsyncMock()
        mock_service.list_recurring_invoices.return_value = ([mock_recurring], 1)
        mock_get_service.return_value = mock_service

        result = await list_recurring_invoices.__wrapped__(
            request=mock_request,
            status_filter=None,
            page=0,
            page_size=25,
            current_user=mock_user,
            db=mock_db,
        )

        assert result.total == 1
        assert result.page == 0
        assert result.page_size == 25
        assert len(result.items) == 1
        assert result.items[0].vendor_name == "Testfirma GmbH"
        mock_service.list_recurring_invoices.assert_called_once_with(
            mock_db,
            company_id=TEST_COMPANY_UUID,
            status_filter=None,
            page=0,
            page_size=25,
        )

    @pytest.mark.asyncio
    @patch("app.api.v1.recurring_invoices.get_recurring_invoice_service")
    @patch("app.api.v1.recurring_invoices.limiter")
    async def test_list_recurring_invoices_with_status_filter(
        self,
        mock_limiter: Mock,
        mock_get_service: Mock,
        mock_user: Mock,
        mock_db: AsyncMock,
        mock_request: Mock,
    ) -> None:
        """GET /?status=active sollte nach Status filtern."""
        mock_service = AsyncMock()
        mock_service.list_recurring_invoices.return_value = ([], 0)
        mock_get_service.return_value = mock_service

        result = await list_recurring_invoices.__wrapped__(
            request=mock_request,
            status_filter=RecurringInvoiceStatus.ACTIVE,
            page=0,
            page_size=25,
            current_user=mock_user,
            db=mock_db,
        )

        assert result.total == 0
        assert len(result.items) == 0
        mock_service.list_recurring_invoices.assert_called_once_with(
            mock_db,
            company_id=TEST_COMPANY_UUID,
            status_filter=RecurringInvoiceStatus.ACTIVE,
            page=0,
            page_size=25,
        )

    @pytest.mark.asyncio
    @patch("app.api.v1.recurring_invoices.get_recurring_invoice_service")
    @patch("app.api.v1.recurring_invoices.limiter")
    async def test_list_recurring_invoices_empty(
        self,
        mock_limiter: Mock,
        mock_get_service: Mock,
        mock_user: Mock,
        mock_db: AsyncMock,
        mock_request: Mock,
    ) -> None:
        """GET / sollte leere Liste bei keinen Ergebnissen zurueckgeben."""
        mock_service = AsyncMock()
        mock_service.list_recurring_invoices.return_value = ([], 0)
        mock_get_service.return_value = mock_service

        result = await list_recurring_invoices.__wrapped__(
            request=mock_request,
            status_filter=None,
            page=0,
            page_size=25,
            current_user=mock_user,
            db=mock_db,
        )

        assert result.total == 0
        assert len(result.items) == 0


# ========================= Get Detail Endpoint Tests =========================


class TestGetRecurringInvoice:
    """Tests fuer GET /recurring-invoices/{id}."""

    @pytest.mark.asyncio
    @patch("app.api.v1.recurring_invoices.get_recurring_invoice_service")
    @patch("app.api.v1.recurring_invoices.limiter")
    async def test_get_recurring_invoice_detail(
        self,
        mock_limiter: Mock,
        mock_get_service: Mock,
        mock_user: Mock,
        mock_db: AsyncMock,
        mock_request: Mock,
    ) -> None:
        """GET /{id} sollte Detail mit Occurrences zurueckgeben."""
        occurrence = _make_mock_occurrence()
        recurring = _make_mock_recurring(occurrences=[occurrence])
        mock_service = AsyncMock()
        mock_service.get_recurring_invoice.return_value = recurring
        mock_get_service.return_value = mock_service

        result = await get_recurring_invoice.__wrapped__(
            request=mock_request,
            recurring_id=TEST_RECURRING_UUID,
            current_user=mock_user,
            db=mock_db,
        )

        assert result.id == TEST_RECURRING_UUID
        assert result.vendor_name == "Testfirma GmbH"
        assert len(result.occurrences) == 1
        assert result.occurrences[0].id == TEST_OCCURRENCE_UUID
        mock_service.get_recurring_invoice.assert_called_once_with(
            mock_db, TEST_RECURRING_UUID,
        )

    @pytest.mark.asyncio
    @patch("app.api.v1.recurring_invoices.get_recurring_invoice_service")
    @patch("app.api.v1.recurring_invoices.limiter")
    async def test_get_recurring_invoice_not_found(
        self,
        mock_limiter: Mock,
        mock_get_service: Mock,
        mock_user: Mock,
        mock_db: AsyncMock,
        mock_request: Mock,
    ) -> None:
        """GET /{id} sollte 404 bei unbekannter ID zurueckgeben."""
        mock_service = AsyncMock()
        mock_service.get_recurring_invoice.return_value = None
        mock_get_service.return_value = mock_service

        with pytest.raises(HTTPException) as exc_info:
            await get_recurring_invoice.__wrapped__(
                request=mock_request,
                recurring_id=TEST_RECURRING_UUID,
                current_user=mock_user,
                db=mock_db,
            )

        assert exc_info.value.status_code == 404
        assert "nicht gefunden" in exc_info.value.detail

    @pytest.mark.asyncio
    @patch("app.api.v1.recurring_invoices.get_recurring_invoice_service")
    @patch("app.api.v1.recurring_invoices.limiter")
    async def test_get_recurring_invoice_forbidden(
        self,
        mock_limiter: Mock,
        mock_get_service: Mock,
        mock_user: Mock,
        mock_db: AsyncMock,
        mock_request: Mock,
    ) -> None:
        """GET /{id} sollte 403 bei fremder company_id zurueckgeben."""
        # Erstelle Recurring mit anderer company_id
        other_company = UUID("00000000-0000-0000-0000-000000000099")
        recurring = _make_mock_recurring(company_id=other_company)
        mock_service = AsyncMock()
        mock_service.get_recurring_invoice.return_value = recurring
        mock_get_service.return_value = mock_service

        with pytest.raises(HTTPException) as exc_info:
            await get_recurring_invoice.__wrapped__(
                request=mock_request,
                recurring_id=TEST_RECURRING_UUID,
                current_user=mock_user,
                db=mock_db,
            )

        assert exc_info.value.status_code == 403
        assert "Kein Zugriff" in exc_info.value.detail


# ========================= Create Endpoint Tests =========================


class TestCreateRecurringInvoice:
    """Tests fuer POST /recurring-invoices."""

    @pytest.mark.asyncio
    @patch("app.api.v1.recurring_invoices.get_recurring_invoice_service")
    @patch("app.api.v1.recurring_invoices.limiter")
    async def test_create_recurring_invoice(
        self,
        mock_limiter: Mock,
        mock_get_service: Mock,
        mock_user: Mock,
        mock_db: AsyncMock,
        mock_request: Mock,
        mock_recurring: Mock,
    ) -> None:
        """POST / sollte wiederkehrende Rechnung erstellen."""
        mock_service = AsyncMock()
        mock_service.create_recurring_invoice.return_value = mock_recurring
        mock_get_service.return_value = mock_service

        create_data = RecurringInvoiceCreateSchema(
            vendor_name="Testfirma GmbH",
            interval_type=RecurringIntervalType.MONTHLY,
            interval_months=1,
            expected_amount=Decimal("99.99"),
            currency="EUR",
            tolerance_percent=5.0,
            auto_renewal=True,
            category="Software",
        )

        result = await create_recurring_invoice.__wrapped__(
            request=mock_request,
            data=create_data,
            current_user=mock_user,
            db=mock_db,
        )

        assert result.vendor_name == "Testfirma GmbH"
        assert result.status == RecurringInvoiceStatus.ACTIVE
        mock_service.create_recurring_invoice.assert_called_once()
        # Pruefe dass company_id vom User gesetzt wird
        call_args = mock_service.create_recurring_invoice.call_args
        request_obj = call_args[0][1]  # Zweites positional arg
        assert request_obj.company_id == TEST_COMPANY_UUID

    @pytest.mark.asyncio
    @patch("app.api.v1.recurring_invoices.get_recurring_invoice_service")
    @patch("app.api.v1.recurring_invoices.limiter")
    async def test_create_recurring_invoice_invalid_regex(
        self,
        mock_limiter: Mock,
        mock_get_service: Mock,
        mock_user: Mock,
        mock_db: AsyncMock,
        mock_request: Mock,
    ) -> None:
        """POST / sollte 422 bei ungueltigem reference_pattern zurueckgeben."""
        # Pydantic-Validierung schlaegt bei ungueltigem Regex fehl
        with pytest.raises(Exception):
            RecurringInvoiceCreateSchema(
                vendor_name="Test GmbH",
                expected_amount=Decimal("100.00"),
                reference_pattern="[invalid(regex",  # Ungueltiger Regex
            )

    @pytest.mark.asyncio
    @patch("app.api.v1.recurring_invoices.get_recurring_invoice_service")
    @patch("app.api.v1.recurring_invoices.limiter")
    async def test_create_recurring_invoice_service_error(
        self,
        mock_limiter: Mock,
        mock_get_service: Mock,
        mock_user: Mock,
        mock_db: AsyncMock,
        mock_request: Mock,
    ) -> None:
        """POST / sollte 400 bei ValueError vom Service zurueckgeben."""
        mock_service = AsyncMock()
        mock_service.create_recurring_invoice.side_effect = ValueError(
            "Validierungsfehler"
        )
        mock_get_service.return_value = mock_service

        create_data = RecurringInvoiceCreateSchema(
            vendor_name="Test GmbH",
            expected_amount=Decimal("100.00"),
        )

        with pytest.raises(HTTPException) as exc_info:
            await create_recurring_invoice.__wrapped__(
                request=mock_request,
                data=create_data,
                current_user=mock_user,
                db=mock_db,
            )

        assert exc_info.value.status_code == 400


# ========================= Update Endpoint Tests =========================


class TestUpdateRecurringInvoice:
    """Tests fuer PATCH /recurring-invoices/{id}."""

    @pytest.mark.asyncio
    @patch("app.api.v1.recurring_invoices.get_recurring_invoice_service")
    @patch("app.api.v1.recurring_invoices.limiter")
    async def test_update_recurring_invoice(
        self,
        mock_limiter: Mock,
        mock_get_service: Mock,
        mock_user: Mock,
        mock_db: AsyncMock,
        mock_request: Mock,
        mock_recurring: Mock,
    ) -> None:
        """PATCH /{id} sollte Felder aktualisieren."""
        # Simuliere aktualisiertes Objekt
        updated = _make_mock_recurring()
        updated.status = RecurringInvoiceStatus.PAUSED
        updated.description = "Aktualisierte Beschreibung"

        mock_service = AsyncMock()
        mock_service.update_recurring_invoice.return_value = updated
        mock_get_service.return_value = mock_service

        update_data = RecurringInvoiceUpdateSchema(
            status=RecurringInvoiceStatus.PAUSED,
            description="Aktualisierte Beschreibung",
        )

        result = await update_recurring_invoice.__wrapped__(
            request=mock_request,
            data=update_data,
            recurring_id=TEST_RECURRING_UUID,
            current_user=mock_user,
            db=mock_db,
        )

        assert result.status == RecurringInvoiceStatus.PAUSED
        mock_service.update_recurring_invoice.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.api.v1.recurring_invoices.get_recurring_invoice_service")
    @patch("app.api.v1.recurring_invoices.limiter")
    async def test_update_recurring_invoice_not_found(
        self,
        mock_limiter: Mock,
        mock_get_service: Mock,
        mock_user: Mock,
        mock_db: AsyncMock,
        mock_request: Mock,
    ) -> None:
        """PATCH /{id} sollte 400 bei ValueError (nicht gefunden) zurueckgeben."""
        mock_service = AsyncMock()
        mock_service.update_recurring_invoice.side_effect = ValueError(
            "Nicht gefunden"
        )
        mock_get_service.return_value = mock_service

        update_data = RecurringInvoiceUpdateSchema(
            status=RecurringInvoiceStatus.CANCELLED,
        )

        with pytest.raises(HTTPException) as exc_info:
            await update_recurring_invoice.__wrapped__(
                request=mock_request,
                data=update_data,
                recurring_id=TEST_RECURRING_UUID,
                current_user=mock_user,
                db=mock_db,
            )

        assert exc_info.value.status_code == 400


# ========================= Detect Endpoint Tests =========================


class TestDetectRecurringInvoices:
    """Tests fuer POST /recurring-invoices/detect."""

    @pytest.mark.asyncio
    @patch("app.api.v1.recurring_invoices.get_recurring_invoice_service")
    @patch("app.api.v1.recurring_invoices.limiter")
    async def test_detect_patterns_success(
        self,
        mock_limiter: Mock,
        mock_get_service: Mock,
        mock_user: Mock,
        mock_db: AsyncMock,
        mock_request: Mock,
    ) -> None:
        """POST /detect sollte erkannte Muster zurueckgeben."""
        # Erstelle Mock-DetectedPattern
        pattern = Mock()
        pattern.vendor_name = "Cloud Provider AG"
        pattern.vendor_entity_id = TEST_VENDOR_ENTITY_UUID
        pattern.interval_type = RecurringIntervalType.MONTHLY
        pattern.interval_months = 1
        pattern.average_amount = Decimal("199.00")
        pattern.occurrences_found = 6
        pattern.confidence = 0.87
        pattern.first_date = date(2025, 7, 1)
        pattern.last_date = date(2026, 1, 1)

        mock_service = AsyncMock()
        mock_service.detect_recurring_invoices.return_value = [pattern]
        mock_get_service.return_value = mock_service

        result = await detect_recurring_invoices.__wrapped__(
            request=mock_request,
            min_occurrences=3,
            lookback_months=12,
            current_user=mock_user,
            db=mock_db,
        )

        assert len(result) == 1
        assert result[0].vendor_name == "Cloud Provider AG"
        assert result[0].occurrences_found == 6
        assert result[0].confidence == 0.87
        mock_service.detect_recurring_invoices.assert_called_once_with(
            mock_db,
            company_id=TEST_COMPANY_UUID,
            min_occurrences=3,
            lookback_months=12,
        )

    @pytest.mark.asyncio
    @patch("app.api.v1.recurring_invoices.get_recurring_invoice_service")
    @patch("app.api.v1.recurring_invoices.limiter")
    async def test_detect_patterns_with_params(
        self,
        mock_limiter: Mock,
        mock_get_service: Mock,
        mock_user: Mock,
        mock_db: AsyncMock,
        mock_request: Mock,
    ) -> None:
        """POST /detect sollte benutzerdefinierte Parameter weiterleiten."""
        mock_service = AsyncMock()
        mock_service.detect_recurring_invoices.return_value = []
        mock_get_service.return_value = mock_service

        result = await detect_recurring_invoices.__wrapped__(
            request=mock_request,
            min_occurrences=5,
            lookback_months=6,
            current_user=mock_user,
            db=mock_db,
        )

        assert len(result) == 0
        mock_service.detect_recurring_invoices.assert_called_once_with(
            mock_db,
            company_id=TEST_COMPANY_UUID,
            min_occurrences=5,
            lookback_months=6,
        )

    @pytest.mark.asyncio
    @patch("app.api.v1.recurring_invoices.get_recurring_invoice_service")
    @patch("app.api.v1.recurring_invoices.limiter")
    async def test_detect_patterns_service_error(
        self,
        mock_limiter: Mock,
        mock_get_service: Mock,
        mock_user: Mock,
        mock_db: AsyncMock,
        mock_request: Mock,
    ) -> None:
        """POST /detect sollte 500 bei Service-Fehler zurueckgeben."""
        mock_service = AsyncMock()
        mock_service.detect_recurring_invoices.side_effect = RuntimeError("DB down")
        mock_get_service.return_value = mock_service

        with pytest.raises(HTTPException) as exc_info:
            await detect_recurring_invoices.__wrapped__(
                request=mock_request,
                min_occurrences=3,
                lookback_months=12,
                current_user=mock_user,
                db=mock_db,
            )

        assert exc_info.value.status_code == 500


# ========================= Missing Invoices Tests =========================


class TestGetMissingInvoices:
    """Tests fuer GET /recurring-invoices/missing."""

    @pytest.mark.asyncio
    @patch("app.api.v1.recurring_invoices.get_recurring_invoice_service")
    @patch("app.api.v1.recurring_invoices.limiter")
    async def test_get_missing_invoices(
        self,
        mock_limiter: Mock,
        mock_get_service: Mock,
        mock_user: Mock,
        mock_db: AsyncMock,
        mock_request: Mock,
    ) -> None:
        """GET /missing sollte fehlende Rechnungen zurueckgeben."""
        missing_info = Mock()
        missing_info.recurring_invoice_id = TEST_RECURRING_UUID
        missing_info.vendor_name = "Telekom AG"
        missing_info.expected_date = date(2026, 1, 15)
        missing_info.expected_amount = Decimal("49.99")
        missing_info.days_overdue = 25

        mock_service = AsyncMock()
        mock_service.check_missing_invoices.return_value = [missing_info]
        mock_get_service.return_value = mock_service

        result = await get_missing_invoices.__wrapped__(
            request=mock_request,
            current_user=mock_user,
            db=mock_db,
        )

        assert len(result) == 1
        assert result[0].vendor_name == "Telekom AG"
        assert result[0].days_overdue == 25
        assert result[0].expected_amount == 49.99
        mock_service.check_missing_invoices.assert_called_once_with(
            mock_db, TEST_COMPANY_UUID,
        )

    @pytest.mark.asyncio
    @patch("app.api.v1.recurring_invoices.get_recurring_invoice_service")
    @patch("app.api.v1.recurring_invoices.limiter")
    async def test_get_missing_invoices_empty(
        self,
        mock_limiter: Mock,
        mock_get_service: Mock,
        mock_user: Mock,
        mock_db: AsyncMock,
        mock_request: Mock,
    ) -> None:
        """GET /missing sollte leere Liste bei keinen Fehlenden zurueckgeben."""
        mock_service = AsyncMock()
        mock_service.check_missing_invoices.return_value = []
        mock_get_service.return_value = mock_service

        result = await get_missing_invoices.__wrapped__(
            request=mock_request,
            current_user=mock_user,
            db=mock_db,
        )

        assert len(result) == 0


# ========================= Price Changes Tests =========================


class TestGetPriceChanges:
    """Tests fuer GET /recurring-invoices/price-changes."""

    @pytest.mark.asyncio
    @patch("app.api.v1.recurring_invoices.get_recurring_invoice_service")
    @patch("app.api.v1.recurring_invoices.limiter")
    async def test_get_price_changes(
        self,
        mock_limiter: Mock,
        mock_get_service: Mock,
        mock_user: Mock,
        mock_db: AsyncMock,
        mock_request: Mock,
    ) -> None:
        """GET /price-changes sollte Preisaenderungen zurueckgeben."""
        change = Mock()
        change.recurring_invoice_id = TEST_RECURRING_UUID
        change.vendor_name = "Hosting GmbH"
        change.old_amount = Decimal("29.99")
        change.new_amount = Decimal("34.99")
        change.change_percent = 16.67
        change.change_date = date(2026, 1, 1)

        mock_service = AsyncMock()
        mock_service.check_price_changes.return_value = [change]
        mock_get_service.return_value = mock_service

        result = await get_price_changes.__wrapped__(
            request=mock_request,
            current_user=mock_user,
            db=mock_db,
        )

        assert len(result) == 1
        assert result[0].vendor_name == "Hosting GmbH"
        assert result[0].old_amount == 29.99
        assert result[0].new_amount == 34.99
        assert result[0].change_percent == 16.67


# ========================= Soll/Ist Report Tests =========================


class TestGetSollIstReport:
    """Tests fuer GET /recurring-invoices/soll-ist."""

    @pytest.mark.asyncio
    @patch("app.api.v1.recurring_invoices.get_recurring_invoice_service")
    @patch("app.api.v1.recurring_invoices.limiter")
    async def test_get_soll_ist_report(
        self,
        mock_limiter: Mock,
        mock_get_service: Mock,
        mock_user: Mock,
        mock_db: AsyncMock,
        mock_request: Mock,
    ) -> None:
        """GET /soll-ist sollte Soll/Ist-Bericht zurueckgeben."""
        # Erstelle Mock-Report
        row = Mock()
        row.recurring_invoice_id = TEST_RECURRING_UUID
        row.vendor_name = "Testfirma GmbH"
        row.category = "Software"
        row.expected_amount = Decimal("99.99")
        row.actual_amount = Decimal("99.99")
        row.deviation = Decimal("0.00")
        row.deviation_percent = 0.0
        row.status = OccurrenceStatus.MATCHED
        row.expected_date = date(2026, 1, 15)
        row.actual_date = date(2026, 1, 14)

        report = Mock()
        report.company_id = TEST_COMPANY_UUID
        report.year = 2026
        report.month = 1
        report.rows = [row]
        report.total_expected = Decimal("99.99")
        report.total_actual = Decimal("99.99")
        report.total_deviation = Decimal("0.00")
        report.missing_count = 0
        report.matched_count = 1
        report.generated_at = date(2026, 2, 10)

        mock_service = AsyncMock()
        mock_service.get_soll_ist_report.return_value = report
        mock_get_service.return_value = mock_service

        result = await get_soll_ist_report.__wrapped__(
            request=mock_request,
            year=2026,
            month=1,
            current_user=mock_user,
            db=mock_db,
        )

        assert result.company_id == TEST_COMPANY_UUID
        assert result.year == 2026
        assert result.month == 1
        assert len(result.rows) == 1
        assert result.rows[0].vendor_name == "Testfirma GmbH"
        assert result.total_expected == 99.99
        assert result.missing_count == 0
        assert result.matched_count == 1
        mock_service.get_soll_ist_report.assert_called_once_with(
            mock_db,
            company_id=TEST_COMPANY_UUID,
            year=2026,
            month=1,
        )

    @pytest.mark.asyncio
    @patch("app.api.v1.recurring_invoices.get_recurring_invoice_service")
    @patch("app.api.v1.recurring_invoices.limiter")
    async def test_get_soll_ist_report_with_missing(
        self,
        mock_limiter: Mock,
        mock_get_service: Mock,
        mock_user: Mock,
        mock_db: AsyncMock,
        mock_request: Mock,
    ) -> None:
        """GET /soll-ist sollte fehlende Rechnungen im Bericht anzeigen."""
        row = Mock()
        row.recurring_invoice_id = TEST_RECURRING_UUID
        row.vendor_name = "Fehlend GmbH"
        row.category = None
        row.expected_amount = Decimal("50.00")
        row.actual_amount = None
        row.deviation = None
        row.deviation_percent = None
        row.status = OccurrenceStatus.MISSING
        row.expected_date = date(2026, 1, 15)
        row.actual_date = None

        report = Mock()
        report.company_id = TEST_COMPANY_UUID
        report.year = 2026
        report.month = 1
        report.rows = [row]
        report.total_expected = Decimal("50.00")
        report.total_actual = Decimal("0.00")
        report.total_deviation = Decimal("-50.00")
        report.missing_count = 1
        report.matched_count = 0
        report.generated_at = date(2026, 2, 10)

        mock_service = AsyncMock()
        mock_service.get_soll_ist_report.return_value = report
        mock_get_service.return_value = mock_service

        result = await get_soll_ist_report.__wrapped__(
            request=mock_request,
            year=2026,
            month=1,
            current_user=mock_user,
            db=mock_db,
        )

        assert result.missing_count == 1
        assert result.rows[0].status == OccurrenceStatus.MISSING
        assert result.rows[0].actual_amount is None


# ========================= Manual Match Tests =========================


class TestManualMatchDocument:
    """Tests fuer POST /recurring-invoices/{id}/match."""

    @pytest.mark.asyncio
    @patch("app.api.v1.recurring_invoices.get_recurring_invoice_service")
    @patch("app.api.v1.recurring_invoices.limiter")
    async def test_manual_match_document(
        self,
        mock_limiter: Mock,
        mock_get_service: Mock,
        mock_user: Mock,
        mock_db: AsyncMock,
        mock_request: Mock,
    ) -> None:
        """POST /{id}/match sollte Occurrence erstellen."""
        occurrence = _make_mock_occurrence()
        occurrence.matched_by = OccurrenceMatchMethod.MANUAL
        occurrence.match_confidence = 1.0

        mock_service = AsyncMock()
        mock_service.manual_match_document.return_value = occurrence
        mock_get_service.return_value = mock_service

        match_data = ManualMatchSchema(document_id=TEST_DOCUMENT_UUID)

        result = await manual_match_document.__wrapped__(
            request=mock_request,
            data=match_data,
            recurring_id=TEST_RECURRING_UUID,
            current_user=mock_user,
            db=mock_db,
        )

        assert result.id == TEST_OCCURRENCE_UUID
        assert result.document_id == TEST_DOCUMENT_UUID
        assert result.matched_by == OccurrenceMatchMethod.MANUAL
        mock_service.manual_match_document.assert_called_once_with(
            mock_db, TEST_RECURRING_UUID, TEST_DOCUMENT_UUID,
        )

    @pytest.mark.asyncio
    @patch("app.api.v1.recurring_invoices.get_recurring_invoice_service")
    @patch("app.api.v1.recurring_invoices.limiter")
    async def test_manual_match_not_found(
        self,
        mock_limiter: Mock,
        mock_get_service: Mock,
        mock_user: Mock,
        mock_db: AsyncMock,
        mock_request: Mock,
    ) -> None:
        """POST /{id}/match sollte 404 bei unbekannter Recurring-ID zurueckgeben."""
        mock_service = AsyncMock()
        mock_service.manual_match_document.side_effect = ValueError(
            "Wiederkehrende Rechnung nicht gefunden"
        )
        mock_get_service.return_value = mock_service

        match_data = ManualMatchSchema(document_id=TEST_DOCUMENT_UUID)

        with pytest.raises(HTTPException) as exc_info:
            await manual_match_document.__wrapped__(
                request=mock_request,
                data=match_data,
                recurring_id=TEST_RECURRING_UUID,
                current_user=mock_user,
                db=mock_db,
            )

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    @patch("app.api.v1.recurring_invoices.get_recurring_invoice_service")
    @patch("app.api.v1.recurring_invoices.limiter")
    async def test_manual_match_service_error(
        self,
        mock_limiter: Mock,
        mock_get_service: Mock,
        mock_user: Mock,
        mock_db: AsyncMock,
        mock_request: Mock,
    ) -> None:
        """POST /{id}/match sollte 500 bei unerwartetem Fehler zurueckgeben."""
        mock_service = AsyncMock()
        mock_service.manual_match_document.side_effect = RuntimeError("DB-Fehler")
        mock_get_service.return_value = mock_service

        match_data = ManualMatchSchema(document_id=TEST_DOCUMENT_UUID)

        with pytest.raises(HTTPException) as exc_info:
            await manual_match_document.__wrapped__(
                request=mock_request,
                data=match_data,
                recurring_id=TEST_RECURRING_UUID,
                current_user=mock_user,
                db=mock_db,
            )

        assert exc_info.value.status_code == 500


# ========================= Schema Validation Tests =========================


class TestSchemaValidation:
    """Tests fuer Pydantic Schema-Validierung."""

    def test_create_schema_valid(self) -> None:
        """Gueltiges Create-Schema sollte kein Fehler werfen."""
        schema = RecurringInvoiceCreateSchema(
            vendor_name="Test GmbH",
            expected_amount=Decimal("100.00"),
            interval_type=RecurringIntervalType.QUARTERLY,
            interval_months=3,
        )
        assert schema.vendor_name == "Test GmbH"
        assert schema.interval_type == RecurringIntervalType.QUARTERLY
        assert schema.interval_months == 3

    def test_create_schema_valid_regex_pattern(self) -> None:
        """Gueltiger Regex in reference_pattern sollte akzeptiert werden."""
        schema = RecurringInvoiceCreateSchema(
            vendor_name="Test GmbH",
            expected_amount=Decimal("50.00"),
            reference_pattern=r"RE-\d{4}-\d+",
        )
        assert schema.reference_pattern == r"RE-\d{4}-\d+"

    def test_create_schema_invalid_regex_pattern(self) -> None:
        """Ungueltiger Regex in reference_pattern sollte Fehler werfen."""
        with pytest.raises(Exception):
            RecurringInvoiceCreateSchema(
                vendor_name="Test GmbH",
                expected_amount=Decimal("50.00"),
                reference_pattern="[unbalanced(",
            )

    def test_update_schema_valid_regex(self) -> None:
        """Gueltiger Regex im Update-Schema sollte akzeptiert werden."""
        schema = RecurringInvoiceUpdateSchema(
            reference_pattern=r"INV-\d+",
        )
        assert schema.reference_pattern == r"INV-\d+"

    def test_update_schema_invalid_regex(self) -> None:
        """Ungueltiger Regex im Update-Schema sollte Fehler werfen."""
        with pytest.raises(Exception):
            RecurringInvoiceUpdateSchema(
                reference_pattern="***invalid",
            )

    def test_create_schema_defaults(self) -> None:
        """Sollte korrekte Defaults setzen."""
        schema = RecurringInvoiceCreateSchema(
            vendor_name="Test",
            expected_amount=Decimal("10.00"),
        )
        assert schema.interval_type == RecurringIntervalType.MONTHLY
        assert schema.interval_months == 1
        assert schema.currency == "EUR"
        assert schema.tolerance_percent == 5.0
        assert schema.auto_renewal is True

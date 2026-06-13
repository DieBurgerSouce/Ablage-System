# -*- coding: utf-8 -*-
"""
Unit Tests fuer PO-Matching API Endpoints.

Testet alle 9 REST-Endpoints fuer 3-Way Purchase Order Matching:
- Matches auflisten (GET /)
- Ungematchte Dokumente (GET /unmatched)
- Statistiken (GET /statistics)
- Match-Detail (GET /{match_id})
- Match erstellen (POST /)
- Auto-Matching (POST /auto-detect)
- Dokument hinzufuegen (POST /{match_id}/add-document)
- Match bewerten (POST /{match_id}/evaluate)
- Match freigeben (POST /{match_id}/approve)

Feinpoliert und durchdacht - Enterprise Test Coverage.
"""

import pytest
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from uuid import UUID

from fastapi import HTTPException
from starlette.datastructures import Headers
from starlette.requests import Request

from app.db.models_po_matching import (
    MatchStatus,
    DiscrepancyCategory,
    DiscrepancySeverity,
)
from app.api.v1.po_matching import (
    list_matches,
    get_unmatched_documents,
    get_matching_statistics,
    get_match_detail,
    create_match,
    auto_detect_matches,
    add_document_to_match,
    evaluate_match,
    approve_match,
    MatchCreateSchema,
    AddDocumentSchema,
    ApproveMatchSchema,
)

# Test-Konstanten
TEST_USER_UUID = UUID("00000000-0000-0000-0000-000000000001")
TEST_COMPANY_UUID = UUID("00000000-0000-0000-0000-000000000002")
TEST_MATCH_UUID = UUID("00000000-0000-0000-0000-000000000003")
TEST_DISCREPANCY_UUID = UUID("00000000-0000-0000-0000-000000000004")
TEST_PO_DOC_UUID = UUID("00000000-0000-0000-0000-000000000010")
TEST_DN_DOC_UUID = UUID("00000000-0000-0000-0000-000000000011")
TEST_INV_DOC_UUID = UUID("00000000-0000-0000-0000-000000000012")
TEST_VENDOR_UUID = UUID("00000000-0000-0000-0000-000000000020")
OTHER_COMPANY_UUID = UUID("00000000-0000-0000-0000-000000000099")

NOW_UTC = datetime(2026, 2, 10, 12, 0, 0, tzinfo=timezone.utc)

pytestmark = [pytest.mark.unit, pytest.mark.api]


# ========================= Mock Fixtures =========================


@pytest.fixture
def mock_user() -> Mock:
    """Mock-Benutzer fuer Authentifizierung."""
    user = Mock()
    user.id = TEST_USER_UUID
    user.company_id = TEST_COMPANY_UUID
    return user


@pytest.fixture
def mock_db() -> AsyncMock:
    """Mock-Datenbank-Session."""
    return AsyncMock()


@pytest.fixture(autouse=True)
def _bypass_rate_limiter() -> None:
    """Deaktiviert den slowapi Rate Limiter (kein Redis in Unit Tests)."""
    with patch(
        "app.core.rate_limiting.limiter._check_request_limit",
        new_callable=AsyncMock,
    ):
        yield


@pytest.fixture
def mock_request() -> Request:
    """Echtes Starlette Request Objekt (benoetigt fuer slowapi Rate Limiter)."""
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/po-matching",
        "headers": Headers({}).raw,
        "query_string": b"",
        "root_path": "",
        "client": ("127.0.0.1", 12345),
    }
    request = Request(scope)
    # slowapi erwartet diese State-Attribute nach dem Rate-Limit-Check
    request.state.view_rate_limit = None
    request.state._rate_limiting_complete = True
    return request


@pytest.fixture
def mock_match() -> Mock:
    """Mock PurchaseOrderMatch mit Standardwerten."""
    match = Mock()
    match.id = TEST_MATCH_UUID
    match.company_id = TEST_COMPANY_UUID
    match.purchase_order_id = TEST_PO_DOC_UUID
    match.delivery_note_id = TEST_DN_DOC_UUID
    match.invoice_id = TEST_INV_DOC_UUID
    match.document_chain_id = "CHAIN-2026-00001"
    match.vendor_entity_id = TEST_VENDOR_UUID
    match.vendor_name = "Lieferant GmbH"
    match.order_number = "PO-2026-001"
    match.order_date = NOW_UTC
    match.po_amount = Decimal("1000.00")
    match.dn_amount = Decimal("1000.00")
    match.invoice_amount = Decimal("1000.00")
    match.match_status = MatchStatus.FULL
    match.match_score = 100.0
    match.auto_matched = False
    match.amount_tolerance_percent = 2.0
    match.quantity_tolerance_percent = 1.0
    match.approved_by_id = None
    match.approved_at = None
    match.approval_notes = None
    match.document_count = 3
    match.is_complete = True
    match.created_at = NOW_UTC
    match.updated_at = NOW_UTC
    match.matched_at = NOW_UTC
    match.discrepancies = []
    return match


@pytest.fixture
def mock_discrepancy() -> Mock:
    """Mock MatchDiscrepancy."""
    disc = Mock()
    disc.id = TEST_DISCREPANCY_UUID
    disc.match_id = TEST_MATCH_UUID
    disc.category = DiscrepancyCategory.AMOUNT
    disc.description = "Betragabweichung Bestellung vs. Rechnung"
    disc.field_name = "amount_po_vs_invoice"
    disc.expected_value = "1000.00 EUR"
    disc.actual_value = "1100.00 EUR"
    disc.expected_amount = Decimal("1000.00")
    disc.actual_amount = Decimal("1100.00")
    disc.deviation_percent = 10.0
    disc.severity = DiscrepancySeverity.CRITICAL
    disc.resolved = False
    disc.resolved_at = None
    disc.resolution_notes = None
    disc.created_at = NOW_UTC
    return disc


@pytest.fixture
def mock_service() -> AsyncMock:
    """Mock POMatchingService."""
    return AsyncMock()


# ========================= List Matches Tests =========================


class TestListMatches:
    """Tests fuer GET /po-matching (Matches auflisten)."""

    @pytest.mark.asyncio
    @patch("app.api.v1.po_matching.get_po_matching_service")
    async def test_list_matches_success(
        self,
        mock_get_service: Mock,
        mock_request: Mock,
        mock_user: Mock,
        mock_db: AsyncMock,
        mock_match: Mock,
    ) -> None:
        """Erfolgreiche Auflistung von Matches."""
        service = AsyncMock()
        service.list_matches.return_value = ([mock_match], 1)
        mock_get_service.return_value = service

        result = await list_matches(
            request=mock_request,
            status=None,
            vendor_entity_id=None,
            date_from=None,
            date_to=None,
            order_number=None,
            page=0,
            page_size=25,
            current_user=mock_user,
            db=mock_db,
        )

        assert result.total == 1
        assert result.page == 0
        assert result.page_size == 25
        assert len(result.items) == 1
        assert result.items[0].id == TEST_MATCH_UUID
        assert result.items[0].match_status == MatchStatus.FULL

    @pytest.mark.asyncio
    @patch("app.api.v1.po_matching.get_po_matching_service")
    async def test_list_matches_with_status_filter(
        self,
        mock_get_service: Mock,
        mock_request: Mock,
        mock_user: Mock,
        mock_db: AsyncMock,
        mock_match: Mock,
    ) -> None:
        """Filterung nach Status liefert gefilterte Ergebnisse."""
        mock_match.match_status = MatchStatus.PENDING
        service = AsyncMock()
        service.list_matches.return_value = ([mock_match], 1)
        mock_get_service.return_value = service

        result = await list_matches(
            request=mock_request,
            status=MatchStatus.PENDING,
            vendor_entity_id=None,
            date_from=None,
            date_to=None,
            order_number=None,
            page=0,
            page_size=25,
            current_user=mock_user,
            db=mock_db,
            company_id=TEST_COMPANY_UUID,
        )

        # Pruefen dass Filter an Service uebergeben wurde
        call_args = service.list_matches.call_args
        filter_param = call_args[0][1]  # zweites Positionsargument (MatchFilter)
        assert filter_param.status == MatchStatus.PENDING
        assert filter_param.company_id == TEST_COMPANY_UUID

    @pytest.mark.asyncio
    @patch("app.api.v1.po_matching.get_po_matching_service")
    async def test_list_matches_pagination(
        self,
        mock_get_service: Mock,
        mock_request: Mock,
        mock_user: Mock,
        mock_db: AsyncMock,
    ) -> None:
        """Paginierung wird korrekt an Service weitergereicht."""
        service = AsyncMock()
        service.list_matches.return_value = ([], 50)
        mock_get_service.return_value = service

        result = await list_matches(
            request=mock_request,
            status=None,
            vendor_entity_id=None,
            date_from=None,
            date_to=None,
            order_number=None,
            page=2,
            page_size=10,
            current_user=mock_user,
            db=mock_db,
        )

        assert result.page == 2
        assert result.page_size == 10
        assert result.total == 50
        assert len(result.items) == 0

        # Pruefen dass page und page_size an Service uebergeben wurden
        call_kwargs = service.list_matches.call_args[1]
        assert call_kwargs["page"] == 2
        assert call_kwargs["page_size"] == 10

    @pytest.mark.asyncio
    @patch("app.api.v1.po_matching.get_po_matching_service")
    async def test_list_matches_empty_result(
        self,
        mock_get_service: Mock,
        mock_request: Mock,
        mock_user: Mock,
        mock_db: AsyncMock,
    ) -> None:
        """Leere Ergebnisliste bei keinen Matches."""
        service = AsyncMock()
        service.list_matches.return_value = ([], 0)
        mock_get_service.return_value = service

        result = await list_matches(
            request=mock_request,
            status=None,
            vendor_entity_id=None,
            date_from=None,
            date_to=None,
            order_number=None,
            page=0,
            page_size=25,
            current_user=mock_user,
            db=mock_db,
        )

        assert result.total == 0
        assert len(result.items) == 0


# ========================= Get Match Detail Tests =========================


class TestGetMatchDetail:
    """Tests fuer GET /po-matching/{match_id} (Match-Detail)."""

    @pytest.mark.asyncio
    @patch("app.api.v1.po_matching.get_po_matching_service")
    async def test_get_match_detail_success(
        self,
        mock_get_service: Mock,
        mock_request: Mock,
        mock_user: Mock,
        mock_db: AsyncMock,
        mock_match: Mock,
        mock_discrepancy: Mock,
    ) -> None:
        """Match-Detail mit Abweichungen wird korrekt zurueckgegeben."""
        mock_match.discrepancies = [mock_discrepancy]
        service = AsyncMock()
        service.get_match_detail.return_value = mock_match
        mock_get_service.return_value = service

        result = await get_match_detail(
            request=mock_request,
            match_id=TEST_MATCH_UUID,
            current_user=mock_user,
            db=mock_db,
            company_id=TEST_COMPANY_UUID,
        )

        assert result.id == TEST_MATCH_UUID
        assert len(result.discrepancies) == 1
        assert result.discrepancies[0].category == DiscrepancyCategory.AMOUNT
        assert result.discrepancies[0].severity == DiscrepancySeverity.CRITICAL

    @pytest.mark.asyncio
    @patch("app.api.v1.po_matching.get_po_matching_service")
    async def test_get_match_detail_not_found(
        self,
        mock_get_service: Mock,
        mock_request: Mock,
        mock_user: Mock,
        mock_db: AsyncMock,
    ) -> None:
        """Nicht existierender Match liefert 404."""
        service = AsyncMock()
        service.get_match_detail.return_value = None
        mock_get_service.return_value = service

        with pytest.raises(HTTPException) as exc_info:
            await get_match_detail(
                request=mock_request,
                match_id=TEST_MATCH_UUID,
                current_user=mock_user,
                db=mock_db,
            )

        assert exc_info.value.status_code == 404
        assert "nicht gefunden" in exc_info.value.detail

    @pytest.mark.asyncio
    @patch("app.api.v1.po_matching.get_po_matching_service")
    async def test_get_match_detail_forbidden(
        self,
        mock_get_service: Mock,
        mock_request: Mock,
        mock_user: Mock,
        mock_db: AsyncMock,
        mock_match: Mock,
    ) -> None:
        """Match einer anderen Company liefert 403."""
        mock_match.company_id = OTHER_COMPANY_UUID
        service = AsyncMock()
        service.get_match_detail.return_value = mock_match
        mock_get_service.return_value = service

        with pytest.raises(HTTPException) as exc_info:
            await get_match_detail(
                request=mock_request,
                match_id=TEST_MATCH_UUID,
                current_user=mock_user,
                db=mock_db,
            )

        assert exc_info.value.status_code == 403
        assert "Kein Zugriff" in exc_info.value.detail


# ========================= Create Match Tests =========================


class TestCreateMatch:
    """Tests fuer POST /po-matching (Match erstellen)."""

    @pytest.mark.asyncio
    @patch("app.api.v1.po_matching.get_po_matching_service")
    async def test_create_match_success(
        self,
        mock_get_service: Mock,
        mock_request: Mock,
        mock_user: Mock,
        mock_db: AsyncMock,
        mock_match: Mock,
    ) -> None:
        """Match wird erfolgreich erstellt."""
        service = AsyncMock()
        service.create_match.return_value = mock_match
        mock_get_service.return_value = service

        data = MatchCreateSchema(
            purchase_order_id=TEST_PO_DOC_UUID,
            delivery_note_id=TEST_DN_DOC_UUID,
            invoice_id=TEST_INV_DOC_UUID,
            vendor_name="Lieferant GmbH",
            order_number="PO-2026-001",
            po_amount=Decimal("1000.00"),
            dn_amount=Decimal("1000.00"),
            invoice_amount=Decimal("1000.00"),
        )

        result = await create_match(
            request=mock_request,
            data=data,
            current_user=mock_user,
            db=mock_db,
            company_id=TEST_COMPANY_UUID,
        )

        assert result.id == TEST_MATCH_UUID
        assert result.match_status == MatchStatus.FULL

        # Pruefen dass company_id vom User uebernommen wird
        call_args = service.create_match.call_args
        create_request = call_args[0][1]  # zweites Positionsargument
        assert create_request.company_id == TEST_COMPANY_UUID

    @pytest.mark.asyncio
    @patch("app.api.v1.po_matching.get_po_matching_service")
    async def test_create_match_validation_error(
        self,
        mock_get_service: Mock,
        mock_request: Mock,
        mock_user: Mock,
        mock_db: AsyncMock,
    ) -> None:
        """ValueError vom Service fuehrt zu 400."""
        service = AsyncMock()
        service.create_match.side_effect = ValueError("Ungueltige Daten")
        mock_get_service.return_value = service

        data = MatchCreateSchema(
            purchase_order_id=TEST_PO_DOC_UUID,
        )

        with pytest.raises(HTTPException) as exc_info:
            await create_match(
                request=mock_request,
                data=data,
                current_user=mock_user,
                db=mock_db,
            )

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    @patch("app.api.v1.po_matching.get_po_matching_service")
    async def test_create_match_internal_error(
        self,
        mock_get_service: Mock,
        mock_request: Mock,
        mock_user: Mock,
        mock_db: AsyncMock,
    ) -> None:
        """Unerwarteter Fehler fuehrt zu 500."""
        service = AsyncMock()
        service.create_match.side_effect = RuntimeError("DB-Verbindung fehlgeschlagen")
        mock_get_service.return_value = service

        data = MatchCreateSchema(
            purchase_order_id=TEST_PO_DOC_UUID,
        )

        with pytest.raises(HTTPException) as exc_info:
            await create_match(
                request=mock_request,
                data=data,
                current_user=mock_user,
                db=mock_db,
            )

        assert exc_info.value.status_code == 500


# ========================= Auto-Detect Matches Tests =========================


class TestAutoDetectMatches:
    """Tests fuer POST /po-matching/auto-detect (Auto-Matching)."""

    @pytest.mark.asyncio
    @patch("app.api.v1.po_matching.get_po_matching_service")
    async def test_auto_detect_matches_success(
        self,
        mock_get_service: Mock,
        mock_request: Mock,
        mock_user: Mock,
        mock_db: AsyncMock,
        mock_match: Mock,
    ) -> None:
        """Auto-Matching findet und aktualisiert Matches."""
        mock_match.auto_matched = True
        service = AsyncMock()
        service.auto_match_by_reference.return_value = [mock_match]
        mock_get_service.return_value = service

        result = await auto_detect_matches(
            request=mock_request,
            current_user=mock_user,
            db=mock_db,
            company_id=TEST_COMPANY_UUID,
        )

        assert result.matches_updated == 1
        assert len(result.matches) == 1
        assert result.matches[0].id == TEST_MATCH_UUID

        # Pruefen dass company_id korrekt uebergeben wird
        service.auto_match_by_reference.assert_called_once_with(
            mock_db,
            company_id=TEST_COMPANY_UUID,
        )

    @pytest.mark.asyncio
    @patch("app.api.v1.po_matching.get_po_matching_service")
    async def test_auto_detect_matches_no_results(
        self,
        mock_get_service: Mock,
        mock_request: Mock,
        mock_user: Mock,
        mock_db: AsyncMock,
    ) -> None:
        """Auto-Matching ohne Treffer gibt leere Liste zurueck."""
        service = AsyncMock()
        service.auto_match_by_reference.return_value = []
        mock_get_service.return_value = service

        result = await auto_detect_matches(
            request=mock_request,
            current_user=mock_user,
            db=mock_db,
        )

        assert result.matches_updated == 0
        assert len(result.matches) == 0

    @pytest.mark.asyncio
    @patch("app.api.v1.po_matching.get_po_matching_service")
    async def test_auto_detect_matches_error(
        self,
        mock_get_service: Mock,
        mock_request: Mock,
        mock_user: Mock,
        mock_db: AsyncMock,
    ) -> None:
        """Unerwarteter Fehler beim Auto-Matching fuehrt zu 500."""
        service = AsyncMock()
        service.auto_match_by_reference.side_effect = RuntimeError("DB-Fehler")
        mock_get_service.return_value = service

        with pytest.raises(HTTPException) as exc_info:
            await auto_detect_matches(
                request=mock_request,
                current_user=mock_user,
                db=mock_db,
            )

        assert exc_info.value.status_code == 500
        assert "Auto-Matching" in exc_info.value.detail


# ========================= Get Statistics Tests =========================


class TestGetStatistics:
    """Tests fuer GET /po-matching/statistics (Statistiken)."""

    @pytest.mark.asyncio
    @patch("app.api.v1.po_matching.get_po_matching_service")
    async def test_get_statistics_success(
        self,
        mock_get_service: Mock,
        mock_request: Mock,
        mock_user: Mock,
        mock_db: AsyncMock,
    ) -> None:
        """Statistiken werden korrekt berechnet und zurueckgegeben."""
        # Mock MatchStatistics Dataclass
        mock_stats = Mock()
        mock_stats.total_matches = 50
        mock_stats.pending_matches = 10
        mock_stats.partial_matches = 15
        mock_stats.full_matches = 20
        mock_stats.discrepancy_matches = 3
        mock_stats.approved_matches = 2
        mock_stats.rejected_matches = 0
        mock_stats.auto_matched_count = 12
        mock_stats.avg_match_score = 85.5
        mock_stats.total_discrepancies = 8
        mock_stats.unresolved_discrepancies = 5
        mock_stats.avg_amount_deviation_percent = 3.2
        mock_stats.period_start = date(2026, 1, 1)
        mock_stats.period_end = date(2026, 2, 10)

        service = AsyncMock()
        service.get_matching_statistics.return_value = mock_stats
        mock_get_service.return_value = service

        result = await get_matching_statistics(
            request=mock_request,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 2, 10),
            current_user=mock_user,
            db=mock_db,
        )

        assert result.total_matches == 50
        assert result.pending_matches == 10
        assert result.full_matches == 20
        assert result.avg_match_score == 85.5
        assert result.unresolved_discrepancies == 5
        assert result.period_start == date(2026, 1, 1)
        assert result.period_end == date(2026, 2, 10)

    @pytest.mark.asyncio
    @patch("app.api.v1.po_matching.get_po_matching_service")
    async def test_get_statistics_error(
        self,
        mock_get_service: Mock,
        mock_request: Mock,
        mock_user: Mock,
        mock_db: AsyncMock,
    ) -> None:
        """Fehler bei Statistik-Berechnung fuehrt zu 500."""
        service = AsyncMock()
        service.get_matching_statistics.side_effect = RuntimeError("Aggregation fehlgeschlagen")
        mock_get_service.return_value = service

        with pytest.raises(HTTPException) as exc_info:
            await get_matching_statistics(
                request=mock_request,
                period_start=date(2026, 1, 1),
                period_end=date(2026, 2, 10),
                current_user=mock_user,
                db=mock_db,
            )

        assert exc_info.value.status_code == 500


# ========================= Approve Match Tests =========================


class TestApproveMatch:
    """Tests fuer POST /po-matching/{match_id}/approve (Freigabe)."""

    @pytest.mark.asyncio
    @patch("app.api.v1.po_matching.get_po_matching_service")
    async def test_approve_match_success(
        self,
        mock_get_service: Mock,
        mock_request: Mock,
        mock_user: Mock,
        mock_db: AsyncMock,
        mock_match: Mock,
    ) -> None:
        """Match wird erfolgreich freigegeben."""
        mock_match.match_status = MatchStatus.APPROVED
        mock_match.approved_by_id = TEST_USER_UUID
        mock_match.approved_at = NOW_UTC
        mock_match.approval_notes = "Freigabe nach Pruefung"

        service = AsyncMock()
        service.approve_match.return_value = mock_match
        mock_get_service.return_value = service

        data = ApproveMatchSchema(notes="Freigabe nach Pruefung")

        result = await approve_match(
            request=mock_request,
            data=data,
            match_id=TEST_MATCH_UUID,
            current_user=mock_user,
            db=mock_db,
        )

        assert result.match_status == MatchStatus.APPROVED
        assert result.approved_by_id == TEST_USER_UUID

        service.approve_match.assert_called_once_with(
            mock_db,
            TEST_MATCH_UUID,
            user_id=TEST_USER_UUID,
            notes="Freigabe nach Pruefung",
        )

    @pytest.mark.asyncio
    @patch("app.api.v1.po_matching.get_po_matching_service")
    async def test_approve_match_not_found(
        self,
        mock_get_service: Mock,
        mock_request: Mock,
        mock_user: Mock,
        mock_db: AsyncMock,
    ) -> None:
        """Freigabe eines nicht existierenden Matches fuehrt zu 400."""
        service = AsyncMock()
        service.approve_match.side_effect = ValueError("Match nicht gefunden")
        mock_get_service.return_value = service

        data = ApproveMatchSchema()

        with pytest.raises(HTTPException) as exc_info:
            await approve_match(
                request=mock_request,
                data=data,
                match_id=TEST_MATCH_UUID,
                current_user=mock_user,
                db=mock_db,
            )

        assert exc_info.value.status_code == 400


# ========================= Evaluate Match Tests =========================


class TestEvaluateMatch:
    """Tests fuer POST /po-matching/{match_id}/evaluate (Bewertung)."""

    @pytest.mark.asyncio
    @patch("app.api.v1.po_matching.get_po_matching_service")
    async def test_evaluate_match_success(
        self,
        mock_get_service: Mock,
        mock_request: Mock,
        mock_user: Mock,
        mock_db: AsyncMock,
        mock_match: Mock,
        mock_discrepancy: Mock,
    ) -> None:
        """Match-Bewertung erkennt Abweichungen und gibt Detail zurueck."""
        mock_match.discrepancies = [mock_discrepancy]
        mock_match.match_status = MatchStatus.DISCREPANCY
        mock_match.match_score = 70.0

        service = AsyncMock()
        service.evaluate_match.return_value = mock_match
        mock_get_service.return_value = service

        result = await evaluate_match(
            request=mock_request,
            match_id=TEST_MATCH_UUID,
            current_user=mock_user,
            db=mock_db,
        )

        assert result.match_status == MatchStatus.DISCREPANCY
        assert result.match_score == 70.0
        assert len(result.discrepancies) == 1
        assert result.discrepancies[0].deviation_percent == 10.0

    @pytest.mark.asyncio
    @patch("app.api.v1.po_matching.get_po_matching_service")
    async def test_evaluate_match_not_found(
        self,
        mock_get_service: Mock,
        mock_request: Mock,
        mock_user: Mock,
        mock_db: AsyncMock,
    ) -> None:
        """Bewertung eines nicht existierenden Matches fuehrt zu 400."""
        service = AsyncMock()
        service.evaluate_match.side_effect = ValueError("Match nicht gefunden")
        mock_get_service.return_value = service

        with pytest.raises(HTTPException) as exc_info:
            await evaluate_match(
                request=mock_request,
                match_id=TEST_MATCH_UUID,
                current_user=mock_user,
                db=mock_db,
            )

        assert exc_info.value.status_code == 400


# ========================= Add Document Tests =========================


class TestAddDocument:
    """Tests fuer POST /po-matching/{match_id}/add-document."""

    @pytest.mark.asyncio
    @patch("app.api.v1.po_matching.get_po_matching_service")
    async def test_add_document_success(
        self,
        mock_get_service: Mock,
        mock_request: Mock,
        mock_user: Mock,
        mock_db: AsyncMock,
        mock_match: Mock,
    ) -> None:
        """Dokument wird erfolgreich zu Match hinzugefuegt."""
        service = AsyncMock()
        service.add_document_to_match.return_value = mock_match
        mock_get_service.return_value = service

        data = AddDocumentSchema(
            document_id=TEST_INV_DOC_UUID,
            document_type="invoice",
            amount=Decimal("1000.00"),
        )

        result = await add_document_to_match(
            request=mock_request,
            data=data,
            match_id=TEST_MATCH_UUID,
            current_user=mock_user,
            db=mock_db,
        )

        assert result.id == TEST_MATCH_UUID
        service.add_document_to_match.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.api.v1.po_matching.get_po_matching_service")
    async def test_add_document_already_linked(
        self,
        mock_get_service: Mock,
        mock_request: Mock,
        mock_user: Mock,
        mock_db: AsyncMock,
    ) -> None:
        """Bereits verknuepftes Dokument fuehrt zu 400."""
        service = AsyncMock()
        service.add_document_to_match.side_effect = ValueError(
            "Rechnung ist bereits verknuepft"
        )
        mock_get_service.return_value = service

        data = AddDocumentSchema(
            document_id=TEST_INV_DOC_UUID,
            document_type="invoice",
        )

        with pytest.raises(HTTPException) as exc_info:
            await add_document_to_match(
                request=mock_request,
                data=data,
                match_id=TEST_MATCH_UUID,
                current_user=mock_user,
                db=mock_db,
            )

        assert exc_info.value.status_code == 400


# ========================= Unmatched Documents Tests =========================


class TestGetUnmatchedDocuments:
    """Tests fuer GET /po-matching/unmatched (Ungematchte Dokumente)."""

    @pytest.mark.asyncio
    @patch("app.api.v1.po_matching.get_po_matching_service")
    async def test_get_unmatched_documents_success(
        self,
        mock_get_service: Mock,
        mock_request: Mock,
        mock_user: Mock,
        mock_db: AsyncMock,
    ) -> None:
        """Ungematchte Dokumente werden korrekt zurueckgegeben."""
        mock_doc = Mock()
        mock_doc.id = TEST_PO_DOC_UUID
        mock_doc.filename = "bestellung_001.pdf"
        mock_doc.document_type = "bestellung"
        mock_doc.chain_id = "CHAIN-2026-00001"
        mock_doc.created_at = NOW_UTC

        service = AsyncMock()
        service.get_unmatched_documents.return_value = [mock_doc]
        mock_get_service.return_value = service

        result = await get_unmatched_documents(
            request=mock_request,
            document_type=None,
            current_user=mock_user,
            db=mock_db,
        )

        assert len(result) == 1
        assert result[0].id == TEST_PO_DOC_UUID
        assert result[0].filename == "bestellung_001.pdf"

    @pytest.mark.asyncio
    @patch("app.api.v1.po_matching.get_po_matching_service")
    async def test_get_unmatched_documents_with_type_filter(
        self,
        mock_get_service: Mock,
        mock_request: Mock,
        mock_user: Mock,
        mock_db: AsyncMock,
    ) -> None:
        """Typ-Filter wird korrekt an Service durchgereicht."""
        service = AsyncMock()
        service.get_unmatched_documents.return_value = []
        mock_get_service.return_value = service

        await get_unmatched_documents(
            request=mock_request,
            document_type="invoice",
            current_user=mock_user,
            db=mock_db,
            company_id=TEST_COMPANY_UUID,
        )

        service.get_unmatched_documents.assert_called_once_with(
            mock_db,
            company_id=TEST_COMPANY_UUID,
            document_type="invoice",
        )


# ========================= Schema Validation Tests =========================


class TestSchemaValidation:
    """Tests fuer Pydantic Schema-Validierung."""

    def test_match_create_schema_defaults(self) -> None:
        """MatchCreateSchema hat korrekte Default-Werte."""
        schema = MatchCreateSchema()
        assert schema.amount_tolerance_percent == 2.0
        assert schema.quantity_tolerance_percent == 1.0
        assert schema.purchase_order_id is None
        assert schema.delivery_note_id is None
        assert schema.invoice_id is None

    def test_add_document_schema_required_fields(self) -> None:
        """AddDocumentSchema erfordert document_id und document_type."""
        data = AddDocumentSchema(
            document_id=TEST_PO_DOC_UUID,
            document_type="purchase_order",
        )
        assert data.document_id == TEST_PO_DOC_UUID
        assert data.document_type == "purchase_order"
        assert data.amount is None

    def test_approve_match_schema_optional_notes(self) -> None:
        """ApproveMatchSchema hat optionale Notizen."""
        schema = ApproveMatchSchema()
        assert schema.notes is None

        schema_with_notes = ApproveMatchSchema(notes="Geprueft und freigegeben")
        assert schema_with_notes.notes == "Geprueft und freigegeben"


# ========================= Helper Function Tests =========================


class TestHelperFunctions:
    """Tests fuer _match_to_response und _match_to_detail_response."""

    def test_match_to_response_nullable_amounts(self, mock_match: Mock) -> None:
        """Nullable Betraege werden korrekt in Float konvertiert."""
        from app.api.v1.po_matching import _match_to_response

        # Alle Betraege vorhanden
        result = _match_to_response(mock_match)
        assert result.po_amount == 1000.0
        assert result.dn_amount == 1000.0
        assert result.invoice_amount == 1000.0

    def test_match_to_response_none_amounts(self, mock_match: Mock) -> None:
        """None-Betraege werden als None zurueckgegeben."""
        from app.api.v1.po_matching import _match_to_response

        mock_match.po_amount = None
        mock_match.dn_amount = None
        mock_match.invoice_amount = None

        result = _match_to_response(mock_match)
        assert result.po_amount is None
        assert result.dn_amount is None
        assert result.invoice_amount is None

    def test_match_to_detail_response_with_discrepancies(
        self, mock_match: Mock, mock_discrepancy: Mock
    ) -> None:
        """Detail-Response enthaelt Abweichungen."""
        from app.api.v1.po_matching import _match_to_detail_response

        mock_match.discrepancies = [mock_discrepancy]

        result = _match_to_detail_response(mock_match)
        assert len(result.discrepancies) == 1
        assert result.discrepancies[0].id == TEST_DISCREPANCY_UUID
        assert result.discrepancies[0].deviation_percent == 10.0

    def test_match_to_detail_response_empty_discrepancies(
        self, mock_match: Mock
    ) -> None:
        """Detail-Response ohne Abweichungen hat leere Liste."""
        from app.api.v1.po_matching import _match_to_detail_response

        mock_match.discrepancies = []

        result = _match_to_detail_response(mock_match)
        assert result.discrepancies == []

    def test_match_to_detail_response_none_discrepancies(
        self, mock_match: Mock
    ) -> None:
        """Detail-Response mit None-Discrepancies hat leere Liste."""
        from app.api.v1.po_matching import _match_to_detail_response

        mock_match.discrepancies = None

        result = _match_to_detail_response(mock_match)
        assert result.discrepancies == []

    def test_match_to_response_default_score(self, mock_match: Mock) -> None:
        """Fehlender match_score wird als 0.0 zurueckgegeben."""
        from app.api.v1.po_matching import _match_to_response

        mock_match.match_score = None

        result = _match_to_response(mock_match)
        assert result.match_score == 0.0

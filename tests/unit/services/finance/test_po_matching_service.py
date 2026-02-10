# -*- coding: utf-8 -*-
"""
Unit Tests fuer POMatchingService.

Testet die Business-Logik fuer 3-Way Purchase Order Matching:
- Match-Erstellung mit Statusbestimmung
- Filterung und Paginierung
- Abweichungserkennung und Bewertung
- Freigabe-Workflow
- Auto-Matching nach Referenznummer
- Statistik-Aggregation
- Dokument-Hinzufuegen mit Statusaktualisierung

Feinpoliert und durchdacht - Enterprise Test Coverage.
"""

import pytest
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional
from unittest.mock import AsyncMock, Mock, patch, MagicMock, PropertyMock

from app.services.finance.po_matching_service import (
    POMatchingService,
    MatchCreateRequest,
    MatchFilter,
    AddDocumentRequest,
    MatchStatistics,
)
from app.db.models_po_matching import (
    PurchaseOrderMatch,
    MatchDiscrepancy,
    MatchStatus,
    DiscrepancyCategory,
    DiscrepancySeverity,
)

# Test-Konstanten
TEST_USER_UUID = uuid.UUID("00000000-0000-0000-0000-000000000001")
TEST_COMPANY_UUID = uuid.UUID("00000000-0000-0000-0000-000000000002")
TEST_MATCH_UUID = uuid.UUID("00000000-0000-0000-0000-000000000003")
TEST_DISCREPANCY_UUID = uuid.UUID("00000000-0000-0000-0000-000000000004")
TEST_PO_DOC_UUID = uuid.UUID("00000000-0000-0000-0000-000000000010")
TEST_DN_DOC_UUID = uuid.UUID("00000000-0000-0000-0000-000000000011")
TEST_INV_DOC_UUID = uuid.UUID("00000000-0000-0000-0000-000000000012")
TEST_VENDOR_UUID = uuid.UUID("00000000-0000-0000-0000-000000000020")

NOW_UTC = datetime(2026, 2, 10, 12, 0, 0, tzinfo=timezone.utc)

pytestmark = [pytest.mark.unit, pytest.mark.services]


# ========================= Fixtures =========================


@pytest.fixture
def service() -> POMatchingService:
    """POMatchingService Instanz."""
    return POMatchingService()


@pytest.fixture
def mock_db() -> AsyncMock:
    """Mock AsyncSession mit Standard-Konfiguration."""
    db = AsyncMock()
    return db


@pytest.fixture
def mock_match() -> Mock:
    """Mock PurchaseOrderMatch mit allen Feldern."""
    match = Mock(spec=PurchaseOrderMatch)
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
    match.created_at = NOW_UTC
    match.updated_at = NOW_UTC
    match.matched_at = None
    match.discrepancies = []
    # Properties
    match.document_count = 3
    match.is_complete = True
    return match


# ========================= Create Match Tests =========================


class TestCreateMatch:
    """Tests fuer POMatchingService.create_match."""

    @pytest.mark.asyncio
    async def test_create_match_pending_status(
        self, service: POMatchingService, mock_db: AsyncMock
    ) -> None:
        """Match mit einem Dokument erhaelt Status PENDING."""
        request = MatchCreateRequest(
            company_id=TEST_COMPANY_UUID,
            purchase_order_id=TEST_PO_DOC_UUID,
            order_number="PO-2026-001",
        )

        # Mock db.add, db.commit, db.refresh
        created_match = Mock(spec=PurchaseOrderMatch)
        created_match.id = TEST_MATCH_UUID
        created_match.match_status = MatchStatus.PENDING

        mock_db.add = Mock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        result = await service.create_match(mock_db, request)

        # Service ruft db.add mit PurchaseOrderMatch auf
        mock_db.add.assert_called_once()
        added_match = mock_db.add.call_args[0][0]
        assert isinstance(added_match, PurchaseOrderMatch)
        assert added_match.match_status == MatchStatus.PENDING
        assert added_match.company_id == TEST_COMPANY_UUID
        assert added_match.purchase_order_id == TEST_PO_DOC_UUID

        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_match_partial_status(
        self, service: POMatchingService, mock_db: AsyncMock
    ) -> None:
        """Match mit zwei Dokumenten erhaelt Status PARTIAL."""
        request = MatchCreateRequest(
            company_id=TEST_COMPANY_UUID,
            purchase_order_id=TEST_PO_DOC_UUID,
            delivery_note_id=TEST_DN_DOC_UUID,
        )

        mock_db.add = Mock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        await service.create_match(mock_db, request)

        added_match = mock_db.add.call_args[0][0]
        assert added_match.match_status == MatchStatus.PARTIAL

    @pytest.mark.asyncio
    async def test_create_match_full_status(
        self, service: POMatchingService, mock_db: AsyncMock
    ) -> None:
        """Match mit drei Dokumenten erhaelt Status FULL."""
        request = MatchCreateRequest(
            company_id=TEST_COMPANY_UUID,
            purchase_order_id=TEST_PO_DOC_UUID,
            delivery_note_id=TEST_DN_DOC_UUID,
            invoice_id=TEST_INV_DOC_UUID,
            po_amount=Decimal("1000.00"),
            dn_amount=Decimal("1000.00"),
            invoice_amount=Decimal("1000.00"),
        )

        mock_db.add = Mock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        await service.create_match(mock_db, request)

        added_match = mock_db.add.call_args[0][0]
        assert added_match.match_status == MatchStatus.FULL
        assert added_match.po_amount == Decimal("1000.00")
        assert added_match.dn_amount == Decimal("1000.00")
        assert added_match.invoice_amount == Decimal("1000.00")

    @pytest.mark.asyncio
    async def test_create_match_with_all_fields(
        self, service: POMatchingService, mock_db: AsyncMock
    ) -> None:
        """Match mit allen optionalen Feldern wird korrekt erstellt."""
        request = MatchCreateRequest(
            company_id=TEST_COMPANY_UUID,
            purchase_order_id=TEST_PO_DOC_UUID,
            delivery_note_id=TEST_DN_DOC_UUID,
            invoice_id=TEST_INV_DOC_UUID,
            document_chain_id="CHAIN-2026-00001",
            vendor_entity_id=TEST_VENDOR_UUID,
            vendor_name="Lieferant GmbH",
            order_number="PO-2026-001",
            order_date=NOW_UTC,
            po_amount=Decimal("5000.00"),
            dn_amount=Decimal("5000.00"),
            invoice_amount=Decimal("5000.00"),
            amount_tolerance_percent=3.0,
            quantity_tolerance_percent=2.0,
        )

        mock_db.add = Mock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        await service.create_match(mock_db, request)

        added_match = mock_db.add.call_args[0][0]
        assert added_match.vendor_name == "Lieferant GmbH"
        assert added_match.order_number == "PO-2026-001"
        assert added_match.amount_tolerance_percent == 3.0
        assert added_match.quantity_tolerance_percent == 2.0
        assert added_match.document_chain_id == "CHAIN-2026-00001"


# ========================= Get Match Detail Tests =========================


class TestGetMatchDetail:
    """Tests fuer POMatchingService.get_match_detail."""

    @pytest.mark.asyncio
    async def test_get_match_detail_found(
        self, service: POMatchingService, mock_db: AsyncMock, mock_match: Mock
    ) -> None:
        """Match wird mit Abweichungen zurueckgegeben."""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_match
        mock_db.execute.return_value = mock_result

        result = await service.get_match_detail(mock_db, TEST_MATCH_UUID)

        assert result is not None
        assert result.id == TEST_MATCH_UUID
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_match_detail_not_found(
        self, service: POMatchingService, mock_db: AsyncMock
    ) -> None:
        """Nicht existierender Match gibt None zurueck."""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await service.get_match_detail(mock_db, TEST_MATCH_UUID)

        assert result is None


# ========================= List Matches Tests =========================


class TestListMatches:
    """Tests fuer POMatchingService.list_matches."""

    @pytest.mark.asyncio
    async def test_list_matches_basic(
        self, service: POMatchingService, mock_db: AsyncMock, mock_match: Mock
    ) -> None:
        """Einfache Auflistung ohne Filter."""
        filter_params = MatchFilter(company_id=TEST_COMPANY_UUID)

        # Mock fuer count-Query
        mock_count_result = Mock()
        mock_count_result.scalar.return_value = 1

        # Mock fuer paginated Query
        mock_scalars = Mock()
        mock_scalars.all.return_value = [mock_match]
        mock_list_result = Mock()
        mock_list_result.scalars.return_value = mock_scalars

        # Erster Aufruf: Count, Zweiter Aufruf: Daten
        mock_db.execute = AsyncMock(
            side_effect=[mock_count_result, mock_list_result]
        )

        matches, total = await service.list_matches(mock_db, filter_params)

        assert total == 1
        assert len(matches) == 1
        assert matches[0].id == TEST_MATCH_UUID

    @pytest.mark.asyncio
    async def test_list_matches_with_status_filter(
        self, service: POMatchingService, mock_db: AsyncMock
    ) -> None:
        """Filterung nach Match-Status."""
        filter_params = MatchFilter(
            company_id=TEST_COMPANY_UUID,
            status=MatchStatus.PENDING,
        )

        mock_count_result = Mock()
        mock_count_result.scalar.return_value = 0

        mock_scalars = Mock()
        mock_scalars.all.return_value = []
        mock_list_result = Mock()
        mock_list_result.scalars.return_value = mock_scalars

        mock_db.execute = AsyncMock(
            side_effect=[mock_count_result, mock_list_result]
        )

        matches, total = await service.list_matches(mock_db, filter_params)

        assert total == 0
        assert len(matches) == 0
        # execute wird zweimal aufgerufen: count + paginated
        assert mock_db.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_list_matches_pagination(
        self, service: POMatchingService, mock_db: AsyncMock
    ) -> None:
        """Paginierung wird korrekt angewendet."""
        filter_params = MatchFilter(company_id=TEST_COMPANY_UUID)

        mock_count_result = Mock()
        mock_count_result.scalar.return_value = 50

        mock_scalars = Mock()
        mock_scalars.all.return_value = []
        mock_list_result = Mock()
        mock_list_result.scalars.return_value = mock_scalars

        mock_db.execute = AsyncMock(
            side_effect=[mock_count_result, mock_list_result]
        )

        matches, total = await service.list_matches(
            mock_db, filter_params, page=2, page_size=10
        )

        assert total == 50
        assert len(matches) == 0


# ========================= Add Document Tests =========================


class TestAddDocument:
    """Tests fuer POMatchingService.add_document_to_match."""

    @pytest.mark.asyncio
    async def test_add_purchase_order(
        self, service: POMatchingService, mock_db: AsyncMock
    ) -> None:
        """Bestellung wird korrekt hinzugefuegt."""
        mock_match = Mock(spec=PurchaseOrderMatch)
        mock_match.purchase_order_id = None
        mock_match.delivery_note_id = TEST_DN_DOC_UUID
        mock_match.invoice_id = None
        mock_match.is_complete = False
        mock_match.document_count = 2

        mock_db.get = AsyncMock(return_value=mock_match)
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        request = AddDocumentRequest(
            document_id=TEST_PO_DOC_UUID,
            document_type="purchase_order",
            amount=Decimal("500.00"),
        )

        result = await service.add_document_to_match(
            mock_db, TEST_MATCH_UUID, request
        )

        assert mock_match.purchase_order_id == TEST_PO_DOC_UUID
        assert mock_match.po_amount == Decimal("500.00")
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_delivery_note(
        self, service: POMatchingService, mock_db: AsyncMock
    ) -> None:
        """Lieferschein wird korrekt hinzugefuegt."""
        mock_match = Mock(spec=PurchaseOrderMatch)
        mock_match.purchase_order_id = TEST_PO_DOC_UUID
        mock_match.delivery_note_id = None
        mock_match.invoice_id = None
        mock_match.is_complete = False
        mock_match.document_count = 2

        mock_db.get = AsyncMock(return_value=mock_match)
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        request = AddDocumentRequest(
            document_id=TEST_DN_DOC_UUID,
            document_type="delivery_note",
            amount=Decimal("500.00"),
        )

        result = await service.add_document_to_match(
            mock_db, TEST_MATCH_UUID, request
        )

        assert mock_match.delivery_note_id == TEST_DN_DOC_UUID
        assert mock_match.dn_amount == Decimal("500.00")

    @pytest.mark.asyncio
    async def test_add_invoice(
        self, service: POMatchingService, mock_db: AsyncMock
    ) -> None:
        """Rechnung wird korrekt hinzugefuegt und vervollstaendigt Match."""
        mock_match = Mock(spec=PurchaseOrderMatch)
        mock_match.purchase_order_id = TEST_PO_DOC_UUID
        mock_match.delivery_note_id = TEST_DN_DOC_UUID
        mock_match.invoice_id = None
        mock_match.is_complete = True  # wird True nach Hinzufuegen
        mock_match.document_count = 3

        mock_db.get = AsyncMock(return_value=mock_match)
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        request = AddDocumentRequest(
            document_id=TEST_INV_DOC_UUID,
            document_type="invoice",
            amount=Decimal("1000.00"),
        )

        result = await service.add_document_to_match(
            mock_db, TEST_MATCH_UUID, request
        )

        assert mock_match.invoice_id == TEST_INV_DOC_UUID
        assert mock_match.invoice_amount == Decimal("1000.00")
        assert mock_match.match_status == MatchStatus.FULL

    @pytest.mark.asyncio
    async def test_add_document_match_not_found(
        self, service: POMatchingService, mock_db: AsyncMock
    ) -> None:
        """Fehler bei nicht existierendem Match."""
        mock_db.get = AsyncMock(return_value=None)

        request = AddDocumentRequest(
            document_id=TEST_PO_DOC_UUID,
            document_type="purchase_order",
        )

        with pytest.raises(ValueError, match="Match nicht gefunden"):
            await service.add_document_to_match(
                mock_db, TEST_MATCH_UUID, request
            )

    @pytest.mark.asyncio
    async def test_add_document_already_linked(
        self, service: POMatchingService, mock_db: AsyncMock
    ) -> None:
        """Fehler bei bereits verknuepftem Dokument-Slot."""
        mock_match = Mock(spec=PurchaseOrderMatch)
        mock_match.purchase_order_id = TEST_PO_DOC_UUID  # bereits gesetzt

        mock_db.get = AsyncMock(return_value=mock_match)

        request = AddDocumentRequest(
            document_id=uuid.uuid4(),
            document_type="purchase_order",
        )

        with pytest.raises(ValueError, match="bereits verknuepft"):
            await service.add_document_to_match(
                mock_db, TEST_MATCH_UUID, request
            )

    @pytest.mark.asyncio
    async def test_add_document_invalid_type(
        self, service: POMatchingService, mock_db: AsyncMock
    ) -> None:
        """Fehler bei ungueltigem Dokumenttyp."""
        mock_match = Mock(spec=PurchaseOrderMatch)
        mock_match.purchase_order_id = None
        mock_match.delivery_note_id = None
        mock_match.invoice_id = None

        mock_db.get = AsyncMock(return_value=mock_match)

        request = AddDocumentRequest(
            document_id=TEST_PO_DOC_UUID,
            document_type="ungueltig",
        )

        with pytest.raises(ValueError, match="Ungueltiger Dokumenttyp"):
            await service.add_document_to_match(
                mock_db, TEST_MATCH_UUID, request
            )


# ========================= Evaluate Match Tests =========================


class TestEvaluateMatch:
    """Tests fuer POMatchingService.evaluate_match."""

    @pytest.mark.asyncio
    async def test_evaluate_match_no_discrepancies(
        self, service: POMatchingService, mock_db: AsyncMock, mock_match: Mock
    ) -> None:
        """Bewertung ohne Abweichungen ergibt Score 100."""
        # Alle Betraege gleich -> keine Abweichung
        mock_match.po_amount = Decimal("1000.00")
        mock_match.dn_amount = Decimal("1000.00")
        mock_match.invoice_amount = Decimal("1000.00")
        mock_match.amount_tolerance_percent = 2.0
        mock_match.discrepancies = []
        mock_match.is_complete = True

        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_match
        mock_db.execute.return_value = mock_result
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        result = await service.evaluate_match(mock_db, TEST_MATCH_UUID)

        assert result.match_score == 100.0
        assert result.match_status == MatchStatus.FULL

    @pytest.mark.asyncio
    async def test_evaluate_match_with_warning_discrepancy(
        self, service: POMatchingService, mock_db: AsyncMock, mock_match: Mock
    ) -> None:
        """Bewertung mit leichter Abweichung (Warning) behaelt FULL Status."""
        # 3% Abweichung bei 2% Toleranz -> WARNING
        mock_match.po_amount = Decimal("1000.00")
        mock_match.dn_amount = Decimal("1000.00")
        mock_match.invoice_amount = Decimal("1030.00")
        mock_match.amount_tolerance_percent = 2.0
        mock_match.discrepancies = []
        mock_match.is_complete = True

        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_match
        mock_db.execute.return_value = mock_result
        mock_db.delete = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        result = await service.evaluate_match(mock_db, TEST_MATCH_UUID)

        # 3% ist WARNING-Niveau (2-5%)
        assert result.match_score < 100.0
        # WARNING-Abweichung bei komplettem Match -> bleibt FULL
        assert result.match_status == MatchStatus.FULL

    @pytest.mark.asyncio
    async def test_evaluate_match_with_critical_discrepancy(
        self, service: POMatchingService, mock_db: AsyncMock, mock_match: Mock
    ) -> None:
        """Bewertung mit kritischer Abweichung setzt Status auf DISCREPANCY."""
        # >10% Abweichung -> CRITICAL
        mock_match.po_amount = Decimal("1000.00")
        mock_match.dn_amount = Decimal("1000.00")
        mock_match.invoice_amount = Decimal("1200.00")
        mock_match.amount_tolerance_percent = 2.0
        mock_match.discrepancies = []
        mock_match.is_complete = True

        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_match
        mock_db.execute.return_value = mock_result
        mock_db.delete = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        result = await service.evaluate_match(mock_db, TEST_MATCH_UUID)

        assert result.match_status == MatchStatus.DISCREPANCY
        assert result.match_score < 100.0

    @pytest.mark.asyncio
    async def test_evaluate_match_not_found(
        self, service: POMatchingService, mock_db: AsyncMock
    ) -> None:
        """Bewertung nicht existierender Match wirft ValueError."""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with pytest.raises(ValueError, match="Match nicht gefunden"):
            await service.evaluate_match(mock_db, TEST_MATCH_UUID)

    @pytest.mark.asyncio
    async def test_evaluate_match_clears_old_discrepancies(
        self, service: POMatchingService, mock_db: AsyncMock, mock_match: Mock
    ) -> None:
        """Neubewertung loescht bestehende Abweichungen."""
        old_disc = Mock(spec=MatchDiscrepancy)
        mock_match.discrepancies = [old_disc]
        mock_match.po_amount = Decimal("1000.00")
        mock_match.dn_amount = Decimal("1000.00")
        mock_match.invoice_amount = Decimal("1000.00")
        mock_match.amount_tolerance_percent = 2.0
        mock_match.is_complete = True

        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_match
        mock_db.execute.return_value = mock_result
        mock_db.delete = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        await service.evaluate_match(mock_db, TEST_MATCH_UUID)

        # Alte Abweichung muss geloescht werden
        mock_db.delete.assert_called_once_with(old_disc)


# ========================= Approve Match Tests =========================


class TestApproveMatch:
    """Tests fuer POMatchingService.approve_match."""

    @pytest.mark.asyncio
    async def test_approve_match_success(
        self, service: POMatchingService, mock_db: AsyncMock
    ) -> None:
        """Match wird erfolgreich freigegeben."""
        mock_match = Mock(spec=PurchaseOrderMatch)
        mock_match.id = TEST_MATCH_UUID

        mock_db.get = AsyncMock(return_value=mock_match)
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        result = await service.approve_match(
            mock_db,
            TEST_MATCH_UUID,
            user_id=TEST_USER_UUID,
            notes="Freigabe nach manueller Pruefung",
        )

        assert mock_match.match_status == MatchStatus.APPROVED
        assert mock_match.approved_by_id == TEST_USER_UUID
        assert mock_match.approval_notes == "Freigabe nach manueller Pruefung"
        assert mock_match.approved_at is not None
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_approve_match_not_found(
        self, service: POMatchingService, mock_db: AsyncMock
    ) -> None:
        """Freigabe nicht existierender Match wirft ValueError."""
        mock_db.get = AsyncMock(return_value=None)

        with pytest.raises(ValueError, match="Match nicht gefunden"):
            await service.approve_match(
                mock_db, TEST_MATCH_UUID, user_id=TEST_USER_UUID
            )

    @pytest.mark.asyncio
    async def test_approve_match_without_notes(
        self, service: POMatchingService, mock_db: AsyncMock
    ) -> None:
        """Freigabe ohne Notizen setzt approval_notes auf None."""
        mock_match = Mock(spec=PurchaseOrderMatch)

        mock_db.get = AsyncMock(return_value=mock_match)
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        await service.approve_match(
            mock_db, TEST_MATCH_UUID, user_id=TEST_USER_UUID
        )

        assert mock_match.approval_notes is None


# ========================= Auto Match Tests =========================


class TestAutoMatch:
    """Tests fuer POMatchingService.auto_match_by_reference."""

    @pytest.mark.asyncio
    async def test_auto_match_no_pending(
        self, service: POMatchingService, mock_db: AsyncMock
    ) -> None:
        """Keine ausstehenden Matches -> leere Liste."""
        mock_scalars = Mock()
        mock_scalars.all.return_value = []
        mock_result = Mock()
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute.return_value = mock_result

        result = await service.auto_match_by_reference(
            mock_db, company_id=TEST_COMPANY_UUID
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_auto_match_skips_null_order_number(
        self, service: POMatchingService, mock_db: AsyncMock
    ) -> None:
        """Match ohne order_number wird uebersprungen."""
        mock_match = Mock(spec=PurchaseOrderMatch)
        mock_match.order_number = None
        mock_match.purchase_order_id = None
        mock_match.delivery_note_id = None
        mock_match.invoice_id = None

        mock_scalars = Mock()
        mock_scalars.all.return_value = [mock_match]
        mock_result = Mock()
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute.return_value = mock_result

        result = await service.auto_match_by_reference(
            mock_db, company_id=TEST_COMPANY_UUID
        )

        assert result == []


# ========================= Amount Discrepancy Detection Tests =========================


class TestAmountDiscrepancyDetection:
    """Tests fuer _collect_amounts und _check_amount_discrepancies."""

    def test_collect_amounts(self, service: POMatchingService, mock_match: Mock) -> None:
        """Betraege werden korrekt gesammelt."""
        mock_match.po_amount = Decimal("1000.00")
        mock_match.dn_amount = Decimal("950.00")
        mock_match.invoice_amount = Decimal("1050.00")

        amounts = service._collect_amounts(mock_match)

        assert amounts["po"] == Decimal("1000.00")
        assert amounts["dn"] == Decimal("950.00")
        assert amounts["invoice"] == Decimal("1050.00")

    def test_collect_amounts_with_none(
        self, service: POMatchingService, mock_match: Mock
    ) -> None:
        """None-Betraege werden korrekt behandelt."""
        mock_match.po_amount = Decimal("1000.00")
        mock_match.dn_amount = None
        mock_match.invoice_amount = None

        amounts = service._collect_amounts(mock_match)

        assert amounts["po"] == Decimal("1000.00")
        assert amounts["dn"] is None
        assert amounts["invoice"] is None

    def test_no_discrepancy_within_tolerance(
        self, service: POMatchingService, mock_match: Mock
    ) -> None:
        """Keine Abweichung innerhalb der Toleranz."""
        mock_match.po_amount = Decimal("1000.00")
        mock_match.dn_amount = Decimal("1010.00")  # 1% -> innerhalb 2%
        mock_match.invoice_amount = Decimal("1005.00")
        mock_match.amount_tolerance_percent = 2.0

        amounts = service._collect_amounts(mock_match)
        discrepancies = service._check_amount_discrepancies(mock_match, amounts)

        assert len(discrepancies) == 0

    def test_warning_discrepancy_3_percent(
        self, service: POMatchingService, mock_match: Mock
    ) -> None:
        """3% Abweichung bei 2% Toleranz ergibt WARNING."""
        mock_match.po_amount = Decimal("1000.00")
        mock_match.dn_amount = Decimal("1000.00")
        mock_match.invoice_amount = Decimal("1030.00")
        mock_match.amount_tolerance_percent = 2.0

        amounts = service._collect_amounts(mock_match)
        discrepancies = service._check_amount_discrepancies(mock_match, amounts)

        # po vs invoice: 3%, dn vs invoice: 3% -> 2 Abweichungen
        assert len(discrepancies) >= 1
        for d in discrepancies:
            assert d.severity == DiscrepancySeverity.WARNING
            assert d.category == DiscrepancyCategory.AMOUNT

    def test_error_discrepancy_7_percent(
        self, service: POMatchingService, mock_match: Mock
    ) -> None:
        """7% Abweichung ergibt ERROR."""
        mock_match.po_amount = Decimal("1000.00")
        mock_match.dn_amount = Decimal("1000.00")
        mock_match.invoice_amount = Decimal("1070.00")
        mock_match.amount_tolerance_percent = 2.0

        amounts = service._collect_amounts(mock_match)
        discrepancies = service._check_amount_discrepancies(mock_match, amounts)

        assert len(discrepancies) >= 1
        for d in discrepancies:
            assert d.severity == DiscrepancySeverity.ERROR

    def test_critical_discrepancy_15_percent(
        self, service: POMatchingService, mock_match: Mock
    ) -> None:
        """15% Abweichung ergibt CRITICAL."""
        mock_match.po_amount = Decimal("1000.00")
        mock_match.dn_amount = Decimal("1000.00")
        mock_match.invoice_amount = Decimal("1150.00")
        mock_match.amount_tolerance_percent = 2.0

        amounts = service._collect_amounts(mock_match)
        discrepancies = service._check_amount_discrepancies(mock_match, amounts)

        assert len(discrepancies) >= 1
        for d in discrepancies:
            assert d.severity == DiscrepancySeverity.CRITICAL

    def test_skip_comparison_with_none_amounts(
        self, service: POMatchingService, mock_match: Mock
    ) -> None:
        """Vergleiche mit None-Betraegen werden uebersprungen."""
        mock_match.po_amount = Decimal("1000.00")
        mock_match.dn_amount = None
        mock_match.invoice_amount = None
        mock_match.amount_tolerance_percent = 2.0

        amounts = service._collect_amounts(mock_match)
        discrepancies = service._check_amount_discrepancies(mock_match, amounts)

        assert len(discrepancies) == 0

    def test_skip_comparison_with_zero_source(
        self, service: POMatchingService, mock_match: Mock
    ) -> None:
        """Vergleich mit Quellbetrag 0 wird uebersprungen (Division by Zero)."""
        mock_match.po_amount = Decimal("0")
        mock_match.dn_amount = Decimal("1000.00")
        mock_match.invoice_amount = Decimal("1000.00")
        mock_match.amount_tolerance_percent = 2.0

        amounts = service._collect_amounts(mock_match)
        discrepancies = service._check_amount_discrepancies(mock_match, amounts)

        # po ist 0, wird uebersprungen -> nur dn vs invoice (gleich = 0%)
        assert len(discrepancies) == 0

    def test_discrepancy_fields_populated(
        self, service: POMatchingService, mock_match: Mock
    ) -> None:
        """Abweichungsfelder werden vollstaendig befuellt."""
        mock_match.po_amount = Decimal("1000.00")
        mock_match.dn_amount = Decimal("1000.00")
        mock_match.invoice_amount = Decimal("1200.00")
        mock_match.amount_tolerance_percent = 2.0

        amounts = service._collect_amounts(mock_match)
        discrepancies = service._check_amount_discrepancies(mock_match, amounts)

        # Mindestens po vs invoice
        po_vs_inv = [d for d in discrepancies if "po_vs_invoice" in d.field_name]
        assert len(po_vs_inv) == 1

        disc = po_vs_inv[0]
        assert disc.match_id == TEST_MATCH_UUID
        assert disc.expected_amount == Decimal("1000.00")
        assert disc.actual_amount == Decimal("1200.00")
        assert disc.deviation_percent == pytest.approx(20.0, abs=0.1)
        assert "Betragabweichung" in disc.description
        assert "1000.00 EUR" in disc.expected_value
        assert "1200.00 EUR" in disc.actual_value


# ========================= Statistics Tests =========================


class TestGetStatistics:
    """Tests fuer POMatchingService.get_matching_statistics."""

    @pytest.mark.asyncio
    async def test_get_statistics_returns_dataclass(
        self, service: POMatchingService, mock_db: AsyncMock
    ) -> None:
        """Statistiken geben korrekte MatchStatistics zurueck."""
        # Mock verschiedene DB-Aufrufe in Reihenfolge
        # 1. Status-Zaehlung
        mock_status_counts = Mock()
        mock_status_counts.__iter__ = Mock(
            return_value=iter([
                (MatchStatus.PENDING, 5),
                (MatchStatus.PARTIAL, 10),
                (MatchStatus.FULL, 20),
                (MatchStatus.DISCREPANCY, 3),
                (MatchStatus.APPROVED, 8),
                (MatchStatus.REJECTED, 1),
            ])
        )

        # 2. Avg Score
        mock_avg_score = Mock()
        mock_avg_score.scalar.return_value = 85.5

        # 3. Auto-matched Count
        mock_auto_count = Mock()
        mock_auto_count.scalar.return_value = 12

        # 4. Total Discrepancies
        mock_total_disc = Mock()
        mock_total_disc.scalar.return_value = 15

        # 5. Unresolved Discrepancies
        mock_unresolved = Mock()
        mock_unresolved.scalar.return_value = 7

        # 6. Avg Deviation
        mock_avg_dev = Mock()
        mock_avg_dev.scalar.return_value = 4.2

        mock_db.execute = AsyncMock(side_effect=[
            mock_status_counts,
            mock_avg_score,
            mock_auto_count,
            mock_total_disc,
            mock_unresolved,
            mock_avg_dev,
        ])

        result = await service.get_matching_statistics(
            mock_db,
            company_id=TEST_COMPANY_UUID,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 2, 10),
        )

        assert isinstance(result, MatchStatistics)
        assert result.total_matches == 47  # 5+10+20+3+8+1
        assert result.pending_matches == 5
        assert result.partial_matches == 10
        assert result.full_matches == 20
        assert result.discrepancy_matches == 3
        assert result.approved_matches == 8
        assert result.rejected_matches == 1
        assert result.auto_matched_count == 12
        assert result.avg_match_score == 85.5
        assert result.total_discrepancies == 15
        assert result.unresolved_discrepancies == 7
        assert result.avg_amount_deviation_percent == 4.2
        assert result.period_start == date(2026, 1, 1)
        assert result.period_end == date(2026, 2, 10)

    @pytest.mark.asyncio
    async def test_get_statistics_empty_period(
        self, service: POMatchingService, mock_db: AsyncMock
    ) -> None:
        """Leerer Zeitraum gibt Nullwerte zurueck."""
        mock_status_counts = Mock()
        mock_status_counts.__iter__ = Mock(return_value=iter([]))

        mock_avg_score = Mock()
        mock_avg_score.scalar.return_value = None  # kein Durchschnitt

        mock_auto_count = Mock()
        mock_auto_count.scalar.return_value = None

        mock_total_disc = Mock()
        mock_total_disc.scalar.return_value = None

        mock_unresolved = Mock()
        mock_unresolved.scalar.return_value = None

        mock_avg_dev = Mock()
        mock_avg_dev.scalar.return_value = None

        mock_db.execute = AsyncMock(side_effect=[
            mock_status_counts,
            mock_avg_score,
            mock_auto_count,
            mock_total_disc,
            mock_unresolved,
            mock_avg_dev,
        ])

        result = await service.get_matching_statistics(
            mock_db,
            company_id=TEST_COMPANY_UUID,
            period_start=date(2026, 3, 1),
            period_end=date(2026, 3, 31),
        )

        assert result.total_matches == 0
        assert result.avg_match_score == 0.0
        assert result.auto_matched_count == 0
        assert result.total_discrepancies == 0
        assert result.unresolved_discrepancies == 0


# ========================= Singleton Tests =========================


class TestSingleton:
    """Tests fuer get_po_matching_service Singleton."""

    def test_singleton_returns_same_instance(self) -> None:
        """Factory gibt immer dieselbe Instanz zurueck."""
        from app.services.finance.po_matching_service import get_po_matching_service

        service1 = get_po_matching_service()
        service2 = get_po_matching_service()

        assert service1 is service2
        assert isinstance(service1, POMatchingService)

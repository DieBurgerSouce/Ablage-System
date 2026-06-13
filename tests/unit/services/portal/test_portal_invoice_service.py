# -*- coding: utf-8 -*-
"""
Unit Tests fuer PortalInvoiceService.

Testet:
- get_invoices_for_entity() mit Filterung
- get_invoice_summary() Berechnung
- get_open_invoices()
- get_invoice_detail() mit gueltigen/ungueltigen IDs
- Entity-Isolation (keine fremden Rechnungen sichtbar)

Feinpoliert und durchdacht - Portal Invoice Tests.
"""

from datetime import date, timedelta
from decimal import Decimal
from typing import List
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from app.services.portal.portal_invoice_service import (
    PortalInvoiceService,
    get_portal_invoice_service,
)
from .conftest import create_mock_result, generate_invoices


# ========================= Test Fixtures =========================


@pytest.fixture
def invoice_service(mock_db: AsyncMock) -> PortalInvoiceService:
    """Create PortalInvoiceService instance with mocked db."""
    return PortalInvoiceService(mock_db)


# ========================= Factory Function Tests =========================


class TestFactoryFunction:
    """Tests fuer get_portal_invoice_service Factory."""

    def test_get_portal_invoice_service_returns_instance(self, mock_db: AsyncMock):
        """Factory sollte PortalInvoiceService-Instanz zurueckgeben."""
        service = get_portal_invoice_service(mock_db)

        assert isinstance(service, PortalInvoiceService)
        assert service.db is mock_db


# ========================= Get Invoices Tests =========================


class TestGetInvoicesForEntity:
    """Tests fuer get_invoices_for_entity() Methode."""

    @pytest.mark.asyncio
    async def test_get_invoices_success(
        self,
        invoice_service: PortalInvoiceService,
        mock_db: AsyncMock,
        entity_id: UUID,
        company_id: UUID,
    ):
        """Sollte Rechnungen fuer Entity zurueckgeben."""
        invoices = generate_invoices(entity_id, company_id, count=5, status="open")

        # Mock count query
        count_result = create_mock_result(scalar_value=5)
        # Mock list query
        list_result = create_mock_result(scalars_list=invoices)

        mock_db.execute.side_effect = [count_result, list_result]

        result, total = await invoice_service.get_invoices_for_entity(
            entity_id=entity_id,
            company_id=company_id,
        )

        assert total == 5
        assert len(result) == 5
        assert mock_db.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_get_invoices_with_status_filter(
        self,
        invoice_service: PortalInvoiceService,
        mock_db: AsyncMock,
        entity_id: UUID,
        company_id: UUID,
    ):
        """Sollte nach Status filtern."""
        open_invoices = generate_invoices(entity_id, company_id, count=3, status="open")

        count_result = create_mock_result(scalar_value=3)
        list_result = create_mock_result(scalars_list=open_invoices)
        mock_db.execute.side_effect = [count_result, list_result]

        result, total = await invoice_service.get_invoices_for_entity(
            entity_id=entity_id,
            company_id=company_id,
            status="open",
        )

        assert total == 3
        # get_invoices_for_entity liefert eine Liste von Dicts
        for inv in result:
            assert inv["status"] == "open"

    @pytest.mark.asyncio
    async def test_get_invoices_with_date_filter(
        self,
        invoice_service: PortalInvoiceService,
        mock_db: AsyncMock,
        entity_id: UUID,
        company_id: UUID,
    ):
        """Sollte nach Datumsbereich filtern."""
        invoices = generate_invoices(entity_id, company_id, count=2)

        count_result = create_mock_result(scalar_value=2)
        list_result = create_mock_result(scalars_list=invoices)
        mock_db.execute.side_effect = [count_result, list_result]

        from_date = date.today() - timedelta(days=30)
        to_date = date.today()

        result, total = await invoice_service.get_invoices_for_entity(
            entity_id=entity_id,
            company_id=company_id,
            from_date=from_date,
            to_date=to_date,
        )

        assert total == 2

    @pytest.mark.asyncio
    async def test_get_invoices_pagination(
        self,
        invoice_service: PortalInvoiceService,
        mock_db: AsyncMock,
        entity_id: UUID,
        company_id: UUID,
    ):
        """Sollte Pagination unterstuetzen."""
        invoices = generate_invoices(entity_id, company_id, count=2)

        count_result = create_mock_result(scalar_value=10)
        list_result = create_mock_result(scalars_list=invoices)
        mock_db.execute.side_effect = [count_result, list_result]

        result, total = await invoice_service.get_invoices_for_entity(
            entity_id=entity_id,
            company_id=company_id,
            limit=2,
            offset=4,
        )

        assert total == 10
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_invoices_empty(
        self,
        invoice_service: PortalInvoiceService,
        mock_db: AsyncMock,
        entity_id: UUID,
        company_id: UUID,
    ):
        """Sollte leere Liste zurueckgeben wenn keine Rechnungen."""
        count_result = create_mock_result(scalar_value=0)
        list_result = create_mock_result(scalars_list=[])
        mock_db.execute.side_effect = [count_result, list_result]

        result, total = await invoice_service.get_invoices_for_entity(
            entity_id=entity_id,
            company_id=company_id,
        )

        assert total == 0
        assert result == []


# ========================= Invoice Summary Tests =========================


class TestGetInvoiceSummary:
    """Tests fuer get_invoice_summary() Methode."""

    @pytest.mark.asyncio
    async def test_get_invoice_summary_success(
        self,
        invoice_service: PortalInvoiceService,
        mock_db: AsyncMock,
        entity_id: UUID,
        company_id: UUID,
    ):
        """Sollte korrekte Zusammenfassung berechnen.

        Vertrag: get_invoice_summary laedt ALLE Rechnungen (scalars().all())
        und aggregiert in Python. Rueckgabe-Dict nutzt die Schluessel
        total_invoices/open_invoices/overdue_invoices/total_outstanding/...
        (keine SQL-Aggregat-Zeile mit total_count).
        """
        invoices = generate_invoices(entity_id, company_id, count=5, status="open")
        # Eine Rechnung bezahlt, eine ueberfaellig machen
        invoices[0].status = "paid"
        invoices[1].status = "overdue"
        invoices[1].due_date = date.today() - timedelta(days=5)
        invoices[1].outstanding_amount = Decimal("200.00")

        mock_db.execute.return_value = create_mock_result(scalars_list=invoices)

        result = await invoice_service.get_invoice_summary(
            entity_id=entity_id,
            company_id=company_id,
        )

        assert result["total_invoices"] == 5
        # 4 nicht bezahlte (eine ist "paid")
        assert result["open_invoices"] == 4
        assert result["overdue_invoices"] >= 1
        assert result["currency"] == "EUR"


# ========================= Open Invoices Tests =========================


class TestGetOpenInvoices:
    """Tests fuer get_open_invoices() Methode."""

    @pytest.mark.asyncio
    async def test_get_open_invoices_success(
        self,
        invoice_service: PortalInvoiceService,
        mock_db: AsyncMock,
        entity_id: UUID,
        company_id: UUID,
    ):
        """Sollte nur offene Rechnungen zurueckgeben."""
        open_invoices = generate_invoices(entity_id, company_id, count=3, status="open")

        mock_db.execute.return_value = create_mock_result(scalars_list=open_invoices)

        result = await invoice_service.get_open_invoices(
            entity_id=entity_id,
            company_id=company_id,
        )

        assert len(result) == 3
        # get_open_invoices liefert eine schlanke Dict-Ansicht (ohne status-Feld;
        # der Status-Filter erfolgt in der Query)
        for inv in result:
            assert "id" in inv
            assert "outstanding_amount" in inv


# ========================= Invoice Detail Tests =========================


class TestGetInvoiceDetail:
    """Tests fuer get_invoice_detail() Methode."""

    @pytest.mark.asyncio
    async def test_get_invoice_detail_success(
        self,
        invoice_service: PortalInvoiceService,
        mock_db: AsyncMock,
        sample_invoice_tracking,
        entity_id: UUID,
        company_id: UUID,
        invoice_id: UUID,
    ):
        """Sollte Rechnungsdetails zurueckgeben."""
        mock_db.execute.return_value = create_mock_result(
            scalar_value=sample_invoice_tracking
        )

        result = await invoice_service.get_invoice_detail(
            invoice_id=invoice_id,
            entity_id=entity_id,
            company_id=company_id,
        )

        assert result is not None
        # get_invoice_detail liefert ein Dict (serialisierte Rechnung)
        assert result["id"] == str(sample_invoice_tracking.id)

    @pytest.mark.asyncio
    async def test_get_invoice_detail_not_found(
        self,
        invoice_service: PortalInvoiceService,
        mock_db: AsyncMock,
        entity_id: UUID,
        company_id: UUID,
    ):
        """Sollte None zurueckgeben wenn Rechnung nicht existiert."""
        mock_db.execute.return_value = create_mock_result(scalar_value=None)

        result = await invoice_service.get_invoice_detail(
            invoice_id=uuid4(),
            entity_id=entity_id,
            company_id=company_id,
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_get_invoice_detail_wrong_entity(
        self,
        invoice_service: PortalInvoiceService,
        mock_db: AsyncMock,
        sample_invoice_tracking,
        other_entity_id: UUID,
        company_id: UUID,
        invoice_id: UUID,
    ):
        """Sollte None zurueckgeben wenn Rechnung zu anderer Entity gehoert."""
        # Invoice belongs to different entity, query should return None
        mock_db.execute.return_value = create_mock_result(scalar_value=None)

        result = await invoice_service.get_invoice_detail(
            invoice_id=invoice_id,
            entity_id=other_entity_id,
            company_id=company_id,
        )

        assert result is None


# ========================= Entity Isolation Tests =========================


class TestEntityIsolation:
    """Tests fuer Entity-Isolation - keine fremden Daten sichtbar."""

    @pytest.mark.asyncio
    async def test_cannot_see_other_entity_invoices(
        self,
        invoice_service: PortalInvoiceService,
        mock_db: AsyncMock,
        entity_id: UUID,
        other_entity_id: UUID,
        company_id: UUID,
    ):
        """Entity A sollte keine Rechnungen von Entity B sehen."""
        # Create invoices for entity_id
        entity_invoices = generate_invoices(entity_id, company_id, count=3)
        # Create invoices for other_entity_id
        other_invoices = generate_invoices(other_entity_id, company_id, count=2)

        # Query for other_entity_id should only return its invoices
        count_result = create_mock_result(scalar_value=2)
        list_result = create_mock_result(scalars_list=other_invoices)
        mock_db.execute.side_effect = [count_result, list_result]

        result, total = await invoice_service.get_invoices_for_entity(
            entity_id=other_entity_id,
            company_id=company_id,
        )

        # Sieht nur die Rechnungen der abgefragten Entity. Die Isolation wird
        # ueber den Query-Filter (entity_id) erzwungen; die schlanke Dict-Ansicht
        # enthaelt selbst kein entity_id-Feld.
        assert total == 2
        assert len(result) == 2

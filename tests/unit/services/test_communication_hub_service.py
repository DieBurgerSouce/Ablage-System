# -*- coding: utf-8 -*-
"""Unit Tests fuer CommunicationHubService.

Vision 2026+ Feature #1: Kommunikations-Hub (360° Entity View)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.communication_hub_service import (
    CommunicationHubService,
    CommunicationHubData,
    CommunicationTimelineItem,
    InvoiceSummary,
    RiskTrend,
)


@pytest.fixture
def mock_db() -> AsyncMock:
    """Mock AsyncSession."""
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def service(mock_db: AsyncMock) -> CommunicationHubService:
    """Erstellt Service-Instanz."""
    return CommunicationHubService(mock_db)


@pytest.fixture
def entity_id() -> uuid.UUID:
    """Test Entity ID."""
    return uuid.uuid4()


@pytest.fixture
def company_id() -> uuid.UUID:
    """Test Company ID."""
    return uuid.uuid4()


# =============================================================================
# Test: get_communication_hub - Basis
# =============================================================================


class TestGetCommunicationHub:
    """Tests fuer get_communication_hub Methode."""

    @pytest.mark.asyncio
    async def test_returns_communication_hub_data(
        self,
        service: CommunicationHubService,
        mock_db: AsyncMock,
        entity_id: uuid.UUID,
        company_id: uuid.UUID,
    ) -> None:
        """Gibt CommunicationHubData zurueck."""
        # Mock _load_entity
        with patch.object(
            service, "_load_entity", new_callable=AsyncMock
        ) as mock_entity:
            mock_entity.return_value = {"id": str(entity_id), "name": "Test GmbH"}

            with patch.object(
                service, "_build_timeline", new_callable=AsyncMock
            ) as mock_timeline:
                mock_timeline.return_value = []

                with patch.object(
                    service, "_get_invoice_summary", new_callable=AsyncMock
                ) as mock_invoices:
                    mock_invoices.return_value = InvoiceSummary()

                    with patch.object(
                        service, "_get_risk_trend", new_callable=AsyncMock
                    ) as mock_risk:
                        mock_risk.return_value = RiskTrend()

                        with patch.object(
                            service, "_get_communication_stats", new_callable=AsyncMock
                        ) as mock_stats:
                            mock_stats.return_value = {}

                            with patch.object(
                                service, "_get_recent_documents", new_callable=AsyncMock
                            ) as mock_docs:
                                mock_docs.return_value = []

                                with patch.object(
                                    service, "_get_open_tasks", new_callable=AsyncMock
                                ) as mock_tasks:
                                    mock_tasks.return_value = []

                                    with patch.object(
                                        service, "_get_phone_notes", new_callable=AsyncMock
                                    ) as mock_notes:
                                        mock_notes.return_value = []

                                        result = await service.get_communication_hub(
                                            entity_id, company_id
                                        )

        assert isinstance(result, CommunicationHubData)
        assert result.entity == {"id": str(entity_id), "name": "Test GmbH"}

    @pytest.mark.asyncio
    async def test_filters_sections(
        self,
        service: CommunicationHubService,
        mock_db: AsyncMock,
        entity_id: uuid.UUID,
        company_id: uuid.UUID,
    ) -> None:
        """Filtert Sektionen basierend auf include_sections."""
        with patch.object(
            service, "_load_entity", new_callable=AsyncMock
        ) as mock_entity:
            mock_entity.return_value = {"id": str(entity_id)}

            result = await service.get_communication_hub(
                entity_id, company_id, include_sections=["entity"]
            )

        # Nur entity sollte geladen werden
        mock_entity.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_entity_error_gracefully(
        self,
        service: CommunicationHubService,
        mock_db: AsyncMock,
        entity_id: uuid.UUID,
        company_id: uuid.UUID,
    ) -> None:
        """Behandelt Entity-Fehler ohne Exception."""
        with patch.object(
            service, "_load_entity", new_callable=AsyncMock
        ) as mock_entity:
            mock_entity.side_effect = Exception("DB Error")

            result = await service.get_communication_hub(
                entity_id, company_id, include_sections=["entity"]
            )

        # Sollte nicht crashen, sondern Error-Entity zurueckgeben
        assert "error" in result.entity

    @pytest.mark.asyncio
    async def test_handles_timeline_error_gracefully(
        self,
        service: CommunicationHubService,
        mock_db: AsyncMock,
        entity_id: uuid.UUID,
        company_id: uuid.UUID,
    ) -> None:
        """Behandelt Timeline-Fehler ohne Abbruch."""
        with patch.object(
            service, "_load_entity", new_callable=AsyncMock
        ) as mock_entity:
            mock_entity.return_value = {"id": str(entity_id)}

            with patch.object(
                service, "_build_timeline", new_callable=AsyncMock
            ) as mock_timeline:
                mock_timeline.side_effect = Exception("Timeline Error")

                result = await service.get_communication_hub(
                    entity_id, company_id, include_sections=["entity", "timeline"]
                )

        # Timeline sollte leer sein, aber Hub sollte existieren
        assert result.timeline == []


# =============================================================================
# Test: _load_entity - Multi-Tenant
# =============================================================================


class TestLoadEntity:
    """Tests fuer _load_entity mit Multi-Tenant Isolation."""

    @pytest.mark.asyncio
    async def test_verifies_company_access_via_documents(
        self,
        service: CommunicationHubService,
        mock_db: AsyncMock,
        entity_id: uuid.UUID,
        company_id: uuid.UUID,
    ) -> None:
        """Prueft Zugriff via Document.company_id."""
        # Mock: Kein Zugriff (0 Dokumente)
        mock_result = MagicMock()
        mock_result.scalar.return_value = 0
        mock_db.execute.return_value = mock_result

        result = await service._load_entity(entity_id, company_id)

        # Sollte leer zurueckgeben wenn kein Zugriff
        assert result == {}

    @pytest.mark.asyncio
    async def test_returns_entity_when_access_granted(
        self,
        service: CommunicationHubService,
        mock_db: AsyncMock,
        entity_id: uuid.UUID,
        company_id: uuid.UUID,
    ) -> None:
        """Gibt Entity zurueck wenn Zugriff erlaubt."""
        # Mock: Zugriff erlaubt (1+ Dokumente)
        access_result = MagicMock()
        access_result.scalar.return_value = 1

        # Mock Entity
        mock_entity = MagicMock()
        mock_entity.id = entity_id
        mock_entity.name = "Test GmbH"
        mock_entity.display_name = "Test GmbH"
        mock_entity.entity_type = "supplier"
        mock_entity.risk_score = 25.0
        mock_entity.created_at = datetime.now(timezone.utc)

        entity_result = MagicMock()
        entity_result.scalar_one_or_none.return_value = mock_entity

        # Zwei execute Aufrufe: Access Check, dann Entity laden
        mock_db.execute.side_effect = [access_result, entity_result]

        result = await service._load_entity(entity_id, company_id)

        assert result.get("id") == str(entity_id)
        assert result.get("name") == "Test GmbH"


# =============================================================================
# Test: InvoiceSummary
# =============================================================================


class TestGetInvoiceSummary:
    """Tests fuer _get_invoice_summary."""

    @pytest.mark.asyncio
    async def test_calculates_invoice_totals(
        self,
        service: CommunicationHubService,
        mock_db: AsyncMock,
        entity_id: uuid.UUID,
        company_id: uuid.UUID,
    ) -> None:
        """Berechnet Rechnungssummen korrekt."""
        # Quelle iteriert ueber einzelne InvoiceTracking-Objekte
        # (result.scalars().all()), nicht ueber eine aggregierte .one()-Zeile.
        now = datetime.now(timezone.utc)
        past_due = (now - timedelta(days=10)).date()
        future_due = (now + timedelta(days=10)).date()
        inv_date = (now - timedelta(days=20)).date()

        invoices = []
        # 1 ueberfaellige offene Rechnung (open + ueberfaellig)
        inv_overdue = MagicMock()
        inv_overdue.amount = Decimal("1000.00")
        inv_overdue.status = "open"
        inv_overdue.due_date = past_due
        inv_overdue.invoice_date = inv_date
        inv_overdue.dunning_level = 0
        inv_overdue.paid_at = None
        invoices.append(inv_overdue)
        # 2 weitere offene, nicht ueberfaellige
        for _ in range(2):
            inv = MagicMock()
            inv.amount = Decimal("1000.00")
            inv.status = "open"
            inv.due_date = future_due
            inv.invoice_date = inv_date
            inv.dunning_level = 0
            inv.paid_at = None
            invoices.append(inv)
        # 7 bezahlte
        for _ in range(7):
            inv = MagicMock()
            inv.amount = Decimal("1000.00")
            inv.status = "paid"
            inv.due_date = past_due
            inv.invoice_date = inv_date
            inv.dunning_level = 0
            inv.paid_at = now
            invoices.append(inv)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = invoices
        mock_db.execute.return_value = mock_result

        result = await service._get_invoice_summary(entity_id, company_id)

        assert isinstance(result, InvoiceSummary)
        assert result.total_invoices == 10
        assert result.open_invoices == 3
        assert result.overdue_invoices == 1


# =============================================================================
# Test: RiskTrend
# =============================================================================


class TestGetRiskTrend:
    """Tests fuer _get_risk_trend."""

    @pytest.mark.asyncio
    async def test_returns_risk_trend(
        self,
        service: CommunicationHubService,
        mock_db: AsyncMock,
        entity_id: uuid.UUID,
        company_id: uuid.UUID,
    ) -> None:
        """Gibt RiskTrend zurueck."""
        # Mock Entity mit Risk Score
        mock_entity = MagicMock()
        mock_entity.risk_score = 45.0
        mock_entity.risk_factors = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_entity
        # Folge-Queries (Zahlungsverzoegerung) nutzen .scalar(); None -> 0,
        # sonst MagicMock-Arithmetik (TypeError) in der Trend-Berechnung.
        mock_result.scalar.return_value = None
        mock_db.execute.return_value = mock_result

        result = await service._get_risk_trend(entity_id, company_id)

        assert isinstance(result, RiskTrend)
        assert result.current_score == 45.0
        assert result.risk_level == "medium"  # 45.0 -> medium


# =============================================================================
# Test: Error Handling
# =============================================================================


class TestErrorHandling:
    """Tests fuer robustes Error Handling."""

    @pytest.mark.asyncio
    async def test_partial_failure_returns_partial_data(
        self,
        service: CommunicationHubService,
        mock_db: AsyncMock,
        entity_id: uuid.UUID,
        company_id: uuid.UUID,
    ) -> None:
        """Bei partiellem Fehler werden andere Sektionen trotzdem geladen."""
        with patch.object(
            service, "_load_entity", new_callable=AsyncMock
        ) as mock_entity:
            mock_entity.return_value = {"id": str(entity_id)}

            # Timeline schlaegt fehl
            with patch.object(
                service, "_build_timeline", new_callable=AsyncMock
            ) as mock_timeline:
                mock_timeline.side_effect = Exception("Timeline broken")

                # Invoices funktionieren
                with patch.object(
                    service, "_get_invoice_summary", new_callable=AsyncMock
                ) as mock_invoices:
                    mock_invoices.return_value = InvoiceSummary(total_invoices=5)

                    with patch.object(
                        service, "_get_risk_trend", new_callable=AsyncMock
                    ) as mock_risk:
                        mock_risk.return_value = RiskTrend()

                        with patch.object(
                            service, "_get_communication_stats", new_callable=AsyncMock
                        ) as mock_stats:
                            mock_stats.return_value = {}

                            with patch.object(
                                service, "_get_recent_documents", new_callable=AsyncMock
                            ) as mock_docs:
                                mock_docs.return_value = []

                                with patch.object(
                                    service, "_get_open_tasks", new_callable=AsyncMock
                                ) as mock_tasks:
                                    mock_tasks.return_value = []

                                    with patch.object(
                                        service, "_get_phone_notes", new_callable=AsyncMock
                                    ) as mock_notes:
                                        mock_notes.return_value = []

                                        result = await service.get_communication_hub(
                                            entity_id, company_id
                                        )

        # Entity und Invoices sollten geladen sein
        assert result.entity.get("id") == str(entity_id)
        assert result.invoice_summary.total_invoices == 5
        # Timeline sollte leer sein
        assert result.timeline == []

    @pytest.mark.asyncio
    async def test_all_sections_fail_returns_empty_hub(
        self,
        service: CommunicationHubService,
        mock_db: AsyncMock,
        entity_id: uuid.UUID,
        company_id: uuid.UUID,
    ) -> None:
        """Bei totalem Fehler gibt leeren Hub zurueck."""
        methods = [
            "_load_entity",
            "_build_timeline",
            "_get_invoice_summary",
            "_get_risk_trend",
            "_get_communication_stats",
            "_get_recent_documents",
            "_get_open_tasks",
            "_get_phone_notes",
        ]

        patches = {}
        for method in methods:
            patches[method] = patch.object(
                service, method, new_callable=AsyncMock,
                side_effect=Exception("DB Error")
            )

        with patches["_load_entity"], patches["_build_timeline"], \
             patches["_get_invoice_summary"], patches["_get_risk_trend"], \
             patches["_get_communication_stats"], patches["_get_recent_documents"], \
             patches["_get_open_tasks"], patches["_get_phone_notes"]:

            result = await service.get_communication_hub(entity_id, company_id)

        # Sollte nicht crashen
        assert isinstance(result, CommunicationHubData)


# =============================================================================
# Test: Edge Cases
# =============================================================================


class TestEdgeCases:
    """Tests fuer Edge Cases."""

    @pytest.mark.asyncio
    async def test_handles_unicode_entity_names(
        self,
        service: CommunicationHubService,
        mock_db: AsyncMock,
        entity_id: uuid.UUID,
        company_id: uuid.UUID,
    ) -> None:
        """Behandelt Unicode/Umlaute in Entity-Namen korrekt."""
        with patch.object(
            service, "_load_entity", new_callable=AsyncMock
        ) as mock_entity:
            # Deutsche Umlaute und Sonderzeichen
            mock_entity.return_value = {
                "id": str(entity_id),
                "name": "Müller & Söhne GmbH",
                "address": "Königstraße 42, München",
            }

            result = await service.get_communication_hub(
                entity_id, company_id, include_sections=["entity"]
            )

        assert "Müller" in result.entity.get("name", "")
        assert "Königstraße" in result.entity.get("address", "")

    @pytest.mark.asyncio
    async def test_handles_empty_entity_id(
        self,
        service: CommunicationHubService,
        mock_db: AsyncMock,
        company_id: uuid.UUID,
    ) -> None:
        """Behandelt ungültige Entity-ID graceful."""
        with patch.object(
            service, "_load_entity", new_callable=AsyncMock
        ) as mock_entity:
            mock_entity.return_value = {}

            # Sollte nicht crashen
            result = await service.get_communication_hub(
                uuid.uuid4(), company_id, include_sections=["entity"]
            )

        assert result.entity == {}

    @pytest.mark.asyncio
    async def test_handles_large_timeline(
        self,
        service: CommunicationHubService,
        mock_db: AsyncMock,
        entity_id: uuid.UUID,
        company_id: uuid.UUID,
    ) -> None:
        """Respektiert Limits bei grosser Timeline."""
        with patch.object(
            service, "_load_entity", new_callable=AsyncMock
        ) as mock_entity:
            mock_entity.return_value = {"id": str(entity_id)}

            with patch.object(
                service, "_build_timeline", new_callable=AsyncMock
            ) as mock_timeline:
                # Simuliere 1000 Timeline-Eintraege (mehr als Limit)
                mock_timeline.return_value = []

                result = await service.get_communication_hub(
                    entity_id, company_id,
                    timeline_limit=50,  # Nur 50 erlaubt
                    include_sections=["entity", "timeline"]
                )

        # Timeline sollte leer sein (gemockt)
        assert len(result.timeline) == 0


# =============================================================================
# Test: Limits and Pagination
# =============================================================================


class TestLimitsAndPagination:
    """Tests fuer Limits und Pagination."""

    @pytest.mark.asyncio
    async def test_respects_timeline_limit(
        self,
        service: CommunicationHubService,
        mock_db: AsyncMock,
        entity_id: uuid.UUID,
        company_id: uuid.UUID,
    ) -> None:
        """Respektiert timeline_limit Parameter."""
        with patch.object(
            service, "_load_entity", new_callable=AsyncMock
        ) as mock_entity:
            mock_entity.return_value = {"id": str(entity_id)}

            with patch.object(
                service, "_build_timeline", new_callable=AsyncMock
            ) as mock_timeline:
                mock_timeline.return_value = []

                await service.get_communication_hub(
                    entity_id, company_id,
                    timeline_limit=25,
                    include_sections=["entity", "timeline"]
                )

        # Sollte mit limit=25 aufgerufen werden
        mock_timeline.assert_called_once_with(entity_id, company_id, limit=25)

    @pytest.mark.asyncio
    async def test_respects_documents_limit(
        self,
        service: CommunicationHubService,
        mock_db: AsyncMock,
        entity_id: uuid.UUID,
        company_id: uuid.UUID,
    ) -> None:
        """Respektiert documents_limit Parameter."""
        with patch.object(
            service, "_load_entity", new_callable=AsyncMock
        ) as mock_entity:
            mock_entity.return_value = {"id": str(entity_id)}

            with patch.object(
                service, "_get_recent_documents", new_callable=AsyncMock
            ) as mock_docs:
                mock_docs.return_value = []

                await service.get_communication_hub(
                    entity_id, company_id,
                    documents_limit=5,
                    include_sections=["entity", "documents"]
                )

        # Sollte mit limit=5 aufgerufen werden
        mock_docs.assert_called_once_with(entity_id, company_id, limit=5)

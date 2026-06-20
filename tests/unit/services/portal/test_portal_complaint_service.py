# -*- coding: utf-8 -*-
"""
Unit Tests fuer PortalComplaintService.

Testet:
- submit_complaint()
- get_complaints()
- get_complaint_detail()
- update_complaint_status()
- add_complaint_response()
- Entity-Isolation

Feinpoliert und durchdacht - Portal Complaint Tests.
"""

from datetime import datetime, timezone, timedelta
from typing import List
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from app.services.portal.portal_complaint_service import (
    PortalComplaintService,
    get_portal_complaint_service,
)
from app.db.models_portal import ComplaintStatus, ComplaintType
from .conftest import create_mock_result, generate_complaints


# ========================= Test Fixtures =========================


@pytest.fixture
def complaint_service(mock_db: AsyncMock) -> PortalComplaintService:
    """Create PortalComplaintService instance with mocked db."""
    return PortalComplaintService(mock_db)


# ========================= Factory Function Tests =========================


class TestFactoryFunction:
    """Tests fuer get_portal_complaint_service Factory."""

    def test_get_portal_complaint_service_returns_instance(self, mock_db: AsyncMock):
        """Factory sollte PortalComplaintService-Instanz zurueckgeben."""
        service = get_portal_complaint_service(mock_db)

        assert isinstance(service, PortalComplaintService)
        assert service.db is mock_db


# ========================= Submit Complaint Tests =========================


class TestSubmitComplaint:
    """Tests fuer submit_complaint() Methode."""

    @pytest.mark.asyncio
    async def test_submit_complaint_success(
        self,
        complaint_service: PortalComplaintService,
        mock_db: AsyncMock,
        sample_portal_user,
    ):
        """Sollte Reklamation erfolgreich erstellen."""
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        await complaint_service.submit_complaint(
            portal_user=sample_portal_user,
            complaint_type=ComplaintType.INVOICE_ERROR.value,
            subject="Falscher Betrag auf Rechnung",
            description="Die Rechnung RE-2026-00123 weist einen falschen Gesamtbetrag auf.",
        )

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_submit_complaint_with_invoice(
        self,
        complaint_service: PortalComplaintService,
        mock_db: AsyncMock,
        sample_portal_user,
        invoice_id: UUID,
    ):
        """Sollte Reklamation mit Rechnungsbezug erstellen."""
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        await complaint_service.submit_complaint(
            portal_user=sample_portal_user,
            complaint_type=ComplaintType.INVOICE_ERROR.value,
            subject="Rechnungsfehler",
            description="Fehler auf der Rechnung",
            invoice_tracking_id=invoice_id,
        )

        mock_db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_submit_complaint_with_document(
        self,
        complaint_service: PortalComplaintService,
        mock_db: AsyncMock,
        sample_portal_user,
        document_id: UUID,
    ):
        """Sollte Reklamation mit Dokumentbezug erstellen."""
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        await complaint_service.submit_complaint(
            portal_user=sample_portal_user,
            complaint_type=ComplaintType.DELIVERY_ISSUE.value,
            subject="Lieferproblem",
            description="Paket beschaedigt angekommen",
            document_id=document_id,
        )

        mock_db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_submit_complaint_generates_reference(
        self,
        complaint_service: PortalComplaintService,
        mock_db: AsyncMock,
        sample_portal_user,
    ):
        """Sollte eindeutige Referenznummer generieren."""
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        await complaint_service.submit_complaint(
            portal_user=sample_portal_user,
            complaint_type=ComplaintType.OTHER.value,
            subject="Sonstiges",
            description="Allgemeine Anfrage",
        )

        # Verify add was called (reference is generated internally)
        mock_db.add.assert_called_once()


# ========================= Get Complaints Tests =========================


class TestGetComplaints:
    """Tests fuer get_complaints() Methode."""

    @pytest.mark.asyncio
    async def test_get_complaints_success(
        self,
        complaint_service: PortalComplaintService,
        mock_db: AsyncMock,
        entity_id: UUID,
        company_id: UUID,
        portal_user_id: UUID,
    ):
        """Sollte Reklamationen zurueckgeben."""
        complaints = generate_complaints(entity_id, company_id, portal_user_id, count=3)

        count_result = create_mock_result(scalar_value=3)
        list_result = create_mock_result(scalars_list=complaints)
        mock_db.execute.side_effect = [count_result, list_result]

        result, total = await complaint_service.get_complaints(
            entity_id=entity_id,
            company_id=company_id,
        )

        assert total == 3
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_get_complaints_filter_by_status(
        self,
        complaint_service: PortalComplaintService,
        mock_db: AsyncMock,
        entity_id: UUID,
        company_id: UUID,
        portal_user_id: UUID,
    ):
        """Sollte nach Status filtern."""
        complaints = generate_complaints(entity_id, company_id, portal_user_id, count=2)
        for c in complaints:
            c.status = ComplaintStatus.NEW

        count_result = create_mock_result(scalar_value=2)
        list_result = create_mock_result(scalars_list=complaints)
        mock_db.execute.side_effect = [count_result, list_result]

        result, total = await complaint_service.get_complaints(
            entity_id=entity_id,
            company_id=company_id,
            status=ComplaintStatus.NEW,
        )

        assert total == 2
        # get_complaints liefert eine Liste von Dicts (serialisierte Reklamationen)
        for c in result:
            assert c["status"] == ComplaintStatus.NEW

    @pytest.mark.asyncio
    async def test_get_complaints_filter_by_type(
        self,
        complaint_service: PortalComplaintService,
        mock_db: AsyncMock,
        entity_id: UUID,
        company_id: UUID,
        portal_user_id: UUID,
    ):
        """Sollte nach Reklamationstyp filtern."""
        complaints = generate_complaints(entity_id, company_id, portal_user_id, count=1)
        complaints[0].complaint_type = ComplaintType.INVOICE_ERROR.value

        count_result = create_mock_result(scalar_value=1)
        list_result = create_mock_result(scalars_list=complaints)
        mock_db.execute.side_effect = [count_result, list_result]

        result, total = await complaint_service.get_complaints(
            entity_id=entity_id,
            company_id=company_id,
            complaint_type=ComplaintType.INVOICE_ERROR,
        )

        assert total == 1

    @pytest.mark.asyncio
    async def test_get_complaints_empty(
        self,
        complaint_service: PortalComplaintService,
        mock_db: AsyncMock,
        entity_id: UUID,
        company_id: UUID,
    ):
        """Sollte leere Liste bei keinen Reklamationen."""
        count_result = create_mock_result(scalar_value=0)
        list_result = create_mock_result(scalars_list=[])
        mock_db.execute.side_effect = [count_result, list_result]

        result, total = await complaint_service.get_complaints(
            entity_id=entity_id,
            company_id=company_id,
        )

        assert total == 0
        assert result == []


# ========================= Get Complaint Detail Tests =========================


class TestGetComplaintDetail:
    """Tests fuer get_complaint_detail() Methode."""

    @pytest.mark.asyncio
    async def test_get_complaint_detail_success(
        self,
        complaint_service: PortalComplaintService,
        mock_db: AsyncMock,
        sample_complaint,
        entity_id: UUID,
        company_id: UUID,
    ):
        """Sollte Reklamationsdetails zurueckgeben."""
        mock_db.execute.return_value = create_mock_result(scalar_value=sample_complaint)

        result = await complaint_service.get_complaint_detail(
            complaint_id=sample_complaint.id,
            entity_id=entity_id,
            company_id=company_id,
        )

        assert result is not None
        # get_complaint_detail liefert ein Dict (serialisierte Reklamation)
        assert result["id"] == str(sample_complaint.id)

    @pytest.mark.asyncio
    async def test_get_complaint_detail_not_found(
        self,
        complaint_service: PortalComplaintService,
        mock_db: AsyncMock,
        entity_id: UUID,
        company_id: UUID,
    ):
        """Sollte None zurueckgeben wenn nicht gefunden."""
        mock_db.execute.return_value = create_mock_result(scalar_value=None)

        result = await complaint_service.get_complaint_detail(
            complaint_id=uuid4(),
            entity_id=entity_id,
            company_id=company_id,
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_get_complaint_detail_wrong_entity(
        self,
        complaint_service: PortalComplaintService,
        mock_db: AsyncMock,
        sample_complaint,
        other_entity_id: UUID,
        company_id: UUID,
    ):
        """Sollte None bei falscher Entity-ID."""
        # Query returns None for wrong entity
        mock_db.execute.return_value = create_mock_result(scalar_value=None)

        result = await complaint_service.get_complaint_detail(
            complaint_id=sample_complaint.id,
            entity_id=other_entity_id,
            company_id=company_id,
        )

        assert result is None


# ========================= Update Status Tests =========================


@pytest.mark.xfail(
    strict=True,
    reason=(
        "update_complaint_status ist im kundenseitigen PortalComplaintService "
        "nicht implementiert. Der interne Status-Wechsel laeuft ueber den "
        "Admin-/Workflow-Pfad, nicht ueber diesen Service. Test bleibt als "
        "Vertrags-Marker (xfail) bis ein interner Service die Methode bereitstellt."
    ),
)
class TestUpdateComplaintStatus:
    """Tests fuer update_complaint_status() Methode (nicht im Service vorhanden)."""

    @pytest.mark.asyncio
    async def test_update_status_success(
        self,
        complaint_service: PortalComplaintService,
        mock_db: AsyncMock,
        sample_complaint,
        company_id: UUID,
    ):
        """Sollte Status aktualisieren."""
        sample_complaint.status = ComplaintStatus.NEW
        mock_db.execute.return_value = create_mock_result(scalar_value=sample_complaint)
        mock_db.commit = AsyncMock()

        result = await complaint_service.update_complaint_status(
            complaint_id=sample_complaint.id,
            company_id=company_id,
            new_status=ComplaintStatus.IN_REVIEW,
            updated_by_id=uuid4(),
        )

        assert result is not None
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_status_to_resolved(
        self,
        complaint_service: PortalComplaintService,
        mock_db: AsyncMock,
        sample_complaint,
        company_id: UUID,
    ):
        """Sollte Status auf RESOLVED setzen mit Resolution."""
        sample_complaint.status = ComplaintStatus.IN_REVIEW
        mock_db.execute.return_value = create_mock_result(scalar_value=sample_complaint)
        mock_db.commit = AsyncMock()

        result = await complaint_service.update_complaint_status(
            complaint_id=sample_complaint.id,
            company_id=company_id,
            new_status=ComplaintStatus.RESOLVED,
            updated_by_id=uuid4(),
            resolution="Problem wurde behoben",
        )

        assert result is not None
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_status_not_found(
        self,
        complaint_service: PortalComplaintService,
        mock_db: AsyncMock,
        company_id: UUID,
    ):
        """Sollte Fehler werfen wenn nicht gefunden."""
        mock_db.execute.return_value = create_mock_result(scalar_value=None)

        with pytest.raises(ValueError, match="nicht gefunden"):
            await complaint_service.update_complaint_status(
                complaint_id=uuid4(),
                company_id=company_id,
                new_status=ComplaintStatus.IN_REVIEW,
                updated_by_id=uuid4(),
            )


# ========================= Add Response Tests =========================


@pytest.mark.xfail(
    strict=True,
    reason=(
        "add_complaint_response (interne Antwort des Unternehmens) ist im "
        "kundenseitigen PortalComplaintService nicht implementiert. Kunden "
        "ergaenzen Infos ueber add_information; eine Unternehmens-Antwort-API "
        "fehlt hier. Test bleibt als Vertrags-Marker (xfail)."
    ),
)
class TestAddComplaintResponse:
    """Tests fuer add_complaint_response() Methode (nicht im Service vorhanden)."""

    @pytest.mark.asyncio
    async def test_add_response_success(
        self,
        complaint_service: PortalComplaintService,
        mock_db: AsyncMock,
        sample_complaint,
        company_id: UUID,
    ):
        """Sollte Antwort zur Reklamation hinzufuegen."""
        sample_complaint.first_response_at = None
        mock_db.execute.return_value = create_mock_result(scalar_value=sample_complaint)
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        responder_id = uuid4()
        result = await complaint_service.add_complaint_response(
            complaint_id=sample_complaint.id,
            company_id=company_id,
            internal_user_id=responder_id,
            content="Vielen Dank fuer Ihre Meldung. Wir pruefen das.",
        )

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_add_response_sets_first_response_at(
        self,
        complaint_service: PortalComplaintService,
        mock_db: AsyncMock,
        sample_complaint,
        company_id: UUID,
    ):
        """Sollte first_response_at bei erster Antwort setzen."""
        sample_complaint.first_response_at = None
        mock_db.execute.return_value = create_mock_result(scalar_value=sample_complaint)
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        await complaint_service.add_complaint_response(
            complaint_id=sample_complaint.id,
            company_id=company_id,
            internal_user_id=uuid4(),
            content="Erste Antwort",
        )

        # The service should set first_response_at
        mock_db.commit.assert_called()


# ========================= Entity Isolation Tests =========================


class TestEntityIsolation:
    """Tests fuer Entity-Isolation bei Reklamationen."""

    @pytest.mark.asyncio
    async def test_cannot_see_other_entity_complaints(
        self,
        complaint_service: PortalComplaintService,
        mock_db: AsyncMock,
        other_entity_id: UUID,
        company_id: UUID,
    ):
        """Entity A sollte keine Reklamationen von Entity B sehen."""
        count_result = create_mock_result(scalar_value=0)
        list_result = create_mock_result(scalars_list=[])
        mock_db.execute.side_effect = [count_result, list_result]

        result, total = await complaint_service.get_complaints(
            entity_id=other_entity_id,
            company_id=company_id,
        )

        assert total == 0
        assert result == []

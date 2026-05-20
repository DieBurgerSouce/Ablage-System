# -*- coding: utf-8 -*-
"""
Unit Tests fuer PortalCommunicationService.

Testet:
- send_message()
- get_messages()
- get_message_detail()
- mark_message_read()
- get_unread_count()
- Entity-Isolation

Feinpoliert und durchdacht - Portal Communication Tests.
"""

from datetime import datetime, timezone, timedelta
from typing import List
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from app.services.portal.portal_communication_service import (
    PortalCommunicationService,
    get_portal_communication_service,
)
from app.db.models_portal import MessageDirection
from .conftest import create_mock_result, generate_messages


# ========================= Test Fixtures =========================


@pytest.fixture
def communication_service(mock_db: AsyncMock) -> PortalCommunicationService:
    """Create PortalCommunicationService instance with mocked db."""
    return PortalCommunicationService(mock_db)


# ========================= Factory Function Tests =========================


class TestFactoryFunction:
    """Tests fuer get_portal_communication_service Factory."""

    def test_get_portal_communication_service_returns_instance(
        self, mock_db: AsyncMock
    ):
        """Factory sollte PortalCommunicationService-Instanz zurueckgeben."""
        service = get_portal_communication_service(mock_db)

        assert isinstance(service, PortalCommunicationService)
        assert service.db is mock_db


# ========================= Send Message Tests =========================


class TestSendMessage:
    """Tests fuer send_message() Methode."""

    @pytest.mark.asyncio
    async def test_send_message_success(
        self,
        communication_service: PortalCommunicationService,
        mock_db: AsyncMock,
        entity_id: UUID,
        company_id: UUID,
        portal_user_id: UUID,
    ):
        """Sollte Nachricht erfolgreich senden."""
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        message = await communication_service.send_message(
            entity_id=entity_id,
            company_id=company_id,
            portal_user_id=portal_user_id,
            subject="Frage zur Rechnung",
            content="Ich habe eine Frage zu meiner letzten Rechnung.",
        )

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_message_with_complaint_reference(
        self,
        communication_service: PortalCommunicationService,
        mock_db: AsyncMock,
        entity_id: UUID,
        company_id: UUID,
        portal_user_id: UUID,
    ):
        """Sollte Nachricht mit Reklamationsbezug senden."""
        complaint_id = uuid4()
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        await communication_service.send_message(
            entity_id=entity_id,
            company_id=company_id,
            portal_user_id=portal_user_id,
            subject="Nachfrage zur Reklamation",
            content="Wann wird meine Reklamation bearbeitet?",
            complaint_id=complaint_id,
        )

        mock_db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_message_with_attachments(
        self,
        communication_service: PortalCommunicationService,
        mock_db: AsyncMock,
        entity_id: UUID,
        company_id: UUID,
        portal_user_id: UUID,
    ):
        """Sollte Nachricht mit Anhaengen senden."""
        attachment_ids = [uuid4(), uuid4()]
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        await communication_service.send_message(
            entity_id=entity_id,
            company_id=company_id,
            portal_user_id=portal_user_id,
            subject="Dokumente anbei",
            content="Hier sind die angeforderten Dokumente.",
            attachment_ids=attachment_ids,
        )

        mock_db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_message_internal_user(
        self,
        communication_service: PortalCommunicationService,
        mock_db: AsyncMock,
        entity_id: UUID,
        company_id: UUID,
    ):
        """Sollte Nachricht von internem Benutzer senden (outbound)."""
        internal_user_id = uuid4()
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        await communication_service.send_message(
            entity_id=entity_id,
            company_id=company_id,
            internal_user_id=internal_user_id,
            subject="Antwort auf Ihre Anfrage",
            content="Vielen Dank fuer Ihre Nachricht. Hier sind die Details...",
        )

        mock_db.add.assert_called_once()


# ========================= Get Messages Tests =========================


class TestGetMessages:
    """Tests fuer get_messages() Methode."""

    @pytest.mark.asyncio
    async def test_get_messages_success(
        self,
        communication_service: PortalCommunicationService,
        mock_db: AsyncMock,
        entity_id: UUID,
        company_id: UUID,
        portal_user_id: UUID,
    ):
        """Sollte Nachrichten zurueckgeben."""
        messages = generate_messages(entity_id, company_id, portal_user_id, count=5)

        count_result = create_mock_result(scalar_value=5)
        list_result = create_mock_result(scalars_list=messages)
        mock_db.execute.side_effect = [count_result, list_result]

        result, total = await communication_service.get_messages(
            entity_id=entity_id,
            company_id=company_id,
        )

        assert total == 5
        assert len(result) == 5

    @pytest.mark.asyncio
    async def test_get_messages_filter_by_direction(
        self,
        communication_service: PortalCommunicationService,
        mock_db: AsyncMock,
        entity_id: UUID,
        company_id: UUID,
        portal_user_id: UUID,
    ):
        """Sollte nach Richtung filtern."""
        messages = generate_messages(entity_id, company_id, portal_user_id, count=3)
        for m in messages:
            m.direction = MessageDirection.INBOUND.value

        count_result = create_mock_result(scalar_value=3)
        list_result = create_mock_result(scalars_list=messages)
        mock_db.execute.side_effect = [count_result, list_result]

        result, total = await communication_service.get_messages(
            entity_id=entity_id,
            company_id=company_id,
            direction=MessageDirection.INBOUND,
        )

        assert total == 3
        for m in result:
            assert m.direction == MessageDirection.INBOUND.value

    @pytest.mark.asyncio
    async def test_get_messages_unread_only(
        self,
        communication_service: PortalCommunicationService,
        mock_db: AsyncMock,
        entity_id: UUID,
        company_id: UUID,
        portal_user_id: UUID,
    ):
        """Sollte nur ungelesene Nachrichten filtern."""
        messages = generate_messages(entity_id, company_id, portal_user_id, count=2)
        for m in messages:
            m.is_read = False

        count_result = create_mock_result(scalar_value=2)
        list_result = create_mock_result(scalars_list=messages)
        mock_db.execute.side_effect = [count_result, list_result]

        result, total = await communication_service.get_messages(
            entity_id=entity_id,
            company_id=company_id,
            unread_only=True,
        )

        assert total == 2
        for m in result:
            assert m.is_read is False

    @pytest.mark.asyncio
    async def test_get_messages_by_complaint(
        self,
        communication_service: PortalCommunicationService,
        mock_db: AsyncMock,
        entity_id: UUID,
        company_id: UUID,
        portal_user_id: UUID,
    ):
        """Sollte Nachrichten zu bestimmter Reklamation filtern."""
        complaint_id = uuid4()
        messages = generate_messages(entity_id, company_id, portal_user_id, count=2)
        for m in messages:
            m.complaint_id = complaint_id

        count_result = create_mock_result(scalar_value=2)
        list_result = create_mock_result(scalars_list=messages)
        mock_db.execute.side_effect = [count_result, list_result]

        result, total = await communication_service.get_messages(
            entity_id=entity_id,
            company_id=company_id,
            complaint_id=complaint_id,
        )

        assert total == 2

    @pytest.mark.asyncio
    async def test_get_messages_empty(
        self,
        communication_service: PortalCommunicationService,
        mock_db: AsyncMock,
        entity_id: UUID,
        company_id: UUID,
    ):
        """Sollte leere Liste bei keinen Nachrichten."""
        count_result = create_mock_result(scalar_value=0)
        list_result = create_mock_result(scalars_list=[])
        mock_db.execute.side_effect = [count_result, list_result]

        result, total = await communication_service.get_messages(
            entity_id=entity_id,
            company_id=company_id,
        )

        assert total == 0
        assert result == []


# ========================= Get Message Detail Tests =========================


class TestGetMessageDetail:
    """Tests fuer get_message_detail() Methode."""

    @pytest.mark.asyncio
    async def test_get_message_detail_success(
        self,
        communication_service: PortalCommunicationService,
        mock_db: AsyncMock,
        sample_message_inbound,
        entity_id: UUID,
        company_id: UUID,
    ):
        """Sollte Nachrichtendetails zurueckgeben."""
        mock_db.execute.return_value = create_mock_result(
            scalar_value=sample_message_inbound
        )

        result = await communication_service.get_message_detail(
            message_id=sample_message_inbound.id,
            entity_id=entity_id,
            company_id=company_id,
        )

        assert result is not None
        assert result.id == sample_message_inbound.id

    @pytest.mark.asyncio
    async def test_get_message_detail_not_found(
        self,
        communication_service: PortalCommunicationService,
        mock_db: AsyncMock,
        entity_id: UUID,
        company_id: UUID,
    ):
        """Sollte None zurueckgeben wenn nicht gefunden."""
        mock_db.execute.return_value = create_mock_result(scalar_value=None)

        result = await communication_service.get_message_detail(
            message_id=uuid4(),
            entity_id=entity_id,
            company_id=company_id,
        )

        assert result is None


# ========================= Mark Message Read Tests =========================


class TestMarkMessageRead:
    """Tests fuer mark_message_read() Methode."""

    @pytest.mark.asyncio
    async def test_mark_message_read_success(
        self,
        communication_service: PortalCommunicationService,
        mock_db: AsyncMock,
        sample_message_outbound,
        entity_id: UUID,
        company_id: UUID,
    ):
        """Sollte Nachricht als gelesen markieren."""
        sample_message_outbound.is_read = False
        sample_message_outbound.read_at = None
        mock_db.execute.return_value = create_mock_result(
            scalar_value=sample_message_outbound
        )
        mock_db.commit = AsyncMock()

        result = await communication_service.mark_message_read(
            message_id=sample_message_outbound.id,
            entity_id=entity_id,
            company_id=company_id,
        )

        assert result is not None
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_mark_message_read_already_read(
        self,
        communication_service: PortalCommunicationService,
        mock_db: AsyncMock,
        sample_message_inbound,
        entity_id: UUID,
        company_id: UUID,
    ):
        """Sollte keine Aenderung bei bereits gelesener Nachricht."""
        sample_message_inbound.is_read = True
        sample_message_inbound.read_at = datetime.now(timezone.utc)
        mock_db.execute.return_value = create_mock_result(
            scalar_value=sample_message_inbound
        )
        mock_db.commit = AsyncMock()

        result = await communication_service.mark_message_read(
            message_id=sample_message_inbound.id,
            entity_id=entity_id,
            company_id=company_id,
        )

        assert result is not None
        # Still committed but no actual change

    @pytest.mark.asyncio
    async def test_mark_message_read_not_found(
        self,
        communication_service: PortalCommunicationService,
        mock_db: AsyncMock,
        entity_id: UUID,
        company_id: UUID,
    ):
        """Sollte Fehler werfen wenn nicht gefunden."""
        mock_db.execute.return_value = create_mock_result(scalar_value=None)

        with pytest.raises(ValueError, match="nicht gefunden"):
            await communication_service.mark_message_read(
                message_id=uuid4(),
                entity_id=entity_id,
                company_id=company_id,
            )


# ========================= Get Unread Count Tests =========================


class TestGetUnreadCount:
    """Tests fuer get_unread_count() Methode."""

    @pytest.mark.asyncio
    async def test_get_unread_count_success(
        self,
        communication_service: PortalCommunicationService,
        mock_db: AsyncMock,
        entity_id: UUID,
        company_id: UUID,
    ):
        """Sollte Anzahl ungelesener Nachrichten zurueckgeben."""
        mock_db.execute.return_value = create_mock_result(scalar_value=3)

        count = await communication_service.get_unread_count(
            entity_id=entity_id,
            company_id=company_id,
        )

        assert count == 3

    @pytest.mark.asyncio
    async def test_get_unread_count_zero(
        self,
        communication_service: PortalCommunicationService,
        mock_db: AsyncMock,
        entity_id: UUID,
        company_id: UUID,
    ):
        """Sollte 0 bei keinen ungelesenen Nachrichten."""
        mock_db.execute.return_value = create_mock_result(scalar_value=0)

        count = await communication_service.get_unread_count(
            entity_id=entity_id,
            company_id=company_id,
        )

        assert count == 0


# ========================= Entity Isolation Tests =========================


class TestEntityIsolation:
    """Tests fuer Entity-Isolation bei Nachrichten."""

    @pytest.mark.asyncio
    async def test_cannot_see_other_entity_messages(
        self,
        communication_service: PortalCommunicationService,
        mock_db: AsyncMock,
        other_entity_id: UUID,
        company_id: UUID,
    ):
        """Entity A sollte keine Nachrichten von Entity B sehen."""
        count_result = create_mock_result(scalar_value=0)
        list_result = create_mock_result(scalars_list=[])
        mock_db.execute.side_effect = [count_result, list_result]

        result, total = await communication_service.get_messages(
            entity_id=other_entity_id,
            company_id=company_id,
        )

        assert total == 0
        assert result == []

    @pytest.mark.asyncio
    async def test_cannot_read_other_entity_message(
        self,
        communication_service: PortalCommunicationService,
        mock_db: AsyncMock,
        sample_message_inbound,
        other_entity_id: UUID,
        company_id: UUID,
    ):
        """Sollte Nachricht anderer Entity nicht lesen koennen."""
        # Query returns None for wrong entity
        mock_db.execute.return_value = create_mock_result(scalar_value=None)

        result = await communication_service.get_message_detail(
            message_id=sample_message_inbound.id,
            entity_id=other_entity_id,
            company_id=company_id,
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_unread_count_isolated_by_entity(
        self,
        communication_service: PortalCommunicationService,
        mock_db: AsyncMock,
        other_entity_id: UUID,
        company_id: UUID,
    ):
        """Unread-Count sollte Entity-isoliert sein."""
        mock_db.execute.return_value = create_mock_result(scalar_value=0)

        count = await communication_service.get_unread_count(
            entity_id=other_entity_id,
            company_id=company_id,
        )

        assert count == 0

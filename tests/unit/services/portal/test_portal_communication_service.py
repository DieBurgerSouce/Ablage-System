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
    """Tests fuer send_message() Methode.

    Vertrag des echten Services:
        send_message(portal_user, content, subject=None, complaint_id=None,
                     attachments=None) -> PortalMessage (immer INBOUND).
    Die company_id/entity_id/portal_user_id werden aus dem portal_user-Objekt
    abgeleitet, nicht als einzelne Argumente uebergeben.
    """

    @pytest.mark.asyncio
    async def test_send_message_success(
        self,
        communication_service: PortalCommunicationService,
        mock_db: AsyncMock,
        sample_portal_user,
    ):
        """Sollte Nachricht erfolgreich senden."""
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        await communication_service.send_message(
            portal_user=sample_portal_user,
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
        sample_portal_user,
    ):
        """Sollte Nachricht mit Reklamationsbezug senden."""
        complaint_id = uuid4()
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        await communication_service.send_message(
            portal_user=sample_portal_user,
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
        sample_portal_user,
    ):
        """Sollte Nachricht mit Anhaengen senden."""
        attachments = [str(uuid4()), str(uuid4())]
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        await communication_service.send_message(
            portal_user=sample_portal_user,
            subject="Dokumente anbei",
            content="Hier sind die angeforderten Dokumente.",
            attachments=attachments,
        )

        mock_db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_message_is_inbound(
        self,
        communication_service: PortalCommunicationService,
        mock_db: AsyncMock,
        sample_portal_user,
    ):
        """Eine vom Kunden gesendete Nachricht ist immer INBOUND."""
        added = {}
        mock_db.add = MagicMock(side_effect=lambda obj: added.setdefault("msg", obj))
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        await communication_service.send_message(
            portal_user=sample_portal_user,
            subject="Antwort auf Ihre Anfrage",
            content="Vielen Dank fuer Ihre Nachricht. Hier sind die Details...",
        )

        mock_db.add.assert_called_once()
        assert added["msg"].direction == MessageDirection.INBOUND.value
        assert added["msg"].portal_user_id == sample_portal_user.id


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
        # get_messages liefert eine Liste von Dicts (serialisierte Nachrichten)
        for m in result:
            assert m["direction"] == MessageDirection.INBOUND.value

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
        # get_messages liefert eine Liste von Dicts (serialisierte Nachrichten)
        for m in result:
            assert m["is_read"] is False

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


class TestGetConversation:
    """Tests fuer get_conversation() Methode.

    Der echte Service besitzt keinen get_message_detail-Einzelabruf; die
    chronologische Konversation wird ueber get_conversation geladen
    (entity-/company-isoliert, Rueckgabe als Liste von Dicts).
    """

    @pytest.mark.asyncio
    async def test_get_conversation_success(
        self,
        communication_service: PortalCommunicationService,
        mock_db: AsyncMock,
        sample_message_inbound,
        entity_id: UUID,
        company_id: UUID,
    ):
        """Sollte Konversation als Liste von Dicts zurueckgeben."""
        mock_db.execute.return_value = create_mock_result(
            scalars_list=[sample_message_inbound]
        )

        result = await communication_service.get_conversation(
            entity_id=entity_id,
            company_id=company_id,
        )

        assert len(result) == 1
        assert result[0]["id"] == str(sample_message_inbound.id)
        assert result[0]["direction"] == sample_message_inbound.direction

    @pytest.mark.asyncio
    async def test_get_conversation_empty(
        self,
        communication_service: PortalCommunicationService,
        mock_db: AsyncMock,
        entity_id: UUID,
        company_id: UUID,
    ):
        """Sollte leere Liste zurueckgeben wenn keine Nachrichten existieren."""
        mock_db.execute.return_value = create_mock_result(scalars_list=[])

        result = await communication_service.get_conversation(
            entity_id=entity_id,
            company_id=company_id,
        )

        assert result == []


# ========================= Mark Message Read Tests =========================


class TestMarkAsRead:
    """Tests fuer mark_as_read() Methode.

    Vertrag des echten Services:
        mark_as_read(message_id, entity_id, company_id) -> bool.
        Nur ausgehende (OUTBOUND) Nachrichten koennen als gelesen markiert
        werden. Nicht gefundene Nachrichten liefern False (kein Raise).
    """

    @pytest.mark.asyncio
    async def test_mark_as_read_success(
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

        result = await communication_service.mark_as_read(
            message_id=sample_message_outbound.id,
            entity_id=entity_id,
            company_id=company_id,
        )

        assert result is True
        assert sample_message_outbound.is_read is True
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_mark_as_read_already_read(
        self,
        communication_service: PortalCommunicationService,
        mock_db: AsyncMock,
        sample_message_outbound,
        entity_id: UUID,
        company_id: UUID,
    ):
        """Sollte True liefern aber nicht erneut committen wenn bereits gelesen."""
        sample_message_outbound.is_read = True
        sample_message_outbound.read_at = datetime.now(timezone.utc)
        mock_db.execute.return_value = create_mock_result(
            scalar_value=sample_message_outbound
        )
        mock_db.commit = AsyncMock()

        result = await communication_service.mark_as_read(
            message_id=sample_message_outbound.id,
            entity_id=entity_id,
            company_id=company_id,
        )

        assert result is True
        # Bereits gelesen -> kein erneuter Commit
        mock_db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_mark_as_read_not_found(
        self,
        communication_service: PortalCommunicationService,
        mock_db: AsyncMock,
        entity_id: UUID,
        company_id: UUID,
    ):
        """Sollte False liefern wenn Nachricht nicht gefunden."""
        mock_db.execute.return_value = create_mock_result(scalar_value=None)

        result = await communication_service.mark_as_read(
            message_id=uuid4(),
            entity_id=entity_id,
            company_id=company_id,
        )

        assert result is False


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
    async def test_cannot_mark_other_entity_message_read(
        self,
        communication_service: PortalCommunicationService,
        mock_db: AsyncMock,
        sample_message_outbound,
        other_entity_id: UUID,
        company_id: UUID,
    ):
        """Sollte Nachricht anderer Entity nicht als gelesen markieren koennen.

        Die entity-gefilterte Query liefert fuer die fremde Entity None ->
        mark_as_read gibt False zurueck (Isolation).
        """
        mock_db.execute.return_value = create_mock_result(scalar_value=None)

        result = await communication_service.mark_as_read(
            message_id=sample_message_outbound.id,
            entity_id=other_entity_id,
            company_id=company_id,
        )

        assert result is False

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

# -*- coding: utf-8 -*-
"""
Unit Tests fuer NotificationEscalationService.

Testet:
- Eskalationsketten-Erstellung
- Zeitbasierte Eskalation
- Eskalationsaufloesung
- Auto-Resolve nach Timeout
- Preset-Chains (standard, urgent, approval)
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.notification.escalation_chain_service import (
    NotificationEscalationService,
    EscalationLevel,
    EscalationChain,
    EscalationStatus,
    EscalationChannel,
    PRESET_CHAINS,
)


class TestEscalationLevel:
    """Tests fuer EscalationLevel Dataclass."""

    def test_valid_level(self) -> None:
        """Valides Level sollte funktionieren."""
        level = EscalationLevel(
            level=1,
            channel=EscalationChannel.EMAIL.value,
            delay_minutes=60,
            recipients=["user"],
        )

        assert level.level == 1
        assert level.channel == EscalationChannel.EMAIL.value
        assert level.delay_minutes == 60
        assert level.recipients == ["user"]

    def test_invalid_level_negative(self) -> None:
        """Negatives Level sollte ValueError werfen."""
        with pytest.raises(ValueError, match="Level muss >= 1 sein"):
            EscalationLevel(
                level=0,
                channel=EscalationChannel.EMAIL.value,
                delay_minutes=60,
                recipients=["user"],
            )

    def test_invalid_delay_negative(self) -> None:
        """Negativer Delay sollte ValueError werfen."""
        with pytest.raises(ValueError, match="Delay muss >= 0 sein"):
            EscalationLevel(
                level=1,
                channel=EscalationChannel.EMAIL.value,
                delay_minutes=-10,
                recipients=["user"],
            )


class TestEscalationChain:
    """Tests fuer EscalationChain Dataclass."""

    def test_valid_chain(self) -> None:
        """Valide Chain sollte funktionieren."""
        chain = EscalationChain(
            id="test",
            name="Test Chain",
            description="Test",
            levels=[
                EscalationLevel(
                    level=1,
                    channel=EscalationChannel.IN_APP.value,
                    delay_minutes=0,
                    recipients=["user"],
                ),
                EscalationLevel(
                    level=2,
                    channel=EscalationChannel.EMAIL.value,
                    delay_minutes=60,
                    recipients=["user"],
                ),
            ],
            max_escalation_level=2,
        )

        assert chain.id == "test"
        assert len(chain.levels) == 2
        assert chain.max_escalation_level == 2

    def test_empty_levels(self) -> None:
        """Leere Levels sollte ValueError werfen."""
        with pytest.raises(ValueError, match="mindestens ein Level haben"):
            EscalationChain(
                id="test",
                name="Test",
                description="Test",
                levels=[],
                max_escalation_level=1,
            )

    def test_max_level_exceeds_levels(self) -> None:
        """max_escalation_level > len(levels) sollte ValueError werfen."""
        with pytest.raises(ValueError, match="max_escalation_level > Anzahl Levels"):
            EscalationChain(
                id="test",
                name="Test",
                description="Test",
                levels=[
                    EscalationLevel(
                        level=1,
                        channel=EscalationChannel.IN_APP.value,
                        delay_minutes=0,
                        recipients=["user"],
                    ),
                ],
                max_escalation_level=3,
            )


class TestPresetChains:
    """Tests fuer vordefinierte Chains."""

    def test_standard_chain_exists(self) -> None:
        """Standard-Chain sollte existieren."""
        assert "standard" in PRESET_CHAINS
        chain = PRESET_CHAINS["standard"]
        assert chain.id == "standard"
        assert chain.max_escalation_level == 3
        assert len(chain.levels) >= 3

    def test_urgent_chain_exists(self) -> None:
        """Urgent-Chain sollte existieren."""
        assert "urgent" in PRESET_CHAINS
        chain = PRESET_CHAINS["urgent"]
        assert chain.id == "urgent"
        assert chain.max_escalation_level == 3

    def test_approval_chain_exists(self) -> None:
        """Approval-Chain sollte existieren."""
        assert "approval" in PRESET_CHAINS
        chain = PRESET_CHAINS["approval"]
        assert chain.id == "approval"
        assert chain.max_escalation_level == 3


@pytest.mark.asyncio
class TestNotificationEscalationService:
    """Tests fuer NotificationEscalationService."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Mock AsyncSession."""
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_db: AsyncMock) -> NotificationEscalationService:
        """Service-Instanz."""
        return NotificationEscalationService(mock_db)

    async def test_create_escalation_standard(
        self,
        service: NotificationEscalationService,
    ) -> None:
        """Standard-Eskalation sollte erstellt werden."""
        notification_id = uuid.uuid4()
        user_id = uuid.uuid4()

        escalation_id = await service.create_escalation(
            notification_id=notification_id,
            chain_name="standard",
            user_id=user_id,
        )

        assert escalation_id is not None
        assert len(service._active_escalations) == 1

        state = service._active_escalations[escalation_id]
        assert state.notification_id == str(notification_id)
        assert state.user_id == str(user_id)
        assert state.chain_id == "standard"
        assert state.current_level == 1
        assert state.status == EscalationStatus.PENDING
        assert state.next_escalation_at is not None

    async def test_create_escalation_urgent(
        self,
        service: NotificationEscalationService,
    ) -> None:
        """Urgent-Eskalation sollte erstellt werden."""
        notification_id = uuid.uuid4()
        user_id = uuid.uuid4()

        escalation_id = await service.create_escalation(
            notification_id=notification_id,
            chain_name="urgent",
            user_id=user_id,
        )

        assert escalation_id is not None
        state = service._active_escalations[escalation_id]
        assert state.chain_id == "urgent"

    async def test_create_escalation_invalid_chain(
        self,
        service: NotificationEscalationService,
    ) -> None:
        """Unbekannte Chain sollte ValueError werfen."""
        notification_id = uuid.uuid4()
        user_id = uuid.uuid4()

        with pytest.raises(ValueError, match="Unbekannte Eskalationskette"):
            await service.create_escalation(
                notification_id=notification_id,
                chain_name="nonexistent",
                user_id=user_id,
            )

    async def test_resolve_escalation(
        self,
        service: NotificationEscalationService,
    ) -> None:
        """Eskalation sollte aufgeloest werden."""
        notification_id = uuid.uuid4()
        user_id = uuid.uuid4()

        escalation_id = await service.create_escalation(
            notification_id=notification_id,
            chain_name="standard",
            user_id=user_id,
        )

        # Resolve
        resolved = await service.resolve_escalation(notification_id)

        assert resolved is True
        assert escalation_id not in service._active_escalations

    async def test_resolve_nonexistent_escalation(
        self,
        service: NotificationEscalationService,
    ) -> None:
        """Resolve fuer nicht-existierende Eskalation sollte False liefern."""
        notification_id = uuid.uuid4()

        resolved = await service.resolve_escalation(notification_id)

        assert resolved is False

    async def test_get_active_escalations_for_user(
        self,
        service: NotificationEscalationService,
    ) -> None:
        """Aktive Eskalationen fuer User sollten zurueckgegeben werden."""
        user_id = uuid.uuid4()
        other_user_id = uuid.uuid4()

        # Erstelle 2 Eskalationen fuer user_id
        await service.create_escalation(
            notification_id=uuid.uuid4(),
            chain_name="standard",
            user_id=user_id,
        )
        await service.create_escalation(
            notification_id=uuid.uuid4(),
            chain_name="urgent",
            user_id=user_id,
        )

        # Erstelle 1 Eskalation fuer other_user_id
        await service.create_escalation(
            notification_id=uuid.uuid4(),
            chain_name="standard",
            user_id=other_user_id,
        )

        # Get active escalations
        escalations = await service.get_active_escalations(user_id)

        assert len(escalations) == 2
        assert all(e["status"] in ["pending", "in_progress"] for e in escalations)

    async def test_check_escalations_no_pending(
        self,
        service: NotificationEscalationService,
    ) -> None:
        """check_escalations sollte [] liefern wenn nichts faellig."""
        notification_id = uuid.uuid4()
        user_id = uuid.uuid4()

        await service.create_escalation(
            notification_id=notification_id,
            chain_name="standard",
            user_id=user_id,
        )

        # Check (sofort nach Erstellung - nichts faellig)
        escalated = await service.check_escalations()

        assert len(escalated) == 0

    async def test_check_escalations_with_pending(
        self,
        service: NotificationEscalationService,
    ) -> None:
        """check_escalations sollte eskalieren wenn faellig."""
        notification_id = uuid.uuid4()
        user_id = uuid.uuid4()

        escalation_id = await service.create_escalation(
            notification_id=notification_id,
            chain_name="standard",
            user_id=user_id,
        )

        # Manipuliere next_escalation_at (faellig machen)
        state = service._active_escalations[escalation_id]
        state.next_escalation_at = datetime.now(timezone.utc) - timedelta(minutes=1)

        # Check
        escalated = await service.check_escalations()

        assert len(escalated) == 1
        assert escalated[0]["notification_id"] == str(notification_id)
        assert escalated[0]["level"] == 2  # Eskaliert zu Level 2

        # State sollte aktualisiert sein
        updated_state = service._active_escalations[escalation_id]
        assert updated_state.current_level == 2
        assert updated_state.status == EscalationStatus.IN_PROGRESS

    async def test_auto_resolve_after_timeout(
        self,
        service: NotificationEscalationService,
    ) -> None:
        """Eskalation sollte nach Timeout auto-resolved werden."""
        notification_id = uuid.uuid4()
        user_id = uuid.uuid4()

        escalation_id = await service.create_escalation(
            notification_id=notification_id,
            chain_name="standard",
            user_id=user_id,
        )

        # Manipuliere created_at (alt machen)
        state = service._active_escalations[escalation_id]
        state.created_at = datetime.now(timezone.utc) - timedelta(hours=25)

        # Check (sollte auto-resolve triggern)
        escalated = await service.check_escalations()

        assert len(escalated) == 0
        assert escalation_id not in service._active_escalations

    async def test_escalate_to_max_level(
        self,
        service: NotificationEscalationService,
    ) -> None:
        """Eskalation zu max_level sollte auto-resolve."""
        notification_id = uuid.uuid4()
        user_id = uuid.uuid4()

        escalation_id = await service.create_escalation(
            notification_id=notification_id,
            chain_name="standard",
            user_id=user_id,
        )

        # Manipuliere State zu Level 3 (max)
        state = service._active_escalations[escalation_id]
        state.current_level = 3
        state.next_escalation_at = datetime.now(timezone.utc) - timedelta(minutes=1)

        # Check (sollte nicht weiter eskalieren)
        escalated = await service.check_escalations()

        # Keine Eskalation (bereits max level)
        assert len(escalated) == 0
        assert escalation_id not in service._active_escalations

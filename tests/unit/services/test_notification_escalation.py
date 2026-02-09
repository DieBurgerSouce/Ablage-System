"""
Unit tests für NotificationEscalationService und NotificationDeduplicationService.

Testet Eskalationsketten und Notification-Deduplizierung.
"""
import pytest
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from unittest.mock import AsyncMock, MagicMock, patch
from decimal import Decimal

from app.services.notification.escalation_chain_service import (
    NotificationEscalationService,
    EscalationChain,
    EscalationLevel,
    EscalationPreset
)
from app.services.notification.dedup_service import (
    NotificationDeduplicationService,
    DedupWindow
)


class TestNotificationEscalationService:
    """Tests für NotificationEscalationService."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Mock AsyncSession."""
        db = AsyncMock()
        db.execute = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        return db

    @pytest.fixture
    def service(self, mock_db: AsyncMock) -> NotificationEscalationService:
        """NotificationEscalationService Instanz."""
        return NotificationEscalationService(db=mock_db)

    @pytest.fixture
    def user_id(self) -> str:
        """Test User ID."""
        return "user-123"

    @pytest.fixture
    def notification_id(self) -> str:
        """Test Notification ID."""
        return "notif-456"

    # -------------------------------------------------------------------------
    # Create Escalation Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_create_escalation_from_standard_preset(
        self,
        service: NotificationEscalationService,
        user_id: str,
        notification_id: str
    ) -> None:
        """Eskalation aus Standard-Preset erstellen."""
        # Act
        result = await service.create_escalation(
            notification_id=notification_id,
            user_id=user_id,
            preset=EscalationPreset.STANDARD
        )

        # Assert
        assert result is not None
        assert result.notification_id == notification_id
        assert result.user_id == user_id
        assert len(result.levels) == 3  # InApp -> Email -> Slack
        assert result.levels[0].channel == "InApp"
        assert result.levels[1].channel == "Email"
        assert result.levels[2].channel == "Slack"

    @pytest.mark.asyncio
    async def test_create_escalation_from_urgent_preset(
        self,
        service: NotificationEscalationService,
        user_id: str,
        notification_id: str
    ) -> None:
        """Eskalation aus Urgent-Preset mit schnelleren Delays."""
        # Act
        result = await service.create_escalation(
            notification_id=notification_id,
            user_id=user_id,
            preset=EscalationPreset.URGENT
        )

        # Assert
        assert result is not None
        assert len(result.levels) >= 3
        # Urgent hat kürzere Delays
        assert result.levels[0].delay_minutes < 60
        assert result.levels[1].delay_minutes < 180

    @pytest.mark.asyncio
    async def test_create_escalation_with_custom_levels(
        self,
        service: NotificationEscalationService,
        user_id: str,
        notification_id: str
    ) -> None:
        """Eskalation mit custom Levels."""
        # Arrange
        custom_levels = [
            EscalationLevel(
                level=1,
                channel="InApp",
                delay_minutes=30
            ),
            EscalationLevel(
                level=2,
                channel="Email",
                delay_minutes=120
            )
        ]

        # Act
        result = await service.create_escalation(
            notification_id=notification_id,
            user_id=user_id,
            levels=custom_levels
        )

        # Assert
        assert result is not None
        assert len(result.levels) == 2
        assert result.levels[0].delay_minutes == 30
        assert result.levels[1].delay_minutes == 120

    # -------------------------------------------------------------------------
    # Check Escalations Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_check_escalations_finds_overdue(
        self,
        service: NotificationEscalationService,
        mock_db: AsyncMock
    ) -> None:
        """check_escalations findet überfällige Eskalationen."""
        # Arrange
        now = datetime.utcnow()
        overdue_time = now - timedelta(minutes=120)

        mock_escalation = MagicMock()
        mock_escalation.id = "esc-1"
        mock_escalation.notification_id = "notif-1"
        mock_escalation.user_id = "user-1"
        mock_escalation.current_level = 0
        mock_escalation.created_at = overdue_time
        mock_escalation.levels = [
            EscalationLevel(level=1, channel="InApp", delay_minutes=60),
            EscalationLevel(level=2, channel="Email", delay_minutes=180)
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_escalation]
        mock_db.execute.return_value = mock_result

        # Act
        result = await service.check_escalations()

        # Assert
        assert len(result) > 0
        assert result[0].id == "esc-1"

    @pytest.mark.asyncio
    async def test_check_escalations_skips_not_overdue(
        self,
        service: NotificationEscalationService,
        mock_db: AsyncMock
    ) -> None:
        """check_escalations überspringt nicht überfällige Eskalationen."""
        # Arrange
        now = datetime.utcnow()
        recent_time = now - timedelta(minutes=30)

        mock_escalation = MagicMock()
        mock_escalation.id = "esc-1"
        mock_escalation.current_level = 0
        mock_escalation.created_at = recent_time
        mock_escalation.levels = [
            EscalationLevel(level=1, channel="InApp", delay_minutes=60)
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_escalation]
        mock_db.execute.return_value = mock_result

        # Act
        result = await service.check_escalations()

        # Assert
        # Sollte leer sein, da nicht überfällig
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_check_escalations_processes_next_level(
        self,
        service: NotificationEscalationService,
        mock_db: AsyncMock
    ) -> None:
        """check_escalations verarbeitet nächstes Level."""
        # Arrange
        now = datetime.utcnow()
        overdue_time = now - timedelta(minutes=200)

        mock_escalation = MagicMock()
        mock_escalation.id = "esc-1"
        mock_escalation.notification_id = "notif-1"
        mock_escalation.user_id = "user-1"
        mock_escalation.current_level = 0
        mock_escalation.created_at = overdue_time
        mock_escalation.levels = [
            EscalationLevel(level=1, channel="InApp", delay_minutes=60),
            EscalationLevel(level=2, channel="Email", delay_minutes=180)
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_escalation]
        mock_db.execute.return_value = mock_result

        # Act
        with patch.object(service, "_send_notification", new_callable=AsyncMock) as mock_send:
            await service.check_escalations()

            # Assert
            mock_send.assert_called()
            # current_level sollte erhöht worden sein
            assert mock_escalation.current_level == 1

    # -------------------------------------------------------------------------
    # Resolve Escalation Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_resolve_escalation_stops_chain(
        self,
        service: NotificationEscalationService,
        notification_id: str,
        mock_db: AsyncMock
    ) -> None:
        """resolve_escalation stoppt Eskalationskette."""
        # Arrange
        mock_escalation = MagicMock()
        mock_escalation.id = "esc-1"
        mock_escalation.notification_id = notification_id
        mock_escalation.resolved_at = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_escalation
        mock_db.execute.return_value = mock_result

        # Act
        await service.resolve_escalation(notification_id=notification_id)

        # Assert
        assert mock_escalation.resolved_at is not None
        mock_db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_resolve_escalation_nonexistent(
        self,
        service: NotificationEscalationService,
        mock_db: AsyncMock
    ) -> None:
        """resolve_escalation für nicht existierende Eskalation."""
        # Arrange
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        # Act & Assert (sollte nicht crashen)
        await service.resolve_escalation(notification_id="nonexistent")

    # -------------------------------------------------------------------------
    # Auto Resolve Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_auto_resolve_after_hours(
        self,
        service: NotificationEscalationService,
        mock_db: AsyncMock
    ) -> None:
        """Eskalationen werden nach auto_resolve_after_hours aufgelöst."""
        # Arrange
        now = datetime.utcnow()
        old_time = now - timedelta(hours=25)

        mock_escalation = MagicMock()
        mock_escalation.id = "esc-1"
        mock_escalation.created_at = old_time
        mock_escalation.resolved_at = None
        mock_escalation.auto_resolve_after_hours = 24

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_escalation]
        mock_db.execute.return_value = mock_result

        # Act
        await service.auto_resolve_old_escalations()

        # Assert
        assert mock_escalation.resolved_at is not None

    # -------------------------------------------------------------------------
    # Get Active Escalations Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_get_active_escalations_for_user(
        self,
        service: NotificationEscalationService,
        user_id: str,
        mock_db: AsyncMock
    ) -> None:
        """get_active_escalations für User."""
        # Arrange
        mock_escalation1 = MagicMock()
        mock_escalation1.id = "esc-1"
        mock_escalation1.resolved_at = None

        mock_escalation2 = MagicMock()
        mock_escalation2.id = "esc-2"
        mock_escalation2.resolved_at = None

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [
            mock_escalation1,
            mock_escalation2
        ]
        mock_db.execute.return_value = mock_result

        # Act
        result = await service.get_active_escalations(user_id=user_id)

        # Assert
        assert len(result) == 2
        assert result[0].id == "esc-1"

    @pytest.mark.asyncio
    async def test_get_active_escalations_excludes_resolved(
        self,
        service: NotificationEscalationService,
        user_id: str,
        mock_db: AsyncMock
    ) -> None:
        """get_active_escalations schließt resolved aus."""
        # Arrange
        mock_escalation1 = MagicMock()
        mock_escalation1.id = "esc-1"
        mock_escalation1.resolved_at = None

        mock_escalation2 = MagicMock()
        mock_escalation2.id = "esc-2"
        mock_escalation2.resolved_at = datetime.utcnow()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_escalation1]
        mock_db.execute.return_value = mock_result

        # Act
        result = await service.get_active_escalations(user_id=user_id)

        # Assert
        assert len(result) == 1
        assert result[0].id == "esc-1"


class TestNotificationDeduplicationService:
    """Tests für NotificationDeduplicationService."""

    @pytest.fixture
    def service(self) -> NotificationDeduplicationService:
        """NotificationDeduplicationService Instanz."""
        return NotificationDeduplicationService()

    @pytest.fixture
    def user_id(self) -> str:
        """Test User ID."""
        return "user-123"

    # -------------------------------------------------------------------------
    # is_duplicate Tests
    # -------------------------------------------------------------------------

    def test_is_duplicate_returns_false_for_new_notification(
        self,
        service: NotificationDeduplicationService,
        user_id: str
    ) -> None:
        """is_duplicate gibt False für neue Notification zurück."""
        # Act
        result = service.is_duplicate(
            user_id=user_id,
            notification_type="document_processed",
            entity_id="doc-123"
        )

        # Assert
        assert result is False

    def test_is_duplicate_returns_true_for_recent_duplicate(
        self,
        service: NotificationDeduplicationService,
        user_id: str
    ) -> None:
        """is_duplicate gibt True für recent duplicate zurück."""
        # Arrange
        notification_type = "document_processed"
        entity_id = "doc-123"

        # Erster Aufruf registriert die Notification
        service.is_duplicate(user_id, notification_type, entity_id)

        # Act
        # Zweiter Aufruf sollte duplicate sein
        result = service.is_duplicate(user_id, notification_type, entity_id)

        # Assert
        assert result is True

    def test_is_duplicate_different_types_not_duplicate(
        self,
        service: NotificationDeduplicationService,
        user_id: str
    ) -> None:
        """Verschiedene notification_types sind nicht duplicate."""
        # Arrange
        entity_id = "doc-123"
        service.is_duplicate(user_id, "document_processed", entity_id)

        # Act
        result = service.is_duplicate(user_id, "document_failed", entity_id)

        # Assert
        assert result is False

    def test_is_duplicate_different_entities_not_duplicate(
        self,
        service: NotificationDeduplicationService,
        user_id: str
    ) -> None:
        """Verschiedene entity_ids sind nicht duplicate."""
        # Arrange
        notification_type = "document_processed"
        service.is_duplicate(user_id, notification_type, "doc-123")

        # Act
        result = service.is_duplicate(user_id, notification_type, "doc-456")

        # Assert
        assert result is False

    def test_is_duplicate_different_users_not_duplicate(
        self,
        service: NotificationDeduplicationService
    ) -> None:
        """Verschiedene user_ids sind nicht duplicate."""
        # Arrange
        notification_type = "document_processed"
        entity_id = "doc-123"
        service.is_duplicate("user-123", notification_type, entity_id)

        # Act
        result = service.is_duplicate("user-456", notification_type, entity_id)

        # Assert
        assert result is False

    # -------------------------------------------------------------------------
    # Dedup Window Tests
    # -------------------------------------------------------------------------

    def test_dedup_window_expiration(
        self,
        service: NotificationDeduplicationService,
        user_id: str
    ) -> None:
        """Dedup window expiration."""
        # Arrange
        notification_type = "document_processed"
        entity_id = "doc-123"
        window_seconds = 1

        # Custom window für Test
        service._dedup_window = DedupWindow(seconds=window_seconds)

        # Erster Aufruf
        service.is_duplicate(user_id, notification_type, entity_id)

        # Act
        import time
        time.sleep(window_seconds + 0.5)

        # Nach window sollte es nicht mehr duplicate sein
        result = service.is_duplicate(user_id, notification_type, entity_id)

        # Assert
        assert result is False

    def test_dedup_within_window(
        self,
        service: NotificationDeduplicationService,
        user_id: str
    ) -> None:
        """Duplicate innerhalb des Windows."""
        # Arrange
        notification_type = "document_processed"
        entity_id = "doc-123"

        # Erster Aufruf
        service.is_duplicate(user_id, notification_type, entity_id)

        # Act
        import time
        time.sleep(0.1)  # Kurze Wartezeit, aber innerhalb window

        result = service.is_duplicate(user_id, notification_type, entity_id)

        # Assert
        assert result is True

    # -------------------------------------------------------------------------
    # Clear User Dedup Tests
    # -------------------------------------------------------------------------

    def test_clear_user_dedup(
        self,
        service: NotificationDeduplicationService,
        user_id: str
    ) -> None:
        """clear_user_dedup entfernt User-spezifische Einträge."""
        # Arrange
        service.is_duplicate(user_id, "type1", "entity1")
        service.is_duplicate(user_id, "type2", "entity2")
        service.is_duplicate("other-user", "type1", "entity1")

        # Act
        service.clear_user_dedup(user_id)

        # Assert
        # User entries sollten weg sein
        assert service.is_duplicate(user_id, "type1", "entity1") is False
        assert service.is_duplicate(user_id, "type2", "entity2") is False
        # Other user sollte noch da sein
        assert service.is_duplicate("other-user", "type1", "entity1") is True

    # -------------------------------------------------------------------------
    # Cleanup Expired Tests
    # -------------------------------------------------------------------------

    def test_cleanup_expired_removes_old_entries(
        self,
        service: NotificationDeduplicationService,
        user_id: str
    ) -> None:
        """cleanup_expired entfernt alte Einträge."""
        # Arrange
        window_seconds = 1
        service._dedup_window = DedupWindow(seconds=window_seconds)

        service.is_duplicate(user_id, "type1", "entity1")

        # Act
        import time
        time.sleep(window_seconds + 0.5)
        service.cleanup_expired()

        # Assert
        # Nach cleanup sollte entry weg sein
        assert service.is_duplicate(user_id, "type1", "entity1") is False

    def test_cleanup_expired_keeps_recent_entries(
        self,
        service: NotificationDeduplicationService,
        user_id: str
    ) -> None:
        """cleanup_expired behält recent entries."""
        # Arrange
        service.is_duplicate(user_id, "type1", "entity1")

        # Act
        import time
        time.sleep(0.1)  # Kurze Wartezeit
        service.cleanup_expired()

        # Assert
        # Recent entry sollte noch da sein
        assert service.is_duplicate(user_id, "type1", "entity1") is True

    # -------------------------------------------------------------------------
    # Edge Cases
    # -------------------------------------------------------------------------

    def test_multiple_notifications_same_type_different_entities(
        self,
        service: NotificationDeduplicationService,
        user_id: str
    ) -> None:
        """Multiple Notifications mit gleichem Type aber verschiedenen Entities."""
        # Arrange
        notification_type = "document_processed"
        entities = ["doc-1", "doc-2", "doc-3", "doc-4", "doc-5"]

        # Act
        for entity_id in entities:
            result = service.is_duplicate(user_id, notification_type, entity_id)
            # Assert
            assert result is False  # Jeweils neue Entity

        # Zweiter Durchgang sollte duplicates sein
        for entity_id in entities:
            result = service.is_duplicate(user_id, notification_type, entity_id)
            # Assert
            assert result is True

    def test_same_entity_different_types(
        self,
        service: NotificationDeduplicationService,
        user_id: str
    ) -> None:
        """Gleiche Entity mit verschiedenen Types."""
        # Arrange
        entity_id = "doc-123"
        types = ["processed", "failed", "archived", "deleted"]

        # Act & Assert
        for notification_type in types:
            result = service.is_duplicate(user_id, notification_type, entity_id)
            assert result is False  # Verschiedene Types

    def test_empty_entity_id(
        self,
        service: NotificationDeduplicationService,
        user_id: str
    ) -> None:
        """Leere entity_id."""
        # Act
        result1 = service.is_duplicate(user_id, "type1", "")
        result2 = service.is_duplicate(user_id, "type1", "")

        # Assert
        assert result1 is False
        assert result2 is True

    def test_none_entity_id(
        self,
        service: NotificationDeduplicationService,
        user_id: str
    ) -> None:
        """None als entity_id."""
        # Act
        result1 = service.is_duplicate(user_id, "type1", None)
        result2 = service.is_duplicate(user_id, "type1", None)

        # Assert
        assert result1 is False
        assert result2 is True


class TestEscalationChain:
    """Tests für EscalationChain Dataclass."""

    def test_escalation_chain_initialization(self) -> None:
        """EscalationChain korrekt initialisiert."""
        levels = [
            EscalationLevel(level=1, channel="InApp", delay_minutes=60),
            EscalationLevel(level=2, channel="Email", delay_minutes=180)
        ]

        chain = EscalationChain(
            id="esc-1",
            notification_id="notif-1",
            user_id="user-1",
            levels=levels,
            current_level=0,
            created_at=datetime.utcnow()
        )

        assert chain.id == "esc-1"
        assert len(chain.levels) == 2
        assert chain.current_level == 0


class TestEscalationLevel:
    """Tests für EscalationLevel Dataclass."""

    def test_escalation_level_initialization(self) -> None:
        """EscalationLevel korrekt initialisiert."""
        level = EscalationLevel(
            level=1,
            channel="Email",
            delay_minutes=120
        )

        assert level.level == 1
        assert level.channel == "Email"
        assert level.delay_minutes == 120

    def test_escalation_level_ordering(self) -> None:
        """EscalationLevel Ordering."""
        level1 = EscalationLevel(level=1, channel="InApp", delay_minutes=60)
        level2 = EscalationLevel(level=2, channel="Email", delay_minutes=120)
        level3 = EscalationLevel(level=3, channel="Slack", delay_minutes=240)

        levels = [level2, level3, level1]
        sorted_levels = sorted(levels, key=lambda x: x.level)

        assert sorted_levels[0].level == 1
        assert sorted_levels[1].level == 2
        assert sorted_levels[2].level == 3


class TestEscalationPreset:
    """Tests für EscalationPreset Enum."""

    def test_escalation_preset_values(self) -> None:
        """EscalationPreset hat erwartete Werte."""
        assert EscalationPreset.STANDARD
        assert EscalationPreset.URGENT
        assert EscalationPreset.RELAXED

    def test_escalation_preset_string_representation(self) -> None:
        """EscalationPreset String-Repräsentation."""
        assert "STANDARD" in str(EscalationPreset.STANDARD).upper()
        assert "URGENT" in str(EscalationPreset.URGENT).upper()

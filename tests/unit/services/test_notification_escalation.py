# -*- coding: utf-8 -*-
"""
Unit-Tests für NotificationEscalationService und NotificationDeduplicationService.

Testet die echten Verträge der Services:
- Eskalationsketten (In-Memory State, Preset-Chains, zeitbasierte Stufen)
- Notification-Deduplizierung (is_duplicate prüft, mark_sent registriert)

Hinweis zur API-Realität (Stand: app/services/notification/):
- ``EscalationLevel`` benötigt ``recipients`` (Pflichtfeld) und validiert ``level``/``delay_minutes``.
- ``EscalationChain`` ist eine *Preset-Definition* (id/name/description/levels/
  max_escalation_level/auto_resolve_after_hours), KEIN Laufzeit-Zustand.
- ``create_escalation(notification_id, chain_name, user_id)`` gibt eine
  Eskalations-ID (str) zurück und arbeitet rein In-Memory (kein DB-Persist).
- ``is_duplicate`` ist async und PRÜFT nur; das Registrieren erfolgt via ``mark_sent``.
"""
import uuid

import pytest

from app.services.notification.escalation_chain_service import (
    NotificationEscalationService,
    EscalationChain,
    EscalationLevel,
    EscalationPreset,
    EscalationChannel,
    EscalationStatus,
    EscalationState,
    PRESET_CHAINS,
)
from app.services.notification.dedup_service import (
    NotificationDeduplicationService,
    DedupWindow,
)


class TestNotificationEscalationService:
    """Tests für NotificationEscalationService (In-Memory Eskalationsverwaltung)."""

    @pytest.fixture
    def service(self) -> NotificationEscalationService:
        """NotificationEscalationService Instanz (DB wird nicht persistierend genutzt)."""
        # Der Service speichert Eskalationen In-Memory; db wird im Konstruktor
        # nur referenziert, nicht für create/check/resolve verwendet.
        return NotificationEscalationService(db=object())

    @pytest.fixture
    def user_id(self) -> uuid.UUID:
        """Test User ID."""
        return uuid.uuid4()

    @pytest.fixture
    def notification_id(self) -> uuid.UUID:
        """Test Notification ID."""
        return uuid.uuid4()

    # -------------------------------------------------------------------------
    # Create Escalation Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_create_escalation_from_standard_chain(
        self,
        service: NotificationEscalationService,
        user_id: uuid.UUID,
        notification_id: uuid.UUID,
    ) -> None:
        """Eskalation aus Standard-Chain erstellen und State initialisieren."""
        escalation_id = await service.create_escalation(
            notification_id=notification_id,
            chain_name="standard",
            user_id=user_id,
        )

        # Rückgabe ist eine String-UUID
        assert isinstance(escalation_id, str)
        uuid.UUID(escalation_id)  # gültige UUID, sonst ValueError

        # State wurde In-Memory angelegt
        state = service._active_escalations[escalation_id]
        assert isinstance(state, EscalationState)
        assert state.notification_id == str(notification_id)
        assert state.user_id == str(user_id)
        assert state.chain_id == "standard"
        # Level 1 wird sofort gesendet -> current_level startet bei 1
        assert state.current_level == 1
        assert state.status == EscalationStatus.PENDING
        # Standard hat mehrere Levels -> nächste Eskalation ist geplant
        assert state.next_escalation_at is not None

    @pytest.mark.asyncio
    async def test_create_escalation_from_urgent_chain(
        self,
        service: NotificationEscalationService,
        user_id: uuid.UUID,
        notification_id: uuid.UUID,
    ) -> None:
        """Urgent-Chain eskaliert schneller als Standard (kürzeres auto_resolve)."""
        escalation_id = await service.create_escalation(
            notification_id=notification_id,
            chain_name="urgent",
            user_id=user_id,
        )

        state = service._active_escalations[escalation_id]
        assert state.chain_id == "urgent"

        # Urgent-Chain hat ein kürzeres auto_resolve_after_hours als Standard.
        urgent_chain = PRESET_CHAINS["urgent"]
        standard_chain = PRESET_CHAINS["standard"]
        assert urgent_chain.auto_resolve_after_hours < standard_chain.auto_resolve_after_hours

    @pytest.mark.asyncio
    async def test_create_escalation_unknown_chain_raises(
        self,
        service: NotificationEscalationService,
        user_id: uuid.UUID,
        notification_id: uuid.UUID,
    ) -> None:
        """Unbekannte Chain führt zu ValueError."""
        with pytest.raises(ValueError, match="Unbekannte Eskalationskette"):
            await service.create_escalation(
                notification_id=notification_id,
                chain_name="does_not_exist",
                user_id=user_id,
            )

    # -------------------------------------------------------------------------
    # Check Escalations Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_check_escalations_escalates_overdue(
        self,
        service: NotificationEscalationService,
        user_id: uuid.UUID,
        notification_id: uuid.UUID,
    ) -> None:
        """check_escalations eskaliert eine überfällige Eskalation zur nächsten Stufe."""
        escalation_id = await service.create_escalation(
            notification_id=notification_id,
            chain_name="standard",
            user_id=user_id,
        )

        # Nächste Eskalation in die Vergangenheit setzen -> fällig
        state = service._active_escalations[escalation_id]
        from datetime import datetime, timedelta, timezone
        state.next_escalation_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        level_before = state.current_level

        escalated = await service.check_escalations()

        # Es wurde mindestens eine Stufe eskaliert
        assert len(escalated) >= 1
        entry = escalated[0]
        assert entry["escalation_id"] == escalation_id
        assert entry["notification_id"] == str(notification_id)
        # current_level wurde erhöht
        assert service._active_escalations[escalation_id].current_level == level_before + 1

    @pytest.mark.asyncio
    async def test_check_escalations_skips_not_overdue(
        self,
        service: NotificationEscalationService,
        user_id: uuid.UUID,
        notification_id: uuid.UUID,
    ) -> None:
        """check_escalations überspringt eine noch nicht fällige Eskalation."""
        escalation_id = await service.create_escalation(
            notification_id=notification_id,
            chain_name="standard",
            user_id=user_id,
        )

        # next_escalation_at liegt (Standard: 60 Min Delay) in der Zukunft
        state = service._active_escalations[escalation_id]
        level_before = state.current_level

        escalated = await service.check_escalations()

        # Nichts eskaliert, Level unverändert
        assert escalated == []
        assert service._active_escalations[escalation_id].current_level == level_before

    @pytest.mark.asyncio
    async def test_check_escalations_auto_resolves_after_timeout(
        self,
        service: NotificationEscalationService,
        user_id: uuid.UUID,
        notification_id: uuid.UUID,
    ) -> None:
        """check_escalations löst Eskalationen nach auto_resolve_after_hours auf."""
        escalation_id = await service.create_escalation(
            notification_id=notification_id,
            chain_name="urgent",  # auto_resolve_after_hours=8
            user_id=user_id,
        )

        # created_at weit genug in die Vergangenheit setzen, dass auto-resolve greift
        from datetime import datetime, timedelta, timezone
        state = service._active_escalations[escalation_id]
        chain = PRESET_CHAINS["urgent"]
        state.created_at = datetime.now(timezone.utc) - timedelta(
            hours=chain.auto_resolve_after_hours + 1
        )

        await service.check_escalations()

        # Auto-resolved -> aus aktiven Eskalationen entfernt
        assert escalation_id not in service._active_escalations

    # -------------------------------------------------------------------------
    # Resolve Escalation Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_resolve_escalation_stops_chain(
        self,
        service: NotificationEscalationService,
        user_id: uuid.UUID,
        notification_id: uuid.UUID,
    ) -> None:
        """resolve_escalation beendet die Kette und entfernt sie aus aktiven Eskalationen."""
        escalation_id = await service.create_escalation(
            notification_id=notification_id,
            chain_name="standard",
            user_id=user_id,
        )

        resolved = await service.resolve_escalation(notification_id=notification_id)

        assert resolved is True
        # Nach Auflösung nicht mehr aktiv
        assert escalation_id not in service._active_escalations

    @pytest.mark.asyncio
    async def test_resolve_escalation_nonexistent_returns_false(
        self,
        service: NotificationEscalationService,
    ) -> None:
        """resolve_escalation gibt False für nicht existierende Eskalation zurück."""
        result = await service.resolve_escalation(notification_id=uuid.uuid4())
        assert result is False

    # -------------------------------------------------------------------------
    # Get Active Escalations Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_get_active_escalations_for_user(
        self,
        service: NotificationEscalationService,
        user_id: uuid.UUID,
    ) -> None:
        """get_active_escalations liefert die aktiven Eskalationen eines Users."""
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
        # Eskalation eines anderen Users -> darf nicht erscheinen
        await service.create_escalation(
            notification_id=uuid.uuid4(),
            chain_name="standard",
            user_id=uuid.uuid4(),
        )

        result = await service.get_active_escalations(user_id=user_id)

        assert len(result) == 2
        # Rückgabe sind Dicts mit erwarteten Schlüsseln
        for entry in result:
            assert "escalation_id" in entry
            assert "notification_id" in entry
            assert "current_level" in entry
            assert entry["status"] == EscalationStatus.PENDING.value

    @pytest.mark.asyncio
    async def test_get_active_escalations_excludes_resolved(
        self,
        service: NotificationEscalationService,
        user_id: uuid.UUID,
    ) -> None:
        """get_active_escalations schließt aufgelöste Eskalationen aus."""
        notif_keep = uuid.uuid4()
        notif_resolve = uuid.uuid4()

        await service.create_escalation(
            notification_id=notif_keep,
            chain_name="standard",
            user_id=user_id,
        )
        await service.create_escalation(
            notification_id=notif_resolve,
            chain_name="standard",
            user_id=user_id,
        )

        # Eine der beiden auflösen
        await service.resolve_escalation(notification_id=notif_resolve)

        result = await service.get_active_escalations(user_id=user_id)

        assert len(result) == 1
        assert result[0]["notification_id"] == str(notif_keep)


class TestNotificationDeduplicationService:
    """Tests für NotificationDeduplicationService (In-Memory Modus, ohne Redis)."""

    @pytest.fixture
    def service(self) -> NotificationDeduplicationService:
        """Dedup-Service ohne Redis-Client -> In-Memory Local-Cache."""
        return NotificationDeduplicationService()

    @pytest.fixture
    def user_id(self) -> str:
        """Test User ID."""
        return "user-123"

    # -------------------------------------------------------------------------
    # is_duplicate / mark_sent Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_is_duplicate_false_for_new_notification(
        self,
        service: NotificationDeduplicationService,
        user_id: str,
    ) -> None:
        """is_duplicate gibt False für eine noch nicht markierte Notification zurück."""
        result = await service.is_duplicate(
            user_id=user_id,
            notification_type="document_processed",
            entity_id="doc-123",
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_is_duplicate_true_after_mark_sent(
        self,
        service: NotificationDeduplicationService,
        user_id: str,
    ) -> None:
        """Nach mark_sent erkennt is_duplicate ein Duplikat innerhalb des Windows."""
        notification_type = "document_processed"
        entity_id = "doc-123"

        await service.mark_sent(user_id, notification_type, entity_id)
        result = await service.is_duplicate(user_id, notification_type, entity_id)

        assert result is True

    @pytest.mark.asyncio
    async def test_is_duplicate_different_types_not_duplicate(
        self,
        service: NotificationDeduplicationService,
        user_id: str,
    ) -> None:
        """Unterschiedliche notification_types erzeugen unterschiedliche Keys."""
        entity_id = "doc-123"
        await service.mark_sent(user_id, "document_processed", entity_id)

        result = await service.is_duplicate(user_id, "document_failed", entity_id)
        assert result is False

    @pytest.mark.asyncio
    async def test_is_duplicate_different_entities_not_duplicate(
        self,
        service: NotificationDeduplicationService,
        user_id: str,
    ) -> None:
        """Unterschiedliche entity_ids erzeugen unterschiedliche Keys."""
        notification_type = "document_processed"
        await service.mark_sent(user_id, notification_type, "doc-123")

        result = await service.is_duplicate(user_id, notification_type, "doc-456")
        assert result is False

    @pytest.mark.asyncio
    async def test_is_duplicate_different_users_not_duplicate(
        self,
        service: NotificationDeduplicationService,
    ) -> None:
        """Unterschiedliche user_ids erzeugen unterschiedliche Keys."""
        notification_type = "document_processed"
        entity_id = "doc-123"
        await service.mark_sent("user-123", notification_type, entity_id)

        result = await service.is_duplicate("user-456", notification_type, entity_id)
        assert result is False

    # -------------------------------------------------------------------------
    # Dedup Window Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_dedup_window_expiration(
        self,
        service: NotificationDeduplicationService,
        user_id: str,
    ) -> None:
        """Nach Ablauf des Windows ist die Notification kein Duplikat mehr."""
        notification_type = "document_processed"
        entity_id = "doc-123"
        window_seconds = 1

        await service.mark_sent(
            user_id, notification_type, entity_id, window_seconds=window_seconds
        )

        import time
        time.sleep(window_seconds + 0.5)

        result = await service.is_duplicate(
            user_id, notification_type, entity_id, window_seconds=window_seconds
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_dedup_within_window(
        self,
        service: NotificationDeduplicationService,
        user_id: str,
    ) -> None:
        """Innerhalb des Windows bleibt die Notification ein Duplikat."""
        notification_type = "document_processed"
        entity_id = "doc-123"

        await service.mark_sent(user_id, notification_type, entity_id)

        import time
        time.sleep(0.1)

        result = await service.is_duplicate(user_id, notification_type, entity_id)
        assert result is True

    def test_dedup_window_dataclass_default(self) -> None:
        """DedupWindow hat den dokumentierten Default von 300 Sekunden."""
        assert DedupWindow().seconds == 300
        assert DedupWindow(seconds=42).seconds == 42

    # -------------------------------------------------------------------------
    # Clear User Dedup Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_clear_user_dedup(
        self,
        service: NotificationDeduplicationService,
        user_id: str,
    ) -> None:
        """clear_user_dedup entfernt nur die Einträge des angegebenen Users."""
        await service.mark_sent(user_id, "type1", "entity1")
        await service.mark_sent(user_id, "type2", "entity2")
        await service.mark_sent("other-user", "type1", "entity1")

        cleared = await service.clear_user_dedup(user_id)
        assert cleared == 2

        # Einträge des Users sind weg
        assert await service.is_duplicate(user_id, "type1", "entity1") is False
        assert await service.is_duplicate(user_id, "type2", "entity2") is False
        # Anderer User bleibt erhalten
        assert await service.is_duplicate("other-user", "type1", "entity1") is True

    # -------------------------------------------------------------------------
    # Cleanup Expired Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_cleanup_expired_removes_old_entries(
        self,
        service: NotificationDeduplicationService,
        user_id: str,
    ) -> None:
        """cleanup_expired entfernt abgelaufene Einträge aus dem Local-Cache."""
        window_seconds = 1
        await service.mark_sent(
            user_id, "type1", "entity1", window_seconds=window_seconds
        )

        import time
        time.sleep(window_seconds + 0.5)
        removed = service.cleanup_expired()

        assert removed >= 1
        assert await service.is_duplicate(user_id, "type1", "entity1") is False

    @pytest.mark.asyncio
    async def test_cleanup_expired_keeps_recent_entries(
        self,
        service: NotificationDeduplicationService,
        user_id: str,
    ) -> None:
        """cleanup_expired behält noch gültige Einträge."""
        await service.mark_sent(user_id, "type1", "entity1")

        import time
        time.sleep(0.1)
        service.cleanup_expired()

        # Noch innerhalb des Default-Windows -> weiterhin Duplikat
        assert await service.is_duplicate(user_id, "type1", "entity1") is True

    # -------------------------------------------------------------------------
    # Edge Cases
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_multiple_notifications_same_type_different_entities(
        self,
        service: NotificationDeduplicationService,
        user_id: str,
    ) -> None:
        """Gleicher Type, verschiedene Entities -> jeweils eigenständige Dedup-Keys."""
        notification_type = "document_processed"
        entities = ["doc-1", "doc-2", "doc-3", "doc-4", "doc-5"]

        # Erster Durchgang: alle neu
        for entity_id in entities:
            assert await service.is_duplicate(user_id, notification_type, entity_id) is False
            await service.mark_sent(user_id, notification_type, entity_id)

        # Zweiter Durchgang: alle Duplikate
        for entity_id in entities:
            assert await service.is_duplicate(user_id, notification_type, entity_id) is True

    @pytest.mark.asyncio
    async def test_same_entity_different_types(
        self,
        service: NotificationDeduplicationService,
        user_id: str,
    ) -> None:
        """Gleiche Entity, verschiedene Types -> verschiedene Keys, kein Duplikat."""
        entity_id = "doc-123"
        types = ["processed", "failed", "archived", "deleted"]

        for notification_type in types:
            assert await service.is_duplicate(user_id, notification_type, entity_id) is False
            await service.mark_sent(user_id, notification_type, entity_id)

    @pytest.mark.asyncio
    async def test_empty_entity_id_behaves_as_no_entity(
        self,
        service: NotificationDeduplicationService,
        user_id: str,
    ) -> None:
        """Leere entity_id ('') wird wie 'keine Entity' behandelt (falsy -> Key ohne Entity)."""
        # Der echte _build_dedup_key behandelt '' (falsy) wie None.
        assert await service.is_duplicate(user_id, "type1", "") is False
        await service.mark_sent(user_id, "type1", "")
        assert await service.is_duplicate(user_id, "type1", "") is True

    @pytest.mark.asyncio
    async def test_none_entity_id(
        self,
        service: NotificationDeduplicationService,
        user_id: str,
    ) -> None:
        """None als entity_id erzeugt einen Key ohne Entity-Teil."""
        assert await service.is_duplicate(user_id, "type1", None) is False
        await service.mark_sent(user_id, "type1", None)
        assert await service.is_duplicate(user_id, "type1", None) is True


class TestEscalationChain:
    """Tests für die EscalationChain Preset-Dataclass."""

    def test_escalation_chain_initialization(self) -> None:
        """EscalationChain wird mit gültigen Levels korrekt initialisiert."""
        levels = [
            EscalationLevel(level=1, channel="in_app", delay_minutes=0, recipients=["user"]),
            EscalationLevel(level=2, channel="email", delay_minutes=180, recipients=["user"]),
        ]

        chain = EscalationChain(
            id="esc-1",
            name="Test-Chain",
            description="Beschreibung",
            levels=levels,
            max_escalation_level=2,
        )

        assert chain.id == "esc-1"
        assert len(chain.levels) == 2
        assert chain.max_escalation_level == 2
        assert chain.auto_resolve_after_hours is None

    def test_escalation_chain_requires_levels(self) -> None:
        """EscalationChain ohne Levels wirft ValueError (Post-Init Validierung)."""
        with pytest.raises(ValueError, match="mindestens ein Level"):
            EscalationChain(
                id="esc-1",
                name="Leer",
                description="",
                levels=[],
                max_escalation_level=1,
            )

    def test_escalation_chain_max_level_exceeds_levels(self) -> None:
        """max_escalation_level darf nicht größer als die Anzahl der Levels sein."""
        levels = [
            EscalationLevel(level=1, channel="in_app", delay_minutes=0, recipients=["user"]),
        ]
        with pytest.raises(ValueError, match="max_escalation_level"):
            EscalationChain(
                id="esc-1",
                name="Test",
                description="",
                levels=levels,
                max_escalation_level=5,
            )


class TestEscalationLevel:
    """Tests für die EscalationLevel Dataclass."""

    def test_escalation_level_initialization(self) -> None:
        """EscalationLevel wird korrekt initialisiert (recipients ist Pflicht)."""
        level = EscalationLevel(
            level=1,
            channel="email",
            delay_minutes=120,
            recipients=["user"],
        )

        assert level.level == 1
        assert level.channel == "email"
        assert level.delay_minutes == 120
        assert level.recipients == ["user"]
        assert level.message_template is None

    def test_escalation_level_invalid_level_raises(self) -> None:
        """level < 1 wirft ValueError (Post-Init Validierung)."""
        with pytest.raises(ValueError, match="Level muss >= 1 sein"):
            EscalationLevel(level=0, channel="email", delay_minutes=10, recipients=["user"])

    def test_escalation_level_negative_delay_raises(self) -> None:
        """Negatives delay_minutes wirft ValueError (Post-Init Validierung)."""
        with pytest.raises(ValueError, match="Delay muss >= 0 sein"):
            EscalationLevel(level=1, channel="email", delay_minutes=-5, recipients=["user"])

    def test_escalation_level_ordering(self) -> None:
        """EscalationLevel lassen sich nach ihrem level-Attribut sortieren."""
        level1 = EscalationLevel(level=1, channel="in_app", delay_minutes=60, recipients=["user"])
        level2 = EscalationLevel(level=2, channel="email", delay_minutes=120, recipients=["user"])
        level3 = EscalationLevel(level=3, channel="slack", delay_minutes=240, recipients=["user"])

        sorted_levels = sorted([level2, level3, level1], key=lambda x: x.level)

        assert [lv.level for lv in sorted_levels] == [1, 2, 3]


class TestEscalationPreset:
    """Tests für das EscalationPreset Enum."""

    def test_escalation_preset_values(self) -> None:
        """EscalationPreset hat die erwarteten Werte."""
        assert EscalationPreset.STANDARD.value == "standard"
        assert EscalationPreset.URGENT.value == "urgent"
        assert EscalationPreset.RELAXED.value == "relaxed"

    def test_escalation_preset_string_representation(self) -> None:
        """EscalationPreset ist ein str-Enum mit den passenden String-Werten."""
        assert EscalationPreset.STANDARD == "standard"
        assert EscalationPreset.URGENT == "urgent"


class TestPresetChains:
    """Tests für die vordefinierten Eskalationsketten (PRESET_CHAINS)."""

    def test_preset_chains_contain_expected_keys(self) -> None:
        """PRESET_CHAINS enthält standard, urgent und approval."""
        assert set(PRESET_CHAINS.keys()) == {"standard", "urgent", "approval"}

    def test_standard_chain_channel_progression(self) -> None:
        """Standard-Chain eskaliert von In-App über Email zu Slack."""
        chain = PRESET_CHAINS["standard"]
        channels = [lv.channel for lv in chain.levels]
        assert channels == [
            EscalationChannel.IN_APP.value,
            EscalationChannel.EMAIL.value,
            EscalationChannel.SLACK.value,
        ]
        # Delays steigen monoton (sofort -> später)
        delays = [lv.delay_minutes for lv in chain.levels]
        assert delays == sorted(delays)

    def test_urgent_chain_resolves_faster_than_standard(self) -> None:
        """Urgent-Chain hat ein kürzeres auto_resolve_after_hours als Standard."""
        assert (
            PRESET_CHAINS["urgent"].auto_resolve_after_hours
            < PRESET_CHAINS["standard"].auto_resolve_after_hours
        )

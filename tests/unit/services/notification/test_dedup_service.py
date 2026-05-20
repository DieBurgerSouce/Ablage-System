# -*- coding: utf-8 -*-
"""
Unit Tests fuer NotificationDeduplicationService.

Testet:
- Duplikat-Erkennung (Redis + In-Memory)
- Mark-as-Sent
- Key-Building
- TTL-basierte Expiration
- User-spezifische Dedup
- Cleanup
"""

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.notification.dedup_service import (
    NotificationDeduplicationService,
    get_dedup_service,
)


class TestDedupKeyBuilding:
    """Tests fuer Dedup-Key-Building."""

    def test_key_without_entity(self) -> None:
        """Key ohne Entity sollte korrekt gebaut werden."""
        service = NotificationDeduplicationService()

        key = service._build_dedup_key(
            user_id="user-123",
            notification_type="invoice_received",
            entity_id=None,
        )

        assert key == "notif_dedup:user:user-123:type:invoice_received"

    def test_key_with_entity(self) -> None:
        """Key mit Entity sollte Entity-Hash enthalten."""
        service = NotificationDeduplicationService()

        key = service._build_dedup_key(
            user_id="user-123",
            notification_type="invoice_received",
            entity_id="invoice-456",
        )

        assert key.startswith("notif_dedup:user:user-123:type:invoice_received:entity:")
        assert len(key.split(":")[-1]) == 8  # MD5 hash (8 chars)

    def test_key_different_entities_different_keys(self) -> None:
        """Unterschiedliche Entities sollten unterschiedliche Keys erzeugen."""
        service = NotificationDeduplicationService()

        key1 = service._build_dedup_key(
            user_id="user-123",
            notification_type="invoice_received",
            entity_id="invoice-1",
        )

        key2 = service._build_dedup_key(
            user_id="user-123",
            notification_type="invoice_received",
            entity_id="invoice-2",
        )

        assert key1 != key2


@pytest.mark.asyncio
class TestDedupServiceInMemory:
    """Tests fuer In-Memory Mode (ohne Redis)."""

    @pytest.fixture
    def service(self) -> NotificationDeduplicationService:
        """Service-Instanz ohne Redis."""
        return NotificationDeduplicationService(redis_client=None)

    async def test_is_duplicate_first_time(
        self,
        service: NotificationDeduplicationService,
    ) -> None:
        """Erstes Mal sollte kein Duplikat sein."""
        is_dup = await service.is_duplicate(
            user_id="user-123",
            notification_type="invoice_received",
            entity_id="invoice-1",
        )

        assert is_dup is False

    async def test_is_duplicate_after_mark_sent(
        self,
        service: NotificationDeduplicationService,
    ) -> None:
        """Nach mark_sent sollte Duplikat erkannt werden."""
        # Mark as sent
        await service.mark_sent(
            user_id="user-123",
            notification_type="invoice_received",
            entity_id="invoice-1",
            window_seconds=10,
        )

        # Check duplicate
        is_dup = await service.is_duplicate(
            user_id="user-123",
            notification_type="invoice_received",
            entity_id="invoice-1",
        )

        assert is_dup is True

    async def test_is_duplicate_after_expiry(
        self,
        service: NotificationDeduplicationService,
    ) -> None:
        """Nach TTL-Ablauf sollte kein Duplikat mehr erkannt werden."""
        # Mark as sent mit kurzem Window
        await service.mark_sent(
            user_id="user-123",
            notification_type="invoice_received",
            entity_id="invoice-1",
            window_seconds=1,
        )

        # Wait for expiry
        time.sleep(1.1)

        # Check duplicate (sollte expired sein)
        is_dup = await service.is_duplicate(
            user_id="user-123",
            notification_type="invoice_received",
            entity_id="invoice-1",
        )

        assert is_dup is False

    async def test_different_users_no_duplicate(
        self,
        service: NotificationDeduplicationService,
    ) -> None:
        """Unterschiedliche User sollten keine Duplikate untereinander haben."""
        # User 1 sendet
        await service.mark_sent(
            user_id="user-1",
            notification_type="invoice_received",
            entity_id="invoice-1",
        )

        # User 2 prueft (sollte kein Duplikat sein)
        is_dup = await service.is_duplicate(
            user_id="user-2",
            notification_type="invoice_received",
            entity_id="invoice-1",
        )

        assert is_dup is False

    async def test_different_notification_types_no_duplicate(
        self,
        service: NotificationDeduplicationService,
    ) -> None:
        """Unterschiedliche Typen sollten keine Duplikate sein."""
        # Type 1 senden
        await service.mark_sent(
            user_id="user-123",
            notification_type="invoice_received",
            entity_id="invoice-1",
        )

        # Type 2 pruefen (sollte kein Duplikat sein)
        is_dup = await service.is_duplicate(
            user_id="user-123",
            notification_type="payment_received",
            entity_id="invoice-1",
        )

        assert is_dup is False

    async def test_type_specific_window(
        self,
        service: NotificationDeduplicationService,
    ) -> None:
        """Typ-spezifisches Window sollte verwendet werden."""
        # OCR completed hat 120s Window (siehe TYPE_WINDOWS)
        await service.mark_sent(
            user_id="user-123",
            notification_type="ocr_completed",
            entity_id="doc-1",
        )

        is_dup = await service.is_duplicate(
            user_id="user-123",
            notification_type="ocr_completed",
            entity_id="doc-1",
        )

        assert is_dup is True

    async def test_cleanup_expired(
        self,
        service: NotificationDeduplicationService,
    ) -> None:
        """Cleanup sollte abgelaufene Eintraege entfernen."""
        # Mehrere Eintraege mit kurzem TTL
        await service.mark_sent(
            user_id="user-123",
            notification_type="invoice_received",
            entity_id="invoice-1",
            window_seconds=1,
        )
        await service.mark_sent(
            user_id="user-123",
            notification_type="invoice_received",
            entity_id="invoice-2",
            window_seconds=1,
        )

        # Wait for expiry
        time.sleep(1.1)

        # Cleanup
        cleaned = service.cleanup_expired()

        assert cleaned == 2
        assert len(service._local_cache) == 0

    async def test_clear_user_dedup(
        self,
        service: NotificationDeduplicationService,
    ) -> None:
        """clear_user_dedup sollte alle Eintraege fuer User loeschen."""
        # User 1 - 2 Eintraege
        await service.mark_sent(
            user_id="user-1",
            notification_type="invoice_received",
            entity_id="invoice-1",
        )
        await service.mark_sent(
            user_id="user-1",
            notification_type="payment_received",
            entity_id="payment-1",
        )

        # User 2 - 1 Eintrag
        await service.mark_sent(
            user_id="user-2",
            notification_type="invoice_received",
            entity_id="invoice-1",
        )

        # Clear User 1
        count = await service.clear_user_dedup("user-1")

        assert count == 2

        # User 1 Eintraege sollten weg sein
        is_dup = await service.is_duplicate(
            user_id="user-1",
            notification_type="invoice_received",
            entity_id="invoice-1",
        )
        assert is_dup is False

        # User 2 Eintrag sollte noch existieren
        is_dup2 = await service.is_duplicate(
            user_id="user-2",
            notification_type="invoice_received",
            entity_id="invoice-1",
        )
        assert is_dup2 is True


@pytest.mark.asyncio
class TestDedupServiceRedis:
    """Tests fuer Redis Mode."""

    @pytest.fixture
    def mock_redis(self) -> AsyncMock:
        """Mock Redis Client."""
        redis = AsyncMock()
        redis.exists = AsyncMock(return_value=0)
        redis.setex = AsyncMock()
        redis.scan = AsyncMock(return_value=(0, []))
        redis.delete = AsyncMock()
        return redis

    @pytest.fixture
    def service(self, mock_redis: AsyncMock) -> NotificationDeduplicationService:
        """Service-Instanz mit Mock Redis."""
        return NotificationDeduplicationService(redis_client=mock_redis)

    async def test_is_duplicate_redis_miss(
        self,
        service: NotificationDeduplicationService,
        mock_redis: AsyncMock,
    ) -> None:
        """Redis miss sollte kein Duplikat sein."""
        mock_redis.exists.return_value = 0

        is_dup = await service.is_duplicate(
            user_id="user-123",
            notification_type="invoice_received",
            entity_id="invoice-1",
        )

        assert is_dup is False
        mock_redis.exists.assert_called_once()

    async def test_is_duplicate_redis_hit(
        self,
        service: NotificationDeduplicationService,
        mock_redis: AsyncMock,
    ) -> None:
        """Redis hit sollte Duplikat sein."""
        mock_redis.exists.return_value = 1

        is_dup = await service.is_duplicate(
            user_id="user-123",
            notification_type="invoice_received",
            entity_id="invoice-1",
        )

        assert is_dup is True
        mock_redis.exists.assert_called_once()

    async def test_mark_sent_redis(
        self,
        service: NotificationDeduplicationService,
        mock_redis: AsyncMock,
    ) -> None:
        """mark_sent sollte Redis SETEX aufrufen."""
        await service.mark_sent(
            user_id="user-123",
            notification_type="invoice_received",
            entity_id="invoice-1",
            window_seconds=300,
        )

        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args[0]
        assert call_args[1] == 300  # TTL
        assert call_args[2] == "1"  # Value

    async def test_clear_user_dedup_redis(
        self,
        service: NotificationDeduplicationService,
        mock_redis: AsyncMock,
    ) -> None:
        """clear_user_dedup sollte Redis SCAN + DELETE aufrufen."""
        # Mock scan to return some keys
        mock_redis.scan.return_value = (0, ["key1", "key2"])

        count = await service.clear_user_dedup("user-123")

        mock_redis.scan.assert_called_once()
        mock_redis.delete.assert_called_once_with("key1", "key2")
        assert count == 2

    async def test_redis_fallback_on_error(
        self,
        service: NotificationDeduplicationService,
        mock_redis: AsyncMock,
    ) -> None:
        """Bei Redis-Fehler sollte auf Local Cache gefallen werden."""
        # Redis exists wirft Exception
        mock_redis.exists.side_effect = Exception("Redis connection error")

        # Sollte trotzdem funktionieren (Fallback)
        is_dup = await service.is_duplicate(
            user_id="user-123",
            notification_type="invoice_received",
            entity_id="invoice-1",
        )

        assert is_dup is False

        # Mark sent sollte auch im Fallback funktionieren
        await service.mark_sent(
            user_id="user-123",
            notification_type="invoice_received",
            entity_id="invoice-1",
        )

        # Jetzt sollte Duplikat erkannt werden (im Local Cache)
        is_dup2 = await service.is_duplicate(
            user_id="user-123",
            notification_type="invoice_received",
            entity_id="invoice-1",
        )

        assert is_dup2 is True


class TestDedupFactory:
    """Tests fuer Factory-Funktion."""

    def test_get_dedup_service_singleton(self) -> None:
        """Factory sollte Singleton liefern."""
        service1 = get_dedup_service()
        service2 = get_dedup_service()

        assert service1 is service2

    def test_get_dedup_service_with_redis(self) -> None:
        """Factory mit Redis sollte funktionieren."""
        mock_redis = MagicMock()
        service = get_dedup_service(mock_redis)

        assert service.redis is mock_redis
        assert service._use_redis is True

# -*- coding: utf-8 -*-
"""
Notification Deduplication Service.

Verhindert doppelte Benachrichtigungen innerhalb konfigurierbarer Zeitfenster:
- Redis-basiert (mit Fallback auf In-Memory)
- Konfigurierbare Time Windows pro Notification-Typ
- Entity-basierte Dedup-Keys
- Automatische Cleanup veralteter Einträge

Features:
- Cross-Process Deduplication (via Redis)
- Graceful Fallback (In-Memory wenn Redis offline)
- Flexible Key-Building (user + type + entity)
- TTL-basierte Auto-Expiration

Feinpoliert und durchdacht - Keine Spam-Benachrichtigungen mehr.
"""

from __future__ import annotations

import hashlib
import time
from typing import Dict, Optional

import structlog
from prometheus_client import Counter

logger = structlog.get_logger(__name__)


# =============================================================================
# Prometheus Metriken
# =============================================================================


DEDUP_CHECKS = Counter(
    "notification_dedup_checks_total",
    "Anzahl Dedup-Prüfungen",
    ["result"]
)

DEDUP_HITS = Counter(
    "notification_dedup_hits_total",
    "Anzahl verhinderte Duplikate",
    ["notification_type"]
)

DEDUP_CLEANUP = Counter(
    "notification_dedup_cleanup_total",
    "Anzahl bereinigter Dedup-Einträge"
)


# =============================================================================
# Deduplication Service
# =============================================================================


class DedupWindow:
    """Konfiguration für Dedup-Zeitfenster."""

    def __init__(self, seconds: int = 300) -> None:
        self.seconds = seconds


class NotificationDeduplicationService:
    """
    Verhindert doppelte Benachrichtigungen.

    Verwendet Redis für Cross-Process Deduplication mit Fallback auf In-Memory.

    Verwendung:
        dedup = NotificationDeduplicationService(redis_client)

        # Vor dem Senden prüfen
        if await dedup.is_duplicate(user_id, "invoice_received", invoice_id):
            logger.info("duplicate_skipped")
            return

        # Nach dem Senden markieren
        await dedup.mark_sent(user_id, "invoice_received", invoice_id)
    """

    DEFAULT_WINDOW_SECONDS = 300  # 5 Minuten

    # Typ-spezifische Windows (in Sekunden)
    TYPE_WINDOWS: Dict[str, int] = {
        # Häufige Events - kurzes Window
        "document_uploaded": 60,
        "ocr_started": 60,
        "ocr_completed": 120,

        # Business Events - mittleres Window
        "invoice_received": 300,
        "payment_received": 300,
        "approval_required": 600,

        # Kritische Events - langes Window
        "fraud_detected": 3600,
        "security_breach": 3600,
        "system_down": 1800,

        # Workflow - mittleres Window
        "workflow_step": 300,
        "deadline_tomorrow": 600,

        # Anomalien - langes Window
        "anomaly_critical": 900,
        "anomaly_warning": 600,
    }

    def __init__(self, redis_client: Optional[object] = None) -> None:
        """
        Initialisiert den Service.

        Args:
            redis_client: Redis Client (optional, Fallback auf In-Memory)
        """
        self.redis = redis_client
        self._local_cache: Dict[str, float] = {}
        self._use_redis = redis_client is not None

        if not self._use_redis:
            logger.warning(
                "dedup_service_no_redis",
                message="Dedup laeuft im In-Memory Modus (nicht Cross-Process)",
            )

    def _build_dedup_key(
        self,
        user_id: str,
        notification_type: str,
        entity_id: Optional[str] = None,
    ) -> str:
        """
        Baut eindeutigen Dedup-Key.

        Format: notif_dedup:user:{user_id}:type:{type}:entity:{entity_id_hash}

        Args:
            user_id: Benutzer-ID
            notification_type: Typ der Benachrichtigung
            entity_id: Optionale Entity-ID (z.B. Document-ID)

        Returns:
            Dedup-Key
        """
        if entity_id:
            # Hash entity_id für kompakte Keys
            entity_hash = hashlib.md5(entity_id.encode()).hexdigest()[:8]
            return f"notif_dedup:user:{user_id}:type:{notification_type}:entity:{entity_hash}"
        else:
            return f"notif_dedup:user:{user_id}:type:{notification_type}"

    async def is_duplicate(
        self,
        user_id: str,
        notification_type: str,
        entity_id: Optional[str] = None,
        window_seconds: Optional[int] = None,
    ) -> bool:
        """
        Prüft ob Benachrichtigung ein Duplikat ist.

        Args:
            user_id: Benutzer-ID (UUID als String)
            notification_type: Typ der Benachrichtigung
            entity_id: Optionale Entity-ID
            window_seconds: Optionales Window (überschreibt Typ-Default)

        Returns:
            True wenn Duplikat (bereits kürzlich gesendet)
        """
        key = self._build_dedup_key(user_id, notification_type, entity_id)
        window = window_seconds or self.TYPE_WINDOWS.get(
            notification_type,
            self.DEFAULT_WINDOW_SECONDS
        )

        if self._use_redis and self.redis:
            # Redis-basiert
            try:
                exists = await self._redis_exists(key)
                DEDUP_CHECKS.labels(result="redis_hit" if exists else "redis_miss").inc()

                if exists:
                    DEDUP_HITS.labels(notification_type=notification_type).inc()

                return exists

            except Exception as e:
                logger.warning(
                    "dedup_redis_error",
                    error=str(e),
                    message="Fallback auf Local Cache",
                )
                # Fallback auf Local Cache
                return self._is_duplicate_local(key, window)
        else:
            # In-Memory
            return self._is_duplicate_local(key, window)

    async def mark_sent(
        self,
        user_id: str,
        notification_type: str,
        entity_id: Optional[str] = None,
        window_seconds: Optional[int] = None,
    ) -> None:
        """
        Markiert Benachrichtigung als gesendet (verhindert Duplikate).

        Args:
            user_id: Benutzer-ID (UUID als String)
            notification_type: Typ der Benachrichtigung
            entity_id: Optionale Entity-ID
            window_seconds: Optionales Window
        """
        key = self._build_dedup_key(user_id, notification_type, entity_id)
        window = window_seconds or self.TYPE_WINDOWS.get(
            notification_type,
            self.DEFAULT_WINDOW_SECONDS
        )

        if self._use_redis and self.redis:
            # Redis-basiert
            try:
                await self._redis_set(key, window)
                logger.debug(
                    "dedup_marked_sent_redis",
                    user_id=user_id,
                    notification_type=notification_type,
                    window_seconds=window,
                )
            except Exception as e:
                logger.warning(
                    "dedup_redis_set_error",
                    error=str(e),
                    message="Fallback auf Local Cache",
                )
                # Fallback auf Local Cache
                self._mark_sent_local(key, window)
        else:
            # In-Memory
            self._mark_sent_local(key, window)

    async def clear_user_dedup(self, user_id: str) -> int:
        """
        Löscht alle Dedup-Einträge für einen Benutzer.

        Nützlich z.B. nach Logout oder beim Testen.

        Args:
            user_id: Benutzer-ID

        Returns:
            Anzahl gelöschter Einträge
        """
        pattern = f"notif_dedup:user:{user_id}:*"
        count = 0

        if self._use_redis and self.redis:
            try:
                count = await self._redis_delete_pattern(pattern)
            except Exception as e:
                logger.warning(
                    "dedup_clear_redis_error",
                    error=str(e),
                )
        else:
            # In-Memory
            keys_to_delete = [k for k in self._local_cache.keys() if k.startswith(f"notif_dedup:user:{user_id}:")]
            for k in keys_to_delete:
                del self._local_cache[k]
            count = len(keys_to_delete)

        logger.info(
            "dedup_user_cleared",
            user_id=user_id,
            count=count,
        )

        return count

    def cleanup_expired(self) -> int:
        """
        Entfernt abgelaufene Einträge aus dem Local Cache.

        Wird periodisch aufgerufen (z.B. via Celery Beat).

        Returns:
            Anzahl entfernter Einträge
        """
        if self._use_redis:
            # Redis hat TTL-basierte Auto-Expiration
            return 0

        now = time.time()
        expired_keys = [
            k for k, v in self._local_cache.items()
            if v < now
        ]

        for k in expired_keys:
            del self._local_cache[k]

        if expired_keys:
            DEDUP_CLEANUP.inc(len(expired_keys))
            logger.debug(
                "dedup_cleanup_expired",
                count=len(expired_keys),
            )

        return len(expired_keys)

    # =========================================================================
    # Private Methods - Local Cache
    # =========================================================================

    def _is_duplicate_local(self, key: str, window_seconds: int) -> bool:
        """Prüft Duplikat im Local Cache."""
        now = time.time()

        if key in self._local_cache:
            expiry = self._local_cache[key]
            if expiry > now:
                DEDUP_CHECKS.labels(result="local_hit").inc()
                return True

            # Expired - cleanup
            del self._local_cache[key]

        DEDUP_CHECKS.labels(result="local_miss").inc()
        return False

    def _mark_sent_local(self, key: str, window_seconds: int) -> None:
        """Markiert als gesendet im Local Cache."""
        expiry = time.time() + window_seconds
        self._local_cache[key] = expiry

        logger.debug(
            "dedup_marked_sent_local",
            key=key,
            window_seconds=window_seconds,
        )

    # =========================================================================
    # Private Methods - Redis
    # =========================================================================

    async def _redis_exists(self, key: str) -> bool:
        """Prüft ob Key in Redis existiert."""
        if not self.redis:
            return False

        # Redis client ist vermutlich aioredis oder redis-py mit async support
        # Annahme: self.redis.exists(key) gibt int zurück (1 oder 0)
        try:
            exists = await self.redis.exists(key)
            return exists > 0
        except AttributeError:
            # Fallback für synchronen Redis-Client
            exists = self.redis.exists(key)
            return exists > 0

    async def _redis_set(self, key: str, window_seconds: int) -> None:
        """Setzt Key in Redis mit TTL."""
        if not self.redis:
            return

        try:
            # SET mit EX (TTL in Sekunden)
            await self.redis.setex(key, window_seconds, "1")
        except AttributeError:
            # Fallback für synchronen Redis-Client
            self.redis.setex(key, window_seconds, "1")

    async def _redis_delete_pattern(self, pattern: str) -> int:
        """Löscht alle Keys die Pattern matchen."""
        if not self.redis:
            return 0

        try:
            # SCAN + DELETE Pattern
            cursor = 0
            count = 0

            while True:
                cursor, keys = await self.redis.scan(cursor, match=pattern, count=100)
                if keys:
                    await self.redis.delete(*keys)
                    count += len(keys)

                if cursor == 0:
                    break

            return count

        except AttributeError:
            # Fallback für synchronen Redis-Client
            keys = self.redis.keys(pattern)
            if keys:
                self.redis.delete(*keys)
                return len(keys)
            return 0


# =============================================================================
# Factory
# =============================================================================


_dedup_service: Optional[NotificationDeduplicationService] = None


def get_dedup_service(redis_client: Optional[object] = None) -> NotificationDeduplicationService:
    """
    Factory für NotificationDeduplicationService.

    Args:
        redis_client: Redis Client (optional)

    Returns:
        NotificationDeduplicationService Instanz
    """
    global _dedup_service
    if _dedup_service is None:
        _dedup_service = NotificationDeduplicationService(redis_client)
    return _dedup_service

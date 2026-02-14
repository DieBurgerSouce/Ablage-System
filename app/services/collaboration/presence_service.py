# -*- coding: utf-8 -*-
"""
Presence Service - Echtzeit-Dokument-Praesenz-Tracking.

Redis-basiertes Tracking wer gerade welches Dokument betrachtet/bearbeitet:
- Join/Leave fuer Dokumente
- Heartbeat mit automatischem Timeout (TTL 120s)
- Editing-State Tracking
- Deterministische Avatar-Farben pro User

Multi-Tenant:
- Alle Operationen sind company_id-isoliert

Feinpoliert und durchdacht - Collaborative Presence.
"""

import hashlib
import json
import structlog
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

import redis.asyncio as aioredis

from app.core.config import settings
from app.core.datetime_utils import utc_now
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)

# Deterministic avatar colors for consistent user identification
_AVATAR_COLORS = [
    "#4F46E5",  # Indigo
    "#059669",  # Emerald
    "#D97706",  # Amber
    "#DC2626",  # Red
    "#7C3AED",  # Violet
    "#0891B2",  # Cyan
    "#BE185D",  # Pink
    "#65A30D",  # Lime
    "#EA580C",  # Orange
    "#6366F1",  # Blue-Violet
    "#0D9488",  # Teal
    "#CA8A04",  # Yellow
]


def _avatar_color_for_user(user_id: UUID) -> str:
    """Deterministic color from user_id hash."""
    hash_val = int(hashlib.md5(str(user_id).encode()).hexdigest(), 16)
    return _AVATAR_COLORS[hash_val % len(_AVATAR_COLORS)]


@dataclass
class PresenceEntry:
    """Ein Praesenz-Eintrag fuer einen Benutzer auf einem Dokument."""

    user_id: str
    user_name: str
    joined_at: str  # ISO format
    last_heartbeat: str  # ISO format
    is_editing: bool = False
    avatar_color: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


class PresenceService:
    """
    Redis-basiertes Document Presence Tracking.

    Verwendet Redis HSET mit JSON-Werten pro User.
    Key-Schema: presence:doc:{document_id}
    TTL: 120 Sekunden (refreshed by heartbeat).
    """

    PRESENCE_KEY_PREFIX = "presence:doc:"
    PRESENCE_TTL = 120  # 2 Minuten, wird durch Heartbeat erneuert

    def __init__(self, redis_url: Optional[str] = None) -> None:
        """Initialize with Redis connection URL."""
        if redis_url:
            self._redis_url = redis_url
        elif settings.REDIS_URL:
            self._redis_url = settings.REDIS_URL
        else:
            password_part = (
                f":{settings.REDIS_PASSWORD.get_secret_value()}@"
                if settings.REDIS_PASSWORD
                else ""
            )
            self._redis_url = (
                f"redis://{password_part}{settings.REDIS_HOST}:"
                f"{settings.REDIS_PORT}/{settings.REDIS_DB}"
            )
        self._redis: Optional[aioredis.Redis] = None

    async def _ensure_connection(self) -> aioredis.Redis:
        """Ensure Redis connection is established."""
        if self._redis is None:
            self._redis = await aioredis.from_url(
                self._redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_timeout=5.0,
                socket_connect_timeout=5.0,
            )
        return self._redis

    def _key(self, document_id: UUID) -> str:
        """Build Redis key for document presence."""
        return f"{self.PRESENCE_KEY_PREFIX}{document_id}"

    async def join_document(
        self,
        document_id: UUID,
        user_id: UUID,
        user_name: str,
    ) -> List[PresenceEntry]:
        """
        User betritt ein Dokument.

        Args:
            document_id: Dokument-ID
            user_id: Benutzer-ID
            user_name: Anzeigename des Benutzers

        Returns:
            Aktuelle Liste aller Praesenz-Eintraege fuer das Dokument
        """
        r = await self._ensure_connection()
        key = self._key(document_id)
        now = utc_now()

        entry = PresenceEntry(
            user_id=str(user_id),
            user_name=user_name,
            joined_at=now.isoformat(),
            last_heartbeat=now.isoformat(),
            is_editing=False,
            avatar_color=_avatar_color_for_user(user_id),
        )

        try:
            await r.hset(key, str(user_id), json.dumps(entry.to_dict()))
            await r.expire(key, self.PRESENCE_TTL)

            logger.info(
                "presence_joined",
                document_id=str(document_id),
                user_id=str(user_id),
            )
        except Exception as e:
            logger.error(
                "presence_join_failed",
                document_id=str(document_id),
                user_id=str(user_id),
                **safe_error_log(e),
            )

        return await self.get_presence(document_id)

    async def leave_document(
        self,
        document_id: UUID,
        user_id: UUID,
    ) -> None:
        """
        User verlaesst ein Dokument.

        Args:
            document_id: Dokument-ID
            user_id: Benutzer-ID
        """
        r = await self._ensure_connection()
        key = self._key(document_id)

        try:
            await r.hdel(key, str(user_id))
            logger.info(
                "presence_left",
                document_id=str(document_id),
                user_id=str(user_id),
            )
        except Exception as e:
            logger.error(
                "presence_leave_failed",
                document_id=str(document_id),
                user_id=str(user_id),
                **safe_error_log(e),
            )

    async def heartbeat(
        self,
        document_id: UUID,
        user_id: UUID,
    ) -> None:
        """
        Heartbeat fuer Praesenz-Aktualisierung.

        Aktualisiert last_heartbeat und erneuert TTL.

        Args:
            document_id: Dokument-ID
            user_id: Benutzer-ID
        """
        r = await self._ensure_connection()
        key = self._key(document_id)

        try:
            raw = await r.hget(key, str(user_id))
            if raw:
                data = json.loads(raw)
                data["last_heartbeat"] = utc_now().isoformat()
                await r.hset(key, str(user_id), json.dumps(data))
                await r.expire(key, self.PRESENCE_TTL)
            else:
                logger.debug(
                    "presence_heartbeat_no_entry",
                    document_id=str(document_id),
                    user_id=str(user_id),
                )
        except Exception as e:
            logger.error(
                "presence_heartbeat_failed",
                document_id=str(document_id),
                user_id=str(user_id),
                **safe_error_log(e),
            )

    async def get_presence(
        self,
        document_id: UUID,
    ) -> List[PresenceEntry]:
        """
        Gibt alle Praesenz-Eintraege fuer ein Dokument zurueck.

        Args:
            document_id: Dokument-ID

        Returns:
            Liste aller aktuellen Praesenz-Eintraege
        """
        r = await self._ensure_connection()
        key = self._key(document_id)
        entries: List[PresenceEntry] = []

        try:
            all_data = await r.hgetall(key)
            now = utc_now()

            for uid, raw in all_data.items():
                data = json.loads(raw)
                # Check if heartbeat is stale (>TTL seconds old)
                last_hb = datetime.fromisoformat(data["last_heartbeat"])
                if last_hb.tzinfo is None:
                    last_hb = last_hb.replace(tzinfo=timezone.utc)
                age_seconds = (now - last_hb).total_seconds()

                if age_seconds > self.PRESENCE_TTL:
                    # Stale entry - clean up
                    await r.hdel(key, uid)
                    continue

                entries.append(PresenceEntry(
                    user_id=data["user_id"],
                    user_name=data["user_name"],
                    joined_at=data["joined_at"],
                    last_heartbeat=data["last_heartbeat"],
                    is_editing=data.get("is_editing", False),
                    avatar_color=data.get("avatar_color", ""),
                ))

        except Exception as e:
            logger.error(
                "presence_get_failed",
                document_id=str(document_id),
                **safe_error_log(e),
            )

        return entries

    async def get_active_editors(
        self,
        document_id: UUID,
    ) -> List[PresenceEntry]:
        """
        Gibt nur die aktiv bearbeitenden Benutzer zurueck.

        Args:
            document_id: Dokument-ID

        Returns:
            Liste der Benutzer mit is_editing=True
        """
        all_entries = await self.get_presence(document_id)
        return [e for e in all_entries if e.is_editing]

    async def set_editing(
        self,
        document_id: UUID,
        user_id: UUID,
        is_editing: bool,
    ) -> None:
        """
        Setzt den Bearbeitungsstatus eines Benutzers.

        Args:
            document_id: Dokument-ID
            user_id: Benutzer-ID
            is_editing: True wenn aktiv bearbeitend
        """
        r = await self._ensure_connection()
        key = self._key(document_id)

        try:
            raw = await r.hget(key, str(user_id))
            if raw:
                data = json.loads(raw)
                data["is_editing"] = is_editing
                data["last_heartbeat"] = utc_now().isoformat()
                await r.hset(key, str(user_id), json.dumps(data))
                await r.expire(key, self.PRESENCE_TTL)

                logger.info(
                    "presence_editing_changed",
                    document_id=str(document_id),
                    user_id=str(user_id),
                    is_editing=is_editing,
                )
            else:
                logger.warning(
                    "presence_set_editing_no_entry",
                    document_id=str(document_id),
                    user_id=str(user_id),
                )
        except Exception as e:
            logger.error(
                "presence_set_editing_failed",
                document_id=str(document_id),
                user_id=str(user_id),
                **safe_error_log(e),
            )

    async def close(self) -> None:
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()
            self._redis = None


# =============================================================================
# Singleton / Factory
# =============================================================================

_presence_service_instance: Optional[PresenceService] = None


def get_presence_service() -> PresenceService:
    """Factory function to get PresenceService singleton."""
    global _presence_service_instance
    if _presence_service_instance is None:
        _presence_service_instance = PresenceService()
    return _presence_service_instance

"""
SSO State Manager - Redis-basierter State Storage für OIDC/SAML.

Ersetzt In-Memory-Dictionaries für Multi-Worker-Skalierbarkeit.
Fallback auf In-Memory wenn Redis nicht verfügbar (mit Warning).

SECURITY:
- TTL von 600 Sekunden (10 Minuten) für State
- Automatische Bereinigung abgelaufener States
- State kann nur einmal konsumiert werden (delete after get)
- Multi-Tenant-Isolation durch company_id im State (nicht im Key)

Feinpoliert und durchdacht - Enterprise SSO State Management.
"""

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Dict, Optional, Tuple
import json

import structlog

if TYPE_CHECKING:
    from redis.asyncio import Redis
    from app.services.auth.sso.oidc_service import OIDCState
    from app.services.auth.sso.saml_service import SAMLRequest

logger = structlog.get_logger(__name__)

# Default TTL for SSO states (10 minutes)
STATE_TTL_SECONDS = 600

# Key prefixes for Redis
OIDC_STATE_PREFIX = "sso:oidc:state:"
SAML_REQUEST_PREFIX = "sso:saml:request:"


class SSOStateManager:
    """Redis-basierter State Manager für SSO-Flows.

    Bietet thread-safe und multi-worker-safe State-Verwaltung für
    OIDC und SAML Authentication Flows.

    Features:
    - Redis-basiert für horizontale Skalierung
    - Automatischer Fallback auf In-Memory bei Redis-Ausfall
    - TTL-basierte automatische Bereinigung
    - One-time-use States (delete after get)

    SECURITY:
    - States sind zeitlich begrenzt (10 Minuten default)
    - States werden nach Abruf gelöscht (Replay-Schutz)
    - Keine sensiblen Daten in Redis Keys
    """

    def __init__(self, redis_client: Optional["Redis"] = None):
        """
        Initialisiert den SSO State Manager.

        Args:
            redis_client: Redis async client (optional, Fallback auf In-Memory)
        """
        self._redis = redis_client
        self._fallback_storage: Dict[str, Tuple[str, datetime]] = {}  # key -> (json_data, expires_at)
        self._using_fallback = redis_client is None

        if self._using_fallback:
            logger.warning(
                "sso_state_manager_fallback_mode",
                nachricht="SSO State Manager verwendet In-Memory-Fallback. "
                         "Nicht für Multi-Worker-Deployments geeignet.",
            )

    async def _get_redis(self) -> Optional["Redis"]:
        """Gibt Redis-Client zurück (lazy loading möglich)."""
        if self._redis is not None:
            return self._redis

        # Versuche lazy loading aus Core
        try:
            from app.core.rate_limiting import get_redis_storage
            redis = await get_redis_storage()
            if redis:
                self._redis = redis
                self._using_fallback = False
                logger.info("sso_state_manager_redis_connected")
            return redis
        except Exception as e:
            logger.debug(
                "sso_state_manager_redis_unavailable",
                error_type=type(e).__name__,
            )
            return None

    # =========================================================================
    # OIDC State Methods
    # =========================================================================

    async def store_oidc_state(
        self,
        state: str,
        data: "OIDCState",
        ttl: int = STATE_TTL_SECONDS,
    ) -> None:
        """
        Speichert OIDC State für Authorization Flow.

        Args:
            state: State Parameter (unique identifier)
            data: OIDCState Pydantic Model
            ttl: Time-to-live in Sekunden (default: 600)

        SECURITY:
        - State wird mit TTL gespeichert
        - Keine sensiblen Daten im Key
        """
        key = f"{OIDC_STATE_PREFIX}{state}"
        json_data = data.model_dump_json()

        redis = await self._get_redis()
        if redis:
            try:
                await redis.setex(key, ttl, json_data)
                logger.debug(
                    "oidc_state_stored",
                    state=state[:8] + "...",
                    ttl=ttl,
                )
                return
            except Exception as e:
                logger.warning(
                    "oidc_state_store_redis_failed",
                    error_type=type(e).__name__,
                )

        # Fallback auf In-Memory
        expires_at = datetime.utcnow() + timedelta(seconds=ttl)
        self._fallback_storage[key] = (json_data, expires_at)
        self._using_fallback = True
        logger.debug(
            "oidc_state_stored_fallback",
            state=state[:8] + "...",
        )

    async def get_oidc_state(
        self,
        state: str,
        delete: bool = True,
    ) -> Optional["OIDCState"]:
        """
        Ruft OIDC State ab. Löscht standardmaessig nach Abruf (one-time use).

        Args:
            state: State Parameter
            delete: Wenn True, wird State nach Abruf gelöscht (default: True)

        Returns:
            OIDCState oder None wenn nicht gefunden/abgelaufen

        SECURITY:
        - Delete-after-get verhindert Replay-Attacken
        - Abgelaufene States werden nicht zurückgegeben
        """
        from app.services.auth.sso.oidc_service import OIDCState

        key = f"{OIDC_STATE_PREFIX}{state}"

        redis = await self._get_redis()
        if redis:
            try:
                if delete:
                    # Atomic get and delete
                    json_data = await redis.getdel(key)
                else:
                    json_data = await redis.get(key)

                if json_data:
                    oidc_state = OIDCState.model_validate_json(json_data)
                    logger.debug(
                        "oidc_state_retrieved",
                        state=state[:8] + "...",
                        deleted=delete,
                    )
                    return oidc_state
                return None
            except Exception as e:
                logger.warning(
                    "oidc_state_get_redis_failed",
                    error_type=type(e).__name__,
                )

        # Fallback auf In-Memory
        entry = self._fallback_storage.get(key)
        if entry:
            json_data, expires_at = entry
            if datetime.utcnow() < expires_at:
                if delete:
                    del self._fallback_storage[key]
                oidc_state = OIDCState.model_validate_json(json_data)
                logger.debug(
                    "oidc_state_retrieved_fallback",
                    state=state[:8] + "...",
                )
                return oidc_state
            else:
                # Abgelaufen - aufraumen
                del self._fallback_storage[key]

        return None

    async def delete_oidc_state(self, state: str) -> bool:
        """
        Löscht einen OIDC State explizit.

        Args:
            state: State Parameter

        Returns:
            True wenn gelöscht, False wenn nicht gefunden
        """
        key = f"{OIDC_STATE_PREFIX}{state}"

        redis = await self._get_redis()
        if redis:
            try:
                deleted = await redis.delete(key)
                if deleted:
                    logger.debug(
                        "oidc_state_deleted",
                        state=state[:8] + "...",
                    )
                return bool(deleted)
            except Exception as e:
                logger.warning(
                    "oidc_state_delete_redis_failed",
                    error_type=type(e).__name__,
                )

        # Fallback auf In-Memory
        if key in self._fallback_storage:
            del self._fallback_storage[key]
            return True
        return False

    # =========================================================================
    # SAML Request Methods
    # =========================================================================

    async def store_saml_request(
        self,
        request_id: str,
        data: "SAMLRequest",
        ttl: int = STATE_TTL_SECONDS,
    ) -> None:
        """
        Speichert SAML Request State für Authentication Flow.

        Args:
            request_id: SAML Request ID (unique identifier)
            data: SAMLRequest Pydantic Model
            ttl: Time-to-live in Sekunden (default: 600)

        SECURITY:
        - Request wird mit TTL gespeichert
        - Keine sensiblen Daten im Key
        """
        key = f"{SAML_REQUEST_PREFIX}{request_id}"
        json_data = data.model_dump_json()

        redis = await self._get_redis()
        if redis:
            try:
                await redis.setex(key, ttl, json_data)
                logger.debug(
                    "saml_request_stored",
                    request_id=request_id[:16] + "...",
                    ttl=ttl,
                )
                return
            except Exception as e:
                logger.warning(
                    "saml_request_store_redis_failed",
                    error_type=type(e).__name__,
                )

        # Fallback auf In-Memory
        expires_at = datetime.utcnow() + timedelta(seconds=ttl)
        self._fallback_storage[key] = (json_data, expires_at)
        self._using_fallback = True
        logger.debug(
            "saml_request_stored_fallback",
            request_id=request_id[:16] + "...",
        )

    async def get_saml_request(
        self,
        request_id: str,
        delete: bool = True,
    ) -> Optional["SAMLRequest"]:
        """
        Ruft SAML Request ab. Löscht standardmaessig nach Abruf (one-time use).

        Args:
            request_id: SAML Request ID
            delete: Wenn True, wird Request nach Abruf gelöscht (default: True)

        Returns:
            SAMLRequest oder None wenn nicht gefunden/abgelaufen

        SECURITY:
        - Delete-after-get verhindert Replay-Attacken
        - Abgelaufene Requests werden nicht zurückgegeben
        """
        from app.services.auth.sso.saml_service import SAMLRequest

        key = f"{SAML_REQUEST_PREFIX}{request_id}"

        redis = await self._get_redis()
        if redis:
            try:
                if delete:
                    # Atomic get and delete
                    json_data = await redis.getdel(key)
                else:
                    json_data = await redis.get(key)

                if json_data:
                    saml_request = SAMLRequest.model_validate_json(json_data)
                    logger.debug(
                        "saml_request_retrieved",
                        request_id=request_id[:16] + "...",
                        deleted=delete,
                    )
                    return saml_request
                return None
            except Exception as e:
                logger.warning(
                    "saml_request_get_redis_failed",
                    error_type=type(e).__name__,
                )

        # Fallback auf In-Memory
        entry = self._fallback_storage.get(key)
        if entry:
            json_data, expires_at = entry
            if datetime.utcnow() < expires_at:
                if delete:
                    del self._fallback_storage[key]
                saml_request = SAMLRequest.model_validate_json(json_data)
                logger.debug(
                    "saml_request_retrieved_fallback",
                    request_id=request_id[:16] + "...",
                )
                return saml_request
            else:
                # Abgelaufen - aufraumen
                del self._fallback_storage[key]

        return None

    async def delete_saml_request(self, request_id: str) -> bool:
        """
        Löscht einen SAML Request explizit.

        Args:
            request_id: SAML Request ID

        Returns:
            True wenn gelöscht, False wenn nicht gefunden
        """
        key = f"{SAML_REQUEST_PREFIX}{request_id}"

        redis = await self._get_redis()
        if redis:
            try:
                deleted = await redis.delete(key)
                if deleted:
                    logger.debug(
                        "saml_request_deleted",
                        request_id=request_id[:16] + "...",
                    )
                return bool(deleted)
            except Exception as e:
                logger.warning(
                    "saml_request_delete_redis_failed",
                    error_type=type(e).__name__,
                )

        # Fallback auf In-Memory
        if key in self._fallback_storage:
            del self._fallback_storage[key]
            return True
        return False

    # =========================================================================
    # Maintenance Methods
    # =========================================================================

    async def cleanup_expired(self) -> int:
        """
        Bereinigt abgelaufene States (für In-Memory Fallback).

        Redis handhabt dies automatisch via TTL.

        Returns:
            Anzahl der bereinigten Einträge
        """
        if not self._using_fallback:
            # Redis handhabt TTL automatisch
            return 0

        now = datetime.utcnow()
        expired_keys = [
            key for key, (_, expires_at) in self._fallback_storage.items()
            if expires_at <= now
        ]

        for key in expired_keys:
            del self._fallback_storage[key]

        if expired_keys:
            logger.info(
                "sso_state_cleanup_completed",
                cleaned_count=len(expired_keys),
            )

        return len(expired_keys)

    async def get_stats(self) -> dict:
        """
        Gibt Statistiken über den State Manager zurück.

        Returns:
            Dict mit Statistiken
        """
        stats = {
            "using_fallback": self._using_fallback,
            "fallback_entry_count": len(self._fallback_storage),
        }

        if self._using_fallback:
            now = datetime.utcnow()
            oidc_count = sum(
                1 for key, (_, exp) in self._fallback_storage.items()
                if key.startswith(OIDC_STATE_PREFIX) and exp > now
            )
            saml_count = sum(
                1 for key, (_, exp) in self._fallback_storage.items()
                if key.startswith(SAML_REQUEST_PREFIX) and exp > now
            )
            stats["active_oidc_states"] = oidc_count
            stats["active_saml_requests"] = saml_count

        redis = await self._get_redis()
        if redis:
            try:
                # Zaehle aktive States in Redis
                oidc_keys = []
                saml_keys = []
                async for key in redis.scan_iter(match=f"{OIDC_STATE_PREFIX}*"):
                    oidc_keys.append(key)
                async for key in redis.scan_iter(match=f"{SAML_REQUEST_PREFIX}*"):
                    saml_keys.append(key)
                stats["redis_oidc_states"] = len(oidc_keys)
                stats["redis_saml_requests"] = len(saml_keys)
            except Exception as e:
                logger.debug(
                    "sso_state_stats_redis_failed",
                    error_type=type(e).__name__,
                )

        return stats

    @property
    def is_using_fallback(self) -> bool:
        """True wenn In-Memory Fallback statt Redis verwendet wird."""
        return self._using_fallback


# Singleton-Instanz für einfachen Zugriff
_state_manager: Optional[SSOStateManager] = None


def get_sso_state_manager(redis_client: Optional["Redis"] = None) -> SSOStateManager:
    """
    Gibt die Singleton-Instanz des SSO State Managers zurück.

    Args:
        redis_client: Optional Redis client für Erstinitialisierung

    Returns:
        SSOStateManager Instanz
    """
    global _state_manager
    if _state_manager is None:
        _state_manager = SSOStateManager(redis_client)
    return _state_manager


async def cleanup_sso_states() -> int:
    """
    Führt Cleanup auf dem Singleton State Manager aus.
    Kann als Celery Task aufgerufen werden.

    Returns:
        Anzahl bereinigter States
    """
    manager = get_sso_state_manager()
    return await manager.cleanup_expired()

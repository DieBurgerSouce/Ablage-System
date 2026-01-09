# -*- coding: utf-8 -*-
"""
Celery Task Idempotency Service.

PHASE 0.6 CRITICAL FIX: Stellt sicher, dass Beat-Tasks nicht mehrfach ausgefuehrt werden.

Verhindert:
- Doppelte KPI-History-Eintraege wenn Task erneut getriggert wird
- Doppelte Alerts wenn Task waehrend Ausfuehrung erneut gestartet wird
- Inkonsistente Daten durch Race Conditions

Verwendet Redis fuer verteilte Idempotency-Pruefung.
"""

import hashlib
import json
from datetime import datetime, timezone, date
from typing import Any, Dict, Optional, Union
from functools import wraps

from redis import Redis
from redis.exceptions import RedisError
import structlog

from app.core.config import settings

logger = structlog.get_logger(__name__)

# Redis Client fuer Idempotency
_redis_client: Optional[Redis] = None
_IDEMPOTENCY_PREFIX = "celery:idempotent:"
_DEFAULT_TTL = 86400  # 24 Stunden


def _get_redis_client() -> Redis:
    """Get or create Redis client for idempotency checks."""
    global _redis_client
    if _redis_client is None:
        _redis_client = Redis.from_url(
            settings.CELERY_BROKER_URL,
            decode_responses=True,
            socket_timeout=5.0,
            socket_connect_timeout=5.0,
        )
    return _redis_client


class IdempotencyKey:
    """
    Idempotency Key Manager fuer Celery Tasks.

    Verwendung:
        # In Task-Funktion
        key = IdempotencyKey.generate("record_kpi_history", space_id, date.today())
        if IdempotencyKey.exists(key):
            return IdempotencyKey.get_result(key)

        # ... Task ausfuehren ...

        IdempotencyKey.set_result(key, result)
    """

    @staticmethod
    def generate(
        task_name: str,
        *args: Any,
        date_scope: Optional[Union[date, datetime]] = None,
    ) -> str:
        """
        Generiert einen Idempotency Key basierend auf Task-Name und Argumenten.

        Args:
            task_name: Name des Celery Tasks
            *args: Task-Argumente die den Key eindeutig machen
            date_scope: Optional - Beschraenkt Key auf bestimmten Tag (default: heute)

        Returns:
            Eindeutiger Idempotency Key
        """
        # Verwende heutiges Datum wenn nicht spezifiziert
        if date_scope is None:
            date_scope = date.today()
        elif isinstance(date_scope, datetime):
            date_scope = date_scope.date()

        # Baue Key-Komponenten
        key_parts = [
            task_name,
            date_scope.isoformat(),
        ]

        # Fuege alle Argumente hinzu
        for arg in args:
            if arg is not None:
                key_parts.append(str(arg))

        # Erstelle Hash fuer kompakten Key
        content = ":".join(key_parts)
        hash_value = hashlib.sha256(content.encode()).hexdigest()[:16]

        return f"{_IDEMPOTENCY_PREFIX}{task_name}:{date_scope.isoformat()}:{hash_value}"

    @staticmethod
    def exists(key: str) -> bool:
        """
        Prueft ob ein Idempotency Key bereits existiert.

        Args:
            key: Der zu pruefende Key

        Returns:
            True wenn Key existiert (Task wurde bereits ausgefuehrt)
        """
        try:
            redis = _get_redis_client()
            return bool(redis.exists(key))
        except RedisError as e:
            logger.warning(
                "idempotency_check_failed",
                key=key,
                error=str(e),
            )
            # Bei Redis-Fehler: Erlaube Task-Ausfuehrung
            return False

    @staticmethod
    def get_result(key: str) -> Optional[Dict[str, Any]]:
        """
        Holt das gespeicherte Ergebnis eines bereits ausgefuehrten Tasks.

        Args:
            key: Der Idempotency Key

        Returns:
            Das gecachte Ergebnis oder None
        """
        try:
            redis = _get_redis_client()
            cached = redis.get(key)
            if cached:
                data = json.loads(cached)
                logger.info(
                    "idempotency_cache_hit",
                    key=key,
                    executed_at=data.get("executed_at"),
                )
                return data.get("result")
        except (RedisError, json.JSONDecodeError) as e:
            logger.warning(
                "idempotency_get_result_failed",
                key=key,
                error=str(e),
            )
        return None

    @staticmethod
    def set_result(
        key: str,
        result: Any,
        ttl: int = _DEFAULT_TTL,
    ) -> bool:
        """
        Speichert das Ergebnis eines Tasks.

        Args:
            key: Der Idempotency Key
            result: Das zu speichernde Ergebnis
            ttl: Time-to-Live in Sekunden (default: 24 Stunden)

        Returns:
            True wenn erfolgreich gespeichert
        """
        try:
            redis = _get_redis_client()
            data = {
                "result": result,
                "executed_at": datetime.now(timezone.utc).isoformat(),
                "key": key,
            }
            redis.set(key, json.dumps(data, default=str), ex=ttl)
            logger.debug(
                "idempotency_result_cached",
                key=key,
                ttl=ttl,
            )
            return True
        except RedisError as e:
            logger.warning(
                "idempotency_set_result_failed",
                key=key,
                error=str(e),
            )
            return False

    @staticmethod
    def acquire_lock(key: str, lock_ttl: int = 600) -> bool:
        """
        Erwirbt einen Lock fuer einen Task um Race Conditions zu verhindern.

        Args:
            key: Der Idempotency Key
            lock_ttl: Lock-Timeout in Sekunden (default: 10 Minuten)

        Returns:
            True wenn Lock erworben, False wenn Task bereits laeuft
        """
        lock_key = f"{key}:lock"
        try:
            redis = _get_redis_client()
            acquired = redis.set(
                lock_key,
                datetime.now(timezone.utc).isoformat(),
                nx=True,  # Nur wenn nicht existiert
                ex=lock_ttl,
            )
            if acquired:
                logger.debug("idempotency_lock_acquired", key=key)
            return bool(acquired)
        except RedisError as e:
            logger.warning(
                "idempotency_lock_acquire_failed",
                key=key,
                error=str(e),
            )
            # Bei Fehler: Erlaube Task-Ausfuehrung
            return True

    @staticmethod
    def release_lock(key: str) -> None:
        """
        Gibt den Lock fuer einen Task frei.

        Args:
            key: Der Idempotency Key
        """
        lock_key = f"{key}:lock"
        try:
            redis = _get_redis_client()
            redis.delete(lock_key)
            logger.debug("idempotency_lock_released", key=key)
        except RedisError as e:
            logger.warning(
                "idempotency_lock_release_failed",
                key=key,
                error=str(e),
            )


def idempotent_task(
    *key_args: str,
    date_scoped: bool = True,
    ttl: int = _DEFAULT_TTL,
):
    """
    Decorator um Celery Tasks idempotent zu machen.

    Verwendung:
        @celery_app.task(bind=True, base=CPUTask)
        @idempotent_task("space_id", date_scoped=True)
        def record_kpi_history(self, space_id: str = None):
            # Task wird nur einmal pro Tag pro space_id ausgefuehrt
            ...

    Args:
        *key_args: Namen der Argumente die den Key eindeutig machen
        date_scoped: Ob Key auf heutigen Tag beschraenkt ist (default: True)
        ttl: Time-to-Live fuer Cache in Sekunden (default: 24 Stunden)
    """
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            # Extrahiere Task-Name
            task_name = getattr(self, "name", func.__name__)

            # Baue Key-Argumente
            key_values = []
            for arg_name in key_args:
                if arg_name in kwargs:
                    key_values.append(kwargs[arg_name])

            # Generiere Idempotency Key
            if date_scoped:
                idempotency_key = IdempotencyKey.generate(
                    task_name,
                    *key_values,
                    date_scope=date.today(),
                )
            else:
                idempotency_key = IdempotencyKey.generate(
                    task_name,
                    *key_values,
                    date_scope=None,
                )

            # Pruefe ob bereits ausgefuehrt
            if IdempotencyKey.exists(idempotency_key):
                cached_result = IdempotencyKey.get_result(idempotency_key)
                logger.info(
                    "idempotent_task_skipped",
                    task_name=task_name,
                    key=idempotency_key,
                    reason="already_executed",
                )
                if cached_result is not None:
                    # Fuege Marker hinzu dass es aus Cache kommt
                    if isinstance(cached_result, dict):
                        cached_result["_from_cache"] = True
                    return cached_result
                return {
                    "_from_cache": True,
                    "status": "already_executed",
                    "key": idempotency_key,
                }

            # Erwirb Lock
            if not IdempotencyKey.acquire_lock(idempotency_key):
                logger.info(
                    "idempotent_task_skipped",
                    task_name=task_name,
                    key=idempotency_key,
                    reason="task_in_progress",
                )
                return {
                    "_from_cache": False,
                    "status": "task_in_progress",
                    "key": idempotency_key,
                }

            try:
                # Fuehre Task aus
                result = func(self, *args, **kwargs)

                # Speichere Ergebnis
                IdempotencyKey.set_result(idempotency_key, result, ttl=ttl)

                return result

            finally:
                # Lock freigeben
                IdempotencyKey.release_lock(idempotency_key)

        return wrapper
    return decorator


# ============================================================================
# Hilfsfunktionen fuer manuelle Idempotency-Pruefung
# ============================================================================

def check_task_idempotency(
    task_name: str,
    *args: Any,
    date_scope: Optional[date] = None,
) -> Optional[Dict[str, Any]]:
    """
    Prueft ob ein Task mit diesen Argumenten heute bereits ausgefuehrt wurde.

    Args:
        task_name: Name des Celery Tasks
        *args: Task-Argumente
        date_scope: Optional - Tag fuer den geprueft werden soll

    Returns:
        Gecachtes Ergebnis wenn vorhanden, sonst None
    """
    key = IdempotencyKey.generate(task_name, *args, date_scope=date_scope)
    if IdempotencyKey.exists(key):
        return IdempotencyKey.get_result(key)
    return None


def mark_task_executed(
    task_name: str,
    result: Any,
    *args: Any,
    date_scope: Optional[date] = None,
    ttl: int = _DEFAULT_TTL,
) -> str:
    """
    Markiert einen Task als ausgefuehrt.

    Args:
        task_name: Name des Celery Tasks
        result: Das Ergebnis des Tasks
        *args: Task-Argumente
        date_scope: Optional - Tag fuer den markiert werden soll
        ttl: Time-to-Live in Sekunden

    Returns:
        Der verwendete Idempotency Key
    """
    key = IdempotencyKey.generate(task_name, *args, date_scope=date_scope)
    IdempotencyKey.set_result(key, result, ttl=ttl)
    return key


def clear_task_idempotency(
    task_name: str,
    *args: Any,
    date_scope: Optional[date] = None,
) -> bool:
    """
    Loescht den Idempotency-Cache fuer einen Task (fuer erneute Ausfuehrung).

    Args:
        task_name: Name des Celery Tasks
        *args: Task-Argumente
        date_scope: Optional - Tag fuer den geloescht werden soll

    Returns:
        True wenn erfolgreich geloescht
    """
    key = IdempotencyKey.generate(task_name, *args, date_scope=date_scope)
    try:
        redis = _get_redis_client()
        redis.delete(key)
        redis.delete(f"{key}:lock")
        logger.info("idempotency_cache_cleared", key=key)
        return True
    except RedisError as e:
        logger.warning(
            "idempotency_cache_clear_failed",
            key=key,
            error=str(e),
        )
        return False

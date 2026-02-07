"""
Account-Lockout-System für Ablage-System OCR.

Schützt vor Brute-Force-Angriffen durch exponentielles Backoff bei fehlgeschlagenen Login-Versuchen.

Features:
- Redis-basiertes Tracking mit In-Memory-Fallback
- Exponentielles Backoff (1min → 5min → 15min → 1h)
- IP- und Username-basiertes Tracking
- Admin-Funktionen zum Entsperren
- Alerting bei verdächtigen Aktivitäten

Feinpoliert und durchdacht - Enterprise-grade Sicherheit.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Tuple, Union
import structlog

from app.core.config import settings
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)

# Lockout-Konfiguration
MAX_FAILED_ATTEMPTS = 5  # Maximal erlaubte Fehlversuche
ALERT_THRESHOLD = 10  # Ab dieser Anzahl wird ein Alert gesendet

# Exponentielles Backoff (in Sekunden)
# Nach 1 Fehlversuch: 0s, 2: 0s, ..., 5: 60s, 6: 300s, 7: 900s, 8+: 3600s
LOCKOUT_DURATIONS = {
    5: 60,      # 1 Minute
    6: 300,     # 5 Minuten
    7: 900,     # 15 Minuten
    8: 3600,    # 1 Stunde
}
MAX_LOCKOUT_DURATION = 3600  # Maximale Sperrzeit: 1 Stunde

# Redis-Key-Prefixe
FAILED_ATTEMPTS_PREFIX = "login:failed:"
LOCKOUT_PREFIX = "login:lockout:"

# FAANG-AUDIT FIX: In-Memory-Fallback (wenn Redis nicht verfügbar)
# SICHERHEITSWARNUNG: In-Memory ist prozesslokal!
# Bei Multi-Worker-Deployments:
# - Brute-Force kann ueber verschiedene Worker verteilt werden
# - Lockout-Status ist nicht synchronisiert
# EMPFEHLUNG: fail_closed=True in Production (Default), dann wird In-Memory nicht genutzt
import asyncio
_failed_attempts_fallback: Dict[str, int] = {}
_lockout_until_fallback: Dict[str, datetime] = {}
_fallback_lock: asyncio.Lock = asyncio.Lock()  # Thread-Safety fuer Fallback-Dicts

# Flag um einmalig vor In-Memory Fallback zu warnen
_fallback_warned: bool = False

# Redis-Client (lazy-loaded)
_redis_client: Optional[object] = None
_redis_available: Optional[bool] = None


class AccountLockoutStorageError(Exception):
    """
    Raised when account lockout storage (Redis) is unavailable and fail_closed mode is enabled.

    This exception indicates that the login attempt should be denied due to inability
    to verify lockout status - a security-critical operation.
    """
    pass


async def _get_redis_client() -> Optional[object]:
    """
    Hole Redis-Client für Account-Lockout-Operationen.

    Verwendet Lazy-Loading und cacht den Verfügbarkeitsstatus.

    Returns:
        Redis-Client oder None wenn nicht verfügbar
    """
    global _redis_client, _redis_available

    if _redis_available is False:
        return None

    if _redis_client is not None:
        return _redis_client

    try:
        from app.core.redis_state import RedisStateManager

        manager = RedisStateManager.get_instance()
        await manager.connect()

        if await manager.ping():
            _redis_client = manager._redis
            _redis_available = True
            logger.info("account_lockout_redis_connected")
            return _redis_client
        else:
            _redis_available = False
            logger.warning("account_lockout_redis_ping_failed",
                          message="Fallback auf In-Memory-Tracking")
            return None

    except Exception as e:
        _redis_available = False
        logger.warning("account_lockout_redis_unavailable",
                      **safe_error_log(e),
                      message="Fallback auf In-Memory-Tracking")
        return None


def _get_lockout_key(identifier: str) -> str:
    """Generiere Redis-Key für Lockout-Status."""
    return f"{LOCKOUT_PREFIX}{identifier}"


def _get_attempts_key(identifier: str) -> str:
    """Generiere Redis-Key für Fehlversuche."""
    return f"{FAILED_ATTEMPTS_PREFIX}{identifier}"


def _calculate_lockout_duration(failed_attempts: int) -> int:
    """
    Berechne Sperrdauer basierend auf Anzahl der Fehlversuche.

    Exponentielles Backoff:
    - 1-4 Versuche: Keine Sperre
    - 5 Versuche: 1 Minute
    - 6 Versuche: 5 Minuten
    - 7 Versuche: 15 Minuten
    - 8+ Versuche: 1 Stunde

    Args:
        failed_attempts: Anzahl der fehlgeschlagenen Versuche

    Returns:
        Sperrdauer in Sekunden
    """
    if failed_attempts < MAX_FAILED_ATTEMPTS:
        return 0

    # Finde passende Sperrdauer aus LOCKOUT_DURATIONS
    for threshold in sorted(LOCKOUT_DURATIONS.keys(), reverse=True):
        if failed_attempts >= threshold:
            return LOCKOUT_DURATIONS[threshold]

    return MAX_LOCKOUT_DURATION


def _create_identifier(ip: Optional[str], username: Optional[str]) -> str:
    """
    Erstelle eindeutigen Identifier für Tracking.

    Kombiniert IP und Username für präzises Tracking.

    Args:
        ip: Client-IP-Adresse
        username: Benutzername oder E-Mail

    Returns:
        Eindeutiger Identifier-String
    """
    parts = []
    if ip:
        parts.append(f"ip:{ip}")
    if username:
        # Normalisiere Username (lowercase)
        parts.append(f"user:{username.lower()}")

    return ":".join(parts) if parts else "unknown"


async def check_account_lockout(
    ip: Optional[str] = None,
    username: Optional[str] = None,
    fail_closed: Optional[bool] = None
) -> Tuple[bool, Optional[int], Optional[str]]:
    """
    Prüfe ob ein Account/IP gesperrt ist.

    Args:
        ip: Client-IP-Adresse
        username: Benutzername oder E-Mail
        fail_closed: Wenn True, wird bei Redis-Fehler der Login blockiert (sicherste Option).
                    Wenn None, wird settings.RATE_LIMIT_FAIL_CLOSED_CRITICAL verwendet.
                    Wenn False, wird In-Memory-Fallback genutzt (unsicher bei Multi-Worker).

    Returns:
        Tuple von:
        - is_locked: True wenn gesperrt
        - remaining_seconds: Verbleibende Sperrdauer in Sekunden
        - message: Deutsche Fehlermeldung

    Raises:
        AccountLockoutStorageError: Wenn fail_closed=True und Redis nicht verfügbar ist.
    """
    # Bestimme fail_closed Modus (Default aus Settings)
    if fail_closed is None:
        fail_closed = getattr(settings, 'RATE_LIMIT_FAIL_CLOSED_CRITICAL', True)

    identifier = _create_identifier(ip, username)
    redis = await _get_redis_client()
    redis_error_occurred = False

    if redis is not None:
        try:
            lockout_key = _get_lockout_key(identifier)
            lockout_until_str = await redis.get(lockout_key)

            if lockout_until_str:
                lockout_until = datetime.fromisoformat(lockout_until_str)
                now = datetime.now(timezone.utc)

                if lockout_until > now:
                    remaining = int((lockout_until - now).total_seconds())
                    return (
                        True,
                        remaining,
                        _format_lockout_message(remaining)
                    )
            # Redis verfügbar und kein Lockout gefunden -> nicht gesperrt
            return (False, None, None)
        except Exception as e:
            logger.warning("check_lockout_redis_error", error=type(e).__name__)
            redis_error_occurred = True
    else:
        redis_error_occurred = True

    # Redis nicht verfügbar oder Fehler aufgetreten
    if redis_error_occurred and fail_closed:
        logger.error(
            "account_lockout_redis_unavailable_fail_closed",
            identifier=identifier[:30] + "...",
            message="Login wird blockiert, da Lockout-Status nicht geprüft werden kann"
        )
        raise AccountLockoutStorageError(
            "Anmeldung vorübergehend nicht möglich. "
            "Der Sicherheitsdienst ist nicht verfügbar. "
            "Bitte versuchen Sie es in wenigen Minuten erneut."
        )

    # Fallback auf In-Memory (nur wenn fail_closed=False)
    # FAANG-AUDIT: Thread-Safety mit Lock + einmalige Warnung
    global _fallback_warned
    if not _fallback_warned:
        logger.warning(
            "account_lockout_using_memory_fallback",
            identifier=identifier[:30] + "...",
            message="SICHERHEITSWARNUNG: In-Memory-Fallback ist prozesslokal! "
                    "Bei Multi-Worker-Deployments kann Brute-Force verteilt werden. "
                    "Empfehlung: Redis verfuegbar machen oder fail_closed=True setzen."
        )
        _fallback_warned = True

    async with _fallback_lock:
        if identifier in _lockout_until_fallback:
            lockout_until = _lockout_until_fallback[identifier]
            now = datetime.now(timezone.utc)

            if lockout_until > now:
                remaining = int((lockout_until - now).total_seconds())
                return (
                    True,
                    remaining,
                    _format_lockout_message(remaining)
                )
            else:
                # Lockout abgelaufen, entfernen
                del _lockout_until_fallback[identifier]

    return (False, None, None)


def _format_lockout_message(remaining_seconds: int) -> str:
    """
    Formatiere deutsche Lockout-Nachricht.

    Args:
        remaining_seconds: Verbleibende Sperrdauer

    Returns:
        Formatierte deutsche Nachricht
    """
    if remaining_seconds >= 3600:
        hours = remaining_seconds // 3600
        return f"Konto vorübergehend gesperrt. Bitte versuchen Sie es in {hours} Stunde(n) erneut."
    elif remaining_seconds >= 60:
        minutes = remaining_seconds // 60
        return f"Konto vorübergehend gesperrt. Bitte versuchen Sie es in {minutes} Minute(n) erneut."
    else:
        return f"Konto vorübergehend gesperrt. Bitte versuchen Sie es in {remaining_seconds} Sekunden erneut."


async def record_failed_attempt(
    ip: Optional[str] = None,
    username: Optional[str] = None,
    fail_closed: Optional[bool] = None
) -> Tuple[int, bool, Optional[int]]:
    """
    Registriere einen fehlgeschlagenen Login-Versuch.

    Erhöht den Zähler und aktiviert ggf. die Sperre.

    Args:
        ip: Client-IP-Adresse
        username: Benutzername oder E-Mail
        fail_closed: Wenn True, wird bei Redis-Fehler der Versuch als gesperrt behandelt.
                    Wenn None, wird settings.RATE_LIMIT_FAIL_CLOSED_CRITICAL verwendet.

    Returns:
        Tuple von:
        - attempts: Aktuelle Anzahl Fehlversuche
        - is_now_locked: True wenn Account jetzt gesperrt wurde
        - lockout_seconds: Sperrdauer in Sekunden (wenn gesperrt)

    Raises:
        AccountLockoutStorageError: Wenn fail_closed=True und Redis nicht verfügbar ist.
    """
    # Bestimme fail_closed Modus (Default aus Settings)
    if fail_closed is None:
        fail_closed = getattr(settings, 'RATE_LIMIT_FAIL_CLOSED_CRITICAL', True)

    identifier = _create_identifier(ip, username)
    redis = await _get_redis_client()
    redis_error_occurred = False

    # Erhöhe Zähler
    attempts = 1
    if redis is not None:
        try:
            attempts_key = _get_attempts_key(identifier)
            attempts = await redis.incr(attempts_key)
            # Setze TTL auf 1 Stunde (Versuche verfallen nach 1h Inaktivität)
            await redis.expire(attempts_key, 3600)
        except Exception as e:
            logger.warning("record_attempt_redis_error", error=type(e).__name__)
            redis_error_occurred = True
    else:
        redis_error_occurred = True

    # Bei Redis-Fehler und fail_closed -> blockieren
    if redis_error_occurred:
        if fail_closed:
            logger.error(
                "record_failed_attempt_redis_unavailable_fail_closed",
                identifier=identifier[:30] + "...",
                message="Fehlversuch kann nicht aufgezeichnet werden - blockiere zur Sicherheit"
            )
            raise AccountLockoutStorageError(
                "Anmeldung vorübergehend nicht möglich. "
                "Der Sicherheitsdienst ist nicht verfügbar. "
                "Bitte versuchen Sie es in wenigen Minuten erneut."
            )
        else:
            # FAANG-AUDIT: In-Memory Fallback mit Lock (unsicher bei Multi-Worker!)
            async with _fallback_lock:
                attempts = _failed_attempts_fallback.get(identifier, 0) + 1
                _failed_attempts_fallback[identifier] = attempts

    # Logge den Fehlversuch
    logger.warning(
        "login_failed_attempt",
        identifier=identifier[:50] + "..." if len(identifier) > 50 else identifier,
        attempts=attempts,
        ip=ip,
        username=username[:3] + "***" if username else None,  # Maskiert
    )

    # Prüfe ob Alert gesendet werden soll
    if attempts == ALERT_THRESHOLD:
        logger.error(
            "login_brute_force_alert",
            message=f"Verdächtige Aktivität: {ALERT_THRESHOLD}+ fehlgeschlagene Login-Versuche",
            identifier=identifier,
            ip=ip,
        )
        # Hier könnte ein Alert an ein Monitoring-System gesendet werden

    # Berechne Sperrdauer
    lockout_duration = _calculate_lockout_duration(attempts)

    if lockout_duration > 0:
        lockout_until = datetime.now(timezone.utc) + timedelta(seconds=lockout_duration)

        if redis is not None:
            try:
                lockout_key = _get_lockout_key(identifier)
                await redis.setex(
                    lockout_key,
                    lockout_duration,
                    lockout_until.isoformat()
                )
            except Exception as e:
                logger.warning("set_lockout_redis_error", **safe_error_log(e))
                async with _fallback_lock:
                    _lockout_until_fallback[identifier] = lockout_until
        else:
            async with _fallback_lock:
                _lockout_until_fallback[identifier] = lockout_until

        logger.warning(
            "account_locked",
            identifier=identifier[:50] + "..." if len(identifier) > 50 else identifier,
            duration_seconds=lockout_duration,
            attempts=attempts,
        )

        return (attempts, True, lockout_duration)

    return (attempts, False, None)


async def reset_failed_attempts(
    ip: Optional[str] = None,
    username: Optional[str] = None
) -> bool:
    """
    Setze Fehlversuche nach erfolgreichem Login zurück.

    Args:
        ip: Client-IP-Adresse
        username: Benutzername oder E-Mail

    Returns:
        True wenn erfolgreich zurückgesetzt
    """
    identifier = _create_identifier(ip, username)
    redis = await _get_redis_client()

    if redis is not None:
        try:
            attempts_key = _get_attempts_key(identifier)
            lockout_key = _get_lockout_key(identifier)
            await redis.delete(attempts_key, lockout_key)
            logger.debug("failed_attempts_reset", identifier=identifier[:30] + "...")
            return True
        except Exception as e:
            logger.warning("reset_attempts_redis_error", **safe_error_log(e))

    # FAANG-AUDIT: Fallback mit Lock
    async with _fallback_lock:
        if identifier in _failed_attempts_fallback:
            del _failed_attempts_fallback[identifier]
        if identifier in _lockout_until_fallback:
            del _lockout_until_fallback[identifier]

    return True


async def admin_unlock_account(
    ip: Optional[str] = None,
    username: Optional[str] = None,
    admin_user: Optional[str] = None
) -> bool:
    """
    Admin-Funktion zum manuellen Entsperren eines Accounts.

    Args:
        ip: IP-Adresse zum Entsperren
        username: Benutzername zum Entsperren
        admin_user: Admin der die Entsperrung durchführt (für Audit)

    Returns:
        True wenn erfolgreich entsperrt
    """
    identifier = _create_identifier(ip, username)

    logger.info(
        "admin_account_unlock",
        identifier=identifier,
        admin_user=admin_user,
    )

    return await reset_failed_attempts(ip=ip, username=username)


async def get_lockout_status(
    ip: Optional[str] = None,
    username: Optional[str] = None
) -> Dict[str, Union[str, int, bool, None]]:
    """
    Hole detaillierten Lockout-Status für Admin-Dashboard.

    Args:
        ip: IP-Adresse
        username: Benutzername

    Returns:
        Dict mit Statusdetails
    """
    identifier = _create_identifier(ip, username)
    redis = await _get_redis_client()

    attempts = 0
    is_locked = False
    lockout_until = None
    remaining_seconds = None

    if redis is not None:
        try:
            attempts_key = _get_attempts_key(identifier)
            lockout_key = _get_lockout_key(identifier)

            attempts_str = await redis.get(attempts_key)
            if attempts_str:
                attempts = int(attempts_str)

            lockout_until_str = await redis.get(lockout_key)
            if lockout_until_str:
                lockout_until = datetime.fromisoformat(lockout_until_str)
                now = datetime.now(timezone.utc)
                if lockout_until > now:
                    is_locked = True
                    remaining_seconds = int((lockout_until - now).total_seconds())

        except Exception as e:
            logger.warning("get_status_redis_error", **safe_error_log(e))

    # FAANG-AUDIT: Fallback-Werte mit Lock wenn Redis nicht verfügbar
    if redis is None or attempts == 0:
        async with _fallback_lock:
            attempts = _failed_attempts_fallback.get(identifier, 0)
            if identifier in _lockout_until_fallback:
                lockout_until = _lockout_until_fallback[identifier]
                now = datetime.now(timezone.utc)
                if lockout_until > now:
                    is_locked = True
                    remaining_seconds = int((lockout_until - now).total_seconds())

    return {
        "identifier": identifier,
        "failed_attempts": attempts,
        "is_locked": is_locked,
        "lockout_until": lockout_until.isoformat() if lockout_until else None,
        "remaining_seconds": remaining_seconds,
        "max_attempts_before_lock": MAX_FAILED_ATTEMPTS,
        "using_redis": redis is not None,
    }

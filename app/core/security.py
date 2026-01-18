"""
Authentication and security utilities for Ablage-System.

Handles JWT token generation/validation, password hashing, and token blacklisting.
All error messages in German for user-facing responses.

Token-Blacklist: Redis-basiert mit In-Memory-Fallback für Skalierbarkeit.

SECURITY UTILITIES (Phase 10):
- Content-Disposition Header sanitization (CRLF injection prevention)
- Email Header sanitization
- Redis Key validation
"""

from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
import asyncio
import secrets
import re
from urllib.parse import quote

import bcrypt
from jose import JWTError, jwt
from fastapi import HTTPException, status
import structlog

# TTLCache for memory-efficient token blacklist with automatic expiration
try:
    from cachetools import TTLCache
    CACHETOOLS_AVAILABLE = True
except ImportError:
    TTLCache = None
    CACHETOOLS_AVAILABLE = False

from app.core.config import settings


logger = structlog.get_logger(__name__)

# Bcrypt cost factor (12 is a good security/performance balance)
BCRYPT_COST_FACTOR = 12

# Redis key prefix for token blacklist
TOKEN_BLACKLIST_PREFIX = "token:blacklist:"

# Token blacklist configuration
TOKEN_BLACKLIST_MAX_SIZE = 10000  # Maximum entries to prevent memory exhaustion
TOKEN_BLACKLIST_TTL_SECONDS = 86400  # 24 hours (max typical token lifetime)

# SECURITY FIX: Fail-closed mode for token blacklist
# Bei Multi-Worker Deployments ist In-Memory nicht synchronisiert!
# True = HTTP 503 bei Redis-Ausfall (sicherer, empfohlen für Production)
# False = Fallback auf In-Memory (unsicher bei Multi-Worker)
TOKEN_BLACKLIST_FAIL_CLOSED = True

# In-Memory Fallback Blacklist (used when Redis is unavailable)
# Uses TTLCache for automatic expiration and size limits
# Format: {token_jti: expiration_timestamp}
if CACHETOOLS_AVAILABLE:
    _token_blacklist_fallback: TTLCache = TTLCache(
        maxsize=TOKEN_BLACKLIST_MAX_SIZE,
        ttl=TOKEN_BLACKLIST_TTL_SECONDS
    )
else:
    # Fallback to regular Dict if cachetools not installed
    _token_blacklist_fallback: Dict[str, datetime] = {}
    logger.warning(
        "cachetools_not_available",
        message="Verwende Dict statt TTLCache für Token-Blacklist. "
                "Installiere cachetools für automatische Speicherbereinigung: pip install cachetools"
    )

# THREAD-SAFETY FIX: asyncio.Lock für In-Memory Blacklist
# Verhindert Race Conditions bei Multi-Worker Deployments mit In-Memory-Fallback
_blacklist_lock: asyncio.Lock = asyncio.Lock()

# Redis client instance (lazy-loaded)
_redis_client: Optional[Any] = None
_redis_available: Optional[bool] = None


# ==================== Redis Token Blacklist ====================

async def _get_redis_client() -> Optional[Any]:
    """
    Get Redis client for token blacklist operations.

    Uses lazy loading and caches availability status.

    Returns:
        Redis client or None if unavailable
    """
    global _redis_client, _redis_available

    # Return cached result if already checked
    if _redis_available is False:
        return None

    if _redis_client is not None:
        return _redis_client

    try:
        from app.core.redis_state import RedisStateManager
        manager = RedisStateManager.get_instance()
        await manager.connect()

        # Test connection
        if await manager.ping():
            _redis_client = manager._redis
            _redis_available = True
            logger.info("token_blacklist_redis_connected")
            return _redis_client
        else:
            _redis_available = False
            logger.warning("token_blacklist_redis_ping_failed",
                          message="Fallback auf In-Memory-Blacklist")
            return None

    except Exception as e:
        _redis_available = False
        # SECURITY: Nur Fehlertyp loggen, nicht Details (könnten Credentials enthalten)
        logger.warning("token_blacklist_redis_unavailable",
                      error_type=type(e).__name__,
                      message="Fallback auf In-Memory-Blacklist")
        return None


async def blacklist_token_redis(jti: str, expires_at: datetime) -> bool:
    """
    Add token to Redis blacklist with TTL.

    SECURITY: Bei TOKEN_BLACKLIST_FAIL_CLOSED=True wird bei Redis-Ausfall
    ein HTTP 503 geworfen statt unsicher auf In-Memory zurückzufallen.

    Args:
        jti: Token JTI (unique identifier)
        expires_at: Token expiration time (used for TTL)

    Returns:
        True if stored in Redis, False if fallback used

    Raises:
        HTTPException: 503 wenn Redis nicht verfügbar und fail-closed aktiviert
    """
    redis = await _get_redis_client()
    redis_write_failed = False

    if redis is not None:
        try:
            key = f"{TOKEN_BLACKLIST_PREFIX}{jti}"
            # Calculate TTL from expiration
            ttl_seconds = int((expires_at - datetime.now(timezone.utc)).total_seconds())

            if ttl_seconds > 0:
                await redis.setex(key, ttl_seconds, expires_at.isoformat())
                logger.debug("token_blacklisted_redis", jti=jti[:8] + "...")
                return True
        except Exception as e:
            redis_write_failed = True
            # SECURITY: Nur Fehlertyp loggen, nicht Details (könnten Credentials enthalten)
            logger.warning("token_blacklist_redis_error", error_type=type(e).__name__)
    else:
        redis_write_failed = True

    # SECURITY FIX: Fail-closed bei Redis-Ausfall
    # In Multi-Worker Deployments ist In-Memory nicht synchronisiert!
    if redis_write_failed and TOKEN_BLACKLIST_FAIL_CLOSED:
        logger.error(
            "token_blacklist_redis_write_failed_fail_closed",
            message="Redis nicht verfügbar - Token-Blacklist-Write fehlgeschlagen (fail-closed Modus)",
            jti_prefix=jti[:8]
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Sicherheitsdienst temporär nicht verfügbar. Logout konnte nicht durchgeführt werden.",
        )

    # Fallback to in-memory (nur wenn fail-closed deaktiviert)
    # WARNUNG: Nicht synchronisiert zwischen Workern!
    # THREAD-SAFETY: Lock verwenden für In-Memory-Zugriff
    async with _blacklist_lock:
        _token_blacklist_fallback[jti] = expires_at
        _cleanup_fallback_blacklist()
    logger.warning(
        "token_blacklisted_fallback_insecure",
        jti=jti[:8] + "...",
        message="Token nur lokal blacklisted - NICHT synchronisiert zwischen Workern!"
    )
    return False


async def is_token_blacklisted_redis(jti: str) -> bool:
    """
    Check if token is blacklisted (Redis + fallback).

    SECURITY: Bei TOKEN_BLACKLIST_FAIL_CLOSED=True wird bei Redis-Ausfall
    ein HTTP 503 geworfen statt unsicher auf In-Memory zurückzufallen.

    Args:
        jti: Token JTI to check

    Returns:
        True if token is blacklisted

    Raises:
        HTTPException: 503 wenn Redis nicht verfügbar und fail-closed aktiviert
    """
    redis = await _get_redis_client()
    redis_check_failed = False

    if redis is not None:
        try:
            key = f"{TOKEN_BLACKLIST_PREFIX}{jti}"
            exists = await redis.exists(key)
            if exists:
                return True
        except Exception as e:
            redis_check_failed = True
            # SECURITY: Nur Fehlertyp loggen, nicht Details (könnten Credentials enthalten)
            logger.warning("token_blacklist_check_redis_error", error_type=type(e).__name__)
    else:
        redis_check_failed = True

    # SECURITY FIX: Fail-closed bei Redis-Ausfall
    # In Multi-Worker Deployments ist In-Memory nicht synchronisiert!
    if redis_check_failed and TOKEN_BLACKLIST_FAIL_CLOSED:
        logger.error(
            "token_blacklist_redis_unavailable_fail_closed",
            message="Redis nicht verfügbar - Blacklist-Check fehlgeschlagen (fail-closed Modus)"
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Sicherheitsdienst temporär nicht verfügbar. Bitte später erneut versuchen.",
        )

    # Fallback auf In-Memory (nur wenn fail-closed deaktiviert)
    # WARNUNG: Nicht synchronisiert zwischen Workern!
    # THREAD-SAFETY: Lock verwenden für In-Memory-Zugriff
    async with _blacklist_lock:
        if jti in _token_blacklist_fallback:
            expiration = _token_blacklist_fallback[jti]
            if datetime.now(timezone.utc) < expiration:
                return True
            else:
                # Expired, remove from fallback
                del _token_blacklist_fallback[jti]

    return False


async def get_blacklist_stats() -> Dict[str, Any]:
    """
    Get token blacklist statistics for monitoring.

    Returns:
        Dictionary with blacklist statistics
    """
    redis = await _get_redis_client()

    # Trigger cleanup of expired entries
    _cleanup_fallback_blacklist()

    stats = {
        "redis_available": redis is not None,
        "fallback_count": len(_token_blacklist_fallback),
        "storage_type": "redis" if redis else "in-memory",
        "fallback_storage": "TTLCache" if CACHETOOLS_AVAILABLE else "Dict",
        "fallback_max_size": TOKEN_BLACKLIST_MAX_SIZE if CACHETOOLS_AVAILABLE else "unlimited",
        "fallback_ttl_seconds": TOKEN_BLACKLIST_TTL_SECONDS if CACHETOOLS_AVAILABLE else "manual",
    }

    if redis is not None:
        try:
            # Count Redis blacklist entries
            cursor = 0
            count = 0
            while True:
                cursor, keys = await redis.scan(
                    cursor,
                    match=f"{TOKEN_BLACKLIST_PREFIX}*",
                    count=100
                )
                count += len(keys)
                if cursor == 0:
                    break
            stats["redis_count"] = count
        except Exception as e:
            stats["redis_error"] = str(e)

    return stats


def _cleanup_fallback_blacklist() -> int:
    """
    Remove expired tokens from fallback blacklist.

    Note: If using TTLCache, expiration is automatic. This function
    only performs manual cleanup for Dict fallback and logs stats.

    Returns:
        Number of tokens removed
    """
    if CACHETOOLS_AVAILABLE:
        # TTLCache handles expiration automatically
        # Just expire any stale entries by accessing the cache
        try:
            _token_blacklist_fallback.expire()  # Trigger expiration check
        except AttributeError:
            pass  # expire() may not exist in all cachetools versions
        return 0

    # Manual cleanup for Dict fallback
    now = datetime.now(timezone.utc)
    expired = [jti for jti, exp in _token_blacklist_fallback.items() if now >= exp]

    removed = 0
    for jti in expired:
        try:
            del _token_blacklist_fallback[jti]
            removed += 1
        except KeyError:
            # Already deleted by concurrent cleanup (race condition safe)
            pass

    if removed:
        logger.debug("token_blacklist_cleanup", removed=removed)

    return removed


# ==================== Password Hashing ====================

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plain password against a hashed password.

    Args:
        plain_password: Plain text password
        hashed_password: Bcrypt hashed password

    Returns:
        True if password matches, False otherwise
    """
    password_bytes = plain_password.encode("utf-8")
    hash_bytes = hashed_password.encode("utf-8")
    return bcrypt.checkpw(password_bytes, hash_bytes)


def get_password_hash(password: str) -> str:
    """
    Hash a password using bcrypt with cost factor 12.

    Args:
        password: Plain text password

    Returns:
        Bcrypt hashed password
    """
    password_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt(rounds=BCRYPT_COST_FACTOR)
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode("utf-8")


# ==================== JWT Token Generation ====================

def create_access_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Create a JWT access token.

    Args:
        data: Payload data to encode in token (typically user_id, email)
        expires_delta: Optional custom expiration time

    Returns:
        Encoded JWT token string
    """
    to_encode = data.copy()

    # Set expiration time
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    # Add standard JWT claims
    to_encode.update({
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "access",
        "jti": secrets.token_urlsafe(32)  # Unique token ID for blacklisting
    })

    # Encode token
    # SECURITY FIX: SECRET_KEY ist jetzt SecretStr - verwende get_secret_value()
    secret_key = settings.SECRET_KEY.get_secret_value() if hasattr(settings.SECRET_KEY, 'get_secret_value') else settings.SECRET_KEY
    encoded_jwt = jwt.encode(
        to_encode,
        secret_key,
        algorithm=settings.ALGORITHM
    )

    return encoded_jwt


def create_refresh_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Create a JWT refresh token.

    Args:
        data: Payload data to encode in token
        expires_delta: Optional custom expiration time

    Returns:
        Encoded JWT refresh token string
    """
    to_encode = data.copy()

    # Set expiration time (7 days default)
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    # Add standard JWT claims
    to_encode.update({
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "refresh",
        "jti": secrets.token_urlsafe(32)
    })

    # Encode token
    # SECURITY FIX: SECRET_KEY ist jetzt SecretStr - verwende get_secret_value()
    secret_key = settings.SECRET_KEY.get_secret_value() if hasattr(settings.SECRET_KEY, 'get_secret_value') else settings.SECRET_KEY
    encoded_jwt = jwt.encode(
        to_encode,
        secret_key,
        algorithm=settings.ALGORITHM
    )

    return encoded_jwt


# ==================== JWT Token Validation ====================

async def decode_token(
    token: str,
    expected_type: Optional[str] = None
) -> Dict[str, Any]:
    """
    Decode and validate a JWT token (async, Redis-backed blacklist).

    Args:
        token: JWT token string
        expected_type: Expected token type ("access" or "refresh").
                      If None, accepts both types.

    Returns:
        Decoded token payload

    Raises:
        HTTPException: If token is invalid, expired, blacklisted, or wrong type
    """
    try:
        # SECURITY FIX: SECRET_KEY ist jetzt SecretStr - verwende get_secret_value()
        secret_key = settings.SECRET_KEY.get_secret_value() if hasattr(settings.SECRET_KEY, 'get_secret_value') else settings.SECRET_KEY
        payload = jwt.decode(
            token,
            secret_key,
            algorithms=[settings.ALGORITHM]
        )

        # SECURITY FIX: Validate token type to prevent refresh token misuse
        token_type = payload.get("type")
        if token_type not in ("access", "refresh"):
            logger.warning(
                "invalid_token_type",
                token_type=token_type,
                message="Token ohne gültigen Typ erkannt"
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Ungültiger Token-Typ",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # If specific type expected, validate it
        if expected_type and token_type != expected_type:
            logger.warning(
                "token_type_mismatch",
                expected=expected_type,
                actual=token_type,
                message="Falscher Token-Typ verwendet"
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Falscher Token-Typ. Erwartet: {expected_type}",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Check if token is blacklisted (async Redis check)
        jti = payload.get("jti")
        if jti and await is_token_blacklisted(jti):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token wurde widerrufen",  # German: "Token was revoked"
                headers={"WWW-Authenticate": "Bearer"},
            )

        return payload

    except JWTError as e:
        # Token invalid or expired
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token ungültig oder abgelaufen",  # German: "Token invalid or expired"
            headers={"WWW-Authenticate": "Bearer"},
        )


def decode_token_sync(token: str) -> Dict[str, Any]:
    """
    Synchronous token decode (only checks in-memory blacklist).

    DEPRECATED: Use async decode_token() for full Redis blacklist support.

    Args:
        token: JWT token string

    Returns:
        Decoded token payload

    Raises:
        HTTPException: If token is invalid, expired, or blacklisted
    """
    import warnings
    warnings.warn(
        "decode_token_sync ist deprecated. "
        "Verwende async decode_token() für Redis-Blacklist-Unterstützung.",
        DeprecationWarning,
        stacklevel=2
    )
    try:
        # SECURITY FIX: SECRET_KEY ist jetzt SecretStr - verwende get_secret_value()
        secret_key = settings.SECRET_KEY.get_secret_value() if hasattr(settings.SECRET_KEY, 'get_secret_value') else settings.SECRET_KEY
        payload = jwt.decode(
            token,
            secret_key,
            algorithms=[settings.ALGORITHM]
        )

        # Check fallback blacklist only (sync)
        jti = payload.get("jti")
        if jti and is_token_blacklisted_sync(jti):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token wurde widerrufen",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return payload

    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token ungültig oder abgelaufen",
            headers={"WWW-Authenticate": "Bearer"},
        )


def verify_token_type(payload: Dict[str, Any], expected_type: str) -> None:
    """
    Verify token type (access or refresh).

    Args:
        payload: Decoded token payload
        expected_type: Expected token type ("access" or "refresh")

    Raises:
        HTTPException: If token type doesn't match
    """
    token_type = payload.get("type")
    if token_type != expected_type:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Falscher Token-Typ. Erwartet: {expected_type}",  # German: "Wrong token type"
            headers={"WWW-Authenticate": "Bearer"},
        )


# ==================== Token Blacklisting ====================

async def blacklist_token(jti: str, expires_at: datetime) -> None:
    """
    Add a token to the blacklist (Redis with In-Memory fallback).

    Uses Redis for persistence and scalability across multiple instances.
    Falls back to in-memory storage if Redis is unavailable.

    Args:
        jti: Token JTI (unique identifier)
        expires_at: Token expiration time
    """
    await blacklist_token_redis(jti, expires_at)


async def is_token_blacklisted(jti: str) -> bool:
    """
    Check if a token is blacklisted (Redis + fallback).

    Args:
        jti: Token JTI to check

    Returns:
        True if token is blacklisted, False otherwise
    """
    return await is_token_blacklisted_redis(jti)


# Legacy sync versions for backward compatibility
def blacklist_token_sync(jti: str, expires_at: datetime) -> None:
    """
    Synchronous version of blacklist_token (In-Memory only).

    DEPRECATED: Use async blacklist_token() instead.
    Only for backward compatibility with sync code paths.

    Args:
        jti: Token JTI (unique identifier)
        expires_at: Token expiration time
    """
    _token_blacklist_fallback[jti] = expires_at
    _cleanup_fallback_blacklist()
    logger.warning("blacklist_token_sync_deprecated",
                  message="Verwende async blacklist_token() für Redis-Unterstützung")


def is_token_blacklisted_sync(jti: str) -> bool:
    """
    Synchronous version of is_token_blacklisted (In-Memory only).

    DEPRECATED: Use async is_token_blacklisted() instead.
    Only checks in-memory fallback, not Redis.

    Args:
        jti: Token JTI to check

    Returns:
        True if token is blacklisted in fallback storage
    """
    import warnings
    warnings.warn(
        "is_token_blacklisted_sync ist deprecated. "
        "Verwende async is_token_blacklisted() für Redis-Unterstützung.",
        DeprecationWarning,
        stacklevel=2
    )
    if jti not in _token_blacklist_fallback:
        return False

    expiration = _token_blacklist_fallback[jti]
    if datetime.now(timezone.utc) >= expiration:
        del _token_blacklist_fallback[jti]
        return False

    return True


# ==================== Token Utilities ====================

def create_token_pair(user_data: Dict[str, Any]) -> Dict[str, str]:
    """
    Create both access and refresh tokens for a user.

    Args:
        user_data: User information to encode in tokens (user_id, email, etc.)

    Returns:
        Dictionary with access_token and refresh_token
    """
    access_token = create_access_token(data=user_data)
    refresh_token = create_refresh_token(data=user_data)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }


def create_2fa_temp_token(user_id: str) -> str:
    """
    Create a temporary token for 2FA verification during login.

    This token is short-lived (5 minutes) and can only be used to complete
    the 2FA verification step after password authentication.

    Args:
        user_id: User ID to encode in token

    Returns:
        Encoded JWT token string for 2FA verification
    """
    to_encode = {
        "sub": user_id,
        "type": "2fa_temp",
        "jti": secrets.token_urlsafe(32),
    }

    expire = datetime.now(timezone.utc) + timedelta(minutes=5)
    to_encode["exp"] = expire
    to_encode["iat"] = datetime.now(timezone.utc)

    # R.2 SECURITY FIX: Konsistente SECRET_KEY Verwendung mit get_secret_value()
    secret_key = settings.SECRET_KEY.get_secret_value() if hasattr(settings.SECRET_KEY, 'get_secret_value') else settings.SECRET_KEY
    encoded_jwt = jwt.encode(to_encode, secret_key, algorithm=settings.ALGORITHM)

    logger.debug("2fa_temp_token_created", user_id=user_id[:8] + "...", expires_in_minutes=5)

    return encoded_jwt


async def verify_2fa_temp_token(token: str) -> str:
    """
    Verify a 2FA temporary token and extract user ID.

    Args:
        token: 2FA temp token string

    Returns:
        User ID if token is valid

    Raises:
        HTTPException: If token is invalid, expired, or wrong type
    """
    try:
        # R.2 SECURITY FIX: Konsistente SECRET_KEY Verwendung mit get_secret_value()
        secret_key = settings.SECRET_KEY.get_secret_value() if hasattr(settings.SECRET_KEY, 'get_secret_value') else settings.SECRET_KEY
        payload = jwt.decode(token, secret_key, algorithms=[settings.ALGORITHM])

        # Verify token type
        token_type = payload.get("type")
        if token_type != "2fa_temp":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Ungueltiger Token-Typ",
                headers={"WWW-Authenticate": "Bearer"},
            )

        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Ungueltiges Token-Format",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Check if token is blacklisted
        jti = payload.get("jti")
        if jti and await is_token_blacklisted(jti):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token wurde bereits verwendet",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return user_id

    except JWTError as e:
        logger.warning("2fa_temp_token_invalid", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="2FA-Token ungueltig oder abgelaufen",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def extract_user_id_from_token(token: str) -> str:
    """
    Extract user ID from JWT token (async).

    Args:
        token: JWT token string

    Returns:
        User ID from token

    Raises:
        HTTPException: If token is invalid or user_id not in payload
    """
    payload = await decode_token(token)
    user_id = payload.get("sub")

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungültiges Token-Format",  # German: "Invalid token format"
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user_id


def extract_user_id_from_token_sync(token: str) -> str:
    """
    Synchronous version - DEPRECATED.

    Use async extract_user_id_from_token() for Redis blacklist support.
    """
    import warnings
    warnings.warn(
        "extract_user_id_from_token_sync ist deprecated. "
        "Verwende async extract_user_id_from_token() für Redis-Blacklist-Unterstützung.",
        DeprecationWarning,
        stacklevel=2
    )
    payload = decode_token_sync(token)
    user_id = payload.get("sub")

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungültiges Token-Format",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user_id


# ==================== Password Validation ====================

def validate_password_strength(password: str) -> tuple[bool, Optional[str]]:
    """
    Validate password strength.

    Requirements:
    - At least 8 characters
    - Contains uppercase letter
    - Contains lowercase letter
    - Contains digit
    - Contains special character

    Args:
        password: Password to validate

    Returns:
        Tuple of (is_valid, error_message_in_german)
    """
    if len(password) < 8:
        return False, "Passwort muss mindestens 8 Zeichen lang sein"

    if not any(c.isupper() for c in password):
        return False, "Passwort muss mindestens einen Großbuchstaben enthalten"

    if not any(c.islower() for c in password):
        return False, "Passwort muss mindestens einen Kleinbuchstaben enthalten"

    if not any(c.isdigit() for c in password):
        return False, "Passwort muss mindestens eine Ziffer enthalten"

    special_chars = "!@#$%^&*()_+-=[]{}|;:,.<>?"
    if not any(c in special_chars for c in password):
        return False, "Passwort muss mindestens ein Sonderzeichen enthalten"

    return True, None


# ==================== SSRF Protection (M.1 CRITICAL FIX) ====================

import ipaddress
import socket
from urllib.parse import urlparse
from typing import Tuple

# M.1 CRITICAL: Liste der blockierten IP-Ranges fuer SSRF-Schutz
SSRF_BLOCKED_IP_RANGES = [
    ipaddress.ip_network("10.0.0.0/8"),       # Private Class A
    ipaddress.ip_network("172.16.0.0/12"),    # Private Class B
    ipaddress.ip_network("192.168.0.0/16"),   # Private Class C
    ipaddress.ip_network("127.0.0.0/8"),      # Loopback
    ipaddress.ip_network("169.254.0.0/16"),   # Link-Local (AWS/GCP Metadata!)
    ipaddress.ip_network("0.0.0.0/8"),        # This network
    ipaddress.ip_network("100.64.0.0/10"),    # Carrier-grade NAT
    ipaddress.ip_network("198.18.0.0/15"),    # Benchmark testing
    ipaddress.ip_network("224.0.0.0/4"),      # Multicast
    ipaddress.ip_network("240.0.0.0/4"),      # Reserved
    ipaddress.ip_network("255.255.255.255/32"),  # Broadcast
]

# IPv6 blocked ranges
SSRF_BLOCKED_IPV6_RANGES = [
    ipaddress.ip_network("::1/128"),          # Loopback
    ipaddress.ip_network("fc00::/7"),         # Unique local
    ipaddress.ip_network("fe80::/10"),        # Link-local
    ipaddress.ip_network("ff00::/8"),         # Multicast
]


def is_ip_blocked_for_ssrf(ip_str: str) -> bool:
    """
    Prueft ob eine IP-Adresse in einem blockierten Range liegt.

    Args:
        ip_str: IP-Adresse als String

    Returns:
        True wenn blockiert, False wenn erlaubt
    """
    try:
        ip_obj = ipaddress.ip_address(ip_str)

        if ip_obj.version == 4:
            for blocked_range in SSRF_BLOCKED_IP_RANGES:
                if ip_obj in blocked_range:
                    return True
        else:  # IPv6
            for blocked_range in SSRF_BLOCKED_IPV6_RANGES:
                if ip_obj in blocked_range:
                    return True

        return False

    except ValueError:
        # Ungueltige IP - sicherheitshalber blockieren
        return True


def validate_url_for_ssrf(url: str) -> Tuple[bool, str]:
    """
    Validiert eine URL gegen SSRF-Angriffe.

    M.1 CRITICAL: Diese Funktion MUSS vor allen HTTP-Aufrufen mit
    user-kontrollierten URLs aufgerufen werden!

    Args:
        url: Die zu validierende URL

    Returns:
        Tuple[bool, str]: (is_valid, error_message)
        - True, "" wenn URL sicher ist
        - False, error_message wenn URL blockiert wird

    Example:
        is_valid, error = validate_url_for_ssrf(webhook_url)
        if not is_valid:
            raise ValueError(f"Ungueltige Webhook-URL: {error}")
    """
    if not url:
        return False, "URL darf nicht leer sein"

    # Parse URL
    try:
        parsed = urlparse(url)
    except Exception:
        return False, "Ungueltige URL-Syntax"

    # Protokoll pruefen
    if parsed.scheme not in ("http", "https"):
        return False, f"Nur HTTP/HTTPS erlaubt, nicht '{parsed.scheme}'"

    hostname = parsed.hostname
    if not hostname:
        return False, "Hostname fehlt in URL"

    # Bekannte gefaehrliche Hostnames blockieren
    dangerous_hostnames = [
        "localhost",
        "127.0.0.1",
        "::1",
        "0.0.0.0",
        "metadata.google.internal",      # GCP Metadata
        "metadata.google",               # GCP Metadata
        "169.254.169.254",              # AWS/GCP/Azure Metadata
        "fd00::1",                       # IPv6 local
    ]

    hostname_lower = hostname.lower()
    if hostname_lower in dangerous_hostnames:
        return False, f"Hostname '{hostname}' ist nicht erlaubt (Sicherheitsrisiko)"

    # DNS-Aufloesung und IP-Pruefung
    try:
        # Alle IP-Adressen fuer den Hostname abrufen
        ip_addresses = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)

        for addr_info in ip_addresses:
            ip_str = addr_info[4][0]
            if is_ip_blocked_for_ssrf(ip_str):
                logger.warning(
                    "ssrf_blocked_ip",
                    url=url,
                    hostname=hostname,
                    resolved_ip=ip_str,
                    message="Webhook-URL resolves zu blockierter IP"
                )
                return False, f"URL resolves zu interner Adresse ({ip_str}) - nicht erlaubt"

    except socket.gaierror as e:
        # DNS-Aufloesung fehlgeschlagen
        return False, f"Hostname '{hostname}' konnte nicht aufgeloest werden"
    except socket.timeout:
        return False, f"DNS-Timeout fuer '{hostname}'"
    except Exception as e:
        logger.error(
            "ssrf_validation_error",
            url=url,
            error=str(e)
        )
        return False, "Fehler bei URL-Validierung"

    # URL ist sicher
    return True, ""


async def validate_url_for_ssrf_async(url: str) -> Tuple[bool, str]:
    """
    Async Version der SSRF-Validierung.

    Verwendet ThreadPool fuer DNS-Aufloesung um Event-Loop nicht zu blockieren.

    Args:
        url: Die zu validierende URL

    Returns:
        Tuple[bool, str]: (is_valid, error_message)
    """
    import asyncio

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, validate_url_for_ssrf, url)


# =============================================================================
# SECURITY: HTTP Header Sanitization (PHASE 10 FIX)
# =============================================================================
# Prevents CRLF injection / HTTP Response Splitting attacks
# Reference: CWE-113, OWASP HTTP Response Splitting

def sanitize_filename_for_header(filename: str) -> str:
    """Sanitize filename for use in Content-Disposition header.

    Removes CRLF characters to prevent HTTP Response Splitting attacks
    and encodes the filename using RFC 5987 for Unicode support.

    Args:
        filename: Original filename (may contain Unicode, CRLF)

    Returns:
        Safe filename header value with proper encoding

    Security:
        - Strips CR (\\r), LF (\\n), and NULL (\\x00) characters
        - Removes other control characters (ASCII 0-31 except tab)
        - Removes dangerous characters (<, >, ", \\, /) that can cause XSS or header issues
        - Removes path traversal attempts (..)
        - Limits filename length to 255 characters
    """
    if not filename:
        return "download"

    # SECURITY: Remove CRLF and NULL characters completely
    safe_name = filename.replace('\r', '').replace('\n', '').replace('\x00', '')

    # Remove any other control characters (ASCII 0-31 except tab)
    safe_name = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', safe_name)

    # SECURITY: Remove dangerous characters that can break headers or cause XSS
    # - Angle brackets: potential XSS vectors
    # - Double quotes: can break Content-Disposition format
    # - Backslash/forward slash: path traversal
    # - Pipe, ampersand, semicolon: command injection patterns
    safe_name = re.sub(r'[<>"\\/|&;]', '', safe_name)

    # SECURITY: Remove path traversal patterns
    safe_name = safe_name.replace('..', '')

    # Limit filename length to prevent buffer overflow attacks
    if len(safe_name) > 255:
        # Keep extension
        parts = safe_name.rsplit('.', 1)
        if len(parts) == 2 and len(parts[1]) < 20:
            safe_name = parts[0][:255 - len(parts[1]) - 1] + '.' + parts[1]
        else:
            safe_name = safe_name[:255]

    return safe_name or "download"


def build_content_disposition(filename: str, disposition: str = "attachment") -> str:
    """Build a safe Content-Disposition header value.

    Uses RFC 5987 encoding for proper Unicode support while
    maintaining backwards compatibility with ASCII-only clients.

    Args:
        filename: Original filename
        disposition: 'attachment' (download) or 'inline' (display)

    Returns:
        Safe Content-Disposition header value

    Example:
        >>> build_content_disposition("Rechnung_Müller.pdf")
        'attachment; filename="Rechnung_M_ller.pdf"; filename*=UTF-8\'\'Rechnung_M%C3%BCller.pdf'
    """
    safe_name = sanitize_filename_for_header(filename)

    # Create ASCII fallback (replace non-ASCII with underscore)
    ascii_name = safe_name.encode('ascii', 'replace').decode('ascii').replace('?', '_')

    # RFC 5987 encoding for the full Unicode filename
    encoded_name = quote(safe_name, safe='')

    # Return header with both fallback and encoded filename
    return f'{disposition}; filename="{ascii_name}"; filename*=UTF-8\'\'{encoded_name}'


def sanitize_email_header(value: str) -> str:
    """Sanitize email header values to prevent header injection attacks.

    Removes CRLF characters that could be used to inject additional headers.

    Args:
        value: Raw header value (e.g., subject, to address)

    Returns:
        Sanitized header value safe for email headers

    Security:
        - Prevents email header injection (CWE-93)
        - Removes CR, LF, and NULL characters
    """
    if not value:
        return ""
    return value.replace('\r', '').replace('\n', '').replace('\x00', '')


# =============================================================================
# TOTP Replay Protection
# =============================================================================
# SECURITY FIX: Verhindert mehrfache Verwendung desselben TOTP-Codes
# innerhalb seines Gueltigkeitsfensters (30s + Toleranz)

TOTP_REPLAY_PREFIX = "totp_used:"
TOTP_REPLAY_TTL_SECONDS = 90  # 30s Intervall + 30s Window + 30s Puffer
_totp_used_fallback: Dict[str, datetime] = {}


async def check_totp_replay(user_id: str, code: str) -> bool:
    """
    Prueft ob ein TOTP-Code bereits verwendet wurde (Replay-Schutz).

    Args:
        user_id: Benutzer-ID
        code: Der zu pruefende TOTP-Code

    Returns:
        True wenn der Code bereits verwendet wurde (REPLAY!)
        False wenn der Code noch nicht verwendet wurde

    Security:
        - Verhindert Replay-Angriffe bei gestohlenem TOTP-Code
        - Jeder Code kann nur EINMAL verwendet werden
        - TTL von 90 Sekunden deckt das Gueltigkeitsfenster ab
    """
    # Hash des Codes mit User-ID fuer Eindeutigkeit
    code_hash = hashlib.sha256(f"{user_id}:{code}".encode()).hexdigest()[:32]
    key = f"{TOTP_REPLAY_PREFIX}{code_hash}"

    redis = await _get_redis_client()

    if redis is not None:
        try:
            exists = await redis.exists(key)
            return bool(exists)
        except Exception as e:
            logger.warning(
                "totp_replay_check_redis_failed",
                error_type=type(e).__name__,
                user_id=user_id[:8] + "..." if len(user_id) > 8 else user_id
            )

    # Fallback: In-Memory Check
    _cleanup_totp_fallback()
    return key in _totp_used_fallback


async def mark_totp_used(user_id: str, code: str) -> bool:
    """
    Markiert einen TOTP-Code als verwendet.

    Args:
        user_id: Benutzer-ID
        code: Der verwendete TOTP-Code

    Returns:
        True wenn erfolgreich markiert
        False bei Fehler (aber Login wird NICHT blockiert)

    Security:
        - Muss NACH erfolgreicher Verifikation aufgerufen werden
        - Speichert nur Hash, nicht den Code selbst
    """
    code_hash = hashlib.sha256(f"{user_id}:{code}".encode()).hexdigest()[:32]
    key = f"{TOTP_REPLAY_PREFIX}{code_hash}"

    redis = await _get_redis_client()

    if redis is not None:
        try:
            await redis.setex(key, TOTP_REPLAY_TTL_SECONDS, "1")
            logger.debug(
                "totp_code_marked_used",
                user_id=user_id[:8] + "..." if len(user_id) > 8 else user_id,
                ttl_seconds=TOTP_REPLAY_TTL_SECONDS
            )
            return True
        except Exception as e:
            logger.warning(
                "totp_mark_used_redis_failed",
                error_type=type(e).__name__,
                user_id=user_id[:8] + "..." if len(user_id) > 8 else user_id
            )

    # Fallback: In-Memory
    _totp_used_fallback[key] = datetime.now(tz=timezone.utc)
    return True


def _cleanup_totp_fallback() -> None:
    """Entfernt abgelaufene TOTP-Eintraege aus dem Fallback-Speicher."""
    now = datetime.now(tz=timezone.utc)
    expired_keys = [
        key for key, timestamp in _totp_used_fallback.items()
        if (now - timestamp).total_seconds() > TOTP_REPLAY_TTL_SECONDS
    ]
    for key in expired_keys:
        del _totp_used_fallback[key]

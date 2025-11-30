"""
Authentication and security utilities for Ablage-System.

Handles JWT token generation/validation, password hashing, and token blacklisting.
All error messages in German for user-facing responses.

Token-Blacklist: Redis-basiert mit In-Memory-Fallback für Skalierbarkeit.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
import secrets

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

    for jti in expired:
        del _token_blacklist_fallback[jti]

    if expired:
        logger.debug("token_blacklist_cleanup", removed=len(expired))

    return len(expired)


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
    encoded_jwt = jwt.encode(
        to_encode,
        settings.SECRET_KEY,
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
    encoded_jwt = jwt.encode(
        to_encode,
        settings.SECRET_KEY,
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
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
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
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
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

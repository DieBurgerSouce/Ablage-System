"""
FastAPI dependency injection functions.

Handles authentication, database sessions, and authorization.
All error messages in German.
"""

from typing import Optional, Generator
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import sessionmaker
import structlog

logger = structlog.get_logger(__name__)

from app.core.config import settings
from app.core.security import decode_token, verify_token_type, extract_user_id_from_token
from app.db.models import User
from app.services.user_service import UserService


# ==================== Database Dependencies ====================

# Create async engine
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_pre_ping=settings.DB_POOL_PRE_PING,
)

# Create async session maker
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> Generator[AsyncSession, None, None]:
    """
    Dependency for getting database session.

    Yields:
        AsyncSession: Database session

    Usage:
        @app.get("/endpoint")
        async def endpoint(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


# ==================== Authentication Dependencies ====================

# HTTP Bearer token scheme
security = HTTPBearer(
    scheme_name="JWT",
    description="JWT Bearer token authentication",
    auto_error=True
)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    Dependency for getting current authenticated user from JWT token.

    Args:
        credentials: HTTP Bearer credentials
        db: Database session

    Returns:
        Current authenticated user

    Raises:
        HTTPException: If token is invalid or user not found

    Usage:
        @app.get("/endpoint")
        async def endpoint(user: User = Depends(get_current_user)):
            ...
    """
    token = credentials.credentials

    # Decode and validate token (async for Redis blacklist check)
    try:
        payload = await decode_token(token)
        verify_token_type(payload, "access")
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("token_validation_failed", error=str(e), error_type=type(e).__name__)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentifizierung fehlgeschlagen",  # Authentication failed
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Extract user ID from token
    user_id_str = payload.get("sub")
    if not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungültiges Token-Format",  # Invalid token format
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Convert string UUID to UUID object
    try:
        user_id = UUID(user_id_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungültige Benutzer-ID im Token",  # Invalid user ID in token
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Get user from database
    user = await UserService.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Benutzer nicht gefunden",  # User not found
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Dependency for ensuring user is active.

    Args:
        current_user: Current authenticated user

    Returns:
        Active user

    Raises:
        HTTPException: If user is inactive

    Usage:
        @app.get("/endpoint")
        async def endpoint(user: User = Depends(get_current_active_user)):
            ...
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Benutzerkonto ist deaktiviert",  # User account is deactivated
        )
    return current_user


async def get_current_superuser(
    current_user: User = Depends(get_current_active_user)
) -> User:
    """
    Dependency for ensuring user is a superuser (admin).

    Args:
        current_user: Current active user

    Returns:
        Superuser

    Raises:
        HTTPException: If user is not a superuser

    Usage:
        @app.delete("/admin/user/{user_id}")
        async def delete_user(
            user_id: UUID,
            admin: User = Depends(get_current_superuser)
        ):
            ...
    """
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nur Administratoren haben Zugriff auf diese Funktion",  # Only admins have access
        )
    return current_user


# ==================== Optional Authentication ====================

async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False)),
    db: AsyncSession = Depends(get_db)
) -> Optional[User]:
    """
    Dependency for optionally getting current user.
    Returns None if no valid token is provided.

    Args:
        credentials: Optional HTTP Bearer credentials
        db: Database session

    Returns:
        User if authenticated, None otherwise

    Usage:
        @app.get("/public-endpoint")
        async def endpoint(user: Optional[User] = Depends(get_current_user_optional)):
            if user:
                # Authenticated behavior
            else:
                # Anonymous behavior
    """
    if not credentials:
        return None

    try:
        token = credentials.credentials
        payload = await decode_token(token)
        verify_token_type(payload, "access")

        user_id_str = payload.get("sub")
        if not user_id_str:
            return None

        user_id = UUID(user_id_str)
        user = await UserService.get_user_by_id(db, user_id)

        if user and user.is_active:
            return user

    except Exception:
        pass

    return None


# ==================== Rate Limiting Dependencies ====================

from fastapi import Request


async def check_rate_limit(
    request: Request,
    current_user: User = Depends(get_current_active_user)
) -> User:
    """
    Dependency for checking rate limits using Redis backend.

    Implements distributed rate limiting with user-based and IP-based limits.

    Args:
        request: FastAPI request object
        current_user: Current active user

    Returns:
        User if within rate limits

    Raises:
        HTTPException: If rate limit exceeded
    """
    from app.core.rate_limiting import (
        get_redis_storage,
        ip_whitelist,
        get_remote_address,
        rate_limit_metrics,
    )

    # Record request in metrics
    rate_limit_metrics.record_request()

    # Check whitelist
    ip = get_remote_address(request)
    if ip_whitelist.is_whitelisted(ip):
        rate_limit_metrics.record_whitelisted()
        return current_user

    # Get Redis storage
    storage = await get_redis_storage()
    if not storage or not storage.is_available:
        # Redis unavailable - fail open (allow request)
        return current_user

    # Determine rate limit based on user tier
    user_tier = getattr(current_user, "tier", "free")
    is_admin = current_user.is_superuser

    if is_admin:
        limit = 10000  # Effectively unlimited
        window = 3600  # 1 hour
    elif user_tier == "premium":
        limit = 100
        window = 3600  # 1 hour
    else:
        limit = 10
        window = 3600  # 1 hour

    # Check rate limit
    key = f"rate_limit:{current_user.id}:{window}"
    current_count = await storage.increment(key, window)

    if current_count > limit:
        rate_limit_metrics.record_rate_limited()
        raise HTTPException(
            status_code=429,
            detail="Ratenlimit überschritten. Bitte versuchen Sie es später erneut.",
            headers={"Retry-After": str(window)},
        )

    return current_user


async def check_ocr_rate_limit(
    request: Request,
    current_user: User = Depends(get_current_active_user)
) -> User:
    """
    Dependency for OCR-specific rate limits.

    OCR operations have stricter limits due to resource intensity.

    Args:
        request: FastAPI request object
        current_user: Current active user

    Returns:
        User if within OCR rate limits

    Raises:
        HTTPException: If OCR rate limit exceeded
    """
    from app.core.rate_limiting import (
        get_redis_storage,
        ip_whitelist,
        get_remote_address,
        rate_limit_metrics,
        RateLimitTier,
    )

    # Record request
    rate_limit_metrics.record_request()

    # Check whitelist
    ip = get_remote_address(request)
    if ip_whitelist.is_whitelisted(ip):
        rate_limit_metrics.record_whitelisted()
        return current_user

    # Get Redis storage
    storage = await get_redis_storage()
    if not storage or not storage.is_available:
        return current_user

    # Determine OCR rate limit based on user tier
    user_tier = getattr(current_user, "tier", "free")
    is_admin = current_user.is_superuser

    if is_admin:
        hourly_limit = 10000
        daily_limit = 100000
    elif user_tier == "premium":
        hourly_limit = 100
        daily_limit = 1000
    else:
        hourly_limit = 10
        daily_limit = 50

    # Check hourly limit
    hourly_key = f"ocr_rate_limit:{current_user.id}:hourly"
    hourly_count = await storage.increment(hourly_key, 3600)

    if hourly_count > hourly_limit:
        rate_limit_metrics.record_rate_limited()
        raise HTTPException(
            status_code=429,
            detail=f"OCR-Stundenlimit überschritten ({hourly_limit} Dokumente/Stunde). "
                   f"Bitte versuchen Sie es in einer Stunde erneut.",
            headers={"Retry-After": "3600"},
        )

    # Check daily limit
    daily_key = f"ocr_rate_limit:{current_user.id}:daily"
    daily_count = await storage.increment(daily_key, 86400)

    if daily_count > daily_limit:
        rate_limit_metrics.record_rate_limited()
        raise HTTPException(
            status_code=429,
            detail=f"OCR-Tageslimit überschritten ({daily_limit} Dokumente/Tag). "
                   f"Bitte versuchen Sie es morgen erneut.",
            headers={"Retry-After": "86400"},
        )

    return current_user


async def check_batch_rate_limit(
    request: Request,
    current_user: User = Depends(get_current_active_user)
) -> User:
    """
    Dependency for batch operation rate limits.

    Batch operations have stricter limits to prevent system overload.

    Args:
        request: FastAPI request object
        current_user: Current active user

    Returns:
        User if within batch rate limits

    Raises:
        HTTPException: If batch rate limit exceeded
    """
    from app.core.rate_limiting import (
        get_redis_storage,
        rate_limit_metrics,
    )

    rate_limit_metrics.record_request()

    storage = await get_redis_storage()
    if not storage or not storage.is_available:
        return current_user

    # Batch limits
    user_tier = getattr(current_user, "tier", "free")
    is_admin = current_user.is_superuser

    if is_admin:
        batch_limit = 1000
    elif user_tier == "premium":
        batch_limit = 50
    else:
        batch_limit = 5

    # Check batch limit (per hour)
    batch_key = f"batch_rate_limit:{current_user.id}:hourly"
    batch_count = await storage.increment(batch_key, 3600)

    if batch_count > batch_limit:
        rate_limit_metrics.record_rate_limited()
        raise HTTPException(
            status_code=429,
            detail=f"Stapelverarbeitungs-Limit überschritten ({batch_limit}/Stunde). "
                   f"Bitte versuchen Sie es später erneut.",
            headers={"Retry-After": "3600"},
        )

    return current_user


async def get_rate_limit_status(
    request: Request,
    current_user: User = Depends(get_current_active_user)
) -> dict:
    """
    Get current rate limit status for the user.

    Args:
        request: FastAPI request object
        current_user: Current active user

    Returns:
        Dictionary with rate limit status
    """
    from app.core.rate_limiting import (
        get_redis_storage,
        ip_whitelist,
        get_remote_address,
    )

    ip = get_remote_address(request)
    user_tier = getattr(current_user, "tier", "free")
    is_admin = current_user.is_superuser

    # Determine limits
    if is_admin:
        hourly_limit = 10000
        daily_limit = 100000
        batch_limit = 1000
    elif user_tier == "premium":
        hourly_limit = 100
        daily_limit = 1000
        batch_limit = 50
    else:
        hourly_limit = 10
        daily_limit = 50
        batch_limit = 5

    # Get current usage from Redis
    storage = await get_redis_storage()
    usage = {
        "hourly_used": 0,
        "daily_used": 0,
        "batch_used": 0,
        "hourly_reset_in": 3600,
        "daily_reset_in": 86400,
        "batch_reset_in": 3600,
    }

    if storage and storage.is_available:
        try:
            redis = storage._redis
            user_id = str(current_user.id)

            # Get actual counts using GET (not INCR)
            hourly_key = f"ocr_rate_limit:{user_id}:hourly"
            daily_key = f"ocr_rate_limit:{user_id}:daily"
            batch_key = f"batch_rate_limit:{user_id}:hourly"

            hourly_val = await redis.get(hourly_key)
            daily_val = await redis.get(daily_key)
            batch_val = await redis.get(batch_key)

            usage["hourly_used"] = int(hourly_val) if hourly_val else 0
            usage["daily_used"] = int(daily_val) if daily_val else 0
            usage["batch_used"] = int(batch_val) if batch_val else 0

            # Get TTLs for reset times
            hourly_ttl = await redis.ttl(hourly_key)
            daily_ttl = await redis.ttl(daily_key)
            batch_ttl = await redis.ttl(batch_key)

            usage["hourly_reset_in"] = max(0, hourly_ttl) if hourly_ttl > 0 else 3600
            usage["daily_reset_in"] = max(0, daily_ttl) if daily_ttl > 0 else 86400
            usage["batch_reset_in"] = max(0, batch_ttl) if batch_ttl > 0 else 3600

        except Exception as e:
            logger.warning("rate_limit_status_error", error=str(e))

    return {
        "user_id": str(current_user.id),
        "tier": user_tier,
        "is_admin": is_admin,
        "is_whitelisted": ip_whitelist.is_whitelisted(ip),
        "limits": {
            "ocr_hourly": hourly_limit,
            "ocr_daily": daily_limit,
            "batch_hourly": batch_limit,
        },
        "usage": usage,
        "rate_limiting_enabled": storage.is_available if storage else False,
    }


# ==================== Document Ownership ====================

async def verify_document_ownership(
    document_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> bool:
    """
    Verify that the current user owns the specified document.

    Args:
        document_id: Document ID to check
        current_user: Current authenticated user
        db: Database session

    Returns:
        True if user owns document or is superuser

    Raises:
        HTTPException: If user doesn't own document
    """
    from app.db.models import Document
    from sqlalchemy import select

    # Superusers can access all documents
    if current_user.is_superuser:
        return True

    # Check document ownership
    result = await db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.owner_id == current_user.id
        )
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Zugriff auf dieses Dokument verweigert",  # Access to this document denied
        )

    return True

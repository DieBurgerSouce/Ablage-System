"""
FastAPI dependency injection functions.

Handles authentication, database sessions, and authorization.
All error messages in German.
"""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

logger = structlog.get_logger(__name__)

from app.core.config import settings
from app.core.safe_errors import safe_error_log
from app.core.security import decode_token, verify_token_type, extract_user_id_from_token
from app.db.models import User, UserCompany, Company
from app.services.user_service import UserService

# Re-export company context functions for convenient access
from app.middleware.company_context import get_current_company_id

# Alias for backwards compatibility (used in alerts.py)
get_company_id = get_current_company_id


# ==================== Database Dependencies ====================

# W1/1a Engine-Konsolidierung: Dieses Modul baute frueher eine EIGENE Engine
# samt get_db. Folgen: (a) der RLS-Kontext (SET LOCAL in require_company,
# Session aus app.db.database) erreichte die Endpoint-Sessions nie, (b) zwei
# Connection-Pools gegen dieselbe DB, (c) Test-/Dependency-Overrides deckten
# nur eine der beiden get_db-Varianten ab. Jetzt ist app.db.database die
# einzige Quelle: get_db IST get_db_session (identisches Callable ->
# FastAPI-Dependency-Cache liefert pro Request dieselbe Session, SET LOCAL
# aus require_company greift, Overrides wirken ueberall).
# Commit-Semantik unveraendert: commit bei Erfolg, rollback bei Exception
# (DatabaseManager.get_session verhaelt sich identisch zur alten get_db).
from app.db.database import DatabaseManager, get_db_session

_db_manager = DatabaseManager()
engine = _db_manager.engine
AsyncSessionLocal = _db_manager.session_maker
get_db = get_db_session


async def set_rls_context(
    session: AsyncSession,
    user_id: str,
    is_admin: bool = False
) -> None:
    """
    Set Row Level Security context for the current session.

    This must be called before any queries that are protected by RLS policies.
    The settings are LOCAL to the current transaction.

    Args:
        session: Database session
        user_id: Current user's UUID as string
        is_admin: Whether user has admin privileges (bypasses RLS)

    Usage:
        async with AsyncSessionLocal() as session:
            # WICHTIG: User-Model hat is_superuser, nicht is_admin!
            await set_rls_context(session, str(user.id), user.is_superuser)
            # Now RLS policies will filter results
    """
    from sqlalchemy import text
    from uuid import UUID as UUIDType

    # K.4 SECURITY FIX: Validiere user_id Format vor RLS-Context-Setzen
    try:
        validated_user_id = UUIDType(str(user_id))
    except ValueError:
        logger.warning(
            "rls_context_invalid_user_id",
            attempted_value=str(user_id)[:50]  # Trunkiert für Sicherheit
        )
        raise ValueError(f"Ungültige User-ID für RLS-Context: {str(user_id)[:8]}...")

    # SECURITY + KORREKTHEIT: set_config() statt 'SET LOCAL x = :param'.
    # PostgreSQL/asyncpg akzeptiert bei 'SET LOCAL' KEINE Bind-Parameter
    # (ProgrammingError) -> die alte Variante war doppelt kaputt: nie aufgerufen
    # UND syntaktisch unausfuehrbar. set_config(...,:v,true) ist parametrisiert
    # (injection-sicher) und transaktions-lokal (is_local=true).
    #
    # F-P1-001 (Perception-Audit 2026-07-12): persist_rls_gucs statt direkter
    # set_configs — ein commit() im Handler beendet die Transaktion und verlor
    # den Kontext fuer den Rest des Requests (Upload-500 via ''-Cast bzw.
    # "Could not refresh instance"). Der after_begin-Listener re-appliziert
    # die GUCs jetzt in jeder Folgetransaktion derselben Request-Session.
    # 'app.current_user_is_superuser': Migration-210-superuser_bypass-Policies
    # nutzen diese Variable (nicht 'app.is_admin') — konsistent mitsetzen.
    from app.db.session import persist_rls_gucs

    await persist_rls_gucs(
        session,
        {
            "app.current_user_id": str(validated_user_id),
            "app.is_admin": "true" if is_admin else "false",
            "app.current_user_is_superuser": "true" if is_admin else "false",
        },
    )


# ==================== Authentication Dependencies ====================

# HTTP Bearer token scheme
security = HTTPBearer(
    scheme_name="JWT",
    description="JWT Bearer token authentication",
    auto_error=True
)

# ==================== G03: httpOnly-Cookie-Auth (additiv) ====================
# Access-/Refresh-Token koennen ZUSAETZLICH zum Authorization-Header als
# httpOnly-Cookie transportiert werden -> kein XSS-Exfiltrationsrisiko (Token
# nicht aus JS lesbar). Header-basierte API-Clients bleiben unveraendert.
# Cookie-basierte (Browser-)Clients werden bei state-changing Requests
# automatisch durch die CSRFMiddleware geschuetzt (Double-Submit-Cookie,
# bearer_token_bypass=True -> nur Nicht-Bearer-Requests muessen CSRF mitsenden).
ACCESS_COOKIE_NAME = "access_token"
REFRESH_COOKIE_NAME = "refresh_token"

# Optionaler Bearer (auto_error=False) -> erlaubt Fallback auf Cookie, ohne dass
# FastAPI bei fehlendem Header vorzeitig abbricht.
_bearer_optional = HTTPBearer(
    scheme_name="JWT",
    description="JWT Bearer token authentication",
    auto_error=False,
)


def set_auth_cookies(
    response: Response,
    access_token: str,
    refresh_token: Optional[str] = None,
) -> None:
    """Setzt Access-/Refresh-Token als httpOnly-Cookies (G03).

    secure nur in Produktion (sonst wird das Cookie ueber http:// im Dev nie
    gesetzt). SameSite=lax erlaubt normale Top-Level-Navigation, blockt aber
    Cross-Site-POSTs. Max-Age = jeweilige Token-Lebensdauer aus den Settings.
    """
    secure = settings.is_production
    response.set_cookie(
        key=ACCESS_COOKIE_NAME,
        value=access_token,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )
    if refresh_token is not None:
        response.set_cookie(
            key=REFRESH_COOKIE_NAME,
            value=refresh_token,
            max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
            httponly=True,
            secure=secure,
            samesite="lax",
            path="/",
        )


def clear_auth_cookies(response: Response) -> None:
    """Entfernt die Auth-Cookies (Logout, G03)."""
    response.delete_cookie(ACCESS_COOKIE_NAME, path="/")
    response.delete_cookie(REFRESH_COOKIE_NAME, path="/")


async def _get_access_token(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_optional),
) -> str:
    """Access-Token aus Authorization-Header ODER httpOnly-Cookie (G03).

    Header hat Vorrang (bestehende API-Clients unveraendert). Fehlt beides, wird
    - wie zuvor bei HTTPBearer(auto_error=True) - mit 403 abgewiesen.
    """
    if credentials and credentials.credentials:
        return credentials.credentials
    cookie_token = request.cookies.get(ACCESS_COOKIE_NAME)
    if cookie_token:
        return cookie_token
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Not authenticated",
    )


async def get_current_user(
    token: str = Depends(_get_access_token),
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
    # Decode and validate token (async for Redis blacklist check)
    try:
        payload = await decode_token(token)
        verify_token_type(payload, "access")
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("token_validation_failed", **safe_error_log(e))
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

    # Q.1 SECURITY FIX: is_active Prüfung direkt in get_current_user()
    # Verhindert, dass deaktivierte User mit gültigem Token API-Calls machen
    if not user.is_active:
        logger.warning(
            "inactive_user_api_access_blocked",
            user_id=str(user.id),
            email=user.email[:20] if user.email else None
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Benutzerkonto ist deaktiviert",  # User account is deactivated
        )

    # K2 (Trust-Folge, 2026-07-14): Befristete Zugaenge (z.B. tax_advisor via
    # Einladung) tragen access_until — nach Ablauf ist JEDER API-Zugriff zu
    # verweigern. Vorher wurde das Feld nur gesetzt, aber im Auth-Pfad nie
    # geprueft: abgelaufene Steuerberater-Konten behielten vollen Zugriff.
    if user.access_until is not None and user.access_until < datetime.now(timezone.utc):
        logger.warning(
            "expired_user_api_access_blocked",
            user_id=str(user.id),
            access_until=user.access_until.isoformat(),
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Der befristete Zugang ist abgelaufen",  # Temporary access expired
        )

    # RLS-USER-KONTEXT (Root-Cause-Fix RLS-light): Setzt app.current_user_id /
    # app.is_admin / app.current_user_is_superuser auf der Request-Session, BEVOR
    # user-scoped Policies (companies, user_companies, invoices, documents-alt)
    # abgefragt werden. Unter dem frueheren Superuser-App-User war das folgenlos
    # (BYPASSRLS); als NOBYPASSRLS-Rolle 'ablage_app' lieferten diese Policies
    # sonst 0 Zeilen -> "keine Firma ausgewaehlt". Muss VOR
    # _resolve_accessible_company_ids stehen (fragt user_companies ab).
    # Dependency-Cache garantiert: dieselbe get_db-Session wie der Endpoint.
    await set_rls_context(db, str(user.id), bool(user.is_superuser))

    # B1 Multi-Tenant: zugängliche Firmen-IDs am User-Objekt hinterlegen, damit
    # synchrone Checks (validate_company_access) ohne erneuten DB-Zugriff funktionieren.
    # Das User-Modell hat KEINE company_id-Spalte – die Firmen kommen aus UserCompany.
    setattr(
        user,
        "accessible_company_ids",
        await _resolve_accessible_company_ids(db, user),
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


# ==================== Multi-Tenant Company Validation ====================


def validate_company_access(company_id: UUID, current_user: User) -> None:
    """
    Validate that the current user has access to the specified company.

    SECURITY: Prevents Cross-Company Authorization Bypass (CWE-863).
    Users can only access data for their own company unless they are superadmins.

    Args:
        company_id: The company ID being accessed
        current_user: The authenticated user

    Raises:
        HTTPException: 403 if user doesn't have access to the company

    Usage:
        @app.get("/endpoint")
        async def endpoint(
            company_id: UUID = Query(...),
            current_user: User = Depends(get_current_active_user),
        ):
            validate_company_access(company_id, current_user)
            ...
    """
    # Superusers can access any company
    if current_user.is_superuser:
        return

    # B1 Multi-Tenant: Das User-Modell hat KEINE company_id-Spalte. Die zugänglichen
    # Firmen werden in get_current_user über UserCompany aufgelöst und am User-Objekt
    # als ``accessible_company_ids`` hinterlegt (frozenset von UUIDs).
    accessible: Optional[frozenset[UUID]] = getattr(
        current_user, "accessible_company_ids", None
    )

    if not accessible:
        logger.warning(
            "user_without_company_accessing_company_data",
            user_id=str(current_user.id),
            requested_company_id=str(company_id),
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Benutzer ist keiner Firma zugeordnet",
        )

    if company_id not in accessible:
        logger.warning(
            "cross_company_access_attempt",
            user_id=str(current_user.id),
            requested_company_id=str(company_id),
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Kein Zugriff auf diese Firma",
        )


async def get_validated_company_id(
    company_id: UUID,
    current_user: User = Depends(get_current_active_user),
) -> UUID:
    """
    Dependency that validates company access and returns the company_id.

    SECURITY: Use this dependency when you need validated company_id.

    Args:
        company_id: The company ID from query/path parameter
        current_user: The authenticated user (injected)

    Returns:
        The validated company_id

    Raises:
        HTTPException: 403 if user doesn't have access

    Usage:
        @app.get("/endpoint")
        async def endpoint(
            validated_company_id: UUID = Depends(get_validated_company_id),
        ):
            # validated_company_id is safe to use
            ...
    """
    validate_company_access(company_id, current_user)
    return company_id


# ==================== Multi-Tenant Company Resolution (B1) ====================


async def _resolve_accessible_company_ids(db: AsyncSession, user: User) -> frozenset[UUID]:
    """Ermittelt alle aktiven Firmen-IDs, auf die der User via UserCompany Zugriff hat."""
    result = await db.execute(
        select(UserCompany.company_id)
        .join(Company, Company.id == UserCompany.company_id)
        .where(UserCompany.user_id == user.id)
        .where(Company.is_active == True)  # noqa: E712
        .where(Company.deleted_at.is_(None))
    )
    return frozenset(result.scalars().all())


async def get_user_company_id(db: AsyncSession, user: User) -> Optional[UUID]:
    """Ermittelt die aktive Company-ID des Users via UserCompany-Tabelle.

    SECURITY FIX (B1): Das User-Modell hat KEIN Firmen-Feld - die Firma muss
    über ``UserCompany`` geholt werden. Ersetzt das vorher genutzte (latent broken)
    Direktzugriff-Pattern auf eine nicht existierende User-Spalte, das im Betrieb
    einen ``AttributeError`` ausgelöst hätte. Zentralisiert aus invoices.py.

    Returns:
        Aktive Company-ID oder None, wenn keine Zuordnung existiert.
    """
    # 1. Aktuelle Firma (is_current=True).
    # W1/1a: Defensiv gegen Bestandsdaten mit MEHREREN is_current=True (vor
    # Migration 268 verhinderte das kein Constraint): deterministisch die
    # neueste Mitgliedschaft statt MultipleResultsFound (-> HTTP 500).
    result = await db.execute(
        select(UserCompany.company_id)
        .join(Company, Company.id == UserCompany.company_id)
        .where(UserCompany.user_id == user.id)
        .where(UserCompany.is_current == True)  # noqa: E712
        .where(Company.is_active == True)  # noqa: E712
        .where(Company.deleted_at.is_(None))
        .order_by(UserCompany.created_at.desc(), UserCompany.id.desc())
        .limit(1)
    )
    current_company_id = result.scalars().first()

    if current_company_id:
        return current_company_id

    # 2. Fallback: Erste verfügbare Firma
    result = await db.execute(
        select(UserCompany.company_id)
        .join(Company, Company.id == UserCompany.company_id)
        .where(UserCompany.user_id == user.id)
        .where(Company.is_active == True)  # noqa: E712
        .where(Company.deleted_at.is_(None))
        .order_by(UserCompany.created_at)
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _require_user_company_id(db: AsyncSession, user: User) -> UUID:
    """Wie ``get_user_company_id``, wirft aber 403, wenn keine Firma zugeordnet ist."""
    company_id = await get_user_company_id(db, user)
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Kein Unternehmen zugeordnet",
        )
    return company_id


async def get_user_company_id_dep(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> UUID:
    """FastAPI-Dependency: liefert die aktive Firmen-ID des Users.

    Wirft 403, wenn keine Firmenzuordnung existiert. Nutzung als Endpoint-Parameter::

        company_id: UUID = Depends(get_user_company_id_dep)
    """
    return await _require_user_company_id(db, current_user)


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

    except Exception as e:
        logger.debug("optional_user_lookup_failed", **safe_error_log(e))

    return None


# ==================== Rate Limiting Dependencies ====================

from fastapi import Request


def resolve_user_hourly_rate_limit(user: User) -> int:
    """Ermittelt das Stunden-Request-Budget eines Nutzers (F-P1-003).

    Prioritaet:
    1. Superuser -> RATE_LIMIT_ADMIN_HOURLY
    2. Admin-Console-Override users.rate_limit_hourly (falls gesetzt, > 0)
    3. Tier-Setting (premium -> RATE_LIMIT_PREMIUM_HOURLY, sonst FREE)

    Vorher waren 10/h (free) / 100/h (premium) hart codiert — normale
    Buero-Nutzer waren damit nach 10 Such-/Listen-Aufrufen eine Stunde
    gesperrt, und weder die Settings noch das User-Override wirkten.
    """
    if user.is_superuser:
        return settings.RATE_LIMIT_ADMIN_HOURLY
    custom_hourly = getattr(user, "rate_limit_hourly", None)
    if custom_hourly and custom_hourly > 0:
        return int(custom_hourly)
    if getattr(user, "tier", "free") == "premium":
        return settings.RATE_LIMIT_PREMIUM_HOURLY
    return settings.RATE_LIMIT_FREE_HOURLY


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

    # BUGFIX (2026-06-12): Ist Rate-Limiting EXPLIZIT deaktiviert
    # (RATE_LIMIT_ENABLED=False, z.B. Dev/Test), liefert get_redis_storage()
    # None - das ist KEIN Redis-Ausfall. Fail-Closed (L.1) gilt nur fuer den
    # Storage-Ausfall bei AKTIVIERTEM Rate-Limiting; sonst waren diese
    # Endpoints bei deaktiviertem Limiter pauschal tot (503).
    if not settings.RATE_LIMIT_ENABLED:
        return current_user

    # Get Redis storage
    storage = await get_redis_storage()
    if not storage or not storage.is_available:
        # L.1 SECURITY FIX: Fail-Closed statt Fail-Open
        # Bei Redis-Ausfall wird Anfrage abgelehnt statt durchgelassen
        logger.error(
            "rate_limit_redis_unavailable",
            message="Redis nicht verfügbar - Rate Limiting nicht möglich"
        )
        raise HTTPException(
            status_code=503,
            detail="Sicherheitsdienst temporär nicht verfügbar. Bitte später erneut versuchen.",
            headers={"Retry-After": "60"}
        )

    # Determine rate limit based on user tier
    # F-P1-003 (Perception-Audit 2026-07-12): Werte waren hart codiert
    # (Free 10/h!) und ignorierten sowohl die RATE_LIMIT_*_HOURLY-Settings
    # als auch das Admin-Console-Override users.rate_limit_hourly.
    limit = resolve_user_hourly_rate_limit(current_user)
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

    # BUGFIX (2026-06-12): Explizit deaktiviertes Rate-Limiting ist kein
    # Redis-Ausfall - kein Fail-Closed (siehe check_rate_limit).
    if not settings.RATE_LIMIT_ENABLED:
        return current_user

    # Get Redis storage
    storage = await get_redis_storage()
    if not storage or not storage.is_available:
        # L.1 SECURITY FIX: Fail-Closed für OCR Rate Limiting
        # Bei Redis-Ausfall werden OCR-Requests abgelehnt um GPU-Überlastung zu verhindern
        logger.error(
            "ocr_rate_limit_redis_unavailable",
            message="Redis nicht verfügbar - OCR Rate Limiting nicht möglich"
        )
        raise HTTPException(
            status_code=503,
            detail="OCR-Service temporär nicht verfügbar. Bitte später erneut versuchen.",
            headers={"Retry-After": "60"}
        )

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

    # BUGFIX (2026-06-12): Explizit deaktiviertes Rate-Limiting ist kein
    # Redis-Ausfall - kein Fail-Closed (siehe check_rate_limit).
    if not settings.RATE_LIMIT_ENABLED:
        return current_user

    storage = await get_redis_storage()
    if not storage or not storage.is_available:
        # L.1 SECURITY FIX: Fail-Closed für Batch Rate Limiting
        logger.error(
            "batch_rate_limit_redis_unavailable",
            message="Redis nicht verfügbar - Batch Rate Limiting nicht möglich"
        )
        raise HTTPException(
            status_code=503,
            detail="Batch-Service temporär nicht verfügbar. Bitte später erneut versuchen.",
            headers={"Retry-After": "60"}
        )

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


async def check_destructive_admin_rate_limit(
    request: Request,
    admin: User = Depends(get_current_superuser)
) -> User:
    """
    Dependency for rate limiting destructive admin operations.

    Destructive operations (clear_queue, bulk_cancel, bulk_retry) have
    STRICT limits even for admins to prevent accidental or malicious
    mass operations that could DoS the system.

    Limits:
    - 10 destructive operations per minute
    - 50 destructive operations per hour

    Args:
        request: FastAPI request object
        admin: Current superuser (already verified)

    Returns:
        User if within destructive operation rate limits

    Raises:
        HTTPException: If destructive operation rate limit exceeded
    """
    from app.core.rate_limiting import (
        get_redis_storage,
        rate_limit_metrics,
    )

    rate_limit_metrics.record_request()

    # BUGFIX (2026-06-12): Explizit deaktiviertes Rate-Limiting ist kein
    # Redis-Ausfall - kein Fail-Closed (siehe check_rate_limit).
    if not settings.RATE_LIMIT_ENABLED:
        return admin

    storage = await get_redis_storage()
    if not storage or not storage.is_available:
        # Fail closed for destructive operations - require Redis to be available
        raise HTTPException(
            status_code=503,
            detail="Rate-Limiting-Service nicht verfügbar. "
                   "Destruktive Operationen erfordern funktionierendes Rate-Limiting."
        )

    # Strict limits for destructive operations
    MINUTE_LIMIT = 10
    HOURLY_LIMIT = 50

    user_id = str(admin.id)

    # Check per-minute limit (burst protection)
    minute_key = f"destructive_rate_limit:{user_id}:minute"
    minute_count = await storage.increment(minute_key, 60)

    if minute_count > MINUTE_LIMIT:
        rate_limit_metrics.record_rate_limited()
        raise HTTPException(
            status_code=429,
            detail=f"Destruktive Operationen-Limit überschritten "
                   f"({MINUTE_LIMIT}/Minute). Bitte warten Sie eine Minute.",
            headers={"Retry-After": "60"},
        )

    # Check hourly limit (sustained protection)
    hourly_key = f"destructive_rate_limit:{user_id}:hourly"
    hourly_count = await storage.increment(hourly_key, 3600)

    if hourly_count > HOURLY_LIMIT:
        rate_limit_metrics.record_rate_limited()
        raise HTTPException(
            status_code=429,
            detail=f"Destruktive Operationen-Stundenlimit überschritten "
                   f"({HOURLY_LIMIT}/Stunde). Bitte versuchen Sie es später erneut.",
            headers={"Retry-After": "3600"},
        )

    return admin


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
            logger.warning("rate_limit_status_error", **safe_error_log(e))

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
    # P.2 SECURITY FIX: is_deleted Prüfung hinzugefügt (GDPR Art. 17 Compliance)
    result = await db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.owner_id == current_user.id,
            Document.deleted_at.is_(None)  # P.2 FIX: Gelöschte Dokumente ausschließen
        )
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Zugriff auf dieses Dokument verweigert",  # Access to this document denied
        )

    return True


# ==================== API Key Authentication ====================

API_KEY_PREFIX = "ablage_"


async def get_user_from_api_key(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    Dependency für Authentifizierung mit API-Key.

    Unterstützt sowohl JWT-Token als auch API-Keys.
    API-Keys beginnen mit 'ablage_'.

    Args:
        credentials: HTTP Bearer credentials
        db: Database session

    Returns:
        Authentifizierter User

    Raises:
        HTTPException: Bei ungültigem Token/Key

    Usage:
        @app.get("/api/v1/documents")
        async def get_documents(user: User = Depends(get_user_from_api_key)):
            ...
    """
    token = credentials.credentials

    # Prüfe ob es ein API-Key ist
    if token.startswith(API_KEY_PREFIX):
        from app.services.api_key_service import get_api_key_service

        service = get_api_key_service()
        result = await service.validate_api_key(db, token)

        if not result:
            logger.warning(
                "api_key_validation_failed",
                key_prefix=token[:16] + "..." if len(token) > 16 else token
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Ungültiger oder abgelaufener API-Key",
                headers={"WWW-Authenticate": "Bearer"},
            )

        api_key, user = result
        return user

    # Andernfalls: JWT-Token verwenden
    return await get_current_user(credentials, db)


async def get_user_with_api_key_permission(
    required_permission: str,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    Dependency die Benutzer authentifiziert und API-Key-Berechtigung prüft.

    Bei JWT-Token werden alle Berechtigungen gewährt.
    Bei API-Key wird die spezifische Berechtigung geprüft.

    Args:
        required_permission: Benötigte Berechtigung (z.B. "read:documents")
        credentials: HTTP Bearer credentials
        db: Database session

    Returns:
        Authentifizierter User mit Berechtigung

    Raises:
        HTTPException: Bei fehlender Berechtigung
    """
    token = credentials.credentials

    if token.startswith(API_KEY_PREFIX):
        from app.services.api_key_service import get_api_key_service

        service = get_api_key_service()
        result = await service.validate_api_key(db, token)

        if not result:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Ungültiger oder abgelaufener API-Key",
                headers={"WWW-Authenticate": "Bearer"},
            )

        api_key, user = result

        # Prüfe Berechtigung
        if not service.has_permission(api_key, required_permission):
            logger.warning(
                "api_key_permission_denied",
                key_name=api_key.name,
                required_permission=required_permission,
                key_permissions=api_key.permissions
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"API-Key hat keine '{required_permission}' Berechtigung"
            )

        return user

    # JWT-Token: Voller Zugriff (Berechtigungen werden durch User-Rolle geprüft)
    return await get_current_user(credentials, db)


def require_api_key_permission(permission: str):
    """
    Factory für Permission-abhängige Dependency.

    Usage:
        @app.get("/documents")
        async def get_documents(
            user: User = Depends(require_api_key_permission("read:documents"))
        ):
            ...
    """
    async def dependency(
        credentials: HTTPAuthorizationCredentials = Depends(security),
        db: AsyncSession = Depends(get_db)
    ) -> User:
        return await get_user_with_api_key_permission(permission, credentials, db)

    return dependency


# ==================== Admin Authorization ====================

async def check_datev_export_rate_limit(
    request: Request,
    current_user: User = Depends(get_current_active_user)
) -> User:
    """
    Dependency für DATEV-Export-spezifisches Rate Limiting.

    DATEV-Exporte sind ressourcenintensive Operationen mit ThreadPool-Execution.
    Limit: 10 Exports pro Stunde pro User (Admins: 100).

    Args:
        request: FastAPI request object
        current_user: Current active user

    Returns:
        User if within DATEV rate limits

    Raises:
        HTTPException: If DATEV export rate limit exceeded
    """
    from app.core.rate_limiting import (
        get_redis_storage,
        rate_limit_metrics,
    )

    rate_limit_metrics.record_request()

    # BUGFIX (2026-06-12): Explizit deaktiviertes Rate-Limiting ist kein
    # Redis-Ausfall - kein Fail-Closed (siehe check_rate_limit).
    if not settings.RATE_LIMIT_ENABLED:
        return current_user

    storage = await get_redis_storage()
    if not storage or not storage.is_available:
        # L.1 SECURITY FIX: Fail-Closed für DATEV-Export Rate Limiting
        logger.error(
            "datev_export_rate_limit_redis_unavailable",
            message="Redis nicht verfügbar - DATEV-Export nicht möglich"
        )
        raise HTTPException(
            status_code=503,
            detail="DATEV-Export temporär nicht verfügbar. Bitte später erneut versuchen.",
            headers={"Retry-After": "60"}
        )

    # DATEV export limits - stricter due to CPU-intensive ThreadPool operations
    is_admin = current_user.is_superuser

    if is_admin:
        hourly_limit = 100
    else:
        hourly_limit = 10

    # Check hourly limit
    hourly_key = f"datev_export_limit:{current_user.id}:hourly"
    hourly_count = await storage.increment(hourly_key, 3600)

    if hourly_count > hourly_limit:
        rate_limit_metrics.record_rate_limited()
        logger.warning(
            "datev_export_rate_limited",
            user_id=str(current_user.id),
            count=hourly_count,
            limit=hourly_limit,
        )
        raise HTTPException(
            status_code=429,
            detail=f"DATEV-Export-Limit erreicht ({hourly_limit} Exports/Stunde). "
                   f"Bitte versuchen Sie es in einer Stunde erneut.",
            headers={"Retry-After": "3600"},
        )

    return current_user


async def require_admin(
    current_user: User = Depends(get_current_active_user)
) -> User:
    """
    Dependency für Admin-Berechtigungsprüfung.

    Prüft ob der aktuelle Benutzer Admin/Superuser ist.

    Args:
        current_user: Aktueller aktiver Benutzer

    Returns:
        Admin-Benutzer

    Raises:
        HTTPException: Wenn Benutzer kein Admin ist

    Usage:
        @app.delete("/admin/users/{user_id}")
        async def delete_user(
            user_id: UUID,
            admin: User = Depends(require_admin)
        ):
            ...

        # Oder als Router-Dependency:
        @router.post("/admin-action", dependencies=[Depends(require_admin)])
        async def admin_action():
            ...
    """
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nur Administratoren haben Zugriff auf diese Funktion",
        )
    return current_user


# Alias für require_admin (Backwards-Kompatibilität)
get_current_admin_user = require_admin


class RateLimitDependency:
    """
    Konfigurierbare Rate-Limit-Dependency für FastAPI.

    Ermöglicht das Erstellen von benutzerdefinierten Rate-Limits
    für verschiedene Endpunkte mit individuellen Limits und Zeitfenstern.

    Usage:
        # In Router-Datei:
        check_read_rate_limit = RateLimitDependency(
            requests_per_hour=100,
            key_prefix="my_endpoint_read"
        )

        @router.get("/items", dependencies=[Depends(check_read_rate_limit)])
        async def list_items():
            ...
    """

    def __init__(
        self,
        requests_per_hour: int = 100,
        key_prefix: str = "rate_limit",
    ):
        """
        Initialisiert die Rate-Limit-Dependency.

        Args:
            requests_per_hour: Maximale Anfragen pro Stunde
            key_prefix: Prefix für den Redis-Key
        """
        self.requests_per_hour = requests_per_hour
        self.key_prefix = key_prefix
        self.window = 3600  # 1 Stunde in Sekunden

    async def __call__(
        self,
        request: Request,
        current_user: User = Depends(get_current_active_user),
    ) -> User:
        """
        Prüft das Rate-Limit für den aktuellen Benutzer.

        Args:
            request: FastAPI Request-Objekt
            current_user: Aktueller aktiver Benutzer

        Returns:
            Benutzer wenn innerhalb des Limits

        Raises:
            HTTPException: Wenn Rate-Limit überschritten
        """
        from app.core.rate_limiting import (
            get_redis_storage,
            ip_whitelist,
            get_remote_address,
            rate_limit_metrics,
        )

        # Request in Metriken erfassen
        rate_limit_metrics.record_request()

        # Whitelist prüfen
        ip = get_remote_address(request)
        if ip_whitelist.is_whitelisted(ip):
            rate_limit_metrics.record_whitelisted()
            return current_user

        # BUGFIX (2026-06-12): Explizit deaktiviertes Rate-Limiting ist kein
        # Redis-Ausfall - kein Fail-Closed (siehe check_rate_limit).
        if not settings.RATE_LIMIT_ENABLED:
            return current_user

        # Redis-Speicher holen
        storage = await get_redis_storage()
        if not storage or not storage.is_available:
            # L.1 SECURITY FIX: Fail-Closed für RateLimitDependency
            logger.error(
                "rate_limit_dependency_redis_unavailable",
                key_prefix=self.key_prefix,
                message="Redis nicht verfügbar - Rate-Limit nicht prüfbar"
            )
            raise HTTPException(
                status_code=503,
                detail="Service temporär nicht verfügbar. Bitte später erneut versuchen.",
                headers={"Retry-After": "60"}
            )

        # Admins haben effektiv unbegrenzte Anfragen
        if current_user.is_superuser:
            return current_user

        # Rate-Limit prüfen
        key = f"{self.key_prefix}:{current_user.id}:{self.window}"
        current_count = await storage.increment(key, self.window)

        if current_count > self.requests_per_hour:
            rate_limit_metrics.record_rate_limited()
            raise HTTPException(
                status_code=429,
                detail=f"Ratenlimit überschritten ({self.requests_per_hour} Anfragen/Stunde). "
                       f"Bitte versuchen Sie es später erneut.",
                headers={"Retry-After": str(self.window)},
            )

        return current_user

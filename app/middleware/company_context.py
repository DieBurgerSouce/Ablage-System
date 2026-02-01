"""Company Context Middleware fuer Multi-Company Support.

Dieses Modul stellt die Infrastruktur fuer Multi-Mandanten-Faehigkeit bereit:
- ContextVar fuer aktuelle Company-ID (Thread-/Async-safe)
- Middleware zum Setzen des Company-Kontexts
- Dependency fuer FastAPI-Endpoints

Verwendung in Endpoints:
    @router.get("/kasse/entries")
    async def get_entries(
        company: Company = Depends(require_company),
        db: AsyncSession = Depends(get_db)
    ):
        # company ist bereits validiert
        entries = await cash_service.get_entries(db, company.id)
        ...
"""

from contextvars import ContextVar
from typing import Optional
from uuid import UUID

import jwt
import sqlalchemy as sa
import structlog
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.base import BaseHTTPMiddleware

from app.db.database import get_db
from app.db.models import Company, UserCompany, User

logger = structlog.get_logger(__name__)

# ContextVar fuer aktuelle Company-ID (Thread-/Async-safe)
_current_company_id: ContextVar[Optional[UUID]] = ContextVar(
    "current_company_id",
    default=None
)


def get_current_company_id() -> Optional[UUID]:
    """Gibt die aktuelle Company-ID aus dem Context zurueck.

    Returns:
        Company-ID oder None wenn nicht gesetzt
    """
    return _current_company_id.get()


def set_company_context(company_id: Optional[UUID]) -> None:
    """Setzt die aktuelle Company-ID im Context.

    Args:
        company_id: Company-ID oder None zum Loeschen
    """
    _current_company_id.set(company_id)


class CompanyContextMiddleware(BaseHTTPMiddleware):
    """Middleware zum Setzen des Company-Kontexts aus JWT/Session.

    Liest die aktuelle Company-ID aus:
    1. X-Company-ID Header (fuer explizite Auswahl)
    2. JWT Claims (falls vorhanden)
    3. User's is_current Company aus user_companies

    Setzt die ID im ContextVar fuer alle nachfolgenden Operationen.
    """

    async def dispatch(self, request: Request, call_next):
        """Verarbeitet Request und setzt Company-Kontext."""

        company_id: Optional[UUID] = None

        # 1. Versuche X-Company-ID Header
        company_header = request.headers.get("X-Company-ID")
        if company_header:
            try:
                company_id = UUID(company_header)
                logger.debug(
                    "company_context_from_header",
                    company_id=str(company_id)
                )
            except ValueError:
                logger.warning(
                    "invalid_company_header",
                    header_value=company_header
                )

        # 2. Falls kein Header, aus User-Session (wird in require_company gemacht)
        # Hier setzen wir nur wenn explizit angegeben

        if company_id:
            set_company_context(company_id)

        try:
            response = await call_next(request)
            return response
        finally:
            # Context zuruecksetzen nach Request
            set_company_context(None)


async def get_user_current_company(
    user_id: UUID,
    db: AsyncSession
) -> Optional[Company]:
    """Holt die aktuelle Company eines Users.

    Args:
        user_id: User-ID
        db: Datenbank-Session

    Returns:
        Company oder None
    """
    # Finde is_current=True fuer User
    result = await db.execute(
        select(UserCompany)
        .where(UserCompany.user_id == user_id)
        .where(UserCompany.is_current == True)
    )
    user_company = result.scalar_one_or_none()

    if not user_company:
        # Fallback: Erste Company des Users
        result = await db.execute(
            select(UserCompany)
            .where(UserCompany.user_id == user_id)
            .order_by(UserCompany.created_at)
            .limit(1)
        )
        user_company = result.scalar_one_or_none()

    if user_company:
        # Lade Company
        result = await db.execute(
            select(Company)
            .where(Company.id == user_company.company_id)
            .where(Company.is_active == True)
            .where(Company.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    return None


async def switch_company(
    user_id: UUID,
    company_id: UUID,
    db: AsyncSession
) -> bool:
    """Wechselt die aktuelle Company eines Users.

    Args:
        user_id: User-ID
        company_id: Ziel-Company-ID
        db: Datenbank-Session

    Returns:
        True wenn erfolgreich

    Raises:
        ValueError: Wenn User keinen Zugriff auf Company hat
        RuntimeError: Wenn DB-Operation fehlschlaegt
    """
    # Pruefe ob User Zugriff hat
    result = await db.execute(
        select(UserCompany)
        .where(UserCompany.user_id == user_id)
        .where(UserCompany.company_id == company_id)
    )
    target_uc = result.scalar_one_or_none()

    if not target_uc:
        raise ValueError(f"Benutzer hat keinen Zugriff auf Firma {company_id}")

    # CWE-362 FIX: Row-Level Locking mit SELECT FOR UPDATE
    # Lock timeout verhindert Deadlocks, FOR UPDATE sichert Atomaritaet
    try:
        await db.execute(sa.text("SET LOCAL lock_timeout = '5s'"))

        # Row-Level Lock auf alle UserCompany-Eintraege des Users
        await db.execute(
            select(UserCompany)
            .where(UserCompany.user_id == user_id)
            .with_for_update()
        )

        await db.execute(
            update(UserCompany)
            .where(UserCompany.user_id == user_id)
            .values(is_current=False)
        )
        await db.execute(
            update(UserCompany)
            .where(UserCompany.user_id == user_id)
            .where(UserCompany.company_id == company_id)
            .values(is_current=True)
        )
        await db.commit()
    except sa.exc.OperationalError as e:
        # Lock timeout oder connection error
        await db.rollback()
        logger.error(
            "company_switch_lock_timeout",
            user_id=str(user_id)[:8],
            error_type=type(e).__name__
        )
        raise RuntimeError("Firmenwechsel fehlgeschlagen - bitte erneut versuchen") from e
    except sa.exc.SQLAlchemyError as e:
        await db.rollback()
        logger.error(
            "company_switch_failed",
            user_id=str(user_id)[:8],
            error_type=type(e).__name__
        )
        raise RuntimeError("Firmenwechsel fehlgeschlagen") from e

    # Update Context
    set_company_context(company_id)

    logger.info(
        "company_switched",
        user_id=str(user_id),
        company_id=str(company_id)
    )

    return True


async def _get_user_from_request_optional(
    request: Request,
    db: AsyncSession,
) -> Optional[User]:
    """Extract user from request, return None if not authenticated.

    P1 DRY-FIX: Nutzt _extract_user_from_token() fuer gemeinsame Logik.

    Args:
        request: FastAPI Request
        db: Datenbank-Session

    Returns:
        User oder None wenn nicht authentifiziert
    """
    return await _extract_user_from_token(request, db)


async def get_current_company(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Optional[Company]:
    """Dependency: Holt die aktuelle Company (optional).

    U.4 SECURITY FIX: Ownership-Validierung bei Company-ID aus Header.

    Verwendung:
        @router.get("/optional-company")
        async def endpoint(company: Optional[Company] = Depends(get_current_company)):
            ...

    Returns:
        Company oder None
    """
    # Erst aus ContextVar (gesetzt von Middleware aus X-Company-ID Header)
    company_id = get_current_company_id()

    # Get user without circular import
    user = await _get_user_from_request_optional(request, db)

    if company_id:
        # U.4 SECURITY FIX: Wenn company_id aus Header kommt UND User bekannt,
        # MUSS Ownership geprueft werden um Company Context Bypass zu verhindern
        if user:
            # P1 DRY-FIX: Nutzt _get_user_company() Helper
            user_company = await _get_user_company(user.id, company_id, db)

            if not user_company:
                # U.4 SECURITY FIX: User hat KEINEN Zugriff auf diese Company!
                # Header wurde manipuliert - ignoriere und verwende User's aktuelle Company
                logger.warning(
                    "company_context_bypass_blocked",
                    user_id=str(user.id),
                    attempted_company_id=str(company_id),
                    message="X-Company-ID Header ohne Berechtigung blockiert"
                )
                # Setze Context zurück und hole User's echte Company
                set_company_context(None)
                return await get_user_current_company(user.id, db)

        # Company-ID ist valide (entweder User hat Zugriff oder kein User bekannt)
        result = await db.execute(
            select(Company)
            .where(Company.id == company_id)
            .where(Company.is_active == True)
            .where(Company.deleted_at.is_(None))
        )
        company = result.scalar_one_or_none()
        if company:
            return company

    # Fallback: Aus User's is_current Company
    if user:
        return await get_user_current_company(user.id, db)

    return None


async def set_rls_company_context(db: AsyncSession, company_id: UUID) -> None:
    """Setzt die PostgreSQL Session-Variable fuer RLS.

    WICHTIG: Diese Funktion muss vor allen DB-Operationen aufgerufen werden,
    die durch RLS geschuetzt sind!

    I.7 HIGH: SQL-Injection Fix - Verwendet set_config() statt f-string

    Args:
        db: Datenbank-Session
        company_id: Company-ID fuer RLS-Filter
    """
    try:
        # I.7 CRITICAL: Strenge UUID-Validierung gegen SQL-Injection
        from uuid import UUID as UUIDType
        company_id_str = str(company_id)
        # Validierung: Nur gültige UUIDs erlauben
        validated_uuid = UUIDType(company_id_str)  # Wirft ValueError bei ungültiger UUID

        # I.7 HIGH: Verwende set_config() mit Parameter statt f-string SET
        # set_config() ist sicher gegen SQL-Injection da es den Wert als String behandelt
        await db.execute(
            sa.text("SELECT set_config('app.current_company_id', :cid, true)"),
            {"cid": str(validated_uuid)}
        )
        logger.debug(
            "rls_context_set",
            company_id=str(validated_uuid)
        )
    except ValueError as e:
        # Ungültige UUID - könnte Injection-Versuch sein
        logger.warning(
            "rls_context_invalid_uuid",
            attempted_value=str(company_id)[:50],  # Trunkiert für Sicherheit
            error_type="ValueError"
        )
    except sa.exc.SQLAlchemyError as e:
        # CWE-390/391 FIX: Spezifische Exception, RLS-Failure ist KRITISCH
        logger.error(
            "rls_context_failed",
            error_type=type(e).__name__,
            company_id=str(company_id)[:8] + "...",  # Nur Prefix fuer Logs (PII)
            message="RLS-Context konnte nicht gesetzt werden - Datenzugriff ohne Tenant-Filter!"
        )
        # Bei Fehler: Session zurueckrollen um "aborted transaction" zu vermeiden
        try:
            await db.rollback()
        except sa.exc.SQLAlchemyError as rollback_err:
            # CWE-391 FIX: Rollback-Fehler ist KRITISCH, nicht sekundaer!
            logger.critical(
                "rls_rollback_failed",
                error_type=type(rollback_err).__name__,
                original_error=type(e).__name__,
                message="Rollback nach RLS-Fehler fehlgeschlagen - DB-Session in undefiniertem Zustand"
            )
            # Raise kombinierter Fehler
            raise RuntimeError(
                f"RLS-Fehler: {type(e).__name__}, Rollback-Fehler: {type(rollback_err).__name__}"
            ) from e
        # WICHTIG: Exception weitergeben um unsicheren Zustand zu verhindern
        raise


async def enable_rls_bypass(db: AsyncSession) -> None:
    """P1.1 SECURITY: Aktiviert RLS-Bypass fuer Service-Account Operationen.

    WARNUNG: Nur fuer Hintergrund-Tasks, Migrations, und Admin-Operationen!
    Niemals fuer normale User-Requests verwenden!

    Args:
        db: Datenbank-Session

    Raises:
        sa.exc.SQLAlchemyError: Wenn RLS-Bypass nicht aktiviert werden kann
    """
    try:
        await db.execute(
            sa.text("SELECT set_config('app.rls_bypass', 'true', true)")
        )
        # CWE-390/391 FIX: RLS-Bypass ist sicherheitskritisch - Audit-Level Logging
        logger.warning(
            "rls_bypass_enabled",
            audit_event="RLS_BYPASS_START",
            message="RLS-Bypass aktiviert - Cross-Tenant Zugriff moeglich"
        )
    except sa.exc.SQLAlchemyError as e:
        # CWE-390 FIX: Spezifische Exception statt bare except
        logger.error(
            "rls_bypass_enable_failed",
            error_type=type(e).__name__,
            message="RLS-Bypass konnte nicht aktiviert werden"
        )
        raise  # RLS-Bypass-Fehler ist kritisch!


async def disable_rls_bypass(db: AsyncSession) -> None:
    """P1.1 SECURITY: Deaktiviert RLS-Bypass.

    Sollte IMMER nach Service-Operationen aufgerufen werden!

    Args:
        db: Datenbank-Session

    Raises:
        sa.exc.SQLAlchemyError: Wenn RLS-Bypass nicht deaktiviert werden kann
    """
    try:
        await db.execute(
            sa.text("SELECT set_config('app.rls_bypass', 'false', true)")
        )
        # CWE-390/391 FIX: Audit-Level Logging fuer RLS-Bypass Ende
        logger.warning(
            "rls_bypass_disabled",
            audit_event="RLS_BYPASS_END",
            message="RLS-Bypass deaktiviert - Normale Tenant-Isolation wiederhergestellt"
        )
    except sa.exc.SQLAlchemyError as e:
        # CWE-390 FIX: Spezifische Exception statt bare except
        logger.error(
            "rls_bypass_disable_failed",
            error_type=type(e).__name__,
            message="RLS-Bypass konnte nicht deaktiviert werden - KRITISCH!"
        )
        raise  # RLS-Bypass-Fehler ist kritisch!


from contextlib import asynccontextmanager


@asynccontextmanager
async def rls_bypass_context(db: AsyncSession):
    """P1.1 SECURITY: Context Manager fuer RLS-Bypass.

    Verwendung:
        async with rls_bypass_context(db):
            # Hier koennen cross-tenant Operationen ausgefuehrt werden
            ...
        # RLS ist wieder aktiv

    Args:
        db: Datenbank-Session

    WARNUNG: Nur fuer Celery-Tasks, Migrations und System-Operationen!
    """
    try:
        await enable_rls_bypass(db)
        yield
    finally:
        await disable_rls_bypass(db)


from app.core.safe_errors import safe_error_detail
from app.core.security import decode_token, verify_token_type
from app.services.user_service import UserService


# =============================================================================
# P1 DRY-FIX: Konsolidierte Helper-Funktionen
# =============================================================================


async def _get_user_company(
    user_id: UUID,
    company_id: UUID,
    db: AsyncSession
) -> Optional[UserCompany]:
    """Get UserCompany relationship with proper error handling.

    P1 DRY-FIX: Konsolidierte Query-Funktion statt 5x identischer Code.

    Args:
        user_id: User-ID
        company_id: Company-ID
        db: Datenbank-Session

    Returns:
        UserCompany oder None wenn keine Beziehung existiert
    """
    result = await db.execute(
        select(UserCompany)
        .where(UserCompany.user_id == user_id)
        .where(UserCompany.company_id == company_id)
    )
    return result.scalar_one_or_none()


async def _extract_user_from_token(
    request: Request,
    db: AsyncSession,
) -> Optional[User]:
    """Core logic for extracting user from JWT token.

    P1 DRY-FIX: Gemeinsame Logik fuer optional und required User extraction.

    Args:
        request: FastAPI Request
        db: Datenbank-Session

    Returns:
        Tuple of (User or None, error_detail or None)
        - If user found: (user, None)
        - If no token: (None, None) - nicht authentifiziert aber kein Fehler
        - If token invalid: (None, "error message") - Fehler aufgetreten
    """
    # Try to get from request state first (set by middleware)
    if hasattr(request.state, "user") and request.state.user:
        return request.state.user

    # Try to get from Authorization header
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None

    token = auth_header[7:]  # Remove "Bearer " prefix
    if not token:
        return None

    try:
        payload = await decode_token(token)
        verify_token_type(payload, "access")

        user_id_str = payload.get("sub")
        if not user_id_str:
            return None

        user_id = UUID(user_id_str)
        user = await UserService.get_user_by_id(db, user_id)

        if user and user.is_active:
            return user
        return None

    except (ValueError, jwt.PyJWTError) as e:
        # CWE-390 FIX: Spezifische Exceptions statt bare except
        logger.debug("token_decode_failed", error_type=type(e).__name__)
        return None


async def _get_user_from_request_required(
    request: Request,
    db: AsyncSession,
) -> User:
    """Extract authenticated user from request, raise 401 if not found.

    P1 DRY-FIX: Nutzt _extract_user_from_token() und wirft HTTPException bei Fehler.

    Args:
        request: FastAPI Request
        db: Datenbank-Session

    Returns:
        User (garantiert aktiv)

    Raises:
        HTTPException 401: Wenn nicht authentifiziert
    """
    user = await _extract_user_from_token(request, db)

    if not user:
        # Detaillierte Fehlermeldung basierend auf Header-Praesenz
        auth_header = request.headers.get("Authorization", "")
        if not auth_header or not auth_header.startswith("Bearer "):
            raise HTTPException(
                status_code=401,
                detail="Nicht authentifiziert"
            )
        # Token war vorhanden aber ungueltig
        raise HTTPException(
            status_code=401,
            detail="Authentifizierung fehlgeschlagen"
        )

    return user


async def require_company(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Company:
    """Dependency: Erfordert eine aktuelle Company.

    Verwendung:
        @router.get("/kasse/entries")
        async def get_entries(
            company: Company = Depends(require_company),
            db: AsyncSession = Depends(get_db)
        ):
            ...

    Returns:
        Company (validiert und aktiv)

    Raises:
        HTTPException 400: Keine Firma ausgewaehlt
        HTTPException 401: Nicht authentifiziert
        HTTPException 403: Kein Zugriff auf Firma
    """
    # Get authenticated user (raises 401 if not authenticated)
    current_user = await _get_user_from_request_required(request, db)

    company = await get_current_company(request, db)

    if not company:
        raise HTTPException(
            status_code=400,
            detail="Keine Firma ausgewaehlt. Bitte waehlen Sie zuerst eine Firma aus."
        )

    # I.5 CRITICAL: Validiere Zugriff IMMER (User ist garantiert vorhanden)
    # P1 DRY-FIX: Nutzt _get_user_company() Helper
    user_company = await _get_user_company(current_user.id, company.id, db)

    if not user_company:
        logger.warning(
            "company_access_denied",
            user_id=str(current_user.id),
            company_id=str(company.id)
        )
        raise HTTPException(
            status_code=403,
            detail="Sie haben keinen Zugriff auf diese Firma."
        )

    # Setze Context fuer nachfolgende Operationen
    set_company_context(company.id)

    # Setze PostgreSQL RLS Context
    await set_rls_company_context(db, company.id)

    return company


async def require_cash_permission(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Company:
    """Dependency: Erfordert Kassenbuch-Berechtigung.

    Raises:
        HTTPException 403: Keine Berechtigung fuer Kassenbuchfuehrung
    """
    company = await require_company(request, db)
    user = await _get_user_from_request_required(request, db)

    # P1 DRY-FIX: Nutzt _get_user_company() Helper
    user_company = await _get_user_company(user.id, company.id, db)

    # J.2 CRITICAL FIX: user_company=None bedeutet KEIN Zugriff, nicht Durchlassen!
    if not user_company:
        logger.warning(
            "cash_permission_no_company_link",
            user_id=str(user.id),
            company_id=str(company.id)
        )
        raise HTTPException(
            status_code=403,
            detail="Sie haben keinen Zugriff auf diese Firma."
        )

    # Pruefe Kassenberechtigung
    if not user_company.can_manage_cash:
        # Admins und Owners haben immer Zugriff
        if user_company.role not in ["owner", "admin"]:
            raise HTTPException(
                status_code=403,
                detail="Sie haben keine Berechtigung fuer die Kassenbuchfuehrung."
            )

    return company


async def require_expense_approval_permission(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Company:
    """Dependency: Erfordert Spesenfreigabe-Berechtigung.

    Raises:
        HTTPException 403: Keine Berechtigung fuer Spesenfreigabe
    """
    company = await require_company(request, db)
    user = await _get_user_from_request_required(request, db)

    # P1 DRY-FIX: Nutzt _get_user_company() Helper
    user_company = await _get_user_company(user.id, company.id, db)

    # J.2 CRITICAL FIX: user_company=None bedeutet KEIN Zugriff!
    if not user_company:
        logger.warning(
            "expense_approval_no_company_link",
            user_id=str(user.id),
            company_id=str(company.id)
        )
        raise HTTPException(
            status_code=403,
            detail="Sie haben keinen Zugriff auf diese Firma."
        )

    # Pruefe Spesenfreigabe-Berechtigung
    if not user_company.can_approve_expenses:
        # Admins und Owners haben immer Zugriff
        if user_company.role not in ["owner", "admin"]:
            raise HTTPException(
                status_code=403,
                detail="Sie haben keine Berechtigung zur Spesenfreigabe."
            )

    return company

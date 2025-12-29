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

import sqlalchemy as sa
import structlog
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
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

    # Setze alle is_current auf False
    result = await db.execute(
        select(UserCompany)
        .where(UserCompany.user_id == user_id)
    )
    user_companies = result.scalars().all()

    for uc in user_companies:
        uc.is_current = (uc.company_id == company_id)

    await db.commit()

    # Update Context
    set_company_context(company_id)

    logger.info(
        "company_switched",
        user_id=str(user_id),
        company_id=str(company_id)
    )

    return True


from app.api.dependencies import get_current_user_optional


async def get_current_company(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
) -> Optional[Company]:
    """Dependency: Holt die aktuelle Company (optional).

    Verwendung:
        @router.get("/optional-company")
        async def endpoint(company: Optional[Company] = Depends(get_current_company)):
            ...

    Returns:
        Company oder None
    """
    # Erst aus ContextVar
    company_id = get_current_company_id()

    if company_id:
        result = await db.execute(
            select(Company)
            .where(Company.id == company_id)
            .where(Company.is_active == True)
            .where(Company.deleted_at.is_(None))
        )
        company = result.scalar_one_or_none()
        if company:
            return company

    # Fallback: Aus User (Parameter oder request.state)
    user = current_user or getattr(request.state, "user", None)
    if user:
        return await get_user_current_company(user.id, db)

    return None


async def set_rls_company_context(db: AsyncSession, company_id: UUID) -> None:
    """Setzt die PostgreSQL Session-Variable fuer RLS.

    WICHTIG: Diese Funktion muss vor allen DB-Operationen aufgerufen werden,
    die durch RLS geschuetzt sind!

    Args:
        db: Datenbank-Session
        company_id: Company-ID fuer RLS-Filter
    """
    try:
        # PostgreSQL Session-Variable setzen fuer RLS Policies
        # SICHERHEIT: Parameterisierte Query statt String-Interpolation!
        await db.execute(
            sa.text("SET app.current_company_id = :company_id"),
            {"company_id": str(company_id)}
        )
        logger.debug(
            "rls_context_set",
            company_id=str(company_id)
        )
    except Exception as e:
        # SQLite oder andere DBs ohne SET-Support
        logger.debug(
            "rls_context_skip",
            reason=str(e)
        )


from app.api.dependencies import get_current_active_user


async def require_company(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
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
        HTTPException 403: Kein Zugriff auf Firma
    """
    company = await get_current_company(request, db, current_user)

    if not company:
        raise HTTPException(
            status_code=400,
            detail="Keine Firma ausgewaehlt. Bitte waehlen Sie zuerst eine Firma aus."
        )

    # Validiere Zugriff (falls User bekannt)
    user = current_user or getattr(request.state, "user", None)
    if user:
        result = await db.execute(
            select(UserCompany)
            .where(UserCompany.user_id == user.id)
            .where(UserCompany.company_id == company.id)
        )
        user_company = result.scalar_one_or_none()

        if not user_company:
            logger.warning(
                "company_access_denied",
                user_id=str(user.id),
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
    current_user: User = Depends(get_current_active_user),
) -> Company:
    """Dependency: Erfordert Kassenbuch-Berechtigung.

    Raises:
        HTTPException 403: Keine Berechtigung fuer Kassenbuchfuehrung
    """
    company = await require_company(request, db, current_user)
    user = current_user

    if user:
        result = await db.execute(
            select(UserCompany)
            .where(UserCompany.user_id == user.id)
            .where(UserCompany.company_id == company.id)
        )
        user_company = result.scalar_one_or_none()

        if not user_company or not user_company.can_manage_cash:
            # Admins und Owners haben immer Zugriff
            if user_company and user_company.role not in ["owner", "admin"]:
                raise HTTPException(
                    status_code=403,
                    detail="Sie haben keine Berechtigung fuer die Kassenbuchfuehrung."
                )

    return company


async def require_expense_approval_permission(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Company:
    """Dependency: Erfordert Spesenfreigabe-Berechtigung.

    Raises:
        HTTPException 403: Keine Berechtigung fuer Spesenfreigabe
    """
    company = await require_company(request, db, current_user)
    user = current_user

    if user:
        result = await db.execute(
            select(UserCompany)
            .where(UserCompany.user_id == user.id)
            .where(UserCompany.company_id == company.id)
        )
        user_company = result.scalar_one_or_none()

        if not user_company or not user_company.can_approve_expenses:
            # Admins und Owners haben immer Zugriff
            if user_company and user_company.role not in ["owner", "admin"]:
                raise HTTPException(
                    status_code=403,
                    detail="Sie haben keine Berechtigung zur Spesenfreigabe."
                )

    return company

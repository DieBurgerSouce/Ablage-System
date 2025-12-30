"""
Company API Endpoints.

Verwaltet Firmen im Multi-Mandanten-System:
- Firmen-CRUD fuer autorisierte Benutzer
- Firmenwechsel (aktuelle Firma setzen)
- Benutzer-Firmen-Zuordnung

Alle Antworten auf Deutsch.
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
import structlog

from app.api.dependencies import get_db, get_current_active_user
from app.db.models import User, Company, UserCompany
from app.db.schemas import (
    CompanyCreate,
    CompanyUpdate,
    CompanyResponse,
    CompanyListResponse,
    UserCompanyCreate,
    UserCompanyUpdate,
    UserCompanyResponse,
    CompanyRole,
)
from app.middleware.company_context import (
    get_current_company,
    require_company,
    switch_company,
    set_company_context,
)

logger = structlog.get_logger(__name__)

# ==================== Router ====================

router = APIRouter(prefix="/companies", tags=["Firmen"])


# ==================== Company Endpoints ====================

@router.get(
    "",
    response_model=CompanyListResponse,
    summary="Firmen des Benutzers auflisten",
    description="Gibt alle Firmen zurueck, auf die der aktuelle Benutzer Zugriff hat."
)
async def list_companies(
    request: Request,
    skip: int = 0,
    limit: int = 50,
    include_inactive: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> CompanyListResponse:
    """Liste aller Firmen des Benutzers."""

    # Basis-Query mit Join
    query = (
        select(Company)
        .join(UserCompany, UserCompany.company_id == Company.id)
        .where(UserCompany.user_id == current_user.id)
        .where(Company.deleted_at.is_(None))
    )

    if not include_inactive:
        query = query.where(Company.is_active == True)

    # Count total
    count_query = (
        select(func.count())
        .select_from(Company)
        .join(UserCompany, UserCompany.company_id == Company.id)
        .where(UserCompany.user_id == current_user.id)
        .where(Company.deleted_at.is_(None))
    )
    if not include_inactive:
        count_query = count_query.where(Company.is_active == True)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Fetch companies
    query = query.order_by(Company.name).offset(skip).limit(limit)
    result = await db.execute(query)
    companies = result.scalars().all()

    # Get current company ID
    current_company = await get_current_company(request, db)
    current_id = current_company.id if current_company else None

    return CompanyListResponse(
        companies=[
            CompanyResponse(
                id=c.id,
                name=c.name,
                vat_id=c.vat_id,
                tax_number=c.tax_number,
                address_street=c.address_street,
                address_city=c.address_city,
                address_postal_code=c.address_postal_code,
                address_country=c.address_country,
                email=c.email,
                phone=c.phone,
                website=c.website,
                account_chart=c.account_chart,
                fiscal_year_start_month=c.fiscal_year_start_month,
                settings=c.settings or {},
                is_active=c.is_active,
                created_at=c.created_at,
                updated_at=c.updated_at,
            )
            for c in companies
        ],
        total=total,
        current_company_id=current_id,
    )


@router.post(
    "",
    response_model=CompanyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Neue Firma erstellen",
    description="Erstellt eine neue Firma. Der Ersteller wird automatisch als Owner zugewiesen."
)
async def create_company(
    data: CompanyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> CompanyResponse:
    """Erstellt eine neue Firma."""

    # Pruefe ob Firmenname bereits existiert
    existing = await db.execute(
        select(Company)
        .where(Company.name == data.name)
        .where(Company.deleted_at.is_(None))
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Eine Firma mit dem Namen '{data.name}' existiert bereits."
        )

    # Erstelle Firma
    company = Company(
        name=data.name,
        vat_id=data.vat_id,
        tax_number=data.tax_number,
        address_street=data.address_street,
        address_city=data.address_city,
        address_postal_code=data.address_postal_code,
        address_country=data.address_country or "DE",
        email=data.email,
        phone=data.phone,
        website=data.website,
        account_chart=data.account_chart or "SKR03",
        fiscal_year_start_month=data.fiscal_year_start_month or 1,
        settings=data.settings or {},
        is_active=True,
    )
    db.add(company)
    await db.flush()

    # Erstelle UserCompany-Zuordnung als Owner
    user_company = UserCompany(
        user_id=current_user.id,
        company_id=company.id,
        role="owner",
        can_manage_cash=True,
        can_approve_expenses=True,
        is_current=True,  # Neue Firma wird aktuelle Firma
    )
    db.add(user_company)

    # Setze andere Firmen auf is_current=False
    await db.execute(
        select(UserCompany)
        .where(UserCompany.user_id == current_user.id)
        .where(UserCompany.company_id != company.id)
    )
    other_ucs = await db.execute(
        select(UserCompany)
        .where(UserCompany.user_id == current_user.id)
        .where(UserCompany.company_id != company.id)
    )
    for uc in other_ucs.scalars().all():
        uc.is_current = False

    await db.commit()
    await db.refresh(company)

    logger.info(
        "company_created",
        company_id=str(company.id),
        company_name=company.name,
        user_id=str(current_user.id),
    )

    return CompanyResponse(
        id=company.id,
        name=company.name,
        vat_id=company.vat_id,
        tax_number=company.tax_number,
        address_street=company.address_street,
        address_city=company.address_city,
        address_postal_code=company.address_postal_code,
        address_country=company.address_country,
        email=company.email,
        phone=company.phone,
        website=company.website,
        account_chart=company.account_chart,
        fiscal_year_start_month=company.fiscal_year_start_month,
        settings=company.settings or {},
        is_active=company.is_active,
        created_at=company.created_at,
        updated_at=company.updated_at,
    )


@router.get(
    "/current",
    response_model=Optional[CompanyResponse],
    summary="Aktuelle Firma abrufen",
    description="Gibt die aktuell ausgewaehlte Firma des Benutzers zurueck."
)
async def get_current_company_endpoint(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Optional[CompanyResponse]:
    """Gibt die aktuelle Firma zurueck."""

    company = await get_current_company(request, db)

    if not company:
        return None

    return CompanyResponse(
        id=company.id,
        name=company.name,
        vat_id=company.vat_id,
        tax_number=company.tax_number,
        address_street=company.address_street,
        address_city=company.address_city,
        address_postal_code=company.address_postal_code,
        address_country=company.address_country,
        email=company.email,
        phone=company.phone,
        website=company.website,
        account_chart=company.account_chart,
        fiscal_year_start_month=company.fiscal_year_start_month,
        settings=company.settings or {},
        is_active=company.is_active,
        created_at=company.created_at,
        updated_at=company.updated_at,
    )


@router.post(
    "/current/{company_id}",
    response_model=CompanyResponse,
    summary="Aktuelle Firma wechseln",
    description="Wechselt zur angegebenen Firma (setzt is_current)."
)
async def switch_current_company(
    company_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> CompanyResponse:
    """Wechselt die aktuelle Firma."""

    try:
        await switch_company(current_user.id, company_id, db)
    except ValueError as e:
        # SECURITY FIX 29: Generic error message - no internal details
        logger.warning("company_switch_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Firmenwechsel nicht erlaubt."
        )

    # Lade Firma
    result = await db.execute(
        select(Company)
        .where(Company.id == company_id)
    )
    company = result.scalar_one_or_none()

    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Firma nicht gefunden."
        )

    return CompanyResponse(
        id=company.id,
        name=company.name,
        vat_id=company.vat_id,
        tax_number=company.tax_number,
        address_street=company.address_street,
        address_city=company.address_city,
        address_postal_code=company.address_postal_code,
        address_country=company.address_country,
        email=company.email,
        phone=company.phone,
        website=company.website,
        account_chart=company.account_chart,
        fiscal_year_start_month=company.fiscal_year_start_month,
        settings=company.settings or {},
        is_active=company.is_active,
        created_at=company.created_at,
        updated_at=company.updated_at,
    )


@router.get(
    "/{company_id}",
    response_model=CompanyResponse,
    summary="Firma abrufen",
    description="Gibt Details einer spezifischen Firma zurueck."
)
async def get_company(
    company_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> CompanyResponse:
    """Gibt eine spezifische Firma zurueck."""

    # Pruefe Zugriff
    access_result = await db.execute(
        select(UserCompany)
        .where(UserCompany.user_id == current_user.id)
        .where(UserCompany.company_id == company_id)
    )
    if not access_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sie haben keinen Zugriff auf diese Firma."
        )

    # Lade Firma
    result = await db.execute(
        select(Company)
        .where(Company.id == company_id)
        .where(Company.deleted_at.is_(None))
    )
    company = result.scalar_one_or_none()

    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Firma nicht gefunden."
        )

    return CompanyResponse(
        id=company.id,
        name=company.name,
        vat_id=company.vat_id,
        tax_number=company.tax_number,
        address_street=company.address_street,
        address_city=company.address_city,
        address_postal_code=company.address_postal_code,
        address_country=company.address_country,
        email=company.email,
        phone=company.phone,
        website=company.website,
        account_chart=company.account_chart,
        fiscal_year_start_month=company.fiscal_year_start_month,
        settings=company.settings or {},
        is_active=company.is_active,
        created_at=company.created_at,
        updated_at=company.updated_at,
    )


@router.put(
    "/{company_id}",
    response_model=CompanyResponse,
    summary="Firma aktualisieren",
    description="Aktualisiert eine Firma. Nur Owner und Admins."
)
async def update_company(
    company_id: UUID,
    data: CompanyUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> CompanyResponse:
    """Aktualisiert eine Firma."""

    # Pruefe Berechtigung (Owner oder Admin)
    access_result = await db.execute(
        select(UserCompany)
        .where(UserCompany.user_id == current_user.id)
        .where(UserCompany.company_id == company_id)
    )
    user_company = access_result.scalar_one_or_none()

    if not user_company:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sie haben keinen Zugriff auf diese Firma."
        )

    if user_company.role not in ["owner", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nur Owner und Admins koennen Firmendaten aendern."
        )

    # Lade Firma
    result = await db.execute(
        select(Company)
        .where(Company.id == company_id)
        .where(Company.deleted_at.is_(None))
    )
    company = result.scalar_one_or_none()

    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Firma nicht gefunden."
        )

    # Update Felder
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(company, field, value)

    company.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(company)

    logger.info(
        "company_updated",
        company_id=str(company.id),
        updated_fields=list(update_data.keys()),
        user_id=str(current_user.id),
    )

    return CompanyResponse(
        id=company.id,
        name=company.name,
        vat_id=company.vat_id,
        tax_number=company.tax_number,
        address_street=company.address_street,
        address_city=company.address_city,
        address_postal_code=company.address_postal_code,
        address_country=company.address_country,
        email=company.email,
        phone=company.phone,
        website=company.website,
        account_chart=company.account_chart,
        fiscal_year_start_month=company.fiscal_year_start_month,
        settings=company.settings or {},
        is_active=company.is_active,
        created_at=company.created_at,
        updated_at=company.updated_at,
    )


@router.delete(
    "/{company_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Firma loeschen (Soft-Delete)",
    description="Setzt deleted_at fuer die Firma. Nur Owner."
)
async def delete_company(
    company_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> None:
    """Loescht eine Firma (Soft-Delete)."""

    # Pruefe Berechtigung (nur Owner)
    access_result = await db.execute(
        select(UserCompany)
        .where(UserCompany.user_id == current_user.id)
        .where(UserCompany.company_id == company_id)
    )
    user_company = access_result.scalar_one_or_none()

    if not user_company or user_company.role != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nur der Firmen-Owner kann die Firma loeschen."
        )

    # Lade Firma
    result = await db.execute(
        select(Company)
        .where(Company.id == company_id)
        .where(Company.deleted_at.is_(None))
    )
    company = result.scalar_one_or_none()

    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Firma nicht gefunden."
        )

    # Soft-Delete
    company.deleted_at = datetime.utcnow()
    company.is_active = False

    await db.commit()

    logger.info(
        "company_deleted",
        company_id=str(company.id),
        company_name=company.name,
        user_id=str(current_user.id),
    )


# ==================== User-Company Management ====================

@router.get(
    "/{company_id}/users",
    response_model=List[UserCompanyResponse],
    summary="Benutzer der Firma auflisten",
    description="Gibt alle Benutzer zurueck, die Zugriff auf die Firma haben."
)
async def list_company_users(
    company_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> List[UserCompanyResponse]:
    """Liste der Benutzer einer Firma."""

    # Pruefe Zugriff
    access_result = await db.execute(
        select(UserCompany)
        .where(UserCompany.user_id == current_user.id)
        .where(UserCompany.company_id == company_id)
    )
    user_company = access_result.scalar_one_or_none()

    if not user_company:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sie haben keinen Zugriff auf diese Firma."
        )

    # Nur Owner/Admin duerfen Benutzer sehen
    if user_company.role not in ["owner", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nur Owner und Admins koennen Benutzer verwalten."
        )

    # Lade alle UserCompany-Eintraege
    result = await db.execute(
        select(UserCompany)
        .options(selectinload(UserCompany.user))
        .where(UserCompany.company_id == company_id)
    )
    user_companies = result.scalars().all()

    return [
        UserCompanyResponse(
            id=uc.id,
            user_id=uc.user_id,
            user_email=uc.user.email if uc.user else None,
            user_name=uc.user.full_name if uc.user else None,
            company_id=uc.company_id,
            role=CompanyRole(uc.role),
            can_manage_cash=uc.can_manage_cash,
            can_approve_expenses=uc.can_approve_expenses,
            is_current=uc.is_current,
            created_at=uc.created_at,
        )
        for uc in user_companies
    ]


@router.post(
    "/{company_id}/users",
    response_model=UserCompanyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Benutzer zur Firma hinzufuegen",
    description="Fuegt einen Benutzer zur Firma hinzu. Nur Owner und Admins."
)
async def add_user_to_company(
    company_id: UUID,
    data: UserCompanyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> UserCompanyResponse:
    """Fuegt einen Benutzer zur Firma hinzu."""

    # Pruefe Berechtigung
    access_result = await db.execute(
        select(UserCompany)
        .where(UserCompany.user_id == current_user.id)
        .where(UserCompany.company_id == company_id)
    )
    user_company = access_result.scalar_one_or_none()

    if not user_company or user_company.role not in ["owner", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nur Owner und Admins koennen Benutzer hinzufuegen."
        )

    # Pruefe ob Benutzer existiert
    user_result = await db.execute(
        select(User).where(User.id == data.user_id)
    )
    target_user = user_result.scalar_one_or_none()

    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Benutzer nicht gefunden."
        )

    # Pruefe ob bereits zugeordnet
    existing_result = await db.execute(
        select(UserCompany)
        .where(UserCompany.user_id == data.user_id)
        .where(UserCompany.company_id == company_id)
    )
    if existing_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Benutzer ist bereits dieser Firma zugeordnet."
        )

    # Erstelle Zuordnung
    new_uc = UserCompany(
        user_id=data.user_id,
        company_id=company_id,
        role=data.role or "member",
        can_manage_cash=data.can_manage_cash or False,
        can_approve_expenses=data.can_approve_expenses or False,
        is_current=False,
    )
    db.add(new_uc)
    await db.commit()
    await db.refresh(new_uc)

    logger.info(
        "user_added_to_company",
        company_id=str(company_id),
        target_user_id=str(data.user_id),
        role=data.role,
        by_user_id=str(current_user.id),
    )

    return UserCompanyResponse(
        id=new_uc.id,
        user_id=new_uc.user_id,
        user_email=target_user.email,
        user_name=target_user.full_name,
        company_id=new_uc.company_id,
        role=CompanyRole(new_uc.role),
        can_manage_cash=new_uc.can_manage_cash,
        can_approve_expenses=new_uc.can_approve_expenses,
        is_current=new_uc.is_current,
        created_at=new_uc.created_at,
    )


@router.put(
    "/{company_id}/users/{user_id}",
    response_model=UserCompanyResponse,
    summary="Benutzerrolle aktualisieren",
    description="Aktualisiert die Rolle und Berechtigungen eines Benutzers."
)
async def update_company_user(
    company_id: UUID,
    user_id: UUID,
    data: UserCompanyUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> UserCompanyResponse:
    """Aktualisiert die Benutzerrolle in einer Firma."""

    # Pruefe Berechtigung
    access_result = await db.execute(
        select(UserCompany)
        .where(UserCompany.user_id == current_user.id)
        .where(UserCompany.company_id == company_id)
    )
    user_company = access_result.scalar_one_or_none()

    if not user_company or user_company.role not in ["owner", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nur Owner und Admins koennen Benutzer verwalten."
        )

    # Lade Ziel-UserCompany
    target_result = await db.execute(
        select(UserCompany)
        .options(selectinload(UserCompany.user))
        .where(UserCompany.user_id == user_id)
        .where(UserCompany.company_id == company_id)
    )
    target_uc = target_result.scalar_one_or_none()

    if not target_uc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Benutzer nicht in dieser Firma gefunden."
        )

    # Verhindere Selbst-Degradierung des Owners
    if target_uc.role == "owner" and data.role and data.role != "owner":
        # Pruefe ob es noch einen anderen Owner gibt
        other_owner = await db.execute(
            select(UserCompany)
            .where(UserCompany.company_id == company_id)
            .where(UserCompany.role == "owner")
            .where(UserCompany.user_id != user_id)
        )
        if not other_owner.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Kann den letzten Owner nicht herabstufen. "
                       "Ernennen Sie zuerst einen neuen Owner."
            )

    # Update Felder
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(target_uc, field, value)

    await db.commit()
    await db.refresh(target_uc)

    logger.info(
        "user_company_updated",
        company_id=str(company_id),
        target_user_id=str(user_id),
        updated_fields=list(update_data.keys()),
        by_user_id=str(current_user.id),
    )

    return UserCompanyResponse(
        id=target_uc.id,
        user_id=target_uc.user_id,
        user_email=target_uc.user.email if target_uc.user else None,
        user_name=target_uc.user.full_name if target_uc.user else None,
        company_id=target_uc.company_id,
        role=CompanyRole(target_uc.role),
        can_manage_cash=target_uc.can_manage_cash,
        can_approve_expenses=target_uc.can_approve_expenses,
        is_current=target_uc.is_current,
        created_at=target_uc.created_at,
    )


@router.delete(
    "/{company_id}/users/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Benutzer aus Firma entfernen",
    description="Entfernt einen Benutzer aus der Firma."
)
async def remove_user_from_company(
    company_id: UUID,
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> None:
    """Entfernt einen Benutzer aus der Firma."""

    # Pruefe Berechtigung
    access_result = await db.execute(
        select(UserCompany)
        .where(UserCompany.user_id == current_user.id)
        .where(UserCompany.company_id == company_id)
    )
    user_company = access_result.scalar_one_or_none()

    if not user_company or user_company.role not in ["owner", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nur Owner und Admins koennen Benutzer entfernen."
        )

    # Lade Ziel-UserCompany
    target_result = await db.execute(
        select(UserCompany)
        .where(UserCompany.user_id == user_id)
        .where(UserCompany.company_id == company_id)
    )
    target_uc = target_result.scalar_one_or_none()

    if not target_uc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Benutzer nicht in dieser Firma gefunden."
        )

    # Verhindere Entfernung des letzten Owners
    if target_uc.role == "owner":
        other_owner = await db.execute(
            select(UserCompany)
            .where(UserCompany.company_id == company_id)
            .where(UserCompany.role == "owner")
            .where(UserCompany.user_id != user_id)
        )
        if not other_owner.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Kann den letzten Owner nicht entfernen. "
                       "Loeschen Sie stattdessen die Firma."
            )

    await db.delete(target_uc)
    await db.commit()

    logger.info(
        "user_removed_from_company",
        company_id=str(company_id),
        removed_user_id=str(user_id),
        by_user_id=str(current_user.id),
    )

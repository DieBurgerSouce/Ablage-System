"""
Privat-Modul API Router.

Stellt Endpunkte für persönliches Dokumentenmanagement bereit:
- Spaces (persönliche und geteilte Bereiche)
- Ordner (flexible Struktur)
- Dokumente (mit optionaler Extra-Verschlüsselung)
- Immobilien (mit Mietverwaltung)
- Fahrzeuge (mit Tankbelegen)
- Versicherungen
- Kredite
- Geldanlagen
- Fristen (mit iCal-Export)
- Notfallzugriff (für Vertrauenspersonen)
"""

import uuid
from datetime import date
from decimal import Decimal
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Depends, status, Query, Response, Header, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.api.dependencies import get_db, get_current_active_user
from app.core.rate_limiting import limiter, get_user_identifier
from app.core.security import build_content_disposition
from app.db.models import User, PrivatSpace
from app.db.schemas import (
    # Space
    PrivatSpaceCreate,
    PrivatSpaceUpdate,
    PrivatSpaceResponse,
    PrivatSpaceWithStats,
    PrivatSpaceType,
    # Folder
    PrivatFolderCreate,
    PrivatFolderUpdate,
    PrivatFolderResponse,
    PrivatFolderTree,
    # Document
    PrivatDocumentCreate,
    PrivatDocumentUpdate,
    PrivatDocumentResponse,
    PrivatDocumentListResponse,
    PrivatDocumentType,
    # Property
    PrivatPropertyCreate,
    PrivatPropertyUpdate,
    PrivatPropertyResponse,
    PrivatPropertyWithDetails,
    PrivatPropertyListResponse,
    # Tenant
    PrivatTenantCreate,
    PrivatTenantUpdate,
    PrivatTenantResponse,
    # Rental Income
    PrivatRentalIncomeCreate,
    PrivatRentalIncomeResponse,
    # Utility Statement
    PrivatUtilityStatementCreate,
    PrivatUtilityStatementResponse,
    # Vehicle
    PrivatVehicleCreate,
    PrivatVehicleUpdate,
    PrivatVehicleResponse,
    PrivatVehicleWithStats,
    PrivatVehicleListResponse,
    VehicleType,
    # Fuel Log
    PrivatFuelLogCreate,
    PrivatFuelLogResponse,
    PrivatFuelStatisticsResponse,
    # Insurance
    PrivatInsuranceCreate,
    PrivatInsuranceUpdate,
    PrivatInsuranceWithDeadlines,
    PrivatInsuranceListResponse,
    InsuranceType,
    # Loan
    PrivatLoanCreate,
    PrivatLoanUpdate,
    PrivatLoanWithStats,
    PrivatLoanListResponse,
    LoanType,
    # Investment
    PrivatInvestmentCreate,
    PrivatInvestmentUpdate,
    PrivatInvestmentWithStats,
    PrivatInvestmentListResponse,
    PrivatPortfolioBreakdownResponse,
    InvestmentType,
    # Deadline
    PrivatDeadlineCreate,
    PrivatDeadlineUpdate,
    PrivatDeadlineWithStatus,
    PrivatDeadlineListResponse,
    PrivatDeadlineWidget,
    PrivatDeadlineType,
    # Emergency
    PrivatEmergencyContactCreate,
    PrivatEmergencyContactUpdate,
    PrivatEmergencyContactResponse,
    PrivatEmergencyAccessRequestCreate,
    PrivatEmergencyAccessRequestResponse,
    PrivatEmergencyAccessStatus,
    # Dashboard
    PrivatDashboardStats,
    PrivatFinancialSummary,
    # Access
    PrivatSpaceAccessCreate,
    PrivatSpaceAccessResponse,
    PrivatAccessLevel,
)
from app.services.privat import (
    PrivatSpaceService,
    PrivatFolderService,
    PrivatDocumentService,
    PrivatAccessService,
    PrivatEncryptionService,
    PrivatPropertyService,
    PrivatVehicleService,
    PrivatInsuranceService,
    PrivatLoanService,
    PrivatInvestmentService,
    PrivatDeadlineService,
    PrivatEmergencyService,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/privat", tags=["privat"])

# ==================== Service Instances ====================

space_service = PrivatSpaceService()
folder_service = PrivatFolderService()
document_service = PrivatDocumentService()
access_service = PrivatAccessService()
encryption_service = PrivatEncryptionService()
property_service = PrivatPropertyService()
vehicle_service = PrivatVehicleService()
insurance_service = PrivatInsuranceService()
loan_service = PrivatLoanService()
investment_service = PrivatInvestmentService()
deadline_service = PrivatDeadlineService()
emergency_service = PrivatEmergencyService()


# ==================== Helper Functions ====================

async def get_user_space_or_403(
    db: AsyncSession,
    space_id: uuid.UUID,
    user: User,
    required_level: PrivatAccessLevel = PrivatAccessLevel.READ,
) -> PrivatSpace:
    """Prueft ob User Zugriff auf Space hat und gibt Space zurueck.

    SECURITY FIX (Iteration 19):
    - TOCTOU-sicher: Check und Abruf sind atomar kombiniert
    - CWE-200 Prevention: KEINE Unterscheidung zwischen "nicht gefunden"
      und "kein Zugriff" - verhindert Information Disclosure ueber
      Existenz fremder Spaces

    Args:
        db: Datenbank-Session
        space_id: Space-ID
        user: Aktueller Benutzer
        required_level: Erforderliche Zugriffsebene

    Returns:
        PrivatSpace wenn Zugriff erlaubt

    Raises:
        HTTPException 404: Space nicht gefunden ODER kein Zugriff
                          (einheitliche Meldung zur Verhinderung von
                          Information Disclosure)
    """
    # SECURITY: Verwende atomare TOCTOU-sichere Methode
    space = await space_service.get_with_access_check(
        db, space_id, user.id, required_level.value if hasattr(required_level, 'value') else required_level
    )

    if space is None:
        # SECURITY FIX (Iteration 19): CWE-200 Information Disclosure Prevention
        # KEINE Unterscheidung zwischen "nicht gefunden" und "kein Zugriff"!
        # Ein Angreifer darf NICHT erfahren, ob ein Space existiert.
        # Vorher: Separater Check auf Existenz → ermoeglichte Enumeration
        # Jetzt: Einheitliche 404-Meldung in allen Faellen
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Space nicht gefunden",
        )

    return space


async def get_user_space_with_owner_info(
    db: AsyncSession,
    space_id: uuid.UUID,
    user: User,
    required_level: PrivatAccessLevel = PrivatAccessLevel.READ,
) -> tuple[PrivatSpace, bool]:
    """Prueft Zugriff und gibt Space + Owner-Status zurueck.

    SECURITY FIX 21-4: Ermoeglicht es Endpoints zu entscheiden, ob sensitive
    Felder (account_number, policy_number) angezeigt werden sollen.
    Nur Owner sehen diese Felder, Shared-Access-User bekommen maskierte Werte.

    Args:
        db: Datenbank-Session
        space_id: Space-ID
        user: Aktueller Benutzer
        required_level: Erforderliche Zugriffsebene

    Returns:
        Tuple (PrivatSpace, is_owner: bool)

    Raises:
        HTTPException 404: Space nicht gefunden ODER kein Zugriff
    """
    space = await get_user_space_or_403(db, space_id, user, required_level)
    is_owner = space.owner_id == user.id
    return space, is_owner


def mask_sensitive_field(value: Optional[str], is_owner: bool) -> Optional[str]:
    """Maskiert sensitive Felder fuer Nicht-Owner.

    SECURITY FIX 21-4: PII Protection - account_number, policy_number etc.
    werden fuer Shared-Access-User maskiert.

    Args:
        value: Original-Wert
        is_owner: True wenn User der Owner ist

    Returns:
        Original-Wert fuer Owner, maskierter Wert fuer andere
    """
    if value is None:
        return None
    if is_owner:
        return value
    # Maskiere alle bis auf die letzten 4 Zeichen
    if len(value) <= 4:
        return "****"
    return "*" * (len(value) - 4) + value[-4:]


# ==================== Dashboard ====================

@router.get(
    "/dashboard",
    response_model=PrivatDashboardStats,
    summary="Dashboard-Statistiken abrufen",
)
@limiter.limit("60/minute", key_func=get_user_identifier)  # SECURITY FIX 20-11: Rate limit for dashboard
async def get_dashboard_stats(
    request: Request,  # Required for rate limiter
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PrivatDashboardStats:
    """Holt alle Dashboard-Statistiken für den aktuellen User."""
    # Hole alle Spaces des Users
    spaces = await space_service.get_user_spaces(db, current_user.id)

    if not spaces:
        return PrivatDashboardStats(
            total_spaces=0,
            total_documents=0,
            total_properties=0,
            total_vehicles=0,
            total_insurances=0,
            total_loans=0,
            total_investments=0,
            upcoming_deadlines=0,
            overdue_deadlines=0,
        )

    # Aggregiere Statistiken über alle Spaces
    total_documents = 0
    total_properties = 0
    total_vehicles = 0
    total_insurances = 0
    total_loans = 0
    total_investments = 0
    upcoming_deadlines = 0
    overdue_deadlines = 0

    for space in spaces:
        # Hole Deadline-Widget für jeden Space
        widget = await deadline_service.get_dashboard_widget(db, space.id)
        upcoming_deadlines += len(widget.today) + len(widget.this_week) + len(widget.this_month)
        overdue_deadlines += len(widget.overdue)

    return PrivatDashboardStats(
        total_spaces=len(spaces),
        total_documents=total_documents,
        total_properties=total_properties,
        total_vehicles=total_vehicles,
        total_insurances=total_insurances,
        total_loans=total_loans,
        total_investments=total_investments,
        upcoming_deadlines=upcoming_deadlines,
        overdue_deadlines=overdue_deadlines,
    )


@router.get(
    "/dashboard/financial-summary",
    response_model=PrivatFinancialSummary,
    summary="Finanzübersicht abrufen",
)
@limiter.limit("60/minute", key_func=get_user_identifier)  # SECURITY FIX 20-11: Rate limit for financial data
async def get_financial_summary(
    request: Request,  # Required for rate limiter
    space_id: uuid.UUID = Query(..., description="Space-ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PrivatFinancialSummary:
    """Holt die Finanzübersicht für einen Space."""
    await get_user_space_or_403(db, space_id, current_user)

    # Hole alle Finanzdaten
    total_loan_balance = await loan_service.get_total_balance(db, space_id)
    monthly_loan_payments = await loan_service.get_monthly_payments(db, space_id)

    investment_return = await investment_service.get_total_return(db, space_id)
    total_investment_value = investment_return["total_value"]

    annual_insurance_cost = await insurance_service.get_total_annual_cost(db, space_id)

    # Berechne Nettovermögen
    net_worth = total_investment_value - total_loan_balance

    return PrivatFinancialSummary(
        net_worth=net_worth,
        total_investments=total_investment_value,
        total_loans=total_loan_balance,
        monthly_loan_payments=monthly_loan_payments,
        annual_insurance_cost=annual_insurance_cost,
        investment_return_percentage=investment_return["return_percentage"],
    )


# ==================== Spaces ====================

@router.post(
    "/spaces",
    response_model=PrivatSpaceWithStats,
    status_code=status.HTTP_201_CREATED,
    summary="Neuen Space erstellen",
)
@limiter.limit("5/minute", key_func=get_user_identifier)  # Rate Limit: Max 5 Spaces/Minute
async def create_space(
    request: Request,  # Required for rate limiter
    data: PrivatSpaceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PrivatSpaceWithStats:
    """Erstellt einen neuen persoenlichen oder geteilten Space.

    Fuer persoenliche Spaces wird kein Company-Kontext benoetigt.
    Fuer geteilte Spaces muss ein Company-Kontext (X-Company-ID Header) gesetzt sein.
    """
    if data.space_type == PrivatSpaceType.PERSONAL:
        space = await space_service.create_personal_space(
            db, current_user.id, data
        )
    else:
        # Geteilte Spaces benoetigen Company-Kontext
        from app.middleware.company_context import get_current_company_id
        company_id = get_current_company_id()
        if not company_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Fuer geteilte Spaces muss eine Firma ausgewaehlt sein (X-Company-ID Header)"
            )
        space = await space_service.create_shared_space(
            db, company_id, current_user.id, data
        )

    # Hole Stats
    stats = await space_service.get_space_stats(db, space.id)

    return PrivatSpaceWithStats(
        id=space.id,
        name=space.name,
        description=space.description,
        space_type=PrivatSpaceType(space.space_type),
        owner_id=space.owner_id,
        is_active=space.is_active,
        created_at=space.created_at,
        updated_at=space.updated_at,
        **stats,
    )


@router.get(
    "/spaces",
    response_model=List[PrivatSpaceWithStats],
    summary="Eigene Spaces auflisten",
)
@limiter.limit("60/minute", key_func=get_user_identifier)  # SECURITY FIX 20-11: Rate limit for spaces list
async def list_spaces(
    request: Request,  # Required for rate limiter
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> List[PrivatSpaceWithStats]:
    """Listet alle Spaces auf, auf die der User Zugriff hat."""
    spaces = await space_service.get_user_spaces(db, current_user.id)

    result = []
    for space in spaces:
        stats = await space_service.get_space_stats(db, space.id)
        result.append(PrivatSpaceWithStats(
            id=space.id,
            name=space.name,
            description=space.description,
            space_type=PrivatSpaceType(space.space_type),
            owner_id=space.owner_id,
            is_active=space.is_active,
            created_at=space.created_at,
            updated_at=space.updated_at,
            **stats,
        ))

    return result


@router.get(
    "/spaces/{space_id}",
    response_model=PrivatSpaceWithStats,
    summary="Space-Details abrufen",
)
@limiter.limit("60/minute", key_func=get_user_identifier)  # SECURITY FIX 20-11: Rate limit for space details
async def get_space(
    request: Request,  # Required for rate limiter
    space_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PrivatSpaceWithStats:
    """Holt Details eines Spaces."""
    # SECURITY FIX (Iteration 19): TOCTOU-sicher - Space wird direkt zurueckgegeben
    space = await get_user_space_or_403(db, space_id, current_user)
    # KEIN separater get_by_id() mehr noetig - TOCTOU verhindert!

    stats = await space_service.get_space_stats(db, space.id)

    return PrivatSpaceWithStats(
        id=space.id,
        name=space.name,
        description=space.description,
        space_type=PrivatSpaceType(space.space_type),
        owner_id=space.owner_id,
        is_active=space.is_active,
        created_at=space.created_at,
        updated_at=space.updated_at,
        **stats,
    )


@router.patch(
    "/spaces/{space_id}",
    response_model=PrivatSpaceResponse,
    summary="Space aktualisieren",
)
@limiter.limit("30/minute", key_func=get_user_identifier)  # SECURITY: Rate limit for space updates
async def update_space(
    request: Request,  # Required for rate limiter
    space_id: uuid.UUID,
    data: PrivatSpaceUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PrivatSpaceResponse:
    """Aktualisiert einen Space."""
    await get_user_space_or_403(db, space_id, current_user, PrivatAccessLevel.MANAGE)

    space = await space_service.update(db, space_id, data)
    if not space:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Space nicht gefunden",
        )

    return PrivatSpaceResponse(
        id=space.id,
        name=space.name,
        description=space.description,
        space_type=PrivatSpaceType(space.space_type),
        owner_id=space.owner_id,
        is_active=space.is_active,
        created_at=space.created_at,
        updated_at=space.updated_at,
    )


@router.delete(
    "/spaces/{space_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Space löschen",
)
@limiter.limit("5/minute", key_func=get_user_identifier)  # SECURITY: Very strict rate limit for space deletion
async def delete_space(
    request: Request,
    space_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> None:
    """Löscht einen Space (soft delete)."""
    await get_user_space_or_403(db, space_id, current_user, PrivatAccessLevel.ADMIN)

    success = await space_service.delete(db, space_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Space nicht gefunden",
        )


# ==================== Space Access ====================

@router.post(
    "/spaces/{space_id}/access",
    response_model=PrivatSpaceAccessResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Zugriff gewähren",
)
@limiter.limit("5/minute", key_func=get_user_identifier)  # SECURITY: Rate limit for access grants per user
async def grant_access(
    request: Request,  # SECURITY FIX 26-1: Required for rate limiter
    space_id: uuid.UUID,
    data: PrivatSpaceAccessCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PrivatSpaceAccessResponse:
    """Gewährt einem User Zugriff auf einen Space."""
    await get_user_space_or_403(db, space_id, current_user, PrivatAccessLevel.ADMIN)

    access = await access_service.grant_access(
        db, space_id, data, current_user.id
    )

    return PrivatSpaceAccessResponse(
        id=access.id,
        space_id=access.space_id,
        user_id=access.user_id,
        access_level=PrivatAccessLevel(access.access_level),
        granted_by=access.granted_by,
        granted_at=access.granted_at,
        expires_at=access.expires_at,
        is_active=access.is_active,
    )


@router.get(
    "/spaces/{space_id}/access",
    response_model=List[PrivatSpaceAccessResponse],
    summary="Zugriffsberechtigungen auflisten",
)
@limiter.limit("60/minute", key_func=get_user_identifier)  # SECURITY FIX 21-6: Rate limit gegen Enumeration
async def list_access(
    request: Request,  # Required for rate limiter
    space_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> List[PrivatSpaceAccessResponse]:
    """Listet alle Zugriffsberechtigungen eines Spaces."""
    await get_user_space_or_403(db, space_id, current_user, PrivatAccessLevel.MANAGE)

    return await access_service.list_access(db, space_id)


@router.delete(
    "/spaces/{space_id}/access/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Zugriff entziehen",
)
@limiter.limit("10/minute", key_func=get_user_identifier)  # Rate limit for access revocation
async def revoke_access(
    request: Request,
    space_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> None:
    """Entzieht einem User den Zugriff auf einen Space."""
    await get_user_space_or_403(db, space_id, current_user, PrivatAccessLevel.ADMIN)

    success = await access_service.revoke_access(db, space_id, user_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Zugriffsberechtigung nicht gefunden",
        )


# ==================== Folders ====================

@router.post(
    "/spaces/{space_id}/folders",
    response_model=PrivatFolderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ordner erstellen",
)
@limiter.limit("30/minute", key_func=get_user_identifier)  # SECURITY: Per-user rate limit
async def create_folder(
    request: Request,  # SECURITY FIX 26-2: Required for rate limiter
    space_id: uuid.UUID,
    data: PrivatFolderCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PrivatFolderResponse:
    """Erstellt einen neuen Ordner."""
    await get_user_space_or_403(db, space_id, current_user, PrivatAccessLevel.WRITE)

    folder = await folder_service.create(db, space_id, data)

    return PrivatFolderResponse(
        id=folder.id,
        space_id=folder.space_id,
        parent_id=folder.parent_id,
        name=folder.name,
        path=folder.path,
        icon=folder.icon,
        color=folder.color,
        sort_order=folder.sort_order,
        created_at=folder.created_at,
        updated_at=folder.updated_at,
    )


@router.get(
    "/spaces/{space_id}/folders",
    response_model=List[PrivatFolderTree],
    summary="Ordnerstruktur abrufen",
)
@limiter.limit("60/minute", key_func=get_user_identifier)  # SECURITY FIX 21-6: Rate limit gegen Enumeration
async def get_folder_tree(
    request: Request,  # Required for rate limiter
    space_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> List[PrivatFolderTree]:
    """Holt die komplette Ordnerstruktur eines Spaces."""
    await get_user_space_or_403(db, space_id, current_user)

    return await folder_service.get_folder_tree(db, space_id)


@router.patch(
    "/folders/{folder_id}",
    response_model=PrivatFolderResponse,
    summary="Ordner aktualisieren",
)
@limiter.limit("30/minute", key_func=get_user_identifier)  # SECURITY: Rate limit for folder updates
async def update_folder(
    request: Request,  # Required for rate limiter
    folder_id: uuid.UUID,
    data: PrivatFolderUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PrivatFolderResponse:
    """Aktualisiert einen Ordner."""
    # SECURITY: IDOR-sichere Methode - Access-Check integriert
    folder = await folder_service.get_by_id_with_access_check(
        db, folder_id, current_user.id
    )
    if not folder:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ordner nicht gefunden",
        )

    updated = await folder_service.update(db, folder_id, data)

    return PrivatFolderResponse(
        id=updated.id,
        space_id=updated.space_id,
        parent_id=updated.parent_id,
        name=updated.name,
        path=updated.path,
        icon=updated.icon,
        color=updated.color,
        sort_order=updated.sort_order,
        created_at=updated.created_at,
        updated_at=updated.updated_at,
    )


@router.post(
    "/folders/{folder_id}/move",
    response_model=PrivatFolderResponse,
    summary="Ordner verschieben",
)
@limiter.limit("20/minute", key_func=get_user_identifier)  # SECURITY: Per-user rate limit
async def move_folder(
    request: Request,  # Required for rate limiter
    folder_id: uuid.UUID,
    new_parent_id: Optional[uuid.UUID] = Query(None, description="Neuer Eltern-Ordner (null für Root)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PrivatFolderResponse:
    """Verschiebt einen Ordner.

    SECURITY FIX 20-2/20-3: Atomare TOCTOU-sichere Operation.
    Prueft dass Zielordner im gleichen Space liegt (IDOR-Prevention).
    """
    try:
        # SECURITY FIX 20-2: Atomare Operation - Access-Check + Move in einem Schritt
        # Verhindert TOCTOU Race Condition
        updated = await folder_service.move_with_access_check(
            db, folder_id, new_parent_id, current_user.id
        )
        if not updated:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Ordner nicht gefunden",
            )
    except ValueError as e:
        # SECURITY FIX 29: Generic error message - no internal details
        # ValueError wird bei ungueltigem Zielordner oder Zirkularitaet geworfen
        logger.warning("privat_folder_update_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ungueltige Anfrage. Bitte Eingaben pruefen.",
        )

    return PrivatFolderResponse(
        id=updated.id,
        space_id=updated.space_id,
        parent_id=updated.parent_id,
        name=updated.name,
        path=updated.path,
        icon=updated.icon,
        color=updated.color,
        sort_order=updated.sort_order,
        created_at=updated.created_at,
        updated_at=updated.updated_at,
    )


@router.delete(
    "/folders/{folder_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Ordner löschen",
)
@limiter.limit("10/minute", key_func=get_user_identifier)  # Rate limit for folder deletion
async def delete_folder(
    request: Request,
    folder_id: uuid.UUID,
    recursive: bool = Query(False, description="Mit Unterordnern löschen"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> None:
    """Löscht einen Ordner."""
    # SECURITY: IDOR-sichere Methode - Access-Check integriert
    folder = await folder_service.get_by_id_with_access_check(
        db, folder_id, current_user.id
    )
    if not folder:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ordner nicht gefunden",
        )

    success = await folder_service.delete(db, folder_id, recursive)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ordner konnte nicht gelöscht werden (enthält Unterordner)",
        )


# ==================== Documents ====================

@router.post(
    "/spaces/{space_id}/documents",
    response_model=PrivatDocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Dokument erstellen",
)
@limiter.limit("30/minute", key_func=get_user_identifier)  # Rate Limit: Max 30 Dokumente/Minute
async def create_document(
    request: Request,  # Required for rate limiter
    space_id: uuid.UUID,
    data: PrivatDocumentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    x_privat_password: Optional[str] = Header(
        None,
        alias="X-Privat-Password",
        description="Extra-Passwort fuer Verschluesselung (Security: Header statt URL)"
    ),
) -> PrivatDocumentResponse:
    """Erstellt ein neues Dokument mit optionaler Extra-Verschluesselung.

    Das Passwort wird aus Sicherheitsgruenden per Header uebermittelt,
    nicht als URL-Parameter (vermeidet Logging in Browser History/Server Logs).
    """
    await get_user_space_or_403(db, space_id, current_user, PrivatAccessLevel.WRITE)

    document = await document_service.create(db, space_id, data, x_privat_password)

    return PrivatDocumentResponse(
        id=document.id,
        space_id=document.space_id,
        folder_id=document.folder_id,
        title=document.title,
        document_type=PrivatDocumentType(document.document_type),
        file_path=document.file_path,
        file_size=document.file_size,
        mime_type=document.mime_type,
        description=document.description,
        tags=document.tags,
        is_extra_encrypted=document.is_extra_encrypted,
        password_hint=document.password_hint,
        is_active=document.is_active,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


@router.get(
    "/spaces/{space_id}/documents",
    response_model=PrivatDocumentListResponse,
    summary="Dokumente auflisten",
)
@limiter.limit("60/minute", key_func=get_user_identifier)  # SECURITY FIX 20-11: Rate limit for documents list
async def list_documents(
    request: Request,  # Required for rate limiter
    space_id: uuid.UUID,
    folder_id: Optional[uuid.UUID] = Query(None, description="Filter nach Ordner"),
    document_type: Optional[PrivatDocumentType] = Query(None, description="Filter nach Typ"),
    search: Optional[str] = Query(None, description="Suchbegriff"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PrivatDocumentListResponse:
    """Listet Dokumente eines Spaces."""
    await get_user_space_or_403(db, space_id, current_user)

    return await document_service.list_documents(
        db, space_id, folder_id, document_type, search, page, page_size
    )


@router.get(
    "/documents/{document_id}",
    response_model=PrivatDocumentResponse,
    summary="Dokument abrufen",
)
@limiter.limit("60/minute", key_func=get_user_identifier)  # SECURITY FIX 20-11: Rate limit for document details
async def get_document(
    request: Request,  # Required for rate limiter
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PrivatDocumentResponse:
    """Holt Dokument-Metadaten.

    SECURITY:
        - IDOR Protection: Access-Check erfolgt VOR dem Abrufen
        - Password Hint: Nur an Space-Owner zurueckgegeben
        - TOCTOU-sicher (Iteration 19): Document + Space in einer atomaren Operation
    """
    # SECURITY FIX (Iteration 19): TOCTOU-sicher - Document + Space atomar holen
    # Verhindert CWE-367 Race Condition zwischen Access-Check und Space-Lookup
    result = await document_service.get_by_id_with_space_and_access_check(
        db, document_id, current_user.id
    )
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dokument nicht gefunden",
        )

    document, space = result  # TOCTOU-sicher: Beide aus EINER Query

    # SECURITY FIX 20-10: Password Hint NUR an direkten Owner (nicht ueber Shared Access)
    # Verhindert Information Disclosure bei geteilten Dokumenten
    # KEIN separater space_service.get_by_id() noetig - Space bereits vorhanden!
    password_hint = None
    if document.is_extra_encrypted and document.password_hint:
        # Nur der direkte Owner sieht den Hint (nicht Shared-Access-User)
        is_direct_owner = space.owner_id == current_user.id
        if is_direct_owner:
            password_hint = document.password_hint

    return PrivatDocumentResponse(
        id=document.id,
        space_id=document.space_id,
        folder_id=document.folder_id,
        title=document.title,
        document_type=PrivatDocumentType(document.document_type),
        file_path=document.file_path,
        file_size=document.file_size,
        mime_type=document.mime_type,
        description=document.description,
        tags=document.tags,
        is_extra_encrypted=document.is_extra_encrypted,
        password_hint=password_hint,  # SECURITY: Nur fuer Owner
        is_active=document.is_active,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


@router.get(
    "/documents/{document_id}/content",
    summary="Dokument-Inhalt herunterladen",
)
@limiter.limit("60/minute", key_func=get_user_identifier)  # Rate Limit: Max 60 Downloads/Minute
async def download_document(
    request: Request,  # Required for rate limiter
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    x_privat_password: Optional[str] = Header(
        None,
        alias="X-Privat-Password",
        description="Passwort fuer verschluesselte Dokumente (Security: Header statt URL)"
    ),
) -> Response:
    """Laedt den Dokumentinhalt herunter.

    Das Passwort wird aus Sicherheitsgruenden per Header uebermittelt,
    nicht als URL-Parameter (vermeidet Logging in Browser History/Server Logs).

    Security:
        - IDOR Protection: Access-Check VOR get_by_id (IDOR-sicher)
        - Header Injection Prevention: Filename is URL-encoded
        - Error Message Sanitization: No internal error details exposed
    """
    # SECURITY: Access-Check VOR get_by_id (IDOR-Schutz)
    document = await document_service.get_by_id_with_access_check(
        db, document_id, current_user.id
    )
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dokument nicht gefunden",
        )

    try:
        # SECURITY: Pass requesting_user_id for service-level access control
        content = await document_service.get_content(
            db,
            document_id,
            x_privat_password,
            requesting_user_id=current_user.id,
        )
        if content is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Dokumentinhalt nicht gefunden",
            )

        # SECURITY: Use centralized sanitization to prevent CRLF injection (Phase 10)
        return Response(
            content=content,
            media_type=document.mime_type or "application/octet-stream",
            headers={
                "Content-Disposition": build_content_disposition(document.title, "attachment"),
            },
        )
    except ValueError:
        # SECURITY: Do NOT expose internal error messages
        # ValueError can contain sensitive info like "wrong password" vs specific password errors
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Fehler beim Laden des Dokuments",
        )


@router.patch(
    "/documents/{document_id}",
    response_model=PrivatDocumentResponse,
    summary="Dokument aktualisieren",
)
@limiter.limit("30/minute", key_func=get_user_identifier)  # SECURITY: Rate limit for document updates
async def update_document(
    request: Request,  # Required for rate limiter
    document_id: uuid.UUID,
    data: PrivatDocumentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PrivatDocumentResponse:
    """Aktualisiert Dokument-Metadaten.

    SECURITY FIX 20-5/20-13: IDOR-sicher + Password Hint Konsistenz
    """
    # SECURITY FIX 20-5: TOCTOU-sicher - Document + Space atomar holen
    result = await document_service.get_by_id_with_space_and_access_check(
        db, document_id, current_user.id
    )
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dokument nicht gefunden",
        )

    document, space = result

    updated = await document_service.update(db, document_id, data)

    # SECURITY FIX 20-13: Password Hint Konsistenz - nur fuer Owner
    password_hint = None
    if updated.is_extra_encrypted and updated.password_hint:
        is_direct_owner = space.owner_id == current_user.id
        if is_direct_owner:
            password_hint = updated.password_hint

    return PrivatDocumentResponse(
        id=updated.id,
        space_id=updated.space_id,
        folder_id=updated.folder_id,
        title=updated.title,
        document_type=PrivatDocumentType(updated.document_type),
        file_path=updated.file_path,
        file_size=updated.file_size,
        mime_type=updated.mime_type,
        description=updated.description,
        tags=updated.tags,
        is_extra_encrypted=updated.is_extra_encrypted,
        password_hint=password_hint,  # SECURITY: Nur fuer Owner
        is_active=updated.is_active,
        created_at=updated.created_at,
        updated_at=updated.updated_at,
    )


@router.delete(
    "/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Dokument löschen",
)
@limiter.limit("10/minute", key_func=get_user_identifier)  # Rate Limit: Max 10 Loeschungen/Minute
async def delete_document(
    request: Request,  # Required for rate limiter
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> None:
    """Loescht ein Dokument (soft delete).

    SECURITY: IDOR-sicher - Access-Check VOR get_by_id
    """
    # SECURITY: Access-Check VOR get_by_id (IDOR-Schutz)
    document = await document_service.get_by_id_with_access_check(
        db, document_id, current_user.id
    )
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dokument nicht gefunden",
        )

    success = await document_service.delete(db, document_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Dokument konnte nicht gelöscht werden",
        )


# ==================== Properties ====================

@router.post(
    "/spaces/{space_id}/properties",
    response_model=PrivatPropertyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Immobilie erstellen",
)
@limiter.limit("30/minute", key_func=get_user_identifier)  # SECURITY: Rate limit for create operations
async def create_property(
    request: Request,  # SECURITY FIX 25-1: Required for rate limiter
    space_id: uuid.UUID,
    data: PrivatPropertyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PrivatPropertyResponse:
    """Erstellt eine neue Immobilie."""
    await get_user_space_or_403(db, space_id, current_user, PrivatAccessLevel.WRITE)

    prop = await property_service.create_property(db, space_id, data)

    return PrivatPropertyResponse(
        id=prop.id,
        space_id=prop.space_id,
        name=prop.name,
        property_type=prop.property_type,
        address_street=prop.address_street,
        address_city=prop.address_city,
        address_zip=prop.address_zip,
        address_country=prop.address_country,
        purchase_date=prop.purchase_date,
        purchase_price=prop.purchase_price,
        current_value=prop.current_value,
        size_sqm=prop.size_sqm,
        rooms=prop.rooms,
        notes=prop.notes,
        is_active=prop.is_active,
        created_at=prop.created_at,
        updated_at=prop.updated_at,
    )


@router.get(
    "/spaces/{space_id}/properties",
    response_model=PrivatPropertyListResponse,
    summary="Immobilien auflisten",
)
@limiter.limit("60/minute", key_func=get_user_identifier)  # Rate limit for list operations
async def list_properties(
    request: Request,
    space_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PrivatPropertyListResponse:
    """Listet alle Immobilien eines Spaces.

    SECURITY FIX 25-8: PII Masking - Adressen werden fuer Nicht-Owner maskiert.
    """
    space = await get_user_space_or_403(db, space_id, current_user)

    # SECURITY FIX 25-8: Pruefe Owner-Status fuer PII-Masking
    is_owner = space.owner_id == current_user.id

    result = await property_service.list_properties(db, space_id, page, page_size)

    # SECURITY FIX 25-8: PII Masking - Adressen fuer Nicht-Owner maskieren
    for item in result.items:
        item.address_street = mask_sensitive_field(item.address_street, is_owner)
        item.address_city = mask_sensitive_field(item.address_city, is_owner)
        item.address_zip = mask_sensitive_field(item.address_zip, is_owner)

    return result


@router.get(
    "/properties/{property_id}",
    response_model=PrivatPropertyWithDetails,
    summary="Immobilien-Details abrufen",
)
@limiter.limit("60/minute", key_func=get_user_identifier)  # Rate limit for detail operations
async def get_property(
    request: Request,
    property_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PrivatPropertyWithDetails:
    """Holt Immobilien-Details mit Mietern und Statistiken.

    SECURITY FIX 25-9: PII Masking - Adressen und Tenant-PII werden fuer Nicht-Owner maskiert.
    """
    # SECURITY: IDOR-sichere Methode - Access-Check integriert
    prop = await property_service.get_property_with_access_check(
        db, property_id, current_user.id
    )
    if not prop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Immobilie nicht gefunden",
        )

    # SECURITY FIX 25-9: Pruefe Owner-Status fuer PII-Masking
    space = await space_service.get_by_id(db, prop.space_id)
    is_owner = space and space.owner_id == current_user.id

    # Hole zusaetzliche Details (Mieter, Statistiken)
    tenants = await property_service.list_tenants(db, property_id)
    total_income = await property_service.get_total_rental_income(db, property_id)
    pending_payment_count = await property_service.get_pending_payments_count(db, property_id)

    # SECURITY FIX 25-9: PII Masking fuer Tenants
    tenant_responses = []
    for t in tenants:
        tenant_resp = PrivatTenantResponse.model_validate(t)
        tenant_resp.phone = mask_sensitive_field(tenant_resp.phone, is_owner)
        tenant_resp.email = mask_sensitive_field(tenant_resp.email, is_owner)
        tenant_responses.append(tenant_resp)

    return PrivatPropertyWithDetails(
        id=prop.id,
        space_id=prop.space_id,
        # SECURITY FIX 25-9: Adress-Masking fuer Nicht-Owner
        address=mask_sensitive_field(prop.address, is_owner),
        city=mask_sensitive_field(prop.city, is_owner),
        postal_code=mask_sensitive_field(prop.postal_code, is_owner),
        country=prop.country,
        property_type=prop.property_type,
        purchase_date=prop.purchase_date,
        purchase_price=prop.purchase_price,
        current_value=prop.current_value,
        is_rented=prop.is_rented,
        monthly_rent=prop.monthly_rent,
        notes=prop.notes,
        is_active=prop.is_active,
        created_at=prop.created_at,
        updated_at=prop.updated_at,
        tenants=tenant_responses,
        total_rental_income=total_income,
        pending_payments=pending_payment_count,
    )


@router.patch(
    "/properties/{property_id}",
    response_model=PrivatPropertyResponse,
    summary="Immobilie aktualisieren",
)
@limiter.limit("30/minute", key_func=get_user_identifier)  # Rate limit for update operations
async def update_property(
    request: Request,
    property_id: uuid.UUID,
    data: PrivatPropertyUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PrivatPropertyResponse:
    """Aktualisiert eine Immobilie."""
    # SECURITY: IDOR-sichere Methode - Access-Check integriert
    prop = await property_service.get_property_with_access_check(
        db, property_id, current_user.id
    )
    if not prop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Immobilie nicht gefunden",
        )

    updated = await property_service.update_property(db, property_id, data)

    return PrivatPropertyResponse(
        id=updated.id,
        space_id=updated.space_id,
        name=updated.name,
        property_type=updated.property_type,
        address_street=updated.address_street,
        address_city=updated.address_city,
        address_zip=updated.address_zip,
        address_country=updated.address_country,
        purchase_date=updated.purchase_date,
        purchase_price=updated.purchase_price,
        current_value=updated.current_value,
        size_sqm=updated.size_sqm,
        rooms=updated.rooms,
        notes=updated.notes,
        is_active=updated.is_active,
        created_at=updated.created_at,
        updated_at=updated.updated_at,
    )


@router.delete(
    "/properties/{property_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Immobilie löschen",
)
@limiter.limit("10/minute", key_func=get_user_identifier)  # Rate limit for delete operations
async def delete_property(
    request: Request,
    property_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> None:
    """Löscht eine Immobilie (soft delete)."""
    # SECURITY: IDOR-sichere Methode - Access-Check integriert
    prop = await property_service.get_property_with_access_check(
        db, property_id, current_user.id
    )
    if not prop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Immobilie nicht gefunden",
        )

    await property_service.delete_property(db, property_id)


# ==================== Tenants ====================

@router.post(
    "/properties/{property_id}/tenants",
    response_model=PrivatTenantResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Mieter erstellen",
)
@limiter.limit("30/minute", key_func=get_user_identifier)  # Rate limit for create operations
async def create_tenant(
    request: Request,
    property_id: uuid.UUID,
    data: PrivatTenantCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PrivatTenantResponse:
    """Erstellt einen neuen Mieter."""
    # SECURITY: IDOR-sichere Methode - Access-Check integriert
    prop = await property_service.get_property_with_access_check(
        db, property_id, current_user.id
    )
    if not prop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Immobilie nicht gefunden",
        )

    tenant = await property_service.create_tenant(db, property_id, data)

    # SECURITY FIX 26-3: PII Masking fuer Nicht-Owner
    is_owner = prop.space.owner_id == current_user.id if prop.space else True

    return PrivatTenantResponse(
        id=tenant.id,
        property_id=tenant.property_id,
        first_name=tenant.first_name,
        last_name=tenant.last_name,
        email=mask_sensitive_field(tenant.email, is_owner),
        phone=mask_sensitive_field(tenant.phone, is_owner),
        move_in_date=tenant.move_in_date,
        move_out_date=tenant.move_out_date,
        monthly_rent=tenant.monthly_rent,
        deposit=tenant.deposit,
        deposit_paid=tenant.deposit_paid,
        notes=tenant.notes,
        is_active=tenant.is_active,
        created_at=tenant.created_at,
        updated_at=tenant.updated_at,
    )


@router.get(
    "/properties/{property_id}/tenants",
    response_model=List[PrivatTenantResponse],
    summary="Mieter auflisten",
)
@limiter.limit("60/minute", key_func=get_user_identifier)  # SECURITY FIX 22-1: Rate-Limit
async def list_tenants(
    request: Request,  # Required for rate limiter
    property_id: uuid.UUID,
    active_only: bool = Query(True, description="Nur aktive Mieter"),
    page: int = Query(1, ge=1, description="Seite"),  # SECURITY FIX 22-6: Pagination
    page_size: int = Query(50, ge=1, le=100, description="Eintraege pro Seite"),  # Max 100
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> List[PrivatTenantResponse]:
    """Listet alle Mieter einer Immobilie.

    SECURITY FIX 24-7: PII Masking - phone und email werden fuer Nicht-Owner maskiert.
    """
    # SECURITY: IDOR-sichere Methode - Access-Check integriert
    prop = await property_service.get_property_with_access_check(
        db, property_id, current_user.id
    )
    if not prop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Immobilie nicht gefunden",
        )

    # SECURITY FIX 24-7: Pruefe Owner-Status fuer PII-Masking
    space = await space_service.get_by_id(db, prop.space_id)
    is_owner = space and space.owner_id == current_user.id

    # SECURITY FIX 22-6: Pagination um DoS zu verhindern
    tenants = await property_service.list_tenants(
        db, property_id, active_only, page=page, page_size=page_size
    )

    # SECURITY FIX 24-7: PII Masking - phone/email fuer Nicht-Owner maskieren
    for tenant in tenants:
        tenant.phone = mask_sensitive_field(tenant.phone, is_owner)
        tenant.email = mask_sensitive_field(tenant.email, is_owner)

    return tenants


# ==================== Rental Income ====================

@router.post(
    "/tenants/{tenant_id}/income",
    response_model=PrivatRentalIncomeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Mieteinnahme erfassen",
)
@limiter.limit("30/minute", key_func=get_user_identifier)  # SECURITY: Rate limit for income recording
async def record_rental_income(
    request: Request,  # Required for rate limiter
    tenant_id: uuid.UUID,
    data: PrivatRentalIncomeCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PrivatRentalIncomeResponse:
    """Erfasst eine Mieteinnahme.

    SECURITY FIX 20-1/20-4: Verwendet IDOR-sichere Methode mit Access-Check.
    """
    # SECURITY FIX 20-4: Setze tenant_id im Schema (falls Schema es erwartet)
    # Hinweis: Das Schema muss die tenant_id enthalten
    data_with_tenant = PrivatRentalIncomeCreate(
        tenant_id=tenant_id,
        amount=data.amount,
        payment_date=data.payment_date,
        period_start=data.period_start,
        period_end=data.period_end,
        payment_method=data.payment_method,
        notes=data.notes,
    )

    # SECURITY FIX 20-4: Atomare IDOR-sichere Operation
    income = await property_service.record_rental_income_with_access_check(
        db, data_with_tenant, current_user.id
    )
    if not income:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mieter nicht gefunden",
        )

    return PrivatRentalIncomeResponse(
        id=income.id,
        tenant_id=income.tenant_id,
        amount=income.amount,
        payment_date=income.payment_date,
        period_start=income.period_start,
        period_end=income.period_end,
        payment_method=income.payment_method,
        notes=income.notes,
        created_at=income.created_at,
    )


# ==================== Vehicles ====================

@router.post(
    "/spaces/{space_id}/vehicles",
    response_model=PrivatVehicleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Fahrzeug erstellen",
)
@limiter.limit("30/minute", key_func=get_user_identifier)  # SECURITY: Rate limit for create operations
async def create_vehicle(
    request: Request,  # SECURITY FIX 25-2: Required for rate limiter
    space_id: uuid.UUID,
    data: PrivatVehicleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PrivatVehicleResponse:
    """Erstellt ein neues Fahrzeug."""
    await get_user_space_or_403(db, space_id, current_user, PrivatAccessLevel.WRITE)

    vehicle = await vehicle_service.create_vehicle(db, space_id, data)

    return PrivatVehicleResponse(
        id=vehicle.id,
        space_id=vehicle.space_id,
        name=vehicle.name,
        vehicle_type=VehicleType(vehicle.vehicle_type),
        brand=vehicle.brand,
        model=vehicle.model,
        year=vehicle.year,
        license_plate=vehicle.license_plate,
        vin=vehicle.vin,
        fuel_type=vehicle.fuel_type,
        purchase_date=vehicle.purchase_date,
        purchase_price=vehicle.purchase_price,
        current_mileage=vehicle.current_mileage,
        notes=vehicle.notes,
        is_active=vehicle.is_active,
        created_at=vehicle.created_at,
        updated_at=vehicle.updated_at,
    )


@router.get(
    "/spaces/{space_id}/vehicles",
    response_model=PrivatVehicleListResponse,
    summary="Fahrzeuge auflisten",
)
@limiter.limit("60/minute", key_func=get_user_identifier)  # Rate limit for list operations
async def list_vehicles(
    request: Request,
    space_id: uuid.UUID,
    vehicle_type: Optional[VehicleType] = Query(None, description="Filter nach Typ"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PrivatVehicleListResponse:
    """Listet alle Fahrzeuge eines Spaces.

    SECURITY FIX 24-6: PII Masking - VIN wird fuer Nicht-Owner maskiert.
    """
    space = await get_user_space_or_403(db, space_id, current_user)

    # SECURITY FIX 24-6: Pruefe Owner-Status fuer PII-Masking
    is_owner = space.owner_id == current_user.id

    result = await vehicle_service.list_vehicles(db, space_id, vehicle_type, page, page_size)

    # SECURITY FIX 24-6: PII Masking - VIN fuer Nicht-Owner maskieren
    for item in result.items:
        item.vin = mask_sensitive_field(item.vin, is_owner)

    return result


@router.get(
    "/vehicles/{vehicle_id}",
    response_model=PrivatVehicleWithStats,
    summary="Fahrzeug-Details abrufen",
)
@limiter.limit("60/minute", key_func=get_user_identifier)  # SECURITY FIX 21-6: Rate limit gegen Enumeration
async def get_vehicle(
    request: Request,  # Required for rate limiter
    vehicle_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PrivatVehicleWithStats:
    """Holt Fahrzeug-Details mit Statistiken.

    SECURITY FIX 23-19: PII Masking - insurance_number und VIN werden fuer
    Nicht-Owner maskiert um PII-Exposure zu verhindern.
    """
    # SECURITY: IDOR-sichere Methode - Access-Check integriert
    vehicle = await vehicle_service.get_vehicle_with_access_check(
        db, vehicle_id, current_user.id
    )
    if not vehicle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Fahrzeug nicht gefunden",
        )

    # SECURITY FIX 23-19: Pruefe Owner-Status fuer PII-Masking
    space = await space_service.get_by_id(db, vehicle.space_id)
    is_owner = space and space.owner_id == current_user.id

    # Hole zusaetzliche Details (Tankbelege, Statistiken)
    fuel_logs = await vehicle_service.list_fuel_logs(db, vehicle_id, limit=5)
    fuel_stats = await vehicle_service.get_fuel_statistics(db, vehicle_id)

    return PrivatVehicleWithStats(
        id=vehicle.id,
        space_id=vehicle.space_id,
        make=vehicle.make,
        model=vehicle.model,
        year=vehicle.year,
        license_plate=vehicle.license_plate,
        # SECURITY FIX 23-19: VIN teilweise maskieren fuer Nicht-Owner
        vin=mask_sensitive_field(vehicle.vin, is_owner),
        vehicle_type=vehicle.vehicle_type,
        fuel_type=vehicle.fuel_type,
        mileage=vehicle.mileage,
        purchase_date=vehicle.purchase_date,
        purchase_price=vehicle.purchase_price,
        current_value=vehicle.current_value,
        insurance_company=vehicle.insurance_company,
        # SECURITY FIX 23-19: insurance_number maskieren fuer Nicht-Owner
        insurance_number=mask_sensitive_field(vehicle.insurance_number, is_owner),
        tuev_due=vehicle.tuev_due,
        notes=vehicle.notes,
        is_active=vehicle.is_active,
        created_at=vehicle.created_at,
        updated_at=vehicle.updated_at,
        recent_fuel_logs=[PrivatFuelLogResponse.model_validate(log) for log in fuel_logs],
        total_fuel_cost_year=fuel_stats.get("total_cost_year", Decimal("0.00")),
        average_consumption=fuel_stats.get("average_consumption"),
    )


@router.patch(
    "/vehicles/{vehicle_id}",
    response_model=PrivatVehicleResponse,
    summary="Fahrzeug aktualisieren",
)
@limiter.limit("30/minute", key_func=get_user_identifier)  # Rate limit for update operations
async def update_vehicle(
    request: Request,
    vehicle_id: uuid.UUID,
    data: PrivatVehicleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PrivatVehicleResponse:
    """Aktualisiert ein Fahrzeug."""
    # SECURITY: IDOR-sichere Methode - Access-Check integriert
    vehicle = await vehicle_service.get_vehicle_with_access_check(
        db, vehicle_id, current_user.id
    )
    if not vehicle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Fahrzeug nicht gefunden",
        )

    updated = await vehicle_service.update_vehicle(db, vehicle_id, data)

    return PrivatVehicleResponse(
        id=updated.id,
        space_id=updated.space_id,
        name=updated.name,
        vehicle_type=VehicleType(updated.vehicle_type),
        brand=updated.brand,
        model=updated.model,
        year=updated.year,
        license_plate=updated.license_plate,
        vin=updated.vin,
        fuel_type=updated.fuel_type,
        purchase_date=updated.purchase_date,
        purchase_price=updated.purchase_price,
        current_mileage=updated.current_mileage,
        notes=updated.notes,
        is_active=updated.is_active,
        created_at=updated.created_at,
        updated_at=updated.updated_at,
    )


@router.delete(
    "/vehicles/{vehicle_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Fahrzeug löschen",
)
@limiter.limit("10/minute", key_func=get_user_identifier)  # Rate limit for delete operations
async def delete_vehicle(
    request: Request,
    vehicle_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> None:
    """Löscht ein Fahrzeug (soft delete)."""
    # SECURITY: IDOR-sichere Methode - Access-Check integriert
    vehicle = await vehicle_service.get_vehicle_with_access_check(
        db, vehicle_id, current_user.id
    )
    if not vehicle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Fahrzeug nicht gefunden",
        )

    await vehicle_service.delete_vehicle(db, vehicle_id)


# ==================== Fuel Logs ====================

@router.post(
    "/vehicles/{vehicle_id}/fuel",
    response_model=PrivatFuelLogResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Tankbeleg erfassen",
)
@limiter.limit("30/minute", key_func=get_user_identifier)  # SECURITY: Rate limit for fuel log creation
async def create_fuel_log(
    request: Request,  # SECURITY FIX 25-3: Required for rate limiter
    vehicle_id: uuid.UUID,
    data: PrivatFuelLogCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PrivatFuelLogResponse:
    """Erfasst einen Tankbeleg."""
    # SECURITY: IDOR-sichere Methode - Access-Check integriert
    vehicle = await vehicle_service.get_vehicle_with_access_check(
        db, vehicle_id, current_user.id
    )
    if not vehicle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Fahrzeug nicht gefunden",
        )

    log = await vehicle_service.create_fuel_log(db, vehicle_id, data)

    return PrivatFuelLogResponse(
        id=log.id,
        vehicle_id=log.vehicle_id,
        date=log.date,
        mileage=log.mileage,
        liters=log.liters,
        price_per_liter=log.price_per_liter,
        total_cost=log.total_cost,
        fuel_type=log.fuel_type,
        station=log.station,
        is_full_tank=log.is_full_tank,
        notes=log.notes,
        created_at=log.created_at,
    )


@router.get(
    "/vehicles/{vehicle_id}/fuel",
    response_model=List[PrivatFuelLogResponse],
    summary="Tankbelege auflisten",
)
@limiter.limit("60/minute", key_func=get_user_identifier)  # SECURITY FIX 23-13: Rate limit
async def list_fuel_logs(
    request: Request,  # Required for rate limiter
    vehicle_id: uuid.UUID,
    start_date: Optional[date] = Query(None, description="Start-Datum"),
    end_date: Optional[date] = Query(None, description="End-Datum"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> List[PrivatFuelLogResponse]:
    """Listet alle Tankbelege eines Fahrzeugs."""
    # SECURITY: IDOR-sichere Methode - Access-Check integriert
    vehicle = await vehicle_service.get_vehicle_with_access_check(
        db, vehicle_id, current_user.id
    )
    if not vehicle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Fahrzeug nicht gefunden",
        )

    return await vehicle_service.list_fuel_logs(db, vehicle_id, start_date, end_date)


@router.get(
    "/vehicles/{vehicle_id}/fuel/statistics",
    response_model=PrivatFuelStatisticsResponse,
    summary="Kraftstoff-Statistiken abrufen",
)
@limiter.limit("60/minute", key_func=get_user_identifier)  # SECURITY FIX 23-14: Rate limit
async def get_fuel_statistics(
    request: Request,  # Required for rate limiter
    vehicle_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PrivatFuelStatisticsResponse:
    """Holt Kraftstoff-Statistiken für ein Fahrzeug."""
    # SECURITY: IDOR-sichere Methode - Access-Check integriert
    vehicle = await vehicle_service.get_vehicle_with_access_check(
        db, vehicle_id, current_user.id
    )
    if not vehicle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Fahrzeug nicht gefunden",
        )

    stats = await vehicle_service.get_fuel_statistics(db, vehicle_id)
    return PrivatFuelStatisticsResponse(**stats)


# ==================== Insurances ====================

@router.post(
    "/spaces/{space_id}/insurances",
    response_model=PrivatInsuranceWithDeadlines,
    status_code=status.HTTP_201_CREATED,
    summary="Versicherung erstellen",
)
@limiter.limit("30/minute", key_func=get_user_identifier)  # SECURITY: Rate limit for create operations
async def create_insurance(
    request: Request,  # SECURITY FIX 25-4: Required for rate limiter
    space_id: uuid.UUID,
    data: PrivatInsuranceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PrivatInsuranceWithDeadlines:
    """Erstellt eine neue Versicherung."""
    # SECURITY FIX 26-10: Pruefe Owner-Status fuer PII-Masking
    space, is_owner = await get_user_space_with_owner_info(db, space_id, current_user, PrivatAccessLevel.WRITE)

    insurance = await insurance_service.create(db, space_id, data)

    # Baue Response mit Deadline-Infos
    upcoming_payment = insurance_service._calculate_next_payment(insurance)
    days_until = None
    if upcoming_payment:
        days_until = (upcoming_payment - date.today()).days

    annual_cost = insurance_service._calculate_annual_cost(insurance)

    return PrivatInsuranceWithDeadlines(
        id=insurance.id,
        space_id=insurance.space_id,
        name=insurance.name,
        insurance_type=InsuranceType(insurance.insurance_type),
        provider=insurance.provider,
        policy_number=mask_sensitive_field(insurance.policy_number, is_owner),
        premium=insurance.premium,
        premium_interval=insurance.premium_interval,
        coverage_amount=insurance.coverage_amount,
        deductible=insurance.deductible,
        start_date=insurance.start_date,
        end_date=insurance.end_date,
        cancellation_period=insurance.cancellation_period,
        auto_renewal=insurance.auto_renewal,
        notes=insurance.notes,
        is_active=insurance.is_active,
        created_at=insurance.created_at,
        updated_at=insurance.updated_at,
        upcoming_payment=upcoming_payment,
        days_until_payment=days_until,
        annual_cost=annual_cost,
    )


@router.get(
    "/spaces/{space_id}/insurances",
    response_model=PrivatInsuranceListResponse,
    summary="Versicherungen auflisten",
)
@limiter.limit("60/minute", key_func=get_user_identifier)  # SECURITY FIX 21-6: Rate limit
async def list_insurances(
    request: Request,  # Required for rate limiter
    space_id: uuid.UUID,
    insurance_type: Optional[InsuranceType] = Query(None, description="Filter nach Typ"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PrivatInsuranceListResponse:
    """Listet alle Versicherungen eines Spaces."""
    # SECURITY FIX 21-4: Pruefe Owner-Status fuer PII-Masking
    space, is_owner = await get_user_space_with_owner_info(db, space_id, current_user)

    result = await insurance_service.list_insurances(
        db, space_id, insurance_type, True, page, page_size
    )

    # SECURITY FIX 21-4: Maskiere policy_number fuer Nicht-Owner
    if not is_owner:
        for item in result.items:
            item.policy_number = mask_sensitive_field(item.policy_number, is_owner)

    return result


@router.patch(
    "/insurances/{insurance_id}",
    response_model=PrivatInsuranceWithDeadlines,
    summary="Versicherung aktualisieren",
)
@limiter.limit("30/minute", key_func=get_user_identifier)  # SECURITY: Rate limit for insurance updates
async def update_insurance(
    request: Request,  # Required for rate limiter
    insurance_id: uuid.UUID,
    data: PrivatInsuranceUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PrivatInsuranceWithDeadlines:
    """Aktualisiert eine Versicherung."""
    # SECURITY: IDOR-sichere Methode - Access-Check integriert
    insurance = await insurance_service.get_by_id_with_access_check(
        db, insurance_id, current_user.id
    )
    if not insurance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Versicherung nicht gefunden",
        )

    updated = await insurance_service.update(db, insurance_id, data)

    upcoming_payment = insurance_service._calculate_next_payment(updated)
    days_until = None
    if upcoming_payment:
        days_until = (upcoming_payment - date.today()).days

    annual_cost = insurance_service._calculate_annual_cost(updated)

    # SECURITY FIX 26-11: PII Masking - pruefe Owner-Status ueber Space
    space, is_owner = await get_user_space_with_owner_info(db, insurance.space_id, current_user)

    return PrivatInsuranceWithDeadlines(
        id=updated.id,
        space_id=updated.space_id,
        name=updated.name,
        insurance_type=InsuranceType(updated.insurance_type),
        provider=updated.provider,
        policy_number=mask_sensitive_field(updated.policy_number, is_owner),
        premium=updated.premium,
        premium_interval=updated.premium_interval,
        coverage_amount=updated.coverage_amount,
        deductible=updated.deductible,
        start_date=updated.start_date,
        end_date=updated.end_date,
        cancellation_period=updated.cancellation_period,
        auto_renewal=updated.auto_renewal,
        notes=updated.notes,
        is_active=updated.is_active,
        created_at=updated.created_at,
        updated_at=updated.updated_at,
        upcoming_payment=upcoming_payment,
        days_until_payment=days_until,
        annual_cost=annual_cost,
    )


@router.delete(
    "/insurances/{insurance_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Versicherung löschen",
)
@limiter.limit("10/minute", key_func=get_user_identifier)  # Rate limit for delete operations
async def delete_insurance(
    request: Request,
    insurance_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> None:
    """Löscht eine Versicherung (soft delete)."""
    # SECURITY: IDOR-sichere Methode - Access-Check integriert
    insurance = await insurance_service.get_by_id_with_access_check(
        db, insurance_id, current_user.id
    )
    if not insurance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Versicherung nicht gefunden",
        )

    await insurance_service.delete(db, insurance_id)


# ==================== Loans ====================

@router.post(
    "/spaces/{space_id}/loans",
    response_model=PrivatLoanWithStats,
    status_code=status.HTTP_201_CREATED,
    summary="Kredit erstellen",
)
@limiter.limit("30/minute", key_func=get_user_identifier)  # SECURITY: Rate limit for create operations
async def create_loan(
    request: Request,  # SECURITY FIX 24-1: Required for rate limiter
    space_id: uuid.UUID,
    data: PrivatLoanCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PrivatLoanWithStats:
    """Erstellt einen neuen Kredit."""
    # SECURITY FIX 26-4: Pruefe Owner-Status fuer PII-Masking
    space, is_owner = await get_user_space_with_owner_info(db, space_id, current_user, PrivatAccessLevel.WRITE)

    loan = await loan_service.create(db, space_id, data)
    stats = loan_service._calculate_loan_stats(loan)

    return PrivatLoanWithStats(
        id=loan.id,
        space_id=loan.space_id,
        name=loan.name,
        loan_type=LoanType(loan.loan_type),
        lender=loan.lender,
        principal_amount=loan.principal_amount,
        current_balance=loan.current_balance,
        interest_rate=loan.interest_rate,
        monthly_payment=loan.monthly_payment,
        start_date=loan.start_date,
        end_date=loan.end_date,
        next_payment_date=loan.next_payment_date,
        account_number=mask_sensitive_field(loan.account_number, is_owner),
        notes=loan.notes,
        is_active=loan.is_active,
        created_at=loan.created_at,
        updated_at=loan.updated_at,
        **stats,
    )


@router.get(
    "/spaces/{space_id}/loans",
    response_model=PrivatLoanListResponse,
    summary="Kredite auflisten",
)
@limiter.limit("60/minute", key_func=get_user_identifier)  # SECURITY FIX 21-6: Rate limit
async def list_loans(
    request: Request,  # Required for rate limiter
    space_id: uuid.UUID,
    loan_type: Optional[LoanType] = Query(None, description="Filter nach Typ"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PrivatLoanListResponse:
    """Listet alle Kredite eines Spaces."""
    # SECURITY FIX 21-4: Pruefe Owner-Status fuer PII-Masking
    space, is_owner = await get_user_space_with_owner_info(db, space_id, current_user)

    result = await loan_service.list_loans(db, space_id, loan_type, True, page, page_size)

    # SECURITY FIX 21-4: Maskiere account_number fuer Nicht-Owner
    if not is_owner:
        for item in result.items:
            item.account_number = mask_sensitive_field(item.account_number, is_owner)

    return result


@router.post(
    "/loans/{loan_id}/payment",
    response_model=PrivatLoanWithStats,
    summary="Zahlung erfassen",
)
@limiter.limit("30/minute", key_func=get_user_identifier)  # SECURITY: Rate limit for payment recording
async def record_loan_payment(
    request: Request,  # SECURITY FIX 25-5: Required for rate limiter
    loan_id: uuid.UUID,
    amount: Decimal = Query(..., description="Zahlungsbetrag"),
    payment_date: Optional[date] = Query(None, description="Zahlungsdatum"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PrivatLoanWithStats:
    """Erfasst eine Kreditzahlung."""
    # SECURITY: IDOR-sichere Methode - Access-Check integriert
    loan = await loan_service.get_by_id_with_access_check(
        db, loan_id, current_user.id
    )
    if not loan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kredit nicht gefunden",
        )

    updated = await loan_service.record_payment(db, loan_id, amount, payment_date)
    stats = loan_service._calculate_loan_stats(updated)

    # SECURITY FIX 26-5: PII Masking - pruefe Owner-Status ueber Space
    space, is_owner = await get_user_space_with_owner_info(db, loan.space_id, current_user)

    return PrivatLoanWithStats(
        id=updated.id,
        space_id=updated.space_id,
        name=updated.name,
        loan_type=LoanType(updated.loan_type),
        lender=updated.lender,
        principal_amount=updated.principal_amount,
        current_balance=updated.current_balance,
        interest_rate=updated.interest_rate,
        monthly_payment=updated.monthly_payment,
        start_date=updated.start_date,
        end_date=updated.end_date,
        next_payment_date=updated.next_payment_date,
        account_number=mask_sensitive_field(updated.account_number, is_owner),
        notes=updated.notes,
        is_active=updated.is_active,
        created_at=updated.created_at,
        updated_at=updated.updated_at,
        **stats,
    )


@router.patch(
    "/loans/{loan_id}",
    response_model=PrivatLoanWithStats,
    summary="Kredit aktualisieren",
)
@limiter.limit("30/minute", key_func=get_user_identifier)  # SECURITY: Rate limit for loan updates
async def update_loan(
    request: Request,  # Required for rate limiter
    loan_id: uuid.UUID,
    data: PrivatLoanUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PrivatLoanWithStats:
    """Aktualisiert einen Kredit."""
    # SECURITY: IDOR-sichere Methode - Access-Check integriert
    loan = await loan_service.get_by_id_with_access_check(
        db, loan_id, current_user.id
    )
    if not loan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kredit nicht gefunden",
        )

    updated = await loan_service.update(db, loan_id, data)
    stats = loan_service._calculate_loan_stats(updated)

    # SECURITY FIX 26-6: PII Masking - pruefe Owner-Status ueber Space
    space, is_owner = await get_user_space_with_owner_info(db, loan.space_id, current_user)

    return PrivatLoanWithStats(
        id=updated.id,
        space_id=updated.space_id,
        name=updated.name,
        loan_type=LoanType(updated.loan_type),
        lender=updated.lender,
        principal_amount=updated.principal_amount,
        current_balance=updated.current_balance,
        interest_rate=updated.interest_rate,
        monthly_payment=updated.monthly_payment,
        start_date=updated.start_date,
        end_date=updated.end_date,
        next_payment_date=updated.next_payment_date,
        account_number=mask_sensitive_field(updated.account_number, is_owner),
        notes=updated.notes,
        is_active=updated.is_active,
        created_at=updated.created_at,
        updated_at=updated.updated_at,
        **stats,
    )


@router.delete(
    "/loans/{loan_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Kredit löschen",
)
@limiter.limit("10/minute", key_func=get_user_identifier)  # Rate limit for delete operations
async def delete_loan(
    request: Request,
    loan_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> None:
    """Löscht einen Kredit (soft delete)."""
    # SECURITY: IDOR-sichere Methode - Access-Check integriert
    loan = await loan_service.get_by_id_with_access_check(
        db, loan_id, current_user.id
    )
    if not loan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kredit nicht gefunden",
        )

    await loan_service.delete(db, loan_id)


# ==================== Investments ====================

@router.post(
    "/spaces/{space_id}/investments",
    response_model=PrivatInvestmentWithStats,
    status_code=status.HTTP_201_CREATED,
    summary="Geldanlage erstellen",
)
@limiter.limit("30/minute", key_func=get_user_identifier)  # SECURITY: Rate limit for create operations
async def create_investment(
    request: Request,  # SECURITY FIX 24-2: Required for rate limiter
    space_id: uuid.UUID,
    data: PrivatInvestmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PrivatInvestmentWithStats:
    """Erstellt eine neue Geldanlage."""
    # SECURITY FIX 26-7: Pruefe Owner-Status fuer PII-Masking
    space, is_owner = await get_user_space_with_owner_info(db, space_id, current_user, PrivatAccessLevel.WRITE)

    investment = await investment_service.create(db, space_id, data)
    stats = investment_service._calculate_investment_stats(investment)

    return PrivatInvestmentWithStats(
        id=investment.id,
        space_id=investment.space_id,
        name=investment.name,
        investment_type=InvestmentType(investment.investment_type),
        institution=investment.institution,
        account_number=mask_sensitive_field(investment.account_number, is_owner),
        initial_amount=investment.initial_amount,
        current_value=investment.current_value,
        interest_rate=investment.interest_rate,
        start_date=investment.start_date,
        maturity_date=investment.maturity_date,
        is_taxable=investment.is_taxable,
        notes=investment.notes,
        is_active=investment.is_active,
        created_at=investment.created_at,
        updated_at=investment.updated_at,
        **stats,
    )


@router.get(
    "/spaces/{space_id}/investments",
    response_model=PrivatInvestmentListResponse,
    summary="Geldanlagen auflisten",
)
@limiter.limit("60/minute", key_func=get_user_identifier)  # SECURITY FIX 21-6: Rate limit
async def list_investments(
    request: Request,  # Required for rate limiter
    space_id: uuid.UUID,
    investment_type: Optional[InvestmentType] = Query(None, description="Filter nach Typ"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PrivatInvestmentListResponse:
    """Listet alle Geldanlagen eines Spaces."""
    # SECURITY FIX 21-4: Pruefe Owner-Status fuer PII-Masking
    space, is_owner = await get_user_space_with_owner_info(db, space_id, current_user)

    result = await investment_service.list_investments(
        db, space_id, investment_type, True, page, page_size
    )

    # SECURITY FIX 21-4: Maskiere account_number fuer Nicht-Owner
    if not is_owner:
        for item in result.items:
            item.account_number = mask_sensitive_field(item.account_number, is_owner)

    return result


@router.post(
    "/investments/{investment_id}/value",
    response_model=PrivatInvestmentWithStats,
    summary="Wert aktualisieren",
)
@limiter.limit("30/minute", key_func=get_user_identifier)  # SECURITY: Rate limit for value updates
async def update_investment_value(
    request: Request,  # SECURITY FIX 24-3: Required for rate limiter
    investment_id: uuid.UUID,
    new_value: Decimal = Query(..., description="Neuer aktueller Wert"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PrivatInvestmentWithStats:
    """Aktualisiert den aktuellen Wert einer Geldanlage."""
    # SECURITY: IDOR-sichere Methode - Access-Check integriert
    investment = await investment_service.get_by_id_with_access_check(
        db, investment_id, current_user.id
    )
    if not investment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Geldanlage nicht gefunden",
        )

    updated = await investment_service.update_value(db, investment_id, new_value)
    stats = investment_service._calculate_investment_stats(updated)

    # SECURITY FIX 26-8: PII Masking - pruefe Owner-Status ueber Space
    space, is_owner = await get_user_space_with_owner_info(db, investment.space_id, current_user)

    return PrivatInvestmentWithStats(
        id=updated.id,
        space_id=updated.space_id,
        name=updated.name,
        investment_type=InvestmentType(updated.investment_type),
        institution=updated.institution,
        account_number=mask_sensitive_field(updated.account_number, is_owner),
        initial_amount=updated.initial_amount,
        current_value=updated.current_value,
        interest_rate=updated.interest_rate,
        start_date=updated.start_date,
        maturity_date=updated.maturity_date,
        is_taxable=updated.is_taxable,
        notes=updated.notes,
        is_active=updated.is_active,
        created_at=updated.created_at,
        updated_at=updated.updated_at,
        **stats,
    )


@router.get(
    "/spaces/{space_id}/investments/portfolio",
    response_model=PrivatPortfolioBreakdownResponse,
    summary="Portfolio-Übersicht abrufen",
)
@limiter.limit("60/minute", key_func=get_user_identifier)  # SECURITY FIX 23-15: Rate limit
async def get_portfolio_breakdown(
    request: Request,  # Required for rate limiter
    space_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PrivatPortfolioBreakdownResponse:
    """Holt die Portfolio-Verteilung nach Anlagetyp."""
    await get_user_space_or_403(db, space_id, current_user)

    data = await investment_service.get_portfolio_breakdown(db, space_id)
    return PrivatPortfolioBreakdownResponse(**data)


@router.patch(
    "/investments/{investment_id}",
    response_model=PrivatInvestmentWithStats,
    summary="Geldanlage aktualisieren",
)
@limiter.limit("30/minute", key_func=get_user_identifier)  # SECURITY: Rate limit for investment updates
async def update_investment(
    request: Request,  # Required for rate limiter
    investment_id: uuid.UUID,
    data: PrivatInvestmentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PrivatInvestmentWithStats:
    """Aktualisiert eine Geldanlage."""
    # SECURITY: IDOR-sichere Methode - Access-Check integriert
    investment = await investment_service.get_by_id_with_access_check(
        db, investment_id, current_user.id
    )
    if not investment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Geldanlage nicht gefunden",
        )

    updated = await investment_service.update(db, investment_id, data)
    stats = investment_service._calculate_investment_stats(updated)

    # SECURITY FIX 26-9: PII Masking - pruefe Owner-Status ueber Space
    space, is_owner = await get_user_space_with_owner_info(db, investment.space_id, current_user)

    return PrivatInvestmentWithStats(
        id=updated.id,
        space_id=updated.space_id,
        name=updated.name,
        investment_type=InvestmentType(updated.investment_type),
        institution=updated.institution,
        account_number=mask_sensitive_field(updated.account_number, is_owner),
        initial_amount=updated.initial_amount,
        current_value=updated.current_value,
        interest_rate=updated.interest_rate,
        start_date=updated.start_date,
        maturity_date=updated.maturity_date,
        is_taxable=updated.is_taxable,
        notes=updated.notes,
        is_active=updated.is_active,
        created_at=updated.created_at,
        updated_at=updated.updated_at,
        **stats,
    )


@router.delete(
    "/investments/{investment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Geldanlage löschen",
)
@limiter.limit("10/minute", key_func=get_user_identifier)  # Rate limit for delete operations
async def delete_investment(
    request: Request,
    investment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> None:
    """Löscht eine Geldanlage (soft delete)."""
    # SECURITY: IDOR-sichere Methode - Access-Check integriert
    investment = await investment_service.get_by_id_with_access_check(
        db, investment_id, current_user.id
    )
    if not investment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Geldanlage nicht gefunden",
        )

    await investment_service.delete(db, investment_id)


# ==================== Deadlines ====================

@router.post(
    "/spaces/{space_id}/deadlines",
    response_model=PrivatDeadlineWithStatus,
    status_code=status.HTTP_201_CREATED,
    summary="Frist erstellen",
)
@limiter.limit("30/minute", key_func=get_user_identifier)  # SECURITY: Rate limit for create operations
async def create_deadline(
    request: Request,  # SECURITY FIX 25-6: Required for rate limiter
    space_id: uuid.UUID,
    data: PrivatDeadlineCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PrivatDeadlineWithStatus:
    """Erstellt eine neue Frist."""
    await get_user_space_or_403(db, space_id, current_user, PrivatAccessLevel.WRITE)

    deadline = await deadline_service.create(db, space_id, data)

    return await deadline_service._to_deadline_with_status(db, deadline)


@router.get(
    "/spaces/{space_id}/deadlines",
    response_model=PrivatDeadlineListResponse,
    summary="Fristen auflisten",
)
@limiter.limit("60/minute", key_func=get_user_identifier)  # SECURITY FIX 23-16: Rate limit
async def list_deadlines(
    request: Request,  # Required for rate limiter
    space_id: uuid.UUID,
    include_completed: bool = Query(False, description="Erledigte einschließen"),
    deadline_type: Optional[PrivatDeadlineType] = Query(None, description="Filter nach Typ"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PrivatDeadlineListResponse:
    """Listet alle Fristen eines Spaces."""
    await get_user_space_or_403(db, space_id, current_user)

    return await deadline_service.list_deadlines(
        db, space_id, include_completed, deadline_type, page, page_size
    )


@router.get(
    "/spaces/{space_id}/deadlines/widget",
    response_model=PrivatDeadlineWidget,
    summary="Fristen-Widget abrufen",
)
@limiter.limit("60/minute", key_func=get_user_identifier)  # SECURITY FIX 23-17: Rate limit
async def get_deadline_widget(
    request: Request,  # Required for rate limiter
    space_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PrivatDeadlineWidget:
    """Holt das Fristen-Widget für das Dashboard."""
    await get_user_space_or_403(db, space_id, current_user)

    return await deadline_service.get_dashboard_widget(db, space_id)


@router.post(
    "/deadlines/{deadline_id}/complete",
    response_model=PrivatDeadlineWithStatus,
    summary="Frist als erledigt markieren",
)
@limiter.limit("30/minute", key_func=get_user_identifier)  # SECURITY FIX 20-15: Rate limit for complete
async def complete_deadline(
    request: Request,  # Required for rate limiter
    deadline_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PrivatDeadlineWithStatus:
    """Markiert eine Frist als erledigt."""
    # SECURITY: IDOR-sichere Methode - Access-Check integriert
    deadline = await deadline_service.get_by_id_with_access_check(
        db, deadline_id, current_user.id
    )
    if not deadline:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Frist nicht gefunden",
        )

    completed = await deadline_service.complete(db, deadline_id)

    return await deadline_service._to_deadline_with_status(db, completed)


@router.patch(
    "/deadlines/{deadline_id}",
    response_model=PrivatDeadlineWithStatus,
    summary="Frist aktualisieren",
)
@limiter.limit("30/minute", key_func=get_user_identifier)  # SECURITY: Rate limit for deadline updates
async def update_deadline(
    request: Request,  # Required for rate limiter
    deadline_id: uuid.UUID,
    data: PrivatDeadlineUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PrivatDeadlineWithStatus:
    """Aktualisiert eine Frist."""
    # SECURITY: IDOR-sichere Methode - Access-Check integriert
    deadline = await deadline_service.get_by_id_with_access_check(
        db, deadline_id, current_user.id
    )
    if not deadline:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Frist nicht gefunden",
        )

    updated = await deadline_service.update(db, deadline_id, data)

    return await deadline_service._to_deadline_with_status(db, updated)


@router.delete(
    "/deadlines/{deadline_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Frist löschen",
)
@limiter.limit("10/minute", key_func=get_user_identifier)  # Rate limit for delete operations
async def delete_deadline(
    request: Request,
    deadline_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> None:
    """Löscht eine Frist."""
    # SECURITY: IDOR-sichere Methode - Access-Check integriert
    deadline = await deadline_service.get_by_id_with_access_check(
        db, deadline_id, current_user.id
    )
    if not deadline:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Frist nicht gefunden",
        )

    await deadline_service.delete(db, deadline_id)


@router.get(
    "/spaces/{space_id}/deadlines/calendar",
    summary="Kalender exportieren (iCal)",
)
@limiter.limit("30/minute", key_func=get_user_identifier)  # SECURITY FIX 23-18: Stricter rate limit for export
async def export_calendar(
    request: Request,  # Required for rate limiter
    space_id: uuid.UUID,
    include_completed: bool = Query(False, description="Erledigte einschließen"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Response:
    """Exportiert alle Fristen als iCal-Datei."""
    await get_user_space_or_403(db, space_id, current_user)

    ical_bytes = await deadline_service.export_calendar(db, space_id, include_completed)

    return Response(
        content=ical_bytes,
        media_type="text/calendar",
        headers={
            # SECURITY: Use sanitized Content-Disposition (Phase 10)
            "Content-Disposition": build_content_disposition("privat-fristen.ics", "attachment"),
        },
    )


# ==================== Emergency Access ====================

@router.post(
    "/spaces/{space_id}/emergency/contacts",
    response_model=PrivatEmergencyContactResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Vertrauensperson hinzufügen",
)
@limiter.limit("5/minute", key_func=get_user_identifier)  # SECURITY: Strict rate limit for emergency contacts
async def create_emergency_contact(
    request: Request,  # Required for rate limiter
    space_id: uuid.UUID,
    data: PrivatEmergencyContactCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PrivatEmergencyContactResponse:
    """Fügt eine Vertrauensperson für Notfallzugriff hinzu."""
    await get_user_space_or_403(db, space_id, current_user, PrivatAccessLevel.ADMIN)

    contact = await emergency_service.create_contact(db, space_id, data)

    return PrivatEmergencyContactResponse(
        id=contact.id,
        space_id=contact.space_id,
        first_name=contact.first_name,
        last_name=contact.last_name,
        email=contact.email,
        phone=contact.phone,
        relationship=contact.relationship,
        waiting_period_days=contact.waiting_period_days,
        notes=contact.notes,
        is_active=contact.is_active,
        created_at=contact.created_at,
        updated_at=contact.updated_at,
    )


@router.get(
    "/spaces/{space_id}/emergency/contacts",
    response_model=List[PrivatEmergencyContactResponse],
    summary="Vertrauenspersonen auflisten",
)
@limiter.limit("30/minute", key_func=get_user_identifier)  # SECURITY: Rate limit for emergency access
async def list_emergency_contacts(
    request: Request,  # Required for rate limiter
    space_id: uuid.UUID,
    page: int = Query(1, ge=1, description="Seite"),  # SECURITY FIX 22-4: Pagination
    page_size: int = Query(50, ge=1, le=100, description="Eintraege pro Seite"),  # Max 100
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> List[PrivatEmergencyContactResponse]:
    """Listet alle Vertrauenspersonen eines Spaces.

    SECURITY FIX 25-10: PII Masking - phone und email werden fuer Nicht-Owner maskiert.
    """
    space = await get_user_space_or_403(db, space_id, current_user, PrivatAccessLevel.MANAGE)

    # SECURITY FIX 25-10: Pruefe Owner-Status fuer PII-Masking
    is_owner = space.owner_id == current_user.id

    # SECURITY FIX 22-4: Pagination um DoS zu verhindern
    contacts = await emergency_service.list_contacts(
        db, space_id, page=page, page_size=page_size
    )

    # SECURITY FIX 25-10: PII Masking - phone/email fuer Nicht-Owner maskieren
    for contact in contacts:
        contact.phone = mask_sensitive_field(contact.phone, is_owner)
        contact.email = mask_sensitive_field(contact.email, is_owner)

    return contacts


@router.patch(
    "/emergency/contacts/{contact_id}",
    response_model=PrivatEmergencyContactResponse,
    summary="Vertrauensperson aktualisieren",
)
@limiter.limit("10/minute", key_func=get_user_identifier)  # SECURITY: Rate limit for emergency contact updates
async def update_emergency_contact(
    request: Request,  # Required for rate limiter
    contact_id: uuid.UUID,
    data: PrivatEmergencyContactUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PrivatEmergencyContactResponse:
    """Aktualisiert eine Vertrauensperson."""
    # SECURITY: IDOR-sichere Methode - Access-Check integriert
    contact = await emergency_service.get_contact_with_access_check(
        db, contact_id, current_user.id
    )
    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vertrauensperson nicht gefunden",
        )

    updated = await emergency_service.update_contact(db, contact_id, data)

    return PrivatEmergencyContactResponse(
        id=updated.id,
        space_id=updated.space_id,
        first_name=updated.first_name,
        last_name=updated.last_name,
        email=updated.email,
        phone=updated.phone,
        relationship=updated.relationship,
        waiting_period_days=updated.waiting_period_days,
        notes=updated.notes,
        is_active=updated.is_active,
        created_at=updated.created_at,
        updated_at=updated.updated_at,
    )


@router.delete(
    "/emergency/contacts/{contact_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Vertrauensperson entfernen",
)
@limiter.limit("5/minute", key_func=get_user_identifier)  # SECURITY: Strict rate limit for emergency contact deletion
async def delete_emergency_contact(
    request: Request,  # Required for rate limiter
    contact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> None:
    """Entfernt eine Vertrauensperson."""
    # SECURITY: IDOR-sichere Methode - Access-Check integriert
    contact = await emergency_service.get_contact_with_access_check(
        db, contact_id, current_user.id
    )
    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vertrauensperson nicht gefunden",
        )

    await emergency_service.delete_contact(db, contact_id)


@router.post(
    "/emergency/request",
    response_model=PrivatEmergencyAccessRequestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Notfallzugriff anfordern",
)
@limiter.limit("2/minute", key_func=get_user_identifier)  # SECURITY: CRITICAL - Very strict rate limit for emergency access requests
async def request_emergency_access(
    request: Request,  # Required for rate limiter
    data: PrivatEmergencyAccessRequestCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PrivatEmergencyAccessRequestResponse:
    """Fordert Notfallzugriff auf einen Space an (als Vertrauensperson)."""
    access_request = await emergency_service.request_access(db, current_user.email, data)

    if not access_request:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sie sind nicht als Vertrauensperson für diesen Bereich registriert",
        )

    return PrivatEmergencyAccessRequestResponse(
        id=access_request.id,
        space_id=access_request.space_id,
        contact_id=access_request.contact_id,
        status=PrivatEmergencyAccessStatus(access_request.status),
        reason=access_request.reason,
        requested_at=access_request.requested_at,
        waiting_until=access_request.waiting_until,
        approved_at=access_request.approved_at,
        denied_at=access_request.denied_at,
        denied_reason=access_request.denied_reason,
    )


@router.get(
    "/spaces/{space_id}/emergency/requests",
    response_model=List[PrivatEmergencyAccessRequestResponse],
    summary="Notfallzugriff-Anfragen auflisten",
)
@limiter.limit("30/minute", key_func=get_user_identifier)  # SECURITY: Rate limit for emergency requests list
async def list_emergency_requests(
    request: Request,  # Required for rate limiter
    space_id: uuid.UUID,
    status_filter: Optional[PrivatEmergencyAccessStatus] = Query(None, description="Filter nach Status"),
    page: int = Query(1, ge=1, description="Seite"),  # SECURITY FIX 22-5: Pagination
    page_size: int = Query(50, ge=1, le=100, description="Eintraege pro Seite"),  # Max 100
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> List[PrivatEmergencyAccessRequestResponse]:
    """Listet alle Notfallzugriff-Anfragen eines Spaces."""
    await get_user_space_or_403(db, space_id, current_user, PrivatAccessLevel.ADMIN)

    # SECURITY FIX 22-5: Pagination um DoS zu verhindern
    return await emergency_service.list_requests(
        db, space_id, status_filter, page=page, page_size=page_size
    )


@router.post(
    "/emergency/requests/{request_id}/approve",
    response_model=PrivatEmergencyAccessRequestResponse,
    summary="Notfallzugriff genehmigen",
)
@limiter.limit("5/minute", key_func=get_user_identifier)  # SECURITY: Strict rate limit for emergency request approval
async def approve_emergency_request(
    request: Request,  # Required for rate limiter
    request_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PrivatEmergencyAccessRequestResponse:
    """Genehmigt eine Notfallzugriff-Anfrage (durch Owner)."""
    # SECURITY: IDOR-sichere Methode - Access-Check integriert (nur Owner)
    access_request = await emergency_service.get_request_with_access_check(
        db, request_id, current_user.id
    )
    if not access_request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Anfrage nicht gefunden",
        )

    try:
        approved = await emergency_service.approve_request(db, request_id, current_user.id)
    except ValueError:
        # SECURITY: Do NOT expose internal error messages
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Anfrage kann nicht genehmigt werden",
        )

    return PrivatEmergencyAccessRequestResponse(
        id=approved.id,
        space_id=approved.space_id,
        contact_id=approved.contact_id,
        status=PrivatEmergencyAccessStatus(approved.status),
        reason=approved.reason,
        requested_at=approved.requested_at,
        waiting_until=approved.waiting_until,
        approved_at=approved.approved_at,
        denied_at=approved.denied_at,
        denied_reason=approved.denied_reason,
    )


@router.post(
    "/emergency/requests/{request_id}/deny",
    response_model=PrivatEmergencyAccessRequestResponse,
    summary="Notfallzugriff ablehnen",
)
@limiter.limit("5/minute", key_func=get_user_identifier)  # SECURITY: Strict rate limit for emergency request denial
async def deny_emergency_request(
    request: Request,  # Required for rate limiter
    request_id: uuid.UUID,
    reason: str = Query(..., description="Ablehnungsgrund", max_length=1000),  # INPUT VALIDATION
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PrivatEmergencyAccessRequestResponse:
    """Lehnt eine Notfallzugriff-Anfrage ab (durch Owner)."""
    # SECURITY: IDOR-sichere Methode - Access-Check integriert (nur Owner)
    access_request = await emergency_service.get_request_with_access_check(
        db, request_id, current_user.id
    )
    if not access_request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Anfrage nicht gefunden",
        )

    try:
        denied = await emergency_service.deny_request(db, request_id, current_user.id, reason)
    except ValueError:
        # SECURITY: Do NOT expose internal error messages
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Anfrage kann nicht abgelehnt werden",
        )

    return PrivatEmergencyAccessRequestResponse(
        id=denied.id,
        space_id=denied.space_id,
        contact_id=denied.contact_id,
        status=PrivatEmergencyAccessStatus(denied.status),
        reason=denied.reason,
        requested_at=denied.requested_at,
        waiting_until=denied.waiting_until,
        approved_at=denied.approved_at,
        denied_at=denied.denied_at,
        denied_reason=denied.denied_reason,
    )


@router.post(
    "/emergency/requests/{request_id}/revoke",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Genehmigten Zugriff widerrufen",
)
@limiter.limit("5/minute", key_func=get_user_identifier)  # SECURITY: Strict rate limit for emergency access revocation
async def revoke_emergency_access(
    request: Request,  # Required for rate limiter
    request_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> None:
    """Widerruft einen genehmigten Notfallzugriff."""
    # SECURITY: IDOR-sichere Methode - Access-Check integriert (nur Owner)
    access_request = await emergency_service.get_request_with_access_check(
        db, request_id, current_user.id
    )
    if not access_request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Anfrage nicht gefunden",
        )

    success = await emergency_service.revoke_emergency_access(db, request_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Zugriff kann nicht widerrufen werden",
        )

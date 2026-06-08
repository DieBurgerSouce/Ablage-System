"""
Company API Endpoints.

Verwaltet Firmen im Multi-Mandanten-System:
- Firmen-CRUD für autorisierte Benutzer
- Firmenwechsel (aktuelle Firma setzen)
- Benutzer-Firmen-Zuordnung

Alle Antworten auf Deutsch.
"""

from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status, Request, Response
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
import structlog

from app.api.dependencies import get_db, get_current_active_user
from app.db.models import User, Company, UserCompany
from app.core.safe_errors import safe_error_log
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
from app.services.company_metrics_service import (

    company_metrics_service,
    CompanyMetrics,
    DashboardSummary,
)

logger = structlog.get_logger(__name__)

# ==================== Router ====================

router = APIRouter(prefix="/companies", tags=["Firmen"])


# ==================== Company Endpoints ====================

@router.get(
    "",
    response_model=CompanyListResponse,
    summary="Firmen des Benutzers auflisten",
    description="Gibt alle Firmen zurück, auf die der aktuelle Benutzer Zugriff hat."
)
async def list_companies(
    request: Request,
    page: int = Query(1, ge=1, description="Seitennummer (1-basiert)"),
    per_page: int = Query(50, ge=1, le=100, description="Eintraege pro Seite"),
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
    query = query.order_by(Company.name).offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    companies = result.scalars().all()

    # Get current company ID
    # get_current_company ist eine Dependency (request, db); den User ermittelt
    # sie selbst aus dem Request. Ein dritter Positional-Arg (current_user) warf
    # frueher TypeError -> HTTP 500 (Firmen-Liste kaputt).
    current_company = await get_current_company(request, db)
    current_id = current_company.id if current_company else None

    return CompanyListResponse(
        items=[CompanyResponse.model_validate(c) for c in companies],
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

    # Prüfe ob Firmenname bereits existiert
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
        short_name=data.short_name,
        display_name=data.display_name,
        legal_form=data.legal_form,
        commercial_register=data.commercial_register,
        court=data.court,
        vat_id=data.vat_id,
        tax_number=data.tax_number,
        street=data.street,
        street_number=data.street_number,
        postal_code=data.postal_code,
        city=data.city,
        country=data.country or "DE",
        email=data.email,
        phone=data.phone,
        website=data.website,
        iban=data.iban,
        bic=data.bic,
        bank_name=data.bank_name,
        default_currency=data.default_currency or "EUR",
        kontenrahmen=data.kontenrahmen or "SKR03",
        fiscal_year_start=data.fiscal_year_start or 1,
        alternative_names=data.alternative_names or [],
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

    return CompanyResponse.model_validate(company)


@router.get(
    "/current",
    response_model=CompanyResponse,
    summary="Aktuelle Firma abrufen",
    description="Gibt die aktuell ausgewaehlte Firma des Benutzers zurück.",
    responses={404: {"description": "Keine aktuelle Firma ausgewaehlt"}}
)
async def get_current_company_endpoint(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> CompanyResponse:
    """Gibt die aktuelle Firma zurück."""

    # get_current_company ermittelt den User selbst aus dem Request; ein dritter
    # Positional-Arg warf frueher TypeError -> HTTP 500.
    company = await get_current_company(request, db)

    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Keine aktuelle Firma ausgewaehlt. Bitte wählen Sie eine Firma aus."
        )

    return CompanyResponse.model_validate(company)


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
        logger.warning("company_switch_failed", **safe_error_log(e))
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

    return CompanyResponse.model_validate(company)


@router.get(
    "/{company_id}",
    response_model=CompanyResponse,
    summary="Firma abrufen",
    description="Gibt Details einer spezifischen Firma zurück."
)
async def get_company(
    company_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> CompanyResponse:
    """Gibt eine spezifische Firma zurück."""

    # Prüfe Zugriff
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

    return CompanyResponse.model_validate(company)


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

    # Prüfe Berechtigung (Owner oder Admin)
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
            detail="Nur Owner und Admins können Firmendaten ändern."
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

    company.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(company)

    logger.info(
        "company_updated",
        company_id=str(company.id),
        updated_fields=list(update_data.keys()),
        user_id=str(current_user.id),
    )

    return CompanyResponse.model_validate(company)


@router.delete(
    "/{company_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Firma löschen (Soft-Delete)",
    description="Setzt deleted_at für die Firma. Nur Owner."
)
async def delete_company(
    company_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Response:
    """Löscht eine Firma (Soft-Delete)."""

    # Prüfe Berechtigung (nur Owner)
    access_result = await db.execute(
        select(UserCompany)
        .where(UserCompany.user_id == current_user.id)
        .where(UserCompany.company_id == company_id)
    )
    user_company = access_result.scalar_one_or_none()

    if not user_company or user_company.role != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nur der Firmen-Owner kann die Firma löschen."
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
    company.deleted_at = datetime.now(timezone.utc)
    company.is_active = False

    await db.commit()

    logger.info(
        "company_deleted",
        company_id=str(company.id),
        company_name=company.name,
        user_id=str(current_user.id),
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ==================== Dashboard Endpoints ====================

@router.get(
    "/dashboard",
    summary="Multi-Firma Dashboard abrufen",
    description="Gibt eine Übersicht aller Firmen-Metriken zurück, auf die der Benutzer Zugriff hat."
)
async def get_dashboard(
    include_inactive: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> dict:
    """
    Holt das Multi-Firma Dashboard.

    Zeigt:
    - Zusammenfassung aller Firmen
    - Metriken pro Firma (sortiert nach Health Score)
    - KPIs und Trends

    Args:
        include_inactive: Auch inaktive Firmen einbeziehen

    Returns:
        Dashboard-Daten mit Summary und Company-Metrics
    """
    # Prüfe welche Firmen der Benutzer sehen darf
    user_companies_query = (
        select(UserCompany.company_id)
        .where(UserCompany.user_id == current_user.id)
    )
    user_companies_result = await db.execute(user_companies_query)
    allowed_company_ids = [row[0] for row in user_companies_result.fetchall()]

    if not allowed_company_ids:
        return {
            "summary": DashboardSummary().to_dict(),
            "companies": [],
            "alerts": [],
        }

    # Hole Summary (nur für erlaubte Firmen)
    summary = await company_metrics_service.get_dashboard_summary(db)

    # Hole Metriken für alle Firmen
    all_metrics = await company_metrics_service.get_all_company_metrics(
        db, include_inactive=include_inactive
    )

    # Filtere auf erlaubte Firmen
    allowed_metrics = [
        m for m in all_metrics if m.company_id in allowed_company_ids
    ]

    # Generiere Alerts
    alerts = _generate_dashboard_alerts(allowed_metrics)

    logger.info(
        "dashboard_accessed",
        user_id=str(current_user.id),
        company_count=len(allowed_metrics),
    )

    return {
        "summary": summary.to_dict(),
        "companies": [m.to_dict() for m in allowed_metrics],
        "alerts": alerts,
    }


@router.get(
    "/comparison",
    summary="Firmen-Vergleich abrufen",
    description="Vergleicht ausgewaehlte Metriken zwischen Firmen."
)
async def get_comparison(
    metric: str = "invoices",
    company_ids: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> dict:
    """
    Vergleicht Metriken zwischen Firmen.

    Args:
        metric: Zu vergleichende Metrik (invoices, documents, entities, dunning, outstanding, overdue, health)
        company_ids: Komma-separierte Liste von Company-IDs (optional)

    Returns:
        Vergleichsdaten für Charts
    """
    # Validiere Metrik
    valid_metrics = ["invoices", "documents", "entities", "dunning", "outstanding", "overdue", "health"]
    if metric not in valid_metrics:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ungültige Metrik. Erlaubt: {', '.join(valid_metrics)}"
        )

    # Parse Company-IDs
    parsed_company_ids: Optional[List[UUID]] = None
    if company_ids:
        try:
            parsed_company_ids = [UUID(cid.strip()) for cid in company_ids.split(",")]
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ungültige Company-ID im Format"
            )

    # Prüfe Zugriff
    user_companies_query = (
        select(UserCompany.company_id)
        .where(UserCompany.user_id == current_user.id)
    )
    user_companies_result = await db.execute(user_companies_query)
    allowed_company_ids = {row[0] for row in user_companies_result.fetchall()}

    # Filtere auf erlaubte Firmen
    if parsed_company_ids:
        filtered_ids = [cid for cid in parsed_company_ids if cid in allowed_company_ids]
        if not filtered_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Keine Berechtigung für die angegebenen Firmen"
            )
        parsed_company_ids = filtered_ids
    else:
        parsed_company_ids = list(allowed_company_ids)

    # Hole Vergleichsdaten
    comparison_data = await company_metrics_service.get_company_comparison(
        db,
        company_ids=parsed_company_ids,
        metric=metric,
    )

    logger.info(
        "comparison_accessed",
        user_id=str(current_user.id),
        metric=metric,
        company_count=len(comparison_data),
    )

    return {
        "metric": metric,
        "metric_label": _get_metric_label(metric),
        "data": comparison_data,
    }


@router.get(
    "/{company_id}/metrics",
    summary="Einzelne Firmen-Metriken abrufen",
    description="Gibt detaillierte Metriken für eine spezifische Firma zurück."
)
async def get_company_metrics(
    company_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> dict:
    """
    Holt detaillierte Metriken für eine Firma.

    Args:
        company_id: ID der Firma

    Returns:
        CompanyMetrics-Daten
    """
    # Prüfe Zugriff
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

    try:
        metrics = await company_metrics_service.get_company_metrics(db, company_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Firma nicht gefunden."
        )

    return metrics.to_dict()


def _generate_dashboard_alerts(metrics_list: List[CompanyMetrics]) -> List[dict]:
    """Generiert Alerts basierend auf Metriken."""
    alerts = []

    for m in metrics_list:
        # Low Health Score
        if m.health_score < 50:
            alerts.append({
                "type": "critical",
                "company_id": str(m.company_id),
                "company_name": m.company_name,
                "message": f"Niedriger Health Score ({m.health_score}/100)",
                "action": "company_review",
            })
        elif m.health_score < 70:
            alerts.append({
                "type": "warning",
                "company_id": str(m.company_id),
                "company_name": m.company_name,
                "message": f"Health Score unter Zielwert ({m.health_score}/100)",
                "action": "company_review",
            })

        # Hohe überfällige Betraege
        if m.invoices.overdue_amount > 10000:
            alerts.append({
                "type": "critical",
                "company_id": str(m.company_id),
                "company_name": m.company_name,
                "message": f"Überfällige Rechnungen: {float(m.invoices.overdue_amount):,.2f} EUR",
                "action": "dunning_review",
            })

        # Viele Level 3/4 Mahnungen
        serious_dunnings = m.dunning.level_3_count + m.dunning.level_4_count
        if serious_dunnings >= 5:
            alerts.append({
                "type": "warning",
                "company_id": str(m.company_id),
                "company_name": m.company_name,
                "message": f"{serious_dunnings} kritische Mahnungen (Stufe 3/4)",
                "action": "dunning_review",
            })

        # High-Risk Entities
        if m.entities.high_risk_entities >= 3:
            alerts.append({
                "type": "warning",
                "company_id": str(m.company_id),
                "company_name": m.company_name,
                "message": f"{m.entities.high_risk_entities} High-Risk Geschäftspartner",
                "action": "entity_review",
            })

    # Sortiere: critical zuerst
    alerts.sort(key=lambda a: (0 if a["type"] == "critical" else 1, a["company_name"]))

    return alerts


def _get_metric_label(metric: str) -> str:
    """Gibt das deutsche Label für eine Metrik zurück."""
    labels = {
        "invoices": "Rechnungsvolumen",
        "documents": "Dokumente",
        "entities": "Geschäftspartner",
        "dunning": "Mahnbetraege",
        "outstanding": "Offene Forderungen",
        "overdue": "Überfällige Forderungen",
        "health": "Health Score",
    }
    return labels.get(metric, metric)


# ==================== User-Company Management ====================

@router.get(
    "/{company_id}/users",
    response_model=List[UserCompanyResponse],
    summary="Benutzer der Firma auflisten",
    description="Gibt alle Benutzer zurück, die Zugriff auf die Firma haben."
)
async def list_company_users(
    company_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> List[UserCompanyResponse]:
    """Liste der Benutzer einer Firma."""

    # Prüfe Zugriff
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
            detail="Nur Owner und Admins können Benutzer verwalten."
        )

    # Lade alle UserCompany-Einträge
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

    # Prüfe Berechtigung
    access_result = await db.execute(
        select(UserCompany)
        .where(UserCompany.user_id == current_user.id)
        .where(UserCompany.company_id == company_id)
    )
    user_company = access_result.scalar_one_or_none()

    if not user_company or user_company.role not in ["owner", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nur Owner und Admins können Benutzer hinzufügen."
        )

    # Prüfe ob Benutzer existiert
    user_result = await db.execute(
        select(User).where(User.id == data.user_id)
    )
    target_user = user_result.scalar_one_or_none()

    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Benutzer nicht gefunden."
        )

    # Prüfe ob bereits zugeordnet
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

    # Prüfe Berechtigung
    access_result = await db.execute(
        select(UserCompany)
        .where(UserCompany.user_id == current_user.id)
        .where(UserCompany.company_id == company_id)
    )
    user_company = access_result.scalar_one_or_none()

    if not user_company or user_company.role not in ["owner", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nur Owner und Admins können Benutzer verwalten."
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
        # Prüfe ob es noch einen anderen Owner gibt
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
    response_class=Response,
    summary="Benutzer aus Firma entfernen",
    description="Entfernt einen Benutzer aus der Firma."
)
async def remove_user_from_company(
    company_id: UUID,
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Response:
    """Entfernt einen Benutzer aus der Firma."""

    # Prüfe Berechtigung
    access_result = await db.execute(
        select(UserCompany)
        .where(UserCompany.user_id == current_user.id)
        .where(UserCompany.company_id == company_id)
    )
    user_company = access_result.scalar_one_or_none()

    if not user_company or user_company.role not in ["owner", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nur Owner und Admins können Benutzer entfernen."
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
                       "Löschen Sie stattdessen die Firma."
            )

    await db.delete(target_uc)
    await db.commit()

    logger.info(
        "user_removed_from_company",
        company_id=str(company_id),
        removed_user_id=str(user_id),
        by_user_id=str(current_user.id),
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)

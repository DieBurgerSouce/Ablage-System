"""
Holding Dashboard API Endpoints.

API fuer Multi-Company Holding-Sicht mit konsolidierten KPIs.

Endpoints:
- GET /holding/overview - Konsolidierte Uebersicht aller Firmen
- GET /holding/companies - Firmen-Liste mit Zusammenfassung
- GET /holding/compare - Firmenvergleich nach Metrik
- GET /holding/intercompany - Intercompany-Transaktionen
- GET /holding/cashflow - Konzern-Cashflow Uebersicht

Created: 2026-01-19
"""

from datetime import datetime, timezone, timedelta
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db
from app.db.models import User, Company, UserCompany
from app.services.holding.holding_kpi_service import HoldingKPIService

router = APIRouter(prefix="/holding", tags=["Holding Dashboard"])


# ==================== Pydantic Models ====================


class CompanySummaryResponse(BaseModel):
    """Zusammenfassung einer Firma."""
    id: str
    name: str
    short_name: Optional[str] = None
    subscription_tier: str
    is_active: bool


class FinancialsResponse(BaseModel):
    """Konsolidierte Finanzkennzahlen."""
    total_receivables: float
    total_payables: float
    net_position: float
    overdue_receivables: float
    overdue_payables: float
    currency: str = "EUR"


class DocumentMetricsResponse(BaseModel):
    """Dokument-Metriken."""
    total: int
    this_month: int
    by_status: dict


class InvoiceMetricsResponse(BaseModel):
    """Rechnungs-Metriken."""
    open_outgoing: int
    open_incoming: int
    avg_payment_days: Optional[int] = None


class BankingMetricsResponse(BaseModel):
    """Banking-Metriken."""
    total_balance: float
    account_count: int
    transactions_last_30d: int
    currency: str = "EUR"


class IntercompanyMetricsResponse(BaseModel):
    """Intercompany-Metriken."""
    total_intercompany_volume: float
    intercompany_receivables: float
    intercompany_payables: float
    transaction_count: int


class ConsolidatedOverviewResponse(BaseModel):
    """Vollstaendige konsolidierte Uebersicht."""
    generated_at: str
    company_count: int
    companies: List[CompanySummaryResponse]
    financials: FinancialsResponse
    documents: DocumentMetricsResponse
    invoices: InvoiceMetricsResponse
    banking: BankingMetricsResponse
    intercompany: IntercompanyMetricsResponse


class CompanyComparisonItem(BaseModel):
    """Vergleichseintrag fuer eine Firma."""
    company_id: str
    company_name: str
    metric: str
    value: float


class CompanyComparisonResponse(BaseModel):
    """Firmenvergleich Antwort."""
    metric: str
    comparison_date: str
    companies: List[CompanyComparisonItem]


class CashFlowItemResponse(BaseModel):
    """Cashflow-Eintrag."""
    company_id: str
    company_name: str
    inflows: float
    outflows: float
    net_flow: float
    period: str


class CashFlowOverviewResponse(BaseModel):
    """Konzern-Cashflow Uebersicht."""
    period_type: str
    total_inflows: float
    total_outflows: float
    total_net_flow: float
    by_company: List[CashFlowItemResponse]


# ==================== Helper Functions ====================


async def get_user_company_ids(
    db: AsyncSession,
    user: User,
    requested_ids: Optional[List[UUID]] = None,
) -> List[UUID]:
    """Hole Company-IDs die der User sehen darf.

    Args:
        db: Database session
        user: Current user
        requested_ids: Optional - Nur diese IDs filtern

    Returns:
        Liste der erlaubten Company-IDs
    """
    # Admins sehen alle aktiven Companies
    if user.is_admin:
        query = select(Company.id).where(
            Company.deleted_at.is_(None),
            Company.is_active == True,
        )
        if requested_ids:
            query = query.where(Company.id.in_(requested_ids))
        result = await db.execute(query)
        return [row[0] for row in result.all()]

    # Normale User sehen nur ihre Companies
    result = await db.execute(
        select(UserCompany.company_id).where(
            UserCompany.user_id == user.id,
        )
    )
    user_company_ids = [row[0] for row in result.all()]

    if requested_ids:
        # Filtere auf angeforderte IDs
        return [cid for cid in user_company_ids if cid in requested_ids]

    return user_company_ids


# ==================== Endpoints ====================


@router.get(
    "/overview",
    response_model=ConsolidatedOverviewResponse,
    summary="Konsolidierte Holding-Uebersicht",
    description="Zeigt konsolidierte KPIs ueber alle Firmen des Users.",
)
async def get_holding_overview(
    company_ids: Optional[List[UUID]] = Query(
        None,
        description="Optional: Nur diese Firmen einbeziehen"
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Hole konsolidierte Uebersicht fuer Holding-Sicht."""
    allowed_ids = await get_user_company_ids(db, current_user, company_ids)

    if not allowed_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Keine Firmen gefunden oder keine Berechtigung"
        )

    service = HoldingKPIService(db)
    overview = await service.get_consolidated_overview(
        user_id=current_user.id,
        company_ids=allowed_ids,
    )

    return ConsolidatedOverviewResponse(
        generated_at=overview["generated_at"],
        company_count=overview["company_count"],
        companies=[CompanySummaryResponse(**c) for c in overview["companies"]],
        financials=FinancialsResponse(**overview["financials"]),
        documents=DocumentMetricsResponse(**overview["documents"]),
        invoices=InvoiceMetricsResponse(**overview["invoices"]),
        banking=BankingMetricsResponse(**overview["banking"]),
        intercompany=IntercompanyMetricsResponse(**overview["intercompany"]),
    )


@router.get(
    "/companies",
    response_model=List[CompanySummaryResponse],
    summary="Firmen-Liste",
    description="Listet alle Firmen des Users mit Zusammenfassung.",
)
async def get_holding_companies(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Hole Liste aller Firmen fuer Holding-Sicht."""
    allowed_ids = await get_user_company_ids(db, current_user)

    if not allowed_ids:
        return []

    result = await db.execute(
        select(Company).where(Company.id.in_(allowed_ids))
    )
    companies = result.scalars().all()

    return [
        CompanySummaryResponse(
            id=str(c.id),
            name=c.name,
            short_name=c.short_name,
            subscription_tier=c.subscription_tier or "free",
            is_active=c.is_active,
        )
        for c in companies
    ]


@router.get(
    "/compare",
    response_model=CompanyComparisonResponse,
    summary="Firmenvergleich",
    description="Vergleicht Firmen anhand einer ausgewaehlten Metrik.",
)
async def compare_companies(
    metric: str = Query(
        "receivables",
        pattern="^(documents|receivables|payables|balance)$",
        description="Metrik fuer Vergleich"
    ),
    company_ids: Optional[List[UUID]] = Query(
        None,
        description="Optional: Nur diese Firmen vergleichen"
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Vergleiche Firmen anhand einer Metrik."""
    allowed_ids = await get_user_company_ids(db, current_user, company_ids)

    if not allowed_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Keine Firmen gefunden oder keine Berechtigung"
        )

    service = HoldingKPIService(db)
    comparison = await service.get_company_comparison(
        company_ids=allowed_ids,
        metric=metric,
    )

    return CompanyComparisonResponse(
        metric=metric,
        comparison_date=datetime.now(timezone.utc).isoformat(),
        companies=[CompanyComparisonItem(**c) for c in comparison],
    )


@router.get(
    "/intercompany",
    response_model=IntercompanyMetricsResponse,
    summary="Intercompany-Transaktionen",
    description="Zeigt Transaktionen zwischen Firmen der Holding.",
)
async def get_intercompany_transactions(
    company_ids: Optional[List[UUID]] = Query(
        None,
        description="Optional: Nur diese Firmen einbeziehen"
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Hole Intercompany-Transaktionen."""
    allowed_ids = await get_user_company_ids(db, current_user, company_ids)

    if not allowed_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Keine Firmen gefunden oder keine Berechtigung"
        )

    service = HoldingKPIService(db)
    overview = await service.get_consolidated_overview(
        user_id=current_user.id,
        company_ids=allowed_ids,
    )

    return IntercompanyMetricsResponse(**overview["intercompany"])


@router.get(
    "/cashflow",
    response_model=CashFlowOverviewResponse,
    summary="Konzern-Cashflow",
    description="Zeigt Cashflow-Uebersicht fuer die Holding.",
)
async def get_holding_cashflow(
    period: str = Query(
        "monthly",
        pattern="^(daily|weekly|monthly)$",
        description="Zeitraum-Aggregation"
    ),
    company_ids: Optional[List[UUID]] = Query(
        None,
        description="Optional: Nur diese Firmen einbeziehen"
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Hole Cashflow-Uebersicht fuer Holding."""
    from app.db.models import BankTransaction, BankAccount

    allowed_ids = await get_user_company_ids(db, current_user, company_ids)

    if not allowed_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Keine Firmen gefunden oder keine Berechtigung"
        )

    # Zeitraum bestimmen
    now = datetime.now(timezone.utc)
    if period == "daily":
        start_date = now - timedelta(days=1)
    elif period == "weekly":
        start_date = now - timedelta(weeks=1)
    else:  # monthly
        start_date = now - timedelta(days=30)

    # Cashflow pro Firma berechnen
    by_company = []
    total_inflows = 0.0
    total_outflows = 0.0

    for company_id in allowed_ids:
        # Hole Company-Name
        company_result = await db.execute(
            select(Company.name).where(Company.id == company_id)
        )
        company_name = company_result.scalar() or "Unbekannt"

        # Hole Transaktionen ueber BankAccount.user_id -> UserCompany.company_id
        # Subquery: User-IDs die zur Company gehoeren
        user_ids_subquery = (
            select(UserCompany.user_id)
            .where(UserCompany.company_id == company_id)
            .scalar_subquery()
        )

        # BankAccounts der User
        bank_accounts_subquery = (
            select(BankAccount.id)
            .where(BankAccount.user_id.in_(user_ids_subquery))
            .scalar_subquery()
        )

        inflows_result = await db.execute(
            select(func.sum(BankTransaction.amount))
            .where(
                BankTransaction.bank_account_id.in_(bank_accounts_subquery),
                BankTransaction.booking_date >= start_date,
                BankTransaction.amount > 0,
            )
        )
        inflows = float(inflows_result.scalar() or 0)

        outflows_result = await db.execute(
            select(func.sum(func.abs(BankTransaction.amount)))
            .where(
                BankTransaction.bank_account_id.in_(bank_accounts_subquery),
                BankTransaction.booking_date >= start_date,
                BankTransaction.amount < 0,
            )
        )
        outflows = float(outflows_result.scalar() or 0)

        by_company.append(CashFlowItemResponse(
            company_id=str(company_id),
            company_name=company_name,
            inflows=inflows,
            outflows=outflows,
            net_flow=inflows - outflows,
            period=period,
        ))

        total_inflows += inflows
        total_outflows += outflows

    return CashFlowOverviewResponse(
        period_type=period,
        total_inflows=total_inflows,
        total_outflows=total_outflows,
        total_net_flow=total_inflows - total_outflows,
        by_company=by_company,
    )

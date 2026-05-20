"""
Holding Dashboard API Endpoints.

API für Multi-Company Holding-Sicht mit konsolidierten KPIs.

Endpoints:
- GET /holding/overview - Konsolidierte Übersicht aller Firmen
- GET /holding/companies - Firmen-Liste mit Zusammenfassung
- GET /holding/compare - Firmenvergleich nach Metrik
- GET /holding/intercompany - Intercompany-Transaktionen (Legacy)
- GET /holding/cashflow - Konzern-Cashflow Übersicht

Intercompany Reconciliation (NEU Phase 5.3):
- GET /holding/ic/summary - IC-Zusammenfassung
- GET /holding/ic/transactions - IC-Transaktionen
- GET /holding/ic/balances - IC-Salden zwischen Firmen
- POST /holding/ic/reconcile - Abstimmung durchführen
- GET /holding/ic/eliminations - Eliminierungsbuchungen generieren
- GET /holding/ic/report - Vollständiger Abstimmungsbericht

Created: 2026-01-19
Updated: 2026-01-21 (Phase 5.3 IC Reconciliation)
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
from app.services.holding.intercompany_reconciliation_service import (
    IntercompanyReconciliationService,
    get_intercompany_reconciliation_service,
    ICTransactionType,
    ReconciliationStatus,
    DifferenceType,
)

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
    """Vollständige konsolidierte Übersicht."""
    generated_at: str
    company_count: int
    companies: List[CompanySummaryResponse]
    financials: FinancialsResponse
    documents: DocumentMetricsResponse
    invoices: InvoiceMetricsResponse
    banking: BankingMetricsResponse
    intercompany: IntercompanyMetricsResponse


class CompanyComparisonItem(BaseModel):
    """Vergleichseintrag für eine Firma."""
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
    """Konzern-Cashflow Übersicht."""
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
    summary="Konsolidierte Holding-Übersicht",
    description="Zeigt konsolidierte KPIs über alle Firmen des Users.",
)
async def get_holding_overview(
    company_ids: Optional[List[UUID]] = Query(
        None,
        description="Optional: Nur diese Firmen einbeziehen"
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Hole konsolidierte Übersicht für Holding-Sicht."""
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
    """Hole Liste aller Firmen für Holding-Sicht."""
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
        description="Metrik für Vergleich"
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
    description="Zeigt Cashflow-Übersicht für die Holding.",
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
    """Hole Cashflow-Übersicht für Holding."""
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

        # Hole Transaktionen über BankAccount.user_id -> UserCompany.company_id
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


# ==================== IC Reconciliation Pydantic Models ====================


class ICTransactionResponse(BaseModel):
    """Intercompany-Transaktion."""

    id: str
    from_company_id: str
    from_company_name: str
    to_company_id: str
    to_company_name: str
    transaction_type: str
    amount: float
    currency: str = "EUR"
    reference: str
    document_id: Optional[str] = None
    invoice_id: Optional[str] = None
    transaction_date: str
    due_date: Optional[str] = None
    description: Optional[str] = None
    status: str
    matched_transaction_id: Optional[str] = None


class ICBalanceResponse(BaseModel):
    """Intercompany-Saldo zwischen zwei Firmen."""

    company_a_id: str
    company_a_name: str
    company_b_id: str
    company_b_name: str
    balance_a_to_b: float
    balance_b_to_a: float
    net_balance: float
    open_transactions_count: int
    last_reconciled_at: Optional[str] = None
    currency: str = "EUR"


class ReconciliationDifferenceResponse(BaseModel):
    """Identifizierte Differenz im Abgleich."""

    id: str
    difference_type: str
    from_company_id: str
    to_company_id: str
    transaction_id: Optional[str] = None
    counterpart_id: Optional[str] = None
    expected_amount: float
    actual_amount: float
    difference_amount: float
    expected_date: Optional[str] = None
    actual_date: Optional[str] = None
    description: str
    recommendation: str
    created_at: str


class EliminationEntryResponse(BaseModel):
    """Eliminierungsbuchung für Konsolidierung."""

    id: str
    account_debit: str
    account_credit: str
    amount: float
    description: str
    from_company_id: str
    to_company_id: str
    transaction_ids: List[str]
    elimination_type: str
    period: str


class ICSummaryResponse(BaseModel):
    """IC-Zusammenfassung für Dashboard."""

    has_ic_relationships: bool
    company_pairs: int = 0
    total_ic_receivables: float = 0.0
    total_ic_payables: float = 0.0
    net_ic_position: float = 0.0
    open_transactions: int = 0
    currency: str = "EUR"
    generated_at: str
    message: Optional[str] = None


class ICTransactionsListResponse(BaseModel):
    """Liste der IC-Transaktionen."""

    total: int
    period_start: str
    period_end: str
    transactions: List[ICTransactionResponse]


class ICBalancesResponse(BaseModel):
    """Liste der IC-Salden."""

    as_of_date: str
    balances: List[ICBalanceResponse]


class ReconciliationResultResponse(BaseModel):
    """Ergebnis der Abstimmung."""

    total_transactions: int
    matched: int
    unmatched: int
    match_rate: float
    differences: List[ReconciliationDifferenceResponse]
    transactions: List[ICTransactionResponse]


class EliminationsResponse(BaseModel):
    """Generierte Eliminierungen."""

    period: str
    eliminations: List[EliminationEntryResponse]
    total_eliminated: float


class ReconciliationReportResponse(BaseModel):
    """Vollständiger Abstimmungsbericht."""

    generated_at: str
    period_start: str
    period_end: str
    companies_involved: List[dict]
    total_ic_volume: float
    matched_volume: float
    unmatched_volume: float
    balances: List[ICBalanceResponse]
    differences: List[ReconciliationDifferenceResponse]
    eliminations: List[EliminationEntryResponse]
    statistics: dict


# ==================== IC Reconciliation Endpoints ====================


@router.get(
    "/ic/summary",
    response_model=ICSummaryResponse,
    summary="IC-Zusammenfassung",
    description="Kompakte Zusammenfassung der Intercompany-Beziehungen.",
)
async def get_ic_summary(
    company_ids: Optional[List[UUID]] = Query(
        None, description="Optional: Nur diese Firmen einbeziehen"
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Hole IC-Zusammenfassung für Dashboard."""
    allowed_ids = await get_user_company_ids(db, current_user, company_ids)

    if not allowed_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Keine Firmen gefunden oder keine Berechtigung",
        )

    service = get_intercompany_reconciliation_service(db)
    summary = await service.get_ic_summary(allowed_ids)

    return ICSummaryResponse(**summary)


@router.get(
    "/ic/transactions",
    response_model=ICTransactionsListResponse,
    summary="IC-Transaktionen",
    description="Listet alle Intercompany-Transaktionen im Zeitraum.",
)
async def get_ic_transactions(
    company_ids: Optional[List[UUID]] = Query(
        None, description="Optional: Nur diese Firmen einbeziehen"
    ),
    start_date: Optional[datetime] = Query(
        None, description="Startdatum (ISO 8601)"
    ),
    end_date: Optional[datetime] = Query(
        None, description="Enddatum (ISO 8601)"
    ),
    transaction_type: Optional[ICTransactionType] = Query(
        None, description="Nach Typ filtern"
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Hole IC-Transaktionen."""
    allowed_ids = await get_user_company_ids(db, current_user, company_ids)

    if not allowed_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Keine Firmen gefunden oder keine Berechtigung",
        )

    if end_date is None:
        end_date = datetime.now(timezone.utc)
    if start_date is None:
        start_date = end_date - timedelta(days=90)

    service = get_intercompany_reconciliation_service(db)
    transactions = await service.identify_ic_transactions(
        allowed_ids, start_date, end_date
    )

    # Optional nach Typ filtern
    if transaction_type:
        transactions = [t for t in transactions if t.transaction_type == transaction_type]

    return ICTransactionsListResponse(
        total=len(transactions),
        period_start=start_date.isoformat(),
        period_end=end_date.isoformat(),
        transactions=[
            ICTransactionResponse(**service.to_dict(t)) for t in transactions
        ],
    )


@router.get(
    "/ic/balances",
    response_model=ICBalancesResponse,
    summary="IC-Salden",
    description="Zeigt IC-Salden zwischen allen Firmenpaaren.",
)
async def get_ic_balances(
    company_ids: Optional[List[UUID]] = Query(
        None, description="Optional: Nur diese Firmen einbeziehen"
    ),
    as_of_date: Optional[datetime] = Query(
        None, description="Stichtag (default: heute)"
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Hole IC-Salden zwischen Firmen."""
    allowed_ids = await get_user_company_ids(db, current_user, company_ids)

    if not allowed_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Keine Firmen gefunden oder keine Berechtigung",
        )

    if as_of_date is None:
        as_of_date = datetime.now(timezone.utc)

    service = get_intercompany_reconciliation_service(db)
    balances = await service.calculate_ic_balances(allowed_ids, as_of_date)

    return ICBalancesResponse(
        as_of_date=as_of_date.isoformat(),
        balances=[ICBalanceResponse(**service.to_dict(b)) for b in balances],
    )


@router.post(
    "/ic/reconcile",
    response_model=ReconciliationResultResponse,
    summary="IC-Abstimmung durchführen",
    description="Führt den Abgleich der IC-Transaktionen durch.",
)
async def perform_ic_reconciliation(
    company_ids: Optional[List[UUID]] = Query(
        None, description="Optional: Nur diese Firmen einbeziehen"
    ),
    start_date: Optional[datetime] = Query(
        None, description="Startdatum (ISO 8601)"
    ),
    end_date: Optional[datetime] = Query(
        None, description="Enddatum (ISO 8601)"
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Führe IC-Abstimmung durch."""
    allowed_ids = await get_user_company_ids(db, current_user, company_ids)

    if not allowed_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Keine Firmen gefunden oder keine Berechtigung",
        )

    service = get_intercompany_reconciliation_service(db)
    transactions, differences = await service.reconcile_transactions(
        allowed_ids, start_date, end_date
    )

    matched = [t for t in transactions if t.status == ReconciliationStatus.MATCHED]
    match_rate = len(matched) / len(transactions) if transactions else 0

    return ReconciliationResultResponse(
        total_transactions=len(transactions),
        matched=len(matched),
        unmatched=len(transactions) - len(matched),
        match_rate=match_rate,
        differences=[
            ReconciliationDifferenceResponse(**service.to_dict(d)) for d in differences
        ],
        transactions=[
            ICTransactionResponse(**service.to_dict(t)) for t in transactions
        ],
    )


@router.get(
    "/ic/eliminations",
    response_model=EliminationsResponse,
    summary="Eliminierungsbuchungen",
    description="Generiert Eliminierungsbuchungen für den Konzernabschluss.",
)
async def get_ic_eliminations(
    period: str = Query(
        ...,
        pattern=r"^\d{4}-(0[1-9]|1[0-2])$",
        description="Periode im Format YYYY-MM",
    ),
    company_ids: Optional[List[UUID]] = Query(
        None, description="Optional: Nur diese Firmen einbeziehen"
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generiere Eliminierungsbuchungen."""
    allowed_ids = await get_user_company_ids(db, current_user, company_ids)

    if not allowed_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Keine Firmen gefunden oder keine Berechtigung",
        )

    service = get_intercompany_reconciliation_service(db)
    eliminations = await service.generate_eliminations(allowed_ids, period)

    total_eliminated = sum(e.amount for e in eliminations)

    return EliminationsResponse(
        period=period,
        eliminations=[
            EliminationEntryResponse(**service.to_dict(e)) for e in eliminations
        ],
        total_eliminated=float(total_eliminated),
    )


@router.get(
    "/ic/report",
    response_model=ReconciliationReportResponse,
    summary="IC-Abstimmungsbericht",
    description="Generiert vollständigen Abstimmungsbericht mit allen Details.",
)
async def get_ic_report(
    company_ids: Optional[List[UUID]] = Query(
        None, description="Optional: Nur diese Firmen einbeziehen"
    ),
    start_date: Optional[datetime] = Query(
        None, description="Startdatum (ISO 8601)"
    ),
    end_date: Optional[datetime] = Query(
        None, description="Enddatum (ISO 8601)"
    ),
    period: Optional[str] = Query(
        None,
        pattern=r"^\d{4}-(0[1-9]|1[0-2])$",
        description="Periode für Eliminierungen (YYYY-MM)",
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generiere vollständigen IC-Abstimmungsbericht."""
    allowed_ids = await get_user_company_ids(db, current_user, company_ids)

    if not allowed_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Keine Firmen gefunden oder keine Berechtigung",
        )

    service = get_intercompany_reconciliation_service(db)
    report = await service.generate_reconciliation_report(
        allowed_ids, start_date, end_date, period
    )

    report_dict = service.to_dict(report)

    return ReconciliationReportResponse(
        generated_at=report_dict["generated_at"],
        period_start=report_dict["period_start"],
        period_end=report_dict["period_end"],
        companies_involved=report_dict["companies_involved"],
        total_ic_volume=report_dict["total_ic_volume"],
        matched_volume=report_dict["matched_volume"],
        unmatched_volume=report_dict["unmatched_volume"],
        balances=[ICBalanceResponse(**b) for b in report_dict["balances"]],
        differences=[
            ReconciliationDifferenceResponse(**d) for d in report_dict["differences"]
        ],
        eliminations=[
            EliminationEntryResponse(**e) for e in report_dict["eliminations"]
        ],
        statistics=report_dict["statistics"],
    )

# -*- coding: utf-8 -*-
"""
Accounting API Endpoints.

REST API für integrierte Buchhaltung:
- Offene Posten (Debitoren/Kreditoren)
- USt-Voranmeldung
- Einnahmen-Überschuss-Rechnung (EUER)

GoBD-konform und Enterprise-Ready.
"""

from typing import Optional, List, Dict, Union
from uuid import UUID
from datetime import date, datetime
from decimal import Decimal
from enum import Enum

import structlog
from fastapi import APIRouter, Depends, HTTPException, status, Query, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.api.dependencies import get_db, get_current_active_user, validate_company_access
from app.core.safe_errors import safe_error_detail, safe_error_log
from app.services.accounting.vat_service import VATSummary, VATReport
from app.services.accounting.eur_service import EURCategorySummary, EURReport
from app.services.accounting import (
    get_open_items_service,
    get_vat_service,
    get_eur_service,
    get_auto_booking_service,
    OpenItemType,
    PaymentPriority,
    VATRate,
    IncomeCategory,
    ExpenseCategory,
    BookingConfidence,
    BookingType,
    TaxCode,
)
from app.services.accounting.fx_rate_service import (
    FXRateService,
    get_fx_rate_service,
    ConversionResult,
    RevaluationSummary,
)
from app.services.accounting.fx_gain_loss_service import (
    FXGainLossService,
    get_fx_gain_loss_service,
    FXGainLossResult,
)
from app.core.security_auth import build_content_disposition
from sqlalchemy import and_

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/accounting", tags=["Buchhaltung"])


# =============================================================================
# SCHEMAS
# =============================================================================


class OpenItemSchema(BaseModel):
    """Schema für einen offenen Posten."""

    id: UUID
    document_id: UUID
    entity_id: Optional[UUID] = None
    entity_name: str
    item_type: str
    invoice_number: Optional[str] = None
    invoice_date: Optional[date] = None
    due_date: Optional[date] = None
    amount: Decimal
    paid_amount: Decimal
    outstanding_amount: Decimal
    currency: str = "EUR"
    days_overdue: int = 0
    dunning_level: int = 0
    payment_priority: str
    skonto_deadline: Optional[date] = None
    skonto_amount: Optional[Decimal] = None
    skonto_percentage: Optional[float] = None

    model_config = ConfigDict(from_attributes=True)


class EntityBalanceSchema(BaseModel):
    """Schema für Entity-Saldo."""

    entity_id: UUID
    entity_name: str
    entity_type: str
    total_invoices: Decimal
    total_paid: Decimal
    outstanding: Decimal
    overdue_amount: Decimal
    invoice_count: int
    open_items_count: int
    oldest_open_days: int
    average_payment_days: float
    credit_limit: Optional[Decimal] = None
    credit_usage_percent: float = 0.0


class OpenItemsReportSchema(BaseModel):
    """Schema für Offene-Posten-Bericht."""

    report_date: date
    generated_at: datetime
    # Forderungen
    total_receivables: Decimal
    total_receivables_overdue: Decimal
    receivables_count: int
    receivables_overdue_count: int
    # Verbindlichkeiten
    total_payables: Decimal
    total_payables_overdue: Decimal
    payables_count: int
    payables_overdue_count: int
    # Skonto-Potenzial
    skonto_potential: Decimal
    skonto_items_count: int
    # Netto-Position
    net_position: Decimal


class PaymentSuggestionSchema(BaseModel):
    """Schema für Zahlungsvorschlag."""

    entity_id: UUID
    entity_name: str
    invoice_number: str
    amount: Decimal
    due_date: date
    priority: str
    reason: str
    skonto_savings: Optional[Decimal] = None


class VATSummarySchema(BaseModel):
    """Schema für USt-Kennziffer-Zusammenfassung."""

    kennziffer: str
    label: str
    net_amount: Decimal
    vat_amount: Decimal
    count: int


class VATReportSchema(BaseModel):
    """Schema für USt-Voranmeldung."""

    company_id: UUID
    period_type: str  # monthly, quarterly, annual
    period_start: date
    period_end: date
    period_label: str
    generated_at: datetime
    status: str = "draft"

    # Umsätze (Output VAT)
    output_vat_19: VATSummarySchema
    output_vat_7: VATSummarySchema
    inner_eu_deliveries: VATSummarySchema
    export_deliveries: VATSummarySchema

    # Vorsteuer (Input VAT)
    input_vat: VATSummarySchema
    input_vat_inner_eu: VATSummarySchema
    input_vat_reverse_charge: VATSummarySchema

    # Innergemeinschaftliche Erwerbe
    inner_eu_acquisition_19: VATSummarySchema
    inner_eu_acquisition_7: VATSummarySchema

    # Berechnung
    total_output_vat: Decimal
    total_input_vat: Decimal
    vat_payable: Decimal  # Positive = Zahllast, Negative = Erstattung


class EURCategorySummarySchema(BaseModel):
    """Schema für EUER-Kategorie-Zusammenfassung."""

    category: str
    label: str
    amount: Decimal
    count: int


class EURReportSchema(BaseModel):
    """Schema für Einnahmen-Überschuss-Rechnung."""

    company_id: UUID
    fiscal_year: int
    period_start: date
    period_end: date
    generated_at: datetime
    status: str = "draft"

    # Einnahmen
    income_categories: List[EURCategorySummarySchema]
    total_income: Decimal

    # Ausgaben
    expense_categories: List[EURCategorySummarySchema]
    total_expenses: Decimal

    # Gewinn/Verlust
    profit_loss: Decimal
    is_profit: bool

    # Vorsteuer
    deductible_vat: Decimal


class YTDSummarySchema(BaseModel):
    """Schema für Year-to-Date Zusammenfassung."""

    year: int
    months_completed: int
    total_income: Decimal
    total_expenses: Decimal
    cumulative_profit: Decimal
    avg_monthly_income: Decimal
    avg_monthly_expenses: Decimal
    monthly_data: List[Dict[str, Union[str, int, float, Decimal, None]]]


class OptimizeForEnum(str, Enum):
    """Optimierungsziel für Zahlungsvorschläge."""

    SKONTO = "skonto"
    CASHFLOW = "cashflow"
    PRIORITY = "priority"


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def _map_vat_summary(summary: VATSummary) -> VATSummarySchema:
    """Mappt VATSummary zu VATSummarySchema."""
    return VATSummarySchema(
        kennziffer=summary.kennziffer,
        label=summary.label,
        net_amount=summary.net_amount,
        vat_amount=summary.vat_amount,
        count=summary.count,
    )


def _map_vat_report(report: VATReport) -> VATReportSchema:
    """Mappt VATReport zu VATReportSchema."""
    return VATReportSchema(
        company_id=report.company_id,
        period_type=report.period_type.value,
        period_start=report.period_start,
        period_end=report.period_end,
        period_label=report.period_label,
        generated_at=report.generated_at,
        status=report.status,
        output_vat_19=_map_vat_summary(report.output_vat_19),
        output_vat_7=_map_vat_summary(report.output_vat_7),
        inner_eu_deliveries=_map_vat_summary(report.inner_eu_deliveries),
        export_deliveries=_map_vat_summary(report.export_deliveries),
        input_vat=_map_vat_summary(report.input_vat),
        input_vat_inner_eu=_map_vat_summary(report.input_vat_inner_eu),
        input_vat_reverse_charge=_map_vat_summary(report.input_vat_reverse_charge),
        inner_eu_acquisition_19=_map_vat_summary(report.inner_eu_acquisition_19),
        inner_eu_acquisition_7=_map_vat_summary(report.inner_eu_acquisition_7),
        total_output_vat=report.total_output_vat,
        total_input_vat=report.total_input_vat,
        vat_payable=report.vat_payable,
    )


def _map_eur_category(category: EURCategorySummary) -> EURCategorySummarySchema:
    """Mappt EURCategorySummary zu EURCategorySummarySchema."""
    return EURCategorySummarySchema(
        category=category.category,
        label=category.label,
        amount=category.amount,
        count=category.count,
    )


def _map_eur_report(report: EURReport) -> EURReportSchema:
    """Mappt EURReport zu EURReportSchema."""
    return EURReportSchema(
        company_id=report.company_id,
        fiscal_year=report.fiscal_year,
        period_start=report.period_start,
        period_end=report.period_end,
        generated_at=report.generated_at,
        status=report.status,
        income_categories=[_map_eur_category(c) for c in report.income_categories],
        total_income=report.total_income,
        expense_categories=[_map_eur_category(c) for c in report.expense_categories],
        total_expenses=report.total_expenses,
        profit_loss=report.profit_loss,
        is_profit=report.is_profit,
        deductible_vat=report.deductible_vat,
    )



# =============================================================================
# OFFENE POSTEN (DEBITOREN/KREDITOREN)
# =============================================================================


@router.get(
    "/open-items/report",
    response_model=OpenItemsReportSchema,
    summary="Offene-Posten-Bericht",
    description="Generiert einen Bericht über alle offenen Posten (Debitoren/Kreditoren)",
)
async def get_open_items_report(
    company_id: UUID = Query(..., description="Firmen-ID"),
    as_of_date: Optional[date] = Query(None, description="Stichtag (Standard: heute)"),
    include_details: bool = Query(False, description="Einzelposten einbeziehen"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> OpenItemsReportSchema:
    """
    Erstellt einen Offene-Posten-Bericht zum Stichtag.

    **Enthält:**
    - Summe Forderungen (Debitoren)
    - Summe Verbindlichkeiten (Kreditoren)
    - Netto-Position
    - Altersstruktur (0-30, 31-60, 61-90, 90+ Tage)
    """
    validate_company_access(company_id, current_user)
    logger.info(
        "open_items_report_requested",
        company_id=str(company_id),
        user_id=str(current_user.id),
        as_of_date=str(as_of_date) if as_of_date else "today",
    )

    service = get_open_items_service(db)
    report = await service.get_open_items_report(
        company_id=company_id,
        as_of_date=as_of_date,
        include_details=include_details,
    )

    return OpenItemsReportSchema(
        report_date=report.report_date,
        generated_at=report.generated_at,
        total_receivables=report.total_receivables,
        total_receivables_overdue=report.total_receivables_overdue,
        receivables_count=report.receivables_count,
        receivables_overdue_count=report.receivables_overdue_count,
        total_payables=report.total_payables,
        total_payables_overdue=report.total_payables_overdue,
        payables_count=report.payables_count,
        payables_overdue_count=report.payables_overdue_count,
        skonto_potential=report.skonto_potential,
        skonto_items_count=report.skonto_items_count,
        net_position=report.net_position,
    )


@router.get(
    "/open-items/receivables",
    response_model=List[OpenItemSchema],
    summary="Offene Forderungen",
    description="Listet alle offenen Forderungen (Debitoren)",
)
async def get_open_receivables(
    company_id: UUID = Query(..., description="Firmen-ID"),
    entity_id: Optional[UUID] = Query(None, description="Nur für bestimmten Debitor"),
    overdue_only: bool = Query(False, description="Nur überfällige"),
    priority: Optional[PaymentPriority] = Query(None, description="Nach Priorität filtern"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> List[OpenItemSchema]:
    """
    Listet alle offenen Forderungen auf.

    **Prioritäten:**
    - **normal**: Fällig in >14 Tagen
    - **high**: Skonto-Frist naht
    - **urgent**: Überfällig
    - **critical**: Stark überfällig (90+ Tage)
    """
    validate_company_access(company_id, current_user)
    service = get_open_items_service(db)
    items = await service.get_open_receivables(
        company_id=company_id,
        entity_id=entity_id,
        overdue_only=overdue_only,
        priority=priority,
    )

    return [
        OpenItemSchema(
            id=item.id,
            document_id=item.document_id,
            entity_id=item.entity_id,
            entity_name=item.entity_name,
            item_type=item.item_type.value,
            invoice_number=item.invoice_number,
            invoice_date=item.invoice_date,
            due_date=item.due_date,
            amount=item.amount,
            paid_amount=item.paid_amount,
            outstanding_amount=item.outstanding_amount,
            currency=item.currency,
            days_overdue=item.days_overdue,
            dunning_level=item.dunning_level,
            payment_priority=item.payment_priority.value,
            skonto_deadline=item.skonto_deadline,
            skonto_amount=item.skonto_amount,
            skonto_percentage=item.skonto_percentage,
        )
        for item in items
    ]


@router.get(
    "/open-items/payables",
    response_model=List[OpenItemSchema],
    summary="Offene Verbindlichkeiten",
    description="Listet alle offenen Verbindlichkeiten (Kreditoren)",
)
async def get_open_payables(
    company_id: UUID = Query(..., description="Firmen-ID"),
    entity_id: Optional[UUID] = Query(None, description="Nur für bestimmten Kreditor"),
    due_within_days: Optional[int] = Query(
        None, description="Nur fällig innerhalb X Tagen"
    ),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> List[OpenItemSchema]:
    """
    Listet alle offenen Verbindlichkeiten auf.

    Nützlich für:
    - Zahlungsplanung
    - Skonto-Optimierung
    - Liquiditätsmanagement
    """
    validate_company_access(company_id, current_user)
    service = get_open_items_service(db)
    items = await service.get_open_payables(
        company_id=company_id,
        entity_id=entity_id,
        due_within_days=due_within_days,
    )

    return [
        OpenItemSchema(
            id=item.id,
            document_id=item.document_id,
            entity_id=item.entity_id,
            entity_name=item.entity_name,
            item_type=item.item_type.value,
            invoice_number=item.invoice_number,
            invoice_date=item.invoice_date,
            due_date=item.due_date,
            amount=item.amount,
            paid_amount=item.paid_amount,
            outstanding_amount=item.outstanding_amount,
            currency=item.currency,
            days_overdue=item.days_overdue,
            dunning_level=item.dunning_level,
            payment_priority=item.payment_priority.value,
            skonto_deadline=item.skonto_deadline,
            skonto_amount=item.skonto_amount,
            skonto_percentage=item.skonto_percentage,
        )
        for item in items
    ]


@router.get(
    "/open-items/debtor-balances",
    response_model=List[EntityBalanceSchema],
    summary="Debitorensalden",
    description="Aggregierte Salden pro Debitor",
)
async def get_debtor_balances(
    company_id: UUID = Query(..., description="Firmen-ID"),
    min_outstanding: Optional[Decimal] = Query(
        None, description="Mindest-Aussstand in EUR"
    ),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> List[EntityBalanceSchema]:
    """
    Zeigt aggregierte Salden pro Debitor.

    Sortiert nach Ausstand (höchster zuerst).
    """
    validate_company_access(company_id, current_user)
    service = get_open_items_service(db)
    balances = await service.get_debtor_balances(
        company_id=company_id,
        min_outstanding=min_outstanding,
    )

    return [
        EntityBalanceSchema(
            entity_id=b.entity_id,
            entity_name=b.entity_name,
            entity_type=b.entity_type,
            total_invoices=b.total_invoices,
            total_paid=b.total_paid,
            outstanding=b.outstanding,
            overdue_amount=b.overdue_amount,
            invoice_count=b.invoice_count,
            open_items_count=b.open_items_count,
            oldest_open_days=b.oldest_open_days,
            average_payment_days=b.average_payment_days,
            credit_limit=b.credit_limit,
            credit_usage_percent=b.credit_usage_percent,
        )
        for b in balances
    ]


@router.get(
    "/open-items/creditor-balances",
    response_model=List[EntityBalanceSchema],
    summary="Kreditorensalden",
    description="Aggregierte Salden pro Kreditor",
)
async def get_creditor_balances(
    company_id: UUID = Query(..., description="Firmen-ID"),
    min_outstanding: Optional[Decimal] = Query(
        None, description="Mindest-Ausstand in EUR"
    ),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> List[EntityBalanceSchema]:
    """
    Zeigt aggregierte Salden pro Kreditor.

    Sortiert nach Ausstand (höchster zuerst).
    """
    validate_company_access(company_id, current_user)
    service = get_open_items_service(db)
    balances = await service.get_creditor_balances(
        company_id=company_id,
        min_outstanding=min_outstanding,
    )

    return [
        EntityBalanceSchema(
            entity_id=b.entity_id,
            entity_name=b.entity_name,
            entity_type=b.entity_type,
            total_invoices=b.total_invoices,
            total_paid=b.total_paid,
            outstanding=b.outstanding,
            overdue_amount=b.overdue_amount,
            invoice_count=b.invoice_count,
            open_items_count=b.open_items_count,
            oldest_open_days=b.oldest_open_days,
            average_payment_days=b.average_payment_days,
            credit_limit=b.credit_limit,
            credit_usage_percent=b.credit_usage_percent,
        )
        for b in balances
    ]


@router.get(
    "/open-items/payment-suggestions",
    response_model=List[PaymentSuggestionSchema],
    summary="Zahlungsvorschläge",
    description="Generiert optimierte Zahlungsvorschläge",
)
async def get_payment_suggestions(
    company_id: UUID = Query(..., description="Firmen-ID"),
    available_funds: Decimal = Query(..., description="Verfügbare Mittel in EUR"),
    optimize_for: OptimizeForEnum = Query(
        OptimizeForEnum.SKONTO, description="Optimierungsziel"
    ),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> List[PaymentSuggestionSchema]:
    """
    Generiert optimierte Zahlungsvorschläge.

    **Optimierungsziele:**
    - **skonto**: Maximiere Skonto-Ersparnis
    - **cashflow**: Minimiere Zahlungsausgang
    - **priority**: Zahle nach Dringlichkeit
    """
    validate_company_access(company_id, current_user)
    service = get_open_items_service(db)
    suggestions = await service.get_payment_suggestions(
        company_id=company_id,
        available_funds=available_funds,
        optimize_for=optimize_for.value,
    )

    return [
        PaymentSuggestionSchema(
            entity_id=s["entity_id"],
            entity_name=s["entity_name"],
            invoice_number=s["invoice_number"],
            amount=s["amount"],
            due_date=s["due_date"],
            priority=s["priority"],
            reason=s["reason"],
            skonto_savings=s.get("skonto_savings"),
        )
        for s in suggestions
    ]


# =============================================================================
# UST-VORANMELDUNG
# =============================================================================


@router.get(
    "/vat/monthly",
    response_model=VATReportSchema,
    summary="Monatliche USt-Voranmeldung",
    description="Generiert USt-VA für einen Monat",
)
async def get_monthly_vat_report(
    company_id: UUID = Query(..., description="Firmen-ID"),
    year: int = Query(..., description="Jahr"),
    month: int = Query(..., ge=1, le=12, description="Monat (1-12)"),
    include_details: bool = Query(False, description="Einzelposten einbeziehen"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> VATReportSchema:
    """
    Erstellt eine monatliche USt-Voranmeldung.

    **Enthält:**
    - Steuerpflichtige Umsätze (19%, 7%)
    - Vorsteuer aus Eingangsrechnungen
    - Zahllast / Erstattungsanspruch
    - Kennziffern nach ELSTER-Format
    """
    validate_company_access(company_id, current_user)
    logger.info(
        "vat_monthly_report_requested",
        company_id=str(company_id),
        user_id=str(current_user.id),
        year=year,
        month=month,
    )

    service = get_vat_service(db)
    report = await service.generate_monthly_report(
        company_id=company_id,
        year=year,
        month=month,
        include_details=include_details,
    )

    return _map_vat_report(report)


@router.get(
    "/vat/quarterly",
    response_model=VATReportSchema,
    summary="Quartals-USt-Voranmeldung",
    description="Generiert USt-VA für ein Quartal",
)
async def get_quarterly_vat_report(
    company_id: UUID = Query(..., description="Firmen-ID"),
    year: int = Query(..., description="Jahr"),
    quarter: int = Query(..., ge=1, le=4, description="Quartal (1-4)"),
    include_details: bool = Query(False, description="Einzelposten einbeziehen"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> VATReportSchema:
    """
    Erstellt eine quartalsweise USt-Voranmeldung.

    Für Unternehmen mit quartalsweiser Abgabepflicht.
    """
    validate_company_access(company_id, current_user)
    logger.info(
        "vat_quarterly_report_requested",
        company_id=str(company_id),
        user_id=str(current_user.id),
        year=year,
        quarter=quarter,
    )

    service = get_vat_service(db)
    report = await service.generate_quarterly_report(
        company_id=company_id,
        year=year,
        quarter=quarter,
        include_details=include_details,
    )

    return _map_vat_report(report)


@router.get(
    "/vat/elster-xml",
    summary="ELSTER-XML Export",
    description="Exportiert USt-VA als ELSTER-kompatibles XML",
)
async def export_vat_elster_xml(
    company_id: UUID = Query(..., description="Firmen-ID"),
    year: int = Query(..., description="Jahr"),
    month: int = Query(..., ge=1, le=12, description="Monat (1-12)"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Exportiert die USt-Voranmeldung als ELSTER-XML.

    Die XML-Datei kann direkt in ElsterOnline importiert werden.
    """
    validate_company_access(company_id, current_user)
    logger.info(
        "vat_elster_export_requested",
        company_id=str(company_id),
        user_id=str(current_user.id),
        year=year,
        month=month,
    )

    service = get_vat_service(db)
    report = await service.generate_monthly_report(
        company_id=company_id,
        year=year,
        month=month,
        include_details=False,
    )

    # Steuernummer der Firma laden für ELSTER XML
    from app.db.models import Company
    company_stmt = select(Company).where(Company.id == company_id)
    company_result = await db.execute(company_stmt)
    company = company_result.scalar_one_or_none()
    steuernummer = company.tax_number if company else None

    xml_content = report.to_elster_xml(steuernummer=steuernummer)
    filename = f"UStVA_{year}_{month:02d}.xml"

    return Response(
        content=xml_content,
        media_type="application/xml",
        headers={
            "Content-Disposition": build_content_disposition(filename, "attachment"),
        },
    )


# =============================================================================
# EINNAHMEN-UEBERSCHUSS-RECHNUNG (EUER)
# =============================================================================


@router.get(
    "/eur/annual",
    response_model=EURReportSchema,
    summary="Jahres-EUER",
    description="Generiert Einnahmen-Überschuss-Rechnung für ein Geschäftsjahr",
)
async def get_annual_eur_report(
    company_id: UUID = Query(..., description="Firmen-ID"),
    fiscal_year: int = Query(..., description="Geschäftsjahr"),
    include_details: bool = Query(False, description="Einzelposten einbeziehen"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> EURReportSchema:
    """
    Erstellt eine Einnahmen-Überschuss-Rechnung (EUER) für ein Geschäftsjahr.

    **Einnahmen-Kategorien:**
    - Warenverkäufe
    - Dienstleistungen
    - Zinserträge
    - Sonstige Einnahmen

    **Ausgaben-Kategorien:**
    - Wareneinkauf
    - Personal
    - Miete
    - Versicherungen
    - Fahrzeuge
    - Und weitere...
    """
    validate_company_access(company_id, current_user)
    logger.info(
        "eur_annual_report_requested",
        company_id=str(company_id),
        user_id=str(current_user.id),
        fiscal_year=fiscal_year,
    )

    service = get_eur_service(db)
    report = await service.generate_eur_report(
        company_id=company_id,
        fiscal_year=fiscal_year,
        include_details=include_details,
    )

    return _map_eur_report(report)


@router.get(
    "/eur/monthly",
    response_model=EURReportSchema,
    summary="Monats-EUER",
    description="Generiert EUER für einen einzelnen Monat",
)
async def get_monthly_eur_report(
    company_id: UUID = Query(..., description="Firmen-ID"),
    year: int = Query(..., description="Jahr"),
    month: int = Query(..., ge=1, le=12, description="Monat (1-12)"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> EURReportSchema:
    """
    Erstellt eine monatliche Einnahmen-Überschuss-Rechnung.

    Nützlich für:
    - Monatliches Controlling
    - Liquiditätsplanung
    - Trend-Analyse
    """
    validate_company_access(company_id, current_user)
    logger.info(
        "eur_monthly_report_requested",
        company_id=str(company_id),
        user_id=str(current_user.id),
        year=year,
        month=month,
    )

    service = get_eur_service(db)
    report = await service.generate_monthly_eur(
        company_id=company_id,
        year=year,
        month=month,
    )

    return _map_eur_report(report)


@router.get(
    "/eur/ytd",
    response_model=YTDSummarySchema,
    summary="Year-to-Date Zusammenfassung",
    description="Kumulierte EUER-Daten für das laufende Jahr",
)
async def get_ytd_summary(
    company_id: UUID = Query(..., description="Firmen-ID"),
    year: int = Query(..., description="Jahr"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> YTDSummarySchema:
    """
    Zeigt Year-to-Date Zusammenfassung mit monatlicher Aufschlüsselung.

    **Enthält:**
    - Kumulierte Einnahmen/Ausgaben
    - Durchschnittliche monatliche Werte
    - Monat-für-Monat Entwicklung
    """
    validate_company_access(company_id, current_user)
    logger.info(
        "eur_ytd_requested",
        company_id=str(company_id),
        user_id=str(current_user.id),
        year=year,
    )

    service = get_eur_service(db)
    summary = await service.get_ytd_summary(
        company_id=company_id,
        year=year,
    )

    return YTDSummarySchema(
        year=summary["year"],
        months_completed=summary["months_completed"],
        total_income=summary["total_income"],
        total_expenses=summary["total_expenses"],
        cumulative_profit=summary["cumulative_profit"],
        avg_monthly_income=summary["avg_monthly_income"],
        avg_monthly_expenses=summary["avg_monthly_expenses"],
        monthly_data=summary["monthly_data"],
    )


@router.get(
    "/eur/anlage-eur",
    summary="Anlage EUER Export",
    description="Exportiert EUER als Anlage EUER (Steuerformular)",
)
async def export_anlage_eur(
    company_id: UUID = Query(..., description="Firmen-ID"),
    fiscal_year: int = Query(..., description="Geschäftsjahr"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, object]:
    """
    Exportiert die EUER als Anlage EUER für die Steuererklärung.

    Die Daten sind nach den offiziellen Zeilen der Anlage EUER strukturiert.
    """
    validate_company_access(company_id, current_user)
    logger.info(
        "eur_anlage_export_requested",
        company_id=str(company_id),
        user_id=str(current_user.id),
        fiscal_year=fiscal_year,
    )

    service = get_eur_service(db)
    report = await service.generate_eur_report(
        company_id=company_id,
        fiscal_year=fiscal_year,
        include_details=False,
    )

    anlage_data = report.to_anlage_eur()

    return {
        "fiscal_year": fiscal_year,
        "company_id": str(company_id),
        "anlage_eur": anlage_data,
        "generated_at": datetime.now().isoformat(),
    }


@router.get(
    "/eur/anlage-eur-html",
    summary="Anlage EUER HTML Export",
    description="Exportiert Anlage EUER als druckbare HTML-Seite",
)
async def export_anlage_eur_html(
    company_id: UUID = Query(..., description="Firmen-ID"),
    fiscal_year: int = Query(..., description="Geschäftsjahr"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Generiert eine druckbare HTML-Darstellung der Anlage EUER.

    Kann im Browser geöffnet und als PDF gedruckt werden.
    """
    validate_company_access(company_id, current_user)
    logger.info(
        "eur_anlage_html_export_requested",
        company_id=str(company_id),
        user_id=str(current_user.id),
        fiscal_year=fiscal_year,
    )

    service = get_eur_service(db)
    report = await service.generate_eur_report(
        company_id=company_id,
        fiscal_year=fiscal_year,
        include_details=False,
    )

    html_content = report.to_anlage_eur_html()

    return Response(
        content=html_content,
        media_type="text/html; charset=utf-8",
    )


# =============================================================================
# STATISTIKEN & DASHBOARD
# =============================================================================


@router.get(
    "/statistics",
    summary="Buchhaltungs-Statistiken",
    description="Aggregierte Kennzahlen für Dashboard",
)
async def get_accounting_statistics(
    company_id: UUID = Query(..., description="Firmen-ID"),
    year: Optional[int] = Query(None, description="Jahr (Standard: aktuelles Jahr)"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, object]:
    """
    Liefert aggregierte Buchhaltungs-Kennzahlen für das Dashboard.

    **Enthält:**
    - Offene Posten Zusammenfassung
    - USt-Status
    - EUER Year-to-Date
    - Trend-Indikatoren
    """
    validate_company_access(company_id, current_user)
    current_year = year or date.today().year

    # Services initialisieren
    op_service = get_open_items_service(db)
    vat_service = get_vat_service(db)
    eur_service = get_eur_service(db)

    # Daten parallel sammeln (vereinfacht)
    op_report = await op_service.get_open_items_report(company_id=company_id)
    ytd_summary = await eur_service.get_ytd_summary(company_id=company_id, year=current_year)

    return {
        "year": current_year,
        "open_items": {
            "total_receivables": str(op_report.total_receivables),
            "total_payables": str(op_report.total_payables),
            "net_position": str(op_report.net_position),
            "overdue_receivables": str(op_report.overdue_receivables),
            "overdue_payables": str(op_report.overdue_payables),
        },
        "eur_ytd": {
            "total_income": str(ytd_summary["total_income"]),
            "total_expenses": str(ytd_summary["total_expenses"]),
            "profit_loss": str(ytd_summary["cumulative_profit"]),
            "months_completed": ytd_summary["months_completed"],
        },
        "generated_at": datetime.now().isoformat(),
    }


# =============================================================================
# AUTO-BOOKING (BUCHUNGSVORSCHLAEGE)
# =============================================================================


class BookingSuggestionSchema(BaseModel):
    """Schema für einen Buchungsvorschlag."""

    debit_account: str = Field(..., description="Soll-Konto (SKR03/04)")
    debit_account_name: str = Field(..., description="Name des Soll-Kontos")
    credit_account: str = Field(..., description="Haben-Konto (SKR03/04)")
    credit_account_name: str = Field(..., description="Name des Haben-Kontos")
    amount: Decimal = Field(..., description="Buchungsbetrag")
    tax_code: Optional[str] = Field(None, description="DATEV-Steuerschlüssel")
    tax_rate: Optional[float] = Field(None, description="Steuersatz in Prozent")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Konfidenz (0-1)")
    confidence_level: str = Field(..., description="Konfidenz-Stufe")
    explanation: str = Field(..., description="Erklärung für den Vorschlag")
    similar_bookings_count: int = Field(0, description="Anzahl ähnlicher Buchungen")
    booking_text: Optional[str] = Field(None, description="Buchungstext")

    model_config = ConfigDict(from_attributes=True)


class AlternativeSuggestionSchema(BaseModel):
    """Schema für alternative Buchungsvorschläge."""

    debit_account: str
    debit_account_name: str
    credit_account: str
    credit_account_name: str
    confidence: float
    explanation: str


class AutoBookingResultSchema(BaseModel):
    """Schema für das Auto-Booking Ergebnis."""

    document_id: UUID
    document_type: Optional[str] = None
    entity_name: Optional[str] = None
    primary_suggestion: BookingSuggestionSchema
    alternative_suggestions: List[AlternativeSuggestionSchema] = []
    booking_type: str = Field(..., description="expense, revenue, etc.")
    analysis_details: Dict[str, object] = Field(default_factory=dict)
    can_auto_book: bool = Field(
        False, description="True wenn Confidence >= 90% (HIGH)"
    )


class BookingPatternSchema(BaseModel):
    """Schema für ein Buchungsmuster."""

    supplier_name: Optional[str] = None
    entity_id: Optional[UUID] = None
    debit_account: str
    credit_account: str
    tax_code: Optional[str] = None
    occurrence_count: int
    last_used_at: Optional[datetime] = None
    average_amount: Optional[Decimal] = None
    confidence: float


class LearnBookingRequest(BaseModel):
    """Request für Booking-Feedback."""

    document_id: UUID = Field(..., description="Dokument-ID")
    debit_account: str = Field(..., description="Gewaehltes Soll-Konto")
    credit_account: str = Field(..., description="Gewaehltes Haben-Konto")
    tax_code: Optional[str] = Field(None, description="DATEV-Steuerschlüssel")
    booking_text: Optional[str] = Field(None, description="Buchungstext")


class ApplyBookingRequest(BaseModel):
    """Request zum Anwenden eines Buchungsvorschlags."""

    document_id: UUID = Field(..., description="Dokument-ID")
    debit_account: str = Field(..., description="Soll-Konto")
    credit_account: str = Field(..., description="Haben-Konto")
    amount: Decimal = Field(..., description="Buchungsbetrag")
    tax_code: Optional[str] = Field(None, description="DATEV-Steuerschlüssel")
    booking_date: Optional[date] = Field(None, description="Buchungsdatum")
    booking_text: Optional[str] = Field(None, description="Buchungstext")
    auto_export_datev: bool = Field(False, description="Direkt nach DATEV exportieren")


class ApplyBookingResponse(BaseModel):
    """Response nach Anwenden einer Buchung."""

    success: bool
    booking_id: Optional[UUID] = None
    message: str
    datev_exported: bool = False


@router.post(
    "/auto-booking/suggest/{document_id}",
    response_model=AutoBookingResultSchema,
    summary="Buchungsvorschlag generieren",
    description="Generiert ML-basierte Buchungsvorschläge für ein Dokument",
)
async def suggest_booking(
    document_id: UUID,
    company_id: UUID = Query(..., description="Firmen-ID"),
    kontenrahmen: str = Query("SKR03", description="Kontenrahmen (SKR03/SKR04)"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> AutoBookingResultSchema:
    """
    Generiert automatische Buchungsvorschläge basierend auf:

    **Analyse-Faktoren:**
    - **Lieferanten-Historie**: Wie wurde dieser Lieferant bisher gebucht?
    - **Dokumenttyp**: Rechnung → Aufwand, Gutschrift → Ertrag
    - **Betragsanalyse**: Kleine Beträge oft Büromaterial
    - **Text-Analyse**: Keywords wie "Telefon", "Miete", "Personal"

    **Konfidenz-Stufen:**
    - **HIGH** (>90%): Auto-Booking möglich
    - **MEDIUM** (70-90%): Vorschlag mit Bestätigung
    - **LOW** (50-70%): Vorschlag mit Warnung
    - **UNCERTAIN** (<50%): Manuelle Kontierung
    """
    validate_company_access(company_id, current_user)
    logger.info(
        "auto_booking_suggest_requested",
        document_id=str(document_id),
        company_id=str(company_id),
        user_id=str(current_user.id),
        kontenrahmen=kontenrahmen,
    )

    # Kontenrahmen validieren
    if kontenrahmen not in ("SKR03", "SKR04"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ungültiger Kontenrahmen. Erlaubt: SKR03, SKR04",
        )

    service = get_auto_booking_service(db)
    result = await service.suggest_booking(
        document_id=document_id,
        company_id=company_id,
        kontenrahmen=kontenrahmen,
    )

    # Primary Suggestion mappen
    primary = result.suggestion
    primary_schema = BookingSuggestionSchema(
        debit_account=primary.debit_account,
        debit_account_name=primary.debit_account_name,
        credit_account=primary.credit_account,
        credit_account_name=primary.credit_account_name,
        amount=primary.amount,
        tax_code=primary.tax_code.value if primary.tax_code else None,
        tax_rate=primary.tax_rate,
        confidence=primary.confidence,
        confidence_level=primary.confidence_level.value,
        explanation=primary.explanation,
        similar_bookings_count=primary.similar_bookings_count,
        booking_text=primary.booking_text,
    )

    # Alternativen mappen
    alternatives = [
        AlternativeSuggestionSchema(
            debit_account=alt.debit_account,
            debit_account_name=alt.debit_account_name,
            credit_account=alt.credit_account,
            credit_account_name=alt.credit_account_name,
            confidence=alt.confidence,
            explanation=alt.explanation,
        )
        for alt in (primary.alternative_suggestions or [])
    ]

    return AutoBookingResultSchema(
        document_id=result.document_id,
        document_type=result.document_type,
        entity_name=result.entity_name,
        primary_suggestion=primary_schema,
        alternative_suggestions=alternatives,
        booking_type=result.booking_type.value,
        analysis_details=result.analysis_details,
        can_auto_book=result.can_auto_book,
    )


@router.post(
    "/auto-booking/learn",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Buchung lernen",
    description="Meldet eine tatsächliche Buchung zum Lernen",
)
async def learn_booking(
    request: LearnBookingRequest,
    company_id: UUID = Query(..., description="Firmen-ID"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Meldet eine vom User bestätigte/korrigierte Buchung zurück.

    Das System lernt aus diesen Korrekturen und verbessert zukuenftige
    Vorschläge für diesen Lieferanten/Dokumenttyp.

    **Verwendung:**
    - Nach manueller Kontierung
    - Nach Korrektur eines Vorschlags
    - Nach Bestätigung eines Auto-Bookings
    """
    validate_company_access(company_id, current_user)
    logger.info(
        "auto_booking_learn_requested",
        document_id=str(request.document_id),
        company_id=str(company_id),
        user_id=str(current_user.id),
        debit_account=request.debit_account,
        credit_account=request.credit_account,
    )

    service = get_auto_booking_service(db)
    await service.learn_from_booking(
        document_id=request.document_id,
        company_id=company_id,
        debit_account=request.debit_account,
        credit_account=request.credit_account,
        tax_code=request.tax_code,
        user_id=current_user.id,
    )


@router.get(
    "/auto-booking/patterns",
    response_model=List[BookingPatternSchema],
    summary="Buchungsmuster abrufen",
    description="Zeigt gelernte Buchungsmuster für einen Lieferanten",
)
async def get_booking_patterns(
    company_id: UUID = Query(..., description="Firmen-ID"),
    supplier_name: Optional[str] = Query(None, description="Lieferantenname"),
    entity_id: Optional[UUID] = Query(None, description="Entity-ID"),
    min_occurrences: int = Query(2, ge=1, description="Mindestanzahl Vorkommen"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> List[BookingPatternSchema]:
    """
    Zeigt die gelernten Buchungsmuster für einen Lieferanten.

    **Nützlich für:**
    - Analyse der Buchungshistorie
    - Erkennung von Anomalien
    - Optimierung der Kontierung

    **Filter:**
    - Nach Lieferantenname (Fuzzy-Match)
    - Nach Entity-ID (exakt)
    - Mindestanzahl Vorkommen
    """
    validate_company_access(company_id, current_user)
    logger.info(
        "auto_booking_patterns_requested",
        company_id=str(company_id),
        user_id=str(current_user.id),
        supplier_name=supplier_name,
        entity_id=str(entity_id) if entity_id else None,
    )

    service = get_auto_booking_service(db)
    patterns = await service.get_supplier_patterns(
        company_id=company_id,
        supplier_name=supplier_name,
        entity_id=entity_id,
    )

    # Nach min_occurrences filtern
    filtered = [p for p in patterns if p.occurrence_count >= min_occurrences]

    return [
        BookingPatternSchema(
            supplier_name=p.supplier_name,
            entity_id=p.entity_id,
            debit_account=p.debit_account,
            credit_account=p.credit_account,
            tax_code=p.tax_code.value if p.tax_code else None,
            occurrence_count=p.occurrence_count,
            last_used_at=p.last_used_at,
            average_amount=p.average_amount,
            confidence=p.confidence,
        )
        for p in filtered
    ]


@router.post(
    "/auto-booking/apply",
    response_model=ApplyBookingResponse,
    summary="Buchung anwenden",
    description="Wendet einen Buchungsvorschlag an und speichert die Buchung",
)
async def apply_booking(
    request: ApplyBookingRequest,
    company_id: UUID = Query(..., description="Firmen-ID"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> ApplyBookingResponse:
    """
    Wendet einen Buchungsvorschlag an und speichert die Buchung.

    **Aktionen:**
    1. Buchung in der Datenbank speichern
    2. Dokument als "gebucht" markieren
    3. Optional: DATEV-Export vorbereiten
    4. Lernen aus der Buchung (für zukuenftige Vorschläge)

    **Hinweis:** Bei auto_export_datev=true wird die Buchung direkt
    in den nächsten DATEV-Buchungsstapel aufgenommen.
    """
    validate_company_access(company_id, current_user)
    logger.info(
        "auto_booking_apply_requested",
        document_id=str(request.document_id),
        company_id=str(company_id),
        user_id=str(current_user.id),
        debit_account=request.debit_account,
        credit_account=request.credit_account,
        amount=str(request.amount),
        auto_export_datev=request.auto_export_datev,
    )

    service = get_auto_booking_service(db)

    try:
        # Buchung anwenden
        booking_id = await service.apply_booking(
            document_id=request.document_id,
            company_id=company_id,
            debit_account=request.debit_account,
            credit_account=request.credit_account,
            amount=request.amount,
            tax_code=request.tax_code,
            booking_date=request.booking_date,
            booking_text=request.booking_text,
            user_id=current_user.id,
            auto_export_datev=request.auto_export_datev,
        )

        # Lernen aus der Buchung
        await service.learn_from_booking(
            document_id=request.document_id,
            company_id=company_id,
            debit_account=request.debit_account,
            credit_account=request.credit_account,
            tax_code=request.tax_code,
            user_id=current_user.id,
        )

        return ApplyBookingResponse(
            success=True,
            booking_id=booking_id,
            message="Buchung erfolgreich angewendet",
            datev_exported=request.auto_export_datev,
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Buchung"),
        )
    except Exception as e:
        logger.error(
            "auto_booking_apply_failed",
            document_id=str(request.document_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Buchung"),
        )


@router.get(
    "/auto-booking/statistics",
    summary="Auto-Booking Statistiken",
    description="Zeigt Statistiken zur Auto-Booking Performance",
)
async def get_auto_booking_statistics(
    company_id: UUID = Query(..., description="Firmen-ID"),
    period_days: int = Query(30, ge=1, le=365, description="Zeitraum in Tagen"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, object]:
    """
    Zeigt Statistiken zur Auto-Booking Performance.

    **Metriken:**
    - Anzahl Vorschläge (gesamt, akzeptiert, korrigiert)
    - Durchschnittliche Konfidenz
    - Top-Konten nach Häufigkeit
    - Lernfortschritt über Zeit
    """
    validate_company_access(company_id, current_user)
    logger.info(
        "auto_booking_statistics_requested",
        company_id=str(company_id),
        user_id=str(current_user.id),
        period_days=period_days,
    )

    service = get_auto_booking_service(db)
    stats = await service.get_statistics(
        company_id=company_id,
        period_days=period_days,
    )

    return {
        "period_days": period_days,
        "total_suggestions": stats.get("total_suggestions", 0),
        "accepted_suggestions": stats.get("accepted_suggestions", 0),
        "corrected_suggestions": stats.get("corrected_suggestions", 0),
        "acceptance_rate": stats.get("acceptance_rate", 0.0),
        "average_confidence": stats.get("average_confidence", 0.0),
        "auto_booked_count": stats.get("auto_booked_count", 0),
        "top_debit_accounts": stats.get("top_debit_accounts", []),
        "top_credit_accounts": stats.get("top_credit_accounts", []),
        "confidence_distribution": stats.get("confidence_distribution", {}),
        "generated_at": datetime.now().isoformat(),
    }


@router.get(
    "/auto-booking/kontenrahmen/{kontenrahmen}",
    summary="Kontenrahmen abrufen",
    description="Gibt die verfügbaren Konten des Kontenrahmens zurück",
)
async def get_kontenrahmen(
    kontenrahmen: str,
    account_class: Optional[str] = Query(None, description="Kontenklasse (0-9)"),
    search: Optional[str] = Query(None, description="Suchbegriff"),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, object]:
    """
    Gibt die Konten eines Kontenrahmens zurück.

    **Kontenklassen (SKR03):**
    - **0**: Anlage- und Kapitalkonten
    - **1**: Finanzkonten
    - **2**: Abgrenzungskonten
    - **3**: Wareneingang/Bestand
    - **4**: Betriebliche Aufwendungen
    - **5**: Sonstige Aufwendungen
    - **6**: (Reserviert)
    - **7**: Bestandsveränderungen
    - **8**: Erlöse
    - **9**: Vortragskonten
    """
    if kontenrahmen not in ("SKR03", "SKR04"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ungültiger Kontenrahmen. Erlaubt: SKR03, SKR04",
        )

    # Kontenrahmen-Daten laden
    if kontenrahmen == "SKR03":
        from app.services.datev.kontenrahmen.skr03 import SKR03_ACCOUNTS
        accounts = SKR03_ACCOUNTS
    else:
        from app.services.datev.kontenrahmen.skr04 import SKR04_ACCOUNTS
        accounts = SKR04_ACCOUNTS

    # Filtern
    result = []
    for account_num, account_name in accounts.items():
        # Nach Kontenklasse filtern
        if account_class and not account_num.startswith(account_class):
            continue

        # Nach Suchbegriff filtern
        if search:
            search_lower = search.lower()
            if (
                search_lower not in account_num.lower()
                and search_lower not in account_name.lower()
            ):
                continue

        result.append({
            "account_number": account_num,
            "account_name": account_name,
            "account_class": account_num[0] if account_num else "",
        })

    # Nach Kontonummer sortieren
    result.sort(key=lambda x: x["account_number"])

    return {
        "kontenrahmen": kontenrahmen,
        "account_count": len(result),
        "accounts": result[:100],  # Limitieren auf 100
        "has_more": len(result) > 100,
    }


# =============================================================================
# GL-POSTING (GENERAL LEDGER)
# =============================================================================


class JournalEntryLineSchema(BaseModel):
    """Schema für Buchungszeile."""
    account_number: str = Field(..., max_length=5, description="Kontonummer")
    account_name: str = Field(..., max_length=100, description="Kontobezeichnung")
    debit_amount: Decimal = Field(default=Decimal("0"), description="Soll-Betrag")
    credit_amount: Decimal = Field(default=Decimal("0"), description="Haben-Betrag")
    tax_code: Optional[str] = Field(None, max_length=10, description="BU-Schlüssel")
    tax_rate: Optional[Decimal] = Field(None, description="Steuersatz")
    cost_center: Optional[str] = Field(None, max_length=20, description="Kostenstelle")
    text: str = Field(default="", max_length=60, description="Buchungstext")

    model_config = ConfigDict(from_attributes=True)


class JournalEntrySchema(BaseModel):
    """Schema für Buchungssatz."""
    id: UUID
    company_id: UUID
    document_id: Optional[UUID] = None
    posting_date: date
    fiscal_year: int
    fiscal_period: int
    entry_number: str
    description: Optional[str] = None
    total_amount: Optional[Decimal] = None
    currency: str = "EUR"
    status: str
    source: Optional[str] = None
    confidence: Optional[Decimal] = None
    created_at: datetime
    posted_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class JournalEntryCreateRequest(BaseModel):
    """Request zum Erstellen eines Buchungssatzes."""
    lines: List[JournalEntryLineSchema] = Field(..., min_length=2, description="Buchungszeilen (min. 2)")
    posting_date: date = Field(..., description="Buchungsdatum")
    description: Optional[str] = Field(None, max_length=60, description="Beschreibung")
    document_id: Optional[UUID] = Field(None, description="Verknüpftes Dokument")


class TrialBalanceRowSchema(BaseModel):
    """Schema für Summen-Saldenliste Zeile."""
    account_number: str
    account_name: str
    total_debit: Decimal
    total_credit: Decimal
    balance: Decimal


class LedgerEntrySchema(BaseModel):
    """Schema für Kontoblatt-Zeile."""
    entry_id: UUID
    posting_date: date
    entry_number: str
    description: str
    debit_amount: Decimal
    credit_amount: Decimal
    running_balance: Decimal


class TaxPeriodSchema(BaseModel):
    """Schema für Steuerperiode."""
    id: UUID
    company_id: UUID
    fiscal_year: int
    period_type: str
    period_number: int
    period_start: date
    period_end: date
    status: str
    total_output_vat: Decimal
    total_input_vat: Decimal
    vat_payable: Decimal
    filed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class UStVAReportSchema(BaseModel):
    """Schema für USt-VA Report."""
    company_id: UUID
    fiscal_year: int
    period_type: str
    period_number: int
    period_start: date
    period_end: date
    total_output_vat: Decimal
    total_input_vat: Decimal
    vat_payable: Decimal


class EUeRReportSchema(BaseModel):
    """Schema für EÜR Report."""
    company_id: UUID
    fiscal_year: int
    period_start: date
    period_end: date
    total_revenue: Decimal
    total_expenses: Decimal
    profit_loss: Decimal


@router.post(
    "/journal-entries",
    response_model=JournalEntrySchema,
    status_code=status.HTTP_201_CREATED,
    summary="Buchungssatz erstellen",
    description="Erstellt einen neuen Buchungssatz (status=draft)",
)
async def create_journal_entry(
    request: JournalEntryCreateRequest,
    company_id: UUID = Query(..., description="Firmen-ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> JournalEntrySchema:
    """Erstellt einen Buchungssatz im Entwurfs-Status."""
    validate_company_access(company_id, current_user)

    from app.services.accounting.gl_posting_service import (
        GLPostingService,
        JournalEntryLineCreate,
    )

    service = GLPostingService(db)

    lines = [
        JournalEntryLineCreate(
            account_number=line.account_number,
            account_name=line.account_name,
            debit_amount=line.debit_amount,
            credit_amount=line.credit_amount,
            tax_code=line.tax_code,
            tax_rate=line.tax_rate,
            cost_center=line.cost_center,
            text=line.text,
        )
        for line in request.lines
    ]

    entry = await service.create_journal_entry(
        company_id=company_id,
        lines=lines,
        posting_date=request.posting_date,
        description=request.description,
        document_id=request.document_id,
        source="manual",
        created_by=current_user.id,
    )
    await db.commit()

    return JournalEntrySchema.model_validate(entry)


@router.get(
    "/journal-entries",
    response_model=List[JournalEntrySchema],
    summary="Buchungssätze auflisten",
    description="Listet Buchungssätze mit Filtern",
)
async def list_journal_entries(
    company_id: UUID = Query(..., description="Firmen-ID"),
    fiscal_year: Optional[int] = Query(None, description="Geschäftsjahr"),
    fiscal_period: Optional[int] = Query(None, ge=1, le=12, description="Periode 1-12"),
    status_filter: Optional[str] = Query(None, description="Status-Filter"),
    limit: int = Query(50, ge=1, le=100, description="Max Anzahl"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> List[JournalEntrySchema]:
    """Listet Buchungssätze."""
    validate_company_access(company_id, current_user)

    from app.db.models_gl_posting import JournalEntry

    stmt = select(JournalEntry).where(JournalEntry.company_id == company_id)

    if fiscal_year:
        stmt = stmt.where(JournalEntry.fiscal_year == fiscal_year)
    if fiscal_period:
        stmt = stmt.where(JournalEntry.fiscal_period == fiscal_period)
    if status_filter:
        stmt = stmt.where(JournalEntry.status == status_filter)

    stmt = stmt.order_by(JournalEntry.posting_date.desc(), JournalEntry.entry_number.desc()).limit(limit)

    result = await db.execute(stmt)
    entries = result.scalars().all()

    return [JournalEntrySchema.model_validate(e) for e in entries]


@router.get(
    "/journal-entries/{entry_id}",
    response_model=JournalEntrySchema,
    summary="Buchungssatz abrufen",
    description="Ruft einzelnen Buchungssatz ab",
)
async def get_journal_entry(
    entry_id: UUID,
    company_id: UUID = Query(..., description="Firmen-ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> JournalEntrySchema:
    """Ruft einzelnen Buchungssatz ab."""
    validate_company_access(company_id, current_user)

    from app.db.models_gl_posting import JournalEntry

    stmt = select(JournalEntry).where(
        and_(JournalEntry.id == entry_id, JournalEntry.company_id == company_id)
    )
    result = await db.execute(stmt)
    entry = result.scalar_one_or_none()

    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Buchungssatz nicht gefunden",
        )

    return JournalEntrySchema.model_validate(entry)


@router.post(
    "/journal-entries/{entry_id}/post",
    response_model=JournalEntrySchema,
    summary="Buchungssatz buchen",
    description="Bucht einen Entwurf (draft -> posted)",
)
async def post_journal_entry(
    entry_id: UUID,
    company_id: UUID = Query(..., description="Firmen-ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> JournalEntrySchema:
    """Bucht einen Buchungssatz."""
    validate_company_access(company_id, current_user)

    from app.services.accounting.gl_posting_service import GLPostingService

    service = GLPostingService(db)
    entry = await service.post_journal_entry(entry_id, current_user.id)
    await db.commit()

    return JournalEntrySchema.model_validate(entry)


@router.post(
    "/journal-entries/{entry_id}/reverse",
    response_model=JournalEntrySchema,
    summary="Buchungssatz stornieren",
    description="Storniert einen gebuchten Eintrag (GoBD-konform)",
)
async def reverse_journal_entry(
    entry_id: UUID,
    reason: str = Query(..., description="Stornierungsgrund"),
    company_id: UUID = Query(..., description="Firmen-ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> JournalEntrySchema:
    """Storniert einen Buchungssatz."""
    validate_company_access(company_id, current_user)

    from app.services.accounting.gl_posting_service import GLPostingService

    service = GLPostingService(db)
    reversal = await service.reverse_journal_entry(entry_id, current_user.id, reason)
    await db.commit()

    return JournalEntrySchema.model_validate(reversal)


@router.post(
    "/journal-entries/from-document/{document_id}",
    response_model=JournalEntrySchema,
    status_code=status.HTTP_201_CREATED,
    summary="Buchung aus Dokument",
    description="Erstellt und bucht Entry aus OCR-Dokument",
)
async def create_entry_from_document(
    document_id: UUID,
    company_id: UUID = Query(..., description="Firmen-ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> JournalEntrySchema:
    """Erstellt Buchung aus Dokument."""
    validate_company_access(company_id, current_user)

    from app.services.accounting.gl_posting_service import GLPostingService

    service = GLPostingService(db)
    entry = await service.post_from_invoice(company_id, document_id, current_user.id)
    await db.commit()

    return JournalEntrySchema.model_validate(entry)


@router.get(
    "/trial-balance",
    response_model=List[TrialBalanceRowSchema],
    summary="Summen-Saldenliste",
    description="Erstellt Summen-Saldenliste (Trial Balance)",
)
async def get_trial_balance(
    company_id: UUID = Query(..., description="Firmen-ID"),
    fiscal_year: int = Query(..., description="Geschäftsjahr"),
    period: Optional[int] = Query(None, ge=1, le=12, description="Periode (optional)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> List[TrialBalanceRowSchema]:
    """Erstellt Summen-Saldenliste."""
    validate_company_access(company_id, current_user)

    from app.services.accounting.gl_posting_service import GLPostingService

    service = GLPostingService(db)
    rows = await service.get_trial_balance(company_id, fiscal_year, period)

    return [TrialBalanceRowSchema.model_validate(r) for r in rows]


@router.get(
    "/account-ledger/{account_number}",
    response_model=List[LedgerEntrySchema],
    summary="Kontoblatt",
    description="Erstellt Kontoblatt für ein Konto",
)
async def get_account_ledger(
    account_number: str,
    company_id: UUID = Query(..., description="Firmen-ID"),
    fiscal_year: int = Query(..., description="Geschäftsjahr"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> List[LedgerEntrySchema]:
    """Erstellt Kontoblatt."""
    validate_company_access(company_id, current_user)

    from app.services.accounting.gl_posting_service import GLPostingService

    service = GLPostingService(db)
    entries = await service.get_account_ledger(company_id, account_number, fiscal_year)

    return [LedgerEntrySchema.model_validate(e) for e in entries]


@router.get(
    "/tax-periods",
    response_model=List[TaxPeriodSchema],
    summary="Steuerperioden auflisten",
    description="Listet USt-VA Perioden",
)
async def list_tax_periods(
    company_id: UUID = Query(..., description="Firmen-ID"),
    fiscal_year: Optional[int] = Query(None, description="Geschäftsjahr"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> List[TaxPeriodSchema]:
    """Listet Steuerperioden."""
    validate_company_access(company_id, current_user)

    from app.db.models_gl_posting import TaxPeriod

    stmt = select(TaxPeriod).where(TaxPeriod.company_id == company_id)
    if fiscal_year:
        stmt = stmt.where(TaxPeriod.fiscal_year == fiscal_year)
    stmt = stmt.order_by(TaxPeriod.fiscal_year.desc(), TaxPeriod.period_number.desc())

    result = await db.execute(stmt)
    periods = result.scalars().all()

    return [TaxPeriodSchema.model_validate(p) for p in periods]


@router.post(
    "/tax-periods",
    response_model=TaxPeriodSchema,
    status_code=status.HTTP_201_CREATED,
    summary="USt-VA erstellen",
    description="Erstellt USt-Voranmeldung",
)
async def create_tax_period(
    fiscal_year: int = Query(..., description="Jahr"),
    period_type: str = Query(..., description="monthly oder quarterly"),
    period_number: int = Query(..., description="Monat 1-12 oder Quartal 1-4"),
    company_id: UUID = Query(..., description="Firmen-ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> TaxPeriodSchema:
    """Erstellt USt-VA."""
    validate_company_access(company_id, current_user)

    from app.services.accounting.ust_voranmeldung_service import UStVoranmeldungService

    service = UStVoranmeldungService(db)
    report = await service.generate_ust_voranmeldung(
        company_id, fiscal_year, period_type, period_number
    )
    tax_period = await service.file_ust_voranmeldung(company_id, report)
    await db.commit()

    return TaxPeriodSchema.model_validate(tax_period)


@router.post(
    "/tax-periods/{tax_period_id}/file",
    response_model=TaxPeriodSchema,
    summary="USt-VA einreichen",
    description="Reicht USt-VA ein (Status filed)",
)
async def file_tax_period(
    tax_period_id: UUID,
    company_id: UUID = Query(..., description="Firmen-ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> TaxPeriodSchema:
    """Reicht USt-VA ein."""
    validate_company_access(company_id, current_user)

    from app.db.models_gl_posting import TaxPeriod, TaxPeriodStatus
    from app.core.datetime_utils import utc_now

    stmt = select(TaxPeriod).where(
        and_(TaxPeriod.id == tax_period_id, TaxPeriod.company_id == company_id)
    )
    result = await db.execute(stmt)
    period = result.scalar_one_or_none()

    if not period:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Steuerperiode nicht gefunden",
        )

    period.status = TaxPeriodStatus.FILED.value
    period.filed_at = utc_now()
    await db.commit()

    return TaxPeriodSchema.model_validate(period)


@router.get(
    "/euer",
    response_model=EUeRReportSchema,
    summary="EÜR Report",
    description="Generiert Einnahmen-Überschuss-Rechnung",
)
async def get_euer_report(
    company_id: UUID = Query(..., description="Firmen-ID"),
    fiscal_year: int = Query(..., description="Geschäftsjahr"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> EUeRReportSchema:
    """Generiert EÜR."""
    validate_company_access(company_id, current_user)

    from app.services.accounting.euer_report_service import EUeRReportService

    service = EUeRReportService(db)
    report = await service.generate_euer(company_id, fiscal_year)

    return EUeRReportSchema.model_validate(report)


# =============================================================================
# FX RATE & CURRENCY ENDPOINTS
# =============================================================================


class ExchangeRateSchema(BaseModel):
    """Schema für Wechselkurs."""
    base_currency: str = "EUR"
    target_currency: str
    rate: Decimal
    rate_date: date
    source: str

    model_config = ConfigDict(from_attributes=True)


class ConversionRequest(BaseModel):
    """Anfrage zur Währungsumrechnung."""
    amount: Decimal = Field(..., gt=0, description="Betrag")
    from_currency: str = Field(..., min_length=3, max_length=3, description="Von Währung")
    to_currency: str = Field(default="EUR", min_length=3, max_length=3, description="Zu Währung")
    rate_date: Optional[date] = Field(None, description="Stichtag (optional)")


class ConversionResultSchema(BaseModel):
    """Ergebnis einer Währungsumrechnung."""
    original_amount: Decimal
    original_currency: str
    converted_amount: Decimal
    target_currency: str
    rate_used: Decimal
    rate_date: date
    rate_source: str


class FXGainLossSchema(BaseModel):
    """Schema für Kursgewinn/-verlust."""
    id: UUID
    original_currency: str
    original_amount: Decimal
    booking_rate: Decimal
    settlement_rate: Decimal
    gain_loss_amount: Decimal
    gain_loss_account: str
    realized: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FXGainLossCalculateRequest(BaseModel):
    """Anfrage zur Berechnung von Kursgewinn/-verlust.

    Schemathesis-Fix (W1-004 #1): Denormal-Floats (z.B. 5e-324) als Kurs
    führten zu decimal.InvalidOperation beim Quantisieren (500).
    max_digits/decimal_places begrenzen den Wertebereich -> 422.
    Währung muss ein ISO-4217-Alphacode sein ("000" -> 422).
    """
    original_amount: Decimal = Field(
        ..., gt=0, max_digits=18, decimal_places=6, description="Ursprungsbetrag"
    )
    original_currency: str = Field(
        ...,
        min_length=3,
        max_length=3,
        pattern=r"^[A-Za-z]{3}$",
        description="Währung (ISO 4217, z.B. USD)",
    )
    booking_rate: Decimal = Field(
        ..., gt=0, max_digits=20, decimal_places=10, description="Buchungskurs"
    )
    settlement_rate: Decimal = Field(
        ..., gt=0, max_digits=20, decimal_places=10, description="Zahlungskurs"
    )


class FXGainLossCalculateResponse(BaseModel):
    """Vorschau der Kursgewinn/-verlust Berechnung."""
    original_currency: str
    original_amount: Decimal
    booking_rate: Decimal
    settlement_rate: Decimal
    booking_eur_amount: Decimal
    settlement_eur_amount: Decimal
    gain_loss_amount: Decimal
    gain_loss_account: str
    is_gain: bool


@router.get(
    "/fx-rates",
    response_model=ExchangeRateSchema,
    summary="Wechselkurs abfragen",
    description="Holt ECB-Referenzkurs für eine Währung",
)
async def get_exchange_rate(
    currency: str = Query(..., description="Währung (z.B. USD, GBP)"),
    rate_date: Optional[date] = Query(None, description="Stichtag (optional)"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> ExchangeRateSchema:
    """
    Gibt den ECB-Wechselkurs für eine Währung zurück.

    Falls kein exakter Kurs vorhanden, wird auf den nächsten verfügbaren
    Kurs innerhalb von 7 Tagen zurückgegriffen.
    """
    logger.info(
        "fx_rate_requested",
        user_id=str(current_user.id),
        currency=currency,
        rate_date=str(rate_date) if rate_date else "today",
    )

    service = get_fx_rate_service(db)
    rate = await service.get_rate(currency, rate_date)

    if rate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Kein Wechselkurs verfügbar für {currency}",
        )

    lookup_date = rate_date or date.today()

    return ExchangeRateSchema(
        base_currency="EUR",
        target_currency=currency,
        rate=rate,
        rate_date=lookup_date,
        source="ecb",
    )


@router.post(
    "/fx-rates/fetch",
    status_code=status.HTTP_202_ACCEPTED,
    summary="ECB Kurse abrufen (Admin)",
    description="Triggert Abruf der aktuellen ECB-Referenzkurse",
)
async def fetch_ecb_rates(
    historical: bool = Query(False, description="Historische Kurse (90 Tage)"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, object]:
    """
    Triggert den Abruf von ECB-Referenzkursen.

    **Nur für Administratoren.**

    - historical=False: Aktuelle Tageskurse
    - historical=True: Letzte 90 Tage
    """
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nur Administratoren können Kurse abrufen",
        )

    logger.info(
        "fx_rates_fetch_triggered",
        user_id=str(current_user.id),
        historical=historical,
    )

    from app.workers.tasks.fx_rate_tasks import (
        fetch_ecb_rates_daily,
        fetch_ecb_rates_historical,
    )

    if historical:
        task = fetch_ecb_rates_historical.delay()
    else:
        task = fetch_ecb_rates_daily.delay()

    return {
        "status": "accepted",
        "task_id": task.id,
        "message": "Kursabruf wurde gestartet",
    }


@router.post(
    "/fx-rates/convert",
    response_model=ConversionResultSchema,
    summary="Währungsumrechnung",
    description="Rechnet Betrag in andere Währung um",
)
async def convert_currency(
    request: ConversionRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> ConversionResultSchema:
    """
    Rechnet einen Betrag von einer Währung in eine andere um.

    Verwendet ECB-Referenzkurse. Bei Cross-Rates wird über EUR gerechnet.
    """
    logger.info(
        "fx_conversion_requested",
        user_id=str(current_user.id),
        amount=str(request.amount),
        from_currency=request.from_currency,
        to_currency=request.to_currency,
    )

    service = get_fx_rate_service(db)

    try:
        result = await service.convert(
            amount=request.amount,
            from_currency=request.from_currency,
            to_currency=request.to_currency,
            rate_date=request.rate_date,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Buchhaltung"),
        )

    return ConversionResultSchema(
        original_amount=result.original_amount,
        original_currency=result.original_currency,
        converted_amount=result.converted_amount,
        target_currency=result.target_currency,
        rate_used=result.rate_used,
        rate_date=result.rate_date,
        rate_source=result.rate_source,
    )


@router.get(
    "/fx-rates/currencies",
    response_model=List[str],
    summary="Verfügbare Währungen",
    description="Listet alle Währungen mit verfügbaren ECB-Kursen",
)
async def get_available_currencies(
    for_date: Optional[date] = Query(None, description="Stichtag (optional)"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> List[str]:
    """
    Gibt Liste aller Währungen zurück, für die ECB-Kurse verfügbar sind.
    """
    service = get_fx_rate_service(db)
    currencies = await service.get_available_currencies(for_date)

    return ["EUR"] + sorted(currencies)


@router.get(
    "/fx-gain-loss",
    response_model=List[FXGainLossSchema],
    summary="Kursgewinne/-verluste",
    description="Listet Kursgewinne und -verluste",
)
async def get_fx_gain_loss_entries(
    company_id: UUID = Query(..., description="Firmen-ID"),
    realized: Optional[bool] = Query(None, description="Nur realisierte (True) oder unrealisierte (False)"),
    currency: Optional[str] = Query(None, description="Währung filtern"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> List[FXGainLossSchema]:
    """
    Listet alle Kursgewinn-/verlust-Einträge für eine Firma.

    **Filter:**
    - realized: True (realisiert), False (unrealisiert), None (alle)
    - currency: Währung (z.B. USD)
    """
    validate_company_access(company_id, current_user)

    logger.info(
        "fx_gain_loss_list_requested",
        company_id=str(company_id),
        user_id=str(current_user.id),
        realized=realized,
        currency=currency,
    )

    service = get_fx_gain_loss_service(db)
    entries = await service.get_fx_entries(
        company_id=company_id,
        realized=realized,
        currency=currency,
    )

    return [FXGainLossSchema.model_validate(e) for e in entries]


@router.post(
    "/fx-gain-loss/calculate",
    response_model=FXGainLossCalculateResponse,
    summary="Kursgewinn/-verlust berechnen",
    description="Berechnet Vorschau von Kursgewinn oder -verlust",
)
async def calculate_fx_gain_loss(
    request: FXGainLossCalculateRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> FXGainLossCalculateResponse:
    """
    Berechnet einen Kursgewinn oder -verlust als Vorschau.

    Zeigt, wie viel Gewinn (Konto 2650) oder Verlust (Konto 2150)
    bei gegebenem Buchungs- und Zahlungskurs entsteht.

    **Keine Buchung** - nur Vorschau!
    """
    logger.info(
        "fx_gain_loss_calculate_requested",
        user_id=str(current_user.id),
        currency=request.original_currency,
        amount=str(request.original_amount),
    )

    service = get_fx_gain_loss_service(db)
    result = service.calculate_realized_gain_loss(
        original_amount=request.original_amount,
        original_currency=request.original_currency,
        booking_rate=request.booking_rate,
        settlement_rate=request.settlement_rate,
    )

    return FXGainLossCalculateResponse(
        original_currency=result.original_currency,
        original_amount=result.original_amount,
        booking_rate=result.booking_rate,
        settlement_rate=result.settlement_rate,
        booking_eur_amount=result.booking_eur_amount,
        settlement_eur_amount=result.settlement_eur_amount,
        gain_loss_amount=result.gain_loss_amount,
        gain_loss_account=result.gain_loss_account,
        is_gain=result.is_gain,
    )


# =============================================================================
# FX REVALUATION (Monatsabschluss-Stichtagsbewertung)
# =============================================================================


class FXRevaluationRequest(BaseModel):
    """Anfrage für manuelle Stichtagsbewertung."""
    company_id: UUID = Field(..., description="Firmen-ID")
    revaluation_date: date = Field(..., description="Bewertungsstichtag")


class CurrencyBreakdownSchema(BaseModel):
    """Währungs-Aufschlüsselung."""
    gain: str = Field(..., description="Kursgewinne in EUR")
    loss: str = Field(..., description="Kursverluste in EUR")
    positions: str = Field(..., description="Anzahl Positionen")


class FXRevaluationResponse(BaseModel):
    """Ergebnis der Stichtagsbewertung."""
    entries_processed: int = Field(..., description="Anzahl bewerteter Positionen")
    total_gain: str = Field(..., description="Gesamte Kursgewinne in EUR")
    total_loss: str = Field(..., description="Gesamte Kursverluste in EUR")
    currency_breakdown: Dict[str, CurrencyBreakdownSchema] = Field(
        default_factory=dict, description="Aufschlüsselung nach Währung"
    )


class FXRevaluationHistoryEntry(BaseModel):
    """Eintrag in der Bewertungshistorie."""
    id: str
    company_id: str
    original_currency: str
    original_amount: Decimal
    booking_rate: Decimal
    settlement_rate: Decimal
    gain_loss_amount: Decimal
    gain_loss_account: str
    realized: bool
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class FXExposureEntry(BaseModel):
    """Einzelne FX-Exposure-Position."""
    currency: str = Field(..., description="Währung")
    amount: str = Field(..., description="Ausstehender Betrag in Fremdwährung")
    eur_equivalent: str = Field(..., description="EUR-Gegenwert zum aktuellen Kurs")


class FXExposureResponse(BaseModel):
    """FX-Exposure-Übersicht."""
    exposures: List[FXExposureEntry] = Field(
        default_factory=list, description="Offene Währungs-Exposures"
    )


@router.post(
    "/fx/revaluation",
    response_model=FXRevaluationResponse,
    summary="Stichtagsbewertung auslösen",
    description="Führt eine manuelle Monatsabschluss-Stichtagsbewertung aller offenen Fremdwährungspositionen durch",
)
async def trigger_fx_revaluation(
    request: FXRevaluationRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> FXRevaluationResponse:
    """
    Manuelle Monatsabschluss-Bewertung aller offenen FX-Positionen.

    Bewertet offene Forderungen und Verbindlichkeiten in Fremdwährungen
    zum Stichtagskurs und bucht unrealisierte Kursgewinne/-verluste.

    **Achtung:** Diese Aktion erstellt Buchungen im Hauptbuch!
    """
    validate_company_access(request.company_id, current_user)

    logger.info(
        "fx_revaluation_triggered",
        user_id=str(current_user.id),
        company_id=str(request.company_id),
        revaluation_date=str(request.revaluation_date),
    )

    try:
        fx_service = get_fx_rate_service(db)
        summary = await fx_service.month_end_revaluation(
            company_id=request.company_id,
            revaluation_date=request.revaluation_date,
            db=db,
        )

        breakdown: Dict[str, CurrencyBreakdownSchema] = {}
        for cur, vals in summary.currency_breakdown.items():
            breakdown[cur] = CurrencyBreakdownSchema(
                gain=vals["gain"],
                loss=vals["loss"],
                positions=vals["positions"],
            )

        return FXRevaluationResponse(
            entries_processed=summary.entries_processed,
            total_gain=str(summary.total_gain),
            total_loss=str(summary.total_loss),
            currency_breakdown=breakdown,
        )
    except Exception as exc:
        logger.error("fx_revaluation_failed", **safe_error_log(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Stichtagsbewertung fehlgeschlagen: {safe_error_detail(exc)}",
        )


@router.get(
    "/fx/revaluation/history",
    response_model=List[FXRevaluationHistoryEntry],
    summary="Bewertungshistorie abrufen",
    description="Zeigt vergangene FX-Bewertungsläufe und ihre Ergebnisse",
)
async def get_fx_revaluation_history(
    company_id: UUID = Query(..., description="Firmen-ID"),
    from_date: Optional[date] = Query(None, description="Startdatum"),
    to_date: Optional[date] = Query(None, description="Enddatum"),
    limit: int = Query(50, ge=1, le=500, description="Max. Einträge"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> List[FXRevaluationHistoryEntry]:
    """
    Gibt die Historie der FX-Bewertungen zurück.

    Zeigt alle unrealisierten Kursgewinne/-verluste für die angegebene Firma
    im angegebenen Zeitraum.
    """
    validate_company_access(company_id, current_user)

    fx_gl_service = get_fx_gain_loss_service(db)
    entries = await fx_gl_service.get_fx_entries(
        company_id=company_id,
        realized=False,
    )

    # Filter nach Datum
    filtered = entries
    if from_date:
        filtered = [
            e for e in filtered
            if e.created_at and e.created_at.date() >= from_date
        ]
    if to_date:
        filtered = [
            e for e in filtered
            if e.created_at and e.created_at.date() <= to_date
        ]

    # Limit anwenden
    filtered = filtered[:limit]

    return [
        FXRevaluationHistoryEntry(
            id=str(e.id),
            company_id=str(e.company_id),
            original_currency=e.original_currency,
            original_amount=e.original_amount,
            booking_rate=e.booking_rate,
            settlement_rate=e.settlement_rate,
            gain_loss_amount=e.gain_loss_amount,
            gain_loss_account=e.gain_loss_account,
            realized=e.realized,
            created_at=e.created_at,
        )
        for e in filtered
    ]


@router.get(
    "/fx/exposure",
    response_model=FXExposureResponse,
    summary="Aktuelle FX-Exposure anzeigen",
    description="Zeigt offene Währungs-Exposure aller Nicht-EUR-Positionen",
)
async def get_fx_exposure(
    company_id: UUID = Query(..., description="Firmen-ID"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> FXExposureResponse:
    """
    Aktuelle Fremdwährungs-Exposure.

    Zeigt alle offenen Positionen in Nicht-EUR-Währungen
    mit dem aktuellen EUR-Gegenwert.
    """
    validate_company_access(company_id, current_user)

    try:
        fx_service = get_fx_rate_service(db)
        exposures = await fx_service.get_fx_exposure(
            company_id=company_id,
            db=db,
        )

        return FXExposureResponse(
            exposures=[
                FXExposureEntry(
                    currency=e["currency"],
                    amount=e["amount"],
                    eur_equivalent=e["eur_equivalent"],
                )
                for e in exposures
            ]
        )
    except Exception as exc:
        logger.error("fx_exposure_failed", **safe_error_log(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"FX-Exposure-Abfrage fehlgeschlagen: {safe_error_detail(exc)}",
        )

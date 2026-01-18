# -*- coding: utf-8 -*-
"""
Accounting API Endpoints.

REST API fuer integrierte Buchhaltung:
- Offene Posten (Debitoren/Kreditoren)
- USt-Voranmeldung
- Einnahmen-Ueberschuss-Rechnung (EUER)

GoBD-konform und Enterprise-Ready.
"""

from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import date, datetime
from decimal import Decimal
from enum import Enum

import structlog
from fastapi import APIRouter, Depends, HTTPException, status, Query, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.api.dependencies import get_db, get_current_active_user
from app.services.accounting import (
    get_open_items_service,
    get_vat_service,
    get_eur_service,
    OpenItemType,
    PaymentPriority,
    VATRate,
    IncomeCategory,
    ExpenseCategory,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/accounting", tags=["Buchhaltung"])


# =============================================================================
# SCHEMAS
# =============================================================================


class OpenItemSchema(BaseModel):
    """Schema fuer einen offenen Posten."""

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
    """Schema fuer Entity-Saldo."""

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
    """Schema fuer Offene-Posten-Bericht."""

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
    """Schema fuer Zahlungsvorschlag."""

    entity_id: UUID
    entity_name: str
    invoice_number: str
    amount: Decimal
    due_date: date
    priority: str
    reason: str
    skonto_savings: Optional[Decimal] = None


class VATSummarySchema(BaseModel):
    """Schema fuer USt-Kennziffer-Zusammenfassung."""

    kennziffer: str
    label: str
    net_amount: Decimal
    vat_amount: Decimal
    count: int


class VATReportSchema(BaseModel):
    """Schema fuer USt-Voranmeldung."""

    company_id: UUID
    period_type: str  # monthly, quarterly, annual
    period_start: date
    period_end: date
    period_label: str
    generated_at: datetime
    status: str = "draft"

    # Umsaetze (Output VAT)
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
    """Schema fuer EUER-Kategorie-Zusammenfassung."""

    category: str
    label: str
    amount: Decimal
    count: int


class EURReportSchema(BaseModel):
    """Schema fuer Einnahmen-Ueberschuss-Rechnung."""

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
    """Schema fuer Year-to-Date Zusammenfassung."""

    year: int
    months_completed: int
    total_income: Decimal
    total_expenses: Decimal
    cumulative_profit: Decimal
    avg_monthly_income: Decimal
    avg_monthly_expenses: Decimal
    monthly_data: List[Dict[str, Any]]


class OptimizeForEnum(str, Enum):
    """Optimierungsziel fuer Zahlungsvorschlaege."""

    SKONTO = "skonto"
    CASHFLOW = "cashflow"
    PRIORITY = "priority"


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def _map_vat_summary(summary: Any) -> VATSummarySchema:
    """Mappt VATSummary zu VATSummarySchema."""
    return VATSummarySchema(
        kennziffer=summary.kennziffer,
        label=summary.label,
        net_amount=summary.net_amount,
        vat_amount=summary.vat_amount,
        count=summary.count,
    )


def _map_vat_report(report: Any) -> VATReportSchema:
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


def _map_eur_category(category: Any) -> EURCategorySummarySchema:
    """Mappt EURCategorySummary zu EURCategorySummarySchema."""
    return EURCategorySummarySchema(
        category=category.category,
        label=category.label,
        amount=category.amount,
        count=category.count,
    )


def _map_eur_report(report: Any) -> EURReportSchema:
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
    description="Generiert einen Bericht ueber alle offenen Posten (Debitoren/Kreditoren)",
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

    **Enthaelt:**
    - Summe Forderungen (Debitoren)
    - Summe Verbindlichkeiten (Kreditoren)
    - Netto-Position
    - Altersstruktur (0-30, 31-60, 61-90, 90+ Tage)
    """
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
    entity_id: Optional[UUID] = Query(None, description="Nur fuer bestimmten Debitor"),
    overdue_only: bool = Query(False, description="Nur ueberfaellige"),
    priority: Optional[PaymentPriority] = Query(None, description="Nach Prioritaet filtern"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> List[OpenItemSchema]:
    """
    Listet alle offenen Forderungen auf.

    **Prioritaeten:**
    - **normal**: Faellig in >14 Tagen
    - **high**: Skonto-Frist naht
    - **urgent**: Ueberfaellig
    - **critical**: Stark ueberfaellig (90+ Tage)
    """
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
    entity_id: Optional[UUID] = Query(None, description="Nur fuer bestimmten Kreditor"),
    due_within_days: Optional[int] = Query(
        None, description="Nur faellig innerhalb X Tagen"
    ),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> List[OpenItemSchema]:
    """
    Listet alle offenen Verbindlichkeiten auf.

    Nuetzlich fuer:
    - Zahlungsplanung
    - Skonto-Optimierung
    - Liquiditaetsmanagement
    """
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

    Sortiert nach Ausstand (hoechster zuerst).
    """
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

    Sortiert nach Ausstand (hoechster zuerst).
    """
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
    summary="Zahlungsvorschlaege",
    description="Generiert optimierte Zahlungsvorschlaege",
)
async def get_payment_suggestions(
    company_id: UUID = Query(..., description="Firmen-ID"),
    available_funds: Decimal = Query(..., description="Verfuegbare Mittel in EUR"),
    optimize_for: OptimizeForEnum = Query(
        OptimizeForEnum.SKONTO, description="Optimierungsziel"
    ),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> List[PaymentSuggestionSchema]:
    """
    Generiert optimierte Zahlungsvorschlaege.

    **Optimierungsziele:**
    - **skonto**: Maximiere Skonto-Ersparnis
    - **cashflow**: Minimiere Zahlungsausgang
    - **priority**: Zahle nach Dringlichkeit
    """
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
    description="Generiert USt-VA fuer einen Monat",
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

    **Enthaelt:**
    - Steuerpflichtige Umsaetze (19%, 7%)
    - Vorsteuer aus Eingangsrechnungen
    - Zahllast / Erstattungsanspruch
    - Kennziffern nach ELSTER-Format
    """
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
    description="Generiert USt-VA fuer ein Quartal",
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

    Fuer Unternehmen mit quartalsweiser Abgabepflicht.
    """
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

    xml_content = report.to_elster_xml()
    filename = f"UStVA_{year}_{month:02d}.xml"

    return Response(
        content=xml_content,
        media_type="application/xml",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


# =============================================================================
# EINNAHMEN-UEBERSCHUSS-RECHNUNG (EUER)
# =============================================================================


@router.get(
    "/eur/annual",
    response_model=EURReportSchema,
    summary="Jahres-EUER",
    description="Generiert Einnahmen-Ueberschuss-Rechnung fuer ein Geschaeftsjahr",
)
async def get_annual_eur_report(
    company_id: UUID = Query(..., description="Firmen-ID"),
    fiscal_year: int = Query(..., description="Geschaeftsjahr"),
    include_details: bool = Query(False, description="Einzelposten einbeziehen"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> EURReportSchema:
    """
    Erstellt eine Einnahmen-Ueberschuss-Rechnung (EUER) fuer ein Geschaeftsjahr.

    **Einnahmen-Kategorien:**
    - Warenverkaeufe
    - Dienstleistungen
    - Zinsertraege
    - Sonstige Einnahmen

    **Ausgaben-Kategorien:**
    - Wareneinkauf
    - Personal
    - Miete
    - Versicherungen
    - Fahrzeuge
    - Und weitere...
    """
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
    description="Generiert EUER fuer einen einzelnen Monat",
)
async def get_monthly_eur_report(
    company_id: UUID = Query(..., description="Firmen-ID"),
    year: int = Query(..., description="Jahr"),
    month: int = Query(..., ge=1, le=12, description="Monat (1-12)"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> EURReportSchema:
    """
    Erstellt eine monatliche Einnahmen-Ueberschuss-Rechnung.

    Nuetzlich fuer:
    - Monatliches Controlling
    - Liquiditaetsplanung
    - Trend-Analyse
    """
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
    description="Kumulierte EUER-Daten fuer das laufende Jahr",
)
async def get_ytd_summary(
    company_id: UUID = Query(..., description="Firmen-ID"),
    year: int = Query(..., description="Jahr"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> YTDSummarySchema:
    """
    Zeigt Year-to-Date Zusammenfassung mit monatlicher Aufschluesselung.

    **Enthaelt:**
    - Kumulierte Einnahmen/Ausgaben
    - Durchschnittliche monatliche Werte
    - Monat-fuer-Monat Entwicklung
    """
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
    fiscal_year: int = Query(..., description="Geschaeftsjahr"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Exportiert die EUER als Anlage EUER fuer die Steuererklaerung.

    Die Daten sind nach den offiziellen Zeilen der Anlage EUER strukturiert.
    """
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


# =============================================================================
# STATISTIKEN & DASHBOARD
# =============================================================================


@router.get(
    "/statistics",
    summary="Buchhaltungs-Statistiken",
    description="Aggregierte Kennzahlen fuer Dashboard",
)
async def get_accounting_statistics(
    company_id: UUID = Query(..., description="Firmen-ID"),
    year: Optional[int] = Query(None, description="Jahr (Standard: aktuelles Jahr)"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Liefert aggregierte Buchhaltungs-Kennzahlen fuer das Dashboard.

    **Enthaelt:**
    - Offene Posten Zusammenfassung
    - USt-Status
    - EUER Year-to-Date
    - Trend-Indikatoren
    """
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

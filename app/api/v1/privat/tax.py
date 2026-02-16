# -*- coding: utf-8 -*-
"""
Steuer-Optimierung API Endpunkte für das Privat-Modul.

Stellt Endpunkte bereit für:
- Jahres-Steuerzusammenfassung
- Dokument-Steueranalyse
- Optimierungsvorschläge
- Steuer-Prognose
- ELSTER Export
- Was-waere-wenn Szenarien

SECURITY: NIEMALS persoenliche Finanzdaten loggen!
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, List, Dict

from app.core.types import JSONDict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status, Request
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.api.dependencies import get_db, get_current_active_user
from app.core.rate_limiting import limiter, get_user_identifier
from app.db.models import User, PrivatSpace
from app.core.safe_errors import safe_error_log
from app.services.privat.space_service import PrivatSpaceService
from app.services.privat.tax_optimization_service import (
    get_tax_optimization_service,
    TaxCategory,
    TaxRating,
    ElsterAnlage,
    TaxOptimizationResult,
    TaxProjection,
    WhatIfScenario,
    ElsterExportData,
    DocumentTaxAnalysis,
    AfACalculation,
    TaxAdvancedPayment,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/tax", tags=["privat-tax"])
space_service = PrivatSpaceService()


# =============================================================================
# Pydantic Schemas (Response Models)
# =============================================================================


class TaxDeductionItemSchema(BaseModel):
    """Schema für einen einzelnen Steuerabzugs-Posten."""

    category: str
    description: str
    gross_amount: str
    deductible_amount: str
    document_id: Optional[UUID] = None
    confidence: float
    is_verified: bool
    notes: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class TaxDeductionSummarySchema(BaseModel):
    """Schema für Kategorie-Zusammenfassung."""

    category: str
    category_name: str
    total_gross: str
    total_deductible: str
    max_deductible: Optional[str] = None
    utilization_percent: Optional[float] = None
    item_count: int
    recommendations: List[str]

    model_config = ConfigDict(from_attributes=True)


class TaxDeadlineSchema(BaseModel):
    """Schema für Steuerfristen."""

    deadline_type: str
    title: str
    due_date: str
    description: str
    days_until_due: int
    is_overdue: bool

    model_config = ConfigDict(from_attributes=True)


class TaxYearSummaryResponse(BaseModel):
    """Response für Jahres-Zusammenfassung."""

    space_id: UUID
    tax_year: int
    total_deductible: str
    estimated_tax_savings: str
    optimization_rating: str
    deduction_summaries: List[TaxDeductionSummarySchema]
    upcoming_deadlines: List[TaxDeadlineSchema]
    overdue_deadlines: List[TaxDeadlineSchema]
    optimization_suggestions: List[str]
    missing_deductions: List[str]
    datev_export_ready: bool
    datev_export_notes: Optional[str] = None
    calculated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TaxProjectionResponse(BaseModel):
    """Response für Steuer-Prognose."""

    tax_year: int

    # Einkuenfte
    total_income: str
    income_from_employment: str
    income_from_rental: str
    income_from_capital: str
    other_income: str

    # Abzuege
    total_deductions: str
    werbungskosten: str
    sonderausgaben: str
    aussergewoehnliche_belastungen: str
    haushaltsnahe_abzug: str
    handwerker_abzug: str

    # Steuern
    taxable_income: str
    estimated_income_tax: str
    solidarity_surcharge: str
    church_tax: str
    total_tax: str

    # Vorauszahlungen
    already_paid: str
    expected_refund: str  # Positiv = Erstattung

    # Optimierung
    optimization_potential: str
    unused_allowances: List[str]

    # Metadata
    is_married: bool
    number_of_children: int
    federal_state: str
    calculated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WhatIfScenarioRequest(BaseModel):
    """Request für Was-waere-wenn Szenario."""

    scenario_name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    additional_income: Decimal = Field(default=Decimal("0"), ge=Decimal("-100000"))
    additional_deductions: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    change_marital_status: Optional[bool] = None
    additional_children: int = Field(default=0, ge=0, le=10)


class WhatIfScenarioResponse(BaseModel):
    """Response für Was-waere-wenn Szenario."""

    scenario_name: str
    description: str
    tax_before: str
    tax_after: str
    tax_difference: str
    recommendation: str

    model_config = ConfigDict(from_attributes=True)


class DocumentTaxAnalysisResponse(BaseModel):
    """Response für Dokument-Steueranalyse."""

    document_id: UUID
    document_name: str
    category: str
    category_name: str
    confidence: float
    gross_amount: str
    deductible_amount: str
    potential_savings: str
    elster_anlage: str
    elster_field: str
    suggestions: List[str]
    missing_info: List[str]

    model_config = ConfigDict(from_attributes=True)


class TaxSuggestionResponse(BaseModel):
    """Response für einen Optimierungsvorschlag."""

    title: str
    description: str
    potential_savings: Optional[str] = None
    priority: str
    category: str
    actions: List[str]

    model_config = ConfigDict(from_attributes=True)


class ElsterExportResponse(BaseModel):
    """Response für ELSTER Export."""

    tax_year: int
    is_complete: bool
    missing_fields: List[str]
    validation_warnings: List[str]
    anlagen: Dict[str, bool]
    anlage_n_fields: JSONDict
    anlage_v_fields: JSONDict
    anlage_vorsorge_fields: JSONDict
    anlage_haushaltsnahe_fields: JSONDict
    export_format: str
    generated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ElsterXmlExportRequest(BaseModel):
    """Request für ELSTER XML Export."""

    taxpayer_name: str = Field(..., min_length=1, max_length=100)
    steuernummer: str = Field(..., pattern=r"^\d{2,3}/\d{3}/\d{5}$")


class AfACalculationResponse(BaseModel):
    """Response für AfA-Berechnung."""

    asset_name: str
    asset_type: str
    purchase_date: str
    purchase_price: str
    useful_life_years: int
    afa_rate: float
    annual_depreciation: str
    accumulated_depreciation: str
    remaining_book_value: str
    years_remaining: int
    elster_anlage: str
    elster_field: str

    model_config = ConfigDict(from_attributes=True)


class AdvancePaymentResponse(BaseModel):
    """Response für Vorauszahlungstermin."""

    quarter: int
    due_date: str
    amount_due: str
    is_paid: bool
    is_overdue: bool
    days_until_due: int

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# Helper Functions
# =============================================================================


async def get_user_space_or_403(
    db: AsyncSession,
    space_id: UUID,
    user: User,
) -> PrivatSpace:
    """Prüft ob User Zugriff auf Space hat und gibt Space zurück."""
    # SECURITY: Atomarer TOCTOU-sicherer Check
    space = await space_service.get_with_access_check(
        db, space_id, user.id, "read"
    )

    if space is None:
        # SECURITY: CWE-200 Prevention - keine Info über Existenz
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Space nicht gefunden",
        )

    return space


def _decimal_to_str(value: Decimal) -> str:
    """Konvertiert Decimal zu String für JSON-Serialisierung."""
    return str(value.quantize(Decimal("0.01")))


def _convert_optimization_result(result: TaxOptimizationResult) -> TaxYearSummaryResponse:
    """Konvertiert TaxOptimizationResult zu Response-Schema."""
    summaries = []
    for summary in result.deduction_summaries:
        summaries.append(TaxDeductionSummarySchema(
            category=summary.category.value,
            category_name=summary.category_name,
            total_gross=_decimal_to_str(summary.total_gross),
            total_deductible=_decimal_to_str(summary.total_deductible),
            max_deductible=_decimal_to_str(summary.max_deductible) if summary.max_deductible else None,
            utilization_percent=float(summary.utilization_percent) if summary.utilization_percent else None,
            item_count=len(summary.items),
            recommendations=summary.recommendations,
        ))

    upcoming = [
        TaxDeadlineSchema(
            deadline_type=d.deadline_type.value,
            title=d.title,
            due_date=d.due_date.isoformat(),
            description=d.description,
            days_until_due=d.days_until_due,
            is_overdue=d.is_overdue,
        )
        for d in result.upcoming_deadlines[:5]  # Max 5
    ]

    overdue = [
        TaxDeadlineSchema(
            deadline_type=d.deadline_type.value,
            title=d.title,
            due_date=d.due_date.isoformat(),
            description=d.description,
            days_until_due=d.days_until_due,
            is_overdue=d.is_overdue,
        )
        for d in result.overdue_deadlines[:5]
    ]

    return TaxYearSummaryResponse(
        space_id=result.space_id,
        tax_year=result.tax_year,
        total_deductible=_decimal_to_str(result.total_deductible),
        estimated_tax_savings=_decimal_to_str(result.estimated_tax_savings),
        optimization_rating=result.optimization_rating.value,
        deduction_summaries=summaries,
        upcoming_deadlines=upcoming,
        overdue_deadlines=overdue,
        optimization_suggestions=result.optimization_suggestions,
        missing_deductions=result.missing_deductions,
        datev_export_ready=result.datev_export_ready,
        datev_export_notes=result.datev_export_notes,
        calculated_at=result.calculated_at,
    )


def _convert_projection(projection: TaxProjection) -> TaxProjectionResponse:
    """Konvertiert TaxProjection zu Response-Schema."""
    return TaxProjectionResponse(
        tax_year=projection.tax_year,
        total_income=_decimal_to_str(projection.total_income),
        income_from_employment=_decimal_to_str(projection.income_from_employment),
        income_from_rental=_decimal_to_str(projection.income_from_rental),
        income_from_capital=_decimal_to_str(projection.income_from_capital),
        other_income=_decimal_to_str(projection.other_income),
        total_deductions=_decimal_to_str(projection.total_deductions),
        werbungskosten=_decimal_to_str(projection.werbungskosten),
        sonderausgaben=_decimal_to_str(projection.sonderausgaben),
        aussergewoehnliche_belastungen=_decimal_to_str(projection.aussergewoehnliche_belastungen),
        haushaltsnahe_abzug=_decimal_to_str(projection.haushaltsnahe_abzug),
        handwerker_abzug=_decimal_to_str(projection.handwerker_abzug),
        taxable_income=_decimal_to_str(projection.taxable_income),
        estimated_income_tax=_decimal_to_str(projection.estimated_income_tax),
        solidarity_surcharge=_decimal_to_str(projection.solidarity_surcharge),
        church_tax=_decimal_to_str(projection.church_tax),
        total_tax=_decimal_to_str(projection.total_tax),
        already_paid=_decimal_to_str(projection.already_paid),
        expected_refund=_decimal_to_str(projection.expected_refund),
        optimization_potential=_decimal_to_str(projection.optimization_potential),
        unused_allowances=projection.unused_allowances,
        is_married=projection.is_married,
        number_of_children=projection.number_of_children,
        federal_state=projection.federal_state,
        calculated_at=projection.calculated_at,
    )


# =============================================================================
# API Endpoints
# =============================================================================


@router.get(
    "/summary/{year}",
    response_model=TaxYearSummaryResponse,
    summary="Jahres-Steuerzusammenfassung abrufen",
)
@limiter.limit("30/minute", key_func=get_user_identifier)
async def get_tax_year_summary(
    request: Request,
    year: int,
    space_id: UUID = Query(..., description="Space-ID"),
    estimated_gross_income: Optional[Decimal] = Query(
        None, description="Geschätztes Bruttoeinkommen", ge=Decimal("0")
    ),
    is_married: bool = Query(False, description="Verheiratet (Splittingtarif)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> TaxYearSummaryResponse:
    """
    Ruft die Jahres-Steuerzusammenfassung für ein Steuerjahr ab.

    Analysiert alle steuerlich relevanten Dokumente und berechnet:
    - Abzuege nach Kategorie (Werbungskosten, Sonderausgaben, etc.)
    - Geschätzte Steuerersparnis
    - Optimierungsvorschläge
    - Anstehende Fristen

    Args:
        year: Steuerjahr (z.B. 2024, 2025, 2026)
        space_id: ID des Privat-Space
        estimated_gross_income: Optionales Bruttoeinkommen für Ersparnisberechnung
        is_married: Verheiratet für Splittingtarif

    Returns:
        TaxYearSummaryResponse mit vollständiger Analyse
    """
    await get_user_space_or_403(db, space_id, current_user)

    # Validiere Jahr
    current_year = datetime.now(timezone.utc).year
    if year < 2020 or year > current_year + 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Steuerjahr muss zwischen 2020 und {current_year + 1} liegen",
        )

    try:
        service = get_tax_optimization_service()
        result = await service.analyze_tax_optimization(
            db=db,
            space_id=space_id,
            tax_year=year,
            estimated_gross_income=estimated_gross_income,
            is_married=is_married,
        )

        logger.info(
            "tax_year_summary_retrieved",
            space_id=str(space_id),
            year=year,
            user_id=str(current_user.id),
        )

        return _convert_optimization_result(result)

    except Exception as e:
        logger.error(
            "tax_year_summary_error",
            space_id=str(space_id),
            year=year,
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler bei der Steuerberechnung",
        )


@router.get(
    "/document/{document_id}/analysis",
    response_model=DocumentTaxAnalysisResponse,
    summary="Dokument-Steueranalyse abrufen",
)
@limiter.limit("60/minute", key_func=get_user_identifier)
async def get_document_tax_analysis(
    request: Request,
    document_id: UUID,
    space_id: UUID = Query(..., description="Space-ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> DocumentTaxAnalysisResponse:
    """
    Analysiert ein einzelnes Dokument auf steuerliche Relevanz.

    Bestimmt:
    - Steuer-Kategorie (Werbungskosten, Sonderausgaben, etc.)
    - Abzugsfaehigen Betrag
    - Potenzielle Ersparnis
    - ELSTER-Zuordnung (Anlage N, V, etc.)
    - Optimierungsempfehlungen

    Args:
        document_id: ID des zu analysierenden Dokuments
        space_id: ID des Privat-Space

    Returns:
        DocumentTaxAnalysisResponse mit Analyse-Ergebnis
    """
    await get_user_space_or_403(db, space_id, current_user)

    try:
        service = get_tax_optimization_service()
        analysis = await service.analyze_document_for_tax(
            db=db,
            document_id=document_id,
            space_id=space_id,
        )

        return DocumentTaxAnalysisResponse(
            document_id=analysis.document_id,
            document_name=analysis.document_name,
            category=analysis.category.value,
            category_name=analysis.category_name,
            confidence=float(analysis.confidence),
            gross_amount=_decimal_to_str(analysis.gross_amount),
            deductible_amount=_decimal_to_str(analysis.deductible_amount),
            potential_savings=_decimal_to_str(analysis.potential_savings),
            elster_anlage=analysis.elster_anlage.value,
            elster_field=analysis.elster_field,
            suggestions=analysis.suggestions,
            missing_info=analysis.missing_info,
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.error(
            "document_tax_analysis_error",
            document_id=str(document_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler bei der Dokumentanalyse",
        )


@router.get(
    "/suggestions",
    response_model=List[TaxSuggestionResponse],
    summary="Personalisierte Optimierungsvorschläge abrufen",
)
@limiter.limit("30/minute", key_func=get_user_identifier)
async def get_tax_suggestions(
    request: Request,
    space_id: UUID = Query(..., description="Space-ID"),
    year: Optional[int] = Query(None, description="Steuerjahr"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> List[TaxSuggestionResponse]:
    """
    Holt personalisierte Steuer-Optimierungsvorschläge.

    Analysiert die vorhandenen Daten und generiert spezifische
    Empfehlungen mit geschätztem Sparpotenzial.

    Beispiele:
    - "Sie könnten noch 1.500 EUR haushaltsnahe DL absetzen"
    - "Ihre Werbungskosten liegen unter der Pauschale"
    - "Handwerkerleistungen nicht ausgeschoepft"

    Args:
        space_id: ID des Privat-Space
        year: Optionales Steuerjahr (Default: aktuelles Jahr)

    Returns:
        Liste von TaxSuggestionResponse mit Empfehlungen
    """
    await get_user_space_or_403(db, space_id, current_user)

    try:
        service = get_tax_optimization_service()
        suggestions = await service.get_personalized_suggestions(
            db=db,
            space_id=space_id,
            tax_year=year,
        )

        return [
            TaxSuggestionResponse(
                title=s["title"],
                description=s["description"],
                potential_savings=_decimal_to_str(s["potential_savings"]) if s.get("potential_savings") else None,
                priority=s["priority"],
                category=s["category"],
                actions=s["actions"],
            )
            for s in suggestions
        ]

    except Exception as e:
        logger.error(
            "tax_suggestions_error",
            space_id=str(space_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Abrufen der Vorschläge",
        )


@router.get(
    "/projection/{year}",
    response_model=TaxProjectionResponse,
    summary="Steuer-Prognose berechnen",
)
@limiter.limit("20/minute", key_func=get_user_identifier)
async def get_tax_projection(
    request: Request,
    year: int,
    space_id: UUID = Query(..., description="Space-ID"),
    gross_income: Decimal = Query(..., description="Bruttoeinkommen", ge=Decimal("0")),
    is_married: bool = Query(False, description="Verheiratet"),
    number_of_children: int = Query(0, description="Anzahl Kinder", ge=0, le=10),
    federal_state: str = Query("default", description="Bundesland (2-Buchstaben-Code)"),
    already_paid: Decimal = Query(
        Decimal("0"), description="Bereits gezahlte Vorauszahlungen", ge=Decimal("0")
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> TaxProjectionResponse:
    """
    Berechnet eine vollständige Steuer-Prognose.

    Ermittelt:
    - Geschätzte Einkommensteuer
    - Solidaritaetszuschlag
    - Kirchensteuer
    - Erwartete Erstattung/Nachzahlung
    - Nicht genutzte Freibetraege
    - Optimierungspotenzial

    Args:
        year: Steuerjahr
        space_id: ID des Privat-Space
        gross_income: Jahres-Bruttoeinkommen
        is_married: Verheiratet (Splittingtarif)
        number_of_children: Anzahl Kinder für Kinderfreibetrag
        federal_state: Bundesland für Kirchensteuer (z.B. "BY", "NW")
        already_paid: Bereits gezahlte Vorauszahlungen

    Returns:
        TaxProjectionResponse mit vollständiger Prognose
    """
    await get_user_space_or_403(db, space_id, current_user)

    # Bundesland validieren
    valid_states = ["BW", "BY", "BE", "BB", "HB", "HH", "HE", "MV",
                    "NI", "NW", "RP", "SL", "SN", "ST", "SH", "TH", "default"]
    if federal_state.upper() not in valid_states:
        federal_state = "default"

    try:
        service = get_tax_optimization_service()
        projection = await service.calculate_tax_projection(
            db=db,
            space_id=space_id,
            tax_year=year,
            gross_income=gross_income,
            is_married=is_married,
            number_of_children=number_of_children,
            federal_state=federal_state.upper(),
            already_paid=already_paid,
        )

        return _convert_projection(projection)

    except Exception as e:
        logger.error(
            "tax_projection_error",
            space_id=str(space_id),
            year=year,
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler bei der Steuer-Prognose",
        )


@router.post(
    "/projection/{year}/what-if",
    response_model=WhatIfScenarioResponse,
    summary="Was-waere-wenn Szenario berechnen",
)
@limiter.limit("20/minute", key_func=get_user_identifier)
async def calculate_what_if_scenario(
    request: Request,
    year: int,
    scenario: WhatIfScenarioRequest,
    space_id: UUID = Query(..., description="Space-ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> WhatIfScenarioResponse:
    """
    Berechnet ein Was-waere-wenn Szenario.

    Simuliert Steuerauswirkungen von Änderungen wie:
    - Gehaltserhöhung
    - Zusätzliche Werbungskosten
    - Heirat
    - Kinder

    Args:
        year: Steuerjahr
        scenario: Szenario-Parameter
        space_id: ID des Privat-Space

    Returns:
        WhatIfScenarioResponse mit Vergleich vorher/nachher
    """
    await get_user_space_or_403(db, space_id, current_user)

    try:
        service = get_tax_optimization_service()

        what_if = WhatIfScenario(
            scenario_name=scenario.scenario_name,
            description=scenario.description or "",
            additional_income=scenario.additional_income,
            additional_deductions=scenario.additional_deductions,
            change_marital_status=scenario.change_marital_status,
            additional_children=scenario.additional_children,
        )

        result = await service.calculate_what_if_scenario(
            db=db,
            space_id=space_id,
            scenario=what_if,
        )

        return WhatIfScenarioResponse(
            scenario_name=result.scenario_name,
            description=result.description,
            tax_before=_decimal_to_str(result.tax_before),
            tax_after=_decimal_to_str(result.tax_after),
            tax_difference=_decimal_to_str(result.tax_difference),
            recommendation=result.recommendation,
        )

    except Exception as e:
        logger.error(
            "what_if_scenario_error",
            space_id=str(space_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler bei der Szenario-Berechnung",
        )


@router.get(
    "/projection/{year}/scenarios",
    response_model=List[WhatIfScenarioResponse],
    summary="Gaengige Szenarien berechnen",
)
@limiter.limit("10/minute", key_func=get_user_identifier)
async def get_common_scenarios(
    request: Request,
    year: int,
    space_id: UUID = Query(..., description="Space-ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> List[WhatIfScenarioResponse]:
    """
    Berechnet gaengige Was-waere-wenn Szenarien automatisch.

    Liefert Empfehlungen wie:
    - Steuerersparnis bei Heirat
    - Auswirkung von mehr Werbungskosten
    - Haushaltsnahe Dienstleistungen maximieren
    - Handwerkerleistungen ausschoepfen

    Args:
        year: Steuerjahr
        space_id: ID des Privat-Space

    Returns:
        Liste von WhatIfScenarioResponse
    """
    await get_user_space_or_403(db, space_id, current_user)

    try:
        service = get_tax_optimization_service()
        scenarios = await service.calculate_common_scenarios(
            db=db,
            space_id=space_id,
        )

        return [
            WhatIfScenarioResponse(
                scenario_name=s.scenario_name,
                description=s.description,
                tax_before=_decimal_to_str(s.tax_before),
                tax_after=_decimal_to_str(s.tax_after),
                tax_difference=_decimal_to_str(s.tax_difference),
                recommendation=s.recommendation,
            )
            for s in scenarios
        ]

    except Exception as e:
        logger.error(
            "common_scenarios_error",
            space_id=str(space_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Berechnen der Szenarien",
        )


@router.get(
    "/elster-export/{year}",
    response_model=ElsterExportResponse,
    summary="ELSTER Export vorbereiten",
)
@limiter.limit("10/minute", key_func=get_user_identifier)
async def prepare_elster_export(
    request: Request,
    year: int,
    space_id: UUID = Query(..., description="Space-ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ElsterExportResponse:
    """
    Bereitet Daten für ELSTER-Export vor.

    Erzeugt strukturierte Daten für:
    - Anlage N (Arbeitnehmereinkuenfte)
    - Anlage V (Vermietung und Verpachtung)
    - Anlage Vorsorge (Vorsorgeaufwendungen)
    - Haushaltsnahe Dienstleistungen

    Validiert Vollständigkeit und zeigt fehlende Felder an.

    Args:
        year: Steuerjahr
        space_id: ID des Privat-Space

    Returns:
        ElsterExportResponse mit Feldwerten und Validierung
    """
    await get_user_space_or_403(db, space_id, current_user)

    try:
        service = get_tax_optimization_service()
        export_data = await service.prepare_elster_export(
            db=db,
            space_id=space_id,
            tax_year=year,
        )

        return ElsterExportResponse(
            tax_year=export_data.tax_year,
            is_complete=export_data.is_complete,
            missing_fields=export_data.missing_fields,
            validation_warnings=export_data.validation_warnings,
            anlagen={k.value: v for k, v in export_data.anlagen.items()},
            anlage_n_fields={k: str(v) for k, v in export_data.anlage_n_fields.items()},
            anlage_v_fields={k: str(v) for k, v in export_data.anlage_v_fields.items()},
            anlage_vorsorge_fields={k: str(v) for k, v in export_data.anlage_vorsorge_fields.items()},
            anlage_haushaltsnahe_fields={k: str(v) for k, v in export_data.anlage_haushaltsnahe_fields.items()},
            export_format=export_data.export_format,
            generated_at=export_data.generated_at,
        )

    except Exception as e:
        logger.error(
            "elster_export_error",
            space_id=str(space_id),
            year=year,
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim ELSTER-Export",
        )


@router.post(
    "/elster-export/{year}/xml",
    response_model=Dict[str, str],
    summary="ELSTER XML generieren",
)
@limiter.limit("5/minute", key_func=get_user_identifier)
async def generate_elster_xml(
    request: Request,
    year: int,
    export_request: ElsterXmlExportRequest,
    space_id: UUID = Query(..., description="Space-ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, str]:
    """
    Generiert ELSTER-kompatibles XML für die Steuererklärung.

    HINWEIS: Dies ist ein vereinfachtes Format für die Vorschau.
    Für die echte ELSTER-Übertragung ist die offizielle
    ERiC-Bibliothek des Finanzamts erforderlich.

    SECURITY: Die Steuernummer wird NICHT gespeichert!

    Args:
        year: Steuerjahr
        export_request: Steuerzahler-Informationen
        space_id: ID des Privat-Space

    Returns:
        Dict mit "xml" Schluessel und XML-Inhalt
    """
    await get_user_space_or_403(db, space_id, current_user)

    try:
        service = get_tax_optimization_service()

        # Export-Daten vorbereiten
        export_data = await service.prepare_elster_export(
            db=db,
            space_id=space_id,
            tax_year=year,
        )

        # XML generieren
        taxpayer_info = {
            "name": export_request.taxpayer_name,
            "steuernummer": export_request.steuernummer,
        }

        xml_content = service.generate_elster_xml(export_data, taxpayer_info)

        logger.info(
            "elster_xml_generated",
            space_id=str(space_id),
            year=year,
            user_id=str(current_user.id),
        )

        return {"xml": xml_content}

    except Exception as e:
        logger.error(
            "elster_xml_error",
            space_id=str(space_id),
            year=year,
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Generieren des ELSTER-XML",
        )


@router.get(
    "/afa/{year}",
    response_model=List[AfACalculationResponse],
    summary="AfA-Berechnungen abrufen",
)
@limiter.limit("30/minute", key_func=get_user_identifier)
async def get_afa_calculations(
    request: Request,
    year: int,
    space_id: UUID = Query(..., description="Space-ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> List[AfACalculationResponse]:
    """
    Ruft AfA-Berechnungen (Abschreibungen) für vermietete Immobilien ab.

    Berechnet für jede Immobilie:
    - Jährliche Abschreibung
    - Kumulierte Abschreibung
    - Restbuchwert
    - Verbleibende Nutzungsdauer

    Args:
        year: Steuerjahr
        space_id: ID des Privat-Space

    Returns:
        Liste von AfACalculationResponse
    """
    await get_user_space_or_403(db, space_id, current_user)

    try:
        service = get_tax_optimization_service()
        calculations = await service.calculate_afa_for_properties(
            db=db,
            space_id=space_id,
            tax_year=year,
        )

        return [
            AfACalculationResponse(
                asset_name=calc.asset_name,
                asset_type=calc.asset_type,
                purchase_date=calc.purchase_date.isoformat(),
                purchase_price=_decimal_to_str(calc.purchase_price),
                useful_life_years=calc.useful_life_years,
                afa_rate=float(calc.afa_rate),
                annual_depreciation=_decimal_to_str(calc.annual_depreciation),
                accumulated_depreciation=_decimal_to_str(calc.accumulated_depreciation),
                remaining_book_value=_decimal_to_str(calc.remaining_book_value),
                years_remaining=calc.years_remaining,
                elster_anlage=calc.elster_anlage.value,
                elster_field=calc.elster_field,
            )
            for calc in calculations
        ]

    except Exception as e:
        logger.error(
            "afa_calculations_error",
            space_id=str(space_id),
            year=year,
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler bei den AfA-Berechnungen",
        )


@router.get(
    "/advance-payments/{year}",
    response_model=List[AdvancePaymentResponse],
    summary="Vorauszahlungs-Termine abrufen",
)
@limiter.limit("30/minute", key_func=get_user_identifier)
async def get_advance_payments(
    request: Request,
    year: int,
    quarterly_amount: Decimal = Query(..., description="Vierteljahresbetrag", ge=Decimal("0")),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> List[AdvancePaymentResponse]:
    """
    Ruft die Vorauszahlungs-Termine für ein Steuerjahr ab.

    Zeigt:
    - Fälligkeitstermine (10. Maerz, Juni, September, Dezember)
    - Fällige Betraege
    - Überfällige Zahlungen

    Args:
        year: Steuerjahr
        quarterly_amount: Vierteljahresbetrag der Vorauszahlung

    Returns:
        Liste von AdvancePaymentResponse
    """
    service = get_tax_optimization_service()
    payments = service.get_advance_payment_schedule(
        tax_year=year,
        quarterly_amount=quarterly_amount,
    )

    return [
        AdvancePaymentResponse(
            quarter=p.quarter,
            due_date=p.due_date.isoformat(),
            amount_due=_decimal_to_str(p.amount_due),
            is_paid=p.is_paid,
            is_overdue=p.is_overdue,
            days_until_due=p.days_until_due,
        )
        for p in payments
    ]

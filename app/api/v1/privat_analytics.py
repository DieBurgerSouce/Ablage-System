# -*- coding: utf-8 -*-
"""
Enterprise Analytics API Router fuer Privat-Modul.

Stellt Endpunkte fuer:
- Immobilien-KPIs (Mietrendite, ROI)
- Fahrzeug-TCO (Total Cost of Ownership)
- Versicherungs-Analyse (Deckungsluecken)
- Kredit-Tilgungsplaene
- Finanz-Trends und Prognosen
- NER und Deadline-Extraktion
"""

import uuid
from datetime import date, datetime

from app.core.datetime_utils import utc_now
from decimal import Decimal
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Depends, status, Query, Request, BackgroundTasks
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.api.dependencies import get_db, get_current_active_user
from app.core.rate_limiting import limiter, get_user_identifier
from app.core.safe_errors import safe_error_detail, safe_error_log
from app.db.models import User
from app.db.schemas import PrivatAccessLevel

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/privat/analytics", tags=["privat-analytics"])


# ==================== Response Models ====================


class PropertyKPIResponse(BaseModel):
    """Immobilien-KPI Antwort."""
    property_id: uuid.UUID
    property_name: str
    rental_yield_percent: Optional[float] = Field(None, description="Bruttomietrendite in %")
    net_yield_percent: Optional[float] = Field(None, description="Nettomietrendite in %")
    roi_percent: Optional[float] = Field(None, description="Return on Investment in %")
    current_value: Optional[float] = Field(None, description="Aktueller Schaetzwert")
    value_appreciation_percent: Optional[float] = Field(None, description="Wertsteigerung in %")
    total_costs_ytd: Optional[float] = Field(None, description="Nebenkosten YTD")
    calculated_at: datetime


class VehicleTCOResponse(BaseModel):
    """Fahrzeug-TCO Antwort."""
    vehicle_id: uuid.UUID
    brand: str
    model: str
    cost_per_km: Optional[float] = Field(None, description="Kosten pro km")
    monthly_depreciation: Optional[float] = Field(None, description="Monatl. Wertverlust")
    current_estimated_value: Optional[float] = Field(None, description="Aktueller Schaetzwert")
    next_service_date: Optional[date] = Field(None, description="Naechster Service")
    next_service_km: Optional[int] = Field(None, description="Naechster Service bei km")
    total_cost_breakdown: Optional[dict] = Field(None, description="Kostenaufschluesselung")
    calculated_at: datetime


class InsuranceCoverageGap(BaseModel):
    """Einzelne Deckungsluecke."""
    insurance_type: str
    recommended_coverage: float
    current_coverage: float
    gap_amount: float
    severity: str = Field(..., description="low, medium, high, critical")
    recommendation: str


class InsuranceAnalysisResponse(BaseModel):
    """Versicherungs-Analyse Antwort."""
    space_id: uuid.UUID
    total_insurances: int
    gaps: List[InsuranceCoverageGap]
    cancellation_deadlines: List[dict]
    monthly_premium_total: float
    coverage_score: float = Field(..., ge=0, le=100, description="Deckungsqualitaet 0-100")
    analyzed_at: datetime


class LoanPayment(BaseModel):
    """Einzelne Tilgungsrate."""
    payment_number: int
    date: date
    principal: float
    interest: float
    total_payment: float
    remaining_balance: float


class LoanAmortizationResponse(BaseModel):
    """Tilgungsplan Antwort."""
    loan_id: uuid.UUID
    loan_name: str
    principal_amount: float
    interest_rate: float
    monthly_payment: float
    total_interest: float
    payoff_date: Optional[date]
    payments: List[LoanPayment]
    extra_payment_savings: Optional[dict] = Field(None, description="Ersparnis bei Sondertilgung")
    generated_at: datetime


class MonthlyTrendData(BaseModel):
    """Monatliche Trenddaten."""
    month: str
    income: float
    expenses: float
    net: float
    savings_rate: Optional[float] = None


class RecurringPaymentData(BaseModel):
    """Erkannte wiederkehrende Zahlung."""
    name: str
    amount: float
    frequency: str  # monthly, quarterly, yearly
    expected_day: Optional[int] = None
    category: str
    confidence: float


class CashFlowPrediction(BaseModel):
    """Cash-Flow Prognose."""
    month: str
    predicted_income: float
    predicted_expenses: float
    predicted_net: float
    confidence: float


class FinanceAnalyticsResponse(BaseModel):
    """Umfassende Finanzanalyse."""
    space_id: uuid.UUID
    net_worth: float
    current_monthly_net: float
    monthly_trends: List[MonthlyTrendData]
    yoy_comparison: Optional[dict] = None
    recurring_payments: List[RecurringPaymentData]
    cash_flow_predictions: List[CashFlowPrediction]
    trend_direction: str  # up, down, stable
    analyzed_at: datetime


class ExtractedEntity(BaseModel):
    """Extrahierte Entitaet aus NER."""
    entity_type: str
    value: str
    confidence: float
    context: Optional[str] = None


class NERExtractionResponse(BaseModel):
    """NER Extraktions-Antwort."""
    document_id: uuid.UUID
    entities: List[ExtractedEntity]
    processing_time_ms: int
    from_cache: bool


class ExtractedDeadline(BaseModel):
    """Extrahierte Frist."""
    title: str
    due_date: Optional[date]
    deadline_type: str
    original_text: str
    confidence: float
    auto_created: bool = False


class DeadlineExtractionResponse(BaseModel):
    """Deadline Extraktions-Antwort."""
    document_id: uuid.UUID
    deadlines: List[ExtractedDeadline]
    created_count: int
    processing_time_ms: int


class TaskTriggerResponse(BaseModel):
    """Antwort beim Triggern eines Background Tasks."""
    task_id: str
    status: str = "queued"
    message: str


# ==================== Helper Functions ====================


async def get_user_space_or_403(
    db: AsyncSession,
    space_id: uuid.UUID,
    user: User,
    required_level: PrivatAccessLevel = PrivatAccessLevel.READ,
):
    """Prueft ob User Zugriff auf Space hat."""
    from app.services.privat import PrivatSpaceService
    space_service = PrivatSpaceService()

    space = await space_service.get_with_access_check(
        db, space_id, user.id, required_level.value if hasattr(required_level, 'value') else required_level
    )

    if space is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Space nicht gefunden",
        )

    return space


# ==================== Property KPIs ====================


@router.get(
    "/properties/{property_id}/kpis",
    response_model=PropertyKPIResponse,
    summary="Immobilien-KPIs abrufen",
)
@limiter.limit("30/minute", key_func=get_user_identifier)
async def get_property_kpis(
    request: Request,
    property_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PropertyKPIResponse:
    """
    Berechnet KPIs fuer eine Immobilie:
    - Brutto-/Nettomietrendite
    - ROI inkl. Wertsteigerung
    - Nebenkostentrend
    """
    from app.services.privat import get_property_calculation_service, PrivatPropertyService

    property_service = PrivatPropertyService()
    prop = await property_service.get_by_id(db, property_id)

    if not prop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Immobilie nicht gefunden",
        )

    # Pruefe Space-Zugriff
    await get_user_space_or_403(db, prop.space_id, current_user, PrivatAccessLevel.READ)

    calc_service = get_property_calculation_service(db)

    # Mietrendite berechnen
    yield_result = await calc_service.calculate_rental_yield(property_id)

    # ROI berechnen
    roi_result = await calc_service.calculate_roi(property_id)

    return PropertyKPIResponse(
        property_id=property_id,
        property_name=prop.name,
        rental_yield_percent=yield_result.rental_yield_percent if yield_result else None,
        net_yield_percent=yield_result.net_yield_percent if yield_result else None,
        roi_percent=roi_result.total_roi_percent if roi_result else None,
        current_value=roi_result.current_value if roi_result else None,
        value_appreciation_percent=roi_result.value_appreciation_percent if roi_result else None,
        total_costs_ytd=yield_result.annual_costs if yield_result else None,
        calculated_at=utc_now(),
    )


@router.post(
    "/spaces/{space_id}/properties/calculate-all",
    response_model=TaskTriggerResponse,
    summary="Alle Immobilien-KPIs eines Spaces berechnen",
)
@limiter.limit("5/minute", key_func=get_user_identifier)
async def trigger_property_kpi_calculation(
    request: Request,
    space_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> TaskTriggerResponse:
    """Triggert Hintergrund-Berechnung aller Immobilien-KPIs."""
    await get_user_space_or_403(db, space_id, current_user, PrivatAccessLevel.READ)

    from app.workers.tasks.privat_tasks import calculate_property_kpis

    task = calculate_property_kpis.delay(space_id=str(space_id))

    return TaskTriggerResponse(
        task_id=task.id,
        status="queued",
        message="KPI-Berechnung fuer alle Immobilien gestartet",
    )


# ==================== Vehicle TCO ====================


@router.get(
    "/vehicles/{vehicle_id}/tco",
    response_model=VehicleTCOResponse,
    summary="Fahrzeug-TCO abrufen",
)
@limiter.limit("30/minute", key_func=get_user_identifier)
async def get_vehicle_tco(
    request: Request,
    vehicle_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> VehicleTCOResponse:
    """
    Berechnet Total Cost of Ownership fuer ein Fahrzeug:
    - Kosten pro km
    - Abschreibung
    - Naechster Service
    """
    from app.services.privat import get_vehicle_calculation_service, PrivatVehicleService

    vehicle_service = PrivatVehicleService()
    vehicle = await vehicle_service.get_by_id(db, vehicle_id)

    if not vehicle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Fahrzeug nicht gefunden",
        )

    await get_user_space_or_403(db, vehicle.space_id, current_user, PrivatAccessLevel.READ)

    calc_service = get_vehicle_calculation_service(db)

    tco = await calc_service.calculate_tco(vehicle_id)
    depreciation = await calc_service.calculate_depreciation(vehicle_id)
    next_service = await calc_service.predict_next_service(vehicle_id)

    return VehicleTCOResponse(
        vehicle_id=vehicle_id,
        brand=vehicle.brand,
        model=vehicle.model,
        cost_per_km=tco.cost_per_km if tco else None,
        monthly_depreciation=depreciation.monthly_depreciation if depreciation else None,
        current_estimated_value=depreciation.current_value if depreciation else None,
        next_service_date=next_service.predicted_date if next_service else None,
        next_service_km=next_service.predicted_km if next_service else None,
        total_cost_breakdown=tco.breakdown if tco else None,
        calculated_at=utc_now(),
    )


@router.post(
    "/spaces/{space_id}/vehicles/calculate-all",
    response_model=TaskTriggerResponse,
    summary="Alle Fahrzeug-TCOs eines Spaces berechnen",
)
@limiter.limit("5/minute", key_func=get_user_identifier)
async def trigger_vehicle_tco_calculation(
    request: Request,
    space_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> TaskTriggerResponse:
    """Triggert Hintergrund-Berechnung aller Fahrzeug-TCOs."""
    await get_user_space_or_403(db, space_id, current_user, PrivatAccessLevel.READ)

    from app.workers.tasks.privat_tasks import calculate_vehicle_tco

    task = calculate_vehicle_tco.delay(space_id=str(space_id))

    return TaskTriggerResponse(
        task_id=task.id,
        status="queued",
        message="TCO-Berechnung fuer alle Fahrzeuge gestartet",
    )


# ==================== Insurance Analysis ====================


@router.get(
    "/spaces/{space_id}/insurances/analysis",
    response_model=InsuranceAnalysisResponse,
    summary="Versicherungs-Analyse abrufen",
)
@limiter.limit("30/minute", key_func=get_user_identifier)
async def get_insurance_analysis(
    request: Request,
    space_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> InsuranceAnalysisResponse:
    """
    Analysiert Versicherungsdeckung:
    - Identifiziert Deckungsluecken
    - Berechnet Kuendigungsfristen
    - Gesamtpraemien-Uebersicht
    """
    await get_user_space_or_403(db, space_id, current_user, PrivatAccessLevel.READ)

    from app.services.privat import get_insurance_analysis_service

    analysis_service = get_insurance_analysis_service(db)

    gap_analysis = await analysis_service.analyze_coverage_gaps(space_id)
    deadlines = await analysis_service.calculate_cancellation_deadlines(space_id)

    gaps = []
    if gap_analysis:
        for gap in gap_analysis.gaps:
            gaps.append(InsuranceCoverageGap(
                insurance_type=gap.insurance_type,
                recommended_coverage=gap.recommended_coverage,
                current_coverage=gap.current_coverage,
                gap_amount=gap.gap_amount,
                severity=gap.severity,
                recommendation=gap.recommendation,
            ))

    return InsuranceAnalysisResponse(
        space_id=space_id,
        total_insurances=gap_analysis.total_insurances if gap_analysis else 0,
        gaps=gaps,
        cancellation_deadlines=[
            {"insurance_id": str(d.insurance_id), "deadline": d.deadline.isoformat(), "name": d.name}
            for d in (deadlines or [])
        ],
        monthly_premium_total=gap_analysis.monthly_premium_total if gap_analysis else 0,
        coverage_score=gap_analysis.coverage_score if gap_analysis else 0,
        analyzed_at=utc_now(),
    )


# ==================== Loan Amortization ====================


@router.get(
    "/loans/{loan_id}/amortization",
    response_model=LoanAmortizationResponse,
    summary="Tilgungsplan abrufen",
)
@limiter.limit("30/minute", key_func=get_user_identifier)
async def get_loan_amortization(
    request: Request,
    loan_id: uuid.UUID,
    extra_payment: Optional[float] = Query(None, gt=0, le=1000000, description="Optionale Sondertilgung in EUR"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> LoanAmortizationResponse:
    """
    Generiert Tilgungsplan fuer einen Kredit:
    - Monatliche Raten mit Zins-/Tilgungsaufteilung
    - Voraussichtliches Auszahlungsdatum
    - Optional: Zinsersparnis bei Sondertilgung
    """
    from app.services.privat import get_loan_amortization_service, PrivatLoanService

    loan_service = PrivatLoanService()
    loan = await loan_service.get_by_id(db, loan_id)

    if not loan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kredit nicht gefunden",
        )

    await get_user_space_or_403(db, loan.space_id, current_user, PrivatAccessLevel.READ)

    amort_service = get_loan_amortization_service(db)

    schedule = await amort_service.generate_amortization_schedule(loan_id)
    payoff = await amort_service.calculate_payoff_date(loan_id)

    extra_savings = None
    if extra_payment and extra_payment > 0:
        savings = await amort_service.calculate_interest_saved(loan_id, extra_payment)
        if savings:
            extra_savings = {
                "extra_payment": extra_payment,
                "interest_saved": float(savings.interest_saved),
                "months_saved": savings.months_saved,
                "new_payoff_date": savings.new_payoff_date.isoformat() if savings.new_payoff_date else None,
            }

    payments = []
    if schedule:
        for p in schedule.payments[:60]:  # Max 5 Jahre anzeigen
            payments.append(LoanPayment(
                payment_number=p.payment_number,
                date=p.date,
                principal=float(p.principal),
                interest=float(p.interest),
                total_payment=float(p.total_payment),
                remaining_balance=float(p.remaining_balance),
            ))

    return LoanAmortizationResponse(
        loan_id=loan_id,
        loan_name=loan.name,
        principal_amount=float(loan.principal_amount) if loan.principal_amount else 0,
        interest_rate=float(loan.interest_rate) if loan.interest_rate else 0,
        monthly_payment=float(schedule.monthly_payment) if schedule else 0,
        total_interest=float(schedule.total_interest) if schedule else 0,
        payoff_date=payoff.payoff_date if payoff else None,
        payments=payments,
        extra_payment_savings=extra_savings,
        generated_at=utc_now(),
    )


# ==================== Finance Analytics ====================


@router.get(
    "/spaces/{space_id}/finance/analytics",
    response_model=FinanceAnalyticsResponse,
    summary="Finanz-Analyse abrufen",
)
@limiter.limit("20/minute", key_func=get_user_identifier)
async def get_finance_analytics(
    request: Request,
    space_id: uuid.UUID,
    months: int = Query(12, ge=3, le=36, description="Analysezeitraum in Monaten"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> FinanceAnalyticsResponse:
    """
    Umfassende Finanzanalyse:
    - Monats-Trends (Einnahmen, Ausgaben, Netto)
    - YoY-Vergleich
    - Erkannte wiederkehrende Zahlungen
    - Cash-Flow-Prognosen
    """
    await get_user_space_or_403(db, space_id, current_user, PrivatAccessLevel.READ)

    from app.services.privat import get_finance_analytics_service

    analytics_service = get_finance_analytics_service(db)

    analysis = await analytics_service.get_full_analysis(space_id)

    if not analysis:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Keine Finanzdaten gefunden",
        )

    monthly_trends = [
        MonthlyTrendData(
            month=t.month,
            income=t.income,
            expenses=t.expenses,
            net=t.net,
            savings_rate=t.savings_rate,
        )
        for t in (analysis.monthly_trends or [])
    ]

    recurring = [
        RecurringPaymentData(
            name=r.name,
            amount=r.amount,
            frequency=r.frequency,
            expected_day=r.expected_day,
            category=r.category,
            confidence=r.confidence,
        )
        for r in (analysis.recurring_payments or [])
    ]

    predictions = [
        CashFlowPrediction(
            month=p.month,
            predicted_income=p.predicted_income,
            predicted_expenses=p.predicted_expenses,
            predicted_net=p.predicted_net,
            confidence=p.confidence,
        )
        for p in (analysis.predictions or [])
    ]

    return FinanceAnalyticsResponse(
        space_id=space_id,
        net_worth=analysis.net_worth,
        current_monthly_net=analysis.current_monthly_net,
        monthly_trends=monthly_trends,
        yoy_comparison=analysis.yoy_comparison,
        recurring_payments=recurring,
        cash_flow_predictions=predictions,
        trend_direction=analysis.trend_direction,
        analyzed_at=utc_now(),
    )


@router.post(
    "/spaces/{space_id}/finance/analyze",
    response_model=TaskTriggerResponse,
    summary="Finanz-Analyse starten",
)
@limiter.limit("5/minute", key_func=get_user_identifier)
async def trigger_finance_analysis(
    request: Request,
    space_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> TaskTriggerResponse:
    """Triggert umfassende Finanzanalyse im Hintergrund."""
    await get_user_space_or_403(db, space_id, current_user, PrivatAccessLevel.READ)

    from app.workers.tasks.privat_tasks import run_finance_analytics

    task = run_finance_analytics.delay(space_id=str(space_id))

    return TaskTriggerResponse(
        task_id=task.id,
        status="queued",
        message="Finanz-Analyse gestartet",
    )


# ==================== NER & Deadline Extraction ====================


@router.post(
    "/documents/{document_id}/extract-entities",
    response_model=NERExtractionResponse,
    summary="Entitaeten aus Dokument extrahieren",
)
@limiter.limit("10/minute", key_func=get_user_identifier)
async def extract_document_entities(
    request: Request,
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> NERExtractionResponse:
    """
    Extrahiert Entitaeten aus Dokumenttext mittels LLM-NER:
    - Fristen und Termine
    - Geldbetraege
    - Firmen und Personen
    - Vertragsnummern, IBAN, etc.
    """
    from app.db.models import Document
    from sqlalchemy import select

    result = await db.execute(select(Document).where(Document.id == document_id))
    doc = result.scalar_one_or_none()

    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dokument nicht gefunden",
        )

    # Pruefe ob User Zugriff hat
    if doc.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Kein Zugriff auf dieses Dokument",
        )

    if not doc.extracted_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Kein OCR-Text vorhanden",
        )

    from app.services.document_intelligence import get_llm_ner_service

    ner_service = get_llm_ner_service()
    ner_result = await ner_service.extract_entities(doc.extracted_text)

    entities = []
    if ner_result and ner_result.entities:
        for e in ner_result.entities:
            entities.append(ExtractedEntity(
                entity_type=e.entity_type.value,
                value=e.value,
                confidence=e.confidence,
                context=e.context,
            ))

    return NERExtractionResponse(
        document_id=document_id,
        entities=entities,
        processing_time_ms=ner_result.processing_time_ms if ner_result else 0,
        from_cache=ner_result.from_cache if ner_result else False,
    )


@router.post(
    "/documents/{document_id}/extract-deadlines",
    response_model=DeadlineExtractionResponse,
    summary="Fristen aus Dokument extrahieren",
)
@limiter.limit("10/minute", key_func=get_user_identifier)
async def extract_document_deadlines(
    request: Request,
    document_id: uuid.UUID,
    space_id: uuid.UUID = Query(..., description="Space fuer Fristen-Erstellung"),
    auto_create: bool = Query(True, description="Fristen automatisch anlegen"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> DeadlineExtractionResponse:
    """
    Extrahiert Fristen aus Dokumenttext und erstellt optional
    PrivatDeadline-Eintraege.
    """
    from app.db.models import Document
    from sqlalchemy import select

    result = await db.execute(select(Document).where(Document.id == document_id))
    doc = result.scalar_one_or_none()

    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dokument nicht gefunden",
        )

    if doc.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Kein Zugriff auf dieses Dokument",
        )

    if not doc.extracted_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Kein OCR-Text vorhanden",
        )

    await get_user_space_or_403(db, space_id, current_user, PrivatAccessLevel.WRITE)

    from app.services.document_intelligence import get_deadline_extraction_service

    deadline_service = get_deadline_extraction_service()

    if auto_create:
        deadline_result = await deadline_service.extract_and_create_deadlines(
            text=doc.extracted_text,
            db=db,
            space_id=space_id,
            document_id=document_id,
        )
    else:
        deadline_result = await deadline_service.extract_deadlines(doc.extracted_text)

    deadlines = []
    if deadline_result and deadline_result.deadlines:
        for d in deadline_result.deadlines:
            deadlines.append(ExtractedDeadline(
                title=d.title,
                due_date=d.due_date,
                deadline_type=d.deadline_type,
                original_text=d.original_text,
                confidence=d.confidence,
                auto_created=auto_create,
            ))

    return DeadlineExtractionResponse(
        document_id=document_id,
        deadlines=deadlines,
        created_count=deadline_result.created_count if deadline_result and auto_create else 0,
        processing_time_ms=deadline_result.processing_time_ms if deadline_result else 0,
    )


# ==================== Bulk Calculations ====================


@router.post(
    "/spaces/{space_id}/calculate-all-kpis",
    response_model=TaskTriggerResponse,
    summary="Alle KPIs eines Spaces berechnen",
)
@limiter.limit("2/minute", key_func=get_user_identifier)
async def trigger_all_kpi_calculations(
    request: Request,
    space_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> TaskTriggerResponse:
    """
    Startet Berechnung aller KPIs fuer einen Space:
    - Immobilien-KPIs
    - Fahrzeug-TCO
    - Versicherungs-Analyse
    - Kredit-Tilgungsplaene
    - Finanz-Analytics
    """
    await get_user_space_or_403(db, space_id, current_user, PrivatAccessLevel.READ)

    from celery import group
    from app.workers.tasks.privat_tasks import (
        calculate_property_kpis,
        calculate_vehicle_tco,
        analyze_insurance_coverage,
        generate_loan_amortization,
        run_finance_analytics,
    )

    space_id_str = str(space_id)

    task_group = group(
        calculate_property_kpis.s(space_id=space_id_str),
        calculate_vehicle_tco.s(space_id=space_id_str),
        analyze_insurance_coverage.s(space_id=space_id_str),
        generate_loan_amortization.s(space_id=space_id_str),
        run_finance_analytics.s(space_id=space_id_str),
    )

    result = task_group.apply_async()

    return TaskTriggerResponse(
        task_id=result.id,
        status="queued",
        message="Alle KPI-Berechnungen gestartet (5 Tasks)",
    )


# ==================== Enterprise Intelligence API ====================


# -------------------- Response Models --------------------


class InvestmentPerformanceResponse(BaseModel):
    """Investment Performance Response."""
    investment_id: uuid.UUID
    investment_name: str
    absolute_return: float
    percentage_return: float
    annualized_return: Optional[float] = None
    holding_period_days: int
    current_value: float
    purchase_value: float
    calculated_at: datetime


class PortfolioAllocationItem(BaseModel):
    """Einzelne Allokation im Portfolio."""
    category: str
    value: float
    percentage: float
    count: int


class PortfolioAllocationResponse(BaseModel):
    """Portfolio Allokation Response."""
    space_id: uuid.UUID
    total_value: float
    allocation_by_type: List[PortfolioAllocationItem]
    allocation_by_risk: List[PortfolioAllocationItem]
    calculated_at: datetime


class DiversificationResponse(BaseModel):
    """Diversifikations-Analyse Response."""
    space_id: uuid.UUID
    herfindahl_index: float
    diversification_score: float  # 0-100, hoeher = besser
    rating: str  # excellent, good, moderate, poor, critical
    largest_position_percent: float
    recommendation: str
    analyzed_at: datetime


class RiskProfileResponse(BaseModel):
    """Risikoprofil Response."""
    space_id: uuid.UUID
    overall_risk_score: float  # 0-100
    risk_category: str  # konservativ, ausgewogen, wachstum, aggressiv
    target_profile: Optional[str] = None
    deviation_from_target: Optional[float] = None
    recommendation: str
    analyzed_at: datetime


class RebalancingItem(BaseModel):
    """Einzelne Rebalancing-Empfehlung."""
    investment_id: uuid.UUID
    investment_name: str
    action: str  # kaufen, verkaufen, halten
    current_allocation: float
    target_allocation: float
    deviation: float
    suggested_amount: Optional[float] = None
    priority: str  # high, medium, low


class RebalancingResponse(BaseModel):
    """Rebalancing-Empfehlungen Response."""
    space_id: uuid.UUID
    recommendations: List[RebalancingItem]
    total_deviation_score: float
    rebalancing_urgency: str  # urgent, recommended, optional
    generated_at: datetime


class FullPortfolioAnalyticsResponse(BaseModel):
    """Vollstaendige Portfolio-Analyse Response."""
    space_id: uuid.UUID
    total_value: float
    total_investments: int
    performance: Optional[dict] = None
    allocation: PortfolioAllocationResponse
    diversification: DiversificationResponse
    risk_profile: RiskProfileResponse
    rebalancing: Optional[RebalancingResponse] = None
    analyzed_at: datetime


class NetWorthItem(BaseModel):
    """Einzelne Vermoegensposition."""
    category: str
    label: str
    value: float


class NetWorthResponse(BaseModel):
    """Net Worth Summary Response."""
    space_id: uuid.UUID
    total_assets: float
    total_liabilities: float
    net_worth: float
    assets: List[NetWorthItem]
    liabilities: List[NetWorthItem]
    calculated_at: datetime


class HealthDimension(BaseModel):
    """Einzelne Health-Dimension."""
    name: str
    score: float  # 0-100
    weight: float
    rating: str
    factors: List[str]


class FinancialHealthResponse(BaseModel):
    """Financial Health Score Response."""
    space_id: uuid.UUID
    overall_score: float  # 0-100
    overall_rating: str  # excellent, good, moderate, poor, critical
    dimensions: List[HealthDimension]
    priority_recommendations: List[str]
    calculated_at: datetime


class RecommendationItem(BaseModel):
    """Einzelne Empfehlung."""
    id: str
    category: str
    priority: str  # critical, high, medium, low
    title: str
    description: str
    potential_benefit: Optional[str] = None
    action_required: Optional[str] = None
    related_entity_id: Optional[uuid.UUID] = None
    related_entity_type: Optional[str] = None


class RecommendationsResponse(BaseModel):
    """Smart Recommendations Response."""
    space_id: uuid.UUID
    recommendations: List[RecommendationItem]
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    generated_at: datetime


class AmortizationPayment(BaseModel):
    """Einzelne Tilgungsrate."""
    payment_number: int
    date: date
    principal: float
    interest: float
    total_payment: float
    remaining_balance: float


class ExtraPaymentScenarioResponse(BaseModel):
    """Sondertilgungs-Szenario Response."""
    loan_id: uuid.UUID
    loan_name: str
    extra_payment_amount: float
    extra_payment_frequency: str
    original_payoff_date: date
    new_payoff_date: date
    months_saved: int
    original_total_interest: float
    new_total_interest: float
    interest_saved: float
    savings_percentage: float
    calculated_at: datetime


class RefinancingScenarioResponse(BaseModel):
    """Umschuldungs-Szenario Response."""
    loan_id: uuid.UUID
    loan_name: str
    current_rate: float
    new_rate: float
    current_monthly_payment: float
    new_monthly_payment: float
    monthly_savings: float
    estimated_penalty: float
    total_new_interest: float
    total_current_remaining_interest: float
    net_savings: float
    break_even_months: int
    recommendation: str
    calculated_at: datetime


class PaymentChangeScenarioResponse(BaseModel):
    """Ratenänderungs-Szenario Response."""
    loan_id: uuid.UUID
    loan_name: str
    current_payment: float
    new_payment: float
    payment_change: float
    original_payoff_date: date
    new_payoff_date: date
    months_difference: int
    original_total_interest: float
    new_total_interest: float
    interest_difference: float
    calculated_at: datetime


class FullAmortizationResponse(BaseModel):
    """Vollstaendiger Tilgungsplan Response."""
    loan_id: uuid.UUID
    loan_name: str
    principal_amount: float
    interest_rate: float
    monthly_payment: float
    start_date: date
    payoff_date: date
    total_payments: int
    total_interest: float
    total_cost: float
    schedule: List[AmortizationPayment]
    generated_at: datetime


class ScenarioComparisonItem(BaseModel):
    """Einzelnes Vergleichsszenario."""
    scenario_name: str
    scenario_type: str
    parameter: float
    payoff_date: date
    total_interest: float
    interest_saved: float
    months_difference: int


class LoanComparisonResponse(BaseModel):
    """Kredit-Szenarien-Vergleich Response."""
    loan_id: uuid.UUID
    loan_name: str
    base_scenario: ScenarioComparisonItem
    alternative_scenarios: List[ScenarioComparisonItem]
    best_scenario: str
    max_savings: float
    generated_at: datetime


# -------------------- Investment Intelligence Endpoints --------------------


@router.get(
    "/investments/{investment_id}/performance",
    response_model=InvestmentPerformanceResponse,
    summary="Investment Performance abrufen",
)
@limiter.limit("30/minute", key_func=get_user_identifier)
async def get_investment_performance(
    request: Request,
    investment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> InvestmentPerformanceResponse:
    """
    Berechnet Performance fuer ein einzelnes Investment:
    - Absolute und prozentuale Rendite
    - Annualisierte Rendite (CAGR)
    - Haltedauer
    """
    from app.services.privat import PrivatInvestmentService, get_investment_intelligence_service

    investment_service = PrivatInvestmentService()
    investment = await investment_service.get_by_id(db, investment_id)

    if not investment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Investment nicht gefunden",
        )

    await get_user_space_or_403(db, investment.space_id, current_user, PrivatAccessLevel.READ)

    intelligence_service = get_investment_intelligence_service()
    performance = await intelligence_service.calculate_investment_performance(db, investment_id)

    if not performance:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Performance konnte nicht berechnet werden",
        )

    return InvestmentPerformanceResponse(
        investment_id=investment_id,
        investment_name=investment.name,
        absolute_return=float(performance.absolute_return),
        percentage_return=float(performance.percentage_return),
        annualized_return=float(performance.annualized_return) if performance.annualized_return else None,
        holding_period_days=performance.holding_period_days,
        current_value=float(performance.current_value),
        purchase_value=float(performance.purchase_value),
        calculated_at=utc_now(),
    )


@router.get(
    "/spaces/{space_id}/portfolio/allocation",
    response_model=PortfolioAllocationResponse,
    summary="Portfolio Allokation abrufen",
)
@limiter.limit("20/minute", key_func=get_user_identifier)
async def get_portfolio_allocation(
    request: Request,
    space_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PortfolioAllocationResponse:
    """
    Berechnet Portfolio-Allokation:
    - Nach Investment-Typ (ETF, Aktie, Anleihe, etc.)
    - Nach Risikokategorie
    """
    await get_user_space_or_403(db, space_id, current_user, PrivatAccessLevel.READ)

    from app.services.privat import get_investment_intelligence_service

    intelligence_service = get_investment_intelligence_service()
    allocation = await intelligence_service.calculate_allocation(db, space_id)

    if not allocation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Keine Investments gefunden",
        )

    by_type = [
        PortfolioAllocationItem(
            category=item.category,
            value=float(item.value),
            percentage=float(item.percentage),
            count=item.count,
        )
        for item in allocation.by_type
    ]

    by_risk = [
        PortfolioAllocationItem(
            category=item.category,
            value=float(item.value),
            percentage=float(item.percentage),
            count=item.count,
        )
        for item in allocation.by_risk
    ]

    return PortfolioAllocationResponse(
        space_id=space_id,
        total_value=float(allocation.total_value),
        allocation_by_type=by_type,
        allocation_by_risk=by_risk,
        calculated_at=utc_now(),
    )


@router.get(
    "/spaces/{space_id}/portfolio/diversification",
    response_model=DiversificationResponse,
    summary="Diversifikations-Analyse abrufen",
)
@limiter.limit("20/minute", key_func=get_user_identifier)
async def get_diversification_analysis(
    request: Request,
    space_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> DiversificationResponse:
    """
    Analysiert Portfolio-Diversifikation:
    - Herfindahl-Index Berechnung
    - Diversifikations-Score (0-100)
    - Empfehlungen zur Verbesserung
    """
    await get_user_space_or_403(db, space_id, current_user, PrivatAccessLevel.READ)

    from app.services.privat import get_investment_intelligence_service

    intelligence_service = get_investment_intelligence_service()
    diversification = await intelligence_service.analyze_diversification(db, space_id)

    if not diversification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Keine Investments gefunden",
        )

    return DiversificationResponse(
        space_id=space_id,
        herfindahl_index=float(diversification.herfindahl_index),
        diversification_score=float(diversification.diversification_score),
        rating=diversification.rating,
        largest_position_percent=float(diversification.largest_position_percent),
        recommendation=diversification.recommendation,
        analyzed_at=utc_now(),
    )


@router.get(
    "/spaces/{space_id}/portfolio/risk-profile",
    response_model=RiskProfileResponse,
    summary="Risikoprofil abrufen",
)
@limiter.limit("20/minute", key_func=get_user_identifier)
async def get_risk_profile(
    request: Request,
    space_id: uuid.UUID,
    target_profile: Optional[str] = Query(None, pattern="^(konservativ|ausgewogen|wachstum|aggressiv)$", description="Ziel-Profil: konservativ, ausgewogen, wachstum, aggressiv"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> RiskProfileResponse:
    """
    Analysiert Risikoprofil des Portfolios:
    - Gesamt-Risikoscore (0-100)
    - Risikokategorie
    - Optional: Abweichung vom Zielprofil
    """
    await get_user_space_or_403(db, space_id, current_user, PrivatAccessLevel.READ)

    from app.services.privat import get_investment_intelligence_service

    intelligence_service = get_investment_intelligence_service()
    risk_profile = await intelligence_service.analyze_risk_profile(db, space_id, target_profile)

    if not risk_profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Keine Investments gefunden",
        )

    return RiskProfileResponse(
        space_id=space_id,
        overall_risk_score=float(risk_profile.overall_risk_score),
        risk_category=risk_profile.risk_category,
        target_profile=risk_profile.target_profile,
        deviation_from_target=float(risk_profile.deviation_from_target) if risk_profile.deviation_from_target else None,
        recommendation=risk_profile.recommendation,
        analyzed_at=utc_now(),
    )


@router.get(
    "/spaces/{space_id}/portfolio/rebalancing",
    response_model=RebalancingResponse,
    summary="Rebalancing-Empfehlungen abrufen",
)
@limiter.limit("10/minute", key_func=get_user_identifier)
async def get_rebalancing_recommendations(
    request: Request,
    space_id: uuid.UUID,
    target_profile: str = Query("ausgewogen", description="Ziel-Profil"),
    tolerance: float = Query(5.0, ge=1.0, le=20.0, description="Toleranz in %"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> RebalancingResponse:
    """
    Generiert Rebalancing-Empfehlungen:
    - Welche Positionen anpassen
    - Kauf-/Verkaufsempfehlungen
    - Priorisierung nach Abweichung
    """
    await get_user_space_or_403(db, space_id, current_user, PrivatAccessLevel.READ)

    from app.services.privat import get_investment_intelligence_service

    intelligence_service = get_investment_intelligence_service()
    rebalancing = await intelligence_service.generate_rebalancing_recommendations(
        db, space_id, target_profile, Decimal(str(tolerance))
    )

    if not rebalancing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Keine Investments gefunden",
        )

    items = [
        RebalancingItem(
            investment_id=r.investment_id,
            investment_name=r.investment_name,
            action=r.action,
            current_allocation=float(r.current_allocation),
            target_allocation=float(r.target_allocation),
            deviation=float(r.deviation),
            suggested_amount=float(r.suggested_amount) if r.suggested_amount else None,
            priority=r.priority,
        )
        for r in rebalancing
    ]

    total_deviation = sum(abs(r.deviation) for r in items)
    urgency = "urgent" if total_deviation > 30 else ("recommended" if total_deviation > 15 else "optional")

    return RebalancingResponse(
        space_id=space_id,
        recommendations=items,
        total_deviation_score=total_deviation,
        rebalancing_urgency=urgency,
        generated_at=utc_now(),
    )


@router.get(
    "/spaces/{space_id}/portfolio/full-analytics",
    response_model=FullPortfolioAnalyticsResponse,
    summary="Vollstaendige Portfolio-Analyse",
)
@limiter.limit("5/minute", key_func=get_user_identifier)
async def get_full_portfolio_analytics(
    request: Request,
    space_id: uuid.UUID,
    target_profile: Optional[str] = Query(None, pattern="^(konservativ|ausgewogen|wachstum|aggressiv)$", description="Ziel-Profil fuer Rebalancing"),
    include_rebalancing: bool = Query(True, description="Rebalancing-Empfehlungen einbeziehen"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> FullPortfolioAnalyticsResponse:
    """
    Vollstaendige Portfolio-Analyse in einem Aufruf:
    - Allokation
    - Diversifikation
    - Risikoprofil
    - Optional: Rebalancing-Empfehlungen
    """
    await get_user_space_or_403(db, space_id, current_user, PrivatAccessLevel.READ)

    from app.services.privat import get_investment_intelligence_service

    intelligence_service = get_investment_intelligence_service()
    analytics = await intelligence_service.get_full_portfolio_analytics(
        db, space_id, target_profile, include_rebalancing
    )

    if not analytics:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Keine Investments gefunden",
        )

    # Baue Response zusammen
    allocation_response = PortfolioAllocationResponse(
        space_id=space_id,
        total_value=float(analytics.allocation.total_value),
        allocation_by_type=[
            PortfolioAllocationItem(
                category=a.category, value=float(a.value),
                percentage=float(a.percentage), count=a.count
            )
            for a in analytics.allocation.by_type
        ],
        allocation_by_risk=[
            PortfolioAllocationItem(
                category=a.category, value=float(a.value),
                percentage=float(a.percentage), count=a.count
            )
            for a in analytics.allocation.by_risk
        ],
        calculated_at=utc_now(),
    )

    diversification_response = DiversificationResponse(
        space_id=space_id,
        herfindahl_index=float(analytics.diversification.herfindahl_index),
        diversification_score=float(analytics.diversification.diversification_score),
        rating=analytics.diversification.rating,
        largest_position_percent=float(analytics.diversification.largest_position_percent),
        recommendation=analytics.diversification.recommendation,
        analyzed_at=utc_now(),
    )

    risk_response = RiskProfileResponse(
        space_id=space_id,
        overall_risk_score=float(analytics.risk_profile.overall_risk_score),
        risk_category=analytics.risk_profile.risk_category,
        target_profile=analytics.risk_profile.target_profile,
        deviation_from_target=float(analytics.risk_profile.deviation_from_target) if analytics.risk_profile.deviation_from_target else None,
        recommendation=analytics.risk_profile.recommendation,
        analyzed_at=utc_now(),
    )

    rebalancing_response = None
    if analytics.rebalancing:
        items = [
            RebalancingItem(
                investment_id=r.investment_id,
                investment_name=r.investment_name,
                action=r.action,
                current_allocation=float(r.current_allocation),
                target_allocation=float(r.target_allocation),
                deviation=float(r.deviation),
                suggested_amount=float(r.suggested_amount) if r.suggested_amount else None,
                priority=r.priority,
            )
            for r in analytics.rebalancing
        ]
        total_deviation = sum(abs(r.deviation) for r in items)
        urgency = "urgent" if total_deviation > 30 else ("recommended" if total_deviation > 15 else "optional")
        rebalancing_response = RebalancingResponse(
            space_id=space_id,
            recommendations=items,
            total_deviation_score=total_deviation,
            rebalancing_urgency=urgency,
            generated_at=utc_now(),
        )

    return FullPortfolioAnalyticsResponse(
        space_id=space_id,
        total_value=float(analytics.total_value),
        total_investments=analytics.total_investments,
        performance=None,  # Optional aggregate
        allocation=allocation_response,
        diversification=diversification_response,
        risk_profile=risk_response,
        rebalancing=rebalancing_response,
        analyzed_at=utc_now(),
    )


# -------------------- Financial Health Endpoints --------------------


@router.get(
    "/spaces/{space_id}/net-worth",
    response_model=NetWorthResponse,
    summary="Net Worth Uebersicht",
)
@limiter.limit("20/minute", key_func=get_user_identifier)
async def get_net_worth(
    request: Request,
    space_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> NetWorthResponse:
    """
    Berechnet Net Worth (Reinvermoegen):
    - Alle Vermoegenswerte (Immobilien, Fahrzeuge, Investments)
    - Alle Verbindlichkeiten (Kredite)
    - Netto-Vermoegen
    """
    await get_user_space_or_403(db, space_id, current_user, PrivatAccessLevel.READ)

    from app.services.privat import get_financial_health_service

    health_service = get_financial_health_service()
    net_worth = await health_service.calculate_net_worth(db, space_id)

    if not net_worth:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Net Worth konnte nicht berechnet werden",
        )

    assets = [
        NetWorthItem(category=a.category, label=a.label, value=float(a.value))
        for a in net_worth.assets
    ]

    liabilities = [
        NetWorthItem(category=l.category, label=l.label, value=float(l.value))
        for l in net_worth.liabilities
    ]

    return NetWorthResponse(
        space_id=space_id,
        total_assets=float(net_worth.total_assets),
        total_liabilities=float(net_worth.total_liabilities),
        net_worth=float(net_worth.net_worth),
        assets=assets,
        liabilities=liabilities,
        calculated_at=utc_now(),
    )


@router.get(
    "/spaces/{space_id}/health-score",
    response_model=FinancialHealthResponse,
    summary="Financial Health Score abrufen",
)
@limiter.limit("10/minute", key_func=get_user_identifier)
async def get_financial_health_score(
    request: Request,
    space_id: uuid.UUID,
    monthly_income: Optional[float] = Query(None, gt=0, le=1000000, description="Monatliches Nettoeinkommen"),
    monthly_expenses: Optional[float] = Query(None, ge=0, le=1000000, description="Monatliche Fixausgaben"),
    age: Optional[int] = Query(None, ge=18, le=100, description="Alter fuer Altersvorsorge-Bewertung"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> FinancialHealthResponse:
    """
    Berechnet Financial Health Score (0-100):
    - 6 Dimensionen: Vermoegensaufbau, Schulden, Risikoabdeckung,
      Liquiditaet, Altersvorsorge, Diversifikation
    - Gewichteter Gesamtscore
    - Priorisierte Empfehlungen
    """
    await get_user_space_or_403(db, space_id, current_user, PrivatAccessLevel.READ)

    from app.services.privat import get_financial_health_service

    health_service = get_financial_health_service()
    health_score = await health_service.calculate_health_score(
        db,
        space_id,
        monthly_income=Decimal(str(monthly_income)) if monthly_income else None,
        monthly_expenses=Decimal(str(monthly_expenses)) if monthly_expenses else None,
        user_age=age,
    )

    if not health_score:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Health Score konnte nicht berechnet werden",
        )

    dimensions = [
        HealthDimension(
            name=d.name,
            score=float(d.score),
            weight=float(d.weight),
            rating=d.rating,
            factors=d.factors,
        )
        for d in health_score.dimensions
    ]

    return FinancialHealthResponse(
        space_id=space_id,
        overall_score=float(health_score.overall_score),
        overall_rating=health_score.overall_rating,
        dimensions=dimensions,
        priority_recommendations=health_score.priority_recommendations,
        calculated_at=utc_now(),
    )


# -------------------- Smart Recommendations Endpoints --------------------


@router.get(
    "/spaces/{space_id}/recommendations",
    response_model=RecommendationsResponse,
    summary="Smart Recommendations abrufen",
)
@limiter.limit("10/minute", key_func=get_user_identifier)
async def get_recommendations(
    request: Request,
    space_id: uuid.UUID,
    max_recommendations: int = Query(20, ge=5, le=50, description="Max. Anzahl Empfehlungen"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> RecommendationsResponse:
    """
    Generiert intelligente Empfehlungen:
    - Refinanzierungs-Moeglichkeiten
    - Rebalancing-Bedarf
    - Versicherungsluecken
    - Notgroschen-Status
    - Bevorstehende Fristen
    - Veraltete Werte
    """
    await get_user_space_or_403(db, space_id, current_user, PrivatAccessLevel.READ)

    from app.services.privat import get_recommendations_service

    reco_service = get_recommendations_service()
    recommendations_result = await reco_service.generate_recommendations(db, space_id)

    if not recommendations_result:
        return RecommendationsResponse(
            space_id=space_id,
            recommendations=[],
            critical_count=0,
            high_count=0,
            medium_count=0,
            low_count=0,
            generated_at=utc_now(),
        )

    items = [
        RecommendationItem(
            id=r.id,
            category=r.category,
            priority=r.priority,
            title=r.title,
            description=r.description,
            potential_benefit=r.potential_benefit,
            action_required=r.action_required,
            related_entity_id=r.related_entity_id,
            related_entity_type=r.related_entity_type,
        )
        for r in recommendations_result.recommendations[:max_recommendations]
    ]

    return RecommendationsResponse(
        space_id=space_id,
        recommendations=items,
        critical_count=recommendations_result.critical_count,
        high_count=recommendations_result.high_count,
        medium_count=recommendations_result.medium_count,
        low_count=recommendations_result.low_count,
        generated_at=utc_now(),
    )


# -------------------- Loan Scenario Endpoints --------------------


@router.post(
    "/loans/{loan_id}/simulate/extra-payment",
    response_model=ExtraPaymentScenarioResponse,
    summary="Sondertilgung simulieren",
)
@limiter.limit("20/minute", key_func=get_user_identifier)
async def simulate_extra_payment(
    request: Request,
    loan_id: uuid.UUID,
    extra_amount: float = Query(..., gt=0, description="Sondertilgungs-Betrag"),
    frequency: str = Query("einmalig", description="einmalig, monatlich, jaehrlich"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ExtraPaymentScenarioResponse:
    """
    Simuliert Auswirkungen einer Sondertilgung:
    - Neue Restlaufzeit
    - Gesamtzins-Ersparnis
    - Neues Payoff-Datum
    """
    from app.services.privat import PrivatLoanService, get_loan_scenario_service

    loan_service = PrivatLoanService()
    loan = await loan_service.get_by_id(db, loan_id)

    if not loan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kredit nicht gefunden",
        )

    await get_user_space_or_403(db, loan.space_id, current_user, PrivatAccessLevel.READ)

    scenario_service = get_loan_scenario_service()
    scenario = await scenario_service.simulate_extra_payment(
        db, loan_id, Decimal(str(extra_amount)), frequency
    )

    if not scenario:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Simulation konnte nicht durchgefuehrt werden",
        )

    return ExtraPaymentScenarioResponse(
        loan_id=loan_id,
        loan_name=loan.name,
        extra_payment_amount=float(scenario.extra_payment_amount),
        extra_payment_frequency=scenario.extra_payment_frequency,
        original_payoff_date=scenario.original_payoff_date,
        new_payoff_date=scenario.new_payoff_date,
        months_saved=scenario.months_saved,
        original_total_interest=float(scenario.original_total_interest),
        new_total_interest=float(scenario.new_total_interest),
        interest_saved=float(scenario.interest_saved),
        savings_percentage=float(scenario.savings_percentage),
        calculated_at=utc_now(),
    )


@router.post(
    "/loans/{loan_id}/simulate/refinancing",
    response_model=RefinancingScenarioResponse,
    summary="Umschuldung simulieren",
)
@limiter.limit("20/minute", key_func=get_user_identifier)
async def simulate_refinancing(
    request: Request,
    loan_id: uuid.UUID,
    new_rate: float = Query(..., gt=0, le=30, description="Neuer Zinssatz in %"),
    penalty_rate: float = Query(1.0, ge=0, le=5, description="Vorfaelligkeitsentschaedigung in %"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> RefinancingScenarioResponse:
    """
    Simuliert Umschuldungs-Szenario:
    - Neue monatliche Rate
    - Geschaetzte Vorfaelligkeitsentschaedigung
    - Gesamt-Ersparnis
    - Break-Even-Punkt
    """
    from app.services.privat import PrivatLoanService, get_loan_scenario_service

    loan_service = PrivatLoanService()
    loan = await loan_service.get_by_id(db, loan_id)

    if not loan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kredit nicht gefunden",
        )

    await get_user_space_or_403(db, loan.space_id, current_user, PrivatAccessLevel.READ)

    scenario_service = get_loan_scenario_service()
    scenario = await scenario_service.simulate_refinancing(
        db, loan_id, Decimal(str(new_rate)), Decimal(str(penalty_rate))
    )

    if not scenario:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Simulation konnte nicht durchgefuehrt werden",
        )

    return RefinancingScenarioResponse(
        loan_id=loan_id,
        loan_name=loan.name,
        current_rate=float(scenario.current_rate),
        new_rate=float(scenario.new_rate),
        current_monthly_payment=float(scenario.current_monthly_payment),
        new_monthly_payment=float(scenario.new_monthly_payment),
        monthly_savings=float(scenario.monthly_savings),
        estimated_penalty=float(scenario.estimated_penalty),
        total_new_interest=float(scenario.total_new_interest),
        total_current_remaining_interest=float(scenario.total_current_remaining_interest),
        net_savings=float(scenario.net_savings),
        break_even_months=scenario.break_even_months,
        recommendation=scenario.recommendation,
        calculated_at=utc_now(),
    )


@router.post(
    "/loans/{loan_id}/simulate/payment-change",
    response_model=PaymentChangeScenarioResponse,
    summary="Ratenänderung simulieren",
)
@limiter.limit("20/minute", key_func=get_user_identifier)
async def simulate_payment_change(
    request: Request,
    loan_id: uuid.UUID,
    new_payment: float = Query(..., gt=0, description="Neue monatliche Rate"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PaymentChangeScenarioResponse:
    """
    Simuliert Auswirkungen einer Ratenänderung:
    - Neue Laufzeit
    - Zins-Differenz
    """
    from app.services.privat import PrivatLoanService, get_loan_scenario_service

    loan_service = PrivatLoanService()
    loan = await loan_service.get_by_id(db, loan_id)

    if not loan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kredit nicht gefunden",
        )

    await get_user_space_or_403(db, loan.space_id, current_user, PrivatAccessLevel.READ)

    scenario_service = get_loan_scenario_service()
    scenario = await scenario_service.simulate_payment_change(
        db, loan_id, Decimal(str(new_payment))
    )

    if not scenario:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Simulation konnte nicht durchgefuehrt werden",
        )

    return PaymentChangeScenarioResponse(
        loan_id=loan_id,
        loan_name=loan.name,
        current_payment=float(scenario.current_payment),
        new_payment=float(scenario.new_payment),
        payment_change=float(scenario.payment_change),
        original_payoff_date=scenario.original_payoff_date,
        new_payoff_date=scenario.new_payoff_date,
        months_difference=scenario.months_difference,
        original_total_interest=float(scenario.original_total_interest),
        new_total_interest=float(scenario.new_total_interest),
        interest_difference=float(scenario.interest_difference),
        calculated_at=utc_now(),
    )


@router.get(
    "/loans/{loan_id}/full-amortization",
    response_model=FullAmortizationResponse,
    summary="Vollstaendiger Tilgungsplan",
)
@limiter.limit("10/minute", key_func=get_user_identifier)
async def get_full_amortization(
    request: Request,
    loan_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> FullAmortizationResponse:
    """
    Generiert vollstaendigen Tilgungsplan:
    - Monatliche Aufschluesselung
    - Zins-/Tilgungsanteil pro Rate
    - Restschuld nach jeder Rate
    """
    from app.services.privat import PrivatLoanService, get_loan_scenario_service

    loan_service = PrivatLoanService()
    loan = await loan_service.get_by_id(db, loan_id)

    if not loan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kredit nicht gefunden",
        )

    await get_user_space_or_403(db, loan.space_id, current_user, PrivatAccessLevel.READ)

    scenario_service = get_loan_scenario_service()
    amortization = await scenario_service.generate_full_amortization(db, loan_id)

    if not amortization:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tilgungsplan konnte nicht erstellt werden",
        )

    schedule = [
        AmortizationPayment(
            payment_number=p.payment_number,
            date=p.date,
            principal=float(p.principal),
            interest=float(p.interest),
            total_payment=float(p.total_payment),
            remaining_balance=float(p.remaining_balance),
        )
        for p in amortization.schedule[:360]  # Max 30 Jahre
    ]

    return FullAmortizationResponse(
        loan_id=loan_id,
        loan_name=loan.name,
        principal_amount=float(amortization.principal_amount),
        interest_rate=float(amortization.interest_rate),
        monthly_payment=float(amortization.monthly_payment),
        start_date=amortization.start_date,
        payoff_date=amortization.payoff_date,
        total_payments=amortization.total_payments,
        total_interest=float(amortization.total_interest),
        total_cost=float(amortization.total_cost),
        schedule=schedule,
        generated_at=utc_now(),
    )


@router.post(
    "/loans/{loan_id}/compare-scenarios",
    response_model=LoanComparisonResponse,
    summary="Kredit-Szenarien vergleichen",
)
@limiter.limit("5/minute", key_func=get_user_identifier)
async def compare_loan_scenarios(
    request: Request,
    loan_id: uuid.UUID,
    extra_payments: List[float] = Query([], description="Sondertilgungsbeträge zu vergleichen"),
    new_rates: List[float] = Query([], description="Neue Zinssätze zu vergleichen"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> LoanComparisonResponse:
    """
    Vergleicht mehrere Kredit-Szenarien:
    - Basis vs. Sondertilgungen vs. Umschuldungen
    - Beste Option ermitteln
    """
    from app.services.privat import PrivatLoanService, get_loan_scenario_service

    loan_service = PrivatLoanService()
    loan = await loan_service.get_by_id(db, loan_id)

    if not loan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kredit nicht gefunden",
        )

    await get_user_space_or_403(db, loan.space_id, current_user, PrivatAccessLevel.READ)

    scenario_service = get_loan_scenario_service()
    comparison = await scenario_service.compare_scenarios(
        db, loan_id,
        [Decimal(str(ep)) for ep in extra_payments],
        [Decimal(str(nr)) for nr in new_rates]
    )

    if not comparison:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vergleich konnte nicht erstellt werden",
        )

    base = ScenarioComparisonItem(
        scenario_name=comparison.base_scenario.scenario_name,
        scenario_type=comparison.base_scenario.scenario_type,
        parameter=float(comparison.base_scenario.parameter),
        payoff_date=comparison.base_scenario.payoff_date,
        total_interest=float(comparison.base_scenario.total_interest),
        interest_saved=float(comparison.base_scenario.interest_saved),
        months_difference=comparison.base_scenario.months_difference,
    )

    alternatives = [
        ScenarioComparisonItem(
            scenario_name=s.scenario_name,
            scenario_type=s.scenario_type,
            parameter=float(s.parameter),
            payoff_date=s.payoff_date,
            total_interest=float(s.total_interest),
            interest_saved=float(s.interest_saved),
            months_difference=s.months_difference,
        )
        for s in comparison.alternative_scenarios
    ]

    return LoanComparisonResponse(
        loan_id=loan_id,
        loan_name=loan.name,
        base_scenario=base,
        alternative_scenarios=alternatives,
        best_scenario=comparison.best_scenario,
        max_savings=float(comparison.max_savings),
        generated_at=utc_now(),
    )


# -------------------- Property Intelligence Endpoints --------------------


@router.post(
    "/properties/{property_id}/recalculate-intelligence",
    response_model=TaskTriggerResponse,
    summary="Immobilien-Intelligence neu berechnen",
)
@limiter.limit("5/minute", key_func=get_user_identifier)
async def trigger_property_intelligence(
    request: Request,
    property_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> TaskTriggerResponse:
    """Triggert Neuberechnung aller Property-Intelligence-KPIs."""
    from app.services.privat import PrivatPropertyService, get_property_intelligence_service

    property_service = PrivatPropertyService()
    prop = await property_service.get_by_id(db, property_id)

    if not prop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Immobilie nicht gefunden",
        )

    await get_user_space_or_403(db, prop.space_id, current_user, PrivatAccessLevel.WRITE)

    from app.workers.tasks.privat_tasks import recalculate_property_intelligence

    task = recalculate_property_intelligence.delay(property_id=str(property_id))

    return TaskTriggerResponse(
        task_id=task.id,
        status="queued",
        message="Property-Intelligence-Berechnung gestartet",
    )


# -------------------- Vehicle Intelligence Endpoints --------------------


@router.post(
    "/vehicles/{vehicle_id}/recalculate-intelligence",
    response_model=TaskTriggerResponse,
    summary="Fahrzeug-Intelligence neu berechnen",
)
@limiter.limit("5/minute", key_func=get_user_identifier)
async def trigger_vehicle_intelligence(
    request: Request,
    vehicle_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> TaskTriggerResponse:
    """Triggert Neuberechnung aller Vehicle-Intelligence-KPIs."""
    from app.services.privat import PrivatVehicleService, get_vehicle_intelligence_service

    vehicle_service = PrivatVehicleService()
    vehicle = await vehicle_service.get_by_id(db, vehicle_id)

    if not vehicle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Fahrzeug nicht gefunden",
        )

    await get_user_space_or_403(db, vehicle.space_id, current_user, PrivatAccessLevel.WRITE)

    from app.workers.tasks.privat_tasks import recalculate_vehicle_intelligence

    task = recalculate_vehicle_intelligence.delay(vehicle_id=str(vehicle_id))

    return TaskTriggerResponse(
        task_id=task.id,
        status="queued",
        message="Vehicle-Intelligence-Berechnung gestartet",
    )


# -------------------- Bulk Intelligence Trigger --------------------


@router.post(
    "/spaces/{space_id}/calculate-all-intelligence",
    response_model=TaskTriggerResponse,
    summary="Alle Intelligence-Berechnungen starten",
)
@limiter.limit("1/minute", key_func=get_user_identifier)
async def trigger_all_intelligence_calculations(
    request: Request,
    space_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> TaskTriggerResponse:
    """
    Startet alle Intelligence-Berechnungen fuer einen Space:
    - Property Intelligence (Werte, Renditen)
    - Vehicle Intelligence (TCO, Depreciation)
    - Investment Intelligence (Portfolio, Risk)
    - Financial Health Score
    - Smart Recommendations
    """
    await get_user_space_or_403(db, space_id, current_user, PrivatAccessLevel.WRITE)

    from celery import group
    from app.workers.tasks.privat_tasks import (
        recalculate_all_property_intelligence,
        recalculate_all_vehicle_intelligence,
        recalculate_investment_intelligence,
        calculate_financial_health,
        generate_smart_recommendations,
    )

    space_id_str = str(space_id)

    task_group = group(
        recalculate_all_property_intelligence.s(space_id=space_id_str),
        recalculate_all_vehicle_intelligence.s(space_id=space_id_str),
        recalculate_investment_intelligence.s(space_id=space_id_str),
        calculate_financial_health.s(space_id=space_id_str),
        generate_smart_recommendations.s(space_id=space_id_str),
    )

    result = task_group.apply_async()

    return TaskTriggerResponse(
        task_id=result.id,
        status="queued",
        message="Alle Intelligence-Berechnungen gestartet (5 Tasks)",
    )


# ==================== KI-Analyse Endpoints ====================


# -------------------- Response Models --------------------


class PropertyKIAnalysisResponse(BaseModel):
    """KI-gestuetzte Immobilien-Analyse Response."""
    property_id: uuid.UUID
    estimated_value_eur: float
    confidence_percent: float = Field(..., ge=0, le=100)
    reasoning: str
    market_comparison: str
    value_trend: str  # steigend, stabil, fallend
    rental_potential_eur: Optional[float] = None
    roi_estimate_percent: Optional[float] = None
    from_cache: bool
    analyzed_at: datetime


class VehicleKIAnalysisResponse(BaseModel):
    """KI-gestuetzte Fahrzeug-Analyse Response."""
    vehicle_id: uuid.UUID
    current_value_eur: float
    depreciation_percent: float
    remaining_value_percent: float
    optimal_sell_timeframe: str
    market_demand: str  # hoch, mittel, gering
    value_factors: List[str]
    from_cache: bool
    analyzed_at: datetime


class InvestmentKIAdviceResponse(BaseModel):
    """KI-gestuetzte Investment-Beratung Response."""
    space_id: uuid.UUID
    portfolio_health_score: float = Field(..., ge=0, le=100)
    risk_assessment: str  # konservativ, ausgewogen, wachstumsorientiert, spekulativ
    diversification_score: float = Field(..., ge=0, le=100)
    recommendations: List[dict]
    rebalancing_needed: bool
    rebalancing_suggestions: List[str]
    tax_optimization_hints: List[str]
    projected_annual_return_percent: float
    risk_warnings: List[str]
    from_cache: bool
    analyzed_at: datetime


class InsuranceKICheckResponse(BaseModel):
    """KI-gestuetzte Versicherungs-Pruefung Response."""
    space_id: uuid.UUID
    coverage_score: float = Field(..., ge=0, le=100)
    cost_efficiency_score: float = Field(..., ge=0, le=100)
    critical_gaps: List[dict]
    optimization_suggestions: List[dict]
    unnecessary_insurances: List[dict]
    recommended_actions: List[str]
    overall_assessment: str
    from_cache: bool
    analyzed_at: datetime


class FinancialQARequest(BaseModel):
    """Request fuer Financial Q&A."""
    question: str = Field(..., min_length=10, max_length=1000, description="Finanzfrage in Deutsch")


class FinancialQAAnswerResponse(BaseModel):
    """KI-gestuetzte Finanz-Assistent Response."""
    space_id: uuid.UUID
    question: str
    answer: str
    confidence: str  # hoch, mittel, niedrig
    sources: List[str]
    related_topics: List[str]
    action_items: List[str]
    warnings: List[str]
    consult_expert: bool
    expert_type: Optional[str] = None  # Steuerberater, Finanzberater, Rechtsanwalt, etc.
    analyzed_at: datetime


# -------------------- Property KI Analysis --------------------


@router.post(
    "/properties/{property_id}/ki-analysis",
    response_model=PropertyKIAnalysisResponse,
    summary="KI-gestuetzte Immobilien-Wertanalyse",
)
@limiter.limit("5/minute", key_func=get_user_identifier)
async def get_property_ki_analysis(
    request: Request,
    property_id: uuid.UUID,
    use_cache: bool = Query(True, description="Gecachete Analyse verwenden wenn vorhanden"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PropertyKIAnalysisResponse:
    """
    KI-gestuetzte Immobilienbewertung mit Ollama LLM:
    - Marktwert-Schaetzung
    - Vergleich mit Region
    - Mietrendite-Potenzial
    - Markttrend-Einschaetzung

    Verwendet lokales Ollama Modell (qwen2.5) fuer datenschutzfreundliche Analyse.
    """
    from app.services.privat import PrivatPropertyService, get_privat_ki_prompt_service

    property_service = PrivatPropertyService()
    prop = await property_service.get_by_id(db, property_id)

    if not prop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Immobilie nicht gefunden",
        )

    await get_user_space_or_403(db, prop.space_id, current_user, PrivatAccessLevel.READ)

    ki_service = get_privat_ki_prompt_service()

    try:
        analysis = await ki_service.analyze_property_value(db, property_id, use_cache)
    except Exception as e:
        logger.error("ki_property_analysis_failed", property_id=str(property_id), **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="KI-Analyse derzeit nicht verfuegbar. Bitte spaeter erneut versuchen.",
        )

    return PropertyKIAnalysisResponse(
        property_id=property_id,
        estimated_value_eur=analysis.estimated_value_eur,
        confidence_percent=analysis.confidence_percent,
        reasoning=analysis.reasoning,
        market_comparison=analysis.market_comparison,
        value_trend=analysis.value_trend,
        rental_potential_eur=analysis.rental_potential_eur,
        roi_estimate_percent=analysis.roi_estimate_percent,
        from_cache=analysis.from_cache,
        analyzed_at=utc_now(),
    )


# -------------------- Vehicle KI Analysis --------------------


@router.post(
    "/vehicles/{vehicle_id}/ki-analysis",
    response_model=VehicleKIAnalysisResponse,
    summary="KI-gestuetzte Fahrzeug-Wertanalyse",
)
@limiter.limit("5/minute", key_func=get_user_identifier)
async def get_vehicle_ki_analysis(
    request: Request,
    vehicle_id: uuid.UUID,
    use_cache: bool = Query(True, description="Gecachete Analyse verwenden wenn vorhanden"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> VehicleKIAnalysisResponse:
    """
    KI-gestuetzte Fahrzeugbewertung mit Ollama LLM:
    - Aktueller Marktwert
    - Wertverlust-Analyse
    - Optimaler Verkaufszeitpunkt
    - Markttrend und Nachfrage

    Beruecksichtigt deutsche Marktbedingungen und E-Mobilitaets-Trends.
    """
    from app.services.privat import PrivatVehicleService, get_privat_ki_prompt_service

    vehicle_service = PrivatVehicleService()
    vehicle = await vehicle_service.get_by_id(db, vehicle_id)

    if not vehicle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Fahrzeug nicht gefunden",
        )

    await get_user_space_or_403(db, vehicle.space_id, current_user, PrivatAccessLevel.READ)

    ki_service = get_privat_ki_prompt_service()

    try:
        analysis = await ki_service.analyze_vehicle_depreciation(db, vehicle_id, use_cache)
    except Exception as e:
        logger.error("ki_vehicle_analysis_failed", vehicle_id=str(vehicle_id), **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="KI-Analyse derzeit nicht verfuegbar. Bitte spaeter erneut versuchen.",
        )

    return VehicleKIAnalysisResponse(
        vehicle_id=vehicle_id,
        current_value_eur=analysis.current_value_eur,
        depreciation_percent=analysis.depreciation_percent,
        remaining_value_percent=analysis.remaining_value_percent,
        optimal_sell_timeframe=analysis.optimal_sell_timeframe,
        market_demand=analysis.market_demand,
        value_factors=analysis.value_factors,
        from_cache=analysis.from_cache,
        analyzed_at=utc_now(),
    )


# -------------------- Investment KI Advice --------------------


@router.post(
    "/spaces/{space_id}/investments/ki-advice",
    response_model=InvestmentKIAdviceResponse,
    summary="KI-gestuetzte Anlageberatung",
)
@limiter.limit("3/minute", key_func=get_user_identifier)
async def get_investment_ki_advice(
    request: Request,
    space_id: uuid.UUID,
    use_cache: bool = Query(True, description="Gecachete Analyse verwenden wenn vorhanden"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> InvestmentKIAdviceResponse:
    """
    KI-gestuetzte Portfolio-Analyse und Anlageberatung:
    - Portfolio-Gesundheitscheck
    - Risikobewertung
    - Diversifikations-Analyse
    - Rebalancing-Empfehlungen
    - Steueroptimierungs-Hinweise (DE)

    HINWEIS: Keine Anlageberatung im rechtlichen Sinne.
    """
    await get_user_space_or_403(db, space_id, current_user, PrivatAccessLevel.READ)

    from app.services.privat import get_privat_ki_prompt_service

    ki_service = get_privat_ki_prompt_service()

    try:
        advice = await ki_service.get_investment_advice(db, space_id, use_cache)
    except Exception as e:
        logger.error("ki_investment_advice_failed", space_id=str(space_id), **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="KI-Analyse derzeit nicht verfuegbar. Bitte spaeter erneut versuchen.",
        )

    return InvestmentKIAdviceResponse(
        space_id=space_id,
        portfolio_health_score=advice.portfolio_health_score,
        risk_assessment=advice.risk_assessment,
        diversification_score=advice.diversification_score,
        recommendations=advice.recommendations,
        rebalancing_needed=advice.rebalancing_needed,
        rebalancing_suggestions=advice.rebalancing_suggestions,
        tax_optimization_hints=advice.tax_optimization_hints,
        projected_annual_return_percent=advice.projected_annual_return_percent,
        risk_warnings=advice.risk_warnings,
        from_cache=advice.from_cache,
        analyzed_at=utc_now(),
    )


# -------------------- Insurance KI Check --------------------


@router.post(
    "/spaces/{space_id}/insurances/ki-check",
    response_model=InsuranceKICheckResponse,
    summary="KI-gestuetzte Versicherungs-Pruefung",
)
@limiter.limit("3/minute", key_func=get_user_identifier)
async def get_insurance_ki_check(
    request: Request,
    space_id: uuid.UUID,
    use_cache: bool = Query(True, description="Gecachete Analyse verwenden wenn vorhanden"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> InsuranceKICheckResponse:
    """
    KI-gestuetzte Versicherungs-Analyse:
    - Deckungsluecken identifizieren
    - Preis-Leistungs-Bewertung
    - Optimierungsvorschlaege
    - Unnoetige Versicherungen erkennen

    Basiert auf deutschen Versicherungsstandards und Marktpreisen.
    """
    await get_user_space_or_403(db, space_id, current_user, PrivatAccessLevel.READ)

    from app.services.privat import get_privat_ki_prompt_service

    ki_service = get_privat_ki_prompt_service()

    try:
        check_result = await ki_service.check_insurance_coverage(db, space_id, use_cache)
    except Exception as e:
        logger.error("ki_insurance_check_failed", space_id=str(space_id), **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="KI-Analyse derzeit nicht verfuegbar. Bitte spaeter erneut versuchen.",
        )

    return InsuranceKICheckResponse(
        space_id=space_id,
        coverage_score=check_result.coverage_score,
        cost_efficiency_score=check_result.cost_efficiency_score,
        critical_gaps=check_result.critical_gaps,
        optimization_suggestions=check_result.optimization_suggestions,
        unnecessary_insurances=check_result.unnecessary_insurances,
        recommended_actions=check_result.recommended_actions,
        overall_assessment=check_result.overall_assessment,
        from_cache=check_result.from_cache,
        analyzed_at=utc_now(),
    )


# -------------------- Financial Q&A Chat --------------------


@router.post(
    "/spaces/{space_id}/financial-qa",
    response_model=FinancialQAAnswerResponse,
    summary="KI-gestuetzter Finanz-Assistent",
)
@limiter.limit("10/minute", key_func=get_user_identifier)
async def financial_qa_chat(
    request: Request,
    space_id: uuid.UUID,
    qa_request: FinancialQARequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> FinancialQAAnswerResponse:
    """
    KI-gestuetzter Finanz-Assistent fuer Privatfragen:
    - Beantwortet Finanzfragen basierend auf Nutzerdaten
    - Beruecksichtigt deutsches Steuer- und Finanzrecht
    - Gibt Handlungsempfehlungen
    - Verweist auf Experten bei komplexen Themen

    HINWEIS: Keine Rechts-, Steuer- oder Anlageberatung.
    """
    await get_user_space_or_403(db, space_id, current_user, PrivatAccessLevel.READ)

    from app.services.privat import get_privat_ki_prompt_service

    ki_service = get_privat_ki_prompt_service()

    try:
        answer = await ki_service.financial_qa(db, space_id, qa_request.question)
    except Exception as e:
        logger.error(
            "ki_financial_qa_failed",
            space_id=str(space_id),
            question_length=len(qa_request.question),
            **safe_error_log(e)
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="KI-Assistent derzeit nicht verfuegbar. Bitte spaeter erneut versuchen.",
        )

    return FinancialQAAnswerResponse(
        space_id=space_id,
        question=qa_request.question,
        answer=answer.answer,
        confidence=answer.confidence,
        sources=answer.sources,
        related_topics=answer.related_topics,
        action_items=answer.action_items,
        warnings=answer.warnings,
        consult_expert=answer.consult_expert,
        expert_type=answer.expert_type,
        analyzed_at=utc_now(),
    )


# =============================================================================
# PREDICTIVE INTELLIGENCE (Phase 1 - PROAKTIV)
# =============================================================================
# Warnt VOR Problemen statt nur zu berichten wenn sie da sind
# =============================================================================


class TrendAnalysisResponse(BaseModel):
    """Trend-Analyse fuer einen KPI."""
    method: str
    direction: str  # rising, falling, stable
    strength: float  # 0-1
    slope: Optional[float] = None
    r_squared: Optional[float] = None
    seasonality_detected: bool
    seasonality_amplitude: Optional[float] = None


class ProjectedValueResponse(BaseModel):
    """Projizierter Wert fuer einen Monat."""
    month: int
    date: str  # ISO date
    value: float
    lower_bound: float
    upper_bound: float
    confidence: float  # 0-1


class ThresholdBreachResponse(BaseModel):
    """Prognostizierter Schwellenwert-Durchbruch."""
    month: int
    date: str
    kpi_name: str
    current_value: float
    projected_value: float
    threshold_value: float
    threshold_type: str  # warning, critical
    severity: str  # WARNING, CRITICAL


class KPIProjectionResponse(BaseModel):
    """Vollstaendige KPI-Projektion."""
    kpi_name: str
    current_value: float
    unit: str
    trend: TrendAnalysisResponse
    projections: List[ProjectedValueResponse]
    threshold_breaches: List[ThresholdBreachResponse]
    data_points_used: int
    generated_at: datetime


class EarlyWarningResponse(BaseModel):
    """Single Early Warning Alert."""
    id: Optional[uuid.UUID] = None
    kpi_name: str
    warning_type: str  # threshold_warning, threshold_critical, trend_warning
    severity: str  # WARNING, CRITICAL
    current_value: float
    projected_value: float
    threshold_value: float
    projected_breach_date: str
    months_until_breach: int
    title: str
    description: str
    recommendation: str
    is_resolved: bool = False
    created_at: Optional[datetime] = None


class PredictiveInsightsResponse(BaseModel):
    """Vollstaendige Predictive Insights Summary."""
    space_id: uuid.UUID
    projections: List[KPIProjectionResponse]
    early_warnings: List[EarlyWarningResponse]
    improving_kpis: List[str]
    declining_kpis: List[str]
    stable_kpis: List[str]
    outlook_score: float  # 0-100 (100 = alles wird besser)
    generated_at: datetime


# -------------------- Predictive Intelligence Endpoints --------------------


@router.get(
    "/spaces/{space_id}/predictive-insights",
    response_model=PredictiveInsightsResponse,
    summary="Vollstaendige Predictive Insights Summary",
)
@limiter.limit("10/minute", key_func=get_user_identifier)
async def get_predictive_insights(
    request: Request,
    space_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PredictiveInsightsResponse:
    """
    Liefert vollstaendige proaktive Insights:

    - **Projektionen**: KPIs 3/6/12 Monate in die Zukunft
    - **Early Warnings**: Warnungen VOR Problemen
    - **Trend-Analyse**: Welche KPIs verbessern/verschlechtern sich
    - **Outlook Score**: 0-100 wie positiv die Prognose ist

    **PROAKTIV**: Zeigt Probleme die der User noch nicht gesehen hat!
    """
    await get_user_space_or_403(db, space_id, current_user, PrivatAccessLevel.READ)

    from app.services.privat import get_predictive_intelligence_service
    import dataclasses

    service = get_predictive_intelligence_service()

    try:
        summary = await service.get_predictive_insights(
            db, space_id, current_user.id
        )
    except Exception as e:
        logger.error(
            "predictive_insights_failed",
            space_id=str(space_id),
            **safe_error_log(e)
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Predictive Intelligence derzeit nicht verfuegbar. Bitte spaeter erneut versuchen.",
        )

    # Convert dataclasses to Pydantic models
    projections = []
    for proj in summary.projections:
        projections.append(KPIProjectionResponse(
            kpi_name=proj.kpi_name,
            current_value=proj.current_value,
            unit=proj.unit,
            trend=TrendAnalysisResponse(
                method=proj.trend.method,
                direction=proj.trend.direction,
                strength=proj.trend.strength,
                slope=proj.trend.slope,
                r_squared=proj.trend.r_squared,
                seasonality_detected=proj.trend.seasonality_detected,
                seasonality_amplitude=proj.trend.seasonality_amplitude,
            ),
            projections=[
                ProjectedValueResponse(
                    month=p.month,
                    date=p.date.isoformat() if hasattr(p.date, 'isoformat') else str(p.date),
                    value=p.value,
                    lower_bound=p.lower_bound,
                    upper_bound=p.upper_bound,
                    confidence=p.confidence,
                )
                for p in proj.projections
            ],
            threshold_breaches=[
                ThresholdBreachResponse(
                    month=b.month,
                    date=b.date.isoformat() if hasattr(b.date, 'isoformat') else str(b.date),
                    kpi_name=b.kpi_name,
                    current_value=b.current_value,
                    projected_value=b.projected_value,
                    threshold_value=b.threshold_value,
                    threshold_type=b.threshold_type,
                    severity=b.severity,
                )
                for b in proj.threshold_breaches
            ],
            data_points_used=proj.data_points_used,
            generated_at=utc_now(),
        ))

    warnings = []
    for w in summary.early_warnings:
        warnings.append(EarlyWarningResponse(
            kpi_name=w.kpi_name,
            warning_type=w.warning_type,
            severity=w.severity,
            current_value=w.current_value,
            projected_value=w.projected_value,
            threshold_value=w.threshold_value,
            projected_breach_date=w.projected_breach_date.isoformat() if hasattr(w.projected_breach_date, 'isoformat') else str(w.projected_breach_date),
            months_until_breach=w.months_until_breach,
            title=w.title,
            description=w.description,
            recommendation=w.recommendation,
        ))

    return PredictiveInsightsResponse(
        space_id=space_id,
        projections=projections,
        early_warnings=warnings,
        improving_kpis=summary.improving_kpis,
        declining_kpis=summary.declining_kpis,
        stable_kpis=summary.stable_kpis,
        outlook_score=summary.outlook_score,
        generated_at=utc_now(),
    )


@router.get(
    "/spaces/{space_id}/projections/{kpi_name}",
    response_model=KPIProjectionResponse,
    summary="KPI-Projektion fuer spezifischen KPI",
)
@limiter.limit("20/minute", key_func=get_user_identifier)
async def get_kpi_projection(
    request: Request,
    space_id: uuid.UUID,
    kpi_name: str,
    months_ahead: int = Query(default=12, ge=1, le=24),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> KPIProjectionResponse:
    """
    Projiziert einen spezifischen KPI in die Zukunft.

    **Verfuegbare KPIs:**
    - financial_health_score
    - dti_ratio (Debt-to-Income)
    - emergency_fund_months
    - net_worth
    - savings_rate
    - diversification_score
    - roi (Return on Investment)

    **months_ahead**: 1-24 Monate in die Zukunft
    """
    await get_user_space_or_403(db, space_id, current_user, PrivatAccessLevel.READ)

    from app.services.privat import get_predictive_intelligence_service

    service = get_predictive_intelligence_service()

    try:
        projection = await service.project_kpi(
            db, space_id, kpi_name, months_ahead, current_user.id
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "KPI-Projektion"),
        )
    except Exception as e:
        logger.error(
            "kpi_projection_failed",
            space_id=str(space_id),
            kpi_name=kpi_name,
            **safe_error_log(e)
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="KPI-Projektion derzeit nicht verfuegbar.",
        )

    return KPIProjectionResponse(
        kpi_name=projection.kpi_name,
        current_value=projection.current_value,
        unit=projection.unit,
        trend=TrendAnalysisResponse(
            method=projection.trend.method,
            direction=projection.trend.direction,
            strength=projection.trend.strength,
            slope=projection.trend.slope,
            r_squared=projection.trend.r_squared,
            seasonality_detected=projection.trend.seasonality_detected,
            seasonality_amplitude=projection.trend.seasonality_amplitude,
        ),
        projections=[
            ProjectedValueResponse(
                month=p.month,
                date=p.date.isoformat() if hasattr(p.date, 'isoformat') else str(p.date),
                value=p.value,
                lower_bound=p.lower_bound,
                upper_bound=p.upper_bound,
                confidence=p.confidence,
            )
            for p in projection.projections
        ],
        threshold_breaches=[
            ThresholdBreachResponse(
                month=b.month,
                date=b.date.isoformat() if hasattr(b.date, 'isoformat') else str(b.date),
                kpi_name=b.kpi_name,
                current_value=b.current_value,
                projected_value=b.projected_value,
                threshold_value=b.threshold_value,
                threshold_type=b.threshold_type,
                severity=b.severity,
            )
            for b in projection.threshold_breaches
        ],
        data_points_used=projection.data_points_used,
        generated_at=utc_now(),
    )


@router.get(
    "/spaces/{space_id}/early-warnings",
    response_model=List[EarlyWarningResponse],
    summary="Aktive Early Warning Alerts",
)
@limiter.limit("30/minute", key_func=get_user_identifier)
async def get_early_warnings(
    request: Request,
    space_id: uuid.UUID,
    include_resolved: bool = Query(default=False),
    severity: Optional[str] = Query(default=None, pattern="^(WARNING|CRITICAL)$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> List[EarlyWarningResponse]:
    """
    Liefert alle aktiven Early Warning Alerts.

    **PROAKTIV**: Warnungen VOR dem Problem!

    - **include_resolved**: Auch bereits geloeste Warnungen zeigen
    - **severity**: Filter nach WARNING oder CRITICAL
    """
    await get_user_space_or_403(db, space_id, current_user, PrivatAccessLevel.READ)

    from sqlalchemy import select, and_
    from app.db.models import PrivatEarlyWarning

    stmt = select(PrivatEarlyWarning).where(
        PrivatEarlyWarning.space_id == space_id
    )

    if not include_resolved:
        stmt = stmt.where(PrivatEarlyWarning.is_resolved == False)

    if severity:
        stmt = stmt.where(PrivatEarlyWarning.severity == severity)

    stmt = stmt.order_by(
        PrivatEarlyWarning.severity.desc(),  # CRITICAL first
        PrivatEarlyWarning.months_until_breach.asc(),  # Soonest first
    )

    result = await db.execute(stmt)
    warnings_db = result.scalars().all()

    return [
        EarlyWarningResponse(
            id=w.id,
            kpi_name=w.kpi_name,
            warning_type=w.warning_type,
            severity=w.severity,
            current_value=float(w.current_value),
            projected_value=float(w.projected_value),
            threshold_value=float(w.threshold_value),
            projected_breach_date=w.projected_breach_date.isoformat(),
            months_until_breach=w.months_until_breach,
            title=w.title,
            description=w.description,
            recommendation=w.recommendation,
            is_resolved=w.is_resolved,
            created_at=w.created_at,
        )
        for w in warnings_db
    ]


@router.post(
    "/spaces/{space_id}/early-warnings/{warning_id}/resolve",
    response_model=EarlyWarningResponse,
    summary="Early Warning als geloest markieren",
)
@limiter.limit("20/minute", key_func=get_user_identifier)
async def resolve_early_warning(
    request: Request,
    space_id: uuid.UUID,
    warning_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> EarlyWarningResponse:
    """
    Markiert eine Early Warning als geloest.

    User hat die empfohlene Aktion durchgefuehrt oder
    das Problem wurde anderweitig addressiert.
    """
    await get_user_space_or_403(db, space_id, current_user, PrivatAccessLevel.MANAGE)

    from sqlalchemy import select
    from app.db.models import PrivatEarlyWarning

    stmt = select(PrivatEarlyWarning).where(
        and_(
            PrivatEarlyWarning.id == warning_id,
            PrivatEarlyWarning.space_id == space_id,
        )
    )

    result = await db.execute(stmt)
    warning = result.scalar_one_or_none()

    if not warning:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Early Warning nicht gefunden.",
        )

    warning.is_resolved = True
    warning.resolved_at = utc_now()
    warning.resolved_by = current_user.id

    await db.commit()
    await db.refresh(warning)

    logger.info(
        "early_warning_resolved",
        warning_id=str(warning_id),
        space_id=str(space_id),
        user_id=str(current_user.id),
        kpi_name=warning.kpi_name,
    )

    return EarlyWarningResponse(
        id=warning.id,
        kpi_name=warning.kpi_name,
        warning_type=warning.warning_type,
        severity=warning.severity,
        current_value=float(warning.current_value),
        projected_value=float(warning.projected_value),
        threshold_value=float(warning.threshold_value),
        projected_breach_date=warning.projected_breach_date.isoformat(),
        months_until_breach=warning.months_until_breach,
        title=warning.title,
        description=warning.description,
        recommendation=warning.recommendation,
        is_resolved=warning.is_resolved,
        created_at=warning.created_at,
    )


# ==================== Portfolio Snapshots ====================


class AssetAllocation(BaseModel):
    """Asset Allocation Detail."""
    real_estate: float = Field(..., description="Immobilien-Anteil in %")
    vehicles: float = Field(..., description="Fahrzeuge-Anteil in %")
    investments: float = Field(..., description="Investments-Anteil in %")
    cash: float = Field(..., description="Bargeld/Konten-Anteil in %")


class PortfolioSnapshotResponse(BaseModel):
    """Portfolio Snapshot Antwort."""
    id: uuid.UUID
    space_id: uuid.UUID
    snapshot_date: date

    # Vermoegenswerte
    total_real_estate: float
    total_vehicles: float
    total_investments: float
    total_cash: float
    total_other_assets: float

    # Verbindlichkeiten
    total_mortgages: float
    total_loans: float
    total_other_liabilities: float

    # Aggregierte Werte
    total_assets: float
    total_liabilities: float
    net_worth: float

    # Veraenderungen
    net_worth_change_absolute: Optional[float] = None
    net_worth_change_percent: Optional[float] = None

    # Kennzahlen
    debt_to_assets_ratio: float
    liquidity_ratio: float

    # Allocation
    asset_allocation: Optional[dict] = None

    created_at: datetime


class PortfolioSummaryResponse(BaseModel):
    """Portfolio Zusammenfassung mit Trend."""
    space_id: uuid.UUID
    latest_snapshot: Optional[PortfolioSnapshotResponse] = None
    snapshot_count: int
    net_worth_trend: List[dict] = Field(default_factory=list, description="Liste von {date, net_worth}")
    created_at: datetime


class NetWorthTrendItem(BaseModel):
    """Einzelner Trend-Datenpunkt."""
    date: date
    net_worth: float


class NetWorthTrendResponse(BaseModel):
    """Nettovermoegen-Trend Antwort."""
    space_id: uuid.UUID
    months: int
    trend_data: List[NetWorthTrendItem]
    trend_direction: str = Field(..., description="up, down, stable")
    total_change_absolute: Optional[float] = None
    total_change_percent: Optional[float] = None


@router.post(
    "/spaces/{space_id}/portfolio/snapshots",
    response_model=PortfolioSnapshotResponse,
    summary="Portfolio-Snapshot erstellen",
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("5/minute", key_func=get_user_identifier)
async def create_portfolio_snapshot(
    request: Request,
    space_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PortfolioSnapshotResponse:
    """
    Erstellt einen neuen Portfolio-Snapshot fuer den Space.

    Aggregiert alle Vermoegenswerte und Verbindlichkeiten:
    - Immobilien (current_value)
    - Fahrzeuge (current_estimated_value)
    - Investments (current_value)
    - Bankkonten (current_balance)
    - Hypotheken und Kredite (remaining_balance)

    Berechnet ausserdem:
    - Nettovermoegen-Veraenderung zum Vormonat
    - Schulden-zu-Vermoegen-Verhaeltnis
    - Liquiditaetsquote
    - Asset Allocation in %
    """
    await get_user_space_or_403(db, space_id, current_user, PrivatAccessLevel.WRITE)

    from app.services.privat.portfolio_service import PortfolioService

    portfolio_service = PortfolioService(db)

    try:
        latest = await portfolio_service.create_monthly_snapshot(space_id)
    except Exception as e:
        logger.error(
            "portfolio_snapshot_creation_failed",
            space_id=str(space_id),
            **safe_error_log(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Portfolio-Snapshot konnte nicht erstellt werden",
        )

    if not latest:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Snapshot wurde erstellt aber konnte nicht geladen werden",
        )

    return PortfolioSnapshotResponse(
        id=latest.id,
        space_id=latest.space_id,
        snapshot_date=latest.snapshot_date,
        total_real_estate=float(latest.total_real_estate),
        total_vehicles=float(latest.total_vehicles),
        total_investments=float(latest.total_investments),
        total_cash=float(latest.total_cash),
        total_other_assets=float(latest.total_other_assets),
        total_mortgages=float(latest.total_mortgages),
        total_loans=float(latest.total_loans),
        total_other_liabilities=float(latest.total_other_liabilities),
        total_assets=float(latest.total_assets),
        total_liabilities=float(latest.total_liabilities),
        net_worth=float(latest.net_worth),
        net_worth_change_absolute=float(latest.net_worth_change_absolute) if latest.net_worth_change_absolute else None,
        net_worth_change_percent=float(latest.net_worth_change_percent) if latest.net_worth_change_percent else None,
        debt_to_assets_ratio=float(latest.debt_to_assets_ratio),
        liquidity_ratio=float(latest.liquidity_ratio),
        asset_allocation=latest.asset_allocation,
        created_at=latest.created_at,
    )


@router.get(
    "/spaces/{space_id}/portfolio/snapshots",
    response_model=List[PortfolioSnapshotResponse],
    summary="Historische Portfolio-Snapshots abrufen",
)
@limiter.limit("30/minute", key_func=get_user_identifier)
async def get_portfolio_snapshots(
    request: Request,
    space_id: uuid.UUID,
    months: int = Query(12, ge=1, le=120, description="Anzahl Monate zurueck"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> List[PortfolioSnapshotResponse]:
    """
    Laedt historische Portfolio-Snapshots fuer einen Space.

    Gibt die Snapshots der letzten X Monate zurueck,
    sortiert nach Datum (neueste zuerst).
    """
    await get_user_space_or_403(db, space_id, current_user, PrivatAccessLevel.READ)

    from app.services.privat.portfolio_service import PortfolioService

    portfolio_service = PortfolioService(db)
    snapshots = await portfolio_service.get_portfolio_history(space_id, months)

    return [
        PortfolioSnapshotResponse(
            id=s.id,
            space_id=s.space_id,
            snapshot_date=s.snapshot_date,
            total_real_estate=float(s.total_real_estate),
            total_vehicles=float(s.total_vehicles),
            total_investments=float(s.total_investments),
            total_cash=float(s.total_cash),
            total_other_assets=float(s.total_other_assets),
            total_mortgages=float(s.total_mortgages),
            total_loans=float(s.total_loans),
            total_other_liabilities=float(s.total_other_liabilities),
            total_assets=float(s.total_assets),
            total_liabilities=float(s.total_liabilities),
            net_worth=float(s.net_worth),
            net_worth_change_absolute=float(s.net_worth_change_absolute) if s.net_worth_change_absolute else None,
            net_worth_change_percent=float(s.net_worth_change_percent) if s.net_worth_change_percent else None,
            debt_to_assets_ratio=float(s.debt_to_assets_ratio),
            liquidity_ratio=float(s.liquidity_ratio),
            asset_allocation=s.asset_allocation,
            created_at=s.created_at,
        )
        for s in snapshots
    ]


@router.get(
    "/spaces/{space_id}/portfolio/snapshots/latest",
    response_model=PortfolioSnapshotResponse,
    summary="Neuesten Portfolio-Snapshot abrufen",
)
@limiter.limit("60/minute", key_func=get_user_identifier)
async def get_latest_portfolio_snapshot(
    request: Request,
    space_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PortfolioSnapshotResponse:
    """
    Laedt den neuesten Portfolio-Snapshot fuer einen Space.

    Falls kein Snapshot existiert, wird ein 404 zurueckgegeben.
    """
    await get_user_space_or_403(db, space_id, current_user, PrivatAccessLevel.READ)

    from app.services.privat.portfolio_service import PortfolioService

    portfolio_service = PortfolioService(db)
    latest = await portfolio_service.get_latest_snapshot(space_id)

    if not latest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kein Portfolio-Snapshot vorhanden. Bitte zuerst einen erstellen.",
        )

    return PortfolioSnapshotResponse(
        id=latest.id,
        space_id=latest.space_id,
        snapshot_date=latest.snapshot_date,
        total_real_estate=float(latest.total_real_estate),
        total_vehicles=float(latest.total_vehicles),
        total_investments=float(latest.total_investments),
        total_cash=float(latest.total_cash),
        total_other_assets=float(latest.total_other_assets),
        total_mortgages=float(latest.total_mortgages),
        total_loans=float(latest.total_loans),
        total_other_liabilities=float(latest.total_other_liabilities),
        total_assets=float(latest.total_assets),
        total_liabilities=float(latest.total_liabilities),
        net_worth=float(latest.net_worth),
        net_worth_change_absolute=float(latest.net_worth_change_absolute) if latest.net_worth_change_absolute else None,
        net_worth_change_percent=float(latest.net_worth_change_percent) if latest.net_worth_change_percent else None,
        debt_to_assets_ratio=float(latest.debt_to_assets_ratio),
        liquidity_ratio=float(latest.liquidity_ratio),
        asset_allocation=latest.asset_allocation,
        created_at=latest.created_at,
    )


@router.get(
    "/spaces/{space_id}/portfolio/net-worth-trend",
    response_model=NetWorthTrendResponse,
    summary="Nettovermoegen-Trend abrufen",
)
@limiter.limit("30/minute", key_func=get_user_identifier)
async def get_net_worth_trend(
    request: Request,
    space_id: uuid.UUID,
    months: int = Query(12, ge=1, le=120, description="Anzahl Monate zurueck"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> NetWorthTrendResponse:
    """
    Laedt den Nettovermoegen-Trend fuer einen Space.

    Gibt eine Liste von (Datum, Nettovermoegen) Tupeln zurueck,
    sowie Trend-Richtung und Gesamtveraenderung.
    """
    await get_user_space_or_403(db, space_id, current_user, PrivatAccessLevel.READ)

    from app.services.privat.portfolio_service import PortfolioService
    from datetime import datetime as dt

    portfolio_service = PortfolioService(db)
    trend_data = await portfolio_service.get_net_worth_trend(space_id, months)

    if not trend_data:
        return NetWorthTrendResponse(
            space_id=space_id,
            months=months,
            trend_data=[],
            trend_direction="stable",
            total_change_absolute=None,
            total_change_percent=None,
        )

    # Trend-Daten formatieren (service returns list of dicts)
    items = [
        NetWorthTrendItem(
            date=dt.fromisoformat(item["date"]).date(),
            net_worth=item["net_worth"]
        )
        for item in trend_data
    ]

    # Trend-Richtung und Veraenderung berechnen
    first_value = trend_data[0]["net_worth"] if trend_data else 0.0
    last_value = trend_data[-1]["net_worth"] if trend_data else 0.0

    total_change = last_value - first_value
    total_change_percent = None
    if first_value and first_value != 0:
        total_change_percent = (total_change / first_value) * 100

    if total_change > 1000:
        trend_direction = "up"
    elif total_change < -1000:
        trend_direction = "down"
    else:
        trend_direction = "stable"

    return NetWorthTrendResponse(
        space_id=space_id,
        months=months,
        trend_data=items,
        trend_direction=trend_direction,
        total_change_absolute=total_change,
        total_change_percent=total_change_percent,
    )


@router.post(
    "/spaces/{space_id}/portfolio/snapshots/trigger",
    response_model=TaskTriggerResponse,
    summary="Portfolio-Snapshot im Hintergrund erstellen",
)
@limiter.limit("2/minute", key_func=get_user_identifier)
async def trigger_portfolio_snapshot(
    request: Request,
    space_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> TaskTriggerResponse:
    """
    Startet die Portfolio-Snapshot-Erstellung als Hintergrund-Task.

    Nuetzlich fuer grosse Spaces mit vielen Assets,
    wo die Berechnung laenger dauern kann.
    """
    await get_user_space_or_403(db, space_id, current_user, PrivatAccessLevel.WRITE)

    from app.workers.tasks.privat_tasks import create_monthly_portfolio_snapshot

    task = create_monthly_portfolio_snapshot.delay(space_id=str(space_id))

    logger.info(
        "portfolio_snapshot_task_triggered",
        space_id=str(space_id),
        task_id=task.id,
        user_id=str(current_user.id),
    )

    return TaskTriggerResponse(
        task_id=task.id,
        status="queued",
        message="Portfolio-Snapshot Erstellung gestartet",
    )

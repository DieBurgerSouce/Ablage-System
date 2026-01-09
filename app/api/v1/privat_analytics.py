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
from decimal import Decimal
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Depends, status, Query, Request, BackgroundTasks
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.api.dependencies import get_db, get_current_active_user
from app.core.rate_limiting import limiter, get_user_identifier
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
        calculated_at=datetime.utcnow(),
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
        calculated_at=datetime.utcnow(),
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
        analyzed_at=datetime.utcnow(),
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
        generated_at=datetime.utcnow(),
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
        analyzed_at=datetime.utcnow(),
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
        calculated_at=datetime.utcnow(),
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
        calculated_at=datetime.utcnow(),
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
        analyzed_at=datetime.utcnow(),
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
        analyzed_at=datetime.utcnow(),
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
        generated_at=datetime.utcnow(),
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
        calculated_at=datetime.utcnow(),
    )

    diversification_response = DiversificationResponse(
        space_id=space_id,
        herfindahl_index=float(analytics.diversification.herfindahl_index),
        diversification_score=float(analytics.diversification.diversification_score),
        rating=analytics.diversification.rating,
        largest_position_percent=float(analytics.diversification.largest_position_percent),
        recommendation=analytics.diversification.recommendation,
        analyzed_at=datetime.utcnow(),
    )

    risk_response = RiskProfileResponse(
        space_id=space_id,
        overall_risk_score=float(analytics.risk_profile.overall_risk_score),
        risk_category=analytics.risk_profile.risk_category,
        target_profile=analytics.risk_profile.target_profile,
        deviation_from_target=float(analytics.risk_profile.deviation_from_target) if analytics.risk_profile.deviation_from_target else None,
        recommendation=analytics.risk_profile.recommendation,
        analyzed_at=datetime.utcnow(),
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
            generated_at=datetime.utcnow(),
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
        analyzed_at=datetime.utcnow(),
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
        calculated_at=datetime.utcnow(),
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
        calculated_at=datetime.utcnow(),
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
            generated_at=datetime.utcnow(),
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
        generated_at=datetime.utcnow(),
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
        calculated_at=datetime.utcnow(),
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
        calculated_at=datetime.utcnow(),
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
        calculated_at=datetime.utcnow(),
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
        generated_at=datetime.utcnow(),
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
        generated_at=datetime.utcnow(),
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

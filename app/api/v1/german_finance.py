# -*- coding: utf-8 -*-
"""
Deutsche Finanz-Feature API Endpoints.

Feature #11: REST API fuer:
- USt-Voranmeldung (Umsatzsteuer-Voranmeldung)
- BWA (Betriebswirtschaftliche Auswertung)
- Cashflow-Prognose mit Szenarien

Feinpoliert und durchdacht - Enterprise-grade Deutsche Finanzberichterstattung.
"""

from datetime import date
from typing import Dict, List, Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.api.dependencies import get_db, get_current_active_user, validate_company_access
from app.core.safe_errors import safe_error_detail, safe_error_log
from app.db.models_german_finance import BWAPeriod, SKRSchema
from app.services.finance.ust_voranmeldung_service import get_ust_voranmeldung_service
from app.services.finance.bwa_service import get_bwa_service
from app.services.finance.cashflow_forecast_service import get_cashflow_forecast_service

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/finance/de", tags=["Deutsche Finanzen"])


# =============================================================================
# PYDANTIC SCHEMAS
# =============================================================================


# --- USt-Voranmeldung Schemas ---


class UStVoranmeldungResponse(BaseModel):
    """Response-Schema fuer USt-Voranmeldung."""

    id: str
    company_id: str
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    period_type: Optional[str] = None
    vorsteuer_summe: float = 0.0
    umsatzsteuer_summe: float = 0.0
    zahllast: float = 0.0
    steuerfrei_inland: float = 0.0
    steuerfrei_export: float = 0.0
    innergemeinschaftliche_lieferungen: float = 0.0
    vorsteuer_details: Optional[Dict[str, object]] = None
    umsatzsteuer_details: Optional[Dict[str, object]] = None
    status: Optional[str] = None
    elster_xml: Optional[bool] = None
    notes: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class UStVoranmeldungCalculateRequest(BaseModel):
    """Request-Schema fuer USt-Voranmeldung Berechnung."""

    company_id: str = Field(..., description="Firmen-UUID")
    year: int = Field(..., ge=2020, le=2099, description="Steuerjahr")
    month: Optional[int] = Field(None, ge=1, le=12, description="Monat (1-12)")
    quarter: Optional[int] = Field(None, ge=1, le=4, description="Quartal (1-4)")


class TaxRateBreakdownResponse(BaseModel):
    """Response-Schema fuer Steuersatz-Aufschluesselung."""

    period_start: str
    period_end: str
    vorsteuer: Dict[str, float]
    umsatzsteuer: Dict[str, float]
    vorsteuer_summe: float
    umsatzsteuer_summe: float
    zahllast: float
    innergemeinschaftliche_lieferungen: float


# --- BWA Schemas ---


class BWAReportResponse(BaseModel):
    """Response-Schema fuer BWA."""

    id: str
    company_id: str
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    period_type: Optional[str] = None
    skr_schema: Optional[str] = None
    erloese: Optional[Dict[str, object]] = None
    materialaufwand: Optional[Dict[str, object]] = None
    personalaufwand: Optional[Dict[str, object]] = None
    sonstige_aufwendungen: Optional[Dict[str, object]] = None
    abschreibungen: Optional[Dict[str, object]] = None
    betriebsergebnis: float = 0.0
    finanzergebnis: float = 0.0
    ergebnis_vor_steuern: float = 0.0
    steuern: float = 0.0
    jahresueberschuss: float = 0.0
    vorjahresvergleich: Optional[Dict[str, object]] = None
    status: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class BWAGenerateRequest(BaseModel):
    """Request-Schema fuer BWA-Generierung."""

    company_id: str = Field(..., description="Firmen-UUID")
    year: int = Field(..., ge=2020, le=2099, description="Geschaeftsjahr")
    month: Optional[int] = Field(None, ge=1, le=12, description="Geschaeftsmonat")
    quarter: Optional[int] = Field(None, ge=1, le=4, description="Geschaeftsquartal")
    skr_schema: str = Field(default="SKR03", description="SKR03 oder SKR04")
    period_type: str = Field(
        default="monthly",
        description="Zeitraum: monthly, quarterly, yearly",
    )


# --- Cashflow Forecast Schemas ---


class CashflowForecastResponse(BaseModel):
    """Response-Schema fuer Cashflow-Prognose."""

    id: str
    company_id: str
    forecast_date: Optional[str] = None
    forecast_generated_at: Optional[str] = None
    horizon_days: int = 90
    predicted_balance: float = 0.0
    confidence_lower: Optional[float] = None
    confidence_upper: Optional[float] = None
    einnahmen_prognose: float = 0.0
    ausgaben_prognose: float = 0.0
    offene_forderungen: float = 0.0
    offene_verbindlichkeiten: float = 0.0
    saisonaler_faktor: Optional[float] = None
    warnung_liquiditaetsengpass: bool = False
    engpass_datum: Optional[str] = None
    scenario_type: Optional[str] = None
    scenario_config: Optional[Dict[str, object]] = None
    created_at: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class CashflowGenerateRequest(BaseModel):
    """Request-Schema fuer Cashflow-Prognose."""

    company_id: str = Field(..., description="Firmen-UUID")
    horizon_days: int = Field(
        default=90, ge=7, le=365, description="Prognosehorizont in Tagen"
    )
    scenario_type: str = Field(
        default="basis",
        description="basis, optimistisch, pessimistisch, wenn_kunde_nicht_zahlt",
    )
    scenario_config: Optional[Dict[str, object]] = None


class WhatIfRequest(BaseModel):
    """Request-Schema fuer Was-waere-wenn-Szenario."""

    company_id: str = Field(..., description="Firmen-UUID")
    base_forecast_id: str = Field(..., description="Basis-Prognose-UUID")
    modifications: Dict[str, object]


class PaymentBehaviorResponse(BaseModel):
    """Response-Schema fuer Zahlungsverhalten-Analyse."""

    company_id: str
    entity_id: Optional[str] = None
    analyse_zeitraum_tage: int = 365
    anzahl_rechnungen: int = 0
    durchschnittliche_zahlungsdauer_tage: float = 0.0
    median_zahlungsdauer_tage: float = 0.0
    puenktlich_bezahlt_prozent: float = 0.0
    ueberfaellig_bezahlt_prozent: float = 0.0
    message: Optional[str] = None


# =============================================================================
# UST-VORANMELDUNG ENDPOINTS
# =============================================================================


@router.post(
    "/ust-va/calculate",
    response_model=UStVoranmeldungResponse,
    status_code=status.HTTP_201_CREATED,
    summary="USt-Voranmeldung berechnen",
    description="Berechnet die USt-Voranmeldung fuer einen Monat oder Quartal.",
)
async def calculate_ust_voranmeldung(
    request: UStVoranmeldungCalculateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> UStVoranmeldungResponse:
    """Berechnet USt-Voranmeldung fuer den angegebenen Zeitraum."""
    company_id = UUID(request.company_id)
    validate_company_access(company_id, current_user)

    service = get_ust_voranmeldung_service()

    try:
        va = await service.calculate_period(
            db=db,
            company_id=company_id,
            year=request.year,
            month=request.month,
            quarter=request.quarter,
        )
        return UStVoranmeldungResponse(**va.to_dict())
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error("ust_va_calculate_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="USt-Voranmeldung konnte nicht berechnet werden",
        )


@router.get(
    "/ust-va/{report_id}",
    response_model=UStVoranmeldungResponse,
    summary="USt-Voranmeldung abrufen",
)
async def get_ust_voranmeldung(
    report_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> UStVoranmeldungResponse:
    """Einzelne USt-Voranmeldung abrufen."""
    service = get_ust_voranmeldung_service()

    report = await service.get_report(db, report_id)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="USt-Voranmeldung nicht gefunden",
        )

    validate_company_access(report.company_id, current_user)
    return UStVoranmeldungResponse(**report.to_dict())


@router.get(
    "/ust-va",
    response_model=List[UStVoranmeldungResponse],
    summary="USt-Voranmeldungen auflisten",
    description="Alle USt-Voranmeldungen fuer ein bestimmtes Jahr.",
)
async def list_ust_voranmeldungen(
    company_id: UUID = Query(..., description="Firmen-UUID"),
    year: int = Query(..., ge=2020, le=2099, description="Steuerjahr"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> List[UStVoranmeldungResponse]:
    """Alle USt-Voranmeldungen fuer ein Jahr auflisten."""
    validate_company_access(company_id, current_user)

    service = get_ust_voranmeldung_service()
    reports = await service.list_reports(db, company_id, year)
    return [UStVoranmeldungResponse(**r.to_dict()) for r in reports]


@router.post(
    "/ust-va/{report_id}/elster-xml",
    summary="ELSTER-XML generieren",
    description="Generiert ELSTER-kompatibles XML fuer eine USt-Voranmeldung.",
)
async def generate_elster_xml(
    report_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, str]:
    """ELSTER-XML fuer eine USt-VA generieren."""
    service = get_ust_voranmeldung_service()

    # Zugriffspruefung
    report = await service.get_report(db, report_id)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="USt-Voranmeldung nicht gefunden",
        )
    validate_company_access(report.company_id, current_user)

    try:
        xml_str = await service.generate_elster_xml(db, report_id)
        return {"xml": xml_str, "report_id": str(report_id)}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.error("elster_xml_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="ELSTER-XML konnte nicht generiert werden",
        )


@router.get(
    "/ust-va/{report_id}/validate",
    summary="USt-Voranmeldung validieren",
    description="Validiert eine USt-VA gegen DATEV-Buchungen.",
)
async def validate_ust_voranmeldung(
    report_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, object]:
    """USt-VA validieren und mit DATEV abgleichen."""
    service = get_ust_voranmeldung_service()

    report = await service.get_report(db, report_id)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="USt-Voranmeldung nicht gefunden",
        )
    validate_company_access(report.company_id, current_user)

    try:
        return await service.validate_report(db, report_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.get(
    "/ust-va/tax-breakdown",
    response_model=TaxRateBreakdownResponse,
    summary="Steuersatz-Aufschluesselung",
    description="Detaillierte Aufschluesselung der Steuerbetraege nach Steuersatz.",
)
async def get_tax_rate_breakdown(
    company_id: UUID = Query(..., description="Firmen-UUID"),
    period_start: date = Query(..., description="Beginn des Zeitraums"),
    period_end: date = Query(..., description="Ende des Zeitraums"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> TaxRateBreakdownResponse:
    """Steuersatz-Aufschluesselung fuer einen Zeitraum."""
    validate_company_access(company_id, current_user)

    service = get_ust_voranmeldung_service()
    result = await service.get_tax_rate_breakdown(
        db, company_id, period_start, period_end
    )
    return TaxRateBreakdownResponse(**result)


# =============================================================================
# BWA ENDPOINTS
# =============================================================================


@router.post(
    "/bwa/generate",
    response_model=BWAReportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="BWA generieren",
    description="Generiert eine BWA nach SKR03/SKR04 fuer einen Zeitraum.",
)
async def generate_bwa(
    request: BWAGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> BWAReportResponse:
    """BWA generieren fuer den angegebenen Zeitraum."""
    company_id = UUID(request.company_id)
    validate_company_access(company_id, current_user)

    try:
        skr = SKRSchema(request.skr_schema)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ungueltiger Kontenrahmen: {request.skr_schema}. Erlaubt: SKR03, SKR04",
        )

    try:
        period = BWAPeriod(request.period_type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Ungueltiger Zeitraumtyp: {request.period_type}. "
                "Erlaubt: monthly, quarterly, yearly"
            ),
        )

    service = get_bwa_service()

    try:
        bwa = await service.generate_bwa(
            db=db,
            company_id=company_id,
            skr_schema=skr,
            period_type=period,
            year=request.year,
            month=request.month,
            quarter=request.quarter,
        )
        return BWAReportResponse(**bwa.to_dict())
    except Exception as e:
        logger.error("bwa_generate_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="BWA konnte nicht generiert werden",
        )


@router.get(
    "/bwa/{report_id}",
    response_model=BWAReportResponse,
    summary="BWA abrufen",
)
async def get_bwa_report(
    report_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> BWAReportResponse:
    """Einzelnen BWA-Report abrufen."""
    service = get_bwa_service()

    report = await service.get_bwa(db, report_id)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="BWA-Report nicht gefunden",
        )

    validate_company_access(report.company_id, current_user)
    return BWAReportResponse(**report.to_dict())


@router.get(
    "/bwa",
    response_model=List[BWAReportResponse],
    summary="BWA-Reports auflisten",
    description="Alle BWA-Reports fuer ein bestimmtes Jahr.",
)
async def list_bwa_reports(
    company_id: UUID = Query(..., description="Firmen-UUID"),
    year: int = Query(..., ge=2020, le=2099, description="Geschaeftsjahr"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> List[BWAReportResponse]:
    """Alle BWA-Reports fuer ein Jahr auflisten."""
    validate_company_access(company_id, current_user)

    service = get_bwa_service()
    reports = await service.list_bwa_reports(db, company_id, year)
    return [BWAReportResponse(**r.to_dict()) for r in reports]


@router.get(
    "/bwa/{report_id}/export-pdf",
    summary="BWA als PDF exportieren",
    description="Generiert eine PDF-ready Datenstruktur fuer einen BWA-Report.",
)
async def export_bwa_pdf(
    report_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, object]:
    """BWA-Report als PDF-Datenstruktur exportieren."""
    service = get_bwa_service()

    report = await service.get_bwa(db, report_id)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="BWA-Report nicht gefunden",
        )
    validate_company_access(report.company_id, current_user)

    try:
        return await service.export_pdf(db, report_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.get(
    "/bwa/compare",
    summary="BWA-Perioden vergleichen",
    description="Vergleicht zwei BWA-Perioden side-by-side mit Abweichungsanalyse.",
)
async def compare_bwa_periods(
    company_id: UUID = Query(..., description="Firmen-UUID"),
    period_a_start: date = Query(..., description="Periode A Start"),
    period_a_end: date = Query(..., description="Periode A Ende"),
    period_b_start: date = Query(..., description="Periode B Start"),
    period_b_end: date = Query(..., description="Periode B Ende"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, object]:
    """BWA-Perioden vergleichen."""
    validate_company_access(company_id, current_user)

    service = get_bwa_service()
    return await service.compare_periods(
        db, company_id,
        period_a_start, period_a_end,
        period_b_start, period_b_end,
    )


@router.get(
    "/bwa/{bwa_id}/comparison",
    summary="BWA Vorjahresvergleich",
    description="Vergleicht eine BWA mit den Vorjahresdaten.",
)
async def get_bwa_comparison(
    bwa_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, object]:
    """BWA mit Vorjahr vergleichen."""
    service = get_bwa_service()

    report = await service.get_bwa(db, bwa_id)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="BWA-Report nicht gefunden",
        )
    validate_company_access(report.company_id, current_user)

    try:
        return await service.generate_comparison(db, report.company_id, bwa_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


# =============================================================================
# CASHFLOW FORECAST ENDPOINTS
# =============================================================================


@router.post(
    "/cashflow/forecast",
    response_model=CashflowForecastResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Cashflow-Prognose generieren",
    description=(
        "Generiert eine Cashflow-Prognose basierend auf offenen Rechnungen, "
        "Zahlungsverhalten und saisonalen Mustern."
    ),
)
async def generate_cashflow_forecast(
    request: CashflowGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> CashflowForecastResponse:
    """Cashflow-Prognose generieren."""
    company_id = UUID(request.company_id)
    validate_company_access(company_id, current_user)

    service = get_cashflow_forecast_service()

    try:
        forecast = await service.generate_forecast(
            db=db,
            company_id=company_id,
            horizon_days=request.horizon_days,
            scenario_type=request.scenario_type,
            scenario_config=request.scenario_config,
        )
        return CashflowForecastResponse(**forecast.to_dict())
    except Exception as e:
        logger.error("cashflow_forecast_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Cashflow-Prognose konnte nicht erstellt werden",
        )


@router.get(
    "/cashflow/forecasts",
    response_model=List[CashflowForecastResponse],
    summary="Cashflow-Prognosen abrufen",
    description="Ruft Cashflow-Prognosen fuer einen optionalen Zeitraum ab.",
)
async def get_cashflow_forecasts(
    company_id: UUID = Query(..., description="Firmen-UUID"),
    from_date: Optional[date] = Query(None, description="Startdatum"),
    to_date: Optional[date] = Query(None, description="Enddatum"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> List[CashflowForecastResponse]:
    """Cashflow-Prognosen fuer einen Zeitraum abrufen."""
    validate_company_access(company_id, current_user)

    service = get_cashflow_forecast_service()
    forecasts = await service.get_forecast(db, company_id, from_date, to_date)
    return [CashflowForecastResponse(**f.to_dict()) for f in forecasts]


@router.get(
    "/cashflow/warnings",
    response_model=List[CashflowForecastResponse],
    summary="Liquiditaetswarnungen",
    description="Alle Prognosen mit Liquiditaetsengpass-Warnung.",
)
async def get_liquidity_warnings(
    company_id: UUID = Query(..., description="Firmen-UUID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> List[CashflowForecastResponse]:
    """Alle Liquiditaetswarnungen abrufen."""
    validate_company_access(company_id, current_user)

    service = get_cashflow_forecast_service()
    warnings = await service.get_liquidity_warnings(db, company_id)
    return [CashflowForecastResponse(**w.to_dict()) for w in warnings]


@router.post(
    "/cashflow/scenario",
    response_model=CashflowForecastResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Was-waere-wenn-Szenario",
    description=(
        "Erstellt eine Cashflow-Prognose fuer ein spezifisches Szenario. "
        "Unterstuetzt: basis, optimistisch, pessimistisch, wenn_kunde_nicht_zahlt."
    ),
)
async def generate_cashflow_scenario(
    request: CashflowGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> CashflowForecastResponse:
    """Szenario-Prognose generieren."""
    company_id = UUID(request.company_id)
    validate_company_access(company_id, current_user)

    service = get_cashflow_forecast_service()

    try:
        forecast = await service.generate_scenario(
            db=db,
            company_id=company_id,
            scenario_type=request.scenario_type,
            scenario_config=request.scenario_config,
            horizon_days=request.horizon_days,
        )
        return CashflowForecastResponse(**forecast.to_dict())
    except Exception as e:
        logger.error("cashflow_scenario_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Szenario konnte nicht generiert werden",
        )


@router.post(
    "/cashflow/what-if",
    response_model=CashflowForecastResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Was-waere-wenn mit Basis-Prognose",
    description="Erstellt ein Was-waere-wenn-Szenario basierend auf einer bestehenden Prognose.",
)
async def what_if_scenario(
    request: WhatIfRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> CashflowForecastResponse:
    """Was-waere-wenn-Szenario mit Basis-Prognose."""
    company_id = UUID(request.company_id)
    validate_company_access(company_id, current_user)

    service = get_cashflow_forecast_service()

    try:
        forecast = await service.what_if_scenario(
            db=db,
            company_id=company_id,
            base_forecast_id=UUID(request.base_forecast_id),
            modifications=request.modifications,
        )
        return CashflowForecastResponse(**forecast.to_dict())
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.error("what_if_scenario_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Was-waere-wenn-Szenario fehlgeschlagen",
        )


@router.get(
    "/cashflow/seasonal-factors",
    summary="Saisonale Faktoren",
    description="Saisonale Korrekturfaktoren fuer alle 12 Monate.",
)
async def get_seasonal_factors(
    company_id: UUID = Query(..., description="Firmen-UUID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, float]:
    """Saisonale Faktoren fuer alle Monate abrufen."""
    validate_company_access(company_id, current_user)

    service = get_cashflow_forecast_service()
    return await service.get_seasonal_factors(db, company_id)


@router.get(
    "/cashflow/payment-behavior",
    response_model=PaymentBehaviorResponse,
    summary="Zahlungsverhalten analysieren",
    description=(
        "Analysiert das historische Zahlungsverhalten fuer eine Firma "
        "oder eine spezifische Entity (Kunde/Lieferant)."
    ),
)
async def get_payment_behavior(
    company_id: UUID = Query(..., description="Firmen-UUID"),
    entity_id: Optional[UUID] = Query(None, description="Entity-UUID (optional)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PaymentBehaviorResponse:
    """Zahlungsverhalten analysieren."""
    validate_company_access(company_id, current_user)

    service = get_cashflow_forecast_service()
    result = await service.get_payment_behavior_analysis(db, company_id, entity_id)
    return PaymentBehaviorResponse(**result)


@router.get(
    "/cashflow/{forecast_id}/accuracy",
    summary="Prognose-Genauigkeit",
    description="Vergleicht eine Cashflow-Prognose mit den tatsaechlichen Werten.",
)
async def get_forecast_accuracy(
    forecast_id: UUID,
    company_id: UUID = Query(..., description="Firmen-UUID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, object]:
    """Prognose-Genauigkeit evaluieren."""
    validate_company_access(company_id, current_user)

    service = get_cashflow_forecast_service()

    try:
        return await service.compare_forecast_accuracy(db, company_id, forecast_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )

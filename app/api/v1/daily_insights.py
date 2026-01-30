# -*- coding: utf-8 -*-
"""
Daily Insights API Endpoints.

Vision 2026 Q4: Proactive Insights System.

Batch-generierte Insights die BEVOR Probleme entstehen warnen:
- GET  /daily-insights             - Alle täglichen Insights abrufen
- GET  /daily-insights/cashflow    - Cashflow-Warnungen
- GET  /daily-insights/contracts   - Vertragsablauf-Warnungen
- GET  /daily-insights/payments    - Zahlungsrisiko-Warnungen
- GET  /daily-insights/skonto      - Skonto-Fristen
- GET  /daily-insights/compliance  - Compliance-Erinnerungen
- GET  /daily-insights/overdue     - Überfällige Rechnungen
- POST /daily-insights/generate    - Insights manuell generieren (Admin)
- GET  /daily-insights/config      - Generator-Konfiguration abrufen
- PATCH /daily-insights/config     - Generator-Konfiguration ändern
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_active_user, get_db, get_current_admin_user
from app.core.rate_limiting import limiter, get_user_identifier
from app.db.models import User
from app.services.insights.daily_insights_engine import (
    get_daily_insights_engine,
    DailyInsight,
    DailyInsightType,
    InsightSeverity,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/daily-insights", tags=["Daily Insights"])


# =============================================================================
# Pydantic Schemas
# =============================================================================

class InsightFactorResponse(BaseModel):
    """Ein Faktor der zur Insight-Entscheidung beiträgt."""
    name: str = Field(..., description="Name des Faktors")
    contribution: float = Field(..., description="Beitrag zur Entscheidung (0-1)")
    value: str = Field(..., description="Wert des Faktors")
    explanation: str = Field(..., description="Erklärung des Faktors")


class DailyInsightResponse(BaseModel):
    """Ein täglich generierter Insight."""
    id: str = Field(..., description="Insight-ID")
    insight_type: str = Field(..., description="Typ des Insights")
    severity: str = Field(..., description="Schweregrad (critical, high, medium, low)")
    title: str = Field(..., description="Titel")
    message: str = Field(..., description="Hauptnachricht")
    explanation: str = Field(default="", description="Detaillierte Erklärung")
    recommendation: str = Field(default="", description="Handlungsempfehlung")
    factors: List[InsightFactorResponse] = Field(
        default=[], description="Beitragende Faktoren"
    )
    confidence: float = Field(..., description="Konfidenz (0-1)")
    impact_value: Optional[float] = Field(None, description="Geschätzter Impact in EUR")
    deadline: Optional[str] = Field(None, description="Relevante Frist")
    related_entity_id: Optional[str] = Field(None, description="Verknüpfte Entity-ID")
    related_entity_name: Optional[str] = Field(None, description="Verknüpfter Entity-Name")
    related_document_id: Optional[str] = Field(None, description="Verknüpfte Dokument-ID")
    action_url: Optional[str] = Field(None, description="URL zur Aktion")
    created_at: str = Field(..., description="Erstellungszeitpunkt")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "id": "insight-cashflow-2026-01-28",
            "insight_type": "cashflow_warning",
            "severity": "high",
            "title": "Liquiditätsengpass in 14 Tagen möglich",
            "message": "Am 11.02.2026 könnte die Liquidität auf -2.500€ sinken.",
            "explanation": "Basierend auf offenen Rechnungen und erwarteten Ausgaben.",
            "recommendation": "Zahlungseingänge beschleunigen oder Zahlungen verschieben.",
            "confidence": 0.85,
            "impact_value": 2500.0,
            "deadline": "2026-02-11",
            "created_at": "2026-01-28T06:00:00Z",
        }
    })


class DailyInsightListResponse(BaseModel):
    """Liste von Daily Insights mit Metadaten."""
    insights: List[DailyInsightResponse] = Field(..., description="Liste der Insights")
    total_count: int = Field(..., description="Gesamtanzahl")
    by_severity: Dict[str, int] = Field(
        default_factory=dict, description="Anzahl nach Schweregrad"
    )
    by_type: Dict[str, int] = Field(
        default_factory=dict, description="Anzahl nach Typ"
    )
    generated_at: Optional[str] = Field(None, description="Zeitpunkt der Generierung")


class InsightGenerationRequest(BaseModel):
    """Request für manuelle Insight-Generierung."""
    insight_types: Optional[List[str]] = Field(
        None, description="Zu generierende Insight-Typen (None = alle)"
    )
    days_ahead: int = Field(30, ge=7, le=90, description="Tage in die Zukunft")


class InsightGenerationResponse(BaseModel):
    """Response nach Insight-Generierung."""
    success: bool = Field(..., description="Generierung erfolgreich")
    total_generated: int = Field(..., description="Anzahl generierter Insights")
    by_type: Dict[str, int] = Field(
        default_factory=dict, description="Generiert nach Typ"
    )
    duration_ms: int = Field(..., description="Dauer in Millisekunden")


class GeneratorConfigResponse(BaseModel):
    """Konfiguration eines Insight-Generators."""
    name: str = Field(..., description="Generator-Name")
    enabled: bool = Field(..., description="Aktiviert")
    priority: int = Field(..., description="Priorität")
    max_insights: int = Field(..., description="Maximale Insights")
    description: str = Field(default="", description="Beschreibung")


class GeneratorConfigUpdateRequest(BaseModel):
    """Update für Generator-Konfiguration."""
    enabled: Optional[bool] = Field(None, description="Aktiviert")
    priority: Optional[int] = Field(None, ge=1, le=100, description="Priorität")
    max_insights: Optional[int] = Field(None, ge=1, le=50, description="Max Insights")


# =============================================================================
# Helper Functions
# =============================================================================

def _insight_to_response(insight: DailyInsight) -> DailyInsightResponse:
    """Konvertiert DailyInsight zu Response-Schema."""
    return DailyInsightResponse(
        id=insight.id,
        insight_type=insight.insight_type.value,
        severity=insight.severity.value,
        title=insight.title,
        message=insight.message,
        explanation=insight.explanation,
        recommendation=insight.recommendation,
        factors=[
            InsightFactorResponse(
                name=f.name,
                contribution=f.contribution,
                value=f.value,
                explanation=f.explanation,
            )
            for f in insight.factors
        ],
        confidence=insight.confidence,
        impact_value=float(insight.impact_value) if insight.impact_value else None,
        deadline=insight.deadline.isoformat() if insight.deadline else None,
        related_entity_id=str(insight.related_entity_id) if insight.related_entity_id else None,
        related_entity_name=insight.related_entity_name,
        related_document_id=str(insight.related_document_id) if insight.related_document_id else None,
        action_url=insight.action_url,
        created_at=insight.created_at.isoformat(),
    )


def _count_by_severity(insights: List[DailyInsight]) -> Dict[str, int]:
    """Zählt Insights nach Schweregrad."""
    counts: Dict[str, int] = {}
    for insight in insights:
        key = insight.severity.value
        counts[key] = counts.get(key, 0) + 1
    return counts


def _count_by_type(insights: List[DailyInsight]) -> Dict[str, int]:
    """Zählt Insights nach Typ."""
    counts: Dict[str, int] = {}
    for insight in insights:
        key = insight.insight_type.value
        counts[key] = counts.get(key, 0) + 1
    return counts


# =============================================================================
# Endpoints
# =============================================================================

@router.get(
    "",
    response_model=DailyInsightListResponse,
    summary="Alle Daily Insights abrufen",
    description="Ruft alle täglich generierten proaktiven Insights ab.",
)
@limiter.limit("30/minute")
async def get_all_daily_insights(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    severity: Optional[str] = Query(None, description="Filter nach Schweregrad"),
    max_insights: int = Query(50, ge=1, le=100, description="Maximale Anzahl"),
) -> DailyInsightListResponse:
    """
    Ruft alle täglich generierten Insights ab.

    Diese Insights werden proaktiv generiert und warnen BEVOR Probleme entstehen:
    - Cashflow-Warnungen
    - Vertragsablauf
    - Zahlungsrisiken
    - Skonto-Fristen
    - Compliance-Erinnerungen
    """
    company_id = current_user.company_id
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer ist keiner Firma zugeordnet.",
        )

    logger.info(
        "fetching_daily_insights",
        user_id=str(current_user.id),
        company_id=str(company_id),
    )

    engine = get_daily_insights_engine()
    all_insights = await engine.generate_all_insights(db, company_id)

    # Filter nach Schweregrad
    if severity:
        try:
            severity_enum = InsightSeverity(severity)
            all_insights = [i for i in all_insights if i.severity == severity_enum]
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Ungültiger Schweregrad: {severity}. "
                       f"Erlaubt: critical, high, medium, low",
            )

    # Limitieren
    limited_insights = all_insights[:max_insights]

    return DailyInsightListResponse(
        insights=[_insight_to_response(i) for i in limited_insights],
        total_count=len(all_insights),
        by_severity=_count_by_severity(all_insights),
        by_type=_count_by_type(all_insights),
        generated_at=datetime.utcnow().isoformat(),
    )


@router.get(
    "/cashflow",
    response_model=DailyInsightListResponse,
    summary="Cashflow-Warnungen",
    description="Ruft Insights zu möglichen Liquiditätsengpässen ab.",
)
@limiter.limit("30/minute")
async def get_cashflow_insights(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    days_ahead: int = Query(30, ge=7, le=90, description="Prognosezeitraum"),
) -> DailyInsightListResponse:
    """
    Ruft Cashflow-Warnungen ab.

    Prognostiziert Liquiditätsengpässe basierend auf:
    - Aktuellem Kontostand
    - Offenen Ausgangsrechnungen
    - Fälligen Eingangsrechnungen
    - Geplanten Zahlungen
    """
    company_id = current_user.company_id
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer ist keiner Firma zugeordnet.",
        )

    engine = get_daily_insights_engine()
    insights = await engine.generate_insights_by_type(
        db, company_id, DailyInsightType.CASHFLOW_WARNING
    )

    return DailyInsightListResponse(
        insights=[_insight_to_response(i) for i in insights],
        total_count=len(insights),
        by_severity=_count_by_severity(insights),
        by_type=_count_by_type(insights),
    )


@router.get(
    "/contracts",
    response_model=DailyInsightListResponse,
    summary="Vertrags-Warnungen",
    description="Ruft Insights zu ablaufenden Verträgen ab.",
)
@limiter.limit("30/minute")
async def get_contract_insights(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    days_ahead: int = Query(60, ge=7, le=180, description="Vorlauf in Tagen"),
) -> DailyInsightListResponse:
    """
    Ruft Vertragsablauf-Warnungen ab.

    Warnt vor:
    - Ablaufenden Verträgen
    - Kündigungsfristen
    - Verlängerungsoptionen
    """
    company_id = current_user.company_id
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer ist keiner Firma zugeordnet.",
        )

    engine = get_daily_insights_engine()
    insights = await engine.generate_insights_by_type(
        db, company_id, DailyInsightType.CONTRACT_EXPIRING
    )

    return DailyInsightListResponse(
        insights=[_insight_to_response(i) for i in insights],
        total_count=len(insights),
        by_severity=_count_by_severity(insights),
        by_type=_count_by_type(insights),
    )


@router.get(
    "/payments",
    response_model=DailyInsightListResponse,
    summary="Zahlungsrisiko-Warnungen",
    description="Ruft Insights zu Zahlungsrisiken ab.",
)
@limiter.limit("30/minute")
async def get_payment_risk_insights(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> DailyInsightListResponse:
    """
    Ruft Zahlungsrisiko-Warnungen ab.

    Identifiziert:
    - Kunden mit mehreren überfälligen Rechnungen
    - High-Risk Entities
    - Ungewöhnliche Zahlungsverzögerungen
    """
    company_id = current_user.company_id
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer ist keiner Firma zugeordnet.",
        )

    engine = get_daily_insights_engine()
    insights = await engine.generate_insights_by_type(
        db, company_id, DailyInsightType.PAYMENT_RISK
    )

    return DailyInsightListResponse(
        insights=[_insight_to_response(i) for i in insights],
        total_count=len(insights),
        by_severity=_count_by_severity(insights),
        by_type=_count_by_type(insights),
    )


@router.get(
    "/skonto",
    response_model=DailyInsightListResponse,
    summary="Skonto-Fristen",
    description="Ruft Insights zu ablaufenden Skonto-Fristen ab.",
)
@limiter.limit("30/minute")
async def get_skonto_insights(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    days_ahead: int = Query(7, ge=1, le=30, description="Tage Vorlauf"),
) -> DailyInsightListResponse:
    """
    Ruft Skonto-Fristen-Warnungen ab.

    Warnt vor ablaufenden Skonto-Fristen mit:
    - Fälligkeitsdatum
    - Einsparpotenzial
    - Empfohlene Aktion
    """
    company_id = current_user.company_id
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer ist keiner Firma zugeordnet.",
        )

    engine = get_daily_insights_engine()
    insights = await engine.generate_insights_by_type(
        db, company_id, DailyInsightType.SKONTO_DEADLINE
    )

    return DailyInsightListResponse(
        insights=[_insight_to_response(i) for i in insights],
        total_count=len(insights),
        by_severity=_count_by_severity(insights),
        by_type=_count_by_type(insights),
    )


@router.get(
    "/compliance",
    response_model=DailyInsightListResponse,
    summary="Compliance-Erinnerungen",
    description="Ruft Compliance-bezogene Insights ab.",
)
@limiter.limit("30/minute")
async def get_compliance_insights(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> DailyInsightListResponse:
    """
    Ruft Compliance-Erinnerungen ab.

    Warnt vor:
    - Ablaufenden Aufbewahrungsfristen
    - GoBD-Compliance-Problemen
    - GDPR-Fristen
    """
    company_id = current_user.company_id
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer ist keiner Firma zugeordnet.",
        )

    engine = get_daily_insights_engine()
    insights = await engine.generate_insights_by_type(
        db, company_id, DailyInsightType.COMPLIANCE_REMINDER
    )

    return DailyInsightListResponse(
        insights=[_insight_to_response(i) for i in insights],
        total_count=len(insights),
        by_severity=_count_by_severity(insights),
        by_type=_count_by_type(insights),
    )


@router.get(
    "/overdue",
    response_model=DailyInsightListResponse,
    summary="Überfällige Rechnungen",
    description="Ruft Insights zu überfälligen Rechnungen ab.",
)
@limiter.limit("30/minute")
async def get_overdue_insights(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> DailyInsightListResponse:
    """
    Ruft Warnungen zu überfälligen Rechnungen ab.

    Gruppiert nach:
    - Überfälligkeitsdauer
    - Mahnstufe
    - Risiko-Score
    """
    company_id = current_user.company_id
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer ist keiner Firma zugeordnet.",
        )

    engine = get_daily_insights_engine()
    insights = await engine.generate_insights_by_type(
        db, company_id, DailyInsightType.OVERDUE_INVOICE
    )

    return DailyInsightListResponse(
        insights=[_insight_to_response(i) for i in insights],
        total_count=len(insights),
        by_severity=_count_by_severity(insights),
        by_type=_count_by_type(insights),
    )


@router.post(
    "/generate",
    response_model=InsightGenerationResponse,
    summary="Insights manuell generieren (Admin)",
    description="Generiert Insights manuell außerhalb des täglichen Batches.",
)
@limiter.limit("5/minute")
async def generate_insights(
    request: Request,
    data: InsightGenerationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
) -> InsightGenerationResponse:
    """
    Generiert Insights manuell.

    **Nur für Administratoren.**

    Nützlich für:
    - Testen der Insight-Generierung
    - Ad-hoc-Analysen
    - Nach wichtigen Datenänderungen
    """
    import time

    company_id = current_user.company_id
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer ist keiner Firma zugeordnet.",
        )

    start_time = time.time()

    engine = get_daily_insights_engine()

    if data.insight_types:
        # Nur bestimmte Typen
        all_insights: List[DailyInsight] = []
        for type_str in data.insight_types:
            try:
                insight_type = DailyInsightType(type_str)
                insights = await engine.generate_insights_by_type(
                    db, company_id, insight_type
                )
                all_insights.extend(insights)
            except ValueError:
                logger.warning(
                    "invalid_insight_type_requested",
                    type=type_str,
                    user_id=str(current_user.id),
                )
    else:
        # Alle Typen
        all_insights = await engine.generate_all_insights(db, company_id)

    duration_ms = int((time.time() - start_time) * 1000)

    logger.info(
        "manual_insight_generation_complete",
        user_id=str(current_user.id),
        company_id=str(company_id),
        total_generated=len(all_insights),
        duration_ms=duration_ms,
    )

    return InsightGenerationResponse(
        success=True,
        total_generated=len(all_insights),
        by_type=_count_by_type(all_insights),
        duration_ms=duration_ms,
    )


@router.get(
    "/config",
    response_model=List[GeneratorConfigResponse],
    summary="Generator-Konfiguration abrufen",
    description="Ruft die Konfiguration aller Insight-Generatoren ab.",
)
@limiter.limit("30/minute")
async def get_generator_config(
    request: Request,
    current_user: User = Depends(get_current_admin_user),
) -> List[GeneratorConfigResponse]:
    """
    Ruft die Konfiguration aller Insight-Generatoren ab.

    **Nur für Administratoren.**
    """
    engine = get_daily_insights_engine()
    configs = engine.get_generator_configs()

    return [
        GeneratorConfigResponse(
            name=c.name,
            enabled=c.enabled,
            priority=c.priority,
            max_insights=c.max_insights,
            description=c.description,
        )
        for c in configs
    ]


@router.patch(
    "/config/{generator_name}",
    response_model=GeneratorConfigResponse,
    summary="Generator-Konfiguration ändern",
    description="Ändert die Konfiguration eines Insight-Generators.",
)
@limiter.limit("10/minute")
async def update_generator_config(
    request: Request,
    generator_name: str = Path(..., description="Name des Generators"),
    data: GeneratorConfigUpdateRequest = ...,
    current_user: User = Depends(get_current_admin_user),
) -> GeneratorConfigResponse:
    """
    Ändert die Konfiguration eines Insight-Generators.

    **Nur für Administratoren.**

    Ermöglicht:
    - Aktivieren/Deaktivieren von Generatoren
    - Anpassen der Priorität
    - Limitieren der maximalen Insights
    """
    engine = get_daily_insights_engine()

    # Validierung des Generator-Namens
    configs = engine.get_generator_configs()
    config = next((c for c in configs if c.name == generator_name), None)

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Generator '{generator_name}' nicht gefunden.",
        )

    # Update
    success = engine.update_generator_config(
        generator_name,
        enabled=data.enabled,
        priority=data.priority,
        max_insights=data.max_insights,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Konfiguration konnte nicht aktualisiert werden.",
        )

    logger.info(
        "generator_config_updated",
        generator=generator_name,
        user_id=str(current_user.id),
        changes=data.model_dump(exclude_unset=True),
    )

    # Aktualisierte Konfiguration abrufen
    configs = engine.get_generator_configs()
    updated_config = next(c for c in configs if c.name == generator_name)

    return GeneratorConfigResponse(
        name=updated_config.name,
        enabled=updated_config.enabled,
        priority=updated_config.priority,
        max_insights=updated_config.max_insights,
        description=updated_config.description,
    )

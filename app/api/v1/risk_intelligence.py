"""
Risk Intelligence API Endpoints

Erweiterte Risikoanalyse mit Branchen-Benchmarks, Trends und Netzwerk-Analyse.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db
from app.db.models import User
from app.services.finanzki.risk_intelligence_service import (
    RiskIntelligenceService,
    TrendDirection,
)

router = APIRouter(prefix="/risk-intelligence", tags=["Risk Intelligence"])


# ==================== Schemas ====================


class TrendAnalysisSchema(BaseModel):
    """Schema fuer Trend-Analyse."""
    direction: str
    change_percentage: float
    quarters: list[dict]
    trend_score: float


class BenchmarkComparisonSchema(BaseModel):
    """Schema fuer Benchmark-Vergleich."""
    industry: str
    benchmark: dict
    actual_payment_delay: float
    actual_default_rate: float
    delay_deviation: float
    default_deviation: float
    performance: str
    benchmark_score: float


class NetworkAnalysisSchema(BaseModel):
    """Schema fuer Netzwerk-Analyse."""
    connections: list[dict]
    connection_count: int
    network_risk_score: float
    has_suspicious_connections: bool


class RecommendationSchema(BaseModel):
    """Schema fuer Handlungsempfehlung."""
    priority: str
    category: str
    title: str
    description: str
    action: str


class RiskProfileResponse(BaseModel):
    """Response fuer umfassendes Risikoprofil."""
    entity_id: str
    entity_name: str
    entity_type: str
    industry: str
    overall_risk_score: float
    risk_level: str
    analysis: dict
    recommendations: list[RecommendationSchema]
    analyzed_at: str


class PortfolioRiskOverviewResponse(BaseModel):
    """Response fuer Portfolio-Risikouebersicht."""
    total_entities: int
    risk_distribution: dict
    high_risk_entities: list[dict]
    total_exposure: float
    portfolio_risk_score: float
    analyzed_at: str


class ExternalSourceCheckResponse(BaseModel):
    """Response fuer externe Quellenprüfung."""
    entity_id: str
    entity_name: str
    sources_checked: list[dict]
    alerts: list[dict]
    last_checked: str


class IndustryBenchmarkSchema(BaseModel):
    """Schema fuer Branchen-Benchmark."""
    industry: str
    avg_payment_delay: int
    default_rate: float
    industry_risk_factor: float


# ==================== Endpoints ====================


@router.get("/entity/{entity_id}/profile", response_model=RiskProfileResponse)
async def get_risk_profile(
    entity_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Liefert umfassendes Risikoprofil fuer eine Entity.

    Kombiniert:
    - Interne Zahlungsdaten-Analyse
    - Trend-Analyse (quartalsweise)
    - Branchen-Benchmark-Vergleich
    - Netzwerk-Analyse (Verbindungen zu anderen Entities)
    """
    if not current_user.company_id:
        raise HTTPException(status_code=400, detail="Keine Firma zugewiesen")

    service = RiskIntelligenceService(db)
    result = await service.get_comprehensive_risk_profile(
        entity_id=entity_id,
        company_id=current_user.company_id,
    )

    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    return result


@router.get("/entity/{entity_id}/trend")
async def get_entity_trend(
    entity_id: UUID,
    quarters: int = Query(4, ge=2, le=8, description="Anzahl Quartale"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Liefert detaillierte Trend-Analyse fuer eine Entity.
    """
    if not current_user.company_id:
        raise HTTPException(status_code=400, detail="Keine Firma zugewiesen")

    service = RiskIntelligenceService(db)
    result = await service._analyze_trends(entity_id, current_user.company_id)

    return {
        "entity_id": str(entity_id),
        "trend": result,
    }


@router.get("/entity/{entity_id}/benchmark")
async def get_entity_benchmark(
    entity_id: UUID,
    industry: Optional[str] = Query(None, description="Branche fuer Vergleich"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Vergleicht Entity mit Branchen-Benchmark.
    """
    if not current_user.company_id:
        raise HTTPException(status_code=400, detail="Keine Firma zugewiesen")

    service = RiskIntelligenceService(db)
    result = await service._compare_with_benchmarks(
        entity_id, current_user.company_id, industry or "default"
    )

    return {
        "entity_id": str(entity_id),
        "benchmark_comparison": result,
    }


@router.get("/entity/{entity_id}/network")
async def get_entity_network(
    entity_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Analysiert Netzwerk-Verbindungen der Entity.

    Findet Entities mit:
    - Gleicher IBAN (hoher Risiko-Indikator)
    - Gleicher Adresse (mittlerer Risiko-Indikator)
    """
    if not current_user.company_id:
        raise HTTPException(status_code=400, detail="Keine Firma zugewiesen")

    service = RiskIntelligenceService(db)
    result = await service._analyze_network(entity_id, current_user.company_id)

    return {
        "entity_id": str(entity_id),
        "network": result,
    }


@router.get("/entity/{entity_id}/external", response_model=ExternalSourceCheckResponse)
async def check_external_sources(
    entity_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Prueft externe Datenquellen fuer Entity.

    Unterstuetzte Quellen:
    - Handelsregister
    - Insolvenzregister
    - Creditreform (wenn konfiguriert)
    - SCHUFA (wenn konfiguriert)
    """
    if not current_user.company_id:
        raise HTTPException(status_code=400, detail="Keine Firma zugewiesen")

    service = RiskIntelligenceService(db)
    result = await service.check_external_sources(entity_id, current_user.company_id)

    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    return result


@router.get("/portfolio", response_model=PortfolioRiskOverviewResponse)
async def get_portfolio_risk(
    entity_type: Optional[str] = Query(None, description="customer oder supplier"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Liefert Portfolio-Risikouebersicht fuer alle Entities.

    Zeigt:
    - Risikoverteilung
    - High-Risk Entities
    - Gesamtexposure
    - Portfolio-Risikoscore
    """
    if not current_user.company_id:
        raise HTTPException(status_code=400, detail="Keine Firma zugewiesen")

    service = RiskIntelligenceService(db)
    result = await service.get_portfolio_risk_overview(
        company_id=current_user.company_id,
        entity_type=entity_type,
    )

    return result


@router.get("/benchmarks", response_model=list[IndustryBenchmarkSchema])
async def get_industry_benchmarks():
    """
    Liefert verfuegbare Branchen-Benchmarks.
    """
    # Statische Benchmarks aus Service
    benchmarks = [
        {
            "industry": "retail",
            "avg_payment_delay": 15,
            "default_rate": 0.02,
            "industry_risk_factor": 1.0,
        },
        {
            "industry": "manufacturing",
            "avg_payment_delay": 30,
            "default_rate": 0.03,
            "industry_risk_factor": 1.1,
        },
        {
            "industry": "services",
            "avg_payment_delay": 21,
            "default_rate": 0.015,
            "industry_risk_factor": 0.9,
        },
        {
            "industry": "construction",
            "avg_payment_delay": 45,
            "default_rate": 0.05,
            "industry_risk_factor": 1.3,
        },
        {
            "industry": "technology",
            "avg_payment_delay": 14,
            "default_rate": 0.02,
            "industry_risk_factor": 1.0,
        },
    ]
    return benchmarks


@router.get("/trend-directions")
async def get_trend_directions():
    """
    Liefert alle moeglichen Trend-Richtungen mit Beschreibung.
    """
    return [
        {
            "direction": TrendDirection.IMPROVING,
            "name": "Verbessernd",
            "description": "Zahlungsverhalten verbessert sich",
            "color": "#22c55e",
        },
        {
            "direction": TrendDirection.STABLE,
            "name": "Stabil",
            "description": "Keine signifikante Aenderung",
            "color": "#3b82f6",
        },
        {
            "direction": TrendDirection.DETERIORATING,
            "name": "Verschlechternd",
            "description": "Zahlungsverhalten verschlechtert sich",
            "color": "#f59e0b",
        },
        {
            "direction": TrendDirection.CRITICAL,
            "name": "Kritisch",
            "description": "Starke Verschlechterung - sofortige Massnahmen empfohlen",
            "color": "#ef4444",
        },
    ]


@router.get("/external-sources")
async def get_external_sources():
    """
    Liefert verfuegbare externe Datenquellen.
    """
    return [
        {
            "source": "creditreform",
            "name": "Creditreform",
            "description": "Wirtschaftsauskunft und Bonitaetsinformationen",
            "status": "not_configured",
        },
        {
            "source": "schufa",
            "name": "SCHUFA",
            "description": "Kreditwuerdigkeitspruefung",
            "status": "not_configured",
        },
        {
            "source": "insolvency_register",
            "name": "Insolvenzregister",
            "description": "Insolvenzbekanntmachungen",
            "status": "available",
        },
        {
            "source": "handelsregister",
            "name": "Handelsregister",
            "description": "Firmendaten und Vertretungsberechtigte",
            "status": "available",
        },
    ]

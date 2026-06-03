# -*- coding: utf-8 -*-
"""
Supplier Ranking API Endpoints.

Endpoints für Lieferanten-Bewertung und -Vergleich:
- Einzelbewertung eines Lieferanten
- Ranking-Report über alle Lieferanten
- Lieferanten-Vergleich
"""

from datetime import date
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_active_user, get_db, get_user_company_id_dep
from app.db.models import User
from app.services.supplier_ranking_service import (
    get_supplier_ranking_service,
    SupplierRankingCategory,
    SupplierTier,
)


router = APIRouter(prefix="/supplier-ranking", tags=["Supplier Ranking"])


# =============================================================================
# Response Models
# =============================================================================

class CategoryScoreResponse(BaseModel):
    """Einzelbewertung einer Kategorie."""
    category: str = Field(..., description="Kategorie (punctuality, price, reliability, communication, payment_terms)")
    category_label: str = Field(..., description="Deutsche Bezeichnung")
    score: float = Field(..., ge=0, le=100, description="Score 0-100")
    weight: float = Field(..., description="Gewichtung im Gesamtscore")
    data_points: int = Field(..., description="Anzahl ausgewerteter Datenpunkte")
    trend: str = Field(..., description="Trend (up, down, stable)")
    details: dict = Field(default_factory=dict, description="Zusätzliche Details")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "category": "punctuality",
                "category_label": "Puenktlichkeit",
                "score": 85.5,
                "weight": 0.30,
                "data_points": 15,
                "trend": "up",
                "details": {"delivery_scores": 10, "avg_delivery_score": 88.0}
            }
        },
    )


class SupplierRankingResponse(BaseModel):
    """Gesamtbewertung eines Lieferanten."""
    entity_id: str = Field(..., description="Lieferanten-ID")
    entity_name: str = Field(..., description="Lieferantenname")
    overall_score: float = Field(..., ge=0, le=100, description="Gesamtscore 0-100")
    tier: str = Field(..., description="Tier (platinum, gold, silver, bronze, critical)")
    tier_label: str = Field(..., description="Deutsche Tier-Bezeichnung")
    category_scores: List[CategoryScoreResponse] = Field(..., description="Einzelkategorien")
    total_orders: int = Field(..., description="Gesamtanzahl Bestellungen")
    total_volume: float = Field(..., description="Gesamtvolumen in EUR")
    first_order_date: Optional[str] = Field(None, description="Datum erste Bestellung")
    last_order_date: Optional[str] = Field(None, description="Datum letzte Bestellung")
    avg_order_value: float = Field(..., description="Durchschnittlicher Bestellwert")
    score_trend: str = Field(..., description="Score-Trend (improving, declining, stable)")
    previous_score: Optional[float] = Field(None, description="Vorheriger Score")
    recommendations: List[str] = Field(default_factory=list, description="Empfehlungen")
    calculated_at: str = Field(..., description="Berechnungszeitpunkt")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "entity_id": "123e4567-e89b-12d3-a456-426614174000",
                "entity_name": "Mustermann GmbH",
                "overall_score": 82.5,
                "tier": "gold",
                "tier_label": "Bevorzugter Lieferant",
                "category_scores": [],
                "total_orders": 25,
                "total_volume": 15000.00,
                "first_order_date": "2025-01-15",
                "last_order_date": "2026-01-10",
                "avg_order_value": 600.00,
                "score_trend": "improving",
                "previous_score": 78.0,
                "recommendations": ["Guter Lieferant - bevorzugt behandeln"],
                "calculated_at": "2026-01-17T10:30:00Z"
            }
        },
    )


class TierDistributionResponse(BaseModel):
    """Verteilung der Lieferanten auf Tiers."""
    platinum: int = Field(0, description="Anzahl Platinum-Lieferanten")
    gold: int = Field(0, description="Anzahl Gold-Lieferanten")
    silver: int = Field(0, description="Anzahl Silver-Lieferanten")
    bronze: int = Field(0, description="Anzahl Bronze-Lieferanten")
    critical: int = Field(0, description="Anzahl kritischer Lieferanten")


class SupplierRankingReportResponse(BaseModel):
    """Report über alle Lieferanten-Rankings."""
    company_id: str = Field(..., description="Firmen-ID")
    total_suppliers: int = Field(..., description="Gesamtanzahl Lieferanten")
    ranked_suppliers: int = Field(..., description="Bewertete Lieferanten")
    tier_distribution: TierDistributionResponse = Field(..., description="Tier-Verteilung")
    top_suppliers: List[SupplierRankingResponse] = Field(..., description="Top-Lieferanten")
    critical_suppliers: List[SupplierRankingResponse] = Field(..., description="Kritische Lieferanten")
    improving_suppliers: List[SupplierRankingResponse] = Field(..., description="Sich verbessernde Lieferanten")
    declining_suppliers: List[SupplierRankingResponse] = Field(..., description="Sich verschlechternde Lieferanten")
    avg_overall_score: float = Field(..., description="Durchschnittlicher Gesamtscore")
    avg_punctuality: float = Field(..., description="Durchschnittliche Puenktlichkeit")
    avg_reliability: float = Field(..., description="Durchschnittliche Zuverlaessigkeit")
    analysis_period_start: str = Field(..., description="Analysezeitraum Start")
    analysis_period_end: str = Field(..., description="Analysezeitraum Ende")
    generated_at: str = Field(..., description="Report-Generierungszeitpunkt")


class SupplierComparisonRequest(BaseModel):
    """Anfrage für Lieferanten-Vergleich."""
    entity_ids: List[str] = Field(..., min_length=2, max_length=10, description="Lieferanten-IDs zum Vergleich")
    period_days: int = Field(365, ge=30, le=730, description="Auswertungszeitraum in Tagen")


# =============================================================================
# Helper Functions
# =============================================================================

CATEGORY_LABELS = {
    SupplierRankingCategory.PUNCTUALITY: "Puenktlichkeit",
    SupplierRankingCategory.PRICE: "Preis-Leistung",
    SupplierRankingCategory.RELIABILITY: "Zuverlaessigkeit",
    SupplierRankingCategory.COMMUNICATION: "Kommunikation",
    SupplierRankingCategory.PAYMENT_TERMS: "Zahlungsbedingungen",
}

TIER_LABELS = {
    SupplierTier.PLATINUM: "Top-Lieferant",
    SupplierTier.GOLD: "Bevorzugter Lieferant",
    SupplierTier.SILVER: "Standard-Lieferant",
    SupplierTier.BRONZE: "Lieferant unter Beobachtung",
    SupplierTier.CRITICAL: "Kritischer Lieferant",
}


def ranking_to_response(ranking) -> SupplierRankingResponse:
    """Konvertiert SupplierRanking zu Response."""
    category_responses = []
    for cs in ranking.category_scores:
        category_responses.append(CategoryScoreResponse(
            category=cs.category.value,
            category_label=CATEGORY_LABELS.get(cs.category, cs.category.value),
            score=cs.score,
            weight=cs.weight,
            data_points=cs.data_points,
            trend=cs.trend,
            details=cs.details,
        ))

    return SupplierRankingResponse(
        entity_id=str(ranking.entity_id),
        entity_name=ranking.entity_name,
        overall_score=ranking.overall_score,
        tier=ranking.tier.value,
        tier_label=TIER_LABELS.get(ranking.tier, ranking.tier.value),
        category_scores=category_responses,
        total_orders=ranking.total_orders,
        total_volume=float(ranking.total_volume),
        first_order_date=ranking.first_order_date.isoformat() if ranking.first_order_date else None,
        last_order_date=ranking.last_order_date.isoformat() if ranking.last_order_date else None,
        avg_order_value=float(ranking.avg_order_value),
        score_trend=ranking.score_trend,
        previous_score=ranking.previous_score,
        recommendations=ranking.recommendations,
        calculated_at=ranking.calculated_at.isoformat(),
    )


# =============================================================================
# API Endpoints
# =============================================================================

@router.get(
    "/{entity_id}",
    response_model=SupplierRankingResponse,
    summary="Lieferanten-Ranking abrufen",
    description="Berechnet und liefert die Bewertung eines einzelnen Lieferanten.",
)
async def get_supplier_ranking(
    entity_id: UUID,
    period_days: int = Query(365, ge=30, le=730, description="Auswertungszeitraum in Tagen"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
):
    """
    Ruft Ranking für einen Lieferanten ab.

    - **entity_id**: ID des Lieferanten
    - **period_days**: Auswertungszeitraum (30-730 Tage)

    Das Ranking basiert auf:
    - Puenktlichkeit (30%): Liefertreue und Rechnungsstellung
    - Preis-Leistung (25%): Preiskonsistenz und Skonto
    - Zuverlaessigkeit (25%): Reklamationsquote und Qualitaet
    - Kommunikation (10%): Dokumentenqualitaet
    - Zahlungsbedingungen (10%): Zahlungsziele und Skonto-Angebote
    """
    service = get_supplier_ranking_service()

    ranking = await service.calculate_supplier_ranking(
        db=db,
        entity_id=entity_id,
        company_id=company_id,
        period_days=period_days,
    )

    if not ranking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lieferant nicht gefunden oder keine Lieferanten-Entity"
        )

    return ranking_to_response(ranking)


@router.get(
    "",
    response_model=SupplierRankingReportResponse,
    summary="Lieferanten-Ranking-Report",
    description="Erstellt einen Report über alle Lieferanten-Bewertungen.",
)
async def get_supplier_ranking_report(
    period_days: int = Query(365, ge=30, le=730, description="Auswertungszeitraum in Tagen"),
    top_n: int = Query(10, ge=1, le=50, description="Anzahl Top/Bottom Lieferanten"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
):
    """
    Erstellt Gesamt-Report über alle Lieferanten.

    Der Report enthält:
    - Tier-Verteilung (Platinum/Gold/Silver/Bronze/Critical)
    - Top-Lieferanten
    - Kritische Lieferanten
    - Sich verbessernde/verschlechternde Lieferanten
    - Durchschnittswerte

    Wird für strategische Lieferanten-Entscheidungen verwendet.
    """
    service = get_supplier_ranking_service()

    report = await service.get_supplier_ranking_report(
        db=db,
        company_id=company_id,
        period_days=period_days,
        top_n=top_n,
    )

    # Tier-Distribution konvertieren
    tier_dist = TierDistributionResponse(
        platinum=report.tier_distribution.get("platinum", 0),
        gold=report.tier_distribution.get("gold", 0),
        silver=report.tier_distribution.get("silver", 0),
        bronze=report.tier_distribution.get("bronze", 0),
        critical=report.tier_distribution.get("critical", 0),
    )

    return SupplierRankingReportResponse(
        company_id=str(report.company_id),
        total_suppliers=report.total_suppliers,
        ranked_suppliers=report.ranked_suppliers,
        tier_distribution=tier_dist,
        top_suppliers=[ranking_to_response(r) for r in report.top_suppliers],
        critical_suppliers=[ranking_to_response(r) for r in report.critical_suppliers],
        improving_suppliers=[ranking_to_response(r) for r in report.improving_suppliers],
        declining_suppliers=[ranking_to_response(r) for r in report.declining_suppliers],
        avg_overall_score=report.avg_overall_score,
        avg_punctuality=report.avg_punctuality,
        avg_reliability=report.avg_reliability,
        analysis_period_start=report.analysis_period_start.isoformat(),
        analysis_period_end=report.analysis_period_end.isoformat(),
        generated_at=report.generated_at.isoformat(),
    )


@router.post(
    "/compare",
    response_model=List[SupplierRankingResponse],
    summary="Lieferanten vergleichen",
    description="Vergleicht mehrere Lieferanten miteinander.",
)
async def compare_suppliers(
    request: SupplierComparisonRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
):
    """
    Vergleicht mehrere Lieferanten anhand ihrer Bewertungen.

    - **entity_ids**: 2-10 Lieferanten-IDs zum Vergleich
    - **period_days**: Auswertungszeitraum

    Nuetzlich für:
    - Lieferantenauswahl bei neuen Produkten
    - Konsolidierung der Lieferantenbasis
    - Preisverhandlungen
    """
    service = get_supplier_ranking_service()

    # UUIDs parsen
    try:
        entity_ids = [UUID(id_str) for id_str in request.entity_ids]
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ungültige Lieferanten-IDs"
        )

    rankings = await service.get_supplier_comparison(
        db=db,
        company_id=company_id,
        entity_ids=entity_ids,
        period_days=request.period_days,
    )

    if not rankings:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Keine der angegebenen Lieferanten gefunden"
        )

    return [ranking_to_response(r) for r in rankings]


@router.get(
    "/tiers/distribution",
    response_model=TierDistributionResponse,
    summary="Tier-Verteilung abrufen",
    description="Zeigt die Verteilung der Lieferanten auf die verschiedenen Tiers.",
)
async def get_tier_distribution(
    period_days: int = Query(365, ge=30, le=730, description="Auswertungszeitraum in Tagen"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
):
    """
    Schnelle Übersicht über Tier-Verteilung.

    Tiers:
    - **Platinum** (90-100): Top-Lieferanten, strategische Partner
    - **Gold** (75-89): Bevorzugte Lieferanten
    - **Silver** (60-74): Standard-Lieferanten
    - **Bronze** (40-59): Unter Beobachtung
    - **Critical** (0-39): Dringend Alternative suchen
    """
    service = get_supplier_ranking_service()

    report = await service.get_supplier_ranking_report(
        db=db,
        company_id=company_id,
        period_days=period_days,
        top_n=1,  # Minimale Daten
    )

    return TierDistributionResponse(
        platinum=report.tier_distribution.get("platinum", 0),
        gold=report.tier_distribution.get("gold", 0),
        silver=report.tier_distribution.get("silver", 0),
        bronze=report.tier_distribution.get("bronze", 0),
        critical=report.tier_distribution.get("critical", 0),
    )

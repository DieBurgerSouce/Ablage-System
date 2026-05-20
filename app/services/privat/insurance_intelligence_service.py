# -*- coding: utf-8 -*-
"""
InsuranceIntelligenceService - Intelligenter Wrapper um InsuranceAnalysisService.

Wrapper-Service der:
- Einheitliches Interface wie PropertyIntelligenceService bietet
- An bestehenden InsuranceAnalysisService delegiert
- Integration mit RecommendationsService hat
- Batch-Operationen für alle Spaces unterstützt
- Event-Publishing für Deckungslücken

Enterprise Feature - Singleton Pattern wie alle Intelligence Services.
"""

from __future__ import annotations

import threading
from app.core.safe_errors import safe_error_detail, safe_error_log
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

import structlog
from prometheus_client import Counter, Gauge, Histogram
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.privat.insurance_analysis_service import (
    InsuranceAnalysisService,
    InsuranceKPIs,
    CoverageGapAnalysisResult,
    CancellationDeadlineResult,
    InsurancePremiumSummary,
    get_insurance_analysis_service,
)

logger = structlog.get_logger(__name__)


# =============================================================================
# Prometheus Metriken
# =============================================================================

INSURANCE_INTEL_CALCULATIONS = Counter(
    "insurance_intelligence_calculations_total",
    "Anzahl der Insurance-Intelligence Berechnungen",
    ["calculation_type"]
)

INSURANCE_INTEL_DURATION = Histogram(
    "insurance_intelligence_duration_seconds",
    "Dauer der Insurance-Intelligence Berechnung",
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0]
)

INSURANCE_COVERAGE_SCORE = Gauge(
    "insurance_coverage_score_average",
    "Durchschnittlicher Deckungsscore aller Spaces"
)

INSURANCE_CRITICAL_GAPS = Gauge(
    "insurance_critical_gaps_total",
    "Anzahl kritischer Deckungslücken insgesamt"
)


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class InsuranceIntelligenceResult:
    """Vollständiges Ergebnis der Insurance Intelligence Analyse."""
    space_id: UUID

    # Deckungsanalyse
    coverage_analysis: Optional[CoverageGapAnalysisResult] = None
    coverage_score: Decimal = Decimal("0")

    # Kündigungsfristen
    cancellation_deadlines: List[CancellationDeadlineResult] = field(default_factory=list)
    urgent_deadlines_count: int = 0
    approaching_deadlines_count: int = 0

    # Praemien
    premium_summary: Optional[InsurancePremiumSummary] = None
    annual_premium_total: Decimal = Decimal("0")

    # Empfehlungen
    recommendations: List[str] = field(default_factory=list)

    # Health Score (0-100)
    health_score: Decimal = Decimal("50")

    calculated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class BatchInsuranceResult:
    """Ergebnis der Batch-Berechnung für alle Spaces."""
    total_spaces: int = 0
    calculated: int = 0
    skipped: int = 0
    errors: List[str] = field(default_factory=list)  # FIX: default_factory statt kein Default

    # Aggregierte Werte
    average_coverage_score: Decimal = Decimal("0")
    total_critical_gaps: int = 0
    total_urgent_deadlines: int = 0
    total_annual_premiums: Decimal = Decimal("0")

    calculated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# =============================================================================
# Service
# =============================================================================

class InsuranceIntelligenceService:
    """
    Intelligenter Wrapper um InsuranceAnalysisService.

    Features:
    - Einheitliches Interface wie PropertyIntelligenceService
    - Delegation an bestehenden InsuranceAnalysisService
    - Integration mit RecommendationsService
    - Batch-Operationen für alle Spaces
    - Event-Publishing bei kritischen Lücken

    Thread-safe Singleton mit Double-Checked Locking.
    """

    _instance: Optional["InsuranceIntelligenceService"] = None
    _class_lock: threading.Lock = threading.Lock()

    def __new__(cls) -> "InsuranceIntelligenceService":
        """Thread-safe Singleton mit Double-Checked Locking."""
        if cls._instance is None:
            with cls._class_lock:
                if cls._instance is None:
                    instance = super().__new__(cls)
                    # ALLE Attribute hier initialisieren
                    instance._analysis_service = get_insurance_analysis_service()
                    instance._cache: Dict[str, Any] = {}
                    instance._cache_lock = threading.RLock()  # Thread-safe Cache
                    instance._initialized = True
                    cls._instance = instance
                    logger.info("insurance_intelligence_service_initialized")
        return cls._instance

    def __init__(self) -> None:
        """No-op - Initialisierung erfolgt in __new__."""
        pass

    # =========================================================================
    # Vollständige Analyse
    # =========================================================================

    async def get_full_analysis(
        self,
        db: AsyncSession,
        space_id: UUID,
        persist: bool = True,
    ) -> InsuranceIntelligenceResult:
        """
        Führt vollständige Insurance Intelligence Analyse durch.

        Delegiert an InsuranceAnalysisService und reichert mit
        Empfehlungen und Health Score an.

        Args:
            db: Datenbank-Session
            space_id: Space-ID
            persist: Ob die Werte in der Datenbank gespeichert werden sollen

        Returns:
            InsuranceIntelligenceResult mit allen berechneten Werten
        """
        result, _ = await self._get_full_analysis_internal(
            db, space_id, persist=persist, defer_events=False
        )

        logger.info(
            "insurance_intelligence_analysis_completed",
            space_id=str(space_id),
            coverage_score=float(result.coverage_score),
            health_score=float(result.health_score),
            urgent_deadlines=result.urgent_deadlines_count,
        )

        return result

    # =========================================================================
    # Empfehlungen
    # =========================================================================

    async def _generate_recommendations(
        self,
        db: AsyncSession,
        space_id: UUID,
        kpis: InsuranceKPIs,
    ) -> List[str]:
        """
        Generiert intelligente Empfehlungen basierend auf Analyse.

        Args:
            db: Datenbank-Session
            space_id: Space-ID
            kpis: Berechnete KPIs

        Returns:
            Liste von Empfehlungen
        """
        recommendations: List[str] = []

        # Deckungslücken-Empfehlungen
        if kpis.coverage_analysis:
            # Fehlende essentielle Versicherungen
            for missing in kpis.coverage_analysis.missing_essential:
                recommendations.append(
                    f"Essentielle Versicherung fehlt: {missing} - "
                    "Dringend Abschluss empfohlen"
                )

            # Kritische Lücken
            for gap in kpis.coverage_analysis.gaps:
                if gap.severity == "critical":
                    recommendations.append(
                        f"Kritische Deckungslücke bei {gap.insurance_name}: "
                        f"Nur {float(gap.current_coverage):,.0f} EUR von "
                        f"{float(gap.recommended_coverage):,.0f} EUR empfohlen"
                    )
                elif gap.severity == "high" and gap.is_essential:
                    recommendations.append(
                        f"Hohe Deckungslücke bei {gap.insurance_name}: "
                        f"Erhöhung auf {float(gap.recommended_coverage):,.0f} EUR prüfen"
                    )

        # Kündigungsfristen-Empfehlungen
        for deadline in kpis.cancellation_deadlines:
            if deadline.is_urgent:
                recommendations.append(
                    f"DRINGEND: Kündigungsfrist für {deadline.insurance_name} "
                    f"endet in {deadline.days_until_deadline} Tagen - "
                    "Jetzt prüfen ob Kündigung oder Verlängerung gewünscht!"
                )
            elif deadline.is_approaching and deadline.days_until_deadline <= 60:
                recommendations.append(
                    f"Kündigungsfrist für {deadline.insurance_name} "
                    f"in {deadline.days_until_deadline} Tagen - "
                    "Rechtzeitig Konditionen vergleichen"
                )

        # Praemien-Empfehlungen
        if kpis.premium_summary:
            monthly = kpis.premium_summary.monthly_equivalent
            if monthly > Decimal("500"):
                recommendations.append(
                    f"Monatliche Versicherungskosten von {float(monthly):,.0f} EUR - "
                    "Potenzial für Buendelrabatte oder Tarifwechsel prüfen"
                )

        # Coverage Score Empfehlung
        if kpis.coverage_analysis and kpis.coverage_analysis.coverage_score < Decimal("50"):
            recommendations.append(
                f"Deckungsscore nur {float(kpis.coverage_analysis.coverage_score):.0f}% - "
                "Dringende Überarbeitung des Versicherungsportfolios empfohlen"
            )

        return recommendations

    # =========================================================================
    # Health Score
    # =========================================================================

    def _calculate_health_score(self, kpis: InsuranceKPIs) -> Decimal:
        """
        Berechnet einen Gesundheits-Score (0-100) für Versicherungen.

        Args:
            kpis: Berechnete KPIs

        Returns:
            Health Score als Decimal
        """
        score = Decimal("50")  # Basis

        if kpis.coverage_analysis:
            # Deckungsscore einbeziehen (max +30 Punkte)
            coverage_contribution = (kpis.coverage_analysis.coverage_score / 100) * 30
            score += coverage_contribution

            # Abzuege für kritische Lücken
            score -= Decimal(str(kpis.coverage_analysis.critical_gaps * 10))
            score -= Decimal(str(kpis.coverage_analysis.high_gaps * 5))

            # Abzug für fehlende essentielle Versicherungen
            score -= Decimal(str(len(kpis.coverage_analysis.missing_essential) * 8))

        # Kündigungsfristen (max +10 Punkte wenn keine dringend)
        urgent_count = sum(1 for d in kpis.cancellation_deadlines if d.is_urgent)
        if urgent_count == 0:
            score += Decimal("10")
        else:
            score -= Decimal(str(urgent_count * 5))

        # Versicherungsanzahl (max +10 Punkte)
        if kpis.premium_summary:
            if kpis.premium_summary.insurance_count >= 5:
                score += Decimal("10")
            elif kpis.premium_summary.insurance_count >= 3:
                score += Decimal("5")

        # Sicherstellen 0-100
        return max(Decimal("0"), min(Decimal("100"), score)).quantize(Decimal("0.01"))

    # =========================================================================
    # Event Publishing
    # =========================================================================

    async def _publish_events_if_needed(
        self,
        db: AsyncSession,
        space_id: UUID,
        kpis: InsuranceKPIs,
    ) -> None:
        """
        Publiziert Events bei kritischen Ereignissen.

        Args:
            db: Datenbank-Session
            space_id: Space-ID
            kpis: Berechnete KPIs
        """
        try:
            from app.services.events.event_bus import get_event_bus, EventType

            event_bus = get_event_bus()

            # Event bei kritischen Deckungslücken
            if kpis.coverage_analysis and kpis.coverage_analysis.critical_gaps > 0:
                await event_bus.publish(
                    EventType.INSURANCE_GAP_DETECTED,
                    {
                        "space_id": str(space_id),
                        "critical_gaps": kpis.coverage_analysis.critical_gaps,
                        "high_gaps": kpis.coverage_analysis.high_gaps,
                        "coverage_score": float(kpis.coverage_analysis.coverage_score),
                        "missing_essential": kpis.coverage_analysis.missing_essential,
                    }
                )

            # Event bei dringenden Kündigungsfristen
            urgent_deadlines = [d for d in kpis.cancellation_deadlines if d.is_urgent]
            for deadline in urgent_deadlines:
                await event_bus.publish(
                    EventType.INSURANCE_DEADLINE_APPROACHING,
                    {
                        "space_id": str(space_id),
                        "insurance_id": str(deadline.insurance_id),
                        "insurance_name": deadline.insurance_name,
                        "days_until_deadline": deadline.days_until_deadline,
                        "cancellation_deadline": str(deadline.cancellation_deadline),
                    }
                )

        except Exception as e:
            # Event-Publishing sollte nie die Hauptfunktion blockieren
            logger.warning(
                "event_publishing_failed",
                space_id=str(space_id),
                **safe_error_log(e),
            )

    # =========================================================================
    # Batch-Operationen
    # =========================================================================

    async def recalculate_all_spaces(
        self,
        db: AsyncSession,
        space_ids: Optional[List[UUID]] = None,
    ) -> BatchInsuranceResult:
        """
        Berechnet Insurance Intelligence für alle Spaces.

        WICHTIG: Events werden NACH db.commit() publiziert um Transaktions-
        konsistenz zu gewährleisten.

        Args:
            db: Datenbank-Session
            space_ids: Optional: Nur diese Spaces berechnen

        Returns:
            BatchInsuranceResult mit Statistiken
        """
        from app.db.models import PrivatSpace


        INSURANCE_INTEL_CALCULATIONS.labels(calculation_type="batch_all").inc()

        # Spaces laden
        if space_ids:
            query = select(PrivatSpace).where(PrivatSpace.id.in_(space_ids))
        else:
            query = select(PrivatSpace).where(PrivatSpace.deleted_at.is_(None))

        result = await db.execute(query)
        spaces = result.scalars().all()

        batch_result = BatchInsuranceResult(total_spaces=len(spaces))

        total_coverage_score = Decimal("0")

        # Events sammeln für spätere Publikation NACH db.commit()
        pending_events: List[tuple[UUID, InsuranceKPIs]] = []

        for space in spaces:
            try:
                # Analyse ohne Event-Publishing (defer_events=True)
                analysis, kpis = await self._get_full_analysis_internal(
                    db, space.id, persist=True, defer_events=True
                )
                batch_result.calculated += 1

                # Aggregieren
                total_coverage_score += analysis.coverage_score
                batch_result.total_annual_premiums += analysis.annual_premium_total
                batch_result.total_urgent_deadlines += analysis.urgent_deadlines_count

                if analysis.coverage_analysis:
                    batch_result.total_critical_gaps += analysis.coverage_analysis.critical_gaps

                # Events für später merken
                if kpis:
                    pending_events.append((space.id, kpis))

            except Exception as e:
                batch_result.skipped += 1
                batch_result.errors.append(f"{space.id}: {safe_error_detail(e, 'Insurance')}")
                logger.warning(
                    "insurance_batch_calculation_failed",
                    space_id=str(space.id),
                    **safe_error_log(e),
                )

        # Durchschnitt berechnen
        if batch_result.calculated > 0:
            batch_result.average_coverage_score = (
                total_coverage_score / batch_result.calculated
            ).quantize(Decimal("0.01"))

        # Prometheus Gauges aktualisieren
        INSURANCE_COVERAGE_SCORE.set(float(batch_result.average_coverage_score))
        INSURANCE_CRITICAL_GAPS.set(batch_result.total_critical_gaps)

        # ERST db.commit() - Daten sind jetzt persistent!
        await db.commit()

        # DANN Events publizieren - NACH erfolgreichem Commit
        for space_id, kpis in pending_events:
            await self._publish_events_if_needed(db, space_id, kpis)

        logger.info(
            "insurance_batch_calculation_completed",
            total_spaces=batch_result.total_spaces,
            calculated=batch_result.calculated,
            skipped=batch_result.skipped,
            average_score=float(batch_result.average_coverage_score),
            total_critical_gaps=batch_result.total_critical_gaps,
            events_published=len(pending_events),
        )

        return batch_result

    async def _get_full_analysis_internal(
        self,
        db: AsyncSession,
        space_id: UUID,
        persist: bool = True,
        defer_events: bool = False,
    ) -> tuple[InsuranceIntelligenceResult, Optional[InsuranceKPIs]]:
        """
        Interne Methode für get_full_analysis mit optionalem Event-Defer.

        Args:
            db: Datenbank-Session
            space_id: Space-ID
            persist: Ob die Werte gespeichert werden sollen
            defer_events: Wenn True, Events nicht publizieren sondern KPIs zurückgeben

        Returns:
            Tuple aus Result und optional KPIs (wenn defer_events=True)
        """
        INSURANCE_INTEL_CALCULATIONS.labels(calculation_type="full_analysis").inc()

        with INSURANCE_INTEL_DURATION.time():
            kpis = await self._analysis_service.analyze_all(db, space_id, persist=persist)

            result = InsuranceIntelligenceResult(
                space_id=space_id,
                coverage_analysis=kpis.coverage_analysis,
                coverage_score=kpis.coverage_analysis.coverage_score if kpis.coverage_analysis else Decimal("0"),
                cancellation_deadlines=kpis.cancellation_deadlines,
                premium_summary=kpis.premium_summary,
            )

            result.urgent_deadlines_count = sum(
                1 for d in kpis.cancellation_deadlines if d.is_urgent
            )
            result.approaching_deadlines_count = sum(
                1 for d in kpis.cancellation_deadlines if d.is_approaching
            )

            if kpis.premium_summary:
                result.annual_premium_total = kpis.premium_summary.annual_total

            result.recommendations = await self._generate_recommendations(db, space_id, kpis)
            result.health_score = self._calculate_health_score(kpis)

            # Events nur publizieren wenn nicht deferred
            if not defer_events:
                await self._publish_events_if_needed(db, space_id, kpis)
                return result, None
            else:
                return result, kpis

    # =========================================================================
    # Convenience Methods (Delegation)
    # =========================================================================

    async def get_coverage_gaps(
        self,
        db: AsyncSession,
        space_id: UUID,
    ) -> CoverageGapAnalysisResult:
        """Delegiert an InsuranceAnalysisService.analyze_coverage_gaps()."""
        return await self._analysis_service.analyze_coverage_gaps(db, space_id)

    async def get_cancellation_deadlines(
        self,
        db: AsyncSession,
        space_id: UUID,
    ) -> List[CancellationDeadlineResult]:
        """Delegiert an InsuranceAnalysisService.calculate_cancellation_deadlines()."""
        return await self._analysis_service.calculate_cancellation_deadlines(db, space_id)

    async def get_premium_summary(
        self,
        db: AsyncSession,
        space_id: UUID,
    ) -> InsurancePremiumSummary:
        """Delegiert an InsuranceAnalysisService.calculate_premium_summary()."""
        return await self._analysis_service.calculate_premium_summary(db, space_id)

    async def analyze_single_insurance(
        self,
        db: AsyncSession,
        insurance_id: UUID,
        persist: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """Delegiert an InsuranceAnalysisService.analyze_single_insurance()."""
        return await self._analysis_service.analyze_single_insurance(
            db, insurance_id, persist=persist
        )


# =============================================================================
# Singleton Factory
# =============================================================================


def get_insurance_intelligence_service() -> InsuranceIntelligenceService:
    """Factory für InsuranceIntelligenceService Singleton (Thread-safe).

    Note:
        Thread-safety wird durch das Singleton Pattern in der Klasse garantiert.
        Keine separate globale Variable noetig.
    """
    return InsuranceIntelligenceService()

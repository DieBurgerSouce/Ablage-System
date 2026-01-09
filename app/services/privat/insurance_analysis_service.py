# -*- coding: utf-8 -*-
"""
InsuranceAnalysisService - Versicherungsanalyse und Deckungsluecken.

Berechnet automatisch:
- Deckungsluecken-Analyse
- Kuendigungsfristen
- Jaehrliche Praemien
- Deckungsadaequanz-Score

Enterprise Feature - feinpoliert und durchdacht.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone, date, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

import structlog
from prometheus_client import Counter, Histogram
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


# =============================================================================
# Prometheus Metriken
# =============================================================================

INSURANCE_CALCULATIONS = Counter(
    "insurance_calculation_requests_total",
    "Anzahl der Versicherungs-Analysen",
    ["calculation_type"]
)

INSURANCE_CALCULATION_DURATION = Histogram(
    "insurance_calculation_duration_seconds",
    "Dauer der Versicherungs-Analyse in Sekunden",
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0]
)


# =============================================================================
# Empfohlene Deckungssummen
# =============================================================================

RECOMMENDED_COVERAGE = {
    # Haftpflichtversicherung
    "haftpflicht": {
        "name": "Privathaftpflicht",
        "min_coverage": Decimal("5000000"),    # 5 Mio EUR
        "recommended_coverage": Decimal("10000000"),  # 10 Mio EUR
        "essential": True,
    },
    # Hausratversicherung
    "hausrat": {
        "name": "Hausrat",
        "min_coverage": Decimal("50000"),
        "recommended_coverage": Decimal("100000"),
        "essential": False,
    },
    # Rechtsschutzversicherung
    "rechtsschutz": {
        "name": "Rechtsschutz",
        "min_coverage": Decimal("300000"),
        "recommended_coverage": Decimal("500000"),
        "essential": False,
    },
    # Berufsunfaehigkeit
    "berufsunfaehigkeit": {
        "name": "Berufsunfaehigkeit",
        "min_coverage": Decimal("1000"),  # Monatliche Rente
        "recommended_coverage": Decimal("2000"),
        "essential": True,
    },
    # Risikolebensversicherung
    "risikoleben": {
        "name": "Risikoleben",
        "min_coverage": Decimal("100000"),
        "recommended_coverage": Decimal("300000"),
        "essential": False,  # Abhaengig von Familiensituation
    },
    # Unfallversicherung
    "unfall": {
        "name": "Unfall",
        "min_coverage": Decimal("100000"),
        "recommended_coverage": Decimal("200000"),
        "essential": False,
    },
    # Wohngebaeudeversicherung
    "wohngebaeude": {
        "name": "Wohngebaeude",
        "min_coverage": Decimal("500000"),  # Abhaengig vom Gebaeudewert
        "recommended_coverage": Decimal("1000000"),
        "essential": True,  # Fuer Eigentuemer
    },
    # KFZ-Haftpflicht
    "kfz_haftpflicht": {
        "name": "Kfz-Haftpflicht",
        "min_coverage": Decimal("100000000"),  # 100 Mio (gesetzlich)
        "recommended_coverage": Decimal("100000000"),
        "essential": True,
    },
    # KFZ-Kasko
    "kfz_kasko": {
        "name": "Kfz-Kasko",
        "min_coverage": Decimal("0"),  # Zeitwert
        "recommended_coverage": Decimal("0"),  # Neuwert bei neuem Fahrzeug
        "essential": False,
    },
    # Krankenversicherung (privat)
    "kranken": {
        "name": "Krankenversicherung",
        "min_coverage": Decimal("0"),
        "recommended_coverage": Decimal("0"),
        "essential": True,
    },
    # Pflegeversicherung
    "pflege": {
        "name": "Pflegezusatz",
        "min_coverage": Decimal("1500"),  # Monatlich
        "recommended_coverage": Decimal("2500"),
        "essential": False,
    },
}

# Severity-Levels fuer Deckungsluecken
SEVERITY_LEVELS = {
    "critical": {"threshold": 0.5, "label": "Kritisch"},  # <50% der empfohlenen Deckung
    "high": {"threshold": 0.7, "label": "Hoch"},          # 50-70%
    "medium": {"threshold": 0.85, "label": "Mittel"},     # 70-85%
    "low": {"threshold": 1.0, "label": "Niedrig"},        # 85-100%
}


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class CoverageGap:
    """Eine einzelne Deckungsluecke."""
    insurance_type: str
    insurance_name: str
    recommended_coverage: Decimal
    current_coverage: Decimal
    gap_amount: Decimal
    gap_percentage: Decimal
    severity: str
    severity_label: str
    is_essential: bool


@dataclass
class CoverageGapAnalysisResult:
    """Ergebnis der Deckungsluecken-Analyse."""
    space_id: UUID
    gaps: List[CoverageGap]
    total_gap_count: int
    critical_gaps: int
    high_gaps: int
    coverage_score: Decimal  # 0-100
    missing_essential: List[str]
    calculated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class CancellationDeadlineResult:
    """Ergebnis der Kuendigungsfrist-Berechnung."""
    insurance_id: UUID
    insurance_name: str
    contract_end: Optional[date]
    cancellation_period_months: int
    cancellation_deadline: date
    days_until_deadline: int
    is_urgent: bool  # Weniger als 30 Tage
    is_approaching: bool  # Weniger als 90 Tage
    calculated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class InsurancePremiumSummary:
    """Zusammenfassung der Versicherungspraemien."""
    space_id: UUID
    annual_total: Decimal
    monthly_equivalent: Decimal
    by_type: Dict[str, Decimal]
    insurance_count: int
    calculated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class InsuranceKPIs:
    """Alle berechneten KPIs fuer Versicherungen eines Spaces."""
    space_id: UUID
    coverage_analysis: Optional[CoverageGapAnalysisResult] = None
    cancellation_deadlines: List[CancellationDeadlineResult] = field(default_factory=list)
    premium_summary: Optional[InsurancePremiumSummary] = None
    calculated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# =============================================================================
# Service
# =============================================================================

class InsuranceAnalysisService:
    """
    Service fuer Versicherungsanalyse.

    Analysiert:
    - Deckungsluecken vs. Empfehlungen
    - Kuendigungsfristen
    - Praemien-Uebersicht
    - Deckungsadaequanz-Score
    """

    def __init__(self) -> None:
        """Initialisiert den Service."""
        pass

    # =========================================================================
    # Deckungsluecken-Analyse
    # =========================================================================

    async def analyze_coverage_gaps(
        self,
        db: AsyncSession,
        space_id: UUID,
    ) -> CoverageGapAnalysisResult:
        """
        Analysiert Deckungsluecken fuer alle Versicherungen eines Spaces.

        Vergleicht vorhandene Deckung mit Empfehlungen und identifiziert Luecken.

        Args:
            db: Datenbank-Session
            space_id: Space-ID

        Returns:
            CoverageGapAnalysisResult
        """
        from app.db.models import PrivatInsurance

        INSURANCE_CALCULATIONS.labels(calculation_type="coverage_gaps").inc()

        # Alle aktiven Versicherungen laden
        result = await db.execute(
            select(PrivatInsurance)
            .where(
                and_(
                    PrivatInsurance.space_id == space_id,
                    PrivatInsurance.is_active == True,
                )
            )
        )
        insurances = result.scalars().all()

        # Nach Typ gruppieren
        coverage_by_type: Dict[str, Decimal] = {}
        for insurance in insurances:
            ins_type = self._normalize_insurance_type(insurance.insurance_type)
            current = coverage_by_type.get(ins_type, Decimal("0"))
            if insurance.coverage_amount:
                current += insurance.coverage_amount
            coverage_by_type[ins_type] = current

        # Luecken identifizieren
        gaps: List[CoverageGap] = []
        missing_essential: List[str] = []

        for ins_type, recommendation in RECOMMENDED_COVERAGE.items():
            current_coverage = coverage_by_type.get(ins_type, Decimal("0"))
            recommended = recommendation["recommended_coverage"]

            # Fehlende essentielle Versicherungen
            if recommendation["essential"] and current_coverage == 0:
                missing_essential.append(recommendation["name"])

            # Deckungsluecke berechnen
            if recommended > 0 and current_coverage < recommended:
                gap_amount = recommended - current_coverage
                gap_percentage = ((recommended - current_coverage) / recommended) * 100

                # Severity bestimmen
                coverage_ratio = float(current_coverage / recommended) if recommended > 0 else 0
                severity = "low"
                severity_label = "Niedrig"

                for sev_name, sev_data in sorted(
                    SEVERITY_LEVELS.items(),
                    key=lambda x: x[1]["threshold"]
                ):
                    if coverage_ratio < sev_data["threshold"]:
                        severity = sev_name
                        severity_label = sev_data["label"]
                        break

                gaps.append(CoverageGap(
                    insurance_type=ins_type,
                    insurance_name=recommendation["name"],
                    recommended_coverage=recommended,
                    current_coverage=current_coverage,
                    gap_amount=gap_amount,
                    gap_percentage=round(gap_percentage, 1),
                    severity=severity,
                    severity_label=severity_label,
                    is_essential=recommendation["essential"],
                ))

        # Statistiken
        critical_gaps = sum(1 for g in gaps if g.severity == "critical")
        high_gaps = sum(1 for g in gaps if g.severity == "high")

        # Deckungsscore berechnen (0-100)
        total_types = len(RECOMMENDED_COVERAGE)
        covered_types = len(coverage_by_type)
        essential_types = sum(1 for r in RECOMMENDED_COVERAGE.values() if r["essential"])
        essential_covered = sum(
            1 for ins_type, r in RECOMMENDED_COVERAGE.items()
            if r["essential"] and coverage_by_type.get(ins_type, Decimal("0")) > 0
        )

        # Score-Berechnung: 60% essentielle, 40% alle
        essential_score = (essential_covered / essential_types * 60) if essential_types > 0 else 60
        total_score = (covered_types / total_types * 40) if total_types > 0 else 40
        coverage_score = Decimal(str(essential_score + total_score))

        # Abzuege fuer kritische Luecken
        coverage_score -= Decimal(str(critical_gaps * 10))
        coverage_score -= Decimal(str(high_gaps * 5))
        coverage_score = max(Decimal("0"), min(Decimal("100"), coverage_score))

        logger.info(
            "coverage_gaps_analyzed",
            space_id=str(space_id),
            total_gaps=len(gaps),
            critical_gaps=critical_gaps,
            coverage_score=float(coverage_score),
        )

        return CoverageGapAnalysisResult(
            space_id=space_id,
            gaps=gaps,
            total_gap_count=len(gaps),
            critical_gaps=critical_gaps,
            high_gaps=high_gaps,
            coverage_score=round(coverage_score, 1),
            missing_essential=missing_essential,
        )

    def _normalize_insurance_type(self, insurance_type: str) -> str:
        """Normalisiert Versicherungstyp zu internem Key."""
        type_mapping = {
            "privathaftpflicht": "haftpflicht",
            "haftpflicht": "haftpflicht",
            "hausrat": "hausrat",
            "hausratversicherung": "hausrat",
            "rechtsschutz": "rechtsschutz",
            "rechtsschutzversicherung": "rechtsschutz",
            "berufsunfaehigkeit": "berufsunfaehigkeit",
            "bu": "berufsunfaehigkeit",
            "risikoleben": "risikoleben",
            "risiko-leben": "risikoleben",
            "lebensversicherung": "risikoleben",
            "unfall": "unfall",
            "unfallversicherung": "unfall",
            "wohngebaeude": "wohngebaeude",
            "gebaeude": "wohngebaeude",
            "kfz": "kfz_haftpflicht",
            "kfz-haftpflicht": "kfz_haftpflicht",
            "auto": "kfz_haftpflicht",
            "kasko": "kfz_kasko",
            "kfz-kasko": "kfz_kasko",
            "vollkasko": "kfz_kasko",
            "teilkasko": "kfz_kasko",
            "kranken": "kranken",
            "krankenversicherung": "kranken",
            "pkv": "kranken",
            "pflege": "pflege",
            "pflegezusatz": "pflege",
        }
        normalized = insurance_type.lower().replace(" ", "").replace("-", "")
        return type_mapping.get(normalized, insurance_type.lower())

    # =========================================================================
    # Kuendigungsfristen
    # =========================================================================

    async def calculate_cancellation_deadlines(
        self,
        db: AsyncSession,
        space_id: UUID,
    ) -> List[CancellationDeadlineResult]:
        """
        Berechnet Kuendigungsfristen fuer alle Versicherungen.

        Args:
            db: Datenbank-Session
            space_id: Space-ID

        Returns:
            Liste von CancellationDeadlineResult
        """
        from app.db.models import PrivatInsurance

        INSURANCE_CALCULATIONS.labels(calculation_type="cancellation_deadlines").inc()

        result = await db.execute(
            select(PrivatInsurance)
            .where(
                and_(
                    PrivatInsurance.space_id == space_id,
                    PrivatInsurance.is_active == True,
                )
            )
        )
        insurances = result.scalars().all()

        today = date.today()
        deadlines: List[CancellationDeadlineResult] = []

        for insurance in insurances:
            # Kuendigungsfrist berechnen
            cancellation_months = insurance.cancellation_period_months or 3  # Default: 3 Monate

            # Vertragsende bestimmen
            contract_end = insurance.end_date

            # Bei Auto-Renewal: naechstes Vertragsende = 1 Jahr nach Start
            if contract_end is None and insurance.is_auto_renew and insurance.start_date:
                # Naechstes Vertragsende berechnen
                years_since_start = (today.year - insurance.start_date.year)
                if today.month < insurance.start_date.month or \
                   (today.month == insurance.start_date.month and today.day < insurance.start_date.day):
                    years_since_start -= 1
                contract_end = insurance.start_date.replace(
                    year=insurance.start_date.year + years_since_start + 1
                )

            if contract_end is None:
                continue

            # Kuendigungsfrist berechnen
            cancellation_deadline = contract_end - timedelta(days=cancellation_months * 30)

            days_until = (cancellation_deadline - today).days

            deadlines.append(CancellationDeadlineResult(
                insurance_id=insurance.id,
                insurance_name=insurance.name,
                contract_end=contract_end,
                cancellation_period_months=cancellation_months,
                cancellation_deadline=cancellation_deadline,
                days_until_deadline=days_until,
                is_urgent=days_until <= 30,
                is_approaching=days_until <= 90,
            ))

        # Sortieren nach Dringlichkeit
        deadlines.sort(key=lambda x: x.days_until_deadline)

        logger.info(
            "cancellation_deadlines_calculated",
            space_id=str(space_id),
            total_deadlines=len(deadlines),
            urgent_count=sum(1 for d in deadlines if d.is_urgent),
        )

        return deadlines

    # =========================================================================
    # Praemien-Zusammenfassung
    # =========================================================================

    async def calculate_premium_summary(
        self,
        db: AsyncSession,
        space_id: UUID,
    ) -> InsurancePremiumSummary:
        """
        Berechnet die jaehrlichen Gesamtpraemien.

        Args:
            db: Datenbank-Session
            space_id: Space-ID

        Returns:
            InsurancePremiumSummary
        """
        from app.db.models import PrivatInsurance

        INSURANCE_CALCULATIONS.labels(calculation_type="premium_summary").inc()

        result = await db.execute(
            select(PrivatInsurance)
            .where(
                and_(
                    PrivatInsurance.space_id == space_id,
                    PrivatInsurance.is_active == True,
                )
            )
        )
        insurances = result.scalars().all()

        annual_total = Decimal("0")
        by_type: Dict[str, Decimal] = {}

        for insurance in insurances:
            if not insurance.premium_amount:
                continue

            # Auf jaehrlich umrechnen
            annual_premium = insurance.premium_amount
            frequency = insurance.premium_frequency or "yearly"

            if frequency == "monthly":
                annual_premium = insurance.premium_amount * 12
            elif frequency == "quarterly":
                annual_premium = insurance.premium_amount * 4
            elif frequency == "half-yearly":
                annual_premium = insurance.premium_amount * 2

            annual_total += annual_premium

            # Nach Typ gruppieren
            ins_type = self._normalize_insurance_type(insurance.insurance_type)
            by_type[ins_type] = by_type.get(ins_type, Decimal("0")) + annual_premium

        logger.info(
            "premium_summary_calculated",
            space_id=str(space_id),
            annual_total=float(annual_total),
            insurance_count=len(insurances),
        )

        return InsurancePremiumSummary(
            space_id=space_id,
            annual_total=round(annual_total, 2),
            monthly_equivalent=round(annual_total / 12, 2),
            by_type=by_type,
            insurance_count=len(insurances),
        )

    # =========================================================================
    # Alle KPIs berechnen
    # =========================================================================

    async def analyze_all(
        self,
        db: AsyncSession,
        space_id: UUID,
        persist: bool = True,
    ) -> InsuranceKPIs:
        """
        Fuehrt alle Versicherungs-Analysen durch.

        Args:
            db: Datenbank-Session
            space_id: Space-ID
            persist: Ob die Werte in der Datenbank gespeichert werden sollen

        Returns:
            InsuranceKPIs
        """
        coverage_analysis = await self.analyze_coverage_gaps(db, space_id)
        cancellation_deadlines = await self.calculate_cancellation_deadlines(db, space_id)
        premium_summary = await self.calculate_premium_summary(db, space_id)

        kpis = InsuranceKPIs(
            space_id=space_id,
            coverage_analysis=coverage_analysis,
            cancellation_deadlines=cancellation_deadlines,
            premium_summary=premium_summary,
        )

        if persist:
            await self._persist_insurance_kpis(db, space_id, kpis)

        return kpis

    async def _persist_insurance_kpis(
        self,
        db: AsyncSession,
        space_id: UUID,
        kpis: InsuranceKPIs,
    ) -> None:
        """
        Speichert berechnete KPIs in der Datenbank.

        Args:
            db: Datenbank-Session
            space_id: Space-ID
            kpis: Berechnete KPIs
        """
        from app.db.models import PrivatInsurance

        # Kuendigungsfristen in einzelne Versicherungen speichern
        for deadline in kpis.cancellation_deadlines:
            result = await db.execute(
                select(PrivatInsurance).where(PrivatInsurance.id == deadline.insurance_id)
            )
            insurance = result.scalar_one_or_none()

            if insurance:
                insurance.cancellation_deadline = deadline.cancellation_deadline
                insurance.last_kpi_calculation = datetime.now(timezone.utc)

                # Praemie annualisieren
                if kpis.premium_summary:
                    ins_type = self._normalize_insurance_type(insurance.insurance_type)
                    if ins_type in kpis.premium_summary.by_type:
                        insurance.annual_premium_total = kpis.premium_summary.by_type[ins_type]

                # Coverage Score fuer diese Versicherung
                if kpis.coverage_analysis:
                    insurance.coverage_adequacy_score = kpis.coverage_analysis.coverage_score

                    # Gap Analysis als JSON speichern
                    gaps_for_type = [
                        {
                            "type": g.insurance_type,
                            "recommended": float(g.recommended_coverage),
                            "current": float(g.current_coverage),
                            "gap": float(g.gap_amount),
                            "severity": g.severity,
                        }
                        for g in kpis.coverage_analysis.gaps
                        if self._normalize_insurance_type(insurance.insurance_type) == g.insurance_type
                    ]
                    if gaps_for_type:
                        insurance.coverage_gap_analysis = {"gaps": gaps_for_type}

        await db.flush()

        logger.info(
            "insurance_kpis_persisted",
            space_id=str(space_id),
            deadlines_count=len(kpis.cancellation_deadlines),
        )

    # =========================================================================
    # Einzelversicherung analysieren
    # =========================================================================

    async def analyze_single_insurance(
        self,
        db: AsyncSession,
        insurance_id: UUID,
        persist: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """
        Analysiert eine einzelne Versicherung.

        Args:
            db: Datenbank-Session
            insurance_id: Versicherungs-ID
            persist: Ob die Werte in der Datenbank gespeichert werden sollen

        Returns:
            Analyse-Dictionary oder None
        """
        from app.db.models import PrivatInsurance

        INSURANCE_CALCULATIONS.labels(calculation_type="single_analysis").inc()

        result = await db.execute(
            select(PrivatInsurance).where(PrivatInsurance.id == insurance_id)
        )
        insurance = result.scalar_one_or_none()

        if not insurance:
            return None

        # Typ normalisieren
        ins_type = self._normalize_insurance_type(insurance.insurance_type)
        recommendation = RECOMMENDED_COVERAGE.get(ins_type)

        analysis: Dict[str, Any] = {
            "insurance_id": str(insurance_id),
            "insurance_type": ins_type,
            "insurance_name": insurance.name,
        }

        # Deckungsanalyse
        if recommendation:
            current = insurance.coverage_amount or Decimal("0")
            recommended = recommendation["recommended_coverage"]

            if recommended > 0:
                coverage_ratio = float(current / recommended)
                analysis["coverage_ratio"] = round(coverage_ratio, 2)
                analysis["is_adequate"] = coverage_ratio >= 1.0
                analysis["recommended_coverage"] = float(recommended)
                analysis["current_coverage"] = float(current)

        # Kuendigungsfrist
        today = date.today()
        if insurance.end_date or insurance.is_auto_renew:
            contract_end = insurance.end_date
            if contract_end is None and insurance.is_auto_renew and insurance.start_date:
                years_since_start = (today.year - insurance.start_date.year)
                if today.month < insurance.start_date.month or \
                   (today.month == insurance.start_date.month and today.day < insurance.start_date.day):
                    years_since_start -= 1
                contract_end = insurance.start_date.replace(
                    year=insurance.start_date.year + years_since_start + 1
                )

            if contract_end:
                cancellation_months = insurance.cancellation_period_months or 3
                cancellation_deadline = contract_end - timedelta(days=cancellation_months * 30)
                days_until = (cancellation_deadline - today).days

                analysis["contract_end"] = str(contract_end)
                analysis["cancellation_deadline"] = str(cancellation_deadline)
                analysis["days_until_deadline"] = days_until
                analysis["is_urgent"] = days_until <= 30

        # Jaehrliche Praemie
        if insurance.premium_amount:
            annual = insurance.premium_amount
            frequency = insurance.premium_frequency or "yearly"
            if frequency == "monthly":
                annual = insurance.premium_amount * 12
            elif frequency == "quarterly":
                annual = insurance.premium_amount * 4
            elif frequency == "half-yearly":
                annual = insurance.premium_amount * 2

            analysis["annual_premium"] = float(annual)

        # Persist
        if persist and insurance:
            if "cancellation_deadline" in analysis:
                insurance.cancellation_deadline = date.fromisoformat(analysis["cancellation_deadline"])
            if "annual_premium" in analysis:
                insurance.annual_premium_total = Decimal(str(analysis["annual_premium"]))
            if "coverage_ratio" in analysis:
                insurance.coverage_adequacy_score = Decimal(str(analysis["coverage_ratio"] * 100))
            insurance.last_kpi_calculation = datetime.now(timezone.utc)
            await db.flush()

        return analysis


# =============================================================================
# Singleton
# =============================================================================

_insurance_analysis_service: Optional[InsuranceAnalysisService] = None
_service_lock = threading.Lock()


def get_insurance_analysis_service() -> InsuranceAnalysisService:
    """Factory fuer InsuranceAnalysisService Singleton (Thread-safe)."""
    global _insurance_analysis_service
    if _insurance_analysis_service is None:
        with _service_lock:
            if _insurance_analysis_service is None:
                _insurance_analysis_service = InsuranceAnalysisService()
    return _insurance_analysis_service

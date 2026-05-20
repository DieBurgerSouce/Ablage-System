# -*- coding: utf-8 -*-
"""
Seasonal Pattern Detector Service.

Enterprise Feature: Proaktive Erkennung und Warnung bei saisonalen Mustern.

Features:
- Analyse historischer Daten nach Monat
- Q4-Spitzen und Sommer-Einbrueche erkennen
- Vergleich aktuelles vs. vorheriges Jahr
- Proaktive Warnungen generieren
- Liquiditaetsanpassungen vorschlagen

Feinpoliert und durchdacht - Proaktive Finanzplanung.
"""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from statistics import mean, stdev
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID, uuid4

import structlog
from sqlalchemy import and_, extract, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.safe_errors import safe_error_log
from app.db.models import Document, InvoiceTracking, BankTransaction, Company
from app.db.models_alert import Alert, AlertCategory, AlertSeverity

logger = structlog.get_logger(__name__)


# =============================================================================
# Enums
# =============================================================================


class TrendType(str, Enum):
    """Arten von Trends."""
    INCREASING = "increasing"
    DECREASING = "decreasing"
    STABLE = "stable"
    VOLATILE = "volatile"


class SeasonalPhase(str, Enum):
    """Saisonale Phasen."""
    Q1 = "q1"  # Januar-Maerz
    Q2 = "q2"  # April-Juni
    Q3 = "q3"  # Juli-September
    Q4 = "q4"  # Oktober-Dezember
    SUMMER = "summer"  # Juni-August
    WINTER = "winter"  # Dezember-Februar
    YEAR_END = "year_end"  # November-Dezember


class AlertPriority(str, Enum):
    """Priorität von Warnungen."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class MonthlyStats:
    """Statistiken für einen Monat."""
    month: int  # 1-12
    year: int
    total_revenue: Decimal = Decimal("0")
    total_expenses: Decimal = Decimal("0")
    invoice_count: int = 0
    average_invoice_amount: Decimal = Decimal("0")
    payment_delay_days: float = 0.0


@dataclass
class SeasonalPattern:
    """Ein erkanntes saisonales Muster."""
    id: UUID = field(default_factory=uuid4)
    company_id: UUID = field(default_factory=uuid4)
    pattern_type: str = ""
    description: str = ""

    # Zeitraum
    peak_months: List[int] = field(default_factory=list)
    low_months: List[int] = field(default_factory=list)

    # Metriken
    peak_factor: float = 1.0  # Multiplikator gegenüber Durchschnitt
    low_factor: float = 1.0
    variability_coefficient: float = 0.0

    # Konfidenz
    confidence: float = 0.5
    data_points: int = 0

    detected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class YearComparison:
    """Vergleich zwischen Jahren."""
    company_id: UUID = field(default_factory=uuid4)
    current_year: int = 2026
    previous_year: int = 2025

    # Vergleichsmetriken
    revenue_change_percent: float = 0.0
    expense_change_percent: float = 0.0
    invoice_volume_change_percent: float = 0.0

    # Monatliche Unterschiede (month -> change_percent)
    monthly_differences: Dict[int, float] = field(default_factory=dict)

    # Auffälligkeiten
    anomalies: List[str] = field(default_factory=list)


@dataclass
class SeasonalWarning:
    """Eine saisonale Warnung."""
    id: UUID = field(default_factory=uuid4)
    company_id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Warnung
    title: str = ""
    description: str = ""
    priority: AlertPriority = AlertPriority.MEDIUM

    # Kontext
    affected_period: str = ""
    expected_impact_amount: Decimal = Decimal("0")
    historical_pattern: Optional[SeasonalPattern] = None

    # Empfehlungen
    recommendations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            "id": str(self.id),
            "company_id": str(self.company_id),
            "created_at": self.created_at.isoformat(),
            "title": self.title,
            "description": self.description,
            "priority": self.priority.value,
            "affected_period": self.affected_period,
            "expected_impact_amount": float(self.expected_impact_amount),
            "recommendations": self.recommendations,
        }


@dataclass
class LiquidityAdjustment:
    """Vorgeschlagene Liquiditaetsanpassung."""
    id: UUID = field(default_factory=uuid4)
    company_id: UUID = field(default_factory=uuid4)

    # Anpassung
    adjustment_type: str = ""  # "reserve", "credit_line", "payment_deferral"
    description: str = ""
    amount: Decimal = Decimal("0")

    # Zeitraum
    effective_from: date = field(default_factory=date.today)
    effective_until: date = field(default_factory=date.today)

    # Begruendung
    reason: str = ""
    based_on_pattern: Optional[SeasonalPattern] = None


@dataclass
class SeasonalAnalysis:
    """Vollständige saisonale Analyse."""
    id: UUID = field(default_factory=uuid4)
    company_id: UUID = field(default_factory=uuid4)
    analysis_date: date = field(default_factory=date.today)

    # Erkannte Muster
    patterns: List[SeasonalPattern] = field(default_factory=list)

    # Jahresvergleich
    year_comparison: Optional[YearComparison] = None

    # Warnungen
    warnings: List[SeasonalWarning] = field(default_factory=list)

    # Anpassungsvorschläge
    liquidity_adjustments: List[LiquidityAdjustment] = field(default_factory=list)

    # Metriken
    analysis_time_ms: int = 0
    data_points_analyzed: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            "id": str(self.id),
            "company_id": str(self.company_id),
            "analysis_date": self.analysis_date.isoformat(),
            "patterns_count": len(self.patterns),
            "warnings_count": len(self.warnings),
            "adjustments_count": len(self.liquidity_adjustments),
            "warnings": [w.to_dict() for w in self.warnings],
        }


# =============================================================================
# Seasonal Detector Service
# =============================================================================


class SeasonalDetectorService:
    """
    Service für saisonale Mustererkennung und proaktive Warnungen.

    Analysiert historische Daten um saisonale Muster zu erkennen
    und generiert proaktive Warnungen und Liquiditaetsempfehlungen.
    """

    _instance: Optional["SeasonalDetectorService"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "SeasonalDetectorService":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True

        # Cache für Muster
        self._pattern_cache: Dict[UUID, List[SeasonalPattern]] = {}
        self._cache_lock = asyncio.Lock()

        # Konfiguration
        self._lookback_years = 3  # Jahre für Analyse
        self._min_data_months = 12  # Mindest-Datenpunkte

        # Deutsche Monatsnamen
        self._month_names = {
            1: "Januar", 2: "Februar", 3: "Maerz", 4: "April",
            5: "Mai", 6: "Juni", 7: "Juli", 8: "August",
            9: "September", 10: "Oktober", 11: "November", 12: "Dezember",
        }

        logger.info("seasonal_detector_service_initialized")

    # =========================================================================
    # Main Analysis
    # =========================================================================

    async def analyze_company_seasonality(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> SeasonalAnalysis:
        """
        Führt eine vollständige saisonale Analyse für eine Company durch.

        Args:
            db: Database Session
            company_id: Company ID

        Returns:
            SeasonalAnalysis mit Mustern, Warnungen und Empfehlungen
        """
        start_time = datetime.now(timezone.utc)

        # 1. Historische Daten sammeln
        monthly_stats = await self._collect_monthly_stats(db, company_id)

        if len(monthly_stats) < self._min_data_months:
            logger.warning(
                "insufficient_data_for_seasonal_analysis",
                company_id=str(company_id),
                data_points=len(monthly_stats),
                required=self._min_data_months,
            )
            return SeasonalAnalysis(
                company_id=company_id,
                data_points_analyzed=len(monthly_stats),
            )

        # 2. Muster erkennen
        patterns = await self._detect_patterns(company_id, monthly_stats)

        # 3. Jahresvergleich
        year_comparison = await self._compare_years(company_id, monthly_stats)

        # 4. Warnungen generieren
        warnings = await self._generate_warnings(
            company_id, patterns, year_comparison, monthly_stats
        )

        # 5. Liquiditaetsanpassungen vorschlagen
        adjustments = await self._suggest_liquidity_adjustments(
            company_id, patterns, warnings
        )

        # 6. Alerts erstellen für kritische Warnungen
        for warning in warnings:
            if warning.priority in [AlertPriority.HIGH, AlertPriority.CRITICAL]:
                await self._create_warning_alert(db, warning)

        elapsed = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)

        analysis = SeasonalAnalysis(
            company_id=company_id,
            patterns=patterns,
            year_comparison=year_comparison,
            warnings=warnings,
            liquidity_adjustments=adjustments,
            analysis_time_ms=elapsed,
            data_points_analyzed=len(monthly_stats),
        )

        # Cache aktualisieren
        async with self._cache_lock:
            self._pattern_cache[company_id] = patterns

        logger.info(
            "seasonal_analysis_completed",
            company_id=str(company_id),
            patterns_found=len(patterns),
            warnings_generated=len(warnings),
            adjustments_suggested=len(adjustments),
            analysis_time_ms=elapsed,
        )

        return analysis

    # =========================================================================
    # Data Collection
    # =========================================================================

    async def _collect_monthly_stats(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> List[MonthlyStats]:
        """Sammelt monatliche Statistiken."""
        stats: List[MonthlyStats] = []
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=self._lookback_years * 365)

        # Einnahmen aus Rechnungen (bezahlt)
        revenue_query = (
            select(
                extract('year', InvoiceTracking.paid_at).label('year'),
                extract('month', InvoiceTracking.paid_at).label('month'),
                func.sum(InvoiceTracking.gross_amount).label('total'),
                func.count(InvoiceTracking.id).label('count'),
                func.avg(InvoiceTracking.gross_amount).label('avg'),
            )
            .join(Document, InvoiceTracking.document_id == Document.id)
            .where(
                and_(
                    Document.company_id == company_id,
                    InvoiceTracking.paid_at >= cutoff_date,
                    InvoiceTracking.status == 'paid',
                )
            )
            .group_by(
                extract('year', InvoiceTracking.paid_at),
                extract('month', InvoiceTracking.paid_at),
            )
        )

        result = await db.execute(revenue_query)
        revenue_data = {(int(r[0]), int(r[1])): r for r in result.all()}

        # Ausgaben aus Transaktionen (negativ)
        expense_query = (
            select(
                extract('year', BankTransaction.booking_date).label('year'),
                extract('month', BankTransaction.booking_date).label('month'),
                func.sum(BankTransaction.amount).label('total'),
            )
            .where(
                and_(
                    BankTransaction.company_id == company_id,
                    BankTransaction.booking_date >= cutoff_date,
                    BankTransaction.amount < 0,
                )
            )
            .group_by(
                extract('year', BankTransaction.booking_date),
                extract('month', BankTransaction.booking_date),
            )
        )

        result = await db.execute(expense_query)
        expense_data = {(int(r[0]), int(r[1])): r for r in result.all()}

        # Statistiken zusammenführen
        all_months = set(revenue_data.keys()) | set(expense_data.keys())

        for year, month in sorted(all_months):
            rev_row = revenue_data.get((year, month))
            exp_row = expense_data.get((year, month))

            monthly_stat = MonthlyStats(
                month=month,
                year=year,
                total_revenue=Decimal(str(rev_row[2] or 0)) if rev_row else Decimal("0"),
                total_expenses=abs(Decimal(str(exp_row[2] or 0))) if exp_row else Decimal("0"),
                invoice_count=int(rev_row[3] or 0) if rev_row else 0,
                average_invoice_amount=Decimal(str(rev_row[4] or 0)) if rev_row else Decimal("0"),
            )
            stats.append(monthly_stat)

        return stats

    # =========================================================================
    # Pattern Detection
    # =========================================================================

    async def _detect_patterns(
        self,
        company_id: UUID,
        monthly_stats: List[MonthlyStats],
    ) -> List[SeasonalPattern]:
        """Erkennt saisonale Muster in den Daten."""
        patterns: List[SeasonalPattern] = []

        # Gruppiere nach Monat (über alle Jahre)
        by_month: Dict[int, List[Decimal]] = {m: [] for m in range(1, 13)}
        for stat in monthly_stats:
            by_month[stat.month].append(stat.total_revenue)

        # Berechne Durchschnitte
        monthly_averages: Dict[int, float] = {}
        for month, values in by_month.items():
            if values:
                monthly_averages[month] = float(mean([float(v) for v in values]))
            else:
                monthly_averages[month] = 0.0

        if not monthly_averages or all(v == 0 for v in monthly_averages.values()):
            return patterns

        overall_avg = mean([v for v in monthly_averages.values() if v > 0])
        if overall_avg == 0:
            return patterns

        # Q4-Spitze erkennen
        q4_avg = mean([monthly_averages[m] for m in [10, 11, 12] if monthly_averages[m] > 0] or [0])
        if q4_avg > overall_avg * 1.2:  # 20% über Durchschnitt
            patterns.append(SeasonalPattern(
                company_id=company_id,
                pattern_type="q4_peak",
                description="Erhöhte Umsätze im vierten Quartal (Oktober-Dezember)",
                peak_months=[10, 11, 12],
                low_months=[],
                peak_factor=q4_avg / overall_avg if overall_avg > 0 else 1.0,
                confidence=0.8 if len(monthly_stats) >= 24 else 0.6,
                data_points=len(monthly_stats),
            ))

        # Sommer-Einbruch erkennen
        summer_avg = mean([monthly_averages[m] for m in [6, 7, 8] if monthly_averages[m] > 0] or [0])
        if summer_avg < overall_avg * 0.8:  # 20% unter Durchschnitt
            patterns.append(SeasonalPattern(
                company_id=company_id,
                pattern_type="summer_dip",
                description="Umsatzrückgang in den Sommermonaten (Juni-August)",
                peak_months=[],
                low_months=[6, 7, 8],
                low_factor=summer_avg / overall_avg if overall_avg > 0 else 1.0,
                confidence=0.75 if len(monthly_stats) >= 24 else 0.55,
                data_points=len(monthly_stats),
            ))

        # Jahresende-Spitze (November-Dezember)
        year_end_avg = mean([monthly_averages[m] for m in [11, 12] if monthly_averages[m] > 0] or [0])
        if year_end_avg > overall_avg * 1.3:  # 30% über Durchschnitt
            patterns.append(SeasonalPattern(
                company_id=company_id,
                pattern_type="year_end_peak",
                description="Jahresend-Spitze im November/Dezember",
                peak_months=[11, 12],
                low_months=[],
                peak_factor=year_end_avg / overall_avg if overall_avg > 0 else 1.0,
                confidence=0.85 if len(monthly_stats) >= 24 else 0.65,
                data_points=len(monthly_stats),
            ))

        # Januar-Einbruch (nach Weihnachten)
        jan_avg = monthly_averages.get(1, 0)
        dec_avg = monthly_averages.get(12, 0)
        if jan_avg > 0 and dec_avg > 0 and jan_avg < dec_avg * 0.6:
            patterns.append(SeasonalPattern(
                company_id=company_id,
                pattern_type="january_dip",
                description="Umsatzrückgang im Januar nach Weihnachtsgeschäft",
                peak_months=[],
                low_months=[1],
                low_factor=jan_avg / overall_avg if overall_avg > 0 else 1.0,
                confidence=0.70,
                data_points=len(monthly_stats),
            ))

        # Variabilitaet berechnen
        try:
            values = [float(v) for v in monthly_averages.values() if v > 0]
            if len(values) >= 2:
                cv = stdev(values) / mean(values) if mean(values) > 0 else 0
                if cv > 0.3:  # Hohe Variabilitaet
                    patterns.append(SeasonalPattern(
                        company_id=company_id,
                        pattern_type="high_variability",
                        description=f"Hohe monatliche Umsatzschwankungen (CV: {cv:.2f})",
                        variability_coefficient=cv,
                        confidence=0.9,
                        data_points=len(monthly_stats),
                    ))
        except Exception:
            pass

        return patterns

    # =========================================================================
    # Year Comparison
    # =========================================================================

    async def _compare_years(
        self,
        company_id: UUID,
        monthly_stats: List[MonthlyStats],
    ) -> Optional[YearComparison]:
        """Vergleicht aktuelles mit vorherigem Jahr."""
        current_year = datetime.now().year
        previous_year = current_year - 1

        current_data = [s for s in monthly_stats if s.year == current_year]
        previous_data = [s for s in monthly_stats if s.year == previous_year]

        if not current_data or not previous_data:
            return None

        # Gesamtvergleich
        current_revenue = sum(s.total_revenue for s in current_data)
        previous_revenue = sum(s.total_revenue for s in previous_data)

        current_expenses = sum(s.total_expenses for s in current_data)
        previous_expenses = sum(s.total_expenses for s in previous_data)

        revenue_change = (
            ((current_revenue - previous_revenue) / previous_revenue * 100)
            if previous_revenue > 0
            else 0.0
        )

        expense_change = (
            ((current_expenses - previous_expenses) / previous_expenses * 100)
            if previous_expenses > 0
            else 0.0
        )

        # Monatliche Unterschiede
        monthly_diffs: Dict[int, float] = {}
        anomalies: List[str] = []

        current_by_month = {s.month: s for s in current_data}
        previous_by_month = {s.month: s for s in previous_data}

        for month in range(1, 13):
            curr = current_by_month.get(month)
            prev = previous_by_month.get(month)

            if curr and prev and prev.total_revenue > 0:
                diff = float((curr.total_revenue - prev.total_revenue) / prev.total_revenue * 100)
                monthly_diffs[month] = diff

                # Anomalien erkennen
                if diff < -30:
                    anomalies.append(
                        f"{self._month_names[month]}: Umsatzrückgang von {abs(diff):.0f}% gegenüber Vorjahr"
                    )
                elif diff > 50:
                    anomalies.append(
                        f"{self._month_names[month]}: Umsatzsteigerung von {diff:.0f}% gegenüber Vorjahr"
                    )

        return YearComparison(
            company_id=company_id,
            current_year=current_year,
            previous_year=previous_year,
            revenue_change_percent=float(revenue_change),
            expense_change_percent=float(expense_change),
            monthly_differences=monthly_diffs,
            anomalies=anomalies,
        )

    # =========================================================================
    # Warning Generation
    # =========================================================================

    async def _generate_warnings(
        self,
        company_id: UUID,
        patterns: List[SeasonalPattern],
        year_comparison: Optional[YearComparison],
        monthly_stats: List[MonthlyStats],
    ) -> List[SeasonalWarning]:
        """Generiert proaktive Warnungen."""
        warnings: List[SeasonalWarning] = []
        current_month = datetime.now().month

        # Warnung vor Q4-Spitze (wenn in Q3)
        q4_pattern = next((p for p in patterns if p.pattern_type == "q4_peak"), None)
        if q4_pattern and current_month in [7, 8, 9]:
            expected_increase = (q4_pattern.peak_factor - 1) * 100
            recent_revenue = self._get_recent_monthly_revenue(monthly_stats)

            warnings.append(SeasonalWarning(
                company_id=company_id,
                title="Q4-Spitze erwartet",
                description=(
                    f"Basierend auf historischen Daten erwarten wir im Q4 "
                    f"einen Umsatzanstieg von ca. {expected_increase:.0f}%."
                ),
                priority=AlertPriority.MEDIUM,
                affected_period="Oktober bis Dezember",
                expected_impact_amount=recent_revenue * Decimal(str(q4_pattern.peak_factor - 1)),
                historical_pattern=q4_pattern,
                recommendations=[
                    "Lagerbestände frühzeitig aufstocken",
                    "Personalplanung für Q4 vorbereiten",
                    "Liquiditaet für erhöhte Einkaufskosten sicherstellen",
                ],
            ))

        # Warnung vor Sommer-Einbruch (wenn in Q2)
        summer_pattern = next((p for p in patterns if p.pattern_type == "summer_dip"), None)
        if summer_pattern and current_month in [4, 5]:
            expected_decrease = (1 - summer_pattern.low_factor) * 100
            recent_revenue = self._get_recent_monthly_revenue(monthly_stats)

            warnings.append(SeasonalWarning(
                company_id=company_id,
                title="Sommer-Einbruch erwartet",
                description=(
                    f"Historische Daten zeigen einen typischen Umsatzrückgang "
                    f"von ca. {expected_decrease:.0f}% in den Sommermonaten."
                ),
                priority=AlertPriority.HIGH,
                affected_period="Juni bis August",
                expected_impact_amount=recent_revenue * Decimal(str(1 - summer_pattern.low_factor)),
                historical_pattern=summer_pattern,
                recommendations=[
                    "Fixkosten auf Minimum reduzieren",
                    "Zahlungsziele mit Lieferanten verhandeln",
                    "Marketing für Sommerangebote vorbereiten",
                    "Liquiditaetsreserve aufbauen",
                ],
            ))

        # Warnung bei Jahresvergleich-Anomalien
        if year_comparison and year_comparison.revenue_change_percent < -20:
            warnings.append(SeasonalWarning(
                company_id=company_id,
                title="Deutlicher Umsatzrückgang",
                description=(
                    f"Der Umsatz liegt {abs(year_comparison.revenue_change_percent):.0f}% "
                    f"unter dem Vorjahresniveau."
                ),
                priority=AlertPriority.CRITICAL,
                affected_period=f"{year_comparison.current_year}",
                recommendations=[
                    "Ursachenanalyse durchführen",
                    "Kostensenkungspotenziale identifizieren",
                    "Vertriebsaktivitäten intensivieren",
                    "Bankgespraeche zur Liquiditaetssicherung führen",
                ],
            ))

        # Warnung vor Variabilitaet
        var_pattern = next((p for p in patterns if p.pattern_type == "high_variability"), None)
        if var_pattern:
            warnings.append(SeasonalWarning(
                company_id=company_id,
                title="Hohe Umsatzschwankungen",
                description=(
                    f"Die monatlichen Umsätze schwanken stark "
                    f"(Variationskoeffizient: {var_pattern.variability_coefficient:.2f})."
                ),
                priority=AlertPriority.MEDIUM,
                affected_period="Ganzjaehrig",
                historical_pattern=var_pattern,
                recommendations=[
                    "Liquiditaetsreserve erhöhen",
                    "Fixkosten flexibilisieren",
                    "Umsatzdiversifikation prüfen",
                    "Rahmenverträge mit Kunden abschließen",
                ],
            ))

        return warnings

    def _get_recent_monthly_revenue(
        self,
        monthly_stats: List[MonthlyStats],
    ) -> Decimal:
        """Ermittelt den durchschnittlichen monatlichen Umsatz der letzten 3 Monate."""
        if not monthly_stats:
            return Decimal("0")

        # Sortiere nach Datum (neueste zuerst)
        sorted_stats = sorted(
            monthly_stats,
            key=lambda s: (s.year, s.month),
            reverse=True,
        )

        recent = sorted_stats[:3]
        if not recent:
            return Decimal("0")

        return sum(s.total_revenue for s in recent) / len(recent)

    # =========================================================================
    # Liquidity Adjustments
    # =========================================================================

    async def _suggest_liquidity_adjustments(
        self,
        company_id: UUID,
        patterns: List[SeasonalPattern],
        warnings: List[SeasonalWarning],
    ) -> List[LiquidityAdjustment]:
        """Generiert Liquiditaetsanpassungsvorschläge."""
        adjustments: List[LiquidityAdjustment] = []
        today = date.today()

        # Bei Sommer-Einbruch: Reserve aufbauen
        summer_warning = next(
            (w for w in warnings if "Sommer" in w.title),
            None,
        )
        if summer_warning:
            summer_start = date(today.year, 6, 1)
            if today < summer_start:
                adjustments.append(LiquidityAdjustment(
                    company_id=company_id,
                    adjustment_type="reserve",
                    description="Liquiditaetsreserve für Sommereinbruch aufbauen",
                    amount=summer_warning.expected_impact_amount * Decimal("1.2"),  # 20% Puffer
                    effective_from=today,
                    effective_until=summer_start,
                    reason="Erwarteter Umsatzrückgang in den Sommermonaten",
                ))

        # Bei Q4-Spitze: Kreditlinie erhöhen
        q4_warning = next(
            (w for w in warnings if "Q4" in w.title),
            None,
        )
        if q4_warning:
            q4_start = date(today.year, 10, 1)
            if today < q4_start:
                adjustments.append(LiquidityAdjustment(
                    company_id=company_id,
                    adjustment_type="credit_line",
                    description="Kreditlinie für Q4-Wareneinkauf erhöhen",
                    amount=q4_warning.expected_impact_amount * Decimal("0.5"),
                    effective_from=date(today.year, 9, 15),
                    effective_until=date(today.year, 12, 31),
                    reason="Erhöhter Kapitalbedarf für Q4-Hochsaison",
                ))

        # Bei hoher Variabilitaet: Generelle Reserve
        var_pattern = next(
            (p for p in patterns if p.pattern_type == "high_variability"),
            None,
        )
        if var_pattern:
            adjustments.append(LiquidityAdjustment(
                company_id=company_id,
                adjustment_type="reserve",
                description="Erhöhte Liquiditaetsreserve aufgrund hoher Umsatzschwankungen",
                amount=Decimal("0"),  # Wird individuell berechnet
                effective_from=today,
                effective_until=date(today.year, 12, 31),
                reason="Hohe monatliche Umsatzvariabilitaet erfordert Puffer",
                based_on_pattern=var_pattern,
            ))

        return adjustments

    # =========================================================================
    # Alert Creation
    # =========================================================================

    async def _create_warning_alert(
        self,
        db: AsyncSession,
        warning: SeasonalWarning,
    ) -> UUID:
        """Erstellt einen Alert für eine Warnung."""
        severity_map = {
            AlertPriority.LOW: AlertSeverity.LOW,
            AlertPriority.MEDIUM: AlertSeverity.MEDIUM,
            AlertPriority.HIGH: AlertSeverity.HIGH,
            AlertPriority.CRITICAL: AlertSeverity.CRITICAL,
        }

        alert = Alert(
            company_id=warning.company_id,
            alert_code="SEASONAL_WARNING",
            category=AlertCategory.DEADLINE.value,
            severity=severity_map[warning.priority].value,
            title=warning.title,
            message=warning.description,
            source_type="seasonal_detector",
            source_id=str(warning.id),
            metadata={
                "affected_period": warning.affected_period,
                "expected_impact": float(warning.expected_impact_amount),
            },
            context={
                "recommendations": warning.recommendations,
            },
            available_actions=["acknowledge", "dismiss"],
        )

        db.add(alert)
        await db.flush()

        return alert.id

    # =========================================================================
    # Public API
    # =========================================================================

    async def get_cached_patterns(
        self,
        company_id: UUID,
    ) -> List[SeasonalPattern]:
        """Gibt gecachte Muster zurück."""
        async with self._cache_lock:
            return self._pattern_cache.get(company_id, [])

    async def get_upcoming_seasonal_events(
        self,
        company_id: UUID,
        horizon_days: int = 90,
    ) -> List[Dict[str, Any]]:
        """Gibt bevorstehende saisonale Events zurück."""
        events: List[Dict[str, Any]] = []
        today = date.today()

        async with self._cache_lock:
            patterns = self._pattern_cache.get(company_id, [])

        for pattern in patterns:
            if pattern.peak_months:
                for month in pattern.peak_months:
                    event_date = date(today.year, month, 1)
                    if event_date < today:
                        event_date = date(today.year + 1, month, 1)

                    days_until = (event_date - today).days
                    if 0 < days_until <= horizon_days:
                        events.append({
                            "date": event_date.isoformat(),
                            "days_until": days_until,
                            "type": "peak",
                            "pattern_type": pattern.pattern_type,
                            "description": pattern.description,
                            "factor": pattern.peak_factor,
                        })

            if pattern.low_months:
                for month in pattern.low_months:
                    event_date = date(today.year, month, 1)
                    if event_date < today:
                        event_date = date(today.year + 1, month, 1)

                    days_until = (event_date - today).days
                    if 0 < days_until <= horizon_days:
                        events.append({
                            "date": event_date.isoformat(),
                            "days_until": days_until,
                            "type": "low",
                            "pattern_type": pattern.pattern_type,
                            "description": pattern.description,
                            "factor": pattern.low_factor,
                        })

        # Sortiere nach Datum
        events.sort(key=lambda e: e["days_until"])

        return events


# =============================================================================
# Singleton Factory
# =============================================================================

_service_instance: Optional[SeasonalDetectorService] = None
_service_lock = threading.Lock()


def get_seasonal_detector_service() -> SeasonalDetectorService:
    """Factory-Funktion für SeasonalDetectorService Singleton."""
    global _service_instance
    if _service_instance is None:
        with _service_lock:
            if _service_instance is None:
                _service_instance = SeasonalDetectorService()
    return _service_instance

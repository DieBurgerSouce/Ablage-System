# -*- coding: utf-8 -*-
"""
PredictiveIntelligenceService - Antizipiert Probleme bevor sie auftreten.

Enterprise Predictive Intelligence Features:
1. KPI-Projektion: Extrapoliert alle KPIs 3/6/12 Monate in die Zukunft
2. Early Warning Alerts: Warnt BEVOR ein Schwellenwert erreicht wird
3. Trend-Analyse: Linear, Exponentiell, Saisonal
4. Threshold-Breach Detection: Erkennt kommende Probleme

Das System REAGIERT nicht mehr nur - es ANTIZIPIERT.
KEINE externen APIs - alles lokal berechnet.
"""

from __future__ import annotations

import math
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone, date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Tuple, Sequence
from uuid import UUID
from enum import Enum
from collections import defaultdict

import numpy as np
import structlog
from prometheus_client import Counter, Histogram, Gauge
from sqlalchemy import select, func, and_, or_, desc, asc
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    PrivatKPIHistory,
    PrivatProjection,
    PrivatEarlyWarning,
    PrivatUserThreshold,
    PrivatSpace,
    ProjectionMethod,
    TrendDirection,
    WarningSeverity,
    WarningType,
    KPIUnit,
    ProfessionType,
    RiskProfile,
)

logger = structlog.get_logger(__name__)


# =============================================================================
# Prometheus Metriken
# =============================================================================

PREDICTION_CALCULATIONS = Counter(
    "predictive_intelligence_calculations_total",
    "Anzahl der Predictive Intelligence Berechnungen",
    ["calculation_type"]
)

PREDICTION_DURATION = Histogram(
    "predictive_intelligence_duration_seconds",
    "Dauer der Predictive Intelligence Berechnung",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
)

EARLY_WARNINGS_GENERATED = Counter(
    "early_warnings_generated_total",
    "Anzahl der generierten Early Warnings",
    ["severity", "kpi_name"]
)

ACTIVE_WARNINGS_GAUGE = Gauge(
    "active_early_warnings",
    "Anzahl aktiver Early Warnings",
    ["space_id"]
)


# =============================================================================
# KPI-Definitionen und Schwellenwerte
# =============================================================================

# Standard-Schwellenwerte (koennen pro User angepasst werden)
DEFAULT_THRESHOLDS: Dict[str, Dict[str, Decimal]] = {
    # Debt-to-Income Ratio (niedriger ist besser)
    "dti_ratio": {
        "warning": Decimal("0.36"),      # 36% - Standard-Grenze
        "critical": Decimal("0.50"),     # 50% - Kritisch
        "direction": Decimal("-1"),      # Negativ = hoeher ist schlecht
    },
    # Notgroschen in Monaten (hoeher ist besser)
    "emergency_fund_months": {
        "warning": Decimal("3"),         # 3 Monate minimum
        "critical": Decimal("1"),        # 1 Monat kritisch
        "direction": Decimal("1"),       # Positiv = niedriger ist schlecht
    },
    # Financial Health Score (hoeher ist besser)
    "financial_health_score": {
        "warning": Decimal("50"),        # Unter 50 = Warnung
        "critical": Decimal("30"),       # Unter 30 = Kritisch
        "direction": Decimal("1"),
    },
    # Net Worth (hoeher ist besser, negativ ist schlecht)
    "net_worth": {
        "warning": Decimal("0"),         # Negatives Net Worth
        "critical": Decimal("-50000"),   # Stark negativ
        "direction": Decimal("1"),
    },
    # Monatliche Sparquote % (hoeher ist besser)
    "savings_rate": {
        "warning": Decimal("10"),        # Unter 10% Sparquote
        "critical": Decimal("0"),        # Keine Ersparnisse
        "direction": Decimal("1"),
    },
    # Liquiditaetsquote (hoeher ist besser)
    "liquidity_ratio": {
        "warning": Decimal("0.20"),      # Unter 20%
        "critical": Decimal("0.10"),     # Unter 10%
        "direction": Decimal("1"),
    },
    # Versicherungsdeckungsquote (hoeher ist besser)
    "insurance_coverage": {
        "warning": Decimal("60"),        # Unter 60%
        "critical": Decimal("40"),       # Unter 40%
        "direction": Decimal("1"),
    },
    # Immobilien-Rendite % (hoeher ist besser)
    "property_yield": {
        "warning": Decimal("3"),         # Unter 3%
        "critical": Decimal("1"),        # Unter 1%
        "direction": Decimal("1"),
    },
    # Fahrzeug-TCO als % des Einkommens (niedriger ist besser)
    "vehicle_tco_ratio": {
        "warning": Decimal("0.15"),      # Ueber 15%
        "critical": Decimal("0.25"),     # Ueber 25%
        "direction": Decimal("-1"),
    },
    # Kredit-Zinsbelastung % (niedriger ist besser)
    "interest_burden": {
        "warning": Decimal("0.08"),      # Ueber 8%
        "critical": Decimal("0.15"),     # Ueber 15%
        "direction": Decimal("-1"),
    },
}

# Profession-basierte Anpassungen
PROFESSION_THRESHOLD_ADJUSTMENTS: Dict[str, Dict[str, Decimal]] = {
    "freelancer": {
        "dti_ratio_warning": Decimal("0.40"),        # Freelancer = mehr Varianz ok
        "emergency_fund_months_warning": Decimal("9"),  # Brauchen mehr Reserve
    },
    "civil_servant": {
        "emergency_fund_months_warning": Decimal("3"),  # Job ist sicher
        "dti_ratio_warning": Decimal("0.40"),        # Stabiles Einkommen
    },
    "self_employed": {
        "emergency_fund_months_warning": Decimal("12"), # Hoechste Reserve
        "dti_ratio_warning": Decimal("0.30"),        # Konservativer
    },
    "employee": {
        # Standard-Werte
    },
    "retiree": {
        "savings_rate_warning": Decimal("0"),        # Keine Sparquote erwartet
        "dti_ratio_warning": Decimal("0.25"),        # Niedrigere Belastung
    },
}


# =============================================================================
# Response Data Classes
# =============================================================================

@dataclass
class TrendAnalysis:
    """Ergebnis einer Trend-Analyse."""
    method: ProjectionMethod
    direction: TrendDirection
    strength: Decimal  # 0-1, wie stark ist der Trend
    slope: Decimal  # Aenderungsrate pro Monat
    r_squared: Decimal  # Guete der Anpassung (0-1)
    seasonality_detected: bool
    seasonal_amplitude: Optional[Decimal]
    confidence: Decimal  # Gesamt-Konfidenz (0-1)


@dataclass
class ProjectedValue:
    """Ein projizierter Wert fuer einen Zeitpunkt."""
    month: int  # Monate ab jetzt
    date: date
    value: Decimal
    lower_bound: Decimal  # 90% Konfidenzintervall
    upper_bound: Decimal
    confidence: Decimal


@dataclass
class ThresholdBreach:
    """Ein vorhergesagter Schwellenwert-Durchbruch."""
    month: int
    date: date
    kpi_name: str
    current_value: Decimal
    projected_value: Decimal
    threshold_value: Decimal
    threshold_type: str  # "warning" oder "critical"
    severity: WarningSeverity
    confidence: Decimal


@dataclass
class KPIProjection:
    """Vollstaendige Projektion fuer einen KPI."""
    kpi_name: str
    current_value: Decimal
    unit: KPIUnit
    trend: TrendAnalysis
    projections: List[ProjectedValue]  # 3, 6, 12 Monate
    threshold_breaches: List[ThresholdBreach]
    data_points_used: int
    calculated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class EarlyWarningAlert:
    """Ein proaktiver Warnhinweis."""
    kpi_name: str
    warning_type: WarningType
    severity: WarningSeverity

    current_value: Decimal
    projected_value: Decimal
    threshold_value: Decimal
    breach_date: date
    days_until_breach: int

    title: str
    description: str
    recommendation: str
    potential_impact: Optional[str]
    action_url: Optional[str]

    confidence: Decimal
    factors: List[str]  # Faktoren die zur Warnung beitragen


@dataclass
class PredictiveInsightsSummary:
    """Zusammenfassung aller proaktiven Insights fuer einen Space."""
    space_id: UUID

    # Projektionen
    projections: List[KPIProjection]

    # Early Warnings
    early_warnings: List[EarlyWarningAlert]
    critical_warnings: int
    high_warnings: int
    medium_warnings: int
    low_warnings: int

    # Trends
    improving_kpis: List[str]
    declining_kpis: List[str]
    stable_kpis: List[str]

    # Gesamt-Ausblick
    outlook_score: Decimal  # 0-100, wie sieht die Zukunft aus
    outlook_summary: str

    calculated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    valid_until: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc) + timedelta(hours=24)
    )


# =============================================================================
# Predictive Intelligence Service
# =============================================================================

class PredictiveIntelligenceService:
    """
    Singleton Service fuer Predictive Intelligence.

    Kernfunktionen:
    - KPI-Projektion in die Zukunft (3/6/12 Monate)
    - Early Warning Detection
    - Trend-Analyse (Linear, Exponentiell, Saisonal)
    - Personalisierte Schwellenwerte

    Das System antizipiert Probleme BEVOR sie auftreten.
    """

    _instance: Optional["PredictiveIntelligenceService"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "PredictiveIntelligenceService":
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
        logger.info("predictive_intelligence_service_initialized")

    # =========================================================================
    # Trend-Analyse
    # =========================================================================

    def _calculate_linear_trend(
        self,
        values: Sequence[Decimal],
        dates: Sequence[date],
    ) -> Tuple[Decimal, Decimal, Decimal]:
        """
        Berechnet linearen Trend mit Least Squares.

        Returns:
            Tuple[slope, intercept, r_squared]
        """
        if len(values) < 2:
            return Decimal("0"), values[0] if values else Decimal("0"), Decimal("0")

        # Konvertiere zu numpy fuer Berechnung
        n = len(values)
        x = np.array([i for i in range(n)], dtype=float)
        y = np.array([float(v) for v in values], dtype=float)

        # Lineare Regression
        x_mean = np.mean(x)
        y_mean = np.mean(y)

        numerator = np.sum((x - x_mean) * (y - y_mean))
        denominator = np.sum((x - x_mean) ** 2)

        if denominator == 0:
            return Decimal("0"), Decimal(str(y_mean)), Decimal("0")

        slope = numerator / denominator
        intercept = y_mean - slope * x_mean

        # R-squared berechnen
        y_pred = slope * x + intercept
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - y_mean) ** 2)

        r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0
        r_squared = max(0, min(1, r_squared))  # Clamp to [0, 1]

        return (
            Decimal(str(round(slope, 6))),
            Decimal(str(round(intercept, 6))),
            Decimal(str(round(r_squared, 4))),
        )

    def _detect_seasonality(
        self,
        values: Sequence[Decimal],
        period: int = 12,  # Monatlich
    ) -> Tuple[bool, Optional[Decimal]]:
        """
        Erkennt saisonale Muster in den Daten.

        Returns:
            Tuple[is_seasonal, amplitude]
        """
        if len(values) < period * 2:
            return False, None

        y = np.array([float(v) for v in values], dtype=float)
        n = len(y)

        # FFT fuer Frequenz-Analyse
        fft_result = np.fft.fft(y)
        frequencies = np.fft.fftfreq(n)

        # Finde dominante Frequenz (ausser DC-Komponente)
        power = np.abs(fft_result)[1:n//2]
        if len(power) == 0:
            return False, None

        dominant_idx = np.argmax(power) + 1
        dominant_freq = abs(frequencies[dominant_idx])

        # Pruefe ob Frequenz nahe der erwarteten Periode liegt
        expected_freq = 1 / period
        freq_tolerance = 0.1

        is_seasonal = abs(dominant_freq - expected_freq) < freq_tolerance

        if is_seasonal:
            # Berechne Amplitude
            amplitude = 2 * np.abs(fft_result[dominant_idx]) / n
            return True, Decimal(str(round(amplitude, 2)))

        return False, None

    def _analyze_trend(
        self,
        values: Sequence[Decimal],
        dates: Sequence[date],
    ) -> TrendAnalysis:
        """Analysiert den Trend einer KPI-Zeitreihe."""
        if len(values) < 3:
            return TrendAnalysis(
                method=ProjectionMethod.LINEAR,
                direction=TrendDirection.STABLE,
                strength=Decimal("0"),
                slope=Decimal("0"),
                r_squared=Decimal("0"),
                seasonality_detected=False,
                seasonal_amplitude=None,
                confidence=Decimal("0.5"),
            )

        # Linearer Trend
        slope, intercept, r_squared = self._calculate_linear_trend(values, dates)

        # Saisonalitaet erkennen
        is_seasonal, amplitude = self._detect_seasonality(values)

        # Trend-Richtung bestimmen
        if abs(float(slope)) < 0.01:
            direction = TrendDirection.STABLE
        elif float(slope) > 0:
            direction = TrendDirection.INCREASING
        else:
            direction = TrendDirection.DECREASING

        # Trend-Staerke (normalisiert)
        if len(values) > 0:
            mean_value = sum(values) / len(values)
            if mean_value != 0:
                strength = min(Decimal("1"), abs(slope * 12 / mean_value))  # Jaehrliche Aenderung
            else:
                strength = Decimal("0")
        else:
            strength = Decimal("0")

        # Methode waehlen
        method = ProjectionMethod.SEASONAL if is_seasonal else ProjectionMethod.LINEAR

        # Konfidenz berechnen
        data_points = len(values)
        confidence = min(Decimal("1"), Decimal(str(
            0.3 +  # Basis
            float(r_squared) * 0.4 +  # Anpassungsguete
            min(data_points / 24, 0.3)  # Datenmenge (max bei 24 Monaten)
        )))

        return TrendAnalysis(
            method=method,
            direction=direction,
            strength=strength.quantize(Decimal("0.01")),
            slope=slope,
            r_squared=r_squared,
            seasonality_detected=is_seasonal,
            seasonal_amplitude=amplitude,
            confidence=confidence.quantize(Decimal("0.01")),
        )

    # =========================================================================
    # KPI-Projektion
    # =========================================================================

    def _project_values(
        self,
        current_value: Decimal,
        trend: TrendAnalysis,
        months_ahead: List[int],
    ) -> List[ProjectedValue]:
        """Projiziert Werte in die Zukunft basierend auf Trend."""
        projections: List[ProjectedValue] = []
        today = date.today()

        for month in months_ahead:
            projected_date = today + timedelta(days=30 * month)

            # Lineare Projektion
            projected_value = current_value + (trend.slope * Decimal(str(month)))

            # Saisonale Anpassung
            if trend.seasonality_detected and trend.seasonal_amplitude:
                # Einfache sinusfoermige Saisonalitaet
                seasonal_factor = float(trend.seasonal_amplitude) * math.sin(
                    2 * math.pi * (today.month + month) / 12
                )
                projected_value += Decimal(str(round(seasonal_factor, 2)))

            # Konfidenzintervall berechnen
            # Breiter fuer weiter in der Zukunft und niedrigere R-squared
            uncertainty = float(
                (1 - float(trend.r_squared)) * 0.1 * month +
                0.05 * month  # Basis-Unsicherheit
            )
            uncertainty = min(uncertainty, 0.5)  # Max 50% Unsicherheit

            if current_value != 0:
                margin = abs(float(projected_value)) * uncertainty
            else:
                margin = abs(float(trend.slope)) * month * 2

            lower_bound = projected_value - Decimal(str(round(margin, 2)))
            upper_bound = projected_value + Decimal(str(round(margin, 2)))

            # Konfidenz nimmt ab mit der Zeit
            month_confidence = max(
                Decimal("0.3"),
                trend.confidence - Decimal(str(month * 0.03))
            )

            projections.append(ProjectedValue(
                month=month,
                date=projected_date,
                value=projected_value.quantize(Decimal("0.01")),
                lower_bound=lower_bound.quantize(Decimal("0.01")),
                upper_bound=upper_bound.quantize(Decimal("0.01")),
                confidence=month_confidence.quantize(Decimal("0.01")),
            ))

        return projections

    async def _get_threshold_for_kpi(
        self,
        db: AsyncSession,
        user_id: Optional[UUID],
        kpi_name: str,
        threshold_type: str,  # "warning" oder "critical"
    ) -> Optional[Decimal]:
        """Holt den Schwellenwert fuer einen KPI (personalisiert oder Standard)."""
        threshold_key = f"{kpi_name}_{threshold_type}"

        # Versuche personalisierte Schwellenwerte
        if user_id:
            result = await db.execute(
                select(PrivatUserThreshold.current_value)
                .where(
                    PrivatUserThreshold.user_id == user_id,
                    PrivatUserThreshold.threshold_type == threshold_key,
                )
            )
            custom = result.scalar_one_or_none()
            if custom is not None:
                return custom

        # Standard-Schwellenwerte
        if kpi_name in DEFAULT_THRESHOLDS:
            return DEFAULT_THRESHOLDS[kpi_name].get(threshold_type)

        return None

    def _check_threshold_breach(
        self,
        kpi_name: str,
        current_value: Decimal,
        projection: ProjectedValue,
        thresholds: Dict[str, Decimal],
    ) -> Optional[ThresholdBreach]:
        """Prueft ob eine Projektion einen Schwellenwert durchbricht."""
        if kpi_name not in DEFAULT_THRESHOLDS:
            return None

        kpi_config = DEFAULT_THRESHOLDS[kpi_name]
        direction = float(kpi_config.get("direction", 1))

        warning_threshold = thresholds.get("warning")
        critical_threshold = thresholds.get("critical")

        breach: Optional[ThresholdBreach] = None

        # Pruefe kritischen Schwellenwert
        if critical_threshold is not None:
            is_breach = (
                (direction > 0 and projection.value < critical_threshold) or
                (direction < 0 and projection.value > critical_threshold)
            )
            if is_breach:
                breach = ThresholdBreach(
                    month=projection.month,
                    date=projection.date,
                    kpi_name=kpi_name,
                    current_value=current_value,
                    projected_value=projection.value,
                    threshold_value=critical_threshold,
                    threshold_type="critical",
                    severity=WarningSeverity.CRITICAL if projection.month <= 3 else WarningSeverity.HIGH,
                    confidence=projection.confidence,
                )

        # Pruefe Warn-Schwellenwert (nur wenn nicht bereits kritisch)
        if breach is None and warning_threshold is not None:
            is_breach = (
                (direction > 0 and projection.value < warning_threshold) or
                (direction < 0 and projection.value > warning_threshold)
            )
            if is_breach:
                severity = WarningSeverity.MEDIUM if projection.month <= 6 else WarningSeverity.LOW
                breach = ThresholdBreach(
                    month=projection.month,
                    date=projection.date,
                    kpi_name=kpi_name,
                    current_value=current_value,
                    projected_value=projection.value,
                    threshold_value=warning_threshold,
                    threshold_type="warning",
                    severity=severity,
                    confidence=projection.confidence,
                )

        return breach

    async def project_kpi(
        self,
        db: AsyncSession,
        space_id: UUID,
        kpi_name: str,
        months_ahead: int = 12,
        user_id: Optional[UUID] = None,
    ) -> KPIProjection:
        """
        Projiziert einen KPI in die Zukunft.

        Args:
            db: Database Session
            space_id: Privat-Space ID
            kpi_name: Name des KPI (z.B. "dti_ratio", "net_worth")
            months_ahead: Maximale Projektion in Monaten
            user_id: Optional fuer personalisierte Schwellenwerte

        Returns:
            KPIProjection mit Trend, Projektionen und Warnungen
        """
        import time
        start_time = time.time()

        PREDICTION_CALCULATIONS.labels(calculation_type="project_kpi").inc()

        # Historische Daten laden
        result = await db.execute(
            select(PrivatKPIHistory)
            .where(
                PrivatKPIHistory.space_id == space_id,
                PrivatKPIHistory.kpi_name == kpi_name,
            )
            .order_by(asc(PrivatKPIHistory.recorded_at))
            .limit(24)  # Max 2 Jahre
        )
        history = result.scalars().all()

        if not history:
            # Keine historischen Daten - versuche aktuellen Wert zu berechnen
            logger.warning(
                "no_historical_data_for_kpi",
                space_id=str(space_id),
                kpi_name=kpi_name,
            )
            return KPIProjection(
                kpi_name=kpi_name,
                current_value=Decimal("0"),
                unit=KPIUnit.NUMBER,
                trend=TrendAnalysis(
                    method=ProjectionMethod.LINEAR,
                    direction=TrendDirection.STABLE,
                    strength=Decimal("0"),
                    slope=Decimal("0"),
                    r_squared=Decimal("0"),
                    seasonality_detected=False,
                    seasonal_amplitude=None,
                    confidence=Decimal("0"),
                ),
                projections=[],
                threshold_breaches=[],
                data_points_used=0,
            )

        # Daten extrahieren
        values = [h.kpi_value for h in history]
        dates = [h.recorded_at.date() for h in history]
        current_value = values[-1]
        unit = history[-1].kpi_unit or KPIUnit.NUMBER

        # Trend analysieren
        trend = self._analyze_trend(values, dates)

        # Projektionen berechnen
        projection_months = [3, 6, 12]
        projection_months = [m for m in projection_months if m <= months_ahead]
        projections = self._project_values(current_value, trend, projection_months)

        # Schwellenwerte holen
        warning_threshold = await self._get_threshold_for_kpi(
            db, user_id, kpi_name, "warning"
        )
        critical_threshold = await self._get_threshold_for_kpi(
            db, user_id, kpi_name, "critical"
        )
        thresholds = {
            "warning": warning_threshold,
            "critical": critical_threshold,
        }

        # Schwellenwert-Durchbrueche pruefen
        breaches: List[ThresholdBreach] = []
        for proj in projections:
            breach = self._check_threshold_breach(
                kpi_name, current_value, proj, thresholds
            )
            if breach:
                breaches.append(breach)

        duration = time.time() - start_time
        PREDICTION_DURATION.observe(duration)

        logger.info(
            "kpi_projected",
            space_id=str(space_id),
            kpi_name=kpi_name,
            current_value=str(current_value),
            trend_direction=trend.direction.value,
            breaches_count=len(breaches),
            data_points=len(history),
            duration_seconds=round(duration, 3),
        )

        return KPIProjection(
            kpi_name=kpi_name,
            current_value=current_value,
            unit=unit,
            trend=trend,
            projections=projections,
            threshold_breaches=breaches,
            data_points_used=len(history),
        )

    # =========================================================================
    # Early Warning Generation
    # =========================================================================

    def _generate_warning_text(
        self,
        kpi_name: str,
        breach: ThresholdBreach,
    ) -> Tuple[str, str, str, Optional[str], Optional[str]]:
        """
        Generiert deutsche Warntexte.

        Returns:
            Tuple[title, description, recommendation, potential_impact, action_url]
        """
        # KPI-spezifische Texte
        kpi_texts: Dict[str, Dict[str, str]] = {
            "dti_ratio": {
                "title": "Schuldenquote wird kritisch",
                "desc": "Ihre Schulden-zu-Einkommen-Quote wird in {days} Tagen voraussichtlich {threshold}% erreichen.",
                "rec": "Reduzieren Sie Schulden oder erhoehen Sie Ihr Einkommen um die Quote zu verbessern.",
                "impact": "Kredite werden teurer und schwerer zu erhalten.",
                "url": "/privat/loans",
            },
            "emergency_fund_months": {
                "title": "Notgroschen schrumpft",
                "desc": "Ihre Notfall-Reserve wird in {days} Tagen voraussichtlich auf {value} Monate sinken.",
                "rec": "Reduzieren Sie diskretionaere Ausgaben und bauen Sie die Reserve wieder auf.",
                "impact": "Bei unerwarteten Ausgaben koennten Sie in finanzielle Schwierigkeiten geraten.",
                "url": "/privat/investments",
            },
            "financial_health_score": {
                "title": "Financial Health verschlechtert sich",
                "desc": "Ihr Financial Health Score wird in {days} Tagen voraussichtlich auf {value} fallen.",
                "rec": "Analysieren Sie die Einzel-Dimensionen des Scores fuer gezielte Verbesserungen.",
                "impact": "Ihre finanzielle Stabilitaet ist gefaehrdet.",
                "url": "/privat/dashboard",
            },
            "net_worth": {
                "title": "Netto-Vermoegen ruecklaeufig",
                "desc": "Ihr Netto-Vermoegen wird in {days} Tagen voraussichtlich {value} EUR erreichen.",
                "rec": "Pruefen Sie Ihre Ausgaben und Investitions-Strategie.",
                "impact": "Ihre Vermoegensbildung stagniert oder ist negativ.",
                "url": "/privat/analytics",
            },
            "savings_rate": {
                "title": "Sparquote sinkt",
                "desc": "Ihre Sparquote wird in {days} Tagen voraussichtlich auf {value}% sinken.",
                "rec": "Identifizieren Sie Einsparpotenziale oder erhoehen Sie Ihr Einkommen.",
                "impact": "Langfristige Ziele wie Altersvorsorge sind gefaehrdet.",
                "url": "/privat/analytics",
            },
        }

        texts = kpi_texts.get(kpi_name, {
            "title": f"Warnung: {kpi_name}",
            "desc": f"Der KPI {kpi_name} erreicht in {{days}} Tagen einen kritischen Wert von {{value}}.",
            "rec": f"Pruefen Sie die Entwicklung von {kpi_name}.",
            "impact": None,
            "url": None,
        })

        days = breach.month * 30

        title = texts["title"]
        if breach.severity == WarningSeverity.CRITICAL:
            title = "KRITISCH: " + title
        elif breach.severity == WarningSeverity.HIGH:
            title = "ACHTUNG: " + title

        description = texts["desc"].format(
            days=days,
            value=str(breach.projected_value.quantize(Decimal("0.01"))),
            threshold=str((breach.threshold_value * 100).quantize(Decimal("0.1"))),
        )

        return (
            title,
            description,
            texts["rec"],
            texts.get("impact"),
            texts.get("url"),
        )

    async def generate_early_warnings(
        self,
        db: AsyncSession,
        space_id: UUID,
        user_id: Optional[UUID] = None,
    ) -> List[EarlyWarningAlert]:
        """
        Generiert Early Warning Alerts fuer alle relevanten KPIs.

        Returns:
            Liste von proaktiven Warnhinweisen
        """
        import time
        start_time = time.time()

        PREDICTION_CALCULATIONS.labels(calculation_type="generate_warnings").inc()

        warnings: List[EarlyWarningAlert] = []

        # Alle KPIs mit Schwellenwerten projizieren
        for kpi_name in DEFAULT_THRESHOLDS.keys():
            try:
                projection = await self.project_kpi(
                    db, space_id, kpi_name, months_ahead=12, user_id=user_id
                )

                for breach in projection.threshold_breaches:
                    title, desc, rec, impact, url = self._generate_warning_text(
                        kpi_name, breach
                    )

                    warning_type = (
                        WarningType.THRESHOLD_BREACH if breach.threshold_type == "critical"
                        else WarningType.TREND_ALERT
                    )

                    factors = [
                        f"Trend: {projection.trend.direction.value}",
                        f"Aenderungsrate: {projection.trend.slope}/Monat",
                    ]
                    if projection.trend.seasonality_detected:
                        factors.append("Saisonale Schwankungen erkannt")

                    warning = EarlyWarningAlert(
                        kpi_name=kpi_name,
                        warning_type=warning_type,
                        severity=breach.severity,
                        current_value=breach.current_value,
                        projected_value=breach.projected_value,
                        threshold_value=breach.threshold_value,
                        breach_date=breach.date,
                        days_until_breach=breach.month * 30,
                        title=title,
                        description=desc,
                        recommendation=rec,
                        potential_impact=impact,
                        action_url=url,
                        confidence=breach.confidence,
                        factors=factors,
                    )
                    warnings.append(warning)

                    EARLY_WARNINGS_GENERATED.labels(
                        severity=breach.severity.value,
                        kpi_name=kpi_name,
                    ).inc()

            except Exception as e:
                logger.error(
                    "warning_generation_failed",
                    space_id=str(space_id),
                    kpi_name=kpi_name,
                    error=str(e),
                )

        # Nach Severity und Datum sortieren
        severity_order = {
            WarningSeverity.CRITICAL: 0,
            WarningSeverity.HIGH: 1,
            WarningSeverity.MEDIUM: 2,
            WarningSeverity.LOW: 3,
        }
        warnings.sort(key=lambda w: (severity_order[w.severity], w.days_until_breach))

        # Metrik aktualisieren
        ACTIVE_WARNINGS_GAUGE.labels(space_id=str(space_id)).set(len(warnings))

        duration = time.time() - start_time
        PREDICTION_DURATION.observe(duration)

        logger.info(
            "early_warnings_generated",
            space_id=str(space_id),
            total_warnings=len(warnings),
            critical=sum(1 for w in warnings if w.severity == WarningSeverity.CRITICAL),
            high=sum(1 for w in warnings if w.severity == WarningSeverity.HIGH),
            duration_seconds=round(duration, 3),
        )

        return warnings

    # =========================================================================
    # Insights Summary
    # =========================================================================

    async def get_predictive_insights(
        self,
        db: AsyncSession,
        space_id: UUID,
        user_id: Optional[UUID] = None,
    ) -> PredictiveInsightsSummary:
        """
        Generiert eine vollstaendige Zusammenfassung aller proaktiven Insights.
        """
        import time
        start_time = time.time()

        PREDICTION_CALCULATIONS.labels(calculation_type="full_insights").inc()

        # Alle KPIs projizieren
        projections: List[KPIProjection] = []
        for kpi_name in DEFAULT_THRESHOLDS.keys():
            try:
                proj = await self.project_kpi(
                    db, space_id, kpi_name, months_ahead=12, user_id=user_id
                )
                if proj.data_points_used > 0:
                    projections.append(proj)
            except Exception as e:
                logger.warning(
                    "projection_failed",
                    kpi_name=kpi_name,
                    error=str(e),
                )

        # Early Warnings generieren
        warnings = await self.generate_early_warnings(db, space_id, user_id)

        # Trends kategorisieren
        improving_kpis: List[str] = []
        declining_kpis: List[str] = []
        stable_kpis: List[str] = []

        for proj in projections:
            # Pruefe ob hoeher oder niedriger besser ist
            direction_is_good = DEFAULT_THRESHOLDS.get(proj.kpi_name, {}).get("direction", 1)

            if proj.trend.direction == TrendDirection.STABLE:
                stable_kpis.append(proj.kpi_name)
            elif proj.trend.direction == TrendDirection.INCREASING:
                if float(direction_is_good) > 0:
                    improving_kpis.append(proj.kpi_name)
                else:
                    declining_kpis.append(proj.kpi_name)
            else:  # DECREASING
                if float(direction_is_good) > 0:
                    declining_kpis.append(proj.kpi_name)
                else:
                    improving_kpis.append(proj.kpi_name)

        # Severity-Counts
        critical = sum(1 for w in warnings if w.severity == WarningSeverity.CRITICAL)
        high = sum(1 for w in warnings if w.severity == WarningSeverity.HIGH)
        medium = sum(1 for w in warnings if w.severity == WarningSeverity.MEDIUM)
        low = sum(1 for w in warnings if w.severity == WarningSeverity.LOW)

        # Outlook Score berechnen (0-100)
        # Startet bei 100 und wird reduziert durch Warnungen und negative Trends
        outlook_score = Decimal("100")
        outlook_score -= Decimal(str(critical * 20))  # -20 pro kritisch
        outlook_score -= Decimal(str(high * 10))       # -10 pro hoch
        outlook_score -= Decimal(str(medium * 5))      # -5 pro mittel
        outlook_score -= Decimal(str(low * 2))         # -2 pro niedrig
        outlook_score -= Decimal(str(len(declining_kpis) * 5))  # -5 pro negativem Trend
        outlook_score = max(Decimal("0"), outlook_score)

        # Outlook Summary
        if outlook_score >= 80:
            outlook_summary = "Ihre finanzielle Zukunft sieht sehr positiv aus! Keine kritischen Entwicklungen erkennbar."
        elif outlook_score >= 60:
            outlook_summary = "Insgesamt stabil, aber einige Bereiche verdienen Aufmerksamkeit."
        elif outlook_score >= 40:
            outlook_summary = "Mehrere Indikatoren zeigen Handlungsbedarf. Pruefen Sie die Warnungen."
        elif outlook_score >= 20:
            outlook_summary = "Achtung: Mehrere kritische Entwicklungen erkannt. Zeitnahes Handeln empfohlen."
        else:
            outlook_summary = "KRITISCH: Ihre finanzielle Situation erfordert sofortige Massnahmen!"

        duration = time.time() - start_time
        PREDICTION_DURATION.observe(duration)

        logger.info(
            "predictive_insights_generated",
            space_id=str(space_id),
            outlook_score=str(outlook_score),
            projections_count=len(projections),
            warnings_count=len(warnings),
            duration_seconds=round(duration, 3),
        )

        return PredictiveInsightsSummary(
            space_id=space_id,
            projections=projections,
            early_warnings=warnings,
            critical_warnings=critical,
            high_warnings=high,
            medium_warnings=medium,
            low_warnings=low,
            improving_kpis=improving_kpis,
            declining_kpis=declining_kpis,
            stable_kpis=stable_kpis,
            outlook_score=outlook_score.quantize(Decimal("0.1")),
            outlook_summary=outlook_summary,
        )

    # =========================================================================
    # KPI History Recording
    # =========================================================================

    async def record_kpi_snapshot(
        self,
        db: AsyncSession,
        space_id: UUID,
        kpi_name: str,
        value: Decimal,
        unit: KPIUnit = KPIUnit.NUMBER,
        components: Optional[Dict[str, Any]] = None,
        source: str = "calculated",
    ) -> PrivatKPIHistory:
        """
        Speichert einen KPI-Schnappschuss fuer die History.
        Wird taeglich von Celery Beat aufgerufen.
        """
        # Pruefe ob heute schon ein Eintrag existiert
        today = date.today()
        result = await db.execute(
            select(PrivatKPIHistory)
            .where(
                PrivatKPIHistory.space_id == space_id,
                PrivatKPIHistory.kpi_name == kpi_name,
                func.date(PrivatKPIHistory.recorded_at) == today,
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            # Update existing record
            existing.kpi_value = value
            existing.kpi_unit = unit
            existing.components = components
            existing.source = source
            await db.commit()
            await db.refresh(existing)
            return existing

        # Create new record
        history = PrivatKPIHistory(
            space_id=space_id,
            kpi_name=kpi_name,
            kpi_value=value,
            kpi_unit=unit,
            components=components,
            source=source,
        )
        db.add(history)
        await db.commit()
        await db.refresh(history)

        logger.debug(
            "kpi_snapshot_recorded",
            space_id=str(space_id),
            kpi_name=kpi_name,
            value=str(value),
        )

        return history

    async def record_all_kpis_for_space(
        self,
        db: AsyncSession,
        space_id: UUID,
    ) -> Dict[str, Any]:
        """
        Erfasst alle KPIs fuer einen Space (fuer Celery Beat).

        Holt aktuelle Werte von verschiedenen Services und speichert sie.
        """
        from app.services.privat.financial_health_service import get_financial_health_service

        health_service = get_financial_health_service()
        recorded = 0
        errors = 0

        try:
            # Financial Health Score berechnen
            health_score = await health_service.calculate_health_score(db, space_id)

            # KPIs extrahieren und speichern
            kpis_to_record = [
                ("financial_health_score", health_score.total_score, KPIUnit.PERCENTAGE),
                ("net_worth", health_score.net_worth.net_worth, KPIUnit.CURRENCY),
            ]

            # DTI Ratio aus Dimensionen
            for dim in health_score.dimensions:
                if dim.name == "debt_management" and "dti_ratio" in dim.details:
                    dti_str = dim.details.get("dti_ratio", "0%").replace("%", "")
                    try:
                        dti = Decimal(dti_str) / 100
                        kpis_to_record.append(("dti_ratio", dti, KPIUnit.PERCENTAGE))
                    except Exception:
                        pass

                if dim.name == "liquidity" and "months_covered" in dim.details:
                    try:
                        months = Decimal(str(dim.details["months_covered"]))
                        kpis_to_record.append(("emergency_fund_months", months, KPIUnit.NUMBER))
                    except Exception:
                        pass

            # Sparquote
            if health_score.monthly_savings_rate is not None:
                kpis_to_record.append((
                    "savings_rate",
                    health_score.monthly_savings_rate,
                    KPIUnit.PERCENTAGE
                ))

            # KPIs speichern
            for kpi_name, value, unit in kpis_to_record:
                try:
                    await self.record_kpi_snapshot(
                        db, space_id, kpi_name, value, unit, source="health_score"
                    )
                    recorded += 1
                except Exception as e:
                    errors += 1
                    logger.error(
                        "kpi_recording_failed",
                        space_id=str(space_id),
                        kpi_name=kpi_name,
                        error=str(e),
                    )

        except Exception as e:
            errors += 1
            logger.error(
                "space_kpi_recording_failed",
                space_id=str(space_id),
                error=str(e),
            )

        return {"recorded": recorded, "errors": errors}

    # =========================================================================
    # Projection Cache Management
    # =========================================================================

    async def cache_projection(
        self,
        db: AsyncSession,
        space_id: UUID,
        projection: KPIProjection,
    ) -> PrivatProjection:
        """Speichert eine Projektion im Cache."""
        # Existierender Cache?
        result = await db.execute(
            select(PrivatProjection)
            .where(
                PrivatProjection.space_id == space_id,
                PrivatProjection.kpi_name == projection.kpi_name,
                PrivatProjection.projection_months == max(
                    p.month for p in projection.projections
                ) if projection.projections else 12,
            )
        )
        existing = result.scalar_one_or_none()

        # Projizierte Werte als JSON
        projected_values = [
            {
                "month": p.month,
                "date": p.date.isoformat(),
                "value": str(p.value),
                "lower_bound": str(p.lower_bound),
                "upper_bound": str(p.upper_bound),
                "confidence": str(p.confidence),
            }
            for p in projection.projections
        ]

        # Threshold Breaches als JSON
        threshold_breaches = [
            {
                "month": b.month,
                "date": b.date.isoformat(),
                "threshold_type": b.threshold_type,
                "threshold_value": str(b.threshold_value),
                "projected_value": str(b.projected_value),
                "severity": b.severity.value,
            }
            for b in projection.threshold_breaches
        ]

        if existing:
            existing.current_value = projection.current_value
            existing.projection_method = projection.trend.method
            existing.projected_values = projected_values
            existing.threshold_breaches = threshold_breaches
            existing.trend_direction = projection.trend.direction
            existing.trend_strength = projection.trend.strength
            existing.seasonality_detected = projection.trend.seasonality_detected
            existing.confidence_overall = projection.trend.confidence
            existing.data_points_used = projection.data_points_used
            existing.calculated_at = datetime.now(timezone.utc)
            existing.valid_until = datetime.now(timezone.utc) + timedelta(hours=24)
            await db.commit()
            await db.refresh(existing)
            return existing

        # Neu erstellen
        cached = PrivatProjection(
            space_id=space_id,
            kpi_name=projection.kpi_name,
            projection_months=max(p.month for p in projection.projections) if projection.projections else 12,
            projection_method=projection.trend.method,
            current_value=projection.current_value,
            projected_values=projected_values,
            threshold_breaches=threshold_breaches,
            trend_direction=projection.trend.direction,
            trend_strength=projection.trend.strength,
            seasonality_detected=projection.trend.seasonality_detected,
            confidence_overall=projection.trend.confidence,
            data_points_used=projection.data_points_used,
            valid_until=datetime.now(timezone.utc) + timedelta(hours=24),
        )
        db.add(cached)
        await db.commit()
        await db.refresh(cached)

        return cached

    # =========================================================================
    # Early Warning Persistence
    # =========================================================================

    async def persist_early_warnings(
        self,
        db: AsyncSession,
        space_id: UUID,
        warnings: List[EarlyWarningAlert],
    ) -> int:
        """
        Speichert Early Warnings in der Datenbank.
        Aktualisiert existierende oder erstellt neue.
        """
        persisted = 0

        for warning in warnings:
            # Suche existierende Warnung fuer diesen KPI
            result = await db.execute(
                select(PrivatEarlyWarning)
                .where(
                    PrivatEarlyWarning.space_id == space_id,
                    PrivatEarlyWarning.kpi_name == warning.kpi_name,
                    PrivatEarlyWarning.is_resolved == False,
                    PrivatEarlyWarning.is_dismissed == False,
                )
            )
            existing = result.scalar_one_or_none()

            if existing:
                # Update
                existing.severity = warning.severity
                existing.current_value = warning.current_value
                existing.projected_value = warning.projected_value
                existing.threshold_value = warning.threshold_value
                existing.breach_date = warning.breach_date
                existing.days_until_breach = warning.days_until_breach
                existing.title = warning.title
                existing.description = warning.description
                existing.recommendation = warning.recommendation
                existing.confidence = warning.confidence
            else:
                # Neu erstellen
                db_warning = PrivatEarlyWarning(
                    space_id=space_id,
                    kpi_name=warning.kpi_name,
                    warning_type=warning.warning_type,
                    severity=warning.severity,
                    current_value=warning.current_value,
                    projected_value=warning.projected_value,
                    threshold_value=warning.threshold_value,
                    breach_date=warning.breach_date,
                    days_until_breach=warning.days_until_breach,
                    title=warning.title,
                    description=warning.description,
                    recommendation=warning.recommendation,
                    potential_impact=warning.potential_impact,
                    action_url=warning.action_url,
                    confidence=warning.confidence,
                )
                db.add(db_warning)

            persisted += 1

        await db.commit()

        logger.info(
            "early_warnings_persisted",
            space_id=str(space_id),
            count=persisted,
        )

        return persisted

    async def dismiss_warning(
        self,
        db: AsyncSession,
        warning_id: UUID,
    ) -> bool:
        """Markiert eine Warnung als abgelehnt (nicht mehr anzeigen)."""
        result = await db.execute(
            select(PrivatEarlyWarning)
            .where(PrivatEarlyWarning.id == warning_id)
        )
        warning = result.scalar_one_or_none()

        if warning:
            warning.is_dismissed = True
            warning.dismissed_at = datetime.now(timezone.utc)
            await db.commit()
            return True
        return False

    async def resolve_warning(
        self,
        db: AsyncSession,
        warning_id: UUID,
    ) -> bool:
        """Markiert eine Warnung als geloest."""
        result = await db.execute(
            select(PrivatEarlyWarning)
            .where(PrivatEarlyWarning.id == warning_id)
        )
        warning = result.scalar_one_or_none()

        if warning:
            warning.is_resolved = True
            warning.resolved_at = datetime.now(timezone.utc)
            await db.commit()
            return True
        return False


# =============================================================================
# Singleton-Instanz
# =============================================================================

def get_predictive_intelligence_service() -> PredictiveIntelligenceService:
    """Gibt die Singleton-Instanz des Predictive Intelligence Service zurueck."""
    return PredictiveIntelligenceService()

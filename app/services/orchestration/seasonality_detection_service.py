# -*- coding: utf-8 -*-
"""
Seasonality Detection Service.

Enterprise Feature: Erkennung saisonaler Muster in finanziellen Daten.

Das System erkennt und beruecksichtigt:
- Monatliche Muster (Heizkosten im Winter, Urlaub im Sommer)
- Jaehrliche Zyklen (Weihnachten, Versicherungspraemien, Steuern)
- Wochentags-Muster (Wochenend-Ausgaben, Arbeitstage)
- Individuelle Muster (Geburtstage, Jubilaeen)

Vorteile:
- Heizkosten im Dezember sind keine Anomalie
- Urlaubsausgaben im August werden erwartet
- Weihnachtsgeschenke sind eingeplant
- Steuerrueckzahlung im Maerz ist bekannt

TRUE Enterprise: Das System versteht KONTEXT, nicht nur Zahlen.
"""

from __future__ import annotations

import logging
import math
import statistics
import threading
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from uuid import UUID, uuid4

import structlog

logger = structlog.get_logger(__name__)


# =============================================================================
# Safe Statistics Helpers
# =============================================================================

def safe_stdev(data: List[float], default: float = 0.0) -> float:
    """Sichere Standardabweichung - gibt default zurueck bei weniger als 2 Datenpunkten.

    statistics.stdev() wirft StatisticsError bei weniger als 2 Werten.
    Diese Funktion vermeidet das Problem.

    Args:
        data: Liste von Float-Werten
        default: Rueckgabewert wenn nicht genug Daten (default: 0.0)

    Returns:
        Standardabweichung oder default
    """
    if len(data) < 2:
        return default
    return statistics.stdev(data)


# =============================================================================
# Enums
# =============================================================================

class SeasonType(str, Enum):
    """Arten von saisonalen Mustern."""
    MONTHLY = "monthly"  # Monatliche Wiederholung
    QUARTERLY = "quarterly"  # Quartalsweise
    SEMI_ANNUAL = "semi_annual"  # Halbjaehrlich
    ANNUAL = "annual"  # Jaehrlich
    WEEKLY = "weekly"  # Woechentlich
    CUSTOM = "custom"  # Benutzerdefiniert


class PatternStrength(str, Enum):
    """Staerke eines erkannten Musters."""
    VERY_STRONG = "very_strong"  # Konfidenz > 90%
    STRONG = "strong"  # Konfidenz 75-90%
    MODERATE = "moderate"  # Konfidenz 60-75%
    WEAK = "weak"  # Konfidenz 40-60%
    NONE = "none"  # Kein Muster erkannt


class CategoryType(str, Enum):
    """Kategorien mit typischen saisonalen Mustern."""
    HEATING = "heating"  # Heizung
    ELECTRICITY = "electricity"  # Strom
    VACATION = "vacation"  # Urlaub
    CHRISTMAS = "christmas"  # Weihnachten
    INSURANCE = "insurance"  # Versicherungen
    TAX = "tax"  # Steuern
    SUBSCRIPTION = "subscription"  # Abonnements
    EDUCATION = "education"  # Bildung (Semester)
    CLOTHING = "clothing"  # Kleidung (Saison)
    GIFTS = "gifts"  # Geschenke
    FOOD = "food"  # Lebensmittel
    ENTERTAINMENT = "entertainment"  # Unterhaltung
    TRANSPORT = "transport"  # Transport
    OTHER = "other"  # Sonstiges


class AnomalyContext(str, Enum):
    """Kontext fuer Anomalie-Bewertung."""
    EXPECTED_SEASONAL = "expected_seasonal"  # Erwartet wegen Saison
    UNEXPECTED_SEASONAL = "unexpected_seasonal"  # Unerwartet fuer Saison
    EXPECTED_EVENT = "expected_event"  # Erwartet wegen Event
    TRUE_ANOMALY = "true_anomaly"  # Echte Anomalie


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class SeasonalPattern:
    """Ein erkanntes saisonales Muster."""
    id: UUID
    category: CategoryType
    season_type: SeasonType
    strength: PatternStrength
    # Wann tritt das Muster auf?
    peak_months: List[int]  # 1-12
    peak_weeks: Optional[List[int]] = None  # 1-52
    peak_days: Optional[List[int]] = None  # 1-7 (Mo-So)
    # Wie stark ist die Abweichung?
    seasonal_factor: float = 1.0  # z.B. 2.5 = 150% mehr als Durchschnitt
    typical_min_factor: float = 0.5  # Minimum im Off-Season
    typical_max_factor: float = 2.0  # Maximum im Peak
    # Statistik
    average_amount: Decimal = Decimal("0")
    std_deviation: Decimal = Decimal("0")
    confidence: float = 0.5
    # Metadaten
    description: str = ""
    detected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    data_points: int = 0  # Wie viele Datenpunkte wurden analysiert?


@dataclass
class MonthlyExpectation:
    """Erwartete Ausgaben fuer einen bestimmten Monat."""
    month: int  # 1-12
    year: int
    category: CategoryType
    # Erwartungen
    expected_amount: Decimal
    expected_range_min: Decimal
    expected_range_max: Decimal
    # Seasonal Adjustment
    seasonal_factor: float
    is_peak_season: bool
    # Events
    expected_events: List[str]
    # Confidence
    confidence: float


@dataclass
class SeasonalEvent:
    """Ein bekanntes saisonales Event."""
    id: UUID
    name: str
    description: str
    # Wann?
    typical_month: int
    typical_day: Optional[int] = None
    flexible_date: bool = True  # Verschiebbar (z.B. Ostern)
    # Auswirkung
    categories_affected: List[CategoryType] = field(default_factory=list)
    typical_impact: Decimal = Decimal("0")  # Typische Zusatzausgaben
    impact_range: Tuple[Decimal, Decimal] = field(
        default_factory=lambda: (Decimal("0"), Decimal("0"))
    )
    # Tracking
    is_recurring: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class SeasonalAnomalyAnalysis:
    """Analyse einer potenziellen Anomalie mit saisonalem Kontext."""
    id: UUID
    # Original-Transaktion
    transaction_date: date
    category: CategoryType
    amount: Decimal
    # Saisonaler Kontext
    context: AnomalyContext
    seasonal_pattern: Optional[SeasonalPattern]
    expected_amount: Decimal
    expected_range: Tuple[Decimal, Decimal]
    # Bewertung
    deviation_percentage: float
    is_true_anomaly: bool
    confidence: float
    # Erklaerung
    explanation: str
    similar_historical: List[Dict[str, Any]]


@dataclass
class SeasonalForecast:
    """Saisonale Prognose fuer zukuenftige Perioden."""
    id: UUID
    forecast_date: date
    horizon_months: int
    # Prognosen pro Kategorie und Monat
    monthly_forecasts: Dict[str, Dict[int, MonthlyExpectation]]
    # Gesamt-Prognose
    total_expected: Decimal
    total_range: Tuple[Decimal, Decimal]
    # Warnungen
    high_expense_months: List[int]
    peak_categories: Dict[int, List[CategoryType]]
    # Confidence
    overall_confidence: float
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# =============================================================================
# Known Seasonal Patterns (Germany-specific)
# =============================================================================

KNOWN_PATTERNS = {
    CategoryType.HEATING: {
        "peak_months": [1, 2, 11, 12],
        "low_months": [6, 7, 8],
        "peak_factor": 2.5,
        "low_factor": 0.2,
        "description": "Heizkosten steigen im Winter erheblich",
    },
    CategoryType.ELECTRICITY: {
        "peak_months": [1, 2, 11, 12],
        "low_months": [5, 6, 7, 8],
        "peak_factor": 1.4,
        "low_factor": 0.8,
        "description": "Stromverbrauch hoehr im Winter (Licht, Heizung)",
    },
    CategoryType.VACATION: {
        "peak_months": [7, 8, 12],
        "low_months": [1, 2, 11],
        "peak_factor": 3.0,
        "low_factor": 0.3,
        "description": "Urlaubsausgaben in Schulferien und Weihnachten",
    },
    CategoryType.CHRISTMAS: {
        "peak_months": [11, 12],
        "low_months": list(range(1, 11)),
        "peak_factor": 5.0,
        "low_factor": 0.1,
        "description": "Weihnachtsgeschenke und Feiertage",
    },
    CategoryType.INSURANCE: {
        "peak_months": [1, 7],  # Viele Versicherungen sind jaehrlich
        "low_months": [],
        "peak_factor": 12.0,  # Jahreszahlung
        "low_factor": 0.0,
        "description": "Jaehrliche Versicherungspraemien",
    },
    CategoryType.TAX: {
        "peak_months": [3, 5, 6],  # Steuererklaerung, Nachzahlungen
        "low_months": [],
        "peak_factor": 1.0,  # Nicht multipliziert
        "low_factor": 0.0,
        "description": "Steuernachzahlungen/-erstattungen",
    },
    CategoryType.EDUCATION: {
        "peak_months": [8, 9, 2],  # Schulanfang, Semester
        "low_months": [11, 12, 6, 7],
        "peak_factor": 2.0,
        "low_factor": 0.5,
        "description": "Schulmaterialien, Semesterbeitraege",
    },
    CategoryType.CLOTHING: {
        "peak_months": [3, 4, 9, 10],  # Saisonwechsel
        "low_months": [1, 6, 7, 8, 12],
        "peak_factor": 1.8,
        "low_factor": 0.6,
        "description": "Saisonale Kleidungskaeufe",
    },
    CategoryType.GIFTS: {
        "peak_months": [12],  # Weihnachten
        "low_months": [1, 2, 3, 4, 6, 7, 8, 9, 10],
        "peak_factor": 4.0,
        "low_factor": 0.4,
        "description": "Geschenke, besonders Weihnachten",
    },
    CategoryType.FOOD: {
        "peak_months": [12],  # Feiertage
        "low_months": [1, 2],
        "peak_factor": 1.4,
        "low_factor": 0.9,
        "description": "Lebensmittel, hoehr zu Feiertagen",
    },
}

KNOWN_EVENTS = [
    SeasonalEvent(
        id=uuid4(),
        name="Weihnachten",
        description="Weihnachtsfeiertage mit Geschenken und Feiern",
        typical_month=12,
        typical_day=25,
        flexible_date=False,
        categories_affected=[
            CategoryType.CHRISTMAS, CategoryType.GIFTS,
            CategoryType.FOOD, CategoryType.ENTERTAINMENT,
        ],
        typical_impact=Decimal("500"),
        impact_range=(Decimal("200"), Decimal("2000")),
    ),
    SeasonalEvent(
        id=uuid4(),
        name="Ostern",
        description="Osterfeiertage",
        typical_month=4,  # Variiert
        flexible_date=True,
        categories_affected=[CategoryType.GIFTS, CategoryType.FOOD],
        typical_impact=Decimal("100"),
        impact_range=(Decimal("50"), Decimal("300")),
    ),
    SeasonalEvent(
        id=uuid4(),
        name="Sommerurlaub",
        description="Haupturlaubssaison",
        typical_month=7,
        flexible_date=True,
        categories_affected=[CategoryType.VACATION, CategoryType.ENTERTAINMENT],
        typical_impact=Decimal("1500"),
        impact_range=(Decimal("500"), Decimal("5000")),
    ),
    SeasonalEvent(
        id=uuid4(),
        name="Schulanfang",
        description="Schulbeginn mit Materialbedarf",
        typical_month=8,
        typical_day=15,
        flexible_date=True,
        categories_affected=[CategoryType.EDUCATION, CategoryType.CLOTHING],
        typical_impact=Decimal("300"),
        impact_range=(Decimal("100"), Decimal("800")),
    ),
    SeasonalEvent(
        id=uuid4(),
        name="Nebenkostenabrechnung",
        description="Jaehrliche Nebenkostenabrechnung",
        typical_month=5,
        flexible_date=True,
        categories_affected=[CategoryType.HEATING, CategoryType.ELECTRICITY],
        typical_impact=Decimal("500"),
        impact_range=(Decimal("-500"), Decimal("1500")),  # Kann Rueckzahlung sein
    ),
    SeasonalEvent(
        id=uuid4(),
        name="Steuererklaerung",
        description="Abgabe Steuererklaerung, Nachzahlung/Erstattung",
        typical_month=6,
        flexible_date=True,
        categories_affected=[CategoryType.TAX],
        typical_impact=Decimal("0"),  # Kann positiv oder negativ sein
        impact_range=(Decimal("-2000"), Decimal("2000")),
    ),
    SeasonalEvent(
        id=uuid4(),
        name="KFZ-Versicherung",
        description="Jaehrliche KFZ-Versicherungspraemie",
        typical_month=1,
        typical_day=1,
        flexible_date=False,
        categories_affected=[CategoryType.INSURANCE],
        typical_impact=Decimal("800"),
        impact_range=(Decimal("300"), Decimal("1500")),
    ),
]


# =============================================================================
# Main Service Class
# =============================================================================

class SeasonalityDetectionService:
    """
    Service fuer Saisonalitaets-Erkennung.

    Features:
    - Erkennung saisonaler Muster aus historischen Daten
    - Kontextbewusste Anomalie-Bewertung
    - Saisonale Prognosen
    - Event-basierte Erwartungen
    """

    _instance: Optional[SeasonalityDetectionService] = None
    _lock = threading.Lock()

    def __new__(cls) -> SeasonalityDetectionService:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return

        # Known patterns and events
        self._known_patterns = KNOWN_PATTERNS
        self._known_events = {e.name: e for e in KNOWN_EVENTS}

        # User-specific learned patterns
        self._user_patterns: Dict[UUID, Dict[CategoryType, SeasonalPattern]] = {}
        self._user_events: Dict[UUID, List[SeasonalEvent]] = {}

        # Cache
        self._monthly_expectations_cache: Dict[str, MonthlyExpectation] = {}

        self._initialized = True
        logger.info("SeasonalityDetectionService initialisiert")

    # -------------------------------------------------------------------------
    # Pattern Detection
    # -------------------------------------------------------------------------

    async def detect_patterns(
        self,
        user_id: UUID,
        historical_data: List[Dict[str, Any]],
        min_data_points: int = 12,
    ) -> List[SeasonalPattern]:
        """
        Erkennt saisonale Muster aus historischen Daten.

        Args:
            user_id: User-ID
            historical_data: Liste von Transaktionen mit date, category, amount
            min_data_points: Minimum Datenpunkte pro Kategorie

        Returns:
            Liste erkannter Muster
        """
        detected_patterns: List[SeasonalPattern] = []

        # Gruppiere nach Kategorie
        by_category: Dict[str, List[Dict[str, Any]]] = {}
        for tx in historical_data:
            cat = tx.get("category", "other")
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(tx)

        for cat_str, transactions in by_category.items():
            if len(transactions) < min_data_points:
                continue

            try:
                category = CategoryType(cat_str)
            except ValueError:
                category = CategoryType.OTHER

            pattern = await self._analyze_category_pattern(
                user_id, category, transactions
            )
            if pattern and pattern.strength != PatternStrength.NONE:
                detected_patterns.append(pattern)

        # Store user patterns
        if user_id not in self._user_patterns:
            self._user_patterns[user_id] = {}
        for pattern in detected_patterns:
            self._user_patterns[user_id][pattern.category] = pattern

        logger.info(
            "patterns_detected",
            user_id=str(user_id),
            pattern_count=len(detected_patterns),
        )

        return detected_patterns

    async def _analyze_category_pattern(
        self,
        user_id: UUID,
        category: CategoryType,
        transactions: List[Dict[str, Any]],
    ) -> Optional[SeasonalPattern]:
        """Analysiert saisonales Muster einer Kategorie."""
        # Gruppiere nach Monat
        by_month: Dict[int, List[Decimal]] = {m: [] for m in range(1, 13)}

        for tx in transactions:
            tx_date = tx.get("date")
            if isinstance(tx_date, str):
                tx_date = datetime.fromisoformat(tx_date).date()
            elif isinstance(tx_date, datetime):
                tx_date = tx_date.date()

            month = tx_date.month
            amount = Decimal(str(tx.get("amount", 0)))
            by_month[month].append(amount)

        # Berechne Durchschnitte pro Monat
        monthly_averages: Dict[int, float] = {}
        for month, amounts in by_month.items():
            if amounts:
                monthly_averages[month] = float(sum(amounts)) / len(amounts)
            else:
                monthly_averages[month] = 0.0

        # Gesamtdurchschnitt
        all_amounts = [a for amounts in by_month.values() for a in amounts]
        if not all_amounts:
            return None

        overall_avg = float(sum(all_amounts)) / len(all_amounts)
        if overall_avg == 0:
            return None

        # Berechne Seasonal Factors
        seasonal_factors: Dict[int, float] = {}
        for month, avg in monthly_averages.items():
            seasonal_factors[month] = avg / overall_avg if overall_avg > 0 else 1.0

        # Finde Peak-Monate (> 1.3x Durchschnitt)
        peak_months = [
            m for m, f in seasonal_factors.items()
            if f > 1.3
        ]

        # Berechne Staerke des Musters
        variance = sum((f - 1.0) ** 2 for f in seasonal_factors.values()) / 12
        coefficient_of_variation = math.sqrt(variance)

        if coefficient_of_variation > 0.5:
            strength = PatternStrength.VERY_STRONG
            confidence = 0.95
        elif coefficient_of_variation > 0.3:
            strength = PatternStrength.STRONG
            confidence = 0.85
        elif coefficient_of_variation > 0.15:
            strength = PatternStrength.MODERATE
            confidence = 0.70
        elif coefficient_of_variation > 0.05:
            strength = PatternStrength.WEAK
            confidence = 0.50
        else:
            strength = PatternStrength.NONE
            confidence = 0.0

        # Beschreibung generieren
        if peak_months:
            month_names = {
                1: "Januar", 2: "Februar", 3: "Maerz", 4: "April",
                5: "Mai", 6: "Juni", 7: "Juli", 8: "August",
                9: "September", 10: "Oktober", 11: "November", 12: "Dezember",
            }
            peak_str = ", ".join(month_names[m] for m in sorted(peak_months))
            description = f"Hohe Ausgaben typischerweise in {peak_str}"
        else:
            description = "Gleichmaessig verteilte Ausgaben"

        # Kombiniere mit bekanntem Muster falls vorhanden
        known = self._known_patterns.get(category)
        if known:
            # Merge peaks
            peak_months = list(set(peak_months + known.get("peak_months", [])))
            description = known.get("description", description)

        return SeasonalPattern(
            id=uuid4(),
            category=category,
            season_type=SeasonType.ANNUAL if peak_months else SeasonType.MONTHLY,
            strength=strength,
            peak_months=peak_months,
            seasonal_factor=max(seasonal_factors.values()) if seasonal_factors else 1.0,
            typical_min_factor=min(seasonal_factors.values()) if seasonal_factors else 1.0,
            typical_max_factor=max(seasonal_factors.values()) if seasonal_factors else 1.0,
            average_amount=Decimal(str(overall_avg)),
            std_deviation=Decimal(str(safe_stdev([float(a) for a in all_amounts]))),
            confidence=confidence,
            description=description,
            data_points=len(all_amounts),
        )

    # -------------------------------------------------------------------------
    # Seasonal Expectations
    # -------------------------------------------------------------------------

    async def get_monthly_expectations(
        self,
        user_id: UUID,
        month: int,
        year: int,
        categories: Optional[List[CategoryType]] = None,
    ) -> List[MonthlyExpectation]:
        """
        Berechnet erwartete Ausgaben fuer einen Monat.

        Args:
            user_id: User-ID
            month: Monat (1-12)
            year: Jahr
            categories: Optional: Nur bestimmte Kategorien

        Returns:
            Liste von MonthlyExpectation pro Kategorie
        """
        expectations: List[MonthlyExpectation] = []

        # Welche Kategorien?
        cats = categories or list(CategoryType)

        # Hole User-Patterns
        user_patterns = self._user_patterns.get(user_id, {})

        for category in cats:
            # User-spezifisches oder bekanntes Muster
            pattern = user_patterns.get(category)
            known = self._known_patterns.get(category, {})

            if pattern:
                base_amount = pattern.average_amount
                is_peak = month in pattern.peak_months
                if is_peak:
                    factor = pattern.seasonal_factor
                else:
                    factor = pattern.typical_min_factor
            elif known:
                base_amount = Decimal("0")  # Kein historischer Durchschnitt
                is_peak = month in known.get("peak_months", [])
                factor = known.get("peak_factor", 1.0) if is_peak else known.get("low_factor", 1.0)
            else:
                continue

            # Erwartete Betraege berechnen
            expected = base_amount * Decimal(str(factor))
            range_min = expected * Decimal("0.7")
            range_max = expected * Decimal("1.5")

            # Events fuer diesen Monat
            events = [
                e.name for e in self._known_events.values()
                if e.typical_month == month and category in e.categories_affected
            ]

            expectations.append(MonthlyExpectation(
                month=month,
                year=year,
                category=category,
                expected_amount=expected,
                expected_range_min=range_min,
                expected_range_max=range_max,
                seasonal_factor=factor,
                is_peak_season=is_peak,
                expected_events=events,
                confidence=pattern.confidence if pattern else 0.5,
            ))

        return expectations

    # -------------------------------------------------------------------------
    # Anomaly Analysis with Seasonal Context
    # -------------------------------------------------------------------------

    async def analyze_anomaly(
        self,
        user_id: UUID,
        transaction_date: date,
        category: CategoryType,
        amount: Decimal,
        historical_avg: Optional[Decimal] = None,
    ) -> SeasonalAnomalyAnalysis:
        """
        Analysiert eine potenzielle Anomalie mit saisonalem Kontext.

        Args:
            user_id: User-ID
            transaction_date: Datum der Transaktion
            category: Kategorie
            amount: Betrag
            historical_avg: Optional: Historischer Durchschnitt

        Returns:
            SeasonalAnomalyAnalysis mit Kontext und Bewertung
        """
        month = transaction_date.month

        # Hole Pattern
        user_patterns = self._user_patterns.get(user_id, {})
        pattern = user_patterns.get(category)
        known = self._known_patterns.get(category, {})

        # Berechne Erwartung
        if pattern:
            base = pattern.average_amount
            is_peak = month in pattern.peak_months
            factor = pattern.seasonal_factor if is_peak else pattern.typical_min_factor
            expected = base * Decimal(str(factor))
            range_min = expected * Decimal("0.5")
            range_max = expected * Decimal("2.0")
            confidence = pattern.confidence
        elif known:
            base = historical_avg or Decimal("0")
            is_peak = month in known.get("peak_months", [])
            factor = known.get("peak_factor", 1.0) if is_peak else known.get("low_factor", 1.0)
            expected = base * Decimal(str(factor))
            range_min = expected * Decimal("0.3")
            range_max = expected * Decimal("3.0")
            confidence = 0.5
        else:
            expected = historical_avg or Decimal("0")
            range_min = expected * Decimal("0.5")
            range_max = expected * Decimal("2.0")
            is_peak = False
            confidence = 0.3

        # Deviation berechnen
        if expected > 0:
            deviation = float((amount - expected) / expected * 100)
        else:
            deviation = 100.0 if amount > 0 else 0.0

        # Kontext bestimmen
        if range_min <= amount <= range_max:
            if is_peak:
                context = AnomalyContext.EXPECTED_SEASONAL
                is_anomaly = False
                explanation = (
                    f"Betrag von {amount:.2f} EUR liegt im erwarteten Bereich "
                    f"fuer {category.value} im {self._month_name(month)}. "
                    f"Dies ist eine typische Peak-Saison."
                )
            else:
                context = AnomalyContext.EXPECTED_SEASONAL
                is_anomaly = False
                explanation = (
                    f"Betrag liegt im normalen Bereich fuer diese Kategorie."
                )
        else:
            # Pruefe auf bekannte Events
            events = [
                e for e in self._known_events.values()
                if e.typical_month == month and category in e.categories_affected
            ]
            if events:
                context = AnomalyContext.EXPECTED_EVENT
                is_anomaly = False
                event_names = ", ".join(e.name for e in events)
                explanation = (
                    f"Erhoehte Ausgaben wahrscheinlich durch: {event_names}. "
                    f"Typisch fuer diese Jahreszeit."
                )
            elif is_peak and amount > range_max:
                context = AnomalyContext.UNEXPECTED_SEASONAL
                is_anomaly = True
                explanation = (
                    f"Obwohl {self._month_name(month)} eine Peak-Saison ist, "
                    f"liegt der Betrag {deviation:.1f}% ueber dem erwarteten Maximum. "
                    f"Dies koennte auf aussergewoehnliche Umstaende hindeuten."
                )
            else:
                context = AnomalyContext.TRUE_ANOMALY
                is_anomaly = True
                explanation = (
                    f"Der Betrag weicht {deviation:.1f}% vom saisonalen Durchschnitt ab. "
                    f"{self._month_name(month)} ist keine typische Peak-Saison fuer {category.value}."
                )

        return SeasonalAnomalyAnalysis(
            id=uuid4(),
            transaction_date=transaction_date,
            category=category,
            amount=amount,
            context=context,
            seasonal_pattern=pattern,
            expected_amount=expected,
            expected_range=(range_min, range_max),
            deviation_percentage=deviation,
            is_true_anomaly=is_anomaly,
            confidence=confidence,
            explanation=explanation,
            similar_historical=[],  # Koennte mit echten Daten gefuellt werden
        )

    # -------------------------------------------------------------------------
    # Seasonal Forecasts
    # -------------------------------------------------------------------------

    async def generate_forecast(
        self,
        user_id: UUID,
        horizon_months: int = 12,
    ) -> SeasonalForecast:
        """
        Generiert saisonale Prognose fuer zukuenftige Monate.

        Args:
            user_id: User-ID
            horizon_months: Prognose-Horizont in Monaten

        Returns:
            SeasonalForecast mit monatlichen Erwartungen
        """
        today = date.today()
        monthly_forecasts: Dict[str, Dict[int, MonthlyExpectation]] = {}
        total_expected = Decimal("0")
        high_expense_months: List[int] = []
        peak_categories: Dict[int, List[CategoryType]] = {}

        for i in range(horizon_months):
            forecast_date = today + timedelta(days=30 * i)
            month = forecast_date.month
            year = forecast_date.year

            expectations = await self.get_monthly_expectations(
                user_id, month, year
            )

            month_total = Decimal("0")
            peaks = []

            for exp in expectations:
                cat_key = exp.category.value
                if cat_key not in monthly_forecasts:
                    monthly_forecasts[cat_key] = {}
                monthly_forecasts[cat_key][month] = exp

                month_total += exp.expected_amount
                if exp.is_peak_season:
                    peaks.append(exp.category)

            total_expected += month_total

            # Track high-expense months (> 1.3x average)
            avg_monthly = total_expected / (i + 1) if i > 0 else month_total
            if month_total > avg_monthly * Decimal("1.3"):
                high_expense_months.append(month)

            if peaks:
                peak_categories[month] = peaks

        # Berechne Gesamt-Range
        range_factor = Decimal("0.2")
        total_range = (
            total_expected * (1 - range_factor),
            total_expected * (1 + range_factor),
        )

        return SeasonalForecast(
            id=uuid4(),
            forecast_date=today,
            horizon_months=horizon_months,
            monthly_forecasts=monthly_forecasts,
            total_expected=total_expected,
            total_range=total_range,
            high_expense_months=high_expense_months,
            peak_categories=peak_categories,
            overall_confidence=0.7,
        )

    # -------------------------------------------------------------------------
    # Events Management
    # -------------------------------------------------------------------------

    async def add_custom_event(
        self,
        user_id: UUID,
        name: str,
        month: int,
        categories: List[CategoryType],
        typical_impact: Decimal,
        description: Optional[str] = None,
    ) -> SeasonalEvent:
        """Fuegt ein benutzerdefiniertes saisonales Event hinzu."""
        event = SeasonalEvent(
            id=uuid4(),
            name=name,
            description=description or f"Benutzerdefiniertes Event: {name}",
            typical_month=month,
            categories_affected=categories,
            typical_impact=typical_impact,
            impact_range=(typical_impact * Decimal("0.5"), typical_impact * Decimal("2.0")),
        )

        if user_id not in self._user_events:
            self._user_events[user_id] = []
        self._user_events[user_id].append(event)

        logger.info(
            "custom_event_added",
            user_id=str(user_id),
            event_name=name,
            month=month,
        )

        return event

    async def get_events_for_month(
        self,
        user_id: UUID,
        month: int,
    ) -> List[SeasonalEvent]:
        """Holt alle Events (bekannt + user-spezifisch) fuer einen Monat."""
        events = [
            e for e in self._known_events.values()
            if e.typical_month == month
        ]

        user_events = self._user_events.get(user_id, [])
        events.extend([e for e in user_events if e.typical_month == month])

        return events

    # -------------------------------------------------------------------------
    # Statistics
    # -------------------------------------------------------------------------

    async def get_seasonality_statistics(
        self,
        user_id: UUID,
    ) -> Dict[str, Any]:
        """Holt Statistiken zur Saisonalitaets-Erkennung."""
        user_patterns = self._user_patterns.get(user_id, {})
        user_events = self._user_events.get(user_id, [])

        strong_patterns = [
            p for p in user_patterns.values()
            if p.strength in [PatternStrength.STRONG, PatternStrength.VERY_STRONG]
        ]

        return {
            "detected_patterns": len(user_patterns),
            "strong_patterns": len(strong_patterns),
            "known_events": len(self._known_events),
            "custom_events": len(user_events),
            "categories_analyzed": list(user_patterns.keys()),
            "average_confidence": (
                sum(p.confidence for p in user_patterns.values()) / len(user_patterns)
                if user_patterns else 0
            ),
            "peak_months_identified": list({
                m for p in user_patterns.values()
                for m in p.peak_months
            }),
        }

    # -------------------------------------------------------------------------
    # Helper Methods
    # -------------------------------------------------------------------------

    def _month_name(self, month: int) -> str:
        """Gibt deutschen Monatsnamen zurueck."""
        names = {
            1: "Januar", 2: "Februar", 3: "Maerz", 4: "April",
            5: "Mai", 6: "Juni", 7: "Juli", 8: "August",
            9: "September", 10: "Oktober", 11: "November", 12: "Dezember",
        }
        return names.get(month, str(month))


# =============================================================================
# Singleton Accessor
# =============================================================================

_service_instance: Optional[SeasonalityDetectionService] = None
_service_lock = threading.Lock()


def get_seasonality_detection_service() -> SeasonalityDetectionService:
    """Gibt die Singleton-Instanz des Service zurueck."""
    global _service_instance

    if _service_instance is None:
        with _service_lock:
            if _service_instance is None:
                _service_instance = SeasonalityDetectionService()

    return _service_instance

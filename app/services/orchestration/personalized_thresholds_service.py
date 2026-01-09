# -*- coding: utf-8 -*-
"""
Personalized Thresholds Service.

Enterprise Feature: User-spezifische Schwellenwerte.

Das System lernt und passt Schwellenwerte an:
- Berufsprofile (Freelancer, Beamter, Angestellter, etc.)
- Individuelle Risikotoleranz
- Historisches Verhalten
- Self-Learning aus User-Feedback

Beispiele:
- DTI-Schwelle: 36% Standard → 40% fuer Freelancer mit variablem Einkommen
- Notgroschen: 6 Monate Standard → 3 Monate fuer Beamte mit Job-Sicherheit
- Rendite: 5% Standard → 8% fuer risikofreudige Investoren

TRUE Enterprise: Das System passt sich dem User an, nicht umgekehrt.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from uuid import UUID, uuid4

import structlog

logger = structlog.get_logger(__name__)


# =============================================================================
# Enums
# =============================================================================

class ProfessionType(str, Enum):
    """Berufstypen mit unterschiedlichen Risikoprofilen."""
    EMPLOYEE = "employee"  # Angestellter
    CIVIL_SERVANT = "civil_servant"  # Beamter
    FREELANCER = "freelancer"  # Freiberufler
    ENTREPRENEUR = "entrepreneur"  # Unternehmer
    SELF_EMPLOYED = "self_employed"  # Selbststaendig
    RETIRED = "retired"  # Rentner
    STUDENT = "student"  # Student
    UNEMPLOYED = "unemployed"  # Arbeitslos
    OTHER = "other"  # Sonstige


class RiskTolerance(str, Enum):
    """Risikotoleranz-Level."""
    VERY_CONSERVATIVE = "very_conservative"  # Sehr konservativ
    CONSERVATIVE = "conservative"  # Konservativ
    MODERATE = "moderate"  # Moderat
    AGGRESSIVE = "aggressive"  # Aggressiv
    VERY_AGGRESSIVE = "very_aggressive"  # Sehr aggressiv


class ThresholdType(str, Enum):
    """Schwellenwert-Typen."""
    DTI_RATIO = "dti_ratio"  # Debt-to-Income
    DTI_WARNING = "dti_warning"  # DTI Warnschwelle
    DTI_CRITICAL = "dti_critical"  # DTI Kritische Schwelle
    EMERGENCY_FUND_MIN = "emergency_fund_min"  # Minimum Notgroschen (Monate)
    EMERGENCY_FUND_TARGET = "emergency_fund_target"  # Ziel Notgroschen (Monate)
    SAVINGS_RATE_MIN = "savings_rate_min"  # Minimum Sparrate (%)
    SAVINGS_RATE_TARGET = "savings_rate_target"  # Ziel Sparrate (%)
    EXPECTED_RETURN = "expected_return"  # Erwartete Rendite (%)
    PORTFOLIO_DIVERSITY_MIN = "portfolio_diversity_min"  # Minimum Diversitaet
    HEALTH_SCORE_WARNING = "health_score_warning"  # Health Score Warnung
    HEALTH_SCORE_CRITICAL = "health_score_critical"  # Health Score Kritisch
    RENT_VS_INCOME_MAX = "rent_vs_income_max"  # Max Miete/Einkommen (%)
    LIQUIDITY_BUFFER_DAYS = "liquidity_buffer_days"  # Liquiditaetspuffer (Tage)
    INSURANCE_COVERAGE_MIN = "insurance_coverage_min"  # Min Versicherungsdeckung (%)
    LOAN_INTEREST_WARNING = "loan_interest_warning"  # Warnschwelle Kreditzins


class ThresholdCategory(str, Enum):
    """Kategorien fuer Schwellenwerte."""
    DEBT = "debt"  # Schulden
    SAVINGS = "savings"  # Ersparnisse
    INVESTMENT = "investment"  # Investments
    INSURANCE = "insurance"  # Versicherungen
    HEALTH_SCORE = "health_score"  # Financial Health
    LIQUIDITY = "liquidity"  # Liquiditaet
    HOUSING = "housing"  # Wohnen


class AdjustmentSource(str, Enum):
    """Quelle einer Schwellenwert-Anpassung."""
    SYSTEM_DEFAULT = "system_default"  # System-Default
    PROFESSION_PROFILE = "profession_profile"  # Berufsprofil
    USER_PREFERENCE = "user_preference"  # User-Praeferenz
    LEARNED_BEHAVIOR = "learned_behavior"  # Gelerntes Verhalten
    ADMIN_OVERRIDE = "admin_override"  # Admin-Override
    SEASONAL_ADJUSTMENT = "seasonal_adjustment"  # Saisonale Anpassung


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class ThresholdDefinition:
    """Definition eines Schwellenwertes."""
    threshold_type: ThresholdType
    category: ThresholdCategory
    name: str
    description: str
    unit: str  # %, Monate, EUR, etc.
    default_value: float
    min_allowed: float
    max_allowed: float
    # Profession-spezifische Defaults
    profession_defaults: Dict[ProfessionType, float] = field(default_factory=dict)
    # Risk-basierte Modifikatoren (multiplikativ)
    risk_modifiers: Dict[RiskTolerance, float] = field(default_factory=dict)


@dataclass
class UserThreshold:
    """Ein personalisierter Schwellenwert fuer einen User."""
    id: UUID
    user_id: UUID
    threshold_type: ThresholdType
    # Werte
    default_value: float
    current_value: float
    # Anpassung
    adjustment_source: AdjustmentSource
    adjustment_reason: Optional[str]
    # Metadaten
    created_at: datetime
    updated_at: datetime
    last_used_at: Optional[datetime]
    # Confidence
    confidence: float = 0.7  # Wie sicher sind wir?
    # Effectiveness Tracking
    times_triggered: int = 0
    times_acted_on: int = 0  # User hat auf Alert reagiert
    effectiveness_score: float = 1.0  # 0-1, wie effektiv ist dieser Threshold?


@dataclass
class UserProfile:
    """User-Profil fuer Schwellenwert-Personalisierung."""
    user_id: UUID
    profession_type: ProfessionType
    risk_tolerance: RiskTolerance
    income_stability: float  # 0-1, wie stabil ist das Einkommen?
    age_group: str  # "18-30", "31-45", "46-60", "60+"
    household_size: int
    # Finanzielle Situation
    has_dependents: bool
    is_homeowner: bool
    has_pension_plan: bool
    # Praeferenzen
    prefers_aggressive_alerts: bool = False
    prefers_conservative_targets: bool = True
    # Lernhistorie
    feedback_history: List[Dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ThresholdAdjustment:
    """Eine Anpassung eines Schwellenwertes."""
    id: UUID
    user_id: UUID
    threshold_type: ThresholdType
    previous_value: float
    new_value: float
    adjustment_source: AdjustmentSource
    reason: str
    confidence: float
    applied_at: datetime
    # Rollback Info
    can_rollback: bool = True
    rolled_back: bool = False


@dataclass
class ThresholdRecommendation:
    """Empfehlung fuer eine Schwellenwert-Anpassung."""
    id: UUID
    user_id: UUID
    threshold_type: ThresholdType
    current_value: float
    recommended_value: float
    reason: str
    confidence: float
    potential_impact: str
    created_at: datetime
    expires_at: datetime
    # Status
    accepted: Optional[bool] = None
    accepted_at: Optional[datetime] = None


# =============================================================================
# Threshold Registry
# =============================================================================

class ThresholdRegistry:
    """Registry aller verfuegbaren Schwellenwerte mit Defaults."""

    def __init__(self):
        self._thresholds: Dict[ThresholdType, ThresholdDefinition] = {}
        self._initialize_thresholds()

    def _initialize_thresholds(self) -> None:
        """Initialisiert alle Standard-Schwellenwerte."""

        # DTI Ratio Warning
        self._thresholds[ThresholdType.DTI_WARNING] = ThresholdDefinition(
            threshold_type=ThresholdType.DTI_WARNING,
            category=ThresholdCategory.DEBT,
            name="DTI Warnschwelle",
            description="Debt-to-Income Ratio ab der eine Warnung erscheint",
            unit="%",
            default_value=36.0,
            min_allowed=20.0,
            max_allowed=60.0,
            profession_defaults={
                ProfessionType.CIVIL_SERVANT: 40.0,  # Sichere Jobs
                ProfessionType.FREELANCER: 32.0,  # Variable Einkommen
                ProfessionType.ENTREPRENEUR: 45.0,  # Hoehere Schulden normal
                ProfessionType.RETIRED: 30.0,  # Konservativer
                ProfessionType.STUDENT: 25.0,  # Sehr konservativ
            },
            risk_modifiers={
                RiskTolerance.VERY_CONSERVATIVE: 0.85,
                RiskTolerance.CONSERVATIVE: 0.92,
                RiskTolerance.MODERATE: 1.0,
                RiskTolerance.AGGRESSIVE: 1.08,
                RiskTolerance.VERY_AGGRESSIVE: 1.15,
            }
        )

        # DTI Ratio Critical
        self._thresholds[ThresholdType.DTI_CRITICAL] = ThresholdDefinition(
            threshold_type=ThresholdType.DTI_CRITICAL,
            category=ThresholdCategory.DEBT,
            name="DTI Kritische Schwelle",
            description="Debt-to-Income Ratio ab der kritische Warnung erscheint",
            unit="%",
            default_value=50.0,
            min_allowed=35.0,
            max_allowed=75.0,
            profession_defaults={
                ProfessionType.CIVIL_SERVANT: 55.0,
                ProfessionType.FREELANCER: 45.0,
                ProfessionType.ENTREPRENEUR: 60.0,
                ProfessionType.RETIRED: 40.0,
                ProfessionType.STUDENT: 35.0,
            },
            risk_modifiers={
                RiskTolerance.VERY_CONSERVATIVE: 0.85,
                RiskTolerance.CONSERVATIVE: 0.92,
                RiskTolerance.MODERATE: 1.0,
                RiskTolerance.AGGRESSIVE: 1.08,
                RiskTolerance.VERY_AGGRESSIVE: 1.15,
            }
        )

        # Emergency Fund Minimum
        self._thresholds[ThresholdType.EMERGENCY_FUND_MIN] = ThresholdDefinition(
            threshold_type=ThresholdType.EMERGENCY_FUND_MIN,
            category=ThresholdCategory.SAVINGS,
            name="Notgroschen Minimum",
            description="Minimale Notreserve in Monats-Ausgaben",
            unit="Monate",
            default_value=3.0,
            min_allowed=1.0,
            max_allowed=12.0,
            profession_defaults={
                ProfessionType.CIVIL_SERVANT: 2.0,  # Sichere Jobs brauchen weniger
                ProfessionType.FREELANCER: 6.0,  # Variable Einkommen
                ProfessionType.ENTREPRENEUR: 6.0,
                ProfessionType.RETIRED: 3.0,
                ProfessionType.STUDENT: 2.0,
            },
            risk_modifiers={
                RiskTolerance.VERY_CONSERVATIVE: 1.3,  # Mehr Puffer
                RiskTolerance.CONSERVATIVE: 1.15,
                RiskTolerance.MODERATE: 1.0,
                RiskTolerance.AGGRESSIVE: 0.9,
                RiskTolerance.VERY_AGGRESSIVE: 0.8,
            }
        )

        # Emergency Fund Target
        self._thresholds[ThresholdType.EMERGENCY_FUND_TARGET] = ThresholdDefinition(
            threshold_type=ThresholdType.EMERGENCY_FUND_TARGET,
            category=ThresholdCategory.SAVINGS,
            name="Notgroschen Ziel",
            description="Ziel-Notreserve in Monats-Ausgaben",
            unit="Monate",
            default_value=6.0,
            min_allowed=3.0,
            max_allowed=24.0,
            profession_defaults={
                ProfessionType.CIVIL_SERVANT: 3.0,
                ProfessionType.FREELANCER: 9.0,
                ProfessionType.ENTREPRENEUR: 12.0,
                ProfessionType.RETIRED: 6.0,
                ProfessionType.STUDENT: 3.0,
            },
            risk_modifiers={
                RiskTolerance.VERY_CONSERVATIVE: 1.5,
                RiskTolerance.CONSERVATIVE: 1.2,
                RiskTolerance.MODERATE: 1.0,
                RiskTolerance.AGGRESSIVE: 0.85,
                RiskTolerance.VERY_AGGRESSIVE: 0.7,
            }
        )

        # Savings Rate Minimum
        self._thresholds[ThresholdType.SAVINGS_RATE_MIN] = ThresholdDefinition(
            threshold_type=ThresholdType.SAVINGS_RATE_MIN,
            category=ThresholdCategory.SAVINGS,
            name="Sparrate Minimum",
            description="Minimale monatliche Sparrate",
            unit="%",
            default_value=10.0,
            min_allowed=0.0,
            max_allowed=50.0,
            profession_defaults={
                ProfessionType.CIVIL_SERVANT: 8.0,  # Pension vorhanden
                ProfessionType.FREELANCER: 15.0,  # Mehr sparen noetig
                ProfessionType.ENTREPRENEUR: 12.0,
                ProfessionType.RETIRED: 0.0,
                ProfessionType.STUDENT: 5.0,
            },
            risk_modifiers={
                RiskTolerance.VERY_CONSERVATIVE: 1.3,
                RiskTolerance.CONSERVATIVE: 1.15,
                RiskTolerance.MODERATE: 1.0,
                RiskTolerance.AGGRESSIVE: 0.9,
                RiskTolerance.VERY_AGGRESSIVE: 0.8,
            }
        )

        # Savings Rate Target
        self._thresholds[ThresholdType.SAVINGS_RATE_TARGET] = ThresholdDefinition(
            threshold_type=ThresholdType.SAVINGS_RATE_TARGET,
            category=ThresholdCategory.SAVINGS,
            name="Sparrate Ziel",
            description="Ziel-Sparrate monatlich",
            unit="%",
            default_value=20.0,
            min_allowed=5.0,
            max_allowed=70.0,
            profession_defaults={
                ProfessionType.CIVIL_SERVANT: 15.0,
                ProfessionType.FREELANCER: 25.0,
                ProfessionType.ENTREPRENEUR: 20.0,
                ProfessionType.RETIRED: 5.0,
                ProfessionType.STUDENT: 10.0,
            },
            risk_modifiers={
                RiskTolerance.VERY_CONSERVATIVE: 1.2,
                RiskTolerance.CONSERVATIVE: 1.1,
                RiskTolerance.MODERATE: 1.0,
                RiskTolerance.AGGRESSIVE: 0.95,
                RiskTolerance.VERY_AGGRESSIVE: 0.9,
            }
        )

        # Expected Return
        self._thresholds[ThresholdType.EXPECTED_RETURN] = ThresholdDefinition(
            threshold_type=ThresholdType.EXPECTED_RETURN,
            category=ThresholdCategory.INVESTMENT,
            name="Erwartete Rendite",
            description="Erwartete jaehrliche Portfolio-Rendite",
            unit="%",
            default_value=5.0,
            min_allowed=0.0,
            max_allowed=20.0,
            profession_defaults={
                ProfessionType.RETIRED: 3.0,  # Konservativer
                ProfessionType.STUDENT: 7.0,  # Langer Zeithorizont
            },
            risk_modifiers={
                RiskTolerance.VERY_CONSERVATIVE: 0.6,  # ~3%
                RiskTolerance.CONSERVATIVE: 0.8,  # ~4%
                RiskTolerance.MODERATE: 1.0,  # 5%
                RiskTolerance.AGGRESSIVE: 1.4,  # ~7%
                RiskTolerance.VERY_AGGRESSIVE: 1.8,  # ~9%
            }
        )

        # Portfolio Diversity Minimum
        self._thresholds[ThresholdType.PORTFOLIO_DIVERSITY_MIN] = ThresholdDefinition(
            threshold_type=ThresholdType.PORTFOLIO_DIVERSITY_MIN,
            category=ThresholdCategory.INVESTMENT,
            name="Portfolio Diversitaet Minimum",
            description="Minimale Portfolio-Diversifikation",
            unit="Index (0-1)",
            default_value=0.5,
            min_allowed=0.1,
            max_allowed=0.9,
            profession_defaults={
                ProfessionType.RETIRED: 0.6,  # Mehr Diversifikation
            },
            risk_modifiers={
                RiskTolerance.VERY_CONSERVATIVE: 1.3,
                RiskTolerance.CONSERVATIVE: 1.15,
                RiskTolerance.MODERATE: 1.0,
                RiskTolerance.AGGRESSIVE: 0.85,
                RiskTolerance.VERY_AGGRESSIVE: 0.7,
            }
        )

        # Health Score Warning
        self._thresholds[ThresholdType.HEALTH_SCORE_WARNING] = ThresholdDefinition(
            threshold_type=ThresholdType.HEALTH_SCORE_WARNING,
            category=ThresholdCategory.HEALTH_SCORE,
            name="Health Score Warnung",
            description="Health Score ab dem eine Warnung erscheint",
            unit="Punkte",
            default_value=60.0,
            min_allowed=40.0,
            max_allowed=80.0,
            profession_defaults={},
            risk_modifiers={
                RiskTolerance.VERY_CONSERVATIVE: 1.1,  # Frueher warnen
                RiskTolerance.CONSERVATIVE: 1.05,
                RiskTolerance.MODERATE: 1.0,
                RiskTolerance.AGGRESSIVE: 0.95,
                RiskTolerance.VERY_AGGRESSIVE: 0.9,
            }
        )

        # Health Score Critical
        self._thresholds[ThresholdType.HEALTH_SCORE_CRITICAL] = ThresholdDefinition(
            threshold_type=ThresholdType.HEALTH_SCORE_CRITICAL,
            category=ThresholdCategory.HEALTH_SCORE,
            name="Health Score Kritisch",
            description="Health Score ab dem kritische Warnung erscheint",
            unit="Punkte",
            default_value=40.0,
            min_allowed=20.0,
            max_allowed=60.0,
            profession_defaults={},
            risk_modifiers={
                RiskTolerance.VERY_CONSERVATIVE: 1.15,
                RiskTolerance.CONSERVATIVE: 1.08,
                RiskTolerance.MODERATE: 1.0,
                RiskTolerance.AGGRESSIVE: 0.92,
                RiskTolerance.VERY_AGGRESSIVE: 0.85,
            }
        )

        # Rent vs Income Maximum
        self._thresholds[ThresholdType.RENT_VS_INCOME_MAX] = ThresholdDefinition(
            threshold_type=ThresholdType.RENT_VS_INCOME_MAX,
            category=ThresholdCategory.HOUSING,
            name="Max Mietanteil",
            description="Maximaler Anteil des Einkommens fuer Miete",
            unit="%",
            default_value=30.0,
            min_allowed=15.0,
            max_allowed=50.0,
            profession_defaults={
                ProfessionType.CIVIL_SERVANT: 35.0,  # Stabiles Einkommen
                ProfessionType.FREELANCER: 25.0,  # Konservativer
                ProfessionType.STUDENT: 40.0,  # Typischerweise hoeher
            },
            risk_modifiers={
                RiskTolerance.VERY_CONSERVATIVE: 0.85,
                RiskTolerance.CONSERVATIVE: 0.92,
                RiskTolerance.MODERATE: 1.0,
                RiskTolerance.AGGRESSIVE: 1.1,
                RiskTolerance.VERY_AGGRESSIVE: 1.2,
            }
        )

        # Liquidity Buffer Days
        self._thresholds[ThresholdType.LIQUIDITY_BUFFER_DAYS] = ThresholdDefinition(
            threshold_type=ThresholdType.LIQUIDITY_BUFFER_DAYS,
            category=ThresholdCategory.LIQUIDITY,
            name="Liquiditaetspuffer",
            description="Minimaler Liquiditaetspuffer in Tagen",
            unit="Tage",
            default_value=30.0,
            min_allowed=7.0,
            max_allowed=90.0,
            profession_defaults={
                ProfessionType.FREELANCER: 45.0,
                ProfessionType.ENTREPRENEUR: 60.0,
            },
            risk_modifiers={
                RiskTolerance.VERY_CONSERVATIVE: 1.5,
                RiskTolerance.CONSERVATIVE: 1.2,
                RiskTolerance.MODERATE: 1.0,
                RiskTolerance.AGGRESSIVE: 0.8,
                RiskTolerance.VERY_AGGRESSIVE: 0.6,
            }
        )

        # Insurance Coverage Minimum
        self._thresholds[ThresholdType.INSURANCE_COVERAGE_MIN] = ThresholdDefinition(
            threshold_type=ThresholdType.INSURANCE_COVERAGE_MIN,
            category=ThresholdCategory.INSURANCE,
            name="Versicherungsdeckung Minimum",
            description="Minimale Versicherungsdeckung",
            unit="%",
            default_value=80.0,
            min_allowed=50.0,
            max_allowed=100.0,
            profession_defaults={
                ProfessionType.FREELANCER: 90.0,  # Mehr Absicherung noetig
                ProfessionType.ENTREPRENEUR: 90.0,
            },
            risk_modifiers={
                RiskTolerance.VERY_CONSERVATIVE: 1.1,
                RiskTolerance.CONSERVATIVE: 1.05,
                RiskTolerance.MODERATE: 1.0,
                RiskTolerance.AGGRESSIVE: 0.95,
                RiskTolerance.VERY_AGGRESSIVE: 0.9,
            }
        )

        # Loan Interest Warning
        self._thresholds[ThresholdType.LOAN_INTEREST_WARNING] = ThresholdDefinition(
            threshold_type=ThresholdType.LOAN_INTEREST_WARNING,
            category=ThresholdCategory.DEBT,
            name="Kreditzins Warnschwelle",
            description="Zinssatz ab dem Refinanzierung geprueft wird",
            unit="%",
            default_value=5.0,
            min_allowed=2.0,
            max_allowed=15.0,
            profession_defaults={},
            risk_modifiers={
                RiskTolerance.VERY_CONSERVATIVE: 0.8,  # Frueher warnen
                RiskTolerance.CONSERVATIVE: 0.9,
                RiskTolerance.MODERATE: 1.0,
                RiskTolerance.AGGRESSIVE: 1.1,
                RiskTolerance.VERY_AGGRESSIVE: 1.2,
            }
        )

    def get_threshold(self, threshold_type: ThresholdType) -> Optional[ThresholdDefinition]:
        """Gibt Threshold-Definition zurueck."""
        return self._thresholds.get(threshold_type)

    def get_all_thresholds(self) -> List[ThresholdDefinition]:
        """Gibt alle Threshold-Definitionen zurueck."""
        return list(self._thresholds.values())

    def get_thresholds_by_category(self, category: ThresholdCategory) -> List[ThresholdDefinition]:
        """Gibt Thresholds einer Kategorie zurueck."""
        return [t for t in self._thresholds.values() if t.category == category]


# =============================================================================
# Main Service Class
# =============================================================================

class PersonalizedThresholdsService:
    """
    Service fuer personalisierte Schwellenwerte.

    Features:
    - Berufsprofilbasierte Defaults
    - Risikotoleranz-Anpassung
    - User-spezifische Overrides
    - Self-Learning aus Feedback
    - Effektivitaets-Tracking
    """

    _instance: Optional[PersonalizedThresholdsService] = None
    _lock = threading.Lock()

    def __new__(cls) -> PersonalizedThresholdsService:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return

        self.registry = ThresholdRegistry()

        # In-Memory Storage (in Produktion: DB-backed)
        self._user_profiles: Dict[UUID, UserProfile] = {}
        self._user_thresholds: Dict[UUID, Dict[ThresholdType, UserThreshold]] = {}
        self._adjustments: List[ThresholdAdjustment] = []
        self._recommendations: Dict[UUID, List[ThresholdRecommendation]] = {}

        # Memory Management Limits
        self._max_profiles = 10000  # Max cached profiles
        self._max_adjustments = 50000  # Max adjustment history
        self._max_recommendations_per_user = 100  # Max recommendations per user

        self._initialized = True
        logger.info("PersonalizedThresholdsService initialisiert")

    def cleanup_old_data(self) -> int:
        """
        Bereinigt alte Daten um Memory-Leaks zu verhindern.

        Returns:
            Anzahl entfernter Eintraege.
        """
        removed = 0

        # Prune adjustments (keep most recent)
        if len(self._adjustments) > self._max_adjustments:
            excess = len(self._adjustments) - self._max_adjustments
            self._adjustments = self._adjustments[excess:]
            removed += excess

        # Prune recommendations per user
        for user_id in self._recommendations:
            recs = self._recommendations[user_id]
            if len(recs) > self._max_recommendations_per_user:
                excess = len(recs) - self._max_recommendations_per_user
                self._recommendations[user_id] = recs[excess:]
                removed += excess

        if removed > 0:
            logger.info("personalized_thresholds_cleanup", removed=removed)

        return removed

    # -------------------------------------------------------------------------
    # Profile Management
    # -------------------------------------------------------------------------

    async def get_or_create_profile(
        self,
        user_id: UUID,
        profession_type: Optional[ProfessionType] = None,
        risk_tolerance: Optional[RiskTolerance] = None,
    ) -> UserProfile:
        """Holt oder erstellt ein User-Profil."""
        if user_id in self._user_profiles:
            profile = self._user_profiles[user_id]
            # Update wenn neue Werte
            if profession_type:
                profile.profession_type = profession_type
                profile.updated_at = datetime.now(timezone.utc)
            if risk_tolerance:
                profile.risk_tolerance = risk_tolerance
                profile.updated_at = datetime.now(timezone.utc)
            return profile

        # Neues Profil erstellen
        profile = UserProfile(
            user_id=user_id,
            profession_type=profession_type or ProfessionType.EMPLOYEE,
            risk_tolerance=risk_tolerance or RiskTolerance.MODERATE,
            income_stability=0.7,
            age_group="31-45",
            household_size=2,
            has_dependents=False,
            is_homeowner=False,
            has_pension_plan=True,
        )
        self._user_profiles[user_id] = profile

        # Initialisiere Thresholds fuer neuen User
        await self._initialize_user_thresholds(user_id, profile)

        logger.info(
            "user_profile_created",
            user_id=str(user_id),
            profession=profession_type.value if profession_type else "employee",
            risk=risk_tolerance.value if risk_tolerance else "moderate",
        )

        return profile

    async def update_profile(
        self,
        user_id: UUID,
        updates: Dict[str, Any],
    ) -> UserProfile:
        """Aktualisiert ein User-Profil."""
        profile = await self.get_or_create_profile(user_id)

        if "profession_type" in updates:
            profile.profession_type = ProfessionType(updates["profession_type"])
        if "risk_tolerance" in updates:
            profile.risk_tolerance = RiskTolerance(updates["risk_tolerance"])
        if "income_stability" in updates:
            profile.income_stability = updates["income_stability"]
        if "age_group" in updates:
            profile.age_group = updates["age_group"]
        if "household_size" in updates:
            profile.household_size = updates["household_size"]
        if "has_dependents" in updates:
            profile.has_dependents = updates["has_dependents"]
        if "is_homeowner" in updates:
            profile.is_homeowner = updates["is_homeowner"]
        if "has_pension_plan" in updates:
            profile.has_pension_plan = updates["has_pension_plan"]
        if "prefers_aggressive_alerts" in updates:
            profile.prefers_aggressive_alerts = updates["prefers_aggressive_alerts"]
        if "prefers_conservative_targets" in updates:
            profile.prefers_conservative_targets = updates["prefers_conservative_targets"]

        profile.updated_at = datetime.now(timezone.utc)

        # Recalculate thresholds
        await self._recalculate_thresholds(user_id, profile)

        logger.info("user_profile_updated", user_id=str(user_id))

        return profile

    # -------------------------------------------------------------------------
    # Threshold Management
    # -------------------------------------------------------------------------

    async def _initialize_user_thresholds(
        self,
        user_id: UUID,
        profile: UserProfile,
    ) -> None:
        """Initialisiert Thresholds fuer einen neuen User."""
        if user_id not in self._user_thresholds:
            self._user_thresholds[user_id] = {}

        now = datetime.now(timezone.utc)

        for definition in self.registry.get_all_thresholds():
            calculated_value = self._calculate_personalized_value(definition, profile)

            threshold = UserThreshold(
                id=uuid4(),
                user_id=user_id,
                threshold_type=definition.threshold_type,
                default_value=definition.default_value,
                current_value=calculated_value,
                adjustment_source=AdjustmentSource.PROFESSION_PROFILE,
                adjustment_reason=f"Basierend auf Berufsprofil: {profile.profession_type.value}",
                created_at=now,
                updated_at=now,
                last_used_at=None,
                confidence=0.75,
            )

            self._user_thresholds[user_id][definition.threshold_type] = threshold

    def _calculate_personalized_value(
        self,
        definition: ThresholdDefinition,
        profile: UserProfile,
    ) -> float:
        """Berechnet personalisierten Schwellenwert."""
        # Start mit Default
        value = definition.default_value

        # Profession-basierter Override
        if profile.profession_type in definition.profession_defaults:
            value = definition.profession_defaults[profile.profession_type]

        # Risk Modifier anwenden
        if profile.risk_tolerance in definition.risk_modifiers:
            modifier = definition.risk_modifiers[profile.risk_tolerance]
            value = value * modifier

        # Clamp to allowed range
        value = max(definition.min_allowed, min(definition.max_allowed, value))

        return round(value, 2)

    async def _recalculate_thresholds(
        self,
        user_id: UUID,
        profile: UserProfile,
    ) -> None:
        """Berechnet alle Thresholds nach Profil-Aenderung neu."""
        if user_id not in self._user_thresholds:
            await self._initialize_user_thresholds(user_id, profile)
            return

        now = datetime.now(timezone.utc)

        for threshold_type, threshold in self._user_thresholds[user_id].items():
            # Nur wenn nicht User-Override
            if threshold.adjustment_source in [
                AdjustmentSource.SYSTEM_DEFAULT,
                AdjustmentSource.PROFESSION_PROFILE,
            ]:
                definition = self.registry.get_threshold(threshold_type)
                if definition:
                    new_value = self._calculate_personalized_value(definition, profile)

                    if new_value != threshold.current_value:
                        # Log adjustment
                        adjustment = ThresholdAdjustment(
                            id=uuid4(),
                            user_id=user_id,
                            threshold_type=threshold_type,
                            previous_value=threshold.current_value,
                            new_value=new_value,
                            adjustment_source=AdjustmentSource.PROFESSION_PROFILE,
                            reason=f"Profil-Update: {profile.profession_type.value}, {profile.risk_tolerance.value}",
                            confidence=0.8,
                            applied_at=now,
                        )
                        self._adjustments.append(adjustment)

                        # Update threshold
                        threshold.current_value = new_value
                        threshold.adjustment_source = AdjustmentSource.PROFESSION_PROFILE
                        threshold.updated_at = now

    async def get_threshold(
        self,
        user_id: UUID,
        threshold_type: ThresholdType,
    ) -> Optional[UserThreshold]:
        """Holt einen personalisierten Schwellenwert."""
        await self.get_or_create_profile(user_id)  # Ensure initialized

        if user_id in self._user_thresholds:
            threshold = self._user_thresholds[user_id].get(threshold_type)
            if threshold:
                threshold.last_used_at = datetime.now(timezone.utc)
                return threshold

        return None

    async def get_all_thresholds(
        self,
        user_id: UUID,
        category: Optional[ThresholdCategory] = None,
    ) -> List[UserThreshold]:
        """Holt alle personalisierten Schwellenwerte eines Users."""
        await self.get_or_create_profile(user_id)  # Ensure initialized

        if user_id not in self._user_thresholds:
            return []

        thresholds = list(self._user_thresholds[user_id].values())

        if category:
            category_types = {
                t.threshold_type
                for t in self.registry.get_thresholds_by_category(category)
            }
            thresholds = [t for t in thresholds if t.threshold_type in category_types]

        return thresholds

    async def set_threshold(
        self,
        user_id: UUID,
        threshold_type: ThresholdType,
        value: float,
        reason: Optional[str] = None,
    ) -> UserThreshold:
        """Setzt einen personalisierten Schwellenwert."""
        await self.get_or_create_profile(user_id)  # Ensure initialized

        definition = self.registry.get_threshold(threshold_type)
        if not definition:
            raise ValueError(f"Unknown threshold type: {threshold_type}")

        # Validate value
        if value < definition.min_allowed or value > definition.max_allowed:
            raise ValueError(
                f"Wert {value} ausserhalb des erlaubten Bereichs "
                f"[{definition.min_allowed}, {definition.max_allowed}]"
            )

        now = datetime.now(timezone.utc)

        # Get or create threshold
        if threshold_type in self._user_thresholds.get(user_id, {}):
            threshold = self._user_thresholds[user_id][threshold_type]
            previous_value = threshold.current_value
        else:
            threshold = UserThreshold(
                id=uuid4(),
                user_id=user_id,
                threshold_type=threshold_type,
                default_value=definition.default_value,
                current_value=value,
                adjustment_source=AdjustmentSource.USER_PREFERENCE,
                adjustment_reason=reason,
                created_at=now,
                updated_at=now,
                last_used_at=None,
            )
            previous_value = definition.default_value
            if user_id not in self._user_thresholds:
                self._user_thresholds[user_id] = {}
            self._user_thresholds[user_id][threshold_type] = threshold

        # Log adjustment
        adjustment = ThresholdAdjustment(
            id=uuid4(),
            user_id=user_id,
            threshold_type=threshold_type,
            previous_value=previous_value,
            new_value=value,
            adjustment_source=AdjustmentSource.USER_PREFERENCE,
            reason=reason or "User-Praeferenz",
            confidence=1.0,  # User knows best
            applied_at=now,
        )
        self._adjustments.append(adjustment)

        # Update threshold
        threshold.current_value = value
        threshold.adjustment_source = AdjustmentSource.USER_PREFERENCE
        threshold.adjustment_reason = reason
        threshold.updated_at = now
        threshold.confidence = 1.0

        logger.info(
            "threshold_set",
            user_id=str(user_id),
            threshold_type=threshold_type.value,
            value=value,
            reason=reason,
        )

        return threshold

    async def reset_threshold(
        self,
        user_id: UUID,
        threshold_type: ThresholdType,
    ) -> UserThreshold:
        """Setzt einen Schwellenwert auf den profil-basierten Default zurueck."""
        profile = await self.get_or_create_profile(user_id)

        definition = self.registry.get_threshold(threshold_type)
        if not definition:
            raise ValueError(f"Unknown threshold type: {threshold_type}")

        # Calculate personalized default
        default_value = self._calculate_personalized_value(definition, profile)

        return await self.set_threshold(
            user_id=user_id,
            threshold_type=threshold_type,
            value=default_value,
            reason="Zurueckgesetzt auf Profil-Default",
        )

    async def reset_all_thresholds(self, user_id: UUID) -> List[UserThreshold]:
        """Setzt alle Schwellenwerte zurueck."""
        profile = await self.get_or_create_profile(user_id)

        results = []
        for threshold_type in ThresholdType:
            try:
                threshold = await self.reset_threshold(user_id, threshold_type)
                results.append(threshold)
            except ValueError:
                continue

        logger.info("all_thresholds_reset", user_id=str(user_id), count=len(results))

        return results

    # -------------------------------------------------------------------------
    # Effectiveness Tracking
    # -------------------------------------------------------------------------

    async def record_threshold_trigger(
        self,
        user_id: UUID,
        threshold_type: ThresholdType,
        actual_value: float,
        triggered: bool,
    ) -> None:
        """Zeichnet auf, wenn ein Threshold getriggert wurde."""
        threshold = await self.get_threshold(user_id, threshold_type)
        if threshold:
            threshold.times_triggered += 1
            threshold.last_used_at = datetime.now(timezone.utc)

    async def record_threshold_action(
        self,
        user_id: UUID,
        threshold_type: ThresholdType,
        action_taken: bool,
    ) -> None:
        """Zeichnet auf, ob User auf Threshold-Alert reagiert hat."""
        threshold = await self.get_threshold(user_id, threshold_type)
        if threshold:
            if action_taken:
                threshold.times_acted_on += 1

            # Update effectiveness
            if threshold.times_triggered > 0:
                threshold.effectiveness_score = (
                    threshold.times_acted_on / threshold.times_triggered
                )

    # -------------------------------------------------------------------------
    # Recommendations
    # -------------------------------------------------------------------------

    async def generate_threshold_recommendations(
        self,
        user_id: UUID,
        current_kpis: Dict[str, float],
    ) -> List[ThresholdRecommendation]:
        """Generiert Empfehlungen fuer Schwellenwert-Anpassungen."""
        profile = await self.get_or_create_profile(user_id)
        recommendations: List[ThresholdRecommendation] = []
        now = datetime.now(timezone.utc)

        # Analyse KPIs und generiere Empfehlungen

        # DTI-basierte Empfehlung
        if "dti_ratio" in current_kpis:
            dti = current_kpis["dti_ratio"]
            dti_warning = await self.get_threshold(user_id, ThresholdType.DTI_WARNING)

            if dti_warning:
                # User ist chronisch nah am Threshold
                if dti > dti_warning.current_value * 0.9 and dti < dti_warning.current_value:
                    # Vielleicht Threshold erhoehen wenn stabil
                    if profile.income_stability > 0.8:
                        recommendations.append(ThresholdRecommendation(
                            id=uuid4(),
                            user_id=user_id,
                            threshold_type=ThresholdType.DTI_WARNING,
                            current_value=dti_warning.current_value,
                            recommended_value=min(dti_warning.current_value + 3, 50),
                            reason=(
                                f"Ihr DTI liegt stabil bei {dti:.1f}%. "
                                f"Bei Ihrer Einkommensstabilitaet koennte der Warnschwellenwert "
                                f"leicht erhoeht werden."
                            ),
                            confidence=0.7,
                            potential_impact="Weniger Warnungen bei stabilem Einkommen",
                            created_at=now,
                            expires_at=now + timedelta(days=30),
                        ))

        # Notgroschen-Empfehlung
        if "emergency_fund_months" in current_kpis:
            ef_months = current_kpis["emergency_fund_months"]
            ef_target = await self.get_threshold(user_id, ThresholdType.EMERGENCY_FUND_TARGET)

            if ef_target:
                # User hat deutlich mehr als Ziel
                if ef_months > ef_target.current_value * 1.5:
                    recommendations.append(ThresholdRecommendation(
                        id=uuid4(),
                        user_id=user_id,
                        threshold_type=ThresholdType.EMERGENCY_FUND_TARGET,
                        current_value=ef_target.current_value,
                        recommended_value=min(ef_months * 0.8, 12),
                        reason=(
                            f"Ihr Notgroschen ({ef_months:.1f} Monate) ist deutlich ueber "
                            f"dem Ziel ({ef_target.current_value:.1f} Monate). "
                            f"Ueberschuessige Liquiditaet koennte investiert werden."
                        ),
                        confidence=0.75,
                        potential_impact="Mehr Kapital fuer Investments verfuegbar",
                        created_at=now,
                        expires_at=now + timedelta(days=60),
                    ))

        # Sparrate-Empfehlung
        if "monthly_savings_rate" in current_kpis:
            savings_rate = current_kpis["monthly_savings_rate"]
            sr_target = await self.get_threshold(user_id, ThresholdType.SAVINGS_RATE_TARGET)

            if sr_target and savings_rate > sr_target.current_value * 1.2:
                # User spart mehr als Ziel
                recommendations.append(ThresholdRecommendation(
                    id=uuid4(),
                    user_id=user_id,
                    threshold_type=ThresholdType.SAVINGS_RATE_TARGET,
                    current_value=sr_target.current_value,
                    recommended_value=min(savings_rate, 50),
                    reason=(
                        f"Sie sparen konstant {savings_rate:.1f}%, mehr als Ihr Ziel "
                        f"von {sr_target.current_value:.1f}%. Das neue Ziel reflektiert "
                        f"Ihre tatsaechliche Sparleistung."
                    ),
                    confidence=0.8,
                    potential_impact="Realistischeres Ziel, besseres Tracking",
                    created_at=now,
                    expires_at=now + timedelta(days=30),
                ))

        # Store recommendations
        if user_id not in self._recommendations:
            self._recommendations[user_id] = []
        self._recommendations[user_id].extend(recommendations)

        return recommendations

    async def get_pending_recommendations(
        self,
        user_id: UUID,
    ) -> List[ThresholdRecommendation]:
        """Holt ausstehende Empfehlungen."""
        now = datetime.now(timezone.utc)

        if user_id not in self._recommendations:
            return []

        # Filter expired and already accepted
        pending = [
            r for r in self._recommendations[user_id]
            if r.expires_at > now and r.accepted is None
        ]

        return pending

    async def accept_recommendation(
        self,
        user_id: UUID,
        recommendation_id: UUID,
    ) -> Optional[UserThreshold]:
        """Akzeptiert eine Empfehlung."""
        if user_id not in self._recommendations:
            return None

        for rec in self._recommendations[user_id]:
            if rec.id == recommendation_id and rec.accepted is None:
                rec.accepted = True
                rec.accepted_at = datetime.now(timezone.utc)

                # Apply the recommendation
                return await self.set_threshold(
                    user_id=user_id,
                    threshold_type=rec.threshold_type,
                    value=rec.recommended_value,
                    reason=f"Empfehlung akzeptiert: {rec.reason[:100]}",
                )

        return None

    async def reject_recommendation(
        self,
        user_id: UUID,
        recommendation_id: UUID,
        reason: Optional[str] = None,
    ) -> bool:
        """Lehnt eine Empfehlung ab."""
        if user_id not in self._recommendations:
            return False

        for rec in self._recommendations[user_id]:
            if rec.id == recommendation_id and rec.accepted is None:
                rec.accepted = False
                rec.accepted_at = datetime.now(timezone.utc)

                # Learn from rejection
                profile = await self.get_or_create_profile(user_id)
                profile.feedback_history.append({
                    "type": "recommendation_rejected",
                    "threshold_type": rec.threshold_type.value,
                    "recommended_value": rec.recommended_value,
                    "reason": reason,
                    "at": datetime.now(timezone.utc).isoformat(),
                })

                return True

        return False

    # -------------------------------------------------------------------------
    # Statistics
    # -------------------------------------------------------------------------

    async def get_threshold_statistics(
        self,
        user_id: UUID,
    ) -> Dict[str, Any]:
        """Holt Statistiken zu Schwellenwerten."""
        thresholds = await self.get_all_thresholds(user_id)

        if not thresholds:
            return {
                "total_thresholds": 0,
                "customized_count": 0,
                "average_effectiveness": 0,
            }

        customized = [
            t for t in thresholds
            if t.adjustment_source == AdjustmentSource.USER_PREFERENCE
        ]

        effectiveness_scores = [
            t.effectiveness_score for t in thresholds
            if t.times_triggered > 0
        ]

        return {
            "total_thresholds": len(thresholds),
            "customized_count": len(customized),
            "system_defaults_count": len(thresholds) - len(customized),
            "average_effectiveness": (
                sum(effectiveness_scores) / len(effectiveness_scores)
                if effectiveness_scores else 0
            ),
            "total_triggers": sum(t.times_triggered for t in thresholds),
            "total_actions": sum(t.times_acted_on for t in thresholds),
            "pending_recommendations": len(
                await self.get_pending_recommendations(user_id)
            ),
        }

    async def get_adjustment_history(
        self,
        user_id: UUID,
        limit: int = 20,
    ) -> List[ThresholdAdjustment]:
        """Holt Anpassungs-Historie."""
        user_adjustments = [
            a for a in self._adjustments
            if a.user_id == user_id
        ]

        # Sort by date descending
        user_adjustments.sort(key=lambda a: a.applied_at, reverse=True)

        return user_adjustments[:limit]


# =============================================================================
# Singleton Accessor
# =============================================================================

_service_instance: Optional[PersonalizedThresholdsService] = None
_service_lock = threading.Lock()


def get_personalized_thresholds_service() -> PersonalizedThresholdsService:
    """Gibt die Singleton-Instanz des Service zurueck."""
    global _service_instance

    if _service_instance is None:
        with _service_lock:
            if _service_instance is None:
                _service_instance = PersonalizedThresholdsService()

    return _service_instance

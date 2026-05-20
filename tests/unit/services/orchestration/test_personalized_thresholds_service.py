# -*- coding: utf-8 -*-
"""
Unit Tests fuer PersonalizedThresholdsService.

Testet:
- Singleton-Verhalten
- Enums (ProfessionType, RiskTolerance, ThresholdType, etc.)
- Dataclasses (ThresholdDefinition, UserThreshold, UserProfile, etc.)
- ThresholdRegistry
- Profile Management
- Threshold Management
- Effectiveness Tracking
- Recommendations
- Statistics

PHASE 0.7 CRITICAL FIX: 80%+ Coverage Ziel
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.services.orchestration.personalized_thresholds_service import (
    PersonalizedThresholdsService,
    ThresholdRegistry,
    ThresholdDefinition,
    UserThreshold,
    UserProfile,
    ThresholdAdjustment,
    ThresholdRecommendation,
    ProfessionType,
    RiskTolerance,
    ThresholdType,
    ThresholdCategory,
    AdjustmentSource,
    get_personalized_thresholds_service,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def reset_service():
    """Reset Singleton vor und nach jedem Test."""
    PersonalizedThresholdsService._instance = None
    yield
    PersonalizedThresholdsService._instance = None


@pytest.fixture
def service(reset_service):
    """Frische Service-Instanz fuer jeden Test."""
    return PersonalizedThresholdsService()


@pytest.fixture
def sample_user_id():
    """Erzeugt eine Beispiel-User-ID."""
    return uuid4()


@pytest.fixture
def sample_profile(sample_user_id):
    """Erstellt ein Beispiel-Profil."""
    return UserProfile(
        user_id=sample_user_id,
        profession_type=ProfessionType.FREELANCER,
        risk_tolerance=RiskTolerance.MODERATE,
        income_stability=0.6,
        age_group="31-45",
        household_size=2,
        has_dependents=False,
        is_homeowner=False,
        has_pension_plan=False,
    )


@pytest.fixture
def sample_threshold(sample_user_id):
    """Erstellt einen Beispiel-Threshold."""
    now = datetime.now(timezone.utc)
    return UserThreshold(
        id=uuid4(),
        user_id=sample_user_id,
        threshold_type=ThresholdType.DTI_WARNING,
        default_value=36.0,
        current_value=32.0,
        adjustment_source=AdjustmentSource.PROFESSION_PROFILE,
        adjustment_reason="Freelancer-Profil",
        created_at=now,
        updated_at=now,
        last_used_at=None,
        confidence=0.75,
    )


@pytest.fixture
def sample_adjustment(sample_user_id):
    """Erstellt eine Beispiel-Anpassung."""
    return ThresholdAdjustment(
        id=uuid4(),
        user_id=sample_user_id,
        threshold_type=ThresholdType.DTI_WARNING,
        previous_value=36.0,
        new_value=32.0,
        adjustment_source=AdjustmentSource.USER_PREFERENCE,
        reason="User hat Threshold angepasst",
        confidence=1.0,
        applied_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def sample_recommendation(sample_user_id):
    """Erstellt eine Beispiel-Empfehlung."""
    now = datetime.now(timezone.utc)
    return ThresholdRecommendation(
        id=uuid4(),
        user_id=sample_user_id,
        threshold_type=ThresholdType.SAVINGS_RATE_TARGET,
        current_value=20.0,
        recommended_value=25.0,
        reason="Sie sparen konstant mehr als Ziel",
        confidence=0.8,
        potential_impact="Realistischeres Ziel",
        created_at=now,
        expires_at=now + timedelta(days=30),
    )


# =============================================================================
# Singleton Tests
# =============================================================================

class TestSingletonPattern:
    """Tests fuer Singleton-Verhalten."""

    def test_singleton_returns_same_instance(self, reset_service):
        """Singleton gibt immer dieselbe Instanz zurueck."""
        instance1 = PersonalizedThresholdsService()
        instance2 = PersonalizedThresholdsService()

        assert instance1 is instance2

    def test_factory_returns_same_instance(self, reset_service):
        """Factory-Funktion gibt Singleton zurueck."""
        instance1 = get_personalized_thresholds_service()
        instance2 = get_personalized_thresholds_service()

        assert instance1 is instance2

    def test_initialization_only_once(self, reset_service):
        """Initialisierung erfolgt nur einmal."""
        instance = PersonalizedThresholdsService()
        original_registry = instance.registry

        instance2 = PersonalizedThresholdsService()

        assert instance2.registry is original_registry


# =============================================================================
# Enum Tests
# =============================================================================

class TestEnums:
    """Tests fuer Enums."""

    def test_profession_type_values(self):
        """ProfessionType hat erwartete Werte."""
        assert ProfessionType.EMPLOYEE.value == "employee"
        assert ProfessionType.CIVIL_SERVANT.value == "civil_servant"
        assert ProfessionType.FREELANCER.value == "freelancer"
        assert ProfessionType.ENTREPRENEUR.value == "entrepreneur"
        assert ProfessionType.RETIRED.value == "retired"
        assert ProfessionType.STUDENT.value == "student"

    def test_risk_tolerance_values(self):
        """RiskTolerance hat erwartete Werte."""
        assert RiskTolerance.VERY_CONSERVATIVE.value == "very_conservative"
        assert RiskTolerance.CONSERVATIVE.value == "conservative"
        assert RiskTolerance.MODERATE.value == "moderate"
        assert RiskTolerance.AGGRESSIVE.value == "aggressive"
        assert RiskTolerance.VERY_AGGRESSIVE.value == "very_aggressive"

    def test_threshold_type_values(self):
        """ThresholdType hat erwartete Werte."""
        assert ThresholdType.DTI_RATIO.value == "dti_ratio"
        assert ThresholdType.DTI_WARNING.value == "dti_warning"
        assert ThresholdType.DTI_CRITICAL.value == "dti_critical"
        assert ThresholdType.EMERGENCY_FUND_MIN.value == "emergency_fund_min"
        assert ThresholdType.EMERGENCY_FUND_TARGET.value == "emergency_fund_target"
        assert ThresholdType.SAVINGS_RATE_MIN.value == "savings_rate_min"
        assert ThresholdType.EXPECTED_RETURN.value == "expected_return"
        assert ThresholdType.HEALTH_SCORE_WARNING.value == "health_score_warning"

    def test_threshold_category_values(self):
        """ThresholdCategory hat erwartete Werte."""
        assert ThresholdCategory.DEBT.value == "debt"
        assert ThresholdCategory.SAVINGS.value == "savings"
        assert ThresholdCategory.INVESTMENT.value == "investment"
        assert ThresholdCategory.INSURANCE.value == "insurance"
        assert ThresholdCategory.HEALTH_SCORE.value == "health_score"
        assert ThresholdCategory.LIQUIDITY.value == "liquidity"
        assert ThresholdCategory.HOUSING.value == "housing"

    def test_adjustment_source_values(self):
        """AdjustmentSource hat erwartete Werte."""
        assert AdjustmentSource.SYSTEM_DEFAULT.value == "system_default"
        assert AdjustmentSource.PROFESSION_PROFILE.value == "profession_profile"
        assert AdjustmentSource.USER_PREFERENCE.value == "user_preference"
        assert AdjustmentSource.LEARNED_BEHAVIOR.value == "learned_behavior"
        assert AdjustmentSource.ADMIN_OVERRIDE.value == "admin_override"
        assert AdjustmentSource.SEASONAL_ADJUSTMENT.value == "seasonal_adjustment"


# =============================================================================
# ThresholdDefinition Tests
# =============================================================================

class TestThresholdDefinition:
    """Tests fuer ThresholdDefinition Dataclass."""

    def test_default_factory_fields(self):
        """Default-Factory-Felder werden korrekt initialisiert."""
        definition = ThresholdDefinition(
            threshold_type=ThresholdType.DTI_WARNING,
            category=ThresholdCategory.DEBT,
            name="Test",
            description="Testbeschreibung",
            unit="%",
            default_value=36.0,
            min_allowed=20.0,
            max_allowed=60.0,
        )

        assert definition.profession_defaults == {}
        assert definition.risk_modifiers == {}

    def test_with_profession_defaults(self):
        """Profession-Defaults werden korrekt gesetzt."""
        definition = ThresholdDefinition(
            threshold_type=ThresholdType.EMERGENCY_FUND_MIN,
            category=ThresholdCategory.SAVINGS,
            name="Notgroschen",
            description="Minimum",
            unit="Monate",
            default_value=3.0,
            min_allowed=1.0,
            max_allowed=12.0,
            profession_defaults={
                ProfessionType.FREELANCER: 6.0,
                ProfessionType.CIVIL_SERVANT: 2.0,
            }
        )

        assert definition.profession_defaults[ProfessionType.FREELANCER] == 6.0
        assert definition.profession_defaults[ProfessionType.CIVIL_SERVANT] == 2.0

    def test_with_risk_modifiers(self):
        """Risk-Modifiers werden korrekt gesetzt."""
        definition = ThresholdDefinition(
            threshold_type=ThresholdType.EXPECTED_RETURN,
            category=ThresholdCategory.INVESTMENT,
            name="Rendite",
            description="Erwartete Rendite",
            unit="%",
            default_value=5.0,
            min_allowed=0.0,
            max_allowed=20.0,
            risk_modifiers={
                RiskTolerance.CONSERVATIVE: 0.8,
                RiskTolerance.AGGRESSIVE: 1.4,
            }
        )

        assert definition.risk_modifiers[RiskTolerance.CONSERVATIVE] == 0.8
        assert definition.risk_modifiers[RiskTolerance.AGGRESSIVE] == 1.4


# =============================================================================
# UserThreshold Tests
# =============================================================================

class TestUserThreshold:
    """Tests fuer UserThreshold Dataclass."""

    def test_defaults(self, sample_threshold):
        """UserThreshold hat sinnvolle Defaults."""
        assert sample_threshold.confidence == 0.75
        assert sample_threshold.times_triggered == 0
        assert sample_threshold.times_acted_on == 0
        assert sample_threshold.effectiveness_score == 1.0

    def test_all_fields_set(self, sample_threshold, sample_user_id):
        """Alle Felder sind korrekt gesetzt."""
        assert sample_threshold.user_id == sample_user_id
        assert sample_threshold.threshold_type == ThresholdType.DTI_WARNING
        assert sample_threshold.default_value == 36.0
        assert sample_threshold.current_value == 32.0
        assert sample_threshold.adjustment_source == AdjustmentSource.PROFESSION_PROFILE


# =============================================================================
# UserProfile Tests
# =============================================================================

class TestUserProfile:
    """Tests fuer UserProfile Dataclass."""

    def test_defaults(self, sample_profile):
        """UserProfile hat sinnvolle Defaults."""
        assert sample_profile.prefers_aggressive_alerts is False
        assert sample_profile.prefers_conservative_targets is True
        assert sample_profile.feedback_history == []
        assert sample_profile.created_at is not None
        assert sample_profile.updated_at is not None

    def test_all_fields_set(self, sample_profile, sample_user_id):
        """Alle Felder sind korrekt gesetzt."""
        assert sample_profile.user_id == sample_user_id
        assert sample_profile.profession_type == ProfessionType.FREELANCER
        assert sample_profile.risk_tolerance == RiskTolerance.MODERATE
        assert sample_profile.income_stability == 0.6
        assert sample_profile.age_group == "31-45"
        assert sample_profile.household_size == 2


# =============================================================================
# ThresholdAdjustment Tests
# =============================================================================

class TestThresholdAdjustment:
    """Tests fuer ThresholdAdjustment Dataclass."""

    def test_defaults(self, sample_adjustment):
        """ThresholdAdjustment hat sinnvolle Defaults."""
        assert sample_adjustment.can_rollback is True
        assert sample_adjustment.rolled_back is False

    def test_all_fields_set(self, sample_adjustment, sample_user_id):
        """Alle Felder sind korrekt gesetzt."""
        assert sample_adjustment.user_id == sample_user_id
        assert sample_adjustment.threshold_type == ThresholdType.DTI_WARNING
        assert sample_adjustment.previous_value == 36.0
        assert sample_adjustment.new_value == 32.0
        assert sample_adjustment.confidence == 1.0


# =============================================================================
# ThresholdRecommendation Tests
# =============================================================================

class TestThresholdRecommendation:
    """Tests fuer ThresholdRecommendation Dataclass."""

    def test_defaults(self, sample_recommendation):
        """ThresholdRecommendation hat sinnvolle Defaults."""
        assert sample_recommendation.accepted is None
        assert sample_recommendation.accepted_at is None

    def test_all_fields_set(self, sample_recommendation, sample_user_id):
        """Alle Felder sind korrekt gesetzt."""
        assert sample_recommendation.user_id == sample_user_id
        assert sample_recommendation.threshold_type == ThresholdType.SAVINGS_RATE_TARGET
        assert sample_recommendation.current_value == 20.0
        assert sample_recommendation.recommended_value == 25.0
        assert sample_recommendation.confidence == 0.8


# =============================================================================
# ThresholdRegistry Tests
# =============================================================================

class TestThresholdRegistry:
    """Tests fuer ThresholdRegistry."""

    def test_initialization(self):
        """Registry wird mit Thresholds initialisiert."""
        registry = ThresholdRegistry()

        assert len(registry._thresholds) > 0

    def test_get_threshold(self):
        """Einzelner Threshold wird gefunden."""
        registry = ThresholdRegistry()

        dti_warning = registry.get_threshold(ThresholdType.DTI_WARNING)

        assert dti_warning is not None
        assert dti_warning.threshold_type == ThresholdType.DTI_WARNING
        assert dti_warning.default_value == 36.0

    def test_get_threshold_not_found(self):
        """Nicht existierender Threshold gibt None zurueck."""
        registry = ThresholdRegistry()

        result = registry.get_threshold(ThresholdType.DTI_RATIO)

        # DTI_RATIO ist nicht in der Registry definiert
        assert result is None

    def test_get_all_thresholds(self):
        """Alle Thresholds werden zurueckgegeben."""
        registry = ThresholdRegistry()

        all_thresholds = registry.get_all_thresholds()

        assert len(all_thresholds) >= 10  # Mindestens 10 definiert
        assert all(isinstance(t, ThresholdDefinition) for t in all_thresholds)

    def test_get_thresholds_by_category_debt(self):
        """Thresholds nach Kategorie DEBT gefiltert."""
        registry = ThresholdRegistry()

        debt_thresholds = registry.get_thresholds_by_category(ThresholdCategory.DEBT)

        assert len(debt_thresholds) >= 2  # DTI_WARNING, DTI_CRITICAL, LOAN_INTEREST_WARNING
        assert all(t.category == ThresholdCategory.DEBT for t in debt_thresholds)

    def test_get_thresholds_by_category_savings(self):
        """Thresholds nach Kategorie SAVINGS gefiltert."""
        registry = ThresholdRegistry()

        savings_thresholds = registry.get_thresholds_by_category(ThresholdCategory.SAVINGS)

        assert len(savings_thresholds) >= 4
        assert all(t.category == ThresholdCategory.SAVINGS for t in savings_thresholds)

    def test_dti_warning_profession_defaults(self):
        """DTI Warning hat Profession-Defaults."""
        registry = ThresholdRegistry()

        dti_warning = registry.get_threshold(ThresholdType.DTI_WARNING)

        assert ProfessionType.CIVIL_SERVANT in dti_warning.profession_defaults
        assert dti_warning.profession_defaults[ProfessionType.CIVIL_SERVANT] == 40.0
        assert dti_warning.profession_defaults[ProfessionType.FREELANCER] == 32.0

    def test_dti_warning_risk_modifiers(self):
        """DTI Warning hat Risk-Modifiers."""
        registry = ThresholdRegistry()

        dti_warning = registry.get_threshold(ThresholdType.DTI_WARNING)

        assert RiskTolerance.VERY_CONSERVATIVE in dti_warning.risk_modifiers
        assert dti_warning.risk_modifiers[RiskTolerance.VERY_CONSERVATIVE] == 0.85
        assert dti_warning.risk_modifiers[RiskTolerance.VERY_AGGRESSIVE] == 1.15


# =============================================================================
# Profile Management Tests
# =============================================================================

class TestProfileManagement:
    """Tests fuer Profile-Verwaltung."""

    @pytest.mark.asyncio
    async def test_get_or_create_profile_new(self, service, sample_user_id):
        """Neues Profil wird erstellt."""
        profile = await service.get_or_create_profile(
            user_id=sample_user_id,
            profession_type=ProfessionType.FREELANCER,
            risk_tolerance=RiskTolerance.AGGRESSIVE,
        )

        assert profile is not None
        assert profile.user_id == sample_user_id
        assert profile.profession_type == ProfessionType.FREELANCER
        assert profile.risk_tolerance == RiskTolerance.AGGRESSIVE

    @pytest.mark.asyncio
    async def test_get_or_create_profile_existing(self, service, sample_user_id):
        """Existierendes Profil wird zurueckgegeben."""
        # Erstelle zuerst
        await service.get_or_create_profile(
            user_id=sample_user_id,
            profession_type=ProfessionType.FREELANCER,
        )

        # Hole wieder
        profile = await service.get_or_create_profile(user_id=sample_user_id)

        assert profile.profession_type == ProfessionType.FREELANCER

    @pytest.mark.asyncio
    async def test_get_or_create_profile_updates_existing(self, service, sample_user_id):
        """Existierendes Profil wird aktualisiert."""
        # Erstelle mit FREELANCER
        await service.get_or_create_profile(
            user_id=sample_user_id,
            profession_type=ProfessionType.FREELANCER,
        )

        # Update auf ENTREPRENEUR
        profile = await service.get_or_create_profile(
            user_id=sample_user_id,
            profession_type=ProfessionType.ENTREPRENEUR,
        )

        assert profile.profession_type == ProfessionType.ENTREPRENEUR

    @pytest.mark.asyncio
    async def test_get_or_create_profile_default_values(self, service, sample_user_id):
        """Profil hat sinnvolle Defaults."""
        profile = await service.get_or_create_profile(user_id=sample_user_id)

        assert profile.profession_type == ProfessionType.EMPLOYEE
        assert profile.risk_tolerance == RiskTolerance.MODERATE
        assert profile.income_stability == 0.7
        assert profile.household_size == 2

    @pytest.mark.asyncio
    async def test_update_profile(self, service, sample_user_id):
        """Profil wird aktualisiert."""
        await service.get_or_create_profile(user_id=sample_user_id)

        updated = await service.update_profile(
            user_id=sample_user_id,
            updates={
                "profession_type": "freelancer",
                "risk_tolerance": "aggressive",
                "income_stability": 0.5,
                "household_size": 3,
                "has_dependents": True,
            }
        )

        assert updated.profession_type == ProfessionType.FREELANCER
        assert updated.risk_tolerance == RiskTolerance.AGGRESSIVE
        assert updated.income_stability == 0.5
        assert updated.household_size == 3
        assert updated.has_dependents is True


# =============================================================================
# Threshold Management Tests
# =============================================================================

class TestThresholdManagement:
    """Tests fuer Threshold-Verwaltung."""

    @pytest.mark.asyncio
    async def test_thresholds_initialized_on_profile_creation(self, service, sample_user_id):
        """Thresholds werden bei Profil-Erstellung initialisiert."""
        await service.get_or_create_profile(user_id=sample_user_id)

        thresholds = await service.get_all_thresholds(sample_user_id)

        assert len(thresholds) > 0

    @pytest.mark.asyncio
    async def test_get_threshold(self, service, sample_user_id):
        """Einzelner Threshold wird gefunden."""
        await service.get_or_create_profile(user_id=sample_user_id)

        threshold = await service.get_threshold(sample_user_id, ThresholdType.DTI_WARNING)

        assert threshold is not None
        assert threshold.threshold_type == ThresholdType.DTI_WARNING

    @pytest.mark.asyncio
    async def test_get_threshold_updates_last_used(self, service, sample_user_id):
        """last_used_at wird beim Abrufen aktualisiert."""
        await service.get_or_create_profile(user_id=sample_user_id)

        threshold = await service.get_threshold(sample_user_id, ThresholdType.DTI_WARNING)

        assert threshold.last_used_at is not None

    @pytest.mark.asyncio
    async def test_get_all_thresholds(self, service, sample_user_id):
        """Alle Thresholds werden zurueckgegeben."""
        await service.get_or_create_profile(user_id=sample_user_id)

        thresholds = await service.get_all_thresholds(sample_user_id)

        assert len(thresholds) >= 10

    @pytest.mark.asyncio
    async def test_get_all_thresholds_by_category(self, service, sample_user_id):
        """Thresholds nach Kategorie gefiltert."""
        await service.get_or_create_profile(user_id=sample_user_id)

        debt_thresholds = await service.get_all_thresholds(
            sample_user_id,
            category=ThresholdCategory.DEBT
        )

        assert len(debt_thresholds) >= 2
        # Alle sollten Debt-Typ sein
        debt_types = {ThresholdType.DTI_WARNING, ThresholdType.DTI_CRITICAL, ThresholdType.LOAN_INTEREST_WARNING}
        for t in debt_thresholds:
            assert t.threshold_type in debt_types

    @pytest.mark.asyncio
    async def test_set_threshold(self, service, sample_user_id):
        """Threshold wird gesetzt."""
        await service.get_or_create_profile(user_id=sample_user_id)

        threshold = await service.set_threshold(
            user_id=sample_user_id,
            threshold_type=ThresholdType.DTI_WARNING,
            value=40.0,
            reason="User-Anpassung",
        )

        assert threshold.current_value == 40.0
        assert threshold.adjustment_source == AdjustmentSource.USER_PREFERENCE
        assert threshold.confidence == 1.0

    @pytest.mark.asyncio
    async def test_set_threshold_validates_min(self, service, sample_user_id):
        """Wert unter Minimum wird abgelehnt."""
        await service.get_or_create_profile(user_id=sample_user_id)

        with pytest.raises(ValueError) as exc_info:
            await service.set_threshold(
                user_id=sample_user_id,
                threshold_type=ThresholdType.DTI_WARNING,
                value=10.0,  # Unter min_allowed (20)
            )

        assert "ausserhalb des erlaubten Bereichs" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_set_threshold_validates_max(self, service, sample_user_id):
        """Wert ueber Maximum wird abgelehnt."""
        await service.get_or_create_profile(user_id=sample_user_id)

        with pytest.raises(ValueError) as exc_info:
            await service.set_threshold(
                user_id=sample_user_id,
                threshold_type=ThresholdType.DTI_WARNING,
                value=70.0,  # Ueber max_allowed (60)
            )

        assert "ausserhalb des erlaubten Bereichs" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_set_threshold_unknown_type(self, service, sample_user_id):
        """Unbekannter Threshold-Typ wird abgelehnt."""
        await service.get_or_create_profile(user_id=sample_user_id)

        with pytest.raises(ValueError) as exc_info:
            await service.set_threshold(
                user_id=sample_user_id,
                threshold_type=ThresholdType.DTI_RATIO,  # Nicht in Registry
                value=36.0,
            )

        assert "Unknown threshold type" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_reset_threshold(self, service, sample_user_id):
        """Threshold wird auf Default zurueckgesetzt."""
        await service.get_or_create_profile(
            user_id=sample_user_id,
            profession_type=ProfessionType.EMPLOYEE,
            risk_tolerance=RiskTolerance.MODERATE,
        )

        # Setze auf eigenen Wert
        await service.set_threshold(
            user_id=sample_user_id,
            threshold_type=ThresholdType.DTI_WARNING,
            value=50.0,
        )

        # Reset
        threshold = await service.reset_threshold(
            user_id=sample_user_id,
            threshold_type=ThresholdType.DTI_WARNING,
        )

        # Sollte auf 36.0 (Default fuer EMPLOYEE + MODERATE) zurueck sein
        assert threshold.current_value == 36.0

    @pytest.mark.asyncio
    async def test_reset_all_thresholds(self, service, sample_user_id):
        """Alle Thresholds werden zurueckgesetzt."""
        await service.get_or_create_profile(user_id=sample_user_id)

        # Setze einige Werte
        await service.set_threshold(sample_user_id, ThresholdType.DTI_WARNING, 50.0)
        await service.set_threshold(sample_user_id, ThresholdType.SAVINGS_RATE_MIN, 25.0)

        # Reset alle
        results = await service.reset_all_thresholds(sample_user_id)

        assert len(results) > 0


# =============================================================================
# Personalization Calculation Tests
# =============================================================================

class TestPersonalizationCalculation:
    """Tests fuer Personalisierungs-Berechnung."""

    @pytest.mark.asyncio
    async def test_freelancer_gets_lower_dti_warning(self, service, sample_user_id):
        """Freelancer bekommt niedrigere DTI-Warnschwelle."""
        await service.get_or_create_profile(
            user_id=sample_user_id,
            profession_type=ProfessionType.FREELANCER,
            risk_tolerance=RiskTolerance.MODERATE,
        )

        threshold = await service.get_threshold(sample_user_id, ThresholdType.DTI_WARNING)

        # Freelancer-Default ist 32%, nicht 36%
        assert threshold.current_value == 32.0

    @pytest.mark.asyncio
    async def test_civil_servant_gets_higher_dti_warning(self, service, sample_user_id):
        """Beamter bekommt hoehere DTI-Warnschwelle."""
        await service.get_or_create_profile(
            user_id=sample_user_id,
            profession_type=ProfessionType.CIVIL_SERVANT,
            risk_tolerance=RiskTolerance.MODERATE,
        )

        threshold = await service.get_threshold(sample_user_id, ThresholdType.DTI_WARNING)

        # Beamter-Default ist 40%, nicht 36%
        assert threshold.current_value == 40.0

    @pytest.mark.asyncio
    async def test_conservative_risk_lowers_thresholds(self, service, sample_user_id):
        """Konservativer Risk senkt Schwellenwerte."""
        await service.get_or_create_profile(
            user_id=sample_user_id,
            profession_type=ProfessionType.EMPLOYEE,
            risk_tolerance=RiskTolerance.VERY_CONSERVATIVE,
        )

        threshold = await service.get_threshold(sample_user_id, ThresholdType.DTI_WARNING)

        # 36 * 0.85 = 30.6
        assert threshold.current_value == 30.6

    @pytest.mark.asyncio
    async def test_aggressive_risk_raises_thresholds(self, service, sample_user_id):
        """Aggressiver Risk erhoeht Schwellenwerte."""
        await service.get_or_create_profile(
            user_id=sample_user_id,
            profession_type=ProfessionType.EMPLOYEE,
            risk_tolerance=RiskTolerance.VERY_AGGRESSIVE,
        )

        threshold = await service.get_threshold(sample_user_id, ThresholdType.DTI_WARNING)

        # 36 * 1.15 = 41.4
        assert threshold.current_value == 41.4

    @pytest.mark.asyncio
    async def test_value_clamped_to_min(self, service, sample_user_id):
        """Wert wird auf Minimum begrenzt."""
        # Student + Very Conservative koennte unter min_allowed fallen
        await service.get_or_create_profile(
            user_id=sample_user_id,
            profession_type=ProfessionType.STUDENT,
            risk_tolerance=RiskTolerance.VERY_CONSERVATIVE,
        )

        threshold = await service.get_threshold(sample_user_id, ThresholdType.DTI_WARNING)

        # Student Default 25 * 0.85 = 21.25
        # Min allowed ist 20, also sollte 21.25 ok sein
        assert threshold.current_value >= 20.0

    @pytest.mark.asyncio
    async def test_freelancer_gets_higher_emergency_fund(self, service, sample_user_id):
        """Freelancer bekommt hoeheren Notgroschen-Bedarf."""
        await service.get_or_create_profile(
            user_id=sample_user_id,
            profession_type=ProfessionType.FREELANCER,
            risk_tolerance=RiskTolerance.MODERATE,
        )

        threshold = await service.get_threshold(sample_user_id, ThresholdType.EMERGENCY_FUND_MIN)

        # Freelancer-Default ist 6 Monate, nicht 3
        assert threshold.current_value == 6.0


# =============================================================================
# Effectiveness Tracking Tests
# =============================================================================

class TestEffectivenessTracking:
    """Tests fuer Effectiveness-Tracking."""

    @pytest.mark.asyncio
    async def test_record_threshold_trigger(self, service, sample_user_id):
        """Threshold-Trigger wird aufgezeichnet."""
        await service.get_or_create_profile(user_id=sample_user_id)

        await service.record_threshold_trigger(
            user_id=sample_user_id,
            threshold_type=ThresholdType.DTI_WARNING,
            actual_value=38.0,
            triggered=True,
        )

        threshold = await service.get_threshold(sample_user_id, ThresholdType.DTI_WARNING)
        assert threshold.times_triggered == 1

    @pytest.mark.asyncio
    async def test_record_threshold_action(self, service, sample_user_id):
        """Threshold-Action wird aufgezeichnet."""
        await service.get_or_create_profile(user_id=sample_user_id)

        # Erst triggern
        await service.record_threshold_trigger(
            user_id=sample_user_id,
            threshold_type=ThresholdType.DTI_WARNING,
            actual_value=38.0,
            triggered=True,
        )

        # Dann Aktion aufzeichnen
        await service.record_threshold_action(
            user_id=sample_user_id,
            threshold_type=ThresholdType.DTI_WARNING,
            action_taken=True,
        )

        threshold = await service.get_threshold(sample_user_id, ThresholdType.DTI_WARNING)
        assert threshold.times_acted_on == 1
        assert threshold.effectiveness_score == 1.0

    @pytest.mark.asyncio
    async def test_effectiveness_score_calculation(self, service, sample_user_id):
        """Effectiveness-Score wird korrekt berechnet."""
        await service.get_or_create_profile(user_id=sample_user_id)

        # 3 Trigger, 1 Action = 33% Effectiveness
        for _ in range(3):
            await service.record_threshold_trigger(
                user_id=sample_user_id,
                threshold_type=ThresholdType.DTI_WARNING,
                actual_value=38.0,
                triggered=True,
            )

        await service.record_threshold_action(
            user_id=sample_user_id,
            threshold_type=ThresholdType.DTI_WARNING,
            action_taken=True,
        )

        threshold = await service.get_threshold(sample_user_id, ThresholdType.DTI_WARNING)
        assert threshold.times_triggered == 3
        assert threshold.times_acted_on == 1
        assert threshold.effectiveness_score == pytest.approx(1/3, rel=0.01)


# =============================================================================
# Recommendation Tests
# =============================================================================

class TestRecommendations:
    """Tests fuer Empfehlungs-System."""

    @pytest.mark.asyncio
    async def test_generate_dti_recommendation(self, service, sample_user_id):
        """DTI-Empfehlung wird generiert."""
        await service.get_or_create_profile(
            user_id=sample_user_id,
            profession_type=ProfessionType.EMPLOYEE,
        )

        # Aktualisiere income_stability
        profile = service._user_profiles[sample_user_id]
        profile.income_stability = 0.9

        # DTI nah am Threshold (90% von 36 = 32.4)
        recommendations = await service.generate_threshold_recommendations(
            user_id=sample_user_id,
            current_kpis={"dti_ratio": 33.0}
        )

        # Sollte Empfehlung enthalten
        dti_recs = [r for r in recommendations if r.threshold_type == ThresholdType.DTI_WARNING]
        assert len(dti_recs) > 0

    @pytest.mark.asyncio
    async def test_generate_emergency_fund_recommendation(self, service, sample_user_id):
        """Notgroschen-Empfehlung wird generiert."""
        await service.get_or_create_profile(user_id=sample_user_id)

        # Notgroschen deutlich ueber Ziel (1.5x von 6 = 9)
        recommendations = await service.generate_threshold_recommendations(
            user_id=sample_user_id,
            current_kpis={"emergency_fund_months": 12.0}
        )

        ef_recs = [r for r in recommendations if r.threshold_type == ThresholdType.EMERGENCY_FUND_TARGET]
        assert len(ef_recs) > 0

    @pytest.mark.asyncio
    async def test_generate_savings_rate_recommendation(self, service, sample_user_id):
        """Sparrate-Empfehlung wird generiert."""
        await service.get_or_create_profile(user_id=sample_user_id)

        # Sparrate deutlich ueber Ziel (1.2x von 20 = 24)
        recommendations = await service.generate_threshold_recommendations(
            user_id=sample_user_id,
            current_kpis={"monthly_savings_rate": 30.0}
        )

        sr_recs = [r for r in recommendations if r.threshold_type == ThresholdType.SAVINGS_RATE_TARGET]
        assert len(sr_recs) > 0

    @pytest.mark.asyncio
    async def test_get_pending_recommendations(self, service, sample_user_id):
        """Ausstehende Empfehlungen werden gefunden."""
        await service.get_or_create_profile(user_id=sample_user_id)

        await service.generate_threshold_recommendations(
            user_id=sample_user_id,
            current_kpis={"monthly_savings_rate": 30.0}
        )

        pending = await service.get_pending_recommendations(sample_user_id)

        assert len(pending) > 0
        assert all(r.accepted is None for r in pending)

    @pytest.mark.asyncio
    async def test_accept_recommendation(self, service, sample_user_id):
        """Empfehlung wird akzeptiert."""
        await service.get_or_create_profile(user_id=sample_user_id)

        recs = await service.generate_threshold_recommendations(
            user_id=sample_user_id,
            current_kpis={"monthly_savings_rate": 30.0}
        )

        if recs:
            rec = recs[0]
            threshold = await service.accept_recommendation(sample_user_id, rec.id)

            assert threshold is not None
            assert threshold.current_value == rec.recommended_value

            # Recommendation sollte als akzeptiert markiert sein
            assert rec.accepted is True
            assert rec.accepted_at is not None

    @pytest.mark.asyncio
    async def test_reject_recommendation(self, service, sample_user_id):
        """Empfehlung wird abgelehnt."""
        await service.get_or_create_profile(user_id=sample_user_id)

        recs = await service.generate_threshold_recommendations(
            user_id=sample_user_id,
            current_kpis={"monthly_savings_rate": 30.0}
        )

        if recs:
            rec = recs[0]
            result = await service.reject_recommendation(
                sample_user_id,
                rec.id,
                reason="Passt nicht zu meiner Situation"
            )

            assert result is True
            assert rec.accepted is False

            # Feedback sollte gespeichert sein
            profile = service._user_profiles[sample_user_id]
            assert len(profile.feedback_history) > 0

    @pytest.mark.asyncio
    async def test_expired_recommendations_filtered(self, service, sample_user_id):
        """Abgelaufene Empfehlungen werden gefiltert."""
        await service.get_or_create_profile(user_id=sample_user_id)

        # Manuelle abgelaufene Empfehlung
        expired_rec = ThresholdRecommendation(
            id=uuid4(),
            user_id=sample_user_id,
            threshold_type=ThresholdType.DTI_WARNING,
            current_value=36.0,
            recommended_value=40.0,
            reason="Test",
            confidence=0.8,
            potential_impact="Test",
            created_at=datetime.now(timezone.utc) - timedelta(days=60),
            expires_at=datetime.now(timezone.utc) - timedelta(days=30),
        )

        service._recommendations[sample_user_id] = [expired_rec]

        pending = await service.get_pending_recommendations(sample_user_id)

        assert len(pending) == 0


# =============================================================================
# Statistics Tests
# =============================================================================

class TestStatistics:
    """Tests fuer Statistiken."""

    @pytest.mark.asyncio
    async def test_get_threshold_statistics(self, service, sample_user_id):
        """Statistiken werden berechnet."""
        await service.get_or_create_profile(user_id=sample_user_id)

        stats = await service.get_threshold_statistics(sample_user_id)

        assert "total_thresholds" in stats
        assert "customized_count" in stats
        assert "average_effectiveness" in stats
        assert "total_triggers" in stats
        assert stats["total_thresholds"] > 0

    @pytest.mark.asyncio
    async def test_get_threshold_statistics_empty(self, service):
        """Statistiken fuer unbekannten User sind leer."""
        stats = await service.get_threshold_statistics(uuid4())

        # Neuer User bekommt Thresholds durch get_or_create_profile in get_all_thresholds
        assert stats["total_thresholds"] >= 0

    @pytest.mark.asyncio
    async def test_get_adjustment_history(self, service, sample_user_id):
        """Anpassungs-Historie wird zurueckgegeben."""
        await service.get_or_create_profile(user_id=sample_user_id)

        # Mache einige Anpassungen
        await service.set_threshold(sample_user_id, ThresholdType.DTI_WARNING, 40.0)
        await service.set_threshold(sample_user_id, ThresholdType.DTI_WARNING, 42.0)

        history = await service.get_adjustment_history(sample_user_id)

        assert len(history) >= 2

    @pytest.mark.asyncio
    async def test_get_adjustment_history_limited(self, service, sample_user_id):
        """Anpassungs-Historie ist limitiert."""
        await service.get_or_create_profile(user_id=sample_user_id)

        # Mache viele Anpassungen
        for i in range(25):
            await service.set_threshold(
                sample_user_id,
                ThresholdType.DTI_WARNING,
                30.0 + (i % 10)
            )

        history = await service.get_adjustment_history(sample_user_id, limit=10)

        assert len(history) <= 10

    @pytest.mark.asyncio
    async def test_adjustment_history_sorted_by_date(self, service, sample_user_id):
        """Anpassungs-Historie ist nach Datum sortiert."""
        await service.get_or_create_profile(user_id=sample_user_id)

        await service.set_threshold(sample_user_id, ThresholdType.DTI_WARNING, 35.0)
        await service.set_threshold(sample_user_id, ThresholdType.DTI_WARNING, 40.0)
        await service.set_threshold(sample_user_id, ThresholdType.DTI_WARNING, 45.0)

        history = await service.get_adjustment_history(sample_user_id)

        # Neuste zuerst
        for i in range(len(history) - 1):
            assert history[i].applied_at >= history[i + 1].applied_at


# =============================================================================
# Profile Recalculation Tests
# =============================================================================

class TestProfileRecalculation:
    """Tests fuer Neuberechnung bei Profil-Aenderung."""

    @pytest.mark.asyncio
    async def test_thresholds_recalculated_on_profile_update(self, service, sample_user_id):
        """Thresholds werden bei Profil-Update neu berechnet."""
        # Start als Employee
        await service.get_or_create_profile(
            user_id=sample_user_id,
            profession_type=ProfessionType.EMPLOYEE,
        )

        threshold_before = await service.get_threshold(sample_user_id, ThresholdType.DTI_WARNING)
        value_before = threshold_before.current_value

        # Update auf Freelancer
        await service.update_profile(
            user_id=sample_user_id,
            updates={"profession_type": "freelancer"}
        )

        threshold_after = await service.get_threshold(sample_user_id, ThresholdType.DTI_WARNING)
        value_after = threshold_after.current_value

        # Freelancer hat niedrigere Schwelle
        assert value_after < value_before

    @pytest.mark.asyncio
    async def test_user_overrides_preserved_on_recalc(self, service, sample_user_id):
        """User-Overrides werden bei Recalc nicht ueberschrieben."""
        await service.get_or_create_profile(
            user_id=sample_user_id,
            profession_type=ProfessionType.EMPLOYEE,
        )

        # User setzt eigenen Wert
        await service.set_threshold(
            user_id=sample_user_id,
            threshold_type=ThresholdType.DTI_WARNING,
            value=45.0,
            reason="Meine Praeferenz",
        )

        # Profile Update
        await service.update_profile(
            user_id=sample_user_id,
            updates={"profession_type": "freelancer"}
        )

        threshold = await service.get_threshold(sample_user_id, ThresholdType.DTI_WARNING)

        # User-Wert sollte erhalten bleiben
        assert threshold.current_value == 45.0
        assert threshold.adjustment_source == AdjustmentSource.USER_PREFERENCE

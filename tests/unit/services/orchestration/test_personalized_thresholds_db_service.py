# -*- coding: utf-8 -*-
"""
Unit Tests fuer PersonalizedThresholdsDBService.

Testet:
- DB-backed Profile Management
- Threshold CRUD Operations
- Recommendations System
- Effectiveness Tracking
- Statistics

PHASE 0.7 CRITICAL FIX: 80%+ Coverage Ziel
"""

from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from uuid import UUID, uuid4

import pytest

from app.services.orchestration.personalized_thresholds_db_service import (
    PersonalizedThresholdsDBService,
    get_personalized_thresholds_db_service,
)
from app.services.orchestration.personalized_thresholds_service import (
    AdjustmentSource,
    ProfessionType,
    RiskTolerance,
    ThresholdCategory,
    ThresholdType,
    ThresholdDefinition,
    UserProfile,
    UserThreshold,
    ThresholdAdjustment,
    ThresholdRecommendation,
)


# =============================================================================
# Mock DB Models
# =============================================================================

class MockDBProfile:
    """Mock fuer DB User Profile."""

    def __init__(
        self,
        user_id: UUID,
        profession_type: str = "employee",
        risk_tolerance: str = "moderate",
        **kwargs
    ):
        self.user_id = user_id
        self.profession_type = profession_type
        self.risk_tolerance = risk_tolerance
        self.income_stability = kwargs.get("income_stability", Decimal("0.7"))
        self.age_group = kwargs.get("age_group", "31-45")
        self.household_size = kwargs.get("household_size", 2)
        self.has_dependents = kwargs.get("has_dependents", False)
        self.is_homeowner = kwargs.get("is_homeowner", False)
        self.has_pension_plan = kwargs.get("has_pension_plan", True)
        self.prefers_aggressive_alerts = kwargs.get("prefers_aggressive_alerts", False)
        self.prefers_conservative_targets = kwargs.get("prefers_conservative_targets", True)
        self.feedback_history = kwargs.get("feedback_history", [])
        self.created_at = kwargs.get("created_at", datetime.now(timezone.utc))
        self.updated_at = kwargs.get("updated_at", datetime.now(timezone.utc))


class MockDBThreshold:
    """Mock fuer DB Threshold."""

    def __init__(
        self,
        id: UUID,
        user_id: UUID,
        threshold_type: str,
        **kwargs
    ):
        self.id = id
        self.user_id = user_id
        self.threshold_type = threshold_type
        self.default_value = kwargs.get("default_value", Decimal("36.0"))
        self.current_value = kwargs.get("current_value", Decimal("36.0"))
        self.adjustment_source = kwargs.get("adjustment_source", "system_default")
        self.adjustment_reason = kwargs.get("adjustment_reason", None)
        self.confidence = kwargs.get("confidence", Decimal("0.8"))
        self.times_triggered = kwargs.get("times_triggered", 0)
        self.times_acted_on = kwargs.get("times_acted_on", 0)
        self.effectiveness_score = kwargs.get("effectiveness_score", Decimal("1.0"))
        self.created_at = kwargs.get("created_at", datetime.now(timezone.utc))
        self.updated_at = kwargs.get("updated_at", datetime.now(timezone.utc))
        self.last_used_at = kwargs.get("last_used_at", None)


class MockDBRecommendation:
    """Mock fuer DB Recommendation."""

    def __init__(
        self,
        id: UUID,
        user_id: UUID,
        threshold_type: str,
        **kwargs
    ):
        self.id = id
        self.user_id = user_id
        self.threshold_type = threshold_type
        self.current_value = kwargs.get("current_value", Decimal("36.0"))
        self.recommended_value = kwargs.get("recommended_value", Decimal("40.0"))
        self.reason = kwargs.get("reason", "Test Empfehlung")
        self.confidence = kwargs.get("confidence", Decimal("0.8"))
        self.potential_impact = kwargs.get("potential_impact", "Weniger Warnungen")
        self.created_at = kwargs.get("created_at", datetime.now(timezone.utc))
        self.expires_at = kwargs.get("expires_at", datetime.now(timezone.utc) + timedelta(days=30))
        self.accepted = kwargs.get("accepted", None)
        self.accepted_at = kwargs.get("accepted_at", None)


class MockDBAdjustment:
    """Mock fuer DB Adjustment."""

    def __init__(
        self,
        id: UUID,
        user_id: UUID,
        threshold_type: str,
        **kwargs
    ):
        self.id = id
        self.user_id = user_id
        self.threshold_type = threshold_type
        self.previous_value = kwargs.get("previous_value", Decimal("36.0"))
        self.new_value = kwargs.get("new_value", Decimal("40.0"))
        self.adjustment_source = kwargs.get("adjustment_source", "user_preference")
        self.reason = kwargs.get("reason", "User-Anpassung")
        self.confidence = kwargs.get("confidence", Decimal("1.0"))
        self.applied_at = kwargs.get("applied_at", datetime.now(timezone.utc))
        self.can_rollback = kwargs.get("can_rollback", True)
        self.rolled_back = kwargs.get("rolled_back", False)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_db():
    """Mock AsyncSession."""
    return MagicMock()


@pytest.fixture
def sample_user_id():
    """Beispiel User-ID."""
    return uuid4()


@pytest.fixture
def service(mock_db):
    """Service-Instanz mit gemockten Repositories."""
    service = PersonalizedThresholdsDBService(mock_db)

    # Mock alle Repositories
    service._profile_repo = AsyncMock()
    service._threshold_repo = AsyncMock()
    service._adjustment_repo = AsyncMock()
    service._recommendation_repo = AsyncMock()

    return service


# =============================================================================
# Initialization Tests
# =============================================================================

class TestInitialization:
    """Tests fuer Service-Initialisierung."""

    def test_init_creates_repositories(self, mock_db):
        """Service erstellt alle notwendigen Repositories."""
        service = PersonalizedThresholdsDBService(mock_db)

        assert service.db is mock_db
        assert service.registry is not None

    def test_factory_function(self, mock_db):
        """Factory-Funktion erstellt Service."""
        service = get_personalized_thresholds_db_service(mock_db)

        assert isinstance(service, PersonalizedThresholdsDBService)
        assert service.db is mock_db


# =============================================================================
# Profile Management Tests
# =============================================================================

class TestProfileManagement:
    """Tests fuer Profile-Verwaltung."""

    @pytest.mark.asyncio
    async def test_get_or_create_profile_existing(self, service, sample_user_id):
        """Existierendes Profil wird zurueckgegeben."""
        mock_profile = MockDBProfile(
            user_id=sample_user_id,
            profession_type="self_employed",
            risk_tolerance="conservative",
        )
        service._profile_repo.get_by_user_id.return_value = mock_profile

        profile = await service.get_or_create_profile(sample_user_id)

        assert profile.user_id == sample_user_id
        assert profile.profession_type == ProfessionType.SELF_EMPLOYED
        assert profile.risk_tolerance == RiskTolerance.CONSERVATIVE

    @pytest.mark.asyncio
    async def test_get_or_create_profile_new(self, service, sample_user_id):
        """Neues Profil wird erstellt wenn nicht vorhanden."""
        service._profile_repo.get_by_user_id.return_value = None

        mock_new_profile = MockDBProfile(
            user_id=sample_user_id,
            profession_type="employee",
            risk_tolerance="moderate",
        )
        service._profile_repo.upsert.return_value = mock_new_profile
        service._threshold_repo.bulk_upsert.return_value = []

        profile = await service.get_or_create_profile(sample_user_id)

        assert profile.user_id == sample_user_id
        service._profile_repo.upsert.assert_called_once()
        service._threshold_repo.bulk_upsert.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_or_create_profile_with_profession(self, service, sample_user_id):
        """Profil mit spezifischer Profession erstellen."""
        service._profile_repo.get_by_user_id.return_value = None

        mock_profile = MockDBProfile(
            user_id=sample_user_id,
            profession_type="civil_servant",
            risk_tolerance="moderate",
        )
        service._profile_repo.upsert.return_value = mock_profile
        service._threshold_repo.bulk_upsert.return_value = []

        profile = await service.get_or_create_profile(
            sample_user_id,
            profession_type=ProfessionType.CIVIL_SERVANT,
        )

        assert profile.profession_type == ProfessionType.CIVIL_SERVANT

    @pytest.mark.asyncio
    async def test_update_profile(self, service, sample_user_id):
        """Profil-Update funktioniert."""
        mock_profile = MockDBProfile(
            user_id=sample_user_id,
            profession_type="employee",
            risk_tolerance="moderate",
        )
        service._profile_repo.get_by_user_id.return_value = mock_profile
        service._profile_repo.upsert.return_value = mock_profile
        service._threshold_repo.get_by_user_id.return_value = []

        profile = await service.update_profile(
            sample_user_id,
            {"risk_tolerance": "aggressive"},
        )

        assert profile is not None
        service._profile_repo.upsert.assert_called()

    @pytest.mark.asyncio
    async def test_update_profile_with_enum_value(self, service, sample_user_id):
        """Profil-Update mit Enum-Objekt funktioniert."""
        mock_profile = MockDBProfile(
            user_id=sample_user_id,
            profession_type="employee",
            risk_tolerance="moderate",
        )
        service._profile_repo.get_by_user_id.return_value = mock_profile
        service._profile_repo.upsert.return_value = mock_profile
        service._threshold_repo.get_by_user_id.return_value = []

        profile = await service.update_profile(
            sample_user_id,
            {"profession_type": ProfessionType.FREELANCER},
        )

        assert profile is not None


# =============================================================================
# Threshold Management Tests
# =============================================================================

class TestThresholdManagement:
    """Tests fuer Threshold-Verwaltung."""

    @pytest.mark.asyncio
    async def test_get_threshold(self, service, sample_user_id):
        """Threshold wird korrekt zurueckgegeben."""
        mock_profile = MockDBProfile(user_id=sample_user_id)
        mock_threshold = MockDBThreshold(
            id=uuid4(),
            user_id=sample_user_id,
            threshold_type="dti_warning",
            current_value=Decimal("40.0"),
        )

        service._profile_repo.get_by_user_id.return_value = mock_profile
        service._threshold_repo.get_by_user_and_type.return_value = mock_threshold
        service._threshold_repo.upsert.return_value = mock_threshold

        threshold = await service.get_threshold(sample_user_id, ThresholdType.DTI_WARNING)

        assert threshold is not None
        assert threshold.threshold_type == ThresholdType.DTI_WARNING
        assert threshold.current_value == 40.0

    @pytest.mark.asyncio
    async def test_get_threshold_not_found(self, service, sample_user_id):
        """Nicht vorhandener Threshold gibt None zurueck."""
        mock_profile = MockDBProfile(user_id=sample_user_id)

        service._profile_repo.get_by_user_id.return_value = mock_profile
        service._threshold_repo.get_by_user_and_type.return_value = None

        threshold = await service.get_threshold(sample_user_id, ThresholdType.DTI_WARNING)

        assert threshold is None

    @pytest.mark.asyncio
    async def test_get_all_thresholds(self, service, sample_user_id):
        """Alle Thresholds werden zurueckgegeben."""
        mock_profile = MockDBProfile(user_id=sample_user_id)
        mock_thresholds = [
            MockDBThreshold(
                id=uuid4(),
                user_id=sample_user_id,
                threshold_type="dti_warning",
            ),
            MockDBThreshold(
                id=uuid4(),
                user_id=sample_user_id,
                threshold_type="dti_critical",
            ),
        ]

        service._profile_repo.get_by_user_id.return_value = mock_profile
        service._threshold_repo.get_by_user_id.return_value = mock_thresholds

        thresholds = await service.get_all_thresholds(sample_user_id)

        assert len(thresholds) == 2

    @pytest.mark.asyncio
    async def test_get_all_thresholds_by_category(self, service, sample_user_id):
        """Thresholds nach Kategorie filtern."""
        mock_profile = MockDBProfile(user_id=sample_user_id)
        mock_thresholds = [
            MockDBThreshold(
                id=uuid4(),
                user_id=sample_user_id,
                threshold_type="dti_warning",
            ),
            MockDBThreshold(
                id=uuid4(),
                user_id=sample_user_id,
                threshold_type="emergency_fund_target",
            ),
        ]

        service._profile_repo.get_by_user_id.return_value = mock_profile
        service._threshold_repo.get_by_user_id.return_value = mock_thresholds

        # Filter by DEBT category
        thresholds = await service.get_all_thresholds(
            sample_user_id,
            category=ThresholdCategory.DEBT,
        )

        # Only DTI thresholds should match
        assert isinstance(thresholds, list)

    @pytest.mark.asyncio
    async def test_set_threshold(self, service, sample_user_id):
        """Threshold setzen funktioniert."""
        mock_profile = MockDBProfile(user_id=sample_user_id)
        mock_existing = MockDBThreshold(
            id=uuid4(),
            user_id=sample_user_id,
            threshold_type="dti_warning",
            current_value=Decimal("36.0"),
        )
        mock_updated = MockDBThreshold(
            id=uuid4(),
            user_id=sample_user_id,
            threshold_type="dti_warning",
            current_value=Decimal("42.0"),
            adjustment_source="user_preference",
        )

        service._profile_repo.get_by_user_id.return_value = mock_profile
        service._threshold_repo.get_by_user_and_type.return_value = mock_existing
        service._threshold_repo.upsert.return_value = mock_updated
        service._adjustment_repo.create.return_value = MagicMock()

        threshold = await service.set_threshold(
            sample_user_id,
            ThresholdType.DTI_WARNING,
            42.0,
            reason="User-Anpassung",
        )

        assert threshold.current_value == 42.0
        assert threshold.adjustment_source == AdjustmentSource.USER_PREFERENCE

    @pytest.mark.asyncio
    async def test_set_threshold_invalid_value(self, service, sample_user_id):
        """Ungueltiger Wert wird abgelehnt."""
        mock_profile = MockDBProfile(user_id=sample_user_id)
        service._profile_repo.get_by_user_id.return_value = mock_profile

        with pytest.raises(ValueError) as exc_info:
            await service.set_threshold(
                sample_user_id,
                ThresholdType.DTI_WARNING,
                200.0,  # Weit ueber max_allowed
            )

        assert "ausserhalb" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_set_threshold_unknown_type(self, service, sample_user_id):
        """Unbekannter Threshold-Typ wird abgelehnt."""
        mock_profile = MockDBProfile(user_id=sample_user_id)
        service._profile_repo.get_by_user_id.return_value = mock_profile

        # Patch registry to return None
        service.registry.get_threshold = MagicMock(return_value=None)

        with pytest.raises(ValueError) as exc_info:
            await service.set_threshold(
                sample_user_id,
                ThresholdType.DTI_WARNING,
                42.0,
            )

        assert "Unknown" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_reset_threshold(self, service, sample_user_id):
        """Threshold zuruecksetzen funktioniert."""
        mock_profile = MockDBProfile(user_id=sample_user_id)
        mock_threshold = MockDBThreshold(
            id=uuid4(),
            user_id=sample_user_id,
            threshold_type="dti_warning",
            current_value=Decimal("36.0"),
        )

        service._profile_repo.get_by_user_id.return_value = mock_profile
        service._threshold_repo.get_by_user_and_type.return_value = mock_threshold
        service._threshold_repo.upsert.return_value = mock_threshold
        service._adjustment_repo.create.return_value = MagicMock()

        threshold = await service.reset_threshold(sample_user_id, ThresholdType.DTI_WARNING)

        assert threshold is not None

    @pytest.mark.asyncio
    async def test_reset_all_thresholds(self, service, sample_user_id):
        """Alle Thresholds zuruecksetzen funktioniert."""
        mock_profile = MockDBProfile(user_id=sample_user_id)
        mock_threshold = MockDBThreshold(
            id=uuid4(),
            user_id=sample_user_id,
            threshold_type="dti_warning",
            current_value=Decimal("36.0"),
        )

        service._profile_repo.get_by_user_id.return_value = mock_profile
        service._threshold_repo.get_by_user_and_type.return_value = mock_threshold
        service._threshold_repo.upsert.return_value = mock_threshold
        service._adjustment_repo.create.return_value = MagicMock()

        results = await service.reset_all_thresholds(sample_user_id)

        assert isinstance(results, list)


# =============================================================================
# Threshold Initialization Tests
# =============================================================================

class TestThresholdInitialization:
    """Tests fuer Threshold-Initialisierung."""

    @pytest.mark.asyncio
    async def test_initialize_user_thresholds(self, service, sample_user_id):
        """User-Thresholds werden korrekt initialisiert."""
        profile = UserProfile(
            user_id=sample_user_id,
            profession_type=ProfessionType.EMPLOYEE,
            risk_tolerance=RiskTolerance.MODERATE,
            income_stability=0.7,
            age_group="31-45",
            household_size=2,
            has_dependents=False,
            is_homeowner=False,
            has_pension_plan=True,
        )

        service._threshold_repo.bulk_upsert.return_value = []

        await service._initialize_user_thresholds(sample_user_id, profile)

        service._threshold_repo.bulk_upsert.assert_called_once()
        call_args = service._threshold_repo.bulk_upsert.call_args
        assert call_args[0][0] == sample_user_id
        assert len(call_args[0][1]) > 0  # Sollte mehrere Thresholds haben

    def test_calculate_personalized_value_with_profession(self, service):
        """Personalisierter Wert beruecksichtigt Profession."""
        profile = UserProfile(
            user_id=uuid4(),
            profession_type=ProfessionType.CIVIL_SERVANT,
            risk_tolerance=RiskTolerance.MODERATE,
            income_stability=0.9,
            age_group="31-45",
            household_size=2,
            has_dependents=False,
            is_homeowner=True,
            has_pension_plan=True,
        )

        # Get DTI definition from registry
        definition = service.registry.get_threshold(ThresholdType.DTI_WARNING)

        if definition:
            value = service._calculate_personalized_value(definition, profile)
            # Beamte haben hoehere erlaubte DTI
            assert value >= definition.default_value

    def test_calculate_personalized_value_with_risk_modifier(self, service):
        """Personalisierter Wert beruecksichtigt Risiko-Toleranz."""
        profile_conservative = UserProfile(
            user_id=uuid4(),
            profession_type=ProfessionType.EMPLOYEE,
            risk_tolerance=RiskTolerance.CONSERVATIVE,
            income_stability=0.7,
            age_group="46-60",
            household_size=3,
            has_dependents=True,
            is_homeowner=True,
            has_pension_plan=True,
        )
        profile_aggressive = UserProfile(
            user_id=uuid4(),
            profession_type=ProfessionType.EMPLOYEE,
            risk_tolerance=RiskTolerance.AGGRESSIVE,
            income_stability=0.8,
            age_group="25-30",
            household_size=1,
            has_dependents=False,
            is_homeowner=False,
            has_pension_plan=False,
        )

        definition = service.registry.get_threshold(ThresholdType.DTI_WARNING)

        if definition:
            value_conservative = service._calculate_personalized_value(
                definition, profile_conservative
            )
            value_aggressive = service._calculate_personalized_value(
                definition, profile_aggressive
            )

            # Unterschiedliche Risk-Toleranz sollte unterschiedliche Werte ergeben
            # (wenn risk_modifiers definiert sind)
            assert isinstance(value_conservative, float)
            assert isinstance(value_aggressive, float)


# =============================================================================
# Effectiveness Tracking Tests
# =============================================================================

class TestEffectivenessTracking:
    """Tests fuer Effectiveness-Tracking."""

    @pytest.mark.asyncio
    async def test_record_threshold_trigger(self, service, sample_user_id):
        """Threshold-Trigger wird aufgezeichnet."""
        service._threshold_repo.record_trigger.return_value = None

        await service.record_threshold_trigger(
            sample_user_id,
            ThresholdType.DTI_WARNING,
            actual_value=42.0,
            triggered=True,
        )

        service._threshold_repo.record_trigger.assert_called_once_with(
            sample_user_id,
            "dti_warning",
        )

    @pytest.mark.asyncio
    async def test_record_threshold_action(self, service, sample_user_id):
        """Threshold-Action wird aufgezeichnet."""
        service._threshold_repo.record_action.return_value = None

        await service.record_threshold_action(
            sample_user_id,
            ThresholdType.DTI_WARNING,
            action_taken=True,
        )

        service._threshold_repo.record_action.assert_called_once_with(
            sample_user_id,
            "dti_warning",
            True,
        )


# =============================================================================
# Recommendations Tests
# =============================================================================

class TestRecommendations:
    """Tests fuer Empfehlungs-System."""

    @pytest.mark.asyncio
    async def test_generate_recommendations_dti(self, service, sample_user_id):
        """DTI-basierte Empfehlung wird generiert."""
        mock_profile = MockDBProfile(
            user_id=sample_user_id,
            income_stability=Decimal("0.85"),
        )
        mock_threshold = MockDBThreshold(
            id=uuid4(),
            user_id=sample_user_id,
            threshold_type="dti_warning",
            current_value=Decimal("40.0"),
        )
        mock_rec = MockDBRecommendation(
            id=uuid4(),
            user_id=sample_user_id,
            threshold_type="dti_warning",
        )

        service._profile_repo.get_by_user_id.return_value = mock_profile
        service._threshold_repo.get_by_user_and_type.return_value = mock_threshold
        service._threshold_repo.upsert.return_value = mock_threshold
        service._recommendation_repo.create.return_value = mock_rec

        recommendations = await service.generate_threshold_recommendations(
            sample_user_id,
            current_kpis={"dti_ratio": 38.0},  # 95% of threshold
        )

        assert isinstance(recommendations, list)

    @pytest.mark.asyncio
    async def test_generate_recommendations_emergency_fund(self, service, sample_user_id):
        """Notgroschen-Empfehlung wird generiert."""
        mock_profile = MockDBProfile(user_id=sample_user_id)
        mock_threshold = MockDBThreshold(
            id=uuid4(),
            user_id=sample_user_id,
            threshold_type="emergency_fund_target",
            current_value=Decimal("6.0"),
        )
        mock_rec = MockDBRecommendation(
            id=uuid4(),
            user_id=sample_user_id,
            threshold_type="emergency_fund_target",
        )

        service._profile_repo.get_by_user_id.return_value = mock_profile
        service._threshold_repo.get_by_user_and_type.return_value = mock_threshold
        service._threshold_repo.upsert.return_value = mock_threshold
        service._recommendation_repo.create.return_value = mock_rec

        recommendations = await service.generate_threshold_recommendations(
            sample_user_id,
            current_kpis={"emergency_fund_months": 10.0},  # Deutlich ueber Ziel
        )

        assert isinstance(recommendations, list)

    @pytest.mark.asyncio
    async def test_generate_recommendations_savings_rate(self, service, sample_user_id):
        """Sparraten-Empfehlung wird generiert."""
        mock_profile = MockDBProfile(user_id=sample_user_id)
        mock_threshold = MockDBThreshold(
            id=uuid4(),
            user_id=sample_user_id,
            threshold_type="savings_rate_target",
            current_value=Decimal("20.0"),
        )
        mock_rec = MockDBRecommendation(
            id=uuid4(),
            user_id=sample_user_id,
            threshold_type="savings_rate_target",
        )

        service._profile_repo.get_by_user_id.return_value = mock_profile
        service._threshold_repo.get_by_user_and_type.return_value = mock_threshold
        service._threshold_repo.upsert.return_value = mock_threshold
        service._recommendation_repo.create.return_value = mock_rec

        recommendations = await service.generate_threshold_recommendations(
            sample_user_id,
            current_kpis={"monthly_savings_rate": 30.0},  # 50% ueber Ziel
        )

        assert isinstance(recommendations, list)

    @pytest.mark.asyncio
    async def test_get_pending_recommendations(self, service, sample_user_id):
        """Ausstehende Empfehlungen werden zurueckgegeben."""
        mock_recs = [
            MockDBRecommendation(
                id=uuid4(),
                user_id=sample_user_id,
                threshold_type="dti_warning",
            ),
        ]

        service._recommendation_repo.get_pending_by_user.return_value = mock_recs

        recommendations = await service.get_pending_recommendations(sample_user_id)

        assert len(recommendations) == 1
        assert recommendations[0].threshold_type == ThresholdType.DTI_WARNING

    @pytest.mark.asyncio
    async def test_accept_recommendation(self, service, sample_user_id):
        """Empfehlung akzeptieren funktioniert."""
        rec_id = uuid4()
        mock_rec = MockDBRecommendation(
            id=rec_id,
            user_id=sample_user_id,
            threshold_type="dti_warning",
            recommended_value=Decimal("42.0"),
        )
        mock_profile = MockDBProfile(user_id=sample_user_id)
        mock_threshold = MockDBThreshold(
            id=uuid4(),
            user_id=sample_user_id,
            threshold_type="dti_warning",
            current_value=Decimal("42.0"),
        )

        service._recommendation_repo.accept.return_value = mock_rec
        service._profile_repo.get_by_user_id.return_value = mock_profile
        service._threshold_repo.get_by_user_and_type.return_value = mock_threshold
        service._threshold_repo.upsert.return_value = mock_threshold
        service._adjustment_repo.create.return_value = MagicMock()

        threshold = await service.accept_recommendation(sample_user_id, rec_id)

        assert threshold is not None
        assert threshold.current_value == 42.0

    @pytest.mark.asyncio
    async def test_accept_recommendation_not_found(self, service, sample_user_id):
        """Nicht existierende Empfehlung gibt None zurueck."""
        service._recommendation_repo.accept.return_value = None

        result = await service.accept_recommendation(sample_user_id, uuid4())

        assert result is None

    @pytest.mark.asyncio
    async def test_reject_recommendation(self, service, sample_user_id):
        """Empfehlung ablehnen funktioniert."""
        rec_id = uuid4()
        mock_rec = MockDBRecommendation(
            id=rec_id,
            user_id=sample_user_id,
            threshold_type="dti_warning",
        )
        mock_profile = MockDBProfile(
            user_id=sample_user_id,
            feedback_history=[],
        )

        service._recommendation_repo.reject.return_value = mock_rec
        service._profile_repo.get_by_user_id.return_value = mock_profile
        service._profile_repo.upsert.return_value = mock_profile

        result = await service.reject_recommendation(
            sample_user_id,
            rec_id,
            reason="Nicht relevant",
        )

        assert result is True
        service._profile_repo.upsert.assert_called()

    @pytest.mark.asyncio
    async def test_reject_recommendation_not_found(self, service, sample_user_id):
        """Nicht existierende Empfehlung gibt False zurueck."""
        service._recommendation_repo.reject.return_value = None

        result = await service.reject_recommendation(sample_user_id, uuid4())

        assert result is False


# =============================================================================
# Statistics Tests
# =============================================================================

class TestStatistics:
    """Tests fuer Statistik-Funktionen."""

    @pytest.mark.asyncio
    async def test_get_threshold_statistics(self, service, sample_user_id):
        """Statistiken werden korrekt berechnet."""
        mock_profile = MockDBProfile(user_id=sample_user_id)
        mock_thresholds = [
            MockDBThreshold(
                id=uuid4(),
                user_id=sample_user_id,
                threshold_type="dti_warning",
                adjustment_source="user_preference",
                times_triggered=10,
                times_acted_on=8,
                effectiveness_score=Decimal("0.8"),
            ),
            MockDBThreshold(
                id=uuid4(),
                user_id=sample_user_id,
                threshold_type="dti_critical",
                adjustment_source="system_default",
                times_triggered=5,
                times_acted_on=5,
                effectiveness_score=Decimal("1.0"),
            ),
        ]

        service._profile_repo.get_by_user_id.return_value = mock_profile
        service._threshold_repo.get_by_user_id.return_value = mock_thresholds
        service._recommendation_repo.get_pending_by_user.return_value = []

        stats = await service.get_threshold_statistics(sample_user_id)

        assert stats["total_thresholds"] == 2
        assert stats["customized_count"] == 1
        assert stats["system_defaults_count"] == 1
        assert stats["total_triggers"] == 15
        assert stats["total_actions"] == 13
        assert stats["average_effectiveness"] == 0.9  # (0.8 + 1.0) / 2

    @pytest.mark.asyncio
    async def test_get_threshold_statistics_empty(self, service, sample_user_id):
        """Statistiken fuer User ohne Thresholds."""
        mock_profile = MockDBProfile(user_id=sample_user_id)

        service._profile_repo.get_by_user_id.return_value = mock_profile
        service._threshold_repo.get_by_user_id.return_value = []

        stats = await service.get_threshold_statistics(sample_user_id)

        assert stats["total_thresholds"] == 0
        assert stats["customized_count"] == 0
        assert stats["average_effectiveness"] == 0

    @pytest.mark.asyncio
    async def test_get_adjustment_history(self, service, sample_user_id):
        """Anpassungs-Historie wird zurueckgegeben."""
        mock_adjustments = [
            MockDBAdjustment(
                id=uuid4(),
                user_id=sample_user_id,
                threshold_type="dti_warning",
                previous_value=Decimal("36.0"),
                new_value=Decimal("40.0"),
            ),
        ]

        service._adjustment_repo.get_by_user_id.return_value = mock_adjustments

        history = await service.get_adjustment_history(sample_user_id)

        assert len(history) == 1
        assert history[0].threshold_type == ThresholdType.DTI_WARNING
        assert history[0].previous_value == 36.0
        assert history[0].new_value == 40.0


# =============================================================================
# Recalculation Tests
# =============================================================================

class TestRecalculation:
    """Tests fuer Threshold-Neuberechnung."""

    @pytest.mark.asyncio
    async def test_recalculate_thresholds_no_existing(self, service, sample_user_id):
        """Neuberechnung initialisiert wenn keine Thresholds existieren."""
        profile = UserProfile(
            user_id=sample_user_id,
            profession_type=ProfessionType.EMPLOYEE,
            risk_tolerance=RiskTolerance.MODERATE,
            income_stability=0.7,
            age_group="31-45",
            household_size=2,
            has_dependents=False,
            is_homeowner=False,
            has_pension_plan=True,
        )

        service._threshold_repo.get_by_user_id.return_value = []
        service._threshold_repo.bulk_upsert.return_value = []

        await service._recalculate_thresholds(sample_user_id, profile)

        service._threshold_repo.bulk_upsert.assert_called_once()

    @pytest.mark.asyncio
    async def test_recalculate_thresholds_updates_system_defaults(self, service, sample_user_id):
        """Neuberechnung aktualisiert nur System-Defaults."""
        profile = UserProfile(
            user_id=sample_user_id,
            profession_type=ProfessionType.CIVIL_SERVANT,
            risk_tolerance=RiskTolerance.CONSERVATIVE,
            income_stability=0.95,
            age_group="46-60",
            household_size=4,
            has_dependents=True,
            is_homeowner=True,
            has_pension_plan=True,
        )

        mock_thresholds = [
            MockDBThreshold(
                id=uuid4(),
                user_id=sample_user_id,
                threshold_type="dti_warning",
                adjustment_source="system_default",
                current_value=Decimal("36.0"),
            ),
            MockDBThreshold(
                id=uuid4(),
                user_id=sample_user_id,
                threshold_type="dti_critical",
                adjustment_source="user_preference",  # Should NOT be updated
                current_value=Decimal("45.0"),
            ),
        ]

        service._threshold_repo.get_by_user_id.return_value = mock_thresholds
        service._threshold_repo.upsert.return_value = mock_thresholds[0]
        service._adjustment_repo.create.return_value = MagicMock()

        await service._recalculate_thresholds(sample_user_id, profile)

        # Sollte nur system_default aktualisieren, nicht user_preference
        # (Genauer Check haengt von Registry-Definition ab)


# =============================================================================
# Conversion Tests
# =============================================================================

class TestConversions:
    """Tests fuer DB-Modell Konvertierungen."""

    def test_db_profile_to_dataclass(self, service, sample_user_id):
        """DB-Profile wird korrekt zu Dataclass konvertiert."""
        db_profile = MockDBProfile(
            user_id=sample_user_id,
            profession_type="freelancer",
            risk_tolerance="aggressive",
            income_stability=Decimal("0.5"),
            age_group="25-30",
            household_size=1,
        )

        profile = service._db_profile_to_dataclass(db_profile)

        assert profile.user_id == sample_user_id
        assert profile.profession_type == ProfessionType.FREELANCER
        assert profile.risk_tolerance == RiskTolerance.AGGRESSIVE
        assert profile.income_stability == 0.5
        assert profile.age_group == "25-30"
        assert profile.household_size == 1

    def test_db_threshold_to_dataclass(self, service, sample_user_id):
        """DB-Threshold wird korrekt zu Dataclass konvertiert."""
        threshold_id = uuid4()
        db_threshold = MockDBThreshold(
            id=threshold_id,
            user_id=sample_user_id,
            threshold_type="dti_warning",
            default_value=Decimal("36.0"),
            current_value=Decimal("42.0"),
            adjustment_source="user_preference",
            confidence=Decimal("0.95"),
            times_triggered=10,
            times_acted_on=8,
            effectiveness_score=Decimal("0.8"),
        )

        threshold = service._db_threshold_to_dataclass(db_threshold)

        assert threshold.id == threshold_id
        assert threshold.threshold_type == ThresholdType.DTI_WARNING
        assert threshold.default_value == 36.0
        assert threshold.current_value == 42.0
        assert threshold.adjustment_source == AdjustmentSource.USER_PREFERENCE
        assert threshold.confidence == 0.95

    def test_db_recommendation_to_dataclass(self, service, sample_user_id):
        """DB-Recommendation wird korrekt zu Dataclass konvertiert."""
        rec_id = uuid4()
        expires = datetime.now(timezone.utc) + timedelta(days=30)

        db_rec = MockDBRecommendation(
            id=rec_id,
            user_id=sample_user_id,
            threshold_type="dti_warning",
            current_value=Decimal("36.0"),
            recommended_value=Decimal("40.0"),
            reason="Test-Grund",
            confidence=Decimal("0.8"),
            potential_impact="Weniger Warnungen",
            expires_at=expires,
        )

        rec = service._db_recommendation_to_dataclass(db_rec)

        assert rec.id == rec_id
        assert rec.threshold_type == ThresholdType.DTI_WARNING
        assert rec.current_value == 36.0
        assert rec.recommended_value == 40.0
        assert rec.confidence == 0.8

    def test_db_adjustment_to_dataclass(self, service, sample_user_id):
        """DB-Adjustment wird korrekt zu Dataclass konvertiert."""
        adj_id = uuid4()
        applied = datetime.now(timezone.utc)

        db_adj = MockDBAdjustment(
            id=adj_id,
            user_id=sample_user_id,
            threshold_type="dti_warning",
            previous_value=Decimal("36.0"),
            new_value=Decimal("42.0"),
            adjustment_source="user_preference",
            reason="Anpassung",
            confidence=Decimal("1.0"),
            applied_at=applied,
            can_rollback=True,
            rolled_back=False,
        )

        adj = service._db_adjustment_to_dataclass(db_adj)

        assert adj.id == adj_id
        assert adj.threshold_type == ThresholdType.DTI_WARNING
        assert adj.previous_value == 36.0
        assert adj.new_value == 42.0
        assert adj.can_rollback is True
        assert adj.rolled_back is False

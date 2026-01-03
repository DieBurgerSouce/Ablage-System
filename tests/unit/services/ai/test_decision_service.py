"""
Unit Tests fuer AIDecisionService.

Tests fuer Confidence-basierte Autonomie und Review-Workflow.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ai.decision_service import (
    AIDecisionService,
    DecisionType,
    ConfidenceLevel,
    ReviewAction,
    ThresholdConfig,
    get_ai_decision_service,
)


class TestConfidenceLevelDetermination:
    """Tests fuer die Bestimmung des Confidence-Levels."""

    def test_auto_level_above_auto_threshold(self) -> None:
        """Test: Confidence >= auto_threshold -> AUTO."""
        service = AIDecisionService()
        config = ThresholdConfig(
            decision_type=DecisionType.CATEGORIZATION,
            auto_threshold=0.95,
            suggest_threshold=0.80,
        )

        level = service.determine_confidence_level(0.97, config)

        assert level == ConfidenceLevel.AUTO

    def test_suggest_level_between_thresholds(self) -> None:
        """Test: suggest <= confidence < auto -> SUGGEST."""
        service = AIDecisionService()
        config = ThresholdConfig(
            decision_type=DecisionType.CATEGORIZATION,
            auto_threshold=0.95,
            suggest_threshold=0.80,
        )

        level = service.determine_confidence_level(0.85, config)

        assert level == ConfidenceLevel.SUGGEST

    def test_manual_level_below_suggest(self) -> None:
        """Test: confidence < suggest -> MANUAL."""
        service = AIDecisionService()
        config = ThresholdConfig(
            decision_type=DecisionType.CATEGORIZATION,
            auto_threshold=0.95,
            suggest_threshold=0.80,
        )

        level = service.determine_confidence_level(0.70, config)

        assert level == ConfidenceLevel.MANUAL

    def test_disabled_feature_returns_manual(self) -> None:
        """Test: Deaktivierte Features -> immer MANUAL."""
        service = AIDecisionService()
        config = ThresholdConfig(
            decision_type=DecisionType.CATEGORIZATION,
            auto_threshold=0.95,
            suggest_threshold=0.80,
            is_enabled=False,
        )

        level = service.determine_confidence_level(0.99, config)

        assert level == ConfidenceLevel.MANUAL

    def test_edge_case_exact_auto_threshold(self) -> None:
        """Test: Exakt auf auto_threshold -> AUTO."""
        service = AIDecisionService()
        config = ThresholdConfig(
            decision_type=DecisionType.CATEGORIZATION,
            auto_threshold=0.95,
            suggest_threshold=0.80,
        )

        level = service.determine_confidence_level(0.95, config)

        assert level == ConfidenceLevel.AUTO

    def test_edge_case_exact_suggest_threshold(self) -> None:
        """Test: Exakt auf suggest_threshold -> SUGGEST."""
        service = AIDecisionService()
        config = ThresholdConfig(
            decision_type=DecisionType.CATEGORIZATION,
            auto_threshold=0.95,
            suggest_threshold=0.80,
        )

        level = service.determine_confidence_level(0.80, config)

        assert level == ConfidenceLevel.SUGGEST


class TestDefaultThresholds:
    """Tests fuer Default-Threshold-Konfiguration."""

    def test_categorization_defaults(self) -> None:
        """Test: Kategorisierung hat korrekte Defaults."""
        from app.services.ai.decision_service import DEFAULT_THRESHOLDS

        config = DEFAULT_THRESHOLDS[DecisionType.CATEGORIZATION]

        assert config.auto_threshold == 0.95
        assert config.suggest_threshold == 0.80
        assert config.allow_auto_apply is True

    def test_accounting_defaults(self) -> None:
        """Test: Buchhaltung hat allow_auto_apply=False."""
        from app.services.ai.decision_service import DEFAULT_THRESHOLDS

        config = DEFAULT_THRESHOLDS[DecisionType.ACCOUNTING]

        assert config.auto_threshold == 0.90
        assert config.suggest_threshold == 0.75
        assert config.allow_auto_apply is False

    def test_anomaly_defaults(self) -> None:
        """Test: Anomalie-Erkennung hat allow_auto_apply=False."""
        from app.services.ai.decision_service import DEFAULT_THRESHOLDS

        config = DEFAULT_THRESHOLDS[DecisionType.ANOMALY]

        assert config.allow_auto_apply is False

    def test_all_decision_types_have_defaults(self) -> None:
        """Test: Alle DecisionTypes haben Default-Konfiguration."""
        from app.services.ai.decision_service import DEFAULT_THRESHOLDS

        for dt in DecisionType:
            assert dt in DEFAULT_THRESHOLDS
            config = DEFAULT_THRESHOLDS[dt]
            assert 0.0 <= config.auto_threshold <= 1.0
            assert 0.0 <= config.suggest_threshold <= 1.0
            assert config.auto_threshold >= config.suggest_threshold


@pytest.mark.asyncio
class TestMakeDecision:
    """Async Tests fuer make_decision."""

    @pytest_asyncio.fixture
    async def mock_db(self) -> AsyncMock:
        """Create mock database session."""
        mock = AsyncMock(spec=AsyncSession)
        mock.execute = AsyncMock()
        mock.commit = AsyncMock()
        mock.refresh = AsyncMock()
        mock.add = MagicMock()
        return mock

    @pytest_asyncio.fixture
    async def service(self) -> AIDecisionService:
        """Create service instance."""
        return AIDecisionService()

    async def test_auto_apply_high_confidence(
        self, service: AIDecisionService, mock_db: AsyncMock
    ) -> None:
        """Test: Hohe Confidence -> auto_applied=True."""
        # Mock empty threshold result
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        result = await service.make_decision(
            db=mock_db,
            decision_type=DecisionType.CATEGORIZATION,
            decision_value={"category": "invoice"},
            confidence=0.97,
        )

        assert result.auto_applied is True
        assert result.requires_review is False
        assert result.confidence_level == ConfidenceLevel.AUTO
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called()

    async def test_suggest_medium_confidence(
        self, service: AIDecisionService, mock_db: AsyncMock
    ) -> None:
        """Test: Mittlere Confidence -> requires_review=True."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        result = await service.make_decision(
            db=mock_db,
            decision_type=DecisionType.CATEGORIZATION,
            decision_value={"category": "invoice"},
            confidence=0.85,
        )

        assert result.auto_applied is False
        assert result.requires_review is True
        assert result.confidence_level == ConfidenceLevel.SUGGEST

    async def test_manual_low_confidence(
        self, service: AIDecisionService, mock_db: AsyncMock
    ) -> None:
        """Test: Niedrige Confidence -> MANUAL Level."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        result = await service.make_decision(
            db=mock_db,
            decision_type=DecisionType.CATEGORIZATION,
            decision_value={"category": "invoice"},
            confidence=0.60,
        )

        assert result.auto_applied is False
        assert result.requires_review is True
        assert result.confidence_level == ConfidenceLevel.MANUAL

    async def test_callback_executed_on_auto_apply(
        self, service: AIDecisionService, mock_db: AsyncMock
    ) -> None:
        """Test: Callback wird bei Auto-Apply ausgefuehrt."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        callback = AsyncMock()

        result = await service.make_decision(
            db=mock_db,
            decision_type=DecisionType.CATEGORIZATION,
            decision_value={"category": "invoice"},
            confidence=0.97,
            apply_callback=callback,
        )

        assert result.auto_applied is True
        callback.assert_called_once_with({"category": "invoice"})

    async def test_callback_not_executed_below_threshold(
        self, service: AIDecisionService, mock_db: AsyncMock
    ) -> None:
        """Test: Callback wird bei niedriger Confidence NICHT ausgefuehrt."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        callback = AsyncMock()

        result = await service.make_decision(
            db=mock_db,
            decision_type=DecisionType.CATEGORIZATION,
            decision_value={"category": "invoice"},
            confidence=0.70,
            apply_callback=callback,
        )

        assert result.auto_applied is False
        callback.assert_not_called()

    async def test_callback_failure_sets_requires_review(
        self, service: AIDecisionService, mock_db: AsyncMock
    ) -> None:
        """Test: Bei Callback-Fehler -> requires_review=True."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        callback = AsyncMock(side_effect=Exception("Callback failed"))

        result = await service.make_decision(
            db=mock_db,
            decision_type=DecisionType.CATEGORIZATION,
            decision_value={"category": "invoice"},
            confidence=0.97,
            apply_callback=callback,
        )

        # Bei Fehler sollte requires_review True sein
        assert result.auto_applied is False
        assert result.requires_review is True


@pytest.mark.asyncio
class TestReviewDecision:
    """Tests fuer review_decision."""

    @pytest_asyncio.fixture
    async def mock_db(self) -> AsyncMock:
        """Create mock database session."""
        mock = AsyncMock(spec=AsyncSession)
        mock.execute = AsyncMock()
        mock.commit = AsyncMock()
        mock.add = MagicMock()
        return mock

    @pytest_asyncio.fixture
    async def service(self) -> AIDecisionService:
        """Create service instance."""
        return AIDecisionService()

    async def test_approve_decision(
        self, service: AIDecisionService, mock_db: AsyncMock
    ) -> None:
        """Test: Entscheidung genehmigen."""
        decision_id = uuid4()
        reviewer_id = uuid4()

        mock_decision = MagicMock()
        mock_decision.id = decision_id
        mock_decision.decision_type = "categorization"
        mock_decision.decision_value = {"category": "invoice"}
        mock_decision.company_id = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_decision
        mock_db.execute.return_value = mock_result

        success = await service.review_decision(
            db=mock_db,
            decision_id=decision_id,
            reviewer_id=reviewer_id,
            action=ReviewAction.APPROVED,
        )

        assert success is True
        assert mock_decision.reviewed_by_id == reviewer_id
        assert mock_decision.review_action == "approved"
        assert mock_decision.requires_review is False
        assert mock_decision.is_final is True
        mock_db.add.assert_called_once()  # Feedback erstellt
        mock_db.commit.assert_called()

    async def test_reject_decision(
        self, service: AIDecisionService, mock_db: AsyncMock
    ) -> None:
        """Test: Entscheidung ablehnen."""
        decision_id = uuid4()
        reviewer_id = uuid4()

        mock_decision = MagicMock()
        mock_decision.id = decision_id
        mock_decision.decision_type = "categorization"
        mock_decision.decision_value = {"category": "invoice"}
        mock_decision.company_id = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_decision
        mock_db.execute.return_value = mock_result

        success = await service.review_decision(
            db=mock_db,
            decision_id=decision_id,
            reviewer_id=reviewer_id,
            action=ReviewAction.REJECTED,
            comment="Falsche Kategorie",
        )

        assert success is True
        assert mock_decision.review_action == "rejected"
        assert mock_decision.review_comment == "Falsche Kategorie"

    async def test_modify_decision(
        self, service: AIDecisionService, mock_db: AsyncMock
    ) -> None:
        """Test: Entscheidung modifizieren."""
        decision_id = uuid4()
        reviewer_id = uuid4()

        mock_decision = MagicMock()
        mock_decision.id = decision_id
        mock_decision.decision_type = "categorization"
        mock_decision.decision_value = {"category": "invoice"}
        mock_decision.company_id = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_decision
        mock_db.execute.return_value = mock_result

        modified_value = {"category": "delivery_note"}

        success = await service.review_decision(
            db=mock_db,
            decision_id=decision_id,
            reviewer_id=reviewer_id,
            action=ReviewAction.MODIFIED,
            modified_value=modified_value,
        )

        assert success is True
        assert mock_decision.review_action == "modified"
        assert mock_decision.modified_value == modified_value

    async def test_review_nonexistent_decision(
        self, service: AIDecisionService, mock_db: AsyncMock
    ) -> None:
        """Test: Review nicht-existenter Entscheidung -> False."""
        decision_id = uuid4()
        reviewer_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        success = await service.review_decision(
            db=mock_db,
            decision_id=decision_id,
            reviewer_id=reviewer_id,
            action=ReviewAction.APPROVED,
        )

        assert success is False


class TestServiceSingleton:
    """Tests fuer Service Singleton."""

    def test_get_ai_decision_service_returns_same_instance(self) -> None:
        """Test: Factory gibt immer gleiche Instanz zurueck."""
        service1 = get_ai_decision_service()
        service2 = get_ai_decision_service()

        assert service1 is service2

    def test_service_has_model_version(self) -> None:
        """Test: Service hat Model-Version."""
        service = get_ai_decision_service()

        assert hasattr(service, '_model_version')
        assert service._model_version is not None

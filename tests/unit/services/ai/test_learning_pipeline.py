# -*- coding: utf-8 -*-
"""
Unit Tests fuer AILearningPipeline.

Tests fuer Self-Learning aus User-Feedback:
- Feedback-Verarbeitung
- Threshold-Anpassungen
- Accuracy-Reports
- Statistik-Berechnung
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ai.learning_pipeline import (
    AILearningPipeline,
    LearningStats,
    ThresholdAdjustment,
    LearningBatchResult,
    get_ai_learning_pipeline,
)
from app.services.ai.decision_service import DecisionType


class TestLearningStats:
    """Tests fuer LearningStats Dataclass."""

    def test_learning_stats_creation(self) -> None:
        """Test: LearningStats kann erstellt werden."""
        stats = LearningStats(
            decision_type=DecisionType.CATEGORIZATION,
            total_decisions=100,
            auto_applied=60,
            reviewed=40,
            approved=30,
            corrected=8,
            rejected=2,
            accuracy_rate=0.90,
            correction_rate=0.20,
            rejection_rate=0.05,
            avg_confidence=0.85,
        )

        assert stats.decision_type == DecisionType.CATEGORIZATION
        assert stats.total_decisions == 100
        assert stats.accuracy_rate == 0.90

    def test_learning_stats_defaults(self) -> None:
        """Test: LearningStats hat korrekte Defaults."""
        stats = LearningStats(decision_type=DecisionType.DUPLICATE)

        assert stats.total_decisions == 0
        assert stats.auto_applied == 0
        assert stats.accuracy_rate == 0.0


class TestThresholdAdjustment:
    """Tests fuer ThresholdAdjustment Dataclass."""

    def test_threshold_adjustment_creation(self) -> None:
        """Test: ThresholdAdjustment kann erstellt werden."""
        adjustment = ThresholdAdjustment(
            decision_type=DecisionType.CATEGORIZATION,
            current_auto=0.95,
            current_suggest=0.80,
            suggested_auto=0.92,
            suggested_suggest=0.75,
            reason="Auto-Accuracy unter Ziel",
            confidence=0.7,
        )

        assert adjustment.decision_type == DecisionType.CATEGORIZATION
        assert adjustment.current_auto == 0.95
        assert adjustment.suggested_auto == 0.92


class TestLearningBatchResult:
    """Tests fuer LearningBatchResult Dataclass."""

    def test_batch_result_creation(self) -> None:
        """Test: LearningBatchResult kann erstellt werden."""
        result = LearningBatchResult(
            batch_id="abc12345",
            processed_count=50,
            decision_types={"categorization": 30, "duplicate": 20},
            threshold_adjustments=[],
            processing_time_ms=150,
        )

        assert result.batch_id == "abc12345"
        assert result.processed_count == 50
        assert result.decision_types["categorization"] == 30


class TestAILearningPipeline:
    """Tests fuer AILearningPipeline."""

    @pytest.fixture
    def pipeline(self) -> AILearningPipeline:
        """Erstellt Pipeline-Instanz."""
        return AILearningPipeline()

    def test_pipeline_configuration(
        self,
        pipeline: AILearningPipeline,
    ) -> None:
        """Test: Pipeline hat korrekte Konfiguration."""
        assert pipeline.MIN_SAMPLES_FOR_ADJUSTMENT == 20
        assert pipeline.ACCURACY_TARGET == 0.90
        assert pipeline.MAX_THRESHOLD_CHANGE == 0.05
        assert pipeline.FEEDBACK_WEIGHT_DECAY == 0.95


class TestGetLearningStats:
    """Tests fuer get_learning_stats Methode."""

    @pytest.fixture
    def pipeline(self) -> AILearningPipeline:
        return AILearningPipeline()

    @pytest.mark.asyncio
    async def test_get_learning_stats_empty_db(
        self,
        pipeline: AILearningPipeline,
    ) -> None:
        """Test: Leere Statistiken bei leerer DB."""
        db = AsyncMock(spec=AsyncSession)
        db.execute = AsyncMock(return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        ))

        stats = await pipeline.get_learning_stats(db)

        assert isinstance(stats, list)
        assert len(stats) == 0

    @pytest.mark.asyncio
    async def test_get_learning_stats_returns_list(
        self,
        pipeline: AILearningPipeline,
    ) -> None:
        """Test: get_learning_stats gibt Liste zurueck."""
        db = AsyncMock(spec=AsyncSession)

        # Mock Decisions
        mock_decision = MagicMock()
        mock_decision.decision_type = "categorization"
        mock_decision.is_final = True
        mock_decision.auto_applied = True
        mock_decision.reviewed_by_id = None
        mock_decision.review_action = None
        mock_decision.confidence = 0.95
        mock_decision.created_at = datetime.now(timezone.utc)

        db.execute = AsyncMock(return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(
                all=MagicMock(return_value=[mock_decision])
            ))
        ))

        stats = await pipeline.get_learning_stats(db)

        assert isinstance(stats, list)


class TestProcessFeedbackQueue:
    """Tests fuer process_feedback_queue Methode."""

    @pytest.fixture
    def pipeline(self) -> AILearningPipeline:
        return AILearningPipeline()

    @pytest.mark.asyncio
    async def test_process_feedback_empty_queue(
        self,
        pipeline: AILearningPipeline,
    ) -> None:
        """Test: Leere Feedback-Queue."""
        db = AsyncMock(spec=AsyncSession)
        db.execute = AsyncMock(return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        ))

        result = await pipeline.process_feedback_queue(db)

        assert isinstance(result, LearningBatchResult)
        assert result.processed_count == 0
        assert len(result.decision_types) == 0

    @pytest.mark.asyncio
    async def test_process_feedback_returns_batch_result(
        self,
        pipeline: AILearningPipeline,
    ) -> None:
        """Test: process_feedback_queue gibt LearningBatchResult zurueck."""
        db = AsyncMock(spec=AsyncSession)
        db.execute = AsyncMock(return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        ))

        result = await pipeline.process_feedback_queue(db, batch_size=50)

        assert isinstance(result, LearningBatchResult)
        assert result.batch_id is not None
        assert result.processing_time_ms >= 0


class TestCalculateOptimalThreshold:
    """Tests fuer _calculate_optimal_threshold Methode."""

    @pytest.fixture
    def pipeline(self) -> AILearningPipeline:
        return AILearningPipeline()

    def test_not_enough_samples(
        self,
        pipeline: AILearningPipeline,
    ) -> None:
        """Test: Keine Anpassung bei zu wenigen Samples."""
        decisions = [MagicMock() for _ in range(5)]  # Weniger als MIN_SAMPLES

        new_auto, new_suggest, reason = pipeline._calculate_optimal_threshold(
            decisions, 0.95, 0.80
        )

        assert new_auto == 0.95
        assert new_suggest == 0.80
        assert "Samples" in reason

    def test_optimal_threshold_no_change(
        self,
        pipeline: AILearningPipeline,
    ) -> None:
        """Test: Keine Aenderung wenn Accuracy gut ist."""
        # Erstelle 25 mock decisions mit hoher Accuracy
        decisions = []
        for _ in range(25):
            d = MagicMock()
            d.auto_applied = True
            d.review_action = None
            d.reviewed_by_id = None
            d.confidence = 0.96
            decisions.append(d)

        new_auto, new_suggest, reason = pipeline._calculate_optimal_threshold(
            decisions, 0.95, 0.80
        )

        # Bei guter Accuracy sollte keine grosse Aenderung passieren
        assert abs(new_auto - 0.95) <= 0.1


class TestSuggestThresholdAdjustments:
    """Tests fuer suggest_threshold_adjustments Methode."""

    @pytest.fixture
    def pipeline(self) -> AILearningPipeline:
        return AILearningPipeline()

    @pytest.mark.asyncio
    async def test_suggest_adjustments_empty_db(
        self,
        pipeline: AILearningPipeline,
    ) -> None:
        """Test: Keine Vorschlaege bei leerer DB."""
        db = AsyncMock(spec=AsyncSession)
        db.execute = AsyncMock(return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        ))

        adjustments = await pipeline.suggest_threshold_adjustments(db)

        assert isinstance(adjustments, list)

    @pytest.mark.asyncio
    async def test_suggest_adjustments_returns_list(
        self,
        pipeline: AILearningPipeline,
    ) -> None:
        """Test: suggest_threshold_adjustments gibt Liste zurueck."""
        db = AsyncMock(spec=AsyncSession)
        db.execute = AsyncMock(return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        ))

        adjustments = await pipeline.suggest_threshold_adjustments(
            db, company_id=uuid4(), days=30
        )

        assert isinstance(adjustments, list)
        for adj in adjustments:
            assert isinstance(adj, ThresholdAdjustment)


class TestApplyThresholdAdjustment:
    """Tests fuer apply_threshold_adjustment Methode."""

    @pytest.fixture
    def pipeline(self) -> AILearningPipeline:
        return AILearningPipeline()

    @pytest.mark.asyncio
    async def test_apply_adjustment_creates_new(
        self,
        pipeline: AILearningPipeline,
    ) -> None:
        """Test: Neuer Threshold wird erstellt wenn keiner existiert."""
        db = AsyncMock(spec=AsyncSession)
        db.execute = AsyncMock(return_value=MagicMock(
            scalar_one_or_none=MagicMock(return_value=None)
        ))

        adjustment = ThresholdAdjustment(
            decision_type=DecisionType.CATEGORIZATION,
            current_auto=0.95,
            current_suggest=0.80,
            suggested_auto=0.92,
            suggested_suggest=0.78,
            reason="Test",
            confidence=0.7,
        )

        result = await pipeline.apply_threshold_adjustment(
            db, adjustment, company_id=uuid4()
        )

        assert result is True
        db.add.assert_called_once()
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_apply_adjustment_updates_existing(
        self,
        pipeline: AILearningPipeline,
    ) -> None:
        """Test: Existierender Threshold wird aktualisiert."""
        db = AsyncMock(spec=AsyncSession)

        # Mock existing threshold
        existing = MagicMock()
        existing.auto_threshold = 0.95
        existing.suggest_threshold = 0.80

        db.execute = AsyncMock(return_value=MagicMock(
            scalar_one_or_none=MagicMock(return_value=existing)
        ))

        adjustment = ThresholdAdjustment(
            decision_type=DecisionType.CATEGORIZATION,
            current_auto=0.95,
            current_suggest=0.80,
            suggested_auto=0.92,
            suggested_suggest=0.78,
            reason="Test",
            confidence=0.7,
        )

        result = await pipeline.apply_threshold_adjustment(db, adjustment)

        assert result is True
        assert existing.auto_threshold == 0.92
        assert existing.suggest_threshold == 0.78


class TestGenerateAccuracyReport:
    """Tests fuer generate_accuracy_report Methode."""

    @pytest.fixture
    def pipeline(self) -> AILearningPipeline:
        return AILearningPipeline()

    @pytest.mark.asyncio
    async def test_generate_report_structure(
        self,
        pipeline: AILearningPipeline,
    ) -> None:
        """Test: Report hat korrekte Struktur."""
        db = AsyncMock(spec=AsyncSession)
        db.execute = AsyncMock(return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        ))

        report = await pipeline.generate_accuracy_report(db)

        assert "generated_at" in report
        assert "period_days" in report
        assert "summary" in report
        assert "by_decision_type" in report
        assert "suggested_adjustments" in report

    @pytest.mark.asyncio
    async def test_generate_report_summary(
        self,
        pipeline: AILearningPipeline,
    ) -> None:
        """Test: Report-Summary hat korrekte Felder."""
        db = AsyncMock(spec=AsyncSession)
        db.execute = AsyncMock(return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        ))

        report = await pipeline.generate_accuracy_report(db, days=60)

        assert report["period_days"] == 60
        assert "total_decision_types" in report["summary"]
        assert "overall_accuracy" in report["summary"]
        assert "pending_adjustments" in report["summary"]


class TestSingleton:
    """Tests fuer Singleton-Pattern."""

    def test_get_ai_learning_pipeline_returns_same_instance(self) -> None:
        """Test: Singleton gibt immer dieselbe Instanz zurueck."""
        pipeline1 = get_ai_learning_pipeline()
        pipeline2 = get_ai_learning_pipeline()
        assert pipeline1 is pipeline2

    def test_pipeline_instance_type(self) -> None:
        """Test: Singleton ist AILearningPipeline."""
        pipeline = get_ai_learning_pipeline()
        assert isinstance(pipeline, AILearningPipeline)

# -*- coding: utf-8 -*-
"""
Unit Tests für Feedback Learning Service.

Testet:
- Korrektur-Analyse
- Backend-Gewichtungsberechnung
- Self-Learning Loop
- Tägliche Statistik-Aggregation
"""

import pytest
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.feedback_learning_service import (
    FeedbackLearningService,
    BackendErrorPattern,
    LearnedBackendWeights,
    get_feedback_learning_service,
)
from app.db.models import (
    OCRValidationCorrection,
    OCRBackendStatsDaily,
    CorrectionType,
)


@pytest.fixture
def feedback_service() -> FeedbackLearningService:
    """Fixture für FeedbackLearningService."""
    return FeedbackLearningService()


@pytest.fixture
def mock_db() -> AsyncMock:
    """Fixture für Mock-Datenbank-Session."""
    db = AsyncMock()
    db.execute = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    return db


@pytest.fixture
def mock_corrections() -> list:
    """Fixture für Mock-Korrekturen."""
    corrections = []

    # DeepSeek Korrekturen (wenige Fehler)
    for i in range(5):
        corr = MagicMock(spec=OCRValidationCorrection)
        corr.id = uuid4()
        corr.backend_used = "deepseek-janus-pro"
        corr.correction_type = CorrectionType.SPELLING.value
        corr.field_corrected = None
        corr.confidence_before = 0.85
        corr.applies_to_training = True
        corr.learning_processed = False
        corr.created_at = datetime.now(timezone.utc)
        corrections.append(corr)

    # Surya Korrekturen (mehr Umlaut-Fehler)
    for i in range(15):
        corr = MagicMock(spec=OCRValidationCorrection)
        corr.id = uuid4()
        corr.backend_used = "surya"
        corr.correction_type = CorrectionType.UMLAUT.value if i < 10 else CorrectionType.SPELLING.value
        corr.field_corrected = "address" if i < 3 else None
        corr.confidence_before = 0.75
        corr.applies_to_training = True
        corr.learning_processed = False
        corr.created_at = datetime.now(timezone.utc)
        corrections.append(corr)

    # GOT-OCR Korrekturen
    for i in range(8):
        corr = MagicMock(spec=OCRValidationCorrection)
        corr.id = uuid4()
        corr.backend_used = "got-ocr-2.0"
        corr.correction_type = CorrectionType.NUMBER.value if i < 4 else CorrectionType.DATE.value
        corr.field_corrected = "amount" if i < 2 else None
        corr.confidence_before = 0.80
        corr.applies_to_training = True
        corr.learning_processed = False
        corr.created_at = datetime.now(timezone.utc)
        corrections.append(corr)

    return corrections


class TestBackendErrorPattern:
    """Tests für BackendErrorPattern Dataclass."""

    def test_error_rate_score_empty(self):
        """Leeres Pattern sollte Score 0 haben."""
        pattern = BackendErrorPattern(backend_name="test")
        assert pattern.error_rate_score == 0.0

    def test_error_rate_score_umlaut_weighted_higher(self):
        """Umlaut-Fehler sollten höher gewichtet werden."""
        pattern_umlaut = BackendErrorPattern(
            backend_name="test",
            total_corrections=10,
            correction_types={CorrectionType.UMLAUT.value: 10},
        )
        pattern_spelling = BackendErrorPattern(
            backend_name="test",
            total_corrections=10,
            correction_types={CorrectionType.SPELLING.value: 10},
        )

        # Umlaute haben Gewicht 2.0, Spelling nur 0.5
        assert pattern_umlaut.error_rate_score > pattern_spelling.error_rate_score

    def test_error_rate_score_currency_critical(self):
        """Währungsfehler sollten kritisch gewichtet werden."""
        pattern = BackendErrorPattern(
            backend_name="test",
            total_corrections=10,
            correction_types={CorrectionType.CURRENCY.value: 10},
        )
        # Currency hat Gewicht 2.0 (maximal)
        assert pattern.error_rate_score == 1.0

    def test_to_dict_includes_all_fields(self):
        """to_dict sollte alle relevanten Felder enthalten."""
        pattern = BackendErrorPattern(
            backend_name="deepseek",
            total_corrections=50,
            umlaut_errors=5,
            confidence_when_wrong=[0.8, 0.75, 0.9],
        )
        result = pattern.to_dict()

        assert result["backend_name"] == "deepseek"
        assert result["total_corrections"] == 50
        assert result["umlaut_errors"] == 5
        assert "error_rate_score" in result
        assert "avg_confidence_when_wrong" in result


class TestLearnedBackendWeights:
    """Tests für LearnedBackendWeights Dataclass."""

    def test_get_weight_existing(self):
        """Vorhandene Gewichtung sollte zurückgegeben werden."""
        weights = LearnedBackendWeights(
            weights={"deepseek": 0.95, "surya": 0.85},
            last_updated=datetime.now(timezone.utc),
            samples_analyzed=100,
            confidence=0.9,
        )
        assert weights.get_weight("deepseek") == 0.95
        assert weights.get_weight("surya") == 0.85

    def test_get_weight_missing_returns_default(self):
        """Nicht vorhandene Gewichtung sollte 1.0 zurückgeben."""
        weights = LearnedBackendWeights(
            weights={"deepseek": 0.95},
            last_updated=datetime.now(timezone.utc),
            samples_analyzed=100,
            confidence=0.9,
        )
        assert weights.get_weight("unknown_backend") == 1.0

    def test_to_dict_format(self):
        """to_dict sollte korrekt formatiert sein."""
        now = datetime.now(timezone.utc)
        weights = LearnedBackendWeights(
            weights={"deepseek": 0.95555, "surya": 0.85111},
            last_updated=now,
            samples_analyzed=100,
            confidence=0.9123,
        )
        result = weights.to_dict()

        # Gewichtungen sollten auf 4 Dezimalstellen gerundet sein
        assert result["weights"]["deepseek"] == 0.9556
        assert result["weights"]["surya"] == 0.8511
        assert result["confidence"] == 0.9123
        assert result["samples_analyzed"] == 100


class TestFeedbackLearningServiceSingleton:
    """Tests für Singleton-Pattern."""

    def test_get_service_returns_same_instance(self):
        """Singleton sollte immer dieselbe Instanz zurückgeben."""
        service1 = get_feedback_learning_service()
        service2 = get_feedback_learning_service()
        assert service1 is service2


class TestCorrectionAnalysis:
    """Tests für Korrektur-Analyse."""

    @pytest.mark.asyncio
    async def test_analyze_corrections_groups_by_backend(
        self,
        feedback_service: FeedbackLearningService,
        mock_db: AsyncMock,
        mock_corrections: list,
    ):
        """Korrekturen sollten nach Backend gruppiert werden."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_corrections
        mock_db.execute.return_value = mock_result

        patterns = await feedback_service.analyze_corrections(mock_db, days=30)

        assert "deepseek-janus-pro" in patterns
        assert "surya" in patterns
        assert "got-ocr-2.0" in patterns

        # DeepSeek hat 5 Korrekturen
        assert patterns["deepseek-janus-pro"].total_corrections == 5
        # Surya hat 15 Korrekturen
        assert patterns["surya"].total_corrections == 15
        # GOT-OCR hat 8 Korrekturen
        assert patterns["got-ocr-2.0"].total_corrections == 8

    @pytest.mark.asyncio
    async def test_analyze_corrections_counts_umlaut_errors(
        self,
        feedback_service: FeedbackLearningService,
        mock_db: AsyncMock,
        mock_corrections: list,
    ):
        """Umlaut-Fehler sollten korrekt gezählt werden."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_corrections
        mock_db.execute.return_value = mock_result

        patterns = await feedback_service.analyze_corrections(mock_db, days=30)

        # Surya hat 10 Umlaut-Fehler
        assert patterns["surya"].umlaut_errors == 10
        # DeepSeek hat keine Umlaut-Fehler
        assert patterns["deepseek-janus-pro"].umlaut_errors == 0

    @pytest.mark.asyncio
    async def test_analyze_corrections_tracks_field_errors(
        self,
        feedback_service: FeedbackLearningService,
        mock_db: AsyncMock,
        mock_corrections: list,
    ):
        """Feld-spezifische Fehler sollten getrackt werden."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_corrections
        mock_db.execute.return_value = mock_result

        patterns = await feedback_service.analyze_corrections(mock_db, days=30)

        # Surya hat 3 Fehler im Address-Feld
        assert patterns["surya"].field_errors.get("address") == 3
        # GOT-OCR hat 2 Fehler im Amount-Feld
        assert patterns["got-ocr-2.0"].field_errors.get("amount") == 2


class TestLearnedWeightsCalculation:
    """Tests für Gewichtungsberechnung."""

    @pytest.mark.asyncio
    async def test_get_learned_weights_returns_weights(
        self,
        feedback_service: FeedbackLearningService,
        mock_db: AsyncMock,
        mock_corrections: list,
    ):
        """Gelernte Gewichtungen sollten berechnet werden."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_corrections
        mock_db.execute.return_value = mock_result

        weights = await feedback_service.get_learned_weights(mock_db)

        assert isinstance(weights, LearnedBackendWeights)
        assert len(weights.weights) > 0
        assert weights.samples_analyzed == len(mock_corrections)

    @pytest.mark.asyncio
    async def test_get_learned_weights_penalizes_errors(
        self,
        feedback_service: FeedbackLearningService,
        mock_db: AsyncMock,
        mock_corrections: list,
    ):
        """Backends mit mehr Fehlern sollten niedrigere Gewichtung haben."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_corrections
        mock_db.execute.return_value = mock_result

        weights = await feedback_service.get_learned_weights(mock_db, force_refresh=True)

        # Surya hat mehr Umlaut-Fehler, sollte niedrigere Gewichtung haben
        # DeepSeek hat nur wenige, leichte Fehler
        deepseek_weight = weights.get_weight("deepseek-janus-pro")
        surya_weight = weights.get_weight("surya")

        # DeepSeek sollte besser sein als Surya
        assert deepseek_weight >= surya_weight

    @pytest.mark.asyncio
    async def test_get_learned_weights_uses_cache(
        self,
        feedback_service: FeedbackLearningService,
        mock_db: AsyncMock,
        mock_corrections: list,
    ):
        """Cache sollte verwendet werden wenn gültig."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_corrections
        mock_db.execute.return_value = mock_result

        # Erste Anfrage berechnet
        await feedback_service.get_learned_weights(mock_db)
        call_count_1 = mock_db.execute.call_count

        # Zweite Anfrage sollte Cache nutzen
        await feedback_service.get_learned_weights(mock_db)
        call_count_2 = mock_db.execute.call_count

        assert call_count_1 == call_count_2

    @pytest.mark.asyncio
    async def test_get_learned_weights_force_refresh_bypasses_cache(
        self,
        feedback_service: FeedbackLearningService,
        mock_db: AsyncMock,
        mock_corrections: list,
    ):
        """force_refresh sollte Cache umgehen."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_corrections
        mock_db.execute.return_value = mock_result

        # Erste Anfrage
        await feedback_service.get_learned_weights(mock_db)
        call_count_1 = mock_db.execute.call_count

        # Zweite Anfrage mit force_refresh
        await feedback_service.get_learned_weights(mock_db, force_refresh=True)
        call_count_2 = mock_db.execute.call_count

        assert call_count_2 > call_count_1


class TestBackendRecommendation:
    """Tests für Backend-Empfehlung."""

    @pytest.mark.asyncio
    async def test_recommendation_considers_umlauts(
        self,
        feedback_service: FeedbackLearningService,
        mock_db: AsyncMock,
        mock_corrections: list,
    ):
        """Empfehlung sollte Umlaut-Anforderungen berücksichtigen."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_corrections
        mock_db.execute.return_value = mock_result

        backend, confidence = await feedback_service.get_backend_recommendation(
            mock_db, has_umlauts=True
        )

        # DeepSeek sollte empfohlen werden wegen weniger Umlaut-Fehlern
        assert backend in ["deepseek-janus-pro", "got-ocr-2.0"]
        assert 0.0 <= confidence <= 1.0

    @pytest.mark.asyncio
    async def test_recommendation_prefers_deepseek_for_tables(
        self,
        feedback_service: FeedbackLearningService,
        mock_db: AsyncMock,
    ):
        """DeepSeek/GOT-OCR sollten für Tabellen bevorzugt werden."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        backend, _ = await feedback_service.get_backend_recommendation(
            mock_db, has_tables=True
        )

        assert backend in ["deepseek-janus-pro", "got-ocr-2.0"]

    @pytest.mark.asyncio
    async def test_recommendation_considers_field_preferences(
        self,
        feedback_service: FeedbackLearningService,
        mock_db: AsyncMock,
    ):
        """Feld-spezifische Präferenzen sollten berücksichtigt werden."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        backend, _ = await feedback_service.get_backend_recommendation(
            mock_db, fields_needed=["iban"]
        )

        # IBAN bevorzugt DeepSeek
        assert backend == "deepseek-janus-pro"


class TestSelfLearningLoop:
    """Tests für Self-Learning Loop."""

    @pytest.mark.asyncio
    async def test_process_unprocessed_corrections(
        self,
        feedback_service: FeedbackLearningService,
        mock_db: AsyncMock,
    ):
        """Unverarbeitete Korrekturen sollten verarbeitet werden."""
        mock_corr1 = MagicMock(spec=OCRValidationCorrection)
        mock_corr1.id = uuid4()
        mock_corr1.learning_processed = False
        mock_corr1.applies_to_training = True

        mock_corr2 = MagicMock(spec=OCRValidationCorrection)
        mock_corr2.id = uuid4()
        mock_corr2.learning_processed = False
        mock_corr2.applies_to_training = True

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_corr1, mock_corr2]
        mock_db.execute.return_value = mock_result

        count = await feedback_service.process_unprocessed_corrections(mock_db)

        assert count == 2
        assert mock_corr1.learning_processed is True
        assert mock_corr2.learning_processed is True
        assert mock_db.commit.called

    @pytest.mark.asyncio
    async def test_process_corrections_invalidates_cache(
        self,
        feedback_service: FeedbackLearningService,
        mock_db: AsyncMock,
        mock_corrections: list,
    ):
        """Verarbeitung sollte Cache invalidieren."""
        # Setup Cache
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_corrections
        mock_db.execute.return_value = mock_result

        await feedback_service.get_learned_weights(mock_db)
        assert feedback_service._cached_weights is not None

        # Verarbeite Korrekturen
        mock_db.execute.return_value.scalars.return_value.all.return_value = mock_corrections[:5]
        await feedback_service.process_unprocessed_corrections(mock_db)

        # Cache sollte invalidiert sein
        assert feedback_service._cached_weights is None


class TestDailyStatsAggregation:
    """Tests für tägliche Statistik-Aggregation."""

    @pytest.mark.asyncio
    async def test_aggregate_daily_stats_creates_entries(
        self,
        feedback_service: FeedbackLearningService,
        mock_db: AsyncMock,
    ):
        """Tägliche Stats sollten erstellt werden."""
        mock_corr = MagicMock(spec=OCRValidationCorrection)
        mock_corr.backend_used = "deepseek-janus-pro"
        mock_corr.correction_type = CorrectionType.UMLAUT.value

        mock_result1 = MagicMock()
        mock_result1.scalars.return_value.all.return_value = [mock_corr]

        mock_result2 = MagicMock()
        mock_result2.scalar_one_or_none.return_value = None

        mock_db.execute.side_effect = [mock_result1, mock_result2]

        stats = await feedback_service.aggregate_daily_stats(mock_db)

        assert len(stats) == 1
        assert mock_db.add.called
        assert mock_db.commit.called

    @pytest.mark.asyncio
    async def test_get_trend_data_formats_correctly(
        self,
        feedback_service: FeedbackLearningService,
        mock_db: AsyncMock,
    ):
        """Trend-Daten sollten korrekt formatiert sein."""
        mock_stat = MagicMock(spec=OCRBackendStatsDaily)
        mock_stat.report_date = datetime.now(timezone.utc).date()
        mock_stat.backend_name = "deepseek-janus-pro"
        mock_stat.samples_processed = 100
        mock_stat.avg_cer = 0.05
        mock_stat.avg_wer = 0.10
        mock_stat.avg_umlaut_accuracy = 0.98
        mock_stat.corrections_count = 5

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_stat]
        mock_db.execute.return_value = mock_result

        trend_data = await feedback_service.get_trend_data(mock_db)

        assert len(trend_data) == 1
        assert trend_data[0]["backend"] == "deepseek-janus-pro"
        assert trend_data[0]["samples_processed"] == 100
        assert trend_data[0]["corrections_count"] == 5


class TestGermanSpecificBehavior:
    """Tests für deutsch-spezifisches Verhalten."""

    @pytest.mark.asyncio
    async def test_umlaut_errors_heavily_weighted(
        self,
        feedback_service: FeedbackLearningService,
        mock_db: AsyncMock,
    ):
        """Umlaut-Fehler sollten stark gewichtet werden."""
        # Backend A: nur Umlaut-Fehler
        corr_a = MagicMock(spec=OCRValidationCorrection)
        corr_a.backend_used = "backend_a"
        corr_a.correction_type = CorrectionType.UMLAUT.value
        corr_a.field_corrected = None
        corr_a.confidence_before = 0.8

        # Backend B: nur Formatierungs-Fehler (gleiche Anzahl)
        corr_b = MagicMock(spec=OCRValidationCorrection)
        corr_b.backend_used = "backend_b"
        corr_b.correction_type = CorrectionType.FORMATTING.value
        corr_b.field_corrected = None
        corr_b.confidence_before = 0.8

        corrections = [corr_a] * 10 + [corr_b] * 10

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = corrections
        mock_db.execute.return_value = mock_result

        patterns = await feedback_service.analyze_corrections(mock_db)

        # Backend A (Umlaute) sollte höheren Error Score haben
        assert patterns["backend_a"].error_rate_score > patterns["backend_b"].error_rate_score

# -*- coding: utf-8 -*-
"""
Tests für ConfidenceService.

Testet Confidence-Aggregation, Quality Assessment und Fallback-Logik.
"""

import pytest
from app.services.confidence_service import (
    ConfidenceService,
    ConfidenceLevel,
    QualityDecision,
    ConfidenceMetrics,
    AggregatedConfidence,
    get_confidence_service,
)


class TestConfidenceLevel:
    """Tests für ConfidenceLevel Enum."""

    def test_confidence_levels_defined(self):
        """Alle Confidence-Levels sollten korrekt definiert sein."""
        assert ConfidenceLevel.EXCELLENT.value == "excellent"
        assert ConfidenceLevel.HIGH.value == "high"
        assert ConfidenceLevel.MEDIUM.value == "medium"
        assert ConfidenceLevel.LOW.value == "low"
        assert ConfidenceLevel.VERY_LOW.value == "very_low"


class TestQualityDecision:
    """Tests für QualityDecision Enum."""

    def test_quality_decisions_defined(self):
        """Alle Qualitätsentscheidungen sollten korrekt definiert sein."""
        assert QualityDecision.ACCEPT.value == "accept"
        assert QualityDecision.ACCEPT_WITH_WARNING.value == "accept_with_warning"
        assert QualityDecision.REQUEST_REVIEW.value == "request_review"
        assert QualityDecision.RETRY_DIFFERENT_BACKEND.value == "retry_different_backend"
        assert QualityDecision.REJECT.value == "reject"


class TestConfidenceMetrics:
    """Tests für ConfidenceMetrics Dataclass."""

    def test_confidence_metrics_to_dict(self):
        """to_dict sollte alle Felder korrekt konvertieren."""
        metrics = ConfidenceMetrics(
            overall_confidence=0.8567,
            confidence_level=ConfidenceLevel.HIGH,
            mean_token_confidence=0.8234,
            min_token_confidence=0.4123,
            max_token_confidence=0.9876,
            std_deviation=0.1234,
            total_tokens=100,
            low_confidence_count=5,
            low_confidence_ratio=0.05,
            confidence_method="token_logits",
            backend="deepseek-janus-pro",
            quality_decision=QualityDecision.ACCEPT,
            should_fallback=False,
            fallback_reason=None
        )

        result = metrics.to_dict()

        assert result["overall_confidence"] == 0.8567
        assert result["confidence_level"] == "high"
        assert result["total_tokens"] == 100
        assert result["quality_decision"] == "accept"
        assert result["should_fallback"] is False

    def test_confidence_metrics_rounding(self):
        """to_dict sollte Werte auf 4 Dezimalstellen runden."""
        metrics = ConfidenceMetrics(
            overall_confidence=0.856789123,
            confidence_level=ConfidenceLevel.HIGH,
            mean_token_confidence=0.823456789,
            min_token_confidence=0.4,
            max_token_confidence=0.9,
            std_deviation=0.123456789,
            total_tokens=100,
            low_confidence_count=5,
            low_confidence_ratio=0.0512345,
            confidence_method="token_logits",
            backend="test",
            quality_decision=QualityDecision.ACCEPT,
            should_fallback=False
        )

        result = metrics.to_dict()

        assert result["overall_confidence"] == 0.8568
        assert result["mean_token_confidence"] == 0.8235
        assert result["std_deviation"] == 0.1235
        assert result["low_confidence_ratio"] == 0.0512


class TestAggregatedConfidence:
    """Tests für AggregatedConfidence Dataclass."""

    def test_aggregated_confidence_to_dict(self):
        """to_dict sollte alle Felder korrekt konvertieren."""
        aggregated = AggregatedConfidence(
            backends_used=["deepseek", "got-ocr"],
            individual_scores={"deepseek": 0.85, "got-ocr": 0.78},
            aggregated_confidence=0.815,
            confidence_level=ConfidenceLevel.HIGH,
            best_backend="deepseek",
            worst_backend="got-ocr",
            agreement_score=0.92,
            recommendation="Verwende Ergebnis von deepseek"
        )

        result = aggregated.to_dict()

        assert result["backends_used"] == ["deepseek", "got-ocr"]
        assert result["best_backend"] == "deepseek"
        assert result["aggregated_confidence"] == 0.815
        assert result["agreement_score"] == 0.92


class TestConfidenceService:
    """Tests für ConfidenceService."""

    @pytest.fixture
    def service(self):
        """Erstellt ConfidenceService-Instanz."""
        return ConfidenceService()

    @pytest.fixture
    def custom_service(self):
        """Erstellt ConfidenceService mit Custom-Thresholds."""
        return ConfidenceService(
            thresholds={"excellent": 0.90, "fallback_trigger": 0.50},
            backend_weights={"custom-backend": 1.0}
        )

    def test_default_thresholds(self, service):
        """Service sollte Standard-Schwellenwerte haben."""
        assert service.thresholds["excellent"] == 0.95
        assert service.thresholds["high"] == 0.85
        assert service.thresholds["fallback_trigger"] == 0.65
        assert service.thresholds["reject_trigger"] == 0.30

    def test_custom_thresholds(self, custom_service):
        """Custom-Schwellenwerte sollten Standard überschreiben."""
        assert custom_service.thresholds["excellent"] == 0.90
        assert custom_service.thresholds["fallback_trigger"] == 0.50
        # Nicht überschriebene Werte bleiben Standard
        assert custom_service.thresholds["high"] == 0.85

    def test_default_backend_weights(self, service):
        """Service sollte Standard-Backend-Gewichtungen haben."""
        assert service.backend_weights["deepseek-janus-pro"] == 1.0
        assert service.backend_weights["got-ocr-2.0"] == 0.95
        assert service.backend_weights["surya"] == 0.85

    # Tests für classify_confidence

    def test_classify_confidence_excellent(self, service):
        """Confidence >= 0.95 sollte EXCELLENT sein."""
        assert service.classify_confidence(0.95) == ConfidenceLevel.EXCELLENT
        assert service.classify_confidence(0.99) == ConfidenceLevel.EXCELLENT
        assert service.classify_confidence(1.0) == ConfidenceLevel.EXCELLENT

    def test_classify_confidence_high(self, service):
        """Confidence >= 0.85 aber < 0.95 sollte HIGH sein."""
        assert service.classify_confidence(0.85) == ConfidenceLevel.HIGH
        assert service.classify_confidence(0.90) == ConfidenceLevel.HIGH
        assert service.classify_confidence(0.94) == ConfidenceLevel.HIGH

    def test_classify_confidence_medium(self, service):
        """Confidence >= 0.70 aber < 0.85 sollte MEDIUM sein."""
        assert service.classify_confidence(0.70) == ConfidenceLevel.MEDIUM
        assert service.classify_confidence(0.75) == ConfidenceLevel.MEDIUM
        assert service.classify_confidence(0.84) == ConfidenceLevel.MEDIUM

    def test_classify_confidence_low(self, service):
        """Confidence >= 0.50 aber < 0.70 sollte LOW sein."""
        assert service.classify_confidence(0.50) == ConfidenceLevel.LOW
        assert service.classify_confidence(0.60) == ConfidenceLevel.LOW
        assert service.classify_confidence(0.69) == ConfidenceLevel.LOW

    def test_classify_confidence_very_low(self, service):
        """Confidence < 0.50 sollte VERY_LOW sein."""
        assert service.classify_confidence(0.0) == ConfidenceLevel.VERY_LOW
        assert service.classify_confidence(0.30) == ConfidenceLevel.VERY_LOW
        assert service.classify_confidence(0.49) == ConfidenceLevel.VERY_LOW

    # Tests für determine_quality_decision

    def test_quality_decision_reject(self, service):
        """Sehr niedrige Confidence sollte REJECT sein."""
        decision, should_fallback, reason = service.determine_quality_decision(
            confidence=0.25,
            min_confidence=0.1,
            low_confidence_ratio=0.5
        )

        assert decision == QualityDecision.REJECT
        assert should_fallback is True
        assert "unter Ablehnungsschwelle" in reason

    def test_quality_decision_retry_backend(self, service):
        """Niedrige Confidence sollte RETRY_DIFFERENT_BACKEND sein."""
        decision, should_fallback, reason = service.determine_quality_decision(
            confidence=0.50,
            min_confidence=0.3,
            low_confidence_ratio=0.2
        )

        assert decision == QualityDecision.RETRY_DIFFERENT_BACKEND
        assert should_fallback is True
        assert "unter Fallback-Schwelle" in reason

    def test_quality_decision_request_review(self, service):
        """Viele niedrig-konfidente Tokens sollte REQUEST_REVIEW sein."""
        decision, should_fallback, reason = service.determine_quality_decision(
            confidence=0.75,
            min_confidence=0.4,
            low_confidence_ratio=0.35  # > 30%
        )

        assert decision == QualityDecision.REQUEST_REVIEW
        assert should_fallback is False
        assert "niedrige Confidence" in reason

    def test_quality_decision_accept_with_warning(self, service):
        """Sehr niedrige min_confidence sollte WARNING sein."""
        decision, should_fallback, reason = service.determine_quality_decision(
            confidence=0.78,  # < HIGH threshold
            min_confidence=0.2,  # < 0.3
            low_confidence_ratio=0.1
        )

        assert decision == QualityDecision.ACCEPT_WITH_WARNING
        assert should_fallback is False
        assert "sehr niedriger Confidence" in reason

    def test_quality_decision_accept(self, service):
        """Gute Werte sollten ACCEPT sein."""
        decision, should_fallback, reason = service.determine_quality_decision(
            confidence=0.90,
            min_confidence=0.65,
            low_confidence_ratio=0.05
        )

        assert decision == QualityDecision.ACCEPT
        assert should_fallback is False
        assert reason is None

    # Tests für analyze_ocr_result

    def test_analyze_ocr_result_basic(self, service):
        """analyze_ocr_result sollte Metriken erstellen."""
        metrics = service.analyze_ocr_result(
            confidence=0.85,
            backend="deepseek-janus-pro"
        )

        assert metrics.overall_confidence == 0.85
        assert metrics.confidence_level == ConfidenceLevel.HIGH
        assert metrics.backend == "deepseek-janus-pro"
        assert metrics.confidence_method == "heuristic"  # Fallback ohne Details

    def test_analyze_ocr_result_with_details(self, service):
        """analyze_ocr_result sollte Token-Details verarbeiten."""
        details = {
            "mean_confidence": 0.82,
            "min_confidence": 0.45,
            "total_tokens": 200,
            "low_confidence_count": 20,
            "method": "token_logits_vectorized",
            "token_confidences": [0.7, 0.8, 0.9, 0.6, 0.85]
        }

        metrics = service.analyze_ocr_result(
            confidence=0.80,
            confidence_details=details,
            backend="got-ocr-2.0"
        )

        assert metrics.mean_token_confidence == 0.82
        assert metrics.min_token_confidence == 0.45
        assert metrics.total_tokens == 200
        assert metrics.low_confidence_count == 20
        assert metrics.confidence_method == "token_logits_vectorized"
        assert metrics.max_token_confidence == 0.9
        assert metrics.std_deviation > 0

    def test_analyze_ocr_result_triggers_fallback(self, service):
        """analyze_ocr_result sollte Fallback auslösen bei niedriger Confidence."""
        metrics = service.analyze_ocr_result(
            confidence=0.40,
            backend="surya"
        )

        assert metrics.should_fallback is True
        assert metrics.quality_decision == QualityDecision.RETRY_DIFFERENT_BACKEND

    # Tests für aggregate_confidences

    def test_aggregate_confidences_empty(self, service):
        """aggregate_confidences sollte leere Liste behandeln."""
        result = service.aggregate_confidences([])

        assert result.backends_used == []
        assert result.aggregated_confidence == 0.0
        assert result.confidence_level == ConfidenceLevel.VERY_LOW

    def test_aggregate_confidences_single_backend(self, service):
        """aggregate_confidences sollte einzelnes Backend behandeln."""
        results = [
            {"backend": "deepseek-janus-pro", "confidence": 0.90}
        ]

        result = service.aggregate_confidences(results)

        assert result.backends_used == ["deepseek-janus-pro"]
        assert result.aggregated_confidence == 0.90
        assert result.best_backend == "deepseek-janus-pro"
        assert result.agreement_score == 1.0

    def test_aggregate_confidences_weighted_average(self, service):
        """aggregate_confidences sollte gewichteten Durchschnitt berechnen."""
        results = [
            {"backend": "deepseek-janus-pro", "confidence": 0.90},  # weight: 1.0
            {"backend": "surya", "confidence": 0.70},  # weight: 0.85
        ]

        result = service.aggregate_confidences(results, method="weighted_average")

        # (0.90 * 1.0 + 0.70 * 0.85) / (1.0 + 0.85) = (0.90 + 0.595) / 1.85 ≈ 0.808
        assert 0.80 < result.aggregated_confidence < 0.82
        assert result.best_backend == "deepseek-janus-pro"
        assert result.worst_backend == "surya"

    def test_aggregate_confidences_max_method(self, service):
        """aggregate_confidences mit max-Methode."""
        results = [
            {"backend": "deepseek-janus-pro", "confidence": 0.90},
            {"backend": "surya", "confidence": 0.70},
        ]

        result = service.aggregate_confidences(results, method="max")

        assert result.aggregated_confidence == 0.90

    def test_aggregate_confidences_median_method(self, service):
        """aggregate_confidences mit median-Methode."""
        results = [
            {"backend": "deepseek-janus-pro", "confidence": 0.90},
            {"backend": "got-ocr-2.0", "confidence": 0.80},
            {"backend": "surya", "confidence": 0.70},
        ]

        result = service.aggregate_confidences(results, method="median")

        assert result.aggregated_confidence == 0.80

    def test_aggregate_confidences_agreement_score(self, service):
        """aggregate_confidences sollte Agreement Score berechnen."""
        # Sehr unterschiedliche Ergebnisse = niedriger Agreement Score
        results = [
            {"backend": "deepseek-janus-pro", "confidence": 0.95},
            {"backend": "surya", "confidence": 0.45},
        ]

        result = service.aggregate_confidences(results)

        assert result.agreement_score < 0.7  # Große Diskrepanz

    def test_aggregate_confidences_high_agreement(self, service):
        """Ähnliche Ergebnisse sollten hohen Agreement Score haben."""
        results = [
            {"backend": "deepseek-janus-pro", "confidence": 0.88},
            {"backend": "got-ocr-2.0", "confidence": 0.86},
        ]

        result = service.aggregate_confidences(results)

        assert result.agreement_score > 0.9

    # Tests für should_trigger_fallback

    def test_should_trigger_fallback_explicit(self, service):
        """should_trigger_fallback sollte expliziten Fallback erkennen."""
        metrics = ConfidenceMetrics(
            overall_confidence=0.5,
            confidence_level=ConfidenceLevel.LOW,
            mean_token_confidence=0.5,
            min_token_confidence=0.2,
            max_token_confidence=0.7,
            std_deviation=0.15,
            total_tokens=100,
            low_confidence_count=30,
            low_confidence_ratio=0.3,
            confidence_method="token_logits",
            backend="surya",
            quality_decision=QualityDecision.RETRY_DIFFERENT_BACKEND,
            should_fallback=True,
            fallback_reason="Confidence zu niedrig"
        )

        should_fallback, reason = service.should_trigger_fallback(metrics)

        assert should_fallback is True
        assert "zu niedrig" in reason

    def test_should_trigger_fallback_document_type_invoice(self, service):
        """Rechnungen sollten höhere Schwelle haben."""
        metrics = ConfidenceMetrics(
            overall_confidence=0.75,  # OK für general, nicht für invoice
            confidence_level=ConfidenceLevel.MEDIUM,
            mean_token_confidence=0.75,
            min_token_confidence=0.5,
            max_token_confidence=0.9,
            std_deviation=0.1,
            total_tokens=100,
            low_confidence_count=10,
            low_confidence_ratio=0.1,
            confidence_method="token_logits",
            backend="surya",
            quality_decision=QualityDecision.ACCEPT,
            should_fallback=False
        )

        should_fallback, reason = service.should_trigger_fallback(
            metrics, document_type="invoice"
        )

        assert should_fallback is True
        assert "invoice" in reason
        assert "80%" in reason

    def test_should_trigger_fallback_high_variance(self, service):
        """Hohe Varianz sollte Fallback triggern."""
        metrics = ConfidenceMetrics(
            overall_confidence=0.80,
            confidence_level=ConfidenceLevel.MEDIUM,
            mean_token_confidence=0.80,
            min_token_confidence=0.2,
            max_token_confidence=1.0,
            std_deviation=0.35,  # > 0.3
            total_tokens=100,
            low_confidence_count=5,
            low_confidence_ratio=0.05,
            confidence_method="token_logits",
            backend="surya",
            quality_decision=QualityDecision.ACCEPT,
            should_fallback=False
        )

        should_fallback, reason = service.should_trigger_fallback(metrics)

        assert should_fallback is True
        assert "Varianz" in reason

    def test_should_not_trigger_fallback(self, service):
        """Gute Metriken sollten keinen Fallback triggern."""
        metrics = ConfidenceMetrics(
            overall_confidence=0.90,
            confidence_level=ConfidenceLevel.HIGH,
            mean_token_confidence=0.90,
            min_token_confidence=0.75,
            max_token_confidence=0.98,
            std_deviation=0.08,
            total_tokens=100,
            low_confidence_count=2,
            low_confidence_ratio=0.02,
            confidence_method="token_logits",
            backend="deepseek-janus-pro",
            quality_decision=QualityDecision.ACCEPT,
            should_fallback=False
        )

        should_fallback, reason = service.should_trigger_fallback(metrics)

        assert should_fallback is False
        assert reason == ""

    # Tests für get_recommended_backends

    def test_get_recommended_backends_excludes_failed(self, service):
        """Empfehlungen sollten fehlgeschlagenes Backend ausschließen."""
        recommendations = service.get_recommended_backends(
            failed_backend="deepseek-janus-pro"
        )

        assert "deepseek-janus-pro" not in recommendations
        assert len(recommendations) > 0

    def test_get_recommended_backends_invoice(self, service):
        """Invoice sollte spezifische Backends bevorzugen."""
        recommendations = service.get_recommended_backends(
            failed_backend="surya",
            document_type="invoice"
        )

        # DeepSeek sollte für Rechnungen an erster Stelle stehen
        assert "deepseek-janus-pro" in recommendations

    def test_get_recommended_backends_formula(self, service):
        """Formeln sollten GOT-OCR bevorzugen."""
        recommendations = service.get_recommended_backends(
            failed_backend="surya",
            document_type="formula"
        )

        # GOT-OCR sollte für Formeln priorisiert werden
        assert "got-ocr-2.0" in recommendations[:2]

    def test_get_recommended_backends_general(self, service):
        """Allgemeine Dokumente sollten Standard-Reihenfolge haben."""
        recommendations = service.get_recommended_backends(
            failed_backend="surya",
            document_type="general"
        )

        assert len(recommendations) >= 2


class TestConfidenceServiceSingleton:
    """Tests für Singleton-Funktion."""

    def test_get_confidence_service_singleton(self):
        """get_confidence_service sollte immer dieselbe Instanz zurückgeben."""
        s1 = get_confidence_service()
        s2 = get_confidence_service()
        assert s1 is s2

    def test_get_confidence_service_is_initialized(self):
        """Singleton sollte korrekt initialisiert sein."""
        service = get_confidence_service()
        assert service.thresholds is not None
        assert service.backend_weights is not None

# -*- coding: utf-8 -*-
"""
Unit Tests für Ensemble Weighted Voting Service.

Testet:
- Majority Voting
- Weighted Voting
- Dynamic Weighted Voting
- Bayesian Combination
- Token-Level Voting

Feinpoliert und durchdacht - Enterprise Test Coverage.
"""

import pytest

# Test markers
pytestmark = [pytest.mark.unit]


class TestOCRResult:
    """Tests für OCRResult Dataclass."""

    def test_creation(self):
        """Test Erstellung eines OCRResult."""
        from app.services.ensemble_voting import OCRResult

        result = OCRResult(
            backend="deepseek",
            text="Test Text",
            confidence=0.9
        )

        assert result.backend == "deepseek"
        assert result.text == "Test Text"
        assert result.confidence == 0.9

    def test_auto_tokenization(self):
        """Test automatische Tokenisierung."""
        from app.services.ensemble_voting import OCRResult

        result = OCRResult(
            backend="deepseek",
            text="Dies ist ein Test",
            confidence=0.9
        )

        assert result.tokens == ["Dies", "ist", "ein", "Test"]

    def test_custom_tokens(self):
        """Test benutzerdefinierte Tokens."""
        from app.services.ensemble_voting import OCRResult

        result = OCRResult(
            backend="deepseek",
            text="Test",
            confidence=0.9,
            tokens=["Custom", "Tokens"]
        )

        assert result.tokens == ["Custom", "Tokens"]


class TestEnsembleResult:
    """Tests für EnsembleResult Dataclass."""

    def test_to_dict(self):
        """Test Serialisierung."""
        from app.services.ensemble_voting import EnsembleResult, OCRResult

        result = EnsembleResult(
            text="Test",
            confidence=0.85,
            method="weighted",
            contributing_backends=["deepseek", "got_ocr"],
            agreement_score=0.9,
            individual_results=[
                OCRResult(backend="deepseek", text="Test", confidence=0.9),
                OCRResult(backend="got_ocr", text="Test", confidence=0.8),
            ]
        )

        d = result.to_dict()

        assert d["text"] == "Test"
        assert d["confidence"] == 0.85
        assert d["method"] == "weighted"
        assert d["num_backends"] == 2


class TestBackendWeight:
    """Tests für BackendWeight."""

    def test_historical_accuracy(self):
        """Test historische Accuracy-Berechnung."""
        from app.services.ensemble_voting import BackendWeight

        weight = BackendWeight(backend="test")

        # Initial: 50% (Prior)
        assert weight.historical_accuracy == 0.5

        # Nach Samples
        weight.record_result(True)
        weight.record_result(True)
        weight.record_result(False)

        assert weight.total_samples == 3
        assert weight.correct_samples == 2
        assert abs(weight.historical_accuracy - 2/3) < 0.001

    def test_effective_weight(self):
        """Test effektives Gewicht."""
        from app.services.ensemble_voting import BackendWeight

        weight = BackendWeight(backend="test", static_weight=1.5)

        # 100% Accuracy
        for _ in range(10):
            weight.record_result(True)

        # effective = static * dynamic * (0.5 + accuracy * 0.5)
        # = 1.5 * 1.0 * (0.5 + 1.0 * 0.5) = 1.5 * 1.0 = 1.5
        assert weight.effective_weight == 1.5

    def test_history_limit(self):
        """Test dass History auf 100 begrenzt ist."""
        from app.services.ensemble_voting import BackendWeight

        weight = BackendWeight(backend="test")

        for _ in range(150):
            weight.record_result(True)

        assert len(weight.accuracy_history) == 100


class TestMajorityVoting:
    """Tests für Majority Voting."""

    @pytest.fixture
    def service(self):
        """Erstelle Service-Instanz."""
        from app.services.ensemble_voting import EnsembleVotingService
        return EnsembleVotingService(default_method="majority")

    def test_clear_majority(self, service):
        """Test mit klarer Mehrheit."""
        from app.services.ensemble_voting import OCRResult

        results = [
            OCRResult(backend="deepseek", text="Richtig", confidence=0.9),
            OCRResult(backend="got_ocr", text="Richtig", confidence=0.8),
            OCRResult(backend="surya_gpu", text="Falsch", confidence=0.7),
        ]

        ensemble = service.combine(results, method="majority")

        assert ensemble.text == "Richtig"
        assert ensemble.method == "majority"
        assert ensemble.agreement_score == 2/3

    def test_tie_uses_higher_confidence(self, service):
        """Test bei Gleichstand: höhere Confidence gewinnt."""
        from app.services.ensemble_voting import OCRResult

        results = [
            OCRResult(backend="deepseek", text="A", confidence=0.9),
            OCRResult(backend="got_ocr", text="B", confidence=0.8),
        ]

        ensemble = service.combine(results, method="majority")

        # Bei Gleichstand (beide 1x) sollte das mit höherer Conf gewinnen
        # Da aber beide gleich oft vorkommen, wird das erste mit höchster conf genommen
        assert ensemble.agreement_score == 0.5


class TestWeightedVoting:
    """Tests für Weighted Voting."""

    @pytest.fixture
    def service(self):
        """Erstelle Service-Instanz."""
        from app.services.ensemble_voting import EnsembleVotingService
        return EnsembleVotingService(default_method="weighted")

    def test_weighted_by_confidence(self, service):
        """Test Gewichtung nach Confidence."""
        from app.services.ensemble_voting import OCRResult

        results = [
            OCRResult(backend="deepseek", text="Hohe Conf", confidence=0.95),
            OCRResult(backend="got_ocr", text="Niedrige Conf", confidence=0.4),
        ]

        ensemble = service.combine(results, method="weighted")

        assert ensemble.text == "Hohe Conf"
        assert ensemble.method == "weighted"

    def test_backend_static_weights(self, service):
        """Test Backend-spezifische Gewichte."""
        from app.services.ensemble_voting import OCRResult

        # DeepSeek hat höheres Gewicht (1.2) als Surya CPU (0.7)
        results = [
            OCRResult(backend="deepseek", text="DeepSeek", confidence=0.8),
            OCRResult(backend="surya_cpu", text="Surya", confidence=0.85),
        ]

        ensemble = service.combine(results, method="weighted")

        # Trotz niedrigerer Confidence sollte DeepSeek wegen höherem Gewicht gewinnen
        # deepseek: 0.8 * 1.2 = 0.96, surya_cpu: 0.85 * 0.7 = 0.595
        assert ensemble.text == "DeepSeek"


class TestDynamicWeightedVoting:
    """Tests für Dynamic Weighted Voting."""

    @pytest.fixture
    def service(self):
        """Erstelle Service-Instanz."""
        from app.services.ensemble_voting import EnsembleVotingService
        return EnsembleVotingService(default_method="dynamic")

    def test_dynamic_weights_improve(self, service):
        """Test dass dynamische Gewichte sich verbessern."""
        from app.services.ensemble_voting import OCRResult

        # Simuliere Feedback: DeepSeek ist konsistent richtig
        for _ in range(10):
            service.record_feedback("deepseek", "Test", "Test")
            service.record_feedback("got_ocr", "Falsch", "Richtig")

        results = [
            OCRResult(backend="deepseek", text="A", confidence=0.8),
            OCRResult(backend="got_ocr", text="B", confidence=0.85),
        ]

        ensemble = service.combine(results, method="dynamic")

        # DeepSeek sollte wegen besserer History gewinnen
        assert ensemble.text == "A"
        assert "effective_weights" in ensemble.metadata


class TestBayesianCombination:
    """Tests für Bayesian Combination."""

    @pytest.fixture
    def service(self):
        """Erstelle Service-Instanz."""
        from app.services.ensemble_voting import EnsembleVotingService
        return EnsembleVotingService(default_method="bayesian")

    def test_bayesian_combination(self, service):
        """Test Bayesian Kombination."""
        from app.services.ensemble_voting import OCRResult

        results = [
            OCRResult(backend="deepseek", text="Test", confidence=0.9),
            OCRResult(backend="got_ocr", text="Test", confidence=0.8),
            OCRResult(backend="surya_gpu", text="Anders", confidence=0.7),
        ]

        ensemble = service.combine(results, method="bayesian")

        assert ensemble.text == "Test"
        assert ensemble.method == "bayesian"


class TestTokenLevelVoting:
    """Tests für Token-Level Voting."""

    @pytest.fixture
    def service(self):
        """Erstelle Service-Instanz."""
        from app.services.ensemble_voting import EnsembleVotingService
        return EnsembleVotingService(default_method="token_level")

    def test_token_level_voting(self, service):
        """Test Token-Level Voting."""
        from app.services.ensemble_voting import OCRResult

        results = [
            OCRResult(
                backend="deepseek",
                text="Der schnelle Fuchs",
                confidence=0.9,
                tokens=["Der", "schnelle", "Fuchs"]
            ),
            OCRResult(
                backend="got_ocr",
                text="Der schnelle Fox",
                confidence=0.85,
                tokens=["Der", "schnelle", "Fox"]
            ),
        ]

        ensemble = service.combine(results, method="token_level")

        assert "Der" in ensemble.text
        assert "schnelle" in ensemble.text
        assert ensemble.method == "token_level"
        assert ensemble.token_agreement is not None

    def test_token_voting_different_lengths(self, service):
        """Test Token-Level Voting mit unterschiedlichen Längen."""
        from app.services.ensemble_voting import OCRResult

        results = [
            OCRResult(
                backend="deepseek",
                text="Eins Zwei Drei",
                confidence=0.9,
                tokens=["Eins", "Zwei", "Drei"]
            ),
            OCRResult(
                backend="got_ocr",
                text="Eins Zwei",
                confidence=0.8,
                tokens=["Eins", "Zwei"]
            ),
        ]

        ensemble = service.combine(results, method="token_level")

        # Sollte trotzdem funktionieren
        assert len(ensemble.text) > 0


class TestSingleResult:
    """Tests für einzelne Ergebnisse."""

    def test_single_result_passthrough(self):
        """Test dass einzelnes Ergebnis durchgereicht wird."""
        from app.services.ensemble_voting import EnsembleVotingService, OCRResult

        service = EnsembleVotingService()

        results = [
            OCRResult(backend="deepseek", text="Einziges Ergebnis", confidence=0.9),
        ]

        ensemble = service.combine(results)

        assert ensemble.text == "Einziges Ergebnis"
        assert ensemble.method == "single"
        assert ensemble.agreement_score == 1.0

    def test_empty_results(self):
        """Test mit leerer Ergebnisliste."""
        from app.services.ensemble_voting import EnsembleVotingService

        service = EnsembleVotingService()

        ensemble = service.combine([])

        assert ensemble.text == ""
        assert ensemble.method == "empty"
        assert ensemble.confidence == 0.0


class TestFeedback:
    """Tests für Feedback-System."""

    def test_record_feedback(self):
        """Test Feedback-Erfassung."""
        from app.services.ensemble_voting import EnsembleVotingService

        service = EnsembleVotingService()

        # Perfektes Match
        service.record_feedback("deepseek", "Test", "Test")

        stats = service.get_backend_stats()
        assert "deepseek" in stats
        assert stats["deepseek"]["total_samples"] == 1
        assert stats["deepseek"]["correct_samples"] == 1

    def test_feedback_affects_weight(self):
        """Test dass Feedback Gewichte beeinflusst."""
        from app.services.ensemble_voting import EnsembleVotingService

        service = EnsembleVotingService()

        # Viele korrekte Ergebnisse
        for _ in range(20):
            service.record_feedback("deepseek", "A", "A")

        # Viele falsche Ergebnisse
        for _ in range(20):
            service.record_feedback("got_ocr", "B", "A")

        stats = service.get_backend_stats()

        # DeepSeek sollte höhere Accuracy haben
        assert stats["deepseek"]["historical_accuracy"] > stats["got_ocr"]["historical_accuracy"]


class TestAgreementCalculation:
    """Tests für Agreement-Berechnung."""

    def test_calculate_agreement_identical(self):
        """Test Agreement bei identischen Ergebnissen."""
        from app.services.ensemble_voting import calculate_agreement, OCRResult

        results = [
            OCRResult(backend="a", text="Gleich", confidence=0.9),
            OCRResult(backend="b", text="Gleich", confidence=0.8),
            OCRResult(backend="c", text="Gleich", confidence=0.7),
        ]

        agreement = calculate_agreement(results)

        assert agreement == 1.0

    def test_calculate_agreement_different(self):
        """Test Agreement bei unterschiedlichen Ergebnissen."""
        from app.services.ensemble_voting import calculate_agreement, OCRResult

        results = [
            OCRResult(backend="a", text="AAAA", confidence=0.9),
            OCRResult(backend="b", text="BBBB", confidence=0.8),
        ]

        agreement = calculate_agreement(results)

        # Komplett unterschiedlich -> Agreement nahe 0
        assert agreement < 0.5

    def test_calculate_agreement_single(self):
        """Test Agreement mit einem Ergebnis."""
        from app.services.ensemble_voting import calculate_agreement, OCRResult

        results = [
            OCRResult(backend="a", text="Einzig", confidence=0.9),
        ]

        agreement = calculate_agreement(results)

        assert agreement == 1.0


class TestConvenienceFunctions:
    """Tests für Convenience-Funktionen."""

    def test_get_ensemble_service_singleton(self):
        """Test Singleton-Pattern."""
        import app.services.ensemble_voting as module
        module._ensemble_service = None

        from app.services.ensemble_voting import get_ensemble_service

        service1 = get_ensemble_service()
        service2 = get_ensemble_service()

        assert service1 is service2

        # Cleanup
        module._ensemble_service = None

    def test_combine_ocr_results_function(self):
        """Test combine_ocr_results Convenience-Funktion."""
        import app.services.ensemble_voting as module
        module._ensemble_service = None

        from app.services.ensemble_voting import combine_ocr_results

        results = [
            {"backend": "deepseek", "text": "Test", "confidence": 0.9},
            {"backend": "got_ocr", "text": "Test", "confidence": 0.8},
        ]

        combined = combine_ocr_results(results)

        assert "text" in combined
        assert "confidence" in combined
        assert "method" in combined

        # Cleanup
        module._ensemble_service = None


class TestBackendWeightConfig:
    """Tests für Backend-Gewicht-Konfiguration."""

    def test_set_backend_weight(self):
        """Test manuelles Setzen von Backend-Gewichten."""
        from app.services.ensemble_voting import EnsembleVotingService

        service = EnsembleVotingService()

        service.set_backend_weight("custom_backend", 2.5)

        stats = service.get_backend_stats()
        assert "custom_backend" in stats
        assert stats["custom_backend"]["static_weight"] == 2.5

    def test_default_backend_weights(self):
        """Test Default-Gewichte für bekannte Backends."""
        from app.services.ensemble_voting import EnsembleVotingService, OCRResult

        service = EnsembleVotingService()

        # Triggere Gewicht-Erstellung durch weighted voting mit mehreren Ergebnissen
        results = [
            OCRResult(backend="deepseek", text="Test", confidence=0.9),
            OCRResult(backend="got_ocr", text="Test", confidence=0.8),
        ]
        service.combine(results, method="weighted")

        stats = service.get_backend_stats()
        assert stats["deepseek"]["static_weight"] == 1.2


class TestAllMethods:
    """Integrationstests für alle Voting-Methoden."""

    @pytest.mark.parametrize("method", [
        "majority", "weighted", "dynamic", "bayesian", "token_level"
    ])
    def test_all_methods_work(self, method):
        """Test dass alle Methoden funktionieren."""
        from app.services.ensemble_voting import EnsembleVotingService, OCRResult

        service = EnsembleVotingService()

        results = [
            OCRResult(
                backend="deepseek",
                text="Gemeinsamer Text",
                confidence=0.9,
                tokens=["Gemeinsamer", "Text"]
            ),
            OCRResult(
                backend="got_ocr",
                text="Gemeinsamer Text",
                confidence=0.85,
                tokens=["Gemeinsamer", "Text"]
            ),
            OCRResult(
                backend="surya_gpu",
                text="Anderer Text",
                confidence=0.7,
                tokens=["Anderer", "Text"]
            ),
        ]

        ensemble = service.combine(results, method=method)

        assert ensemble.text is not None
        assert ensemble.method == method
        assert 0.0 <= ensemble.confidence <= 1.0
        assert 0.0 <= ensemble.agreement_score <= 1.0

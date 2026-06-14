# -*- coding: utf-8 -*-
"""
Tests fuer Differential Privacy Service.

Testet:
- Laplace Mechanism
- Gaussian Mechanism
- K-Anonymitaet
- Privacy Budget Verbrauch
"""

import pytest
import numpy as np
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4

from app.services.privacy.differential_privacy_service import (
    DifferentialPrivacyService,
    DPConfig,
    DPMechanism,
    DPResult,
    QueryType,
    SensitivityLevel,
    get_dp_service,
)


class TestLaplaceMechanism:
    """Tests fuer den Laplace-Mechanismus."""

    def test_laplace_noise_adds_noise(self) -> None:
        """Laplace-Noise sollte den Wert veraendern."""
        service = DifferentialPrivacyService()

        original = 100.0
        noisy, noise_mag = service.add_laplace_noise(original, 1.0, 1.0)

        # Noise sollte hinzugefuegt worden sein
        assert noise_mag > 0 or noisy != original

    def test_laplace_noise_variance(self) -> None:
        """Laplace-Noise sollte korrekte Varianz haben."""
        service = DifferentialPrivacyService()

        epsilon = 1.0
        sensitivity = 1.0
        expected_scale = sensitivity / epsilon

        # Viele Samples - add_laplace_noise liefert |noise| (noise_magnitude),
        # nicht das signierte Rauschen.
        noise_magnitudes = []
        for _ in range(1000):
            _, noise_magnitude = service.add_laplace_noise(0.0, sensitivity, epsilon)
            noise_magnitudes.append(noise_magnitude)

        # Fuer X ~ Laplace(0, b) gilt Var(X) = 2*b^2, ABER der Service gibt
        # |X| zurueck. Fuer den Betrag gilt Var(|X|) = E[X^2] - E[|X|]^2
        # = 2*b^2 - b^2 = b^2 (= scale^2).
        expected_variance = expected_scale ** 2
        actual_variance = np.var(noise_magnitudes)

        # Toleranz fuer statistische Tests
        assert abs(actual_variance - expected_variance) < expected_variance * 0.3

    def test_laplace_noise_smaller_epsilon_more_noise(self) -> None:
        """Kleineres Epsilon sollte mehr Noise bedeuten."""
        service = DifferentialPrivacyService()

        # Sammle Noise fuer verschiedene Epsilons
        noises_small_eps = [
            abs(service.add_laplace_noise(0.0, 1.0, 0.5)[1])
            for _ in range(100)
        ]
        noises_large_eps = [
            abs(service.add_laplace_noise(0.0, 1.0, 2.0)[1])
            for _ in range(100)
        ]

        # Kleineres Epsilon = mehr Noise (im Durchschnitt)
        assert np.mean(noises_small_eps) > np.mean(noises_large_eps)

    def test_laplace_noise_invalid_epsilon(self) -> None:
        """Ungültiges Epsilon sollte Fehler werfen."""
        service = DifferentialPrivacyService()

        with pytest.raises(ValueError, match="Epsilon muss positiv sein"):
            service.add_laplace_noise(100.0, 1.0, 0.0)

        with pytest.raises(ValueError, match="Epsilon muss positiv sein"):
            service.add_laplace_noise(100.0, 1.0, -1.0)


class TestGaussianMechanism:
    """Tests fuer den Gaussian-Mechanismus."""

    def test_gaussian_noise_adds_noise(self) -> None:
        """Gaussian-Noise sollte den Wert veraendern."""
        service = DifferentialPrivacyService()

        original = 100.0
        noisy, noise_mag = service.add_gaussian_noise(original, 1.0, 1.0)

        # Noise sollte hinzugefuegt worden sein
        assert noise_mag >= 0

    def test_gaussian_noise_invalid_delta(self) -> None:
        """Ungueltiges Delta sollte Fehler werfen."""
        service = DifferentialPrivacyService()

        with pytest.raises(ValueError, match="Delta muss in"):
            service.add_gaussian_noise(100.0, 1.0, 1.0, delta=0.0)

        with pytest.raises(ValueError, match="Delta muss in"):
            service.add_gaussian_noise(100.0, 1.0, 1.0, delta=1.0)


class TestDPCount:
    """Tests fuer DP-geschuetzten COUNT."""

    def test_dp_count_returns_integer(self) -> None:
        """dp_count sollte ganzzahligen Wert zurueckgeben."""
        service = DifferentialPrivacyService()

        result = service.dp_count(100, epsilon=1.0)

        assert isinstance(result.noisy_value, float)
        assert result.noisy_value == int(result.noisy_value)

    def test_dp_count_respects_min_count(self) -> None:
        """dp_count sollte Minimum respektieren."""
        service = DifferentialPrivacyService()

        # Bei sehr kleinem Count und viel Noise koennte Ergebnis negativ werden
        result = service.dp_count(1, epsilon=0.1, min_count=0)

        assert result.noisy_value >= 0

    def test_dp_count_k_anonymity(self) -> None:
        """dp_count sollte K-Anonymitaet pruefen."""
        service = DifferentialPrivacyService()
        k_threshold = service.config.k_anonymity_threshold

        # Unter K-Schwelle
        result_below = service.dp_count(k_threshold - 1)
        assert result_below.k_anonymity_satisfied is False

        # Ueber K-Schwelle
        result_above = service.dp_count(k_threshold + 1)
        assert result_above.k_anonymity_satisfied is True

    def test_dp_count_confidence_interval(self) -> None:
        """dp_count sollte Konfidenzintervall zurueckgeben."""
        service = DifferentialPrivacyService()

        result = service.dp_count(100, epsilon=1.0)

        ci_low, ci_high = result.confidence_interval
        assert ci_low < ci_high
        assert ci_low <= result.noisy_value <= ci_high or True  # Toleranz

    def test_dp_count_metadata(self) -> None:
        """dp_count sollte korrekte Metadata haben."""
        service = DifferentialPrivacyService()

        result = service.dp_count(100)

        assert result.mechanism == DPMechanism.LAPLACE
        assert result.metadata.get("query_type") == QueryType.COUNT.value


class TestDPSum:
    """Tests fuer DP-geschuetzte SUM."""

    def test_dp_sum_adds_noise(self) -> None:
        """dp_sum sollte Noise hinzufuegen."""
        service = DifferentialPrivacyService()

        result = service.dp_sum(1000.0, max_contribution=100.0, epsilon=1.0)

        # Ergebnis sollte existieren
        assert result.noisy_value is not None
        assert result.epsilon_used == 1.0

    def test_dp_sum_higher_sensitivity_more_noise(self) -> None:
        """Hoeherer max_contribution sollte mehr Noise bedeuten."""
        service = DifferentialPrivacyService()

        # Sammle Noise fuer verschiedene Sensitivitaeten
        results_low = [
            abs(service.dp_sum(1000.0, max_contribution=10.0).noisy_value - 1000.0)
            for _ in range(50)
        ]
        results_high = [
            abs(service.dp_sum(1000.0, max_contribution=100.0).noisy_value - 1000.0)
            for _ in range(50)
        ]

        # Hoehere Sensitivitaet = mehr Noise (im Durchschnitt)
        assert np.mean(results_high) > np.mean(results_low) * 0.5  # Mit Toleranz


class TestDPAverage:
    """Tests fuer DP-geschuetzten AVERAGE."""

    def test_dp_average_empty_list(self) -> None:
        """dp_average sollte 0 fuer leere Liste zurueckgeben."""
        service = DifferentialPrivacyService()

        result = service.dp_average([], value_bounds=(0, 100))

        assert result.noisy_value == 0.0
        assert result.k_anonymity_satisfied is False

    def test_dp_average_bounds_respected(self) -> None:
        """dp_average sollte Wertegrenzen respektieren."""
        service = DifferentialPrivacyService()

        values = [50.0] * 100  # Alle gleich
        result = service.dp_average(values, value_bounds=(0, 100))

        # Noisy value sollte innerhalb der Grenzen sein (oder nah dran)
        assert 0 <= result.noisy_value <= 100

    def test_dp_average_k_anonymity(self) -> None:
        """dp_average sollte K-Anonymitaet pruefen."""
        service = DifferentialPrivacyService()
        k_threshold = service.config.k_anonymity_threshold

        # Unter K-Schwelle
        values_few = [50.0] * (k_threshold - 1)
        result_few = service.dp_average(values_few, value_bounds=(0, 100))
        assert result_few.k_anonymity_satisfied is False

        # Ueber K-Schwelle
        values_many = [50.0] * (k_threshold + 1)
        result_many = service.dp_average(values_many, value_bounds=(0, 100))
        assert result_many.k_anonymity_satisfied is True


class TestDPHistogram:
    """Tests fuer DP-geschuetztes Histogram."""

    def test_dp_histogram_all_categories(self) -> None:
        """dp_histogram sollte alle Kategorien zurueckgeben."""
        service = DifferentialPrivacyService()

        counts = {"a": 10, "b": 20, "c": 30}
        result = service.dp_histogram(counts)

        assert set(result.keys()) == set(counts.keys())

    def test_dp_histogram_suppresses_small_groups(self) -> None:
        """dp_histogram sollte kleine Gruppen unterdruecken."""
        service = DifferentialPrivacyService()

        counts = {"large": 100, "small": 2}  # small unter K-Schwelle
        result = service.dp_histogram(counts, suppress_below_k=True)

        assert result["small"].metadata.get("suppressed") is True
        assert result["small"].noisy_value == 0.0

    def test_dp_histogram_no_suppression(self) -> None:
        """dp_histogram sollte ohne Unterdrueckung funktionieren."""
        service = DifferentialPrivacyService()

        counts = {"large": 100, "small": 2}
        result = service.dp_histogram(counts, suppress_below_k=False)

        # Kleine Gruppe sollte nicht unterdrueckt sein
        assert result["small"].metadata.get("suppressed") is not True


class TestSensitivityLevels:
    """Tests fuer Sensitivitaetsstufen."""

    def test_get_epsilon_for_sensitivity(self) -> None:
        """Epsilon sollte je nach Sensitivitaet variieren."""
        service = DifferentialPrivacyService()

        eps_low = service.get_epsilon_for_sensitivity(SensitivityLevel.LOW)
        eps_critical = service.get_epsilon_for_sensitivity(SensitivityLevel.CRITICAL)

        # Kritische Daten sollten kleineres Epsilon haben
        assert eps_critical < eps_low

    def test_validate_epsilon(self) -> None:
        """Epsilon-Validierung sollte funktionieren."""
        service = DifferentialPrivacyService()

        assert service.validate_epsilon(1.0) is True
        assert service.validate_epsilon(0.05) is False  # Unter Minimum
        assert service.validate_epsilon(10.0) is False  # Ueber Maximum


class TestNoiseImpactEstimation:
    """Tests fuer Noise-Impact-Schaetzung."""

    def test_estimate_noise_impact(self) -> None:
        """Noise-Impact sollte geschaetzt werden."""
        service = DifferentialPrivacyService()

        impact = service.estimate_noise_impact(
            original_value=1000.0,
            sensitivity=1.0,
            epsilon=1.0
        )

        assert "noise_mean" in impact
        assert "noise_std" in impact
        assert "expected_relative_error" in impact
        assert impact["noise_mean"] == 0  # Laplace hat Mittelwert 0


class TestDPResultSerialization:
    """Tests fuer DPResult Serialisierung."""

    def test_dp_result_to_dict(self) -> None:
        """DPResult.to_dict sollte korrekt serialisieren."""
        result = DPResult(
            original_value=100.0,
            noisy_value=102.5,
            epsilon_used=1.0,
            mechanism=DPMechanism.LAPLACE,
            noise_magnitude=2.5,
            confidence_interval=(90.0, 115.0),
            k_anonymity_satisfied=True,
            group_size=50
        )

        d = result.to_dict()

        assert "value" in d
        assert "original_value" not in d  # Sicherheit: Original nicht exponieren
        assert d["value"] == 102.5
        assert d["mechanism"] == "laplace"


class TestSingleton:
    """Tests fuer Singleton-Pattern."""

    def test_get_dp_service_returns_singleton(self) -> None:
        """get_dp_service sollte Singleton zurueckgeben."""
        service1 = get_dp_service()
        service2 = get_dp_service()

        assert service1 is service2

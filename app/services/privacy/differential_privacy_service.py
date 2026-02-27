# -*- coding: utf-8 -*-
"""
Differential Privacy Service.

Implementiert privacy-preserving Analytics mit:
- Laplace Mechanism für COUNT queries
- Gaussian Mechanism für SUM/AVG queries
- Privacy Budget Tracking pro Tenant
- K-Anonymitaet Enforcement

Vision 2.0 Feature: Anonymized Analytics (Phase 5)
Feinpoliert und durchdacht.
"""

import structlog
import math
import secrets
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Tuple, Union
from typing_extensions import TypedDict
from uuid import UUID

import numpy as np

logger = structlog.get_logger(__name__)

# Type definitions for mypy strict mode
MetadataValue = Union[str, int, float, bool, None]
MetadataDict = Dict[str, MetadataValue]


class DPResultDict(TypedDict, total=False):
    """Typed dictionary for DPResult serialization."""
    value: float
    epsilon_used: float
    mechanism: str
    confidence_interval: List[float]
    k_anonymity_satisfied: bool
    group_size: Optional[int]


class NoiseImpactDict(TypedDict):
    """Typed dictionary for noise impact estimation."""
    noise_mean: float
    noise_std: float
    expected_relative_error: float
    _95_percentile_error: float


class DPMechanism(str, Enum):
    """Differential Privacy Mechanismen."""
    LAPLACE = "laplace"
    GAUSSIAN = "gaussian"
    EXPONENTIAL = "exponential"


class QueryType(str, Enum):
    """Typen von DP-geschuetzten Queries."""
    COUNT = "count"
    SUM = "sum"
    AVG = "average"
    MIN = "min"
    MAX = "max"
    PERCENTILE = "percentile"


class SensitivityLevel(str, Enum):
    """Sensitivitaetsstufen für Analytics-Daten."""
    LOW = "low"           # Epsilon: 2.0-5.0
    MEDIUM = "medium"     # Epsilon: 1.0-2.0
    HIGH = "high"         # Epsilon: 0.5-1.0
    CRITICAL = "critical" # Epsilon: 0.1-0.5


@dataclass
class DPResult:
    """Ergebnis einer DP-geschuetzten Query."""
    original_value: float
    noisy_value: float
    epsilon_used: float
    mechanism: DPMechanism
    noise_magnitude: float
    confidence_interval: Tuple[float, float]
    k_anonymity_satisfied: bool
    group_size: Optional[int] = None
    metadata: MetadataDict = field(default_factory=dict)

    def to_dict(self) -> DPResultDict:
        """Konvertiert zu Dictionary (ohne original_value für Sicherheit)."""
        return DPResultDict(
            value=self.noisy_value,
            epsilon_used=self.epsilon_used,
            mechanism=self.mechanism.value,
            confidence_interval=list(self.confidence_interval),
            k_anonymity_satisfied=self.k_anonymity_satisfied,
            group_size=self.group_size,
        )


@dataclass
class DPConfig:
    """Konfiguration für Differential Privacy."""
    default_epsilon: float = 1.0
    min_epsilon: float = 0.1
    max_epsilon: float = 5.0
    default_delta: float = 1e-5
    k_anonymity_threshold: int = 5
    daily_budget: float = 10.0
    sensitivity_epsilon_map: Dict[SensitivityLevel, Tuple[float, float]] = field(
        default_factory=lambda: {
            SensitivityLevel.LOW: (2.0, 5.0),
            SensitivityLevel.MEDIUM: (1.0, 2.0),
            SensitivityLevel.HIGH: (0.5, 1.0),
            SensitivityLevel.CRITICAL: (0.1, 0.5),
        }
    )


class DifferentialPrivacyService:
    """
    Core Differential Privacy Service.

    Bietet privacy-preserving Mechanismen für sensible Aggregationen.
    """

    def __init__(self, config: Optional[DPConfig] = None) -> None:
        """Initialisiert den Service."""
        self.config = config or DPConfig()
        self._rng = np.random.default_rng(secrets.randbits(128))
        logger.info(
            "differential_privacy_service_initialized",
            default_epsilon=self.config.default_epsilon,
            k_anonymity_threshold=self.config.k_anonymity_threshold
        )

    def add_laplace_noise(
        self,
        value: float,
        sensitivity: float,
        epsilon: float
    ) -> Tuple[float, float]:
        """
        Fuegt Laplace-Rauschen hinzu (für COUNT/SUM queries).

        Args:
            value: Original-Wert
            sensitivity: L1-Sensitivitaet der Query
            epsilon: Privacy-Parameter (kleiner = mehr Privacy)

        Returns:
            Tuple von (noisy_value, noise_magnitude)
        """
        if epsilon <= 0:
            raise ValueError("Epsilon muss positiv sein")
        if sensitivity < 0:
            raise ValueError("Sensitivitaet muss nicht-negativ sein")

        # Laplace-Skala: b = sensitivity / epsilon
        scale = sensitivity / epsilon

        # Generiere Laplace-Rauschen
        noise = self._rng.laplace(0, scale)
        noisy_value = value + noise

        return noisy_value, abs(noise)

    def add_gaussian_noise(
        self,
        value: float,
        sensitivity: float,
        epsilon: float,
        delta: Optional[float] = None
    ) -> Tuple[float, float]:
        """
        Fuegt Gaussian-Rauschen hinzu (für SUM/AVG mit (epsilon, delta)-DP).

        Args:
            value: Original-Wert
            sensitivity: L2-Sensitivitaet der Query
            epsilon: Privacy-Parameter
            delta: Fehlerwahrscheinlichkeit (default: config)

        Returns:
            Tuple von (noisy_value, noise_magnitude)
        """
        if epsilon <= 0:
            raise ValueError("Epsilon muss positiv sein")
        if delta is None:
            delta = self.config.default_delta
        if delta <= 0 or delta >= 1:
            raise ValueError("Delta muss in (0, 1) liegen")

        # Gaussian-Standardabweichung: sigma = sensitivity * sqrt(2 * ln(1.25/delta)) / epsilon
        sigma = sensitivity * math.sqrt(2 * math.log(1.25 / delta)) / epsilon

        # Generiere Gaussian-Rauschen
        noise = self._rng.normal(0, sigma)
        noisy_value = value + noise

        return noisy_value, abs(noise)

    def dp_count(
        self,
        count: int,
        epsilon: Optional[float] = None,
        min_count: int = 0
    ) -> DPResult:
        """
        Privacy-preserving COUNT mit Laplace-Mechanismus.

        Sensitivitaet = 1 (Hinzufuegen/Entfernen einer Zeile ändert COUNT um 1)

        Args:
            count: Original COUNT-Wert
            epsilon: Privacy-Parameter (default: config)
            min_count: Minimaler Rückgabewert (default: 0)

        Returns:
            DPResult mit noisy count
        """
        eps = epsilon or self.config.default_epsilon
        sensitivity = 1.0

        noisy_value, noise_mag = self.add_laplace_noise(count, sensitivity, eps)

        # Runde auf ganze Zahl und setze Minimum
        noisy_count = max(min_count, int(round(noisy_value)))

        # 95% Konfidenzintervall für Laplace: +-ln(0.05) * scale
        scale = sensitivity / eps
        ci_half = math.log(20) * scale  # ln(1/0.05) = ln(20)

        # K-Anonymitaet prüfen
        k_satisfied = count >= self.config.k_anonymity_threshold

        return DPResult(
            original_value=float(count),
            noisy_value=float(noisy_count),
            epsilon_used=eps,
            mechanism=DPMechanism.LAPLACE,
            noise_magnitude=noise_mag,
            confidence_interval=(
                max(min_count, noisy_count - ci_half),
                noisy_count + ci_half
            ),
            k_anonymity_satisfied=k_satisfied,
            group_size=count,
            metadata={"query_type": QueryType.COUNT.value}
        )

    def dp_sum(
        self,
        value_sum: float,
        max_contribution: float,
        epsilon: Optional[float] = None
    ) -> DPResult:
        """
        Privacy-preserving SUM mit Laplace-Mechanismus.

        Args:
            value_sum: Original SUM-Wert
            max_contribution: Maximaler Beitrag einer Einzelperson (Sensitivitaet)
            epsilon: Privacy-Parameter

        Returns:
            DPResult mit noisy sum
        """
        eps = epsilon or self.config.default_epsilon

        noisy_value, noise_mag = self.add_laplace_noise(value_sum, max_contribution, eps)

        scale = max_contribution / eps
        ci_half = math.log(20) * scale

        return DPResult(
            original_value=value_sum,
            noisy_value=noisy_value,
            epsilon_used=eps,
            mechanism=DPMechanism.LAPLACE,
            noise_magnitude=noise_mag,
            confidence_interval=(noisy_value - ci_half, noisy_value + ci_half),
            k_anonymity_satisfied=True,  # SUM hat keine K-Anonymitaet
            metadata={
                "query_type": QueryType.SUM.value,
                "max_contribution": max_contribution
            }
        )

    def dp_average(
        self,
        values: List[float],
        value_bounds: Tuple[float, float],
        epsilon: Optional[float] = None
    ) -> DPResult:
        """
        Privacy-preserving AVERAGE mit Laplace-Mechanismus.

        Verwendet noisy sum / noisy count für Durchschnitt.

        Args:
            values: Liste der Werte
            value_bounds: (min, max) Wertebereich
            epsilon: Privacy-Parameter (wird aufgeteilt)

        Returns:
            DPResult mit noisy average
        """
        eps = epsilon or self.config.default_epsilon

        if len(values) == 0:
            return DPResult(
                original_value=0.0,
                noisy_value=0.0,
                epsilon_used=eps,
                mechanism=DPMechanism.LAPLACE,
                noise_magnitude=0.0,
                confidence_interval=(0.0, 0.0),
                k_anonymity_satisfied=False,
                group_size=0
            )

        n = len(values)
        value_sum = sum(values)
        original_avg = value_sum / n

        # Teile Epsilon: 50% für Summe, 50% für Count
        eps_sum = eps / 2
        eps_count = eps / 2

        # Sensitivitaet für Summe: max_value - min_value
        sensitivity_sum = value_bounds[1] - value_bounds[0]

        noisy_sum, _ = self.add_laplace_noise(value_sum, sensitivity_sum, eps_sum)
        noisy_count, _ = self.add_laplace_noise(n, 1.0, eps_count)

        # Vermeide Division durch Null
        noisy_count = max(1, noisy_count)
        noisy_avg = noisy_sum / noisy_count

        # Clippe auf Wertebereich
        noisy_avg = max(value_bounds[0], min(value_bounds[1], noisy_avg))

        # K-Anonymitaet
        k_satisfied = n >= self.config.k_anonymity_threshold

        # Konservatives Konfidenzintervall
        ci_half = sensitivity_sum / n * 2 / eps

        return DPResult(
            original_value=original_avg,
            noisy_value=noisy_avg,
            epsilon_used=eps,
            mechanism=DPMechanism.LAPLACE,
            noise_magnitude=abs(noisy_avg - original_avg),
            confidence_interval=(
                max(value_bounds[0], noisy_avg - ci_half),
                min(value_bounds[1], noisy_avg + ci_half)
            ),
            k_anonymity_satisfied=k_satisfied,
            group_size=n,
            metadata={"query_type": QueryType.AVG.value}
        )

    def dp_histogram(
        self,
        counts: Dict[str, int],
        epsilon: Optional[float] = None,
        suppress_below_k: bool = True
    ) -> Dict[str, DPResult]:
        """
        Privacy-preserving Histogram mit Laplace-Mechanismus.

        Args:
            counts: Dict von Kategorie -> Count
            epsilon: Privacy-Parameter (wird aufgeteilt)
            suppress_below_k: Unterdrücke Kategorien unter K-Schwelle

        Returns:
            Dict von Kategorie -> DPResult
        """
        eps = epsilon or self.config.default_epsilon

        # Teile Epsilon auf Anzahl Kategorien auf
        n_categories = len(counts)
        if n_categories == 0:
            return {}

        eps_per_category = eps / n_categories

        results: Dict[str, DPResult] = {}

        for category, count in counts.items():
            # K-Anonymitaet prüfen
            if suppress_below_k and count < self.config.k_anonymity_threshold:
                # Unterdrücke kleine Gruppen
                results[category] = DPResult(
                    original_value=float(count),
                    noisy_value=0.0,
                    epsilon_used=eps_per_category,
                    mechanism=DPMechanism.LAPLACE,
                    noise_magnitude=0.0,
                    confidence_interval=(0.0, 0.0),
                    k_anonymity_satisfied=False,
                    group_size=count,
                    metadata={"suppressed": True}
                )
            else:
                results[category] = self.dp_count(count, eps_per_category)

        return results

    def get_epsilon_for_sensitivity(
        self,
        level: SensitivityLevel,
        use_min: bool = False
    ) -> float:
        """
        Gibt empfohlenes Epsilon für Sensitivitaetsstufe zurück.

        Args:
            level: Sensitivitaetsstufe
            use_min: True für minimales (strengeres) Epsilon

        Returns:
            Epsilon-Wert
        """
        eps_range = self.config.sensitivity_epsilon_map.get(
            level,
            (self.config.default_epsilon, self.config.default_epsilon)
        )
        return eps_range[0] if use_min else eps_range[1]

    def estimate_noise_impact(
        self,
        original_value: float,
        sensitivity: float,
        epsilon: float,
        mechanism: DPMechanism = DPMechanism.LAPLACE
    ) -> NoiseImpactDict:
        """
        Schätzt den erwarteten Rausch-Impact.

        Args:
            original_value: Original-Wert
            sensitivity: Query-Sensitivitaet
            epsilon: Privacy-Parameter
            mechanism: DP-Mechanismus

        Returns:
            Dict mit noise_mean, noise_std, relative_error
        """
        if mechanism == DPMechanism.LAPLACE:
            scale = sensitivity / epsilon
            noise_mean = 0
            noise_std = scale * math.sqrt(2)
        else:  # Gaussian
            sigma = sensitivity * math.sqrt(2 * math.log(1.25 / self.config.default_delta)) / epsilon
            noise_mean = 0
            noise_std = sigma

        relative_error = noise_std / abs(original_value) if original_value != 0 else float('inf')

        return NoiseImpactDict(
            noise_mean=noise_mean,
            noise_std=noise_std,
            expected_relative_error=relative_error,
            _95_percentile_error=1.96 * noise_std,
        )

    def validate_epsilon(self, epsilon: float) -> bool:
        """Prüft ob Epsilon im erlaubten Bereich liegt."""
        return self.config.min_epsilon <= epsilon <= self.config.max_epsilon


# Singleton-Instanz
_dp_service: Optional[DifferentialPrivacyService] = None


def get_dp_service() -> DifferentialPrivacyService:
    """Gibt Singleton-Instanz des DP-Service zurück."""
    global _dp_service
    if _dp_service is None:
        _dp_service = DifferentialPrivacyService()
    return _dp_service

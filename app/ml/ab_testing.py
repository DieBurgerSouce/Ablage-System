# -*- coding: utf-8 -*-
"""
A/B Testing Framework für ML-Routing.

Ermöglicht:
- Experimente mit verschiedenen Routing-Strategien
- Traffic-Splitting (50/50, 90/10, etc.)
- Statistische Signifikanz-Tests
- Automatische Gewinner-Erkennung

Feinpoliert und durchdacht - Datengetriebene Optimierung.
"""

import hashlib
import json
import random
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import structlog

logger = structlog.get_logger(__name__)

# Thread-Safety für Singleton
_ab_test_manager_lock = threading.Lock()


class ExperimentStatus(str, Enum):
    """Status eines Experiments."""
    DRAFT = "draft"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class AllocationMethod(str, Enum):
    """Methode zur Varianten-Zuweisung."""
    RANDOM = "random"  # Zufällig bei jedem Request
    STICKY = "sticky"  # Konsistent pro Dokument-ID
    ROUND_ROBIN = "round_robin"  # Abwechselnd


@dataclass
class Variant:
    """Eine Variante in einem A/B Test."""
    name: str
    description: str
    weight: float  # Anteil des Traffics (0-1)
    config: Dict[str, Any]  # Konfiguration (z.B. welches Backend)

    # Metriken
    samples: int = 0
    conversions: int = 0  # Erfolgreiche OCR-Verarbeitungen
    total_latency_ms: float = 0.0
    total_accuracy: float = 0.0
    errors: int = 0

    @property
    def conversion_rate(self) -> float:
        """Erfolgsrate."""
        return self.conversions / self.samples if self.samples > 0 else 0.0

    @property
    def avg_latency_ms(self) -> float:
        """Durchschnittliche Latenz."""
        return self.total_latency_ms / self.samples if self.samples > 0 else 0.0

    @property
    def avg_accuracy(self) -> float:
        """Durchschnittliche Genauigkeit."""
        return self.total_accuracy / self.conversions if self.conversions > 0 else 0.0

    @property
    def error_rate(self) -> float:
        """Fehlerrate."""
        return self.errors / self.samples if self.samples > 0 else 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiere zu Dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "weight": self.weight,
            "config": self.config,
            "metrics": {
                "samples": self.samples,
                "conversions": self.conversions,
                "conversion_rate": self.conversion_rate,
                "avg_latency_ms": self.avg_latency_ms,
                "avg_accuracy": self.avg_accuracy,
                "error_rate": self.error_rate,
            },
        }


@dataclass
class Experiment:
    """Ein A/B Test Experiment."""
    experiment_id: str
    name: str
    description: str
    variants: List[Variant]
    status: ExperimentStatus = ExperimentStatus.DRAFT
    allocation_method: AllocationMethod = AllocationMethod.STICKY

    # Zeitrahmen
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.now)

    # Konfiguration
    min_samples_per_variant: int = 100
    confidence_level: float = 0.95  # 95% Konfidenz

    # Ergebnisse
    winner: Optional[str] = None
    significance_reached: bool = False

    # Tracking
    _allocation_counter: int = field(default=0, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def __post_init__(self) -> None:
        """Validiere Experiment nach Initialisierung."""
        self._validate_weights()

    def _validate_weights(self) -> None:
        """Stelle sicher, dass Gewichte 1.0 ergeben."""
        total_weight = sum(v.weight for v in self.variants)
        if abs(total_weight - 1.0) > 0.01:
            # Normalisiere Gewichte
            for v in self.variants:
                v.weight = v.weight / total_weight

    def allocate_variant(self, document_id: str) -> Variant:
        """
        Weise Dokument einer Variante zu.

        Args:
            document_id: Dokument-ID für konsistente Zuweisung

        Returns:
            Zugewiesene Variante
        """
        if self.allocation_method == AllocationMethod.STICKY:
            return self._sticky_allocation(document_id)
        elif self.allocation_method == AllocationMethod.ROUND_ROBIN:
            return self._round_robin_allocation()
        else:
            return self._random_allocation()

    def _sticky_allocation(self, document_id: str) -> Variant:
        """Konsistente Zuweisung basierend auf Dokument-ID."""
        # Hash der Dokument-ID für deterministischen Bucket
        hash_value = int(hashlib.md5(document_id.encode()).hexdigest(), 16)
        bucket = (hash_value % 10000) / 10000  # 0-1

        cumulative = 0.0
        for variant in self.variants:
            cumulative += variant.weight
            if bucket < cumulative:
                return variant

        return self.variants[-1]

    def _random_allocation(self) -> Variant:
        """Zufällige Zuweisung."""
        r = random.random()
        cumulative = 0.0

        for variant in self.variants:
            cumulative += variant.weight
            if r < cumulative:
                return variant

        return self.variants[-1]

    def _round_robin_allocation(self) -> Variant:
        """Abwechselnde Zuweisung."""
        with self._lock:
            idx = self._allocation_counter % len(self.variants)
            self._allocation_counter += 1
            return self.variants[idx]

    def record_result(
        self,
        variant_name: str,
        success: bool,
        latency_ms: float,
        accuracy: Optional[float] = None,
    ) -> None:
        """
        Erfasse Ergebnis für eine Variante.

        Args:
            variant_name: Name der Variante
            success: War Verarbeitung erfolgreich?
            latency_ms: Verarbeitungszeit in Millisekunden
            accuracy: OCR-Genauigkeit (0-1)
        """
        variant = next((v for v in self.variants if v.name == variant_name), None)
        if not variant:
            logger.warning("unbekannte_variante", variant_name=variant_name)
            return

        with self._lock:
            variant.samples += 1
            variant.total_latency_ms += latency_ms

            if success:
                variant.conversions += 1
                if accuracy is not None:
                    variant.total_accuracy += accuracy
            else:
                variant.errors += 1

        # Check for winner
        self._check_significance()

    def _check_significance(self) -> None:
        """Prüfe statistische Signifikanz."""
        if len(self.variants) < 2:
            return

        # Check minimum samples
        if any(v.samples < self.min_samples_per_variant for v in self.variants):
            return

        # Two-proportion z-test
        control = self.variants[0]
        treatment = self.variants[1]

        try:
            z_score, p_value = self._two_proportion_z_test(
                control.conversions, control.samples,
                treatment.conversions, treatment.samples,
            )

            if p_value < (1 - self.confidence_level):
                self.significance_reached = True

                if treatment.conversion_rate > control.conversion_rate:
                    self.winner = treatment.name
                else:
                    self.winner = control.name

                logger.info(
                    f"Experiment {self.experiment_id}: Signifikanz erreicht! "
                    f"Gewinner: {self.winner} (p={p_value:.4f})"
                )

        except Exception as e:
            logger.debug("signifikanz_test_fehlgeschlagen", error=str(e))

    def _two_proportion_z_test(
        self,
        x1: int, n1: int,
        x2: int, n2: int,
    ) -> Tuple[float, float]:
        """
        Two-proportion z-test.

        Returns:
            (z_score, p_value)
        """
        import math

        if n1 == 0 or n2 == 0:
            return 0.0, 1.0

        p1 = x1 / n1
        p2 = x2 / n2

        # Pooled proportion
        p_pool = (x1 + x2) / (n1 + n2)

        # Standard error
        se = math.sqrt(p_pool * (1 - p_pool) * (1/n1 + 1/n2))

        if se == 0:
            return 0.0, 1.0

        # Z-score
        z = (p1 - p2) / se

        # Two-tailed p-value (approximation)
        p_value = 2 * (1 - self._standard_normal_cdf(abs(z)))

        return z, p_value

    def _standard_normal_cdf(self, x: float) -> float:
        """Standard normal CDF approximation."""
        import math
        return 0.5 * (1 + math.erf(x / math.sqrt(2)))

    def get_summary(self) -> Dict[str, Any]:
        """Hole Experiment-Zusammenfassung."""
        return {
            "experiment_id": self.experiment_id,
            "name": self.name,
            "status": self.status.value,
            "variants": [v.to_dict() for v in self.variants],
            "total_samples": sum(v.samples for v in self.variants),
            "winner": self.winner,
            "significance_reached": self.significance_reached,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
        }

    def to_json(self) -> str:
        """Serialisiere zu JSON."""
        return json.dumps(self.get_summary(), indent=2)


class ABTestManager:
    """
    Manager für A/B Tests.

    Features:
    - Mehrere gleichzeitige Experimente
    - Persistenz der Ergebnisse
    - Automatische Abschaltung bei Signifikanz
    - Prometheus Metriken Integration
    """

    def __init__(
        self,
        storage_path: Optional[Path] = None,
        auto_conclude: bool = True,
    ) -> None:
        """
        Initialisiere A/B Test Manager.

        Args:
            storage_path: Pfad für Experiment-Daten
            auto_conclude: Automatisch abschließen bei Signifikanz
        """
        self.storage_path = storage_path or Path("data/ab_tests")
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.auto_conclude = auto_conclude

        self._experiments: Dict[str, Experiment] = {}
        self._lock = threading.Lock()

        # Load existing experiments
        self._load_experiments()

        logger.info("ABTestManager initialisiert")

    def create_experiment(
        self,
        name: str,
        description: str,
        variants: List[Dict[str, Any]],
        allocation_method: str = "sticky",
        min_samples: int = 100,
        duration_days: Optional[int] = None,
    ) -> Experiment:
        """
        Erstelle neues Experiment.

        Args:
            name: Name des Experiments
            description: Beschreibung
            variants: Liste von Varianten-Konfigurationen
            allocation_method: Zuweisungsmethode
            min_samples: Minimum Samples pro Variante
            duration_days: Laufzeit in Tagen (optional)

        Returns:
            Erstelltes Experiment

        Raises:
            ValueError: Bei ungültigen Parametern
        """
        # Input Validation
        if not name or not name.strip():
            raise ValueError("Experiment-Name darf nicht leer sein")
        name = name.strip()
        if len(name) > 100:
            raise ValueError("Experiment-Name darf maximal 100 Zeichen haben")

        if not variants or len(variants) < 2:
            raise ValueError("Mindestens 2 Varianten erforderlich")
        if len(variants) > 10:
            raise ValueError("Maximal 10 Varianten erlaubt")

        if min_samples < 10:
            raise ValueError("min_samples muss mindestens 10 sein")
        if min_samples > 1_000_000:
            raise ValueError("min_samples darf maximal 1.000.000 sein")

        if duration_days is not None:
            if duration_days < 1:
                raise ValueError("duration_days muss mindestens 1 sein")
            if duration_days > 365:
                raise ValueError("duration_days darf maximal 365 sein")

        valid_methods = {"random", "sticky", "round_robin"}
        if allocation_method not in valid_methods:
            raise ValueError(f"allocation_method muss einer von {valid_methods} sein")

        # Validate variant structure
        for i, v in enumerate(variants):
            if not isinstance(v, dict):
                raise ValueError(f"Variante {i} muss ein Dictionary sein")
            if "name" not in v or not v["name"].strip():
                raise ValueError(f"Variante {i} benötigt einen Namen")
            if len(v.get("name", "")) > 50:
                raise ValueError(f"Varianten-Name {i} darf maximal 50 Zeichen haben")
            weight = v.get("weight", 1.0 / len(variants))
            if not isinstance(weight, (int, float)) or weight < 0 or weight > 1:
                raise ValueError(f"Variante {i}: weight muss zwischen 0 und 1 sein")

        experiment_id = self._generate_experiment_id(name)

        variant_objects = [
            Variant(
                name=v["name"].strip(),
                description=v.get("description", "")[:500],  # Max 500 chars
                weight=v.get("weight", 1.0 / len(variants)),
                config=v.get("config", {}),
            )
            for v in variants
        ]

        end_time = None
        if duration_days:
            end_time = datetime.now() + timedelta(days=duration_days)

        experiment = Experiment(
            experiment_id=experiment_id,
            name=name,
            description=description,
            variants=variant_objects,
            allocation_method=AllocationMethod(allocation_method),
            min_samples_per_variant=min_samples,
            end_time=end_time,
        )

        with self._lock:
            self._experiments[experiment_id] = experiment

        self._save_experiment(experiment)

        logger.info("experiment_erstellt", experiment_id=experiment_id)
        return experiment

    def start_experiment(self, experiment_id: str) -> bool:
        """
        Starte ein Experiment.

        Args:
            experiment_id: Experiment-ID

        Returns:
            True wenn erfolgreich gestartet
        """
        experiment = self._experiments.get(experiment_id)
        if not experiment:
            logger.warning("experiment_nicht_gefunden", experiment_id=experiment_id)
            return False

        if experiment.status != ExperimentStatus.DRAFT:
            logger.warning("experiment_start_nicht_moeglich", status=experiment.status.value)
            return False

        experiment.status = ExperimentStatus.RUNNING
        experiment.start_time = datetime.now()
        self._save_experiment(experiment)

        logger.info("experiment_gestartet", experiment_id=experiment_id)
        return True

    def get_variant(
        self,
        experiment_id: str,
        document_id: str,
    ) -> Optional[Variant]:
        """
        Hole Variante für ein Dokument.

        Args:
            experiment_id: Experiment-ID
            document_id: Dokument-ID

        Returns:
            Zugewiesene Variante oder None
        """
        experiment = self._experiments.get(experiment_id)
        if not experiment:
            return None

        if experiment.status != ExperimentStatus.RUNNING:
            return None

        # Check if experiment expired
        if experiment.end_time and datetime.now() > experiment.end_time:
            self.conclude_experiment(experiment_id)
            return None

        return experiment.allocate_variant(document_id)

    def record_result(
        self,
        experiment_id: str,
        variant_name: str,
        success: bool,
        latency_ms: float,
        accuracy: Optional[float] = None,
    ) -> None:
        """
        Erfasse Experiment-Ergebnis.

        Args:
            experiment_id: Experiment-ID
            variant_name: Name der Variante
            success: Erfolgreiche Verarbeitung?
            latency_ms: Verarbeitungszeit
            accuracy: OCR-Genauigkeit
        """
        experiment = self._experiments.get(experiment_id)
        if not experiment:
            return

        if experiment.status != ExperimentStatus.RUNNING:
            return

        experiment.record_result(variant_name, success, latency_ms, accuracy)

        # Auto-conclude if significance reached
        if self.auto_conclude and experiment.significance_reached:
            self.conclude_experiment(experiment_id)

        # Periodic save
        if sum(v.samples for v in experiment.variants) % 50 == 0:
            self._save_experiment(experiment)

    def conclude_experiment(self, experiment_id: str) -> Optional[str]:
        """
        Schließe Experiment ab.

        Args:
            experiment_id: Experiment-ID

        Returns:
            Name des Gewinners oder None
        """
        experiment = self._experiments.get(experiment_id)
        if not experiment:
            return None

        experiment.status = ExperimentStatus.COMPLETED
        experiment.end_time = datetime.now()

        # Determine winner if not already set
        if not experiment.winner:
            best_variant = max(
                experiment.variants,
                key=lambda v: v.conversion_rate,
            )
            experiment.winner = best_variant.name

        self._save_experiment(experiment)

        logger.info(
            f"Experiment abgeschlossen: {experiment_id}, "
            f"Gewinner: {experiment.winner}"
        )

        return experiment.winner

    def get_experiment(self, experiment_id: str) -> Optional[Experiment]:
        """Hole Experiment nach ID."""
        return self._experiments.get(experiment_id)

    def list_experiments(
        self,
        status: Optional[ExperimentStatus] = None,
    ) -> List[Experiment]:
        """Liste alle Experimente."""
        experiments = list(self._experiments.values())

        if status:
            experiments = [e for e in experiments if e.status == status]

        return experiments

    def get_active_experiments(self) -> List[Experiment]:
        """Hole alle laufenden Experimente."""
        return self.list_experiments(ExperimentStatus.RUNNING)

    def _generate_experiment_id(self, name: str) -> str:
        """Generiere eindeutige Experiment-ID."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        name_slug = name.lower().replace(" ", "_")[:20]
        return f"exp_{name_slug}_{timestamp}"

    def _save_experiment(self, experiment: Experiment) -> None:
        """Speichere Experiment."""
        filepath = self.storage_path / f"{experiment.experiment_id}.json"
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(experiment.to_json())

    def _load_experiments(self) -> None:
        """Lade gespeicherte Experimente."""
        for filepath in self.storage_path.glob("exp_*.json"):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)

                variants = [
                    Variant(
                        name=v["name"],
                        description=v.get("description", ""),
                        weight=v["weight"],
                        config=v.get("config", {}),
                        samples=v.get("metrics", {}).get("samples", 0),
                        conversions=v.get("metrics", {}).get("conversions", 0),
                    )
                    for v in data.get("variants", [])
                ]

                experiment = Experiment(
                    experiment_id=data["experiment_id"],
                    name=data["name"],
                    description=data.get("description", ""),
                    variants=variants,
                    status=ExperimentStatus(data["status"]),
                    winner=data.get("winner"),
                    significance_reached=data.get("significance_reached", False),
                )

                if data.get("start_time"):
                    experiment.start_time = datetime.fromisoformat(data["start_time"])
                if data.get("end_time"):
                    experiment.end_time = datetime.fromisoformat(data["end_time"])

                self._experiments[experiment.experiment_id] = experiment

            except Exception as e:
                logger.warning("experiment_laden_fehlgeschlagen", filepath=str(filepath), error=str(e))


# Singleton instance
_ab_test_manager: Optional[ABTestManager] = None


def get_ab_test_manager() -> ABTestManager:
    """
    Hole globale ABTestManager Instanz.

    Thread-safe mit double-checked locking.
    """
    global _ab_test_manager

    # Fast path: bereits initialisiert
    if _ab_test_manager is not None:
        return _ab_test_manager

    # Slow path: Thread-safe Initialisierung
    with _ab_test_manager_lock:
        # Double-check nach Lock-Erwerb
        if _ab_test_manager is None:
            logger.info("ab_test_manager_initialisierung")
            _ab_test_manager = ABTestManager()
            experiment_count = len(_ab_test_manager._experiments)
            logger.info(
                "ab_test_manager_initialisiert",
                loaded_experiments=experiment_count,
            )

    return _ab_test_manager


# Convenience functions
def create_routing_experiment(
    name: str,
    control_backend: str,
    treatment_backend: str,
    traffic_split: Tuple[float, float] = (0.5, 0.5),
) -> Experiment:
    """
    Erstelle schnell ein Routing-Experiment.

    Args:
        name: Name des Experiments
        control_backend: Kontroll-Backend
        treatment_backend: Test-Backend
        traffic_split: Traffic-Aufteilung (control, treatment)

    Returns:
        Erstelltes und gestartetes Experiment
    """
    manager = get_ab_test_manager()

    experiment = manager.create_experiment(
        name=name,
        description=f"Vergleich: {control_backend} vs {treatment_backend}",
        variants=[
            {
                "name": "control",
                "description": f"Kontrollgruppe: {control_backend}",
                "weight": traffic_split[0],
                "config": {"backend": control_backend},
            },
            {
                "name": "treatment",
                "description": f"Testgruppe: {treatment_backend}",
                "weight": traffic_split[1],
                "config": {"backend": treatment_backend},
            },
        ],
    )

    manager.start_experiment(experiment.experiment_id)
    return experiment

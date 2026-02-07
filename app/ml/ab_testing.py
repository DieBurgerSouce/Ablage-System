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
import math
import random
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import structlog
from pydantic import BaseModel, Field, field_validator


# =============================================================================
# Pydantic Validierungsmodelle fuer sichere JSON-Deserialisierung
# =============================================================================

class QualityMetricsSchema(BaseModel):
    """Validierungsschema fuer Quality Metrics aus JSON."""
    benchmark_samples: int = 0
    avg_cer: float = Field(default=0.0, ge=0.0, le=1.0)
    avg_wer: float = Field(default=0.0, ge=0.0, le=1.0)
    avg_umlaut_accuracy: float = Field(default=0.0, ge=0.0, le=1.0)


class VariantMetricsSchema(BaseModel):
    """Validierungsschema fuer Variant Metrics."""
    samples: int = 0
    conversions: int = 0


class VariantSchema(BaseModel):
    """Validierungsschema fuer Experiment-Varianten."""
    name: str = Field(..., min_length=1, max_length=100)
    description: str = ""
    weight: float = Field(..., ge=0.0, le=1.0)
    config: Dict[str, Any] = Field(default_factory=dict)
    metrics: VariantMetricsSchema = Field(default_factory=VariantMetricsSchema)
    quality_metrics: QualityMetricsSchema = Field(default_factory=QualityMetricsSchema)


class ExperimentSchema(BaseModel):
    """Validierungsschema fuer Experiment-JSON-Dateien.

    Validiert:
    - Pflichtfelder (experiment_id, name, status)
    - Feldtypen und Wertebereiche
    - Varianten-Struktur
    """
    experiment_id: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=200)
    description: str = ""
    status: str = Field(..., pattern="^(draft|running|paused|completed|archived)$")
    variants: List[VariantSchema] = Field(default_factory=list)
    winner: Optional[str] = None
    significance_reached: bool = False
    start_time: Optional[str] = None
    end_time: Optional[str] = None

    @field_validator("start_time", "end_time")
    @classmethod
    def validate_iso_datetime(cls, v: Optional[str]) -> Optional[str]:
        """Validiere ISO-8601 Datumsformat."""
        if v is None:
            return v
        try:
            datetime.fromisoformat(v)
            return v
        except ValueError:
            raise ValueError(f"Ungueltiges Datumsformat: {v}")


def validate_experiment_json(data: Dict[str, Any]) -> ExperimentSchema:
    """Validiere Experiment-JSON mit Pydantic.

    Args:
        data: Deserialisierte JSON-Daten

    Returns:
        Validiertes ExperimentSchema

    Raises:
        pydantic.ValidationError: Bei Validierungsfehlern
    """
    return ExperimentSchema.model_validate(data)

logger = structlog.get_logger(__name__)


class SafeJSONEncoder(json.JSONEncoder):
    """
    JSON Encoder, der nicht-serialisierbare Typen sicher konvertiert.

    Behandelt:
    - numpy Typen (int64, float64, ndarray)
    - datetime Objekte
    - Enum Werte
    - NaN und Infinity
    - Beliebige Objekte via __dict__ oder str()
    """

    def default(self, obj: object) -> object:
        # numpy Typen
        try:
            import numpy as np
            if isinstance(obj, (np.integer, np.int64, np.int32)):
                return int(obj)
            if isinstance(obj, (np.floating, np.float64, np.float32)):
                value = float(obj)
                # NaN und Infinity zu None konvertieren
                if math.isnan(value) or math.isinf(value):
                    return None
                return value
            if isinstance(obj, np.ndarray):
                return obj.tolist()
        except ImportError:
            pass

        # datetime Objekte
        if isinstance(obj, datetime):
            return obj.isoformat()

        # timedelta
        if isinstance(obj, timedelta):
            return obj.total_seconds()

        # Enum Werte
        if isinstance(obj, Enum):
            return obj.value

        # Path Objekte
        if isinstance(obj, Path):
            return str(obj)

        # Objekte mit __dict__
        if hasattr(obj, "__dict__"):
            return obj.__dict__

        # Fallback: String-Repräsentation
        try:
            return str(obj)
        except Exception:
            return f"<non-serializable: {type(obj).__name__}>"

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

    # Ground-Truth Quality Metrics (NEU)
    benchmark_samples: int = 0
    total_cer: float = 0.0  # Character Error Rate Summe
    total_wer: float = 0.0  # Word Error Rate Summe
    total_umlaut_accuracy: float = 0.0  # Umlaut-Genauigkeit Summe

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

    # Ground-Truth Metrics Properties (NEU)
    @property
    def avg_cer(self) -> float:
        """Durchschnittliche Character Error Rate."""
        return self.total_cer / self.benchmark_samples if self.benchmark_samples > 0 else 0.0

    @property
    def avg_wer(self) -> float:
        """Durchschnittliche Word Error Rate."""
        return self.total_wer / self.benchmark_samples if self.benchmark_samples > 0 else 0.0

    @property
    def avg_umlaut_accuracy(self) -> float:
        """Durchschnittliche Umlaut-Genauigkeit."""
        return self.total_umlaut_accuracy / self.benchmark_samples if self.benchmark_samples > 0 else 0.0

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
            # Ground-Truth Quality Metrics (NEU)
            "quality_metrics": {
                "benchmark_samples": self.benchmark_samples,
                "avg_cer": round(self.avg_cer, 4),
                "avg_wer": round(self.avg_wer, 4),
                "avg_umlaut_accuracy": round(self.avg_umlaut_accuracy, 4),
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

    def record_benchmark_result(
        self,
        variant_name: str,
        cer: float,
        wer: float,
        umlaut_accuracy: float,
        latency_ms: float = 0.0,
    ) -> None:
        """
        Erfasse Ground-Truth-basiertes Benchmark-Ergebnis.

        Args:
            variant_name: Name der Variante
            cer: Character Error Rate (0-1)
            wer: Word Error Rate (0-1)
            umlaut_accuracy: Umlaut-Erkennungsgenauigkeit (0-1)
            latency_ms: Verarbeitungszeit in Millisekunden
        """
        variant = next((v for v in self.variants if v.name == variant_name), None)
        if not variant:
            logger.warning("unbekannte_variante_benchmark", variant_name=variant_name)
            return

        with self._lock:
            variant.benchmark_samples += 1
            variant.total_cer += cer
            variant.total_wer += wer
            variant.total_umlaut_accuracy += umlaut_accuracy
            if latency_ms > 0:
                variant.total_latency_ms += latency_ms

        logger.debug(
            "benchmark_ergebnis_erfasst",
            variant=variant_name,
            cer=round(cer, 4),
            wer=round(wer, 4),
            umlaut_accuracy=round(umlaut_accuracy, 4),
        )

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
            logger.debug("signifikanz_test_fehlgeschlagen", **safe_error_log(e))

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
        """Serialisiere zu JSON mit sicherer Typ-Konvertierung."""
        return json.dumps(self.get_summary(), indent=2, cls=SafeJSONEncoder)


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

    def _save_experiment(self, experiment: Experiment) -> bool:
        """
        Speichere Experiment auf Disk.

        Args:
            experiment: Das zu speichernde Experiment

        Returns:
            True bei Erfolg, False bei Fehler
        """
        filepath = self.storage_path / f"{experiment.experiment_id}.json"
        try:
            json_content = experiment.to_json()

            # Validiere, dass Inhalt nicht leer ist
            if not json_content or json_content.strip() == "":
                logger.error(
                    "experiment_speichern_fehlgeschlagen_leerer_inhalt",
                    experiment_id=experiment.experiment_id,
                )
                return False

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(json_content)
                f.flush()  # Sicherstellen, dass Daten auf Disk geschrieben werden

            # Verifiziere, dass Datei nicht leer ist
            if filepath.stat().st_size == 0:
                logger.error(
                    "experiment_speichern_fehlgeschlagen_datei_leer",
                    experiment_id=experiment.experiment_id,
                    filepath=str(filepath),
                )
                return False

            logger.debug(
                "experiment_gespeichert",
                experiment_id=experiment.experiment_id,
                filepath=str(filepath),
                size_bytes=filepath.stat().st_size,
            )
            return True

        except (OSError, IOError) as e:
            logger.error(
                "experiment_speichern_fehlgeschlagen_io",
                experiment_id=experiment.experiment_id,
                filepath=str(filepath),
                **safe_error_log(e),
            )
            return False
        except json.JSONDecodeError as e:
            logger.error(
                "experiment_speichern_fehlgeschlagen_json",
                experiment_id=experiment.experiment_id,
                **safe_error_log(e),
            )
            return False
        except Exception as e:
            logger.exception(
                "experiment_speichern_fehlgeschlagen_unbekannt",
                experiment_id=experiment.experiment_id,
                **safe_error_log(e),
            )
            return False

    def _load_experiments(self) -> None:
        """Lade gespeicherte Experimente."""
        loaded_count = 0
        skipped_count = 0

        for filepath in self.storage_path.glob("exp_*.json"):
            try:
                # Überspringe leere Dateien (bekannter Bug, der jetzt gefixt ist)
                if filepath.stat().st_size == 0:
                    logger.warning(
                        "experiment_datei_leer_uebersprungen",
                        filepath=str(filepath),
                    )
                    skipped_count += 1
                    continue

                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()

                # Überspringe leeren Inhalt
                if not content or content.strip() == "":
                    logger.warning(
                        "experiment_inhalt_leer_uebersprungen",
                        filepath=str(filepath),
                    )
                    skipped_count += 1
                    continue

                data = json.loads(content)

                # Pydantic-Validierung fuer sichere JSON-Deserialisierung
                from pydantic import ValidationError as PydanticValidationError

                try:
                    validated_data = validate_experiment_json(data)
                except PydanticValidationError as e:
                    logger.warning(
                        "experiment_validierung_fehlgeschlagen",
                        filepath=str(filepath),
                        errors=e.error_count(),
                        details=str(e.errors()[:3]),  # Nur erste 3 Fehler loggen
                    )
                    skipped_count += 1
                    continue

                # Nutze validierte Daten
                variants = [
                    Variant(
                        name=v.name,
                        description=v.description,
                        weight=v.weight,
                        config=v.config,
                        samples=v.metrics.samples,
                        conversions=v.metrics.conversions,
                        # Ground-Truth Quality Metrics laden
                        benchmark_samples=v.quality_metrics.benchmark_samples,
                        total_cer=v.quality_metrics.avg_cer * v.quality_metrics.benchmark_samples,
                        total_wer=v.quality_metrics.avg_wer * v.quality_metrics.benchmark_samples,
                        total_umlaut_accuracy=v.quality_metrics.avg_umlaut_accuracy * v.quality_metrics.benchmark_samples,
                    )
                    for v in validated_data.variants
                ]

                experiment = Experiment(
                    experiment_id=validated_data.experiment_id,
                    name=validated_data.name,
                    description=validated_data.description,
                    variants=variants,
                    status=ExperimentStatus(validated_data.status),
                    winner=validated_data.winner,
                    significance_reached=validated_data.significance_reached,
                )

                if validated_data.start_time:
                    experiment.start_time = datetime.fromisoformat(validated_data.start_time)
                if validated_data.end_time:
                    experiment.end_time = datetime.fromisoformat(validated_data.end_time)

                self._experiments[experiment.experiment_id] = experiment
                loaded_count += 1

            except json.JSONDecodeError as e:
                logger.warning(
                    "experiment_laden_fehlgeschlagen_json_ungueltig",
                    filepath=str(filepath),
                    **safe_error_log(e),
                )
                skipped_count += 1
            except Exception as e:
                logger.warning(
                    "experiment_laden_fehlgeschlagen",
                    filepath=str(filepath),
                    **safe_error_log(e),
                )
                skipped_count += 1

        if loaded_count > 0 or skipped_count > 0:
            logger.info(
                "experimente_geladen",
                loaded=loaded_count,
                skipped=skipped_count,
            )

    def get_winning_backend(self, experiment_id: str) -> Optional[str]:
        """
        Hole das gewinnende Backend aus einem Experiment.

        Args:
            experiment_id: ID des Experiments

        Returns:
            Backend-Name des Gewinners oder None
        """
        experiment = self._experiments.get(experiment_id)
        if not experiment:
            return None

        if experiment.winner:
            # Find the variant with the winning name and extract backend
            for variant in experiment.variants:
                if variant.name == experiment.winner:
                    return variant.config.get("backend")
        return None

    def get_significant_winners(self) -> Dict[str, str]:
        """
        Hole alle Experimente mit signifikanten Gewinnern.

        Returns:
            Dict[experiment_id, winning_backend]
        """
        winners = {}
        for exp_id, experiment in self._experiments.items():
            if experiment.significance_reached and experiment.winner:
                backend = self.get_winning_backend(exp_id)
                if backend:
                    winners[exp_id] = backend
        return winners

    def check_and_apply_winners(
        self,
        auto_conclude: bool = True,
        min_improvement_percent: float = 5.0,
    ) -> List[Dict[str, Any]]:
        """
        Prüfe alle laufenden Experimente auf Signifikanz und wende Gewinner an.

        Args:
            auto_conclude: Experimente automatisch beenden bei Signifikanz
            min_improvement_percent: Mindestverbesserung für Gewinner-Anwendung

        Returns:
            Liste der angewendeten Gewinner mit Details
        """
        applied_winners = []

        for experiment in self.get_active_experiments():
            # Skip if not enough samples
            if any(v.samples < experiment.min_samples_per_variant for v in experiment.variants):
                continue

            # Check if significance was reached
            if experiment.significance_reached and experiment.winner:
                # Calculate improvement
                control = experiment.variants[0]
                treatment = None
                for v in experiment.variants:
                    if v.name == experiment.winner:
                        treatment = v
                        break

                if treatment and control:
                    improvement = 0.0
                    if control.conversion_rate > 0:
                        improvement = ((treatment.conversion_rate - control.conversion_rate)
                                      / control.conversion_rate * 100)

                    winner_backend = self.get_winning_backend(experiment.experiment_id)

                    if improvement >= min_improvement_percent or treatment.conversion_rate > control.conversion_rate:
                        result = {
                            "experiment_id": experiment.experiment_id,
                            "winner_backend": winner_backend,
                            "winner_variant": experiment.winner,
                            "improvement_percent": round(improvement, 2),
                            "control_rate": round(control.conversion_rate, 4),
                            "winner_rate": round(treatment.conversion_rate, 4),
                            "total_samples": sum(v.samples for v in experiment.variants),
                        }

                        applied_winners.append(result)

                        logger.info(
                            "ab_test_winner_detected",
                            experiment_id=experiment.experiment_id,
                            winner_backend=winner_backend,
                            improvement_percent=round(improvement, 2),
                        )

                        # Auto-conclude experiment
                        if auto_conclude:
                            self.conclude_experiment(experiment.experiment_id)

        return applied_winners

    def get_recommended_backend_order(self) -> List[str]:
        """
        Empfehle Backend-Reihenfolge basierend auf A/B-Test Ergebnissen.

        Analysiert alle abgeschlossenen Experimente und erstellt
        eine optimierte Backend-Reihenfolge.

        Returns:
            Liste von Backend-Namen, sortiert nach Performance
        """
        backend_scores: Dict[str, Dict[str, float]] = {}

        # Sammle Daten aus allen abgeschlossenen Experimenten
        for experiment in self._experiments.values():
            if experiment.status != ExperimentStatus.COMPLETED:
                continue

            for variant in experiment.variants:
                backend = variant.config.get("backend")
                if not backend:
                    continue

                if backend not in backend_scores:
                    backend_scores[backend] = {
                        "total_rate": 0.0,
                        "experiment_count": 0,
                        "wins": 0,
                    }

                backend_scores[backend]["total_rate"] += variant.conversion_rate
                backend_scores[backend]["experiment_count"] += 1

                if experiment.winner == variant.name:
                    backend_scores[backend]["wins"] += 1

        # Berechne durchschnittliche Rate und sortiere
        backend_ranks = []
        for backend, scores in backend_scores.items():
            if scores["experiment_count"] > 0:
                avg_rate = scores["total_rate"] / scores["experiment_count"]
                win_bonus = scores["wins"] * 0.1  # 10% Bonus pro Gewinn
                final_score = avg_rate + win_bonus
                backend_ranks.append((backend, final_score))

        # Sortiere absteigend nach Score
        backend_ranks.sort(key=lambda x: x[1], reverse=True)

        recommended_order = [b[0] for b in backend_ranks]

        logger.info(
            "recommended_backend_order",
            order=recommended_order,
            scores={b: round(s, 4) for b, s in backend_ranks},
        )

        return recommended_order


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

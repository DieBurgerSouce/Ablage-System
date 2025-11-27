# -*- coding: utf-8 -*-
"""
Model Registry - Sichere Modellverwaltung und Versionierung.

Enterprise-grade Model Registry für ML-Router:
- Semantic Versioning (SemVer) für Modelle
- Sichere Serialisierung (kein pickle!)
- Feature-Kompatibilitätsprüfung
- Audit-Trail für Modellversionen
- A/B Testing Support (Vorbereitung)

Feinpoliert und durchdacht - Sichere Modellverwaltung.
"""

import hashlib
import json
import logging
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ModelVersion:
    """
    Modellversion mit vollständiger Metadaten-Verfolgung.

    Attributes:
        version: Semantische Version (z.B. "1.2.3")
        created_at: Erstellungszeitpunkt (ISO 8601)
        git_commit: Git Commit Hash zum Zeitpunkt des Trainings
        training_samples: Anzahl der Trainingsbeispiele
        validation_accuracy: Validierungsgenauigkeit (0-1)
        feature_hash: Hash der Feature-Namen für Kompatibilitätsprüfung
        model_type: Typ des Modells (z.B. "xgboost", "lightgbm")
        hyperparameters: Trainingsparameter
        metadata: Zusätzliche Metadaten
    """
    version: str
    created_at: str
    git_commit: str
    training_samples: int
    validation_accuracy: float
    feature_hash: str
    model_type: str = "xgboost"
    hyperparameters: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary für JSON-Serialisierung."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ModelVersion":
        """Erstellt ModelVersion aus Dictionary."""
        return cls(**data)

    def is_compatible_with(self, feature_names: List[str]) -> bool:
        """Prüft Kompatibilität mit aktuellen Features."""
        current_hash = compute_feature_hash(feature_names)
        return self.feature_hash == current_hash


@dataclass
class ModelArtifact:
    """
    Komplettes Modellartefakt mit Pfaden und Metadaten.

    Attributes:
        version_info: Versionsinformationen
        model_path: Pfad zur Modelldatei
        metadata_path: Pfad zur Metadaten-Datei
        is_active: Ob dieses Modell aktiv ist
    """
    version_info: ModelVersion
    model_path: Path
    metadata_path: Path
    is_active: bool = False

    def exists(self) -> bool:
        """Prüft ob alle Dateien existieren."""
        return self.model_path.exists() and self.metadata_path.exists()


def compute_feature_hash(feature_names: List[str]) -> str:
    """
    Berechnet einen stabilen Hash über Feature-Namen.

    Dient zur Kompatibilitätsprüfung zwischen Modellversionen.
    """
    # Sortieren für Konsistenz
    sorted_names = sorted(feature_names)
    content = "|".join(sorted_names)
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def get_git_commit() -> str:
    """Holt den aktuellen Git Commit Hash."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip()[:12]
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
    return "unknown"


class ModelRegistry:
    """
    Registry für ML-Modellverwaltung.

    Verwaltet:
    - Modellversionen mit SemVer
    - Sichere Serialisierung
    - Rollback-Unterstützung
    - A/B Testing Vorbereitung
    """

    # Konstanten
    MODEL_FILENAME = "model.json"  # XGBoost JSON Format (sicher!)
    METADATA_FILENAME = "metadata.json"
    REGISTRY_FILENAME = "registry.json"

    def __init__(self, base_path: Path) -> None:
        """
        Initialisiert Model Registry.

        Args:
            base_path: Basisverzeichnis für Modellspeicherung
        """
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

        self._registry_path = self.base_path / self.REGISTRY_FILENAME
        self._registry: Dict[str, Any] = self._load_registry()

        logger.info(f"Model Registry initialisiert: {self.base_path}")

    def _load_registry(self) -> Dict[str, Any]:
        """Lädt Registry-Index."""
        if self._registry_path.exists():
            with open(self._registry_path, encoding="utf-8") as f:
                return json.load(f)
        return {
            "versions": [],
            "active_version": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    def _save_registry(self) -> None:
        """Speichert Registry-Index."""
        with open(self._registry_path, "w", encoding="utf-8") as f:
            json.dump(self._registry, f, indent=2, ensure_ascii=False)

    def get_next_version(self, bump_type: str = "patch") -> str:
        """
        Ermittelt die nächste Versionsnummer.

        Args:
            bump_type: "major", "minor", oder "patch"

        Returns:
            Nächste Versionsnummer
        """
        versions = self._registry.get("versions", [])

        if not versions:
            return "1.0.0"

        # Letzte Version parsen
        last_version = versions[-1]
        parts = last_version.split(".")

        if len(parts) != 3:
            return "1.0.0"

        major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])

        if bump_type == "major":
            return f"{major + 1}.0.0"
        elif bump_type == "minor":
            return f"{major}.{minor + 1}.0"
        else:  # patch
            return f"{major}.{minor}.{patch + 1}"

    def _get_version_path(self, version: str) -> Path:
        """Gibt Verzeichnispfad für Version zurück."""
        return self.base_path / f"v{version}"

    def register_model(
        self,
        model: Any,  # XGBoost model
        feature_names: List[str],
        training_samples: int,
        validation_accuracy: float,
        hyperparameters: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        bump_type: str = "patch",
    ) -> ModelVersion:
        """
        Registriert ein neues Modell in der Registry.

        Args:
            model: XGBoost Modell zum Speichern
            feature_names: Liste der Feature-Namen
            training_samples: Anzahl Trainingsbeispiele
            validation_accuracy: Validierungsgenauigkeit
            hyperparameters: Trainingsparameter
            metadata: Zusätzliche Metadaten
            bump_type: Versionstyp ("major", "minor", "patch")

        Returns:
            ModelVersion mit allen Informationen
        """
        version = self.get_next_version(bump_type)
        version_path = self._get_version_path(version)
        version_path.mkdir(parents=True, exist_ok=True)

        model_path = version_path / self.MODEL_FILENAME
        metadata_path = version_path / self.METADATA_FILENAME

        # Modell sicher speichern (XGBoost JSON Format)
        model.save_model(str(model_path))

        # Version-Info erstellen
        version_info = ModelVersion(
            version=version,
            created_at=datetime.now(timezone.utc).isoformat(),
            git_commit=get_git_commit(),
            training_samples=training_samples,
            validation_accuracy=validation_accuracy,
            feature_hash=compute_feature_hash(feature_names),
            model_type="xgboost",
            hyperparameters=hyperparameters or {},
            metadata=metadata or {},
        )

        # Metadaten speichern
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(version_info.to_dict(), f, indent=2, ensure_ascii=False)

        # Registry aktualisieren
        self._registry["versions"].append(version)
        self._save_registry()

        logger.info(
            f"Modell registriert: v{version}",
            extra={
                "version": version,
                "training_samples": training_samples,
                "validation_accuracy": validation_accuracy,
            },
        )

        return version_info

    def load_model(
        self,
        version: Optional[str] = None,
        model_class: Optional[Any] = None,
    ) -> tuple[Any, ModelVersion]:
        """
        Lädt ein Modell aus der Registry.

        Args:
            version: Spezifische Version oder None für aktive/letzte
            model_class: XGBoost Modellklasse (z.B. xgb.XGBClassifier)

        Returns:
            Tuple aus (model, version_info)
        """
        if model_class is None:
            try:
                import xgboost as xgb
                model_class = xgb.XGBClassifier
            except ImportError as err:
                raise RuntimeError("XGBoost nicht verfügbar") from err

        # Version bestimmen
        if version is None:
            version = self._registry.get("active_version")
            if version is None:
                versions = self._registry.get("versions", [])
                if not versions:
                    raise ValueError("Keine Modellversionen vorhanden")
                version = versions[-1]

        version_path = self._get_version_path(version)
        model_path = version_path / self.MODEL_FILENAME
        metadata_path = version_path / self.METADATA_FILENAME

        if not model_path.exists():
            raise FileNotFoundError(f"Modell nicht gefunden: {model_path}")

        if not metadata_path.exists():
            raise FileNotFoundError(f"Metadaten nicht gefunden: {metadata_path}")

        # Metadaten laden
        with open(metadata_path, encoding="utf-8") as f:
            version_info = ModelVersion.from_dict(json.load(f))

        # Modell sicher laden (XGBoost JSON Format)
        model = model_class()
        model.load_model(str(model_path))

        logger.info(f"Modell geladen: v{version}")

        return model, version_info

    def set_active(self, version: str) -> None:
        """
        Setzt eine Version als aktiv.

        Args:
            version: Version zum Aktivieren
        """
        if version not in self._registry.get("versions", []):
            raise ValueError(f"Version nicht gefunden: {version}")

        self._registry["active_version"] = version
        self._save_registry()

        logger.info(f"Aktive Version gesetzt: v{version}")

    def get_active_version(self) -> Optional[str]:
        """Gibt die aktive Version zurück."""
        return self._registry.get("active_version")

    def list_versions(self) -> List[Dict[str, Any]]:
        """
        Listet alle verfügbaren Versionen.

        Returns:
            Liste mit Versionsinformationen
        """
        result = []
        for version in self._registry.get("versions", []):
            version_path = self._get_version_path(version)
            metadata_path = version_path / self.METADATA_FILENAME

            if metadata_path.exists():
                with open(metadata_path, encoding="utf-8") as f:
                    info = json.load(f)
                    info["is_active"] = version == self._registry.get("active_version")
                    result.append(info)

        return result

    def delete_version(self, version: str) -> bool:
        """
        Löscht eine Modellversion.

        Args:
            version: Version zum Löschen

        Returns:
            True wenn erfolgreich
        """
        if version not in self._registry.get("versions", []):
            return False

        # Nicht aktive Version löschen
        if version == self._registry.get("active_version"):
            raise ValueError("Kann aktive Version nicht löschen")

        import shutil
        version_path = self._get_version_path(version)
        if version_path.exists():
            shutil.rmtree(version_path)

        self._registry["versions"].remove(version)
        self._save_registry()

        logger.info(f"Version gelöscht: v{version}")
        return True

    def get_version_info(self, version: str) -> Optional[ModelVersion]:
        """
        Holt Versionsinformationen.

        Args:
            version: Gewünschte Version

        Returns:
            ModelVersion oder None
        """
        version_path = self._get_version_path(version)
        metadata_path = version_path / self.METADATA_FILENAME

        if not metadata_path.exists():
            return None

        with open(metadata_path, encoding="utf-8") as f:
            return ModelVersion.from_dict(json.load(f))

    def check_compatibility(
        self,
        version: str,
        feature_names: List[str],
    ) -> bool:
        """
        Prüft Feature-Kompatibilität einer Version.

        Args:
            version: Zu prüfende Version
            feature_names: Aktuelle Feature-Namen

        Returns:
            True wenn kompatibel
        """
        version_info = self.get_version_info(version)
        if version_info is None:
            return False
        return version_info.is_compatible_with(feature_names)

    def cleanup_old_versions(self, keep_count: int = 5) -> int:
        """
        Entfernt alte Versionen, behält die neuesten.

        Args:
            keep_count: Anzahl zu behaltender Versionen

        Returns:
            Anzahl gelöschter Versionen
        """
        versions = self._registry.get("versions", [])
        active = self._registry.get("active_version")

        if len(versions) <= keep_count:
            return 0

        to_delete = versions[:-keep_count]
        deleted = 0

        for version in to_delete:
            if version != active:
                try:
                    self.delete_version(version)
                    deleted += 1
                except Exception as e:
                    logger.warning(f"Konnte Version {version} nicht löschen: {e}")

        return deleted


# Legacy-Unterstützung für bestehende pickle-Dateien
def migrate_pickle_to_registry(
    pickle_path: Path,
    registry: ModelRegistry,
    feature_names: List[str],
) -> Optional[ModelVersion]:
    """
    Migriert ein altes pickle-Modell zur neuen Registry.

    WARNUNG: pickle.load ist unsicher! Nur für vertrauenswürdige Dateien verwenden.

    Args:
        pickle_path: Pfad zur pickle-Datei
        registry: Ziel-Registry
        feature_names: Feature-Namen für Kompatibilität

    Returns:
        Neue ModelVersion oder None bei Fehler
    """
    import pickle
    import warnings

    warnings.warn(
        "Migration von pickle-Modell. pickle.load ist unsicher! "
        "Stellen Sie sicher, dass die Datei vertrauenswürdig ist.",
        UserWarning,
    )

    try:
        with open(pickle_path, "rb") as f:
            data = pickle.load(f)  # noqa: S301

        model = data.get("model")
        if model is None:
            logger.error("Kein Modell in pickle-Datei gefunden")
            return None

        training_samples = data.get("training_samples", 0)

        # Da wir keine Validierungsgenauigkeit haben, schätzen wir
        version_info = registry.register_model(
            model=model,
            feature_names=feature_names,
            training_samples=training_samples,
            validation_accuracy=0.0,  # Unbekannt
            metadata={"migrated_from": str(pickle_path)},
            bump_type="major",  # Major version für Migration
        )

        logger.info(f"Pickle-Modell migriert zu v{version_info.version}")
        return version_info

    except Exception as e:
        logger.error(f"Migration fehlgeschlagen: {e}")
        return None

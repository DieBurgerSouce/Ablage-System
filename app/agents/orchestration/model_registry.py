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
import os
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import structlog
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)

# Security Flag für Pickle-Migration
# WARNUNG: Nur auf True setzen wenn Sie ABSOLUT SICHER sind,
# dass die pickle-Dateien aus vertrauenswürdiger Quelle stammen!
# Pickle-Deserialisierung kann beliebigen Code ausführen!
ALLOW_PICKLE_MIGRATION: bool = os.environ.get(
    "ABLAGE_ALLOW_PICKLE_MIGRATION", "false"
).lower() == "true"


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
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        logger.debug(
            "git_commit_hash_failed",
            error_type=type(e).__name__,
        )
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

        logger.info("model_registry_initialisiert", path=str(self.base_path))

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
        model: "xgboost.XGBClassifier",
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
            "modell_registriert",
            version=version,
            training_samples=training_samples,
            validation_accuracy=validation_accuracy,
        )

        return version_info

    def load_model(
        self,
        version: Optional[str] = None,
        model_class: Optional[type] = None,
    ) -> Tuple["xgboost.XGBClassifier", ModelVersion]:
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

        logger.info("modell_geladen", version=version)

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

        logger.info("aktive_version_gesetzt", version=version)

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

        logger.info("version_gelöscht", version=version)
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
                    logger.warning("version_löschen_fehlgeschlagen", version=version, **safe_error_log(e))

        return deleted


# Legacy-Unterstützung für bestehende pickle-Dateien
def migrate_pickle_to_registry(
    pickle_path: Path,
    registry: ModelRegistry,
    feature_names: List[str],
    force_allow: bool = False,
) -> Optional[ModelVersion]:
    """
    Migriert ein altes pickle-Modell zur neuen Registry.

    SICHERHEITSWARNUNG:
    - pickle.load kann BELIEBIGEN CODE ausführen!
    - Verwenden Sie diese Funktion NUR für vertrauenswürdige Dateien!
    - Stellen Sie ABLAGE_ALLOW_PICKLE_MIGRATION=true als Umgebungsvariable
      oder setzen Sie force_allow=True (nur für einmalige Migrationen!)

    Args:
        pickle_path: Pfad zur pickle-Datei
        registry: Ziel-Registry
        feature_names: Feature-Namen für Kompatibilität
        force_allow: Überschreibt Security Flag (GEFÄHRLICH!)

    Returns:
        Neue ModelVersion oder None bei Fehler

    Raises:
        SecurityError: Wenn pickle-Migration nicht erlaubt ist
    """
    # Security Check - KRITISCH!
    if not ALLOW_PICKLE_MIGRATION and not force_allow:
        logger.error(
            "pickle_migration_blocked",
            reason="Security flag not enabled",
            hint="Set ABLAGE_ALLOW_PICKLE_MIGRATION=true if you trust the source",
            pickle_path=str(pickle_path),
        )
        raise PermissionError(
            "Pickle-Migration ist aus Sicherheitsgründen deaktiviert. "
            "Setzen Sie ABLAGE_ALLOW_PICKLE_MIGRATION=true wenn Sie der "
            "Quelle der pickle-Datei vertrauen. WARNUNG: pickle.load kann "
            "beliebigen Code ausführen!"
        )

    import pickle
    import warnings


    # Audit Log - wer hat wann eine pickle-Migration durchgeführt?
    logger.warning(
        "pickle_migration_started",
        pickle_path=str(pickle_path),
        force_allow=force_allow,
        security_warning="pickle.load kann beliebigen Code ausführen!",
    )

    warnings.warn(
        "Migration von pickle-Modell. pickle.load ist unsicher! "
        "Stellen Sie sicher, dass die Datei vertrauenswürdig ist.",
        UserWarning,
        stacklevel=2,
    )

    try:
        # Validate path exists and is a file
        if not pickle_path.exists():
            raise FileNotFoundError(f"Pickle-Datei nicht gefunden: {pickle_path}")
        if not pickle_path.is_file():
            raise ValueError(f"Pfad ist keine Datei: {pickle_path}")

        with open(pickle_path, "rb") as f:
            data = pickle.load(f)  # noqa: S301 - Security check above

        model = data.get("model")
        if model is None:
            logger.error(
                "pickle_migration_failed",
                reason="No model found in pickle file",
                pickle_path=str(pickle_path),
            )
            return None

        training_samples = data.get("training_samples", 0)

        # Da wir keine Validierungsgenauigkeit haben, schätzen wir
        version_info = registry.register_model(
            model=model,
            feature_names=feature_names,
            training_samples=training_samples,
            validation_accuracy=0.0,  # Unbekannt
            metadata={
                "migrated_from": str(pickle_path),
                "migration_timestamp": datetime.now(timezone.utc).isoformat(),
                "security_notice": "Migrated from pickle - verify model integrity",
            },
            bump_type="major",  # Major version für Migration
        )

        logger.info(
            "pickle_migration_completed",
            version=version_info.version,
            pickle_path=str(pickle_path),
        )
        return version_info

    except PermissionError:
        raise  # Re-raise security errors
    except Exception as e:
        logger.exception(
            "pickle_migration_failed",
            **safe_error_log(e),
            pickle_path=str(pickle_path),
        )
        return None

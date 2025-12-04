"""
Checkpoint Manager für Fine-Tuned Models

Verwaltet Checkpoints für DeepSeek und Surya Fine-Tuning:
- Versionierung
- A/B Testing
- Rollback-Funktionalität
- Metriken-Tracking

Author: Claude Code
Created: 2024-12
"""

import json
import logging
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class CheckpointInfo:
    """Information über einen Checkpoint."""
    model_name: str
    version: str
    checkpoint_path: str
    created_at: str
    metrics: Dict[str, float]
    training_config: Dict[str, Any]
    is_active: bool = False
    is_best: bool = False
    parent_version: Optional[str] = None
    notes: str = ""


@dataclass
class ModelVersion:
    """Versionsinformation eines Modells."""
    model_name: str
    version: str
    created_at: str
    checkpoint_path: str
    metrics: Dict[str, float] = field(default_factory=dict)
    is_production: bool = False
    traffic_percentage: float = 0.0


class CheckpointManager:
    """
    Verwaltet Checkpoints für Fine-Tuned Models.

    Struktur:
    /models/finetuned/
        /deepseek/
            /v1.0.0_20241204/
                adapter_model.safetensors
                metrics.json
                config.json
            /v1.0.1_20241205/
                ...
        /surya/
            /v1.0.0_20241204/
                pytorch_model.bin
                metrics.json
    """

    def __init__(self, base_dir: str = "./models/finetuned"):
        """
        Initialisiert den Checkpoint Manager.

        Args:
            base_dir: Basis-Verzeichnis für alle Checkpoints
        """
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

        self._registry_file = self.base_dir / "registry.json"
        self._registry: Dict[str, List[Dict[str, Any]]] = self._load_registry()

        logger.info(f"CheckpointManager initialisiert: {self.base_dir}")

    def _load_registry(self) -> Dict[str, List[Dict[str, Any]]]:
        """Lädt die Checkpoint-Registry."""
        if self._registry_file.exists():
            try:
                with open(self._registry_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Registry konnte nicht geladen werden: {e}")
        return {}

    def _save_registry(self) -> None:
        """Speichert die Checkpoint-Registry."""
        with open(self._registry_file, "w", encoding="utf-8") as f:
            json.dump(self._registry, f, indent=2, ensure_ascii=False)

    def create_version(
        self,
        model_name: str,
        source_path: str,
        metrics: Optional[Dict[str, float]] = None,
        training_config: Optional[Dict[str, Any]] = None,
        notes: str = ""
    ) -> str:
        """
        Erstellt eine neue Version eines Modells.

        Args:
            model_name: Name des Modells (deepseek, surya)
            source_path: Pfad zum trainierten Checkpoint
            metrics: Trainings-Metriken
            training_config: Training-Konfiguration
            notes: Notizen zur Version

        Returns:
            Version-String (z.B. "v1.0.0_20241204")
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        existing = self.list_versions(model_name)
        if existing:
            last_version = existing[-1].version
            major, minor, patch = self._parse_version(last_version)
            new_version = f"v{major}.{minor}.{patch + 1}_{timestamp}"
        else:
            new_version = f"v1.0.0_{timestamp}"

        model_dir = self.base_dir / model_name
        version_dir = model_dir / new_version
        version_dir.mkdir(parents=True, exist_ok=True)

        source_path = Path(source_path)
        if source_path.is_dir():
            for item in source_path.iterdir():
                if item.is_file():
                    shutil.copy2(item, version_dir)
                elif item.is_dir():
                    shutil.copytree(item, version_dir / item.name)
        else:
            shutil.copy2(source_path, version_dir)

        if metrics:
            metrics_file = version_dir / "metrics.json"
            with open(metrics_file, "w", encoding="utf-8") as f:
                json.dump(metrics, f, indent=2, ensure_ascii=False)

        if training_config:
            config_file = version_dir / "training_config.json"
            with open(config_file, "w", encoding="utf-8") as f:
                json.dump(training_config, f, indent=2, ensure_ascii=False)

        checkpoint_info = {
            "model_name": model_name,
            "version": new_version,
            "checkpoint_path": str(version_dir),
            "created_at": datetime.now().isoformat(),
            "metrics": metrics or {},
            "training_config": training_config or {},
            "is_active": False,
            "is_best": False,
            "notes": notes
        }

        if model_name not in self._registry:
            self._registry[model_name] = []
        self._registry[model_name].append(checkpoint_info)
        self._save_registry()

        logger.info(f"Neue Version erstellt: {model_name}/{new_version}")
        return new_version

    def _parse_version(self, version: str) -> tuple:
        """Parsed Version-String zu (major, minor, patch)."""
        try:
            version_part = version.split("_")[0]
            nums = version_part.lstrip("v").split(".")
            return int(nums[0]), int(nums[1]), int(nums[2])
        except Exception:
            return 1, 0, 0

    def list_versions(self, model_name: str) -> List[ModelVersion]:
        """Listet alle Versionen eines Modells auf."""
        if model_name not in self._registry:
            return []

        versions = []
        for info in self._registry[model_name]:
            versions.append(ModelVersion(
                model_name=info["model_name"],
                version=info["version"],
                created_at=info["created_at"],
                checkpoint_path=info["checkpoint_path"],
                metrics=info.get("metrics", {}),
                is_production=info.get("is_active", False),
                traffic_percentage=info.get("traffic_percentage", 0.0)
            ))

        return sorted(versions, key=lambda v: v.created_at)

    def get_version(self, model_name: str, version: str) -> Optional[CheckpointInfo]:
        """Holt Information zu einer spezifischen Version."""
        if model_name not in self._registry:
            return None

        for info in self._registry[model_name]:
            if info["version"] == version:
                return CheckpointInfo(**info)

        return None

    def get_latest_version(self, model_name: str) -> Optional[ModelVersion]:
        """Holt die neueste Version eines Modells."""
        versions = self.list_versions(model_name)
        return versions[-1] if versions else None

    def get_active_version(self, model_name: str) -> Optional[ModelVersion]:
        """Holt die aktive (Production) Version eines Modells."""
        if model_name not in self._registry:
            return None

        for info in self._registry[model_name]:
            if info.get("is_active", False):
                return ModelVersion(
                    model_name=info["model_name"],
                    version=info["version"],
                    created_at=info["created_at"],
                    checkpoint_path=info["checkpoint_path"],
                    metrics=info.get("metrics", {}),
                    is_production=True,
                    traffic_percentage=info.get("traffic_percentage", 100.0)
                )

        return None

    def activate_version(
        self,
        model_name: str,
        version: str,
        traffic_percentage: float = 100.0
    ) -> bool:
        """
        Aktiviert eine Version für Production.

        Args:
            model_name: Modell-Name
            version: Version zum Aktivieren
            traffic_percentage: Anteil des Traffics (für A/B Testing)

        Returns:
            Erfolg
        """
        if model_name not in self._registry:
            return False

        version_found = False
        for info in self._registry[model_name]:
            if info["version"] == version:
                info["is_active"] = True
                info["traffic_percentage"] = traffic_percentage
                info["activated_at"] = datetime.now().isoformat()
                version_found = True
            elif traffic_percentage >= 100.0:
                info["is_active"] = False
                info["traffic_percentage"] = 0.0

        if version_found:
            self._save_registry()
            logger.info(f"Version aktiviert: {model_name}/{version} ({traffic_percentage}%)")

        return version_found

    def deactivate_version(self, model_name: str, version: str) -> bool:
        """Deaktiviert eine Version."""
        if model_name not in self._registry:
            return False

        for info in self._registry[model_name]:
            if info["version"] == version:
                info["is_active"] = False
                info["traffic_percentage"] = 0.0
                info["deactivated_at"] = datetime.now().isoformat()
                self._save_registry()
                logger.info(f"Version deaktiviert: {model_name}/{version}")
                return True

        return False

    def rollback_to_version(
        self,
        model_name: str,
        target_version: str,
        reason: str = ""
    ) -> bool:
        """
        Führt Rollback zu einer früheren Version durch.

        Args:
            model_name: Modell-Name
            target_version: Ziel-Version für Rollback
            reason: Grund für Rollback

        Returns:
            Erfolg
        """
        current_active = self.get_active_version(model_name)

        if current_active:
            self.deactivate_version(model_name, current_active.version)
            for info in self._registry[model_name]:
                if info["version"] == current_active.version:
                    info["rollback_reason"] = reason
                    info["rolled_back_at"] = datetime.now().isoformat()

        success = self.activate_version(model_name, target_version, 100.0)

        if success:
            logger.info(f"Rollback durchgeführt: {model_name} -> {target_version}")
            self._save_registry()

        return success

    def compare_versions(
        self,
        model_name: str,
        version_a: str,
        version_b: str
    ) -> Dict[str, Any]:
        """
        Vergleicht zwei Versionen.

        Returns:
            Vergleichsergebnis mit Metrik-Unterschieden
        """
        info_a = self.get_version(model_name, version_a)
        info_b = self.get_version(model_name, version_b)

        if not info_a or not info_b:
            return {"error": "Version nicht gefunden"}

        comparison = {
            "version_a": version_a,
            "version_b": version_b,
            "metrics_comparison": {},
            "recommendation": None
        }

        all_metrics = set(info_a.metrics.keys()) | set(info_b.metrics.keys())
        for metric in all_metrics:
            val_a = info_a.metrics.get(metric, 0)
            val_b = info_b.metrics.get(metric, 0)
            diff = val_b - val_a
            comparison["metrics_comparison"][metric] = {
                "version_a": val_a,
                "version_b": val_b,
                "difference": diff,
                "improvement": diff < 0 if "loss" in metric or "error" in metric else diff > 0
            }

        improvements = sum(
            1 for m in comparison["metrics_comparison"].values()
            if m["improvement"]
        )

        if improvements > len(all_metrics) / 2:
            comparison["recommendation"] = f"{version_b} ist besser"
        elif improvements < len(all_metrics) / 2:
            comparison["recommendation"] = f"{version_a} ist besser"
        else:
            comparison["recommendation"] = "Gleichwertig"

        return comparison

    def delete_version(self, model_name: str, version: str, force: bool = False) -> bool:
        """
        Löscht eine Version.

        Args:
            model_name: Modell-Name
            version: Version zum Löschen
            force: Auch aktive Version löschen

        Returns:
            Erfolg
        """
        if model_name not in self._registry:
            return False

        for i, info in enumerate(self._registry[model_name]):
            if info["version"] == version:
                if info.get("is_active") and not force:
                    logger.warning(f"Aktive Version kann nicht gelöscht werden: {version}")
                    return False

                checkpoint_path = Path(info["checkpoint_path"])
                if checkpoint_path.exists():
                    shutil.rmtree(checkpoint_path)

                self._registry[model_name].pop(i)
                self._save_registry()
                logger.info(f"Version gelöscht: {model_name}/{version}")
                return True

        return False

    def cleanup_old_versions(
        self,
        model_name: str,
        keep_count: int = 5,
        keep_active: bool = True,
        keep_best: bool = True
    ) -> int:
        """
        Räumt alte Versionen auf.

        Args:
            model_name: Modell-Name
            keep_count: Anzahl der zu behaltenden Versionen
            keep_active: Aktive Version behalten
            keep_best: Beste Version behalten

        Returns:
            Anzahl gelöschter Versionen
        """
        if model_name not in self._registry:
            return 0

        versions = sorted(
            self._registry[model_name],
            key=lambda v: v["created_at"],
            reverse=True
        )

        to_keep = []
        to_delete = []

        for i, info in enumerate(versions):
            should_keep = (
                i < keep_count or
                (keep_active and info.get("is_active")) or
                (keep_best and info.get("is_best"))
            )

            if should_keep:
                to_keep.append(info)
            else:
                to_delete.append(info)

        deleted_count = 0
        for info in to_delete:
            if self.delete_version(model_name, info["version"], force=False):
                deleted_count += 1

        logger.info(f"Cleanup: {deleted_count} Versionen von {model_name} gelöscht")
        return deleted_count

    def get_storage_stats(self) -> Dict[str, Any]:
        """Gibt Speicherstatistiken zurück."""
        stats = {
            "total_size_mb": 0,
            "models": {}
        }

        for model_name in self._registry:
            model_size = 0
            version_count = len(self._registry[model_name])

            for info in self._registry[model_name]:
                checkpoint_path = Path(info["checkpoint_path"])
                if checkpoint_path.exists():
                    for f in checkpoint_path.rglob("*"):
                        if f.is_file():
                            model_size += f.stat().st_size

            stats["models"][model_name] = {
                "version_count": version_count,
                "size_mb": model_size / (1024 * 1024),
                "active_version": None
            }

            active = self.get_active_version(model_name)
            if active:
                stats["models"][model_name]["active_version"] = active.version

            stats["total_size_mb"] += model_size / (1024 * 1024)

        return stats

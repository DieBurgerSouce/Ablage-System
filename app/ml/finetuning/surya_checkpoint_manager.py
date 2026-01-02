"""
Surya Checkpoint Manager fuer Continuous Improvement System

Verwaltet Surya OCR Model Checkpoints mit:
- Datenbank-Integration (SuryaModelVersion, SuryaTrainingRun, etc.)
- A/B Testing Management
- Automatisches Rollback bei Qualitaetsverlust
- Umlaut-fokussierte Metriken

Author: Claude Code
Created: 2024-12
"""

import json
import logging
import os
import shutil
import uuid as uuid_module
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@dataclass
class SuryaCheckpointInfo:
    """Information ueber einen Surya Checkpoint."""
    id: str
    version: str
    checkpoint_path: str
    created_at: datetime
    cer: Optional[float] = None
    wer: Optional[float] = None
    umlaut_accuracy: Optional[float] = None
    eszett_accuracy: Optional[float] = None
    training_samples_count: int = 0
    is_active: bool = False
    is_production: bool = False
    traffic_percentage: float = 0.0
    training_config: Dict[str, Any] = field(default_factory=dict)
    notes: str = ""


@dataclass
class SuryaABTestConfig:
    """Konfiguration fuer einen A/B Test."""
    control_version_id: str
    treatment_version_id: str
    treatment_traffic_pct: float = 20.0
    minimum_samples: int = 100
    minimum_duration_hours: int = 48
    success_criteria: Dict[str, float] = field(default_factory=lambda: {
        "umlaut_accuracy_improvement": 0.02,
        "cer_reduction": 0.01
    })


class SuryaCheckpointManager:
    """
    Verwaltet Surya OCR Model Checkpoints mit Datenbankintegration.

    Features:
    - Versionierung mit semantischen Versionen (v1.0.0)
    - A/B Testing mit automatischer Auswertung
    - Rollback bei Qualitaetsverlust
    - Umlaut-fokussierte Metriken-Tracking
    - Benchmark-History

    Qualitaetsziele:
    - CER < 3%
    - WER < 8%
    - Umlaut-Accuracy = 100% (KRITISCH!)

    Verzeichnisstruktur:
    /models/surya/checkpoints/
        /v1.0.0_20241215_143022/
            model.safetensors
            tokenizer/
            metrics.json
            config.json
    """

    def __init__(
        self,
        checkpoint_dir: str = "./models/surya/checkpoints",
        base_model: str = "vikp/surya_rec"
    ):
        """
        Initialisiert den Surya Checkpoint Manager.

        Args:
            checkpoint_dir: Basis-Verzeichnis fuer Checkpoints
            base_model: Basis-Modell fuer Fine-Tuning
        """
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self.base_model = base_model

        # Qualitaetsziele
        self.target_cer = 0.03  # < 3%
        self.target_wer = 0.08  # < 8%
        self.target_umlaut_accuracy = 1.0  # 100%

        logger.info(f"SuryaCheckpointManager initialisiert: {self.checkpoint_dir}")

    # =========================================================================
    # VERSION MANAGEMENT
    # =========================================================================

    async def create_version(
        self,
        db: AsyncSession,
        source_path: str,
        metrics: Dict[str, float],
        training_config: Dict[str, Any],
        training_samples_count: int = 0,
        notes: str = "",
        user_id: Optional[str] = None
    ) -> SuryaCheckpointInfo:
        """
        Erstellt eine neue Modell-Version.

        Args:
            db: Datenbank-Session
            source_path: Pfad zum trainierten Modell
            metrics: Benchmark-Metriken (cer, wer, umlaut_accuracy, etc.)
            training_config: Training-Konfiguration
            training_samples_count: Anzahl Trainings-Samples
            notes: Notizen zur Version
            user_id: ID des Erstellers

        Returns:
            SuryaCheckpointInfo mit Versionsinformationen
        """
        from app.db.models import SuryaModelVersion

        # Version generieren
        latest = await self.get_latest_version(db)
        if latest:
            major, minor, patch = self._parse_version(latest.version)
            new_patch = patch + 1
        else:
            major, minor, new_patch = 1, 0, 0

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        version = f"v{major}.{minor}.{new_patch}_{timestamp}"

        # Checkpoint-Verzeichnis erstellen
        version_dir = self.checkpoint_dir / version
        version_dir.mkdir(parents=True, exist_ok=True)

        # Modell-Dateien kopieren
        source_path = Path(source_path)
        checkpoint_size_mb = 0.0

        if source_path.is_dir():
            for item in source_path.iterdir():
                if item.is_file():
                    shutil.copy2(item, version_dir)
                    checkpoint_size_mb += item.stat().st_size / (1024 * 1024)
                elif item.is_dir():
                    shutil.copytree(item, version_dir / item.name)
                    for f in (version_dir / item.name).rglob("*"):
                        if f.is_file():
                            checkpoint_size_mb += f.stat().st_size / (1024 * 1024)
        else:
            shutil.copy2(source_path, version_dir)
            checkpoint_size_mb = source_path.stat().st_size / (1024 * 1024)

        # Metriken speichern
        metrics_file = version_dir / "metrics.json"
        with open(metrics_file, "w", encoding="utf-8") as f:
            json.dump(metrics, f, indent=2, ensure_ascii=False)

        # Config speichern
        config_file = version_dir / "training_config.json"
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(training_config, f, indent=2, ensure_ascii=False)

        # Datenbank-Eintrag erstellen
        model_version = SuryaModelVersion(
            id=uuid_module.uuid4(),
            version=version,
            version_major=major,
            version_minor=minor,
            version_patch=new_patch,
            checkpoint_path=str(version_dir),
            checkpoint_size_mb=checkpoint_size_mb,
            base_model=self.base_model,
            parent_version_id=uuid_module.UUID(latest.id) if latest else None,
            cer=metrics.get("cer"),
            wer=metrics.get("wer"),
            umlaut_accuracy=metrics.get("umlaut_accuracy"),
            eszett_accuracy=metrics.get("eszett_accuracy"),
            capitalization_accuracy=metrics.get("capitalization_accuracy"),
            metrics_by_document_type=metrics.get("by_document_type", {}),
            umlaut_confusion_matrix=metrics.get("umlaut_confusion_matrix", {}),
            error_patterns=metrics.get("error_patterns", {}),
            training_samples_count=training_samples_count,
            training_config=training_config,
            is_active=False,
            is_production=False,
            traffic_percentage=0.0,
            created_by_id=uuid_module.UUID(user_id) if user_id else None,
            notes=notes
        )

        db.add(model_version)
        await db.commit()
        await db.refresh(model_version)

        logger.info(f"Neue Surya-Version erstellt: {version}")

        return SuryaCheckpointInfo(
            id=str(model_version.id),
            version=version,
            checkpoint_path=str(version_dir),
            created_at=model_version.created_at,
            cer=model_version.cer,
            wer=model_version.wer,
            umlaut_accuracy=model_version.umlaut_accuracy,
            eszett_accuracy=model_version.eszett_accuracy,
            training_samples_count=training_samples_count,
            is_active=False,
            is_production=False,
            traffic_percentage=0.0,
            training_config=training_config,
            notes=notes
        )

    async def get_version(
        self,
        db: AsyncSession,
        version: str
    ) -> Optional[SuryaCheckpointInfo]:
        """Holt eine spezifische Version."""
        from app.db.models import SuryaModelVersion

        result = await db.execute(
            select(SuryaModelVersion).where(SuryaModelVersion.version == version)
        )
        model = result.scalar_one_or_none()

        if not model:
            return None

        return self._model_to_checkpoint_info(model)

    async def get_version_by_id(
        self,
        db: AsyncSession,
        version_id: str
    ) -> Optional[SuryaCheckpointInfo]:
        """Holt eine Version nach ID."""
        from app.db.models import SuryaModelVersion

        result = await db.execute(
            select(SuryaModelVersion).where(
                SuryaModelVersion.id == uuid_module.UUID(version_id)
            )
        )
        model = result.scalar_one_or_none()

        if not model:
            return None

        return self._model_to_checkpoint_info(model)

    async def get_latest_version(
        self,
        db: AsyncSession
    ) -> Optional[SuryaCheckpointInfo]:
        """Holt die neueste Version."""
        from app.db.models import SuryaModelVersion

        result = await db.execute(
            select(SuryaModelVersion)
            .order_by(desc(SuryaModelVersion.created_at))
            .limit(1)
        )
        model = result.scalar_one_or_none()

        if not model:
            return None

        return self._model_to_checkpoint_info(model)

    async def get_active_version(
        self,
        db: AsyncSession
    ) -> Optional[SuryaCheckpointInfo]:
        """Holt die aktive Production-Version."""
        from app.db.models import SuryaModelVersion

        result = await db.execute(
            select(SuryaModelVersion).where(
                and_(
                    SuryaModelVersion.is_active == True,
                    SuryaModelVersion.is_production == True
                )
            )
        )
        model = result.scalar_one_or_none()

        if not model:
            return None

        return self._model_to_checkpoint_info(model)

    async def list_versions(
        self,
        db: AsyncSession,
        limit: int = 20,
        offset: int = 0,
        only_active: bool = False
    ) -> List[SuryaCheckpointInfo]:
        """Listet alle Versionen auf."""
        from app.db.models import SuryaModelVersion

        query = select(SuryaModelVersion)

        if only_active:
            query = query.where(SuryaModelVersion.is_active == True)

        query = query.order_by(desc(SuryaModelVersion.created_at))
        query = query.offset(offset).limit(limit)

        result = await db.execute(query)
        models = result.scalars().all()

        return [self._model_to_checkpoint_info(m) for m in models]

    async def get_best_version(
        self,
        db: AsyncSession,
        metric: str = "umlaut_accuracy"
    ) -> Optional[SuryaCheckpointInfo]:
        """Holt die beste Version nach Metrik."""
        from app.db.models import SuryaModelVersion

        # Fuer Accuracy: hoeherer Wert besser
        # Fuer Error Rates: niedrigerer Wert besser
        if metric in ["cer", "wer"]:
            order = getattr(SuryaModelVersion, metric).asc()
        else:
            order = getattr(SuryaModelVersion, metric).desc()

        result = await db.execute(
            select(SuryaModelVersion)
            .where(getattr(SuryaModelVersion, metric).isnot(None))
            .order_by(order)
            .limit(1)
        )
        model = result.scalar_one_or_none()

        if not model:
            return None

        return self._model_to_checkpoint_info(model)

    def _parse_version(self, version: str) -> Tuple[int, int, int]:
        """Parsed Version-String zu (major, minor, patch)."""
        try:
            version_part = version.split("_")[0]
            nums = version_part.lstrip("v").split(".")
            return int(nums[0]), int(nums[1]), int(nums[2])
        except Exception:
            return 1, 0, 0

    def _model_to_checkpoint_info(self, model: Any) -> SuryaCheckpointInfo:
        """Konvertiert DB-Modell zu CheckpointInfo."""
        return SuryaCheckpointInfo(
            id=str(model.id),
            version=model.version,
            checkpoint_path=model.checkpoint_path,
            created_at=model.created_at,
            cer=model.cer,
            wer=model.wer,
            umlaut_accuracy=model.umlaut_accuracy,
            eszett_accuracy=model.eszett_accuracy,
            training_samples_count=model.training_samples_count or 0,
            is_active=model.is_active,
            is_production=model.is_production,
            traffic_percentage=model.traffic_percentage,
            training_config=model.training_config or {},
            notes=model.notes or ""
        )

    # =========================================================================
    # ACTIVATION & DEPLOYMENT
    # =========================================================================

    async def activate_version(
        self,
        db: AsyncSession,
        version: str,
        traffic_percentage: float = 100.0,
        is_production: bool = True
    ) -> bool:
        """
        Aktiviert eine Version fuer Production.

        Args:
            db: Datenbank-Session
            version: Version zum Aktivieren
            traffic_percentage: Traffic-Anteil (fuer A/B Testing)
            is_production: Als Production-Modell markieren

        Returns:
            Erfolg
        """
        from app.db.models import SuryaModelVersion

        # Ziel-Version finden
        result = await db.execute(
            select(SuryaModelVersion).where(SuryaModelVersion.version == version)
        )
        target = result.scalar_one_or_none()

        if not target:
            logger.warning(f"Version nicht gefunden: {version}")
            return False

        # Bei 100% Traffic: andere Versionen deaktivieren
        if traffic_percentage >= 100.0:
            await db.execute(
                select(SuryaModelVersion).where(
                    SuryaModelVersion.is_active == True
                )
            )
            result = await db.execute(
                select(SuryaModelVersion).where(SuryaModelVersion.is_active == True)
            )
            active_versions = result.scalars().all()
            for v in active_versions:
                v.is_active = False
                v.is_production = False
                v.traffic_percentage = 0.0
                v.deactivated_at = datetime.utcnow()

        # Ziel-Version aktivieren
        target.is_active = True
        target.is_production = is_production
        target.traffic_percentage = traffic_percentage
        target.activated_at = datetime.utcnow()

        await db.commit()
        logger.info(f"Surya-Version aktiviert: {version} ({traffic_percentage}%)")

        return True

    async def deactivate_version(
        self,
        db: AsyncSession,
        version: str
    ) -> bool:
        """Deaktiviert eine Version."""
        from app.db.models import SuryaModelVersion

        result = await db.execute(
            select(SuryaModelVersion).where(SuryaModelVersion.version == version)
        )
        model = result.scalar_one_or_none()

        if not model:
            return False

        model.is_active = False
        model.is_production = False
        model.traffic_percentage = 0.0
        model.deactivated_at = datetime.utcnow()

        await db.commit()
        logger.info(f"Surya-Version deaktiviert: {version}")

        return True

    # =========================================================================
    # A/B TESTING
    # =========================================================================

    async def start_ab_test(
        self,
        db: AsyncSession,
        config: SuryaABTestConfig,
        test_name: str,
        description: str = "",
        user_id: Optional[str] = None
    ) -> str:
        """
        Startet einen A/B Test zwischen zwei Versionen.

        Args:
            db: Datenbank-Session
            config: A/B Test Konfiguration
            test_name: Name des Tests
            description: Beschreibung
            user_id: ID des Erstellers

        Returns:
            Test-ID
        """
        from app.db.models import SuryaABTest, SuryaABTestStatus

        ab_test = SuryaABTest(
            id=uuid_module.uuid4(),
            test_name=test_name,
            description=description,
            control_version_id=uuid_module.UUID(config.control_version_id),
            treatment_version_id=uuid_module.UUID(config.treatment_version_id),
            control_traffic_pct=100.0 - config.treatment_traffic_pct,
            treatment_traffic_pct=config.treatment_traffic_pct,
            status=SuryaABTestStatus.RUNNING.value,
            success_criteria=config.success_criteria,
            minimum_samples=config.minimum_samples,
            minimum_duration_hours=config.minimum_duration_hours,
            created_by_id=uuid_module.UUID(user_id) if user_id else None,
            started_at=datetime.utcnow()
        )

        db.add(ab_test)

        # Treatment-Version mit Traffic aktivieren
        await self.activate_version(
            db,
            (await self.get_version_by_id(db, config.treatment_version_id)).version,
            traffic_percentage=config.treatment_traffic_pct,
            is_production=False
        )

        await db.commit()
        logger.info(f"A/B Test gestartet: {test_name}")

        return str(ab_test.id)

    async def evaluate_ab_test(
        self,
        db: AsyncSession,
        test_id: str
    ) -> Dict[str, Any]:
        """
        Evaluiert einen laufenden A/B Test.

        Args:
            db: Datenbank-Session
            test_id: Test-ID

        Returns:
            Evaluations-Ergebnis mit Empfehlung
        """
        from app.db.models import SuryaABTest, SuryaABTestStatus

        result = await db.execute(
            select(SuryaABTest).where(SuryaABTest.id == uuid_module.UUID(test_id))
        )
        test = result.scalar_one_or_none()

        if not test:
            return {"error": "Test nicht gefunden"}

        evaluation = {
            "test_id": str(test.id),
            "test_name": test.test_name,
            "status": test.status,
            "control": {
                "samples": test.control_samples,
                "cer": test.control_cer,
                "wer": test.control_wer,
                "umlaut_accuracy": test.control_umlaut_accuracy
            },
            "treatment": {
                "samples": test.treatment_samples,
                "cer": test.treatment_cer,
                "wer": test.treatment_wer,
                "umlaut_accuracy": test.treatment_umlaut_accuracy
            },
            "is_ready_for_decision": test.is_ready_for_decision,
            "winner": test.winner,
            "recommendation": None
        }

        # Empfehlung berechnen
        if test.is_ready_for_decision and not test.winner:
            if (test.treatment_umlaut_accuracy and test.control_umlaut_accuracy
                    and test.treatment_cer and test.control_cer):

                umlaut_improvement = test.treatment_umlaut_accuracy - test.control_umlaut_accuracy
                cer_reduction = test.control_cer - test.treatment_cer

                criteria = test.success_criteria or {}
                target_umlaut = criteria.get("umlaut_accuracy_improvement", 0.02)
                target_cer = criteria.get("cer_reduction", 0.01)

                if umlaut_improvement >= target_umlaut and cer_reduction >= target_cer:
                    evaluation["recommendation"] = "treatment"
                    evaluation["reason"] = f"Treatment zeigt Verbesserung: Umlaut +{umlaut_improvement:.2%}, CER -{cer_reduction:.2%}"
                elif umlaut_improvement < 0 or cer_reduction < -0.01:
                    evaluation["recommendation"] = "control"
                    evaluation["reason"] = "Treatment zeigt Verschlechterung - Rollback empfohlen"
                else:
                    evaluation["recommendation"] = "inconclusive"
                    evaluation["reason"] = "Kein signifikanter Unterschied"

        return evaluation

    async def complete_ab_test(
        self,
        db: AsyncSession,
        test_id: str,
        winner: str,
        auto_deploy: bool = True
    ) -> bool:
        """
        Schliesst einen A/B Test ab.

        Args:
            db: Datenbank-Session
            test_id: Test-ID
            winner: Gewinner ("control" oder "treatment")
            auto_deploy: Automatisch deployen

        Returns:
            Erfolg
        """
        from app.db.models import SuryaABTest, SuryaABTestStatus

        result = await db.execute(
            select(SuryaABTest).where(SuryaABTest.id == uuid_module.UUID(test_id))
        )
        test = result.scalar_one_or_none()

        if not test:
            return False

        test.winner = winner
        test.status = SuryaABTestStatus.COMPLETED.value
        test.completed_at = datetime.utcnow()

        if auto_deploy and winner == "treatment":
            # Treatment-Version als Production aktivieren
            treatment_version = await self.get_version_by_id(
                db, str(test.treatment_version_id)
            )
            if treatment_version:
                await self.activate_version(
                    db,
                    treatment_version.version,
                    traffic_percentage=100.0,
                    is_production=True
                )
                test.auto_deployed = True
        elif winner == "control":
            # Treatment deaktivieren
            treatment_version = await self.get_version_by_id(
                db, str(test.treatment_version_id)
            )
            if treatment_version:
                await self.deactivate_version(db, treatment_version.version)

        await db.commit()
        logger.info(f"A/B Test abgeschlossen: {test.test_name}, Gewinner: {winner}")

        return True

    # =========================================================================
    # ROLLBACK
    # =========================================================================

    async def rollback_to_version(
        self,
        db: AsyncSession,
        target_version: str,
        reason: str = ""
    ) -> bool:
        """
        Fuehrt Rollback zu einer frueheren Version durch.

        Args:
            db: Datenbank-Session
            target_version: Ziel-Version
            reason: Grund für Rollback

        Returns:
            Erfolg
        """
        from app.db.models import SuryaModelVersion

        # Aktuelle Production-Version finden
        current = await self.get_active_version(db)

        # Ziel-Version finden
        target = await self.get_version(db, target_version)

        if not target:
            logger.error(f"Rollback-Ziel nicht gefunden: {target_version}")
            return False

        # Aktuelle Version deaktivieren
        if current:
            result = await db.execute(
                select(SuryaModelVersion).where(
                    SuryaModelVersion.version == current.version
                )
            )
            current_model = result.scalar_one_or_none()
            if current_model:
                current_model.is_active = False
                current_model.is_production = False
                current_model.traffic_percentage = 0.0
                current_model.deactivated_at = datetime.utcnow()

        # Ziel-Version aktivieren
        result = await db.execute(
            select(SuryaModelVersion).where(
                SuryaModelVersion.version == target_version
            )
        )
        target_model = result.scalar_one_or_none()

        if target_model:
            target_model.is_active = True
            target_model.is_production = True
            target_model.traffic_percentage = 100.0
            target_model.activated_at = datetime.utcnow()
            target_model.rolled_back_from_id = uuid_module.UUID(current.id) if current else None
            target_model.rollback_reason = reason

        await db.commit()
        logger.info(f"Rollback durchgefuehrt: {current.version if current else 'None'} -> {target_version}")

        return True

    async def auto_rollback_if_needed(
        self,
        db: AsyncSession,
        current_metrics: Dict[str, float]
    ) -> Optional[str]:
        """
        Prueft ob automatischer Rollback noetig ist.

        Args:
            db: Datenbank-Session
            current_metrics: Aktuelle Metriken

        Returns:
            Rollback-Version wenn Rollback durchgefuehrt, sonst None
        """
        current = await self.get_active_version(db)
        if not current:
            return None

        umlaut_acc = current_metrics.get("umlaut_accuracy", 1.0)
        cer = current_metrics.get("cer", 0.0)

        # Rollback bei kritischen Schwellenwerten
        if umlaut_acc < 0.90:  # Umlaut-Accuracy unter 90%
            # Beste vorherige Version finden
            best = await self.get_best_version(db, "umlaut_accuracy")
            if best and best.version != current.version:
                await self.rollback_to_version(
                    db,
                    best.version,
                    reason=f"Auto-Rollback: Umlaut-Accuracy {umlaut_acc:.2%} unter 90%"
                )
                return best.version

        if cer > 0.10:  # CER ueber 10%
            best = await self.get_best_version(db, "cer")
            if best and best.version != current.version:
                await self.rollback_to_version(
                    db,
                    best.version,
                    reason=f"Auto-Rollback: CER {cer:.2%} ueber 10%"
                )
                return best.version

        return None

    # =========================================================================
    # BENCHMARK HISTORY
    # =========================================================================

    async def save_benchmark_result(
        self,
        db: AsyncSession,
        version_id: str,
        metrics: Dict[str, Any],
        benchmark_type: str = "full",
        comparison_version_id: Optional[str] = None
    ) -> str:
        """
        Speichert Benchmark-Ergebnisse.

        Args:
            db: Datenbank-Session
            version_id: Modell-Version ID
            metrics: Benchmark-Metriken
            benchmark_type: Art des Benchmarks
            comparison_version_id: Vergleichs-Version ID

        Returns:
            Benchmark-History ID
        """
        from app.db.models import SuryaBenchmarkHistory

        benchmark = SuryaBenchmarkHistory(
            id=uuid_module.uuid4(),
            model_version_id=uuid_module.UUID(version_id),
            benchmark_type=benchmark_type,
            test_fixtures_count=metrics.get("test_fixtures_count"),
            avg_cer=metrics.get("avg_cer"),
            avg_wer=metrics.get("avg_wer"),
            avg_umlaut_accuracy=metrics.get("avg_umlaut_accuracy"),
            avg_processing_time_ms=metrics.get("avg_processing_time_ms"),
            p50_cer=metrics.get("p50_cer"),
            p90_cer=metrics.get("p90_cer"),
            p95_cer=metrics.get("p95_cer"),
            p99_cer=metrics.get("p99_cer"),
            results_by_fixture=metrics.get("results_by_fixture", {}),
            results_by_document_type=metrics.get("results_by_document_type", {}),
            umlaut_confusion_details=metrics.get("umlaut_confusion_details", {}),
            comparison_version_id=uuid_module.UUID(comparison_version_id) if comparison_version_id else None,
            cer_improvement=metrics.get("cer_improvement"),
            wer_improvement=metrics.get("wer_improvement"),
            umlaut_accuracy_improvement=metrics.get("umlaut_accuracy_improvement")
        )

        db.add(benchmark)
        await db.commit()

        logger.info(f"Benchmark-Ergebnis gespeichert fuer Version {version_id}")
        return str(benchmark.id)

    async def get_benchmark_history(
        self,
        db: AsyncSession,
        version_id: Optional[str] = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Holt Benchmark-History."""
        from app.db.models import SuryaBenchmarkHistory

        query = select(SuryaBenchmarkHistory)

        if version_id:
            query = query.where(
                SuryaBenchmarkHistory.model_version_id == uuid_module.UUID(version_id)
            )

        query = query.order_by(desc(SuryaBenchmarkHistory.created_at)).limit(limit)

        result = await db.execute(query)
        benchmarks = result.scalars().all()

        return [
            {
                "id": str(b.id),
                "model_version_id": str(b.model_version_id),
                "benchmark_type": b.benchmark_type,
                "avg_cer": b.avg_cer,
                "avg_wer": b.avg_wer,
                "avg_umlaut_accuracy": b.avg_umlaut_accuracy,
                "created_at": b.created_at.isoformat() if b.created_at else None
            }
            for b in benchmarks
        ]

    # =========================================================================
    # CLEANUP & STORAGE
    # =========================================================================

    async def cleanup_old_versions(
        self,
        db: AsyncSession,
        keep_count: int = 5,
        keep_active: bool = True,
        keep_best_umlaut: bool = True
    ) -> int:
        """
        Raeumt alte Versionen auf.

        Args:
            db: Datenbank-Session
            keep_count: Anzahl zu behaltender Versionen
            keep_active: Aktive Versionen behalten
            keep_best_umlaut: Beste Umlaut-Version behalten

        Returns:
            Anzahl geloeschter Versionen
        """
        from app.db.models import SuryaModelVersion

        # Alle Versionen holen
        result = await db.execute(
            select(SuryaModelVersion).order_by(desc(SuryaModelVersion.created_at))
        )
        all_versions = result.scalars().all()

        # Zu behaltende Versionen identifizieren
        keep_ids = set()

        # Neueste behalten
        for v in all_versions[:keep_count]:
            keep_ids.add(v.id)

        # Aktive behalten
        if keep_active:
            for v in all_versions:
                if v.is_active:
                    keep_ids.add(v.id)

        # Beste Umlaut-Version behalten
        if keep_best_umlaut:
            best = await self.get_best_version(db, "umlaut_accuracy")
            if best:
                keep_ids.add(uuid_module.UUID(best.id))

        # Versionen loeschen
        deleted_count = 0
        for v in all_versions:
            if v.id not in keep_ids:
                # Dateien loeschen
                checkpoint_path = Path(v.checkpoint_path)
                if checkpoint_path.exists():
                    shutil.rmtree(checkpoint_path)

                # DB-Eintrag loeschen
                await db.delete(v)
                deleted_count += 1

        await db.commit()
        logger.info(f"Cleanup: {deleted_count} alte Surya-Versionen geloescht")

        return deleted_count

    async def get_storage_stats(self, db: AsyncSession) -> Dict[str, Any]:
        """Gibt Speicherstatistiken zurueck."""
        from app.db.models import SuryaModelVersion

        result = await db.execute(select(SuryaModelVersion))
        versions = result.scalars().all()

        total_size_mb = 0.0
        version_count = len(versions)
        active_version = None

        for v in versions:
            if v.checkpoint_size_mb:
                total_size_mb += v.checkpoint_size_mb
            if v.is_active and v.is_production:
                active_version = v.version

        return {
            "total_size_mb": round(total_size_mb, 2),
            "version_count": version_count,
            "active_version": active_version,
            "checkpoint_dir": str(self.checkpoint_dir),
            "quality_targets": {
                "cer": f"< {self.target_cer:.0%}",
                "wer": f"< {self.target_wer:.0%}",
                "umlaut_accuracy": f"= {self.target_umlaut_accuracy:.0%}"
            }
        }

    # =========================================================================
    # MODEL SELECTION (A/B Routing)
    # =========================================================================

    async def select_model_for_request(
        self,
        db: AsyncSession,
        request_id: Optional[str] = None
    ) -> Optional[SuryaCheckpointInfo]:
        """
        Waehlt Modell fuer eine Anfrage basierend auf A/B Testing.

        Args:
            db: Datenbank-Session
            request_id: Request-ID fuer deterministische Auswahl

        Returns:
            Ausgewaehlte Modell-Version
        """
        from app.db.models import SuryaModelVersion

        # Aktive Versionen mit Traffic holen
        result = await db.execute(
            select(SuryaModelVersion).where(
                and_(
                    SuryaModelVersion.is_active == True,
                    SuryaModelVersion.traffic_percentage > 0
                )
            ).order_by(desc(SuryaModelVersion.traffic_percentage))
        )
        active_versions = result.scalars().all()

        if not active_versions:
            return await self.get_latest_version(db)

        # Bei nur einer aktiven Version: diese zurueckgeben
        if len(active_versions) == 1:
            return self._model_to_checkpoint_info(active_versions[0])

        # A/B Routing basierend auf Request-ID oder Zufall
        import hashlib
        import random

        if request_id:
            # Deterministische Auswahl basierend auf Request-ID
            hash_val = int(hashlib.md5(request_id.encode()).hexdigest(), 16)
            selection_pct = (hash_val % 100) / 100.0
        else:
            selection_pct = random.random()

        # Version basierend auf Traffic-Percentage auswaehlen
        cumulative_pct = 0.0
        for v in active_versions:
            cumulative_pct += v.traffic_percentage / 100.0
            if selection_pct <= cumulative_pct:
                return self._model_to_checkpoint_info(v)

        # Fallback: erste aktive Version
        return self._model_to_checkpoint_info(active_versions[0])

    def get_checkpoint_path(self, version: str) -> Path:
        """Gibt den Checkpoint-Pfad fuer eine Version zurueck."""
        return self.checkpoint_dir / version

    def checkpoint_exists(self, version: str) -> bool:
        """Prueft ob Checkpoint existiert."""
        return self.get_checkpoint_path(version).exists()

"""Surya OCR Training und Versioning Models.

Modularisierung Phase 1.1 - Ausgelagert aus app/db/models.py.
Re-Exports erfolgen in models.py für Rückwärtskompatibilität.
"""

from datetime import datetime, timezone
from typing import Optional
from enum import Enum
import uuid

from sqlalchemy import Column, String, Integer, DateTime, Boolean, Float, Text, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.models_base import Base, CrossDBJSON


# ============================================================================
# SURYA MODEL VERSIONING
# Continuous Improvement System für Surya OCR
# ============================================================================

class SuryaModelStatus(str, Enum):
    """Status eines Surya-Modells."""
    TRAINING = "training"       # Im Training
    EVALUATING = "evaluating"   # Wird evaluiert
    READY = "ready"             # Bereit zur Aktivierung
    ACTIVE = "active"           # Aktiv in Produktion
    INACTIVE = "inactive"       # Deaktiviert
    FAILED = "failed"           # Training fehlgeschlagen
    ROLLED_BACK = "rolled_back" # Zurückgerollt


class SuryaTrainingRunStatus(str, Enum):
    """Status eines Training-Durchlaufs."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SuryaABTestStatus(str, Enum):
    """Status eines A/B Tests."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    ABORTED = "aborted"


class SuryaModelVersion(Base):
    """
    Versioniertes Surya OCR Model für Continuous Improvement.

    Speichert:
    - Checkpoint-Pfade und Versionen
    - Qualitaetsmetriken (CER, WER, Umlaut-Accuracy)
    - Training-Konfiguration
    - Deployment-Status und A/B Testing

    Workflow:
    1. Training erzeugt neue Version (TRAINING)
    2. Benchmark evaluiert Qualitaet (EVALUATING)
    3. A/B Test mit 20% Traffic (ACTIVE + traffic_percentage)
    4. Bei Erfolg: 100% Traffic (ACTIVE + is_production)
    5. Bei Problemen: Rollback zur vorherigen Version
    """
    __tablename__ = "surya_model_versions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Versions-Identifikation
    version = Column(String(100), nullable=False, unique=True)  # z.B. "v1.0.3_20241215_143022"
    version_major = Column(Integer, nullable=False, default=1)
    version_minor = Column(Integer, nullable=False, default=0)
    version_patch = Column(Integer, nullable=False, default=0)

    # Checkpoint-Pfade
    checkpoint_path = Column(String(500), nullable=False)
    checkpoint_size_mb = Column(Float, nullable=True)

    # Basis-Modell
    base_model = Column(String(100), default="vikp/surya_rec")
    parent_version_id = Column(
        UUID(as_uuid=True),
        ForeignKey("surya_model_versions.id", ondelete="SET NULL"),
        nullable=True
    )

    # Qualitaetsmetriken (Benchmark-Ergebnisse)
    cer = Column(Float, nullable=True)  # Character Error Rate (Ziel: < 3%)
    wer = Column(Float, nullable=True)  # Word Error Rate (Ziel: < 8%)
    umlaut_accuracy = Column(Float, nullable=True)  # Umlaut-Genauigkeit (Ziel: 100%)
    eszett_accuracy = Column(Float, nullable=True)  # SS-Genauigkeit
    capitalization_accuracy = Column(Float, nullable=True)

    # Detaillierte Metriken (JSON)
    metrics_by_document_type = Column(CrossDBJSON, default=dict)
    umlaut_confusion_matrix = Column(CrossDBJSON, default=dict)  # {"ae->a": 5, "ue->u": 3}
    error_patterns = Column(CrossDBJSON, default=dict)

    # Training-Informationen
    training_samples_count = Column(Integer, nullable=True)
    training_epochs = Column(Integer, nullable=True)
    training_config = Column(CrossDBJSON, default=dict)
    training_duration_minutes = Column(Float, nullable=True)

    # Deployment-Status
    is_active = Column(Boolean, default=False)  # Ist aktiviert
    is_production = Column(Boolean, default=False)  # Ist Production-Modell
    traffic_percentage = Column(Float, default=0.0)  # A/B Testing Traffic-Anteil

    # Rollback-Info
    rolled_back_from_id = Column(
        UUID(as_uuid=True),
        ForeignKey("surya_model_versions.id", ondelete="SET NULL"),
        nullable=True
    )
    rollback_reason = Column(Text, nullable=True)

    # Audit
    created_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    notes = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    activated_at = Column(DateTime(timezone=True), nullable=True)
    deactivated_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    parent_version = relationship("SuryaModelVersion", remote_side=[id], foreign_keys=[parent_version_id])
    created_by = relationship("User", foreign_keys=[created_by_id])
    training_runs = relationship("SuryaTrainingRun", back_populates="model_version")
    benchmark_history = relationship(
        "SuryaBenchmarkHistory",
        back_populates="model_version",
        foreign_keys="SuryaBenchmarkHistory.model_version_id"
    )

    # Indexes
    __table_args__ = (
        Index("ix_surya_model_versions_version", "version"),
        Index("ix_surya_model_versions_is_active", "is_active"),
        Index("ix_surya_model_versions_is_production", "is_production"),
        Index("ix_surya_model_versions_created_at", "created_at"),
        Index("ix_surya_model_versions_umlaut_acc", "umlaut_accuracy"),
        Index("ix_surya_model_versions_cer", "cer"),
    )

    @property
    def full_version(self) -> str:
        """Gibt vollständige Version zurück."""
        return f"v{self.version_major}.{self.version_minor}.{self.version_patch}"

    @property
    def is_quality_sufficient(self) -> bool:
        """Prüft ob Qualitaetsziele erreicht sind."""
        if self.cer is None or self.umlaut_accuracy is None:
            return False
        return self.cer < 0.03 and self.umlaut_accuracy >= 1.0


class SuryaTrainingRun(Base):
    """
    Training-Durchlauf für Surya Fine-Tuning.

    Dokumentiert:
    - Training-Konfiguration und Dataset
    - Fortschritt und Loss-Verlauf
    - Ressourcen-Nutzung
    - Fehlerbehandlung

    Typen:
    - full: Komplettes Training von Grund auf
    - incremental: Inkrementelles Training mit neuen Daten
    - correction_based: Training basierend auf User-Korrektionen
    """
    __tablename__ = "surya_training_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Referenz auf resultierendes Modell
    model_version_id = Column(
        UUID(as_uuid=True),
        ForeignKey("surya_model_versions.id", ondelete="SET NULL"),
        nullable=True
    )

    # Run-Identifikation
    run_name = Column(String(255), nullable=False)
    run_type = Column(String(50), default="incremental")  # full, incremental, correction_based

    # Trigger-Informationen
    trigger_reason = Column(String(100), nullable=True)  # scheduled, correction_threshold, manual, quality_degradation
    trigger_metrics = Column(CrossDBJSON, default=dict)  # Metriken die zum Trigger führten

    # Training-Konfiguration
    config = Column(CrossDBJSON, nullable=False, default=dict)
    dataset_config = Column(CrossDBJSON, default=dict)

    # Dataset-Statistiken
    training_samples = Column(Integer, default=0)
    validation_samples = Column(Integer, default=0)
    test_samples = Column(Integer, default=0)
    umlaut_samples = Column(Integer, default=0)  # Samples mit Umlauten
    fraktur_samples = Column(Integer, default=0)  # Fraktur-Samples

    # Training-Fortschritt
    status = Column(String(30), default=SuryaTrainingRunStatus.PENDING.value)
    current_epoch = Column(Integer, default=0)
    total_epochs = Column(Integer, nullable=True)
    current_step = Column(Integer, default=0)
    total_steps = Column(Integer, nullable=True)

    # Loss-Tracking
    training_loss = Column(Float, nullable=True)
    validation_loss = Column(Float, nullable=True)
    best_validation_loss = Column(Float, nullable=True)
    loss_history = Column(CrossDBJSON, default=list)  # [{epoch: 1, train_loss: 0.5, val_loss: 0.6}]

    # Metriken während Training
    metrics_history = Column(CrossDBJSON, default=list)  # Checkpoint-Metriken

    # Ressourcen-Nutzung
    gpu_memory_peak_mb = Column(Integer, nullable=True)
    gpu_utilization_avg = Column(Float, nullable=True)

    # Fehlerbehandlung
    error_message = Column(Text, nullable=True)
    error_traceback = Column(Text, nullable=True)

    # Audit
    started_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    model_version = relationship("SuryaModelVersion", back_populates="training_runs")
    started_by = relationship("User", foreign_keys=[started_by_id])

    # Indexes
    __table_args__ = (
        Index("ix_surya_training_runs_status", "status"),
        Index("ix_surya_training_runs_type", "run_type"),
        Index("ix_surya_training_runs_model", "model_version_id"),
        Index("ix_surya_training_runs_created", "created_at"),
    )

    @property
    def progress_percent(self) -> float:
        """Berechnet Training-Fortschritt in Prozent."""
        if self.total_epochs is None or self.total_epochs == 0:
            return 0.0
        return (self.current_epoch / self.total_epochs) * 100

    @property
    def duration_minutes(self) -> Optional[float]:
        """Berechnet bisherige Dauer in Minuten."""
        if self.started_at is None:
            return None
        end_time = self.completed_at or datetime.now(timezone.utc)
        delta = end_time - self.started_at
        return delta.total_seconds() / 60


class SuryaABTest(Base):
    """
    A/B Test für Surya Model-Vergleich.

    Ermöglicht:
    - Traffic-Splitting zwischen Control und Treatment
    - Statistische Signifikanz-Berechnung
    - Automatische Entscheidung und Deployment
    - Rollback bei Qualitaetsverlust

    Workflow:
    1. Control (80%) vs Treatment (20%)
    2. Mindestens 100 Samples pro Gruppe
    3. Mindestens 48 Stunden Laufzeit
    4. Entscheidung basierend auf Umlaut-Accuracy und CER
    """
    __tablename__ = "surya_ab_tests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Test-Identifikation
    test_name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Modell-Versionen im Test
    control_version_id = Column(
        UUID(as_uuid=True),
        ForeignKey("surya_model_versions.id", ondelete="CASCADE"),
        nullable=False
    )
    treatment_version_id = Column(
        UUID(as_uuid=True),
        ForeignKey("surya_model_versions.id", ondelete="CASCADE"),
        nullable=False
    )

    # Traffic-Konfiguration
    control_traffic_pct = Column(Float, default=80.0)
    treatment_traffic_pct = Column(Float, default=20.0)

    # Test-Status
    status = Column(String(30), default=SuryaABTestStatus.PENDING.value)

    # Erfolgskriterien
    success_criteria = Column(CrossDBJSON, default=dict)  # {"umlaut_accuracy_improvement": 0.02}
    minimum_samples = Column(Integer, default=100)
    minimum_duration_hours = Column(Integer, default=48)

    # Ergebnisse - Control
    control_samples = Column(Integer, default=0)
    control_cer = Column(Float, nullable=True)
    control_wer = Column(Float, nullable=True)
    control_umlaut_accuracy = Column(Float, nullable=True)
    control_metrics = Column(CrossDBJSON, default=dict)

    # Ergebnisse - Treatment
    treatment_samples = Column(Integer, default=0)
    treatment_cer = Column(Float, nullable=True)
    treatment_wer = Column(Float, nullable=True)
    treatment_umlaut_accuracy = Column(Float, nullable=True)
    treatment_metrics = Column(CrossDBJSON, default=dict)

    # Statistische Analyse
    statistical_significance = Column(Float, nullable=True)  # p-value
    confidence_interval_lower = Column(Float, nullable=True)
    confidence_interval_upper = Column(Float, nullable=True)
    effect_size = Column(Float, nullable=True)

    # Entscheidung
    winner = Column(String(20), nullable=True)  # control, treatment, inconclusive
    decision_reason = Column(Text, nullable=True)
    auto_deployed = Column(Boolean, default=False)

    # Audit
    created_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    control_version = relationship("SuryaModelVersion", foreign_keys=[control_version_id])
    treatment_version = relationship("SuryaModelVersion", foreign_keys=[treatment_version_id])
    created_by = relationship("User", foreign_keys=[created_by_id])

    # Indexes
    __table_args__ = (
        Index("ix_surya_ab_tests_status", "status"),
        Index("ix_surya_ab_tests_control", "control_version_id"),
        Index("ix_surya_ab_tests_treatment", "treatment_version_id"),
        Index("ix_surya_ab_tests_created", "created_at"),
    )

    @property
    def is_ready_for_decision(self) -> bool:
        """Prüft ob Test bereit für Entscheidung ist."""
        if self.control_samples < self.minimum_samples:
            return False
        if self.treatment_samples < self.minimum_samples:
            return False
        if self.started_at is None:
            return False
        elapsed_hours = (datetime.now(timezone.utc) - self.started_at).total_seconds() / 3600
        return elapsed_hours >= self.minimum_duration_hours

    @property
    def treatment_improvement(self) -> Optional[float]:
        """Berechnet Verbesserung der Treatment-Gruppe."""
        if self.control_umlaut_accuracy is None or self.treatment_umlaut_accuracy is None:
            return None
        return self.treatment_umlaut_accuracy - self.control_umlaut_accuracy


class SuryaBenchmarkHistory(Base):
    """
    Benchmark-History für Surya Model Versionen.

    Speichert detaillierte Benchmark-Ergebnisse für:
    - Trendanalyse über Zeit
    - Vergleich zwischen Versionen
    - Identifikation von Regressionen
    """
    __tablename__ = "surya_benchmark_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Modell-Referenz
    model_version_id = Column(
        UUID(as_uuid=True),
        ForeignKey("surya_model_versions.id", ondelete="CASCADE"),
        nullable=False
    )

    # Benchmark-Kontext
    benchmark_type = Column(String(50), default="full")  # full, umlaut_focus, fraktur, quick
    test_fixtures_count = Column(Integer, nullable=True)

    # Aggregierte Metriken
    avg_cer = Column(Float, nullable=True)
    avg_wer = Column(Float, nullable=True)
    avg_umlaut_accuracy = Column(Float, nullable=True)
    avg_processing_time_ms = Column(Float, nullable=True)

    # Percentile
    p50_cer = Column(Float, nullable=True)
    p90_cer = Column(Float, nullable=True)
    p95_cer = Column(Float, nullable=True)
    p99_cer = Column(Float, nullable=True)

    # Detaillierte Ergebnisse
    results_by_fixture = Column(CrossDBJSON, default=dict)
    results_by_document_type = Column(CrossDBJSON, default=dict)
    umlaut_confusion_details = Column(CrossDBJSON, default=dict)

    # Vergleich mit vorheriger Version
    comparison_version_id = Column(
        UUID(as_uuid=True),
        ForeignKey("surya_model_versions.id", ondelete="SET NULL"),
        nullable=True
    )
    cer_improvement = Column(Float, nullable=True)
    wer_improvement = Column(Float, nullable=True)
    umlaut_accuracy_improvement = Column(Float, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    model_version = relationship("SuryaModelVersion", back_populates="benchmark_history", foreign_keys=[model_version_id])
    comparison_version = relationship("SuryaModelVersion", foreign_keys=[comparison_version_id])

    # Indexes
    __table_args__ = (
        Index("ix_surya_benchmark_history_model", "model_version_id"),
        Index("ix_surya_benchmark_history_type", "benchmark_type"),
        Index("ix_surya_benchmark_history_created", "created_at"),
    )


# =============================================================================
# BUSINESS DOCUMENT PROFILES - Auto Ground-Truth Pipeline
# =============================================================================

class BusinessDocumentProfile(Base):
    """
    Business Document Profile für priorisierte Training-Pipeline.

    Bei 500+ Dokumenten/Tag ist manuelle Annotation unrealistisch.
    Dieses Model definiert:
    - Geschäftskritische Dokumenttypen (Rechnungen, Verträge, Briefe)
    - Tägliche Volumen-Schätzungen
    - Auto-Accept Schwellenwerte für High-Confidence OCR

    Beispiel:
        Invoice: daily_volume=300, business_criticality=1.5, auto_accept_confidence=0.95
        Contract: daily_volume=100, business_criticality=1.3, auto_accept_confidence=0.95
        Letter: daily_volume=100, business_criticality=1.0, auto_accept_confidence=0.93
    """
    __tablename__ = "business_document_profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Dokumenttyp-Identifikation
    document_type = Column(String(50), unique=True, nullable=False)  # "invoice", "contract", "letter"
    display_name = Column(String(100), nullable=False)  # "Rechnung", "Vertrag", "Brief"
    description = Column(Text, nullable=True)

    # Business-Gewichtung
    estimated_daily_volume = Column(Integer, default=100)  # Geschätzte Dokumente pro Tag
    business_criticality = Column(Float, default=1.0)  # 1.5 = hoch, 1.0 = normal, 0.5 = niedrig

    # Auto-Annotation Schwellenwerte
    auto_accept_confidence = Column(Float, default=0.95)  # Minimum Confidence für Auto-Accept
    min_text_length = Column(Integer, default=50)  # Minimum Textlänge für gültige Samples
    require_umlaut_validation = Column(Boolean, default=True)  # Umlaut-Check vor Auto-Accept

    # Training-Gewichtung (berechnet)
    training_weight = Column(Float, default=1.0)  # Wird aus criticality + volume berechnet
    target_coverage = Column(Float, default=0.90)  # Ziel: 90% Abdeckung

    # Validierungsregeln (JSON)
    validation_rules = Column(CrossDBJSON, default=dict)
    # Beispiel: {"required_fields": ["invoice_number", "date", "amount"], "date_patterns": [...]}

    # Statistiken (wird periodisch aktualisiert)
    current_sample_count = Column(Integer, default=0)
    verified_sample_count = Column(Integer, default=0)
    auto_accepted_count = Column(Integer, default=0)
    coverage_percentage = Column(Float, default=0.0)

    # Aktivierung
    is_active = Column(Boolean, default=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Indexes
    __table_args__ = (
        Index("ix_business_document_profiles_type", "document_type"),
        Index("ix_business_document_profiles_active", "is_active"),
        Index("ix_business_document_profiles_criticality", "business_criticality"),
    )

    def calculate_training_weight(self) -> float:
        """Berechnet Training-Gewicht aus Volumen und Kritikalitaet."""
        volume_factor = min(self.estimated_daily_volume / 100.0, 3.0)  # Max 3x
        return volume_factor * self.business_criticality

    def calculate_coverage(self) -> float:
        """Berechnet aktuelle Coverage gegen Ziel."""
        if self.estimated_daily_volume == 0:
            return 1.0
        target_samples = int(self.estimated_daily_volume * self.target_coverage * 0.1)  # 10% Sample-Ratio
        if target_samples == 0:
            return 1.0
        return min(self.verified_sample_count / target_samples, 1.0)


class CoverageSnapshot(Base):
    """
    Täglicher Coverage-Snapshot für Trend-Analyse.

    Celery Beat Task speichert täglich den Stand der Ground-Truth-Abdeckung
    für alle Business-Dokumenttypen.
    """
    __tablename__ = "coverage_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Snapshot-Datum
    snapshot_date = Column(DateTime(timezone=True), nullable=False)

    # Aggregierte Metriken
    total_documents_processed = Column(Integer, default=0)
    total_auto_accepted = Column(Integer, default=0)
    total_manually_verified = Column(Integer, default=0)
    total_rejected = Column(Integer, default=0)

    # Coverage pro Dokumenttyp (JSON)
    coverage_by_type = Column(CrossDBJSON, default=dict)
    # Beispiel: {"invoice": 0.92, "contract": 0.78, "letter": 0.85}

    # Gewichtete Gesamt-Coverage
    weighted_coverage = Column(Float, default=0.0)

    # Qualitaetsmetriken der Auto-Accepts
    auto_accept_avg_confidence = Column(Float, nullable=True)
    spot_check_success_rate = Column(Float, nullable=True)  # Rate der bestandenen Stichproben

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Indexes
    __table_args__ = (
        Index("ix_coverage_snapshots_date", "snapshot_date"),
        Index("ix_coverage_snapshots_weighted", "weighted_coverage"),
    )

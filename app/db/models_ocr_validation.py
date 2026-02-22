"""OCR Training und Validation Modelle - extrahiert aus models.py (Modularisierung Phase 1.1)."""
import uuid
from datetime import datetime, date
from enum import Enum
from sqlalchemy import Column, String, Integer, Boolean, DateTime, Text, Float, ForeignKey, Index, Date, func, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.db.models_base import Base, CrossDBJSON


class TrainingSampleStatus(str, Enum):
    """Status eines Training-Samples."""
    PENDING = "pending"           # Noch nicht annotiert
    IN_PROGRESS = "in_progress"   # Wird gerade bearbeitet
    ANNOTATED = "annotated"       # Annotiert, wartet auf Verifikation
    VERIFIED = "verified"         # Von Admin verifiziert
    REJECTED = "rejected"         # Abgelehnt (schlechte Qualitaet)


class OCRTrainingSample(Base):
    """
    Ground Truth Training Sample für OCR-Benchmarking.

    Speichert Dokumente mit manuell verifiziertem Referenztext
    für die Qualitaetsmessung aller OCR-Backends.

    Workflow:
    1. Dokument wird als Sample ausgewaehlt (PENDING)
    2. Editor annotiert Ground Truth (ANNOTATED)
    3. Admin verifiziert (VERIFIED)
    4. Benchmarks laufen gegen verifizierte Samples
    """
    __tablename__ = "ocr_training_samples"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Multi-Tenant
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=True,  # nullable for backfill of existing data
        index=True,
    )

    # Dokumentreferenz
    file_path = Column(String(500), nullable=False)
    file_hash = Column(String(64), nullable=False, index=True)  # SHA-256
    thumbnail_path = Column(String(500), nullable=True)

    # Ground Truth (manuell verifizierter Text)
    ground_truth_text = Column(Text, nullable=True)

    # Dokumentklassifikation
    language = Column(String(10), default="de")  # de, nl, pl, en
    document_type = Column(String(50), nullable=True)  # invoice, freight, email, letter
    difficulty = Column(String(20), default="medium")  # easy, medium, hard

    # Dokumenteigenschaften
    has_umlauts = Column(Boolean, default=False)
    has_fraktur = Column(Boolean, default=False)
    has_tables = Column(Boolean, default=False)
    has_handwriting = Column(Boolean, default=False)
    has_stamps = Column(Boolean, default=False)
    has_signatures = Column(Boolean, default=False)

    # Umlaut-Tracking (kritisch für Deutsche Dokumente)
    umlaut_words = Column(CrossDBJSON, default=list)  # ["Muenchen", "Größe", "übergeben"]

    # Extrahierte Felder (für Field-Accuracy)
    extracted_fields = Column(CrossDBJSON, default=dict)  # {invoice_number, date, amount, vat, sender, recipient}

    # Workflow Status
    status = Column(String(20), default=TrainingSampleStatus.PENDING.value, nullable=False)

    # Auto-Accept Pipeline Felder (Phase 1.3)
    business_priority = Column(Float, default=1.0)  # Aus BusinessDocumentProfile.training_weight
    auto_accepted = Column(Boolean, default=False)  # True wenn durch Auto-Accept Pipeline erstellt
    auto_acceptance_confidence = Column(Float, nullable=True)  # OCR Confidence bei Auto-Accept
    source = Column(String(30), default="manual")  # "manual", "auto_accepted", "correction"
    needs_spot_check = Column(Boolean, default=False)  # True für 10% Stichproben-Review
    spot_check_passed = Column(Boolean, nullable=True)  # Ergebnis des Stichproben-Reviews
    spot_checked_at = Column(DateTime(timezone=True), nullable=True)
    spot_checked_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # LLM Review Pipeline Felder (Phase 6)
    llm_review_status = Column(String(20), default="pending")  # pending, reviewed, accepted, rejected, needs_human
    llm_review_result = Column(CrossDBJSON, nullable=True)  # {quality_score, issues_found, recommendation, reasoning}
    llm_corrected_text = Column(Text, nullable=True)  # Korrigierter Text vom LLM
    llm_reviewed_at = Column(DateTime(timezone=True), nullable=True)

    # Annotation Tracking
    annotated_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    verified_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    annotation_notes = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    annotated_at = Column(DateTime(timezone=True), nullable=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)  # GDPR Soft-Delete

    # Relationships
    annotated_by = relationship("User", foreign_keys=[annotated_by_id])
    verified_by = relationship("User", foreign_keys=[verified_by_id])
    spot_checked_by = relationship("User", foreign_keys=[spot_checked_by_id])
    benchmarks = relationship("OCRBackendBenchmark", back_populates="training_sample", cascade="all, delete-orphan")

    # Indexes
    __table_args__ = (
        Index("ix_ocr_training_samples_company_id", "company_id"),
        Index("ix_ocr_training_samples_company_status", "company_id", "status"),
        Index("ix_ocr_training_samples_status", "status"),
        Index("ix_ocr_training_samples_language", "language"),
        Index("ix_ocr_training_samples_document_type", "document_type"),
        Index("ix_ocr_training_samples_file_hash", "file_hash"),
        Index("ix_ocr_training_samples_verified", "status", "verified_at"),
        Index("ix_ocr_training_samples_deleted_at", "deleted_at"),
        # Auto-Accept Pipeline Indexes
        Index("ix_ocr_training_samples_auto_accepted", "auto_accepted"),
        Index("ix_ocr_training_samples_source", "source"),
        Index("ix_ocr_training_samples_spot_check", "needs_spot_check", "spot_check_passed"),
        Index("ix_ocr_training_samples_priority", "business_priority"),
        # LLM Review Pipeline Index
        Index("ix_ocr_training_samples_llm_review", "llm_review_status"),
    )

    @property
    def is_deleted(self) -> bool:
        """Check if sample is soft-deleted (GDPR)."""
        return self.deleted_at is not None


class OCRBackendBenchmark(Base):
    """
    Benchmark-Ergebnis eines OCR-Backends gegen ein Training Sample.

    Speichert:
    - OCR-Output des Backends
    - Qualitaetsmetriken (CER, WER, Umlaut-Accuracy)
    - Verarbeitungszeit und Ressourcenverbrauch
    - Feld-spezifische Genauigkeit
    """
    __tablename__ = "ocr_backend_benchmarks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Referenzen
    training_sample_id = Column(
        UUID(as_uuid=True),
        ForeignKey("ocr_training_samples.id", ondelete="CASCADE"),
        nullable=False
    )

    # Backend Identifikation
    backend_name = Column(String(50), nullable=False)  # deepseek, got_ocr, surya_gpu, surya_cpu
    backend_version = Column(String(50), nullable=True)

    # OCR Output
    raw_text = Column(Text, nullable=True)

    # Qualitaetsmetriken
    confidence_score = Column(Float, nullable=True)  # 0.0-1.0 vom Backend
    cer = Column(Float, nullable=True)  # Character Error Rate
    wer = Column(Float, nullable=True)  # Word Error Rate
    umlaut_accuracy = Column(Float, nullable=True)  # Umlaut-Genauigkeit 0.0-1.0
    capitalization_accuracy = Column(Float, nullable=True)  # Grossschreibung

    # Feld-spezifische Genauigkeit
    field_accuracies = Column(CrossDBJSON, default=dict)  # {invoice_number: 1.0, date: 0.9, amount: 1.0}

    # Fehler-Pattern-Analyse
    error_patterns = Column(CrossDBJSON, default=dict)  # {umlaut_errors: 2, date_format: 1}
    insertions = Column(Integer, default=0)
    deletions = Column(Integer, default=0)
    substitutions = Column(Integer, default=0)

    # Performance-Metriken
    processing_time_ms = Column(Integer, nullable=True)
    gpu_memory_mb = Column(Integer, nullable=True)

    # Timestamps
    processed_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    training_sample = relationship("OCRTrainingSample", back_populates="benchmarks")

    # Indexes
    __table_args__ = (
        Index("ix_ocr_backend_benchmarks_sample", "training_sample_id"),
        Index("ix_ocr_backend_benchmarks_backend", "backend_name"),
        Index("ix_ocr_backend_benchmarks_sample_backend", "training_sample_id", "backend_name"),
        Index("ix_ocr_backend_benchmarks_processed_at", "processed_at"),
        Index("ix_ocr_backend_benchmarks_cer", "cer"),
    )


class CorrectionType(str, Enum):
    """Typ der OCR-Korrektur."""
    UMLAUT = "umlaut"           # Umlaut-Fehler (a->ae, etc.)
    DATE = "date"               # Datumsformat
    AMOUNT = "amount"           # Betrag/Währung
    NAME = "name"               # Firmen-/Personenname
    IBAN = "iban"               # IBAN/Bankdaten
    VAT_ID = "vat_id"           # USt-IdNr
    GENERAL = "general"         # Allgemeine Korrektur


class OCRValidationCorrection(Base):
    """
    Feedback-Korrektur aus der Produktion.

    Wenn Benutzer OCR-Fehler korrigieren, wird das Feedback
    gesammelt und für Self-Learning verwendet.

    Self-Learning Workflow:
    1. Benutzer korrigiert OCR-Fehler
    2. Korrektur wird gespeichert und analysiert
    3. Fehler-Patterns werden pro Backend aggregiert
    4. OCR Router passt Backend-Auswahl an
    """
    __tablename__ = "ocr_validation_corrections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Dokument-Referenz (aus Produktion)
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True
    )

    # Korrektur-Details
    original_text = Column(Text, nullable=False)
    corrected_text = Column(Text, nullable=False)
    correction_type = Column(String(30), default=CorrectionType.GENERAL.value)
    field_corrected = Column(String(50), nullable=True)  # Welches Feld korrigiert

    # Backend das den Fehler gemacht hat
    backend_used = Column(String(50), nullable=False)

    # Kontext
    confidence_before = Column(Float, nullable=True)  # Konfidenz vor Korrektur

    # Self-Learning Status
    applies_to_training = Column(Boolean, default=False)  # Soll in Training einfliessen
    learning_processed = Column(Boolean, default=False)  # Wurde für Learning verarbeitet
    learning_processed_at = Column(DateTime(timezone=True), nullable=True)

    # Audit
    corrector_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    document = relationship("Document", backref="ocr_corrections")
    corrector = relationship("User")

    # Indexes
    __table_args__ = (
        Index("ix_ocr_validation_corrections_document", "document_id"),
        Index("ix_ocr_validation_corrections_backend", "backend_used"),
        Index("ix_ocr_validation_corrections_type", "correction_type"),
        Index("ix_ocr_validation_corrections_learning", "learning_processed"),
        Index("ix_ocr_validation_corrections_created", "created_at"),
    )


class BatchType(str, Enum):
    """Typ des Stichproben-Batches."""
    RANDOM = "random"               # Zufällige Auswahl
    STRATIFIED = "stratified"       # Stratifiziert nach Typ/Sprache
    TARGETED = "targeted"           # Gezielt nach Kriterien
    LOW_CONFIDENCE = "low_confidence"  # Niedrige Konfidenz-Dokumente


class BatchStatus(str, Enum):
    """Status des Stichproben-Batches."""
    DRAFT = "draft"           # In Erstellung
    READY = "ready"           # Bereit zum Starten
    IN_PROGRESS = "in_progress"  # Wird gerade bearbeitet
    ACTIVE = "active"         # Aktiv, wird bearbeitet
    COMPLETED = "completed"   # Alle Items validiert
    CANCELLED = "cancelled"   # Abgebrochen


class OCRTrainingBatch(Base):
    """
    Stichproben-Batch für systematische Validierung.

    Ermöglicht:
    - Stratifizierte Zufallsauswahl
    - Zuweisung an Bearbeiter
    - Fortschrittsverfolgung
    - Qualitaetskontrolle
    """
    __tablename__ = "ocr_training_batches"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Multi-Tenant
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=True,  # nullable for backfill of existing data
        index=True,
    )

    # Batch Identifikation
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    batch_type = Column(String(30), default=BatchType.STRATIFIED.value)

    # Backend-spezifische Validierung (für Pro-Backend Stichproben)
    target_backend = Column(String(50), nullable=True)

    # Stratifikations-Konfiguration
    stratification_config = Column(CrossDBJSON, default=dict)  # {by_type: true, by_language: true, type_weights: {...}}

    # Größe
    target_size = Column(Integer, default=100)  # Ziel-Anzahl
    actual_size = Column(Integer, default=0)    # Tatsaechliche Anzahl

    # Status
    status = Column(String(20), default=BatchStatus.DRAFT.value)

    # Fortschritt (wird automatisch berechnet)
    items_pending = Column(Integer, default=0)
    items_completed = Column(Integer, default=0)

    # Audit
    created_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    created_by = relationship("User", foreign_keys=[created_by_id])
    items = relationship("OCRTrainingBatchItem", back_populates="batch", cascade="all, delete-orphan")

    # Indexes
    __table_args__ = (
        Index("ix_ocr_training_batches_company_id", "company_id"),
        Index("ix_ocr_training_batches_company_status", "company_id", "status"),
        Index("ix_ocr_training_batches_status", "status"),
        Index("ix_ocr_training_batches_type", "batch_type"),
        Index("ix_ocr_training_batches_created", "created_at"),
    )

    @property
    def progress_percent(self) -> float:
        """Berechnet Fortschritt in Prozent."""
        if self.actual_size == 0:
            return 0.0
        return (self.items_completed / self.actual_size) * 100


class ItemStatus(str, Enum):
    """Status eines Batch-Items."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    SKIPPED = "skipped"


class OCRTrainingBatchItem(Base):
    """
    Einzelnes Item in einem Stichproben-Batch.

    Verknüpft Batch mit Training Sample und trackt
    den Validierungs-Fortschritt.
    """
    __tablename__ = "ocr_training_batch_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Multi-Tenant
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=True,  # nullable for backfill of existing data
        index=True,
    )

    # Referenzen
    batch_id = Column(
        UUID(as_uuid=True),
        ForeignKey("ocr_training_batches.id", ondelete="CASCADE"),
        nullable=False
    )
    training_sample_id = Column(
        UUID(as_uuid=True),
        ForeignKey("ocr_training_samples.id", ondelete="CASCADE"),
        nullable=False
    )

    # Reihenfolge im Batch
    sequence_number = Column(Integer, nullable=False)

    # Zuweisung
    assigned_to_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Status
    status = Column(String(20), default=ItemStatus.PENDING.value)

    # Validierungs-Ergebnis
    validation_notes = Column(Text, nullable=True)
    validation_time_seconds = Column(Integer, nullable=True)  # Wie lange hat Validierung gedauert

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    batch = relationship("OCRTrainingBatch", back_populates="items")
    training_sample = relationship("OCRTrainingSample")
    assigned_to = relationship("User")

    # Indexes
    __table_args__ = (
        Index("ix_ocr_training_batch_items_company_id", "company_id"),
        Index("ix_ocr_training_batch_items_company_status", "company_id", "status"),
        Index("ix_ocr_training_batch_items_batch", "batch_id"),
        Index("ix_ocr_training_batch_items_sample", "training_sample_id"),
        Index("ix_ocr_training_batch_items_status", "status"),
        Index("ix_ocr_training_batch_items_assigned", "assigned_to_id"),
        Index("ix_ocr_training_batch_items_sequence", "batch_id", "sequence_number"),
    )


class OCRBackendStatsDaily(Base):
    """
    Tägliche aggregierte Statistiken pro Backend.

    Wird automatisch von Celery Beat generiert.
    Ermöglicht Trend-Analyse und Performance-Vergleich.
    """
    __tablename__ = "ocr_backend_stats_daily"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Identifikation
    backend_name = Column(String(50), nullable=False)
    report_date = Column(DateTime(timezone=True), nullable=False)

    # Sample-Zaehler
    samples_processed = Column(Integer, default=0)
    samples_verified = Column(Integer, default=0)

    # Durchschnittsmetriken
    avg_cer = Column(Float, nullable=True)
    avg_wer = Column(Float, nullable=True)
    avg_umlaut_accuracy = Column(Float, nullable=True)
    avg_processing_time_ms = Column(Float, nullable=True)

    # Percentile für CER
    p50_cer = Column(Float, nullable=True)
    p90_cer = Column(Float, nullable=True)
    p95_cer = Column(Float, nullable=True)

    # Aufschluesselung nach Feld-Typ
    field_accuracy_stats = Column(CrossDBJSON, default=dict)
    # {invoice_number: {avg: 0.95, count: 50}, date: {avg: 0.88, count: 45}}

    # Aufschluesselung nach Dokument-Typ
    document_type_stats = Column(CrossDBJSON, default=dict)
    # {invoice: {cer: 0.02, count: 100}, freight: {cer: 0.05, count: 50}}

    # Aufschluesselung nach Sprache
    language_stats = Column(CrossDBJSON, default=dict)
    # {de: {cer: 0.02, count: 120}, nl: {cer: 0.04, count: 30}}

    # Self-Learning Metriken
    corrections_count = Column(Integer, default=0)
    correction_types = Column(CrossDBJSON, default=dict)
    # {umlaut: 15, date: 5, amount: 3}

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Indexes
    __table_args__ = (
        Index("ix_ocr_backend_stats_daily_backend", "backend_name"),
        Index("ix_ocr_backend_stats_daily_date", "report_date"),
        Index("ix_ocr_backend_stats_daily_backend_date", "backend_name", "report_date", unique=True),
    )


# ============================================================================
# BULK OCR PROCESSING MODELS
# Massenverarbeitung aller Trainings-Dokumente
# ============================================================================

class BulkJobStatus(str, Enum):
    """Status eines Bulk-Processing-Jobs."""
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class OCRBulkProcessingJob(Base):
    """
    Bulk OCR Processing Job.

    Trackt den Fortschritt der Massenverarbeitung aller
    Trainings-Dokumente durch alle OCR-Backends.
    """
    __tablename__ = "ocr_bulk_processing_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Job Identifikation
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Status
    status = Column(String(20), default=BulkJobStatus.PENDING.value, nullable=False)

    # Backend-Konfiguration
    backends = Column(CrossDBJSON, nullable=False)  # ["deepseek", "got-ocr", ...]

    # Fortschritt
    total_documents = Column(Integer, default=0)
    processed_documents = Column(Integer, default=0)
    failed_documents = Column(Integer, default=0)

    # Aktueller Stand
    current_backend = Column(String(50), nullable=True)
    current_backend_index = Column(Integer, default=0)
    current_document_index = Column(Integer, default=0)

    # Pro-Backend Statistiken
    documents_per_backend = Column(CrossDBJSON, default=dict)

    # Konfiguration
    configuration = Column(CrossDBJSON, default=dict)

    # Fehlerlog
    error_log = Column(CrossDBJSON, default=list)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    paused_at = Column(DateTime(timezone=True), nullable=True)
    last_checkpoint_at = Column(DateTime(timezone=True), nullable=True)

    # Audit
    created_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Relationships
    created_by = relationship("User", foreign_keys=[created_by_id])
    outputs = relationship("OCRDocumentOutput", back_populates="bulk_job")

    # Indexes
    __table_args__ = (
        Index("ix_ocr_bulk_processing_jobs_status", "status"),
        Index("ix_ocr_bulk_processing_jobs_created", "created_at"),
    )

    @property
    def progress_percent(self) -> float:
        """Berechnet Fortschritt in Prozent."""
        if self.total_documents == 0:
            return 0.0
        return (self.processed_documents / self.total_documents) * 100


class OCRDocumentOutput(Base):
    """
    OCR Output für ein Dokument durch ein spezifisches Backend.

    Speichert den OCR-Output aller Backends für spätere
    Vergleiche und Ground-Truth-Erstellung.
    """
    __tablename__ = "ocr_document_outputs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Referenzen
    training_sample_id = Column(
        UUID(as_uuid=True),
        ForeignKey("ocr_training_samples.id", ondelete="CASCADE"),
        nullable=False
    )
    bulk_job_id = Column(
        UUID(as_uuid=True),
        ForeignKey("ocr_bulk_processing_jobs.id", ondelete="SET NULL"),
        nullable=True
    )

    # Backend Identifikation
    backend_name = Column(String(50), nullable=False)
    backend_version = Column(String(50), nullable=True)

    # OCR Output
    raw_text = Column(Text, nullable=True)
    structured_output = Column(CrossDBJSON, nullable=True)

    # Qualitaetsmetriken
    confidence_score = Column(Float, nullable=True)
    processing_time_ms = Column(Integer, nullable=True)
    gpu_memory_mb = Column(Integer, nullable=True)

    # Fehler
    error_message = Column(Text, nullable=True)
    success = Column(Boolean, default=True)

    # Timestamps
    processed_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    training_sample = relationship("OCRTrainingSample")
    bulk_job = relationship("OCRBulkProcessingJob", back_populates="outputs")

    # Indexes
    __table_args__ = (
        Index("ix_ocr_document_outputs_sample", "training_sample_id"),
        Index("ix_ocr_document_outputs_backend", "backend_name"),
        Index("ix_ocr_document_outputs_job", "bulk_job_id"),
        Index("ix_ocr_document_outputs_sample_backend", "training_sample_id", "backend_name", unique=True),
    )


class OCRQualitySnapshot(Base):
    """
    Stuendliche Qualitaets-Snapshots pro Backend.

    Ermöglicht Trend-Analyse und Quality-Degradation-Erkennung
    für das Continuous-Learning-System.
    """
    __tablename__ = "ocr_quality_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Identifikation
    backend_name = Column(String(50), nullable=False)
    snapshot_time = Column(DateTime(timezone=True), server_default=func.now())

    # Sample Counts
    sample_count = Column(Integer, default=0)

    # Qualitaetsmetriken
    avg_cer = Column(Float, nullable=True)
    avg_wer = Column(Float, nullable=True)
    avg_umlaut_accuracy = Column(Float, nullable=True)
    avg_processing_time_ms = Column(Float, nullable=True)

    # Percentiles
    p50_cer = Column(Float, nullable=True)
    p90_cer = Column(Float, nullable=True)
    p99_cer = Column(Float, nullable=True)

    # Korrekturen
    correction_count = Column(Integer, default=0)
    correction_types = Column(CrossDBJSON, default=dict)

    # Alert Status
    alert_triggered = Column(Boolean, default=False)
    alert_reason = Column(String(255), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Indexes
    __table_args__ = (
        Index("ix_ocr_quality_snapshots_backend", "backend_name"),
        Index("ix_ocr_quality_snapshots_time", "snapshot_time"),
        Index("ix_ocr_quality_snapshots_backend_time", "backend_name", "snapshot_time"),
    )


class ModelType(str, Enum):
    """Typ des Modells."""
    BASE = "base"
    FINETUNED = "finetuned"
    LORA = "lora"


class OCRModelDeployment(Base):
    """
    Modell-Deployment-Tracking für A/B Testing.

    Ermöglicht Versionskontrolle und Rollback
    für fine-getunte Modelle.
    """
    __tablename__ = "ocr_model_deployments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Multi-Tenant
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=True,  # nullable for backfill of existing data
        index=True,
    )

    # Model Identifikation
    model_name = Column(String(100), nullable=False)
    version = Column(String(50), nullable=False)
    model_type = Column(String(50), default=ModelType.BASE.value)

    # Deployment Info
    is_active = Column(Boolean, default=False)
    is_default = Column(Boolean, default=False)
    traffic_percentage = Column(Float, default=0.0)  # Für A/B Testing

    # Performance Metrics
    performance_metrics = Column(CrossDBJSON, default=dict)

    # Checkpoint Info
    checkpoint_path = Column(String(500), nullable=True)
    training_job_id = Column(UUID(as_uuid=True), nullable=True)

    # Rollback Info
    previous_version = Column(String(50), nullable=True)
    rollback_reason = Column(Text, nullable=True)

    # Timestamps
    deployed_at = Column(DateTime(timezone=True), nullable=True)
    deactivated_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Audit
    deployed_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Relationships
    deployed_by = relationship("User")

    # Indexes
    __table_args__ = (
        Index("ix_ocr_model_deployments_company_id", "company_id"),
        Index("ix_ocr_model_deployments_model", "model_name"),
        Index("ix_ocr_model_deployments_active", "is_active"),
        Index("ix_ocr_model_deployments_model_version", "model_name", "version", unique=True),
    )


# =============================================================================
# VALIDATION QUEUE SYSTEM
# Enterprise-Grade Validierungssystem für OCR-Ergebnisse und extrahierte Daten
# =============================================================================

class ValidationStatus(str, Enum):
    """Validierungs-Status."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    APPROVED = "approved"
    REJECTED = "rejected"
    SKIPPED = "skipped"


class SampleSource(str, Enum):
    """Quelle der Stichproben-Auswahl."""
    AUTOMATIC = "automatic"
    RULE_BASED = "rule_based"
    MANUAL = "manual"
    LOW_CONFIDENCE = "low_confidence"


class ValidationRuleType(str, Enum):
    """Typ der Validierungsregel."""
    CONFIDENCE_THRESHOLD = "confidence_threshold"
    FIELD_PATTERN = "field_pattern"
    DOCUMENT_TYPE = "document_type"
    FIRST_OCCURRENCE = "first_occurrence"
    ERROR_PATTERN = "error_pattern"


class ValidationSampleConfig(Base):
    """Konfiguration für prozent-basierte Stichproben."""
    __tablename__ = "validation_sample_configs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Konfiguration
    name = Column(String(100), nullable=False, default="Standard")
    description = Column(Text, nullable=True)
    sample_percentage = Column(Integer, nullable=False, default=10)
    stratify_by_document_type = Column(Boolean, default=True)
    stratify_by_ocr_backend = Column(Boolean, default=False)
    min_confidence_threshold = Column(Float, default=0.85)

    # Zeitraum
    is_active = Column(Boolean, default=True)
    valid_from = Column(DateTime(timezone=True), nullable=True)
    valid_until = Column(DateTime(timezone=True), nullable=True)

    # Statistik
    documents_sampled = Column(Integer, default=0)
    last_sample_at = Column(DateTime(timezone=True), nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    created_by = relationship("User", foreign_keys=[created_by_id])


class ValidationRule(Base):
    """Regelbasierte Stichproben-Definition."""
    __tablename__ = "validation_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Regel-Identifikation
    name = Column(String(100), nullable=False, unique=True)
    description = Column(Text, nullable=True)

    # Regel-Definition
    rule_type = Column(String(50), nullable=False)
    conditions = Column(CrossDBJSON, nullable=False, default=dict)

    # Priorität und Status
    priority = Column(Integer, nullable=False, default=5)
    is_active = Column(Boolean, default=True)
    is_system = Column(Boolean, default=False)

    # Statistik
    documents_matched = Column(Integer, default=0)
    last_triggered_at = Column(DateTime(timezone=True), nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    created_by = relationship("User", foreign_keys=[created_by_id])
    queue_items = relationship("ValidationQueueItem", back_populates="sample_rule")

    __table_args__ = (
        Index("ix_validation_rules_active", "is_active"),
        Index("ix_validation_rules_type", "rule_type"),
        Index("ix_validation_rules_priority", "priority"),
    )


class ValidationQueueItem(Base):
    """Warteschlangen-Eintrag für Validierung."""
    __tablename__ = "validation_queue_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Dokument-Referenz
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)

    # Status und Zuweisung
    status = Column(String(50), nullable=False, default=ValidationStatus.PENDING.value)
    priority = Column(Integer, nullable=False, default=5)
    assigned_to_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    assigned_at = Column(DateTime(timezone=True), nullable=True)

    # Stichproben-Quelle
    sample_source = Column(String(50), nullable=False, default=SampleSource.AUTOMATIC.value)
    sample_rule_id = Column(UUID(as_uuid=True), ForeignKey("validation_rules.id", ondelete="SET NULL"), nullable=True)

    # Confidence Metriken
    overall_confidence = Column(Float, nullable=True)
    min_field_confidence = Column(Float, nullable=True)
    fields_below_threshold = Column(Integer, default=0)
    total_fields = Column(Integer, default=0)

    # Dokumenttyp (kopiert für Filterung ohne Join)
    document_type = Column(String(50), nullable=True)
    document_name = Column(String(255), nullable=True)

    # Validierungsergebnis
    validation_notes = Column(Text, nullable=True)
    rejection_reason = Column(Text, nullable=True)
    rejection_category = Column(String(50), nullable=True)
    validated_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    validated_at = Column(DateTime(timezone=True), nullable=True)

    # Zeit-Tracking
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    validation_duration_seconds = Column(Integer, nullable=True)

    # Korrekturen-Zaehler
    corrections_made = Column(Integer, default=0)
    umlaut_corrections = Column(Integer, default=0)
    format_corrections = Column(Integer, default=0)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    document = relationship("Document", backref="validation_queue_items")
    assigned_to = relationship("User", foreign_keys=[assigned_to_id], backref="assigned_validations")
    validated_by = relationship("User", foreign_keys=[validated_by_id], backref="completed_validations")
    created_by = relationship("User", foreign_keys=[created_by_id])
    sample_rule = relationship("ValidationRule", back_populates="queue_items")
    field_reviews = relationship("ValidationFieldReview", back_populates="queue_item", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_vqi_status", "status"),
        Index("ix_vqi_priority", "priority"),
        Index("ix_vqi_assigned_to", "assigned_to_id"),
        Index("ix_vqi_document", "document_id"),
        Index("ix_vqi_confidence", "overall_confidence"),
        Index("ix_vqi_sample_source", "sample_source"),
        Index("ix_vqi_created_at", "created_at"),
        Index("ix_vqi_document_type", "document_type"),
        Index("ix_vqi_status_priority", "status", "priority", "created_at"),
        Index("ix_vqi_assigned_status", "assigned_to_id", "status"),
        Index("ix_vqi_validated_date", "validated_at", "validated_by_id"),
    )

    @property
    def is_pending(self) -> bool:
        """Prüft ob Item noch ausstehend ist."""
        return self.status == ValidationStatus.PENDING.value

    @property
    def is_completed(self) -> bool:
        """Prüft ob Item abgeschlossen ist."""
        return self.status in [ValidationStatus.APPROVED.value, ValidationStatus.REJECTED.value]


class ValidationFieldReview(Base):
    """Feld-Review für ein Validierungs-Item."""
    __tablename__ = "validation_field_reviews"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Queue-Item Referenz
    queue_item_id = Column(UUID(as_uuid=True), ForeignKey("validation_queue_items.id", ondelete="CASCADE"), nullable=False)

    # Feld-Identifikation
    field_key = Column(String(100), nullable=False)
    field_label = Column(String(255), nullable=False)
    field_type = Column(String(50), nullable=True)

    # Werte
    original_value = Column(Text, nullable=True)
    corrected_value = Column(Text, nullable=True)
    was_corrected = Column(Boolean, default=False)

    # Confidence
    confidence_score = Column(Float, nullable=True)
    confidence_threshold = Column(Float, default=0.85)
    is_below_threshold = Column(Boolean, default=False)

    # Validierung
    validation_status = Column(String(50), default="pending")
    validation_errors = Column(CrossDBJSON, default=list)
    umlaut_issues = Column(CrossDBJSON, default=list)
    format_issues = Column(CrossDBJSON, default=list)

    # OCR-Metadaten für PDF-Highlighting
    bounding_box = Column(CrossDBJSON, nullable=True)
    ocr_backend = Column(String(50), nullable=True)

    # Audit
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    reviewed_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    queue_item = relationship("ValidationQueueItem", back_populates="field_reviews")
    reviewed_by = relationship("User", foreign_keys=[reviewed_by_id])

    __table_args__ = (
        Index("ix_vfr_queue_item", "queue_item_id"),
        Index("ix_vfr_field_key", "field_key"),
        Index("ix_vfr_below_threshold", "is_below_threshold"),
        Index("ix_vfr_was_corrected", "was_corrected"),
    )

    @property
    def needs_review(self) -> bool:
        """Prüft ob Feld Review benötigt."""
        return self.is_below_threshold or len(self.validation_errors) > 0


class ValidationAnalytics(Base):
    """Aggregierte Statistiken für Validierungen."""
    __tablename__ = "validation_analytics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Zeitraum
    date = Column(Date, nullable=False)
    hour = Column(Integer, nullable=True)

    # Editor (NULL = Gesamtstatistik)
    editor_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)

    # Dokumenttyp (NULL = Alle Typen)
    document_type = Column(String(50), nullable=True)

    # Metriken: Anzahl
    items_validated = Column(Integer, default=0)
    items_approved = Column(Integer, default=0)
    items_rejected = Column(Integer, default=0)
    items_skipped = Column(Integer, default=0)

    # Metriken: Zeit
    avg_validation_time_seconds = Column(Integer, nullable=True)
    min_validation_time_seconds = Column(Integer, nullable=True)
    max_validation_time_seconds = Column(Integer, nullable=True)
    total_validation_time_seconds = Column(Integer, default=0)

    # Metriken: Korrekturen
    corrections_made = Column(Integer, default=0)
    umlaut_corrections = Column(Integer, default=0)
    format_corrections = Column(Integer, default=0)
    fields_reviewed = Column(Integer, default=0)

    # Metriken: Confidence
    avg_confidence_before = Column(Float, nullable=True)
    avg_confidence_after = Column(Float, nullable=True)
    confidence_improvement = Column(Float, nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    editor = relationship("User", foreign_keys=[editor_id])

    __table_args__ = (
        Index("ix_va_date", "date"),
        Index("ix_va_editor", "editor_id"),
        Index("ix_va_document_type", "document_type"),
        Index("ix_va_date_editor", "date", "editor_id"),
    )

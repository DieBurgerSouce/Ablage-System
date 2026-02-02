# -*- coding: utf-8 -*-
"""
Workflow Versioning und Saga Pattern Models fuer Ablage-System.

Implementiert:
- WorkflowVersion: Semantische Versionierung von Workflows
- WorkflowABTest: A/B Testing zwischen Workflow-Versionen
- Saga: Saga-Orchestrierung fuer verteilte Transaktionen
- SagaStep: Einzelne Schritte mit Compensation

GoBD-konform: Vollstaendige Nachvollziehbarkeit aller Aenderungen.
"""

from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
import uuid

from sqlalchemy import (
    Column,
    String,
    Integer,
    Boolean,
    Text,
    DateTime,
    Float,
    ForeignKey,
    Index,
    UniqueConstraint,
    CheckConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.models import Base, CrossDBJSON


# ============================================================================
# Enums
# ============================================================================


class WorkflowVersionStatus(str, Enum):
    """Status einer Workflow-Version."""
    DRAFT = "draft"           # In Entwicklung
    ACTIVE = "active"         # Aktiv und verwendbar
    DEPRECATED = "deprecated" # Veraltet, nicht fuer neue Executions
    ARCHIVED = "archived"     # Archiviert, nur Lesezugriff


class ABTestStatus(str, Enum):
    """Status eines A/B Tests."""
    DRAFT = "draft"           # Noch nicht gestartet
    RUNNING = "running"       # Laeuft
    PAUSED = "paused"         # Pausiert
    COMPLETED = "completed"   # Beendet (manuell oder Zeit)
    CANCELLED = "cancelled"   # Abgebrochen


class SagaStatus(str, Enum):
    """Status einer Saga-Ausfuehrung."""
    PENDING = "pending"               # Noch nicht gestartet
    RUNNING = "running"               # Laeuft (Forward)
    COMPENSATING = "compensating"     # Rollback aktiv
    COMPLETED = "completed"           # Erfolgreich abgeschlossen
    FAILED = "failed"                 # Fehlgeschlagen (kein Rollback moeglich)
    COMPENSATED = "compensated"       # Erfolgreich zurueckgerollt
    PARTIALLY_COMPENSATED = "partially_compensated"  # Teilweise Rollback


class SagaStepStatus(str, Enum):
    """Status eines Saga-Schritts."""
    PENDING = "pending"               # Noch nicht ausgefuehrt
    RUNNING = "running"               # Wird ausgefuehrt
    COMPLETED = "completed"           # Erfolgreich
    FAILED = "failed"                 # Fehlgeschlagen
    SKIPPED = "skipped"               # Uebersprungen
    COMPENSATING = "compensating"     # Compensation laeuft
    COMPENSATED = "compensated"       # Erfolgreich kompensiert
    COMPENSATION_FAILED = "compensation_failed"  # Compensation fehlgeschlagen


# ============================================================================
# Workflow Version Model
# ============================================================================


class WorkflowVersion(Base):
    """Workflow-Version mit semantischer Versionierung.

    Ermoeglicht:
    - Vollstaendige Versionshistorie
    - Diff-Ansicht zwischen Versionen
    - Rollback auf jede vorherige Version
    - A/B Testing zwischen Versionen
    - Migration laufender Instanzen

    Semantische Versionierung:
    - major.minor.patch (z.B. 1.2.3)
    - Major: Breaking Changes (Trigger/Steps geaendert)
    - Minor: Neue Features (Steps hinzugefuegt)
    - Patch: Bugfixes (Config-Aenderungen)
    """
    __tablename__ = "workflow_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Workflow Reference
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflows.id", ondelete="CASCADE"),
        nullable=False
    )

    # Multi-Tenant
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False
    )

    # Version Info
    version: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # "1.0.0", "1.1.0", "2.0.0"

    major: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    minor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    patch: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Status
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=WorkflowVersionStatus.DRAFT.value
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_latest: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Vollstaendige Workflow-Definition (Snapshot)
    definition: Mapped[Dict[str, Any]] = mapped_column(
        CrossDBJSON, nullable=False
    )  # nodes, edges, trigger_config, variables

    # Aenderungsinformationen
    change_description: Mapped[str] = mapped_column(Text, nullable=False)
    change_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="minor"
    )  # major, minor, patch

    # Diff zur vorherigen Version
    parent_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_versions.id", ondelete="SET NULL"),
        nullable=True
    )
    diff_summary: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        CrossDBJSON, nullable=True
    )  # {added: [], removed: [], modified: []}

    # Statistiken
    execution_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_execution_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # A/B Test Weight
    ab_test_weight: Mapped[int] = mapped_column(
        Integer, nullable=False, default=100
    )  # 0-100 Prozent Traffic

    # Ersteller
    created_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Audit
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    published_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deprecated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    archived_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    workflow = relationship("Workflow", backref="versions")
    company = relationship("Company")
    created_by = relationship("User")
    parent_version = relationship("WorkflowVersion", remote_side=[id])

    __table_args__ = (
        UniqueConstraint("workflow_id", "version", name="uq_workflow_version"),
        Index("ix_workflow_versions_workflow_id", "workflow_id"),
        Index("ix_workflow_versions_company_id", "company_id"),
        Index("ix_workflow_versions_status", "status"),
        Index("ix_workflow_versions_is_active", "workflow_id", "is_active"),
        Index("ix_workflow_versions_semver", "workflow_id", "major", "minor", "patch"),
        CheckConstraint("major >= 0", name="ck_major_positive"),
        CheckConstraint("minor >= 0", name="ck_minor_positive"),
        CheckConstraint("patch >= 0", name="ck_patch_positive"),
        CheckConstraint("ab_test_weight >= 0 AND ab_test_weight <= 100", name="ck_ab_weight_range"),
    )

    def __repr__(self) -> str:
        return f"<WorkflowVersion workflow={self.workflow_id} v{self.version}>"

    @property
    def semver(self) -> str:
        """Gibt die semantische Version zurueck."""
        return f"{self.major}.{self.minor}.{self.patch}"

    @property
    def is_publishable(self) -> bool:
        """Prueft ob die Version veroeffentlicht werden kann."""
        return self.status == WorkflowVersionStatus.DRAFT.value

    @property
    def success_rate(self) -> float:
        """Berechnet die Erfolgsrate in Prozent."""
        if self.execution_count == 0:
            return 0.0
        return (self.success_count / self.execution_count) * 100


# ============================================================================
# Workflow A/B Test Model
# ============================================================================


class WorkflowABTest(Base):
    """A/B Test zwischen zwei Workflow-Versionen.

    Ermoeglicht:
    - 50/50 oder gewichteten Traffic-Split
    - Statistische Analyse der Ergebnisse
    - Automatisches Beenden bei Signifikanz
    """
    __tablename__ = "workflow_ab_tests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Workflow Reference
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflows.id", ondelete="CASCADE"),
        nullable=False
    )

    # Multi-Tenant
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False
    )

    # Test Name & Description
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Varianten
    control_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_versions.id", ondelete="CASCADE"),
        nullable=False
    )
    treatment_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_versions.id", ondelete="CASCADE"),
        nullable=False
    )

    # Traffic Split (0-100, Rest geht an Control)
    treatment_percentage: Mapped[int] = mapped_column(
        Integer, nullable=False, default=50
    )

    # Status
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ABTestStatus.DRAFT.value
    )

    # Zeitraum
    start_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    end_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Statistiken - Control
    control_executions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    control_successes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    control_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    control_avg_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Statistiken - Treatment
    treatment_executions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    treatment_successes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    treatment_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    treatment_avg_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Ergebnis
    winner: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True
    )  # control, treatment, inconclusive
    statistical_significance: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )  # p-value
    confidence_level: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )  # 0.95 for 95%

    # Ersteller
    created_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Audit
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    workflow = relationship("Workflow", backref="ab_tests")
    company = relationship("Company")
    control_version = relationship(
        "WorkflowVersion",
        foreign_keys=[control_version_id],
        backref="ab_tests_as_control"
    )
    treatment_version = relationship(
        "WorkflowVersion",
        foreign_keys=[treatment_version_id],
        backref="ab_tests_as_treatment"
    )
    created_by = relationship("User")

    __table_args__ = (
        Index("ix_workflow_ab_tests_workflow_id", "workflow_id"),
        Index("ix_workflow_ab_tests_company_id", "company_id"),
        Index("ix_workflow_ab_tests_status", "status"),
        Index("ix_workflow_ab_tests_dates", "start_at", "end_at"),
        CheckConstraint(
            "treatment_percentage >= 0 AND treatment_percentage <= 100",
            name="ck_treatment_percentage_range"
        ),
    )

    def __repr__(self) -> str:
        return f"<WorkflowABTest {self.name} status={self.status}>"

    @property
    def control_success_rate(self) -> float:
        """Erfolgsrate der Control-Variante."""
        if self.control_executions == 0:
            return 0.0
        return (self.control_successes / self.control_executions) * 100

    @property
    def treatment_success_rate(self) -> float:
        """Erfolgsrate der Treatment-Variante."""
        if self.treatment_executions == 0:
            return 0.0
        return (self.treatment_successes / self.treatment_executions) * 100


# ============================================================================
# Saga Model
# ============================================================================


class Saga(Base):
    """Saga fuer verteilte Transaktionen mit Compensation.

    Implementiert das Saga-Pattern fuer:
    - Atomare Multi-Step-Operationen
    - Automatische Compensation bei Fehler
    - Vollstaendige Transaktions-Nachvollziehbarkeit
    - Dead Letter Queue fuer fehlgeschlagene Compensations

    Saga-Zustandsmaschine:
    PENDING -> RUNNING -> COMPLETED
                      -> COMPENSATING -> COMPENSATED
                                     -> PARTIALLY_COMPENSATED
                                     -> FAILED
    """
    __tablename__ = "sagas"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Workflow Execution Reference
    execution_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_executions.id", ondelete="SET NULL"),
        nullable=True
    )

    # Multi-Tenant
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False
    )

    # Saga Name
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Status
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default=SagaStatus.PENDING.value
    )

    # Fortschritt
    current_step_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_steps: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Checkpoint (fuer Resume)
    checkpoint_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        CrossDBJSON, nullable=True
    )

    # Fehlerzaehler
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=3)

    # Fehlerinformationen
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_step_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    # Compensation-Tracking
    compensation_started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    compensation_completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    steps_compensated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Dead Letter Queue
    in_dead_letter_queue: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    dead_letter_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    dead_letter_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Initiator
    initiated_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Audit
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Kontext-Daten (fuer Steps verfuegbar)
    context_data: Mapped[Dict[str, Any]] = mapped_column(
        CrossDBJSON, nullable=False, default=dict
    )

    # Relationships
    execution = relationship("WorkflowExecution", backref="sagas")
    company = relationship("Company")
    initiated_by = relationship("User")
    steps = relationship(
        "SagaStep",
        back_populates="saga",
        cascade="all, delete-orphan",
        order_by="SagaStep.step_order"
    )

    __table_args__ = (
        Index("ix_sagas_execution_id", "execution_id"),
        Index("ix_sagas_company_id", "company_id"),
        Index("ix_sagas_status", "status"),
        Index("ix_sagas_dead_letter", "in_dead_letter_queue"),
        Index("ix_sagas_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<Saga {self.id} name={self.name} status={self.status}>"

    @property
    def is_running(self) -> bool:
        """Prueft ob die Saga noch laeuft."""
        return self.status in (
            SagaStatus.RUNNING.value,
            SagaStatus.COMPENSATING.value
        )

    @property
    def is_completed(self) -> bool:
        """Prueft ob die Saga erfolgreich abgeschlossen ist."""
        return self.status == SagaStatus.COMPLETED.value

    @property
    def needs_compensation(self) -> bool:
        """Prueft ob Compensation erforderlich ist."""
        return self.status == SagaStatus.FAILED.value

    @property
    def progress_percent(self) -> int:
        """Berechnet den Fortschritt in Prozent."""
        if self.total_steps == 0:
            return 0
        return int((self.current_step_index / self.total_steps) * 100)


# ============================================================================
# Saga Step Model
# ============================================================================


class SagaStep(Base):
    """Einzelner Schritt einer Saga mit Compensation-Action.

    Jeder Step hat:
    - Forward Action: Die eigentliche Aktion
    - Compensation Action: Die Umkehraktion bei Fehler
    - Idempotenz-Key: Fuer sichere Wiederholung
    """
    __tablename__ = "saga_steps"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Saga Reference
    saga_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sagas.id", ondelete="CASCADE"),
        nullable=False
    )

    # Step Order
    step_order: Mapped[int] = mapped_column(Integer, nullable=False)

    # Step Name
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Forward Action
    action_type: Mapped[str] = mapped_column(String(50), nullable=False)
    action_params: Mapped[Dict[str, Any]] = mapped_column(
        CrossDBJSON, nullable=False, default=dict
    )

    # Compensation Action (Optional)
    compensation_type: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )
    compensation_params: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        CrossDBJSON, nullable=True
    )
    has_compensation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Status
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default=SagaStepStatus.PENDING.value
    )

    # Retry-Konfiguration
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    retry_delay_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=60)

    # Idempotenz (fuer sichere Wiederholung)
    idempotency_key: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, unique=True
    )

    # Ausfuehrungszeitpunkte
    executed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Compensation-Zeitpunkte
    compensation_started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    compensated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Ergebnis & Fehler
    result_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        CrossDBJSON, nullable=True
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_details: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        CrossDBJSON, nullable=True
    )

    # Compensation-Fehler
    compensation_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    compensation_retry_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )

    # Timeout
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=300)

    # Audit
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    saga = relationship("Saga", back_populates="steps")

    __table_args__ = (
        UniqueConstraint("saga_id", "step_order", name="uq_saga_step_order"),
        Index("ix_saga_steps_saga_id", "saga_id"),
        Index("ix_saga_steps_status", "status"),
        Index("ix_saga_steps_idempotency", "idempotency_key"),
    )

    def __repr__(self) -> str:
        return f"<SagaStep {self.name} order={self.step_order} status={self.status}>"

    @property
    def is_completed(self) -> bool:
        """Prueft ob der Schritt abgeschlossen ist."""
        return self.status == SagaStepStatus.COMPLETED.value

    @property
    def is_compensated(self) -> bool:
        """Prueft ob der Schritt kompensiert wurde."""
        return self.status == SagaStepStatus.COMPENSATED.value

    @property
    def can_retry(self) -> bool:
        """Prueft ob der Schritt wiederholt werden kann."""
        return self.retry_count < self.max_retries

    @property
    def duration_ms(self) -> Optional[int]:
        """Berechnet die Ausfuehrungsdauer in Millisekunden."""
        if not self.executed_at or not self.completed_at:
            return None
        delta = self.completed_at - self.executed_at
        return int(delta.total_seconds() * 1000)


# ============================================================================
# Saga Transaction Log Model (fuer Debugging & Audit)
# ============================================================================


class SagaTransactionLog(Base):
    """Transaktionslog fuer Saga-Ausfuehrungen.

    Protokolliert alle State-Transitions fuer:
    - Debugging
    - Audit-Trail
    - Forensische Analyse
    """
    __tablename__ = "saga_transaction_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Saga Reference
    saga_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sagas.id", ondelete="CASCADE"),
        nullable=False
    )

    # Step Reference (Optional)
    step_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("saga_steps.id", ondelete="SET NULL"),
        nullable=True
    )

    # Event Info
    event_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # saga_started, step_executed, step_failed, compensation_started, etc.

    # State Transition
    previous_state: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    new_state: Mapped[str] = mapped_column(String(30), nullable=False)

    # Event Details
    event_data: Mapped[Dict[str, Any]] = mapped_column(
        CrossDBJSON, nullable=False, default=dict
    )

    # Error Info
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    stack_trace: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Audit
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    saga = relationship("Saga", backref="transaction_logs")
    step = relationship("SagaStep", backref="transaction_logs")

    __table_args__ = (
        Index("ix_saga_tx_logs_saga_id", "saga_id"),
        Index("ix_saga_tx_logs_step_id", "step_id"),
        Index("ix_saga_tx_logs_event_type", "event_type"),
        Index("ix_saga_tx_logs_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<SagaTransactionLog {self.event_type} saga={self.saga_id}>"

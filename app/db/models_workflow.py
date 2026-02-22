"""Workflow Modelle - extrahiert aus models.py (Modularisierung Phase 1.1)."""
import uuid
from datetime import datetime
from enum import Enum
from sqlalchemy import Column, String, Integer, Boolean, DateTime, Text, Float, ForeignKey, Index, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.db.models_base import Base, CrossDBJSON


class Workflow(Base):
    """Workflow-Definitionen für Automatisierung.

    Ermöglicht das Erstellen von Multi-Step-Workflows mit:
    - Trigger (Document Events, Schedule, Condition, Manual, Webhook)
    - Conditions (AND/OR-Logik, wiederverwendet ImportRule Pattern)
    - Actions (20+ Aktionstypen)
    - Branching, Delays, Parallel Execution
    """
    __tablename__ = "workflows"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=True, index=True)

    # Basis-Informationen
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False, index=True)

    # Template-Funktion
    is_template = Column(Boolean, default=False, nullable=False, index=True)
    template_category = Column(String(50), nullable=True, index=True)
    # Categories: document, finance, notification, reporting, approval

    # Trigger-Konfiguration
    trigger_type = Column(String(30), nullable=False, index=True)
    # Types: document_event, schedule, condition, manual, webhook
    trigger_config = Column(CrossDBJSON, nullable=False, default=dict)

    # ReactFlow Graph Definition
    nodes = Column(CrossDBJSON, nullable=False, default=list)
    edges = Column(CrossDBJSON, nullable=False, default=list)
    variables = Column(CrossDBJSON, nullable=True)

    # Webhook-Trigger
    webhook_secret = Column(String(64), nullable=True)
    webhook_path = Column(String(100), nullable=True, unique=True)

    # Ausführungs-Einstellungen
    max_concurrent_executions = Column(Integer, default=10, nullable=False)
    timeout_seconds = Column(Integer, default=3600, nullable=False)
    retry_config = Column(CrossDBJSON, nullable=True)
    error_handling = Column(String(20), default="stop", nullable=False)
    enable_audit_log = Column(Boolean, default=True, nullable=False)

    # Statistiken
    execution_count = Column(Integer, default=0, nullable=False)
    success_count = Column(Integer, default=0, nullable=False)
    failure_count = Column(Integer, default=0, nullable=False)
    last_executed_at = Column(DateTime(timezone=True), nullable=True)
    avg_execution_time_ms = Column(Integer, nullable=True)

    # Nächste geplante Ausführung
    next_run_at = Column(DateTime(timezone=True), nullable=True, index=True)

    # Audit
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    user = relationship("User", foreign_keys=[user_id], backref="workflows")
    company = relationship("Company", backref="workflows")
    created_by = relationship("User", foreign_keys=[created_by_id])
    steps = relationship("WorkflowStep", back_populates="workflow", cascade="all, delete-orphan", order_by="WorkflowStep.step_order")
    executions = relationship("WorkflowExecution", back_populates="workflow", cascade="all, delete-orphan")

    __table_args__ = (
        {"comment": "Workflow-Definitionen für Automatisierung"}
    )


class WorkflowStep(Base):
    """Einzelne Schritte pro Workflow.

    Schritt-Typen:
    - condition: Bedingungsprüfung mit AND/OR-Logik
    - action: Aktion ausführen (move_folder, send_notification, etc.)
    - branch: If-Then-Else Verzweigung
    - delay: Zeitverzögerung
    - parallel: Parallele Ausführung
    - loop: Schleife (optional)
    """
    __tablename__ = "workflow_steps"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_id = Column(UUID(as_uuid=True), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False, index=True)

    # Basis-Informationen
    step_order = Column(Integer, nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Step-Typ
    step_type = Column(String(30), nullable=False, index=True)
    # Types: condition, action, branch, delay, parallel, loop

    # Step-Konfiguration (JSONB)
    config = Column(CrossDBJSON, nullable=False, default=dict)

    # Retry/Error Handling
    retry_on_failure = Column(Boolean, default=True, nullable=False)
    max_retries = Column(Integer, default=3, nullable=False)
    retry_backoff_seconds = Column(Integer, default=60, nullable=False)
    continue_on_error = Column(Boolean, default=False, nullable=False)
    fallback_step_id = Column(UUID(as_uuid=True), ForeignKey("workflow_steps.id", ondelete="SET NULL"), nullable=True)

    # ReactFlow Position
    position_x = Column(Float, nullable=True)
    position_y = Column(Float, nullable=True)
    node_data = Column(CrossDBJSON, nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    workflow = relationship("Workflow", back_populates="steps")
    fallback_step = relationship("WorkflowStep", remote_side=[id])
    step_executions = relationship("WorkflowStepExecution", back_populates="workflow_step", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_workflow_steps_order", "workflow_id", "step_order"),
        {"comment": "Einzelne Schritte pro Workflow"}
    )


class WorkflowExecution(Base):
    """Ausführungs-Historie für Workflows.

    Trackt jeden Workflow-Lauf mit:
    - Trigger-Kontext
    - Status und Fortschritt
    - Ergebnis und Fehler
    - Timing-Informationen
    """
    __tablename__ = "workflow_executions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_id = Column(UUID(as_uuid=True), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False, index=True)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=True, index=True)

    # Wer hat ausgeloest
    triggered_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Trigger-Kontext
    trigger_type = Column(String(30), nullable=False, index=True)
    trigger_source = Column(String(255), nullable=True)
    trigger_data = Column(CrossDBJSON, nullable=True)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True, index=True)

    # Ausführungs-Status
    status = Column(String(20), nullable=False, default="pending", index=True)
    # Status: pending, running, completed, failed, cancelled, paused
    current_step_id = Column(UUID(as_uuid=True), ForeignKey("workflow_steps.id", ondelete="SET NULL"), nullable=True)
    progress_percent = Column(Integer, default=0, nullable=False)

    # Ergebnisse
    result = Column(CrossDBJSON, nullable=True)
    error_message = Column(Text, nullable=True)
    error_code = Column(String(50), nullable=True)
    error_step_id = Column(UUID(as_uuid=True), ForeignKey("workflow_steps.id", ondelete="SET NULL"), nullable=True)

    # Timing
    started_at = Column(DateTime(timezone=True), nullable=True, index=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    duration_ms = Column(Integer, nullable=True)

    # Celery-Integration
    celery_task_id = Column(String(100), nullable=True)
    retry_count = Column(Integer, default=0, nullable=False)

    # Runtime-Variablen
    variables = Column(CrossDBJSON, nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    workflow = relationship("Workflow", back_populates="executions")
    company = relationship("Company", backref="workflow_executions")
    triggered_by = relationship("User", foreign_keys=[triggered_by_id])
    document = relationship("Document", backref="workflow_executions")
    current_step = relationship("WorkflowStep", foreign_keys=[current_step_id])
    error_step = relationship("WorkflowStep", foreign_keys=[error_step_id])
    step_executions = relationship("WorkflowStepExecution", back_populates="workflow_execution", cascade="all, delete-orphan", order_by="WorkflowStepExecution.execution_order")

    __table_args__ = (
        {"comment": "Ausführungs-Historie für Workflows"}
    )


class WorkflowStepExecution(Base):
    """Schritt-Level Audit Trail für Workflow-Ausführungen.

    Trackt jeden einzelnen Schritt mit:
    - Input/Output-Daten
    - Fehler-Details
    - Timing
    - Retry-Informationen
    """
    __tablename__ = "workflow_step_executions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_execution_id = Column(UUID(as_uuid=True), ForeignKey("workflow_executions.id", ondelete="CASCADE"), nullable=False, index=True)
    workflow_step_id = Column(UUID(as_uuid=True), ForeignKey("workflow_steps.id", ondelete="CASCADE"), nullable=False, index=True)

    # Ausführungs-Reihenfolge
    execution_order = Column(Integer, nullable=False)

    # Status
    status = Column(String(20), nullable=False, default="pending", index=True)
    # Status: pending, running, completed, failed, skipped

    # Input/Output
    input_data = Column(CrossDBJSON, nullable=True)
    output_data = Column(CrossDBJSON, nullable=True)

    # Fehler-Details
    error_message = Column(Text, nullable=True)
    error_code = Column(String(50), nullable=True)
    error_details = Column(CrossDBJSON, nullable=True)

    # Timing
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    duration_ms = Column(Integer, nullable=True)

    # Retry-Info
    retry_attempt = Column(Integer, default=0, nullable=False)
    next_retry_at = Column(DateTime(timezone=True), nullable=True)

    # Branch-Entscheidung
    branch_result = Column(Boolean, nullable=True)
    branch_reason = Column(Text, nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    workflow_execution = relationship("WorkflowExecution", back_populates="step_executions")
    workflow_step = relationship("WorkflowStep", back_populates="step_executions")

    __table_args__ = (
        Index("ix_workflow_step_execs_order", "workflow_execution_id", "execution_order"),
        {"comment": "Schritt-Level Audit Trail für Workflow-Ausführungen"}
    )

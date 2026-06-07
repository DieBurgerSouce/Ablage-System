"""BPMN 2.0 Process Engine Database Models.

Enterprise-Grade Workflow Engine mit:
- Process Definitions (BPMN 2.0 XML + JSONB)
- Process Instances (Laufende Prozesse)
- Process Tasks (User Tasks, Service Tasks)
- Timer Events (Celery Integration)
- Gateways (Exclusive, Parallel, Inclusive, Event-based)
- Human Task Assignment & Escalation

Migration: 106_add_bpmn_process_engine.py
"""

from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
import uuid

from sqlalchemy import (
    Column, String, Integer, DateTime, Boolean, Float, Text,
    ForeignKey, Index, CheckConstraint, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

# Import Base, CrossDBJSON and enums from the main models file
from app.db.models import (
    Base,
    CrossDBJSON,
    ProcessStatus,
    BpmnTaskStatus as TaskStatus,
    TaskType,
    GatewayType,
    EventType,
    EventTrigger,
)


# =============================================================================
# PROCESS DEFINITION
# =============================================================================

class ProcessDefinition(Base):
    """BPMN 2.0 Prozess-Definition.

    Speichert die komplette Prozess-Definition inkl. BPMN XML.
    Unterstützt Versionierung für Prozess-Updates.
    """
    __tablename__ = "bpmn_process_definitions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Identifikation
    key = Column(String(255), nullable=False, index=True,
                 comment="Eindeutiger Prozess-Key (z.B. 'invoice-approval')")
    name = Column(String(255), nullable=False,
                  comment="Anzeigename (z.B. 'Rechnungsfreigabe')")
    description = Column(Text, nullable=True)

    # Versionierung
    version = Column(Integer, nullable=False, default=1,
                     comment="Versionsnummer (auto-increment)")
    is_active = Column(Boolean, nullable=False, default=True,
                       comment="Nur aktive Version wird für neue Instanzen genutzt")

    # BPMN Definition
    bpmn_xml = Column(Text, nullable=True,
                      comment="BPMN 2.0 XML für Import/Export")
    process_data = Column(CrossDBJSON, nullable=False, default=dict,
                          comment="Parsed BPMN als JSONB für schnellen Zugriff")

    # Metadaten
    category = Column(String(100), nullable=True, index=True,
                      comment="Kategorie (z.B. 'Finanzen', 'HR')")
    tags = Column(CrossDBJSON, nullable=True, default=list,
                  comment="Tags für Suche/Filter")

    # Deployment
    deployed_at = Column(DateTime(timezone=True), nullable=True,
                         comment="Zeitpunkt der letzten Aktivierung")
    deployed_by_id = Column(UUID(as_uuid=True),
                            ForeignKey("users.id", ondelete="SET NULL"),
                            nullable=True)

    # Multi-Tenant
    company_id = Column(UUID(as_uuid=True),
                        ForeignKey("companies.id", ondelete="CASCADE"),
                        nullable=False, index=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(),
                        onupdate=func.now())

    # Relationships
    company = relationship("Company", back_populates="bpmn_process_definitions")
    deployed_by = relationship("User", foreign_keys=[deployed_by_id])
    instances = relationship("ProcessInstance", back_populates="definition",
                             cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("company_id", "key", "version",
                         name="uq_process_def_company_key_version"),
        Index("ix_process_def_active", "company_id", "key", "is_active"),
    )


# =============================================================================
# PROCESS INSTANCE
# =============================================================================

class ProcessInstance(Base):
    """Laufende Prozess-Instanz.

    Eine Instanz repräsentiert einen konkreten Durchlauf einer Definition.
    Z.B. "Freigabe für Rechnung #12345"
    """
    __tablename__ = "bpmn_process_instances"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Referenz zur Definition
    definition_id = Column(UUID(as_uuid=True),
                           ForeignKey("bpmn_process_definitions.id",
                                      ondelete="RESTRICT"),
                           nullable=False, index=True)

    # Business-Key für externe Referenz
    business_key = Column(String(255), nullable=True, index=True,
                          comment="Externer Schlüssel (z.B. Rechnungsnummer)")

    # Status
    status = Column(String(50), nullable=False, default=ProcessStatus.CREATED,
                    index=True)

    # Prozess-Variablen (Input/Output)
    variables = Column(CrossDBJSON, nullable=False, default=dict,
                       comment="Prozess-Variablen als Key-Value")

    # Aktueller Zustand
    current_elements = Column(CrossDBJSON, nullable=False, default=list,
                              comment="Aktive BPMN Element-IDs")

    # Initiator
    started_by_id = Column(UUID(as_uuid=True),
                           ForeignKey("users.id", ondelete="SET NULL"),
                           nullable=True, index=True)

    # Multi-Tenant
    company_id = Column(UUID(as_uuid=True),
                        ForeignKey("companies.id", ondelete="CASCADE"),
                        nullable=False, index=True)

    # Dokument-Verknüpfung (optional)
    document_id = Column(UUID(as_uuid=True),
                         ForeignKey("documents.id", ondelete="SET NULL"),
                         nullable=True, index=True,
                         comment="Verknüpftes Dokument (z.B. die Rechnung)")

    # Call Activity: Verknüpfung zur Eltern-Instanz (Sub-Prozess via callActivity)
    parent_instance_id = Column(
        UUID(as_uuid=True),
        ForeignKey("bpmn_process_instances.id", ondelete="SET NULL"),
        nullable=True, index=True,
        comment="Eltern-Instanz bei Call-Activity-Sub-Prozessen",
    )
    parent_element_id = Column(
        String(255), nullable=True,
        comment="Call-Activity-Element-ID in der Eltern-Instanz (Rückkopplung)",
    )

    # Timestamps
    started_at = Column(DateTime(timezone=True), nullable=True)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(),
                        onupdate=func.now())

    # Relationships
    definition = relationship("ProcessDefinition", back_populates="instances")
    company = relationship("Company", back_populates="bpmn_process_instances")
    started_by = relationship("User", foreign_keys=[started_by_id])
    document = relationship("Document")
    tasks = relationship("ProcessTask", back_populates="instance",
                         cascade="all, delete-orphan")
    history = relationship("ProcessHistory", back_populates="instance",
                           cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_process_instance_status", "company_id", "status"),
        Index("ix_process_instance_business_key", "company_id", "business_key"),
    )


# =============================================================================
# PROCESS TASK
# =============================================================================

class ProcessTask(Base):
    """BPMN Task innerhalb einer Prozess-Instanz.

    Kann ein User Task, Service Task, etc. sein.
    """
    __tablename__ = "bpmn_process_tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Referenz zur Instanz
    instance_id = Column(UUID(as_uuid=True),
                         ForeignKey("bpmn_process_instances.id",
                                    ondelete="CASCADE"),
                         nullable=False, index=True)

    # BPMN Element-Referenz
    element_id = Column(String(255), nullable=False,
                        comment="ID des BPMN Elements in der Definition")
    element_name = Column(String(255), nullable=True,
                          comment="Name des Tasks für Anzeige")

    # Task-Typ
    task_type = Column(String(50), nullable=False, default=TaskType.USER_TASK)

    # Status
    status = Column(String(50), nullable=False, default=TaskStatus.PENDING,
                    index=True)

    # Zuweisung
    assignee_id = Column(UUID(as_uuid=True),
                         ForeignKey("users.id", ondelete="SET NULL"),
                         nullable=True, index=True,
                         comment="Zugewiesener Benutzer")
    assignee_group = Column(String(255), nullable=True, index=True,
                            comment="Zugewiesene Gruppe/Rolle")

    # Delegation
    delegated_from_id = Column(UUID(as_uuid=True),
                               ForeignKey("users.id", ondelete="SET NULL"),
                               nullable=True,
                               comment="Ursprünglicher Bearbeiter bei Delegation")

    # Priorität & Frist
    priority = Column(Integer, nullable=False, default=50,
                      comment="Priorität 0-100 (höher = wichtiger)")
    due_date = Column(DateTime(timezone=True), nullable=True,
                      comment="Fälligkeitsdatum")
    follow_up_date = Column(DateTime(timezone=True), nullable=True,
                            comment="Wiedervorlage-Datum")

    # Eskalation
    escalation_level = Column(Integer, nullable=False, default=0,
                              comment="Aktuelle Eskalationsstufe")
    escalated_at = Column(DateTime(timezone=True), nullable=True)

    # Task-Daten
    form_key = Column(String(255), nullable=True,
                      comment="Formular-Key für UI")
    task_variables = Column(CrossDBJSON, nullable=False, default=dict,
                            comment="Task-lokale Variablen")

    # Multi-Tenant
    company_id = Column(UUID(as_uuid=True),
                        ForeignKey("companies.id", ondelete="CASCADE"),
                        nullable=False, index=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    claimed_at = Column(DateTime(timezone=True), nullable=True,
                        comment="Zeitpunkt der Übernahme")
    completed_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(),
                        onupdate=func.now())

    # Relationships
    instance = relationship("ProcessInstance", back_populates="tasks")
    company = relationship("Company")
    assignee = relationship("User", foreign_keys=[assignee_id])
    delegated_from = relationship("User", foreign_keys=[delegated_from_id])

    __table_args__ = (
        Index("ix_process_task_assignee", "company_id", "assignee_id", "status"),
        Index("ix_process_task_group", "company_id", "assignee_group", "status"),
        Index("ix_process_task_due", "company_id", "due_date", "status"),
    )


# =============================================================================
# PROCESS HISTORY (Audit Trail)
# =============================================================================

class ProcessHistory(Base):
    """Audit Trail für Prozess-Instanzen.

    Protokolliert jeden Statuswechsel und jede Aktion.
    """
    __tablename__ = "bpmn_process_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Referenz
    instance_id = Column(UUID(as_uuid=True),
                         ForeignKey("bpmn_process_instances.id",
                                    ondelete="CASCADE"),
                         nullable=False, index=True)
    task_id = Column(UUID(as_uuid=True), nullable=True, index=True,
                     comment="Betroffener Task (optional)")

    # Event-Typ
    event_type = Column(String(100), nullable=False, index=True,
                        comment="z.B. 'PROCESS_STARTED', 'TASK_COMPLETED'")

    # Element-Referenz
    element_id = Column(String(255), nullable=True,
                        comment="BPMN Element-ID")
    element_type = Column(String(50), nullable=True,
                          comment="z.B. 'userTask', 'exclusiveGateway'")

    # Details
    old_value = Column(CrossDBJSON, nullable=True,
                       comment="Alter Zustand (für Änderungen)")
    new_value = Column(CrossDBJSON, nullable=True,
                       comment="Neuer Zustand")
    message = Column(Text, nullable=True,
                     comment="Beschreibung des Events")

    # Actor
    actor_id = Column(UUID(as_uuid=True),
                      ForeignKey("users.id", ondelete="SET NULL"),
                      nullable=True)
    actor_type = Column(String(50), nullable=False, default="user",
                        comment="'user', 'system', 'timer'")

    # Multi-Tenant
    company_id = Column(UUID(as_uuid=True),
                        ForeignKey("companies.id", ondelete="CASCADE"),
                        nullable=False, index=True)

    # Timestamp
    timestamp = Column(DateTime(timezone=True), server_default=func.now(),
                       index=True)

    # Relationships
    instance = relationship("ProcessInstance", back_populates="history")
    actor = relationship("User")

    __table_args__ = (
        Index("ix_process_history_time", "company_id", "instance_id", "timestamp"),
    )


# =============================================================================
# TIMER JOB (für Celery Beat Integration)
# =============================================================================

class ProcessTimerJob(Base):
    """Timer-Job für zeitgesteuerte BPMN Events.

    Wird von Celery Beat abgearbeitet.
    """
    __tablename__ = "bpmn_timer_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Referenzen
    instance_id = Column(UUID(as_uuid=True),
                         ForeignKey("bpmn_process_instances.id",
                                    ondelete="CASCADE"),
                         nullable=False, index=True)
    task_id = Column(UUID(as_uuid=True), nullable=True,
                     comment="Zugehöriger Task (für Boundary Timer)")

    # Timer-Konfiguration
    element_id = Column(String(255), nullable=False,
                        comment="BPMN Timer Element-ID")
    timer_type = Column(String(50), nullable=False,
                        comment="'date', 'duration', 'cycle'")
    timer_value = Column(String(255), nullable=False,
                         comment="ISO 8601 Duration oder DateTime")

    # Ausführung
    due_at = Column(DateTime(timezone=True), nullable=False, index=True,
                    comment="Nächste Ausführung")
    repeat_count = Column(Integer, nullable=True,
                          comment="Verbleibende Wiederholungen (für Cycles)")

    # Status
    is_active = Column(Boolean, nullable=False, default=True)
    last_executed_at = Column(DateTime(timezone=True), nullable=True)

    # Multi-Tenant
    company_id = Column(UUID(as_uuid=True),
                        ForeignKey("companies.id", ondelete="CASCADE"),
                        nullable=False, index=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_timer_job_due", "company_id", "due_at", "is_active"),
    )


# =============================================================================
# PROCESS VARIABLE HISTORY (für Debugging)
# =============================================================================

class ProcessVariableHistory(Base):
    """Historie der Prozess-Variablen für Debugging und Audit."""
    __tablename__ = "bpmn_variable_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    instance_id = Column(UUID(as_uuid=True),
                         ForeignKey("bpmn_process_instances.id",
                                    ondelete="CASCADE"),
                         nullable=False, index=True)

    variable_name = Column(String(255), nullable=False)
    old_value = Column(CrossDBJSON, nullable=True)
    new_value = Column(CrossDBJSON, nullable=True)

    # Kontext
    element_id = Column(String(255), nullable=True,
                        comment="BPMN Element, das die Änderung auslöste")
    changed_by_id = Column(UUID(as_uuid=True),
                           ForeignKey("users.id", ondelete="SET NULL"),
                           nullable=True)

    # Multi-Tenant
    company_id = Column(UUID(as_uuid=True),
                        ForeignKey("companies.id", ondelete="CASCADE"),
                        nullable=False, index=True)

    timestamp = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_var_history_instance", "instance_id", "variable_name", "timestamp"),
    )

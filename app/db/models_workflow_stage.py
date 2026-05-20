# -*- coding: utf-8 -*-
"""Database models for Kanban Workflow Stages."""

from datetime import datetime
from enum import Enum
from typing import Optional
import uuid

from sqlalchemy import (
    Column, String, Integer, DateTime, Boolean, ForeignKey,
    Index, UniqueConstraint, Text
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.models import Base, CrossDBJSON


class WorkflowType(str, Enum):
    """Verfügbare Workflow-Typen."""
    DOCUMENT = "document"       # Standard-Dokumentenworkflow
    INVOICE = "invoice"         # Rechnungsworkflow
    CONTRACT = "contract"       # Vertragsworkflow
    CUSTOM = "custom"           # Benutzerdefiniert


class ItemPriority(str, Enum):
    """Prioritätsstufen."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class WorkflowStage(Base):
    """
    Workflow-Stage für Kanban-Board.

    Stages sind die Spalten auf einem Kanban-Board (z.B. "Eingang", "Prüfung", "Archiv").
    Pro Company und Workflow-Type können unterschiedliche Stage-Konfigurationen existieren.
    """
    __tablename__ = "workflow_stages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    workflow_type = Column(String(30), nullable=False)
    stage_key = Column(String(50), nullable=False, comment="Eindeutiger Key (z.B. 'eingang', 'prüfung')")
    stage_name = Column(String(100), nullable=False, comment="Deutsche Anzeige-Bezeichnung")
    stage_order = Column(Integer, nullable=False, comment="Reihenfolge der Stage (1, 2, 3, ...)")
    color = Column(String(20), default="#6B7280", comment="Hex-Farbe für UI")
    icon = Column(String(50), nullable=True, comment="Lucide Icon-Name")
    is_final = Column(Boolean, default=False, comment="Ist dies die finale Stage?")
    auto_transition_after_hours = Column(Integer, nullable=True, comment="Auto-Weiterleitung nach N Stunden")
    required_approval = Column(Boolean, default=False, comment="Freigabe erforderlich?")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    items = relationship("DocumentWorkflowItem", foreign_keys="[DocumentWorkflowItem.current_stage_id]", back_populates="stage", lazy="selectin")

    __table_args__ = (
        UniqueConstraint("company_id", "workflow_type", "stage_key", name="uq_workflow_stage"),
        Index("ix_workflow_stages_company_type", "company_id", "workflow_type"),
        Index("ix_workflow_stages_order", "company_id", "workflow_type", "stage_order"),
    )


class DocumentWorkflowItem(Base):
    """
    Dokument-Position auf einem Kanban-Board.

    Verknüpft ein Dokument mit einer Workflow-Stage und trackt
    Priorität, Zuweisung und Notizen.
    """
    __tablename__ = "document_workflow_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    workflow_type = Column(String(30), nullable=False)
    current_stage_id = Column(UUID(as_uuid=True), ForeignKey("workflow_stages.id", ondelete="RESTRICT"), nullable=False)
    previous_stage_id = Column(UUID(as_uuid=True), ForeignKey("workflow_stages.id", ondelete="SET NULL"), nullable=True)
    entered_stage_at = Column(DateTime(timezone=True), server_default=func.now(), comment="Wann in aktuelle Stage gewechselt")
    assigned_to = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, comment="Zugewiesener Bearbeiter")
    priority = Column(String(20), default="normal", comment="Priorität (low, normal, high, urgent)")
    notes = Column(Text, nullable=True, comment="Notizen zum Workflow-Item")
    metadata_json = Column(CrossDBJSON, nullable=True, comment="Zusätzliche Metadaten")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    stage = relationship("WorkflowStage", foreign_keys=[current_stage_id], back_populates="items")
    previous_stage = relationship("WorkflowStage", foreign_keys=[previous_stage_id])
    document = relationship("Document", foreign_keys=[document_id])
    assignee = relationship("User", foreign_keys=[assigned_to])

    __table_args__ = (
        UniqueConstraint("company_id", "document_id", "workflow_type", name="uq_document_workflow"),
        Index("ix_workflow_items_stage", "current_stage_id"),
        Index("ix_workflow_items_company", "company_id", "workflow_type"),
        Index("ix_workflow_items_document", "document_id"),
        Index("ix_workflow_items_assigned", "assigned_to"),
    )

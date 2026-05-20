# -*- coding: utf-8 -*-
"""
Project Management Models für Ablage-System (Vision 2026).

Projekt-/Kostenstellen-Erweiterung mit:
- Project Model für Projektmanagement
- ProjectMember für Team-Zuordnung
- DocumentProjectAssignment für Dokument-Projekt-Verknüpfung
- KI-basierte Auto-Zuweisung basierend auf Kunden/Entity-Patterns

Phase 1 der Vision 2026 Feature-Roadmap (Q1 2026).
"""

from datetime import datetime, date
from decimal import Decimal
from enum import Enum
from typing import Optional, List
import uuid

from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    Numeric,
    Boolean,
    Text,
    DateTime,
    Date,
    ForeignKey,
    Index,
    UniqueConstraint,
    CheckConstraint,
    Enum as SQLAlchemyEnum,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.models import Base, CrossDBJSON


# ============================================================================
# Enums
# ============================================================================


class ProjectStatus(str, Enum):
    """Projekt-Status."""
    PLANNING = "planning"       # In Planung
    ACTIVE = "active"           # Aktiv
    ON_HOLD = "on_hold"         # Pausiert
    COMPLETED = "completed"     # Abgeschlossen
    CANCELLED = "cancelled"     # Abgebrochen
    ARCHIVED = "archived"       # Archiviert


class ProjectPriority(str, Enum):
    """Projekt-Priorität."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ProjectMemberRole(str, Enum):
    """Rolle eines Projektmitglieds."""
    MEMBER = "member"       # Normales Mitglied
    LEAD = "lead"           # Projektleiter/Stellvertreter
    ADMIN = "admin"         # Administrator (Vollzugriff)
    OBSERVER = "observer"   # Nur Lesezugriff
    EXTERNAL = "external"   # Externer Mitarbeiter


class DocumentAssignmentType(str, Enum):
    """Typ der Dokument-Projekt-Zuordnung."""
    INVOICE = "invoice"             # Rechnung
    CONTRACT = "contract"           # Vertrag
    CORRESPONDENCE = "correspondence"  # Korrespondenz
    DELIVERABLE = "deliverable"     # Lieferobjekt
    REPORT = "report"               # Bericht
    GENERAL = "general"             # Allgemein


# ============================================================================
# Project Model
# ============================================================================


class Project(Base):
    """Projekt für Dokument-Organisation und Kostenzuordnung.

    Multi-Tenant Support:
    - company_id: Firmenzugehoerigkeit (immer erforderlich)

    Kostenstellen-Integration:
    - kostenstelle_id: Optionale Verknüpfung zur Kostenstelle für Budgetierung

    KI-Features:
    - Auto-Zuweisung von Dokumenten basierend auf Kunden/Entity-Patterns
    - Confidence-basierte Vorschläge
    """
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Multi-Tenant
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False
    )

    # Project Identification
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Client (BusinessEntity)
    client_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="SET NULL"),
        nullable=True
    )

    # Status
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default=ProjectStatus.PLANNING.value
    )

    # Timeline
    start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    actual_start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    actual_end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # Budget
    budget: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    budget_spent: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), nullable=False, default=Decimal("0")
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="EUR")

    # Kostenstelle Link
    kostenstelle_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("kostenstellen.id", ondelete="SET NULL"),
        nullable=True
    )

    # Manager
    manager_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Priority & Category
    priority: Mapped[str] = mapped_column(
        String(20), nullable=True, default=ProjectPriority.MEDIUM.value
    )
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Statistics (cached)
    document_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    invoice_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_invoiced: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), nullable=True, default=Decimal("0")
    )

    # Metadata
    tags: Mapped[List[str]] = mapped_column(CrossDBJSON, default=list)
    project_metadata: Mapped[dict] = mapped_column(CrossDBJSON, default=dict)  # Renamed: 'metadata' is reserved in SQLAlchemy

    # Audit
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    created_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Relationships
    company = relationship("Company", foreign_keys=[company_id], backref="projects")
    client = relationship("BusinessEntity", foreign_keys=[client_id])
    kostenstelle = relationship("Kostenstelle", foreign_keys=[kostenstelle_id])
    manager = relationship("User", foreign_keys=[manager_id])
    created_by = relationship("User", foreign_keys=[created_by_id])
    members = relationship(
        "ProjectMember",
        back_populates="project",
        cascade="all, delete-orphan"
    )
    document_assignments = relationship(
        "DocumentProjectAssignment",
        back_populates="project",
        cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("company_id", "code", name="uq_project_code_per_company"),
        Index("ix_projects_company_id", "company_id"),
        Index("ix_projects_client_id", "client_id"),
        Index("ix_projects_kostenstelle_id", "kostenstelle_id"),
        Index("ix_projects_manager_id", "manager_id"),
        Index("ix_projects_status", "status"),
        Index("ix_projects_company_status", "company_id", "status"),
        Index("ix_projects_company_code", "company_id", "code"),
        Index("ix_projects_end_date", "end_date"),
    )

    @property
    def is_active(self) -> bool:
        """Check if project is active."""
        return self.status == ProjectStatus.ACTIVE.value

    @property
    def is_overdue(self) -> bool:
        """Check if project is overdue."""
        if self.status in [ProjectStatus.COMPLETED.value, ProjectStatus.CANCELLED.value]:
            return False
        if self.end_date and self.end_date < date.today():
            return True
        return False

    @property
    def budget_utilization(self) -> Optional[float]:
        """Calculate budget utilization percentage."""
        if not self.budget or self.budget == 0:
            return None
        return float(self.budget_spent / self.budget * 100)

    def __repr__(self) -> str:
        return f"<Project {self.code}: {self.name}>"


# ============================================================================
# Project Member Model
# ============================================================================


class ProjectMember(Base):
    """Projektmitglied - Verknüpfung zwischen User und Project.

    Unterstützt:
    - Rollen-basierte Berechtigungen
    - Zeitlich begrenzte Mitgliedschaft
    - Prozentuale Allokation (für Matrix-Teams)
    """
    __tablename__ = "project_members"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Foreign Keys
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False
    )

    # Role & Permissions
    role: Mapped[str] = mapped_column(
        String(50), nullable=False, default=ProjectMemberRole.MEMBER.value
    )
    permissions: Mapped[List[str]] = mapped_column(CrossDBJSON, default=list)

    # Time-bound (optional)
    valid_from: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    valid_until: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # Allocation
    allocation_percent: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Audit
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    project = relationship("Project", back_populates="members")
    user = relationship("User", backref="project_memberships")

    __table_args__ = (
        UniqueConstraint("project_id", "user_id", name="uq_project_member"),
        Index("ix_project_members_project_id", "project_id"),
        Index("ix_project_members_user_id", "user_id"),
        Index("ix_project_members_active", "project_id", "is_active"),
    )

    @property
    def is_currently_valid(self) -> bool:
        """Check if membership is currently valid."""
        if not self.is_active:
            return False
        today = date.today()
        if self.valid_from and self.valid_from > today:
            return False
        if self.valid_until and self.valid_until < today:
            return False
        return True

    def __repr__(self) -> str:
        return f"<ProjectMember project={self.project_id} user={self.user_id} role={self.role}>"


# ============================================================================
# Document Project Assignment Model
# ============================================================================


class DocumentProjectAssignment(Base):
    """Verknüpfung zwischen Dokument und Projekt.

    Unterstützt:
    - Mehrfach-Zuordnung (ein Dokument kann in mehreren Projekten sein)
    - Auto-Zuweisung durch KI mit Confidence-Score
    - Typisierte Zuordnung (Rechnung, Vertrag, etc.)

    KI-Feature:
    - auto_assigned: True wenn KI zugewiesen hat
    - confidence: KI-Konfidenz (0.0 - 1.0)
    - assignment_reason: Begruendung der KI-Zuweisung
    """
    __tablename__ = "document_project_assignments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Foreign Keys
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False
    )

    # Multi-Tenant (denormalized for RLS performance)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False
    )

    # Assignment Type
    assignment_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default=DocumentAssignmentType.GENERAL.value
    )

    # Assignment Source (Manual vs AI)
    auto_assigned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    assignment_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Assigned By
    assigned_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Audit
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    document = relationship("Document", backref="project_assignments")
    project = relationship("Project", back_populates="document_assignments")
    company = relationship("Company")
    assigned_by = relationship("User")

    __table_args__ = (
        UniqueConstraint("document_id", "project_id", name="uq_document_project"),
        Index("ix_doc_project_document_id", "document_id"),
        Index("ix_doc_project_project_id", "project_id"),
        Index("ix_doc_project_company_id", "company_id"),
        Index("ix_doc_project_auto_assigned", "auto_assigned"),
    )

    @property
    def is_ai_assigned(self) -> bool:
        """Check if this was an AI assignment."""
        return self.auto_assigned and self.confidence is not None

    @property
    def confidence_level(self) -> str:
        """Get human-readable confidence level."""
        if self.confidence is None:
            return "manual"
        if self.confidence >= 0.9:
            return "high"
        if self.confidence >= 0.7:
            return "medium"
        return "low"

    def __repr__(self) -> str:
        return f"<DocumentProjectAssignment doc={self.document_id} project={self.project_id}>"


# ============================================================================
# Project Document Chain Assignment Model (Vision 2026+)
# ============================================================================


class ProjectDocumentChain(Base):
    """Verknüpfung zwischen Projekt und Document Chain.

    Vision 2026+ Feature #3: Projekt-Kontext (Multi-Chain Bundling)
    Ermöglicht die Buendelung mehrerer Document Chains zu einem Projekt.

    Features:
    - Mehrere Chains pro Projekt
    - Fortschritts-Tracking pro Chain
    - Budget-Allokation pro Chain
    - Abweichungs-Aggregation
    """
    __tablename__ = "project_document_chains"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Foreign Keys
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False
    )

    # Chain Identification (chain_id aus document_chain_service)
    chain_id: Mapped[str] = mapped_column(String(100), nullable=False)
    chain_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    chain_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Multi-Tenant (denormalized for RLS)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False
    )

    # Chain Status
    chain_status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="active"
    )  # active, completed, cancelled

    # Progress Tracking
    expected_document_types: Mapped[List[str]] = mapped_column(
        CrossDBJSON, default=lambda: ["quote", "order", "delivery_note", "invoice"]
    )
    completed_document_types: Mapped[List[str]] = mapped_column(CrossDBJSON, default=list)
    progress_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Budget Allocation (optional)
    allocated_budget: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    actual_cost: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), nullable=False, default=Decimal("0")
    )

    # Chain Metrics (cached)
    document_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    discrepancy_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    has_critical_discrepancy: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # First/Last Documents
    first_document_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True
    )
    last_document_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True
    )
    first_document_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    last_document_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # Business Entity (Kunde/Lieferant der Chain)
    entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="SET NULL"),
        nullable=True
    )

    # Order/Reference Numbers
    primary_reference: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    order_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Notes
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Metadata
    chain_metadata: Mapped[dict] = mapped_column(CrossDBJSON, default=dict)  # Renamed: 'metadata' is reserved in SQLAlchemy

    # Audit
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    created_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Relationships
    project = relationship("Project", backref="document_chains")
    company = relationship("Company")
    entity = relationship("BusinessEntity")
    first_document = relationship("Document", foreign_keys=[first_document_id])
    last_document = relationship("Document", foreign_keys=[last_document_id])
    created_by = relationship("User")

    __table_args__ = (
        UniqueConstraint("project_id", "chain_id", name="uq_project_chain"),
        Index("ix_project_chains_project_id", "project_id"),
        Index("ix_project_chains_company_id", "company_id"),
        Index("ix_project_chains_chain_id", "chain_id"),
        Index("ix_project_chains_entity_id", "entity_id"),
        Index("ix_project_chains_status", "chain_status"),
    )

    @property
    def is_complete(self) -> bool:
        """Check if chain has all expected documents."""
        if not self.expected_document_types:
            return False
        return set(self.expected_document_types).issubset(set(self.completed_document_types))

    @property
    def budget_variance(self) -> Optional[Decimal]:
        """Calculate budget variance."""
        if self.allocated_budget is None:
            return None
        return self.allocated_budget - self.actual_cost

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "id": str(self.id),
            "project_id": str(self.project_id),
            "chain_id": self.chain_id,
            "chain_name": self.chain_name,
            "chain_description": self.chain_description,
            "company_id": str(self.company_id),
            "chain_status": self.chain_status,
            "expected_document_types": self.expected_document_types,
            "completed_document_types": self.completed_document_types,
            "progress_percent": self.progress_percent,
            "allocated_budget": float(self.allocated_budget) if self.allocated_budget else None,
            "actual_cost": float(self.actual_cost),
            "document_count": self.document_count,
            "total_amount": float(self.total_amount) if self.total_amount else None,
            "discrepancy_count": self.discrepancy_count,
            "has_critical_discrepancy": self.has_critical_discrepancy,
            "entity_id": str(self.entity_id) if self.entity_id else None,
            "primary_reference": self.primary_reference,
            "order_number": self.order_number,
            "first_document_date": self.first_document_date.isoformat() if self.first_document_date else None,
            "last_document_date": self.last_document_date.isoformat() if self.last_document_date else None,
            "is_complete": self.is_complete,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:
        return f"<ProjectDocumentChain project={self.project_id} chain={self.chain_id}>"

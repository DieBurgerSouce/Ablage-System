"""Approval Matrix Satellite Models.

Erweitert das Genehmigungssystem um:
- ApprovalMatrix: Betrags-/Abteilungsbasierte Genehmigungsketten
- ApprovalChainTemplate: Wiederverwendbare Genehmigungsketten-Vorlagen
- ApprovalAuditLog: Unveraenderliches Audit-Protokoll
- ApprovalGroup + ApprovalGroupMember: Gruppenbasierte Genehmigungen
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Integer, Numeric,
    String, Text, func, UniqueConstraint, Index
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.db.models import Base


class ApprovalMatrix(Base):
    """Genehmigungsmatrix: Betrags- und Abteilungsbasierte Zuordnung.

    Bestimmt automatisch die Genehmigungskette basierend auf:
    - Betragsgrenzen (amount_min/amount_max)
    - Abteilung
    - Vier-Augen-Prinzip Anforderung
    """
    __tablename__ = "approval_matrices"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)

    # Matrix-Dimensionen
    department = Column(String(100), nullable=False, comment="Abteilung (z.B. Einkauf, Finanzen)")
    document_type = Column(String(50), nullable=True, comment="Dokumenttyp (optional, z.B. invoice, contract)")
    amount_min = Column(Numeric(15, 2), nullable=False, default=0, comment="Mindestbetrag (EUR)")
    amount_max = Column(Numeric(15, 2), nullable=True, comment="Hoechstbetrag (EUR, NULL = unbegrenzt)")

    # Genehmigungskette
    chain_template_id = Column(UUID(as_uuid=True), ForeignKey("approval_chain_templates.id", ondelete="SET NULL"), nullable=True)

    # Vier-Augen-Prinzip
    four_eyes_required = Column(Boolean, default=False, comment="Vier-Augen-Prinzip erforderlich")
    min_approvers = Column(Integer, default=1, comment="Mindestanzahl Genehmiger")

    # Prioritaet (bei Ueberlappung)
    priority = Column(Integer, default=0, comment="Hoehere Prioritaet = bevorzugt bei Ueberlappung")

    # Status
    is_active = Column(Boolean, default=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    chain_template = relationship("ApprovalChainTemplate", back_populates="matrices")

    __table_args__ = (
        Index("ix_approval_matrices_company_dept", "company_id", "department"),
        Index("ix_approval_matrices_company_amount", "company_id", "amount_min", "amount_max"),
    )


class ApprovalChainTemplate(Base):
    """Wiederverwendbare Genehmigungsketten-Vorlage.

    Definiert eine Sequenz von Genehmigungsschritten,
    die in der Matrix referenziert werden kann.
    """
    __tablename__ = "approval_chain_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)

    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Kette als JSONB (Schritte mit Rolle/Gruppe/User)
    steps_config = Column(JSONB, nullable=False, default=list, comment="[{step: 1, approver_type: 'role'|'group'|'user', approver_id: UUID, timeout_hours: 48}]")

    is_default = Column(Boolean, default=False, comment="Standard-Kette fuer Firma")
    is_active = Column(Boolean, default=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    matrices = relationship("ApprovalMatrix", back_populates="chain_template")

    __table_args__ = (
        UniqueConstraint("company_id", "name", name="uq_chain_template_company_name"),
    )


class ApprovalAuditLog(Base):
    """Unveraenderliches Audit-Protokoll fuer Genehmigungen.

    Append-only: Keine Updates oder Deletes erlaubt.
    Dokumentiert jeden Statuswechsel einer Genehmigung.
    """
    __tablename__ = "approval_audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)

    # Referenz
    request_id = Column(UUID(as_uuid=True), ForeignKey("approval_requests.id", ondelete="CASCADE"), nullable=False, index=True)
    step_id = Column(UUID(as_uuid=True), ForeignKey("approval_steps.id", ondelete="SET NULL"), nullable=True)

    # Aktion
    actor_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action_type = Column(String(50), nullable=False, comment="created|approved|rejected|escalated|delegated|recalled|four_eyes_check")

    # Status-Aenderung
    old_status = Column(String(50), nullable=True)
    new_status = Column(String(50), nullable=False)

    # Details
    notes = Column(Text, nullable=True)
    metadata_json = Column(JSONB, nullable=True, comment="Zusaetzliche Kontextdaten")

    # IP-Adresse fuer Compliance
    ip_address = Column(String(45), nullable=True, comment="IPv4/IPv6 des Akteurs")

    # Zeitstempel (unveraenderlich)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_audit_log_request_created", "request_id", "created_at"),
        Index("ix_audit_log_company_created", "company_id", "created_at"),
    )


class ApprovalGroup(Base):
    """Genehmigungsgruppe fuer gruppenbasierte Genehmigungen.

    Ermoeglicht Zuweisung von Genehmigungen an Gruppen
    statt einzelne Benutzer.
    """
    __tablename__ = "approval_groups"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)

    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Entscheidungsmodus
    decision_mode = Column(String(50), default="any", comment="any=einer genuegt, all=alle muessen, majority=Mehrheit")

    is_active = Column(Boolean, default=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    members = relationship("ApprovalGroupMember", back_populates="group", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("company_id", "name", name="uq_approval_group_company_name"),
    )


class ApprovalGroupMember(Base):
    """Mitgliedschaft in einer Genehmigungsgruppe."""
    __tablename__ = "approval_group_members"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    group_id = Column(UUID(as_uuid=True), ForeignKey("approval_groups.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Rolle in der Gruppe
    can_approve = Column(Boolean, default=True)
    can_reject = Column(Boolean, default=True)
    is_backup = Column(Boolean, default=False, comment="Stellvertreter (nur bei Abwesenheit)")

    # Audit
    added_at = Column(DateTime(timezone=True), server_default=func.now())
    added_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    group = relationship("ApprovalGroup", back_populates="members")

    __table_args__ = (
        UniqueConstraint("group_id", "user_id", name="uq_group_member"),
    )

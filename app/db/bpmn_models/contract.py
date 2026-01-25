"""
Business Contract Models

Comprehensive contract management for B2B contracts including:
- Contract tracking (Vertragslaufzeiten)
- Cancellation deadline alerts (Kuendigungsfristen)
- Renewal options tracking
- Contract amendments
- Milestones and timeline
"""

from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import Optional, List
from uuid import UUID, uuid4
from enum import Enum

from sqlalchemy import (
    Column, String, Text, DateTime, Date, Integer, Boolean,
    ForeignKey, Numeric, Enum as SQLEnum, UniqueConstraint, Index,
    event, func,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.ext.hybrid import hybrid_property

from app.db.models import Base


# =============================================================================
# Enums
# =============================================================================

class ContractType(str, Enum):
    """Types of business contracts."""
    SERVICE = "service"  # Dienstleistungsvertrag
    SUPPLY = "supply"  # Liefervertrag
    FRAMEWORK = "framework"  # Rahmenvertrag
    MAINTENANCE = "maintenance"  # Wartungsvertrag
    LICENSE = "license"  # Lizenzvertrag
    LEASE = "lease"  # Mietvertrag (Geschaeftsraeume)
    CONSULTING = "consulting"  # Beratungsvertrag
    COOPERATION = "cooperation"  # Kooperationsvertrag
    NDA = "nda"  # Geheimhaltungsvereinbarung
    PURCHASE = "purchase"  # Kaufvertrag
    OTHER = "other"


class ContractStatus(str, Enum):
    """Contract lifecycle status."""
    DRAFT = "draft"  # Entwurf
    PENDING_SIGNATURE = "pending_signature"  # Unterschrift ausstehend
    ACTIVE = "active"  # Aktiv
    SUSPENDED = "suspended"  # Ausgesetzt
    EXPIRING_SOON = "expiring_soon"  # Laeuft bald ab
    EXPIRED = "expired"  # Abgelaufen
    TERMINATED = "terminated"  # Gekuendigt
    RENEWED = "renewed"  # Verlaengert


class RenewalOptionStatus(str, Enum):
    """Status of renewal options."""
    AVAILABLE = "available"  # Verfuegbar
    PENDING = "pending"  # Entscheidung ausstehend
    EXERCISED = "exercised"  # Ausgeubt
    DECLINED = "declined"  # Abgelehnt
    EXPIRED = "expired"  # Abgelaufen


class MilestoneType(str, Enum):
    """Types of contract milestones."""
    CONTRACT_START = "contract_start"
    CONTRACT_END = "contract_end"
    RENEWAL_OPTION = "renewal_option"
    NOTICE_DEADLINE = "notice_deadline"
    PRICE_ADJUSTMENT = "price_adjustment"
    SERVICE_LEVEL_REVIEW = "service_level_review"
    DELIVERABLE_DUE = "deliverable_due"
    PAYMENT_DUE = "payment_due"
    AUDIT = "audit"
    CUSTOM = "custom"


class AmendmentStatus(str, Enum):
    """Status of contract amendments."""
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


# =============================================================================
# Business Contract Model
# =============================================================================

class BusinessContract(Base):
    """
    Business Contract entity for B2B contract management.

    Supports:
    - Contract lifecycle tracking
    - Automatic deadline calculations
    - Renewal options management
    - Multi-tenant operation
    """
    __tablename__ = "business_contracts"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("companies.id"), nullable=False
    )

    # Contract identification
    contract_number: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    contract_type: Mapped[ContractType] = mapped_column(
        SQLEnum(ContractType), default=ContractType.OTHER
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Contract parties
    party_a_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("business_entities.id"), nullable=True
    )
    party_a_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    party_a_signatory: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    party_b_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("business_entities.id"), nullable=True
    )
    party_b_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    party_b_signatory: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Contract timeline
    contract_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    duration_months: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Termination and renewal
    notice_period_days: Mapped[int] = mapped_column(Integer, default=30)
    notice_deadline: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    auto_renewal: Mapped[bool] = mapped_column(Boolean, default=False)
    renewal_period_months: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_renewals: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    current_renewal_count: Mapped[int] = mapped_column(Integer, default=0)

    # Financial terms
    total_value: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(15, 2), nullable=True
    )
    monthly_value: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(15, 2), nullable=True
    )
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    payment_terms: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Price adjustments
    price_adjustment_clause: Mapped[bool] = mapped_column(Boolean, default=False)
    price_adjustment_index: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )  # e.g., "VPI", "Verbraucherpreisindex"
    price_adjustment_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    price_adjustment_percent: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 2), nullable=True
    )

    # Legal terms
    governing_law: Mapped[str] = mapped_column(String(100), default="Deutsches Recht")
    jurisdiction: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    arbitration_clause: Mapped[bool] = mapped_column(Boolean, default=False)

    # Document references
    document_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("documents.id"), nullable=True
    )

    # Status and workflow
    status: Mapped[ContractStatus] = mapped_column(
        SQLEnum(ContractStatus), default=ContractStatus.DRAFT
    )
    signed_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    terminated_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    termination_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Notifications
    reminder_days: Mapped[List[int]] = mapped_column(
        JSONB, default=lambda: [90, 60, 30, 14, 7]
    )
    last_reminder_sent: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    notification_emails: Mapped[List[str]] = mapped_column(
        JSONB, default=list
    )

    # Metadata
    tags: Mapped[List[str]] = mapped_column(JSONB, default=list)
    metadata: Mapped[dict] = mapped_column(JSONB, default=dict)
    key_contacts: Mapped[List[dict]] = mapped_column(JSONB, default=list)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Audit
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )
    created_by_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    # Relationships
    party_a = relationship("BusinessEntity", foreign_keys=[party_a_id])
    party_b = relationship("BusinessEntity", foreign_keys=[party_b_id])
    document = relationship("Document", foreign_keys=[document_id])
    created_by = relationship("User", foreign_keys=[created_by_id])
    milestones = relationship(
        "ContractMilestone", back_populates="contract", cascade="all, delete-orphan"
    )
    amendments = relationship(
        "ContractAmendment", back_populates="contract", cascade="all, delete-orphan"
    )
    renewal_options = relationship(
        "ContractRenewalOption", back_populates="contract", cascade="all, delete-orphan"
    )

    # Indexes and constraints
    __table_args__ = (
        UniqueConstraint("company_id", "contract_number", name="uq_contract_number"),
        Index("ix_contract_company", "company_id"),
        Index("ix_contract_status", "status"),
        Index("ix_contract_end_date", "end_date"),
        Index("ix_contract_notice_deadline", "notice_deadline"),
        Index("ix_contract_party_a", "party_a_id"),
        Index("ix_contract_party_b", "party_b_id"),
    )

    @hybrid_property
    def days_until_end(self) -> Optional[int]:
        """Calculate days until contract ends."""
        if not self.end_date:
            return None
        delta = self.end_date - date.today()
        return delta.days

    @hybrid_property
    def days_until_notice_deadline(self) -> Optional[int]:
        """Calculate days until notice deadline."""
        if not self.notice_deadline:
            return None
        delta = self.notice_deadline - date.today()
        return delta.days

    @hybrid_property
    def is_expiring_soon(self) -> bool:
        """Check if contract is expiring within 90 days."""
        if not self.end_date:
            return False
        return 0 < (self.end_date - date.today()).days <= 90

    @hybrid_property
    def is_notice_deadline_critical(self) -> bool:
        """Check if notice deadline is within 30 days."""
        if not self.notice_deadline:
            return False
        days = (self.notice_deadline - date.today()).days
        return 0 < days <= 30

    def calculate_notice_deadline(self) -> Optional[date]:
        """Calculate notice deadline based on end date and notice period."""
        if not self.end_date:
            return None
        return self.end_date - timedelta(days=self.notice_period_days)

    def update_notice_deadline(self) -> None:
        """Update the notice deadline field."""
        self.notice_deadline = self.calculate_notice_deadline()


# =============================================================================
# Contract Milestone Model
# =============================================================================

class ContractMilestone(Base):
    """
    Contract milestones for tracking key dates and events.
    """
    __tablename__ = "contract_milestones"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    contract_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("business_contracts.id"), nullable=False
    )

    milestone_type: Mapped[MilestoneType] = mapped_column(
        SQLEnum(MilestoneType), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    scheduled_date: Mapped[date] = mapped_column(Date, nullable=False)

    # Completion tracking
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    completed_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    completion_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Notifications
    reminder_days_before: Mapped[List[int]] = mapped_column(
        JSONB, default=lambda: [14, 7, 1]
    )
    last_reminder_sent: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # Linked task (optional)
    linked_task_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )

    # Audit
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    contract = relationship("BusinessContract", back_populates="milestones")

    __table_args__ = (
        Index("ix_milestone_contract", "contract_id"),
        Index("ix_milestone_scheduled", "scheduled_date"),
        Index("ix_milestone_type", "milestone_type"),
    )

    @hybrid_property
    def days_until_due(self) -> int:
        """Calculate days until milestone is due."""
        delta = self.scheduled_date - date.today()
        return delta.days

    @hybrid_property
    def is_overdue(self) -> bool:
        """Check if milestone is overdue and not completed."""
        return not self.is_completed and self.scheduled_date < date.today()


# =============================================================================
# Contract Renewal Option Model
# =============================================================================

class ContractRenewalOption(Base):
    """
    Tracks available renewal options for a contract.
    """
    __tablename__ = "contract_renewal_options"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    contract_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("business_contracts.id"), nullable=False
    )

    # Option details
    option_number: Mapped[int] = mapped_column(Integer, nullable=False)
    renewal_duration_months: Mapped[int] = mapped_column(Integer, nullable=False)

    # Pricing
    price_adjustment_type: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )  # "fixed", "percentage", "index"
    price_adjustment_value: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 2), nullable=True
    )
    new_monthly_value: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(15, 2), nullable=True
    )

    # Deadlines
    exercise_deadline: Mapped[date] = mapped_column(Date, nullable=False)
    renewal_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    notice_required_days: Mapped[int] = mapped_column(Integer, default=30)

    # Status
    status: Mapped[RenewalOptionStatus] = mapped_column(
        SQLEnum(RenewalOptionStatus), default=RenewalOptionStatus.AVAILABLE
    )
    exercised_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    exercised_by_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    decision_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Audit
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    contract = relationship("BusinessContract", back_populates="renewal_options")
    exercised_by = relationship("User", foreign_keys=[exercised_by_id])

    __table_args__ = (
        UniqueConstraint(
            "contract_id", "option_number", name="uq_contract_renewal_option"
        ),
        Index("ix_renewal_contract", "contract_id"),
        Index("ix_renewal_deadline", "exercise_deadline"),
        Index("ix_renewal_status", "status"),
    )

    @hybrid_property
    def days_until_deadline(self) -> int:
        """Calculate days until exercise deadline."""
        delta = self.exercise_deadline - date.today()
        return delta.days

    @hybrid_property
    def is_deadline_critical(self) -> bool:
        """Check if deadline is within 30 days and option still available."""
        if self.status != RenewalOptionStatus.AVAILABLE:
            return False
        return 0 < self.days_until_deadline <= 30


# =============================================================================
# Contract Amendment Model
# =============================================================================

class ContractAmendment(Base):
    """
    Tracks contract amendments and changes.
    """
    __tablename__ = "contract_amendments"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    contract_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("business_contracts.id"), nullable=False
    )

    # Amendment identification
    amendment_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    amendment_date: Mapped[date] = mapped_column(Date, nullable=False)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)

    # Changes
    changes_summary: Mapped[str] = mapped_column(Text, nullable=False)
    affected_clauses: Mapped[List[str]] = mapped_column(JSONB, default=list)
    changes_detail: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Financial impact
    value_change: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(15, 2), nullable=True
    )
    new_total_value: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(15, 2), nullable=True
    )

    # Document
    document_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("documents.id"), nullable=True
    )

    # Status
    status: Mapped[AmendmentStatus] = mapped_column(
        SQLEnum(AmendmentStatus), default=AmendmentStatus.DRAFT
    )
    approved_by_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    approved_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # Audit
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )
    created_by_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    # Relationships
    contract = relationship("BusinessContract", back_populates="amendments")
    document = relationship("Document", foreign_keys=[document_id])
    approved_by = relationship("User", foreign_keys=[approved_by_id])
    created_by = relationship("User", foreign_keys=[created_by_id])

    __table_args__ = (
        UniqueConstraint(
            "contract_id", "amendment_number", name="uq_contract_amendment_number"
        ),
        Index("ix_amendment_contract", "contract_id"),
        Index("ix_amendment_status", "status"),
        Index("ix_amendment_effective", "effective_date"),
    )


# =============================================================================
# Event Listeners
# =============================================================================

@event.listens_for(BusinessContract, 'before_insert')
@event.listens_for(BusinessContract, 'before_update')
def contract_before_save(mapper, connection, target: BusinessContract):
    """Auto-calculate notice deadline before saving."""
    if target.end_date and target.notice_period_days:
        target.notice_deadline = target.calculate_notice_deadline()

    # Auto-update status based on dates
    today = date.today()
    if target.status not in [ContractStatus.DRAFT, ContractStatus.TERMINATED]:
        if target.end_date:
            if target.end_date < today:
                target.status = ContractStatus.EXPIRED
            elif (target.end_date - today).days <= 90:
                target.status = ContractStatus.EXPIRING_SOON
            elif target.status == ContractStatus.EXPIRING_SOON:
                target.status = ContractStatus.ACTIVE

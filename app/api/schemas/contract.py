"""
Contract API Schemas

Pydantic schemas for contract management API endpoints.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any
from uuid import UUID
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


# =============================================================================
# Enums (mirror DB enums for API)
# =============================================================================

class ContractType(str, Enum):
    """Types of business contracts."""
    SERVICE = "service"
    SUPPLY = "supply"
    FRAMEWORK = "framework"
    MAINTENANCE = "maintenance"
    LICENSE = "license"
    LEASE = "lease"
    CONSULTING = "consulting"
    COOPERATION = "cooperation"
    NDA = "nda"
    PURCHASE = "purchase"
    OTHER = "other"


class ContractStatus(str, Enum):
    """Contract lifecycle status."""
    DRAFT = "draft"
    PENDING_SIGNATURE = "pending_signature"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    EXPIRING_SOON = "expiring_soon"
    EXPIRED = "expired"
    TERMINATED = "terminated"
    RENEWED = "renewed"


class RenewalOptionStatus(str, Enum):
    """Status of renewal options."""
    AVAILABLE = "available"
    PENDING = "pending"
    EXERCISED = "exercised"
    DECLINED = "declined"
    EXPIRED = "expired"


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
# Contract Schemas
# =============================================================================

class ContractBase(BaseModel):
    """Base schema for contract fields."""
    contract_number: str = Field(..., min_length=1, max_length=100)
    title: str = Field(..., min_length=1, max_length=500)
    contract_type: ContractType = ContractType.OTHER
    description: Optional[str] = None

    # Parties
    party_a_id: Optional[UUID] = None
    party_a_name: Optional[str] = Field(None, max_length=255)
    party_a_signatory: Optional[str] = Field(None, max_length=255)
    party_b_id: Optional[UUID] = None
    party_b_name: Optional[str] = Field(None, max_length=255)
    party_b_signatory: Optional[str] = Field(None, max_length=255)

    # Timeline
    contract_date: Optional[date] = None
    start_date: date
    end_date: Optional[date] = None
    duration_months: Optional[int] = Field(None, ge=1, le=600)  # max 50 years

    # Termination and renewal
    notice_period_days: int = Field(default=30, ge=0, le=365)
    auto_renewal: bool = False
    renewal_period_months: Optional[int] = Field(None, ge=1, le=120)  # max 10 years
    max_renewals: Optional[int] = Field(None, ge=0, le=99)

    # Financial
    total_value: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    monthly_value: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    currency: str = Field(default="EUR", max_length=3)
    payment_terms: Optional[str] = Field(None, max_length=255)

    # Price adjustments
    price_adjustment_clause: bool = False
    price_adjustment_index: Optional[str] = Field(None, max_length=100)
    price_adjustment_date: Optional[date] = None
    price_adjustment_percent: Optional[Decimal] = Field(None, ge=-100, le=100)

    # Legal
    governing_law: str = Field(default="Deutsches Recht", max_length=100)
    jurisdiction: Optional[str] = Field(None, max_length=255)
    arbitration_clause: bool = False

    # Document
    document_id: Optional[UUID] = None

    # Notifications
    reminder_days: List[int] = Field(default_factory=lambda: [90, 60, 30, 14, 7])
    notification_emails: List[str] = Field(default_factory=list)

    # Metadata
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    key_contacts: List[Dict[str, Any]] = Field(default_factory=list)
    notes: Optional[str] = None

    @field_validator('reminder_days', mode='before')
    @classmethod
    def validate_reminder_days(cls, v: Any) -> List[int]:
        if v is None:
            return [90, 60, 30, 14, 7]
        if isinstance(v, list):
            return sorted([d for d in v if 0 < d <= 365], reverse=True)
        return [90, 60, 30, 14, 7]


class ContractCreate(ContractBase):
    """Schema for creating a new contract."""
    pass


class ContractUpdate(BaseModel):
    """Schema for updating a contract."""
    contract_number: Optional[str] = Field(None, min_length=1, max_length=100)
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    contract_type: Optional[ContractType] = None
    description: Optional[str] = None

    # Parties
    party_a_id: Optional[UUID] = None
    party_a_name: Optional[str] = Field(None, max_length=255)
    party_a_signatory: Optional[str] = Field(None, max_length=255)
    party_b_id: Optional[UUID] = None
    party_b_name: Optional[str] = Field(None, max_length=255)
    party_b_signatory: Optional[str] = Field(None, max_length=255)

    # Timeline
    contract_date: Optional[date] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    duration_months: Optional[int] = Field(None, ge=1, le=600)

    # Termination and renewal
    notice_period_days: Optional[int] = Field(None, ge=0, le=365)
    auto_renewal: Optional[bool] = None
    renewal_period_months: Optional[int] = Field(None, ge=1, le=120)
    max_renewals: Optional[int] = Field(None, ge=0, le=99)

    # Financial
    total_value: Optional[Decimal] = Field(None, ge=0)
    monthly_value: Optional[Decimal] = Field(None, ge=0)
    currency: Optional[str] = Field(None, max_length=3)
    payment_terms: Optional[str] = Field(None, max_length=255)

    # Price adjustments
    price_adjustment_clause: Optional[bool] = None
    price_adjustment_index: Optional[str] = Field(None, max_length=100)
    price_adjustment_date: Optional[date] = None
    price_adjustment_percent: Optional[Decimal] = Field(None, ge=-100, le=100)

    # Legal
    governing_law: Optional[str] = Field(None, max_length=100)
    jurisdiction: Optional[str] = Field(None, max_length=255)
    arbitration_clause: Optional[bool] = None

    # Document
    document_id: Optional[UUID] = None

    # Status
    status: Optional[ContractStatus] = None
    signed_date: Optional[date] = None
    terminated_date: Optional[date] = None
    termination_reason: Optional[str] = None

    # Notifications
    reminder_days: Optional[List[int]] = None
    notification_emails: Optional[List[str]] = None

    # Metadata
    tags: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None
    key_contacts: Optional[List[Dict[str, Any]]] = None
    notes: Optional[str] = None


class EntityBrief(BaseModel):
    """Brief entity info for party references."""
    id: UUID
    name: str
    entity_type: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ContractMilestoneResponse(BaseModel):
    """Response schema for contract milestones."""
    id: UUID
    contract_id: UUID
    milestone_type: MilestoneType
    title: str
    description: Optional[str]
    scheduled_date: date
    is_completed: bool
    completed_date: Optional[date]
    completion_notes: Optional[str]
    reminder_days_before: List[int]
    days_until_due: int
    is_overdue: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ContractRenewalOptionResponse(BaseModel):
    """Response schema for renewal options."""
    id: UUID
    contract_id: UUID
    option_number: int
    renewal_duration_months: int
    price_adjustment_type: Optional[str]
    price_adjustment_value: Optional[Decimal]
    new_monthly_value: Optional[Decimal]
    exercise_deadline: date
    renewal_start_date: date
    notice_required_days: int
    status: RenewalOptionStatus
    exercised_date: Optional[date]
    exercised_by_id: Optional[UUID]
    decision_notes: Optional[str]
    days_until_deadline: int
    is_deadline_critical: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ContractAmendmentResponse(BaseModel):
    """Response schema for contract amendments."""
    id: UUID
    contract_id: UUID
    amendment_number: int
    title: str
    amendment_date: date
    effective_date: date
    changes_summary: str
    affected_clauses: List[str]
    changes_detail: Dict[str, Any]
    value_change: Optional[Decimal]
    new_total_value: Optional[Decimal]
    document_id: Optional[UUID]
    status: AmendmentStatus
    approved_by_id: Optional[UUID]
    approved_date: Optional[date]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ContractResponse(BaseModel):
    """Response schema for a contract."""
    id: UUID
    company_id: UUID
    contract_number: str
    title: str
    contract_type: ContractType
    description: Optional[str]
    status: ContractStatus

    # Parties
    party_a_id: Optional[UUID]
    party_a_name: Optional[str]
    party_a_signatory: Optional[str]
    party_a: Optional[EntityBrief]
    party_b_id: Optional[UUID]
    party_b_name: Optional[str]
    party_b_signatory: Optional[str]
    party_b: Optional[EntityBrief]

    # Timeline
    contract_date: Optional[date]
    start_date: date
    end_date: Optional[date]
    duration_months: Optional[int]
    notice_period_days: int
    notice_deadline: Optional[date]

    # Renewal
    auto_renewal: bool
    renewal_period_months: Optional[int]
    max_renewals: Optional[int]
    current_renewal_count: int

    # Financial
    total_value: Optional[Decimal]
    monthly_value: Optional[Decimal]
    currency: str
    payment_terms: Optional[str]

    # Price adjustments
    price_adjustment_clause: bool
    price_adjustment_index: Optional[str]
    price_adjustment_date: Optional[date]
    price_adjustment_percent: Optional[Decimal]

    # Legal
    governing_law: str
    jurisdiction: Optional[str]
    arbitration_clause: bool

    # Document
    document_id: Optional[UUID]

    # Workflow
    signed_date: Optional[date]
    terminated_date: Optional[date]
    termination_reason: Optional[str]

    # Notifications
    reminder_days: List[int]
    notification_emails: List[str]
    last_reminder_sent: Optional[date]

    # Metadata
    tags: List[str]
    metadata: Dict[str, Any]
    key_contacts: List[Dict[str, Any]]
    notes: Optional[str]

    # Computed
    days_until_end: Optional[int]
    days_until_notice_deadline: Optional[int]
    is_expiring_soon: bool
    is_notice_deadline_critical: bool

    # Audit
    created_at: datetime
    updated_at: datetime
    created_by_id: Optional[UUID]

    model_config = ConfigDict(from_attributes=True)


class ContractDetailResponse(ContractResponse):
    """Detailed contract response with relationships."""
    milestones: List[ContractMilestoneResponse] = Field(default_factory=list)
    renewal_options: List[ContractRenewalOptionResponse] = Field(default_factory=list)
    amendments: List[ContractAmendmentResponse] = Field(default_factory=list)


class ContractListResponse(BaseModel):
    """Paginated list of contracts."""
    items: List[ContractResponse]
    total: int
    offset: int
    limit: int


# =============================================================================
# Deadline and Alert Schemas
# =============================================================================

class DeadlineAlertResponse(BaseModel):
    """Response schema for deadline alerts."""
    contract_id: UUID
    contract_number: str
    contract_title: str
    deadline_type: str  # "notice", "end", "renewal"
    deadline_date: date
    days_remaining: int
    urgency: str  # "critical", "warning", "upcoming"
    party_name: Optional[str]


class DeadlineListResponse(BaseModel):
    """List of deadline alerts."""
    items: List[DeadlineAlertResponse]
    total: int


# =============================================================================
# Summary and Analytics Schemas
# =============================================================================

class ContractSummaryResponse(BaseModel):
    """Contract portfolio summary."""
    total_contracts: int
    active_contracts: int
    expiring_soon: int
    critical_deadlines: int
    total_value: Decimal
    monthly_commitment: Decimal


class ContractTimelineEventResponse(BaseModel):
    """Timeline event for a contract."""
    event_date: date
    event_type: str
    title: str
    description: Optional[str]
    is_completed: bool
    contract_id: UUID


class ContractTimelineResponse(BaseModel):
    """Contract timeline with all events."""
    contract_id: UUID
    contract_number: str
    events: List[ContractTimelineEventResponse]


# =============================================================================
# Milestone Schemas
# =============================================================================

class MilestoneCreate(BaseModel):
    """Schema for creating a milestone."""
    milestone_type: MilestoneType
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    scheduled_date: date
    reminder_days_before: List[int] = Field(default_factory=lambda: [14, 7, 1])


class MilestoneUpdate(BaseModel):
    """Schema for updating a milestone."""
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    scheduled_date: Optional[date] = None
    is_completed: Optional[bool] = None
    completed_date: Optional[date] = None
    completion_notes: Optional[str] = None
    reminder_days_before: Optional[List[int]] = None


# =============================================================================
# Renewal Option Schemas
# =============================================================================

class RenewalOptionCreate(BaseModel):
    """Schema for creating a renewal option."""
    renewal_duration_months: int = Field(..., ge=1, le=120)
    exercise_deadline: date
    renewal_start_date: date
    notice_required_days: int = Field(default=30, ge=0, le=365)
    price_adjustment_type: Optional[str] = Field(None, max_length=50)
    price_adjustment_value: Optional[Decimal] = None
    new_monthly_value: Optional[Decimal] = Field(None, ge=0)


class RenewalOptionDecision(BaseModel):
    """Schema for exercising or declining a renewal option."""
    decision: str = Field(..., pattern="^(exercise|decline)$")
    notes: Optional[str] = None


# =============================================================================
# Amendment Schemas
# =============================================================================

class AmendmentCreate(BaseModel):
    """Schema for creating a contract amendment."""
    title: str = Field(..., min_length=1, max_length=255)
    amendment_date: date
    effective_date: date
    changes_summary: str = Field(..., min_length=1)
    affected_clauses: List[str] = Field(default_factory=list)
    changes_detail: Dict[str, Any] = Field(default_factory=dict)
    value_change: Optional[Decimal] = None
    new_total_value: Optional[Decimal] = Field(None, ge=0)
    document_id: Optional[UUID] = None


class AmendmentUpdate(BaseModel):
    """Schema for updating an amendment."""
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    amendment_date: Optional[date] = None
    effective_date: Optional[date] = None
    changes_summary: Optional[str] = None
    affected_clauses: Optional[List[str]] = None
    changes_detail: Optional[Dict[str, Any]] = None
    value_change: Optional[Decimal] = None
    new_total_value: Optional[Decimal] = Field(None, ge=0)
    document_id: Optional[UUID] = None
    status: Optional[AmendmentStatus] = None


# =============================================================================
# Query Parameters
# =============================================================================

class ContractListParams(BaseModel):
    """Query parameters for listing contracts."""
    status: Optional[ContractStatus] = None
    contract_type: Optional[ContractType] = None
    party_id: Optional[UUID] = None
    expiring_within_days: Optional[int] = Field(None, ge=1, le=365)
    search: Optional[str] = Field(None, max_length=200)
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=50, ge=1, le=200)
    order_by: str = Field(default="end_date", pattern="^(contract_number|title|start_date|end_date|notice_deadline|total_value|created_at)$")
    order_dir: str = Field(default="asc", pattern="^(asc|desc)$")

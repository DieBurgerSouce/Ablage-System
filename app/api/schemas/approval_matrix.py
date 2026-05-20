"""Pydantic Schemas fuer Approval Matrix API.

Request/Response Schemas fuer:
- ApprovalMatrix
- ApprovalChainTemplate
- ApprovalAuditLog
- ApprovalGroup
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from decimal import Decimal
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict


# =============================================================================
# ApprovalMatrix Schemas
# =============================================================================

class ApprovalMatrixBase(BaseModel):
    """Base Schema fuer ApprovalMatrix."""
    department: str = Field(..., max_length=100, description="Abteilung (z.B. Einkauf, Finanzen)")
    document_type: Optional[str] = Field(None, max_length=50, description="Dokumenttyp (z.B. invoice, contract)")
    amount_min: Decimal = Field(default=0, description="Mindestbetrag (EUR)")
    amount_max: Optional[Decimal] = Field(None, description="Hoechstbetrag (EUR, NULL = unbegrenzt)")
    chain_template_id: Optional[UUID] = Field(None, description="Chain Template ID")
    four_eyes_required: bool = Field(default=False, description="Vier-Augen-Prinzip erforderlich")
    min_approvers: int = Field(default=1, ge=1, description="Mindestanzahl Genehmiger")
    priority: int = Field(default=0, description="Prioritaet bei Ueberlappung")


class ApprovalMatrixCreate(ApprovalMatrixBase):
    """Schema zum Erstellen einer ApprovalMatrix."""
    pass


class ApprovalMatrixUpdate(BaseModel):
    """Schema zum Aktualisieren einer ApprovalMatrix."""
    department: Optional[str] = Field(None, max_length=100)
    document_type: Optional[str] = Field(None, max_length=50)
    amount_min: Optional[Decimal] = None
    amount_max: Optional[Decimal] = None
    chain_template_id: Optional[UUID] = None
    four_eyes_required: Optional[bool] = None
    min_approvers: Optional[int] = Field(None, ge=1)
    priority: Optional[int] = None
    is_active: Optional[bool] = None


class ApprovalMatrixResponse(ApprovalMatrixBase):
    """Schema fuer ApprovalMatrix Response."""
    id: UUID
    company_id: UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime
    created_by_id: Optional[UUID]

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# ApprovalChainTemplate Schemas
# =============================================================================

class ChainStepConfig(BaseModel):
    """Schema fuer einzelnen Chain Step."""
    step: int = Field(..., ge=1, description="Schritt-Nummer")
    approver_type: str = Field(..., pattern="^(role|group|user)$", description="Typ des Genehmigers")
    approver_id: str = Field(..., description="ID (User UUID, Rollenname, Gruppen-UUID)")
    required: bool = Field(default=True, description="Pflicht-Schritt")
    timeout_hours: int = Field(default=48, ge=1, description="Timeout in Stunden")


class ApprovalChainTemplateBase(BaseModel):
    """Base Schema fuer ApprovalChainTemplate."""
    name: str = Field(..., max_length=255, description="Template-Name")
    description: Optional[str] = Field(None, description="Beschreibung")
    steps_config: List[ChainStepConfig] = Field(default_factory=list, description="Schritte-Konfiguration")
    is_default: bool = Field(default=False, description="Standard-Template fuer Firma")


class ApprovalChainTemplateCreate(ApprovalChainTemplateBase):
    """Schema zum Erstellen einer ApprovalChainTemplate."""
    pass


class ApprovalChainTemplateUpdate(BaseModel):
    """Schema zum Aktualisieren einer ApprovalChainTemplate."""
    name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    steps_config: Optional[List[ChainStepConfig]] = None
    is_default: Optional[bool] = None
    is_active: Optional[bool] = None


class ApprovalChainTemplateResponse(ApprovalChainTemplateBase):
    """Schema fuer ApprovalChainTemplate Response."""
    id: UUID
    company_id: UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime
    created_by_id: Optional[UUID]

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# ApprovalAuditLog Schemas
# =============================================================================

class ApprovalAuditLogResponse(BaseModel):
    """Schema fuer ApprovalAuditLog Response."""
    id: UUID
    company_id: UUID
    request_id: UUID
    step_id: Optional[UUID]
    actor_id: Optional[UUID]
    action_type: str
    old_status: Optional[str]
    new_status: str
    notes: Optional[str]
    metadata_json: Optional[Dict[str, Any]]
    ip_address: Optional[str]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# ApprovalGroup Schemas
# =============================================================================

class ApprovalGroupBase(BaseModel):
    """Base Schema fuer ApprovalGroup."""
    name: str = Field(..., max_length=255, description="Gruppenname")
    description: Optional[str] = Field(None, description="Beschreibung")
    decision_mode: str = Field(
        default="any",
        pattern="^(any|all|majority)$",
        description="Entscheidungsmodus: any=einer genuegt, all=alle, majority=Mehrheit"
    )


class ApprovalGroupCreate(ApprovalGroupBase):
    """Schema zum Erstellen einer ApprovalGroup."""
    pass


class ApprovalGroupUpdate(BaseModel):
    """Schema zum Aktualisieren einer ApprovalGroup."""
    name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    decision_mode: Optional[str] = Field(None, pattern="^(any|all|majority)$")
    is_active: Optional[bool] = None


class ApprovalGroupMemberAdd(BaseModel):
    """Schema zum Hinzufuegen eines Gruppenmitglieds."""
    user_id: UUID = Field(..., description="User ID")
    can_approve: bool = Field(default=True, description="Kann genehmigen")
    can_reject: bool = Field(default=True, description="Kann ablehnen")
    is_backup: bool = Field(default=False, description="Stellvertreter")


class ApprovalGroupMemberResponse(BaseModel):
    """Schema fuer ApprovalGroupMember Response."""
    id: UUID
    group_id: UUID
    user_id: UUID
    can_approve: bool
    can_reject: bool
    is_backup: bool
    added_at: datetime
    added_by_id: Optional[UUID]

    model_config = ConfigDict(from_attributes=True)


class ApprovalGroupResponse(ApprovalGroupBase):
    """Schema fuer ApprovalGroup Response."""
    id: UUID
    company_id: UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime
    members: List[ApprovalGroupMemberResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# Matrix Lookup Schemas
# =============================================================================

class MatrixLookupRequest(BaseModel):
    """Schema fuer Matrix-Lookup Request."""
    department: str = Field(..., max_length=100, description="Abteilung")
    amount: Decimal = Field(..., description="Betrag")
    document_type: Optional[str] = Field(None, max_length=50, description="Dokumenttyp")


class MatrixLookupResponse(BaseModel):
    """Schema fuer Matrix-Lookup Response."""
    matrix_id: UUID
    chain_template_id: Optional[UUID]
    four_eyes_required: bool
    min_approvers: int
    priority: int
    steps_config: List[ChainStepConfig]

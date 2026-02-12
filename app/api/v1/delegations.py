# -*- coding: utf-8 -*-
"""
Delegations API fuer Ablage-System.

Ermoeglicht temporaere Rechte-Uebertragung:
- Urlaubsvertretung
- Krankheitsvertretung
- Projektbasierte Delegation
- Audit-Trail

Phase 3.2 der Strategischen Roadmap (Januar 2026).
"""

from datetime import datetime
from typing import Optional, List

from app.core.types import JSONDict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db
from app.core.safe_errors import safe_error_detail, safe_error_log
from app.db.models import User
from app.db.models_delegation import (
    DelegationType,
    DelegationStatus,
    DelegationReason,
)
from app.services.delegation_service import DelegationService

router = APIRouter(prefix="/delegations", tags=["Delegations"])


# =============================================================================
# Pydantic Schemas
# =============================================================================


class DelegationCreate(BaseModel):
    """Schema fuer neue Delegation."""
    delegate_id: UUID = Field(..., description="User der die Rechte erhaelt")
    valid_from: datetime = Field(..., description="Startzeitpunkt")
    valid_until: datetime = Field(..., description="Endzeitpunkt")
    delegation_type: DelegationType = Field(
        default=DelegationType.PARTIAL,
        description="Art der Delegation"
    )
    permissions: Optional[List[str]] = Field(
        default=None,
        description="Liste der delegierten Berechtigungen"
    )
    scope: Optional[JSONDict] = Field(
        default=None,
        description="Einschraenkung auf bestimmte Ressourcen"
    )
    reason: DelegationReason = Field(
        default=DelegationReason.OTHER,
        description="Grund fuer die Delegation"
    )
    reason_text: Optional[str] = Field(
        default=None,
        max_length=1000,
        description="Freitext-Begruendung"
    )
    notes: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="Interne Notizen"
    )
    requires_acceptance: bool = Field(
        default=True,
        description="Muss Delegate bestaetigen?"
    )
    notify_on_activation: bool = Field(
        default=True,
        description="Bei Aktivierung benachrichtigen"
    )
    notify_on_expiry: bool = Field(
        default=True,
        description="Bei Ablauf benachrichtigen"
    )
    notify_on_usage: bool = Field(
        default=False,
        description="Bei jeder Nutzung benachrichtigen"
    )
    max_approvals: Optional[int] = Field(
        default=None,
        ge=1,
        description="Max. Anzahl Genehmigungen"
    )
    max_amount: Optional[float] = Field(
        default=None,
        gt=0,
        description="Max. Betrag pro Genehmigung"
    )

    @field_validator("valid_until")
    @classmethod
    def validate_valid_until(cls, v: datetime, info) -> datetime:
        valid_from = info.data.get("valid_from")
        if valid_from and v <= valid_from:
            raise ValueError("Endzeitpunkt muss nach Startzeitpunkt liegen")
        return v


class DelegationFromTemplate(BaseModel):
    """Schema fuer Delegation aus Template."""
    template_id: UUID = Field(..., description="Template-ID")
    delegate_id: UUID = Field(..., description="User der die Rechte erhaelt")
    valid_from: Optional[datetime] = Field(
        default=None,
        description="Startzeitpunkt (default: jetzt)"
    )
    valid_until: Optional[datetime] = Field(
        default=None,
        description="Endzeitpunkt (default: Template-Dauer)"
    )
    reason: DelegationReason = Field(
        default=DelegationReason.OTHER,
        description="Grund fuer die Delegation"
    )
    reason_text: Optional[str] = Field(
        default=None,
        max_length=1000,
        description="Freitext-Begruendung"
    )


class DelegationUpdate(BaseModel):
    """Schema fuer Delegation-Update."""
    permissions: Optional[List[str]] = None
    scope: Optional[JSONDict] = None
    notes: Optional[str] = Field(default=None, max_length=2000)
    notify_on_activation: Optional[bool] = None
    notify_on_expiry: Optional[bool] = None
    notify_on_usage: Optional[bool] = None
    max_approvals: Optional[int] = Field(default=None, ge=1)
    max_amount: Optional[float] = Field(default=None, gt=0)


class DelegationResponse(BaseModel):
    """Response-Schema fuer Delegation."""
    id: UUID
    delegator_id: UUID
    delegator_name: Optional[str] = None
    delegate_id: UUID
    delegate_name: Optional[str] = None
    company_id: UUID
    delegation_type: DelegationType
    permissions: List[str]
    scope: JSONDict
    valid_from: datetime
    valid_until: datetime
    status: DelegationStatus
    reason: DelegationReason
    reason_text: Optional[str]
    notes: Optional[str]
    requires_acceptance: bool
    accepted_at: Optional[datetime]
    declined_at: Optional[datetime]
    decline_reason: Optional[str]
    revoked_at: Optional[datetime]
    revoked_by_id: Optional[UUID]
    revoke_reason: Optional[str]
    notify_on_activation: bool
    notify_on_expiry: bool
    notify_on_usage: bool
    usage_count: int
    last_used_at: Optional[datetime]
    max_approvals: Optional[int]
    max_amount: Optional[float]
    is_active: bool
    is_pending: bool
    days_remaining: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class DelegationListResponse(BaseModel):
    """Response-Schema fuer Delegations-Liste."""
    items: List[DelegationResponse]
    total: int
    limit: int
    offset: int


class DeclineRequest(BaseModel):
    """Request fuer Ablehnung."""
    reason: Optional[str] = Field(
        default=None,
        max_length=1000,
        description="Ablehnungsgrund"
    )


class RevokeRequest(BaseModel):
    """Request fuer Widerruf."""
    reason: Optional[str] = Field(
        default=None,
        max_length=1000,
        description="Widerrufsgrund"
    )


class AuditLogResponse(BaseModel):
    """Response-Schema fuer Audit-Log."""
    id: UUID
    delegation_id: UUID
    action: str
    resource_type: Optional[str]
    resource_id: Optional[UUID]
    resource_name: Optional[str]
    success: bool
    error_message: Optional[str]
    details: JSONDict
    ip_address: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class AuditLogListResponse(BaseModel):
    """Response-Schema fuer Audit-Log-Liste."""
    items: List[AuditLogResponse]
    total: int


class TemplateCreate(BaseModel):
    """Schema fuer neues Template."""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=1000)
    delegation_type: DelegationType
    permissions: Optional[List[str]] = None
    scope: Optional[JSONDict] = None
    default_duration_days: int = Field(default=14, ge=1, le=365)
    requires_acceptance: bool = True
    notify_on_activation: bool = True
    notify_on_usage: bool = False


class TemplateResponse(BaseModel):
    """Response-Schema fuer Template."""
    id: UUID
    company_id: UUID
    name: str
    description: Optional[str]
    delegation_type: DelegationType
    permissions: List[str]
    scope: JSONDict
    default_duration_days: int
    requires_acceptance: bool
    notify_on_activation: bool
    notify_on_usage: bool
    is_active: bool
    is_system: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PermissionCheckRequest(BaseModel):
    """Request fuer Permission-Check."""
    permission: str = Field(..., description="Benoetigte Berechtigung")
    resource_type: Optional[str] = None
    resource_id: Optional[UUID] = None
    amount: Optional[float] = None


class PermissionCheckResponse(BaseModel):
    """Response fuer Permission-Check."""
    allowed: bool
    via_delegation: bool
    delegation_id: Optional[UUID]
    delegator_id: Optional[UUID]
    reason: str


# =============================================================================
# Helper Functions
# =============================================================================


def _delegation_to_response(delegation) -> DelegationResponse:
    """Konvertiert Delegation zu Response."""
    return DelegationResponse(
        id=delegation.id,
        delegator_id=delegation.delegator_id,
        delegator_name=delegation.delegator.full_name if delegation.delegator else None,
        delegate_id=delegation.delegate_id,
        delegate_name=delegation.delegate.full_name if delegation.delegate else None,
        company_id=delegation.company_id,
        delegation_type=delegation.delegation_type,
        permissions=delegation.permissions or [],
        scope=delegation.scope or {},
        valid_from=delegation.valid_from,
        valid_until=delegation.valid_until,
        status=delegation.status,
        reason=delegation.reason,
        reason_text=delegation.reason_text,
        notes=delegation.notes,
        requires_acceptance=delegation.requires_acceptance,
        accepted_at=delegation.accepted_at,
        declined_at=delegation.declined_at,
        decline_reason=delegation.decline_reason,
        revoked_at=delegation.revoked_at,
        revoked_by_id=delegation.revoked_by_id,
        revoke_reason=delegation.revoke_reason,
        notify_on_activation=delegation.notify_on_activation,
        notify_on_expiry=delegation.notify_on_expiry,
        notify_on_usage=delegation.notify_on_usage,
        usage_count=delegation.usage_count or 0,
        last_used_at=delegation.last_used_at,
        max_approvals=delegation.max_approvals,
        max_amount=delegation.max_amount,
        is_active=delegation.is_active,
        is_pending=delegation.is_pending,
        days_remaining=delegation.days_remaining,
        created_at=delegation.created_at,
        updated_at=delegation.updated_at,
    )


# =============================================================================
# Delegation Endpoints
# =============================================================================


@router.post("", response_model=DelegationResponse, status_code=status.HTTP_201_CREATED)
async def create_delegation(
    data: DelegationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DelegationResponse:
    """Erstellt eine neue Delegation.

    Der eingeloggte User wird automatisch als Delegator gesetzt.
    """
    service = DelegationService(db)

    try:
        delegation = await service.create_delegation(
            delegator_id=current_user.id,
            delegate_id=data.delegate_id,
            company_id=current_user.company_id,
            valid_from=data.valid_from,
            valid_until=data.valid_until,
            delegation_type=data.delegation_type,
            permissions=data.permissions,
            scope=data.scope,
            reason=data.reason,
            reason_text=data.reason_text,
            notes=data.notes,
            requires_acceptance=data.requires_acceptance,
            notify_on_activation=data.notify_on_activation,
            notify_on_expiry=data.notify_on_expiry,
            notify_on_usage=data.notify_on_usage,
            max_approvals=data.max_approvals,
            max_amount=data.max_amount,
        )
        await db.commit()

        # Reload mit Relationships
        delegation = await service.get_delegation(delegation.id, current_user.company_id)

        return _delegation_to_response(delegation)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Delegation"),
        )


@router.post("/from-template", response_model=DelegationResponse, status_code=status.HTTP_201_CREATED)
async def create_delegation_from_template(
    data: DelegationFromTemplate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DelegationResponse:
    """Erstellt Delegation aus Template."""
    service = DelegationService(db)

    try:
        delegation = await service.create_from_template(
            template_id=data.template_id,
            delegator_id=current_user.id,
            delegate_id=data.delegate_id,
            company_id=current_user.company_id,
            valid_from=data.valid_from,
            valid_until=data.valid_until,
            reason=data.reason,
            reason_text=data.reason_text,
        )
        await db.commit()

        delegation = await service.get_delegation(delegation.id, current_user.company_id)

        return _delegation_to_response(delegation)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Delegation"),
        )


@router.get("", response_model=DelegationListResponse)
async def list_delegations(
    as_delegator: bool = Query(True, description="Als Delegator anzeigen"),
    as_delegate: bool = Query(True, description="Als Delegate anzeigen"),
    status_filter: Optional[DelegationStatus] = Query(
        None, alias="status", description="Status-Filter"
    ),
    include_expired: bool = Query(False, description="Abgelaufene einbeziehen"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DelegationListResponse:
    """Listet Delegationen des eingeloggten Users auf."""
    service = DelegationService(db)

    delegations = await service.list_delegations(
        company_id=current_user.company_id,
        user_id=current_user.id,
        as_delegator=as_delegator,
        as_delegate=as_delegate,
        status=status_filter,
        include_expired=include_expired,
        limit=limit,
        offset=offset,
    )

    total = await service.count_delegations(
        company_id=current_user.company_id,
        user_id=current_user.id,
        status=status_filter,
    )

    return DelegationListResponse(
        items=[_delegation_to_response(d) for d in delegations],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/pending", response_model=List[DelegationResponse])
async def get_pending_delegations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[DelegationResponse]:
    """Holt ausstehende Delegationen die auf Bestaetigung warten."""
    service = DelegationService(db)

    delegations = await service.get_pending_delegations_for_user(
        user_id=current_user.id,
        company_id=current_user.company_id,
    )

    return [_delegation_to_response(d) for d in delegations]


@router.get("/active", response_model=List[DelegationResponse])
async def get_active_delegations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[DelegationResponse]:
    """Holt aktive Delegationen des Users (als Delegate)."""
    service = DelegationService(db)

    delegations = await service.get_active_delegations_for_user(
        user_id=current_user.id,
        company_id=current_user.company_id,
    )

    return [_delegation_to_response(d) for d in delegations]


@router.get("/{delegation_id}", response_model=DelegationResponse)
async def get_delegation(
    delegation_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DelegationResponse:
    """Holt eine spezifische Delegation."""
    service = DelegationService(db)

    delegation = await service.get_delegation(delegation_id, current_user.company_id)
    if not delegation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Delegation nicht gefunden",
        )

    # Nur Delegator, Delegate oder Admin darf sehen
    if (
        delegation.delegator_id != current_user.id
        and delegation.delegate_id != current_user.id
        and current_user.role != "admin"
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keine Berechtigung fuer diese Delegation",
        )

    return _delegation_to_response(delegation)


@router.patch("/{delegation_id}", response_model=DelegationResponse)
async def update_delegation(
    delegation_id: UUID,
    data: DelegationUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DelegationResponse:
    """Aktualisiert eine Delegation.

    Nur der Delegator kann aktualisieren.
    """
    service = DelegationService(db)

    delegation = await service.get_delegation(delegation_id, current_user.company_id)
    if not delegation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Delegation nicht gefunden",
        )

    if delegation.delegator_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nur der Delegator kann die Delegation aktualisieren",
        )

    updates = data.model_dump(exclude_unset=True)
    delegation = await service.update_delegation(
        delegation_id=delegation_id,
        company_id=current_user.company_id,
        **updates,
    )
    await db.commit()

    delegation = await service.get_delegation(delegation_id, current_user.company_id)

    return _delegation_to_response(delegation)


@router.post("/{delegation_id}/accept", response_model=DelegationResponse)
async def accept_delegation(
    delegation_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DelegationResponse:
    """Delegate akzeptiert eine Delegation."""
    service = DelegationService(db)

    try:
        delegation = await service.accept_delegation(
            delegation_id=delegation_id,
            delegate_id=current_user.id,
            company_id=current_user.company_id,
        )
        await db.commit()

        delegation = await service.get_delegation(delegation_id, current_user.company_id)

        return _delegation_to_response(delegation)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Delegation"),
        )


@router.post("/{delegation_id}/decline", response_model=DelegationResponse)
async def decline_delegation(
    delegation_id: UUID,
    data: DeclineRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DelegationResponse:
    """Delegate lehnt eine Delegation ab."""
    service = DelegationService(db)

    try:
        delegation = await service.decline_delegation(
            delegation_id=delegation_id,
            delegate_id=current_user.id,
            company_id=current_user.company_id,
            reason=data.reason,
        )
        await db.commit()

        delegation = await service.get_delegation(delegation_id, current_user.company_id)

        return _delegation_to_response(delegation)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Delegation"),
        )


@router.post("/{delegation_id}/revoke", response_model=DelegationResponse)
async def revoke_delegation(
    delegation_id: UUID,
    data: RevokeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DelegationResponse:
    """Widerruft eine Delegation.

    Kann vom Delegator oder Admin widerrufen werden.
    """
    service = DelegationService(db)

    delegation = await service.get_delegation(delegation_id, current_user.company_id)
    if not delegation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Delegation nicht gefunden",
        )

    # Nur Delegator oder Admin darf widerrufen
    if delegation.delegator_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nur der Delegator oder Admin kann die Delegation widerrufen",
        )

    try:
        delegation = await service.revoke_delegation(
            delegation_id=delegation_id,
            revoked_by_id=current_user.id,
            company_id=current_user.company_id,
            reason=data.reason,
        )
        await db.commit()

        delegation = await service.get_delegation(delegation_id, current_user.company_id)

        return _delegation_to_response(delegation)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Delegation"),
        )


# =============================================================================
# Audit Log Endpoints
# =============================================================================


@router.get("/{delegation_id}/audit-logs", response_model=AuditLogListResponse)
async def get_delegation_audit_logs(
    delegation_id: UUID,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AuditLogListResponse:
    """Holt Audit-Logs einer Delegation."""
    service = DelegationService(db)

    delegation = await service.get_delegation(delegation_id, current_user.company_id)
    if not delegation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Delegation nicht gefunden",
        )

    # Nur Delegator, Delegate oder Admin darf sehen
    if (
        delegation.delegator_id != current_user.id
        and delegation.delegate_id != current_user.id
        and current_user.role != "admin"
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keine Berechtigung fuer Audit-Logs",
        )

    logs = await service.get_audit_logs(
        delegation_id=delegation_id,
        company_id=current_user.company_id,
        limit=limit,
        offset=offset,
    )

    return AuditLogListResponse(
        items=[
            AuditLogResponse(
                id=log.id,
                delegation_id=log.delegation_id,
                action=log.action,
                resource_type=log.resource_type,
                resource_id=log.resource_id,
                resource_name=log.resource_name,
                success=log.success,
                error_message=log.error_message,
                details=log.details or {},
                ip_address=log.ip_address,
                created_at=log.created_at,
            )
            for log in logs
        ],
        total=len(logs),  # Simplified, could add proper count
    )


# =============================================================================
# Permission Check Endpoint
# =============================================================================


@router.post("/check-permission", response_model=PermissionCheckResponse)
async def check_permission_with_delegation(
    data: PermissionCheckRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PermissionCheckResponse:
    """Prueft Berechtigung unter Beruecksichtigung von Delegationen.

    Nützlich fuer Frontend um zu pruefen ob User via Delegation berechtigt ist.
    """
    service = DelegationService(db)

    request_info = {
        "ip_address": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
    }

    result = await service.check_permission_with_delegation(
        user_id=current_user.id,
        company_id=current_user.company_id,
        permission=data.permission,
        resource_type=data.resource_type,
        resource_id=data.resource_id,
        amount=data.amount,
        request_info=request_info,
    )

    if result.get("via_delegation"):
        await db.commit()  # Commit audit log

    return PermissionCheckResponse(
        allowed=result["allowed"],
        via_delegation=result["via_delegation"],
        delegation_id=result.get("delegation_id"),
        delegator_id=result.get("delegator_id"),
        reason=result["reason"],
    )


# =============================================================================
# Template Endpoints
# =============================================================================


@router.get("/templates", response_model=List[TemplateResponse])
async def list_templates(
    include_inactive: bool = Query(False, description="Inaktive einbeziehen"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[TemplateResponse]:
    """Listet verfuegbare Delegations-Templates."""
    service = DelegationService(db)

    templates = await service.list_templates(
        company_id=current_user.company_id,
        include_inactive=include_inactive,
    )

    return [
        TemplateResponse(
            id=t.id,
            company_id=t.company_id,
            name=t.name,
            description=t.description,
            delegation_type=t.delegation_type,
            permissions=t.permissions or [],
            scope=t.scope or {},
            default_duration_days=t.default_duration_days,
            requires_acceptance=t.requires_acceptance,
            notify_on_activation=t.notify_on_activation,
            notify_on_usage=t.notify_on_usage,
            is_active=t.is_active,
            is_system=t.is_system,
            created_at=t.created_at,
            updated_at=t.updated_at,
        )
        for t in templates
    ]


@router.post("/templates", response_model=TemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_template(
    data: TemplateCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TemplateResponse:
    """Erstellt ein neues Delegations-Template.

    Nur Admins koennen Templates erstellen.
    """
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nur Admins koennen Templates erstellen",
        )

    service = DelegationService(db)

    template = await service.create_template(
        company_id=current_user.company_id,
        name=data.name,
        description=data.description,
        delegation_type=data.delegation_type,
        permissions=data.permissions,
        scope=data.scope,
        default_duration_days=data.default_duration_days,
        requires_acceptance=data.requires_acceptance,
        notify_on_activation=data.notify_on_activation,
        notify_on_usage=data.notify_on_usage,
    )
    await db.commit()

    return TemplateResponse(
        id=template.id,
        company_id=template.company_id,
        name=template.name,
        description=template.description,
        delegation_type=template.delegation_type,
        permissions=template.permissions or [],
        scope=template.scope or {},
        default_duration_days=template.default_duration_days,
        requires_acceptance=template.requires_acceptance,
        notify_on_activation=template.notify_on_activation,
        notify_on_usage=template.notify_on_usage,
        is_active=template.is_active,
        is_system=template.is_system,
        created_at=template.created_at,
        updated_at=template.updated_at,
    )

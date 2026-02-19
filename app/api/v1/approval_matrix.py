"""Approval Matrix API - Genehmigungsmatrix Verwaltung.

REST API fuer Approval Matrix:
- Matrix CRUD (Betrags-/Abteilungsbasierte Genehmigungen)
- Chain Templates CRUD
- Audit Trail
- Groups & Members
- Matrix Lookup
"""

from typing import Optional, List
from uuid import UUID
from decimal import Decimal

import structlog
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.api.dependencies import get_db, get_current_active_user
from app.core.rate_limiting import limiter, get_user_identifier
from app.api.schemas.approval_matrix import (
    ApprovalMatrixCreate,
    ApprovalMatrixUpdate,
    ApprovalMatrixResponse,
    ApprovalChainTemplateCreate,
    ApprovalChainTemplateUpdate,
    ApprovalChainTemplateResponse,
    ApprovalAuditLogResponse,
    ApprovalGroupCreate,
    ApprovalGroupUpdate,
    ApprovalGroupResponse,
    ApprovalGroupMemberAdd,
    ApprovalGroupMemberResponse,
    MatrixLookupRequest,
    MatrixLookupResponse,
    ChainStepConfig,
)
from app.services.approval.approval_matrix_service import ApprovalMatrixService
from app.services.approval.approval_audit_service import ApprovalAuditService
from app.db.models_approval_matrix import (
    ApprovalMatrix,
    ApprovalChainTemplate,
    ApprovalGroup,
    ApprovalGroupMember,
)
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/approval-matrix", tags=["Genehmigungsmatrix"])


# =============================================================================
# Matrix CRUD
# =============================================================================

@router.get(
    "/matrices",
    response_model=List[ApprovalMatrixResponse],
    summary="Matrix-Eintraege auflisten",
    description="Listet alle Genehmigungsmatrix-Eintraege fuer die Firma auf"
)
@limiter.limit("30/minute", key_func=get_user_identifier)
async def list_matrices(
    request: Request,
    department: Optional[str] = Query(None, description="Nach Abteilung filtern"),
    active_only: bool = Query(True, description="Nur aktive Eintraege"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> List[ApprovalMatrixResponse]:
    """Listet Matrix-Eintraege auf."""
    if not current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer hat keine Firma zugewiesen"
        )

    service = ApprovalMatrixService(db)
    matrices = await service.list_matrix_entries(
        company_id=current_user.company_id,
        department=department,
        active_only=active_only,
    )

    return [ApprovalMatrixResponse.model_validate(m) for m in matrices]


@router.post(
    "/matrices",
    response_model=ApprovalMatrixResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Matrix-Eintrag erstellen",
    description="Erstellt einen neuen Matrix-Eintrag"
)
@limiter.limit("10/minute", key_func=get_user_identifier)
async def create_matrix(
    request: Request,
    data: ApprovalMatrixCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> ApprovalMatrixResponse:
    """Erstellt einen Matrix-Eintrag."""
    if not current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer hat keine Firma zugewiesen"
        )

    service = ApprovalMatrixService(db)
    matrix = await service.create_matrix_entry(
        company_id=current_user.company_id,
        department=data.department,
        amount_min=data.amount_min,
        amount_max=data.amount_max,
        chain_template_id=data.chain_template_id,
        created_by_id=current_user.id,
        document_type=data.document_type,
        four_eyes_required=data.four_eyes_required,
        min_approvers=data.min_approvers,
        priority=data.priority,
    )

    return ApprovalMatrixResponse.model_validate(matrix)


@router.put(
    "/matrices/{matrix_id}",
    response_model=ApprovalMatrixResponse,
    summary="Matrix-Eintrag aktualisieren",
    description="Aktualisiert einen vorhandenen Matrix-Eintrag"
)
@limiter.limit("10/minute", key_func=get_user_identifier)
async def update_matrix(
    request: Request,
    matrix_id: UUID,
    data: ApprovalMatrixUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> ApprovalMatrixResponse:
    """Aktualisiert einen Matrix-Eintrag."""
    if not current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer hat keine Firma zugewiesen"
        )

    # Security: Check ownership
    query = select(ApprovalMatrix).where(
        and_(
            ApprovalMatrix.id == matrix_id,
            ApprovalMatrix.company_id == current_user.company_id,
        )
    )
    result = await db.execute(query)
    existing = result.scalar_one_or_none()

    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Matrix-Eintrag nicht gefunden"
        )

    service = ApprovalMatrixService(db)
    updates = data.model_dump(exclude_unset=True)
    matrix = await service.update_matrix_entry(matrix_id, **updates)

    if not matrix:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Matrix-Eintrag nicht gefunden"
        )

    return ApprovalMatrixResponse.model_validate(matrix)


@router.delete(
    "/matrices/{matrix_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Matrix-Eintrag loeschen",
    description="Deaktiviert einen Matrix-Eintrag (Soft Delete)"
)
@limiter.limit("10/minute", key_func=get_user_identifier)
async def delete_matrix(
    request: Request,
    matrix_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Deaktiviert einen Matrix-Eintrag."""
    if not current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer hat keine Firma zugewiesen"
        )

    # Security: Check ownership
    query = select(ApprovalMatrix).where(
        and_(
            ApprovalMatrix.id == matrix_id,
            ApprovalMatrix.company_id == current_user.company_id,
        )
    )
    result = await db.execute(query)
    existing = result.scalar_one_or_none()

    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Matrix-Eintrag nicht gefunden"
        )

    service = ApprovalMatrixService(db)
    success = await service.delete_matrix_entry(matrix_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Matrix-Eintrag nicht gefunden"
        )


# =============================================================================
# Chain Templates CRUD
# =============================================================================

@router.get(
    "/chain-templates",
    response_model=List[ApprovalChainTemplateResponse],
    summary="Chain Templates auflisten",
    description="Listet alle Chain Templates fuer die Firma auf"
)
@limiter.limit("30/minute", key_func=get_user_identifier)
async def list_chain_templates(
    request: Request,
    active_only: bool = Query(True, description="Nur aktive Templates"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> List[ApprovalChainTemplateResponse]:
    """Listet Chain Templates auf."""
    if not current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer hat keine Firma zugewiesen"
        )

    service = ApprovalMatrixService(db)
    templates = await service.list_chain_templates(
        company_id=current_user.company_id,
        active_only=active_only,
    )

    return [ApprovalChainTemplateResponse.model_validate(t) for t in templates]


@router.post(
    "/chain-templates",
    response_model=ApprovalChainTemplateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Chain Template erstellen",
    description="Erstellt eine neue Chain Template"
)
@limiter.limit("10/minute", key_func=get_user_identifier)
async def create_chain_template(
    request: Request,
    data: ApprovalChainTemplateCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> ApprovalChainTemplateResponse:
    """Erstellt eine Chain Template."""
    if not current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer hat keine Firma zugewiesen"
        )

    service = ApprovalMatrixService(db)

    # Convert Pydantic models to dicts for JSONB storage
    steps_config = [step.model_dump() for step in data.steps_config]

    template = await service.create_chain_template(
        company_id=current_user.company_id,
        name=data.name,
        steps_config=steps_config,
        created_by_id=current_user.id,
        description=data.description,
        is_default=data.is_default,
    )

    return ApprovalChainTemplateResponse.model_validate(template)


@router.put(
    "/chain-templates/{template_id}",
    response_model=ApprovalChainTemplateResponse,
    summary="Chain Template aktualisieren",
    description="Aktualisiert eine vorhandene Chain Template"
)
@limiter.limit("10/minute", key_func=get_user_identifier)
async def update_chain_template(
    request: Request,
    template_id: UUID,
    data: ApprovalChainTemplateUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> ApprovalChainTemplateResponse:
    """Aktualisiert eine Chain Template."""
    if not current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer hat keine Firma zugewiesen"
        )

    # Security: Check ownership
    query = select(ApprovalChainTemplate).where(
        and_(
            ApprovalChainTemplate.id == template_id,
            ApprovalChainTemplate.company_id == current_user.company_id,
        )
    )
    result = await db.execute(query)
    template = result.scalar_one_or_none()

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chain Template nicht gefunden"
        )

    # Apply updates
    updates = data.model_dump(exclude_unset=True)

    for key, value in updates.items():
        if hasattr(template, key):
            setattr(template, key, value)

    await db.commit()
    await db.refresh(template)

    return ApprovalChainTemplateResponse.model_validate(template)


@router.delete(
    "/chain-templates/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Chain Template loeschen",
    description="Deaktiviert eine Chain Template (Soft Delete)"
)
@limiter.limit("10/minute", key_func=get_user_identifier)
async def delete_chain_template(
    request: Request,
    template_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Deaktiviert eine Chain Template."""
    if not current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer hat keine Firma zugewiesen"
        )

    # Security: Check ownership
    query = select(ApprovalChainTemplate).where(
        and_(
            ApprovalChainTemplate.id == template_id,
            ApprovalChainTemplate.company_id == current_user.company_id,
        )
    )
    result = await db.execute(query)
    template = result.scalar_one_or_none()

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chain Template nicht gefunden"
        )

    template.is_active = False
    await db.commit()


# =============================================================================
# Audit Trail
# =============================================================================

@router.get(
    "/audit-trail/{request_id}",
    response_model=List[ApprovalAuditLogResponse],
    summary="Audit Trail abrufen",
    description="Ruft den vollstaendigen Audit Trail fuer eine Genehmigung ab"
)
@limiter.limit("30/minute", key_func=get_user_identifier)
async def get_audit_trail(
    request: Request,
    request_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> List[ApprovalAuditLogResponse]:
    """Ruft Audit Trail ab."""
    if not current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer hat keine Firma zugewiesen"
        )

    # Security: Check request belongs to company
    from app.db.models import ApprovalRequest
    query = select(ApprovalRequest).where(
        and_(
            ApprovalRequest.id == request_id,
            ApprovalRequest.company_id == current_user.company_id,
        )
    )
    result = await db.execute(query)
    approval_request = result.scalar_one_or_none()

    if not approval_request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Genehmigungsanfrage nicht gefunden"
        )

    service = ApprovalAuditService(db)
    audit_entries = await service.get_audit_trail(request_id)

    return [
        ApprovalAuditLogResponse(
            id=entry.id,
            company_id=current_user.company_id,
            request_id=entry.request_id,
            step_id=entry.step_id,
            actor_id=entry.actor_id,
            action_type=entry.action_type,
            old_status=entry.old_status,
            new_status=entry.new_status,
            notes=entry.notes,
            metadata_json=None,
            ip_address=entry.ip_address,
            created_at=entry.created_at,
        )
        for entry in audit_entries
    ]


# =============================================================================
# Groups CRUD
# =============================================================================

@router.get(
    "/groups",
    response_model=List[ApprovalGroupResponse],
    summary="Gruppen auflisten",
    description="Listet alle Genehmigungsgruppen fuer die Firma auf"
)
@limiter.limit("30/minute", key_func=get_user_identifier)
async def list_groups(
    request: Request,
    active_only: bool = Query(True, description="Nur aktive Gruppen"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> List[ApprovalGroupResponse]:
    """Listet Genehmigungsgruppen auf."""
    if not current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer hat keine Firma zugewiesen"
        )

    conditions = [ApprovalGroup.company_id == current_user.company_id]
    if active_only:
        conditions.append(ApprovalGroup.is_active.is_(True))

    query = (
        select(ApprovalGroup)
        .options(selectinload(ApprovalGroup.members))
        .where(and_(*conditions))
        .order_by(ApprovalGroup.name)
    )
    result = await db.execute(query)
    groups = result.scalars().all()

    return [ApprovalGroupResponse.model_validate(g) for g in groups]


@router.post(
    "/groups",
    response_model=ApprovalGroupResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Gruppe erstellen",
    description="Erstellt eine neue Genehmigungsgruppe"
)
@limiter.limit("10/minute", key_func=get_user_identifier)
async def create_group(
    request: Request,
    data: ApprovalGroupCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> ApprovalGroupResponse:
    """Erstellt eine Genehmigungsgruppe."""
    if not current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer hat keine Firma zugewiesen"
        )

    group = ApprovalGroup(
        company_id=current_user.company_id,
        name=data.name,
        description=data.description,
        decision_mode=data.decision_mode,
    )
    db.add(group)
    await db.commit()
    await db.refresh(group)

    return ApprovalGroupResponse.model_validate(group)


@router.post(
    "/groups/{group_id}/members",
    response_model=ApprovalGroupMemberResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Gruppenmitglied hinzufuegen",
    description="Fuegt ein Mitglied zur Gruppe hinzu"
)
@limiter.limit("10/minute", key_func=get_user_identifier)
async def add_group_member(
    request: Request,
    group_id: UUID,
    data: ApprovalGroupMemberAdd,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> ApprovalGroupMemberResponse:
    """Fuegt Gruppenmitglied hinzu."""
    if not current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer hat keine Firma zugewiesen"
        )

    # Security: Check group ownership
    query = select(ApprovalGroup).where(
        and_(
            ApprovalGroup.id == group_id,
            ApprovalGroup.company_id == current_user.company_id,
        )
    )
    result = await db.execute(query)
    group = result.scalar_one_or_none()

    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Gruppe nicht gefunden"
        )

    member = ApprovalGroupMember(
        group_id=group_id,
        user_id=data.user_id,
        can_approve=data.can_approve,
        can_reject=data.can_reject,
        is_backup=data.is_backup,
        added_by_id=current_user.id,
    )
    db.add(member)
    await db.commit()
    await db.refresh(member)

    return ApprovalGroupMemberResponse.model_validate(member)


@router.delete(
    "/groups/{group_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Gruppenmitglied entfernen",
    description="Entfernt ein Mitglied aus der Gruppe"
)
@limiter.limit("10/minute", key_func=get_user_identifier)
async def remove_group_member(
    request: Request,
    group_id: UUID,
    user_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Entfernt Gruppenmitglied."""
    if not current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer hat keine Firma zugewiesen"
        )

    # Security: Check group ownership
    query_group = select(ApprovalGroup).where(
        and_(
            ApprovalGroup.id == group_id,
            ApprovalGroup.company_id == current_user.company_id,
        )
    )
    result_group = await db.execute(query_group)
    group = result_group.scalar_one_or_none()

    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Gruppe nicht gefunden"
        )

    # Delete member
    query_member = select(ApprovalGroupMember).where(
        and_(
            ApprovalGroupMember.group_id == group_id,
            ApprovalGroupMember.user_id == user_id,
        )
    )
    result_member = await db.execute(query_member)
    member = result_member.scalar_one_or_none()

    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Gruppenmitglied nicht gefunden"
        )

    await db.delete(member)
    await db.commit()


# =============================================================================
# Matrix Lookup
# =============================================================================

@router.post(
    "/lookup",
    response_model=MatrixLookupResponse,
    summary="Matrix Lookup",
    description="Findet den passenden Matrix-Eintrag fuer eine Genehmigung"
)
@limiter.limit("30/minute", key_func=get_user_identifier)
async def lookup_matrix(
    request: Request,
    data: MatrixLookupRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> MatrixLookupResponse:
    """Findet passenden Matrix-Eintrag."""
    if not current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer hat keine Firma zugewiesen"
        )

    service = ApprovalMatrixService(db)
    match = await service.find_matching_matrix(
        company_id=current_user.company_id,
        department=data.department,
        amount=data.amount,
        document_type=data.document_type,
    )

    if not match:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kein passender Matrix-Eintrag gefunden"
        )

    # Convert steps_config dicts to Pydantic models
    steps_config = [ChainStepConfig(**step) for step in match.steps_config]

    return MatrixLookupResponse(
        matrix_id=match.matrix_id,
        chain_template_id=match.chain_template_id,
        four_eyes_required=match.four_eyes_required,
        min_approvers=match.min_approvers,
        priority=match.priority,
        steps_config=steps_config,
    )

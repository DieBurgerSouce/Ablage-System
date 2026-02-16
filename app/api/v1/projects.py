"""
Project Management API Endpoints - Vision 2026

Endpoints for managing projects including:
- CRUD operations for projects
- Team member management
- Document assignment
- Project statistics
- KI-basierte Auto-Zuweisung
"""

from datetime import date
from decimal import Decimal
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Path, status
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db, get_current_active_user
from app.middleware.company_context import require_company
from app.services.project_service import ProjectService, project_service
from app.db.models import User, Company
from app.db.models_project import (
    Project,
    ProjectMember,
    DocumentProjectAssignment,
    ProjectStatus,
    ProjectPriority,
    ProjectMemberRole,
    DocumentAssignmentType,
)
from app.core.safe_errors import safe_error_detail, safe_error_log

import structlog

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/projects", tags=["Projects"])


# =============================================================================
# Pydantic Schemas
# =============================================================================


class ProjectCreate(BaseModel):
    """Schema für Projekt-Erstellung."""
    code: str = Field(..., min_length=1, max_length=50, description="Eindeutiger Projekt-Code")
    name: str = Field(..., min_length=1, max_length=255, description="Projektname")
    description: Optional[str] = Field(None, description="Projektbeschreibung")
    client_id: Optional[UUID] = Field(None, description="Kunden-ID (BusinessEntity)")
    start_date: Optional[date] = Field(None, description="Geplanter Starttermin")
    end_date: Optional[date] = Field(None, description="Geplanter Endtermin")
    budget: Optional[Decimal] = Field(None, ge=0, description="Budget")
    currency: str = Field("EUR", max_length=3, description="Währung")
    kostenstelle_id: Optional[UUID] = Field(None, description="Kostenstellen-ID")
    manager_id: Optional[UUID] = Field(None, description="Projektleiter-ID")
    priority: str = Field(ProjectPriority.MEDIUM.value, description="Prioritaet")
    category: Optional[str] = Field(None, max_length=100, description="Kategorie")
    tags: List[str] = Field(default_factory=list, description="Tags")


class ProjectUpdate(BaseModel):
    """Schema für Projekt-Update."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    client_id: Optional[UUID] = None
    status: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    actual_start_date: Optional[date] = None
    actual_end_date: Optional[date] = None
    budget: Optional[Decimal] = Field(None, ge=0)
    budget_spent: Optional[Decimal] = Field(None, ge=0)
    currency: Optional[str] = Field(None, max_length=3)
    kostenstelle_id: Optional[UUID] = None
    manager_id: Optional[UUID] = None
    priority: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None


class ProjectResponse(BaseModel):
    """Schema für Projekt-Antwort."""
    id: UUID
    code: str
    name: str
    description: Optional[str]
    client_id: Optional[UUID]
    client_name: Optional[str] = None
    status: str
    start_date: Optional[date]
    end_date: Optional[date]
    actual_start_date: Optional[date]
    actual_end_date: Optional[date]
    budget: Optional[Decimal]
    budget_spent: Decimal
    currency: str
    kostenstelle_id: Optional[UUID]
    kostenstelle_name: Optional[str] = None
    manager_id: Optional[UUID]
    manager_name: Optional[str] = None
    priority: Optional[str]
    category: Optional[str]
    document_count: int
    invoice_count: int
    total_invoiced: Optional[Decimal]
    tags: List[str]
    is_overdue: bool
    budget_utilization: Optional[float]
    created_at: str
    updated_at: str

    model_config = ConfigDict(from_attributes=True)


class ProjectListResponse(BaseModel):
    """Schema für Projekt-Liste."""
    items: List[ProjectResponse]
    total: int
    limit: int
    offset: int


class MemberCreate(BaseModel):
    """Schema für Mitglied-Hinzufuegung."""
    user_id: UUID = Field(..., description="Benutzer-ID")
    role: str = Field(ProjectMemberRole.MEMBER.value, description="Rolle")
    permissions: List[str] = Field(default_factory=list, description="Zusätzliche Berechtigungen")
    valid_from: Optional[date] = Field(None, description="Gültig ab")
    valid_until: Optional[date] = Field(None, description="Gültig bis")
    allocation_percent: Optional[int] = Field(None, ge=0, le=100, description="Allokation in Prozent")


class MemberResponse(BaseModel):
    """Schema für Mitglied-Antwort."""
    id: UUID
    project_id: UUID
    user_id: UUID
    user_name: Optional[str] = None
    user_email: Optional[str] = None
    role: str
    permissions: List[str]
    valid_from: Optional[date]
    valid_until: Optional[date]
    allocation_percent: Optional[int]
    is_active: bool
    is_currently_valid: bool
    created_at: str

    model_config = ConfigDict(from_attributes=True)


class DocumentAssignRequest(BaseModel):
    """Schema für Dokument-Zuweisung."""
    document_id: UUID = Field(..., description="Dokument-ID")
    assignment_type: str = Field(DocumentAssignmentType.GENERAL.value, description="Zuweisungstyp")


class DocumentAssignmentResponse(BaseModel):
    """Schema für Dokument-Zuweisungs-Antwort."""
    id: UUID
    document_id: UUID
    document_filename: Optional[str] = None
    project_id: UUID
    assignment_type: str
    auto_assigned: bool
    confidence: Optional[float]
    assignment_reason: Optional[str]
    assigned_by_id: Optional[UUID]
    assigned_at: str

    model_config = ConfigDict(from_attributes=True)


class AutoAssignSuggestion(BaseModel):
    """Schema für Auto-Zuweisungs-Vorschlag."""
    project_id: UUID
    project_code: str
    project_name: str
    confidence: float
    assignment_reason: str
    assignment_type: str


class ProjectSummaryResponse(BaseModel):
    """Schema für Projekt-Zusammenfassung."""
    total_projects: int
    active_projects: int
    completed_projects: int
    on_hold_projects: int
    total_budget: Decimal
    total_spent: Decimal
    overdue_count: int


class ProjectDocumentStatsResponse(BaseModel):
    """Schema für Dokumenten-Statistiken."""
    total_documents: int
    invoices: int
    contracts: int
    correspondence: int
    other: int
    auto_assigned: int
    manual_assigned: int


# =============================================================================
# Helper Functions
# =============================================================================


def _project_to_response(project: Project) -> ProjectResponse:
    """Convert a project model to a response schema."""
    return ProjectResponse(
        id=project.id,
        code=project.code,
        name=project.name,
        description=project.description,
        client_id=project.client_id,
        client_name=project.client.name if project.client else None,
        status=project.status,
        start_date=project.start_date,
        end_date=project.end_date,
        actual_start_date=project.actual_start_date,
        actual_end_date=project.actual_end_date,
        budget=project.budget,
        budget_spent=project.budget_spent,
        currency=project.currency,
        kostenstelle_id=project.kostenstelle_id,
        kostenstelle_name=project.kostenstelle.name if project.kostenstelle else None,
        manager_id=project.manager_id,
        manager_name=f"{project.manager.first_name} {project.manager.last_name}" if project.manager else None,
        priority=project.priority,
        category=project.category,
        document_count=project.document_count,
        invoice_count=project.invoice_count,
        total_invoiced=project.total_invoiced,
        tags=project.tags,
        is_overdue=project.is_overdue,
        budget_utilization=project.budget_utilization,
        created_at=project.created_at.isoformat(),
        updated_at=project.updated_at.isoformat(),
    )


def _member_to_response(member: ProjectMember) -> MemberResponse:
    """Convert a member model to a response schema."""
    return MemberResponse(
        id=member.id,
        project_id=member.project_id,
        user_id=member.user_id,
        user_name=f"{member.user.first_name} {member.user.last_name}" if member.user else None,
        user_email=member.user.email if member.user else None,
        role=member.role,
        permissions=member.permissions,
        valid_from=member.valid_from,
        valid_until=member.valid_until,
        allocation_percent=member.allocation_percent,
        is_active=member.is_active,
        is_currently_valid=member.is_currently_valid,
        created_at=member.created_at.isoformat(),
    )


def _assignment_to_response(assignment: DocumentProjectAssignment) -> DocumentAssignmentResponse:
    """Convert an assignment model to a response schema."""
    return DocumentAssignmentResponse(
        id=assignment.id,
        document_id=assignment.document_id,
        document_filename=assignment.document.original_filename if assignment.document else None,
        project_id=assignment.project_id,
        assignment_type=assignment.assignment_type,
        auto_assigned=assignment.auto_assigned,
        confidence=assignment.confidence,
        assignment_reason=assignment.assignment_reason,
        assigned_by_id=assignment.assigned_by_id,
        assigned_at=assignment.assigned_at.isoformat(),
    )


# =============================================================================
# CRUD Endpoints
# =============================================================================


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    request: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> ProjectResponse:
    """Neues Projekt erstellen."""
    logger.info(
        "Erstelle Projekt",
        code=request.code,
        name=request.name,
        user_id=str(current_user.id)
    )

    try:
        project = await project_service.create_project(
            db,
            company_id=company.id,
            code=request.code,
            name=request.name,
            description=request.description,
            client_id=request.client_id,
            start_date=request.start_date,
            end_date=request.end_date,
            budget=request.budget,
            currency=request.currency,
            kostenstelle_id=request.kostenstelle_id,
            manager_id=request.manager_id,
            priority=request.priority,
            category=request.category,
            tags=request.tags,
            created_by_id=current_user.id,
        )
        await db.commit()
        return _project_to_response(project)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=safe_error_detail(e, "Projekt"))


@router.get("", response_model=ProjectListResponse)
async def list_projects(
    status: Optional[str] = Query(None, description="Status-Filter"),
    client_id: Optional[UUID] = Query(None, description="Kunden-Filter"),
    manager_id: Optional[UUID] = Query(None, description="Manager-Filter"),
    kostenstelle_id: Optional[UUID] = Query(None, description="Kostenstellen-Filter"),
    search: Optional[str] = Query(None, description="Suchbegriff"),
    include_archived: bool = Query(False, description="Archivierte einbeziehen"),
    sort_by: str = Query("created_at", description="Sortierfeld"),
    sort_order: str = Query("desc", description="Sortierrichtung"),
    limit: int = Query(50, ge=1, le=100, description="Limit"),
    offset: int = Query(0, ge=0, description="Offset"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> ProjectListResponse:
    """Projekte auflisten mit Filterung und Paginierung."""
    projects, total = await project_service.list_projects(
        db,
        company_id=company.id,
        status=status,
        client_id=client_id,
        manager_id=manager_id,
        kostenstelle_id=kostenstelle_id,
        search=search,
        include_archived=include_archived,
        sort_by=sort_by,
        sort_order=sort_order,
        limit=limit,
        offset=offset,
    )

    return ProjectListResponse(
        items=[_project_to_response(p) for p in projects],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/summary", response_model=ProjectSummaryResponse)
async def get_project_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> ProjectSummaryResponse:
    """Projekt-Zusammenfassung für Company."""
    summary = await project_service.get_project_summary(db, company.id)
    return ProjectSummaryResponse(
        total_projects=summary.total_projects,
        active_projects=summary.active_projects,
        completed_projects=summary.completed_projects,
        on_hold_projects=summary.on_hold_projects,
        total_budget=summary.total_budget,
        total_spent=summary.total_spent,
        overdue_count=summary.overdue_count,
    )


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> ProjectResponse:
    """Projekt anhand ID abrufen."""
    project = await project_service.get_project(db, project_id)

    if not project or project.company_id != company.id:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden")

    return _project_to_response(project)


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: UUID,
    request: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> ProjectResponse:
    """Projekt aktualisieren."""
    # Verify access
    existing = await project_service.get_project(db, project_id)
    if not existing or existing.company_id != company.id:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden")

    update_data = request.model_dump(exclude_unset=True)
    project = await project_service.update_project(db, project_id, **update_data)
    await db.commit()

    return _project_to_response(project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_project(
    project_id: UUID,
    hard_delete: bool = Query(False, description="Endgültig löschen statt archivieren"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
):
    """Projekt löschen (archivieren)."""
    existing = await project_service.get_project(db, project_id)
    if not existing or existing.company_id != company.id:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden")

    success = await project_service.delete_project(
        db, project_id, soft_delete=not hard_delete
    )
    if not success:
        raise HTTPException(status_code=500, detail="Projekt konnte nicht gelöscht werden")

    await db.commit()


# =============================================================================
# Status Management
# =============================================================================


@router.post("/{project_id}/activate", response_model=ProjectResponse)
async def activate_project(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> ProjectResponse:
    """Projekt aktivieren."""
    existing = await project_service.get_project(db, project_id)
    if not existing or existing.company_id != company.id:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden")

    project = await project_service.activate_project(db, project_id)
    await db.commit()

    return _project_to_response(project)


@router.post("/{project_id}/complete", response_model=ProjectResponse)
async def complete_project(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> ProjectResponse:
    """Projekt abschließen."""
    existing = await project_service.get_project(db, project_id)
    if not existing or existing.company_id != company.id:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden")

    project = await project_service.complete_project(db, project_id)
    await db.commit()

    return _project_to_response(project)


# =============================================================================
# Team Member Endpoints
# =============================================================================


@router.post("/{project_id}/members", response_model=MemberResponse, status_code=status.HTTP_201_CREATED)
async def add_member(
    project_id: UUID,
    request: MemberCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> MemberResponse:
    """Mitglied zum Projekt hinzufuegen."""
    existing = await project_service.get_project(db, project_id)
    if not existing or existing.company_id != company.id:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden")

    try:
        member = await project_service.add_member(
            db,
            project_id=project_id,
            user_id=request.user_id,
            role=request.role,
            permissions=request.permissions,
            valid_from=request.valid_from,
            valid_until=request.valid_until,
            allocation_percent=request.allocation_percent,
        )
        await db.commit()
        return _member_to_response(member)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=safe_error_detail(e, "Projektmitglied"))


@router.get("/{project_id}/members", response_model=List[MemberResponse])
async def list_members(
    project_id: UUID,
    active_only: bool = Query(True, description="Nur aktive Mitglieder"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> List[MemberResponse]:
    """Projektmitglieder auflisten."""
    existing = await project_service.get_project(db, project_id)
    if not existing or existing.company_id != company.id:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden")

    members = await project_service.list_members(db, project_id, active_only=active_only)
    return [_member_to_response(m) for m in members]


@router.delete("/{project_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def remove_member(
    project_id: UUID,
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
):
    """Mitglied aus Projekt entfernen."""
    existing = await project_service.get_project(db, project_id)
    if not existing or existing.company_id != company.id:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden")

    success = await project_service.remove_member(db, project_id, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="Mitglied nicht gefunden")

    await db.commit()


# =============================================================================
# Document Assignment Endpoints
# =============================================================================


@router.post("/{project_id}/documents", response_model=DocumentAssignmentResponse, status_code=status.HTTP_201_CREATED)
async def assign_document(
    project_id: UUID,
    request: DocumentAssignRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> DocumentAssignmentResponse:
    """Dokument manuell zuweisen."""
    existing = await project_service.get_project(db, project_id)
    if not existing or existing.company_id != company.id:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden")

    try:
        assignment = await project_service.assign_document(
            db,
            document_id=request.document_id,
            project_id=project_id,
            company_id=company.id,
            assignment_type=request.assignment_type,
            assigned_by_id=current_user.id,
            auto_assigned=False,
        )
        await db.commit()
        return _assignment_to_response(assignment)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=safe_error_detail(e, "Dokumentzuweisung"))


@router.get("/{project_id}/documents", response_model=List[DocumentAssignmentResponse])
async def list_project_documents(
    project_id: UUID,
    assignment_type: Optional[str] = Query(None, description="Zuweisungstyp-Filter"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> List[DocumentAssignmentResponse]:
    """Dokumente eines Projekts auflisten."""
    existing = await project_service.get_project(db, project_id)
    if not existing or existing.company_id != company.id:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden")

    assignments, _ = await project_service.list_project_documents(
        db, project_id,
        assignment_type=assignment_type,
        limit=limit,
        offset=offset,
    )
    return [_assignment_to_response(a) for a in assignments]


@router.delete("/{project_id}/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def unassign_document(
    project_id: UUID,
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
):
    """Dokument-Zuweisung entfernen."""
    existing = await project_service.get_project(db, project_id)
    if not existing or existing.company_id != company.id:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden")

    success = await project_service.unassign_document(db, document_id, project_id)
    if not success:
        raise HTTPException(status_code=404, detail="Zuweisung nicht gefunden")

    await db.commit()


@router.get("/{project_id}/document-stats", response_model=ProjectDocumentStatsResponse)
async def get_document_stats(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> ProjectDocumentStatsResponse:
    """Dokumenten-Statistiken eines Projekts."""
    existing = await project_service.get_project(db, project_id)
    if not existing or existing.company_id != company.id:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden")

    stats = await project_service.get_project_document_stats(db, project_id)
    return ProjectDocumentStatsResponse(
        total_documents=stats.total_documents,
        invoices=stats.invoices,
        contracts=stats.contracts,
        correspondence=stats.correspondence,
        other=stats.other,
        auto_assigned=stats.auto_assigned,
        manual_assigned=stats.manual_assigned,
    )


# =============================================================================
# Auto-Assignment (KI-Feature)
# =============================================================================


@router.get("/suggest-for-document/{document_id}", response_model=List[AutoAssignSuggestion])
async def suggest_projects_for_document(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> List[AutoAssignSuggestion]:
    """KI-basierte Projekt-Vorschläge für ein Dokument."""
    suggestions = await project_service.suggest_project_for_document(
        db, document_id, company.id
    )

    result = []
    for s in suggestions:
        project = await project_service.get_project(db, s.project_id)
        if project:
            result.append(AutoAssignSuggestion(
                project_id=s.project_id,
                project_code=project.code,
                project_name=project.name,
                confidence=s.confidence,
                assignment_reason=s.assignment_reason,
                assignment_type=s.assignment_type,
            ))

    return result


@router.post("/auto-assign/{document_id}", response_model=Optional[DocumentAssignmentResponse])
async def auto_assign_document(
    document_id: UUID,
    min_confidence: float = Query(0.85, ge=0.5, le=1.0, description="Mindest-Confidence"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> Optional[DocumentAssignmentResponse]:
    """Automatische Projekt-Zuweisung für ein Dokument."""
    result = await project_service.auto_assign_document(
        db, document_id, company.id,
        min_confidence=min_confidence,
    )

    if not result or not result.auto_assigned:
        return None

    await db.commit()

    # Get the assignment
    assignments, _ = await project_service.list_project_documents(
        db, result.project_id, limit=1
    )
    if assignments:
        return _assignment_to_response(assignments[0])
    return None


# =============================================================================
# Project Document Chains (Vision 2026+ Multi-Chain Bundling)
# =============================================================================


class ProjectChainCreate(BaseModel):
    """Schema für Chain-Projekt-Verknüpfung."""
    chain_id: str = Field(..., min_length=1, max_length=100, description="Chain-ID")
    chain_name: Optional[str] = Field(None, max_length=255, description="Chain-Name")
    chain_description: Optional[str] = Field(None, max_length=2000, description="Beschreibung")
    expected_document_types: List[str] = Field(
        default=["quote", "order", "delivery_note", "invoice"],
        description="Erwartete Dokumenttypen"
    )
    allocated_budget: Optional[Decimal] = Field(None, ge=0, description="Zugewiesenes Budget")
    entity_id: Optional[UUID] = Field(None, description="Geschäftspartner-ID")
    order_number: Optional[str] = Field(None, max_length=100, description="Bestellnummer")
    notes: Optional[str] = Field(None, max_length=2000, description="Notizen")

    model_config = ConfigDict(from_attributes=True)


class ProjectChainUpdate(BaseModel):
    """Schema für Chain-Update."""
    chain_name: Optional[str] = Field(None, max_length=255)
    chain_description: Optional[str] = Field(None, max_length=2000)
    chain_status: Optional[str] = Field(None, description="active, completed, cancelled")
    expected_document_types: Optional[List[str]] = None
    completed_document_types: Optional[List[str]] = None
    allocated_budget: Optional[Decimal] = Field(None, ge=0)
    notes: Optional[str] = Field(None, max_length=2000)

    model_config = ConfigDict(from_attributes=True)


class ProjectChainResponse(BaseModel):
    """Response für eine Projekt-Chain."""
    id: UUID
    project_id: UUID
    chain_id: str
    chain_name: Optional[str] = None
    chain_description: Optional[str] = None
    chain_status: str
    expected_document_types: List[str]
    completed_document_types: List[str]
    progress_percent: int
    allocated_budget: Optional[float] = None
    actual_cost: float = 0
    document_count: int = 0
    total_amount: Optional[float] = None
    discrepancy_count: int = 0
    has_critical_discrepancy: bool = False
    entity_id: Optional[UUID] = None
    primary_reference: Optional[str] = None
    order_number: Optional[str] = None
    first_document_date: Optional[date] = None
    last_document_date: Optional[date] = None
    is_complete: bool
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ProjectChainListResponse(BaseModel):
    """Response für Chain-Liste."""
    items: List[ProjectChainResponse]
    total: int
    project_id: UUID

    model_config = ConfigDict(from_attributes=True)


class ProjectChainStatsResponse(BaseModel):
    """Statistiken für Projekt-Chains."""
    total_chains: int
    active_chains: int
    completed_chains: int
    total_documents: int
    total_discrepancies: int
    critical_discrepancies: int
    total_allocated_budget: Optional[float] = None
    total_actual_cost: float = 0
    overall_progress_percent: int = 0

    model_config = ConfigDict(from_attributes=True)


def _chain_to_response(chain) -> ProjectChainResponse:
    """Konvertiert ProjectDocumentChain zu Response."""
    data = chain.to_dict()
    return ProjectChainResponse(
        id=UUID(data["id"]),
        project_id=UUID(data["project_id"]),
        chain_id=data["chain_id"],
        chain_name=data["chain_name"],
        chain_description=data["chain_description"],
        chain_status=data["chain_status"],
        expected_document_types=data["expected_document_types"] or [],
        completed_document_types=data["completed_document_types"] or [],
        progress_percent=data["progress_percent"],
        allocated_budget=data["allocated_budget"],
        actual_cost=data["actual_cost"],
        document_count=data["document_count"],
        total_amount=data["total_amount"],
        discrepancy_count=data["discrepancy_count"],
        has_critical_discrepancy=data["has_critical_discrepancy"],
        entity_id=UUID(data["entity_id"]) if data["entity_id"] else None,
        primary_reference=data["primary_reference"],
        order_number=data["order_number"],
        first_document_date=date.fromisoformat(data["first_document_date"]) if data["first_document_date"] else None,
        last_document_date=date.fromisoformat(data["last_document_date"]) if data["last_document_date"] else None,
        is_complete=data["is_complete"],
        created_at=data["created_at"],
        updated_at=data["updated_at"],
    )


@router.get("/{project_id}/chains", response_model=ProjectChainListResponse)
async def list_project_chains(
    project_id: UUID,
    status_filter: Optional[str] = Query(None, description="Filter: active, completed, cancelled"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> ProjectChainListResponse:
    """Listet alle Document Chains eines Projekts auf."""
    from sqlalchemy import select
    from app.db.models_project import ProjectDocumentChain

    # Verify project access
    project = await project_service.get_project(db, project_id)
    if not project or project.company_id != company.id:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden")

    # Load chains
    query = select(ProjectDocumentChain).where(
        ProjectDocumentChain.project_id == project_id,
        ProjectDocumentChain.company_id == company.id,
    )

    if status_filter:
        query = query.where(ProjectDocumentChain.chain_status == status_filter)

    query = query.order_by(ProjectDocumentChain.created_at.desc())

    result = await db.execute(query)
    chains = list(result.scalars().all())

    return ProjectChainListResponse(
        items=[_chain_to_response(c) for c in chains],
        total=len(chains),
        project_id=project_id,
    )


@router.post("/{project_id}/chains", response_model=ProjectChainResponse, status_code=status.HTTP_201_CREATED)
async def add_chain_to_project(
    project_id: UUID,
    request: ProjectChainCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> ProjectChainResponse:
    """Fuegt eine Document Chain zu einem Projekt hinzu."""
    from app.db.models_project import ProjectDocumentChain

    # Verify project access
    project = await project_service.get_project(db, project_id)
    if not project or project.company_id != company.id:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden")

    # Check for duplicate
    from sqlalchemy import select
    existing = await db.execute(
        select(ProjectDocumentChain).where(
            ProjectDocumentChain.project_id == project_id,
            ProjectDocumentChain.chain_id == request.chain_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Diese Chain ist bereits mit dem Projekt verknüpft"
        )

    # Create chain assignment
    chain = ProjectDocumentChain(
        project_id=project_id,
        company_id=company.id,
        chain_id=request.chain_id,
        chain_name=request.chain_name,
        chain_description=request.chain_description,
        expected_document_types=request.expected_document_types,
        allocated_budget=request.allocated_budget,
        entity_id=request.entity_id,
        order_number=request.order_number,
        notes=request.notes,
        created_by_id=current_user.id,
    )

    db.add(chain)
    await db.commit()
    await db.refresh(chain)

    logger.info(
        "project_chain_added",
        project_id=str(project_id),
        chain_id=request.chain_id,
    )

    return _chain_to_response(chain)


@router.get("/{project_id}/chains/{chain_id}", response_model=ProjectChainResponse)
async def get_project_chain(
    project_id: UUID,
    chain_id: str = Path(..., min_length=1, max_length=100, description="Chain-ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> ProjectChainResponse:
    """Holt eine spezifische Project-Chain."""
    from sqlalchemy import select
    from app.db.models_project import ProjectDocumentChain

    result = await db.execute(
        select(ProjectDocumentChain).where(
            ProjectDocumentChain.project_id == project_id,
            ProjectDocumentChain.chain_id == chain_id,
            ProjectDocumentChain.company_id == company.id,
        )
    )
    chain = result.scalar_one_or_none()

    if not chain:
        raise HTTPException(status_code=404, detail="Chain nicht gefunden")

    return _chain_to_response(chain)


@router.patch("/{project_id}/chains/{chain_id}", response_model=ProjectChainResponse)
async def update_project_chain(
    project_id: UUID,
    chain_id: str = Path(..., min_length=1, max_length=100, description="Chain-ID"),
    request: ProjectChainUpdate = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> ProjectChainResponse:
    """Aktualisiert eine Project-Chain."""
    from sqlalchemy import select
    from app.db.models_project import ProjectDocumentChain

    result = await db.execute(
        select(ProjectDocumentChain).where(
            ProjectDocumentChain.project_id == project_id,
            ProjectDocumentChain.chain_id == chain_id,
            ProjectDocumentChain.company_id == company.id,
        )
    )
    chain = result.scalar_one_or_none()

    if not chain:
        raise HTTPException(status_code=404, detail="Chain nicht gefunden")

    # Validate status
    if request.chain_status:
        valid_statuses = ["active", "completed", "cancelled"]
        if request.chain_status not in valid_statuses:
            raise HTTPException(
                status_code=400,
                detail=f"Ungültiger Status. Erlaubt: {valid_statuses}"
            )

    # Update fields
    update_data = request.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(chain, key, value)

    # Recalculate progress
    if chain.expected_document_types and chain.completed_document_types:
        total = len(chain.expected_document_types)
        completed = len([t for t in chain.completed_document_types if t in chain.expected_document_types])
        chain.progress_percent = int((completed / total) * 100) if total > 0 else 0

    await db.commit()
    await db.refresh(chain)

    return _chain_to_response(chain)


@router.delete("/{project_id}/chains/{chain_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def remove_chain_from_project(
    project_id: UUID,
    chain_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
):
    """Entfernt eine Chain von einem Projekt."""
    from sqlalchemy import select, delete
    from app.db.models_project import ProjectDocumentChain

    result = await db.execute(
        select(ProjectDocumentChain).where(
            ProjectDocumentChain.project_id == project_id,
            ProjectDocumentChain.chain_id == chain_id,
            ProjectDocumentChain.company_id == company.id,
        )
    )
    chain = result.scalar_one_or_none()

    if not chain:
        raise HTTPException(status_code=404, detail="Chain nicht gefunden")

    await db.delete(chain)
    await db.commit()

    logger.info(
        "project_chain_removed",
        project_id=str(project_id),
        chain_id=chain_id,
    )


@router.get("/{project_id}/chains/stats/summary", response_model=ProjectChainStatsResponse)
async def get_project_chain_stats(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> ProjectChainStatsResponse:
    """Holt Statistiken über alle Chains eines Projekts."""
    from sqlalchemy import select, func
    from app.db.models_project import ProjectDocumentChain

    # Verify project access
    project = await project_service.get_project(db, project_id)
    if not project or project.company_id != company.id:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden")

    # Load all chains
    result = await db.execute(
        select(ProjectDocumentChain).where(
            ProjectDocumentChain.project_id == project_id,
            ProjectDocumentChain.company_id == company.id,
        )
    )
    chains = list(result.scalars().all())

    if not chains:
        return ProjectChainStatsResponse(
            total_chains=0,
            active_chains=0,
            completed_chains=0,
            total_documents=0,
            total_discrepancies=0,
            critical_discrepancies=0,
            overall_progress_percent=0,
        )

    # Calculate stats
    active_count = sum(1 for c in chains if c.chain_status == "active")
    completed_count = sum(1 for c in chains if c.chain_status == "completed")
    total_docs = sum(c.document_count for c in chains)
    total_discrep = sum(c.discrepancy_count for c in chains)
    critical_discrep = sum(1 for c in chains if c.has_critical_discrepancy)
    total_budget = sum(float(c.allocated_budget) for c in chains if c.allocated_budget)
    total_cost = sum(float(c.actual_cost) for c in chains)
    avg_progress = sum(c.progress_percent for c in chains) // len(chains) if chains else 0

    return ProjectChainStatsResponse(
        total_chains=len(chains),
        active_chains=active_count,
        completed_chains=completed_count,
        total_documents=total_docs,
        total_discrepancies=total_discrep,
        critical_discrepancies=critical_discrep,
        total_allocated_budget=total_budget if total_budget > 0 else None,
        total_actual_cost=total_cost,
        overall_progress_percent=avg_progress,
    )


@router.post("/{project_id}/chains/{chain_id}/complete-document-type")
async def complete_chain_document_type(
    project_id: UUID,
    chain_id: str,
    document_type: str = Query(..., description="Dokumenttyp (quote, order, delivery_note, invoice)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> ProjectChainResponse:
    """Markiert einen Dokumenttyp als abgeschlossen in der Chain."""
    from sqlalchemy import select
    from app.db.models_project import ProjectDocumentChain

    result = await db.execute(
        select(ProjectDocumentChain).where(
            ProjectDocumentChain.project_id == project_id,
            ProjectDocumentChain.chain_id == chain_id,
            ProjectDocumentChain.company_id == company.id,
        )
    )
    chain = result.scalar_one_or_none()

    if not chain:
        raise HTTPException(status_code=404, detail="Chain nicht gefunden")

    # Validate document type
    if document_type not in chain.expected_document_types:
        raise HTTPException(
            status_code=400,
            detail=f"Dokumenttyp '{document_type}' ist nicht in den erwarteten Typen"
        )

    # Add to completed if not already
    completed = chain.completed_document_types or []
    if document_type not in completed:
        completed.append(document_type)
        chain.completed_document_types = completed

        # Recalculate progress
        total = len(chain.expected_document_types)
        done = len([t for t in completed if t in chain.expected_document_types])
        chain.progress_percent = int((done / total) * 100) if total > 0 else 0

        # Auto-complete if all done
        if chain.is_complete:
            chain.chain_status = "completed"

    await db.commit()
    await db.refresh(chain)

    return _chain_to_response(chain)

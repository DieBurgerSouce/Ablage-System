"""
Department API Endpoints - Abteilungs-Verwaltung (Enterprise Security).

CRUD-Operationen fuer Abteilungen mit hierarchischer Struktur.
Alle Antworten auf Deutsch.

Security Features:
- RBAC-basierte Zugriffskontrolle (departments:read/write/delete/manage)
- Audit-Logging aller Operationen via SecurityAuditLogger
- Input-Sanitization
- Company Context Enforcement (Multi-Tenancy)
- Hierarchie-Validierung (keine Zyklen)
"""

from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.api.dependencies import get_db, check_rate_limit
from app.db.models import User, Company
from app.middleware.company_context import require_company
from app.core.rbac import (
    require_permission,
    require_any_permission,
    require_department_read,
    require_department_write,
    require_department_delete,
)
from app.services.personal import department_service

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/departments", tags=["Personal - Abteilungen"])


# ==================== F.1 CRITICAL: Safe Error Messages ====================

def _get_safe_error_response(error: ValueError) -> tuple[int, str]:
    """Klassifiziert Fehler und gibt generische Nachricht zurueck.

    F.1 CRITICAL: Verhindert Information Leakage durch Exception-Messages.
    Interne Details werden geloggt, aber nicht an Client gesendet.
    """
    error_msg = str(error).lower()

    if 'existiert bereits' in error_msg or 'duplicate' in error_msg or 'bereits vorhanden' in error_msg:
        return status.HTTP_409_CONFLICT, "Ein Eintrag mit diesen Daten existiert bereits."
    elif 'nicht gefunden' in error_msg or 'not found' in error_msg:
        return status.HTTP_404_NOT_FOUND, "Die referenzierte Ressource wurde nicht gefunden."
    elif 'zyklisch' in error_msg or 'cycle' in error_msg or 'eigenes elternteil' in error_msg:
        return status.HTTP_400_BAD_REQUEST, "Diese Aenderung wuerde eine ungueltige Struktur erzeugen."
    elif 'berechtigung' in error_msg or 'permission' in error_msg or 'zugriff' in error_msg:
        return status.HTTP_403_FORBIDDEN, "Keine Berechtigung fuer diese Aktion."
    elif 'ungueltig' in error_msg or 'invalid' in error_msg or 'format' in error_msg:
        return status.HTTP_400_BAD_REQUEST, "Die Eingabedaten sind ungueltig."
    elif 'unterabteilung' in error_msg or 'nicht leer' in error_msg or 'kinder' in error_msg:
        return status.HTTP_409_CONFLICT, "Die Ressource kann nicht geloescht werden, da sie noch verwendet wird."
    else:
        return status.HTTP_400_BAD_REQUEST, "Die Anfrage konnte nicht verarbeitet werden."


# ==================== Pydantic Schemas ====================

class DepartmentBase(BaseModel):
    """Basis-Schema fuer Abteilung."""
    name: str = Field(..., min_length=1, max_length=200, description="Abteilungsname")
    short_name: Optional[str] = Field(None, max_length=20, description="Kurzname/Kuerzel")
    description: Optional[str] = Field(None, max_length=1000, description="Beschreibung")
    cost_center: Optional[str] = Field(None, max_length=50, description="Kostenstelle")
    parent_id: Optional[UUID] = Field(None, description="Uebergeordnete Abteilung")
    manager_id: Optional[UUID] = Field(None, description="Abteilungsleiter")
    is_active: bool = Field(True, description="Aktiv")
    sort_order: int = Field(0, description="Sortierreihenfolge")

    # F.3 MEDIUM: Leere Strings zu None konvertieren (Konsistenz)
    @field_validator('short_name', 'description', 'cost_center', mode='before')
    @classmethod
    def empty_string_to_none(cls, v: Optional[str]) -> Optional[str]:
        """Konvertiert leere/whitespace-only Strings zu None."""
        if v is not None and isinstance(v, str) and len(v.strip()) == 0:
            return None
        return v

    model_config = ConfigDict(from_attributes=True)


class DepartmentCreate(DepartmentBase):
    """Schema fuer Abteilungs-Erstellung."""
    pass


class DepartmentUpdate(BaseModel):
    """Schema fuer Abteilungs-Update (alle Felder optional)."""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    short_name: Optional[str] = Field(None, max_length=20)
    description: Optional[str] = Field(None, max_length=1000)
    cost_center: Optional[str] = Field(None, max_length=50)
    parent_id: Optional[UUID] = None
    manager_id: Optional[UUID] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None

    # F.3 MEDIUM: Leere Strings zu None konvertieren (Konsistenz)
    @field_validator('short_name', 'description', 'cost_center', mode='before')
    @classmethod
    def empty_string_to_none(cls, v: Optional[str]) -> Optional[str]:
        """Konvertiert leere/whitespace-only Strings zu None."""
        if v is not None and isinstance(v, str) and len(v.strip()) == 0:
            return None
        return v


class ManagerInfo(BaseModel):
    """Eingebettete Manager-Info."""
    id: UUID
    first_name: str
    last_name: str
    full_name: str

    model_config = ConfigDict(from_attributes=True)


class DepartmentResponse(BaseModel):
    """Response-Schema fuer Abteilung."""
    id: UUID
    name: str
    short_name: Optional[str] = None
    description: Optional[str] = None
    cost_center: Optional[str] = None
    parent_id: Optional[UUID] = None
    manager_id: Optional[UUID] = None
    manager: Optional[ManagerInfo] = None
    is_active: bool
    sort_order: int
    employee_count: int = 0
    created_at: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class DepartmentDetailResponse(DepartmentResponse):
    """Detaillierte Response mit Unterabteilungen."""
    children: List["DepartmentResponse"] = []
    updated_at: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class DepartmentTreeItem(BaseModel):
    """Hierarchie-Item fuer Abteilungsbaum."""
    id: UUID
    name: str
    short_name: Optional[str] = None
    parent_id: Optional[UUID] = None
    manager_id: Optional[UUID] = None
    manager_name: Optional[str] = None
    employee_count: int = 0
    is_active: bool
    sort_order: int
    level: int = 0
    children: List["DepartmentTreeItem"] = []

    model_config = ConfigDict(from_attributes=True)


class DepartmentListResponse(BaseModel):
    """Paginierte Liste von Abteilungen."""
    items: List[DepartmentResponse]
    total: int
    page: int
    per_page: int
    total_pages: int


class MessageResponse(BaseModel):
    """Einfache Nachricht-Response."""
    message: str


# ==================== API Endpoints ====================

@router.get(
    "",
    response_model=DepartmentListResponse,
    summary="Abteilungen auflisten",
    description="Gibt alle Abteilungen mit optionaler Filterung und Paginierung zurueck. "
                "Erfordert Berechtigung: departments:read"
)
async def list_departments(
    request: Request,
    page: int = Query(1, ge=1, description="Seitennummer"),
    per_page: int = Query(20, ge=1, le=100, description="Eintraege pro Seite (max 100)"),
    search: Optional[str] = Query(None, min_length=1, max_length=100, description="Suche (Name)"),
    parent_id: Optional[UUID] = Query(None, description="Filter nach uebergeordneter Abteilung"),
    include_inactive: bool = Query(False, description="Inaktive einbeziehen"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_department_read),
    company: Company = Depends(require_company),
    _rate_limit: User = Depends(check_rate_limit),  # A.2 CRITICAL: Rate Limiting
) -> DepartmentListResponse:
    """Liste der Abteilungen.

    Erfordert: departments:read
    """
    # IP-Adresse fuer Audit-Log (A.1 CRITICAL: Audit-Logging fuer List-Operationen)
    ip_address = request.client.host if request.client else None

    # Service-Delegation mit automatischem Audit-Logging
    departments, total = await department_service.list_departments(
        db=db,
        company_id=company.id,
        user_id=current_user.id,  # A.1 CRITICAL: Audit-Logging
        ip_address=ip_address,  # A.1 CRITICAL: Audit-Logging
        page=page,
        per_page=per_page,
        search=search,
        parent_id=parent_id,
        include_inactive=include_inactive,
    )

    return DepartmentListResponse(
        items=[_dict_to_department_response(d) for d in departments],
        total=total,
        page=page,
        per_page=per_page,
        total_pages=(total + per_page - 1) // per_page if total > 0 else 0,
    )


@router.get(
    "/tree",
    response_model=List[DepartmentTreeItem],
    summary="Abteilungsbaum abrufen",
    description="Gibt die hierarchische Abteilungsstruktur zurueck. "
                "Erfordert Berechtigung: departments:read"
)
async def get_department_tree(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_department_read),
    company: Company = Depends(require_company),
    _rate_limit: User = Depends(check_rate_limit),  # A.2 CRITICAL: Rate Limiting
) -> List[DepartmentTreeItem]:
    """Hierarchischer Abteilungsbaum.

    Erfordert: departments:read
    """
    # IP-Adresse fuer Audit-Log (B.7 HIGH: IP-Adresse in Tree-Endpoint)
    ip_address = request.client.host if request.client else None

    # Service-Delegation
    tree_data = await department_service.get_department_tree(
        db=db,
        company_id=company.id,
        user_id=current_user.id,  # B.7 HIGH: Audit-Logging
        ip_address=ip_address,  # B.7 HIGH: Audit-Logging
    )

    return [_dict_to_tree_item(d) for d in tree_data]


@router.post(
    "",
    response_model=DepartmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Abteilung anlegen",
    description="Erstellt eine neue Abteilung. "
                "Erfordert Berechtigung: departments:write"
)
async def create_department(
    request: Request,
    data: DepartmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_department_write),
    company: Company = Depends(require_company),
    _rate_limit: User = Depends(check_rate_limit),  # A.2 CRITICAL: Rate Limiting
) -> DepartmentResponse:
    """Erstellt eine neue Abteilung.

    Erfordert: departments:write
    Audit-Log: DEPARTMENT_CREATED
    """
    # IP-Adresse fuer Audit-Log
    ip_address = request.client.host if request.client else None

    try:
        # Service-Delegation mit Audit-Logging
        department_data = await department_service.create_department(
            db=db,
            company_id=company.id,
            user_id=current_user.id,
            data=data.model_dump(exclude_unset=True),
            ip_address=ip_address,
        )

        return _dict_to_department_response(department_data)

    except ValueError as e:
        # F.1 CRITICAL: Sichere Error-Messages - keine interne Details leaken
        error_status, safe_message = _get_safe_error_response(e)
        logger.warning(
            "department_validation_error",
            error_detail=str(e),
            user_id=str(current_user.id),
            company_id=str(company.id),
        )
        raise HTTPException(status_code=error_status, detail=safe_message)


@router.get(
    "/{department_id}",
    response_model=DepartmentDetailResponse,
    summary="Abteilung abrufen",
    description="Gibt Details einer Abteilung zurueck. "
                "Erfordert Berechtigung: departments:read"
)
async def get_department(
    request: Request,
    department_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_department_read),
    company: Company = Depends(require_company),
    _rate_limit: User = Depends(check_rate_limit),  # A.2 CRITICAL: Rate Limiting
) -> DepartmentDetailResponse:
    """Gibt eine Abteilung zurueck.

    Erfordert: departments:read
    Audit-Log: DEPARTMENT_ACCESSED
    """
    # IP-Adresse fuer Audit-Log
    ip_address = request.client.host if request.client else None

    # Service-Delegation mit Audit-Logging
    department_data = await department_service.get_department(
        db=db,
        department_id=department_id,
        company_id=company.id,
        user_id=current_user.id,
        ip_address=ip_address,
    )

    if not department_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Abteilung nicht gefunden."
        )

    return _dict_to_detail_response(department_data)


@router.put(
    "/{department_id}",
    response_model=DepartmentResponse,
    summary="Abteilung aktualisieren",
    description="Aktualisiert eine Abteilung. "
                "Erfordert Berechtigung: departments:write"
)
async def update_department(
    request: Request,
    department_id: UUID,
    data: DepartmentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_department_write),
    company: Company = Depends(require_company),
    _rate_limit: User = Depends(check_rate_limit),  # A.2 CRITICAL: Rate Limiting
) -> DepartmentResponse:
    """Aktualisiert eine Abteilung.

    Erfordert: departments:write
    Audit-Log: DEPARTMENT_UPDATED
    """
    # IP-Adresse fuer Audit-Log
    ip_address = request.client.host if request.client else None

    try:
        # Service-Delegation mit Audit-Logging und Hierarchie-Validierung
        department_data = await department_service.update_department(
            db=db,
            department_id=department_id,
            company_id=company.id,
            user_id=current_user.id,
            data=data.model_dump(exclude_unset=True),
            ip_address=ip_address,
        )

        if not department_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Abteilung nicht gefunden."
            )

        return _dict_to_department_response(department_data)

    except ValueError as e:
        # F.1 CRITICAL: Sichere Error-Messages - keine interne Details leaken
        error_status, safe_message = _get_safe_error_response(e)
        logger.warning(
            "department_update_error",
            error_detail=str(e),
            user_id=str(current_user.id),
            company_id=str(company.id),
            department_id=str(department_id),
        )
        raise HTTPException(status_code=error_status, detail=safe_message)


@router.delete(
    "/{department_id}",
    response_model=MessageResponse,
    summary="Abteilung loeschen",
    description="Loescht eine Abteilung (Soft-Delete). "
                "Erfordert Berechtigung: departments:delete oder departments:manage"
)
async def delete_department(
    request: Request,
    department_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_department_delete),
    company: Company = Depends(require_company),
    _rate_limit: User = Depends(check_rate_limit),  # A.2 CRITICAL: Rate Limiting
) -> MessageResponse:
    """Loescht eine Abteilung (Soft-Delete).

    Erfordert: departments:delete ODER departments:manage
    Audit-Log: DEPARTMENT_DELETED (Severity: warning)
    """
    # IP-Adresse fuer Audit-Log
    ip_address = request.client.host if request.client else None

    try:
        # Service-Delegation mit Audit-Logging
        success = await department_service.delete_department(
            db=db,
            department_id=department_id,
            company_id=company.id,
            user_id=current_user.id,
            ip_address=ip_address,
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Abteilung nicht gefunden."
            )

        return MessageResponse(message="Abteilung erfolgreich geloescht.")

    except ValueError as e:
        # F.1 CRITICAL: Sichere Error-Messages - keine interne Details leaken
        error_status, safe_message = _get_safe_error_response(e)
        logger.warning(
            "department_delete_error",
            error_detail=str(e),
            user_id=str(current_user.id),
            company_id=str(company.id),
            department_id=str(department_id),
        )
        raise HTTPException(status_code=error_status, detail=safe_message)


# ==================== Helper Functions ====================

def _dict_to_department_response(data: Dict[str, Any]) -> DepartmentResponse:
    """Konvertiert Service-Dict zu Response."""
    return DepartmentResponse(
        id=UUID(data['id']),
        name=data['name'],
        short_name=data.get('short_name'),
        description=data.get('description'),
        cost_center=data.get('cost_center'),
        parent_id=UUID(data['parent_id']) if data.get('parent_id') else None,
        manager_id=UUID(data['manager_id']) if data.get('manager_id') else None,
        manager=None,  # Service liefert keine verschachtelten Manager-Daten
        is_active=data.get('is_active', True),
        sort_order=data.get('sort_order', 0),
        employee_count=data.get('employee_count', 0),
        created_at=data.get('created_at'),
    )


def _dict_to_detail_response(data: Dict[str, Any]) -> DepartmentDetailResponse:
    """Konvertiert Service-Dict zu Detail-Response."""
    children = [
        DepartmentResponse(
            id=UUID(c['id']),
            name=c['name'],
            short_name=c.get('short_name'),
            description=c.get('description'),
            cost_center=c.get('cost_center'),
            parent_id=UUID(c['parent_id']) if c.get('parent_id') else None,
            manager_id=UUID(c['manager_id']) if c.get('manager_id') else None,
            manager=None,
            is_active=c.get('is_active', True),
            sort_order=c.get('sort_order', 0),
            employee_count=0,
            created_at=c.get('created_at'),
        )
        for c in data.get('children', [])
    ]

    return DepartmentDetailResponse(
        id=UUID(data['id']),
        name=data['name'],
        short_name=data.get('short_name'),
        description=data.get('description'),
        cost_center=data.get('cost_center'),
        parent_id=UUID(data['parent_id']) if data.get('parent_id') else None,
        manager_id=UUID(data['manager_id']) if data.get('manager_id') else None,
        manager=None,
        is_active=data.get('is_active', True),
        sort_order=data.get('sort_order', 0),
        employee_count=data.get('employee_count', 0),
        children=children,
        created_at=data.get('created_at'),
        updated_at=data.get('updated_at'),
    )


def _dict_to_tree_item(data: Dict[str, Any], level: int = 0) -> DepartmentTreeItem:
    """Konvertiert Service-Tree-Dict zu TreeItem."""
    return DepartmentTreeItem(
        id=UUID(data['id']),
        name=data['name'],
        short_name=data.get('short_name'),
        parent_id=None,  # Tree-Root-Items haben kein Parent im Response
        manager_id=UUID(data['manager_id']) if data.get('manager_id') else None,
        manager_name=None,  # Service liefert keinen Manager-Namen
        employee_count=data.get('employee_count', 0),
        is_active=data.get('is_active', True),
        sort_order=data.get('sort_order', 0),
        level=level,
        children=[_dict_to_tree_item(c, level + 1) for c in data.get('children', [])],
    )

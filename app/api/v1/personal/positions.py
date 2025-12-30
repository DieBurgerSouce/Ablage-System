"""
Position API Endpoints - Stellen-/Positions-Verwaltung (Enterprise Security).

CRUD-Operationen fuer Positionen/Stellen.
Alle Antworten auf Deutsch.

Security Features:
- RBAC-basierte Zugriffskontrolle (positions:read/write/delete/manage)
- Gehalts-Maskierung basierend auf positions:read_salary
- Audit-Logging aller Operationen via SecurityAuditLogger
- Input-Sanitization
- Company Context Enforcement (Multi-Tenancy)
"""

from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.api.dependencies import get_db, check_rate_limit
from app.db.models import User, Company
from app.middleware.company_context import require_company
from app.core.rbac import (
    require_permission,
    require_any_permission,
    require_position_read,
    require_position_write,
    require_position_delete,
    PermissionContext,
)
from app.services.personal import position_service

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/positions", tags=["Personal - Positionen"])


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
    elif 'zyklisch' in error_msg or 'cycle' in error_msg:
        return status.HTTP_400_BAD_REQUEST, "Diese Aenderung wuerde eine ungueltige Struktur erzeugen."
    elif 'berechtigung' in error_msg or 'permission' in error_msg or 'zugriff' in error_msg:
        return status.HTTP_403_FORBIDDEN, "Keine Berechtigung fuer diese Aktion."
    elif 'ungueltig' in error_msg or 'invalid' in error_msg or 'format' in error_msg:
        return status.HTTP_400_BAD_REQUEST, "Die Eingabedaten sind ungueltig."
    elif 'mitarbeiter' in error_msg or 'zugeordnet' in error_msg or 'nicht leer' in error_msg:
        return status.HTTP_409_CONFLICT, "Die Ressource kann nicht geloescht werden, da sie noch verwendet wird."
    else:
        return status.HTTP_400_BAD_REQUEST, "Die Anfrage konnte nicht verarbeitet werden."


# ==================== Pydantic Schemas ====================

class PositionBase(BaseModel):
    """Basis-Schema fuer Position."""
    title: str = Field(..., min_length=1, max_length=200, description="Stellenbezeichnung")
    description: Optional[str] = Field(None, max_length=2000, description="Stellenbeschreibung")
    department_id: Optional[UUID] = Field(None, description="Zugeordnete Abteilung")
    level: Optional[int] = Field(None, ge=1, le=20, description="Hierarchie-Ebene (1=hoechste)")
    job_family: Optional[str] = Field(None, max_length=100, description="Job-Familie (z.B. IT, Finance)")
    min_salary: Optional[float] = Field(None, ge=0, description="Mindestgehalt")
    max_salary: Optional[float] = Field(None, ge=0, description="Maximalgehalt")
    is_management: bool = Field(False, description="Fuehrungsposition")
    is_active: bool = Field(True, description="Aktiv")
    sort_order: int = Field(0, description="Sortierreihenfolge")
    requirements: Optional[str] = Field(None, description="Anforderungen (Markdown)")
    responsibilities: Optional[str] = Field(None, description="Aufgaben (Markdown)")

    # F.3 MEDIUM: Leere Strings zu None konvertieren (Konsistenz)
    @field_validator('description', 'job_family', 'requirements', 'responsibilities', mode='before')
    @classmethod
    def empty_string_to_none(cls, v: Optional[str]) -> Optional[str]:
        """Konvertiert leere/whitespace-only Strings zu None."""
        if v is not None and isinstance(v, str) and len(v.strip()) == 0:
            return None
        return v

    class Config:
        from_attributes = True


class PositionCreate(PositionBase):
    """Schema fuer Positions-Erstellung."""
    pass


class PositionUpdate(BaseModel):
    """Schema fuer Positions-Update (alle Felder optional)."""
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    department_id: Optional[UUID] = None
    level: Optional[int] = Field(None, ge=1, le=20)
    job_family: Optional[str] = Field(None, max_length=100)
    min_salary: Optional[float] = Field(None, ge=0)
    max_salary: Optional[float] = Field(None, ge=0)
    is_management: Optional[bool] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None
    requirements: Optional[str] = None
    responsibilities: Optional[str] = None

    # F.3 MEDIUM: Leere Strings zu None konvertieren (Konsistenz)
    @field_validator('description', 'job_family', 'requirements', 'responsibilities', mode='before')
    @classmethod
    def empty_string_to_none(cls, v: Optional[str]) -> Optional[str]:
        """Konvertiert leere/whitespace-only Strings zu None."""
        if v is not None and isinstance(v, str) and len(v.strip()) == 0:
            return None
        return v


class DepartmentInfo(BaseModel):
    """Eingebettete Abteilungs-Info."""
    id: UUID
    name: str
    short_name: Optional[str] = None

    class Config:
        from_attributes = True


class PositionResponse(BaseModel):
    """Response-Schema fuer Position.

    Hinweis: Gehaltsfelder sind nur mit positions:read_salary sichtbar.
    """
    id: UUID
    title: str
    description: Optional[str] = None
    department_id: Optional[UUID] = None
    department: Optional[DepartmentInfo] = None
    level: Optional[int] = None
    job_family: Optional[str] = None
    min_salary: Optional[float] = None  # Nur mit positions:read_salary
    max_salary: Optional[float] = None  # Nur mit positions:read_salary
    salary_masked: bool = False  # True wenn Gehalt maskiert
    is_management: bool
    is_active: bool
    sort_order: int = 0
    employee_count: int = 0
    created_at: Optional[str] = None

    class Config:
        from_attributes = True


class PositionDetailResponse(PositionResponse):
    """Detaillierte Response mit zusaetzlichen Infos."""
    requirements: Optional[str] = None
    responsibilities: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


class PositionListResponse(BaseModel):
    """Paginierte Liste von Positionen."""
    items: List[PositionResponse]
    total: int
    page: int
    per_page: int
    total_pages: int


class JobFamilyStats(BaseModel):
    """Statistik pro Job-Familie."""
    job_family: str
    position_count: int
    employee_count: int


class MessageResponse(BaseModel):
    """Einfache Nachricht-Response."""
    message: str


# ==================== API Endpoints ====================

@router.get(
    "",
    response_model=PositionListResponse,
    summary="Positionen auflisten",
    description="Gibt alle Positionen mit optionaler Filterung und Paginierung zurueck. "
                "Erfordert Berechtigung: positions:read. "
                "Gehaltsfelder nur mit positions:read_salary sichtbar."
)
async def list_positions(
    request: Request,
    page: int = Query(1, ge=1, description="Seitennummer"),
    per_page: int = Query(20, ge=1, le=50, description="Eintraege pro Seite (max 50, F.4 MEDIUM)"),
    search: Optional[str] = Query(None, min_length=1, max_length=100, description="Suche (Titel)"),
    department_id: Optional[UUID] = Query(None, description="Filter nach Abteilung"),
    job_family: Optional[str] = Query(None, description="Filter nach Job-Familie"),
    is_management: Optional[bool] = Query(None, description="Nur Fuehrungspositionen"),
    include_inactive: bool = Query(False, description="Inaktive einbeziehen"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_position_read),
    company: Company = Depends(require_company),
    _rate_limit: User = Depends(check_rate_limit),  # A.2 CRITICAL: Rate Limiting
) -> PositionListResponse:
    """Liste der Positionen.

    Erfordert: positions:read
    Gehaltsfelder: Nur mit positions:read_salary sichtbar
    """
    # IP-Adresse fuer Audit-Log (A.1 CRITICAL: Audit-Logging fuer List-Operationen)
    ip_address = request.client.host if request.client else None

    # Pruefen ob User Gehaelter sehen darf
    perm_ctx = PermissionContext(db, current_user)
    can_see_salary = await perm_ctx.can("positions:read_salary")

    # Service-Delegation mit automatischer Gehalts-Maskierung
    positions, total = await position_service.list_positions(
        db=db,
        company_id=company.id,
        user_id=current_user.id,  # A.1 CRITICAL: Audit-Logging
        ip_address=ip_address,  # A.1 CRITICAL: Audit-Logging
        mask_salary=not can_see_salary,
        page=page,
        per_page=per_page,
        search=search,
        department_id=department_id,
        job_family=job_family,
        is_management=is_management,
        include_inactive=include_inactive,
    )

    return PositionListResponse(
        items=[_dict_to_position_response(p) for p in positions],
        total=total,
        page=page,
        per_page=per_page,
        total_pages=(total + per_page - 1) // per_page if total > 0 else 0,
    )


@router.get(
    "/job-families",
    response_model=List[JobFamilyStats],
    summary="Job-Familien auflisten",
    description="Gibt alle Job-Familien mit Statistiken zurueck. "
                "Erfordert Berechtigung: positions:read"
)
async def get_job_families(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_position_read),
    company: Company = Depends(require_company),
    _rate_limit: User = Depends(check_rate_limit),  # A.2 CRITICAL: Rate Limiting
) -> List[JobFamilyStats]:
    """Job-Familien mit Statistiken.

    Erfordert: positions:read
    """
    # Service-Delegation
    job_families_data = await position_service.get_job_families(
        db=db,
        company_id=company.id,
    )

    return [
        JobFamilyStats(
            job_family=jf['name'],
            position_count=jf['position_count'],
            employee_count=jf['employee_count'],
        )
        for jf in job_families_data
    ]


@router.post(
    "",
    response_model=PositionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Position anlegen",
    description="Erstellt eine neue Position. "
                "Erfordert Berechtigung: positions:write"
)
async def create_position(
    request: Request,
    data: PositionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_position_write),
    company: Company = Depends(require_company),
    _rate_limit: User = Depends(check_rate_limit),  # A.2 CRITICAL: Rate Limiting
) -> PositionResponse:
    """Erstellt eine neue Position.

    Erfordert: positions:write
    Audit-Log: POSITION_CREATED
    """
    # IP-Adresse fuer Audit-Log
    ip_address = request.client.host if request.client else None

    # Pruefen ob User Gehaelter sehen darf (A.3 CRITICAL: Gehalt-Maskierung in Response)
    perm_ctx = PermissionContext(db, current_user)
    can_see_salary = await perm_ctx.can("positions:read_salary")

    # Daten fuer Service vorbereiten (Feldnamen-Mapping)
    create_data = data.model_dump(exclude_unset=True)

    # min_salary/max_salary -> salary_band_min/salary_band_max
    if 'min_salary' in create_data:
        create_data['salary_band_min'] = create_data.pop('min_salary')
    if 'max_salary' in create_data:
        create_data['salary_band_max'] = create_data.pop('max_salary')

    try:
        # Service-Delegation mit Audit-Logging
        position_data = await position_service.create_position(
            db=db,
            company_id=company.id,
            user_id=current_user.id,
            data=create_data,
            ip_address=ip_address,
            mask_salary_in_response=not can_see_salary,  # A.3 CRITICAL: Gehalt-Leak Fix
        )

        return _dict_to_position_response(position_data)

    except ValueError as e:
        # F.1 CRITICAL: Sichere Error-Messages - keine interne Details leaken
        error_status, safe_message = _get_safe_error_response(e)
        logger.warning(
            "position_validation_error",
            error_detail=str(e),
            user_id=str(current_user.id),
            company_id=str(company.id),
            operation="create_position",
        )
        raise HTTPException(status_code=error_status, detail=safe_message)


@router.get(
    "/{position_id}",
    response_model=PositionDetailResponse,
    summary="Position abrufen",
    description="Gibt Details einer Position zurueck. "
                "Erfordert Berechtigung: positions:read. "
                "Gehaltsfelder nur mit positions:read_salary sichtbar."
)
async def get_position(
    request: Request,
    position_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_position_read),
    company: Company = Depends(require_company),
    _rate_limit: User = Depends(check_rate_limit),  # A.2 CRITICAL: Rate Limiting
) -> PositionDetailResponse:
    """Gibt eine Position zurueck.

    Erfordert: positions:read
    Gehaltsfelder: Nur mit positions:read_salary sichtbar
    Audit-Log: POSITION_ACCESSED (+ POSITION_SALARY_ACCESSED bei Gehaltszugriff)
    """
    # IP-Adresse fuer Audit-Log
    ip_address = request.client.host if request.client else None

    # Pruefen ob User Gehaelter sehen darf
    perm_ctx = PermissionContext(db, current_user)
    can_see_salary = await perm_ctx.can("positions:read_salary")

    # Service-Delegation mit Audit-Logging und Gehalts-Maskierung
    position_data = await position_service.get_position(
        db=db,
        position_id=position_id,
        company_id=company.id,
        user_id=current_user.id,
        mask_salary=not can_see_salary,
        ip_address=ip_address,
    )

    if not position_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Position nicht gefunden."
        )

    return _dict_to_detail_response(position_data)


@router.put(
    "/{position_id}",
    response_model=PositionResponse,
    summary="Position aktualisieren",
    description="Aktualisiert eine Position. "
                "Erfordert Berechtigung: positions:write"
)
async def update_position(
    request: Request,
    position_id: UUID,
    data: PositionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_position_write),
    company: Company = Depends(require_company),
    _rate_limit: User = Depends(check_rate_limit),  # A.2 CRITICAL: Rate Limiting
) -> PositionResponse:
    """Aktualisiert eine Position.

    Erfordert: positions:write
    Audit-Log: POSITION_UPDATED (Severity: warning bei Gehaltsaenderung)
    """
    # IP-Adresse fuer Audit-Log
    ip_address = request.client.host if request.client else None

    # Pruefen ob User Gehaelter sehen darf (A.3 CRITICAL: Gehalt-Maskierung in Response)
    perm_ctx = PermissionContext(db, current_user)
    can_see_salary = await perm_ctx.can("positions:read_salary")

    # Daten fuer Service vorbereiten (Feldnamen-Mapping)
    update_data = data.model_dump(exclude_unset=True)

    # min_salary/max_salary -> salary_band_min/salary_band_max
    if 'min_salary' in update_data:
        update_data['salary_band_min'] = update_data.pop('min_salary')
    if 'max_salary' in update_data:
        update_data['salary_band_max'] = update_data.pop('max_salary')

    try:
        # Service-Delegation mit Audit-Logging
        position_data = await position_service.update_position(
            db=db,
            position_id=position_id,
            company_id=company.id,
            user_id=current_user.id,
            data=update_data,
            ip_address=ip_address,
            mask_salary_in_response=not can_see_salary,  # A.3 CRITICAL: Gehalt-Leak Fix
        )

        if not position_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Position nicht gefunden."
            )

        return _dict_to_position_response(position_data)

    except ValueError as e:
        # F.1 CRITICAL: Sichere Error-Messages - keine interne Details leaken
        error_status, safe_message = _get_safe_error_response(e)
        logger.warning(
            "position_validation_error",
            error_detail=str(e),
            user_id=str(current_user.id),
            company_id=str(company.id),
            position_id=str(position_id),
            operation="update_position",
        )
        raise HTTPException(status_code=error_status, detail=safe_message)


@router.delete(
    "/{position_id}",
    response_model=MessageResponse,
    summary="Position loeschen",
    description="Loescht eine Position (Soft-Delete). "
                "Erfordert Berechtigung: positions:delete oder positions:manage"
)
async def delete_position(
    request: Request,
    position_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_position_delete),
    company: Company = Depends(require_company),
    _rate_limit: User = Depends(check_rate_limit),  # A.2 CRITICAL: Rate Limiting
) -> MessageResponse:
    """Loescht eine Position (Soft-Delete).

    Erfordert: positions:delete ODER positions:manage
    Audit-Log: POSITION_DELETED (Severity: warning)
    """
    # IP-Adresse fuer Audit-Log
    ip_address = request.client.host if request.client else None

    try:
        # Service-Delegation mit Audit-Logging
        success = await position_service.delete_position(
            db=db,
            position_id=position_id,
            company_id=company.id,
            user_id=current_user.id,
            ip_address=ip_address,
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Position nicht gefunden."
            )

        return MessageResponse(message="Position erfolgreich geloescht.")

    except ValueError as e:
        # F.1 CRITICAL: Sichere Error-Messages - keine interne Details leaken
        error_status, safe_message = _get_safe_error_response(e)
        logger.warning(
            "position_validation_error",
            error_detail=str(e),
            user_id=str(current_user.id),
            company_id=str(company.id),
            position_id=str(position_id),
            operation="delete_position",
        )
        raise HTTPException(status_code=error_status, detail=safe_message)


# ==================== Helper Functions ====================

def _dict_to_position_response(data: Dict[str, Any]) -> PositionResponse:
    """Konvertiert Service-Dict zu Response.

    Mappt salary_band_min/max -> min_salary/max_salary fuer API-Kompatibilitaet.
    """
    # Department-Info aufbauen falls vorhanden
    dept_data = data.get('department')
    department = None
    if dept_data:
        department = DepartmentInfo(
            id=UUID(dept_data['id']),
            name=dept_data['name'],
            short_name=dept_data.get('short_name'),
        )

    return PositionResponse(
        id=UUID(data['id']),
        title=data['title'],
        description=data.get('description'),
        department_id=UUID(data['department_id']) if data.get('department_id') else None,
        department=department,
        level=data.get('level'),
        job_family=data.get('job_family'),
        min_salary=data.get('salary_band_min'),  # Service -> API Mapping
        max_salary=data.get('salary_band_max'),  # Service -> API Mapping
        salary_masked=data.get('salary_masked', False),
        is_management=data.get('is_management', False),
        is_active=data.get('is_active', True),
        sort_order=data.get('sort_order', 0),
        employee_count=data.get('employee_count', 0),
        created_at=data.get('created_at'),
    )


def _dict_to_detail_response(data: Dict[str, Any]) -> PositionDetailResponse:
    """Konvertiert Service-Dict zu Detail-Response.

    Mappt salary_band_min/max -> min_salary/max_salary fuer API-Kompatibilitaet.
    """
    # Department-Info aufbauen falls vorhanden
    dept_data = data.get('department')
    department = None
    if dept_data:
        department = DepartmentInfo(
            id=UUID(dept_data['id']),
            name=dept_data['name'],
            short_name=dept_data.get('short_name'),
        )

    return PositionDetailResponse(
        id=UUID(data['id']),
        title=data['title'],
        description=data.get('description'),
        department_id=UUID(data['department_id']) if data.get('department_id') else None,
        department=department,
        level=data.get('level'),
        job_family=data.get('job_family'),
        min_salary=data.get('salary_band_min'),  # Service -> API Mapping
        max_salary=data.get('salary_band_max'),  # Service -> API Mapping
        salary_masked=data.get('salary_masked', False),
        is_management=data.get('is_management', False),
        is_active=data.get('is_active', True),
        sort_order=data.get('sort_order', 0),
        employee_count=data.get('employee_count', 0),
        requirements=data.get('requirements'),
        responsibilities=data.get('responsibilities'),
        created_at=data.get('created_at'),
        updated_at=data.get('updated_at'),
    )

"""
Employee API Endpoints - Mitarbeiter-Verwaltung (Enterprise Security).

CRUD-Operationen fuer Mitarbeiter-Stammdaten mit:
- RBAC-basierter Zugriffskontrolle
- PII-Maskierung fuer Non-HR-User
- Audit-Logging aller Operationen

Alle Antworten auf Deutsch.
"""

import re
from datetime import date
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.api.dependencies import get_db, get_current_active_user, check_rate_limit
from app.db.models import User, Company, EmployeeStatus, EmploymentType
from app.middleware.company_context import require_company
from app.core.rbac import (
    require_permission,
    require_any_permission,
    PermissionContext,
)
from app.services.personal import employee_service

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/employees", tags=["Personal - Mitarbeiter"])


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
    elif 'zyklisch' in error_msg or 'cycle' in error_msg or 'eigener vorgesetzter' in error_msg:
        return status.HTTP_400_BAD_REQUEST, "Diese Aenderung wuerde eine ungueltige Struktur erzeugen."
    elif 'berechtigung' in error_msg or 'permission' in error_msg or 'zugriff' in error_msg:
        return status.HTTP_403_FORBIDDEN, "Keine Berechtigung fuer diese Aktion."
    elif 'ungueltig' in error_msg or 'invalid' in error_msg or 'format' in error_msg:
        return status.HTTP_400_BAD_REQUEST, "Die Eingabedaten sind ungueltig."
    else:
        return status.HTTP_400_BAD_REQUEST, "Die Anfrage konnte nicht verarbeitet werden."


# ==================== Pydantic Schemas ====================

class EmployeeBase(BaseModel):
    """Basis-Schema fuer Mitarbeiter."""
    employee_number: str = Field(..., min_length=1, max_length=50, description="Personalnummer")
    salutation: Optional[str] = Field(None, max_length=20, description="Anrede (Herr/Frau)")
    title: Optional[str] = Field(None, max_length=50, description="Titel (Dr., Prof.)")
    first_name: str = Field(..., min_length=1, max_length=100, description="Vorname")
    last_name: str = Field(..., min_length=1, max_length=100, description="Nachname")
    birth_name: Optional[str] = Field(None, max_length=100, description="Geburtsname")
    date_of_birth: Optional[date] = Field(None, description="Geburtsdatum")
    place_of_birth: Optional[str] = Field(None, max_length=100, description="Geburtsort")
    nationality: Optional[str] = Field(None, max_length=50, description="Staatsangehoerigkeit")
    gender: Optional[str] = Field(None, max_length=20, description="Geschlecht")

    # Kontakt geschaeftlich
    email: Optional[str] = Field(None, max_length=255, description="Geschaeftliche E-Mail")
    phone: Optional[str] = Field(None, max_length=50, description="Telefon geschaeftlich")
    mobile: Optional[str] = Field(None, max_length=50, description="Mobiltelefon")

    # Kontakt privat
    private_email: Optional[str] = Field(None, max_length=255, description="Private E-Mail")
    private_phone: Optional[str] = Field(None, max_length=50, description="Telefon privat")

    # Adresse privat
    street: Optional[str] = Field(None, max_length=255, description="Strasse")
    street_number: Optional[str] = Field(None, max_length=20, description="Hausnummer")
    postal_code: Optional[str] = Field(None, max_length=10, description="PLZ")
    city: Optional[str] = Field(None, max_length=100, description="Stadt")
    country: Optional[str] = Field("DE", max_length=2, description="Land (ISO 2)")

    # Notfall-Kontakt
    emergency_contact_name: Optional[str] = Field(None, max_length=200, description="Notfall-Kontakt Name")
    emergency_contact_phone: Optional[str] = Field(None, max_length=50, description="Notfall-Kontakt Telefon")
    emergency_contact_relation: Optional[str] = Field(None, max_length=50, description="Beziehung")

    # Organisatorisch
    department_id: Optional[UUID] = Field(None, description="Abteilung")
    position_id: Optional[UUID] = Field(None, description="Position")
    supervisor_id: Optional[UUID] = Field(None, description="Vorgesetzter")

    # Beschaeftigung - B.6 HIGH: Enum-Validierung
    employment_type: Optional[EmploymentType] = Field(
        EmploymentType.FULL_TIME,
        description="Beschaeftigungsart (full_time, part_time, mini_job, temporary, trainee, intern, freelance)"
    )
    status: Optional[EmployeeStatus] = Field(
        EmployeeStatus.ACTIVE,
        description="Status (onboarding, active, on_leave, sick, notice_period, terminated)"
    )
    hire_date: Optional[date] = Field(None, description="Eintrittsdatum")
    probation_end_date: Optional[date] = Field(None, description="Probezeitende")
    termination_date: Optional[date] = Field(None, description="Austrittsdatum")

    # Arbeitszeit - B.6 HIGH: Validierung gegen negative Werte
    weekly_hours: Optional[float] = Field(40.0, ge=0, le=168, description="Wochenstunden (0-168)")
    vacation_days_per_year: Optional[int] = Field(30, ge=0, le=365, description="Urlaubstage pro Jahr (0-365)")

    # Steuer & Sozialversicherung
    tax_id: Optional[str] = Field(None, max_length=20, description="Steuer-ID")
    tax_class: Optional[int] = Field(None, ge=1, le=6, description="Steuerklasse (1-6)")
    social_security_number: Optional[str] = Field(None, max_length=20, description="SV-Nummer")
    health_insurance: Optional[str] = Field(None, max_length=100, description="Krankenkasse")
    health_insurance_number: Optional[str] = Field(None, max_length=50, description="KV-Nummer")

    # Banking
    iban: Optional[str] = Field(None, max_length=34, description="IBAN")
    bic: Optional[str] = Field(None, max_length=11, description="BIC")
    bank_name: Optional[str] = Field(None, max_length=100, description="Bank")

    # C.2 MEDIUM: IBAN Validierung
    @field_validator('iban')
    @classmethod
    def validate_iban(cls, v: Optional[str]) -> Optional[str]:
        """Validiert IBAN-Format."""
        if v is None or v.strip() == '':
            return None
        # Leerzeichen entfernen und uppercase
        v = v.replace(' ', '').upper()
        # IBAN Format: 2 Buchstaben Laendercode + 2 Prüfziffern + 10-30 alphanumerische Zeichen
        # Beispiel DE: DE89370400440532013000 (22 Zeichen)
        if not re.match(r'^[A-Z]{2}[0-9]{2}[A-Z0-9]{10,30}$', v):
            raise ValueError('Ungueltig')  # G.1 CRITICAL: Keine Format-Details leaken!
        return v

    # C.2 MEDIUM: BIC Validierung
    @field_validator('bic')
    @classmethod
    def validate_bic(cls, v: Optional[str]) -> Optional[str]:
        """Validiert BIC/SWIFT-Format."""
        if v is None or v.strip() == '':
            return None
        # Leerzeichen entfernen und uppercase
        v = v.replace(' ', '').upper()
        # BIC Format: 4 Buchstaben (Bank) + 2 Buchstaben (Land) + 2 alphanumerisch (Ort) + optional 3 alphanumerisch (Filiale)
        # Beispiel: COBADEFFXXX (11 Zeichen) oder COBADEFF (8 Zeichen)
        if not re.match(r'^[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}([A-Z0-9]{3})?$', v):
            raise ValueError('Ungueltig')  # G.1 CRITICAL: Keine Format-Details leaken!
        return v

    class Config:
        from_attributes = True


class EmployeeCreate(EmployeeBase):
    """Schema fuer Mitarbeiter-Erstellung."""
    pass


class EmployeeUpdate(BaseModel):
    """Schema fuer Mitarbeiter-Update (alle Felder optional).

    B.6 HIGH: Enum-Felder werden bei Update validiert.
    """
    employee_number: Optional[str] = Field(None, min_length=1, max_length=50)
    salutation: Optional[str] = Field(None, max_length=20)
    title: Optional[str] = Field(None, max_length=50)
    first_name: Optional[str] = Field(None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, min_length=1, max_length=100)
    birth_name: Optional[str] = None
    date_of_birth: Optional[date] = None
    place_of_birth: Optional[str] = None
    nationality: Optional[str] = None
    gender: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    mobile: Optional[str] = None
    private_email: Optional[str] = None
    private_phone: Optional[str] = None
    street: Optional[str] = None
    street_number: Optional[str] = None
    postal_code: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    emergency_contact_relation: Optional[str] = None
    department_id: Optional[UUID] = None
    position_id: Optional[UUID] = None
    supervisor_id: Optional[UUID] = None
    # B.6 HIGH: Enum-Validierung fuer Update
    employment_type: Optional[EmploymentType] = None
    status: Optional[EmployeeStatus] = None
    hire_date: Optional[date] = None
    probation_end_date: Optional[date] = None
    termination_date: Optional[date] = None
    # B.6 HIGH: Validierung gegen negative Werte
    weekly_hours: Optional[float] = Field(None, ge=0, le=168)
    vacation_days_per_year: Optional[int] = Field(None, ge=0, le=365)
    tax_id: Optional[str] = None
    tax_class: Optional[int] = Field(None, ge=1, le=6)
    social_security_number: Optional[str] = None
    health_insurance: Optional[str] = None
    health_insurance_number: Optional[str] = None
    iban: Optional[str] = None
    bic: Optional[str] = None
    bank_name: Optional[str] = None
    photo_path: Optional[str] = None

    # G.3 HIGH: Leere Strings zu None konvertieren (Konsistenz mit Department/Position)
    @field_validator(
        'salutation', 'title', 'birth_name', 'place_of_birth', 'nationality',
        'gender', 'email', 'phone', 'mobile', 'private_email', 'private_phone',
        'street', 'street_number', 'postal_code', 'city', 'country',
        'emergency_contact_name', 'emergency_contact_phone', 'emergency_contact_relation',
        'health_insurance', 'bank_name', 'tax_id', 'social_security_number',
        'health_insurance_number',
        mode='before'
    )
    @classmethod
    def empty_string_to_none(cls, v: Optional[str]) -> Optional[str]:
        """Konvertiert leere/whitespace-only Strings zu None."""
        if v is not None and isinstance(v, str) and len(v.strip()) == 0:
            return None
        return v

    # G.4 MEDIUM: Path Traversal Prevention im Schema
    @field_validator('photo_path', mode='before')
    @classmethod
    def validate_photo_path(cls, v: Optional[str]) -> Optional[str]:
        """Validiert photo_path gegen Path Traversal."""
        import os

        if v is None or (isinstance(v, str) and len(v.strip()) == 0):
            return None

        if not isinstance(v, str):
            raise ValueError('Ungueltig')

        # Nur Dateiname, keine Pfade
        photo_filename = os.path.basename(v)
        if not re.match(r'^[\w\-\.]+$', photo_filename):
            raise ValueError('Ungueltig')
        if photo_filename.startswith('.'):
            raise ValueError('Ungueltig')

        allowed_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
        file_ext = os.path.splitext(photo_filename)[1].lower()
        if file_ext not in allowed_extensions:
            raise ValueError('Ungueltig')

        return photo_filename

    # C.2 MEDIUM: IBAN Validierung (auch bei Update)
    @field_validator('iban')
    @classmethod
    def validate_iban(cls, v: Optional[str]) -> Optional[str]:
        """Validiert IBAN-Format."""
        if v is None or v.strip() == '':
            return None
        v = v.replace(' ', '').upper()
        if not re.match(r'^[A-Z]{2}[0-9]{2}[A-Z0-9]{10,30}$', v):
            raise ValueError('Ungueltig')  # G.1 CRITICAL: Keine Format-Details leaken!
        return v

    # C.2 MEDIUM: BIC Validierung (auch bei Update)
    @field_validator('bic')
    @classmethod
    def validate_bic(cls, v: Optional[str]) -> Optional[str]:
        """Validiert BIC/SWIFT-Format."""
        if v is None or v.strip() == '':
            return None
        v = v.replace(' ', '').upper()
        if not re.match(r'^[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}([A-Z0-9]{3})?$', v):
            raise ValueError('Ungueltig')  # G.1 CRITICAL: Keine Format-Details leaken!
        return v


class DepartmentInfo(BaseModel):
    """Eingebettete Abteilungs-Info."""
    id: UUID
    name: str
    short_name: Optional[str] = None

    class Config:
        from_attributes = True


class PositionInfo(BaseModel):
    """Eingebettete Positions-Info."""
    id: UUID
    title: str
    level: Optional[int] = None

    class Config:
        from_attributes = True


class EmployeeResponse(BaseModel):
    """Response-Schema fuer Mitarbeiter."""
    id: UUID
    employee_number: str
    salutation: Optional[str] = None
    title: Optional[str] = None
    first_name: str
    last_name: str
    full_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    mobile: Optional[str] = None
    department: Optional[DepartmentInfo] = None
    position: Optional[PositionInfo] = None
    employment_type: str
    status: str
    hire_date: Optional[date] = None
    photo_path: Optional[str] = None
    created_at: Optional[str] = None

    class Config:
        from_attributes = True


class EmployeeDetailResponse(EmployeeBase):
    """Detaillierte Response mit allen Feldern."""
    id: UUID
    full_name: str
    department: Optional[DepartmentInfo] = None
    position: Optional[PositionInfo] = None
    photo_path: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


class EmployeeListResponse(BaseModel):
    """Paginierte Liste von Mitarbeitern."""
    items: List[EmployeeResponse]
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
    response_model=EmployeeListResponse,
    summary="Mitarbeiter auflisten",
    description="Gibt alle Mitarbeiter mit optionaler Filterung und Paginierung zurueck. "
                "PII-Felder werden ohne 'employees:read_pii' Berechtigung maskiert."
)
async def list_employees(
    request: Request,
    page: int = Query(1, ge=1, description="Seitennummer"),
    per_page: int = Query(20, ge=1, le=100, description="Eintraege pro Seite (max 100)"),
    search: Optional[str] = Query(None, min_length=1, max_length=100, description="Suche (Name, E-Mail, Personalnummer)"),
    department_id: Optional[UUID] = Query(None, description="Filter nach Abteilung"),
    position_id: Optional[UUID] = Query(None, description="Filter nach Position"),
    status_filter: Optional[str] = Query(None, description="Filter nach Status", alias="status"),
    employment_type: Optional[str] = Query(None, description="Filter nach Beschaeftigungsart"),
    sort_by: str = Query("last_name", description="Sortierfeld"),
    sort_order: str = Query("asc", description="Sortierrichtung (asc/desc)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("employees:read")),
    company: Company = Depends(require_company),
    _rate_limit: User = Depends(check_rate_limit),  # A.2 CRITICAL: Rate Limiting
) -> EmployeeListResponse:
    """Liste der Mitarbeiter mit optionaler PII-Maskierung."""

    # Pruefen ob User PII-Zugriff hat
    perm_ctx = PermissionContext(db, current_user)
    has_pii_access = await perm_ctx.can("employees:read_pii")

    # IP-Adresse fuer Audit-Log (A.1 CRITICAL: Audit-Logging fuer List-Operationen)
    ip_address = request.client.host if request.client else None

    # Service-Aufruf mit PII-Maskierung
    employees, total = await employee_service.list_employees(
        db=db,
        company_id=company.id,
        user_id=current_user.id,
        mask_pii=not has_pii_access,
        ip_address=ip_address,  # A.1 CRITICAL: Audit-Logging
        page=page,
        per_page=per_page,
        search=search,
        department_id=department_id,
        position_id=position_id,
        status_filter=status_filter,
        employment_type=employment_type,
        sort_by=sort_by,
        sort_order=sort_order,
    )

    return EmployeeListResponse(
        items=[_dict_to_employee_response(e) for e in employees],
        total=total,
        page=page,
        per_page=per_page,
        total_pages=(total + per_page - 1) // per_page if total > 0 else 0,
    )


@router.post(
    "",
    response_model=EmployeeDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Mitarbeiter anlegen",
    description="Erstellt einen neuen Mitarbeiter. Erfordert 'employees:write' Berechtigung."
)
async def create_employee(
    request: Request,
    data: EmployeeCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("employees:write")),
    company: Company = Depends(require_company),
    _rate_limit: User = Depends(check_rate_limit),  # A.2 CRITICAL: Rate Limiting
) -> EmployeeDetailResponse:
    """Erstellt einen neuen Mitarbeiter mit Audit-Logging."""

    ip_address = request.client.host if request.client else None

    try:
        employee_dict = await employee_service.create_employee(
            db=db,
            company_id=company.id,
            user_id=current_user.id,
            data=data.model_dump(exclude_unset=True),
            ip_address=ip_address,
        )
    except ValueError as e:
        # F.1 CRITICAL: Sichere Error-Messages - keine interne Details leaken
        error_status, safe_message = _get_safe_error_response(e)
        logger.warning(
            "employee_validation_error",
            error_detail=str(e),
            user_id=str(current_user.id),
            company_id=str(company.id),
        )
        raise HTTPException(status_code=error_status, detail=safe_message)

    return _dict_to_employee_detail_response(employee_dict)


@router.get(
    "/{employee_id}",
    response_model=EmployeeDetailResponse,
    summary="Mitarbeiter abrufen",
    description="Gibt Details eines Mitarbeiters zurueck. "
                "PII-Felder werden ohne 'employees:read_pii' Berechtigung maskiert."
)
async def get_employee(
    request: Request,
    employee_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("employees:read")),
    company: Company = Depends(require_company),
    _rate_limit: User = Depends(check_rate_limit),  # A.2 CRITICAL: Rate Limiting
) -> EmployeeDetailResponse:
    """Gibt einen Mitarbeiter mit optionaler PII-Maskierung zurueck."""

    # Pruefen ob User PII-Zugriff hat
    perm_ctx = PermissionContext(db, current_user)
    has_pii_access = await perm_ctx.can("employees:read_pii")
    ip_address = request.client.host if request.client else None

    employee_dict = await employee_service.get_employee(
        db=db,
        employee_id=employee_id,
        company_id=company.id,
        user_id=current_user.id,
        mask_pii=not has_pii_access,
        ip_address=ip_address,
    )

    if not employee_dict:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mitarbeiter nicht gefunden."
        )

    return _dict_to_employee_detail_response(employee_dict)


@router.put(
    "/{employee_id}",
    response_model=EmployeeDetailResponse,
    summary="Mitarbeiter aktualisieren",
    description="Aktualisiert einen Mitarbeiter. Erfordert 'employees:write' Berechtigung."
)
async def update_employee(
    request: Request,
    employee_id: UUID,
    data: EmployeeUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("employees:write")),
    company: Company = Depends(require_company),
    _rate_limit: User = Depends(check_rate_limit),  # A.2 CRITICAL: Rate Limiting
) -> EmployeeDetailResponse:
    """Aktualisiert einen Mitarbeiter mit Audit-Logging."""

    ip_address = request.client.host if request.client else None

    employee_dict = await employee_service.update_employee(
        db=db,
        employee_id=employee_id,
        company_id=company.id,
        user_id=current_user.id,
        data=data.model_dump(exclude_unset=True),
        ip_address=ip_address,
    )

    if not employee_dict:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mitarbeiter nicht gefunden."
        )

    return _dict_to_employee_detail_response(employee_dict)


@router.delete(
    "/{employee_id}",
    response_model=MessageResponse,
    summary="Mitarbeiter loeschen",
    description="Loescht einen Mitarbeiter (Soft-Delete). "
                "Erfordert 'employees:delete' oder 'employees:manage' Berechtigung."
)
async def delete_employee(
    request: Request,
    employee_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_permission("employees:delete", "employees:manage")),
    company: Company = Depends(require_company),
    _rate_limit: User = Depends(check_rate_limit),  # A.2 CRITICAL: Rate Limiting
) -> MessageResponse:
    """Loescht einen Mitarbeiter (Soft-Delete) mit Audit-Logging."""

    ip_address = request.client.host if request.client else None

    success = await employee_service.delete_employee(
        db=db,
        employee_id=employee_id,
        company_id=company.id,
        user_id=current_user.id,
        ip_address=ip_address,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mitarbeiter nicht gefunden."
        )

    return MessageResponse(message="Mitarbeiter erfolgreich geloescht.")


# ==================== Helper Functions ====================

def _dict_to_employee_response(data: dict) -> EmployeeResponse:
    """Konvertiert Dict zu EmployeeResponse."""
    return EmployeeResponse(
        id=UUID(data['id']) if isinstance(data['id'], str) else data['id'],
        employee_number=data['employee_number'],
        salutation=data.get('salutation'),
        title=data.get('title'),
        first_name=data['first_name'],
        last_name=data['last_name'],
        full_name=data.get('full_name', f"{data['first_name']} {data['last_name']}"),
        email=data.get('email'),
        phone=data.get('phone'),
        mobile=data.get('mobile'),
        department=DepartmentInfo(**data['department']) if data.get('department') else None,
        position=PositionInfo(**data['position']) if data.get('position') else None,
        employment_type=data.get('employment_type', EmploymentType.FULL_TIME.value),
        status=data.get('status', EmployeeStatus.ACTIVE.value),
        hire_date=date.fromisoformat(data['hire_date']) if data.get('hire_date') else None,
        photo_path=data.get('photo_path'),
        created_at=data.get('created_at'),
    )


def _dict_to_employee_detail_response(data: dict) -> EmployeeDetailResponse:
    """Konvertiert Dict zu EmployeeDetailResponse (mit optionaler PII-Maskierung)."""
    return EmployeeDetailResponse(
        id=UUID(data['id']) if isinstance(data['id'], str) else data['id'],
        employee_number=data['employee_number'],
        salutation=data.get('salutation'),
        title=data.get('title'),
        first_name=data['first_name'],
        last_name=data['last_name'],
        full_name=data.get('full_name', f"{data['first_name']} {data['last_name']}"),
        birth_name=data.get('birth_name'),
        date_of_birth=date.fromisoformat(data['date_of_birth']) if data.get('date_of_birth') else None,
        place_of_birth=data.get('place_of_birth'),
        nationality=data.get('nationality'),
        gender=data.get('gender'),
        email=data.get('email'),
        phone=data.get('phone'),
        mobile=data.get('mobile'),
        private_email=data.get('private_email'),
        private_phone=data.get('private_phone'),
        street=data.get('street'),
        street_number=data.get('street_number'),
        postal_code=data.get('postal_code'),
        city=data.get('city'),
        country=data.get('country', 'DE'),
        emergency_contact_name=data.get('emergency_contact_name'),
        emergency_contact_phone=data.get('emergency_contact_phone'),
        emergency_contact_relation=data.get('emergency_contact_relation'),
        department_id=UUID(data['department_id']) if data.get('department_id') else None,
        position_id=UUID(data['position_id']) if data.get('position_id') else None,
        supervisor_id=UUID(data['supervisor_id']) if data.get('supervisor_id') else None,
        department=DepartmentInfo(**data['department']) if data.get('department') else None,
        position=PositionInfo(**data['position']) if data.get('position') else None,
        employment_type=data.get('employment_type', EmploymentType.FULL_TIME.value),
        status=data.get('status', EmployeeStatus.ACTIVE.value),
        hire_date=date.fromisoformat(data['hire_date']) if data.get('hire_date') else None,
        probation_end_date=date.fromisoformat(data['probation_end_date']) if data.get('probation_end_date') else None,
        termination_date=date.fromisoformat(data['termination_date']) if data.get('termination_date') else None,
        weekly_hours=data.get('weekly_hours'),
        vacation_days_per_year=data.get('vacation_days_per_year'),
        tax_id=data.get('tax_id'),
        tax_class=data.get('tax_class'),
        social_security_number=data.get('social_security_number'),
        health_insurance=data.get('health_insurance'),
        health_insurance_number=data.get('health_insurance_number'),
        iban=data.get('iban'),
        bic=data.get('bic'),
        bank_name=data.get('bank_name'),
        photo_path=data.get('photo_path'),
        created_at=data.get('created_at'),
        updated_at=data.get('updated_at'),
    )

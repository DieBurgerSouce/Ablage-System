"""
Personal API Endpoints

Mitarbeiterverwaltung, Abteilungen und Positionen.
"""

from datetime import date, datetime
from app.core.datetime_utils import utc_now
from decimal import Decimal
from typing import Optional, List
from uuid import UUID
import structlog

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, func, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies import get_current_active_user, get_db
from app.db.models import (
    User,
    Employee,
    Department,
    Position,
    EmployeeStatus,
    EmploymentType,
    Company,
    UserCompany,  # SECURITY FIX: Für Multi-Tenant Zugriffskontrolle
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/personal", tags=["Personal"])


# =============================================================================
# SCHEMAS
# =============================================================================

class DepartmentInfoSchema(BaseModel):
    """Minimale Abteilungsinformationen."""
    id: UUID
    name: str
    short_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class PositionInfoSchema(BaseModel):
    """Minimale Positionsinformationen."""
    id: UUID
    title: str
    level: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class ManagerInfoSchema(BaseModel):
    """Minimale Manager-Informationen."""
    id: UUID
    first_name: str
    last_name: str
    full_name: str


# Employee Schemas

class EmployeeSchema(BaseModel):
    """Mitarbeiter-Uebersicht."""
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
    department: Optional[DepartmentInfoSchema] = None
    position: Optional[PositionInfoSchema] = None
    employment_type: str
    status: str
    hire_date: Optional[date] = None
    photo_path: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class EmployeeDetailSchema(EmployeeSchema):
    """Detaillierte Mitarbeiterdaten."""
    birth_name: Optional[str] = None
    date_of_birth: Optional[date] = None
    place_of_birth: Optional[str] = None
    nationality: Optional[str] = None
    gender: Optional[str] = None
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
    probation_end_date: Optional[date] = None
    termination_date: Optional[date] = None
    weekly_hours: Optional[Decimal] = None
    vacation_days_per_year: Optional[int] = None
    tax_id: Optional[str] = None
    tax_class: Optional[str] = None
    social_security_number: Optional[str] = None
    health_insurance: Optional[str] = None
    health_insurance_number: Optional[str] = None
    iban: Optional[str] = None
    bic: Optional[str] = None
    bank_name: Optional[str] = None
    updated_at: Optional[datetime] = None


class EmployeeCreateSchema(BaseModel):
    """Mitarbeiter erstellen."""
    employee_number: str
    salutation: Optional[str] = None
    title: Optional[str] = None
    first_name: str
    last_name: str
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
    country: Optional[str] = "DE"
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    emergency_contact_relation: Optional[str] = None
    department_id: Optional[UUID] = None
    position_id: Optional[UUID] = None
    supervisor_id: Optional[UUID] = None
    employment_type: Optional[str] = "full_time"
    status: Optional[str] = "active"
    hire_date: Optional[date] = None
    probation_end_date: Optional[date] = None
    termination_date: Optional[date] = None
    weekly_hours: Optional[Decimal] = Decimal("40")
    vacation_days_per_year: Optional[int] = 30
    tax_id: Optional[str] = None
    tax_class: Optional[str] = None
    social_security_number: Optional[str] = None
    health_insurance: Optional[str] = None
    health_insurance_number: Optional[str] = None
    iban: Optional[str] = None
    bic: Optional[str] = None
    bank_name: Optional[str] = None


class EmployeeUpdateSchema(BaseModel):
    """Mitarbeiter aktualisieren."""
    employee_number: Optional[str] = None
    salutation: Optional[str] = None
    title: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
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
    employment_type: Optional[str] = None
    status: Optional[str] = None
    hire_date: Optional[date] = None
    probation_end_date: Optional[date] = None
    termination_date: Optional[date] = None
    weekly_hours: Optional[Decimal] = None
    vacation_days_per_year: Optional[int] = None
    tax_id: Optional[str] = None
    tax_class: Optional[str] = None
    social_security_number: Optional[str] = None
    health_insurance: Optional[str] = None
    health_insurance_number: Optional[str] = None
    iban: Optional[str] = None
    bic: Optional[str] = None
    bank_name: Optional[str] = None


class EmployeeListResponse(BaseModel):
    """Paginierte Mitarbeiterliste."""
    items: List[EmployeeSchema]
    total: int
    page: int
    per_page: int
    total_pages: int


# Department Schemas

class DepartmentSchema(BaseModel):
    """Abteilung."""
    id: UUID
    name: str
    short_name: Optional[str] = None
    description: Optional[str] = None
    cost_center: Optional[str] = None
    parent_id: Optional[UUID] = None
    manager_id: Optional[UUID] = None
    manager: Optional[ManagerInfoSchema] = None
    is_active: bool = True
    sort_order: int = 0
    employee_count: int = 0
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class DepartmentDetailSchema(DepartmentSchema):
    """Detaillierte Abteilungsdaten."""
    children: List["DepartmentSchema"] = []
    updated_at: Optional[datetime] = None


class DepartmentTreeItemSchema(BaseModel):
    """Abteilungsbaum-Element."""
    id: UUID
    name: str
    short_name: Optional[str] = None
    parent_id: Optional[UUID] = None
    manager_id: Optional[UUID] = None
    manager_name: Optional[str] = None
    employee_count: int = 0
    is_active: bool = True
    sort_order: int = 0
    level: int = 0
    children: List["DepartmentTreeItemSchema"] = []


class DepartmentCreateSchema(BaseModel):
    """Abteilung erstellen."""
    name: str
    short_name: Optional[str] = None
    description: Optional[str] = None
    cost_center: Optional[str] = None
    parent_id: Optional[UUID] = None
    manager_id: Optional[UUID] = None
    is_active: bool = True
    sort_order: int = 0


class DepartmentUpdateSchema(BaseModel):
    """Abteilung aktualisieren."""
    name: Optional[str] = None
    short_name: Optional[str] = None
    description: Optional[str] = None
    cost_center: Optional[str] = None
    parent_id: Optional[UUID] = None
    manager_id: Optional[UUID] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class DepartmentListResponse(BaseModel):
    """Paginierte Abteilungsliste."""
    items: List[DepartmentSchema]
    total: int
    page: int
    per_page: int
    total_pages: int


# Position Schemas

class PositionSchema(BaseModel):
    """Position/Stelle."""
    id: UUID
    title: str
    description: Optional[str] = None
    department_id: Optional[UUID] = None
    department: Optional[DepartmentInfoSchema] = None
    level: Optional[int] = 1
    job_family: Optional[str] = None
    min_salary: Optional[Decimal] = None
    max_salary: Optional[Decimal] = None
    is_management: bool = False
    is_active: bool = True
    sort_order: int = 0
    employee_count: int = 0
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class PositionDetailSchema(PositionSchema):
    """Detaillierte Positionsdaten."""
    requirements: Optional[str] = None
    responsibilities: Optional[str] = None
    updated_at: Optional[datetime] = None


class PositionCreateSchema(BaseModel):
    """Position erstellen."""
    title: str
    description: Optional[str] = None
    department_id: Optional[UUID] = None
    level: Optional[int] = 1
    job_family: Optional[str] = None
    min_salary: Optional[Decimal] = None
    max_salary: Optional[Decimal] = None
    is_management: bool = False
    is_active: bool = True
    sort_order: int = 0
    requirements: Optional[str] = None
    responsibilities: Optional[str] = None


class PositionUpdateSchema(BaseModel):
    """Position aktualisieren."""
    title: Optional[str] = None
    description: Optional[str] = None
    department_id: Optional[UUID] = None
    level: Optional[int] = None
    job_family: Optional[str] = None
    min_salary: Optional[Decimal] = None
    max_salary: Optional[Decimal] = None
    is_management: Optional[bool] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None
    requirements: Optional[str] = None
    responsibilities: Optional[str] = None


class PositionListResponse(BaseModel):
    """Paginierte Positionsliste."""
    items: List[PositionSchema]
    total: int
    page: int
    per_page: int
    total_pages: int


class JobFamilyStats(BaseModel):
    """Job-Family Statistiken."""
    job_family: str
    position_count: int
    employee_count: int


# Update forward references
DepartmentTreeItemSchema.model_rebuild()
DepartmentDetailSchema.model_rebuild()


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def employee_to_schema(emp: Employee, department: Optional[Department] = None,
                       position: Optional[Position] = None) -> EmployeeSchema:
    """Konvertiert Employee-Model zu Schema."""
    dept_info = None
    if department or emp.department_id:
        dept = department or getattr(emp, 'department', None)
        if dept:
            dept_info = DepartmentInfoSchema(
                id=dept.id,
                name=dept.name,
                short_name=dept.short_name
            )

    pos_info = None
    if position or emp.position_id:
        pos = position or getattr(emp, 'position', None)
        if pos:
            pos_info = PositionInfoSchema(
                id=pos.id,
                title=pos.title,
                level=pos.level
            )

    return EmployeeSchema(
        id=emp.id,
        employee_number=emp.employee_number,
        salutation=emp.salutation,
        title=emp.title,
        first_name=emp.first_name,
        last_name=emp.last_name,
        full_name=f"{emp.first_name} {emp.last_name}",
        email=emp.email,
        phone=emp.phone,
        mobile=emp.mobile,
        department=dept_info,
        position=pos_info,
        employment_type=emp.employment_type or "full_time",
        status=emp.status or "active",
        hire_date=emp.hire_date,
        photo_path=emp.photo_path,
        created_at=emp.created_at,
    )


async def get_company_id_for_user(db: AsyncSession, user: User) -> Optional[UUID]:
    """Ermittelt die Company-ID fuer den aktuellen User via UserCompany-Tabelle.

    SECURITY FIX: Diese Funktion validiert jetzt den Zugriff über die UserCompany-Tabelle,
    um Multi-Tenant-Isolation sicherzustellen. Ein User kann nur auf Firmen zugreifen,
    für die ein entsprechender UserCompany-Eintrag existiert.

    Reihenfolge:
    1. UserCompany mit is_current=True (aktiv ausgewählte Firma)
    2. Erste verfügbare UserCompany (Fallback)

    Returns:
        Company-ID oder None wenn keine Zuordnung existiert
    """
    # 1. Hole aktuelle Firma (is_current=True) über UserCompany-Tabelle
    # SECURITY: Nur Firmen mit explizitem UserCompany-Link sind erlaubt
    result = await db.execute(
        select(UserCompany.company_id)
        .where(UserCompany.user_id == user.id)
        .where(UserCompany.is_current == True)
    )
    current_company_id = result.scalar_one_or_none()

    if current_company_id:
        # Validiere dass Firma aktiv ist
        company_result = await db.execute(
            select(Company.id)
            .where(Company.id == current_company_id)
            .where(Company.is_active == True)
            .where(Company.deleted_at.is_(None))
        )
        if company_result.scalar_one_or_none():
            return current_company_id

    # 2. Fallback: Erste verfügbare Firma des Users über UserCompany
    result = await db.execute(
        select(UserCompany.company_id)
        .join(Company, Company.id == UserCompany.company_id)
        .where(UserCompany.user_id == user.id)
        .where(Company.is_active == True)
        .where(Company.deleted_at.is_(None))
        .order_by(UserCompany.created_at)
        .limit(1)
    )
    fallback_company_id = result.scalar_one_or_none()

    if fallback_company_id:
        logger.debug(
            "personal_company_fallback",
            user_id=str(user.id),
            company_id=str(fallback_company_id),
            message="Keine is_current Firma, verwende erste verfügbare"
        )
        return fallback_company_id

    # Keine Firmenzuordnung gefunden
    logger.debug(
        "personal_no_company_for_user",
        user_id=str(user.id),
        message="User hat keine Firmenzuordnung in UserCompany"
    )
    return None


# =============================================================================
# EMPLOYEE ENDPOINTS
# =============================================================================

@router.get("/employees", response_model=EmployeeListResponse)
async def list_employees(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    department_id: Optional[UUID] = Query(None),
    position_id: Optional[UUID] = Query(None),
    status: Optional[str] = Query(None),
    employment_type: Optional[str] = Query(None),
    sort_by: Optional[str] = Query("last_name"),
    sort_order: Optional[str] = Query("asc"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Listet alle Mitarbeiter auf."""
    company_id = await get_company_id_for_user(db, current_user)
    if not company_id:
        return EmployeeListResponse(
            items=[],
            total=0,
            page=page,
            per_page=per_page,
            total_pages=0,
        )

    # Base query
    query = select(Employee).where(
        Employee.company_id == company_id,
        Employee.status != EmployeeStatus.TERMINATED.value
    )

    # Apply filters
    if search:
        search_term = f"%{search.lower()}%"
        query = query.where(
            or_(
                func.lower(Employee.first_name).like(search_term),
                func.lower(Employee.last_name).like(search_term),
                func.lower(Employee.email).like(search_term),
                func.lower(Employee.employee_number).like(search_term),
            )
        )

    if department_id:
        query = query.where(Employee.department_id == department_id)

    if position_id:
        query = query.where(Employee.position_id == position_id)

    if status:
        query = query.where(Employee.status == status)

    if employment_type:
        query = query.where(Employee.employment_type == employment_type)

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # SECURITY: Whitelist gegen Reflection-Angriffe (CWE-89)
    ALLOWED_SORT_FIELDS = {"first_name", "last_name", "email", "employee_number", "created_at", "updated_at", "hire_date", "status"}
    if sort_by not in ALLOWED_SORT_FIELDS:
        sort_by = "last_name"
    sort_column = getattr(Employee, sort_by)
    if sort_order == "desc":
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())

    # Apply pagination
    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page)

    # Load relationships
    query = query.options(
        selectinload(Employee.department),
        selectinload(Employee.position),
    )

    result = await db.execute(query)
    employees = result.scalars().all()

    items = [employee_to_schema(emp) for emp in employees]
    total_pages = (total + per_page - 1) // per_page if total > 0 else 0

    return EmployeeListResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
    )


@router.get("/employees/{employee_id}", response_model=EmployeeDetailSchema)
async def get_employee(
    employee_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Holt einen einzelnen Mitarbeiter."""
    company_id = await get_company_id_for_user(db, current_user)

    query = select(Employee).where(Employee.id == employee_id)
    if company_id:
        query = query.where(Employee.company_id == company_id)

    query = query.options(
        selectinload(Employee.department),
        selectinload(Employee.position),
    )

    result = await db.execute(query)
    employee = result.scalar_one_or_none()

    if not employee:
        raise HTTPException(status_code=404, detail="Mitarbeiter nicht gefunden")

    # Build response
    dept_info = None
    if employee.department:
        dept_info = DepartmentInfoSchema(
            id=employee.department.id,
            name=employee.department.name,
            short_name=employee.department.short_name,
        )

    pos_info = None
    if employee.position:
        pos_info = PositionInfoSchema(
            id=employee.position.id,
            title=employee.position.title,
            level=employee.position.level,
        )

    return EmployeeDetailSchema(
        id=employee.id,
        employee_number=employee.employee_number,
        salutation=employee.salutation,
        title=employee.title,
        first_name=employee.first_name,
        last_name=employee.last_name,
        full_name=f"{employee.first_name} {employee.last_name}",
        email=employee.email,
        phone=employee.phone,
        mobile=employee.mobile,
        department=dept_info,
        position=pos_info,
        employment_type=employee.employment_type or "full_time",
        status=employee.status or "active",
        hire_date=employee.hire_date,
        photo_path=employee.photo_path,
        created_at=employee.created_at,
        birth_name=employee.birth_name,
        date_of_birth=employee.date_of_birth,
        place_of_birth=employee.place_of_birth,
        nationality=employee.nationality,
        gender=employee.gender,
        private_email=employee.private_email,
        private_phone=employee.private_phone,
        street=employee.street,
        street_number=employee.street_number,
        postal_code=employee.postal_code,
        city=employee.city,
        country=employee.country,
        emergency_contact_name=employee.emergency_contact_name,
        emergency_contact_phone=employee.emergency_contact_phone,
        emergency_contact_relation=employee.emergency_contact_relation,
        department_id=employee.department_id,
        position_id=employee.position_id,
        supervisor_id=employee.supervisor_id,
        probation_end_date=employee.probation_end_date,
        termination_date=employee.termination_date,
        weekly_hours=employee.weekly_hours,
        vacation_days_per_year=employee.vacation_days_per_year,
        tax_id=employee.tax_id,
        tax_class=employee.tax_class,
        social_security_number=employee.social_security_number,
        health_insurance=employee.health_insurance,
        health_insurance_number=employee.health_insurance_number,
        iban=employee.iban,
        bic=employee.bic,
        bank_name=employee.bank_name,
        updated_at=employee.updated_at,
    )


@router.post("/employees", response_model=EmployeeDetailSchema, status_code=201)
async def create_employee(
    data: EmployeeCreateSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Erstellt einen neuen Mitarbeiter."""
    company_id = await get_company_id_for_user(db, current_user)
    if not company_id:
        raise HTTPException(status_code=400, detail="Keine Firma zugeordnet")

    # Check for duplicate employee number
    existing = await db.execute(
        select(Employee).where(
            Employee.company_id == company_id,
            Employee.employee_number == data.employee_number,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail=f"Personalnummer '{data.employee_number}' existiert bereits"
        )

    employee = Employee(
        company_id=company_id,
        **data.model_dump(exclude_unset=True)
    )

    db.add(employee)
    await db.commit()
    await db.refresh(employee)

    logger.info("employee_created", employee_id=str(employee.id), user_id=str(current_user.id))

    return await get_employee(employee.id, db, current_user)


@router.put("/employees/{employee_id}", response_model=EmployeeDetailSchema)
async def update_employee(
    employee_id: UUID,
    data: EmployeeUpdateSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Aktualisiert einen Mitarbeiter."""
    company_id = await get_company_id_for_user(db, current_user)

    query = select(Employee).where(Employee.id == employee_id)
    if company_id:
        query = query.where(Employee.company_id == company_id)

    result = await db.execute(query)
    employee = result.scalar_one_or_none()

    if not employee:
        raise HTTPException(status_code=404, detail="Mitarbeiter nicht gefunden")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(employee, key, value)

    await db.commit()
    await db.refresh(employee)

    logger.info("employee_updated", employee_id=str(employee_id), user_id=str(current_user.id))

    return await get_employee(employee.id, db, current_user)


@router.delete("/employees/{employee_id}")
async def delete_employee(
    employee_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Loescht einen Mitarbeiter (Soft-Delete durch Status-Aenderung)."""
    company_id = await get_company_id_for_user(db, current_user)

    query = select(Employee).where(Employee.id == employee_id)
    if company_id:
        query = query.where(Employee.company_id == company_id)

    result = await db.execute(query)
    employee = result.scalar_one_or_none()

    if not employee:
        raise HTTPException(status_code=404, detail="Mitarbeiter nicht gefunden")

    # Soft delete by setting status to terminated
    employee.status = EmployeeStatus.TERMINATED.value
    employee.termination_date = date.today()
    await db.commit()

    logger.info("employee_deleted", employee_id=str(employee_id), user_id=str(current_user.id))

    return {"message": "Mitarbeiter erfolgreich archiviert"}


# =============================================================================
# DEPARTMENT ENDPOINTS
# =============================================================================

@router.get("/departments", response_model=DepartmentListResponse)
async def list_departments(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    parent_id: Optional[UUID] = Query(None),
    include_inactive: bool = Query(False),
    sort_by: Optional[str] = Query("name"),
    sort_order: Optional[str] = Query("asc"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Listet alle Abteilungen auf."""
    company_id = await get_company_id_for_user(db, current_user)
    if not company_id:
        return DepartmentListResponse(
            items=[],
            total=0,
            page=page,
            per_page=per_page,
            total_pages=0,
        )

    query = select(Department).where(
        Department.company_id == company_id,
        Department.deleted_at.is_(None),
    )

    if not include_inactive:
        query = query.where(Department.is_active == True)

    if search:
        search_term = f"%{search.lower()}%"
        query = query.where(
            or_(
                func.lower(Department.name).like(search_term),
                func.lower(Department.short_name).like(search_term),
            )
        )

    if parent_id:
        query = query.where(Department.parent_id == parent_id)

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # SECURITY: Whitelist gegen Reflection-Angriffe (CWE-89)
    ALLOWED_DEPT_SORT_FIELDS = {"name", "short_name", "created_at", "updated_at", "sort_order", "cost_center"}
    if sort_by not in ALLOWED_DEPT_SORT_FIELDS:
        sort_by = "name"
    sort_column = getattr(Department, sort_by)
    if sort_order == "desc":
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())

    # Apply pagination
    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page)

    result = await db.execute(query)
    departments = result.scalars().all()

    # Get employee counts
    items = []
    for dept in departments:
        emp_count_result = await db.execute(
            select(func.count(Employee.id)).where(
                Employee.department_id == dept.id,
                Employee.status != EmployeeStatus.TERMINATED.value,
            )
        )
        emp_count = emp_count_result.scalar() or 0

        items.append(DepartmentSchema(
            id=dept.id,
            name=dept.name,
            short_name=dept.short_name,
            description=dept.description,
            cost_center=dept.cost_center,
            parent_id=dept.parent_id,
            manager_id=dept.manager_id,
            is_active=dept.is_active if dept.is_active is not None else True,
            sort_order=dept.sort_order if dept.sort_order is not None else 0,
            employee_count=emp_count,
            created_at=dept.created_at,
        ))

    total_pages = (total + per_page - 1) // per_page if total > 0 else 0

    return DepartmentListResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
    )


@router.get("/departments/tree", response_model=List[DepartmentTreeItemSchema])
async def get_department_tree(
    include_inactive: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Holt die Abteilungsstruktur als Baum."""
    company_id = await get_company_id_for_user(db, current_user)
    if not company_id:
        return []

    query = select(Department).where(
        Department.company_id == company_id,
        Department.deleted_at.is_(None),
    )

    if not include_inactive:
        query = query.where(Department.is_active == True)

    query = query.order_by(Department.sort_order, Department.name)

    result = await db.execute(query)
    all_departments = result.scalars().all()

    # Build tree structure
    dept_dict: dict[UUID, dict] = {}
    for dept in all_departments:
        # Get employee count
        emp_count_result = await db.execute(
            select(func.count(Employee.id)).where(
                Employee.department_id == dept.id,
                Employee.status != EmployeeStatus.TERMINATED.value,
            )
        )
        emp_count = emp_count_result.scalar() or 0

        # Get manager name if exists
        manager_name = None
        if dept.manager_id:
            mgr_result = await db.execute(
                select(Employee.first_name, Employee.last_name).where(
                    Employee.id == dept.manager_id
                )
            )
            mgr = mgr_result.first()
            if mgr:
                manager_name = f"{mgr[0]} {mgr[1]}"

        dept_dict[dept.id] = {
            "id": dept.id,
            "name": dept.name,
            "short_name": dept.short_name,
            "parent_id": dept.parent_id,
            "manager_id": dept.manager_id,
            "manager_name": manager_name,
            "employee_count": emp_count,
            "is_active": dept.is_active,
            "sort_order": dept.sort_order,
            "level": 0,
            "children": [],
        }

    # Build hierarchy
    root_items = []
    for dept_id, dept_data in dept_dict.items():
        parent_id = dept_data["parent_id"]
        if parent_id and parent_id in dept_dict:
            dept_data["level"] = dept_dict[parent_id]["level"] + 1
            dept_dict[parent_id]["children"].append(dept_data)
        else:
            root_items.append(dept_data)

    def dict_to_schema(d: dict) -> DepartmentTreeItemSchema:
        return DepartmentTreeItemSchema(
            id=d["id"],
            name=d["name"],
            short_name=d["short_name"],
            parent_id=d["parent_id"],
            manager_id=d["manager_id"],
            manager_name=d["manager_name"],
            employee_count=d["employee_count"],
            is_active=d["is_active"],
            sort_order=d["sort_order"],
            level=d["level"],
            children=[dict_to_schema(c) for c in d["children"]],
        )

    return [dict_to_schema(item) for item in root_items]


@router.get("/departments/{department_id}", response_model=DepartmentDetailSchema)
async def get_department(
    department_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Holt eine einzelne Abteilung."""
    company_id = await get_company_id_for_user(db, current_user)

    query = select(Department).where(
        Department.id == department_id,
        Department.deleted_at.is_(None),
    )
    if company_id:
        query = query.where(Department.company_id == company_id)

    result = await db.execute(query)
    department = result.scalar_one_or_none()

    if not department:
        raise HTTPException(status_code=404, detail="Abteilung nicht gefunden")

    # Get employee count
    emp_count_result = await db.execute(
        select(func.count(Employee.id)).where(
            Employee.department_id == department.id,
            Employee.status != EmployeeStatus.TERMINATED.value,
        )
    )
    emp_count = emp_count_result.scalar() or 0

    # Get children
    children_result = await db.execute(
        select(Department).where(
            Department.parent_id == department_id,
            Department.deleted_at.is_(None),
        )
    )
    children = children_result.scalars().all()

    children_schemas = []
    for child in children:
        child_emp_count_result = await db.execute(
            select(func.count(Employee.id)).where(
                Employee.department_id == child.id,
                Employee.status != EmployeeStatus.TERMINATED.value,
            )
        )
        child_emp_count = child_emp_count_result.scalar() or 0

        children_schemas.append(DepartmentSchema(
            id=child.id,
            name=child.name,
            short_name=child.short_name,
            description=child.description,
            cost_center=child.cost_center,
            parent_id=child.parent_id,
            manager_id=child.manager_id,
            is_active=child.is_active if child.is_active is not None else True,
            sort_order=child.sort_order if child.sort_order is not None else 0,
            employee_count=child_emp_count,
            created_at=child.created_at,
        ))

    return DepartmentDetailSchema(
        id=department.id,
        name=department.name,
        short_name=department.short_name,
        description=department.description,
        cost_center=department.cost_center,
        parent_id=department.parent_id,
        manager_id=department.manager_id,
        is_active=department.is_active if department.is_active is not None else True,
        sort_order=department.sort_order if department.sort_order is not None else 0,
        employee_count=emp_count,
        created_at=department.created_at,
        children=children_schemas,
        updated_at=department.updated_at,
    )


@router.post("/departments", response_model=DepartmentSchema, status_code=201)
async def create_department(
    data: DepartmentCreateSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Erstellt eine neue Abteilung."""
    company_id = await get_company_id_for_user(db, current_user)
    if not company_id:
        raise HTTPException(status_code=400, detail="Keine Firma zugeordnet")

    department = Department(
        company_id=company_id,
        created_by_id=current_user.id,
        **data.model_dump(exclude_unset=True)
    )

    db.add(department)
    await db.commit()
    await db.refresh(department)

    logger.info("department_created", department_id=str(department.id), user_id=str(current_user.id))

    return DepartmentSchema(
        id=department.id,
        name=department.name,
        short_name=department.short_name,
        description=department.description,
        cost_center=department.cost_center,
        parent_id=department.parent_id,
        manager_id=department.manager_id,
        is_active=department.is_active if department.is_active is not None else True,
        sort_order=department.sort_order if department.sort_order is not None else 0,
        employee_count=0,
        created_at=department.created_at,
    )


@router.put("/departments/{department_id}", response_model=DepartmentSchema)
async def update_department(
    department_id: UUID,
    data: DepartmentUpdateSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Aktualisiert eine Abteilung."""
    company_id = await get_company_id_for_user(db, current_user)

    query = select(Department).where(
        Department.id == department_id,
        Department.deleted_at.is_(None),
    )
    if company_id:
        query = query.where(Department.company_id == company_id)

    result = await db.execute(query)
    department = result.scalar_one_or_none()

    if not department:
        raise HTTPException(status_code=404, detail="Abteilung nicht gefunden")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(department, key, value)

    await db.commit()
    await db.refresh(department)

    # Get employee count
    emp_count_result = await db.execute(
        select(func.count(Employee.id)).where(
            Employee.department_id == department.id,
            Employee.status != EmployeeStatus.TERMINATED.value,
        )
    )
    emp_count = emp_count_result.scalar() or 0

    logger.info("department_updated", department_id=str(department_id), user_id=str(current_user.id))

    return DepartmentSchema(
        id=department.id,
        name=department.name,
        short_name=department.short_name,
        description=department.description,
        cost_center=department.cost_center,
        parent_id=department.parent_id,
        manager_id=department.manager_id,
        is_active=department.is_active if department.is_active is not None else True,
        sort_order=department.sort_order if department.sort_order is not None else 0,
        employee_count=emp_count,
        created_at=department.created_at,
    )


@router.delete("/departments/{department_id}")
async def delete_department(
    department_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Loescht eine Abteilung (Soft-Delete)."""
    company_id = await get_company_id_for_user(db, current_user)

    query = select(Department).where(
        Department.id == department_id,
        Department.deleted_at.is_(None),
    )
    if company_id:
        query = query.where(Department.company_id == company_id)

    result = await db.execute(query)
    department = result.scalar_one_or_none()

    if not department:
        raise HTTPException(status_code=404, detail="Abteilung nicht gefunden")

    # Check for children
    children_result = await db.execute(
        select(func.count(Department.id)).where(
            Department.parent_id == department_id,
            Department.deleted_at.is_(None),
        )
    )
    if children_result.scalar() > 0:
        raise HTTPException(
            status_code=400,
            detail="Abteilung hat Unterabteilungen und kann nicht geloescht werden"
        )

    # Soft delete
    department.deleted_at = utc_now()
    await db.commit()

    logger.info("department_deleted", department_id=str(department_id), user_id=str(current_user.id))

    return {"message": "Abteilung erfolgreich geloescht"}


# =============================================================================
# POSITION ENDPOINTS
# =============================================================================

@router.get("/positions", response_model=PositionListResponse)
async def list_positions(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    department_id: Optional[UUID] = Query(None),
    job_family: Optional[str] = Query(None),
    is_management: Optional[bool] = Query(None),
    include_inactive: bool = Query(False),
    sort_by: Optional[str] = Query("title"),
    sort_order: Optional[str] = Query("asc"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Listet alle Positionen auf."""
    company_id = await get_company_id_for_user(db, current_user)
    if not company_id:
        return PositionListResponse(
            items=[],
            total=0,
            page=page,
            per_page=per_page,
            total_pages=0,
        )

    query = select(Position).where(
        Position.company_id == company_id,
        Position.deleted_at.is_(None),
    )

    if not include_inactive:
        query = query.where(Position.is_active == True)

    if search:
        search_term = f"%{search.lower()}%"
        query = query.where(
            or_(
                func.lower(Position.title).like(search_term),
                func.lower(Position.job_family).like(search_term),
            )
        )

    if department_id:
        query = query.where(Position.department_id == department_id)

    if job_family:
        query = query.where(Position.job_family == job_family)

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # SECURITY: Whitelist gegen Reflection-Angriffe (CWE-89)
    ALLOWED_POS_SORT_FIELDS = {"title", "created_at", "updated_at", "level", "job_family", "is_active"}
    if sort_by not in ALLOWED_POS_SORT_FIELDS:
        sort_by = "title"
    sort_column = getattr(Position, sort_by)
    if sort_order == "desc":
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())

    # Apply pagination
    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page)

    query = query.options(selectinload(Position.department))

    result = await db.execute(query)
    positions = result.scalars().all()

    items = []
    for pos in positions:
        # Get employee count
        emp_count_result = await db.execute(
            select(func.count(Employee.id)).where(
                Employee.position_id == pos.id,
                Employee.status != EmployeeStatus.TERMINATED.value,
            )
        )
        emp_count = emp_count_result.scalar() or 0

        dept_info = None
        if pos.department:
            dept_info = DepartmentInfoSchema(
                id=pos.department.id,
                name=pos.department.name,
                short_name=pos.department.short_name,
            )

        items.append(PositionSchema(
            id=pos.id,
            title=pos.title,
            description=pos.description,
            department_id=pos.department_id,
            department=dept_info,
            level=pos.level if pos.level is not None else 1,
            job_family=pos.job_family,
            min_salary=pos.salary_band_min,
            max_salary=pos.salary_band_max,
            is_management=False,  # Not in model, default to False
            is_active=pos.is_active if pos.is_active is not None else True,
            sort_order=0,  # Not in model
            employee_count=emp_count,
            created_at=pos.created_at,
        ))

    total_pages = (total + per_page - 1) // per_page if total > 0 else 0

    return PositionListResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
    )


@router.get("/positions/job-families", response_model=List[JobFamilyStats])
async def get_job_families(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Holt alle Job-Familien mit Statistiken."""
    company_id = await get_company_id_for_user(db, current_user)
    if not company_id:
        return []

    # Get unique job families
    query = (
        select(
            Position.job_family,
            func.count(Position.id).label("position_count"),
        )
        .where(
            Position.company_id == company_id,
            Position.deleted_at.is_(None),
            Position.is_active == True,
            Position.job_family.isnot(None),
        )
        .group_by(Position.job_family)
    )

    result = await db.execute(query)
    job_families = result.all()

    stats = []
    for jf in job_families:
        if jf.job_family:
            # Get employee count for this job family
            emp_query = (
                select(func.count(Employee.id))
                .select_from(Employee)
                .join(Position, Employee.position_id == Position.id)
                .where(
                    Position.job_family == jf.job_family,
                    Employee.status != EmployeeStatus.TERMINATED.value,
                )
            )
            emp_result = await db.execute(emp_query)
            emp_count = emp_result.scalar() or 0

            stats.append(JobFamilyStats(
                job_family=jf.job_family,
                position_count=jf.position_count,
                employee_count=emp_count,
            ))

    return stats


@router.get("/positions/{position_id}", response_model=PositionDetailSchema)
async def get_position(
    position_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Holt eine einzelne Position."""
    company_id = await get_company_id_for_user(db, current_user)

    query = select(Position).where(
        Position.id == position_id,
        Position.deleted_at.is_(None),
    )
    if company_id:
        query = query.where(Position.company_id == company_id)

    query = query.options(selectinload(Position.department))

    result = await db.execute(query)
    position = result.scalar_one_or_none()

    if not position:
        raise HTTPException(status_code=404, detail="Position nicht gefunden")

    # Get employee count
    emp_count_result = await db.execute(
        select(func.count(Employee.id)).where(
            Employee.position_id == position.id,
            Employee.status != EmployeeStatus.TERMINATED.value,
        )
    )
    emp_count = emp_count_result.scalar() or 0

    dept_info = None
    if position.department:
        dept_info = DepartmentInfoSchema(
            id=position.department.id,
            name=position.department.name,
            short_name=position.department.short_name,
        )

    return PositionDetailSchema(
        id=position.id,
        title=position.title,
        description=position.description,
        department_id=position.department_id,
        department=dept_info,
        level=position.level if position.level is not None else 1,
        job_family=position.job_family,
        min_salary=position.salary_band_min,
        max_salary=position.salary_band_max,
        is_management=False,
        is_active=position.is_active if position.is_active is not None else True,
        sort_order=0,
        employee_count=emp_count,
        created_at=position.created_at,
        updated_at=position.updated_at,
    )


@router.post("/positions", response_model=PositionSchema, status_code=201)
async def create_position(
    data: PositionCreateSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Erstellt eine neue Position."""
    company_id = await get_company_id_for_user(db, current_user)
    if not company_id:
        raise HTTPException(status_code=400, detail="Keine Firma zugeordnet")

    position = Position(
        company_id=company_id,
        title=data.title,
        description=data.description,
        department_id=data.department_id,
        level=data.level,
        job_family=data.job_family,
        salary_band_min=data.min_salary,
        salary_band_max=data.max_salary,
        is_active=data.is_active,
    )

    db.add(position)
    await db.commit()
    await db.refresh(position)

    logger.info("position_created", position_id=str(position.id), user_id=str(current_user.id))

    return PositionSchema(
        id=position.id,
        title=position.title,
        description=position.description,
        department_id=position.department_id,
        level=position.level if position.level is not None else 1,
        job_family=position.job_family,
        min_salary=position.salary_band_min,
        max_salary=position.salary_band_max,
        is_management=False,
        is_active=position.is_active if position.is_active is not None else True,
        sort_order=0,
        employee_count=0,
        created_at=position.created_at,
    )


@router.put("/positions/{position_id}", response_model=PositionSchema)
async def update_position(
    position_id: UUID,
    data: PositionUpdateSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Aktualisiert eine Position."""
    company_id = await get_company_id_for_user(db, current_user)

    query = select(Position).where(
        Position.id == position_id,
        Position.deleted_at.is_(None),
    )
    if company_id:
        query = query.where(Position.company_id == company_id)

    result = await db.execute(query)
    position = result.scalar_one_or_none()

    if not position:
        raise HTTPException(status_code=404, detail="Position nicht gefunden")

    update_data = data.model_dump(exclude_unset=True)

    # Map frontend field names to model field names
    if 'min_salary' in update_data:
        position.salary_band_min = update_data.pop('min_salary')
    if 'max_salary' in update_data:
        position.salary_band_max = update_data.pop('max_salary')

    for key, value in update_data.items():
        if hasattr(position, key):
            setattr(position, key, value)

    await db.commit()
    await db.refresh(position)

    # Get employee count
    emp_count_result = await db.execute(
        select(func.count(Employee.id)).where(
            Employee.position_id == position.id,
            Employee.status != EmployeeStatus.TERMINATED.value,
        )
    )
    emp_count = emp_count_result.scalar() or 0

    logger.info("position_updated", position_id=str(position_id), user_id=str(current_user.id))

    return PositionSchema(
        id=position.id,
        title=position.title,
        description=position.description,
        department_id=position.department_id,
        level=position.level if position.level is not None else 1,
        job_family=position.job_family,
        min_salary=position.salary_band_min,
        max_salary=position.salary_band_max,
        is_management=False,
        is_active=position.is_active if position.is_active is not None else True,
        sort_order=0,
        employee_count=emp_count,
        created_at=position.created_at,
    )


@router.delete("/positions/{position_id}")
async def delete_position(
    position_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Loescht eine Position (Soft-Delete)."""
    company_id = await get_company_id_for_user(db, current_user)

    query = select(Position).where(
        Position.id == position_id,
        Position.deleted_at.is_(None),
    )
    if company_id:
        query = query.where(Position.company_id == company_id)

    result = await db.execute(query)
    position = result.scalar_one_or_none()

    if not position:
        raise HTTPException(status_code=404, detail="Position nicht gefunden")

    # Check if position is in use
    emp_count_result = await db.execute(
        select(func.count(Employee.id)).where(
            Employee.position_id == position_id,
            Employee.status != EmployeeStatus.TERMINATED.value,
        )
    )
    if emp_count_result.scalar() > 0:
        raise HTTPException(
            status_code=400,
            detail="Position wird noch verwendet und kann nicht geloescht werden"
        )

    # Soft delete
    position.deleted_at = utc_now()
    await db.commit()

    logger.info("position_deleted", position_id=str(position_id), user_id=str(current_user.id))

    return {"message": "Position erfolgreich geloescht"}

"""Personal/HR Services - Enterprise-Grade Mitarbeiterverwaltung.

Bietet:
- EmployeeService: Mitarbeiter-CRUD mit PII-Maskierung und Audit-Logging
- DepartmentService: Abteilungs-Verwaltung mit Hierarchie
- PositionService: Stellen-Verwaltung mit Gehalts-Maskierung

Security Features:
- RBAC-basierte Zugriffskontrolle
- PII-Maskierung basierend auf Berechtigungen (GDPR Art. 25)
- Audit-Logging fuer alle CRUD-Operationen (GDPR Art. 30)
- Input-Sanitization gegen XSS/Injection

Verwendung:
    from app.services.personal import employee_service

    employees = await employee_service.list_employees(
        db=db,
        company_id=company.id,
        user_id=current_user.id,
        mask_pii=True,  # PII maskieren fuer Non-HR-User
    )
"""

from app.services.personal.employee_service import EmployeeService, employee_service
from app.services.personal.department_service import DepartmentService, department_service
from app.services.personal.position_service import PositionService, position_service

__all__ = [
    "EmployeeService",
    "employee_service",
    "DepartmentService",
    "department_service",
    "PositionService",
    "position_service",
]

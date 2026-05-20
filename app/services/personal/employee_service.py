"""Employee Service - Enterprise-Grade Mitarbeiterverwaltung.

Implementiert GDPR-konforme Mitarbeiter-Operationen:
- CRUD mit vollständigem Audit-Trail
- PII-Maskierung basierend auf Berechtigungen
- Input-Sanitization
- Company Context Enforcement

WICHTIG: Alle PII-Felder werden für Non-HR-User maskiert!
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import structlog
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError, DataError, OperationalError

from app.db.models import Employee, Department, Position, EmployeeStatus, EmploymentType
from app.core.audit_logger import SecurityAuditLogger, SecurityEventType, get_audit_logger
from app.core.input_sanitization import sanitize_text_field, sanitize_search_query

logger = structlog.get_logger(__name__)


class EmployeeService:
    """Service für Mitarbeiter-Verwaltung (Enterprise-Grade).

    Security Features:
    - PII-Maskierung basierend auf Berechtigungen
    - Audit-Logging für alle CRUD-Operationen
    - Input-Sanitization
    - Company Context Enforcement
    """

    # PII-Felder die maskiert werden (GDPR Art. 25 - Privacy by Design)
    # B.2 HIGH: Emergency Contact PII hinzugefuegt!
    PII_FIELDS = {
        'tax_id': lambda v: f"***{v[-4:]}" if v and len(v) >= 4 else "***",
        'social_security_number': lambda v: "***-***-****" if v else None,
        'iban': lambda v: f"{v[:4]}****{v[-4:]}" if v and len(v) >= 8 else "****" if v else None,
        'bic': lambda v: f"{v[:4]}***" if v and len(v) >= 4 else "***" if v else None,
        'health_insurance_number': lambda v: f"***{v[-4:]}" if v and len(v) >= 4 else "***" if v else None,
        'private_email': lambda v: f"{v.split('@')[0][:3]}***@***" if v and '@' in v else "***@***" if v else None,
        'private_phone': lambda v: f"***{v[-4:]}" if v and len(v) >= 4 else "***" if v else None,
        'date_of_birth': lambda v: None,  # Komplett ausblenden
        'place_of_birth': lambda v: None,  # Komplett ausblenden
        'nationality': lambda v: None,  # Komplett ausblenden
        # B.2 HIGH: Emergency Contact ist auch PII!
        'emergency_contact_name': lambda v: f"{v[:3]}***" if v and len(v) >= 3 else "***" if v else None,
        'emergency_contact_phone': lambda v: f"***{v[-4:]}" if v and len(v) >= 4 else "***" if v else None,
    }

    # Felder die für Change-Detection bei Updates geprüft werden (für Audit-Log)
    SENSITIVE_FIELDS = {
        'tax_id', 'social_security_number', 'iban', 'bic',
        'health_insurance_number', 'salary', 'tax_class',
    }

    # Erlaubte Sortierfelder (B.1 HIGH: SQL Injection Prevention)
    ALLOWED_SORT_FIELDS = {
        "last_name", "first_name", "hire_date", "employee_number",
        "created_at", "updated_at", "status", "email"
    }

    async def list_employees(
        self,
        db: AsyncSession,
        company_id: UUID,
        user_id: UUID,
        mask_pii: bool = True,
        page: int = 1,
        per_page: int = 20,
        search: Optional[str] = None,
        department_id: Optional[UUID] = None,
        position_id: Optional[UUID] = None,
        status_filter: Optional[str] = None,
        employment_type: Optional[str] = None,
        sort_by: str = "last_name",
        sort_order: str = "asc",
        ip_address: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Listet Mitarbeiter mit optionaler PII-Maskierung.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID (für Multi-Tenancy)
            user_id: Benutzer-ID (für Audit)
            mask_pii: PII-Felder maskieren (True für Non-HR-User)
            page: Seitennummer (1-basiert)
            per_page: Einträge pro Seite
            search: Suchbegriff (Name, E-Mail, Personalnummer)
            department_id: Filter nach Abteilung
            position_id: Filter nach Position
            status_filter: Filter nach Status
            employment_type: Filter nach Beschäftigungsart
            sort_by: Sortierfeld
            sort_order: Sortierrichtung (asc/desc)
            ip_address: Client-IP für Audit-Log

        Returns:
            Tuple (Liste von Mitarbeiter-Dicts, Gesamtanzahl)
        """
        # Input-Sanitization
        if search:
            search, _ = sanitize_search_query(search, strict_mode=True)

        # B.1 HIGH: Sort-Field Whitelist gegen SQL Injection
        if sort_by not in self.ALLOWED_SORT_FIELDS:
            logger.warning(
                "invalid_sort_field_attempted",
                sort_by=sort_by,
                user_id=str(user_id),
                allowed_fields=list(self.ALLOWED_SORT_FIELDS),
            )
            sort_by = "last_name"

        # Basis-Query mit Company-Filter (Multi-Tenancy)
        query = (
            select(Employee)
            .where(Employee.company_id == company_id)
            .where(Employee.deleted_at.is_(None))
            .options(
                selectinload(Employee.department),
                selectinload(Employee.position),
            )
        )

        # Suchfilter
        if search:
            search_term = f"%{search}%"
            query = query.where(
                or_(
                    Employee.first_name.ilike(search_term),
                    Employee.last_name.ilike(search_term),
                    Employee.email.ilike(search_term),
                    Employee.employee_number.ilike(search_term),
                )
            )

        # Filter
        if department_id:
            query = query.where(Employee.department_id == department_id)
        if position_id:
            query = query.where(Employee.position_id == position_id)
        if status_filter:
            query = query.where(Employee.status == status_filter)
        if employment_type:
            query = query.where(Employee.employment_type == employment_type)

        # Count
        count_query = select(func.count()).select_from(query.subquery())
        total = (await db.execute(count_query)).scalar() or 0

        # Sortierung
        sort_column = getattr(Employee, sort_by, Employee.last_name)
        if sort_order.lower() == "desc":
            sort_column = sort_column.desc()
        query = query.order_by(sort_column)

        # Paginierung
        offset = (page - 1) * per_page
        query = query.offset(offset).limit(per_page)

        # Ausführen
        result = await db.execute(query)
        employees = result.scalars().all()

        # Zu Dict konvertieren mit optionaler PII-Maskierung
        employee_dicts = [
            self._employee_to_dict(emp, mask_pii=mask_pii, include_details=False)
            for emp in employees
        ]

        # A.1 CRITICAL: Audit-Logging für List-Operationen (GDPR Art. 30)
        audit = get_audit_logger(db)
        await audit.log_event(
            event_type=SecurityEventType.EMPLOYEES_LISTED,
            user_id=str(user_id),
            ip_address=ip_address,
            resource_type="employee",
            details={
                "company_id": str(company_id),
                "count": len(employee_dicts),
                "total": total,
                "pii_masked": mask_pii,
                "filters": {
                    "search": bool(search),
                    "department_id": bool(department_id),
                    "position_id": bool(position_id),
                    "status_filter": status_filter,
                    "employment_type": employment_type,
                },
                "page": page,
                "per_page": per_page,
            },
        )

        logger.debug(
            "employees_listed",
            company_id=str(company_id),
            user_id=str(user_id),
            count=len(employee_dicts),
            total=total,
            masked=mask_pii,
        )

        return employee_dicts, total

    async def get_employee(
        self,
        db: AsyncSession,
        employee_id: UUID,
        company_id: UUID,
        user_id: UUID,
        mask_pii: bool = True,
        ip_address: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Holt einen Mitarbeiter mit PII-Maskierung und Audit-Logging.

        Args:
            db: Datenbank-Session
            employee_id: Mitarbeiter-ID
            company_id: Firmen-ID (für Multi-Tenancy)
            user_id: Benutzer-ID (für Audit)
            mask_pii: PII-Felder maskieren
            ip_address: Client-IP für Audit-Log

        Returns:
            Mitarbeiter-Dict oder None
        """
        result = await db.execute(
            select(Employee)
            .where(
                Employee.id == employee_id,
                Employee.company_id == company_id,
                Employee.deleted_at.is_(None),
            )
            .options(
                selectinload(Employee.department),
                selectinload(Employee.position),
            )
        )
        employee = result.scalar_one_or_none()

        if not employee:
            return None

        # Audit-Logging
        audit = get_audit_logger(db)
        await audit.log_event(
            event_type=SecurityEventType.EMPLOYEE_ACCESSED,
            user_id=str(user_id),
            ip_address=ip_address,
            resource_type="employee",
            resource_id=str(employee_id),
            details={
                "company_id": str(company_id),
                "pii_accessed": not mask_pii,
            },
        )

        # PII-Zugriff separat loggen wenn nicht maskiert
        if not mask_pii:
            await audit.log_event(
                event_type=SecurityEventType.EMPLOYEE_PII_ACCESSED,
                user_id=str(user_id),
                ip_address=ip_address,
                resource_type="employee",
                resource_id=str(employee_id),
                details={
                    "company_id": str(company_id),
                    "pii_fields": list(self.PII_FIELDS.keys()),
                },
                severity="warning",
            )

        return self._employee_to_dict(employee, mask_pii=mask_pii, include_details=True)

    async def create_employee(
        self,
        db: AsyncSession,
        company_id: UUID,
        user_id: UUID,
        data: Dict[str, Any],
        ip_address: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Erstellt einen Mitarbeiter mit Audit-Logging.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            user_id: Benutzer-ID (für Audit)
            data: Mitarbeiter-Daten
            ip_address: Client-IP für Audit-Log

        Returns:
            Erstellter Mitarbeiter als Dict

        Raises:
            ValueError: Bei Duplikaten (Personalnummer, E-Mail)
        """
        # Input-Sanitization
        sanitized_data = self._sanitize_input(data)

        # Prüfen auf Duplikate (Personalnummer)
        existing = await db.execute(
            select(Employee).where(
                Employee.company_id == company_id,
                Employee.employee_number == sanitized_data.get('employee_number'),
                Employee.deleted_at.is_(None),
            )
        )
        if existing.scalar_one_or_none():
            # B.4 HIGH: Keine Personalnummer in Fehlermeldung (User Enumeration Prevention)
            raise ValueError(
                "Ein Mitarbeiter mit dieser Personalnummer existiert bereits."
            )

        # Prüfen auf Duplikate (E-Mail falls angegeben)
        email = sanitized_data.get('email')
        if email:
            existing_email = await db.execute(
                select(Employee).where(
                    Employee.company_id == company_id,
                    Employee.email == email,
                    Employee.deleted_at.is_(None),
                )
            )
            if existing_email.scalar_one_or_none():
                # B.4 HIGH: Keine E-Mail in Fehlermeldung (User Enumeration Prevention)
                raise ValueError("Ein Mitarbeiter mit dieser E-Mail-Adresse existiert bereits.")

        # B.5 HIGH: Supervisor Cross-Company Validierung
        supervisor_id = sanitized_data.get('supervisor_id')
        if supervisor_id:
            sup_check = await db.execute(
                select(Employee).where(
                    Employee.id == supervisor_id,
                    Employee.company_id == company_id,
                    Employee.deleted_at.is_(None),
                )
            )
            if not sup_check.scalar_one_or_none():
                # H.5 HIGH: Generische Fehlermeldung - keine Company-Struktur leaken
                raise ValueError("Die referenzierte Ressource wurde nicht gefunden.")

        # Erstellen mit Transaction Error Handling (C.1 MEDIUM)
        try:
            employee = Employee(
                company_id=company_id,
                created_by_id=user_id,
                **sanitized_data
            )
            db.add(employee)
            await db.flush()
            await db.refresh(employee)

            # Audit-Logging innerhalb der Transaction
            audit = get_audit_logger(db)
            await audit.log_event(
                event_type=SecurityEventType.EMPLOYEE_CREATED,
                user_id=str(user_id),
                ip_address=ip_address,
                resource_type="employee",
                resource_id=str(employee.id),
                details={
                    "company_id": str(company_id),
                    # G.2 HIGH: Keine PII im Audit-Log (GDPR Art. 32)
                    # employee_number und name ENTFERNT
                },
            )

            await db.commit()

            # H.1 CRITICAL: Keine PII im strukturierten Logger (GDPR Art. 32)
            logger.info(
                "employee_created",
                employee_id=str(employee.id),
                # employee_number ENTFERNT - ist PII
                company_id=str(company_id),
                user_id=str(user_id),
            )

            # H.2 CRITICAL: PII immer maskieren in API-Response (Defense in Depth)
            # Caller kann mask_pii=False explizit setzen wenn berechtigt
            return self._employee_to_dict(employee, mask_pii=True, include_details=True)

        except IntegrityError as e:
            # I.3 CRITICAL: Spezifische Exception abfangen - keine DB-Details leaken
            await db.rollback()
            logger.error(
                "employee_create_integrity_error",
                error_type="IntegrityError",
                company_id=str(company_id),
                user_id=str(user_id),
            )
            raise ValueError("Ein Eintrag mit diesen Daten existiert bereits.")
        except (DataError, OperationalError) as e:
            # I.3 CRITICAL: DB-Fehler generisch behandeln
            await db.rollback()
            logger.error(
                "employee_create_db_error",
                error_type=type(e).__name__,
                company_id=str(company_id),
                user_id=str(user_id),
            )
            raise ValueError("Ein Datenbankfehler ist aufgetreten.")
        except ValueError:
            # ValueError werden durchgereicht (sind bereits sicher)
            await db.rollback()
            raise
        except Exception as e:
            # I.3 CRITICAL: Unerwartete Fehler generisch behandeln
            await db.rollback()
            logger.error(
                "employee_create_unexpected_error",
                error_type=type(e).__name__,
                company_id=str(company_id),
                user_id=str(user_id),
            )
            raise ValueError("Ein unerwarteter Fehler ist aufgetreten.")

    async def update_employee(
        self,
        db: AsyncSession,
        employee_id: UUID,
        company_id: UUID,
        user_id: UUID,
        data: Dict[str, Any],
        ip_address: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Aktualisiert einen Mitarbeiter mit Change-Detection und Audit-Logging.

        Args:
            db: Datenbank-Session
            employee_id: Mitarbeiter-ID
            company_id: Firmen-ID
            user_id: Benutzer-ID
            data: Update-Daten
            ip_address: Client-IP für Audit-Log

        Returns:
            Aktualisierter Mitarbeiter als Dict oder None
        """
        result = await db.execute(
            select(Employee)
            .where(
                Employee.id == employee_id,
                Employee.company_id == company_id,
                Employee.deleted_at.is_(None),
            )
        )
        employee = result.scalar_one_or_none()

        if not employee:
            return None

        # Input-Sanitization
        sanitized_data = self._sanitize_input(data)

        # B.5 HIGH: Supervisor Cross-Company Validierung bei Update
        # F.2 HIGH: Supervisor Cycle Detection
        supervisor_id = sanitized_data.get('supervisor_id')
        if supervisor_id:
            # F.2 HIGH: Zyklische Supervisor-Ketten verhindern (A->B->C->A)
            if await self._would_create_supervisor_cycle(db, employee_id, supervisor_id, company_id):
                raise ValueError(
                    "Diese Änderung wuerde eine zyklische Vorgesetzten-Hierarchie erzeugen."
                )

            # B.5 HIGH: Cross-Company Check
            sup_check = await db.execute(
                select(Employee).where(
                    Employee.id == supervisor_id,
                    Employee.company_id == company_id,
                    Employee.deleted_at.is_(None),
                )
            )
            if not sup_check.scalar_one_or_none():
                # I.1 CRITICAL: Generische Fehlermeldung - keine Company-Struktur leaken
                raise ValueError("Die referenzierte Ressource wurde nicht gefunden.")

        # Change-Detection für Audit
        changed_fields = {}
        sensitive_changes = {}

        for key, new_value in sanitized_data.items():
            old_value = getattr(employee, key, None)
            if old_value != new_value:
                changed_fields[key] = {"old": str(old_value), "new": str(new_value)}
                if key in self.SENSITIVE_FIELDS:
                    sensitive_changes[key] = True

        # Update mit Transaction Error Handling (C.1 MEDIUM)
        try:
            for key, value in sanitized_data.items():
                setattr(employee, key, value)

            employee.updated_at = datetime.now(timezone.utc)

            # Audit-Logging innerhalb der Transaction
            if changed_fields:
                audit = get_audit_logger(db)
                await audit.log_event(
                    event_type=SecurityEventType.EMPLOYEE_UPDATED,
                    user_id=str(user_id),
                    ip_address=ip_address,
                    resource_type="employee",
                    resource_id=str(employee_id),
                    details={
                        "company_id": str(company_id),
                        "changed_fields": list(changed_fields.keys()),
                        "sensitive_fields_changed": list(sensitive_changes.keys()),
                        # Keine Werte loggen - nur Feldnamen!
                    },
                    severity="warning" if sensitive_changes else "info",
                )

            await db.commit()
            await db.refresh(employee)

            logger.info(
                "employee_updated",
                employee_id=str(employee_id),
                company_id=str(company_id),
                user_id=str(user_id),
                changed_fields=list(changed_fields.keys()),
            )

            # H.2 CRITICAL: PII immer maskieren in API-Response (Defense in Depth)
            return self._employee_to_dict(employee, mask_pii=True, include_details=True)

        except IntegrityError as e:
            # I.3 CRITICAL: Spezifische Exception abfangen
            await db.rollback()
            logger.error(
                "employee_update_integrity_error",
                error_type="IntegrityError",
                employee_id=str(employee_id),
                company_id=str(company_id),
                user_id=str(user_id),
            )
            raise ValueError("Ein Eintrag mit diesen Daten existiert bereits.")
        except (DataError, OperationalError) as e:
            # I.3 CRITICAL: DB-Fehler generisch behandeln
            await db.rollback()
            logger.error(
                "employee_update_db_error",
                error_type=type(e).__name__,
                employee_id=str(employee_id),
                company_id=str(company_id),
                user_id=str(user_id),
            )
            raise ValueError("Ein Datenbankfehler ist aufgetreten.")
        except ValueError:
            await db.rollback()
            raise
        except Exception as e:
            # I.3 CRITICAL: Unerwartete Fehler generisch behandeln
            await db.rollback()
            logger.error(
                "employee_update_unexpected_error",
                error_type=type(e).__name__,
                employee_id=str(employee_id),
                company_id=str(company_id),
                user_id=str(user_id),
            )
            raise ValueError("Ein unerwarteter Fehler ist aufgetreten.")

    async def delete_employee(
        self,
        db: AsyncSession,
        employee_id: UUID,
        company_id: UUID,
        user_id: UUID,
        ip_address: Optional[str] = None,
    ) -> bool:
        """Löscht einen Mitarbeiter (Soft-Delete) mit Audit-Logging.

        Args:
            db: Datenbank-Session
            employee_id: Mitarbeiter-ID
            company_id: Firmen-ID
            user_id: Benutzer-ID
            ip_address: Client-IP für Audit-Log

        Returns:
            True wenn erfolgreich, False wenn nicht gefunden
        """
        result = await db.execute(
            select(Employee)
            .where(
                Employee.id == employee_id,
                Employee.company_id == company_id,
                Employee.deleted_at.is_(None),
            )
        )
        employee = result.scalar_one_or_none()

        if not employee:
            return False

        # Soft-Delete mit Transaction Error Handling (C.1 MEDIUM)
        try:
            employee.deleted_at = datetime.now(timezone.utc)
            employee.deleted_by_id = user_id

            # Audit-Logging innerhalb der Transaction
            audit = get_audit_logger(db)
            await audit.log_event(
                event_type=SecurityEventType.EMPLOYEE_DELETED,
                user_id=str(user_id),
                ip_address=ip_address,
                resource_type="employee",
                resource_id=str(employee_id),
                details={
                    "company_id": str(company_id),
                    # G.2 HIGH: Keine PII im Audit-Log (GDPR Art. 32)
                    # employee_number und name ENTFERNT
                },
                severity="warning",
            )

            await db.commit()

            logger.info(
                "employee_deleted",
                employee_id=str(employee_id),
                company_id=str(company_id),
                user_id=str(user_id),
            )

            return True

        except IntegrityError as e:
            # I.3 CRITICAL: Spezifische Exception abfangen
            await db.rollback()
            logger.error(
                "employee_delete_integrity_error",
                error_type="IntegrityError",
                employee_id=str(employee_id),
                company_id=str(company_id),
                user_id=str(user_id),
            )
            raise ValueError("Der Mitarbeiter kann nicht gelöscht werden (Referenzen vorhanden).")
        except (DataError, OperationalError) as e:
            # I.3 CRITICAL: DB-Fehler generisch behandeln
            await db.rollback()
            logger.error(
                "employee_delete_db_error",
                error_type=type(e).__name__,
                employee_id=str(employee_id),
                company_id=str(company_id),
                user_id=str(user_id),
            )
            raise ValueError("Ein Datenbankfehler ist aufgetreten.")
        except ValueError:
            await db.rollback()
            raise
        except Exception as e:
            # I.3 CRITICAL: Unerwartete Fehler generisch behandeln
            await db.rollback()
            logger.error(
                "employee_delete_unexpected_error",
                error_type=type(e).__name__,
                employee_id=str(employee_id),
                company_id=str(company_id),
                user_id=str(user_id),
            )
            raise ValueError("Ein unerwarteter Fehler ist aufgetreten.")

    def _employee_to_dict(
        self,
        employee: Employee,
        mask_pii: bool = True,
        include_details: bool = False,
    ) -> Dict[str, Any]:
        """Konvertiert Employee zu Dict mit optionaler PII-Maskierung.

        Args:
            employee: Employee-Objekt
            mask_pii: PII-Felder maskieren
            include_details: Alle Details einbeziehen (für Detail-View)

        Returns:
            Mitarbeiter als Dict
        """
        # Basis-Daten (immer sichtbar)
        data = {
            'id': str(employee.id),
            'employee_number': employee.employee_number,
            'salutation': employee.salutation,
            'title': employee.title,
            'first_name': employee.first_name,
            'last_name': employee.last_name,
            'full_name': employee.full_name,
            'email': employee.email,
            'phone': employee.phone,
            'mobile': employee.mobile,
            'department': {
                'id': str(employee.department.id),
                'name': employee.department.name,
                'short_name': employee.department.short_name,
            } if employee.department else None,
            'position': {
                'id': str(employee.position.id),
                'title': employee.position.title,
                'level': employee.position.level,
            } if employee.position else None,
            'employment_type': employee.employment_type,
            'status': employee.status,
            'hire_date': employee.hire_date.isoformat() if employee.hire_date else None,
            'photo_path': employee.photo_path,
            'created_at': employee.created_at.isoformat() if employee.created_at else None,
        }

        if include_details:
            # Erweiterte Daten (NICHT-PII)
            data.update({
                'birth_name': employee.birth_name,
                'gender': employee.gender,
                'street': employee.street,
                'street_number': employee.street_number,
                'postal_code': employee.postal_code,
                'city': employee.city,
                'country': employee.country,
                # O.1 FIX: emergency_contact_relation ist NICHT PII (nur Name/Phone)
                'emergency_contact_relation': employee.emergency_contact_relation,
                'department_id': str(employee.department_id) if employee.department_id else None,
                'position_id': str(employee.position_id) if employee.position_id else None,
                'supervisor_id': str(employee.supervisor_id) if employee.supervisor_id else None,
                'probation_end_date': employee.probation_end_date.isoformat() if employee.probation_end_date else None,
                'termination_date': employee.termination_date.isoformat() if employee.termination_date else None,
                'weekly_hours': float(employee.weekly_hours) if employee.weekly_hours else None,
                'vacation_days_per_year': employee.vacation_days_per_year,
                'health_insurance': employee.health_insurance,
                'bank_name': employee.bank_name,
                'updated_at': employee.updated_at.isoformat() if employee.updated_at else None,
            })

            # O.1 CRITICAL FIX: Alle PII-Felder müssen hier sein (inkl. Emergency Contact)
            # Damit sie bei mask_pii=True maskiert werden!
            pii_data = {
                'date_of_birth': employee.date_of_birth.isoformat() if employee.date_of_birth else None,
                'place_of_birth': employee.place_of_birth,
                'nationality': employee.nationality,
                'tax_id': employee.tax_id,
                'tax_class': employee.tax_class,
                'social_security_number': employee.social_security_number,
                'health_insurance_number': employee.health_insurance_number,
                'iban': employee.iban,
                'bic': employee.bic,
                'private_email': employee.private_email,
                'private_phone': employee.private_phone,
                # O.1 FIX: Emergency Contact PII wurde vorher NICHT maskiert!
                'emergency_contact_name': employee.emergency_contact_name,
                'emergency_contact_phone': employee.emergency_contact_phone,
            }

            if mask_pii:
                # PII maskieren
                for field, mask_func in self.PII_FIELDS.items():
                    if field in pii_data:
                        original_value = pii_data[field]
                        pii_data[field] = mask_func(original_value) if original_value else None

            data.update(pii_data)

        return data

    def _sanitize_input(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitiert alle Text-Eingaben.

        Args:
            data: Eingabe-Daten

        Returns:
            Sanitisierte Daten

        Raises:
            ValueError: Bei ungültigen Eingaben (z.B. Path Traversal)

        Security:
            - B.3 HIGH: photo_path Path Traversal Prevention
            - Alle Text-Felder werden sanitisiert
        """
        import os
        import re

        text_fields = {
            'employee_number', 'salutation', 'title', 'first_name', 'last_name',
            'birth_name', 'place_of_birth', 'nationality', 'gender',
            'email', 'phone', 'mobile', 'private_email', 'private_phone',
            'street', 'street_number', 'postal_code', 'city', 'country',
            'emergency_contact_name', 'emergency_contact_phone', 'emergency_contact_relation',
            'health_insurance', 'bank_name',
        }

        sanitized = {}
        for key, value in data.items():
            if key in text_fields and isinstance(value, str):
                sanitized[key] = sanitize_text_field(value, max_length=255)
            elif key == 'photo_path' and value is not None:
                # B.3 HIGH: Path Traversal Prevention für photo_path
                if isinstance(value, str) and value.strip():
                    # Nur Dateiname extrahieren (keine Verzeichnispfade erlaubt)
                    photo_filename = os.path.basename(value)
                    # Nur sichere Zeichen: alphanumerisch, Unterstriche, Bindestriche, Punkte
                    if not re.match(r'^[\w\-\.]+$', photo_filename):
                        raise ValueError("Ungültiger Dateiname für Foto. Nur Buchstaben, Zahlen, Unterstriche, Bindestriche und Punkte erlaubt.")
                    # Keine versteckten Dateien (beginnend mit .)
                    if photo_filename.startswith('.'):
                        raise ValueError("Versteckte Dateien sind nicht erlaubt.")
                    # Erlaubte Bildformate
                    allowed_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
                    file_ext = os.path.splitext(photo_filename)[1].lower()
                    if file_ext not in allowed_extensions:
                        raise ValueError(f"Ungültige Dateiendung. Erlaubt: {', '.join(allowed_extensions)}")
                    sanitized['photo_path'] = photo_filename
                else:
                    sanitized['photo_path'] = None
            else:
                sanitized[key] = value

        return sanitized

    async def _would_create_supervisor_cycle(
        self,
        db: AsyncSession,
        employee_id: UUID,
        new_supervisor_id: UUID,
        company_id: UUID,
        max_depth: int = 20,
    ) -> bool:
        """Prüft ob eine Supervisor-Zuweisung einen Zyklus erzeugen wuerde.

        F.2 HIGH: Verhindert zyklische Vorgesetzten-Ketten (A->B->C->A).

        Args:
            db: Datenbank-Session
            employee_id: Mitarbeiter, dessen Supervisor geändert werden soll
            new_supervisor_id: Neuer vorgeschlagener Supervisor
            company_id: Firmen-ID
            max_depth: Maximale Hierarchietiefe (Schutz vor Endlosschleife)

        Returns:
            True wenn Zyklus entstehen wuerde, False sonst
        """
        # Self-Reference ist immer ein Zyklus
        if employee_id == new_supervisor_id:
            return True

        # Traversiere die Supervisor-Kette vom neuen Supervisor aufwärts
        visited: set[UUID] = {employee_id}  # Der Mitarbeiter selbst gilt als besucht
        current_id: Optional[UUID] = new_supervisor_id

        for _ in range(max_depth):
            if current_id is None:
                # Kein weiterer Supervisor -> kein Zyklus möglich
                return False

            if current_id in visited:
                # Bereits besucht -> Zyklus gefunden!
                return True

            visited.add(current_id)

            # Hole den Supervisor des aktuellen Mitarbeiters
            result = await db.execute(
                select(Employee.supervisor_id).where(
                    Employee.id == current_id,
                    Employee.company_id == company_id,
                    Employee.deleted_at.is_(None),
                )
            )
            supervisor = result.scalar_one_or_none()
            current_id = supervisor

        # Maximale Tiefe erreicht ohne Zyklus gefunden -> sicherheitshalber True
        # (dies sollte in der Praxis nie passieren, weist auf Datenproblem hin)
        logger.warning(
            "supervisor_cycle_check_max_depth_reached",
            employee_id=str(employee_id),
            new_supervisor_id=str(new_supervisor_id),
            company_id=str(company_id),
            max_depth=max_depth,
        )
        return True


# Singleton-Instance für globalen Zugriff
employee_service = EmployeeService()

"""Position Service - Stellen-Verwaltung.

Implementiert Stellen-Operationen:
- CRUD mit Audit-Trail
- Gehalts-Maskierung basierend auf Berechtigungen
- Job-Family Statistiken
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import structlog
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError, DataError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Position, Employee, Department
from app.core.audit_logger import SecurityAuditLogger, SecurityEventType, get_audit_logger
from app.core.input_sanitization import sanitize_text_field, sanitize_search_query

logger = structlog.get_logger(__name__)


class PositionService:
    """Service für Stellen-Verwaltung.

    Security Features:
    - Audit-Logging für alle CRUD-Operationen
    - Gehalts-Maskierung für Non-HR-User
    - Input-Sanitization
    - Company Context Enforcement
    """

    # Gehalts-Felder die maskiert werden können
    SALARY_FIELDS = {'salary_band_min', 'salary_band_max', 'min_salary', 'max_salary'}

    async def list_positions(
        self,
        db: AsyncSession,
        company_id: UUID,
        user_id: UUID,
        mask_salary: bool = True,
        page: int = 1,
        per_page: int = 50,
        search: Optional[str] = None,
        department_id: Optional[UUID] = None,
        job_family: Optional[str] = None,
        is_management: Optional[bool] = None,
        include_inactive: bool = False,
        ip_address: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Listet Stellen mit optionaler Gehalts-Maskierung.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            mask_salary: Gehalts-Felder maskieren
            page: Seitennummer
            per_page: Einträge pro Seite
            search: Suchbegriff
            department_id: Filter nach Abteilung
            job_family: Filter nach Job-Familie
            is_management: Filter nach Management-Positionen
            include_inactive: Auch inaktive Stellen

        Returns:
            Tuple (Liste von Stellen-Dicts, Gesamtanzahl)
        """
        # Input-Sanitization
        if search:
            search, _ = sanitize_search_query(search, strict_mode=True)

        # Basis-Query
        query = (
            select(Position)
            .where(Position.company_id == company_id)
            .where(Position.deleted_at.is_(None))
            .options(selectinload(Position.department))
        )

        if search:
            search_term = f"%{search}%"
            query = query.where(Position.title.ilike(search_term))

        if department_id:
            query = query.where(Position.department_id == department_id)

        if job_family:
            query = query.where(Position.job_family == job_family)

        if is_management is not None:
            query = query.where(Position.is_management == is_management)

        if not include_inactive:
            query = query.where(Position.is_active == True)

        # Count
        count_query = select(func.count()).select_from(query.subquery())
        total = (await db.execute(count_query)).scalar() or 0

        # Sortierung und Paginierung
        query = query.order_by(Position.level.desc(), Position.title)
        offset = (page - 1) * per_page
        query = query.offset(offset).limit(per_page)

        result = await db.execute(query)
        positions = result.scalars().all()

        position_dicts = [
            self._position_to_dict(p, mask_salary=mask_salary)
            for p in positions
        ]

        # A.1 CRITICAL: Audit-Logging für List-Operationen (GDPR Art. 30)
        audit = get_audit_logger(db)
        await audit.log_event(
            event_type=SecurityEventType.POSITIONS_LISTED,
            user_id=str(user_id),
            ip_address=ip_address,
            resource_type="position",
            details={
                "company_id": str(company_id),
                "count": len(position_dicts),
                "total": total,
                "salary_masked": mask_salary,
                "filters": {
                    "search": bool(search),
                    "department_id": str(department_id) if department_id else None,
                    "job_family": job_family,
                    "is_management": is_management,
                    "include_inactive": include_inactive,
                },
                "page": page,
                "per_page": per_page,
            },
        )

        return position_dicts, total

    async def get_job_families(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> List[Dict[str, Any]]:
        """Holt Job-Family Statistiken.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID

        Returns:
            Liste von Job-Family Statistiken
        """
        # Positionen pro Job-Family
        pos_result = await db.execute(
            select(Position.job_family, func.count(Position.id))
            .where(Position.company_id == company_id)
            .where(Position.deleted_at.is_(None))
            .where(Position.is_active == True)
            .where(Position.job_family.isnot(None))
            .group_by(Position.job_family)
        )
        position_counts = {row[0]: row[1] for row in pos_result}

        # Mitarbeiter pro Job-Family (über Position)
        emp_result = await db.execute(
            select(Position.job_family, func.count(Employee.id))
            .join(Employee, Employee.position_id == Position.id)
            .where(Position.company_id == company_id)
            .where(Position.deleted_at.is_(None))
            .where(Employee.deleted_at.is_(None))
            .where(Position.job_family.isnot(None))
            .group_by(Position.job_family)
        )
        employee_counts = {row[0]: row[1] for row in emp_result}

        # Kombinieren
        job_families = []
        for jf in position_counts:
            job_families.append({
                'name': jf,
                'position_count': position_counts.get(jf, 0),
                'employee_count': employee_counts.get(jf, 0),
            })

        return sorted(job_families, key=lambda x: x['employee_count'], reverse=True)

    async def get_position(
        self,
        db: AsyncSession,
        position_id: UUID,
        company_id: UUID,
        user_id: UUID,
        mask_salary: bool = True,
        ip_address: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Holt eine Stelle mit optionaler Gehalts-Maskierung.

        Args:
            db: Datenbank-Session
            position_id: Stellen-ID
            company_id: Firmen-ID
            user_id: Benutzer-ID
            mask_salary: Gehalts-Felder maskieren
            ip_address: Client-IP

        Returns:
            Stellen-Dict oder None
        """
        result = await db.execute(
            select(Position)
            .where(
                Position.id == position_id,
                Position.company_id == company_id,
                Position.deleted_at.is_(None),
            )
            .options(selectinload(Position.department))
        )
        position = result.scalar_one_or_none()

        if not position:
            return None

        # Audit-Logging
        audit = get_audit_logger(db)
        await audit.log_event(
            event_type=SecurityEventType.POSITION_ACCESSED,
            user_id=str(user_id),
            ip_address=ip_address,
            resource_type="position",
            resource_id=str(position_id),
            details={"company_id": str(company_id)},
        )

        # Gehalts-Zugriff separat loggen
        if not mask_salary:
            await audit.log_event(
                event_type=SecurityEventType.POSITION_SALARY_ACCESSED,
                user_id=str(user_id),
                ip_address=ip_address,
                resource_type="position",
                resource_id=str(position_id),
                details={
                    "company_id": str(company_id),
                    "salary_fields": list(self.SALARY_FIELDS),
                },
                severity="warning",
            )

        # Mitarbeiter-Count
        emp_count = await db.execute(
            select(func.count(Employee.id))
            .where(Employee.position_id == position_id)
            .where(Employee.deleted_at.is_(None))
        )
        employee_count = emp_count.scalar() or 0

        data = self._position_to_dict(position, mask_salary=mask_salary)
        data['employee_count'] = employee_count

        return data

    async def create_position(
        self,
        db: AsyncSession,
        company_id: UUID,
        user_id: UUID,
        data: Dict[str, Any],
        ip_address: Optional[str] = None,
        mask_salary_in_response: bool = True,
    ) -> Dict[str, Any]:
        """Erstellt eine Stelle.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            user_id: Benutzer-ID
            data: Stellen-Daten
            ip_address: Client-IP

        Returns:
            Erstellte Stelle als Dict

        Raises:
            ValueError: Bei Validierungsfehlern
        """
        sanitized_data = self._sanitize_input(data)

        # Gehalts-Validierung
        min_salary = sanitized_data.get('salary_band_min')
        max_salary = sanitized_data.get('salary_band_max')

        if min_salary is not None and max_salary is not None:
            if Decimal(str(min_salary)) > Decimal(str(max_salary)):
                raise ValueError("Mindestgehalt kann nicht höher als Maximalgehalt sein.")

        # Abteilung validieren (falls angegeben)
        department_id = sanitized_data.get('department_id')
        if department_id:
            dept = await db.execute(
                select(Department).where(
                    Department.id == department_id,
                    Department.company_id == company_id,
                    Department.deleted_at.is_(None),
                )
            )
            if not dept.scalar_one_or_none():
                # H.5: Generische Fehlermeldung - keine Struktur leaken
                raise ValueError("Die referenzierte Ressource wurde nicht gefunden.")

        # Erstellen mit Transaction Error Handling (C.1 MEDIUM)
        try:
            position = Position(
                company_id=company_id,
                created_by_id=user_id,
                **sanitized_data
            )
            db.add(position)
            await db.flush()
            await db.refresh(position)

            # Audit-Logging innerhalb der Transaction
            audit = get_audit_logger(db)
            await audit.log_event(
                event_type=SecurityEventType.POSITION_CREATED,
                user_id=str(user_id),
                ip_address=ip_address,
                resource_type="position",
                resource_id=str(position.id),
                details={
                    "company_id": str(company_id),
                    # H.6 MEDIUM: title ENTFERNT - könnte sensible Info enthalten
                },
            )

            await db.commit()

            # H.6: Keine sensitiven Titel im strukturierten Log
            logger.info(
                "position_created",
                position_id=str(position.id),
                company_id=str(company_id),
                user_id=str(user_id),
            )

            # A.3 CRITICAL: Gehalt-Maskierung basierend auf Berechtigung
            return self._position_to_dict(position, mask_salary=mask_salary_in_response)

        except IntegrityError as e:
            # I.3 CRITICAL: Spezifische Exception abfangen - keine DB-Details leaken
            await db.rollback()
            logger.error(
                "position_create_integrity_error",
                error_type="IntegrityError",
                company_id=str(company_id),
                user_id=str(user_id),
            )
            raise ValueError("Ein Eintrag mit diesen Daten existiert bereits.")
        except (DataError, OperationalError) as e:
            # I.3 CRITICAL: DB-Fehler generisch behandeln
            await db.rollback()
            logger.error(
                "position_create_db_error",
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
                "position_create_unexpected_error",
                error_type=type(e).__name__,
                company_id=str(company_id),
                user_id=str(user_id),
            )
            raise ValueError("Ein unerwarteter Fehler ist aufgetreten.")

    async def update_position(
        self,
        db: AsyncSession,
        position_id: UUID,
        company_id: UUID,
        user_id: UUID,
        data: Dict[str, Any],
        ip_address: Optional[str] = None,
        mask_salary_in_response: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """Aktualisiert eine Stelle.

        Args:
            db: Datenbank-Session
            position_id: Stellen-ID
            company_id: Firmen-ID
            user_id: Benutzer-ID
            data: Update-Daten
            ip_address: Client-IP

        Returns:
            Aktualisierte Stelle oder None
        """
        result = await db.execute(
            select(Position).where(
                Position.id == position_id,
                Position.company_id == company_id,
                Position.deleted_at.is_(None),
            )
        )
        position = result.scalar_one_or_none()

        if not position:
            return None

        sanitized_data = self._sanitize_input(data)

        # H.4 HIGH: department_id Cross-Company Validierung bei Update
        department_id = sanitized_data.get('department_id')
        if department_id:
            dept_check = await db.execute(
                select(Department).where(
                    Department.id == department_id,
                    Department.company_id == company_id,
                    Department.deleted_at.is_(None),
                )
            )
            if not dept_check.scalar_one_or_none():
                # Generische Fehlermeldung - keine Company-Struktur leaken
                raise ValueError("Die referenzierte Ressource wurde nicht gefunden.")

        # Gehalts-Validierung
        min_salary = sanitized_data.get('salary_band_min', position.salary_band_min)
        max_salary = sanitized_data.get('salary_band_max', position.salary_band_max)

        if min_salary is not None and max_salary is not None:
            if Decimal(str(min_salary)) > Decimal(str(max_salary)):
                raise ValueError("Mindestgehalt kann nicht höher als Maximalgehalt sein.")

        # Gehalts-Änderungen tracken
        salary_changed = any(
            field in sanitized_data and sanitized_data[field] != getattr(position, field)
            for field in self.SALARY_FIELDS
            if field in sanitized_data
        )

        # Update mit Transaction Error Handling (C.1 MEDIUM)
        try:
            for key, value in sanitized_data.items():
                setattr(position, key, value)

            position.updated_at = datetime.now(timezone.utc)

            # Audit-Logging innerhalb der Transaction
            audit = get_audit_logger(db)
            await audit.log_event(
                event_type=SecurityEventType.POSITION_UPDATED,
                user_id=str(user_id),
                ip_address=ip_address,
                resource_type="position",
                resource_id=str(position_id),
                details={
                    "company_id": str(company_id),
                    "changed_fields": list(sanitized_data.keys()),
                    "salary_changed": salary_changed,
                },
                severity="warning" if salary_changed else "info",
            )

            await db.commit()
            await db.refresh(position)

            logger.info(
                "position_updated",
                position_id=str(position_id),
                company_id=str(company_id),
                user_id=str(user_id),
                salary_changed=salary_changed,
            )

            # A.3 CRITICAL: Gehalt-Maskierung basierend auf Berechtigung
            return self._position_to_dict(position, mask_salary=mask_salary_in_response)

        except IntegrityError as e:
            # I.3 CRITICAL: Spezifische Exception abfangen - keine DB-Details leaken
            await db.rollback()
            logger.error(
                "position_update_integrity_error",
                error_type="IntegrityError",
                position_id=str(position_id),
                company_id=str(company_id),
                user_id=str(user_id),
            )
            raise ValueError("Ein Eintrag mit diesen Daten existiert bereits.")
        except (DataError, OperationalError) as e:
            # I.3 CRITICAL: DB-Fehler generisch behandeln
            await db.rollback()
            logger.error(
                "position_update_db_error",
                error_type=type(e).__name__,
                position_id=str(position_id),
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
                "position_update_unexpected_error",
                error_type=type(e).__name__,
                position_id=str(position_id),
                company_id=str(company_id),
                user_id=str(user_id),
            )
            raise ValueError("Ein unerwarteter Fehler ist aufgetreten.")

    async def delete_position(
        self,
        db: AsyncSession,
        position_id: UUID,
        company_id: UUID,
        user_id: UUID,
        ip_address: Optional[str] = None,
    ) -> bool:
        """Löscht eine Stelle (Soft-Delete).

        Args:
            db: Datenbank-Session
            position_id: Stellen-ID
            company_id: Firmen-ID
            user_id: Benutzer-ID
            ip_address: Client-IP

        Returns:
            True wenn erfolgreich

        Raises:
            ValueError: Wenn Stelle noch Mitarbeiter hat
        """
        result = await db.execute(
            select(Position).where(
                Position.id == position_id,
                Position.company_id == company_id,
                Position.deleted_at.is_(None),
            )
        )
        position = result.scalar_one_or_none()

        if not position:
            return False

        # Prüfen auf Mitarbeiter
        emp_count = await db.execute(
            select(func.count(Employee.id))
            .where(Employee.position_id == position_id)
            .where(Employee.deleted_at.is_(None))
        )
        employee_count = emp_count.scalar() or 0

        if employee_count > 0:
            raise ValueError(
                f"Stelle hat {employee_count} zugewiesene Mitarbeiter. "
                "Bitte zuerst diese einer anderen Stelle zuweisen."
            )

        # Soft-Delete mit Transaction Error Handling (C.1 MEDIUM)
        try:
            position.deleted_at = datetime.now(timezone.utc)
            position.deleted_by_id = user_id

            # Audit-Logging innerhalb der Transaction
            audit = get_audit_logger(db)
            await audit.log_event(
                event_type=SecurityEventType.POSITION_DELETED,
                user_id=str(user_id),
                ip_address=ip_address,
                resource_type="position",
                resource_id=str(position_id),
                details={
                    "company_id": str(company_id),
                    # H.6 MEDIUM: title ENTFERNT - könnte sensible Info enthalten
                },
                severity="warning",
            )

            await db.commit()

            logger.info(
                "position_deleted",
                position_id=str(position_id),
                company_id=str(company_id),
                user_id=str(user_id),
            )

            return True

        except IntegrityError as e:
            # I.3 CRITICAL: Spezifische Exception abfangen - keine DB-Details leaken
            await db.rollback()
            logger.error(
                "position_delete_integrity_error",
                error_type="IntegrityError",
                position_id=str(position_id),
                company_id=str(company_id),
                user_id=str(user_id),
            )
            raise ValueError("Die Stelle kann nicht gelöscht werden (Referenz-Fehler).")
        except (DataError, OperationalError) as e:
            # I.3 CRITICAL: DB-Fehler generisch behandeln
            await db.rollback()
            logger.error(
                "position_delete_db_error",
                error_type=type(e).__name__,
                position_id=str(position_id),
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
                "position_delete_unexpected_error",
                error_type=type(e).__name__,
                position_id=str(position_id),
                company_id=str(company_id),
                user_id=str(user_id),
            )
            raise ValueError("Ein unerwarteter Fehler ist aufgetreten.")

    def _position_to_dict(
        self,
        position: Position,
        mask_salary: bool = True,
    ) -> Dict[str, Any]:
        """Konvertiert Position zu Dict mit optionaler Gehalts-Maskierung."""
        data = {
            'id': str(position.id),
            'title': position.title,
            'title_en': position.title_en,
            'level': position.level,
            'job_family': position.job_family,
            'department_id': str(position.department_id) if position.department_id else None,
            'department': {
                'id': str(position.department.id),
                'name': position.department.name,
                'short_name': position.department.short_name,
            } if position.department else None,
            'is_management': position.is_management,
            'is_active': position.is_active,
            'description': position.description,
            'requirements': position.requirements,
            'created_at': position.created_at.isoformat() if position.created_at else None,
            'updated_at': position.updated_at.isoformat() if position.updated_at else None,
        }

        # Gehalts-Felder
        if mask_salary:
            data['salary_band_min'] = None
            data['salary_band_max'] = None
            data['salary_masked'] = True
        else:
            data['salary_band_min'] = float(position.salary_band_min) if position.salary_band_min else None
            data['salary_band_max'] = float(position.salary_band_max) if position.salary_band_max else None
            data['salary_masked'] = False

        return data

    def _sanitize_input(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitiert Eingaben."""
        # B.3 HIGH: responsibilities hinzugefuegt für vollständige Sanitization
        text_fields = {'title', 'title_en', 'job_family', 'description', 'requirements', 'responsibilities'}
        sanitized = {}

        for key, value in data.items():
            if key in text_fields and isinstance(value, str):
                sanitized[key] = sanitize_text_field(value, max_length=500)
            else:
                sanitized[key] = value

        return sanitized


# Singleton-Instance
position_service = PositionService()

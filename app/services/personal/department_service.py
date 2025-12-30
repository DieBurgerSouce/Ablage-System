"""Department Service - Abteilungs-Verwaltung.

Implementiert Abteilungs-Operationen mit Hierarchie-Support:
- CRUD mit Audit-Trail
- Hierarchie-Validierung (keine Zyklen)
- Tree-Struktur fuer Frontend
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import structlog
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError, DataError, OperationalError

from app.db.models import Department, Employee
from app.core.audit_logger import SecurityAuditLogger, SecurityEventType, get_audit_logger
from app.core.input_sanitization import sanitize_text_field, sanitize_search_query

logger = structlog.get_logger(__name__)


class DepartmentService:
    """Service fuer Abteilungs-Verwaltung.

    Security Features:
    - Audit-Logging fuer alle CRUD-Operationen
    - Input-Sanitization
    - Company Context Enforcement
    - Hierarchie-Validierung
    """

    async def list_departments(
        self,
        db: AsyncSession,
        company_id: UUID,
        user_id: UUID,
        page: int = 1,
        per_page: int = 50,
        search: Optional[str] = None,
        parent_id: Optional[UUID] = None,
        include_inactive: bool = False,
        ip_address: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Listet Abteilungen.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            page: Seitennummer
            per_page: Eintraege pro Seite
            search: Suchbegriff
            parent_id: Filter nach Eltern-Abteilung
            include_inactive: Auch inaktive Abteilungen

        Returns:
            Tuple (Liste von Abteilungs-Dicts, Gesamtanzahl)
        """
        # Input-Sanitization
        if search:
            search, _ = sanitize_search_query(search, strict_mode=True)

        # Basis-Query
        query = (
            select(Department)
            .where(Department.company_id == company_id)
            .where(Department.deleted_at.is_(None))
        )

        if search:
            search_term = f"%{search}%"
            query = query.where(Department.name.ilike(search_term))

        if parent_id:
            query = query.where(Department.parent_id == parent_id)

        if not include_inactive:
            query = query.where(Department.is_active == True)

        # Count
        count_query = select(func.count()).select_from(query.subquery())
        total = (await db.execute(count_query)).scalar() or 0

        # Sortierung und Paginierung
        query = query.order_by(Department.sort_order, Department.name)
        offset = (page - 1) * per_page
        query = query.offset(offset).limit(per_page)

        result = await db.execute(query)
        departments = result.scalars().all()

        department_dicts = [self._department_to_dict(d) for d in departments]

        # A.1 CRITICAL: Audit-Logging fuer List-Operationen (GDPR Art. 30)
        audit = get_audit_logger(db)
        await audit.log_event(
            event_type=SecurityEventType.DEPARTMENTS_LISTED,
            user_id=str(user_id),
            ip_address=ip_address,
            resource_type="department",
            details={
                "company_id": str(company_id),
                "count": len(department_dicts),
                "total": total,
                "filters": {
                    "search": bool(search),
                    "parent_id": str(parent_id) if parent_id else None,
                    "include_inactive": include_inactive,
                },
                "page": page,
                "per_page": per_page,
            },
        )

        return department_dicts, total

    async def get_department_tree(
        self,
        db: AsyncSession,
        company_id: UUID,
        user_id: UUID,
        ip_address: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Holt die Abteilungs-Hierarchie als Baum.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID

        Returns:
            Liste von Abteilungs-Baeumen (verschachtelt)
        """
        # Alle Abteilungen holen
        result = await db.execute(
            select(Department)
            .where(Department.company_id == company_id)
            .where(Department.deleted_at.is_(None))
            .where(Department.is_active == True)
            .options(selectinload(Department.children))
            .order_by(Department.sort_order, Department.name)
        )
        all_departments = result.scalars().all()

        # Mitarbeiter-Counts holen
        counts_result = await db.execute(
            select(Employee.department_id, func.count(Employee.id))
            .where(Employee.company_id == company_id)
            .where(Employee.deleted_at.is_(None))
            .group_by(Employee.department_id)
        )
        employee_counts = {row[0]: row[1] for row in counts_result}

        # Baum aufbauen
        dept_map = {d.id: d for d in all_departments}
        root_depts = [d for d in all_departments if d.parent_id is None]

        def build_tree(dept: Department) -> Dict[str, Any]:
            children = [d for d in all_departments if d.parent_id == dept.id]
            return {
                'id': str(dept.id),
                'name': dept.name,
                'short_name': dept.short_name,
                'cost_center': dept.cost_center,
                'manager_id': str(dept.manager_id) if dept.manager_id else None,
                'is_active': dept.is_active,
                'sort_order': dept.sort_order,
                'employee_count': employee_counts.get(dept.id, 0),
                'children': [build_tree(c) for c in sorted(children, key=lambda x: (x.sort_order or 0, x.name))],
            }

        tree = [build_tree(d) for d in sorted(root_depts, key=lambda x: (x.sort_order or 0, x.name))]

        # A.1 CRITICAL / B.7 HIGH: Audit-Logging mit IP-Adresse
        audit = get_audit_logger(db)
        await audit.log_event(
            event_type=SecurityEventType.DEPARTMENTS_LISTED,
            user_id=str(user_id),
            ip_address=ip_address,
            resource_type="department",
            details={
                "company_id": str(company_id),
                "view_type": "tree",
                "total_departments": len(all_departments),
                "root_departments": len(root_depts),
            },
        )

        return tree

    async def get_department(
        self,
        db: AsyncSession,
        department_id: UUID,
        company_id: UUID,
        user_id: UUID,
        ip_address: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Holt eine Abteilung mit Audit-Logging.

        Args:
            db: Datenbank-Session
            department_id: Abteilungs-ID
            company_id: Firmen-ID
            user_id: Benutzer-ID
            ip_address: Client-IP

        Returns:
            Abteilungs-Dict oder None
        """
        result = await db.execute(
            select(Department)
            .where(
                Department.id == department_id,
                Department.company_id == company_id,
                Department.deleted_at.is_(None),
            )
            .options(selectinload(Department.children))
        )
        department = result.scalar_one_or_none()

        if not department:
            return None

        # Audit-Logging
        audit = get_audit_logger(db)
        await audit.log_event(
            event_type=SecurityEventType.DEPARTMENT_ACCESSED,
            user_id=str(user_id),
            ip_address=ip_address,
            resource_type="department",
            resource_id=str(department_id),
            details={"company_id": str(company_id)},
        )

        # Mitarbeiter-Count
        count_result = await db.execute(
            select(func.count(Employee.id))
            .where(Employee.department_id == department_id)
            .where(Employee.deleted_at.is_(None))
        )
        employee_count = count_result.scalar() or 0

        data = self._department_to_dict(department)
        data['employee_count'] = employee_count
        data['children'] = [
            self._department_to_dict(c)
            for c in department.children
            if c.deleted_at is None
        ]

        return data

    async def create_department(
        self,
        db: AsyncSession,
        company_id: UUID,
        user_id: UUID,
        data: Dict[str, Any],
        ip_address: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Erstellt eine Abteilung.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            user_id: Benutzer-ID
            data: Abteilungs-Daten
            ip_address: Client-IP

        Returns:
            Erstellte Abteilung als Dict

        Raises:
            ValueError: Bei Validierungsfehlern
        """
        sanitized_data = self._sanitize_input(data)

        # Hierarchie-Validierung
        parent_id = sanitized_data.get('parent_id')
        if parent_id:
            parent = await db.execute(
                select(Department).where(
                    Department.id == parent_id,
                    Department.company_id == company_id,
                    Department.deleted_at.is_(None),
                )
            )
            if not parent.scalar_one_or_none():
                # H.5: Generische Fehlermeldung
                raise ValueError("Die referenzierte Ressource wurde nicht gefunden.")

        # H.3 HIGH: manager_id Cross-Company Validierung
        manager_id = sanitized_data.get('manager_id')
        if manager_id:
            manager_check = await db.execute(
                select(Employee).where(
                    Employee.id == manager_id,
                    Employee.company_id == company_id,
                    Employee.deleted_at.is_(None),
                )
            )
            if not manager_check.scalar_one_or_none():
                # Generische Fehlermeldung - keine Company-Struktur leaken
                raise ValueError("Die referenzierte Ressource wurde nicht gefunden.")

        # Erstellen mit Transaction Error Handling (C.1 MEDIUM)
        try:
            department = Department(
                company_id=company_id,
                created_by_id=user_id,
                **sanitized_data
            )
            db.add(department)
            await db.flush()
            await db.refresh(department)

            # Audit-Logging innerhalb der Transaction
            audit = get_audit_logger(db)
            await audit.log_event(
                event_type=SecurityEventType.DEPARTMENT_CREATED,
                user_id=str(user_id),
                ip_address=ip_address,
                resource_type="department",
                resource_id=str(department.id),
                details={
                    "company_id": str(company_id),
                    # H.6 MEDIUM: name ENTFERNT - koennte sensible Info enthalten
                },
            )

            await db.commit()

            # H.6: Keine sensitiven Namen im strukturierten Log
            logger.info(
                "department_created",
                department_id=str(department.id),
                company_id=str(company_id),
                user_id=str(user_id),
            )

            return self._department_to_dict(department)

        except IntegrityError as e:
            # I.3 CRITICAL: Spezifische Exception abfangen
            await db.rollback()
            logger.error(
                "department_create_integrity_error",
                error_type="IntegrityError",
                company_id=str(company_id),
                user_id=str(user_id),
            )
            raise ValueError("Ein Eintrag mit diesen Daten existiert bereits.")
        except (DataError, OperationalError) as e:
            await db.rollback()
            logger.error(
                "department_create_db_error",
                error_type=type(e).__name__,
                company_id=str(company_id),
                user_id=str(user_id),
            )
            raise ValueError("Ein Datenbankfehler ist aufgetreten.")
        except ValueError:
            await db.rollback()
            raise
        except Exception as e:
            await db.rollback()
            logger.error(
                "department_create_unexpected_error",
                error_type=type(e).__name__,
                company_id=str(company_id),
                user_id=str(user_id),
            )
            raise ValueError("Ein unerwarteter Fehler ist aufgetreten.")

    async def update_department(
        self,
        db: AsyncSession,
        department_id: UUID,
        company_id: UUID,
        user_id: UUID,
        data: Dict[str, Any],
        ip_address: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Aktualisiert eine Abteilung.

        Args:
            db: Datenbank-Session
            department_id: Abteilungs-ID
            company_id: Firmen-ID
            user_id: Benutzer-ID
            data: Update-Daten
            ip_address: Client-IP

        Returns:
            Aktualisierte Abteilung oder None

        Raises:
            ValueError: Bei Validierungsfehlern (z.B. zyklische Hierarchie)
        """
        result = await db.execute(
            select(Department).where(
                Department.id == department_id,
                Department.company_id == company_id,
                Department.deleted_at.is_(None),
            )
        )
        department = result.scalar_one_or_none()

        if not department:
            return None

        sanitized_data = self._sanitize_input(data)

        # Hierarchie-Validierung (keine Zyklen)
        new_parent_id = sanitized_data.get('parent_id')
        if new_parent_id:
            if new_parent_id == department_id:
                raise ValueError("Eine Abteilung kann nicht ihr eigenes Elternteil sein.")

            # Pruefen auf Zyklen
            if await self._would_create_cycle(db, department_id, new_parent_id, company_id):
                raise ValueError("Diese Aenderung wuerde eine zyklische Hierarchie erzeugen.")

        # H.3 HIGH: manager_id Cross-Company Validierung auch bei Update
        manager_id = sanitized_data.get('manager_id')
        if manager_id:
            manager_check = await db.execute(
                select(Employee).where(
                    Employee.id == manager_id,
                    Employee.company_id == company_id,
                    Employee.deleted_at.is_(None),
                )
            )
            if not manager_check.scalar_one_or_none():
                # Generische Fehlermeldung - keine Company-Struktur leaken
                raise ValueError("Die referenzierte Ressource wurde nicht gefunden.")

        # Update mit Transaction Error Handling (C.1 MEDIUM)
        try:
            for key, value in sanitized_data.items():
                setattr(department, key, value)

            department.updated_at = datetime.now(timezone.utc)

            # Audit-Logging innerhalb der Transaction
            audit = get_audit_logger(db)
            await audit.log_event(
                event_type=SecurityEventType.DEPARTMENT_UPDATED,
                user_id=str(user_id),
                ip_address=ip_address,
                resource_type="department",
                resource_id=str(department_id),
                details={
                    "company_id": str(company_id),
                    "changed_fields": list(sanitized_data.keys()),
                },
            )

            await db.commit()
            await db.refresh(department)

            logger.info(
                "department_updated",
                department_id=str(department_id),
                company_id=str(company_id),
                user_id=str(user_id),
            )

            return self._department_to_dict(department)

        except IntegrityError as e:
            await db.rollback()
            logger.error(
                "department_update_integrity_error",
                error_type="IntegrityError",
                department_id=str(department_id),
                company_id=str(company_id),
                user_id=str(user_id),
            )
            raise ValueError("Ein Eintrag mit diesen Daten existiert bereits.")
        except (DataError, OperationalError) as e:
            await db.rollback()
            logger.error(
                "department_update_db_error",
                error_type=type(e).__name__,
                department_id=str(department_id),
                company_id=str(company_id),
                user_id=str(user_id),
            )
            raise ValueError("Ein Datenbankfehler ist aufgetreten.")
        except ValueError:
            await db.rollback()
            raise
        except Exception as e:
            await db.rollback()
            logger.error(
                "department_update_unexpected_error",
                error_type=type(e).__name__,
                department_id=str(department_id),
                company_id=str(company_id),
                user_id=str(user_id),
            )
            raise ValueError("Ein unerwarteter Fehler ist aufgetreten.")

    async def delete_department(
        self,
        db: AsyncSession,
        department_id: UUID,
        company_id: UUID,
        user_id: UUID,
        ip_address: Optional[str] = None,
    ) -> bool:
        """Loescht eine Abteilung (Soft-Delete).

        Args:
            db: Datenbank-Session
            department_id: Abteilungs-ID
            company_id: Firmen-ID
            user_id: Benutzer-ID
            ip_address: Client-IP

        Returns:
            True wenn erfolgreich

        Raises:
            ValueError: Wenn Abteilung noch Mitarbeiter oder Kinder hat
        """
        result = await db.execute(
            select(Department)
            .where(
                Department.id == department_id,
                Department.company_id == company_id,
                Department.deleted_at.is_(None),
            )
            .options(selectinload(Department.children))
        )
        department = result.scalar_one_or_none()

        if not department:
            return False

        # Pruefen auf Kinder
        active_children = [c for c in department.children if c.deleted_at is None]
        if active_children:
            raise ValueError(
                f"Abteilung hat {len(active_children)} aktive Unterabteilungen. "
                "Bitte zuerst diese loeschen oder verschieben."
            )

        # Pruefen auf Mitarbeiter
        emp_count = await db.execute(
            select(func.count(Employee.id))
            .where(Employee.department_id == department_id)
            .where(Employee.deleted_at.is_(None))
        )
        employee_count = emp_count.scalar() or 0

        if employee_count > 0:
            raise ValueError(
                f"Abteilung hat {employee_count} zugewiesene Mitarbeiter. "
                "Bitte zuerst diese einer anderen Abteilung zuweisen."
            )

        # Soft-Delete mit Transaction Error Handling (C.1 MEDIUM)
        try:
            department.deleted_at = datetime.now(timezone.utc)
            department.deleted_by_id = user_id

            # Audit-Logging innerhalb der Transaction
            audit = get_audit_logger(db)
            await audit.log_event(
                event_type=SecurityEventType.DEPARTMENT_DELETED,
                user_id=str(user_id),
                ip_address=ip_address,
                resource_type="department",
                resource_id=str(department_id),
                details={
                    "company_id": str(company_id),
                    # H.6 MEDIUM: name ENTFERNT - koennte sensible Info enthalten
                },
                severity="warning",
            )

            await db.commit()

            logger.info(
                "department_deleted",
                department_id=str(department_id),
                company_id=str(company_id),
                user_id=str(user_id),
            )

            return True

        except IntegrityError as e:
            await db.rollback()
            logger.error(
                "department_delete_integrity_error",
                error_type="IntegrityError",
                department_id=str(department_id),
                company_id=str(company_id),
                user_id=str(user_id),
            )
            raise ValueError("Die Abteilung kann nicht geloescht werden (Referenzen vorhanden).")
        except (DataError, OperationalError) as e:
            await db.rollback()
            logger.error(
                "department_delete_db_error",
                error_type=type(e).__name__,
                department_id=str(department_id),
                company_id=str(company_id),
                user_id=str(user_id),
            )
            raise ValueError("Ein Datenbankfehler ist aufgetreten.")
        except ValueError:
            await db.rollback()
            raise
        except Exception as e:
            await db.rollback()
            logger.error(
                "department_delete_unexpected_error",
                error_type=type(e).__name__,
                department_id=str(department_id),
                company_id=str(company_id),
                user_id=str(user_id),
            )
            raise ValueError("Ein unerwarteter Fehler ist aufgetreten.")

    async def _would_create_cycle(
        self,
        db: AsyncSession,
        department_id: UUID,
        new_parent_id: UUID,
        company_id: UUID,
    ) -> bool:
        """Prueft ob ein neues Parent eine Zyklus erzeugen wuerde.

        Args:
            db: Datenbank-Session
            department_id: Zu aktualisierende Abteilung
            new_parent_id: Neues Elternteil
            company_id: Firmen-ID

        Returns:
            True wenn Zyklus entstehen wuerde
        """
        # Traversiere die Hierarchie vom neuen Parent nach oben
        current_id = new_parent_id
        visited = set()

        while current_id:
            if current_id == department_id:
                return True  # Zyklus gefunden!

            if current_id in visited:
                return True  # Bereits besucht (sollte nicht vorkommen)

            visited.add(current_id)

            result = await db.execute(
                select(Department.parent_id)
                .where(Department.id == current_id)
                .where(Department.company_id == company_id)
            )
            row = result.first()
            current_id = row[0] if row else None

        return False

    def _department_to_dict(self, department: Department) -> Dict[str, Any]:
        """Konvertiert Department zu Dict."""
        return {
            'id': str(department.id),
            'name': department.name,
            'short_name': department.short_name,
            'cost_center': department.cost_center,
            'parent_id': str(department.parent_id) if department.parent_id else None,
            'manager_id': str(department.manager_id) if department.manager_id else None,
            'is_active': department.is_active,
            'sort_order': department.sort_order,
            'created_at': department.created_at.isoformat() if department.created_at else None,
            'updated_at': department.updated_at.isoformat() if department.updated_at else None,
        }

    def _sanitize_input(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitiert Eingaben."""
        # B.3 HIGH: description hinzugefuegt fuer vollstaendige Sanitization
        text_fields = {'name', 'short_name', 'cost_center', 'description'}
        sanitized = {}

        for key, value in data.items():
            if key in text_fields and isinstance(value, str):
                max_len = 500 if key == 'description' else 100
                sanitized[key] = sanitize_text_field(value, max_length=max_len)
            else:
                sanitized[key] = value

        return sanitized


# Singleton-Instance
department_service = DepartmentService()

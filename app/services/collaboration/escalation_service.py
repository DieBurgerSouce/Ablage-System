# -*- coding: utf-8 -*-
"""
Escalation Service for Ablage-System.

Enterprise-grade automatische Eskalation:
- Regelbasierte Eskalation nach Timeout
- Multi-Level Eskalationsketten
- Benachrichtigung aller Beteiligten
- Audit-Trail für Compliance

Feinpoliert und durchdacht - Eskalation auf Enterprise-Niveau.
"""

import structlog
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.datetime_utils import utc_now
from app.db.models import (
    Company,
    DocumentTask,
    EscalationRule,
    NotificationType,
    TaskPriority,
    TaskStatus,
    User,
    UserCompany,
    UserNotification,
)
from app.services.notification_service import NotificationService

logger = structlog.get_logger(__name__)


class EscalationService:
    """Service fuer automatische Aufgaben-Eskalation."""

    def __init__(self, db: AsyncSession):
        """Initialisiert den EscalationService.

        Args:
            db: AsyncSession fuer Datenbankoperationen
        """
        self.db = db

    # =========================================================================
    # Escalation Rule Management
    # =========================================================================

    async def create_rule(
        self,
        company_id: UUID,
        name: str,
        timeout_hours: int,
        escalate_to_user_id: Optional[UUID] = None,
        escalate_to_role: Optional[str] = None,
        task_type: Optional[str] = None,
        priority: Optional[str] = None,
        description: Optional[str] = None,
        notify_original_assignee: bool = True,
        notify_escalation_target: bool = True,
        notify_task_creator: bool = False,
        rule_priority: int = 100,
    ) -> EscalationRule:
        """Erstellt eine neue Eskalationsregel.

        Args:
            company_id: ID des Unternehmens
            name: Name der Regel
            timeout_hours: Stunden bis zur Eskalation
            escalate_to_user_id: Ziel-Benutzer fuer Eskalation
            escalate_to_role: Ziel-Rolle fuer Eskalation
            task_type: Filter fuer Aufgabentyp (optional)
            priority: Filter fuer Prioritaet (optional)
            description: Beschreibung der Regel
            notify_original_assignee: Benachrichtige urspr. Beauftragten
            notify_escalation_target: Benachrichtige Eskalationsziel
            notify_task_creator: Benachrichtige Ersteller
            rule_priority: Prioritaet der Regel (niedrig = hoch)

        Returns:
            Erstellte EscalationRule
        """
        rule = EscalationRule(
            company_id=company_id,
            name=name,
            description=description,
            task_type=task_type,
            priority=priority,
            timeout_hours=timeout_hours,
            escalate_to_user_id=escalate_to_user_id,
            escalate_to_role=escalate_to_role,
            notify_original_assignee=notify_original_assignee,
            notify_escalation_target=notify_escalation_target,
            notify_task_creator=notify_task_creator,
            rule_priority=rule_priority,
        )

        self.db.add(rule)
        await self.db.commit()
        await self.db.refresh(rule)

        logger.info(
            "escalation_rule_created",
            rule_id=str(rule.id),
            company_id=str(company_id),
            name=name,
            timeout_hours=timeout_hours,
        )

        return rule

    async def get_rule(
        self,
        rule_id: UUID,
        company_id: UUID,
    ) -> Optional[EscalationRule]:
        """Holt eine Eskalationsregel.

        SECURITY: company_id MUSS fuer Multi-Tenant Isolation uebergeben werden.

        Args:
            rule_id: ID der Regel
            company_id: ID des Unternehmens (Multi-Tenant)

        Returns:
            EscalationRule oder None
        """
        result = await self.db.execute(
            select(EscalationRule)
            .options(selectinload(EscalationRule.escalate_to_user))
            .where(
                and_(
                    EscalationRule.id == rule_id,
                    EscalationRule.company_id == company_id,
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_rules_for_company(
        self,
        company_id: UUID,
        include_inactive: bool = False,
    ) -> List[EscalationRule]:
        """Holt alle Eskalationsregeln eines Unternehmens.

        Args:
            company_id: ID des Unternehmens
            include_inactive: Auch inaktive Regeln einbeziehen

        Returns:
            Liste von EscalationRule
        """
        query = (
            select(EscalationRule)
            .options(selectinload(EscalationRule.escalate_to_user))
            .where(EscalationRule.company_id == company_id)
            .order_by(EscalationRule.rule_priority.asc())
        )

        if not include_inactive:
            query = query.where(EscalationRule.is_active == True)  # noqa: E712

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def update_rule(
        self,
        rule_id: UUID,
        company_id: UUID,
        **kwargs: object,
    ) -> Optional[EscalationRule]:
        """Aktualisiert eine Eskalationsregel.

        SECURITY: company_id MUSS fuer Multi-Tenant Isolation uebergeben werden.

        Args:
            rule_id: ID der Regel
            company_id: ID des Unternehmens (Multi-Tenant)
            **kwargs: Zu aktualisierende Felder

        Returns:
            Aktualisierte EscalationRule oder None
        """
        rule = await self.get_rule(rule_id, company_id=company_id)
        if not rule:
            return None

        allowed_fields = {
            "name", "description", "task_type", "priority",
            "timeout_hours", "escalate_to_user_id", "escalate_to_role",
            "notify_original_assignee", "notify_escalation_target",
            "notify_task_creator", "is_active", "rule_priority",
        }

        for key, value in kwargs.items():
            if key in allowed_fields:
                setattr(rule, key, value)

        rule.updated_at = utc_now()
        await self.db.commit()
        await self.db.refresh(rule)

        logger.info(
            "escalation_rule_updated",
            rule_id=str(rule_id),
            updated_fields=list(kwargs.keys()),
        )

        return rule

    async def delete_rule(
        self,
        rule_id: UUID,
        company_id: UUID,
    ) -> bool:
        """Loescht eine Eskalationsregel.

        SECURITY: company_id MUSS fuer Multi-Tenant Isolation uebergeben werden.

        Args:
            rule_id: ID der Regel
            company_id: ID des Unternehmens (Multi-Tenant)

        Returns:
            True bei Erfolg, False wenn nicht gefunden
        """
        rule = await self.get_rule(rule_id, company_id=company_id)
        if not rule:
            logger.warning(
                "escalation_rule_delete_failed",
                rule_id=str(rule_id),
                company_id=str(company_id),
                reason="not_found_or_wrong_company",
            )
            return False

        await self.db.delete(rule)
        await self.db.commit()

        logger.info(
            "escalation_rule_deleted",
            rule_id=str(rule_id),
            company_id=str(company_id),
        )
        return True

    # =========================================================================
    # Escalation Processing
    # =========================================================================

    async def find_matching_rule(
        self,
        task: DocumentTask,
        company_id: UUID,
    ) -> Optional[EscalationRule]:
        """Findet die passende Eskalationsregel fuer eine Aufgabe.

        Die Regeln werden nach rule_priority sortiert und die erste
        passende Regel wird zurueckgegeben.

        Args:
            task: Die zu pruefende Aufgabe
            company_id: ID des Unternehmens

        Returns:
            Passende EscalationRule oder None
        """
        # Hole alle aktiven Regeln, sortiert nach Prioritaet
        rules = await self.get_rules_for_company(company_id)

        for rule in rules:
            # Pruefe Task-Type Filter
            if rule.task_type and task.task_type != rule.task_type:
                continue

            # Pruefe Prioritaet Filter
            if rule.priority and task.priority != rule.priority:
                continue

            # Regel passt!
            return rule

        return None

    async def check_task_for_escalation(
        self,
        task: DocumentTask,
        company_id: UUID,
    ) -> Tuple[bool, Optional[EscalationRule]]:
        """Prueft ob eine Aufgabe eskaliert werden sollte.

        Args:
            task: Die zu pruefende Aufgabe
            company_id: ID des Unternehmens

        Returns:
            Tuple von (sollte_eskaliert_werden, passende_regel)
        """
        # Bereits eskaliert oder nicht mehr offen?
        if task.escalated or task.status not in [
            TaskStatus.OPEN.value,
            TaskStatus.IN_PROGRESS.value,
            TaskStatus.BLOCKED.value,
        ]:
            return (False, None)

        # Finde passende Regel
        rule = await self.find_matching_rule(task, company_id)
        if not rule:
            return (False, None)

        # Berechne Timeout-Zeitpunkt
        timeout_threshold = utc_now() - timedelta(hours=rule.timeout_hours)

        # Pruefe ob Aufgabe alt genug ist
        if task.created_at > timeout_threshold:
            return (False, None)

        return (True, rule)

    async def escalate_task(
        self,
        task: DocumentTask,
        rule: EscalationRule,
    ) -> bool:
        """Eskaliert eine Aufgabe gemaess Regel.

        Args:
            task: Die zu eskalierende Aufgabe
            rule: Die anzuwendende Eskalationsregel

        Returns:
            True bei Erfolg
        """
        now = utc_now()

        # Bestimme Eskalationsziel
        escalation_target_id = await self._determine_escalation_target(rule, task)

        if not escalation_target_id:
            logger.warning(
                "escalation_no_target",
                task_id=str(task.id),
                rule_id=str(rule.id),
            )
            return False

        # Speichere urspruenglichen Beauftragten
        original_assignee_id = task.assigned_to_id

        # Aktualisiere Aufgabe
        task.escalated = True
        task.escalated_at = now
        task.assigned_to_id = escalation_target_id

        await self.db.commit()

        # Sende Benachrichtigungen
        notification_service = NotificationService(self.db)

        # Benachrichtige Eskalationsziel
        if rule.notify_escalation_target and escalation_target_id:
            await notification_service.create_notification(
                user_id=escalation_target_id,
                notification_type=NotificationType.TASK_ESCALATED.value,
                title="Eskalierte Aufgabe zugewiesen",
                message=f"Eine ueberfaellige Aufgabe wurde an Sie eskaliert: {task.title}",
                action_url=f"/tasks/{task.id}",
                data={
                    "task_id": str(task.id),
                    "rule_id": str(rule.id),
                    "escalation_reason": f"Keine Reaktion nach {rule.timeout_hours} Stunden",
                },
            )

        # Benachrichtige urspruenglichen Beauftragten
        if rule.notify_original_assignee and original_assignee_id:
            await notification_service.create_notification(
                user_id=original_assignee_id,
                notification_type=NotificationType.TASK_ESCALATED.value,
                title="Aufgabe eskaliert",
                message=f"Ihre Aufgabe wurde wegen Zeitüberschreitung eskaliert: {task.title}",
                action_url=f"/tasks/{task.id}",
                data={
                    "task_id": str(task.id),
                    "rule_id": str(rule.id),
                    "timeout_hours": rule.timeout_hours,
                },
            )

        # Benachrichtige Ersteller
        if rule.notify_task_creator and task.created_by_id:
            await notification_service.create_notification(
                user_id=task.created_by_id,
                notification_type=NotificationType.TASK_ESCALATED.value,
                title="Ihre erstellte Aufgabe wurde eskaliert",
                message=f"Die Aufgabe '{task.title}' wurde wegen fehlender Reaktion eskaliert.",
                action_url=f"/tasks/{task.id}",
                data={
                    "task_id": str(task.id),
                    "rule_id": str(rule.id),
                },
            )

        logger.info(
            "task_escalated",
            task_id=str(task.id),
            rule_id=str(rule.id),
            original_assignee=str(original_assignee_id) if original_assignee_id else None,
            new_assignee=str(escalation_target_id),
            timeout_hours=rule.timeout_hours,
        )

        return True

    async def _determine_escalation_target(
        self,
        rule: EscalationRule,
        task: DocumentTask,
    ) -> Optional[UUID]:
        """Bestimmt das Eskalationsziel.

        Args:
            rule: Die Eskalationsregel
            task: Die Aufgabe

        Returns:
            UUID des Eskalationsziels oder None
        """
        # Direkter Benutzer hat Vorrang
        if rule.escalate_to_user_id:
            return rule.escalate_to_user_id

        # Eskalation an Rolle
        if rule.escalate_to_role:
            target = await self._find_user_by_role(
                rule.escalate_to_role,
                rule.company_id,
            )
            if target:
                return target

        # Fallback: Ersteller der Aufgabe
        return task.created_by_id

    async def _find_user_by_role(
        self,
        role: str,
        company_id: UUID,
    ) -> Optional[UUID]:
        """Findet einen Benutzer mit der angegebenen Rolle innerhalb der Company.

        SECURITY: Multi-Tenant Isolation - nur User der gleichen Company!
        Sucht ueber UserCompany Join, um sicherzustellen, dass der User
        auch Zugriff auf die Company hat.

        Args:
            role: Die gesuchte Rolle (admin, manager)
            company_id: ID des Unternehmens (MUSS verwendet werden!)

        Returns:
            UUID des Benutzers oder None
        """
        # SECURITY: Finde Admin NUR innerhalb der Company
        if role == "admin":
            # Erst: Company-Admin mit "owner" oder "admin" Rolle in UserCompany
            result = await self.db.execute(
                select(User.id)
                .join(UserCompany, UserCompany.user_id == User.id)
                .where(
                    and_(
                        UserCompany.company_id == company_id,
                        UserCompany.role.in_(["owner", "admin"]),
                        User.is_active == True,  # noqa: E712
                    )
                )
                .limit(1)
            )
            user_id = result.scalar_one_or_none()
            if user_id:
                return user_id

            # Fallback: Superuser der Company (falls Owner nicht gefunden)
            result = await self.db.execute(
                select(User.id)
                .join(UserCompany, UserCompany.user_id == User.id)
                .where(
                    and_(
                        UserCompany.company_id == company_id,
                        User.is_superuser == True,  # noqa: E712
                        User.is_active == True,  # noqa: E712
                    )
                )
                .limit(1)
            )
            user_id = result.scalar_one_or_none()
            return user_id

        # Manager-Rolle: Finde User mit manager-Rolle in dieser Company
        if role == "manager":
            result = await self.db.execute(
                select(User.id)
                .join(UserCompany, UserCompany.user_id == User.id)
                .where(
                    and_(
                        UserCompany.company_id == company_id,
                        UserCompany.role == "manager",
                        User.is_active == True,  # noqa: E712
                    )
                )
                .limit(1)
            )
            user_id = result.scalar_one_or_none()
            return user_id

        return None

    # =========================================================================
    # Batch Processing
    # =========================================================================

    async def process_escalations_for_company(
        self,
        company_id: UUID,
    ) -> Dict[str, int]:
        """Verarbeitet alle faelligen Eskalationen fuer ein Unternehmen.

        Args:
            company_id: ID des Unternehmens

        Returns:
            Statistiken ueber verarbeitete Eskalationen
        """
        stats = {
            "tasks_checked": 0,
            "tasks_escalated": 0,
            "rules_applied": 0,
        }

        # Hole alle offenen, nicht-eskalierten Aufgaben
        result = await self.db.execute(
            select(DocumentTask)
            .options(
                selectinload(DocumentTask.assigned_to),
                selectinload(DocumentTask.created_by),
            )
            .join(DocumentTask.document)
            .where(
                and_(
                    DocumentTask.escalated == False,  # noqa: E712
                    DocumentTask.status.in_([
                        TaskStatus.OPEN.value,
                        TaskStatus.IN_PROGRESS.value,
                        TaskStatus.BLOCKED.value,
                    ]),
                )
            )
        )

        tasks = result.scalars().all()
        stats["tasks_checked"] = len(tasks)

        rules_used: set[UUID] = set()

        for task in tasks:
            should_escalate, rule = await self.check_task_for_escalation(
                task, company_id
            )

            if should_escalate and rule:
                success = await self.escalate_task(task, rule)
                if success:
                    stats["tasks_escalated"] += 1
                    rules_used.add(rule.id)

        stats["rules_applied"] = len(rules_used)

        logger.info(
            "escalation_batch_completed",
            company_id=str(company_id),
            **stats,
        )

        return stats

    async def process_all_escalations(self) -> Dict[str, Any]:
        """Verarbeitet Eskalationen fuer alle Unternehmen.

        Returns:
            Aggregierte Statistiken
        """
        # Hole alle Unternehmen mit aktiven Eskalationsregeln
        result = await self.db.execute(
            select(Company.id)
            .join(EscalationRule, EscalationRule.company_id == Company.id)
            .where(EscalationRule.is_active == True)  # noqa: E712
            .distinct()
        )

        company_ids = [row[0] for row in result.fetchall()]

        total_stats = {
            "companies_processed": 0,
            "total_tasks_checked": 0,
            "total_tasks_escalated": 0,
        }

        for company_id in company_ids:
            stats = await self.process_escalations_for_company(company_id)
            total_stats["companies_processed"] += 1
            total_stats["total_tasks_checked"] += stats["tasks_checked"]
            total_stats["total_tasks_escalated"] += stats["tasks_escalated"]

        logger.info(
            "escalation_global_batch_completed",
            **total_stats,
        )

        return total_stats

    # =========================================================================
    # Statistics
    # =========================================================================

    async def get_escalation_statistics(
        self,
        company_id: UUID,
        days: int = 30,
    ) -> Dict[str, Any]:
        """Holt Eskalations-Statistiken.

        Args:
            company_id: ID des Unternehmens
            days: Anzahl Tage fuer Statistik

        Returns:
            Statistik-Dict
        """
        cutoff = utc_now() - timedelta(days=days)

        # Anzahl eskalierter Aufgaben im Zeitraum
        escalated_result = await self.db.execute(
            select(func.count(DocumentTask.id))
            .join(DocumentTask.document)
            .where(
                and_(
                    DocumentTask.escalated == True,  # noqa: E712
                    DocumentTask.escalated_at >= cutoff,
                )
            )
        )
        escalated_count = escalated_result.scalar_one()

        # Gesamt-Aufgaben im Zeitraum
        total_result = await self.db.execute(
            select(func.count(DocumentTask.id))
            .join(DocumentTask.document)
            .where(DocumentTask.created_at >= cutoff)
        )
        total_count = total_result.scalar_one()

        # Aktive Regeln
        rules = await self.get_rules_for_company(company_id)

        # Durchschnittliche Zeit bis Eskalation
        avg_time_result = await self.db.execute(
            select(
                func.avg(
                    func.extract(
                        "epoch",
                        DocumentTask.escalated_at - DocumentTask.created_at,
                    )
                )
            )
            .where(
                and_(
                    DocumentTask.escalated == True,  # noqa: E712
                    DocumentTask.escalated_at >= cutoff,
                )
            )
        )
        avg_seconds = avg_time_result.scalar_one()
        avg_hours = round(avg_seconds / 3600, 1) if avg_seconds else 0

        return {
            "period_days": days,
            "escalated_tasks": escalated_count,
            "total_tasks": total_count,
            "escalation_rate": round(
                (escalated_count / total_count * 100) if total_count > 0 else 0, 2
            ),
            "active_rules": len(rules),
            "avg_hours_to_escalation": avg_hours,
        }


# =============================================================================
# Factory Function
# =============================================================================


def get_escalation_service(db: AsyncSession) -> EscalationService:
    """Factory-Funktion fuer EscalationService.

    Args:
        db: AsyncSession fuer Datenbankoperationen

    Returns:
        EscalationService Instanz
    """
    return EscalationService(db)

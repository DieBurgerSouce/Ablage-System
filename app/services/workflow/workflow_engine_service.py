"""Workflow Engine Service für Regel-basierte Automation.

Enterprise Feature: Automatische Regel-Evaluation und Aktions-Ausführung.

Features:
- Entity-basierte Regel-Evaluation mit Multi-Tenant Security
- Bedingungsprüfung (Amount, Category, Risk, etc.)
- Multi-Action Execution
- Approval Request Creation
- Eskalation Management
- Echte DB-Integration mit SQLAlchemy
"""

from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    ApprovalRule,
    ApprovalRequest,
    ApprovalStep,
    ApprovalStatus,
    ApprovalPriority,
    User,
)
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


@dataclass
class WorkflowCondition:
    """Eine Workflow-Bedingung für typsichere Prüfung."""

    field: str
    operator: str  # gt, lt, eq, in, not_in
    value: Decimal | str | list[str]


@dataclass
class WorkflowAction:
    """Eine Workflow-Aktion."""

    action_type: str  # require_approval, notify, auto_approve, escalate
    approver_role: Optional[str] = None
    approver_user_id: Optional[UUID] = None
    deadline_hours: Optional[int] = None
    notification_users: Optional[list[UUID]] = None
    escalate_to_role: Optional[str] = None


class WorkflowEngineService:
    """Engine für Regel-basierte Workflow-Ausführung.

    Evaluiert Entities gegen definierte Regeln und führt
    entsprechende Aktionen aus (Approvals, Notifications, etc.).

    Multi-Tenant Security: Alle Operationen erfordern company_id!
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialisiert den Service.

        Args:
            db: Async Database Session
        """
        self.db = db

    async def evaluate_entity(
        self,
        company_id: UUID,
        entity_type: str,
        entity_id: UUID,
        event: str,
    ) -> list[UUID]:
        """Evaluiert alle Regeln für eine Entity.

        Args:
            company_id: UUID des Unternehmens (Multi-Tenant Security!)
            entity_type: Art der Entity (invoice, expense, etc.)
            entity_id: UUID der Entity
            event: Ausgeloestes Event (created, updated, etc.)

        Returns:
            Liste von erstellten ApprovalRequest IDs
        """
        logger.info(
            "workflow_evaluation_started",
            company_id=str(company_id),
            entity_type=entity_type,
            entity_id=str(entity_id),
            event=event,
        )

        rules = await self._get_matching_rules(company_id, entity_type, event)
        entity = await self._get_entity(entity_type, entity_id, company_id)

        if not entity:
            logger.warning(
                "entity_not_found_for_workflow",
                entity_type=entity_type,
                entity_id=str(entity_id),
            )
            return []

        created_requests: list[UUID] = []

        for rule in rules:
            if self._matches_conditions(entity, rule.conditions):
                logger.info(
                    "rule_matched",
                    rule_id=str(rule.id),
                    rule_name=rule.name,
                    entity_id=str(entity_id),
                )
                request_ids = await self._execute_rule_actions(
                    company_id=company_id,
                    entity=entity,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    rule=rule,
                )
                created_requests.extend(request_ids)

        logger.info(
            "workflow_evaluation_completed",
            company_id=str(company_id),
            entity_id=str(entity_id),
            rules_checked=len(rules),
            requests_created=len(created_requests),
        )

        return created_requests

    async def create_rule(
        self,
        company_id: UUID,
        name: str,
        entity_types: list[str],
        conditions: dict[str, Decimal | str | list[str]],
        approval_chain: list[dict[str, str | int | bool]],
        description: Optional[str] = None,
        priority: int = 100,
        sla_hours: int = 48,
        escalation_after_hours: Optional[int] = None,
        escalation_to_role: Optional[str] = None,
        created_by_id: Optional[UUID] = None,
    ) -> ApprovalRule:
        """Erstellt eine neue Workflow-Regel.

        Args:
            company_id: UUID des Unternehmens
            name: Name der Regel
            entity_types: Betroffene Entity-Arten
            conditions: Bedingungen als Dict
            approval_chain: Genehmiger-Chain
            description: Optionale Beschreibung
            priority: Priorität (niedriger = höher)
            sla_hours: Max. Bearbeitungszeit in Stunden
            escalation_after_hours: Stunden bis zur Eskalation
            escalation_to_role: Eskalations-Ziel-Rolle
            created_by_id: Ersteller-User-ID

        Returns:
            Erstellte ApprovalRule
        """
        from app.db.models import ApprovalRuleType

        rule = ApprovalRule(
            company_id=company_id,
            name=name,
            description=description,
            rule_type=ApprovalRuleType.AMOUNT_THRESHOLD,  # Default
            entity_types=entity_types,
            conditions=conditions,
            approval_chain=approval_chain,
            priority=priority,
            sla_hours=sla_hours,
            escalation_after_hours=escalation_after_hours,
            escalation_to_role=escalation_to_role,
            created_by_id=created_by_id,
            is_active=True,
        )

        self.db.add(rule)
        await self.db.commit()
        await self.db.refresh(rule)

        logger.info(
            "workflow_rule_created",
            rule_id=str(rule.id),
            company_id=str(company_id),
            name=name,
        )

        return rule

    def _matches_conditions(
        self,
        entity: object,
        conditions: dict[str, Decimal | str | list[str]],
    ) -> bool:
        """Prüft ob eine Entity die Bedingungen erfuellt.

        Unterstützte Bedingungen:
        - amount_greater_than: Betrag größer als
        - amount_less_than: Betrag kleiner als
        - category: Kategorie gleich
        - category_in: Kategorie in Liste
        - supplier_risk_level: Lieferanten-Risiko gleich
        - cost_center_id: Kostenstelle gleich

        Args:
            entity: Die zu prüfende Entity
            conditions: Dict mit Bedingungen

        Returns:
            True wenn alle Bedingungen erfuellt sind
        """
        if not conditions:
            return True

        for key, value in conditions.items():
            if key == "amount_greater_than":
                entity_amount = getattr(entity, "amount", None) or getattr(
                    entity, "total_amount", Decimal("0")
                )
                if entity_amount <= Decimal(str(value)):
                    return False

            elif key == "amount_less_than":
                entity_amount = getattr(entity, "amount", None) or getattr(
                    entity, "total_amount", Decimal("0")
                )
                if entity_amount >= Decimal(str(value)):
                    return False

            elif key == "category":
                entity_category = getattr(entity, "category", None)
                if entity_category != value:
                    return False

            elif key == "category_in":
                entity_category = getattr(entity, "category", None)
                if isinstance(value, list) and entity_category not in value:
                    return False

            elif key == "supplier_risk_level":
                entity_risk = getattr(entity, "supplier_risk_level", None)
                if entity_risk != value:
                    return False

            elif key == "cost_center_id":
                entity_cc = getattr(entity, "cost_center_id", None)
                if str(entity_cc) != str(value):
                    return False

        return True

    async def _execute_rule_actions(
        self,
        company_id: UUID,
        entity: object,
        entity_type: str,
        entity_id: UUID,
        rule: ApprovalRule,
    ) -> list[UUID]:
        """Führt alle Aktionen einer Regel aus.

        Args:
            company_id: Company-ID (Multi-Tenant Security)
            entity: Die betroffene Entity
            entity_type: Entity-Typ
            entity_id: Entity-ID
            rule: Die ausloesende Regel

        Returns:
            Liste von erstellten ApprovalRequest IDs
        """
        created_requests: list[UUID] = []

        # Erstelle ApprovalRequest basierend auf der approval_chain der Regel
        if rule.approval_chain:
            request_id = await self._create_approval_request(
                company_id=company_id,
                entity=entity,
                entity_type=entity_type,
                entity_id=entity_id,
                rule=rule,
            )
            if request_id:
                created_requests.append(request_id)

        return created_requests

    async def _create_approval_request(
        self,
        company_id: UUID,
        entity: object,
        entity_type: str,
        entity_id: UUID,
        rule: ApprovalRule,
    ) -> Optional[UUID]:
        """Erstellt eine Genehmigungsanfrage.

        Args:
            company_id: Company-ID (Multi-Tenant Security)
            entity: Die zu genehmigende Entity
            entity_type: Entity-Typ
            entity_id: Entity-ID
            rule: Die ausloesende Regel

        Returns:
            ID der erstellten ApprovalRequest oder None
        """
        # Berechne Deadlines
        now = datetime.now(timezone.utc)
        due_date = None
        escalation_date = None

        if rule.sla_hours:
            due_date = now + timedelta(hours=rule.sla_hours)

        if rule.escalation_after_hours:
            escalation_date = now + timedelta(hours=rule.escalation_after_hours)

        # Hole Betrag falls vorhanden
        amount = getattr(entity, "amount", None) or getattr(
            entity, "total_amount", None
        )

        # Erstelle Titel
        title = f"Genehmigung erforderlich: {entity_type.title()} #{str(entity_id)[:8]}"

        approval_request = ApprovalRequest(
            company_id=company_id,
            entity_type=entity_type,
            entity_id=entity_id,
            triggered_by_rule_id=rule.id,
            title=title,
            description=rule.description,
            amount=amount,
            currency="EUR",
            status=ApprovalStatus.PENDING,
            priority=ApprovalPriority.NORMAL,
            current_step=1,
            total_steps=len(rule.approval_chain),
            approval_chain=rule.approval_chain,
            due_date=due_date,
            escalation_date=escalation_date,
        )

        self.db.add(approval_request)
        await self.db.flush()  # Um die ID zu bekommen

        # Erstelle ApprovalSteps für jeden Schritt in der Chain
        for step_data in rule.approval_chain:
            step_number = step_data.get("step", 1)
            approver_type = step_data.get("type", "role")
            approver_value = step_data.get("value", "")
            is_required = step_data.get("required", True)

            approval_step = ApprovalStep(
                approval_request_id=approval_request.id,
                step_number=step_number,
                approver_type=approver_type,
                approver_value=str(approver_value),
                is_required=is_required,
                status=ApprovalStatus.PENDING if step_number == 1 else ApprovalStatus.PENDING,
            )
            self.db.add(approval_step)

        await self.db.commit()
        await self.db.refresh(approval_request)

        logger.info(
            "approval_request_created",
            request_id=str(approval_request.id),
            company_id=str(company_id),
            entity_type=entity_type,
            entity_id=str(entity_id),
            rule_id=str(rule.id),
            total_steps=len(rule.approval_chain),
        )

        return approval_request.id

    async def approve_step(
        self,
        company_id: UUID,
        request_id: UUID,
        approver_id: UUID,
        notes: Optional[str] = None,
    ) -> bool:
        """Genehmigt den aktuellen Schritt einer Anfrage.

        Args:
            company_id: Company-ID (Multi-Tenant Security)
            request_id: ApprovalRequest-ID
            approver_id: User-ID des Genehmigers
            notes: Optionale Anmerkungen

        Returns:
            True wenn erfolgreich, False sonst
        """
        request = await self._get_approval_request(request_id, company_id)
        if not request:
            return False

        if request.status != ApprovalStatus.PENDING:
            logger.warning(
                "approval_request_not_pending",
                request_id=str(request_id),
                current_status=str(request.status),
            )
            return False

        # Aktualisiere aktuellen Step
        current_step = await self._get_current_step(request)
        if current_step:
            current_step.status = ApprovalStatus.APPROVED
            current_step.decision = "approved"
            current_step.decision_by_id = approver_id
            current_step.decision_date = datetime.now(timezone.utc)
            current_step.decision_notes = notes

        # Prüfe ob alle Schritte abgeschlossen
        if request.current_step >= request.total_steps:
            request.status = ApprovalStatus.APPROVED
            request.resolved_at = datetime.now(timezone.utc)
            request.resolved_by_id = approver_id
            request.resolution_notes = notes
            await self._on_request_approved(request)
        else:
            # Nächster Schritt
            request.current_step += 1

        await self.db.commit()

        logger.info(
            "approval_step_approved",
            request_id=str(request_id),
            approver_id=str(approver_id),
            new_step=request.current_step,
            final_status=str(request.status),
        )

        return True

    async def reject_step(
        self,
        company_id: UUID,
        request_id: UUID,
        rejector_id: UUID,
        notes: Optional[str] = None,
    ) -> bool:
        """Lehnt eine Anfrage ab.

        Args:
            company_id: Company-ID (Multi-Tenant Security)
            request_id: ApprovalRequest-ID
            rejector_id: User-ID des Ablehnenden
            notes: Optionale Anmerkungen (sollte Begruendung enthalten)

        Returns:
            True wenn erfolgreich, False sonst
        """
        request = await self._get_approval_request(request_id, company_id)
        if not request:
            return False

        if request.status != ApprovalStatus.PENDING:
            return False

        # Aktualisiere aktuellen Step
        current_step = await self._get_current_step(request)
        if current_step:
            current_step.status = ApprovalStatus.REJECTED
            current_step.decision = "rejected"
            current_step.decision_by_id = rejector_id
            current_step.decision_date = datetime.now(timezone.utc)
            current_step.decision_notes = notes

        # Gesamte Anfrage ablehnen
        request.status = ApprovalStatus.REJECTED
        request.resolved_at = datetime.now(timezone.utc)
        request.resolved_by_id = rejector_id
        request.resolution_notes = notes

        await self.db.commit()
        await self._on_request_rejected(request)

        logger.info(
            "approval_request_rejected",
            request_id=str(request_id),
            rejector_id=str(rejector_id),
        )

        return True

    async def escalate_request(
        self,
        company_id: UUID,
        request_id: UUID,
    ) -> bool:
        """Eskaliert eine Anfrage.

        Args:
            company_id: Company-ID (Multi-Tenant Security)
            request_id: ApprovalRequest-ID

        Returns:
            True wenn erfolgreich, False sonst
        """
        request = await self._get_approval_request(request_id, company_id)
        if not request:
            return False

        request.is_escalated = True
        request.priority = ApprovalPriority.URGENT

        await self.db.commit()

        logger.info(
            "approval_request_escalated",
            request_id=str(request_id),
            company_id=str(company_id),
        )

        # Benachrichtigung an Eskalations-Ziel senden
        await self._send_escalation_notification(request)
        return True

    async def _send_escalation_notification(
        self,
        request: ApprovalRequest,
    ) -> None:
        """Sendet Eskalations-Benachrichtigung an zuständige Personen.

        Args:
            request: Die eskalierte ApprovalRequest
        """
        from app.services.notification_service import (
            NotificationService,
            NotificationType,
            NotificationPriority,
        )
        from app.db.models import Role, user_roles

        try:
            notification_service = NotificationService()

            # Finde Eskalations-Rolle aus aktueller Approval Chain Step
            escalation_role: Optional[str] = None
            if request.approval_chain and request.current_step > 0:
                # approval_chain ist eine Liste von Step-Konfigurationen
                step_index = request.current_step - 1
                if step_index < len(request.approval_chain):
                    current_chain_step = request.approval_chain[step_index]
                    escalation_role = current_chain_step.get("escalation_to_role")

            # Fallback: Finde Admins wenn keine spezifische Rolle
            target_role = escalation_role or "admin"

            # Finde User mit der Ziel-Rolle
            role_query = select(User).join(
                user_roles, User.id == user_roles.c.user_id
            ).join(
                Role, Role.id == user_roles.c.role_id
            ).where(
                Role.name == target_role,
                Role.is_active == True,
                User.is_active == True,
            )
            result = await self.db.execute(role_query)
            target_users = result.scalars().all()

            # Sende Benachrichtigung an alle Ziel-User
            for user in target_users:
                if user.email:
                    await notification_service.notify(
                        notification_type=NotificationType.APPROVAL_ESCALATED,
                        context={
                            "request_id": str(request.id),
                            "request_title": request.title,
                            "entity_type": request.entity_type,
                            "entity_id": str(request.entity_id),
                            "amount": str(request.amount) if request.amount else None,
                            "currency": request.currency,
                            "original_priority": "NORMAL",
                            "escalated_to_role": target_role,
                        },
                        user_id=str(user.id),
                        email=user.email,
                        priority=NotificationPriority.URGENT,
                    )

            logger.info(
                "escalation_notification_sent",
                request_id=str(request.id),
                target_role=target_role,
                notified_users=len(target_users),
            )

        except Exception as e:
            logger.error(
                "escalation_notification_failed",
                request_id=str(request.id),
                **safe_error_log(e),
            )

    async def _on_request_approved(self, request: ApprovalRequest) -> None:
        """Callback nach erfolgreicher Genehmigung.

        Args:
            request: Die genehmigte ApprovalRequest
        """
        # Aktualisiere die Original-Entity
        entity = await self._get_entity(
            request.entity_type,
            request.entity_id,
            request.company_id,
        )
        if entity and hasattr(entity, "status"):
            entity.status = "approved"
            if hasattr(entity, "approved_at"):
                entity.approved_at = datetime.now(timezone.utc)
            await self.db.commit()

        logger.info(
            "entity_auto_approved",
            entity_type=request.entity_type,
            entity_id=str(request.entity_id),
        )

    async def _on_request_rejected(self, request: ApprovalRequest) -> None:
        """Callback nach Ablehnung.

        Args:
            request: Die abgelehnte ApprovalRequest
        """
        # Aktualisiere die Original-Entity
        entity = await self._get_entity(
            request.entity_type,
            request.entity_id,
            request.company_id,
        )
        if entity and hasattr(entity, "status"):
            entity.status = "rejected"
            if hasattr(entity, "rejected_at"):
                entity.rejected_at = datetime.now(timezone.utc)
            await self.db.commit()

        logger.info(
            "entity_rejected",
            entity_type=request.entity_type,
            entity_id=str(request.entity_id),
        )

    async def _get_matching_rules(
        self,
        company_id: UUID,
        entity_type: str,
        event: str,
    ) -> list[ApprovalRule]:
        """Laedt passende Regeln für Entity-Type und Event.

        Args:
            company_id: Company-ID (Multi-Tenant Security!)
            entity_type: Art der Entity
            event: Ausgeloestes Event (wird für spätere Erweiterung benötigt)

        Returns:
            Liste passender aktiver Regeln, sortiert nach Priorität
        """
        from sqlalchemy.dialects.postgresql import JSONB
        from sqlalchemy import cast

        stmt = (
            select(ApprovalRule)
            .where(
                ApprovalRule.company_id == company_id,  # Multi-Tenant Security!
                ApprovalRule.is_active.is_(True),
            )
            .order_by(ApprovalRule.priority.asc())
        )

        result = await self.db.execute(stmt)
        all_rules = list(result.scalars().all())

        # Filter nach entity_type (entity_types ist ein JSON Array)
        matching_rules = [
            rule for rule in all_rules
            if entity_type in (rule.entity_types or [])
        ]

        logger.debug(
            "matching_rules_found",
            company_id=str(company_id),
            entity_type=entity_type,
            total_rules=len(all_rules),
            matching_rules=len(matching_rules),
        )

        return matching_rules

    async def _get_entity(
        self,
        entity_type: str,
        entity_id: UUID,
        company_id: UUID,
    ) -> Optional[object]:
        """Laedt eine Entity aus der Datenbank.

        Args:
            entity_type: Art der Entity
            entity_id: UUID der Entity
            company_id: Company-ID (Multi-Tenant Security!)

        Returns:
            Die geladene Entity oder None
        """
        # Importiere die relevanten Models dynamisch
        from app.db.models import (

            Invoice,
            Expense,
            Document,
            PurchaseOrder,
        )

        model_map: dict[str, type] = {
            "invoice": Invoice,
            "expense": Expense,
            "document": Document,
            "purchase_order": PurchaseOrder,
        }

        model_class = model_map.get(entity_type.lower())
        if not model_class:
            logger.warning(
                "unknown_entity_type",
                entity_type=entity_type,
            )
            return None

        # Prüfe ob Model company_id hat (Multi-Tenant)
        has_company_id = hasattr(model_class, "company_id")

        if has_company_id:
            stmt = select(model_class).where(
                model_class.id == entity_id,
                model_class.company_id == company_id,  # Multi-Tenant Security!
            )
        else:
            # Fallback für Models ohne company_id (sollte selten sein)
            stmt = select(model_class).where(model_class.id == entity_id)

        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_approval_request(
        self,
        request_id: UUID,
        company_id: UUID,
    ) -> Optional[ApprovalRequest]:
        """Laedt eine ApprovalRequest mit Multi-Tenant Security.

        Args:
            request_id: ID der ApprovalRequest
            company_id: Company-ID (Multi-Tenant Security!)

        Returns:
            ApprovalRequest oder None
        """
        stmt = select(ApprovalRequest).where(
            ApprovalRequest.id == request_id,
            ApprovalRequest.company_id == company_id,  # Multi-Tenant Security!
        )

        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_current_step(
        self,
        request: ApprovalRequest,
    ) -> Optional[ApprovalStep]:
        """Holt den aktuellen ApprovalStep.

        Args:
            request: Die ApprovalRequest

        Returns:
            Der aktuelle ApprovalStep oder None
        """
        stmt = select(ApprovalStep).where(
            ApprovalStep.approval_request_id == request.id,
            ApprovalStep.step_number == request.current_step,
        )

        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_approvers_by_role(
        self,
        company_id: UUID,
        role: str,
    ) -> list[User]:
        """Laedt alle Approver mit einer bestimmten Rolle.

        Args:
            company_id: Company-ID (Multi-Tenant Security!)
            role: Rollen-Name (manager, director, cfo, etc.)

        Returns:
            Liste von Usern mit dieser Rolle
        """
        # Annahme: User hat ein role-Feld oder eine Relationship zu Roles
        stmt = (
            select(User)
            .where(
                User.company_id == company_id,  # Multi-Tenant Security!
                User.is_active.is_(True),
            )
        )

        result = await self.db.execute(stmt)
        all_users = result.scalars().all()

        # Filter nach Rolle (Annahme: role ist ein Feld oder in roles-JSON)
        approvers = [
            user for user in all_users
            if getattr(user, "role", None) == role
            or role in (getattr(user, "roles", []) or [])
        ]

        return approvers

    async def get_pending_requests_for_user(
        self,
        company_id: UUID,
        user_id: UUID,
    ) -> list[ApprovalRequest]:
        """Holt alle offenen Anfragen für einen User.

        Args:
            company_id: Company-ID (Multi-Tenant Security!)
            user_id: User-ID

        Returns:
            Liste offener ApprovalRequests
        """
        # Hole User um Rolle zu bestimmen
        user_stmt = select(User).where(User.id == user_id)
        user_result = await self.db.execute(user_stmt)
        user = user_result.scalar_one_or_none()

        if not user:
            return []

        user_role = getattr(user, "role", "")

        # Hole alle pending Requests der Company
        stmt = (
            select(ApprovalRequest)
            .where(
                ApprovalRequest.company_id == company_id,  # Multi-Tenant Security!
                ApprovalRequest.status == ApprovalStatus.PENDING,
            )
            .order_by(ApprovalRequest.created_at.desc())
        )

        result = await self.db.execute(stmt)
        all_pending = list(result.scalars().all())

        # Filter: Nur Requests wo User im aktuellen Step ist
        user_requests = []
        for request in all_pending:
            chain = request.approval_chain or []
            if request.current_step <= len(chain):
                current_step_data = chain[request.current_step - 1]
                step_type = current_step_data.get("type", "")
                step_value = current_step_data.get("value", "")

                if step_type == "user" and str(step_value) == str(user_id):
                    user_requests.append(request)
                elif step_type == "role" and step_value == user_role:
                    user_requests.append(request)

        return user_requests

    async def check_and_escalate_overdue(
        self,
        company_id: UUID,
    ) -> int:
        """Prüft und eskaliert überfällige Requests.

        Batch-Methode für Celery Tasks.

        Args:
            company_id: Company-ID (Multi-Tenant Security!)

        Returns:
            Anzahl eskalierter Requests
        """
        now = datetime.now(timezone.utc)

        stmt = (
            select(ApprovalRequest)
            .where(
                ApprovalRequest.company_id == company_id,  # Multi-Tenant Security!
                ApprovalRequest.status == ApprovalStatus.PENDING,
                ApprovalRequest.is_escalated.is_(False),
                ApprovalRequest.escalation_date <= now,
            )
        )

        result = await self.db.execute(stmt)
        overdue_requests = list(result.scalars().all())

        escalated_count = 0
        for request in overdue_requests:
            success = await self.escalate_request(company_id, request.id)
            if success:
                escalated_count += 1

        logger.info(
            "overdue_requests_escalated",
            company_id=str(company_id),
            total_overdue=len(overdue_requests),
            escalated=escalated_count,
        )

        return escalated_count

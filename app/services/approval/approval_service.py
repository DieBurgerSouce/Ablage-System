"""Approval Service für Enterprise Genehmigungsworkflows.

Enterprise Feature: Verwaltet Genehmigungsanfragen mit:
- Multi-Step Approval Chains
- Eskalation bei Timeout
- Delegation
- Integration mit Notifications und Workflows
"""

from __future__ import annotations

import structlog
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.core.datetime_utils import utc_now
from decimal import Decimal
from typing import Any, Optional, Sequence
from uuid import UUID

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import (
    ApprovalPriority,
    ApprovalRequest,
    ApprovalRule,
    ApprovalStatus,
    ApprovalStep,
    Role,
    User,
    user_roles,
)
from app.services.approval.approval_rule_service import ApprovalRuleService

logger = structlog.get_logger(__name__)


@dataclass
class ApprovalSummary:
    """Zusammenfassung der Genehmigungen für ein Dashboard."""

    total_pending: int
    total_approved: int
    total_rejected: int
    total_escalated: int
    avg_resolution_hours: float
    overdue_count: int
    my_pending: int  # Für aktuellen User


@dataclass
class ApprovalDecision:
    """Ergebnis einer Genehmigungsentscheidung."""

    success: bool
    request_status: ApprovalStatus
    next_step: Optional[int]
    message: str


class ApprovalService:
    """Service für Genehmigungsanfragen.

    Verwaltet den kompletten Lebenszyklus von Genehmigungsanfragen
    inklusive Multi-Step Chains, Eskalation und Delegation.
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialisiert den Approval Service.

        Args:
            db: Async Database Session
        """
        self.db = db
        self.rule_service = ApprovalRuleService(db)

    async def create_approval_request(
        self,
        company_id: UUID,
        entity_type: str,
        entity_id: UUID,
        title: str,
        approval_chain: list[dict[str, Any]],
        requested_by_id: Optional[UUID] = None,
        description: Optional[str] = None,
        amount: Optional[Decimal] = None,
        currency: str = "EUR",
        priority: ApprovalPriority = ApprovalPriority.NORMAL,
        triggered_by_rule_id: Optional[UUID] = None,
        workflow_execution_id: Optional[UUID] = None,
        sla_hours: int = 48,
        metadata: Optional[dict[str, Any]] = None,
    ) -> ApprovalRequest:
        """Erstellt eine neue Genehmigungsanfrage.

        Args:
            company_id: ID der Firma
            entity_type: Typ der zu genehmigenden Entität
            entity_id: ID der Entität
            title: Titel der Anfrage
            approval_chain: Genehmiger-Kette
            requested_by_id: ID des Antragstellers
            description: Beschreibung
            amount: Betrag falls relevant
            currency: Währung
            priority: Priorität
            triggered_by_rule_id: ID der ausloesenden Regel
            workflow_execution_id: ID der Workflow-Ausführung
            sla_hours: Max. Bearbeitungszeit
            metadata: Zusätzliche Daten

        Returns:
            Erstellte ApprovalRequest
        """
        now = utc_now()
        due_date = now + timedelta(hours=sla_hours)

        request = ApprovalRequest(
            company_id=company_id,
            entity_type=entity_type,
            entity_id=entity_id,
            title=title,
            description=description,
            amount=amount,
            currency=currency,
            status=ApprovalStatus.PENDING,
            priority=priority,
            current_step=1,
            total_steps=len(approval_chain),
            approval_chain=approval_chain,
            due_date=due_date,
            triggered_by_rule_id=triggered_by_rule_id,
            workflow_execution_id=workflow_execution_id,
            requested_by_id=requested_by_id,
            metadata=metadata,
        )

        self.db.add(request)
        await self.db.flush()  # ID generieren

        # Approval Steps erstellen
        for idx, chain_step in enumerate(approval_chain, start=1):
            step = ApprovalStep(
                approval_request_id=request.id,
                step_number=idx,
                approver_type=chain_step.get("type", "role"),
                approver_value=chain_step.get("value", ""),
                is_required=chain_step.get("required", True),
                status=ApprovalStatus.PENDING if idx == 1 else ApprovalStatus.PENDING,
            )

            # Wenn User-Typ, direkt zuweisen
            if step.approver_type == "user":
                try:
                    step.assigned_user_id = UUID(step.approver_value)
                except ValueError as e:
                    logger.debug("invalid_user_id_in_approval_chain", error_type=type(e).__name__, approver_value=step.approver_value)

            self.db.add(step)

        await self.db.commit()
        await self.db.refresh(request)

        logger.info(
            "approval_request_created",
            title=title,
            request_id=str(request.id),
            entity_type=entity_type,
            entity_id=str(entity_id),
            steps=len(approval_chain),
        )

        return request

    async def create_from_rule(
        self,
        company_id: UUID,
        entity_type: str,
        entity_id: UUID,
        entity_data: dict[str, Any],
        requested_by_id: Optional[UUID] = None,
    ) -> Optional[ApprovalRequest]:
        """Erstellt eine Genehmigungsanfrage basierend auf passenden Regeln.

        Args:
            company_id: ID der Firma
            entity_type: Typ der Entität
            entity_id: ID der Entität
            entity_data: Daten der Entität
            requested_by_id: ID des Antragstellers

        Returns:
            ApprovalRequest wenn Regel gefunden, sonst None
        """
        # Passende Regeln finden
        matched_rules = await self.rule_service.find_matching_rules(
            company_id=company_id,
            entity_type=entity_type,
            entity_data=entity_data,
        )

        if not matched_rules:
            logger.debug(
                "no_approval_rule_found",
                entity_type=entity_type,
                entity_id=str(entity_id),
            )
            return None

        # Erste (hoechste Priorität) Regel verwenden
        best_match = matched_rules[0]
        rule = best_match.rule

        # Titel generieren
        amount = entity_data.get("amount")
        title = entity_data.get("title") or entity_data.get("name") or f"{entity_type.capitalize()} Genehmigung"
        if amount:
            title = f"{title} ({amount} EUR)"

        # Anfrage erstellen
        request = await self.create_approval_request(
            company_id=company_id,
            entity_type=entity_type,
            entity_id=entity_id,
            title=title,
            description=entity_data.get("description"),
            amount=Decimal(str(amount)) if amount else None,
            approval_chain=rule.approval_chain,
            requested_by_id=requested_by_id,
            triggered_by_rule_id=rule.id,
            sla_hours=rule.sla_hours or 48,
            priority=ApprovalPriority.NORMAL,
            metadata={
                "matched_conditions": best_match.matched_conditions,
                "match_score": best_match.match_score,
                "rule_name": rule.name,
            },
        )

        logger.info(
            "approval_request_created_from_rule",
            rule_name=rule.name,
            request_id=str(request.id),
        )

        return request

    async def get_request(
        self,
        request_id: UUID,
        company_id: Optional[UUID] = None,
        include_steps: bool = True,
    ) -> Optional[ApprovalRequest]:
        """Holt eine Genehmigungsanfrage.

        SECURITY: company_id MUSS für Multi-Tenant Isolation angegeben werden.

        Args:
            request_id: ID der Anfrage
            company_id: ID der Firma (REQUIRED für Multi-Tenant Isolation)
            include_steps: Steps mit laden

        Returns:
            ApprovalRequest oder None
        """
        conditions = [ApprovalRequest.id == request_id]

        # SECURITY: Multi-Tenant Isolation
        if company_id:
            conditions.append(ApprovalRequest.company_id == company_id)

        query = select(ApprovalRequest).where(and_(*conditions))

        if include_steps:
            query = query.options(selectinload(ApprovalRequest.approval_steps))

        result = await self.db.execute(query)
        request = result.scalar_one_or_none()

        # SECURITY: Log Cross-Tenant Zugriffsversuch wenn company_id angegeben aber nicht gefunden
        if company_id and not request:
            # Prüfen ob Request existiert aber zu anderer Company gehoert
            check_query = select(ApprovalRequest.company_id).where(ApprovalRequest.id == request_id)
            check_result = await self.db.execute(check_query)
            actual_company_id = check_result.scalar_one_or_none()
            if actual_company_id and actual_company_id != company_id:
                logger.warning(
                    "cross_tenant_approval_access_blocked",
                    request_id=str(request_id),
                    requested_company_id=str(company_id),
                    actual_company_id=str(actual_company_id),
                )

        return request

    async def get_pending_for_user(
        self,
        user_id: UUID,
        company_id: Optional[UUID] = None,
    ) -> Sequence[ApprovalRequest]:
        """Holt alle ausstehenden Genehmigungen für einen User.

        Args:
            user_id: ID des Users
            company_id: Optional: Filter nach Firma

        Returns:
            Liste von ApprovalRequests
        """
        # Finde Steps die dem User zugewiesen sind und pending sind
        subquery = (
            select(ApprovalStep.approval_request_id)
            .where(
                and_(
                    ApprovalStep.assigned_user_id == user_id,
                    ApprovalStep.status == ApprovalStatus.PENDING,
                )
            )
            .distinct()
        )

        query = (
            select(ApprovalRequest)
            .where(
                and_(
                    ApprovalRequest.id.in_(subquery),
                    ApprovalRequest.status == ApprovalStatus.PENDING,
                )
            )
            .options(selectinload(ApprovalRequest.approval_steps))
            .order_by(ApprovalRequest.due_date.asc())
        )

        if company_id:
            query = query.where(ApprovalRequest.company_id == company_id)

        result = await self.db.execute(query)
        return result.scalars().all()

    async def approve(
        self,
        request_id: UUID,
        user_id: UUID,
        company_id: Optional[UUID] = None,
        notes: Optional[str] = None,
    ) -> ApprovalDecision:
        """Genehmigt den aktuellen Schritt einer Anfrage.

        SECURITY: company_id MUSS für Multi-Tenant Isolation angegeben werden.

        Args:
            request_id: ID der Anfrage
            user_id: ID des genehmigenden Users
            company_id: ID der Firma (REQUIRED für Multi-Tenant Isolation)
            notes: Optionale Notizen

        Returns:
            ApprovalDecision mit Ergebnis
        """
        request = await self.get_request(request_id, company_id=company_id, include_steps=True)

        if not request:
            return ApprovalDecision(
                success=False,
                request_status=ApprovalStatus.PENDING,
                next_step=None,
                message="Anfrage nicht gefunden",
            )

        if request.status != ApprovalStatus.PENDING:
            return ApprovalDecision(
                success=False,
                request_status=request.status,
                next_step=None,
                message=f"Anfrage ist bereits {request.status.value}",
            )

        # Aktuellen Step finden
        current_step = self._get_current_step(request)

        if not current_step:
            return ApprovalDecision(
                success=False,
                request_status=request.status,
                next_step=None,
                message="Kein aktueller Schritt gefunden",
            )

        # Prüfen ob User berechtigt ist
        if not await self._can_approve(current_step, user_id):
            return ApprovalDecision(
                success=False,
                request_status=request.status,
                next_step=request.current_step,
                message="Keine Berechtigung für diesen Schritt",
            )

        # Schritt genehmigen
        now = utc_now()
        current_step.status = ApprovalStatus.APPROVED
        current_step.decision = "approved"
        current_step.decision_date = now
        current_step.decision_by_id = user_id
        current_step.decision_notes = notes

        # Nächsten Schritt oder abschließen
        if request.current_step < request.total_steps:
            request.current_step += 1
            next_step_num = request.current_step

            # Nächsten Step aktivieren
            next_step = next(
                (s for s in request.approval_steps if s.step_number == next_step_num),
                None
            )
            if next_step:
                next_step.status = ApprovalStatus.PENDING

            message = f"Schritt {request.current_step - 1} genehmigt, weiter zu Schritt {next_step_num}"
        else:
            # Alle Schritte genehmigt
            request.status = ApprovalStatus.APPROVED
            request.resolved_at = now
            request.resolved_by_id = user_id
            next_step_num = None
            message = "Anfrage vollständig genehmigt"

        await self.db.commit()
        await self.db.refresh(request)

        logger.info(
            "approval_granted",
            request_id=str(request_id),
            user_id=str(user_id),
            message=message,
        )

        return ApprovalDecision(
            success=True,
            request_status=request.status,
            next_step=next_step_num,
            message=message,
        )

    async def reject(
        self,
        request_id: UUID,
        user_id: UUID,
        notes: str,
        company_id: Optional[UUID] = None,
    ) -> ApprovalDecision:
        """Lehnt eine Genehmigungsanfrage ab.

        SECURITY: company_id MUSS für Multi-Tenant Isolation angegeben werden.

        Args:
            request_id: ID der Anfrage
            user_id: ID des ablehnenden Users
            notes: Begruendung (Pflicht bei Ablehnung)
            company_id: ID der Firma (REQUIRED für Multi-Tenant Isolation)

        Returns:
            ApprovalDecision mit Ergebnis
        """
        request = await self.get_request(request_id, company_id=company_id, include_steps=True)

        if not request:
            return ApprovalDecision(
                success=False,
                request_status=ApprovalStatus.PENDING,
                next_step=None,
                message="Anfrage nicht gefunden",
            )

        if request.status != ApprovalStatus.PENDING:
            return ApprovalDecision(
                success=False,
                request_status=request.status,
                next_step=None,
                message=f"Anfrage ist bereits {request.status.value}",
            )

        # Aktuellen Step finden
        current_step = self._get_current_step(request)

        if not current_step:
            return ApprovalDecision(
                success=False,
                request_status=request.status,
                next_step=None,
                message="Kein aktueller Schritt gefunden",
            )

        # Prüfen ob User berechtigt ist
        if not await self._can_approve(current_step, user_id):
            return ApprovalDecision(
                success=False,
                request_status=request.status,
                next_step=request.current_step,
                message="Keine Berechtigung für diesen Schritt",
            )

        # Ablehnung durchführen
        now = utc_now()
        current_step.status = ApprovalStatus.REJECTED
        current_step.decision = "rejected"
        current_step.decision_date = now
        current_step.decision_by_id = user_id
        current_step.decision_notes = notes

        # Gesamte Anfrage ablehnen
        request.status = ApprovalStatus.REJECTED
        request.resolved_at = now
        request.resolved_by_id = user_id
        request.resolution_notes = notes

        await self.db.commit()
        await self.db.refresh(request)

        logger.info(
            "approval_rejected",
            request_id=str(request_id),
            user_id=str(user_id),
            notes=notes,
        )

        return ApprovalDecision(
            success=True,
            request_status=ApprovalStatus.REJECTED,
            next_step=None,
            message="Anfrage abgelehnt",
        )

    async def delegate(
        self,
        request_id: UUID,
        user_id: UUID,
        delegate_to_id: UUID,
        reason: str,
        company_id: Optional[UUID] = None,
    ) -> ApprovalDecision:
        """Delegiert eine Genehmigung an einen anderen User.

        SECURITY: company_id MUSS für Multi-Tenant Isolation angegeben werden.

        Args:
            request_id: ID der Anfrage
            user_id: ID des delegierenden Users
            delegate_to_id: ID des neuen Genehmigers
            reason: Begruendung
            company_id: ID der Firma (REQUIRED für Multi-Tenant Isolation)

        Returns:
            ApprovalDecision mit Ergebnis
        """
        request = await self.get_request(request_id, company_id=company_id, include_steps=True)

        if not request:
            return ApprovalDecision(
                success=False,
                request_status=ApprovalStatus.PENDING,
                next_step=None,
                message="Anfrage nicht gefunden",
            )

        current_step = self._get_current_step(request)

        if not current_step:
            return ApprovalDecision(
                success=False,
                request_status=request.status,
                next_step=None,
                message="Kein aktueller Schritt gefunden",
            )

        # Delegation durchführen
        current_step.delegated_to_id = delegate_to_id
        current_step.delegated_at = utc_now()
        current_step.delegation_reason = reason
        current_step.assigned_user_id = delegate_to_id

        await self.db.commit()
        await self.db.refresh(request)

        logger.info(
            "approval_delegated",
            request_id=str(request_id),
            from_user_id=str(user_id),
            to_user_id=str(delegate_to_id),
        )

        return ApprovalDecision(
            success=True,
            request_status=request.status,
            next_step=request.current_step,
            message=f"Delegiert an User {delegate_to_id}",
        )

    async def escalate_overdue(self, company_id: Optional[UUID] = None) -> int:
        """Eskaliert überfällige Genehmigungen.

        Uses bulk UPDATE for performance (avoids N+1 queries).

        Args:
            company_id: Optional: Nur für diese Firma

        Returns:
            Anzahl eskalierter Anfragen
        """
        now = utc_now()

        # Build the WHERE conditions
        conditions = [
            ApprovalRequest.status == ApprovalStatus.PENDING,
            ApprovalRequest.due_date < now,
            ApprovalRequest.is_escalated.is_(False),
        ]

        if company_id:
            conditions.append(ApprovalRequest.company_id == company_id)

        # First, get IDs for logging (lightweight query)
        id_query = select(ApprovalRequest.id, ApprovalRequest.due_date).where(
            and_(*conditions)
        )
        id_result = await self.db.execute(id_query)
        overdue_info = id_result.all()

        if not overdue_info:
            return 0

        # Log each escalation
        for request_id, due_date in overdue_info:
            logger.warning(
                "approval_request_escalated",
                request_id=str(request_id),
                due_date=str(due_date),
            )

        # Bulk UPDATE instead of fetch-and-loop pattern
        stmt = (
            update(ApprovalRequest)
            .where(and_(*conditions))
            .values(
                is_escalated=True,
                status=ApprovalStatus.ESCALATED,
                escalation_date=now,
            )
        )

        result = await self.db.execute(stmt)
        count = result.rowcount

        await self.db.commit()

        if count > 0:
            logger.info("overdue_approvals_escalated", count=count)

        return count

    async def get_summary(
        self,
        company_id: UUID,
        user_id: Optional[UUID] = None,
    ) -> ApprovalSummary:
        """Holt eine Zusammenfassung der Genehmigungen.

        Args:
            company_id: ID der Firma
            user_id: Optional: User für my_pending

        Returns:
            ApprovalSummary
        """
        now = utc_now()

        # Gesamtzahlen
        result = await self.db.execute(
            select(
                ApprovalRequest.status,
                func.count(ApprovalRequest.id)
            )
            .where(ApprovalRequest.company_id == company_id)
            .group_by(ApprovalRequest.status)
        )

        status_counts = {row[0]: row[1] for row in result.all()}

        # Durchschnittliche Bearbeitungszeit
        result = await self.db.execute(
            select(
                func.avg(
                    func.extract(
                        'epoch',
                        ApprovalRequest.resolved_at - ApprovalRequest.created_at
                    ) / 3600
                )
            )
            .where(
                and_(
                    ApprovalRequest.company_id == company_id,
                    ApprovalRequest.resolved_at.isnot(None),
                )
            )
        )
        avg_hours = result.scalar() or 0

        # Überfällige
        result = await self.db.execute(
            select(func.count(ApprovalRequest.id))
            .where(
                and_(
                    ApprovalRequest.company_id == company_id,
                    ApprovalRequest.status == ApprovalStatus.PENDING,
                    ApprovalRequest.due_date < now,
                )
            )
        )
        overdue = result.scalar() or 0

        # My Pending
        my_pending = 0
        if user_id:
            requests = await self.get_pending_for_user(user_id, company_id)
            my_pending = len(requests)

        return ApprovalSummary(
            total_pending=status_counts.get(ApprovalStatus.PENDING, 0),
            total_approved=status_counts.get(ApprovalStatus.APPROVED, 0),
            total_rejected=status_counts.get(ApprovalStatus.REJECTED, 0),
            total_escalated=status_counts.get(ApprovalStatus.ESCALATED, 0),
            avg_resolution_hours=float(avg_hours),
            overdue_count=overdue,
            my_pending=my_pending,
        )

    def _get_current_step(self, request: ApprovalRequest) -> Optional[ApprovalStep]:
        """Findet den aktuellen Genehmigungsschritt.

        Args:
            request: ApprovalRequest mit geladenen Steps

        Returns:
            Aktueller ApprovalStep oder None
        """
        if not request.approval_steps:
            return None

        return next(
            (s for s in request.approval_steps if s.step_number == request.current_step),
            None
        )

    async def _can_approve(self, step: ApprovalStep, user_id: UUID) -> bool:
        """Prüft ob ein User einen Schritt genehmigen kann.

        Args:
            step: Der zu genehmigende Schritt
            user_id: ID des Users

        Returns:
            True wenn berechtigt
        """
        # Direkt zugewiesener User
        if step.assigned_user_id == user_id:
            return True

        # Delegierter User
        if step.delegated_to_id == user_id:
            return True

        # Rollenbasierte Prüfung
        if step.approver_type == "role":
            # Prüfe ob User die erforderliche Rolle hat
            required_role_name = step.approver_value
            user_role_query = (
                select(Role.name)
                .select_from(user_roles)
                .join(Role, Role.id == user_roles.c.role_id)
                .where(
                    and_(
                        user_roles.c.user_id == user_id,
                        Role.name == required_role_name,
                        Role.is_active == True,
                    )
                )
            )
            result = await self.db.execute(user_role_query)
            has_role = result.scalar_one_or_none() is not None

            if has_role:
                logger.debug(
                    "approval_role_match",
                    user_id=str(user_id),
                    required_role=required_role_name,
                )
                return True

        # Gruppenbasierte Prüfung (wenn implementiert)
        if step.approver_type == "group":
            # Hier könnte man Gruppenmitgliedschaft prüfen
            # Aktuell nicht implementiert - als Platzhalter für zukünftige Erweiterung
            pass

        return False

    async def cancel(
        self,
        request_id: UUID,
        user_id: UUID,
        reason: str,
        company_id: Optional[UUID] = None,
    ) -> ApprovalDecision:
        """Storniert eine Genehmigungsanfrage.

        SECURITY: company_id MUSS für Multi-Tenant Isolation angegeben werden.

        Args:
            request_id: ID der Anfrage
            user_id: ID des stornierenden Users
            reason: Begruendung
            company_id: ID der Firma (REQUIRED für Multi-Tenant Isolation)

        Returns:
            ApprovalDecision mit Ergebnis
        """
        request = await self.get_request(request_id, company_id=company_id)

        if not request:
            return ApprovalDecision(
                success=False,
                request_status=ApprovalStatus.PENDING,
                next_step=None,
                message="Anfrage nicht gefunden",
            )

        if request.status not in (ApprovalStatus.PENDING, ApprovalStatus.ESCALATED):
            return ApprovalDecision(
                success=False,
                request_status=request.status,
                next_step=None,
                message=f"Anfrage kann nicht storniert werden (Status: {request.status.value})",
            )

        now = utc_now()
        request.status = ApprovalStatus.CANCELLED
        request.resolved_at = now
        request.resolved_by_id = user_id
        request.resolution_notes = reason

        await self.db.commit()
        await self.db.refresh(request)

        logger.info(
            "approval_cancelled",
            request_id=str(request_id),
            user_id=str(user_id),
            reason=reason,
        )

        return ApprovalDecision(
            success=True,
            request_status=ApprovalStatus.CANCELLED,
            next_step=None,
            message="Anfrage storniert",
        )

    # =========================================================================
    # API-COMPATIBLE METHODS (für app/api/v1/approvals.py)
    # =========================================================================

    async def get_requests_for_company(
        self,
        company_id: UUID,
        status_filter: Optional[ApprovalStatus] = None,
        entity_type: Optional[str] = None,
        for_user_id: Optional[UUID] = None,
        offset: int = 0,
        limit: int = 50,
    ) -> Sequence[ApprovalRequest]:
        """Holt Genehmigungsanfragen für eine Firma mit Filtern.

        Args:
            company_id: ID der Firma
            status_filter: Optional: Nach Status filtern
            entity_type: Optional: Nach Entitätstyp filtern
            for_user_id: Optional: Nur Anfragen für diesen User
            offset: Offset für Pagination
            limit: Max. Anzahl Ergebnisse

        Returns:
            Liste von ApprovalRequests
        """
        query = (
            select(ApprovalRequest)
            .where(ApprovalRequest.company_id == company_id)
            .options(selectinload(ApprovalRequest.approval_steps))
        )

        if status_filter:
            query = query.where(ApprovalRequest.status == status_filter)

        if entity_type:
            query = query.where(ApprovalRequest.entity_type == entity_type)

        if for_user_id:
            # Finde Anfragen wo der User im aktuellen Step zugewiesen ist
            subquery = (
                select(ApprovalStep.approval_request_id)
                .where(
                    and_(
                        or_(
                            ApprovalStep.assigned_user_id == for_user_id,
                            ApprovalStep.delegated_to_id == for_user_id,
                        ),
                        ApprovalStep.status == ApprovalStatus.PENDING,
                    )
                )
                .distinct()
            )
            query = query.where(ApprovalRequest.id.in_(subquery))

        query = (
            query
            .order_by(ApprovalRequest.created_at.desc())
            .offset(offset)
            .limit(limit)
        )

        result = await self.db.execute(query)
        return result.scalars().all()

    async def count_requests_for_company(
        self,
        company_id: UUID,
        status_filter: Optional[ApprovalStatus] = None,
        entity_type: Optional[str] = None,
        for_user_id: Optional[UUID] = None,
    ) -> int:
        """Zaehlt Genehmigungsanfragen für eine Firma.

        Args:
            company_id: ID der Firma
            status_filter: Optional: Nach Status filtern
            entity_type: Optional: Nach Entitätstyp filtern
            for_user_id: Optional: Nur Anfragen für diesen User

        Returns:
            Anzahl der Anfragen
        """
        query = (
            select(func.count(ApprovalRequest.id))
            .where(ApprovalRequest.company_id == company_id)
        )

        if status_filter:
            query = query.where(ApprovalRequest.status == status_filter)

        if entity_type:
            query = query.where(ApprovalRequest.entity_type == entity_type)

        if for_user_id:
            subquery = (
                select(ApprovalStep.approval_request_id)
                .where(
                    and_(
                        or_(
                            ApprovalStep.assigned_user_id == for_user_id,
                            ApprovalStep.delegated_to_id == for_user_id,
                        ),
                        ApprovalStep.status == ApprovalStatus.PENDING,
                    )
                )
                .distinct()
            )
            query = query.where(ApprovalRequest.id.in_(subquery))

        result = await self.db.execute(query)
        return result.scalar() or 0

    async def can_user_approve_step(
        self,
        request: ApprovalRequest,
        user: User,
        step_number: int,
    ) -> bool:
        """Prüft ob ein User einen bestimmten Schritt genehmigen kann.

        Args:
            request: Die ApprovalRequest
            user: Der User
            step_number: Nummer des Schritts

        Returns:
            True wenn berechtigt
        """
        if not request.approval_steps:
            return False

        step = next(
            (s for s in request.approval_steps if s.step_number == step_number),
            None
        )

        if not step:
            return False

        return await self._can_approve(step, user.id)

    async def process_approval_decision(
        self,
        request_id: UUID,
        user_id: UUID,
        decision: str,
        company_id: Optional[UUID] = None,
        notes: Optional[str] = None,
    ) -> ApprovalDecision:
        """Verarbeitet eine Genehmigungsentscheidung (approve/reject).

        SECURITY: company_id MUSS für Multi-Tenant Isolation angegeben werden.

        Args:
            request_id: ID der Anfrage
            user_id: ID des entscheidenden Users
            decision: "approved" oder "rejected"
            company_id: ID der Firma (REQUIRED für Multi-Tenant Isolation)
            notes: Optionale Notizen

        Returns:
            ApprovalDecision mit Ergebnis
        """
        if decision == "approved":
            return await self.approve(request_id, user_id, company_id=company_id, notes=notes)
        elif decision == "rejected":
            if not notes:
                return ApprovalDecision(
                    success=False,
                    request_status=ApprovalStatus.PENDING,
                    next_step=None,
                    message="Begruendung bei Ablehnung erforderlich",
                )
            return await self.reject(request_id, user_id, notes, company_id=company_id)
        else:
            return ApprovalDecision(
                success=False,
                request_status=ApprovalStatus.PENDING,
                next_step=None,
                message=f"Ungültige Entscheidung: {decision}",
            )

    async def escalate_request(
        self,
        request_id: UUID,
        reason: str,
        company_id: Optional[UUID] = None,
        escalate_to_role: Optional[str] = None,
        escalated_by_id: Optional[UUID] = None,
    ) -> bool:
        """Eskaliert eine einzelne Genehmigungsanfrage manuell.

        SECURITY: company_id MUSS für Multi-Tenant Isolation angegeben werden.

        Args:
            request_id: ID der Anfrage
            reason: Eskalationsgrund
            company_id: ID der Firma (REQUIRED für Multi-Tenant Isolation)
            escalate_to_role: Optional: An diese Rolle eskalieren
            escalated_by_id: Optional: ID des eskalierenden Users

        Returns:
            True wenn erfolgreich
        """
        request = await self.get_request(request_id, company_id=company_id)

        if not request:
            logger.warning("approval_request_not_found_for_escalation", request_id=str(request_id))
            return False

        if request.status != ApprovalStatus.PENDING:
            logger.warning(
                f"Anfrage {request_id} kann nicht eskaliert werden "
                f"(Status: {request.status.value})"
            )
            return False

        now = utc_now()
        request.is_escalated = True
        request.status = ApprovalStatus.ESCALATED
        request.escalation_date = now
        request.escalation_reason = reason

        if escalate_to_role:
            request.escalation_to_role = escalate_to_role

        await self.db.commit()
        await self.db.refresh(request)

        logger.info(
            f"Anfrage {request_id} eskaliert: {reason} "
            f"(von User {escalated_by_id})"
        )

        return True

    async def get_step(
        self,
        step_id: UUID,
        company_id: Optional[UUID] = None,
    ) -> Optional[ApprovalStep]:
        """Holt einen einzelnen Genehmigungsschritt.

        SECURITY: company_id MUSS für Multi-Tenant Isolation angegeben werden.

        Args:
            step_id: ID des Schritts
            company_id: ID der Firma (REQUIRED für Multi-Tenant Isolation)

        Returns:
            ApprovalStep oder None
        """
        # SECURITY: Multi-Tenant Isolation via Join auf ApprovalRequest
        if company_id:
            query = (
                select(ApprovalStep)
                .join(ApprovalRequest, ApprovalStep.approval_request_id == ApprovalRequest.id)
                .where(
                    and_(
                        ApprovalStep.id == step_id,
                        ApprovalRequest.company_id == company_id,
                    )
                )
            )
        else:
            query = select(ApprovalStep).where(ApprovalStep.id == step_id)

        result = await self.db.execute(query)
        step = result.scalar_one_or_none()

        # SECURITY: Log Cross-Tenant Zugriffsversuch
        if company_id and not step:
            check_query = (
                select(ApprovalRequest.company_id)
                .join(ApprovalStep, ApprovalStep.approval_request_id == ApprovalRequest.id)
                .where(ApprovalStep.id == step_id)
            )
            check_result = await self.db.execute(check_query)
            actual_company_id = check_result.scalar_one_or_none()
            if actual_company_id and actual_company_id != company_id:
                logger.warning(
                    "cross_tenant_approval_step_access_blocked",
                    step_id=str(step_id),
                    requested_company_id=str(company_id),
                    actual_company_id=str(actual_company_id),
                )

        return step

    async def delegate_step(
        self,
        step_id: UUID,
        delegate_to_id: UUID,
        delegated_by_id: UUID,
        company_id: Optional[UUID] = None,
        reason: Optional[str] = None,
    ) -> Optional[ApprovalStep]:
        """Delegiert einen Genehmigungsschritt an einen anderen User.

        SECURITY: company_id MUSS für Multi-Tenant Isolation angegeben werden.

        Args:
            step_id: ID des Schritts
            delegate_to_id: ID des neuen Genehmigers
            delegated_by_id: ID des delegierenden Users
            company_id: ID der Firma (REQUIRED für Multi-Tenant Isolation)
            reason: Optionale Begruendung

        Returns:
            Aktualisierter ApprovalStep oder None
        """
        step = await self.get_step(step_id, company_id=company_id)

        if not step:
            logger.warning("approval_step_not_found_for_delegation", step_id=str(step_id))
            return None

        step.delegated_to_id = delegate_to_id
        step.delegated_at = utc_now()
        step.delegation_reason = reason
        step.assigned_user_id = delegate_to_id

        await self.db.commit()
        await self.db.refresh(step)

        logger.info(
            f"Step {step_id} delegiert von {delegated_by_id} an {delegate_to_id}"
        )

        return step

    async def get_approval_summary(
        self,
        company_id: UUID,
        user_id: Optional[UUID] = None,
    ) -> ApprovalSummary:
        """Alias für get_summary (API-Kompatibilität).

        Args:
            company_id: ID der Firma
            user_id: Optional: User für my_pending

        Returns:
            ApprovalSummary
        """
        return await self.get_summary(company_id, user_id)

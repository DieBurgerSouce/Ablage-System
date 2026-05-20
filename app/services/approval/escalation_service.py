# -*- coding: utf-8 -*-
"""
EscalationService - Eskalation und Stellvertretung.

Feature #3: Approval Workflow Depth
Verwaltet:
- Überfällige Genehmigungen erkennen und eskalieren
- Stellvertretungsregeln aktivieren/deaktivieren
- Aktive Stellvertretungen finden

Nutzt models_approval_extended für EscalationRule und SubstitutionRule.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Sequence
from uuid import UUID

import structlog
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.datetime_utils import utc_now
from app.db.models import (
    ApprovalRequest,
    ApprovalStatus,
    ApprovalStep,
    User,
)
from app.db.models_approval_extended import (
    EscalationRule,
    SubstitutionRule,
)

logger = structlog.get_logger(__name__)


# ============================================================================
# Datenklassen
# ============================================================================


@dataclass
class EscalationResult:
    """Ergebnis einer Eskalation."""

    approval_request_id: UUID
    escalated: bool
    escalation_target: Optional[str] = None
    message: str = ""


@dataclass
class SubstitutionInfo:
    """Information über eine aktive Stellvertretung."""

    original_user_id: UUID
    substitute_user_id: UUID
    reason: Optional[str] = None
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None


# ============================================================================
# Service
# ============================================================================


class EscalationService:
    """Service für Eskalation und Stellvertretung.

    Verantwortlich für:
    1. Erkennung überfälliger Genehmigungen
    2. Eskalation an definierte Empfänger
    3. Verwaltung von Stellvertretungsregeln
    4. Automatische Aktivierung/Deaktivierung von Vertretungen
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ========================================================================
    # Eskalation
    # ========================================================================

    async def check_overdue_approvals(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> List[ApprovalRequest]:
        """Findet überfällige Genehmigungsanfragen.

        Args:
            db: Async Database Session
            company_id: ID der Firma

        Returns:
            Liste überfälliger ApprovalRequests
        """
        now = utc_now()

        stmt = (
            select(ApprovalRequest)
            .options(selectinload(ApprovalRequest.approval_steps))
            .where(
                and_(
                    ApprovalRequest.company_id == company_id,
                    ApprovalRequest.status == ApprovalStatus.PENDING,
                    ApprovalRequest.due_date < now,
                    ApprovalRequest.is_escalated.is_(False),
                )
            )
            .order_by(ApprovalRequest.due_date.asc())
        )

        result = await db.execute(stmt)
        overdue = result.scalars().all()

        if overdue:
            logger.info(
                "overdue_approvals_found",
                company_id=str(company_id),
                count=len(overdue),
            )

        return list(overdue)

    async def escalate_approval(
        self,
        db: AsyncSession,
        approval_id: UUID,
        escalation_rule: EscalationRule,
    ) -> EscalationResult:
        """Eskaliert eine Genehmigungsanfrage gemäß einer Eskalationsregel.

        Args:
            db: Async Database Session
            approval_id: ID der Genehmigungsanfrage
            escalation_rule: Die anzuwendende Eskalationsregel

        Returns:
            EscalationResult mit Ergebnis
        """
        stmt = (
            select(ApprovalRequest)
            .options(selectinload(ApprovalRequest.approval_steps))
            .where(ApprovalRequest.id == approval_id)
        )
        result = await db.execute(stmt)
        request = result.scalar_one_or_none()

        if not request:
            return EscalationResult(
                approval_request_id=approval_id,
                escalated=False,
                message="Anfrage nicht gefunden",
            )

        if request.status != ApprovalStatus.PENDING:
            return EscalationResult(
                approval_request_id=approval_id,
                escalated=False,
                message=f"Anfrage hat Status {request.status.value}, "
                f"kann nicht eskaliert werden",
            )

        now = utc_now()

        # Anfrage als eskaliert markieren
        request.is_escalated = True
        request.status = ApprovalStatus.ESCALATED
        request.escalation_date = now

        # Eskalationsziel bestimmen
        escalation_target: Optional[str] = None

        if escalation_rule.escalation_target_user_id:
            # An spezifischen User eskalieren
            escalation_target = str(escalation_rule.escalation_target_user_id)

            # Aktuellen Step dem Eskalationsziel zuweisen
            current_step = self._get_current_step(request)
            if current_step:
                current_step.assigned_user_id = (
                    escalation_rule.escalation_target_user_id
                )
                current_step.delegated_at = now
                current_step.delegation_reason = (
                    f"Automatische Eskalation: Timeout nach "
                    f"{escalation_rule.timeout_hours}h"
                )

        elif escalation_rule.escalation_target_role:
            escalation_target = escalation_rule.escalation_target_role

        await db.commit()

        logger.warning(
            "approval_escalated",
            approval_id=str(approval_id),
            rule_name=escalation_rule.name,
            target=escalation_target,
        )

        return EscalationResult(
            approval_request_id=approval_id,
            escalated=True,
            escalation_target=escalation_target,
            message=f"Eskaliert gemäß Regel '{escalation_rule.name}'",
        )

    async def get_escalation_rules(
        self,
        company_id: UUID,
        active_only: bool = True,
    ) -> Sequence[EscalationRule]:
        """Holt Eskalationsregeln für eine Firma.

        Args:
            company_id: ID der Firma
            active_only: Nur aktive Regeln

        Returns:
            Liste der Eskalationsregeln
        """
        stmt = select(EscalationRule).where(
            EscalationRule.company_id == company_id
        )

        if active_only:
            stmt = stmt.where(EscalationRule.is_active.is_(True))

        stmt = stmt.order_by(EscalationRule.timeout_hours.asc())

        result = await self.db.execute(stmt)
        return result.scalars().all()

    # ========================================================================
    # Stellvertretung
    # ========================================================================

    async def find_substitute(
        self,
        db: AsyncSession,
        user_id: UUID,
        company_id: UUID,
    ) -> Optional[SubstitutionInfo]:
        """Findet eine aktive Stellvertretung für einen User.

        Args:
            db: Async Database Session
            user_id: ID des abwesenden Users
            company_id: ID der Firma

        Returns:
            SubstitutionInfo oder None
        """
        now = utc_now()

        stmt = (
            select(SubstitutionRule)
            .where(
                and_(
                    SubstitutionRule.user_id == user_id,
                    SubstitutionRule.company_id == company_id,
                    SubstitutionRule.is_active.is_(True),
                    SubstitutionRule.valid_from <= now,
                    SubstitutionRule.valid_until >= now,
                )
            )
            .order_by(SubstitutionRule.created_at.desc())
            .limit(1)
        )

        result = await db.execute(stmt)
        substitution = result.scalar_one_or_none()

        if not substitution:
            return None

        return SubstitutionInfo(
            original_user_id=substitution.user_id,
            substitute_user_id=substitution.substitute_user_id,
            reason=substitution.reason,
            valid_from=substitution.valid_from,
            valid_until=substitution.valid_until,
        )

    async def activate_substitutions(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> int:
        """Aktiviert fällige Stellvertretungsregeln basierend auf Datum.

        Args:
            db: Async Database Session
            company_id: ID der Firma

        Returns:
            Anzahl aktivierter Regeln
        """
        now = utc_now()

        # Regeln finden die jetzt gültig aber noch nicht aktiviert sind
        stmt = (
            select(SubstitutionRule)
            .where(
                and_(
                    SubstitutionRule.company_id == company_id,
                    SubstitutionRule.valid_from <= now,
                    SubstitutionRule.valid_until >= now,
                    SubstitutionRule.is_active.is_(False),
                    SubstitutionRule.auto_activated.is_(False),
                )
            )
        )

        result = await db.execute(stmt)
        rules_to_activate = result.scalars().all()

        count = 0
        for rule in rules_to_activate:
            rule.is_active = True
            rule.auto_activated = True
            count += 1

            logger.info(
                "substitution_auto_activated",
                rule_id=str(rule.id),
                user_id=str(rule.user_id),
                substitute_id=str(rule.substitute_user_id),
                reason=rule.reason,
            )

        if count > 0:
            await db.commit()

        return count

    async def deactivate_expired_substitutions(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> int:
        """Deaktiviert abgelaufene Stellvertretungsregeln.

        Args:
            db: Async Database Session
            company_id: ID der Firma

        Returns:
            Anzahl deaktivierter Regeln
        """
        now = utc_now()

        stmt = (
            select(SubstitutionRule)
            .where(
                and_(
                    SubstitutionRule.company_id == company_id,
                    SubstitutionRule.is_active.is_(True),
                    SubstitutionRule.valid_until < now,
                )
            )
        )

        result = await db.execute(stmt)
        expired_rules = result.scalars().all()

        count = 0
        for rule in expired_rules:
            rule.is_active = False
            count += 1

            logger.info(
                "substitution_deactivated",
                rule_id=str(rule.id),
                user_id=str(rule.user_id),
                substitute_id=str(rule.substitute_user_id),
            )

        if count > 0:
            await db.commit()

        return count

    async def get_substitution_rules(
        self,
        company_id: UUID,
        active_only: bool = True,
    ) -> Sequence[SubstitutionRule]:
        """Holt Stellvertretungsregeln für eine Firma.

        Args:
            company_id: ID der Firma
            active_only: Nur aktive Regeln

        Returns:
            Liste der Stellvertretungsregeln
        """
        stmt = select(SubstitutionRule).where(
            SubstitutionRule.company_id == company_id
        )

        if active_only:
            stmt = stmt.where(SubstitutionRule.is_active.is_(True))

        stmt = stmt.order_by(SubstitutionRule.valid_from.desc())

        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def create_substitution(
        self,
        company_id: UUID,
        user_id: UUID,
        substitute_user_id: UUID,
        valid_from: datetime,
        valid_until: datetime,
        reason: Optional[str] = None,
    ) -> SubstitutionRule:
        """Erstellt eine neue Stellvertretungsregel.

        Args:
            company_id: ID der Firma
            user_id: ID des abwesenden Users
            substitute_user_id: ID des Stellvertreters
            valid_from: Beginn der Vertretung
            valid_until: Ende der Vertretung
            reason: Grund (z.B. "Urlaub", "Krankheit")

        Returns:
            Erstellte SubstitutionRule

        Raises:
            ValueError: Bei ungültigen Parametern
        """
        if user_id == substitute_user_id:
            raise ValueError("User und Stellvertreter müssen unterschiedlich sein")

        if valid_until <= valid_from:
            raise ValueError("Endzeitpunkt muss nach Startzeitpunkt liegen")

        # Auto-Aktivierung wenn Zeitraum bereits aktiv
        now = utc_now()
        is_currently_active = valid_from <= now <= valid_until

        rule = SubstitutionRule(
            company_id=company_id,
            user_id=user_id,
            substitute_user_id=substitute_user_id,
            valid_from=valid_from,
            valid_until=valid_until,
            reason=reason,
            is_active=is_currently_active,
            auto_activated=is_currently_active,
        )

        self.db.add(rule)
        await self.db.commit()
        await self.db.refresh(rule)

        logger.info(
            "substitution_created",
            rule_id=str(rule.id),
            user_id=str(user_id),
            substitute_id=str(substitute_user_id),
            valid_from=valid_from.isoformat(),
            valid_until=valid_until.isoformat(),
            reason=reason,
        )

        return rule

    async def delete_substitution(
        self,
        rule_id: UUID,
        company_id: UUID,
    ) -> bool:
        """Löscht eine Stellvertretungsregel.

        Args:
            rule_id: ID der Regel
            company_id: ID der Firma (Multi-Tenant Isolation)

        Returns:
            True wenn erfolgreich gelöscht
        """
        stmt = select(SubstitutionRule).where(
            and_(
                SubstitutionRule.id == rule_id,
                SubstitutionRule.company_id == company_id,
            )
        )
        result = await self.db.execute(stmt)
        rule = result.scalar_one_or_none()

        if not rule:
            return False

        await self.db.delete(rule)
        await self.db.commit()

        logger.info(
            "substitution_deleted",
            rule_id=str(rule_id),
            company_id=str(company_id),
        )

        return True

    # ========================================================================
    # Private Hilfsmethoden
    # ========================================================================

    def _get_current_step(
        self,
        request: ApprovalRequest,
    ) -> Optional[ApprovalStep]:
        """Findet den aktuellen Genehmigungsschritt."""
        if not request.approval_steps:
            return None

        return next(
            (
                s
                for s in request.approval_steps
                if s.step_number == request.current_step
            ),
            None,
        )

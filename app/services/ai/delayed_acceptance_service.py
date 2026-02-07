# -*- coding: utf-8 -*-
"""
DelayedAcceptanceService - Queue fuer verzoegerte Auto-Akzeptanz.

Verwaltet eine Queue fuer Aktionen, die nicht sofort ausgefuehrt werden:
- Level 2: 24h Wartezeit bei >90% Confidence
- Level 3: 4h Wartezeit bei 80-95% Confidence

Features:
- Timeout-Handling mit automatischer Ausfuehrung
- User-Intervention (vorzeitige Genehmigung/Ablehnung)
- Rollback-Faehigkeit fuer 7 Tage
- Audit-Trail aller Aktionen
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Callable, Awaitable, Union

import structlog

# Type aliases for JSON data
JSONValue = Union[str, int, float, bool, None, Dict[str, "JSONValue"], List["JSONValue"]]
JSONDict = Dict[str, JSONValue]
from sqlalchemy import select, and_, or_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utc_now
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


# ============================================================================
# Enums
# ============================================================================


class ProposalStatus(str, Enum):
    """Status eines Vorschlags."""

    PENDING = "pending"           # Wartet auf Timeout oder User-Aktion
    APPROVED = "approved"         # Manuell genehmigt
    REJECTED = "rejected"         # Manuell abgelehnt
    AUTO_ACCEPTED = "auto_accepted"  # Automatisch nach Timeout
    EXPIRED = "expired"           # Abgelaufen ohne Aktion
    ROLLED_BACK = "rolled_back"   # Rueckgaengig gemacht
    CANCELLED = "cancelled"       # Abgebrochen


class ProposalType(str, Enum):
    """Typ des Vorschlags."""

    FILE_DOCUMENT = "file_document"
    APPROVE_PAYMENT = "approve_payment"
    SEND_DUNNING = "send_dunning"
    UPDATE_MASTER_DATA = "update_master_data"
    ASSIGN_ENTITY = "assign_entity"
    CLASSIFY_DOCUMENT = "classify_document"


# ============================================================================
# Data Classes
# ============================================================================


@dataclass
class ProposalQueueItem:
    """Ein Item in der Proposal-Queue."""

    id: uuid.UUID
    company_id: uuid.UUID
    proposal_type: ProposalType
    target_id: uuid.UUID
    proposed_value: JSONDict
    confidence: float
    delay_hours: int
    status: ProposalStatus
    created_at: datetime
    scheduled_at: datetime  # Wann wird automatisch ausgefuehrt
    executed_at: Optional[datetime]
    executed_by: Optional[str]  # "system" oder User-ID
    rollback_until: Optional[datetime]
    ai_decision_id: Optional[uuid.UUID]
    reasoning: str
    metadata: JSONDict


@dataclass
class ProposalResult:
    """Ergebnis einer Proposal-Aktion."""

    success: bool
    proposal_id: uuid.UUID
    status: ProposalStatus
    message: str
    executed_value: Optional[JSONDict] = None
    can_rollback: bool = False


# ============================================================================
# Delayed Acceptance Service
# ============================================================================


class DelayedAcceptanceService:
    """Service fuer verzoegerte Auto-Akzeptanz.

    Verwaltet Proposals mit Timeout und User-Intervention.
    """

    # Rollback-Zeitraum in Tagen
    ROLLBACK_WINDOW_DAYS = 7

    def __init__(self, db: AsyncSession):
        """Initialisiert den Service.

        Args:
            db: Async Database Session
        """
        self.db = db

    async def create_proposal(
        self,
        company_id: uuid.UUID,
        proposal_type: ProposalType,
        target_id: uuid.UUID,
        proposed_value: JSONDict,
        confidence: float,
        delay_hours: int,
        ai_decision_id: Optional[uuid.UUID] = None,
        reasoning: str = "",
        metadata: Optional[JSONDict] = None,
    ) -> ProposalQueueItem:
        """Erstellt einen neuen Proposal in der Queue.

        Args:
            company_id: ID der Company
            proposal_type: Typ des Vorschlags
            target_id: ID des Ziel-Objekts
            proposed_value: Vorgeschlagener Wert
            confidence: Confidence-Score
            delay_hours: Verzoegerung in Stunden
            ai_decision_id: Optional AI-Decision Referenz
            reasoning: Begruendung
            metadata: Zusaetzliche Metadaten

        Returns:
            ProposalQueueItem
        """
        from app.db.models import AutonomousProposalQueue

        now = utc_now()
        scheduled_at = now + timedelta(hours=delay_hours)
        rollback_until = scheduled_at + timedelta(days=self.ROLLBACK_WINDOW_DAYS)

        proposal = AutonomousProposalQueue(
            id=uuid.uuid4(),
            company_id=company_id,
            proposal_type=proposal_type.value,
            target_id=target_id,
            proposed_value=proposed_value,
            confidence=confidence,
            delay_hours=delay_hours,
            status=ProposalStatus.PENDING.value,
            scheduled_at=scheduled_at,
            rollback_until=rollback_until,
            ai_decision_id=ai_decision_id,
            reasoning=reasoning,
            metadata=metadata or {},
        )

        self.db.add(proposal)
        await self.db.commit()
        await self.db.refresh(proposal)

        logger.info(
            "proposal_created",
            proposal_id=str(proposal.id),
            proposal_type=proposal_type.value,
            target_id=str(target_id),
            delay_hours=delay_hours,
            scheduled_at=scheduled_at.isoformat(),
        )

        return ProposalQueueItem(
            id=proposal.id,
            company_id=proposal.company_id,
            proposal_type=ProposalType(proposal.proposal_type),
            target_id=proposal.target_id,
            proposed_value=proposal.proposed_value,
            confidence=proposal.confidence,
            delay_hours=proposal.delay_hours,
            status=ProposalStatus(proposal.status),
            created_at=proposal.created_at,
            scheduled_at=proposal.scheduled_at,
            executed_at=proposal.executed_at,
            executed_by=proposal.executed_by,
            rollback_until=proposal.rollback_until,
            ai_decision_id=proposal.ai_decision_id,
            reasoning=proposal.reasoning,
            metadata=proposal.metadata,
        )

    async def get_pending_proposals(
        self,
        company_id: uuid.UUID,
        proposal_type: Optional[ProposalType] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[ProposalQueueItem]:
        """Holt ausstehende Proposals.

        Args:
            company_id: ID der Company
            proposal_type: Optional Filter nach Typ
            limit: Max Anzahl
            offset: Offset

        Returns:
            Liste von ProposalQueueItem
        """
        from app.db.models import AutonomousProposalQueue

        query = select(AutonomousProposalQueue).where(
            and_(
                AutonomousProposalQueue.company_id == company_id,
                AutonomousProposalQueue.status == ProposalStatus.PENDING.value,
            )
        )

        if proposal_type:
            query = query.where(
                AutonomousProposalQueue.proposal_type == proposal_type.value
            )

        query = query.order_by(
            AutonomousProposalQueue.scheduled_at.asc()
        ).limit(limit).offset(offset)

        result = await self.db.execute(query)
        proposals = result.scalars().all()

        return [
            ProposalQueueItem(
                id=p.id,
                company_id=p.company_id,
                proposal_type=ProposalType(p.proposal_type),
                target_id=p.target_id,
                proposed_value=p.proposed_value,
                confidence=p.confidence,
                delay_hours=p.delay_hours,
                status=ProposalStatus(p.status),
                created_at=p.created_at,
                scheduled_at=p.scheduled_at,
                executed_at=p.executed_at,
                executed_by=p.executed_by,
                rollback_until=p.rollback_until,
                ai_decision_id=p.ai_decision_id,
                reasoning=p.reasoning,
                metadata=p.metadata or {},
            )
            for p in proposals
        ]

    async def approve_proposal(
        self,
        proposal_id: uuid.UUID,
        user_id: uuid.UUID,
        company_id: uuid.UUID,
        executor: Optional[Callable[[JSONDict], Awaitable[bool]]] = None,
    ) -> ProposalResult:
        """Genehmigt einen Proposal manuell.

        Args:
            proposal_id: ID des Proposals
            user_id: ID des genehmigenden Users
            company_id: Company-ID fuer Multi-Tenant Check
            executor: Optional Callback fuer Ausfuehrung

        Returns:
            ProposalResult
        """
        from app.db.models import AutonomousProposalQueue

        result = await self.db.execute(
            select(AutonomousProposalQueue).where(
                and_(
                    AutonomousProposalQueue.id == proposal_id,
                    AutonomousProposalQueue.company_id == company_id,
                    AutonomousProposalQueue.status == ProposalStatus.PENDING.value,
                )
            )
        )
        proposal = result.scalar_one_or_none()

        if not proposal:
            return ProposalResult(
                success=False,
                proposal_id=proposal_id,
                status=ProposalStatus.PENDING,
                message="Vorschlag nicht gefunden oder bereits verarbeitet.",
            )

        now = utc_now()

        # Fuehre Aktion aus wenn Executor vorhanden
        execution_success = True
        if executor:
            try:
                execution_success = await executor(proposal.proposed_value)
            except Exception as e:
                logger.error(
                    "proposal_execution_failed",
                    proposal_id=str(proposal_id),
                    **safe_error_log(e),
                )
                execution_success = False

        if execution_success:
            proposal.status = ProposalStatus.APPROVED.value
            proposal.executed_at = now
            proposal.executed_by = str(user_id)
            proposal.rollback_until = now + timedelta(days=self.ROLLBACK_WINDOW_DAYS)
            await self.db.commit()

            logger.info(
                "proposal_approved",
                proposal_id=str(proposal_id),
                user_id=str(user_id),
            )

            return ProposalResult(
                success=True,
                proposal_id=proposal_id,
                status=ProposalStatus.APPROVED,
                message="Vorschlag genehmigt und ausgefuehrt.",
                executed_value=proposal.proposed_value,
                can_rollback=True,
            )
        else:
            proposal.status = ProposalStatus.REJECTED.value
            proposal.executed_at = now
            proposal.executed_by = str(user_id)
            await self.db.commit()

            return ProposalResult(
                success=False,
                proposal_id=proposal_id,
                status=ProposalStatus.REJECTED,
                message="Ausfuehrung fehlgeschlagen.",
            )

    async def reject_proposal(
        self,
        proposal_id: uuid.UUID,
        user_id: uuid.UUID,
        company_id: uuid.UUID,
        reason: Optional[str] = None,
    ) -> ProposalResult:
        """Lehnt einen Proposal ab.

        Args:
            proposal_id: ID des Proposals
            user_id: ID des ablehnenden Users
            company_id: Company-ID fuer Multi-Tenant Check
            reason: Optional Ablehnungsgrund

        Returns:
            ProposalResult
        """
        from app.db.models import AutonomousProposalQueue

        result = await self.db.execute(
            select(AutonomousProposalQueue).where(
                and_(
                    AutonomousProposalQueue.id == proposal_id,
                    AutonomousProposalQueue.company_id == company_id,
                    AutonomousProposalQueue.status == ProposalStatus.PENDING.value,
                )
            )
        )
        proposal = result.scalar_one_or_none()

        if not proposal:
            return ProposalResult(
                success=False,
                proposal_id=proposal_id,
                status=ProposalStatus.PENDING,
                message="Vorschlag nicht gefunden oder bereits verarbeitet.",
            )

        now = utc_now()
        proposal.status = ProposalStatus.REJECTED.value
        proposal.executed_at = now
        proposal.executed_by = str(user_id)
        if reason:
            metadata = proposal.metadata or {}
            metadata["rejection_reason"] = reason
            proposal.metadata = metadata

        await self.db.commit()

        logger.info(
            "proposal_rejected",
            proposal_id=str(proposal_id),
            user_id=str(user_id),
            reason=reason,
        )

        # Trigger Learning-Feedback
        await self._record_rejection_feedback(proposal, user_id)

        return ProposalResult(
            success=True,
            proposal_id=proposal_id,
            status=ProposalStatus.REJECTED,
            message="Vorschlag abgelehnt.",
        )

    async def process_due_proposals(
        self,
        executor_map: Dict[ProposalType, Callable[[uuid.UUID, JSONDict], Awaitable[bool]]],
    ) -> Dict[str, int]:
        """Verarbeitet faellige Proposals (Celery Task).

        Args:
            executor_map: Map von ProposalType zu Executor-Callback

        Returns:
            Dictionary mit Statistiken
        """
        from app.db.models import AutonomousProposalQueue

        now = utc_now()
        stats = {
            "processed": 0,
            "success": 0,
            "failed": 0,
            "skipped": 0,
        }

        # Hole alle faelligen PENDING Proposals
        result = await self.db.execute(
            select(AutonomousProposalQueue).where(
                and_(
                    AutonomousProposalQueue.status == ProposalStatus.PENDING.value,
                    AutonomousProposalQueue.scheduled_at <= now,
                )
            ).limit(100)
        )
        proposals = result.scalars().all()

        for proposal in proposals:
            stats["processed"] += 1

            try:
                proposal_type = ProposalType(proposal.proposal_type)
                executor = executor_map.get(proposal_type)

                if not executor:
                    logger.warning(
                        "no_executor_for_proposal_type",
                        proposal_type=proposal.proposal_type,
                    )
                    stats["skipped"] += 1
                    continue

                # Fuehre aus
                success = await executor(proposal.target_id, proposal.proposed_value)

                if success:
                    proposal.status = ProposalStatus.AUTO_ACCEPTED.value
                    proposal.executed_at = now
                    proposal.executed_by = "system"
                    proposal.rollback_until = now + timedelta(days=self.ROLLBACK_WINDOW_DAYS)
                    stats["success"] += 1

                    logger.info(
                        "proposal_auto_accepted",
                        proposal_id=str(proposal.id),
                        proposal_type=proposal.proposal_type,
                    )
                else:
                    proposal.status = ProposalStatus.EXPIRED.value
                    proposal.executed_at = now
                    proposal.executed_by = "system"
                    stats["failed"] += 1

                    logger.warning(
                        "proposal_execution_failed",
                        proposal_id=str(proposal.id),
                    )

            except Exception as e:
                proposal.status = ProposalStatus.EXPIRED.value
                stats["failed"] += 1
                logger.error(
                    "proposal_processing_error",
                    proposal_id=str(proposal.id),
                    **safe_error_log(e),
                )

        await self.db.commit()

        logger.info(
            "proposals_batch_processed",
            **stats,
        )

        return stats

    async def rollback_proposal(
        self,
        proposal_id: uuid.UUID,
        user_id: uuid.UUID,
        company_id: uuid.UUID,
        rollback_executor: Optional[Callable[[JSONDict], Awaitable[bool]]] = None,
    ) -> ProposalResult:
        """Macht einen ausgefuehrten Proposal rueckgaengig.

        Args:
            proposal_id: ID des Proposals
            user_id: ID des Users
            company_id: Company-ID
            rollback_executor: Callback fuer Rollback-Aktion

        Returns:
            ProposalResult
        """
        from app.db.models import AutonomousProposalQueue

        now = utc_now()

        result = await self.db.execute(
            select(AutonomousProposalQueue).where(
                and_(
                    AutonomousProposalQueue.id == proposal_id,
                    AutonomousProposalQueue.company_id == company_id,
                    or_(
                        AutonomousProposalQueue.status == ProposalStatus.APPROVED.value,
                        AutonomousProposalQueue.status == ProposalStatus.AUTO_ACCEPTED.value,
                    ),
                    AutonomousProposalQueue.rollback_until >= now,
                )
            )
        )
        proposal = result.scalar_one_or_none()

        if not proposal:
            return ProposalResult(
                success=False,
                proposal_id=proposal_id,
                status=ProposalStatus.PENDING,
                message="Vorschlag nicht gefunden, nicht ausgefuehrt oder Rollback-Zeitraum abgelaufen.",
            )

        # Fuehre Rollback aus
        if rollback_executor:
            try:
                success = await rollback_executor(proposal.proposed_value)
                if not success:
                    return ProposalResult(
                        success=False,
                        proposal_id=proposal_id,
                        status=ProposalStatus(proposal.status),
                        message="Rollback fehlgeschlagen.",
                    )
            except Exception as e:
                logger.error(
                    "rollback_execution_failed",
                    proposal_id=str(proposal_id),
                    **safe_error_log(e),
                )
                return ProposalResult(
                    success=False,
                    proposal_id=proposal_id,
                    status=ProposalStatus(proposal.status),
                    message=f"Rollback-Fehler: {type(e).__name__}",
                )

        # Update Status
        old_status = proposal.status
        proposal.status = ProposalStatus.ROLLED_BACK.value
        metadata = proposal.metadata or {}
        metadata["rolled_back_at"] = now.isoformat()
        metadata["rolled_back_by"] = str(user_id)
        metadata["previous_status"] = old_status
        proposal.metadata = metadata

        await self.db.commit()

        logger.info(
            "proposal_rolled_back",
            proposal_id=str(proposal_id),
            user_id=str(user_id),
            previous_status=old_status,
        )

        return ProposalResult(
            success=True,
            proposal_id=proposal_id,
            status=ProposalStatus.ROLLED_BACK,
            message="Vorschlag rueckgaengig gemacht.",
        )

    async def get_proposal_history(
        self,
        company_id: uuid.UUID,
        target_id: Optional[uuid.UUID] = None,
        proposal_type: Optional[ProposalType] = None,
        status: Optional[ProposalStatus] = None,
        days: int = 30,
        limit: int = 100,
    ) -> List[ProposalQueueItem]:
        """Holt Proposal-Historie.

        Args:
            company_id: Company-ID
            target_id: Optional Filter nach Ziel-ID
            proposal_type: Optional Filter nach Typ
            status: Optional Filter nach Status
            days: Anzahl Tage
            limit: Max Anzahl

        Returns:
            Liste von ProposalQueueItem
        """
        from app.db.models import AutonomousProposalQueue

        cutoff = utc_now() - timedelta(days=days)

        filters = [
            AutonomousProposalQueue.company_id == company_id,
            AutonomousProposalQueue.created_at >= cutoff,
        ]

        if target_id:
            filters.append(AutonomousProposalQueue.target_id == target_id)
        if proposal_type:
            filters.append(AutonomousProposalQueue.proposal_type == proposal_type.value)
        if status:
            filters.append(AutonomousProposalQueue.status == status.value)

        result = await self.db.execute(
            select(AutonomousProposalQueue)
            .where(and_(*filters))
            .order_by(AutonomousProposalQueue.created_at.desc())
            .limit(limit)
        )
        proposals = result.scalars().all()

        return [
            ProposalQueueItem(
                id=p.id,
                company_id=p.company_id,
                proposal_type=ProposalType(p.proposal_type),
                target_id=p.target_id,
                proposed_value=p.proposed_value,
                confidence=p.confidence,
                delay_hours=p.delay_hours,
                status=ProposalStatus(p.status),
                created_at=p.created_at,
                scheduled_at=p.scheduled_at,
                executed_at=p.executed_at,
                executed_by=p.executed_by,
                rollback_until=p.rollback_until,
                ai_decision_id=p.ai_decision_id,
                reasoning=p.reasoning,
                metadata=p.metadata or {},
            )
            for p in proposals
        ]

    async def _record_rejection_feedback(
        self,
        proposal,
        user_id: uuid.UUID,
    ) -> None:
        """Zeichnet Ablehnung als Feedback fuer Learning auf.

        Args:
            proposal: Das abgelehnte Proposal
            user_id: User-ID
        """
        try:
            from app.db.models import AILearningFeedback

            if not proposal.ai_decision_id:
                return

            feedback = AILearningFeedback(
                id=uuid.uuid4(),
                ai_decision_id=proposal.ai_decision_id,
                company_id=proposal.company_id,
                feedback_type="rejected",
                original_value=proposal.proposed_value,
                corrected_value=None,
                correction_reason=proposal.metadata.get("rejection_reason"),
                corrector_id=user_id,
                processed_for_learning=False,
            )

            self.db.add(feedback)
            await self.db.commit()

        except Exception as e:
            logger.warning(
                "rejection_feedback_error",
                **safe_error_log(e),
            )


# ============================================================================
# Factory Function
# ============================================================================


def get_delayed_acceptance_service(db: AsyncSession) -> DelayedAcceptanceService:
    """Factory-Funktion fuer DelayedAcceptanceService.

    Args:
        db: Async Database Session

    Returns:
        Konfigurierter DelayedAcceptanceService
    """
    return DelayedAcceptanceService(db=db)

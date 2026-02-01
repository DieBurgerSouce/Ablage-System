# -*- coding: utf-8 -*-
"""Parallel Approval Service fuer BPMN Workflows.

Enterprise-Grade Genehmigungsworkflows mit:
- Parallele Genehmigungen (mehrere Genehmiger gleichzeitig)
- Konsens-Typen (Alle, Mehrheit, Einer)
- Voting-Tracking
- Automatische Weiterleitung bei Konsens

Migration: 150_add_workflow_sla_monitoring.py
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any
from uuid import UUID
import structlog

from sqlalchemy import select, and_, or_, func, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.bpmn_models.bpmn import (
    ProcessInstance,
    ProcessTask,
    ProcessHistory,
    TaskStatus,
    TaskType,
)

logger = structlog.get_logger(__name__)


# =============================================================================
# Approval Enums
# =============================================================================

class ConsensusType(str, Enum):
    """Consensus types for parallel approvals."""
    ALL_MUST_APPROVE = "all"       # Alle muessen zustimmen
    MAJORITY = "majority"          # Mehrheit muss zustimmen
    ANY_ONE = "any"                # Einer reicht
    UNANIMOUS = "unanimous"        # Einstimmig (wie ALL, aber explizit)
    QUORUM = "quorum"              # Mindestanzahl


class ApprovalDecision(str, Enum):
    """Individual approval decision."""
    APPROVED = "approved"
    REJECTED = "rejected"
    ABSTAINED = "abstained"
    PENDING = "pending"


class ParallelApprovalStatus(str, Enum):
    """Status of parallel approval."""
    PENDING = "pending"           # Warten auf Stimmen
    APPROVED = "approved"         # Konsens: Genehmigt
    REJECTED = "rejected"         # Konsens: Abgelehnt
    CANCELLED = "cancelled"       # Abgebrochen
    EXPIRED = "expired"           # Zeitlimit ueberschritten


# =============================================================================
# Parallel Approval Service
# =============================================================================

class ParallelApprovalService:
    """Service fuer parallele Genehmigungen in Workflows.

    Ermoeglicht das gleichzeitige Abstimmen mehrerer Genehmiger
    mit konfigurierbaren Konsens-Regeln.
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize parallel approval service."""
        self.session = session

    # =========================================================================
    # Parallel Approval Creation
    # =========================================================================

    async def create_parallel_approval(
        self,
        workflow_instance_id: UUID,
        approvers: List[UUID],
        company_id: UUID,
        consensus_type: ConsensusType = ConsensusType.ALL_MUST_APPROVE,
        quorum_count: Optional[int] = None,
        title: str = "Parallele Genehmigung",
        description: Optional[str] = None,
        due_date: Optional[datetime] = None,
        element_id: str = "parallel_approval",
    ) -> Dict[str, Any]:
        """Erstellt eine parallele Genehmigung.

        Args:
            workflow_instance_id: Instanz-ID
            approvers: Liste der Genehmiger-User-IDs
            company_id: Mandant
            consensus_type: Art des Konsens
            quorum_count: Mindestanzahl bei QUORUM-Typ
            title: Titel der Genehmigung
            description: Beschreibung
            due_date: Faelligkeitsdatum
            element_id: BPMN Element-ID

        Returns:
            Parallel-Approval-Info
        """
        if not approvers:
            raise ValueError("Mindestens ein Genehmiger erforderlich")

        if consensus_type == ConsensusType.QUORUM and not quorum_count:
            raise ValueError("quorum_count erforderlich bei QUORUM-Konsenstyp")

        if quorum_count and quorum_count > len(approvers):
            raise ValueError("quorum_count darf nicht groesser als Anzahl Genehmiger sein")

        # Instanz laden und pruefen
        instance = await self._get_instance(workflow_instance_id, company_id)
        if not instance:
            raise ValueError("Prozess-Instanz nicht gefunden")

        # Approval-ID generieren
        import uuid
        approval_id = str(uuid.uuid4())

        # Votes initialisieren
        votes: Dict[str, Dict[str, Any]] = {}
        for approver_id in approvers:
            votes[str(approver_id)] = {
                "decision": ApprovalDecision.PENDING.value,
                "comment": None,
                "voted_at": None,
            }

        # Parallel-Approval in Instanz-Variablen speichern
        current_vars = dict(instance.variables)
        parallel_approvals = current_vars.get("_parallel_approvals", {})

        parallel_approvals[approval_id] = {
            "id": approval_id,
            "title": title,
            "description": description,
            "consensus_type": consensus_type.value,
            "quorum_count": quorum_count,
            "approvers": [str(a) for a in approvers],
            "votes": votes,
            "status": ParallelApprovalStatus.PENDING.value,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "due_date": due_date.isoformat() if due_date else None,
            "element_id": element_id,
            "consensus_reached_at": None,
            "final_decision": None,
        }

        current_vars["_parallel_approvals"] = parallel_approvals
        instance.variables = current_vars

        # Tasks fuer jeden Genehmiger erstellen
        for approver_id in approvers:
            task = ProcessTask(
                instance_id=instance.id,
                element_id=f"{element_id}_{approval_id}",
                element_name=title,
                task_type=TaskType.USER_TASK,
                status=TaskStatus.ASSIGNED,
                assignee_id=approver_id,
                priority=70,  # Hohe Prioritaet
                due_date=due_date,
                task_variables={
                    "parallel_approval_id": approval_id,
                    "consensus_type": consensus_type.value,
                    "total_approvers": len(approvers),
                },
                company_id=company_id,
            )
            self.session.add(task)

        # History
        history = ProcessHistory(
            instance_id=instance.id,
            event_type="PARALLEL_APPROVAL_CREATED",
            element_id=element_id,
            message=f"Parallele Genehmigung '{title}' erstellt mit {len(approvers)} Genehmigern",
            new_value={
                "approval_id": approval_id,
                "approvers": [str(a) for a in approvers],
                "consensus_type": consensus_type.value,
            },
            actor_type="system",
            company_id=company_id,
        )
        self.session.add(history)

        await self.session.flush()

        logger.info(
            "parallel_approval_created",
            approval_id=approval_id,
            instance_id=str(workflow_instance_id),
            approvers_count=len(approvers),
            consensus_type=consensus_type.value,
        )

        return {
            "approval_id": approval_id,
            "instance_id": str(workflow_instance_id),
            "title": title,
            "approvers": [str(a) for a in approvers],
            "consensus_type": consensus_type.value,
            "status": ParallelApprovalStatus.PENDING.value,
        }

    # =========================================================================
    # Voting
    # =========================================================================

    async def record_approval_vote(
        self,
        approval_id: str,
        approver_id: UUID,
        decision: ApprovalDecision,
        company_id: UUID,
        comment: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Zeichnet die Abstimmung eines Genehmigers auf.

        Args:
            approval_id: Parallel-Approval-ID
            approver_id: User-ID des Genehmigers
            decision: Entscheidung
            company_id: Mandant
            comment: Optionaler Kommentar

        Returns:
            Aktualisierter Approval-Status
        """
        # Instanz mit Approval finden
        instance = await self._find_instance_by_approval(approval_id, company_id)
        if not instance:
            raise ValueError("Parallele Genehmigung nicht gefunden")

        parallel_approvals = instance.variables.get("_parallel_approvals", {})
        approval = parallel_approvals.get(approval_id)

        if not approval:
            raise ValueError("Parallele Genehmigung nicht gefunden")

        # Status pruefen
        if approval["status"] != ParallelApprovalStatus.PENDING.value:
            raise ValueError(
                f"Genehmigung ist bereits abgeschlossen (Status: {approval['status']})"
            )

        # Genehmiger pruefen
        approver_str = str(approver_id)
        if approver_str not in approval["approvers"]:
            raise ValueError("Benutzer ist kein Genehmiger fuer diese Anfrage")

        # Bereits abgestimmt?
        current_vote = approval["votes"].get(approver_str, {})
        if current_vote.get("decision") != ApprovalDecision.PENDING.value:
            raise ValueError("Benutzer hat bereits abgestimmt")

        # Vote aufzeichnen
        approval["votes"][approver_str] = {
            "decision": decision.value,
            "comment": comment,
            "voted_at": datetime.now(timezone.utc).isoformat(),
        }

        # Konsens pruefen
        consensus_result = self._check_consensus(approval)

        if consensus_result["consensus_reached"]:
            approval["status"] = consensus_result["status"]
            approval["final_decision"] = consensus_result["final_decision"]
            approval["consensus_reached_at"] = datetime.now(timezone.utc).isoformat()

            # Tasks abschliessen
            await self._complete_approval_tasks(
                instance.id,
                approval_id,
                consensus_result["final_decision"],
            )

        # Variablen aktualisieren
        current_vars = dict(instance.variables)
        current_vars["_parallel_approvals"][approval_id] = approval
        instance.variables = current_vars

        # History
        history = ProcessHistory(
            instance_id=instance.id,
            event_type="APPROVAL_VOTE_RECORDED",
            message=f"Stimme abgegeben: {decision.value}",
            new_value={
                "approval_id": approval_id,
                "approver_id": approver_str,
                "decision": decision.value,
                "comment": comment,
            },
            actor_id=approver_id,
            actor_type="user",
            company_id=company_id,
        )
        self.session.add(history)

        await self.session.flush()

        logger.info(
            "approval_vote_recorded",
            approval_id=approval_id,
            approver_id=approver_str,
            decision=decision.value,
            consensus_reached=consensus_result["consensus_reached"],
        )

        return {
            "approval_id": approval_id,
            "vote_recorded": True,
            "decision": decision.value,
            "consensus_reached": consensus_result["consensus_reached"],
            "final_decision": consensus_result.get("final_decision"),
            "status": approval["status"],
            "votes_summary": self._get_votes_summary(approval),
        }

    async def check_consensus(
        self,
        approval_id: str,
        company_id: UUID,
    ) -> Dict[str, Any]:
        """Prueft ob Konsens erreicht wurde.

        Args:
            approval_id: Parallel-Approval-ID
            company_id: Mandant

        Returns:
            Konsens-Status
        """
        instance = await self._find_instance_by_approval(approval_id, company_id)
        if not instance:
            raise ValueError("Parallele Genehmigung nicht gefunden")

        approval = instance.variables.get("_parallel_approvals", {}).get(approval_id)
        if not approval:
            raise ValueError("Parallele Genehmigung nicht gefunden")

        consensus_result = self._check_consensus(approval)

        return {
            "approval_id": approval_id,
            "consensus_type": approval["consensus_type"],
            "status": approval["status"],
            "consensus_reached": consensus_result["consensus_reached"],
            "final_decision": consensus_result.get("final_decision"),
            "votes_summary": self._get_votes_summary(approval),
            "pending_approvers": [
                approver for approver, vote in approval["votes"].items()
                if vote["decision"] == ApprovalDecision.PENDING.value
            ],
        }

    # =========================================================================
    # Approval Status and Listing
    # =========================================================================

    async def get_approval_status(
        self,
        approval_id: str,
        company_id: UUID,
    ) -> Dict[str, Any]:
        """Gibt den Status einer parallelen Genehmigung zurueck.

        Args:
            approval_id: Parallel-Approval-ID
            company_id: Mandant

        Returns:
            Approval-Status mit Details
        """
        instance = await self._find_instance_by_approval(approval_id, company_id)
        if not instance:
            raise ValueError("Parallele Genehmigung nicht gefunden")

        approval = instance.variables.get("_parallel_approvals", {}).get(approval_id)
        if not approval:
            raise ValueError("Parallele Genehmigung nicht gefunden")

        return {
            "approval_id": approval_id,
            "instance_id": str(instance.id),
            "title": approval["title"],
            "description": approval.get("description"),
            "consensus_type": approval["consensus_type"],
            "quorum_count": approval.get("quorum_count"),
            "status": approval["status"],
            "created_at": approval["created_at"],
            "due_date": approval.get("due_date"),
            "final_decision": approval.get("final_decision"),
            "consensus_reached_at": approval.get("consensus_reached_at"),
            "votes": approval["votes"],
            "votes_summary": self._get_votes_summary(approval),
        }

    async def list_pending_approvals(
        self,
        user_id: UUID,
        company_id: UUID,
    ) -> List[Dict[str, Any]]:
        """Listet alle ausstehenden Genehmigungen fuer einen User.

        Args:
            user_id: User-ID
            company_id: Mandant

        Returns:
            Liste ausstehender Genehmigungen
        """
        # Tasks fuer den User finden
        query = (
            select(ProcessTask)
            .where(
                and_(
                    ProcessTask.company_id == company_id,
                    ProcessTask.assignee_id == user_id,
                    ProcessTask.status.in_([
                        TaskStatus.ACTIVE,
                        TaskStatus.ASSIGNED,
                        TaskStatus.IN_PROGRESS,
                    ]),
                    ProcessTask.task_variables.op("?")("parallel_approval_id"),
                )
            )
            .options(selectinload(ProcessTask.instance))
        )

        result = await self.session.execute(query)
        tasks = list(result.scalars().all())

        pending = []
        for task in tasks:
            approval_id = task.task_variables.get("parallel_approval_id")
            if not approval_id:
                continue

            instance = task.instance
            if not instance:
                continue

            approval = (instance.variables or {}).get(
                "_parallel_approvals", {}
            ).get(approval_id)

            if not approval or approval["status"] != ParallelApprovalStatus.PENDING.value:
                continue

            # Hat User schon abgestimmt?
            user_vote = approval["votes"].get(str(user_id), {})
            if user_vote.get("decision") != ApprovalDecision.PENDING.value:
                continue

            pending.append({
                "approval_id": approval_id,
                "instance_id": str(instance.id),
                "task_id": str(task.id),
                "title": approval["title"],
                "description": approval.get("description"),
                "consensus_type": approval["consensus_type"],
                "due_date": approval.get("due_date"),
                "created_at": approval["created_at"],
                "votes_summary": self._get_votes_summary(approval),
            })

        return pending

    async def list_workflow_approvals(
        self,
        workflow_instance_id: UUID,
        company_id: UUID,
    ) -> List[Dict[str, Any]]:
        """Listet alle parallelen Genehmigungen einer Workflow-Instanz.

        Args:
            workflow_instance_id: Instanz-ID
            company_id: Mandant

        Returns:
            Liste aller Genehmigungen der Instanz
        """
        instance = await self._get_instance(workflow_instance_id, company_id)
        if not instance:
            raise ValueError("Prozess-Instanz nicht gefunden")

        parallel_approvals = instance.variables.get("_parallel_approvals", {})

        approvals = []
        for approval_id, approval in parallel_approvals.items():
            approvals.append({
                "approval_id": approval_id,
                "title": approval["title"],
                "status": approval["status"],
                "consensus_type": approval["consensus_type"],
                "created_at": approval["created_at"],
                "final_decision": approval.get("final_decision"),
                "consensus_reached_at": approval.get("consensus_reached_at"),
                "votes_summary": self._get_votes_summary(approval),
            })

        return approvals

    # =========================================================================
    # Cancellation
    # =========================================================================

    async def cancel_approval(
        self,
        approval_id: str,
        company_id: UUID,
        reason: Optional[str] = None,
        cancelled_by_id: Optional[UUID] = None,
    ) -> Dict[str, Any]:
        """Bricht eine parallele Genehmigung ab.

        Args:
            approval_id: Parallel-Approval-ID
            company_id: Mandant
            reason: Abbruchgrund
            cancelled_by_id: User der abgebrochen hat

        Returns:
            Ergebnis
        """
        instance = await self._find_instance_by_approval(approval_id, company_id)
        if not instance:
            raise ValueError("Parallele Genehmigung nicht gefunden")

        approval = instance.variables.get("_parallel_approvals", {}).get(approval_id)
        if not approval:
            raise ValueError("Parallele Genehmigung nicht gefunden")

        if approval["status"] != ParallelApprovalStatus.PENDING.value:
            raise ValueError("Nur ausstehende Genehmigungen koennen abgebrochen werden")

        # Status aktualisieren
        approval["status"] = ParallelApprovalStatus.CANCELLED.value
        approval["cancelled_at"] = datetime.now(timezone.utc).isoformat()
        approval["cancellation_reason"] = reason

        current_vars = dict(instance.variables)
        current_vars["_parallel_approvals"][approval_id] = approval
        instance.variables = current_vars

        # Tasks abbrechen
        await self._cancel_approval_tasks(instance.id, approval_id)

        # History
        history = ProcessHistory(
            instance_id=instance.id,
            event_type="PARALLEL_APPROVAL_CANCELLED",
            message=f"Parallele Genehmigung abgebrochen: {reason or 'Kein Grund angegeben'}",
            new_value={"approval_id": approval_id, "reason": reason},
            actor_id=cancelled_by_id,
            actor_type="user" if cancelled_by_id else "system",
            company_id=company_id,
        )
        self.session.add(history)

        await self.session.flush()

        logger.info(
            "parallel_approval_cancelled",
            approval_id=approval_id,
            reason=reason,
        )

        return {
            "approval_id": approval_id,
            "status": ParallelApprovalStatus.CANCELLED.value,
            "cancelled": True,
        }

    # =========================================================================
    # Internal Helpers
    # =========================================================================

    def _check_consensus(self, approval: Dict[str, Any]) -> Dict[str, Any]:
        """Prueft ob Konsens erreicht wurde basierend auf Votes und Konsenstyp."""
        consensus_type = ConsensusType(approval["consensus_type"])
        votes = approval["votes"]
        total = len(votes)

        approved_count = sum(
            1 for v in votes.values()
            if v["decision"] == ApprovalDecision.APPROVED.value
        )
        rejected_count = sum(
            1 for v in votes.values()
            if v["decision"] == ApprovalDecision.REJECTED.value
        )
        pending_count = sum(
            1 for v in votes.values()
            if v["decision"] == ApprovalDecision.PENDING.value
        )

        # Konsens-Regeln
        if consensus_type == ConsensusType.ALL_MUST_APPROVE:
            # Alle muessen zustimmen
            if rejected_count > 0:
                return {
                    "consensus_reached": True,
                    "status": ParallelApprovalStatus.REJECTED.value,
                    "final_decision": ApprovalDecision.REJECTED.value,
                }
            if approved_count == total:
                return {
                    "consensus_reached": True,
                    "status": ParallelApprovalStatus.APPROVED.value,
                    "final_decision": ApprovalDecision.APPROVED.value,
                }

        elif consensus_type == ConsensusType.UNANIMOUS:
            # Einstimmig
            if rejected_count > 0:
                return {
                    "consensus_reached": True,
                    "status": ParallelApprovalStatus.REJECTED.value,
                    "final_decision": ApprovalDecision.REJECTED.value,
                }
            if approved_count == total and pending_count == 0:
                return {
                    "consensus_reached": True,
                    "status": ParallelApprovalStatus.APPROVED.value,
                    "final_decision": ApprovalDecision.APPROVED.value,
                }

        elif consensus_type == ConsensusType.MAJORITY:
            # Einfache Mehrheit (>50%)
            majority_threshold = total / 2
            if approved_count > majority_threshold:
                return {
                    "consensus_reached": True,
                    "status": ParallelApprovalStatus.APPROVED.value,
                    "final_decision": ApprovalDecision.APPROVED.value,
                }
            if rejected_count > majority_threshold:
                return {
                    "consensus_reached": True,
                    "status": ParallelApprovalStatus.REJECTED.value,
                    "final_decision": ApprovalDecision.REJECTED.value,
                }

        elif consensus_type == ConsensusType.ANY_ONE:
            # Einer reicht
            if approved_count >= 1:
                return {
                    "consensus_reached": True,
                    "status": ParallelApprovalStatus.APPROVED.value,
                    "final_decision": ApprovalDecision.APPROVED.value,
                }
            if rejected_count == total:
                return {
                    "consensus_reached": True,
                    "status": ParallelApprovalStatus.REJECTED.value,
                    "final_decision": ApprovalDecision.REJECTED.value,
                }

        elif consensus_type == ConsensusType.QUORUM:
            # Mindestanzahl
            quorum = approval.get("quorum_count", 1)
            if approved_count >= quorum:
                return {
                    "consensus_reached": True,
                    "status": ParallelApprovalStatus.APPROVED.value,
                    "final_decision": ApprovalDecision.APPROVED.value,
                }
            # Quorum nicht mehr erreichbar?
            max_possible = approved_count + pending_count
            if max_possible < quorum:
                return {
                    "consensus_reached": True,
                    "status": ParallelApprovalStatus.REJECTED.value,
                    "final_decision": ApprovalDecision.REJECTED.value,
                }

        # Noch kein Konsens
        return {
            "consensus_reached": False,
            "status": ParallelApprovalStatus.PENDING.value,
        }

    def _get_votes_summary(self, approval: Dict[str, Any]) -> Dict[str, int]:
        """Erstellt Zusammenfassung der Stimmen."""
        votes = approval["votes"]

        return {
            "total": len(votes),
            "approved": sum(
                1 for v in votes.values()
                if v["decision"] == ApprovalDecision.APPROVED.value
            ),
            "rejected": sum(
                1 for v in votes.values()
                if v["decision"] == ApprovalDecision.REJECTED.value
            ),
            "abstained": sum(
                1 for v in votes.values()
                if v["decision"] == ApprovalDecision.ABSTAINED.value
            ),
            "pending": sum(
                1 for v in votes.values()
                if v["decision"] == ApprovalDecision.PENDING.value
            ),
        }

    async def _complete_approval_tasks(
        self,
        instance_id: UUID,
        approval_id: str,
        final_decision: str,
    ) -> None:
        """Schliesst alle Tasks einer parallelen Genehmigung ab."""
        stmt = (
            update(ProcessTask)
            .where(
                and_(
                    ProcessTask.instance_id == instance_id,
                    ProcessTask.element_id.like(f"%{approval_id}%"),
                    ProcessTask.status.in_([
                        TaskStatus.ACTIVE,
                        TaskStatus.ASSIGNED,
                        TaskStatus.IN_PROGRESS,
                    ]),
                )
            )
            .values(
                status=TaskStatus.COMPLETED,
                completed_at=datetime.now(timezone.utc),
            )
        )
        await self.session.execute(stmt)

    async def _cancel_approval_tasks(
        self,
        instance_id: UUID,
        approval_id: str,
    ) -> None:
        """Bricht alle Tasks einer parallelen Genehmigung ab."""
        stmt = (
            update(ProcessTask)
            .where(
                and_(
                    ProcessTask.instance_id == instance_id,
                    ProcessTask.element_id.like(f"%{approval_id}%"),
                    ProcessTask.status.in_([
                        TaskStatus.ACTIVE,
                        TaskStatus.ASSIGNED,
                        TaskStatus.IN_PROGRESS,
                    ]),
                )
            )
            .values(status=TaskStatus.SKIPPED)
        )
        await self.session.execute(stmt)

    async def _get_instance(
        self,
        instance_id: UUID,
        company_id: UUID,
    ) -> Optional[ProcessInstance]:
        """Laedt Prozess-Instanz."""
        query = select(ProcessInstance).where(
            and_(
                ProcessInstance.id == instance_id,
                ProcessInstance.company_id == company_id,
            )
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def _find_instance_by_approval(
        self,
        approval_id: str,
        company_id: UUID,
    ) -> Optional[ProcessInstance]:
        """Findet Instanz die eine bestimmte parallele Genehmigung enthaelt."""
        # JSONB-Suche nach approval_id
        query = select(ProcessInstance).where(
            and_(
                ProcessInstance.company_id == company_id,
                ProcessInstance.variables.op("->")("_parallel_approvals").op("??")(approval_id),
            )
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()


# =============================================================================
# Factory Function
# =============================================================================

def get_parallel_approval_service(session: AsyncSession) -> ParallelApprovalService:
    """Factory function for ParallelApprovalService."""
    return ParallelApprovalService(session)

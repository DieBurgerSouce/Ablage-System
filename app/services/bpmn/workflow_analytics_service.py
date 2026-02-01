# -*- coding: utf-8 -*-
"""Workflow Analytics Service fuer BPMN Engine.

Enterprise-Grade Analytics mit:
- Bottleneck-Analyse
- Throughput-Metriken
- User-Produktivitaet
- Durchschnittliche Dauern pro Workflow-Typ

Migration: 150_add_workflow_sla_monitoring.py
"""

from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple, Any
from uuid import UUID
import structlog

from sqlalchemy import select, and_, or_, func, text, case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.bpmn_models.bpmn import (
    ProcessInstance,
    ProcessDefinition,
    ProcessTask,
    ProcessHistory,
    ProcessStatus,
    TaskStatus,
)

logger = structlog.get_logger(__name__)


# =============================================================================
# Workflow Analytics Service
# =============================================================================

class WorkflowAnalyticsService:
    """Service fuer Workflow-Analysen und Metriken.

    Bietet Einblicke in:
    - Workflow-Performance
    - Engpaesse
    - User-Produktivitaet
    - Durchlaufzeiten
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize workflow analytics service."""
        self.session = session

    # =========================================================================
    # Bottleneck Analysis
    # =========================================================================

    async def get_bottleneck_analysis(
        self,
        company_id: UUID,
        time_range_days: int = 30,
        limit: int = 10,
    ) -> Dict[str, Any]:
        """Identifiziert Workflow-Engpaesse.

        Analysiert welche Tasks/Schritte am laengsten dauern
        und wo Workflows am haeufigsten haengen bleiben.

        Args:
            company_id: Mandant
            time_range_days: Zeitraum in Tagen
            limit: Max. Anzahl Engpaesse

        Returns:
            Bottleneck-Analyse
        """
        start_date = datetime.now(timezone.utc) - timedelta(days=time_range_days)

        # 1. Langsamste Tasks (durchschnittliche Bearbeitungszeit)
        slow_tasks_query = (
            select(
                ProcessTask.element_id,
                ProcessTask.element_name,
                func.count(ProcessTask.id).label("task_count"),
                func.avg(
                    func.extract(
                        "epoch",
                        ProcessTask.completed_at - ProcessTask.created_at
                    ) / 3600  # In Stunden
                ).label("avg_duration_hours"),
                func.max(
                    func.extract(
                        "epoch",
                        ProcessTask.completed_at - ProcessTask.created_at
                    ) / 3600
                ).label("max_duration_hours"),
            )
            .where(
                and_(
                    ProcessTask.company_id == company_id,
                    ProcessTask.status == TaskStatus.COMPLETED,
                    ProcessTask.completed_at >= start_date,
                    ProcessTask.completed_at.isnot(None),
                    ProcessTask.created_at.isnot(None),
                )
            )
            .group_by(ProcessTask.element_id, ProcessTask.element_name)
            .order_by(text("avg_duration_hours DESC NULLS LAST"))
            .limit(limit)
        )

        slow_tasks_result = await self.session.execute(slow_tasks_query)
        slow_tasks = [
            {
                "element_id": row.element_id,
                "element_name": row.element_name or row.element_id,
                "task_count": row.task_count,
                "avg_duration_hours": float(row.avg_duration_hours or 0),
                "max_duration_hours": float(row.max_duration_hours or 0),
            }
            for row in slow_tasks_result.all()
        ]

        # 2. Meiste offene Tasks (zeigt aktuelle Engpaesse)
        blocked_query = (
            select(
                ProcessTask.element_id,
                ProcessTask.element_name,
                func.count(ProcessTask.id).label("blocked_count"),
                func.min(ProcessTask.created_at).label("oldest_task"),
            )
            .where(
                and_(
                    ProcessTask.company_id == company_id,
                    ProcessTask.status.in_([
                        TaskStatus.ACTIVE,
                        TaskStatus.ASSIGNED,
                        TaskStatus.PENDING,
                    ]),
                )
            )
            .group_by(ProcessTask.element_id, ProcessTask.element_name)
            .order_by(text("blocked_count DESC"))
            .limit(limit)
        )

        blocked_result = await self.session.execute(blocked_query)
        blocked_tasks = [
            {
                "element_id": row.element_id,
                "element_name": row.element_name or row.element_id,
                "blocked_count": row.blocked_count,
                "oldest_task_created": row.oldest_task.isoformat() if row.oldest_task else None,
                "days_waiting": (
                    (datetime.now(timezone.utc) - row.oldest_task).days
                    if row.oldest_task else 0
                ),
            }
            for row in blocked_result.all()
        ]

        # 3. Eskalations-Hotspots
        escalation_query = (
            select(
                ProcessTask.element_id,
                ProcessTask.element_name,
                func.count(ProcessTask.id).label("escalation_count"),
            )
            .where(
                and_(
                    ProcessTask.company_id == company_id,
                    ProcessTask.escalation_level > 0,
                    ProcessTask.created_at >= start_date,
                )
            )
            .group_by(ProcessTask.element_id, ProcessTask.element_name)
            .order_by(text("escalation_count DESC"))
            .limit(limit)
        )

        escalation_result = await self.session.execute(escalation_query)
        escalation_hotspots = [
            {
                "element_id": row.element_id,
                "element_name": row.element_name or row.element_id,
                "escalation_count": row.escalation_count,
            }
            for row in escalation_result.all()
        ]

        return {
            "time_range_days": time_range_days,
            "slow_tasks": slow_tasks,
            "blocked_tasks": blocked_tasks,
            "escalation_hotspots": escalation_hotspots,
            "recommendations": self._generate_bottleneck_recommendations(
                slow_tasks, blocked_tasks, escalation_hotspots
            ),
        }

    def _generate_bottleneck_recommendations(
        self,
        slow_tasks: List[Dict[str, Any]],
        blocked_tasks: List[Dict[str, Any]],
        escalation_hotspots: List[Dict[str, Any]],
    ) -> List[str]:
        """Generiert Empfehlungen basierend auf Bottleneck-Analyse."""
        recommendations = []

        # Langsame Tasks
        if slow_tasks and slow_tasks[0].get("avg_duration_hours", 0) > 24:
            task_name = slow_tasks[0].get("element_name", "Unbekannt")
            recommendations.append(
                f"Task '{task_name}' dauert durchschnittlich ueber 24 Stunden. "
                f"Ueberpruefen Sie den Prozess auf Optimierungsmoeglichkeiten."
            )

        # Blockierte Tasks
        if blocked_tasks and blocked_tasks[0].get("blocked_count", 0) > 10:
            task_name = blocked_tasks[0].get("element_name", "Unbekannt")
            recommendations.append(
                f"Ueber 10 Tasks vom Typ '{task_name}' warten auf Bearbeitung. "
                f"Erwaegen Sie zusaetzliche Ressourcen oder Automatisierung."
            )

        # Eskalationen
        if escalation_hotspots and escalation_hotspots[0].get("escalation_count", 0) > 5:
            task_name = escalation_hotspots[0].get("element_name", "Unbekannt")
            recommendations.append(
                f"Task '{task_name}' wird haeufig eskaliert. "
                f"Schulung oder Prozessanpassung empfohlen."
            )

        if not recommendations:
            recommendations.append(
                "Keine kritischen Engpaesse identifiziert. "
                "Workflow-Performance ist im normalen Bereich."
            )

        return recommendations

    # =========================================================================
    # Throughput Metrics
    # =========================================================================

    async def get_throughput_metrics(
        self,
        company_id: UUID,
        time_range_days: int = 30,
        group_by: str = "day",  # day, week, month
    ) -> Dict[str, Any]:
        """Gibt Durchsatz-Metriken zurueck.

        Args:
            company_id: Mandant
            time_range_days: Zeitraum in Tagen
            group_by: Gruppierung (day, week, month)

        Returns:
            Throughput-Metriken
        """
        start_date = datetime.now(timezone.utc) - timedelta(days=time_range_days)

        # Gruppierungs-Funktion basierend auf Parameter
        if group_by == "week":
            date_trunc = func.date_trunc("week", ProcessInstance.ended_at)
        elif group_by == "month":
            date_trunc = func.date_trunc("month", ProcessInstance.ended_at)
        else:
            date_trunc = func.date(ProcessInstance.ended_at)

        # Durchsatz pro Periode
        throughput_query = (
            select(
                date_trunc.label("period"),
                func.count(ProcessInstance.id).label("completed"),
                func.count(
                    case(
                        (ProcessInstance.status == ProcessStatus.COMPLETED, ProcessInstance.id)
                    )
                ).label("successful"),
                func.count(
                    case(
                        (ProcessInstance.status == ProcessStatus.TERMINATED, ProcessInstance.id)
                    )
                ).label("terminated"),
            )
            .where(
                and_(
                    ProcessInstance.company_id == company_id,
                    ProcessInstance.ended_at >= start_date,
                    ProcessInstance.ended_at.isnot(None),
                )
            )
            .group_by(date_trunc)
            .order_by(date_trunc)
        )

        result = await self.session.execute(throughput_query)
        throughput_data = [
            {
                "period": str(row.period),
                "completed": row.completed,
                "successful": row.successful or 0,
                "terminated": row.terminated or 0,
                "success_rate": (
                    (row.successful / row.completed * 100)
                    if row.completed > 0 else 100.0
                ),
            }
            for row in result.all()
        ]

        # Gesamtstatistiken
        total_completed = sum(d["completed"] for d in throughput_data)
        total_successful = sum(d["successful"] for d in throughput_data)
        avg_per_period = (
            total_completed / len(throughput_data)
            if throughput_data else 0
        )

        # Aktuell laufende Workflows
        running_query = (
            select(func.count(ProcessInstance.id))
            .where(
                and_(
                    ProcessInstance.company_id == company_id,
                    ProcessInstance.status == ProcessStatus.RUNNING,
                )
            )
        )
        running_count = await self.session.scalar(running_query) or 0

        return {
            "time_range_days": time_range_days,
            "group_by": group_by,
            "data": throughput_data,
            "summary": {
                "total_completed": total_completed,
                "total_successful": total_successful,
                "overall_success_rate": (
                    (total_successful / total_completed * 100)
                    if total_completed > 0 else 100.0
                ),
                "avg_per_period": round(avg_per_period, 2),
                "currently_running": running_count,
            },
        }

    # =========================================================================
    # User Productivity
    # =========================================================================

    async def get_user_productivity(
        self,
        user_id: UUID,
        company_id: UUID,
        time_range_days: int = 30,
    ) -> Dict[str, Any]:
        """Gibt Produktivitaetsmetriken fuer einen User zurueck.

        Args:
            user_id: User-ID
            company_id: Mandant
            time_range_days: Zeitraum in Tagen

        Returns:
            User-Produktivitaetsmetriken
        """
        start_date = datetime.now(timezone.utc) - timedelta(days=time_range_days)

        # Abgeschlossene Tasks
        completed_query = (
            select(func.count(ProcessTask.id))
            .where(
                and_(
                    ProcessTask.company_id == company_id,
                    ProcessTask.assignee_id == user_id,
                    ProcessTask.status == TaskStatus.COMPLETED,
                    ProcessTask.completed_at >= start_date,
                )
            )
        )
        completed_count = await self.session.scalar(completed_query) or 0

        # Durchschnittliche Bearbeitungszeit
        avg_duration_query = (
            select(
                func.avg(
                    func.extract(
                        "epoch",
                        ProcessTask.completed_at - ProcessTask.claimed_at
                    ) / 3600
                )
            )
            .where(
                and_(
                    ProcessTask.company_id == company_id,
                    ProcessTask.assignee_id == user_id,
                    ProcessTask.status == TaskStatus.COMPLETED,
                    ProcessTask.completed_at >= start_date,
                    ProcessTask.claimed_at.isnot(None),
                )
            )
        )
        avg_duration = await self.session.scalar(avg_duration_query) or 0

        # Aktuell zugewiesene Tasks
        pending_query = (
            select(func.count(ProcessTask.id))
            .where(
                and_(
                    ProcessTask.company_id == company_id,
                    ProcessTask.assignee_id == user_id,
                    ProcessTask.status.in_([
                        TaskStatus.ASSIGNED,
                        TaskStatus.IN_PROGRESS,
                    ]),
                )
            )
        )
        pending_count = await self.session.scalar(pending_query) or 0

        # Ueberfaellige Tasks
        overdue_query = (
            select(func.count(ProcessTask.id))
            .where(
                and_(
                    ProcessTask.company_id == company_id,
                    ProcessTask.assignee_id == user_id,
                    ProcessTask.status.in_([
                        TaskStatus.ASSIGNED,
                        TaskStatus.IN_PROGRESS,
                    ]),
                    ProcessTask.due_date < datetime.now(timezone.utc),
                )
            )
        )
        overdue_count = await self.session.scalar(overdue_query) or 0

        # Eskalierte Tasks
        escalated_query = (
            select(func.count(ProcessTask.id))
            .where(
                and_(
                    ProcessTask.company_id == company_id,
                    ProcessTask.assignee_id == user_id,
                    ProcessTask.escalation_level > 0,
                    ProcessTask.created_at >= start_date,
                )
            )
        )
        escalated_count = await self.session.scalar(escalated_query) or 0

        # Tasks pro Tag
        tasks_per_day = (
            completed_count / time_range_days
            if time_range_days > 0 else 0
        )

        # Performance-Score berechnen
        performance_score = self._calculate_performance_score(
            completed_count, pending_count, overdue_count, escalated_count
        )

        return {
            "user_id": str(user_id),
            "time_range_days": time_range_days,
            "metrics": {
                "tasks_completed": completed_count,
                "tasks_pending": pending_count,
                "tasks_overdue": overdue_count,
                "tasks_escalated": escalated_count,
                "avg_processing_time_hours": round(float(avg_duration), 2),
                "tasks_per_day": round(tasks_per_day, 2),
            },
            "performance_score": performance_score,
            "score_breakdown": {
                "completion_rate": "Basierend auf abgeschlossenen Tasks",
                "overdue_penalty": "Abzug fuer ueberfaellige Tasks",
                "escalation_penalty": "Abzug fuer eskalierte Tasks",
            },
        }

    def _calculate_performance_score(
        self,
        completed: int,
        pending: int,
        overdue: int,
        escalated: int,
    ) -> Dict[str, Any]:
        """Berechnet Performance-Score fuer User."""
        # Basis-Score
        base_score = 100

        # Completion Bonus (bis zu +20)
        completion_bonus = min(completed * 2, 20)

        # Overdue Penalty (-5 pro ueberfaelligem Task)
        overdue_penalty = min(overdue * 5, 30)

        # Escalation Penalty (-3 pro eskaliertem Task)
        escalation_penalty = min(escalated * 3, 15)

        # Finaler Score
        final_score = max(0, min(100,
            base_score + completion_bonus - overdue_penalty - escalation_penalty
        ))

        # Rating
        if final_score >= 90:
            rating = "Exzellent"
        elif final_score >= 75:
            rating = "Gut"
        elif final_score >= 50:
            rating = "Durchschnittlich"
        else:
            rating = "Verbesserungswuerdig"

        return {
            "score": round(final_score, 1),
            "rating": rating,
            "components": {
                "base": base_score,
                "completion_bonus": completion_bonus,
                "overdue_penalty": -overdue_penalty,
                "escalation_penalty": -escalation_penalty,
            },
        }

    # =========================================================================
    # Duration Analysis
    # =========================================================================

    async def get_average_duration_by_type(
        self,
        company_id: UUID,
        time_range_days: int = 30,
    ) -> Dict[str, Any]:
        """Gibt durchschnittliche Dauer pro Workflow-Typ zurueck.

        Args:
            company_id: Mandant
            time_range_days: Zeitraum in Tagen

        Returns:
            Durchschnittliche Dauern
        """
        start_date = datetime.now(timezone.utc) - timedelta(days=time_range_days)

        query = (
            select(
                ProcessDefinition.key,
                ProcessDefinition.name,
                func.count(ProcessInstance.id).label("instance_count"),
                func.avg(
                    func.extract(
                        "epoch",
                        ProcessInstance.ended_at - ProcessInstance.started_at
                    ) / 3600
                ).label("avg_duration_hours"),
                func.min(
                    func.extract(
                        "epoch",
                        ProcessInstance.ended_at - ProcessInstance.started_at
                    ) / 3600
                ).label("min_duration_hours"),
                func.max(
                    func.extract(
                        "epoch",
                        ProcessInstance.ended_at - ProcessInstance.started_at
                    ) / 3600
                ).label("max_duration_hours"),
                func.stddev(
                    func.extract(
                        "epoch",
                        ProcessInstance.ended_at - ProcessInstance.started_at
                    ) / 3600
                ).label("stddev_hours"),
            )
            .join(ProcessDefinition, ProcessInstance.definition_id == ProcessDefinition.id)
            .where(
                and_(
                    ProcessInstance.company_id == company_id,
                    ProcessInstance.status.in_([
                        ProcessStatus.COMPLETED,
                        ProcessStatus.TERMINATED,
                    ]),
                    ProcessInstance.ended_at >= start_date,
                    ProcessInstance.started_at.isnot(None),
                )
            )
            .group_by(ProcessDefinition.key, ProcessDefinition.name)
            .order_by(text("avg_duration_hours DESC NULLS LAST"))
        )

        result = await self.session.execute(query)
        durations = [
            {
                "workflow_key": row.key,
                "workflow_name": row.name,
                "instance_count": row.instance_count,
                "avg_duration_hours": round(float(row.avg_duration_hours or 0), 2),
                "min_duration_hours": round(float(row.min_duration_hours or 0), 2),
                "max_duration_hours": round(float(row.max_duration_hours or 0), 2),
                "stddev_hours": round(float(row.stddev_hours or 0), 2),
            }
            for row in result.all()
        ]

        # Gesamtdurchschnitt
        total_instances = sum(d["instance_count"] for d in durations)
        weighted_avg = (
            sum(d["avg_duration_hours"] * d["instance_count"] for d in durations) / total_instances
            if total_instances > 0 else 0
        )

        return {
            "time_range_days": time_range_days,
            "by_workflow_type": durations,
            "summary": {
                "total_instances": total_instances,
                "workflow_types": len(durations),
                "overall_avg_duration_hours": round(weighted_avg, 2),
            },
        }

    # =========================================================================
    # Combined Dashboard
    # =========================================================================

    async def get_analytics_dashboard(
        self,
        company_id: UUID,
        time_range_days: int = 30,
    ) -> Dict[str, Any]:
        """Kombiniertes Analytics-Dashboard.

        Args:
            company_id: Mandant
            time_range_days: Zeitraum in Tagen

        Returns:
            Vollstaendiges Dashboard
        """
        # Alle Metriken parallel sammeln
        bottlenecks = await self.get_bottleneck_analysis(
            company_id, time_range_days, limit=5
        )
        throughput = await self.get_throughput_metrics(
            company_id, time_range_days
        )
        durations = await self.get_average_duration_by_type(
            company_id, time_range_days
        )

        return {
            "company_id": str(company_id),
            "time_range_days": time_range_days,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "bottlenecks": {
                "top_slow_tasks": bottlenecks["slow_tasks"][:3],
                "current_blocks": bottlenecks["blocked_tasks"][:3],
                "recommendations": bottlenecks["recommendations"],
            },
            "throughput": {
                "total_completed": throughput["summary"]["total_completed"],
                "success_rate": throughput["summary"]["overall_success_rate"],
                "currently_running": throughput["summary"]["currently_running"],
                "trend": throughput["data"][-7:] if throughput["data"] else [],
            },
            "durations": {
                "slowest_workflows": durations["by_workflow_type"][:3],
                "overall_avg_hours": durations["summary"]["overall_avg_duration_hours"],
            },
        }


# =============================================================================
# Factory Function
# =============================================================================

def get_workflow_analytics_service(session: AsyncSession) -> WorkflowAnalyticsService:
    """Factory function for WorkflowAnalyticsService."""
    return WorkflowAnalyticsService(session)

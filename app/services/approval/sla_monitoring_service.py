# -*- coding: utf-8 -*-
"""
SLAMonitoringService - SLA-Überwachung für Genehmigungsworkflows.

Feature #3: Approval Workflow Depth
- SLA-Metriken pro Genehmigungsschritt erfassen
- SLA-Verletzungen erkennen
- Dashboard-Daten (Durchschnitt, Bottlenecks, Compliance-Rate)
- Bottleneck-Analyse (langsamste Genehmiger)

Nutzt models_approval_extended für ApprovalSLAMetric.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from uuid import UUID

import structlog
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utc_now
from app.db.models import (
    ApprovalRequest,
    ApprovalStatus,
    ApprovalStep,
)
from app.db.models_approval_extended import ApprovalSLAMetric

logger = structlog.get_logger(__name__)


# ============================================================================
# Datenklassen
# ============================================================================


@dataclass
class SLADashboard:
    """Dashboard-Daten für SLA-Monitoring."""

    avg_approval_hours: float
    median_approval_hours: float
    total_requests_period: int
    total_completed_period: int
    sla_compliance_rate: float  # 0.0 - 100.0
    sla_breaches: int
    overdue_count: int
    bottleneck_users: List[Dict[str, object]] = field(default_factory=list)


@dataclass
class BottleneckEntry:
    """Einzelner Bottleneck-Eintrag."""

    user_id: str
    pending_count: int
    avg_wait_hours: float
    oldest_pending_hours: float


# ============================================================================
# Service
# ============================================================================


class SLAMonitoringService:
    """Service für SLA-Überwachung von Genehmigungsworkflows.

    Trackt SLA-Metriken pro Genehmigungsschritt, erkennt Verletzungen
    und liefert Dashboard-Daten für das Management.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def record_sla_metric(
        self,
        db: AsyncSession,
        approval_request_id: UUID,
        step: ApprovalStep,
    ) -> ApprovalSLAMetric:
        """Erfasst SLA-Metrik für einen abgeschlossenen Schritt.

        Args:
            db: Async Database Session
            approval_request_id: ID der Genehmigungsanfrage
            step: Der abgeschlossene Genehmigungsschritt

        Returns:
            Erstellte ApprovalSLAMetric
        """
        # Anfrage laden für company_id und SLA-Ziel
        request_stmt = select(ApprovalRequest).where(
            ApprovalRequest.id == approval_request_id
        )
        request_result = await db.execute(request_stmt)
        request = request_result.scalar_one_or_none()

        if not request:
            raise ValueError(
                f"ApprovalRequest {approval_request_id} nicht gefunden"
            )

        now = utc_now()
        assigned_at = step.created_at or request.created_at
        completed_at = step.decision_date or now

        # SLA-Ziel aus der Anfrage oder Default 48h
        sla_hours_from_chain = 48.0
        if request.approval_chain:
            for chain_step in request.approval_chain:
                if chain_step.get("step") == step.step_number:
                    sla_hours_from_chain = float(
                        chain_step.get("timeout_hours", 48)
                    )
                    break

        # SLA-Verletzung prüfen
        duration_hours = (
            (completed_at - assigned_at).total_seconds() / 3600.0
        )
        is_breached = duration_hours > sla_hours_from_chain
        breached_at_value = None
        if is_breached:
            breached_at_value = assigned_at + timedelta(
                hours=sla_hours_from_chain
            )

        metric = ApprovalSLAMetric(
            company_id=request.company_id,
            approval_request_id=approval_request_id,
            step_number=step.step_number,
            assigned_at=assigned_at,
            completed_at=completed_at,
            sla_target_hours=sla_hours_from_chain,
            is_breached=is_breached,
            breached_at=breached_at_value,
        )

        db.add(metric)
        await db.flush()

        if is_breached:
            logger.warning(
                "sla_breach_recorded",
                approval_request_id=str(approval_request_id),
                step_number=step.step_number,
                duration_hours=round(duration_hours, 2),
                sla_target_hours=sla_hours_from_chain,
            )

        return metric

    async def check_sla_breaches(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> List[Dict[str, object]]:
        """Findet aktuell verletzte SLAs (offene Genehmigungen über dem Limit).

        Args:
            db: Async Database Session
            company_id: ID der Firma

        Returns:
            Liste der SLA-Verletzungen mit Details
        """
        now = utc_now()

        # Offene Genehmigungen die ihr due_date überschritten haben
        stmt = (
            select(ApprovalRequest)
            .where(
                and_(
                    ApprovalRequest.company_id == company_id,
                    ApprovalRequest.status == ApprovalStatus.PENDING,
                    ApprovalRequest.due_date < now,
                )
            )
            .order_by(ApprovalRequest.due_date.asc())
        )

        result = await db.execute(stmt)
        breached_requests = result.scalars().all()

        breaches: List[Dict[str, object]] = []
        for request in breached_requests:
            wait_hours = (
                (now - request.created_at).total_seconds() / 3600.0
                if request.created_at
                else 0.0
            )
            overdue_hours = (
                (now - request.due_date).total_seconds() / 3600.0
                if request.due_date
                else 0.0
            )

            breaches.append(
                {
                    "request_id": str(request.id),
                    "title": request.title,
                    "entity_type": request.entity_type,
                    "current_step": request.current_step,
                    "total_steps": request.total_steps,
                    "created_at": (
                        request.created_at.isoformat()
                        if request.created_at
                        else None
                    ),
                    "due_date": (
                        request.due_date.isoformat()
                        if request.due_date
                        else None
                    ),
                    "wait_hours": round(wait_hours, 1),
                    "overdue_hours": round(overdue_hours, 1),
                    "priority": (
                        request.priority.value
                        if request.priority
                        else "normal"
                    ),
                    "is_escalated": request.is_escalated,
                }
            )

        if breaches:
            logger.warning(
                "sla_breaches_found",
                company_id=str(company_id),
                breach_count=len(breaches),
            )

        return breaches

    async def get_sla_dashboard(
        self,
        db: AsyncSession,
        company_id: UUID,
        period_days: int = 30,
    ) -> SLADashboard:
        """Liefert SLA-Dashboard-Daten.

        Args:
            db: Async Database Session
            company_id: ID der Firma
            period_days: Zeitraum in Tagen für die Berechnung

        Returns:
            SLADashboard mit allen Metriken
        """
        now = utc_now()
        period_start = now - timedelta(days=period_days)

        # Abgeschlossene Anfragen im Zeitraum
        resolved_stmt = select(ApprovalRequest).where(
            and_(
                ApprovalRequest.company_id == company_id,
                ApprovalRequest.resolved_at.isnot(None),
                ApprovalRequest.created_at >= period_start,
            )
        )
        resolved_result = await db.execute(resolved_stmt)
        resolved_requests = resolved_result.scalars().all()

        # Gesamtzahl im Zeitraum
        total_stmt = select(func.count(ApprovalRequest.id)).where(
            and_(
                ApprovalRequest.company_id == company_id,
                ApprovalRequest.created_at >= period_start,
            )
        )
        total_result = await db.execute(total_stmt)
        total_requests = total_result.scalar() or 0

        # Dauer-Berechnung
        durations_hours: List[float] = []
        sla_breaches = 0

        for request in resolved_requests:
            if request.created_at and request.resolved_at:
                duration = (
                    request.resolved_at - request.created_at
                ).total_seconds() / 3600.0
                durations_hours.append(duration)

                # SLA-Verletzung: über due_date
                if request.due_date and request.resolved_at > request.due_date:
                    sla_breaches += 1

        avg_hours = 0.0
        median_hours = 0.0
        if durations_hours:
            durations_hours.sort()
            avg_hours = sum(durations_hours) / len(durations_hours)
            median_idx = len(durations_hours) // 2
            median_hours = durations_hours[median_idx]

        # SLA-Compliance-Rate
        total_completed = len(resolved_requests)
        compliance_rate = 0.0
        if total_completed > 0:
            compliance_rate = (
                (total_completed - sla_breaches) / total_completed
            ) * 100.0

        # Überfällige
        overdue_stmt = select(func.count(ApprovalRequest.id)).where(
            and_(
                ApprovalRequest.company_id == company_id,
                ApprovalRequest.status == ApprovalStatus.PENDING,
                ApprovalRequest.due_date < now,
            )
        )
        overdue_result = await db.execute(overdue_stmt)
        overdue_count = overdue_result.scalar() or 0

        # Bottleneck-Analyse (Top 10 langsamste Genehmiger)
        bottleneck_users = await self._get_bottleneck_users(
            db, company_id, period_start
        )

        return SLADashboard(
            avg_approval_hours=round(avg_hours, 2),
            median_approval_hours=round(median_hours, 2),
            total_requests_period=total_requests,
            total_completed_period=total_completed,
            sla_compliance_rate=round(compliance_rate, 1),
            sla_breaches=sla_breaches,
            overdue_count=overdue_count,
            bottleneck_users=bottleneck_users,
        )

    async def get_bottleneck_analysis(
        self,
        db: AsyncSession,
        company_id: UUID,
        period_days: int = 30,
    ) -> List[Dict[str, object]]:
        """Detaillierte Bottleneck-Analyse: Wer ist der langsamste Genehmiger?

        Args:
            db: Async Database Session
            company_id: ID der Firma
            period_days: Zeitraum in Tagen

        Returns:
            Liste mit Bottleneck-Einträgen sortiert nach Verzögerung
        """
        now = utc_now()
        period_start = now - timedelta(days=period_days)

        return await self._get_bottleneck_users(db, company_id, period_start)

    # ========================================================================
    # Private Hilfsmethoden
    # ========================================================================

    async def _get_bottleneck_users(
        self,
        db: AsyncSession,
        company_id: UUID,
        since: datetime,
    ) -> List[Dict[str, object]]:
        """Berechnet Bottleneck-Statistiken pro Genehmiger."""
        now = utc_now()

        # Ausstehende Steps mit zugewiesenem User
        stmt = (
            select(
                ApprovalStep.assigned_user_id,
                func.count(ApprovalStep.id).label("pending_count"),
                func.min(ApprovalStep.created_at).label("oldest_step"),
            )
            .join(
                ApprovalRequest,
                ApprovalStep.approval_request_id == ApprovalRequest.id,
            )
            .where(
                and_(
                    ApprovalRequest.company_id == company_id,
                    ApprovalRequest.status == ApprovalStatus.PENDING,
                    ApprovalStep.status == ApprovalStatus.PENDING,
                    ApprovalStep.assigned_user_id.isnot(None),
                    ApprovalRequest.created_at >= since,
                )
            )
            .group_by(ApprovalStep.assigned_user_id)
            .order_by(func.count(ApprovalStep.id).desc())
            .limit(10)
        )

        result = await db.execute(stmt)
        rows = result.all()

        bottlenecks: List[Dict[str, object]] = []
        for row in rows:
            user_id, pending_count, oldest_step = row
            wait_hours = (
                (now - oldest_step).total_seconds() / 3600.0
                if oldest_step
                else 0.0
            )
            bottlenecks.append(
                {
                    "user_id": str(user_id),
                    "pending_count": pending_count,
                    "oldest_pending_hours": round(wait_hours, 1),
                }
            )

        return bottlenecks

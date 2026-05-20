# -*- coding: utf-8 -*-
"""
Celery Tasks für Approval Eskalation und Stellvertretung.

Feature #3: Approval Workflow Depth
- check_approval_timeouts_task: Stündlich überfällige Genehmigungen prüfen
- activate_substitutions_task: Täglich Stellvertretungen aktivieren/deaktivieren
- record_sla_metrics_task: SLA-Metrik für abgeschlossenen Schritt erfassen
- generate_sla_report_task: Wöchentlichen SLA-Report generieren
"""

from __future__ import annotations

import asyncio
import structlog
from typing import Dict, List, Optional
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.orm import joinedload

from app.core.datetime_utils import utc_now
from app.db.models import (
    ApprovalRequest,
    ApprovalStatus,
    ApprovalStep,
    Company,
)
from app.db.models_approval_extended import EscalationRule
from app.db.session import get_sync_session
from app.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


@celery_app.task(
    name="app.workers.tasks.approval_escalation_tasks.check_approval_timeouts_task",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def check_approval_timeouts_task(
    self,
    company_id: Optional[str] = None,
) -> Dict[str, object]:
    """Prüft überfällige Genehmigungen und eskaliert bei Bedarf.

    Wird stündlich via Celery Beat ausgeführt.
    Für jede überfällige Anfrage wird die passende Eskalationsregel
    gesucht und angewendet.

    Args:
        company_id: Optional: Nur für diese Firma

    Returns:
        Dict mit Statistiken
    """
    logger.info("Starte Überprüfung überfälliger Genehmigungen...")

    with get_sync_session() as db:
        now = utc_now()

        # Companies ermitteln
        if company_id:
            company_ids = [UUID(company_id)]
        else:
            company_result = db.execute(select(Company.id))
            company_ids = [row[0] for row in company_result.all()]

        total_checked = 0
        total_escalated = 0
        errors: List[str] = []

        for cid in company_ids:
            try:
                # Überfällige Anfragen finden
                overdue_stmt = (
                    select(ApprovalRequest)
                    .options(
                        joinedload(ApprovalRequest.approval_steps)
                    )
                    .where(
                        and_(
                            ApprovalRequest.company_id == cid,
                            ApprovalRequest.status == ApprovalStatus.PENDING,
                            ApprovalRequest.due_date < now,
                            ApprovalRequest.is_escalated.is_(False),
                        )
                    )
                )
                overdue_result = db.execute(overdue_stmt)
                overdue_requests = overdue_result.unique().scalars().all()
                total_checked += len(overdue_requests)

                if not overdue_requests:
                    continue

                # Eskalationsregeln laden
                rules_stmt = (
                    select(EscalationRule)
                    .where(
                        and_(
                            EscalationRule.company_id == cid,
                            EscalationRule.is_active.is_(True),
                        )
                    )
                    .order_by(EscalationRule.timeout_hours.asc())
                )
                rules_result = db.execute(rules_stmt)
                rules = rules_result.scalars().all()

                for request in overdue_requests:
                    # Passende Regel finden (erste die matcht)
                    wait_hours = (
                        (now - request.created_at).total_seconds() / 3600.0
                        if request.created_at
                        else 0.0
                    )

                    matching_rule = None
                    for rule in rules:
                        if wait_hours >= rule.timeout_hours:
                            matching_rule = rule

                    if matching_rule:
                        # Eskalieren
                        request.is_escalated = True
                        request.status = ApprovalStatus.ESCALATED
                        request.escalation_date = now

                        if matching_rule.escalation_target_user_id:
                            # Aktuellen Step zuweisen
                            current_step = next(
                                (
                                    s
                                    for s in request.approval_steps
                                    if s.step_number == request.current_step
                                ),
                                None,
                            )
                            if current_step:
                                current_step.assigned_user_id = (
                                    matching_rule.escalation_target_user_id
                                )
                                current_step.delegated_at = now
                                current_step.delegation_reason = (
                                    f"Automatische Eskalation nach "
                                    f"{matching_rule.timeout_hours}h"
                                )

                        total_escalated += 1
                        logger.info(
                            "Genehmigung eskaliert: %s (Regel: %s)",
                            str(request.id),
                            matching_rule.name,
                        )

                db.commit()

            except Exception as exc:
                db.rollback()
                error_msg = (
                    f"Fehler bei Eskalation für Company {cid}: {exc}"
                )
                errors.append(error_msg)
                logger.error(error_msg)

    result: Dict[str, object] = {
        "checked": total_checked,
        "escalated": total_escalated,
        "companies_processed": len(company_ids),
        "errors": errors,
    }

    logger.info(
        "Eskalation abgeschlossen: %d geprüft, %d eskaliert",
        total_checked,
        total_escalated,
    )

    return result


@celery_app.task(
    name="app.workers.tasks.approval_escalation_tasks.activate_substitutions_task",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def activate_substitutions_task(
    self,
    company_id: Optional[str] = None,
) -> Dict[str, object]:
    """Aktiviert und deaktiviert Stellvertretungen basierend auf Datum.

    Wird täglich via Celery Beat ausgeführt.
    - Aktiviert Stellvertretungen deren Zeitraum begonnen hat
    - Deaktiviert Stellvertretungen deren Zeitraum abgelaufen ist

    Args:
        company_id: Optional: Nur für diese Firma

    Returns:
        Dict mit Statistiken
    """
    logger.info("Starte Stellvertretungs-Aktualisierung...")

    async def _process() -> Dict[str, object]:
        from app.db.session import get_async_session_context
        from app.services.approval.escalation_service import (
            EscalationService,
        )

        total_activated = 0
        total_deactivated = 0
        errors: List[str] = []

        async with get_async_session_context() as db:
            # Companies ermitteln
            if company_id:
                company_ids = [UUID(company_id)]
            else:
                company_result = await db.execute(select(Company.id))
                company_ids = [row[0] for row in company_result.all()]

            for cid in company_ids:
                try:
                    service = EscalationService(db)

                    activated = await service.activate_substitutions(
                        db, cid
                    )
                    deactivated = (
                        await service.deactivate_expired_substitutions(
                            db, cid
                        )
                    )

                    total_activated += activated
                    total_deactivated += deactivated

                except Exception as exc:
                    error_msg = (
                        f"Fehler bei Stellvertretung für "
                        f"Company {cid}: {exc}"
                    )
                    errors.append(error_msg)
                    logger.error(error_msg)

        return {
            "activated": total_activated,
            "deactivated": total_deactivated,
            "companies_processed": len(company_ids),
            "errors": errors,
        }

    result = asyncio.run(_process())

    logger.info(
        "Stellvertretungen aktualisiert: %d aktiviert, %d deaktiviert",
        result.get("activated", 0),
        result.get("deactivated", 0),
    )

    return result


@celery_app.task(
    name="app.workers.tasks.approval_escalation_tasks.record_sla_metrics_task",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def record_sla_metrics_task(
    self,
    approval_request_id: str,
    step_id: str,
) -> Dict[str, object]:
    """Erfasst SLA-Metrik für einen abgeschlossenen Genehmigungsschritt.

    Wird ausgeloest wenn ein ApprovalStep abgeschlossen wird.

    Args:
        approval_request_id: ID der Genehmigungsanfrage
        step_id: ID des abgeschlossenen Schritts

    Returns:
        Dict mit SLA-Metrik-Details
    """
    logger.info(
        "Erfasse SLA-Metrik: request=%s, step=%s",
        approval_request_id,
        step_id,
    )

    async def _record() -> Dict[str, object]:
        from app.db.session import get_async_session_context
        from app.services.approval.sla_monitoring_service import (
            SLAMonitoringService,
        )

        async with get_async_session_context() as db:
            # Step laden
            step_stmt = select(ApprovalStep).where(
                ApprovalStep.id == UUID(step_id)
            )
            step_result = await db.execute(step_stmt)
            step = step_result.scalar_one_or_none()

            if not step:
                return {
                    "recorded": False,
                    "error": f"Step {step_id} nicht gefunden",
                }

            service = SLAMonitoringService(db)
            metric = await service.record_sla_metric(
                db,
                UUID(approval_request_id),
                step,
            )

            await db.commit()

            return {
                "recorded": True,
                "metric_id": str(metric.id),
                "is_breached": metric.is_breached,
                "sla_target_hours": metric.sla_target_hours,
            }

    result = asyncio.run(_record())

    if result.get("is_breached"):
        logger.warning(
            "SLA-Verletzung erkannt: request=%s, step=%s",
            approval_request_id,
            step_id,
        )

    return result


@celery_app.task(
    name="app.workers.tasks.approval_escalation_tasks.generate_sla_report_task",
    bind=True,
    max_retries=3,
    default_retry_delay=120,
)
def generate_sla_report_task(
    self,
    company_id: Optional[str] = None,
    period_days: int = 7,
) -> Dict[str, object]:
    """Generiert wöchentlichen SLA-Report.

    Wird wöchentlich via Celery Beat ausgeführt.
    Erstellt Dashboard-Daten und Bottleneck-Analyse.

    Args:
        company_id: Optional: Nur für diese Firma
        period_days: Zeitraum in Tagen (Default: 7 für wöchentlich)

    Returns:
        Dict mit SLA-Report-Daten
    """
    logger.info(
        "Generiere SLA-Report (Zeitraum: %d Tage)...", period_days
    )

    async def _generate() -> Dict[str, object]:
        from app.db.session import get_async_session_context
        from app.services.approval.sla_monitoring_service import (
            SLAMonitoringService,
        )

        reports: List[Dict[str, object]] = []

        async with get_async_session_context() as db:
            # Companies ermitteln
            if company_id:
                company_ids = [UUID(company_id)]
            else:
                company_result = await db.execute(select(Company.id))
                company_ids = [row[0] for row in company_result.all()]

            for cid in company_ids:
                try:
                    service = SLAMonitoringService(db)

                    dashboard = await service.get_sla_dashboard(
                        db, cid, period_days
                    )
                    bottlenecks = await service.get_bottleneck_analysis(
                        db, cid, period_days
                    )

                    report: Dict[str, object] = {
                        "company_id": str(cid),
                        "period_days": period_days,
                        "avg_approval_hours": dashboard.avg_approval_hours,
                        "median_approval_hours": (
                            dashboard.median_approval_hours
                        ),
                        "total_requests": dashboard.total_requests_period,
                        "total_completed": (
                            dashboard.total_completed_period
                        ),
                        "sla_compliance_rate": (
                            dashboard.sla_compliance_rate
                        ),
                        "sla_breaches": dashboard.sla_breaches,
                        "overdue_count": dashboard.overdue_count,
                        "top_bottlenecks": bottlenecks[:5],
                    }

                    reports.append(report)

                except Exception as exc:
                    logger.error(
                        "Fehler bei SLA-Report für Company %s: %s",
                        str(cid),
                        str(exc),
                    )

        return {
            "reports_generated": len(reports),
            "companies_processed": len(company_ids),
            "reports": reports,
        }

    result = asyncio.run(_generate())

    logger.info(
        "SLA-Report generiert: %d Reports",
        result.get("reports_generated", 0),
    )

    return result

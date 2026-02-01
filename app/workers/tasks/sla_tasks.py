# -*- coding: utf-8 -*-
"""Celery Tasks fuer SLA Monitoring.

4 Tasks:
- sla.check_all: Prueft alle aktiven Workflows auf SLA-Status (alle 15 Min)
- sla.send_warning: Sendet SLA-Warnung an zustaendige User
- sla.escalate: Eskaliert ueberfaellige Workflows
- sla.generate_report: Generiert taeglichen SLA-Report

Celery Beat Integration:
- sla.check_all: Alle 15 Minuten
- sla.generate_report: Taeglich 07:00

Migration: 150_add_workflow_sla_monitoring.py
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

import structlog
from celery import shared_task

from app.core.datetime_utils import utc_now
from app.core.safe_errors import safe_error_log
from app.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


# =============================================================================
# SLA Check Task
# =============================================================================

@shared_task(
    bind=True,
    name="sla.check_all",
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
)
def check_all_slas(
    self,
    company_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Prueft SLA-Status aller aktiven Workflows.

    Wird alle 15 Minuten von Celery Beat aufgerufen.
    Sendet automatisch Alerts bei Ueberschreitung von Schwellwerten.

    Args:
        company_id: Optional: Nur fuer diese Firma pruefen

    Returns:
        Statistiken der Pruefung
    """
    from app.db.session import async_session_factory
    from app.services.bpmn.sla_service import get_sla_service

    logger.info(
        "sla_check_started",
        company_id=company_id or "all",
    )

    async def _check() -> Dict[str, Any]:
        async with async_session_factory() as db:
            sla_service = get_sla_service(db)

            try:
                stats = await sla_service.check_all_slas(
                    company_id=UUID(company_id) if company_id else None,
                )

                await db.commit()

                return {
                    "success": True,
                    **stats,
                    "timestamp": utc_now().isoformat(),
                }

            except Exception as e:
                logger.exception(
                    "sla_check_failed",
                    **safe_error_log(e),
                )
                await db.rollback()
                return {
                    "success": False,
                    "error": str(e),
                    "timestamp": utc_now().isoformat(),
                }

    return asyncio.run(_check())


# =============================================================================
# SLA Warning Task
# =============================================================================

@shared_task(
    bind=True,
    name="sla.send_warning",
    max_retries=3,
    default_retry_delay=30,
    acks_late=True,
)
def send_sla_warning(
    self,
    instance_id: str,
    company_id: str,
    warning_level: str,  # info_50, warning_75, high_90
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Sendet SLA-Warnung an zustaendige Benutzer.

    Args:
        instance_id: Workflow-Instanz-ID
        company_id: Mandant-ID
        warning_level: Warnstufe
        metadata: Zusaetzliche Metadaten

    Returns:
        Ergebnis des Versands
    """
    from app.db.session import async_session_factory
    from app.services.bpmn.sla_service import get_sla_service
    from app.services.notification_service import (
        NotificationService,
        get_notification_service,
        NotificationType,
        NotificationPriority,
    )

    logger.info(
        "sla_warning_sending",
        instance_id=instance_id,
        warning_level=warning_level,
    )

    async def _send() -> Dict[str, Any]:
        async with async_session_factory() as db:
            sla_service = get_sla_service(db)

            try:
                # SLA-Status holen
                status = await sla_service.check_sla_status(
                    workflow_instance_id=UUID(instance_id),
                    company_id=UUID(company_id),
                )

                if not status.get("has_sla"):
                    return {
                        "success": False,
                        "reason": "Keine SLA-Konfiguration",
                    }

                # Notification senden
                notification_service = get_notification_service()

                # Prioritaet basierend auf Level
                priority_map = {
                    "info_50": NotificationPriority.NORMAL,
                    "warning_75": NotificationPriority.HIGH,
                    "high_90": NotificationPriority.CRITICAL,
                    "critical_100": NotificationPriority.CRITICAL,
                }

                title = f"SLA-Warnung: Workflow {status.get('elapsed_percent', 0):.0f}% der Zeit verbraucht"
                message = (
                    f"Der Workflow hat {status.get('elapsed_hours', 0):.1f} von "
                    f"{status.get('max_duration_hours', 0)} Stunden verbraucht. "
                    f"Verbleibend: {status.get('remaining_hours', 0):.1f} Stunden."
                )

                # In-App Notification (wenn Assignee bekannt)
                if metadata and metadata.get("assignee_id"):
                    await notification_service.send_in_app_notification(
                        user_id=metadata["assignee_id"],
                        title=title,
                        message=message,
                        priority=priority_map.get(warning_level, NotificationPriority.HIGH),
                        notification_type=NotificationType.WORKFLOW_NOTIFICATION,
                        metadata={
                            "instance_id": instance_id,
                            "warning_level": warning_level,
                            "deadline": status.get("deadline"),
                        },
                    )

                return {
                    "success": True,
                    "warning_level": warning_level,
                    "notification_sent": True,
                }

            except Exception as e:
                logger.exception(
                    "sla_warning_failed",
                    instance_id=instance_id,
                    **safe_error_log(e),
                )
                return {
                    "success": False,
                    "error": str(e),
                }

    return asyncio.run(_send())


# =============================================================================
# SLA Escalation Task
# =============================================================================

@shared_task(
    bind=True,
    name="sla.escalate",
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
)
def escalate_overdue_workflows(
    self,
    company_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Eskaliert ueberfaellige Workflows.

    Findet alle Workflows mit SLA-Verletzung und eskaliert sie
    an die definierten Eskalationsempfaenger.

    Args:
        company_id: Optional: Nur fuer diese Firma

    Returns:
        Eskalationsstatistiken
    """
    from app.db.session import async_session_factory
    from app.services.bpmn.sla_service import get_sla_service, SLAStatus
    from app.db.bpmn_models.bpmn import ProcessInstance, ProcessStatus

    logger.info(
        "sla_escalation_started",
        company_id=company_id or "all",
    )

    async def _escalate() -> Dict[str, Any]:
        async with async_session_factory() as db:
            sla_service = get_sla_service(db)

            try:
                from sqlalchemy import select, and_

                # Laufende Instanzen finden
                conditions = [ProcessInstance.status == ProcessStatus.RUNNING]
                if company_id:
                    conditions.append(ProcessInstance.company_id == UUID(company_id))

                query = select(ProcessInstance).where(and_(*conditions))
                result = await db.execute(query)
                instances = list(result.scalars().all())

                escalated = 0
                already_escalated = 0
                no_sla = 0

                for instance in instances:
                    sla_data = (instance.variables or {}).get("_sla")
                    if not sla_data:
                        no_sla += 1
                        continue

                    # Status pruefen
                    status = await sla_service.check_sla_status(
                        instance.id,
                        instance.company_id,
                    )

                    if status.get("status") == SLAStatus.BREACHED.value:
                        # Pruefen ob bereits eskaliert
                        alerts_sent = sla_data.get("alerts_sent", [])
                        if "critical_100" in alerts_sent:
                            already_escalated += 1
                            continue

                        # Eskalieren via check_all_slas (sendet Alerts)
                        await sla_service.check_all_slas(instance.company_id)
                        escalated += 1

                await db.commit()

                logger.info(
                    "sla_escalation_completed",
                    escalated=escalated,
                    already_escalated=already_escalated,
                    no_sla=no_sla,
                )

                return {
                    "success": True,
                    "escalated": escalated,
                    "already_escalated": already_escalated,
                    "no_sla_config": no_sla,
                    "total_checked": len(instances),
                    "timestamp": utc_now().isoformat(),
                }

            except Exception as e:
                logger.exception(
                    "sla_escalation_failed",
                    **safe_error_log(e),
                )
                await db.rollback()
                return {
                    "success": False,
                    "error": str(e),
                }

    return asyncio.run(_escalate())


# =============================================================================
# SLA Report Generation Task
# =============================================================================

@shared_task(
    bind=True,
    name="sla.generate_report",
    max_retries=3,
    default_retry_delay=300,
    acks_late=True,
)
def generate_sla_report(
    self,
    company_id: Optional[str] = None,
    time_range_days: int = 7,
    send_email: bool = True,
) -> Dict[str, Any]:
    """Generiert SLA-Report.

    Erstellt einen zusammenfassenden Bericht ueber SLA-Performance
    und sendet diesen optional per Email an Administratoren.

    Args:
        company_id: Optional: Nur fuer diese Firma
        time_range_days: Zeitraum fuer den Report
        send_email: Email an Admins senden

    Returns:
        Report-Daten
    """
    from app.db.session import async_session_factory
    from app.services.bpmn.sla_service import get_sla_service
    from app.services.bpmn.workflow_analytics_service import get_workflow_analytics_service
    from app.db.models import Company

    logger.info(
        "sla_report_generation_started",
        company_id=company_id or "all",
        time_range_days=time_range_days,
    )

    async def _generate() -> Dict[str, Any]:
        async with async_session_factory() as db:
            sla_service = get_sla_service(db)
            analytics_service = get_workflow_analytics_service(db)

            try:
                from sqlalchemy import select

                # Companies ermitteln
                if company_id:
                    companies = [UUID(company_id)]
                else:
                    result = await db.execute(
                        select(Company.id).where(Company.is_active == True)
                    )
                    companies = [row[0] for row in result.all()]

                reports = {}

                for comp_id in companies:
                    # SLA-Metriken
                    sla_metrics = await sla_service.calculate_sla_metrics(
                        comp_id,
                        time_range_days,
                    )

                    # Breaches
                    breaches = await sla_service.get_sla_breaches(
                        comp_id,
                        time_range_days,
                        limit=10,
                    )

                    # Analytics
                    throughput = await analytics_service.get_throughput_metrics(
                        comp_id,
                        time_range_days,
                    )

                    reports[str(comp_id)] = {
                        "sla_compliance_rate": sla_metrics["compliance_rate"],
                        "total_workflows": sla_metrics["total_workflows"],
                        "on_time": sla_metrics["on_time"],
                        "breached": sla_metrics["breached"],
                        "avg_duration_hours": sla_metrics["avg_duration_hours"],
                        "recent_breaches": len(breaches),
                        "throughput_summary": throughput["summary"],
                    }

                    # Optional: Email an Company-Admins senden
                    if send_email:
                        await _send_report_email(db, comp_id, reports[str(comp_id)])

                logger.info(
                    "sla_report_generation_completed",
                    companies_processed=len(companies),
                )

                return {
                    "success": True,
                    "time_range_days": time_range_days,
                    "companies_processed": len(companies),
                    "reports": reports,
                    "generated_at": utc_now().isoformat(),
                }

            except Exception as e:
                logger.exception(
                    "sla_report_generation_failed",
                    **safe_error_log(e),
                )
                return {
                    "success": False,
                    "error": str(e),
                }

    return asyncio.run(_generate())


async def _send_report_email(
    db,
    company_id: UUID,
    report_data: Dict[str, Any],
) -> None:
    """Sendet SLA-Report per Email an Company-Admins."""
    from sqlalchemy import select, and_
    from app.db.models import User, UserCompany
    from app.services.notification_service import get_notification_service

    try:
        # Company-Admins finden
        admin_query = (
            select(User)
            .join(UserCompany, User.id == UserCompany.user_id)
            .where(
                and_(
                    UserCompany.company_id == company_id,
                    UserCompany.role.in_(["admin", "owner"]),
                    User.is_active == True,
                )
            )
        )
        result = await db.execute(admin_query)
        admins = list(result.scalars().all())

        if not admins:
            return

        notification_service = get_notification_service()

        subject = f"SLA-Report: {report_data['sla_compliance_rate']:.1f}% Compliance"

        body = f"""
SLA-Performance-Report
=====================

Zeitraum: Letzte 7 Tage

Zusammenfassung:
- Compliance-Rate: {report_data['sla_compliance_rate']:.1f}%
- Gesamt-Workflows: {report_data['total_workflows']}
- Termingerecht: {report_data['on_time']}
- SLA-Verletzungen: {report_data['breached']}
- Durchschnittliche Dauer: {report_data['avg_duration_hours']:.1f} Stunden

Aktuelle SLA-Verletzungen: {report_data['recent_breaches']}

---
Ablage-System SLA Monitoring
        """.strip()

        for admin in admins:
            if admin.email:
                try:
                    await notification_service.email.send(
                        to_email=admin.email,
                        subject=subject,
                        body=body,
                    )
                except Exception as e:
                    logger.warning(
                        "sla_report_email_failed",
                        admin_id=str(admin.id),
                        error=str(e),
                    )

    except Exception as e:
        logger.warning(
            "sla_report_email_sending_failed",
            company_id=str(company_id),
            error=str(e),
        )


# =============================================================================
# Celery Beat Schedule (wird in celery_config registriert)
# =============================================================================

SLA_BEAT_SCHEDULE = {
    "sla-check-all-15min": {
        "task": "sla.check_all",
        "schedule": 900.0,  # Alle 15 Minuten
        "options": {"queue": "metadata"},
    },
    "sla-generate-report-daily": {
        "task": "sla.generate_report",
        "schedule": {
            "hour": 7,
            "minute": 0,
        },
        "options": {"queue": "maintenance"},
    },
}

"""Celery Tasks fuer das Approval System.

Enterprise Feature: Automatisierte Genehmigungsworkflows mit:
- Eskalation bei Timeout
- Erinnerungen an Genehmiger
- Statistik-Generierung
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from app.core.datetime_utils import utc_now
from typing import Any, Optional
from uuid import UUID

from celery import shared_task
from sqlalchemy import and_, select

from app.workers.celery_app import celery_app
from app.db.session import get_sync_session
from app.db.models import (
    ApprovalRequest,
    ApprovalStatus,
    ApprovalStep,
    Company,
)

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.workers.tasks.approval_tasks.escalate_overdue_approvals",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def escalate_overdue_approvals(
    self,
    company_id: Optional[str] = None,
) -> dict[str, Any]:
    """Eskaliert ueberfaellige Genehmigungsanfragen.

    Wird regelmaessig via Celery Beat ausgefuehrt um alle Anfragen
    zu finden, die ihr Faelligkeitsdatum ueberschritten haben.

    Args:
        company_id: Optional: Nur fuer diese Firma

    Returns:
        Dict mit Statistiken
    """
    logger.info("Starte Eskalation ueberfaelliger Genehmigungen...")

    with get_sync_session() as db:
        now = utc_now()

        query = select(ApprovalRequest).where(
            and_(
                ApprovalRequest.status == ApprovalStatus.PENDING,
                ApprovalRequest.due_date < now,
                ApprovalRequest.is_escalated.is_(False),
            )
        )

        if company_id:
            query = query.where(ApprovalRequest.company_id == UUID(company_id))

        result = db.execute(query)
        overdue_requests = result.scalars().all()

        escalated_count = 0
        for request in overdue_requests:
            request.is_escalated = True
            request.status = ApprovalStatus.ESCALATED
            request.escalation_date = now
            escalated_count += 1

            logger.warning(
                f"Genehmigungsanfrage {request.id} eskaliert - "
                f"Faellig seit {request.due_date}"
            )

            # TODO: Benachrichtigung an Eskalationsempfaenger senden

        db.commit()

    logger.info(f"Eskalation abgeschlossen: {escalated_count} Anfragen eskaliert")

    return {
        "success": True,
        "escalated_count": escalated_count,
        "timestamp": now.isoformat(),
    }


@celery_app.task(
    name="app.workers.tasks.approval_tasks.send_approval_reminders",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def send_approval_reminders(
    self,
    hours_before_due: int = 24,
) -> dict[str, Any]:
    """Sendet Erinnerungen fuer bald faellige Genehmigungen.

    Args:
        hours_before_due: Stunden vor Faelligkeit fuer Erinnerung

    Returns:
        Dict mit Statistiken
    """
    logger.info(f"Starte Erinnerungs-Versand ({hours_before_due}h vor Faelligkeit)...")

    with get_sync_session() as db:
        now = utc_now()
        reminder_threshold = now + timedelta(hours=hours_before_due)

        # Finde bald faellige Steps
        query = (
            select(ApprovalStep)
            .join(ApprovalRequest)
            .where(
                and_(
                    ApprovalRequest.status == ApprovalStatus.PENDING,
                    ApprovalRequest.due_date <= reminder_threshold,
                    ApprovalRequest.due_date > now,
                    ApprovalStep.status == ApprovalStatus.PENDING,
                    ApprovalStep.assigned_user_id.isnot(None),
                )
            )
        )

        result = db.execute(query)
        pending_steps = result.scalars().all()

        reminders_sent = 0
        for step in pending_steps:
            # Nur wenn noch keine Erinnerung heute gesendet wurde
            if step.last_reminder_at:
                if (now - step.last_reminder_at).total_seconds() < 86400:  # 24h
                    continue

            # Erinnerung senden
            # TODO: Notification Service aufrufen
            step.reminder_sent_count += 1
            step.last_reminder_at = now
            reminders_sent += 1

            logger.info(
                f"Erinnerung gesendet fuer Approval-Schritt {step.id} "
                f"an User {step.assigned_user_id}"
            )

        db.commit()

    logger.info(f"Erinnerungs-Versand abgeschlossen: {reminders_sent} Erinnerungen")

    return {
        "success": True,
        "reminders_sent": reminders_sent,
        "timestamp": now.isoformat(),
    }


@celery_app.task(
    name="app.workers.tasks.approval_tasks.generate_approval_stats",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def generate_approval_stats(
    self,
    company_id: Optional[str] = None,
) -> dict[str, Any]:
    """Generiert Statistiken fuer das Approval Dashboard.

    Args:
        company_id: Optional: Nur fuer diese Firma

    Returns:
        Dict mit Statistiken
    """
    logger.info("Generiere Approval-Statistiken...")

    from sqlalchemy import func

    with get_sync_session() as db:
        # Basis-Query
        base_query = select(ApprovalRequest)

        if company_id:
            base_query = base_query.where(ApprovalRequest.company_id == UUID(company_id))
            companies = [UUID(company_id)]
        else:
            # Alle Companies
            result = db.execute(select(Company.id))
            companies = [row[0] for row in result.all()]

        stats_by_company = {}

        for comp_id in companies:
            # Status-Verteilung
            result = db.execute(
                select(
                    ApprovalRequest.status,
                    func.count(ApprovalRequest.id)
                )
                .where(ApprovalRequest.company_id == comp_id)
                .group_by(ApprovalRequest.status)
            )
            status_distribution = {row[0].value: row[1] for row in result.all()}

            # Durchschnittliche Bearbeitungszeit
            result = db.execute(
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
                        ApprovalRequest.company_id == comp_id,
                        ApprovalRequest.resolved_at.isnot(None),
                    )
                )
            )
            avg_hours = result.scalar() or 0

            # Ueberfaellige
            now = utc_now()
            result = db.execute(
                select(func.count(ApprovalRequest.id))
                .where(
                    and_(
                        ApprovalRequest.company_id == comp_id,
                        ApprovalRequest.status == ApprovalStatus.PENDING,
                        ApprovalRequest.due_date < now,
                    )
                )
            )
            overdue_count = result.scalar() or 0

            stats_by_company[str(comp_id)] = {
                "status_distribution": status_distribution,
                "avg_resolution_hours": float(avg_hours),
                "overdue_count": overdue_count,
                "total_requests": sum(status_distribution.values()),
            }

    logger.info(f"Approval-Statistiken generiert fuer {len(stats_by_company)} Companies")

    return {
        "success": True,
        "stats_by_company": stats_by_company,
        "generated_at": utc_now().isoformat(),
    }


@celery_app.task(
    name="app.workers.tasks.approval_tasks.expire_old_approvals",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def expire_old_approvals(
    self,
    days_to_expire: int = 30,
) -> dict[str, Any]:
    """Markiert sehr alte ausstehende Genehmigungen als abgelaufen.

    Args:
        days_to_expire: Tage nach denen eine Anfrage ablaeuft

    Returns:
        Dict mit Statistiken
    """
    logger.info(f"Pruefe Genehmigungen aelter als {days_to_expire} Tage...")

    with get_sync_session() as db:
        now = utc_now()
        expiry_threshold = now - timedelta(days=days_to_expire)

        query = select(ApprovalRequest).where(
            and_(
                ApprovalRequest.status.in_([
                    ApprovalStatus.PENDING,
                    ApprovalStatus.ESCALATED,
                ]),
                ApprovalRequest.created_at < expiry_threshold,
            )
        )

        result = db.execute(query)
        old_requests = result.scalars().all()

        expired_count = 0
        for request in old_requests:
            request.status = ApprovalStatus.EXPIRED
            request.resolved_at = now
            request.resolution_notes = f"Automatisch abgelaufen nach {days_to_expire} Tagen"
            expired_count += 1

            logger.info(
                f"Genehmigungsanfrage {request.id} abgelaufen - "
                f"Erstellt am {request.created_at}"
            )

        db.commit()

    logger.info(f"Ablauf-Pruefung abgeschlossen: {expired_count} Anfragen abgelaufen")

    return {
        "success": True,
        "expired_count": expired_count,
        "days_threshold": days_to_expire,
        "timestamp": now.isoformat(),
    }


@celery_app.task(
    name="app.workers.tasks.approval_tasks.process_approval_action",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def process_approval_action(
    self,
    request_id: str,
    user_id: str,
    action: str,  # "approve", "reject", "delegate"
    notes: Optional[str] = None,
    delegate_to_id: Optional[str] = None,
) -> dict[str, Any]:
    """Verarbeitet eine Genehmigungsaktion asynchron.

    Args:
        request_id: ID der Anfrage
        user_id: ID des handelnden Users
        action: Aktion (approve/reject/delegate)
        notes: Optionale Notizen
        delegate_to_id: ID des Delegationsempfaengers

    Returns:
        Dict mit Ergebnis
    """
    import asyncio
    from app.db.session import get_async_session
    from app.services.approval.approval_service import ApprovalService

    logger.info(
        f"Verarbeite Approval-Aktion: {action} fuer Anfrage {request_id} "
        f"von User {user_id}"
    )

    async def _process():
        async with get_async_session() as db:
            service = ApprovalService(db)

            if action == "approve":
                result = await service.approve(
                    request_id=UUID(request_id),
                    user_id=UUID(user_id),
                    notes=notes,
                )
            elif action == "reject":
                if not notes:
                    return {"success": False, "error": "Begruendung erforderlich"}
                result = await service.reject(
                    request_id=UUID(request_id),
                    user_id=UUID(user_id),
                    notes=notes,
                )
            elif action == "delegate":
                if not delegate_to_id:
                    return {"success": False, "error": "Delegationsempfaenger erforderlich"}
                result = await service.delegate(
                    request_id=UUID(request_id),
                    user_id=UUID(user_id),
                    delegate_to_id=UUID(delegate_to_id),
                    reason=notes or "Delegation ohne Begruendung",
                )
            else:
                return {"success": False, "error": f"Unbekannte Aktion: {action}"}

            return {
                "success": result.success,
                "status": result.request_status.value,
                "next_step": result.next_step,
                "message": result.message,
            }

    # Async ausfuehren
    result = asyncio.run(_process())

    logger.info(f"Approval-Aktion abgeschlossen: {result}")

    return result

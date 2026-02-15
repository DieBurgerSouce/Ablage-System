# -*- coding: utf-8 -*-
"""
Approval Enhanced + Automation 2.0 Celery Tasks.

Feature #3: Approval Workflow Depth
- check_approval_timeouts_task: Ueberfaellige Genehmigungen erkennen + eskalieren
- calculate_approval_sla_task: SLA-Metriken berechnen (taeglich)
- activate_substitutions_task: Stellvertretungen aktivieren/deaktivieren

Feature #7: Automation 2.0
- run_auto_matching_task: Auto-Matching fuer einzelnes Dokument
- run_batch_auto_matching_task: Batch-Matching fuer alle ungematchten Dokumente
- run_auto_filing_task: Auto-Filing fuer einzelnes Dokument

Feinpoliert und durchdacht - Enterprise Workflow Automation.
"""

import asyncio
import structlog
from typing import Dict, List, Optional
from uuid import UUID

from app.workers.celery_app import celery_app
from app.db.session import get_async_session_context
from app.core.safe_errors import safe_error_log, safe_error_detail

logger = structlog.get_logger(__name__)


# =============================================================================
# Feature #3: Approval Workflow Depth Tasks
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.approval_enhanced_tasks.check_approval_timeouts_task",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
    queue="maintenance",
)
def check_approval_timeouts_task(
    self,
    company_id: Optional[str] = None,
) -> Dict[str, object]:
    """Prueft ueberfaellige Genehmigungen und eskaliert automatisch.

    Wird stuendlich per Celery Beat ausgefuehrt.
    Findet alle pending Requests mit ueberschrittenem due_date
    und wendet passende Eskalationsregeln an.

    Args:
        company_id: Optionale Company-ID (sonst alle Companies)

    Returns:
        Dict mit Verarbeitungsstatistiken
    """
    from app.services.approval.escalation_service import EscalationService
    from app.db.models import Company
    from sqlalchemy import select

    async def _check_timeouts() -> Dict[str, object]:
        async with get_async_session_context() as db:
            escalation_service = EscalationService(db)

            companies_to_check: List[UUID] = []

            if company_id:
                companies_to_check.append(UUID(company_id))
            else:
                # Alle aktiven Companies laden
                stmt = select(Company.id).where(Company.is_active.is_(True))
                result = await db.execute(stmt)
                companies_to_check = [row[0] for row in result.all()]

            total_overdue = 0
            total_escalated = 0
            total_substitutions_activated = 0
            total_substitutions_deactivated = 0
            errors = 0

            for cid in companies_to_check:
                try:
                    # 1. Stellvertretungen aktivieren/deaktivieren
                    activated = await escalation_service.activate_substitutions(
                        db, cid
                    )
                    deactivated = await escalation_service.deactivate_expired_substitutions(
                        db, cid
                    )
                    total_substitutions_activated += activated
                    total_substitutions_deactivated += deactivated

                    # 2. Ueberfaellige Genehmigungen finden
                    overdue = await escalation_service.check_overdue_approvals(
                        db, cid
                    )
                    total_overdue += len(overdue)

                    # 3. Eskalationsregeln laden und anwenden
                    rules = await escalation_service.get_escalation_rules(
                        cid, active_only=True
                    )

                    for request in overdue:
                        for rule in rules:
                            result = await escalation_service.escalate_approval(
                                db, request.id, rule
                            )
                            if result.escalated:
                                total_escalated += 1
                                break  # Nur erste passende Regel anwenden

                except Exception as exc:
                    errors += 1
                    logger.warning(
                        "timeout_check_company_error",
                        company_id=str(cid),
                        **safe_error_log(exc),
                    )

            logger.info(
                "approval_timeouts_checked",
                companies=len(companies_to_check),
                overdue=total_overdue,
                escalated=total_escalated,
                substitutions_activated=total_substitutions_activated,
                substitutions_deactivated=total_substitutions_deactivated,
                errors=errors,
            )

            return {
                "companies_checked": len(companies_to_check),
                "overdue_found": total_overdue,
                "escalated": total_escalated,
                "substitutions_activated": total_substitutions_activated,
                "substitutions_deactivated": total_substitutions_deactivated,
                "errors": errors,
            }

    try:
        return asyncio.run(_check_timeouts())
    except Exception as exc:
        logger.error(
            "check_approval_timeouts_failed",
            **safe_error_log(exc),
        )
        raise self.retry(exc=exc)


@celery_app.task(
    name="app.workers.tasks.approval_enhanced_tasks.calculate_approval_sla_task",
    bind=True,
    max_retries=2,
    default_retry_delay=600,
    queue="maintenance",
)
def calculate_approval_sla_task(
    self,
    company_id: Optional[str] = None,
    period_days: int = 30,
) -> Dict[str, object]:
    """Berechnet SLA-Metriken fuer abgeschlossene Genehmigungsschritte.

    Wird taeglich um 03:00 Uhr per Celery Beat ausgefuehrt.
    Erfasst Metriken fuer Schritte die in den letzten 24h abgeschlossen wurden.

    Args:
        company_id: Optionale Company-ID (sonst alle Companies)
        period_days: Zeitraum fuer Dashboard-Berechnung

    Returns:
        Dict mit SLA-Statistiken
    """
    from app.services.approval.sla_monitoring_service import SLAMonitoringService
    from app.db.models import (
        ApprovalRequest,
        ApprovalStatus,
        ApprovalStep,
        Company,
    )
    from app.core.datetime_utils import utc_now
    from datetime import timedelta
    from sqlalchemy import select, and_

    async def _calculate_sla() -> Dict[str, object]:
        async with get_async_session_context() as db:
            sla_service = SLAMonitoringService(db)
            now = utc_now()
            since = now - timedelta(hours=25)  # Etwas mehr als 24h fuer Overlap

            companies_to_check: List[UUID] = []

            if company_id:
                companies_to_check.append(UUID(company_id))
            else:
                stmt = select(Company.id).where(Company.is_active.is_(True))
                result = await db.execute(stmt)
                companies_to_check = [row[0] for row in result.all()]

            total_metrics = 0
            total_breaches = 0
            errors = 0

            for cid in companies_to_check:
                try:
                    # Kuerzlich abgeschlossene Steps finden
                    stmt = (
                        select(ApprovalStep)
                        .join(
                            ApprovalRequest,
                            ApprovalStep.approval_request_id == ApprovalRequest.id,
                        )
                        .where(
                            and_(
                                ApprovalRequest.company_id == cid,
                                ApprovalStep.status.in_([
                                    ApprovalStatus.APPROVED,
                                    ApprovalStatus.REJECTED,
                                ]),
                                ApprovalStep.decision_date >= since,
                            )
                        )
                    )
                    result = await db.execute(stmt)
                    completed_steps = result.scalars().all()

                    for step in completed_steps:
                        try:
                            metric = await sla_service.record_sla_metric(
                                db, step.approval_request_id, step
                            )
                            total_metrics += 1
                            if metric.is_breached:
                                total_breaches += 1
                        except ValueError:
                            # Request nicht gefunden - ueberspringe
                            pass

                    await db.commit()

                except Exception as exc:
                    errors += 1
                    logger.warning(
                        "sla_calculation_company_error",
                        company_id=str(cid),
                        **safe_error_log(exc),
                    )

            logger.info(
                "approval_sla_calculated",
                companies=len(companies_to_check),
                metrics_recorded=total_metrics,
                breaches=total_breaches,
                errors=errors,
            )

            return {
                "companies_checked": len(companies_to_check),
                "metrics_recorded": total_metrics,
                "breaches_found": total_breaches,
                "errors": errors,
            }

    try:
        return asyncio.run(_calculate_sla())
    except Exception as exc:
        logger.error(
            "calculate_approval_sla_failed",
            **safe_error_log(exc),
        )
        raise self.retry(exc=exc)


# =============================================================================
# Feature #7: Automation 2.0 Tasks
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.approval_enhanced_tasks.run_auto_matching_task",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
    queue="default",
)
def run_auto_matching_task(
    self,
    company_id: str,
    document_id: str,
) -> Dict[str, object]:
    """Auto-Matching fuer ein einzelnes Dokument ausfuehren.

    Wird nach OCR-Abschluss oder Dokument-Upload getriggert.
    Sucht passende Dokumente (Bestellung <-> Lieferschein <-> Rechnung).

    Args:
        company_id: Company-ID
        document_id: Dokument-ID

    Returns:
        Dict mit Matching-Ergebnissen
    """
    from app.services.auto_matching_service import AutoMatchingService

    async def _run_matching() -> Dict[str, object]:
        async with get_async_session_context() as db:
            service = AutoMatchingService(db)
            cid = UUID(company_id)
            did = UUID(document_id)

            matches = await service.find_matches(db, cid, did)

            await db.commit()

            return {
                "document_id": document_id,
                "matches_found": len(matches),
                "match_ids": [str(m.id) for m in matches],
                "confidences": [
                    round(m.confidence, 3) for m in matches
                ],
            }

    try:
        return asyncio.run(_run_matching())
    except Exception as exc:
        logger.error(
            "auto_matching_failed",
            document_id=document_id,
            **safe_error_log(exc),
        )
        raise self.retry(exc=exc)


@celery_app.task(
    name="app.workers.tasks.approval_enhanced_tasks.run_batch_auto_matching_task",
    bind=True,
    max_retries=1,
    default_retry_delay=600,
    queue="maintenance",
)
def run_batch_auto_matching_task(
    self,
    company_id: Optional[str] = None,
    limit: int = 500,
) -> Dict[str, object]:
    """Batch-Matching fuer alle ungematchten Dokumente.

    Wird naechtlich per Celery Beat ausgefuehrt.
    Verarbeitet alle Dokumente ohne bestehendes Matching.

    Args:
        company_id: Optionale Company-ID (sonst alle Companies)
        limit: Maximale Anzahl Dokumente pro Company

    Returns:
        Dict mit Batch-Statistiken
    """
    from app.services.auto_matching_service import AutoMatchingService
    from app.db.models import Company
    from sqlalchemy import select

    async def _run_batch() -> Dict[str, object]:
        async with get_async_session_context() as db:
            companies_to_process: List[UUID] = []

            if company_id:
                companies_to_process.append(UUID(company_id))
            else:
                stmt = select(Company.id).where(Company.is_active.is_(True))
                result = await db.execute(stmt)
                companies_to_process = [row[0] for row in result.all()]

            total_processed = 0
            total_matched = 0
            total_errors = 0

            for cid in companies_to_process:
                try:
                    service = AutoMatchingService(db)
                    batch_result = await service.run_batch_matching(
                        db, cid, limit=limit
                    )
                    total_processed += int(batch_result.get("processed", 0))
                    total_matched += int(batch_result.get("matched", 0))
                    total_errors += int(batch_result.get("errors", 0))

                    await db.commit()

                except Exception as exc:
                    total_errors += 1
                    logger.warning(
                        "batch_matching_company_error",
                        company_id=str(cid),
                        **safe_error_log(exc),
                    )

            logger.info(
                "batch_auto_matching_completed",
                companies=len(companies_to_process),
                processed=total_processed,
                matched=total_matched,
                errors=total_errors,
            )

            return {
                "companies_processed": len(companies_to_process),
                "documents_processed": total_processed,
                "matches_created": total_matched,
                "errors": total_errors,
            }

    try:
        return asyncio.run(_run_batch())
    except Exception as exc:
        logger.error(
            "batch_auto_matching_failed",
            **safe_error_log(exc),
        )
        raise self.retry(exc=exc)


@celery_app.task(
    name="app.workers.tasks.approval_enhanced_tasks.run_auto_filing_task",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
    queue="default",
)
def run_auto_filing_task(
    self,
    company_id: str,
    document_id: str,
) -> Dict[str, object]:
    """Auto-Filing fuer ein einzelnes Dokument ausfuehren.

    Wird nach OCR-Abschluss getriggert.
    Klassifiziert das Dokument und ordnet es automatisch ein.

    Args:
        company_id: Company-ID
        document_id: Dokument-ID

    Returns:
        Dict mit Filing-Ergebnis
    """
    from app.services.auto_filing_service import AutoFilingService

    async def _run_filing() -> Dict[str, object]:
        async with get_async_session_context() as db:
            service = AutoFilingService(db)
            cid = UUID(company_id)
            did = UUID(document_id)

            result = await service.auto_file_document(db, cid, did)

            await db.commit()

            return result

    try:
        return asyncio.run(_run_filing())
    except Exception as exc:
        logger.error(
            "auto_filing_failed",
            document_id=document_id,
            **safe_error_log(exc),
        )
        raise self.retry(exc=exc)

# -*- coding: utf-8 -*-
"""
Extended Orchestration Celery Tasks.

Enterprise Features:
- Entity Health Degradation Check (taeglich 07:00)
- Seasonal Pattern Detection (woechentlich)
- Pending Investigation Processing (stuendlich)
- Overdue Approval Escalation (alle 30 Minuten)

Feinpoliert und durchdacht - Proaktive Orchestrierung.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

import structlog
from prometheus_client import Counter, Histogram

from app.workers.celery_app import celery_app, CPUTask
from app.db.session import get_async_session_context
from app.core.safe_errors import safe_error_log, safe_error_detail

logger = structlog.get_logger(__name__)


# =============================================================================
# Prometheus Metriken
# =============================================================================

ORCHESTRATION_EXTENDED_TASKS = Counter(
    "orchestration_extended_tasks_total",
    "Anzahl ausgefuehrter erweiterter Orchestration Tasks",
    ["task_name", "status"]
)

ORCHESTRATION_EXTENDED_DURATION = Histogram(
    "orchestration_extended_task_duration_seconds",
    "Dauer der erweiterten Orchestration Tasks",
    ["task_name"],
    buckets=[0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0]
)


# =============================================================================
# Helper
# =============================================================================

def run_async(coro):
    """Fuehrt eine Coroutine in einem neuen Event Loop aus."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# =============================================================================
# Entity Health Degradation Tasks
# =============================================================================

@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.orchestration_extended_tasks.check_entity_health_degradation",
    max_retries=3,
    default_retry_delay=300,
    queue="orchestration",
    soft_time_limit=600,
    time_limit=900,
)
def check_entity_health_degradation(
    self,
    company_id: Optional[str] = None,
    limit: int = 500,
) -> Dict[str, Any]:
    """
    Prueft alle Entities auf Gesundheitsverschlechterung.

    Sollte taeglich um 07:00 Uhr ausgefuehrt werden.
    Generiert automatisch Empfehlungen und Alerts bei Risiko-Erhoehungen.

    Args:
        company_id: Optional: Nur fuer diese Company
        limit: Maximale Anzahl zu pruefender Entities

    Returns:
        Statistiken ueber die Pruefung
    """
    logger.info(
        "check_entity_health_degradation_started",
        task_id=self.request.id,
        company_id=company_id,
        limit=limit,
    )

    start_time = datetime.now(timezone.utc)

    async def _check():
        from app.services.orchestration.entity_health_handler import (
            get_entity_health_handler,
        )

        handler = get_entity_health_handler()

        async with get_async_session_context() as db:
            company_uuid = UUID(company_id) if company_id else None
            stats = await handler.check_all_entities(
                db, company_id=company_uuid, limit=limit
            )
            await db.commit()

            return stats

    try:
        stats = run_async(_check())

        duration = (datetime.now(timezone.utc) - start_time).total_seconds()

        ORCHESTRATION_EXTENDED_TASKS.labels(
            task_name="check_entity_health_degradation",
            status="success"
        ).inc()

        ORCHESTRATION_EXTENDED_DURATION.labels(
            task_name="check_entity_health_degradation"
        ).observe(duration)

        logger.info(
            "check_entity_health_degradation_completed",
            task_id=self.request.id,
            **stats,
            duration_seconds=duration,
        )

        return {
            "status": "success",
            **stats,
            "duration_seconds": duration,
        }

    except Exception as e:
        ORCHESTRATION_EXTENDED_TASKS.labels(
            task_name="check_entity_health_degradation",
            status="error"
        ).inc()

        logger.error(
            "check_entity_health_degradation_failed",
            task_id=self.request.id,
            **safe_error_log(e),
        )
        raise self.retry(exc=e)


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.orchestration_extended_tasks.apply_health_action",
    max_retries=3,
    default_retry_delay=60,
    queue="orchestration",
    soft_time_limit=120,
    time_limit=180,
)
def apply_health_action(
    self,
    recommendation_id: str,
    applied_by_id: str,
) -> Dict[str, Any]:
    """
    Wendet eine Gesundheits-Empfehlung an.

    Args:
        recommendation_id: ID der Empfehlung
        applied_by_id: ID des ausfuehrenden Benutzers

    Returns:
        Ergebnis der Anwendung
    """
    logger.info(
        "apply_health_action_started",
        task_id=self.request.id,
        recommendation_id=recommendation_id,
    )

    async def _apply():
        from app.services.orchestration.entity_health_handler import (
            get_entity_health_handler,
        )

        handler = get_entity_health_handler()

        async with get_async_session_context() as db:
            success, message = await handler.apply_recommendation(
                db,
                UUID(recommendation_id),
                UUID(applied_by_id),
            )
            await db.commit()

            return success, message

    try:
        success, message = run_async(_apply())

        status = "success" if success else "failed"

        ORCHESTRATION_EXTENDED_TASKS.labels(
            task_name="apply_health_action",
            status=status
        ).inc()

        logger.info(
            "apply_health_action_completed",
            task_id=self.request.id,
            recommendation_id=recommendation_id,
            success=success,
            message=message,
        )

        return {
            "status": status,
            "success": success,
            "message": message,
            "recommendation_id": recommendation_id,
        }

    except Exception as e:
        ORCHESTRATION_EXTENDED_TASKS.labels(
            task_name="apply_health_action",
            status="error"
        ).inc()

        logger.error(
            "apply_health_action_failed",
            task_id=self.request.id,
            recommendation_id=recommendation_id,
            **safe_error_log(e),
        )
        raise self.retry(exc=e)


# =============================================================================
# Seasonal Pattern Detection Tasks
# =============================================================================

@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.orchestration_extended_tasks.detect_seasonal_patterns",
    max_retries=2,
    default_retry_delay=600,
    queue="maintenance",
    soft_time_limit=900,
    time_limit=1200,
)
def detect_seasonal_patterns(
    self,
    company_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Erkennt saisonale Muster und generiert Warnungen.

    Sollte woechentlich (z.B. Montags um 06:00) ausgefuehrt werden.
    Analysiert historische Daten und erstellt proaktive Warnungen.

    Args:
        company_id: Optional: Nur fuer diese Company (sonst alle)

    Returns:
        Analyse-Ergebnisse
    """
    logger.info(
        "detect_seasonal_patterns_started",
        task_id=self.request.id,
        company_id=company_id,
    )

    start_time = datetime.now(timezone.utc)

    async def _detect():
        from app.services.orchestration.seasonal_detector_service import (
            get_seasonal_detector_service,
        )
        from sqlalchemy import select
        from app.db.models import Company

        service = get_seasonal_detector_service()
        results = []

        async with get_async_session_context() as db:
            if company_id:
                company_ids = [UUID(company_id)]
            else:
                # Alle aktiven Companies
                query = select(Company.id).where(Company.is_active == True).limit(100)
                result = await db.execute(query)
                company_ids = [row[0] for row in result.all()]

            for comp_id in company_ids:
                try:
                    analysis = await service.analyze_company_seasonality(db, comp_id)
                    results.append({
                        "company_id": str(comp_id),
                        "patterns_count": len(analysis.patterns),
                        "warnings_count": len(analysis.warnings),
                        "adjustments_count": len(analysis.liquidity_adjustments),
                    })
                    await db.commit()
                except Exception as e:
                    logger.warning(
                        "seasonal_analysis_failed_for_company",
                        company_id=str(comp_id),
                        **safe_error_log(e),
                    )
                    results.append({
                        "company_id": str(comp_id),
                        "error": safe_error_detail(e, "Analyse"),
                    })

            return results

    try:
        results = run_async(_detect())

        duration = (datetime.now(timezone.utc) - start_time).total_seconds()

        total_patterns = sum(r.get("patterns_count", 0) for r in results)
        total_warnings = sum(r.get("warnings_count", 0) for r in results)

        ORCHESTRATION_EXTENDED_TASKS.labels(
            task_name="detect_seasonal_patterns",
            status="success"
        ).inc()

        ORCHESTRATION_EXTENDED_DURATION.labels(
            task_name="detect_seasonal_patterns"
        ).observe(duration)

        logger.info(
            "detect_seasonal_patterns_completed",
            task_id=self.request.id,
            companies_analyzed=len(results),
            total_patterns=total_patterns,
            total_warnings=total_warnings,
            duration_seconds=duration,
        )

        return {
            "status": "success",
            "companies_analyzed": len(results),
            "total_patterns": total_patterns,
            "total_warnings": total_warnings,
            "results": results,
            "duration_seconds": duration,
        }

    except Exception as e:
        ORCHESTRATION_EXTENDED_TASKS.labels(
            task_name="detect_seasonal_patterns",
            status="error"
        ).inc()

        logger.error(
            "detect_seasonal_patterns_failed",
            task_id=self.request.id,
            **safe_error_log(e),
        )
        raise self.retry(exc=e)


# =============================================================================
# Investigation Processing Tasks
# =============================================================================

@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.orchestration_extended_tasks.process_pending_investigations",
    max_retries=3,
    default_retry_delay=120,
    queue="orchestration",
    soft_time_limit=300,
    time_limit=600,
)
def process_pending_investigations(
    self,
    company_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Verarbeitet ausstehende Untersuchungen.

    Sollte stuendlich ausgefuehrt werden.
    Prueft den Status laufender Untersuchungen und erstellt Benachrichtigungen.

    Args:
        company_id: Optional: Nur fuer diese Company

    Returns:
        Verarbeitungsstatistiken
    """
    logger.info(
        "process_pending_investigations_started",
        task_id=self.request.id,
        company_id=company_id,
    )

    start_time = datetime.now(timezone.utc)

    async def _process():
        from app.services.orchestration.anomaly_investigation_service import (
            get_anomaly_investigation_service,
            InvestigationStatus,
        )

        service = get_anomaly_investigation_service()

        company_uuid = UUID(company_id) if company_id else None

        # Liste aller aktiven Untersuchungen
        investigations = await service.list_investigations(
            company_id=company_uuid,
            limit=100,
        )

        stats = {
            "total_active": len(investigations),
            "initiated": 0,
            "collecting_data": 0,
            "analyzing": 0,
            "report_generated": 0,
            "notified": 0,
            "under_review": 0,
        }

        for inv in investigations:
            status_key = inv.status.value
            if status_key in stats:
                stats[status_key] += 1

        return stats

    try:
        stats = run_async(_process())

        duration = (datetime.now(timezone.utc) - start_time).total_seconds()

        ORCHESTRATION_EXTENDED_TASKS.labels(
            task_name="process_pending_investigations",
            status="success"
        ).inc()

        ORCHESTRATION_EXTENDED_DURATION.labels(
            task_name="process_pending_investigations"
        ).observe(duration)

        logger.info(
            "process_pending_investigations_completed",
            task_id=self.request.id,
            **stats,
            duration_seconds=duration,
        )

        return {
            "status": "success",
            **stats,
            "duration_seconds": duration,
        }

    except Exception as e:
        ORCHESTRATION_EXTENDED_TASKS.labels(
            task_name="process_pending_investigations",
            status="error"
        ).inc()

        logger.error(
            "process_pending_investigations_failed",
            task_id=self.request.id,
            **safe_error_log(e),
        )
        raise self.retry(exc=e)


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.orchestration_extended_tasks.start_fraud_investigation",
    max_retries=3,
    default_retry_delay=60,
    queue="orchestration",
    soft_time_limit=300,
    time_limit=600,
)
def start_fraud_investigation(
    self,
    company_id: str,
    anomaly_type: str,
    entity_id: Optional[str] = None,
    document_id: Optional[str] = None,
    trigger_id: Optional[str] = None,
    trigger_type: str = "automated",
) -> Dict[str, Any]:
    """
    Startet eine Anomalie-Untersuchung.

    Args:
        company_id: Company ID
        anomaly_type: Art der Anomalie
        entity_id: Optional: Betroffene Entity
        document_id: Optional: Ausloesende Dokument
        trigger_id: Optional: Ausloeser-ID (z.B. Alert)
        trigger_type: Ausloeser-Typ

    Returns:
        Untersuchungs-Details
    """
    logger.info(
        "start_fraud_investigation_started",
        task_id=self.request.id,
        company_id=company_id,
        anomaly_type=anomaly_type,
    )

    async def _start():
        from app.services.orchestration.anomaly_investigation_service import (
            get_anomaly_investigation_service,
            AnomalyType,
        )

        service = get_anomaly_investigation_service()

        # Anomaly-Typ konvertieren
        try:
            anomaly_enum = AnomalyType(anomaly_type)
        except ValueError:
            anomaly_enum = AnomalyType.PATTERN_BREAK

        async with get_async_session_context() as db:
            investigation = await service.start_investigation(
                db=db,
                company_id=UUID(company_id),
                anomaly_type=anomaly_enum,
                entity_id=UUID(entity_id) if entity_id else None,
                document_id=UUID(document_id) if document_id else None,
                trigger_id=UUID(trigger_id) if trigger_id else None,
                trigger_type=trigger_type,
            )
            await db.commit()

            return {
                "investigation_id": str(investigation.id),
                "status": investigation.status.value,
                "alert_id": str(investigation.alert_id) if investigation.alert_id else None,
                "report": investigation.report.to_dict() if investigation.report else None,
            }

    try:
        result = run_async(_start())

        ORCHESTRATION_EXTENDED_TASKS.labels(
            task_name="start_fraud_investigation",
            status="success"
        ).inc()

        logger.info(
            "start_fraud_investigation_completed",
            task_id=self.request.id,
            investigation_id=result.get("investigation_id"),
            status=result.get("status"),
        )

        return {
            "status": "success",
            **result,
        }

    except Exception as e:
        ORCHESTRATION_EXTENDED_TASKS.labels(
            task_name="start_fraud_investigation",
            status="error"
        ).inc()

        logger.error(
            "start_fraud_investigation_failed",
            task_id=self.request.id,
            **safe_error_log(e),
        )
        raise self.retry(exc=e)


# =============================================================================
# Approval Escalation Tasks
# =============================================================================

@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.orchestration_extended_tasks.escalate_overdue_approvals_extended",
    max_retries=3,
    default_retry_delay=60,
    queue="orchestration",
    soft_time_limit=180,
    time_limit=300,
)
def escalate_overdue_approvals_extended(
    self,
    company_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Eskaliert ueberfaellige Genehmigungen mit Smart-Routing.

    Sollte alle 30 Minuten ausgefuehrt werden.
    Verwendet SmartApprovalRouter fuer intelligente Eskalation.

    Args:
        company_id: Optional: Nur fuer diese Company

    Returns:
        Eskalations-Statistiken
    """
    logger.info(
        "escalate_overdue_approvals_extended_started",
        task_id=self.request.id,
        company_id=company_id,
    )

    start_time = datetime.now(timezone.utc)

    async def _escalate():
        from app.services.orchestration.smart_approval_router import (
            get_smart_approval_router,
        )
        from sqlalchemy import select, and_
        from app.db.models import ApprovalRequest, ApprovalStatus

        router = get_smart_approval_router()

        stats = {
            "checked": 0,
            "escalated_level_1": 0,
            "escalated_level_2": 0,
            "escalated_level_3": 0,
            "deputies_assigned": 0,
        }

        async with get_async_session_context() as db:
            # Ausstehende Approvals laden
            query = select(ApprovalRequest).where(
                ApprovalRequest.status == ApprovalStatus.PENDING
            )

            if company_id:
                query = query.where(ApprovalRequest.company_id == UUID(company_id))

            query = query.limit(200)

            result = await db.execute(query)
            requests = result.scalars().all()

            for request in requests:
                stats["checked"] += 1

                # Pruefe Eskalationsbedarf
                needs_escalation, reason, level = await router.check_escalation_needed(
                    db, request.id
                )

                if needs_escalation and level > 0:
                    # Eskalieren
                    new_approver = await router.escalate_to_next_level(
                        db, request.id, level, request.company_id
                    )

                    if new_approver:
                        stats[f"escalated_level_{level}"] += 1

                        # Request aktualisieren
                        request.is_escalated = True
                        request.escalation_date = datetime.now(timezone.utc)

                        logger.info(
                            "approval_escalated_by_smart_router",
                            request_id=str(request.id),
                            level=level,
                            reason=reason,
                        )

            await db.commit()

        return stats

    try:
        stats = run_async(_escalate())

        duration = (datetime.now(timezone.utc) - start_time).total_seconds()

        ORCHESTRATION_EXTENDED_TASKS.labels(
            task_name="escalate_overdue_approvals_extended",
            status="success"
        ).inc()

        ORCHESTRATION_EXTENDED_DURATION.labels(
            task_name="escalate_overdue_approvals_extended"
        ).observe(duration)

        total_escalated = (
            stats["escalated_level_1"]
            + stats["escalated_level_2"]
            + stats["escalated_level_3"]
        )

        logger.info(
            "escalate_overdue_approvals_extended_completed",
            task_id=self.request.id,
            checked=stats["checked"],
            total_escalated=total_escalated,
            duration_seconds=duration,
        )

        return {
            "status": "success",
            **stats,
            "total_escalated": total_escalated,
            "duration_seconds": duration,
        }

    except Exception as e:
        ORCHESTRATION_EXTENDED_TASKS.labels(
            task_name="escalate_overdue_approvals_extended",
            status="error"
        ).inc()

        logger.error(
            "escalate_overdue_approvals_extended_failed",
            task_id=self.request.id,
            **safe_error_log(e),
        )
        raise self.retry(exc=e)


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.orchestration_extended_tasks.assign_deputy_approvers",
    max_retries=2,
    default_retry_delay=120,
    queue="orchestration",
    soft_time_limit=180,
    time_limit=300,
)
def assign_deputy_approvers(
    self,
    company_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Weist Stellvertreter fuer abwesende Genehmiger zu.

    Sollte taeglich ausgefuehrt werden.

    Args:
        company_id: Optional: Nur fuer diese Company

    Returns:
        Zuweisungs-Statistiken
    """
    logger.info(
        "assign_deputy_approvers_started",
        task_id=self.request.id,
        company_id=company_id,
    )

    async def _assign():
        from app.services.orchestration.smart_approval_router import (
            get_smart_approval_router,
        )
        from sqlalchemy import select, and_
        from app.db.models import ApprovalStep, ApprovalStatus

        router = get_smart_approval_router()

        stats = {
            "checked": 0,
            "deputies_assigned": 0,
            "no_deputy_needed": 0,
            "no_deputy_found": 0,
        }

        async with get_async_session_context() as db:
            # Ausstehende Approval Steps mit zugewiesenem User
            query = (
                select(ApprovalStep)
                .where(
                    and_(
                        ApprovalStep.status == ApprovalStatus.PENDING,
                        ApprovalStep.assigned_user_id.isnot(None),
                    )
                )
            )

            if company_id:
                from app.db.models import ApprovalRequest
                query = (
                    query
                    .join(ApprovalRequest)
                    .where(ApprovalRequest.company_id == UUID(company_id))
                )

            query = query.limit(200)

            result = await db.execute(query)
            steps = result.scalars().all()

            for step in steps:
                stats["checked"] += 1

                # Verfuegbarkeit pruefen und ggf. Stellvertreter waehlen
                selection = await router.select_deputy(
                    db,
                    step.assigned_user_id,
                    step.approval_request.company_id,
                )

                if selection.deputy_id:
                    # Stellvertreter zuweisen
                    step.assigned_user_id = selection.deputy_id
                    stats["deputies_assigned"] += 1

                    logger.info(
                        "deputy_assigned",
                        step_id=str(step.id),
                        reason=selection.reason,
                    )
                elif selection.absence_status.value == "available":
                    stats["no_deputy_needed"] += 1
                else:
                    stats["no_deputy_found"] += 1

            await db.commit()

        return stats

    try:
        stats = run_async(_assign())

        ORCHESTRATION_EXTENDED_TASKS.labels(
            task_name="assign_deputy_approvers",
            status="success"
        ).inc()

        logger.info(
            "assign_deputy_approvers_completed",
            task_id=self.request.id,
            **stats,
        )

        return {
            "status": "success",
            **stats,
        }

    except Exception as e:
        ORCHESTRATION_EXTENDED_TASKS.labels(
            task_name="assign_deputy_approvers",
            status="error"
        ).inc()

        logger.error(
            "assign_deputy_approvers_failed",
            task_id=self.request.id,
            **safe_error_log(e),
        )
        raise self.retry(exc=e)

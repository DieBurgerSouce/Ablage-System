# -*- coding: utf-8 -*-
"""
Document Lifecycle SLA Monitoring - Celery Periodic Task.

Prueft alle 15 Minuten auf SLA-Verletzungen und erstellt
Alerts ueber den Alert Center Service.

Beat Schedule (in celery_app.py zu registrieren):
    'check-lifecycle-sla-violations': {
        'task': 'app.workers.tasks_lifecycle.check_sla_violations_task',
        'schedule': 900.0,  # Alle 15 Minuten
    }
"""

import asyncio
from typing import Dict, List, Optional

import structlog

from app.workers.celery_app import celery_app
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


@celery_app.task(
    name="app.workers.tasks_lifecycle.check_sla_violations_task",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    queue="metadata",
)
def check_sla_violations_task(
    self,
    company_id: Optional[str] = None,
) -> Dict[str, int]:
    """
    Prueft alle Mandanten auf SLA-Verletzungen und erstellt Alerts.

    Wird alle 15 Minuten von Celery Beat aufgerufen.
    Erstellt Alerts ueber den Alert Center Service, wenn
    die Verweildauer in einer Lebenszyklus-Stufe die konfigurierte
    maximale Dauer ueberschreitet.

    Args:
        company_id: Optional - nur fuer bestimmten Mandanten pruefen

    Returns:
        Statistiken ueber gefundene Verletzungen und erstellte Alerts
    """
    logger.info(
        "lifecycle_sla_check_started",
        company_id=company_id,
    )

    try:
        result = asyncio.run(_check_violations_async(company_id))
        logger.info(
            "lifecycle_sla_check_completed",
            companies_checked=result.get("companies_checked", 0),
            violations_found=result.get("violations_found", 0),
            alerts_created=result.get("alerts_created", 0),
        )
        return result
    except Exception as e:
        logger.error(
            "lifecycle_sla_check_failed",
            **safe_error_log(e),
        )
        raise self.retry(exc=e)


async def _check_violations_async(
    company_id: Optional[str] = None,
) -> Dict[str, int]:
    """
    Asynchrone SLA-Pruefung fuer alle oder einen bestimmten Mandanten.

    Erstellt fuer jede gefundene SLA-Verletzung einen Alert
    ueber den Alert Center Service.
    """
    from uuid import UUID

    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

    from app.core.config import settings
    from app.db.models import Company
    from app.db.models_alert import AlertCategory, AlertSeverity
    from app.services.alert_center_service import (
        AlertCenterService,
        AlertCodes,
    )
    from app.services.document_lifecycle_service import DocumentLifecycleService

    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    async_session = async_sessionmaker(engine, class_=AsyncSession)

    stats: Dict[str, int] = {
        "companies_checked": 0,
        "violations_found": 0,
        "alerts_created": 0,
    }

    try:
        async with async_session() as session:
            # Mandanten ermitteln
            if company_id:
                company_ids = [UUID(company_id)]
            else:
                stmt = select(Company.id)
                result = await session.execute(stmt)
                company_ids = [row[0] for row in result.all()]

            for cid in company_ids:
                stats["companies_checked"] += 1

                lifecycle_service = DocumentLifecycleService(session)
                violations = await lifecycle_service.check_sla_violations(cid)

                stats["violations_found"] += len(violations)

                if not violations:
                    continue

                alert_service = AlertCenterService(session)

                for violation in violations:
                    # Schweregrad basierend auf Ueberschreitung
                    if violation.overdue_hours > 24:
                        severity = AlertSeverity.CRITICAL
                    elif violation.overdue_hours > 8:
                        severity = AlertSeverity.HIGH
                    elif violation.overdue_hours > 2:
                        severity = AlertSeverity.MEDIUM
                    else:
                        severity = AlertSeverity.LOW

                    stage_label = violation.current_stage.replace("_", " ").title()

                    await alert_service.create_alert(
                        company_id=cid,
                        alert_code="SLA_001",
                        category=AlertCategory.WORKFLOW,
                        severity=severity,
                        title=f"SLA-Verletzung: {stage_label}",
                        message=(
                            f"Das Dokument '{violation.document_filename}' "
                            f"befindet sich seit "
                            f"{violation.actual_duration_hours:.1f} Stunden "
                            f"in der Stufe '{stage_label}' "
                            f"(Maximum: {violation.max_duration_hours}h). "
                            f"Ueberschreitung: {violation.overdue_hours:.1f}h."
                        ),
                        source_type="lifecycle_sla",
                        source_id=str(violation.document_id),
                        document_id=violation.document_id,
                        metadata={
                            "current_stage": violation.current_stage,
                            "overdue_hours": round(violation.overdue_hours, 1),
                            "max_duration_hours": violation.max_duration_hours,
                        },
                        context={
                            "document_type": violation.document_type,
                            "escalation_to_role": violation.escalation_to_role,
                        },
                        available_actions=[
                            "acknowledge",
                            "transition_stage",
                            "escalate",
                        ],
                        recurrence_key=(
                            f"sla_{violation.document_id}_{violation.current_stage}"
                        ),
                    )
                    stats["alerts_created"] += 1

                await session.commit()

    finally:
        await engine.dispose()

    return stats

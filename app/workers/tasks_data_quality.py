# -*- coding: utf-8 -*-
"""
Data Quality Celery Tasks.

Periodische Aufgaben für Datenqualitäts-Tracking:
- daily_quality_scan_task: Täglicher Scan und History-Speicherung
- quality_trend_cleanup_task: Alte History-Einträge bereinigen

Feinpoliert und durchdacht - Automated Data Quality Monitoring.
"""

import uuid
import structlog
from datetime import datetime, timedelta, timezone

from app.workers.celery_app import celery_app
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


@celery_app.task(
    name="data_quality.daily_scan",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
    acks_late=True,
)
def daily_quality_scan_task(self, company_id: str) -> dict:
    """
    Führt täglichen Datenqualitäts-Scan durch und speichert Ergebnis.

    Wird von Celery Beat getriggert. Erstellt einen DataQualityHistory-Eintrag
    für die angegebene Company.

    Args:
        company_id: Company UUID als String

    Returns:
        Dict mit Ergebnis-Zusammenfassung
    """
    import asyncio
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
    from app.core.config import settings

    logger.info(
        "data_quality_daily_scan_start",
        company_id=company_id,
    )

    async def _run_scan() -> dict:
        engine = create_async_engine(settings.DATABASE_URL)
        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async with session_factory() as session:
            try:
                from app.services.data_quality_service import DataQualityService
                from app.db.models_data_quality import DataQualityHistory

                company_uuid = uuid.UUID(company_id)
                service = DataQualityService(session)

                report = await service.get_quality_report(company_uuid)

                # Build issue_counts dict
                issue_counts = {}
                issue_details_list = []
                for issue in report.issues:
                    issue_counts[issue.category.value] = issue.count
                    issue_details_list.append({
                        "category": issue.category.value,
                        "severity": issue.severity,
                        "title": issue.title,
                        "description": issue.description,
                        "count": issue.count,
                        "action_label": issue.action_label,
                    })

                # Store history entry
                history_entry = DataQualityHistory(
                    company_id=company_uuid,
                    overall_score=report.overall_score,
                    issue_counts=issue_counts,
                    issue_details=issue_details_list,
                )
                session.add(history_entry)
                await session.commit()

                logger.info(
                    "data_quality_daily_scan_complete",
                    company_id=company_id,
                    overall_score=report.overall_score,
                    issue_count=len(report.issues),
                )

                return {
                    "company_id": company_id,
                    "overall_score": report.overall_score,
                    "issue_count": len(report.issues),
                    "status": "success",
                }

            except Exception as e:
                await session.rollback()
                raise e
            finally:
                await engine.dispose()

    try:
        return asyncio.run(_run_scan())
    except Exception as e:
        logger.error(
            "data_quality_daily_scan_failed",
            company_id=company_id,
            **safe_error_log(e),
        )
        raise self.retry(exc=e)


@celery_app.task(
    name="data_quality.scan_all_companies",
    bind=True,
    max_retries=1,
    default_retry_delay=600,
)
def scan_all_companies_task(self) -> dict:
    """
    Startet Daily Quality Scan für alle aktiven Companies.

    Wird von Celery Beat getriggert. Dispatcht einzelne
    daily_quality_scan_task pro Company.

    Returns:
        Dict mit Anzahl gestarteter Scans
    """
    import asyncio
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
    from app.core.config import settings

    logger.info("data_quality_scan_all_companies_start")

    async def _get_companies() -> list:
        engine = create_async_engine(settings.DATABASE_URL)
        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async with session_factory() as session:
            try:
                from app.db.models import Company
                result = await session.execute(
                    select(Company.id).where(Company.is_active == True)
                )
                company_ids = [str(row[0]) for row in result.all()]
                return company_ids
            finally:
                await engine.dispose()

    try:
        company_ids = asyncio.run(_get_companies())

        for cid in company_ids:
            daily_quality_scan_task.delay(cid)

        logger.info(
            "data_quality_scan_all_companies_dispatched",
            company_count=len(company_ids),
        )

        return {
            "dispatched_count": len(company_ids),
            "status": "success",
        }

    except Exception as e:
        logger.error(
            "data_quality_scan_all_companies_failed",
            **safe_error_log(e),
        )
        raise self.retry(exc=e)

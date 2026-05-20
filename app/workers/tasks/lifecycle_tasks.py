# -*- coding: utf-8 -*-
"""Document Lifecycle Celery Tasks - Automatisierte Lebenszyklus-Verwaltung.

Celery-Tasks fuer die automatisierte Verwaltung des Dokumenten-Lebenszyklus:
- Taeglicher Scan auf ablaufende Aufbewahrungsfristen
- Monatlicher Lifecycle-Report
- Automatische Archivierung abgelaufener Dokumente
- Vernichtungsprotokoll-Generierung

Erfuellt GoBD-Kriterien:
- Vollstaendigkeit: Automatische Fristen-Ueberwachung
- Nachvollziehbarkeit: Audit-Trail fuer alle Aktionen
- Ordnung: Kategorisierte Reports
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import date, datetime, timezone
from typing import Dict, List

import structlog

from app.core.safe_errors import safe_error_log
from app.db.session import async_session_factory
from app.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


# =============================================================================
# Daily Retention Scan Task
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.lifecycle_tasks.daily_retention_scan_task",
    bind=True,
    acks_late=True,
    max_retries=3,
    default_retry_delay=300,
)
def daily_retention_scan_task(self, days_ahead: int = 30) -> Dict[str, object]:
    """Taeglicher Scan auf ablaufende Dokumente mit Benachrichtigungen.

    Wird taeglich via Celery Beat um 02:00 Uhr ausgefuehrt.
    Scannt alle Firmen auf Dokumente mit ablaufender Aufbewahrungsfrist
    und sendet Benachrichtigungen an Administratoren.

    Args:
        days_ahead: Tage im Voraus pruefen (default: 30)

    Returns:
        Dictionary mit Scan-Statistiken
    """
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                _run_daily_retention_scan(days_ahead)
            )
            return result
        finally:
            loop.close()
    except Exception as exc:
        logger.error(
            "lifecycle_daily_scan_failed",
            **safe_error_log(exc),
            days_ahead=days_ahead,
        )
        raise self.retry(exc=exc)


async def _run_daily_retention_scan(days_ahead: int) -> Dict[str, object]:
    """Async-Implementierung des taeglichen Retention-Scans."""
    from app.services.document_lifecycle_engine import document_lifecycle_engine

    async with async_session_factory() as db:
        archives = await document_lifecycle_engine.scan_expiring_documents(
            db, days_ahead=days_ahead
        )

        # Benachrichtigungen fuer ablaufende Dokumente
        notification_count = 0
        for archive in archives:
            if not archive.retention_reminder_sent:
                try:
                    from app.services.archive_service import archive_service
                    await archive_service.mark_reminder_sent(db, archive.id)
                    notification_count += 1
                except Exception as e:
                    logger.warning(
                        "lifecycle_scan_reminder_failed",
                        archive_id=str(archive.id),
                        **safe_error_log(e),
                    )

        stats: Dict[str, object] = {
            "task": "daily_retention_scan",
            "scanned_at": datetime.now(timezone.utc).isoformat(),
            "days_ahead": days_ahead,
            "expiring_documents": len(archives),
            "notifications_sent": notification_count,
        }

        logger.info(
            "lifecycle_daily_scan_completed",
            expiring=len(archives),
            notifications=notification_count,
        )

        return stats


# =============================================================================
# Monthly Lifecycle Report Task
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.lifecycle_tasks.monthly_lifecycle_report_task",
    bind=True,
    acks_late=True,
    max_retries=3,
    default_retry_delay=600,
)
def monthly_lifecycle_report_task(self) -> Dict[str, object]:
    """Monatlicher Lifecycle-Report ueber alle Firmen.

    Wird monatlich am 1. via Celery Beat um 06:00 Uhr ausgefuehrt.
    Generiert eine Zusammenfassung des Dokumenten-Lebenszyklus.

    Returns:
        Dictionary mit Report-Daten
    """
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(_run_monthly_report())
            return result
        finally:
            loop.close()
    except Exception as exc:
        logger.error(
            "lifecycle_monthly_report_failed",
            **safe_error_log(exc),
        )
        raise self.retry(exc=exc)


async def _run_monthly_report() -> Dict[str, object]:
    """Async-Implementierung des monatlichen Reports."""
    from app.services.document_lifecycle_engine import document_lifecycle_engine
    from app.db.models import Company
    from sqlalchemy import select

    async with async_session_factory() as db:
        # Alle aktiven Firmen laden
        companies_result = await db.execute(
            select(Company.id, Company.name)
        )
        companies = companies_result.all()

        company_reports: List[Dict[str, object]] = []
        for company_id, company_name in companies:
            try:
                dashboard = await document_lifecycle_engine.get_lifecycle_dashboard(
                    db, company_id
                )
                company_reports.append({
                    "company_id": str(company_id),
                    "company_name": company_name,
                    "dashboard": dashboard,
                })
            except Exception as e:
                logger.warning(
                    "lifecycle_report_company_failed",
                    company_id=str(company_id),
                    **safe_error_log(e),
                )

        # Gesamt-Zusammenfassung
        summary = await document_lifecycle_engine.get_retention_summary(db)

        report: Dict[str, object] = {
            "task": "monthly_lifecycle_report",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "period": date.today().strftime("%Y-%m"),
            "company_count": len(companies),
            "company_reports": company_reports,
            "overall_summary": summary,
        }

        logger.info(
            "lifecycle_monthly_report_completed",
            companies=len(companies),
            reports_generated=len(company_reports),
        )

        return report


# =============================================================================
# Auto Archive Task
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.lifecycle_tasks.auto_archive_task",
    bind=True,
    acks_late=True,
    max_retries=3,
    default_retry_delay=300,
)
def auto_archive_task(self) -> Dict[str, object]:
    """Automatische Archivierung und Verifikation abgelaufener Dokumente.

    Wird taeglich via Celery Beat um 03:00 Uhr ausgefuehrt.
    Verifiziert die Integritaet aller Archive mit abgelaufener Frist.

    Returns:
        Dictionary mit Archivierungs-Statistiken
    """
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(_run_auto_archive())
            return result
        finally:
            loop.close()
    except Exception as exc:
        logger.error(
            "lifecycle_auto_archive_failed",
            **safe_error_log(exc),
        )
        raise self.retry(exc=exc)


async def _run_auto_archive() -> Dict[str, object]:
    """Async-Implementierung der automatischen Archivierung."""
    from app.services.document_lifecycle_engine import document_lifecycle_engine

    async with async_session_factory() as db:
        stats = await document_lifecycle_engine.auto_archive_expired(db)

        result: Dict[str, object] = {
            "task": "auto_archive",
            "executed_at": datetime.now(timezone.utc).isoformat(),
            **stats,
        }

        return result


# =============================================================================
# Destruction Protocol Task
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.lifecycle_tasks.destruction_protocol_task",
    bind=True,
    acks_late=True,
    max_retries=2,
    default_retry_delay=600,
)
def destruction_protocol_task(
    self,
    document_ids: List[str],
    user_id: str,
    reason: str = "Aufbewahrungsfrist abgelaufen",
) -> Dict[str, object]:
    """Generiert ein GoBD-konformes Vernichtungsprotokoll.

    Args:
        document_ids: Liste von Dokument-IDs (als Strings)
        user_id: ID des anordnenden Benutzers
        reason: Begruendung der Vernichtung

    Returns:
        Dictionary mit Vernichtungsprotokoll
    """
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                _run_destruction_protocol(document_ids, user_id, reason)
            )
            return result
        finally:
            loop.close()
    except Exception as exc:
        logger.error(
            "lifecycle_destruction_protocol_failed",
            **safe_error_log(exc),
            document_count=len(document_ids),
        )
        raise self.retry(exc=exc)


async def _run_destruction_protocol(
    document_ids: List[str],
    user_id: str,
    reason: str,
) -> Dict[str, object]:
    """Async-Implementierung der Vernichtungsprotokoll-Generierung."""
    from app.services.document_lifecycle_engine import document_lifecycle_engine

    parsed_doc_ids = [uuid.UUID(doc_id) for doc_id in document_ids]
    parsed_user_id = uuid.UUID(user_id)

    async with async_session_factory() as db:
        protocol = await document_lifecycle_engine.generate_destruction_protocol(
            db,
            document_ids=parsed_doc_ids,
            user_id=parsed_user_id,
            reason=reason,
        )

        return protocol

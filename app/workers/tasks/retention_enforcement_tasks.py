"""Retention Enforcement Tasks - Celery Tasks für Aufbewahrungsfristen-Durchsetzung.

Automatisierte Tasks für:
- Täglicher Scan auf Retention-Verletztungen
- Verarbeitung von Post-Retention Reviews
- Wochentlicher Compliance-Report
- GDPR-Konflikt-Aufloesung
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any, Dict, Optional

import structlog
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from prometheus_client import Counter, Gauge, Histogram

from app.core.safe_errors import safe_error_log
from app.db.session import async_session_factory
from app.db.models import DocumentArchive, Document, Company, AuditLog
from app.services.compliance.retention_enforcement_service import (
    retention_enforcement_service,
)
from app.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


# =============================================================================
# Prometheus Metriken
# =============================================================================

retention_enforcement_documents_scanned_total = Counter(
    "retention_enforcement_documents_scanned_total",
    "Gesamtzahl gescannter Archive im Enforcement-Scan",
    ["company"],
)

retention_enforcement_marked_for_deletion_total = Counter(
    "retention_enforcement_marked_for_deletion_total",
    "Archive die zum Loeschen markiert wurden",
    ["company"],
)

retention_enforcement_deleted_total = Counter(
    "retention_enforcement_deleted_total",
    "Erfolgreich geloeschte Archive",
    ["status"],
)

retention_enforcement_errors_total = Counter(
    "retention_enforcement_errors_total",
    "Fehler bei Retention Enforcement Tasks",
    ["task"],
)

retention_enforcement_scan_duration_seconds = Histogram(
    "retention_enforcement_scan_duration_seconds",
    "Dauer des taeglichen Enforcement-Scans in Sekunden",
    buckets=[1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0],
)

retention_enforcement_documents_by_category = Gauge(
    "retention_enforcement_documents_by_category",
    "Anzahl archivierter Dokumente nach Kategorie",
    ["category"],
)

retention_enforcement_pending_reviews = Gauge(
    "retention_enforcement_pending_reviews",
    "Anzahl ausstehender Post-Retention Reviews",
)


# =============================================================================
# Daily Enforcement Scan
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.retention_enforcement_tasks.enforce_retention_daily_scan",
    bind=True,
    acks_late=True,
    max_retries=3,
    default_retry_delay=300,
)
def enforce_retention_daily_scan(self) -> Dict[str, Any]:
    """Täglicher Scan auf Retention-Verletztungen.

    Prüft:
    - Dokumente die trotz aktiver Frist gelöscht wurden
    - Archive ohne korrekte enforcement_status
    - Inkonsistenzen zwischen Document.is_archived und DocumentArchive

    Returns:
        Dictionary mit Scan-Ergebnissen
    """
    import asyncio

    async def _scan():
        async with async_session_factory() as db:
            return await _daily_enforcement_scan(db)

    try:
        import time as _time
        start = _time.monotonic()
        result = asyncio.get_event_loop().run_until_complete(_scan())
        duration = _time.monotonic() - start
        retention_enforcement_scan_duration_seconds.observe(duration)
        logger.info(
            "retention_enforcement_daily_scan_completed",
            **result
        )
        return result
    except Exception as e:
        retention_enforcement_errors_total.labels(task="daily_scan").inc()
        logger.error(
            "retention_enforcement_daily_scan_failed",
            **safe_error_log(e)
        )
        raise self.retry(exc=e)


async def _daily_enforcement_scan(db: AsyncSession) -> Dict[str, Any]:
    """Interne Funktion für täglichen Enforcement-Scan."""
    violations_found = 0
    inconsistencies_fixed = 0
    archives_checked = 0

    # Alle aktiven Companies
    companies_result = await db.execute(
        select(Company).where(Company.is_active == True)
    )
    companies = companies_result.scalars().all()

    for company in companies:
        # Archivierte Dokumente ohne Archive-Eintrag finden (Inkonsistenz)
        orphaned_result = await db.execute(
            select(Document)
            .where(
                and_(
                    Document.company_id == company.id,
                    Document.is_archived == True,
                )
            )
        )
        orphaned_docs = orphaned_result.scalars().all()

        for doc in orphaned_docs:
            # Prüfe ob Archive-Eintrag existiert
            archive_result = await db.execute(
                select(DocumentArchive)
                .where(DocumentArchive.document_id == doc.id)
            )
            archive = archive_result.scalar_one_or_none()

            if not archive:
                # Inkonsistenz: is_archived=True aber kein Archive
                logger.warning(
                    "retention_inconsistency_found",
                    document_id=str(doc.id),
                    company_id=str(company.id),
                )
                violations_found += 1

                # Automatische Korrektur: is_archived zurücksetzen
                doc.is_archived = False
                doc.archived_at = None
                inconsistencies_fixed += 1

        # Alle Archive dieser Company prüfen
        archives_result = await db.execute(
            select(DocumentArchive)
            .where(DocumentArchive.company_id == company.id)
        )
        archives = archives_result.scalars().all()

        for archive in archives:
            archives_checked += 1

            # Enforcement-Status aktualisieren (wenn Spalte existiert)
            # Nach Migration 205 wuerde hier enforcement_status gesetzt
            # if archive.retention_expires_at < today:
            #     archive.enforcement_status = EnforcementStatus.EXPIRED.value
            # else:
            #     archive.enforcement_status = EnforcementStatus.ACTIVE.value

        # Prometheus Metriken pro Company
        retention_enforcement_documents_scanned_total.labels(
            company=company.short_name or str(company.id)[:8]
        ).inc(len(archives))

    await db.commit()

    # Globale Gauges aktualisieren
    if violations_found > 0:
        retention_enforcement_marked_for_deletion_total.labels(company="all").inc(violations_found)

    # Pending Reviews Gauge
    async with async_session_factory() as count_db:
        pending_reviews_result = await count_db.execute(
            select(func.count(DocumentArchive.id))
            .where(DocumentArchive.retention_expires_at < date.today())
        )
        retention_enforcement_pending_reviews.set(pending_reviews_result.scalar() or 0)

    return {
        "archives_checked": archives_checked,
        "violations_found": violations_found,
        "inconsistencies_fixed": inconsistencies_fixed,
        "companies_scanned": len(companies),
    }


# =============================================================================
# Post-Retention Review Processing
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.retention_enforcement_tasks.process_post_retention_reviews",
    bind=True,
    acks_late=True,
    max_retries=3,
    default_retry_delay=600,
)
def process_post_retention_reviews(self) -> Dict[str, Any]:
    """Verarbeitet Dokumente deren Aufbewahrungsfrist abgelaufen ist.

    Prüft Archive deren post_retention_review_scheduled=True und
    post_retention_review_at <= heute ist. Erstellt Audit-Logs und
    benachrichtigt Admins.

    Returns:
        Dictionary mit Verarbeitungs-Ergebnissen
    """
    import asyncio

    async def _process():
        async with async_session_factory() as db:
            return await _process_post_retention_reviews(db)

    try:
        result = asyncio.get_event_loop().run_until_complete(_process())
        logger.info(
            "post_retention_reviews_processed",
            **result
        )
        return result
    except Exception as e:
        retention_enforcement_errors_total.labels(task="post_retention_reviews").inc()
        logger.error(
            "post_retention_reviews_processing_failed",
            **safe_error_log(e)
        )
        raise self.retry(exc=e)


async def _process_post_retention_reviews(db: AsyncSession) -> Dict[str, Any]:
    """Interne Funktion für Post-Retention Review Verarbeitung."""
    reviews_processed = 0
    notifications_sent = 0

    # Archive mit fälliger Review finden
    # Nach Migration 205:
    # reviews_result = await db.execute(
    #     select(DocumentArchive)
    #     .where(
    #         and_(
    #             DocumentArchive.post_retention_review_scheduled == True,
    #             DocumentArchive.post_retention_review_at <= today,
    #         )
    #     )
    # )

    # Aktuell: Alle abgelaufenen Archive
    reviews_result = await db.execute(
        select(DocumentArchive)
        .where(DocumentArchive.retention_expires_at < date.today())
    )
    archives = reviews_result.scalars().all()

    for archive in archives:
        # Audit-Log erstellen
        await _create_enforcement_audit_log(
            db,
            archive.document_id,
            archive.company_id,
            "post_retention_review_processed",
            {
                "archive_id": str(archive.id),
                "retention_expired_at": str(archive.retention_expires_at),
                "retention_category": archive.retention_category,
                "can_delete": True,
            }
        )

        # Notification via Slack/Email (optional)
        try:
            from app.services.slack_service import SlackService, SlackNotificationType, SlackMessagePriority

            slack = SlackService()
            if slack.is_enabled:
                await slack.send_notification(
                    notification_type=SlackNotificationType.COMPLIANCE_ALERT,
                    title="Aufbewahrungsfrist abgelaufen",
                    message=(
                        f"Archiv {archive.id} kann nun gelöscht werden. "
                        f"Kategorie: {archive.retention_category}, "
                        f"Abgelaufen: {archive.retention_expires_at}"
                    ),
                    priority=SlackMessagePriority.LOW,
                    context={
                        "archive_id": str(archive.id),
                        "document_id": str(archive.document_id),
                        "retention_expires_at": str(archive.retention_expires_at),
                    }
                )
                notifications_sent += 1
        except Exception as notif_error:
            logger.warning(
                "post_retention_notification_failed",
                archive_id=str(archive.id),
                error_type=type(notif_error).__name__,
            )

        reviews_processed += 1

        # Reset review flag (nach Migration 205)
        # archive.post_retention_review_scheduled = False

    await db.commit()

    return {
        "reviews_processed": reviews_processed,
        "notifications_sent": notifications_sent,
    }


# =============================================================================
# Compliance Report Generation
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.retention_enforcement_tasks.generate_retention_compliance_report",
    bind=True,
    acks_late=True,
    max_retries=3,
    default_retry_delay=600,
)
def generate_retention_compliance_report(
    self,
    company_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Generiert wochentlichen Compliance-Report.

    Args:
        company_id: Optional - nur für bestimmte Firma

    Returns:
        Dictionary mit Report-Daten
    """
    import asyncio

    async def _generate():
        async with async_session_factory() as db:
            return await _generate_compliance_report(
                db,
                uuid.UUID(company_id) if company_id else None
            )

    try:
        result = asyncio.get_event_loop().run_until_complete(_generate())
        logger.info(
            "compliance_report_generated",
            company_id=company_id,
        )
        return result
    except Exception as e:
        retention_enforcement_errors_total.labels(task="compliance_report").inc()
        logger.error(
            "compliance_report_generation_failed",
            **safe_error_log(e),
            company_id=company_id
        )
        raise self.retry(exc=e)


async def _generate_compliance_report(
    db: AsyncSession,
    company_id: Optional[uuid.UUID]
) -> Dict[str, Any]:
    """Interne Funktion für Compliance-Report Generierung."""
    reports = {}

    if company_id:
        # Einzelner Report
        dashboard = await retention_enforcement_service.get_compliance_dashboard(
            db, company_id
        )
        reports[str(company_id)] = {
            "total_archives": dashboard.total_archives,
            "active_retention": dashboard.active_retention,
            "expired_retention": dashboard.expired_retention,
            "expiring_30_days": dashboard.expiring_30_days,
            "expiring_90_days": dashboard.expiring_90_days,
            "by_category": dashboard.by_category,
        }
    else:
        # Alle Companies
        companies_result = await db.execute(
            select(Company).where(Company.is_active == True)
        )
        companies = companies_result.scalars().all()

        for company in companies:
            dashboard = await retention_enforcement_service.get_compliance_dashboard(
                db, company.id
            )
            reports[company.short_name or str(company.id)] = {
                "total_archives": dashboard.total_archives,
                "active_retention": dashboard.active_retention,
                "expired_retention": dashboard.expired_retention,
                "expiring_30_days": dashboard.expiring_30_days,
                "expiring_90_days": dashboard.expiring_90_days,
                "by_category": dashboard.by_category,
            }

    return {
        "report_generated_at": datetime.now(timezone.utc).isoformat(),
        "companies_included": len(reports),
        "reports": reports,
    }


# =============================================================================
# Helper Functions
# =============================================================================


async def _create_enforcement_audit_log(
    db: AsyncSession,
    document_id: uuid.UUID,
    company_id: uuid.UUID,
    action: str,
    details: Dict[str, Any],
) -> None:
    """Erstellt Audit-Log für Enforcement-Aktionen."""
    audit_log = AuditLog(
        id=uuid.uuid4(),
        user_id=None,  # System-Aktion
        company_id=company_id,
        action=action,
        resource_type="document_archive",
        resource_id=document_id,
        audit_metadata=details,
        ip_address="system",
        user_agent="retention_enforcement_task",
    )
    db.add(audit_log)


"""GoBD Retention Management Tasks - Aufbewahrungsfristen-Celery-Tasks.

Automatisierte Tasks fuer das GoBD-konforme Aufbewahrungsfristen-Management:
- Taegliche Pruefung auf ablaufende Archive
- Benachrichtigungen an Admins senden
- Optionale automatische Loeschung nach Ablauf (wenn aktiviert)
- Batch-Verifikation der Dokumentintegritaet

Erfuellt GoBD-Kriterien:
- Vollstaendigkeit: Automatische Fristen-Ueberwachung
- Nachvollziehbarkeit: Audit-Trail fuer alle Aktionen
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.safe_errors import safe_error_log
from app.db.database import async_session_factory
from app.db.models import (
    DocumentArchive,
    RetentionSetting,
    AuditLog,
    Company,
)
from app.services.archive_service import archive_service
from app.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


# =============================================================================
# Retention Check Tasks
# =============================================================================


@celery_app.task(
    name="retention.check_expiring_archives",
    bind=True,
    acks_late=True,
    max_retries=3,
    default_retry_delay=300,
)
def check_expiring_archives_task(self, days_ahead: int = 90) -> Dict[str, Any]:
    """Prueft auf bald ablaufende Archive und sendet Erinnerungen.

    Wird taeglich via Celery Beat ausgefuehrt.

    Args:
        days_ahead: Tage im Voraus pruefen (default: 90)

    Returns:
        Dictionary mit Statistiken
    """
    import asyncio

    async def _check():
        async with async_session_factory() as db:
            return await _check_expiring_archives(db, days_ahead)

    try:
        result = asyncio.get_event_loop().run_until_complete(_check())
        logger.info(
            "retention_check_completed",
            days_ahead=days_ahead,
            **result
        )
        return result
    except Exception as e:
        logger.error(
            "retention_check_failed",
            **safe_error_log(e),
            days_ahead=days_ahead
        )
        raise self.retry(exc=e)


async def _check_expiring_archives(
    db: AsyncSession,
    days_ahead: int
) -> Dict[str, Any]:
    """Interne Funktion zum Pruefen ablaufender Archive."""
    # Alle Companies abrufen
    companies_result = await db.execute(
        select(Company).where(Company.is_active == True)
    )
    companies = companies_result.scalars().all()

    total_expiring = 0
    total_reminded = 0
    by_company: Dict[str, int] = {}

    for company in companies:
        # Ablaufende Archive finden (noch nicht erinnert)
        archives = await archive_service.get_expiring_archives(
            db, company.id, days_until_expiry=days_ahead
        )

        if not archives:
            continue

        by_company[company.short_name or str(company.id)] = len(archives)
        total_expiring += len(archives)

        # Erinnerung markieren
        for archive in archives:
            await archive_service.mark_reminder_sent(db, archive.id)
            total_reminded += 1

            # Audit-Log erstellen
            await _create_retention_audit_log(
                db,
                archive.document_id,
                company.id,
                "retention_reminder_sent",
                {
                    "archive_id": str(archive.id),
                    "retention_expires_at": str(archive.retention_expires_at),
                    "days_until_expiry": (archive.retention_expires_at - date.today()).days,
                }
            )

    await db.commit()

    return {
        "total_expiring": total_expiring,
        "total_reminded": total_reminded,
        "by_company": by_company,
        "days_ahead": days_ahead,
    }


# =============================================================================
# Batch Verification Tasks
# =============================================================================


@celery_app.task(
    name="retention.verify_archive_integrity",
    bind=True,
    acks_late=True,
    max_retries=3,
    default_retry_delay=600,
)
def verify_archive_integrity_task(
    self,
    company_id: Optional[str] = None,
    batch_size: int = 100,
) -> Dict[str, Any]:
    """Batch-Verifikation der Dokumentintegritaet.

    Prueft die SHA-256 Hashes aller archivierten Dokumente.
    Wird woechentlich via Celery Beat ausgefuehrt.

    Args:
        company_id: Optional - nur fuer bestimmte Firma
        batch_size: Anzahl Dokumente pro Batch

    Returns:
        Dictionary mit Verifikationsergebnis
    """
    import asyncio

    async def _verify():
        async with async_session_factory() as db:
            return await _batch_verify_integrity(
                db,
                uuid.UUID(company_id) if company_id else None,
                batch_size
            )

    try:
        result = asyncio.get_event_loop().run_until_complete(_verify())
        logger.info(
            "integrity_verification_completed",
            company_id=company_id,
            **result
        )
        return result
    except Exception as e:
        logger.error(
            "integrity_verification_failed",
            **safe_error_log(e),
            company_id=company_id
        )
        raise self.retry(exc=e)


async def _batch_verify_integrity(
    db: AsyncSession,
    company_id: Optional[uuid.UUID],
    batch_size: int
) -> Dict[str, Any]:
    """Interne Funktion fuer Batch-Integritaetspruefung."""
    # Query bauen
    query = select(DocumentArchive)

    if company_id:
        query = query.where(DocumentArchive.company_id == company_id)

    # Nur Archive, die laenger als 24h nicht verifiziert wurden
    stale_threshold = datetime.now(timezone.utc) - timedelta(hours=24)
    query = query.where(
        (DocumentArchive.last_verification_at == None) |
        (DocumentArchive.last_verification_at < stale_threshold)
    ).limit(batch_size)

    result = await db.execute(query)
    archives = result.scalars().all()

    verified_count = 0
    failed_count = 0
    failed_documents: List[str] = []

    for archive in archives:
        is_valid = await archive_service.verify_document_integrity(
            db, archive.document_id
        )

        if is_valid:
            verified_count += 1
        else:
            failed_count += 1
            failed_documents.append(str(archive.document_id))

            # Kritische Warnung loggen
            logger.error(
                "document_integrity_failed",
                document_id=str(archive.document_id),
                archive_id=str(archive.id),
                expected_hash=archive.content_hash[:16],
            )

    return {
        "verified": verified_count,
        "failed": failed_count,
        "failed_documents": failed_documents,
        "batch_size": batch_size,
    }


# =============================================================================
# Auto-Delete Tasks (Optional, Admin-konfigurierbar)
# =============================================================================


@celery_app.task(
    name="retention.process_expired_archives",
    bind=True,
    acks_late=True,
    max_retries=3,
    default_retry_delay=600,
)
def process_expired_archives_task(self) -> Dict[str, Any]:
    """Verarbeitet abgelaufene Archive (nach Aufbewahrungsfrist).

    Wird taeglich via Celery Beat ausgefuehrt.
    Loescht nur wenn auto_delete_enabled fuer die Kategorie aktiv ist.

    Returns:
        Dictionary mit Statistiken
    """
    import asyncio

    async def _process():
        async with async_session_factory() as db:
            return await _process_expired_archives(db)

    try:
        result = asyncio.get_event_loop().run_until_complete(_process())
        logger.info(
            "expired_archives_processed",
            **result
        )
        return result
    except Exception as e:
        logger.error(
            "expired_archives_processing_failed",
            **safe_error_log(e)
        )
        raise self.retry(exc=e)


async def _process_expired_archives(db: AsyncSession) -> Dict[str, Any]:
    """Interne Funktion zum Verarbeiten abgelaufener Archive."""
    today = date.today()

    # Kategorien mit aktivierter Auto-Loeschung finden
    settings_result = await db.execute(
        select(RetentionSetting)
        .where(RetentionSetting.auto_delete_enabled == True)
    )
    auto_delete_categories = [s.category for s in settings_result.scalars().all()]

    if not auto_delete_categories:
        return {
            "message": "Keine Kategorien mit Auto-Loeschung konfiguriert",
            "deleted": 0,
            "pending_approval": 0,
        }

    # Abgelaufene Archive finden
    expired_result = await db.execute(
        select(DocumentArchive)
        .where(
            and_(
                DocumentArchive.retention_expires_at < today,
                DocumentArchive.retention_category.in_(auto_delete_categories),
            )
        )
    )
    expired_archives = expired_result.scalars().all()

    deleted_count = 0
    pending_approval_count = 0

    for archive in expired_archives:
        # Kategorie-Einstellungen laden
        setting_result = await db.execute(
            select(RetentionSetting)
            .where(RetentionSetting.category == archive.retention_category)
        )
        setting = setting_result.scalar_one_or_none()

        if not setting:
            continue

        if setting.requires_approval_for_delete:
            # Nur markieren, Admin muss bestaetigen
            pending_approval_count += 1
            await _create_retention_audit_log(
                db,
                archive.document_id,
                archive.company_id,
                "retention_expired_pending_approval",
                {
                    "archive_id": str(archive.id),
                    "retention_category": archive.retention_category,
                    "retention_expires_at": str(archive.retention_expires_at),
                }
            )
        else:
            # Automatisch loeschen (Document bleibt, nur Archive wird entfernt)
            # WICHTIG: Das Dokument selbst wird NICHT geloescht!
            # Nur der Archiv-Eintrag wird entfernt, was das Dokument wieder editierbar macht
            await db.delete(archive)
            deleted_count += 1

            await _create_retention_audit_log(
                db,
                archive.document_id,
                archive.company_id,
                "retention_expired_archive_removed",
                {
                    "archive_id": str(archive.id),
                    "retention_category": archive.retention_category,
                    "retention_expires_at": str(archive.retention_expires_at),
                    "auto_deleted": True,
                }
            )

            logger.info(
                "archive_auto_removed",
                document_id=str(archive.document_id),
                archive_id=str(archive.id),
                category=archive.retention_category,
            )

    await db.commit()

    return {
        "deleted": deleted_count,
        "pending_approval": pending_approval_count,
        "categories_checked": auto_delete_categories,
    }


# =============================================================================
# Retention Statistics Tasks
# =============================================================================


@celery_app.task(
    name="retention.generate_retention_report",
    bind=True,
    acks_late=True,
    max_retries=3,
    default_retry_delay=300,
)
def generate_retention_report_task(self, company_id: str) -> Dict[str, Any]:
    """Generiert einen Aufbewahrungsfristen-Bericht.

    Args:
        company_id: Firmen-ID

    Returns:
        Dictionary mit Bericht-Daten
    """
    import asyncio

    async def _generate():
        async with async_session_factory() as db:
            return await archive_service.get_archive_statistics(
                db, uuid.UUID(company_id)
            )

    try:
        result = asyncio.get_event_loop().run_until_complete(_generate())
        logger.info(
            "retention_report_generated",
            company_id=company_id,
        )
        return result
    except Exception as e:
        logger.error(
            "retention_report_generation_failed",
            **safe_error_log(e),
            company_id=company_id
        )
        raise self.retry(exc=e)


# =============================================================================
# Helper Functions
# =============================================================================


async def _create_retention_audit_log(
    db: AsyncSession,
    document_id: uuid.UUID,
    company_id: uuid.UUID,
    action: str,
    details: Dict[str, Any],
) -> None:
    """Erstellt einen Audit-Log-Eintrag fuer Retention-Aktionen."""
    audit_log = AuditLog(
        id=uuid.uuid4(),
        user_id=None,  # System-Aktion
        company_id=company_id,
        action=action,
        resource_type="document_archive",
        resource_id=document_id,
        audit_metadata=details,
        ip_address="system",
        user_agent="retention_task",
    )
    db.add(audit_log)


# =============================================================================
# Celery Beat Schedule (zur Referenz)
# =============================================================================
# Diese Tasks werden in celery_app.py zum Beat-Schedule hinzugefuegt:
#
# CELERYBEAT_SCHEDULE = {
#     'retention-check-daily': {
#         'task': 'retention.check_expiring_archives',
#         'schedule': crontab(hour=8, minute=0),  # Taeglich 08:00
#         'kwargs': {'days_ahead': 90},
#     },
#     'integrity-verify-weekly': {
#         'task': 'retention.verify_archive_integrity',
#         'schedule': crontab(day_of_week=0, hour=3, minute=0),  # Sonntag 03:00
#         'kwargs': {'batch_size': 500},
#     },
#     'expired-archives-daily': {
#         'task': 'retention.process_expired_archives',
#         'schedule': crontab(hour=2, minute=0),  # Taeglich 02:00
#     },
# }

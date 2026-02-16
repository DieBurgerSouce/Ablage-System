"""GoBD Compliance Tasks - Celery Tasks für GoBD-konforme Dokumentenverarbeitung.

Automatisierte Tasks für:
- Audit-Chain Verifikation (Blockchain-ähnliche Hash-Kette)
- Integritätsprüfungen der Archive
- RFC 3161 Zeitstempel-Anforderungen (batched)

GoBD = Grundsätze zur ordnungsmaessigen Führung und Aufbewahrung
       von Buechern, Aufzeichnungen und Unterlagen in elektronischer
       Form sowie zum Datenzugriff
"""

import uuid
from datetime import datetime, timedelta
from typing import Optional

import structlog
from celery import shared_task

from app.core.safe_errors import safe_error_log
from app.db.session import async_session_factory
from app.db.models import Company
from app.workers.celery_app import celery_app
from sqlalchemy import select

logger = structlog.get_logger(__name__)


# =============================================================================
# Audit Chain Verification Tasks
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.gobd_compliance_tasks.verify_audit_chain_task",
    bind=True,
    max_retries=3,
    default_retry_delay=300,
)
def verify_audit_chain_task(
    self,
    company_id: Optional[str] = None,
) -> dict:
    """Verifiziert die Integrität der Audit-Chain.

    Prüft ob:
    - Alle Sequenznummern lückenlos sind
    - Alle Hashes korrekt verkette sind
    - Keine Einträge manipuliert wurden

    Wird wöchentlich via Celery Beat ausgeführt.

    Args:
        company_id: Optional - nur für bestimmte Firma

    Returns:
        Dictionary mit Verifikationsergebnis
    """
    import asyncio

    async def _verify():
        async with async_session_factory() as db:
            return await _verify_audit_chains(
                db,
                uuid.UUID(company_id) if company_id else None,
            )

    try:
        result = asyncio.get_event_loop().run_until_complete(_verify())
        logger.info(
            "audit_chain_verification_completed",
            company_id=company_id,
            **result
        )
        return result
    except Exception as e:
        logger.error(
            "audit_chain_verification_failed",
            **safe_error_log(e),
            company_id=company_id
        )
        raise self.retry(exc=e)


async def _verify_audit_chains(
    db,
    company_id: Optional[uuid.UUID],
) -> dict:
    """Interne Funktion für Audit-Chain Verifikation."""
    from app.services.compliance import audit_chain_service

    results = {
        "verified_companies": 0,
        "failed_companies": 0,
        "total_entries_verified": 0,
        "failures": [],
    }

    # Companies zum Prüfen finden
    if company_id:
        company_ids = [company_id]
    else:
        # Alle aktiven Companies prüfen
        result = await db.execute(
            select(Company.id).where(Company.is_active == True)
        )
        company_ids = [row[0] for row in result.fetchall()]

    for cid in company_ids:
        try:
            verification_result = await audit_chain_service.verify_chain(
                db, cid
            )

            if verification_result.is_valid:
                results["verified_companies"] += 1
                results["total_entries_verified"] += verification_result.verified_entries
            else:
                results["failed_companies"] += 1
                results["failures"].append({
                    "company_id": str(cid),
                    "broken_at": verification_result.broken_at_sequence,
                    "error": verification_result.error_message,
                })

                # Kritischer Fehler - Manipulationsverdacht!
                logger.error(
                    "audit_chain_integrity_violation",
                    company_id=str(cid),
                    broken_at_sequence=verification_result.broken_at_sequence,
                    error=verification_result.error_message,
                    alert_level="critical",
                )
        except Exception as e:
            results["failed_companies"] += 1
            results["failures"].append({
                "company_id": str(cid),
                "error": safe_error_detail(e, "Vorgang"),
            })
            logger.error(
                "audit_chain_verification_error",
                company_id=str(cid),
                **safe_error_log(e),
            )

    return results


# =============================================================================
# Archive Integrity Check Tasks (with Audit Chain logging)
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.gobd_compliance_tasks.batch_integrity_check_task",
    bind=True,
    max_retries=3,
    default_retry_delay=600,
)
def batch_integrity_check_task(
    self,
    company_id: Optional[str] = None,
    batch_size: int = 50,
) -> dict:
    """Batch-Integritätsprüfung mit Audit-Chain-Logging.

    Prüft Archive und protokolliert Ergebnisse in der Audit-Chain.

    Args:
        company_id: Optional - nur für bestimmte Firma
        batch_size: Anzahl Archive pro Batch

    Returns:
        Dictionary mit Prüfungsergebnis
    """
    import asyncio

    async def _check():
        async with async_session_factory() as db:
            return await _batch_integrity_check(
                db,
                uuid.UUID(company_id) if company_id else None,
                batch_size
            )

    try:
        result = asyncio.get_event_loop().run_until_complete(_check())
        logger.info(
            "batch_integrity_check_completed",
            company_id=company_id,
            **result
        )
        return result
    except Exception as e:
        logger.error(
            "batch_integrity_check_failed",
            **safe_error_log(e),
            company_id=company_id
        )
        raise self.retry(exc=e)


async def _batch_integrity_check(
    db,
    company_id: Optional[uuid.UUID],
    batch_size: int
) -> dict:
    """Interne Funktion für Batch-Integritätsprüfung."""
    from app.db.models import DocumentArchive
    from app.services.compliance import gobd_archive_service, audit_chain_service
    from app.services.compliance.audit_chain_service import ChainEntry
    from app.db.bpmn_models.gobd import AuditChainEventType

    # Query für Archive die geprüft werden sollen
    query = select(DocumentArchive)

    if company_id:
        query = query.where(DocumentArchive.company_id == company_id)

    # Priorisiere Archive, die länger nicht geprüft wurden
    stale_threshold = datetime.now() - timedelta(days=7)
    query = query.where(
        (DocumentArchive.last_verification_at == None) |
        (DocumentArchive.last_verification_at < stale_threshold)
    ).limit(batch_size)

    result = await db.execute(query)
    archives = result.scalars().all()

    passed = 0
    failed = 0
    errors = []

    # Storage Service für MinIO-Zugriff
    from app.services.storage_service import StorageService
    storage = StorageService()

    for archive in archives:
        try:
            # Dokument aus MinIO laden (wenn storage_path vorhanden)
            document_content = None
            if archive.storage_path:
                try:
                    document_content = await storage.download_document(
                        archive.storage_path
                    )
                except Exception as storage_err:
                    logger.warning(
                        "archive_storage_load_failed",
                        archive_id=str(archive.id),
                        storage_path=archive.storage_path,
                        error_type=type(storage_err).__name__,
                    )
                    # Continue with None - integrity check will use stored hash

            # Integritätsprüfung durchführen
            check_result = await gobd_archive_service.verify_archive_integrity(
                db,
                archive.id,
                archive.company_id,
                document_content=document_content,
                record_check=True,
            )

            # In Audit-Chain protokollieren
            if check_result.hash_match:
                passed += 1
                event_type = AuditChainEventType.INTEGRITY_CHECK_PASSED
            else:
                failed += 1
                event_type = AuditChainEventType.INTEGRITY_CHECK_FAILED
                errors.append({
                    "archive_id": str(archive.id),
                    "expected": check_result.expected_hash[:16] + "...",
                    "actual": check_result.actual_hash[:16] + "..." if check_result.actual_hash else None,
                })

            entry = ChainEntry(
                event_type=event_type.value,
                event_data={
                    "archive_id": str(archive.id),
                    "check_type": "batch_verification",
                    "hash_match": check_result.hash_match,
                    "duration_ms": check_result.duration_ms,
                },
                document_id=archive.document_id,
            )
            await audit_chain_service.append_entry(
                db, archive.company_id, entry
            )

        except Exception as e:
            failed += 1
            errors.append({
                "archive_id": str(archive.id),
                "error": safe_error_detail(e, "Vorgang"),
            })
            logger.error(
                "archive_integrity_check_error",
                archive_id=str(archive.id),
                **safe_error_log(e),
            )

    await db.commit()

    return {
        "checked": passed + failed,
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "batch_size": batch_size,
    }


# =============================================================================
# Chain Statistics Task
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.gobd_compliance_tasks.generate_chain_statistics_task",
    bind=True,
    max_retries=2,
)
def generate_chain_statistics_task(self, company_id: str) -> dict:
    """Generiert Statistiken für die Audit-Chain.

    Args:
        company_id: Firmen-ID

    Returns:
        Dictionary mit Statistiken
    """
    import asyncio

    async def _stats():
        async with async_session_factory() as db:
            from app.services.compliance import audit_chain_service
            return await audit_chain_service.get_chain_statistics(
                db, uuid.UUID(company_id)
            )

    try:
        result = asyncio.get_event_loop().run_until_complete(_stats())
        return result
    except Exception as e:
        logger.error(
            "chain_statistics_failed",
            **safe_error_log(e),
            company_id=company_id
        )
        raise self.retry(exc=e)


# =============================================================================
# Retention Warning Tasks
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.gobd_compliance_tasks.check_retention_warnings_task",
    bind=True,
    max_retries=3,
)
def check_retention_warnings_task(self) -> dict:
    """Prüft auf Archive mit bevorstehenden Aufbewahrungsfristen.

    Sendet Warnungen entsprechend der RetentionPolicy-Einstellungen.

    Returns:
        Dictionary mit Warn-Statistiken
    """
    import asyncio

    async def _check():
        async with async_session_factory() as db:
            return await _check_retention_warnings(db)

    try:
        result = asyncio.get_event_loop().run_until_complete(_check())
        logger.info("retention_warnings_checked", **result)
        return result
    except Exception as e:
        logger.error("retention_warnings_check_failed", **safe_error_log(e))
        raise self.retry(exc=e)


async def _check_retention_warnings(db) -> dict:
    """Interne Funktion für Retention-Warnungen."""
    from app.services.compliance import retention_service

    results = {
        "companies_checked": 0,
        "warnings_sent": 0,
        "critical_warnings": 0,
    }

    # Alle aktiven Companies
    company_result = await db.execute(
        select(Company.id).where(Company.is_active == True)
    )
    company_ids = [row[0] for row in company_result.fetchall()]

    for cid in company_ids:
        results["companies_checked"] += 1

        try:
            expiring = await retention_service.get_expiring_archives(
                db, cid
            )

            for archive_info in expiring:
                # Warnung oder kritische Warnung
                if archive_info.get("is_critical"):
                    results["critical_warnings"] += 1
                else:
                    results["warnings_sent"] += 1

                # Send notification via Slack
                try:
                    from app.services.slack_service import SlackService, SlackNotificationType, SlackMessagePriority

                    slack = SlackService()
                    if slack.is_enabled:
                        priority = SlackMessagePriority.URGENT if archive_info.get("is_critical") else SlackMessagePriority.HIGH
                        await slack.send_notification(
                            notification_type=SlackNotificationType.SYSTEM_ALERT,
                            title="GoBD Aufbewahrungsfrist läuft ab",
                            message=f"Archiv {archive_info.get('archive_id', 'N/A')} erreicht Ende der Aufbewahrungsfrist in {archive_info.get('days_remaining', 0)} Tagen.",
                            priority=priority,
                            context={
                                "archive_id": archive_info.get("archive_id"),
                                "expires_at": archive_info.get("expires_at"),
                                "document_count": archive_info.get("document_count"),
                                "retention_policy": archive_info.get("policy_name"),
                            }
                        )
                except Exception as notification_error:
                    logger.warning(
                        "retention_notification_failed",
                        archive_id=archive_info.get("archive_id"),
                        error_type=type(notification_error).__name__
                    )

        except Exception as e:
            logger.error(
                "retention_warning_check_error",
                company_id=str(cid),
                **safe_error_log(e),
            )

    return results


# =============================================================================
# GDPR Breach Notification Tasks (Art. 33-34)
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.gobd_compliance_tasks.check_breach_deadlines_task",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def check_breach_deadlines_task(self) -> dict:
    """Prüft alle 72-Stunden-Deadlines für Datenschutzverletzungen.

    KRITISCH: Muss regelmäßig laufen um DSGVO-Fristen einzuhalten!

    Prüft:
    - Abgelaufene Deadlines (SOFORT Alarm)
    - Kritische Deadlines (<12h)
    - Warnungen (<24h)

    Wird stündlich via Celery Beat ausgeführt.

    Returns:
        Dictionary mit Deadline-Status
    """
    import asyncio

    async def _check():
        async with async_session_factory() as db:
            return await _check_all_breach_deadlines(db)

    try:
        result = asyncio.get_event_loop().run_until_complete(_check())

        # Bei kritischen Alerts explizit loggen
        if result.get("critical_count", 0) > 0:
            logger.critical(
                "breach_deadlines_critical",
                critical_count=result["critical_count"],
                overdue_count=result.get("overdue_count", 0),
                security_event=True,
            )

        logger.info("breach_deadline_check_completed", **result)
        return result

    except Exception as e:
        logger.error("breach_deadline_check_failed", **safe_error_log(e))
        raise self.retry(exc=e)


async def _check_all_breach_deadlines(db) -> dict:
    """Interne Funktion für Breach-Deadline-Prüfung."""
    from app.services.compliance import get_breach_notification_service

    service = get_breach_notification_service()
    alerts = await service.check_deadline_alerts(db)

    results = {
        "total_alerts": len(alerts),
        "overdue_count": 0,
        "critical_count": 0,
        "warning_count": 0,
        "alerts": [],
    }

    for alert in alerts:
        severity = alert.get("severity", "medium")

        if "overdue" in alert.get("message", "").lower():
            results["overdue_count"] += 1
        elif severity == "critical" or severity == "high":
            results["critical_count"] += 1
        else:
            results["warning_count"] += 1

        results["alerts"].append({
            "breach_id": alert["breach_id"],
            "severity": severity,
            "message": alert["message"],
        })

        # Sende Benachrichtigungen bei kritischen Deadlines
        if severity in ["critical", "high"]:
            await _send_breach_deadline_notification(db, alert)

    return results


async def _send_breach_deadline_notification(db, alert: dict) -> None:
    """Sendet Benachrichtigung bei kritischer Breach-Deadline."""
    try:
        from app.services.notification_service import NotificationService

        service = NotificationService()
        await service.send_admin_alert(
            subject=f"DSGVO FRISTWARNUNG: Breach {alert['breach_id']}",
            message=alert.get("message", "72-Stunden-Frist läuft ab!"),
            priority="critical",
        )
    except Exception as e:
        logger.warning(
            "breach_deadline_notification_failed",
            breach_id=alert.get("breach_id"),
            **safe_error_log(e),
        )


@celery_app.task(
    name="app.workers.tasks.gobd_compliance_tasks.daily_breach_report_task",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
)
def daily_breach_report_task(self) -> dict:
    """Erstellt täglichen Bericht über Datenschutzverletzungen.

    Enthält:
    - Offene Breaches
    - Status-Zusammenfassung
    - Ausstehende Deadlines
    - Abgeschlossene Breaches (letzte 24h)

    Wird täglich via Celery Beat ausgeführt.

    Returns:
        Dictionary mit Tagesbericht
    """
    import asyncio

    async def _report():
        async with async_session_factory() as db:
            return await _generate_daily_breach_report(db)

    try:
        result = asyncio.get_event_loop().run_until_complete(_report())
        logger.info("daily_breach_report_generated", **result)
        return result
    except Exception as e:
        logger.error("daily_breach_report_failed", **safe_error_log(e))
        raise self.retry(exc=e)


async def _generate_daily_breach_report(db) -> dict:
    """Generiert täglichen Breach-Bericht."""
    from app.services.compliance import get_breach_notification_service, BreachStatus

    service = get_breach_notification_service()

    # Alle Breaches holen
    all_breaches, total = await service.list_breaches(db, limit=500)

    report = {
        "report_date": datetime.now().isoformat(),
        "total_breaches": total,
        "by_status": {},
        "by_severity": {},
        "pending_deadlines": 0,
        "overdue": 0,
        "closed_last_24h": 0,
    }

    cutoff = datetime.now() - timedelta(hours=24)

    for breach in all_breaches:
        # Nach Status zählen
        status = breach.status.value
        report["by_status"][status] = report["by_status"].get(status, 0) + 1

        # Nach Schweregrad zählen
        severity = breach.severity.value
        report["by_severity"][severity] = report["by_severity"].get(severity, 0) + 1

        # Ausstehende Deadlines
        if breach.authority_notification.value == "pending":
            report["pending_deadlines"] += 1

            # Überfällig?
            if breach.deadline_72h < datetime.now():
                report["overdue"] += 1

        # In letzten 24h geschlossen
        if breach.status in [BreachStatus.RESOLVED, BreachStatus.CLOSED]:
            if hasattr(breach, 'contained_at') and breach.contained_at:
                if breach.contained_at.replace(tzinfo=None) >= cutoff:
                    report["closed_last_24h"] += 1

    return report


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
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, TypedDict

import structlog
from celery import shared_task
from prometheus_client import Counter

from app.core.safe_errors import safe_error_log, safe_error_detail
from app.db.session import async_session_factory
from app.db.models import Company
from app.workers.celery_app import celery_app
from sqlalchemy import select

logger = structlog.get_logger(__name__)


class ChainVerificationResult(TypedDict):
    verified_companies: int
    failed_companies: int
    total_entries_verified: int
    failures: List[Dict[str, Any]]


class IntegrityCheckResult(TypedDict):
    checked: int
    passed: int
    failed: int
    errors: List[Dict[str, Any]]
    batch_size: int


class RetentionWarningResult(TypedDict):
    companies_checked: int
    warnings_sent: int
    critical_warnings: int


class BreachDeadlineResult(TypedDict):
    total_alerts: int
    overdue_count: int
    critical_count: int
    warning_count: int
    alerts: List[Dict[str, str]]


class DailyBreachReport(TypedDict):
    report_date: str
    total_breaches: int
    by_status: Dict[str, int]
    by_severity: Dict[str, int]
    pending_deadlines: int
    overdue: int
    closed_last_24h: int


# Prometheus Metriken
CHAIN_VERIFICATION_TOTAL = Counter(
    "gobd_chain_verification_total",
    "Ergebnis der Audit-Chain Verifikation",
    ["status"],
)


# =============================================================================
# Audit Chain Verification Tasks
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.gobd_compliance_tasks.verify_audit_chain_task",
    bind=True,
    max_retries=3,
    default_retry_delay=300,
    time_limit=600,
    soft_time_limit=540,
)
def verify_audit_chain_task(
    self,
    company_id: Optional[str] = None,
) -> ChainVerificationResult:
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
        result = asyncio.run(_verify())
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
) -> ChainVerificationResult:
    """Interne Funktion für Audit-Chain Verifikation."""
    from app.services.compliance.audit_chain_service import (
        audit_chain_service,
        ChainVerificationStatus,
    )

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

            if verification_result.status in (
                ChainVerificationStatus.VALID,
                ChainVerificationStatus.EMPTY,
            ):
                results["verified_companies"] += 1
                results["total_entries_verified"] += verification_result.verified_entries
                CHAIN_VERIFICATION_TOTAL.labels(status="valid").inc()
            else:
                results["failed_companies"] += 1
                results["failures"].append({
                    "company_id": str(cid),
                    "broken_at": verification_result.broken_at_sequence,
                    "error": verification_result.error_message,
                })
                CHAIN_VERIFICATION_TOTAL.labels(status="broken").inc()

                # Kritischer Fehler - Manipulationsverdacht!
                logger.error(
                    "audit_chain_integrity_violation",
                    company_id=str(cid),
                    broken_at_sequence=verification_result.broken_at_sequence,
                    error=verification_result.error_message,
                    alert_level="critical",
                )

                # Alert erstellen via Alert Center
                await _create_chain_broken_alert(db, cid, verification_result)

        except Exception as e:
            results["failed_companies"] += 1
            results["failures"].append({
                "company_id": str(cid),
                "error": safe_error_detail(e, "Vorgang"),
            })
            CHAIN_VERIFICATION_TOTAL.labels(status="error").inc()
            logger.error(
                "audit_chain_verification_error",
                company_id=str(cid),
                **safe_error_log(e),
            )

    return results


async def _create_chain_broken_alert(db, company_id: uuid.UUID, verification_result) -> None:
    """Erstellt einen CRITICAL Alert bei gebrochener Audit-Chain."""
    try:
        from app.services.alert_center_service import AlertCenterService

        alert_service = AlertCenterService(db)
        await alert_service.create_alert(
            company_id=company_id,
            alert_type="gobd_chain_integrity",
            severity="critical",
            title="GoBD Audit-Chain Integritaetsverletzung",
            message=(
                f"Die Audit-Chain ist bei Sequenz {verification_result.broken_at_sequence} "
                f"gebrochen: {verification_result.error_message}. "
                "SOFORTIGE PRUEFUNG ERFORDERLICH - Moegliche Manipulation!"
            ),
            metadata={
                "broken_at_sequence": verification_result.broken_at_sequence,
                "broken_entry_id": str(verification_result.broken_entry_id)
                if verification_result.broken_entry_id else None,
                "verification_time_ms": verification_result.verification_time_ms,
            },
        )
    except Exception as alert_err:
        logger.warning(
            "chain_broken_alert_creation_failed",
            company_id=str(company_id),
            error_type=type(alert_err).__name__,
        )


# =============================================================================
# Archive Integrity Check Tasks (with Audit Chain logging)
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.gobd_compliance_tasks.batch_integrity_check_task",
    bind=True,
    max_retries=3,
    default_retry_delay=600,
    time_limit=900,
    soft_time_limit=840,
)
def batch_integrity_check_task(
    self,
    company_id: Optional[str] = None,
    batch_size: int = 50,
) -> IntegrityCheckResult:
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
        result = asyncio.run(_check())
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
) -> IntegrityCheckResult:
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
    stale_threshold = datetime.now(timezone.utc) - timedelta(days=7)
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
    time_limit=300,
    soft_time_limit=270,
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
        result = asyncio.run(_stats())
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
    time_limit=600,
    soft_time_limit=540,
)
def check_retention_warnings_task(self) -> RetentionWarningResult:
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
        result = asyncio.run(_check())
        logger.info("retention_warnings_checked", **result)
        return result
    except Exception as e:
        logger.error("retention_warnings_check_failed", **safe_error_log(e))
        raise self.retry(exc=e)


async def _check_retention_warnings(db) -> RetentionWarningResult:
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
    time_limit=300,
    soft_time_limit=270,
)
def check_breach_deadlines_task(self) -> BreachDeadlineResult:
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
        result = asyncio.run(_check())

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


async def _check_all_breach_deadlines(db) -> BreachDeadlineResult:
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
    time_limit=600,
    soft_time_limit=540,
)
def daily_breach_report_task(self) -> DailyBreachReport:
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
        result = asyncio.run(_report())
        logger.info("daily_breach_report_generated", **result)
        return result
    except Exception as e:
        logger.error("daily_breach_report_failed", **safe_error_log(e))
        raise self.retry(exc=e)


async def _generate_daily_breach_report(db) -> DailyBreachReport:
    """Generiert täglichen Breach-Bericht."""
    from app.services.compliance import get_breach_notification_service, BreachStatus

    service = get_breach_notification_service()

    # Alle Breaches holen
    all_breaches, total = await service.list_breaches(db, limit=500)

    report = {
        "report_date": datetime.now(timezone.utc).isoformat(),
        "total_breaches": total,
        "by_status": {},
        "by_severity": {},
        "pending_deadlines": 0,
        "overdue": 0,
        "closed_last_24h": 0,
    }

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

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
            if breach.deadline_72h < datetime.now(timezone.utc):
                report["overdue"] += 1

        # In letzten 24h geschlossen
        if breach.status in [BreachStatus.RESOLVED, BreachStatus.CLOSED]:
            if hasattr(breach, 'contained_at') and breach.contained_at:
                if breach.contained_at.replace(tzinfo=None) >= cutoff:
                    report["closed_last_24h"] += 1

    return report


# =============================================================================
# GoBD-Auto-Archivierung des Eingangskanals (Neuausrichtung Welle D, Defekt 3)
# =============================================================================
#
# Die formale GoBD-Archivierung (GoBDArchiveService.archive_document ->
# DocumentArchive + SHA256 + Retention + Audit-Chain) passierte bisher NUR
# ueber manuelle API-Aufrufe (api/v1/archive.py). Fuer den Vollarchiv-
# Anspruch (Plan §2: jedes Eingangs-Dokument wird zeitnah revisionssicher
# archiviert) archiviert dieser Beat-Task (taeglich 03:30) automatisch alle
# Eingangskanal-Dokumente, die
#   (a) noch KEINEN DocumentArchive-Eintrag haben,
#   (b) aus dem Eingangskanal stammen (import_source in email/folder/
#       wa_we_altbestand) — odoo_mirror ist AUSGENOMMEN, der Spiegel
#       archiviert seine Dokumente selbst (odoo_mirror_service),
#   (c) aelter als GOBD_AUTO_ARCHIVE_GRACE_DAYS sind (Karenz, s. u.),
#   (d) fertig verarbeitet sind (status == "completed", OCR abgeschlossen).
#
# KARENZ-BEGRUENDUNG (GOBD_AUTO_ARCHIVE_GRACE_DAYS, Default 3 Tage):
# archive_document setzt Document.is_archived=True und legt einen
# DocumentArchive-Eintrag mit content_hash (SHA256) und RESTRICT-FK an.
# Die documents-Tabelle selbst hat KEINEN Unveraenderbarkeits-Trigger
# (Migration 151/234 betrifft domain_events und gobd_audit_chain), aber ab
# der Archivierung ist der INHALT faktisch eingefroren: die taegliche
# batch_integrity_check_task schlaegt bei nachtraeglichem Inhaltstausch fehl
# (Manipulationsverdacht-Alert), eine erneute Archivierung wirft ArchiveError,
# und der RESTRICT-FK verhindert das Loeschen des Dokuments. Die Karenz gibt
# dem Buero-Team deshalb ein Fenster fuer manuelle Korrekturen (falsche Datei,
# Neuscan), BEVOR der Zustand hash-fixiert wird.


class AutoArchiveResult(TypedDict):
    enabled: bool
    candidates: int
    archived: int
    skipped_no_content: int
    errors: int
    error_details: List[Dict[str, str]]


# Eingangskanal-Quellen, die automatisch archiviert werden.
# "odoo_mirror" fehlt hier BEWUSST (Mirror archiviert selbst).
AUTO_ARCHIVE_IMPORT_SOURCES = ("email", "folder", "wa_we_altbestand")

# Fallback-Kategorie: neutrale Beleg-Kategorie (10 Jahre §147 AO),
# wie scripts/import_wa_we.py.
AUTO_ARCHIVE_FALLBACK_CATEGORY = "receipt"

# Klassifikation -> GoBD-Retention-Kategorie. Gleiche Logik wie
# odoo_mirror_service.category_for_move_type: Rechnungen des EINGANGSkanals
# sind Eingangsrechnungen ("invoice_incoming"); die Odoo-Belege mit echter
# out_/in_-Unterscheidung spiegelt/archiviert der Mirror selbst. Alle
# Zielwerte existieren in retention_service.DEFAULT_RETENTION_PERIODS.
GOBD_CATEGORY_BY_DOCUMENT_TYPE: Dict[str, str] = {
    "invoice": "invoice_incoming",
    "credit_note": "invoice_incoming",
    "receipt": "receipt",
    "contract": "contract",
    "delivery_note": "delivery_note",
    "order": "order",
    "purchase_order": "order",
    "offer": "quotation",
    "bank_statement": "bank_statement",
    "tax_document": "tax_document",
    "letter": "correspondence",
}


def gobd_category_for_document_type(document_type: Optional[str]) -> str:
    """GoBD-Retention-Kategorie fuer eine Dokument-Klassifikation.

    Unbekannte/fehlende Klassifikationen fallen konservativ auf die
    neutrale Beleg-Kategorie "receipt" (10 Jahre §147 AO).
    """
    return GOBD_CATEGORY_BY_DOCUMENT_TYPE.get(
        (document_type or "").strip().lower(), AUTO_ARCHIVE_FALLBACK_CATEGORY
    )


def archive_document_date(document) -> date:
    """Belegdatum fuer die Fristberechnung.

    Bevorzugt ``document_metadata.periode`` ("JJJJ-MM", z. B. WA/WE-
    Altbestand -> Monatsletzter), sonst das Anlagedatum des Dokuments.
    """
    import calendar

    meta = document.document_metadata or {}
    periode = meta.get("periode") if isinstance(meta, dict) else None
    if isinstance(periode, str) and len(periode) == 7 and periode[4] == "-":
        try:
            year, month = int(periode[:4]), int(periode[5:7])
            return date(year, month, calendar.monthrange(year, month)[1])
        except (ValueError, IndexError):
            pass
    created = getattr(document, "created_at", None)
    if created is not None:
        return created.date()
    return datetime.now(timezone.utc).date()


def build_auto_archive_stmt(cutoff: datetime, batch_limit: int):
    """Selektions-Query fuer archivierungsfaellige Eingangs-Dokumente.

    Als eigene Funktion testbar (Karenz-Cutoff, odoo_mirror-Ausschluss,
    bereits-archiviert-Skip via NOT EXISTS auf document_archives).
    """
    from sqlalchemy import exists as sa_exists

    from app.db.models import Document, DocumentArchive, ProcessingStatus

    already_archived = (
        select(DocumentArchive.id)
        .where(DocumentArchive.document_id == Document.id)
    )

    return (
        select(Document)
        .where(
            Document.deleted_at.is_(None),
            Document.status == ProcessingStatus.COMPLETED.value,
            Document.created_at < cutoff,
            Document.document_metadata["import_source"]
            .as_string()
            .in_(list(AUTO_ARCHIVE_IMPORT_SOURCES)),
            ~sa_exists(already_archived),
        )
        .order_by(Document.created_at.asc())
        .limit(batch_limit)
    )


async def _run_gobd_auto_archive(db, batch_limit: int) -> AutoArchiveResult:
    """Interne Funktion: selektiert + archiviert mit Fehler-Isolation pro Dokument."""
    from app.core.config import settings
    from app.services.compliance.archive_service import GoBDArchiveService
    from app.services.storage_service import get_storage_service

    result: AutoArchiveResult = {
        "enabled": True,
        "candidates": 0,
        "archived": 0,
        "skipped_no_content": 0,
        "errors": 0,
        "error_details": [],
    }

    grace_days = int(settings.GOBD_AUTO_ARCHIVE_GRACE_DAYS)
    cutoff = datetime.now(timezone.utc) - timedelta(days=grace_days)

    documents = (
        (await db.execute(build_auto_archive_stmt(cutoff, batch_limit)))
        .scalars()
        .all()
    )
    result["candidates"] = len(documents)

    if not documents:
        return result

    storage = get_storage_service()
    archive_service = GoBDArchiveService()

    for document in documents:
        try:
            if not document.file_path:
                result["skipped_no_content"] += 1
                logger.warning(
                    "gobd_auto_archive_no_storage_path",
                    document_id=str(document.id),
                )
                continue

            content = await storage.download_document(document.file_path)

            meta = document.document_metadata or {}
            import_source = (
                meta.get("import_source") if isinstance(meta, dict) else None
            )

            await archive_service.archive_document(
                db=db,
                document_id=document.id,
                company_id=document.company_id,
                category=gobd_category_for_document_type(document.document_type),
                document_content=content,
                document_date=archive_document_date(document),
                archived_by_id=None,  # Systemlauf (Beat), kein User
                metadata={
                    "auto_archived": True,
                    "trigger": "gobd_auto_archive_task",
                    "import_source": import_source,
                },
                # TSA bewusst aus: der Auto-Lauf nutzt SHA256 + Audit-Chain
                # (wie import_wa_we); qualifizierte Zeitstempel bleiben dem
                # manuellen/konfigurierten Pfad vorbehalten.
                use_tsa=False,
            )
            # Pro Dokument committen: Teilfortschritt bleibt bei Abbruch
            # erhalten; ein fehlerhaftes Dokument kippt nicht den Batch.
            await db.commit()
            result["archived"] += 1

        except Exception as exc:
            await db.rollback()
            result["errors"] += 1
            if len(result["error_details"]) < 20:
                result["error_details"].append(
                    {
                        "document_id": str(document.id),
                        "error": safe_error_detail(exc, "Archivierung"),
                    }
                )
            logger.error(
                "gobd_auto_archive_document_failed",
                document_id=str(document.id),
                **safe_error_log(exc),
            )

    return result


@celery_app.task(
    name="app.workers.tasks.gobd_compliance_tasks.gobd_auto_archive_task",
    bind=True,
    max_retries=3,
    default_retry_delay=600,
    time_limit=1800,
    soft_time_limit=1700,
)
def gobd_auto_archive_task(self, batch_limit: int = 500) -> AutoArchiveResult:
    """Archiviert Eingangskanal-Dokumente automatisch GoBD-konform.

    Wird taeglich um 03:30 via Celery Beat ausgefuehrt (Details/Karenz-
    Begruendung im Modul-Kommentar oben).

    Args:
        batch_limit: Max. Dokumente pro Lauf (Default 500); der Rest folgt
            im naechsten Lauf.

    Returns:
        Dictionary mit Archivierungs-Statistiken
    """
    import asyncio

    from app.core.config import settings

    if not settings.GOBD_AUTO_ARCHIVE_ENABLED:
        logger.info("gobd_auto_archive_disabled")
        return {
            "enabled": False,
            "candidates": 0,
            "archived": 0,
            "skipped_no_content": 0,
            "errors": 0,
            "error_details": [],
        }

    async def _run():
        async with async_session_factory() as db:
            return await _run_gobd_auto_archive(db, batch_limit)

    try:
        result = asyncio.run(_run())
        logger.info(
            "gobd_auto_archive_completed",
            candidates=result["candidates"],
            archived=result["archived"],
            skipped_no_content=result["skipped_no_content"],
            errors=result["errors"],
        )
        return result
    except Exception as e:
        logger.error("gobd_auto_archive_failed", **safe_error_log(e))
        raise self.retry(exc=e)


# -*- coding: utf-8 -*-
"""
Ad-Hoc Report Celery Tasks.

Hintergrund-Tasks fuer Feature #12: Ad-Hoc Reporting.
- Asynchrone Report-Ausfuehrung fuer grosse Reports
- Asynchroner Export (PDF, Excel, CSV)
- Geplante Report-Ausfuehrung (Celery Beat, stuendlich)
- E-Mail-Versand von Report-Exporten
- Aufraeum-Task fuer alte Export-Dateien

Feinpoliert und durchdacht - Zuverlaessige Report-Automatisierung.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Union

import structlog

from app.workers.celery_app import celery_app
from app.db.session import get_async_session_context
from app.core.safe_errors import safe_error_log, safe_error_detail

logger = structlog.get_logger(__name__)

# Type alias for task return values
TaskResult = Dict[str, Union[str, int, bool, List[str], None]]


# =============================================================================
# Async Report Execution
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.adhoc_report_tasks.execute_report_async_task",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
)
def execute_report_async_task(
    self,
    report_id: str,
    company_id: str,
    user_id: str,
    export_format: Optional[str] = None,
) -> TaskResult:
    """Fuehrt einen Ad-Hoc Report asynchron im Hintergrund aus.

    Wird fuer grosse Reports verwendet, bei denen die Ausfuehrung
    laenger als wenige Sekunden dauern kann.

    Args:
        report_id: UUID des Reports
        company_id: UUID des Mandanten
        user_id: UUID des ausfuehrenden Benutzers
        export_format: Optionales Export-Format (pdf, excel, csv)

    Returns:
        Dict mit Ausfuehrungs-Ergebnis
    """
    from app.services.adhoc_report_service import get_adhoc_report_service

    async def _execute() -> TaskResult:
        async with get_async_session_context() as db:
            service = get_adhoc_report_service()

            try:
                result = await service.execute_report(
                    db=db,
                    report_id=uuid.UUID(report_id),
                    company_id=uuid.UUID(company_id),
                    user_id=uuid.UUID(user_id),
                )

                row_count = result.get("row_count", 0)
                exec_time = result.get("execution_time_ms", 0)

                logger.info(
                    "adhoc_report_async_completed",
                    report_id=report_id,
                    row_count=row_count,
                    execution_time_ms=exec_time,
                )

                return {
                    "success": True,
                    "report_id": report_id,
                    "row_count": row_count,
                    "execution_time_ms": exec_time,
                }

            except Exception as e:
                logger.error(
                    "adhoc_report_async_failed",
                    report_id=report_id,
                    **safe_error_log(e),
                )
                return {
                    "success": False,
                    "report_id": report_id,
                    "error": safe_error_detail(e, "Report"),
                }

    try:
        return asyncio.get_event_loop().run_until_complete(_execute())
    except Exception as e:
        logger.error(
            "adhoc_report_async_task_error",
            report_id=report_id,
            **safe_error_log(e),
        )
        raise self.retry(exc=e)


# =============================================================================
# Async Export
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.adhoc_report_tasks.export_report_async_task",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
)
def export_report_async_task(
    self,
    report_id: str,
    company_id: str,
    user_id: str,
    export_format: str = "excel",
) -> TaskResult:
    """Report-Export asynchron generieren.

    Erstellt die Export-Datei im Hintergrund und speichert
    den Pfad in der Execution.

    Args:
        report_id: UUID des Reports
        company_id: UUID des Mandanten
        user_id: UUID des ausfuehrenden Benutzers
        export_format: Export-Format (pdf, excel, csv)

    Returns:
        Dict mit Export-Ergebnis (Dateipfad, Groesse)
    """
    from app.services.adhoc_report_service import get_adhoc_report_service
    from app.db.models_adhoc_report import AdHocExportFormat

    async def _export() -> TaskResult:
        async with get_async_session_context() as db:
            service = get_adhoc_report_service()

            try:
                # Export-Format validieren
                try:
                    fmt = AdHocExportFormat(export_format)
                except ValueError:
                    fmt = AdHocExportFormat.CSV

                file_bytes, content_type = await service.export_report(
                    db=db,
                    report_id=uuid.UUID(report_id),
                    company_id=uuid.UUID(company_id),
                    user_id=uuid.UUID(user_id),
                    export_format=fmt,
                )

                # Export-Datei speichern
                reports_dir = os.path.join(os.getcwd(), "data", "adhoc_reports")
                os.makedirs(reports_dir, exist_ok=True)

                extension_map = {"pdf": "pdf", "excel": "xlsx", "csv": "csv"}
                ext = extension_map.get(export_format, "csv")
                timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
                filename = f"adhoc_report_{report_id[:8]}_{timestamp}.{ext}"
                file_path = os.path.join(reports_dir, filename)

                with open(file_path, "wb") as f:
                    f.write(file_bytes)

                logger.info(
                    "adhoc_report_export_completed",
                    report_id=report_id,
                    export_format=export_format,
                    file_size=len(file_bytes),
                )

                return {
                    "success": True,
                    "report_id": report_id,
                    "export_format": export_format,
                    "file_path": file_path,
                    "file_size": len(file_bytes),
                    "content_type": content_type,
                }

            except Exception as e:
                logger.error(
                    "adhoc_report_export_failed",
                    report_id=report_id,
                    export_format=export_format,
                    **safe_error_log(e),
                )
                return {
                    "success": False,
                    "report_id": report_id,
                    "error": safe_error_detail(e, "Export"),
                }

    try:
        return asyncio.get_event_loop().run_until_complete(_export())
    except Exception as e:
        logger.error(
            "adhoc_report_export_task_error",
            report_id=report_id,
            **safe_error_log(e),
        )
        raise self.retry(exc=e)


# =============================================================================
# Scheduled Reports (Celery Beat - stuendlich)
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.adhoc_report_tasks.run_scheduled_reports_task",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
)
def run_scheduled_reports_task(self) -> TaskResult:
    """Prueft und fuehrt faellige geplante Ad-Hoc Reports aus.

    Typisches Schedule: Stuendlich via Celery Beat.
    Sucht nach ReportSchedule-Eintraegen, deren next_run_at <= jetzt ist,
    fuehrt den zugehoerigen Report aus und versendet die Ergebnisse per E-Mail.

    Returns:
        Dict mit Ausfuehrungs-Statistiken
    """
    from app.services.adhoc_report_service import get_adhoc_report_service
    from app.db.models_adhoc_report import AdHocExportFormat

    async def _run_all() -> TaskResult:
        stats: Dict[str, Union[str, int, List[str]]] = {
            "checked": 0,
            "executed": 0,
            "failed": 0,
            "errors": [],
        }

        async with get_async_session_context() as db:
            service = get_adhoc_report_service()

            due_schedules = await service.get_due_schedules(db)
            stats["checked"] = len(due_schedules)

            for schedule in due_schedules:
                try:
                    # Export-Format bestimmen
                    export_fmt_str = schedule.export_format or "excel"
                    try:
                        fmt = AdHocExportFormat(export_fmt_str)
                    except ValueError:
                        fmt = AdHocExportFormat.EXCEL

                    # Report ausfuehren und exportieren
                    file_bytes, content_type = await service.export_report(
                        db=db,
                        report_id=schedule.report_id,
                        company_id=schedule.company_id,
                        user_id=schedule.report_id,  # System-Ausfuehrung
                        export_format=fmt,
                    )

                    # Export-Datei speichern
                    reports_dir = os.path.join(os.getcwd(), "data", "adhoc_reports")
                    os.makedirs(reports_dir, exist_ok=True)

                    ext_map = {"pdf": "pdf", "excel": "xlsx", "csv": "csv"}
                    ext = ext_map.get(export_fmt_str, "csv")
                    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
                    filename = f"scheduled_{schedule.report_id}_{timestamp}.{ext}"
                    file_path = os.path.join(reports_dir, filename)

                    with open(file_path, "wb") as f:
                        f.write(file_bytes)

                    # E-Mail versenden
                    recipients = schedule.recipients or []
                    if recipients:
                        send_scheduled_report_email_task.delay(
                            report_id=str(schedule.report_id),
                            recipients=recipients,
                            file_path=file_path,
                            filename=filename,
                            content_type=content_type,
                        )

                    # Schedule aktualisieren
                    await service.mark_schedule_as_sent(db, schedule)

                    stats["executed"] = int(stats["executed"]) + 1

                    logger.info(
                        "scheduled_adhoc_report_executed",
                        schedule_id=str(schedule.id),
                        report_id=str(schedule.report_id),
                        recipients_count=len(recipients),
                    )

                except Exception as e:
                    stats["failed"] = int(stats["failed"]) + 1
                    error_list = stats.get("errors", [])
                    if isinstance(error_list, list):
                        error_list.append(
                            f"Schedule {schedule.id}: {safe_error_detail(e, 'Report')}"
                        )
                    logger.error(
                        "scheduled_adhoc_report_failed",
                        schedule_id=str(schedule.id),
                        **safe_error_log(e),
                    )

        return stats

    try:
        result = asyncio.get_event_loop().run_until_complete(_run_all())
        logger.info(
            "scheduled_adhoc_reports_batch_completed",
            checked=result.get("checked", 0),
            executed=result.get("executed", 0),
            failed=result.get("failed", 0),
        )
        return result
    except Exception as e:
        logger.error("scheduled_adhoc_reports_batch_failed", **safe_error_log(e))
        raise self.retry(exc=e)


# =============================================================================
# Email Sending
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.adhoc_report_tasks.send_scheduled_report_email_task",
    bind=True,
    max_retries=3,
    default_retry_delay=120,
)
def send_scheduled_report_email_task(
    self,
    report_id: str,
    recipients: List[str],
    file_path: str,
    filename: str,
    content_type: str,
) -> TaskResult:
    """Sendet einen generierten Ad-Hoc Report per E-Mail.

    Args:
        report_id: UUID des Reports (fuer Logging)
        recipients: Liste der E-Mail-Adressen
        file_path: Pfad zur Export-Datei
        filename: Dateiname fuer den Anhang
        content_type: MIME-Type der Datei

    Returns:
        Dict mit Versand-Status
    """
    try:
        # Datei lesen
        if not os.path.exists(file_path):
            logger.warning(
                "scheduled_report_file_not_found",
                report_id=report_id,
                file_path=file_path,
            )
            return {
                "success": False,
                "report_id": report_id,
                "error": "Export-Datei nicht gefunden",
            }

        with open(file_path, "rb") as f:
            attachment_data = f.read()

        subject = (
            f"Geplanter Report - "
            f"{datetime.now(timezone.utc).strftime('%d.%m.%Y')}"
        )
        body = (
            "Ihr geplanter Ad-Hoc Report wurde erfolgreich generiert.\n\n"
            "Der Report ist als Anhang beigefuegt.\n\n"
            "Mit freundlichen Gruessen,\n"
            "Ihr Ablage-System"
        )

        success_count = 0
        failed_recipients: List[str] = []

        for recipient in recipients:
            try:
                # E-Mail-Service verwenden (lazy import)
                from app.core.email import EmailService
                email_service = EmailService()

                asyncio.get_event_loop().run_until_complete(
                    email_service.send_email(
                        to=recipient,
                        subject=subject,
                        body=body,
                        attachments=[{
                            "filename": filename,
                            "content": attachment_data,
                            "content_type": content_type,
                        }],
                    )
                )
                success_count += 1

            except Exception as e:
                failed_recipients.append(recipient)
                logger.warning(
                    "adhoc_report_email_recipient_failed",
                    report_id=report_id,
                    **safe_error_log(e),
                )

        logger.info(
            "adhoc_report_emails_sent",
            report_id=report_id,
            success_count=success_count,
            failed_count=len(failed_recipients),
        )

        return {
            "success": True,
            "sent": success_count,
            "failed_count": len(failed_recipients),
        }

    except Exception as e:
        logger.error(
            "adhoc_report_email_task_error",
            report_id=report_id,
            **safe_error_log(e),
        )
        raise self.retry(exc=e)


# =============================================================================
# Cleanup Task
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.adhoc_report_tasks.cleanup_old_report_exports_task",
)
def cleanup_old_report_exports_task(retention_days: int = 7) -> TaskResult:
    """Loescht alte Ad-Hoc Report Export-Dateien.

    Typisches Schedule: Taeglich um 03:00 Uhr.
    Entfernt Dateien, die aelter als retention_days Tage sind.

    Args:
        retention_days: Maximales Alter der Dateien in Tagen

    Returns:
        Dict mit Cleanup-Statistiken
    """
    reports_dir = os.path.join(os.getcwd(), "data", "adhoc_reports")

    if not os.path.exists(reports_dir):
        return {"deleted_files": 0, "errors": 0}

    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    cutoff_timestamp = cutoff.timestamp()

    deleted = 0
    errors = 0
    bytes_freed = 0

    for filename in os.listdir(reports_dir):
        file_path = os.path.join(reports_dir, filename)
        try:
            if os.path.isfile(file_path):
                file_mtime = os.path.getmtime(file_path)
                if file_mtime < cutoff_timestamp:
                    file_size = os.path.getsize(file_path)
                    os.remove(file_path)
                    deleted += 1
                    bytes_freed += file_size
        except OSError as e:
            errors += 1
            logger.warning(
                "adhoc_report_file_cleanup_failed",
                file_path=file_path,
                **safe_error_log(e),
            )

    if deleted > 0:
        logger.info(
            "adhoc_report_files_cleaned",
            deleted=deleted,
            bytes_freed=bytes_freed,
            errors=errors,
            retention_days=retention_days,
        )

    return {
        "deleted_files": deleted,
        "bytes_freed": bytes_freed,
        "errors": errors,
        "retention_days": retention_days,
    }

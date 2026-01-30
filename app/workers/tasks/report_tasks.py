# -*- coding: utf-8 -*-
"""
Report-Builder Celery Tasks.

Enterprise-Level Report-Automatisierung:
- Periodische Report-Ausfuehrung (Cron-basiert)
- Async Report-Generierung
- E-Mail-Versand von Reports
- Execution Cleanup

Feinpoliert und durchdacht - Zuverlaessige Report-Automatisierung.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import structlog

from celery import shared_task

from app.workers.celery_app import celery_app
from app.db.session import get_async_session_context
from app.core.safe_errors import safe_error_log, safe_error_detail

logger = structlog.get_logger(__name__)


# =============================================================================
# Scheduled Report Execution
# =============================================================================


@celery_app.task(
    name="reports.execute_scheduled_reports",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
)
def execute_scheduled_reports(self) -> Dict[str, Any]:
    """Fuehrt alle faelligen geplanten Reports aus.

    Prueft welche Reports basierend auf ihrem Cron-Schedule
    ausgefuehrt werden muessen und triggert die Ausfuehrung.

    Typisches Schedule: Alle 15 Minuten.

    Returns:
        Dict mit Ausfuehrungs-Statistiken
    """
    from app.services.reports import ReportSchedulerService, ReportBuilderService
    from app.db.models import ReportTemplate

    async def _execute_all():
        stats = {
            "reports_checked": 0,
            "reports_executed": 0,
            "reports_failed": 0,
            "errors": [],
        }

        async with get_async_session_context() as db:
            scheduler = ReportSchedulerService()
            builder = ReportBuilderService()

            # Faellige Reports laden
            due_reports = await scheduler.get_due_reports(db, limit=50)
            stats["reports_checked"] = len(due_reports)

            for template in due_reports:
                try:
                    # Schedule-Config extrahieren
                    config = template.schedule_config or {}
                    report_format = config.get("format", "excel")
                    recipients = config.get("recipients", [])

                    # Execution erstellen
                    execution = await scheduler.create_execution(
                        db=db,
                        template_id=template.id,
                        executed_by_id=template.user_id,
                        format=report_format,
                        trigger_type="scheduled",
                        filter_snapshot=template.default_filters,
                    )

                    # Report-Generierung als separaten Task starten
                    generate_report_async.delay(
                        execution_id=str(execution.id),
                        template_id=str(template.id),
                        format=report_format,
                        recipients=recipients,
                    )

                    # Schedule aktualisieren
                    await scheduler.update_schedule_after_run(db, template)

                    stats["reports_executed"] += 1

                    logger.info(
                        "scheduled_report_triggered",
                        template_id=str(template.id),
                        template_name=template.name,
                        execution_id=str(execution.id),
                        format=report_format,
                    )

                except Exception as e:
                    stats["reports_failed"] += 1
                    stats["errors"].append({
                        "template_id": str(template.id),
                        "name": template.name,
                        "error": safe_error_detail(e, "Vorgang"),
                    })
                    logger.error(
                        "scheduled_report_failed",
                        template_id=str(template.id),
                        **safe_error_log(e),
                    )

        return stats

    try:
        result = asyncio.get_event_loop().run_until_complete(_execute_all())
        logger.info(
            "scheduled_reports_batch_completed",
            checked=result["reports_checked"],
            executed=result["reports_executed"],
            failed=result["reports_failed"],
        )
        return result
    except Exception as e:
        logger.error("scheduled_reports_batch_failed", **safe_error_log(e))
        raise self.retry(exc=e)


# =============================================================================
# Async Report Generation
# =============================================================================


@celery_app.task(
    name="reports.generate_async",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def generate_report_async(
    self,
    execution_id: str,
    template_id: str,
    format: str = "excel",
    recipients: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Generiert einen Report asynchron.

    Wird fuer grosse Reports oder scheduled Reports verwendet.
    Speichert das Ergebnis und sendet optional eine E-Mail.

    Args:
        execution_id: UUID der Execution
        template_id: UUID des Templates
        format: Export-Format (pdf, excel, csv, json)
        recipients: E-Mail-Empfaenger fuer Versand

    Returns:
        Dict mit Generierungs-Ergebnis
    """
    from app.services.reports import (
        ReportBuilderService,
        ReportRendererService,
        ReportSchedulerService,
        ReportTemplateService,
    )

    async def _generate():
        async with get_async_session_context() as db:
            scheduler = ReportSchedulerService()
            template_service = ReportTemplateService()
            builder = ReportBuilderService()
            renderer = ReportRendererService()

            # Status auf running setzen
            await scheduler.update_execution_status(
                db=db,
                execution_id=uuid.UUID(execution_id),
                status="running",
            )

            try:
                # Template laden
                template = await template_service.get_template(
                    db=db,
                    template_id=uuid.UUID(template_id),
                    user_id=None,  # Keine User-Pruefung bei async Tasks
                )

                if not template:
                    raise ValueError(f"Template {template_id} nicht gefunden")

                # Report ausfuehren
                result = await builder.execute_report(
                    db=db,
                    template=template,
                )

                # Report rendern
                if format == "excel":
                    content = await renderer.render_excel(result, template)
                    content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    extension = "xlsx"
                elif format == "pdf":
                    content = await renderer.render_pdf(result, template)
                    content_type = "application/pdf"
                    extension = "pdf"
                elif format == "csv":
                    content = await renderer.render_csv(result, template)
                    content_type = "text/csv"
                    extension = "csv"
                else:
                    content = await renderer.render_json(result, template)
                    content_type = "application/json"
                    extension = "json"

                # Datei speichern
                reports_dir = os.path.join(os.getcwd(), "data", "reports")
                os.makedirs(reports_dir, exist_ok=True)

                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                safe_name = "".join(c for c in template.name if c.isalnum() or c in "._- ")[:50]
                filename = f"{safe_name}_{timestamp}.{extension}"
                file_path = os.path.join(reports_dir, filename)

                if isinstance(content, bytes):
                    with open(file_path, "wb") as f:
                        f.write(content)
                else:
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(content)

                file_size = os.path.getsize(file_path)

                # Download-URL (relativ)
                download_url = f"/api/v1/reports/executions/{execution_id}/download"
                download_expires_at = datetime.now(timezone.utc) + timedelta(days=7)

                # Execution aktualisieren
                await scheduler.update_execution_status(
                    db=db,
                    execution_id=uuid.UUID(execution_id),
                    status="completed",
                    row_count=result.row_count,
                    file_size_bytes=file_size,
                    file_path=file_path,
                    download_url=download_url,
                    download_expires_at=download_expires_at,
                )

                # E-Mail senden wenn Empfaenger angegeben
                if recipients:
                    send_report_email.delay(
                        execution_id=execution_id,
                        recipients=recipients,
                        file_path=file_path,
                        filename=filename,
                        content_type=content_type,
                    )

                logger.info(
                    "report_generated",
                    execution_id=execution_id,
                    template_id=template_id,
                    format=format,
                    row_count=result.row_count,
                    file_size=file_size,
                )

                return {
                    "success": True,
                    "execution_id": execution_id,
                    "file_path": file_path,
                    "row_count": result.row_count,
                    "file_size": file_size,
                }

            except Exception as e:
                # Status auf failed setzen
                await scheduler.update_execution_status(
                    db=db,
                    execution_id=uuid.UUID(execution_id),
                    status="failed",
                    error_message=safe_error_detail(e, "Report"),
                    error_details={"exception_type": type(e).__name__},
                )

                logger.error(
                    "report_generation_failed",
                    execution_id=execution_id,
                    template_id=template_id,
                    **safe_error_log(e),
                )
                raise

    try:
        return asyncio.get_event_loop().run_until_complete(_generate())
    except Exception as e:
        logger.error(
            "report_async_task_failed",
            execution_id=execution_id,
            **safe_error_log(e),
        )
        raise self.retry(exc=e)


# =============================================================================
# Email Sending
# =============================================================================


@celery_app.task(
    name="reports.send_email",
    bind=True,
    max_retries=3,
    default_retry_delay=120,
)
def send_report_email(
    self,
    execution_id: str,
    recipients: List[str],
    file_path: str,
    filename: str,
    content_type: str,
) -> Dict[str, Any]:
    """Sendet einen generierten Report per E-Mail.

    Args:
        execution_id: UUID der Execution
        recipients: Liste der E-Mail-Adressen
        file_path: Pfad zur Report-Datei
        filename: Dateiname fuer Anhang
        content_type: MIME-Type der Datei

    Returns:
        Dict mit Versand-Status
    """
    from app.core.email import EmailService

    async def _send():
        async with get_async_session_context() as db:
            from sqlalchemy import select
            from app.db.models import ReportExecution, ReportTemplate

            # Execution laden fuer Details
            result = await db.execute(
                select(ReportExecution)
                .where(ReportExecution.id == uuid.UUID(execution_id))
            )
            execution = result.scalar_one_or_none()

            if not execution:
                return {"success": False, "error": "Execution nicht gefunden"}

            # Template laden
            template_result = await db.execute(
                select(ReportTemplate)
                .where(ReportTemplate.id == execution.template_id)
            )
            template = template_result.scalar_one_or_none()

            template_name = template.name if template else "Report"

            # E-Mail senden
            try:
                email_service = EmailService()

                subject = f"Report: {template_name}"
                body = f"""
Ihr Report "{template_name}" wurde erfolgreich generiert.

Details:
- Zeilen: {execution.row_count or 'N/A'}
- Format: {execution.format}
- Generiert am: {execution.completed_at.strftime('%d.%m.%Y %H:%M') if execution.completed_at else 'N/A'}

Der Report ist als Anhang beigefuegt.

Mit freundlichen Gruessen,
Ihr Ablage-System
                """.strip()

                # Datei lesen
                with open(file_path, "rb") as f:
                    attachment_data = f.read()

                success_count = 0
                failed_recipients = []

                for recipient in recipients:
                    try:
                        await email_service.send_email(
                            to=recipient,
                            subject=subject,
                            body=body,
                            attachments=[
                                {
                                    "filename": filename,
                                    "content": attachment_data,
                                    "content_type": content_type,
                                }
                            ],
                        )
                        success_count += 1
                    except Exception as e:
                        failed_recipients.append({
                            "recipient": recipient,
                            "error": safe_error_detail(e, "Vorgang"),
                        })

                logger.info(
                    "report_emails_sent",
                    execution_id=execution_id,
                    success_count=success_count,
                    failed_count=len(failed_recipients),
                )

                return {
                    "success": True,
                    "sent": success_count,
                    "failed": failed_recipients,
                }

            except Exception as e:
                logger.error(
                    "report_email_send_failed",
                    execution_id=execution_id,
                    **safe_error_log(e),
                )
                return {"success": False, **safe_error_log(e)}

    try:
        return asyncio.get_event_loop().run_until_complete(_send())
    except Exception as e:
        logger.error(
            "report_email_task_failed",
            execution_id=execution_id,
            **safe_error_log(e),
        )
        raise self.retry(exc=e)


# =============================================================================
# Cleanup Tasks
# =============================================================================


@celery_app.task(name="reports.cleanup_old_executions")
def cleanup_old_executions(retention_days: int = 90) -> Dict[str, Any]:
    """Loescht alte Report-Executions und zugehoerige Dateien.

    Typisches Schedule: Taeglich um 03:00.

    Args:
        retention_days: Tage nach denen Executions geloescht werden

    Returns:
        Dict mit Cleanup-Statistiken
    """
    from app.services.reports import ReportSchedulerService

    async def _cleanup():
        async with get_async_session_context() as db:
            from sqlalchemy import select, and_
            from app.db.models import ReportExecution

            cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)

            # Zuerst Dateien loeschen
            result = await db.execute(
                select(ReportExecution).where(
                    and_(
                        ReportExecution.created_at < cutoff,
                        ReportExecution.status.in_(["completed", "failed"]),
                    )
                )
            )
            executions = result.scalars().all()

            files_deleted = 0
            for execution in executions:
                if execution.file_path and os.path.exists(execution.file_path):
                    try:
                        os.remove(execution.file_path)
                        files_deleted += 1
                    except OSError as e:
                        logger.warning(
                            "report_file_delete_failed",
                            execution_id=str(execution.id),
                            file_path=execution.file_path,
                            **safe_error_log(e),
                        )

            # Dann DB-Eintraege loeschen
            scheduler = ReportSchedulerService()
            deleted_count = await scheduler.cleanup_old_executions(
                db=db,
                days=retention_days,
            )

            logger.info(
                "report_executions_cleaned",
                deleted_db=deleted_count,
                deleted_files=files_deleted,
                retention_days=retention_days,
            )

            return {
                "deleted_db": deleted_count,
                "deleted_files": files_deleted,
                "retention_days": retention_days,
            }

    return asyncio.get_event_loop().run_until_complete(_cleanup())


@celery_app.task(name="reports.cleanup_expired_downloads")
def cleanup_expired_downloads() -> Dict[str, Any]:
    """Loescht abgelaufene Download-Links.

    Setzt download_url und download_expires_at auf NULL
    fuer abgelaufene Executions.

    Typisches Schedule: Stuendlich.

    Returns:
        Dict mit Cleanup-Statistiken
    """

    async def _cleanup():
        async with get_async_session_context() as db:
            from sqlalchemy import update, and_
            from app.db.models import ReportExecution

            now = datetime.now(timezone.utc)

            result = await db.execute(
                update(ReportExecution)
                .where(
                    and_(
                        ReportExecution.download_expires_at.isnot(None),
                        ReportExecution.download_expires_at < now,
                    )
                )
                .values(
                    download_url=None,
                    download_expires_at=None,
                )
            )
            await db.commit()

            affected = result.rowcount

            if affected > 0:
                logger.info(
                    "expired_downloads_cleaned",
                    count=affected,
                )

            return {"expired_cleaned": affected}

    return asyncio.get_event_loop().run_until_complete(_cleanup())


# =============================================================================
# Utility Tasks
# =============================================================================


@celery_app.task(name="reports.cancel_execution")
def cancel_execution(execution_id: str) -> Dict[str, Any]:
    """Bricht eine laufende Report-Ausfuehrung ab.

    Args:
        execution_id: UUID der Execution

    Returns:
        Dict mit Cancel-Status
    """
    from app.services.reports import ReportSchedulerService

    async def _cancel():
        async with get_async_session_context() as db:
            scheduler = ReportSchedulerService()

            execution = await scheduler.get_execution(
                db=db,
                execution_id=uuid.UUID(execution_id),
            )

            if not execution:
                return {"success": False, "error": "Execution nicht gefunden"}

            if execution.status not in ["pending", "running"]:
                return {
                    "success": False,
                    "error": f"Execution kann nicht abgebrochen werden (Status: {execution.status})",
                }

            await scheduler.update_execution_status(
                db=db,
                execution_id=uuid.UUID(execution_id),
                status="cancelled",
            )

            logger.info(
                "execution_cancelled",
                execution_id=execution_id,
            )

            return {"success": True, "execution_id": execution_id}

    return asyncio.get_event_loop().run_until_complete(_cancel())


# =============================================================================
# Celery Beat Schedule
# =============================================================================

REPORT_BEAT_SCHEDULE = {
    # Scheduled Reports alle 15 Minuten pruefen
    "execute-scheduled-reports": {
        "task": "reports.execute_scheduled_reports",
        "schedule": 900.0,  # 15 Minuten
        "options": {"queue": "default"},
    },
    # Cleanup alte Executions taeglich um 03:00
    "cleanup-old-report-executions": {
        "task": "reports.cleanup_old_executions",
        "schedule": {
            "hour": 3,
            "minute": 0,
        },
        "options": {"queue": "default"},
    },
    # Cleanup abgelaufene Downloads stuendlich
    "cleanup-expired-downloads": {
        "task": "reports.cleanup_expired_downloads",
        "schedule": 3600.0,  # 1 Stunde
        "options": {"queue": "default"},
    },
}

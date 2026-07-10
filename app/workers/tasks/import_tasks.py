"""
Email und Folder Import Celery Tasks.

Enterprise-Level Import-Automatisierung:
- Periodische E-Mail-Synchronisation
- Folder-Polling als Watchdog-Fallback
- Retry fehlgeschlagener Imports
- Import-Log Cleanup
- Statistik-Reset

Feinpoliert und durchdacht - Zuverlässige Import-Automatisierung.
"""

import structlog
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, TypedDict
from uuid import UUID

from celery import shared_task
from sqlalchemy import select, and_, update, delete, func

from app.workers.celery_app import celery_app
from app.db.session import get_worker_session_context
from app.db.models import (
    EmailImportConfig,
    FolderImportConfig,
    ImportLog,
    ImportRule,
)
from app.core.safe_errors import safe_error_log, safe_error_detail

logger = structlog.get_logger(__name__)


# =============================================================================
# TypedDict Return Types
# =============================================================================


class _BatchErrorEntry(TypedDict, total=False):
    """Einzelner Fehler-Eintrag in Batch-Ergebnissen."""
    config_id: str
    error: str


class EmailSyncBatchResult(TypedDict):
    """Rueckgabe von sync_all_email_configs."""
    configs_processed: int
    emails_processed: int
    documents_created: int
    errors: List[Any]


class EmailSyncResult(TypedDict):
    """Rueckgabe von sync_email_config."""
    emails_processed: int
    documents_created: int
    duplicates_skipped: int
    errors: List[Any]


class FolderPollBatchResult(TypedDict):
    """Rueckgabe von poll_all_folder_configs."""
    configs_processed: int
    files_processed: int
    documents_created: int
    errors: List[Any]


class FolderPollResult(TypedDict):
    """Rueckgabe von poll_folder_config."""
    files_processed: int
    documents_created: int
    duplicates_skipped: int
    errors: List[Any]


class RetryBatchResult(TypedDict, total=False):
    """Rueckgabe von retry_failed_imports."""
    retried: int
    successful: int
    failed: int
    error: str


class RetryImportResult(TypedDict, total=False):
    """Rueckgabe von retry_import_task."""
    success: bool
    error: str
    log_id: str
    type: str


class EmailRetryResult(TypedDict, total=False):
    """Rueckgabe von retry_single_email."""
    success: bool
    error: str
    documents_created: int
    error_type: str
    error_message: str
    timestamp: str


class FileRetryResult(TypedDict, total=False):
    """Rueckgabe von retry_single_file."""
    success: bool
    error: str
    document_id: str
    skipped: bool
    reason: str
    error_type: str
    error_message: str
    timestamp: str


class CleanupResult(TypedDict):
    """Rueckgabe von cleanup_old_import_logs."""
    deleted: int
    retention_days: int


class ResetStatsResult(TypedDict):
    """Rueckgabe von reset_daily_folder_stats."""
    configs_reset: int


class ApplyRulesResult(TypedDict):
    """Rueckgabe von apply_rules_to_pending_imports."""
    logs_checked: int
    rules_applied: int


class ScanFolderResult(TypedDict, total=False):
    """Rueckgabe von scan_import_folder."""
    folder_path: str
    config_found: bool
    config_id: str
    files_processed: int
    documents_created: int
    duplicates_skipped: int
    errors: List[Any]


class ConnectionHealthResult(TypedDict):
    """Rueckgabe von check_email_connection_health."""
    total: int
    healthy: int
    unhealthy: int
    errors: List[Dict[str, Any]]


# =============================================================================
# Email Sync Tasks
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.import_tasks.sync_all_email_configs",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
)
def sync_all_email_configs(self) -> EmailSyncBatchResult:
    """Synchronisiert alle aktiven Email-Konfigurationen.

    Wird periodisch via Celery Beat aufgerufen.
    Typisches Schedule: Alle 15 Minuten.

    Returns:
        Dict mit Sync-Statistiken
    """
    import asyncio
    from app.services.imports import EmailImportService

    async def _sync_all() -> EmailSyncBatchResult:
        stats = {
            "configs_processed": 0,
            "emails_processed": 0,
            "documents_created": 0,
            "errors": [],
        }

        async with get_worker_session_context() as db:
            # Alle aktiven Configs laden die jetzt sync brauchen
            now = datetime.now(timezone.utc)

            result = await db.execute(
                select(EmailImportConfig).where(
                    and_(
                        EmailImportConfig.is_active == True,
                        EmailImportConfig.connection_status != "error",
                    )
                )
            )
            configs = result.scalars().all()

            for config in configs:
                # Check ob Sync fällig ist
                if config.last_sync_at:
                    next_sync = config.last_sync_at + timedelta(
                        minutes=config.sync_interval_minutes
                    )
                    if now < next_sync:
                        continue

                try:
                    service = EmailImportService(db)
                    sync_result = await service.sync_emails(
                        config_id=config.id,
                        user_id=config.user_id,
                        max_emails=100,
                    )

                    stats["configs_processed"] += 1
                    stats["emails_processed"] += sync_result.emails_processed
                    stats["documents_created"] += sync_result.documents_created

                    if sync_result.errors:
                        stats["errors"].extend(sync_result.errors[:3])

                    logger.info(
                        "email_config_synced",
                        config_id=str(config.id),
                        emails=sync_result.emails_processed,
                        documents=sync_result.documents_created,
                    )

                except Exception as e:
                    stats["errors"].append({
                        "config_id": str(config.id),
                        "error": safe_error_detail(e, "Vorgang"),
                    })
                    logger.error(
                        "email_config_sync_failed",
                        config_id=str(config.id),
                        **safe_error_log(e),
                    )

        return stats

    try:
        result = asyncio.run(_sync_all())
        logger.info(
            "email_sync_batch_completed",
            configs=result["configs_processed"],
            emails=result["emails_processed"],
            documents=result["documents_created"],
        )
        return result
    except Exception as e:
        logger.error("email_sync_batch_failed", **safe_error_log(e))
        raise self.retry(exc=e)


@celery_app.task(
    name="app.workers.tasks.import_tasks.sync_email_config",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def sync_email_config(self, config_id: str, user_id: str, max_emails: int = 100) -> EmailSyncResult:
    """Synchronisiert eine einzelne Email-Konfiguration.

    Kann manuell oder scheduled aufgerufen werden.

    Args:
        config_id: UUID der Email-Config
        user_id: UUID des Users
        max_emails: Maximale Anzahl zu verarbeitender Emails

    Returns:
        Dict mit Sync-Ergebnis
    """
    import asyncio
    from app.services.imports import EmailImportService

    async def _sync() -> EmailSyncResult:
        async with get_worker_session_context() as db:
            service = EmailImportService(db)
            result = await service.sync_emails(
                config_id=UUID(config_id),
                user_id=UUID(user_id),
                max_emails=max_emails,
            )
            return {
                "emails_processed": result.emails_processed,
                "documents_created": result.documents_created,
                "duplicates_skipped": result.duplicates_skipped,
                "errors": result.errors,
            }

    try:
        return asyncio.run(_sync())
    except Exception as e:
        logger.error(
            "email_sync_task_failed",
            config_id=config_id,
            **safe_error_log(e),
        )
        raise self.retry(exc=e)


# =============================================================================
# Folder Polling Tasks
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.import_tasks.poll_all_folder_configs",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
)
def poll_all_folder_configs(self) -> FolderPollBatchResult:
    """Pollt alle aktiven Folder-Konfigurationen.

    Dient als Fallback wenn Watchdog nicht läuft
    (z.B. bei Netzwerklaufwerken).

    Typisches Schedule: Alle 5 Minuten.

    Returns:
        Dict mit Poll-Statistiken
    """
    import asyncio
    from app.services.imports import FolderImportService

    async def _poll_all() -> FolderPollBatchResult:
        stats = {
            "configs_processed": 0,
            "files_processed": 0,
            "documents_created": 0,
            "errors": [],
        }

        async with get_worker_session_context() as db:
            now = datetime.now(timezone.utc)

            # Configs laden die nicht via Watchdog überwacht werden
            result = await db.execute(
                select(FolderImportConfig).where(
                    and_(
                        FolderImportConfig.is_active == True,
                        # Nur wenn Watcher nicht läuft
                        FolderImportConfig.watcher_status != "running",
                    )
                )
            )
            configs = result.scalars().all()

            for config in configs:
                # Check ob Polling fällig ist
                if config.last_poll_at:
                    next_poll = config.last_poll_at + timedelta(
                        seconds=config.poll_interval_seconds
                    )
                    if now < next_poll:
                        continue

                try:
                    service = FolderImportService(db)
                    poll_result = await service.poll_folder(
                        config_id=config.id,
                        user_id=config.user_id,
                    )

                    stats["configs_processed"] += 1
                    stats["files_processed"] += poll_result.files_processed
                    stats["documents_created"] += poll_result.documents_created

                    if poll_result.errors:
                        stats["errors"].extend(poll_result.errors[:3])

                    logger.info(
                        "folder_config_polled",
                        config_id=str(config.id),
                        files=poll_result.files_processed,
                        documents=poll_result.documents_created,
                    )

                except Exception as e:
                    stats["errors"].append({
                        "config_id": str(config.id),
                        "error": safe_error_detail(e, "Vorgang"),
                    })
                    logger.error(
                        "folder_config_poll_failed",
                        config_id=str(config.id),
                        **safe_error_log(e),
                    )

        return stats

    try:
        result = asyncio.run(_poll_all())
        logger.info(
            "folder_poll_batch_completed",
            configs=result["configs_processed"],
            files=result["files_processed"],
            documents=result["documents_created"],
        )
        return result
    except Exception as e:
        logger.error("folder_poll_batch_failed", **safe_error_log(e))
        raise self.retry(exc=e)


@celery_app.task(
    name="app.workers.tasks.import_tasks.poll_folder_config",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def poll_folder_config(self, config_id: str, user_id: str) -> FolderPollResult:
    """Pollt eine einzelne Folder-Konfiguration.

    Args:
        config_id: UUID der Folder-Config
        user_id: UUID des Users

    Returns:
        Dict mit Poll-Ergebnis
    """
    import asyncio
    from app.services.imports import FolderImportService

    async def _poll() -> FolderPollResult:
        async with get_worker_session_context() as db:
            service = FolderImportService(db)
            result = await service.poll_folder(
                config_id=UUID(config_id),
                user_id=UUID(user_id),
            )
            return {
                "files_processed": result.files_processed,
                "documents_created": result.documents_created,
                "duplicates_skipped": result.duplicates_skipped,
                "errors": result.errors,
            }

    try:
        return asyncio.run(_poll())
    except Exception as e:
        logger.error(
            "folder_poll_task_failed",
            config_id=config_id,
            **safe_error_log(e),
        )
        raise self.retry(exc=e)


# =============================================================================
# Retry Tasks
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.import_tasks.retry_failed_imports",
    bind=True,
    max_retries=1,
)
def retry_failed_imports(self) -> RetryBatchResult:
    """Wiederholt fehlgeschlagene Imports.

    Versucht Imports die mit bestimmten Fehlern fehlgeschlagen
    sind erneut zu verarbeiten.

    Typisches Schedule: Alle 30 Minuten.

    Returns:
        Dict mit Retry-Statistiken
    """
    import asyncio
    from app.services.imports import EmailImportService, FolderImportService

    async def _retry_all() -> RetryBatchResult:
        stats = {
            "retried": 0,
            "successful": 0,
            "failed": 0,
        }

        async with get_worker_session_context() as db:
            # Fehlgeschlagene Imports laden (max 3 Retries)
            result = await db.execute(
                select(ImportLog).where(
                    and_(
                        ImportLog.status == "failed",
                        ImportLog.retry_count < 3,
                        # Nur bestimmte Fehler wiederholen
                        ImportLog.error_code.in_([
                            "connection_timeout",
                            "temporary_error",
                            "rate_limited",
                        ]),
                    )
                ).limit(50)
            )
            logs = result.scalars().all()

            for log in logs:
                try:
                    stats["retried"] += 1

                    if log.source_type == "email" and log.email_config_id:
                        # Email-Import: Trigger Celery Task für einzelne Email
                        from app.workers.celery_app import celery_app as celery
                        celery.send_task(
                            "app.workers.tasks.import_tasks.retry_single_email",
                            kwargs={
                                "config_id": str(log.email_config_id),
                                "email_uid": log.email_uid,
                                "log_id": str(log.id),
                            },
                        )
                        log.retry_count += 1
                        log.status = "pending"
                        await db.commit()

                    elif log.source_type == "folder" and log.original_path:
                        # Folder-Import: Trigger Celery Task für einzelne Datei
                        from app.workers.celery_app import celery_app as celery
                        celery.send_task(
                            "app.workers.tasks.import_tasks.retry_single_file",
                            kwargs={
                                "config_id": str(log.folder_config_id) if log.folder_config_id else None,
                                "file_path": log.original_path,
                                "log_id": str(log.id),
                            },
                        )
                        log.retry_count += 1
                        log.status = "pending"
                        await db.commit()

                    else:
                        # Unbekannter Source-Type - nur Status aktualisieren
                        log.retry_count += 1
                        log.status = "failed"
                        log.error_message = "Unbekannter Import-Typ für Retry"
                        await db.commit()
                        stats["failed"] += 1
                        continue

                except Exception as e:
                    stats["failed"] += 1
                    logger.warning(
                        "import_retry_failed",
                        log_id=str(log.id),
                        **safe_error_log(e),
                    )

        return stats

    try:
        return asyncio.run(_retry_all())
    except Exception as e:
        logger.error("retry_failed_imports_error", **safe_error_log(e))
        return {"error": safe_error_detail(e, "Vorgang")}


@celery_app.task(name="app.workers.tasks.import_tasks.retry_import_task")
def retry_import_task(log_id: str) -> RetryImportResult:
    """Wiederholt einen einzelnen fehlgeschlagenen Import.

    Dispatcht automatisch zum richtigen Retry-Task basierend auf source_type.

    Args:
        log_id: UUID des Import-Logs

    Returns:
        Dict mit Retry-Ergebnis
    """
    import asyncio

    async def _retry() -> RetryImportResult:
        async with get_worker_session_context() as db:
            result = await db.execute(
                select(ImportLog).where(ImportLog.id == UUID(log_id))
            )
            log = result.scalar_one_or_none()

            if not log:
                return {"success": False, "error": "Log nicht gefunden"}

            if log.status not in ("pending", "failed"):
                return {"success": False, "error": f"Log Status ist '{log.status}', nicht retry-faehig"}

            # Dispatch basierend auf source_type
            if log.source_type == "email" and log.email_config_id:
                celery_app.send_task(
                    "app.workers.tasks.import_tasks.retry_single_email",
                    kwargs={
                        "config_id": str(log.email_config_id),
                        "email_uid": log.email_uid,
                        "log_id": str(log.id),
                    },
                )
                log.status = "pending"
                log.retry_count += 1
                await db.commit()
                return {"success": True, "log_id": log_id, "type": "email"}

            elif log.source_type == "folder" and log.original_path:
                celery_app.send_task(
                    "app.workers.tasks.import_tasks.retry_single_file",
                    kwargs={
                        "config_id": str(log.folder_config_id) if log.folder_config_id else None,
                        "file_path": log.original_path,
                        "log_id": str(log.id),
                    },
                )
                log.status = "pending"
                log.retry_count += 1
                await db.commit()
                return {"success": True, "log_id": log_id, "type": "folder"}

            else:
                return {"success": False, "error": "Unbekannter Import-Typ"}

    return asyncio.run(_retry())


@celery_app.task(
    name="app.workers.tasks.import_tasks.retry_single_email",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
    soft_time_limit=120,
    time_limit=180,
)
def retry_single_email(
    self,
    config_id: str,
    email_uid: int,
    log_id: str,
) -> EmailRetryResult:
    """Wiederholt den Import einer einzelnen E-Mail.

    Holt die E-Mail erneut via IMAP und verarbeitet die Anhaenge.

    Args:
        config_id: UUID der EmailImportConfig
        email_uid: IMAP UID der E-Mail
        log_id: UUID des Import-Logs für Status-Update

    Returns:
        Dict mit Import-Ergebnis
    """
    import asyncio
    from uuid import UUID
    from datetime import datetime, timezone

    async def _retry_email() -> EmailRetryResult:
        from app.services.imports.email_import_service import (
            EmailImportService,
            IMAP_AVAILABLE,
        )
        from app.core.encryption import decrypt_data

        if not IMAP_AVAILABLE:
            return {
                "success": False,
                "error": "imapclient nicht installiert",
            }

        async with get_worker_session_context() as db:
            # Import-Log laden
            log_result = await db.execute(
                select(ImportLog).where(ImportLog.id == UUID(log_id))
            )
            log = log_result.scalar_one_or_none()
            if not log:
                return {"success": False, "error": "Import-Log nicht gefunden"}

            # Config laden
            config_result = await db.execute(
                select(EmailImportConfig).where(EmailImportConfig.id == UUID(config_id))
            )
            config = config_result.scalar_one_or_none()
            if not config:
                log.status = "failed"
                log.error_message = "Email-Konfiguration nicht gefunden"
                await db.commit()
                return {"success": False, "error": "Konfiguration nicht gefunden"}

            log.status = "processing"
            await db.commit()

            try:
                # Email-Service verwenden
                email_service = EmailImportService(db)

                # Credentials entschluesseln
                from app.core.encryption import decrypt_data
                username = decrypt_data(
                    config.username_encrypted,
                    associated_data=f"email_config:{config_id}"
                )
                password = decrypt_data(
                    config.password_encrypted,
                    associated_data=f"email_config:{config_id}"
                )

                # IMAP-Verbindung erstellen
                client = email_service._create_imap_connection(
                    server=config.imap_server,
                    port=config.imap_port,
                    username=username,
                    password=password,
                    use_ssl=config.use_ssl,
                    use_starttls=config.use_starttls,
                )

                try:
                    # Ordner auswählen
                    folder = config.imap_folder or "INBOX"
                    client.select_folder(folder, readonly=True)

                    # Einzelne Email abrufen
                    raw_messages = client.fetch([email_uid], ["RFC822"])
                    if email_uid not in raw_messages:
                        log.status = "failed"
                        log.error_message = "E-Mail nicht mehr verfügbar (UID nicht gefunden)"
                        await db.commit()
                        return {"success": False, "error": "E-Mail nicht gefunden"}

                    raw_email = raw_messages[email_uid][b"RFC822"]
                    parsed = email_service._parse_email(email_uid, raw_email)

                    # Anhaenge verarbeiten
                    documents_created = 0
                    from uuid import uuid4
                    batch_id = uuid4()

                    for attachment in parsed.attachments:
                        doc_result = await email_service._process_attachment(
                            config=config,
                            email=parsed,
                            attachment=attachment,
                            batch_id=batch_id,
                            user_id=config.user_id,
                        )
                        if doc_result.get("success"):
                            documents_created += 1
                            log.document_id = doc_result.get("document_id")

                    # Erfolg protokollieren
                    log.status = "completed"
                    log.error_message = None
                    log.error_code = None
                    log.completed_at = datetime.now(timezone.utc)
                    await db.commit()

                    logger.info(
                        "email_retry_success",
                        log_id=log_id,
                        email_uid=email_uid,
                        documents_created=documents_created,
                    )

                    return {
                        "success": True,
                        "documents_created": documents_created,
                    }

                finally:
                    client.logout()

            except Exception as e:
                log.status = "failed"
                log.error_message = safe_error_detail(e, "Import-Retry")
                await db.commit()

                logger.error(
                    "email_retry_failed",
                    log_id=log_id,
                    email_uid=email_uid,
                    **safe_error_log(e),
                )

                return {"success": False, **safe_error_log(e)}

    return asyncio.run(_retry_email())


@celery_app.task(
    name="app.workers.tasks.import_tasks.retry_single_file",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
)
def retry_single_file(
    self,
    config_id: Optional[str],
    file_path: str,
    log_id: str,
) -> FileRetryResult:
    """Wiederholt den Import einer einzelnen Datei.

    Args:
        config_id: UUID der FolderImportConfig (optional)
        file_path: Pfad zur Datei
        log_id: UUID des Import-Logs für Status-Update

    Returns:
        Dict mit Import-Ergebnis
    """
    import asyncio
    import os
    from uuid import UUID, uuid4
    from datetime import datetime, timezone
    from pathlib import Path

    async def _retry_file() -> FileRetryResult:
        async with get_worker_session_context() as db:
            # Import-Log laden
            log_result = await db.execute(
                select(ImportLog).where(ImportLog.id == UUID(log_id))
            )
            log = log_result.scalar_one_or_none()
            if not log:
                return {"success": False, "error": "Import-Log nicht gefunden"}

            # Prüfen ob Datei noch existiert
            if not os.path.exists(file_path):
                log.status = "failed"
                log.error_message = "Datei existiert nicht mehr"
                await db.commit()
                return {"success": False, "error": "Datei nicht gefunden"}

            log.status = "processing"
            await db.commit()

            try:
                from app.services.imports.folder_import_service import FolderImportService

                folder_service = FolderImportService(db)

                # Config laden wenn vorhanden
                config = None
                if config_id:
                    config_result = await db.execute(
                        select(FolderImportConfig).where(
                            FolderImportConfig.id == UUID(config_id)
                        )
                    )
                    config = config_result.scalar_one_or_none()

                # Datei verarbeiten
                batch_id = uuid4()
                user_id = log.user_id

                if config:
                    # Mit Config verarbeiten
                    result = await folder_service._process_file(
                        config=config,
                        file_path=Path(file_path),
                        batch_id=batch_id,
                        user_id=user_id,
                    )
                else:
                    # Ohne Config: Direkter Dokument-Upload
                    from app.services.document_services.crud_service import DocumentCRUDService
                    from app.core.storage import StorageService
                    import mimetypes

                    storage = StorageService()
                    crud_service = DocumentCRUDService(db, storage)

                    # Datei lesen
                    with open(file_path, "rb") as f:
                        content = f.read()

                    filename = os.path.basename(file_path)
                    mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

                    # Dokument erstellen
                    document = await crud_service.create_document(
                        user_id=user_id,
                        filename=filename,
                        content=content,
                        mime_type=mime_type,
                        metadata={"retry_from_log": log_id},
                    )

                    result = {
                        "success": True,
                        "document_id": document.id,
                    }

                if result.get("success"):
                    log.status = "completed"
                    log.error_message = None
                    log.error_code = None
                    log.completed_at = datetime.now(timezone.utc)
                    log.document_id = result.get("document_id")
                    await db.commit()

                    logger.info(
                        "file_retry_success",
                        log_id=log_id,
                        file_path=file_path,
                    )

                    return {"success": True, "document_id": str(result.get("document_id"))}

                elif result.get("duplicate"):
                    log.status = "skipped"
                    log.error_message = "Duplikat"
                    await db.commit()
                    return {"success": True, "skipped": True, "reason": "duplicate"}

                else:
                    log.status = "failed"
                    log.error_message = result.get("error", "Unbekannter Fehler")
                    await db.commit()
                    return {"success": False, "error": result.get("error")}

            except Exception as e:
                log.status = "failed"
                log.error_message = safe_error_detail(e, "Import-Retry")
                await db.commit()

                logger.error(
                    "file_retry_failed",
                    log_id=log_id,
                    file_path=file_path,
                    **safe_error_log(e),
                )

                return {"success": False, **safe_error_log(e)}

    return asyncio.run(_retry_file())


# =============================================================================
# Cleanup Tasks
# =============================================================================


@celery_app.task(name="app.workers.tasks.import_tasks.cleanup_old_import_logs")
def cleanup_old_import_logs(retention_days: int = 90) -> CleanupResult:
    """Löscht alte Import-Logs.

    Typisches Schedule: Täglich um 03:00.

    Args:
        retention_days: Tage nach denen Logs gelöscht werden

    Returns:
        Dict mit Cleanup-Statistiken
    """
    import asyncio

    async def _cleanup() -> CleanupResult:
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)

        async with get_worker_session_context() as db:
            # Zaehlen
            count_result = await db.execute(
                select(func.count()).where(
                    and_(
                        ImportLog.started_at < cutoff,
                        ImportLog.status.in_(["completed", "skipped"]),
                    )
                )
            )
            count = count_result.scalar() or 0

            if count > 0:
                # Löschen
                await db.execute(
                    delete(ImportLog).where(
                        and_(
                            ImportLog.started_at < cutoff,
                            ImportLog.status.in_(["completed", "skipped"]),
                        )
                    )
                )
                await db.commit()

            logger.info(
                "import_logs_cleaned",
                deleted=count,
                retention_days=retention_days,
            )

            return {"deleted": count, "retention_days": retention_days}

    return asyncio.run(_cleanup())


@celery_app.task(name="app.workers.tasks.import_tasks.reset_daily_folder_stats")
def reset_daily_folder_stats() -> ResetStatsResult:
    """Setzt tägliche Folder-Statistiken zurück.

    Typisches Schedule: Täglich um 00:00.

    Returns:
        Dict mit Reset-Statistiken
    """
    import asyncio

    async def _reset() -> ResetStatsResult:
        async with get_worker_session_context() as db:
            result = await db.execute(
                update(FolderImportConfig)
                .where(FolderImportConfig.files_processed_today > 0)
                .values(files_processed_today=0)
            )
            await db.commit()

            affected = result.rowcount

            logger.info(
                "folder_daily_stats_reset",
                configs_reset=affected,
            )

            return {"configs_reset": affected}

    return asyncio.run(_reset())


# =============================================================================
# Folder Import Rule Tasks (konsolidiert aus folder_import_rule_tasks.py)
# =============================================================================


@celery_app.task(
    bind=True,
    name="folder_import_rules.apply_pending",
    acks_late=True,
    max_retries=2,
    default_retry_delay=120,
    soft_time_limit=300,
    time_limit=360,
)
def apply_rules_to_pending_imports(self, company_id: str) -> ApplyRulesResult:
    """Wendet Import-Regeln auf kuerzlich importierte Dokumente an.

    Re-evaluiert Regeln auf Dokumente die importiert wurden bevor
    die Regel erstellt wurde (z.B. neue Regeln die rueckwirkend
    angewendet werden sollen).

    Durchsucht ImportLog-Eintraege mit status='completed' der
    letzten 24 Stunden.

    Args:
        company_id: UUID der Firma (als String) fuer Mandanten-Trennung

    Returns:
        Dict mit Auswertungs-Statistiken
    """
    import asyncio
    import uuid as _uuid

    async def _apply_rules_pending_async(company_id_str: str) -> ApplyRulesResult:
        from app.services.imports.import_rule_service import ImportRuleService

        async with get_worker_session_context() as db:
            company_uuid: Optional[_uuid.UUID] = None
            if company_id_str:
                try:
                    company_uuid = _uuid.UUID(company_id_str)
                except ValueError:
                    logger.error(
                        "apply_pending_invalid_company_id",
                        company_id=company_id_str,
                    )
                    raise ValueError(
                        f"Ungueltige Firmen-ID: {company_id_str}"
                    )

            cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

            query = (
                select(ImportLog)
                .where(
                    and_(
                        ImportLog.status == "completed",
                        ImportLog.completed_at >= cutoff,
                        ImportLog.source_type == "folder",
                    )
                )
                .limit(200)
            )

            result = await db.execute(query)
            logs = result.scalars().all()

            rules_applied: int = 0

            for log in logs:
                if not log.document_id or not log.user_id:
                    continue
                try:
                    rule_service = ImportRuleService(db)
                    original_filename: str = log.original_filename or ""
                    file_extension: str = ""
                    if original_filename and "." in original_filename:
                        file_extension = "." + original_filename.rsplit(".", 1)[-1].lower()

                    metadata: Dict[str, Any] = {
                        "filename": original_filename,
                        "file_extension": file_extension,
                        "file_size": log.file_size or 0,
                        "mime_type": log.mime_type or "",
                        "folder_path": log.original_path or "",
                    }

                    matches = await rule_service.evaluate_rules(
                        user_id=log.user_id,
                        metadata=metadata,
                        source_type="folder",
                        config_id=log.folder_config_id,
                    )

                    if matches:
                        rules_applied += 1
                        rule_service.apply_actions(matches)
                        logger.debug(
                            "pending_import_rules_applied",
                            log_id=str(log.id),
                            document_id=str(log.document_id),
                            rule_count=len(matches),
                        )

                except Exception as e:
                    logger.warning(
                        "rule_reeval_failed",
                        log_id=str(log.id),
                        **safe_error_log(e),
                    )

            await db.commit()
            return {
                "logs_checked": len(logs),
                "rules_applied": rules_applied,
            }

    try:
        result = asyncio.run(
            _apply_rules_pending_async(company_id)
        )
        logger.info(
            "apply_pending_rules_completed",
            company_id=company_id,
            logs_checked=result["logs_checked"],
            rules_applied=result["rules_applied"],
        )
        return result
    except Exception as e:
        logger.error(
            "apply_pending_rules_failed",
            company_id=company_id,
            **safe_error_log(e),
        )
        raise self.retry(exc=e)


@celery_app.task(
    bind=True,
    name="folder_import_rules.scan_folder",
    acks_late=True,
    max_retries=2,
    default_retry_delay=60,
    soft_time_limit=300,
    time_limit=360,
)
def scan_import_folder(self, folder_path: str, company_id: str) -> ScanFolderResult:
    """Scannt einen einzelnen Import-Ordner gezielt.

    Findet die passende FolderImportConfig fuer den Pfad
    und fuehrt poll_folder() aus.

    Args:
        folder_path: Absoluter Pfad des zu scannenden Ordners
        company_id: UUID der Firma als String

    Returns:
        Dict mit Scan-Ergebnis
    """
    import asyncio
    from sqlalchemy import or_

    if not folder_path or not folder_path.strip():
        logger.error("scan_folder_invalid_path", folder_path=folder_path)
        raise ValueError("Ordnerpfad darf nicht leer sein")

    # Basic security: reject obvious traversal attempts
    normalized = folder_path.replace("\\", "/")
    if ".." in normalized.split("/"):
        logger.error(
            "scan_folder_path_traversal_blocked",
            folder_path=folder_path,
        )
        raise ValueError(
            f"Ungultiger Ordnerpfad (Path-Traversal erkannt): {folder_path}"
        )

    async def _scan_folder_async(path: str) -> ScanFolderResult:
        from app.services.imports.folder_import_service import FolderImportService

        async with get_worker_session_context() as db:
            # Passende Config anhand watch_path suchen
            result = await db.execute(
                select(FolderImportConfig).where(
                    and_(
                        FolderImportConfig.is_active == True,
                        or_(
                            FolderImportConfig.watch_path == path,
                            FolderImportConfig.watch_path == path.rstrip("/"),
                            FolderImportConfig.watch_path == path.rstrip("\\"),
                        ),
                    )
                )
            )
            config = result.scalars().first()

            if not config:
                logger.warning(
                    "scan_folder_no_config_found",
                    folder_path=path,
                )
                return {
                    "folder_path": path,
                    "config_found": False,
                    "files_processed": 0,
                    "documents_created": 0,
                    "errors": [
                        {
                            "error": f"Keine aktive Konfiguration fuer Pfad '{path}' gefunden"
                        }
                    ],
                }

            service = FolderImportService(db)
            poll_result = await service.poll_folder(
                config_id=config.id,
                user_id=config.user_id,
            )

            return {
                "folder_path": path,
                "config_found": True,
                "config_id": str(config.id),
                "files_processed": poll_result.files_processed,
                "documents_created": poll_result.documents_created,
                "duplicates_skipped": poll_result.duplicates_skipped,
                "errors": poll_result.errors,
            }

    try:
        result = asyncio.run(
            _scan_folder_async(folder_path)
        )
        logger.info(
            "scan_import_folder_completed",
            folder_path=folder_path,
            config_found=result["config_found"],
            files_processed=result.get("files_processed", 0),
            documents_created=result.get("documents_created", 0),
        )
        return result
    except ValueError:
        raise
    except Exception as e:
        logger.error(
            "scan_import_folder_failed",
            folder_path=folder_path,
            **safe_error_log(e),
        )
        raise self.retry(exc=e)


# =============================================================================
# Health Check Tasks
# =============================================================================


@celery_app.task(name="app.workers.tasks.import_tasks.check_email_connection_health")
def check_email_connection_health() -> ConnectionHealthResult:
    """Prüft Gesundheit aller Email-Verbindungen.

    Typisches Schedule: Alle 30 Minuten.

    Returns:
        Dict mit Health-Status
    """
    import asyncio
    from app.services.imports import EmailImportService

    async def _check_all() -> ConnectionHealthResult:
        stats = {
            "total": 0,
            "healthy": 0,
            "unhealthy": 0,
            "errors": [],
        }

        async with get_worker_session_context() as db:
            result = await db.execute(
                select(EmailImportConfig).where(
                    EmailImportConfig.is_active == True
                )
            )
            configs = result.scalars().all()

            for config in configs:
                stats["total"] += 1

                try:
                    service = EmailImportService(db)
                    test_result = await service.test_connection(
                        config_id=config.id,
                        user_id=config.user_id,
                    )

                    if test_result.get("success"):
                        stats["healthy"] += 1
                    else:
                        stats["unhealthy"] += 1
                        stats["errors"].append({
                            "config_id": str(config.id),
                            "name": config.name,
                            "error": test_result.get("message"),
                        })

                except Exception as e:
                    stats["unhealthy"] += 1
                    stats["errors"].append({
                        "config_id": str(config.id),
                        "name": config.name,
                        "error": safe_error_detail(e, "Vorgang"),
                    })

        return stats

    result = asyncio.run(_check_all())

    if result["unhealthy"] > 0:
        logger.warning(
            "unhealthy_email_connections",
            unhealthy=result["unhealthy"],
            total=result["total"],
        )
    else:
        logger.info(
            "email_connections_healthy",
            total=result["total"],
        )

    return result



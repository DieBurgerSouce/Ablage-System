"""
Email und Folder Import Celery Tasks.

Enterprise-Level Import-Automatisierung:
- Periodische E-Mail-Synchronisation
- Folder-Polling als Watchdog-Fallback
- Retry fehlgeschlagener Imports
- Import-Log Cleanup
- Statistik-Reset

Feinpoliert und durchdacht - Zuverlaessige Import-Automatisierung.
"""

import structlog
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from celery import shared_task
from sqlalchemy import select, and_, update, delete, func

from app.workers.celery_app import celery_app
from app.db.session import get_async_session_context
from app.db.models import (
    EmailImportConfig,
    FolderImportConfig,
    ImportLog,
    ImportRule,
)

logger = structlog.get_logger(__name__)


# =============================================================================
# Email Sync Tasks
# =============================================================================


@celery_app.task(
    name="import.sync_all_email_configs",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
)
def sync_all_email_configs(self) -> Dict[str, Any]:
    """Synchronisiert alle aktiven Email-Konfigurationen.

    Wird periodisch via Celery Beat aufgerufen.
    Typisches Schedule: Alle 15 Minuten.

    Returns:
        Dict mit Sync-Statistiken
    """
    import asyncio
    from app.services.imports import EmailImportService

    async def _sync_all():
        stats = {
            "configs_processed": 0,
            "emails_processed": 0,
            "documents_created": 0,
            "errors": [],
        }

        async with get_async_session_context() as db:
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
                # Check ob Sync faellig ist
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
                        "error": str(e),
                    })
                    logger.error(
                        "email_config_sync_failed",
                        config_id=str(config.id),
                        error=str(e),
                    )

        return stats

    try:
        result = asyncio.get_event_loop().run_until_complete(_sync_all())
        logger.info(
            "email_sync_batch_completed",
            configs=result["configs_processed"],
            emails=result["emails_processed"],
            documents=result["documents_created"],
        )
        return result
    except Exception as e:
        logger.error("email_sync_batch_failed", error=str(e))
        raise self.retry(exc=e)


@celery_app.task(
    name="import.sync_email_config",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def sync_email_config(self, config_id: str, user_id: str, max_emails: int = 100) -> Dict[str, Any]:
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

    async def _sync():
        async with get_async_session_context() as db:
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
        return asyncio.get_event_loop().run_until_complete(_sync())
    except Exception as e:
        logger.error(
            "email_sync_task_failed",
            config_id=config_id,
            error=str(e),
        )
        raise self.retry(exc=e)


# =============================================================================
# Folder Polling Tasks
# =============================================================================


@celery_app.task(
    name="import.poll_all_folder_configs",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
)
def poll_all_folder_configs(self) -> Dict[str, Any]:
    """Pollt alle aktiven Folder-Konfigurationen.

    Dient als Fallback wenn Watchdog nicht laeuft
    (z.B. bei Netzwerklaufwerken).

    Typisches Schedule: Alle 5 Minuten.

    Returns:
        Dict mit Poll-Statistiken
    """
    import asyncio
    from app.services.imports import FolderImportService

    async def _poll_all():
        stats = {
            "configs_processed": 0,
            "files_processed": 0,
            "documents_created": 0,
            "errors": [],
        }

        async with get_async_session_context() as db:
            now = datetime.now(timezone.utc)

            # Configs laden die nicht via Watchdog ueberwacht werden
            result = await db.execute(
                select(FolderImportConfig).where(
                    and_(
                        FolderImportConfig.is_active == True,
                        # Nur wenn Watcher nicht laeuft
                        FolderImportConfig.watcher_status != "running",
                    )
                )
            )
            configs = result.scalars().all()

            for config in configs:
                # Check ob Polling faellig ist
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
                        "error": str(e),
                    })
                    logger.error(
                        "folder_config_poll_failed",
                        config_id=str(config.id),
                        error=str(e),
                    )

        return stats

    try:
        result = asyncio.get_event_loop().run_until_complete(_poll_all())
        logger.info(
            "folder_poll_batch_completed",
            configs=result["configs_processed"],
            files=result["files_processed"],
            documents=result["documents_created"],
        )
        return result
    except Exception as e:
        logger.error("folder_poll_batch_failed", error=str(e))
        raise self.retry(exc=e)


@celery_app.task(
    name="import.poll_folder_config",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def poll_folder_config(self, config_id: str, user_id: str) -> Dict[str, Any]:
    """Pollt eine einzelne Folder-Konfiguration.

    Args:
        config_id: UUID der Folder-Config
        user_id: UUID des Users

    Returns:
        Dict mit Poll-Ergebnis
    """
    import asyncio
    from app.services.imports import FolderImportService

    async def _poll():
        async with get_async_session_context() as db:
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
        return asyncio.get_event_loop().run_until_complete(_poll())
    except Exception as e:
        logger.error(
            "folder_poll_task_failed",
            config_id=config_id,
            error=str(e),
        )
        raise self.retry(exc=e)


# =============================================================================
# Retry Tasks
# =============================================================================


@celery_app.task(
    name="import.retry_failed_imports",
    bind=True,
    max_retries=1,
)
def retry_failed_imports(self) -> Dict[str, Any]:
    """Wiederholt fehlgeschlagene Imports.

    Versucht Imports die mit bestimmten Fehlern fehlgeschlagen
    sind erneut zu verarbeiten.

    Typisches Schedule: Alle 30 Minuten.

    Returns:
        Dict mit Retry-Statistiken
    """
    import asyncio
    from app.services.imports import EmailImportService, FolderImportService

    async def _retry_all():
        stats = {
            "retried": 0,
            "successful": 0,
            "failed": 0,
        }

        async with get_async_session_context() as db:
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
                        # Email-Import: Trigger Celery Task fuer einzelne Email
                        from app.workers.celery_app import celery_app as celery
                        celery.send_task(
                            "import.retry_single_email",
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
                        # Folder-Import: Trigger Celery Task fuer einzelne Datei
                        from app.workers.celery_app import celery_app as celery
                        celery.send_task(
                            "import.retry_single_file",
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
                        log.error_message = "Unbekannter Import-Typ fuer Retry"
                        await db.commit()
                        stats["failed"] += 1
                        continue

                except Exception as e:
                    stats["failed"] += 1
                    logger.warning(
                        "import_retry_failed",
                        log_id=str(log.id),
                        error=str(e),
                    )

        return stats

    try:
        return asyncio.get_event_loop().run_until_complete(_retry_all())
    except Exception as e:
        logger.error("retry_failed_imports_error", error=str(e))
        return {"error": str(e)}


@celery_app.task(name="import.retry_import")
def retry_import_task(log_id: str) -> Dict[str, Any]:
    """Wiederholt einen einzelnen fehlgeschlagenen Import.

    Dispatcht automatisch zum richtigen Retry-Task basierend auf source_type.

    Args:
        log_id: UUID des Import-Logs

    Returns:
        Dict mit Retry-Ergebnis
    """
    import asyncio

    async def _retry():
        async with get_async_session_context() as db:
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
                    "import.retry_single_email",
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
                    "import.retry_single_file",
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

    return asyncio.get_event_loop().run_until_complete(_retry())


@celery_app.task(
    name="import.retry_single_email",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
)
def retry_single_email(
    self,
    config_id: str,
    email_uid: int,
    log_id: str,
) -> Dict[str, Any]:
    """Wiederholt den Import einer einzelnen E-Mail.

    Holt die E-Mail erneut via IMAP und verarbeitet die Anhaenge.

    Args:
        config_id: UUID der EmailImportConfig
        email_uid: IMAP UID der E-Mail
        log_id: UUID des Import-Logs fuer Status-Update

    Returns:
        Dict mit Import-Ergebnis
    """
    import asyncio
    from uuid import UUID
    from datetime import datetime, timezone

    async def _retry_email():
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

        async with get_async_session_context() as db:
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
                    # Ordner auswaehlen
                    folder = config.imap_folder or "INBOX"
                    client.select_folder(folder, readonly=True)

                    # Einzelne Email abrufen
                    raw_messages = client.fetch([email_uid], ["RFC822"])
                    if email_uid not in raw_messages:
                        log.status = "failed"
                        log.error_message = "E-Mail nicht mehr verfuegbar (UID nicht gefunden)"
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
                log.error_message = f"Retry fehlgeschlagen: {str(e)}"
                await db.commit()

                logger.error(
                    "email_retry_failed",
                    log_id=log_id,
                    email_uid=email_uid,
                    error=str(e),
                )

                return {"success": False, "error": str(e)}

    return asyncio.get_event_loop().run_until_complete(_retry_email())


@celery_app.task(
    name="import.retry_single_file",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
)
def retry_single_file(
    self,
    config_id: Optional[str],
    file_path: str,
    log_id: str,
) -> Dict[str, Any]:
    """Wiederholt den Import einer einzelnen Datei.

    Args:
        config_id: UUID der FolderImportConfig (optional)
        file_path: Pfad zur Datei
        log_id: UUID des Import-Logs fuer Status-Update

    Returns:
        Dict mit Import-Ergebnis
    """
    import asyncio
    import os
    from uuid import UUID, uuid4
    from datetime import datetime, timezone
    from pathlib import Path

    async def _retry_file():
        async with get_async_session_context() as db:
            # Import-Log laden
            log_result = await db.execute(
                select(ImportLog).where(ImportLog.id == UUID(log_id))
            )
            log = log_result.scalar_one_or_none()
            if not log:
                return {"success": False, "error": "Import-Log nicht gefunden"}

            # Pruefen ob Datei noch existiert
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
                log.error_message = f"Retry fehlgeschlagen: {str(e)}"
                await db.commit()

                logger.error(
                    "file_retry_failed",
                    log_id=log_id,
                    file_path=file_path,
                    error=str(e),
                )

                return {"success": False, "error": str(e)}

    return asyncio.get_event_loop().run_until_complete(_retry_file())


# =============================================================================
# Cleanup Tasks
# =============================================================================


@celery_app.task(name="import.cleanup_old_logs")
def cleanup_old_import_logs(retention_days: int = 90) -> Dict[str, Any]:
    """Loescht alte Import-Logs.

    Typisches Schedule: Taeglich um 03:00.

    Args:
        retention_days: Tage nach denen Logs geloescht werden

    Returns:
        Dict mit Cleanup-Statistiken
    """
    import asyncio

    async def _cleanup():
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)

        async with get_async_session_context() as db:
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
                # Loeschen
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

    return asyncio.get_event_loop().run_until_complete(_cleanup())


@celery_app.task(name="import.reset_daily_stats")
def reset_daily_folder_stats() -> Dict[str, Any]:
    """Setzt taegliche Folder-Statistiken zurueck.

    Typisches Schedule: Taeglich um 00:00.

    Returns:
        Dict mit Reset-Statistiken
    """
    import asyncio

    async def _reset():
        async with get_async_session_context() as db:
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

    return asyncio.get_event_loop().run_until_complete(_reset())


# =============================================================================
# Health Check Tasks
# =============================================================================


@celery_app.task(name="import.check_connection_health")
def check_email_connection_health() -> Dict[str, Any]:
    """Prueft Gesundheit aller Email-Verbindungen.

    Typisches Schedule: Alle 30 Minuten.

    Returns:
        Dict mit Health-Status
    """
    import asyncio
    from app.services.imports import EmailImportService

    async def _check_all():
        stats = {
            "total": 0,
            "healthy": 0,
            "unhealthy": 0,
            "errors": [],
        }

        async with get_async_session_context() as db:
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
                        "error": str(e),
                    })

        return stats

    result = asyncio.get_event_loop().run_until_complete(_check_all())

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


# =============================================================================
# Celery Beat Schedule (wird in celery_app.py registriert)
# =============================================================================

IMPORT_BEAT_SCHEDULE = {
    # Email-Sync alle 15 Minuten
    "sync-all-email-configs": {
        "task": "import.sync_all_email_configs",
        "schedule": 900.0,  # 15 Minuten
        "options": {"queue": "default"},
    },
    # Folder-Polling alle 5 Minuten
    "poll-all-folder-configs": {
        "task": "import.poll_all_folder_configs",
        "schedule": 300.0,  # 5 Minuten
        "options": {"queue": "default"},
    },
    # Retry fehlgeschlagene Imports alle 30 Minuten
    "retry-failed-imports": {
        "task": "import.retry_failed_imports",
        "schedule": 1800.0,  # 30 Minuten
        "options": {"queue": "default"},
    },
    # Cleanup alte Logs taeglich um 03:00
    "cleanup-import-logs": {
        "task": "import.cleanup_old_logs",
        "schedule": {
            "hour": 3,
            "minute": 0,
        },
        "options": {"queue": "default"},
    },
    # Reset taegliche Stats um 00:00
    "reset-daily-folder-stats": {
        "task": "import.reset_daily_stats",
        "schedule": {
            "hour": 0,
            "minute": 0,
        },
        "options": {"queue": "default"},
    },
    # Health-Check alle 30 Minuten
    "check-email-health": {
        "task": "import.check_connection_health",
        "schedule": 1800.0,  # 30 Minuten
        "options": {"queue": "default"},
    },
}

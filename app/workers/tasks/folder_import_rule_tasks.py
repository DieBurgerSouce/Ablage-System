"""Folder-Import + Import-Regel Tasks.

Periodische Tasks fuer:
- Folder-Polling mit automatischer Regelauswertung
- Re-Evaluation von Regeln auf ausstehende Imports
- Gezielter Scan einzelner Import-Ordner

Feinpoliert und durchdacht.
"""

import asyncio
import uuid
from typing import Dict, List, Optional
import structlog

from app.core.safe_errors import safe_error_log
from app.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


def _run_async(coro):
    """Fuehrt eine async Coroutine synchron aus (fuer Celery)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# =============================================================================
# Task 1: Poll ALL active folder configs (with rule evaluation built-in)
# =============================================================================


@celery_app.task(
    bind=True,
    name="folder_import_rules.poll_all",
    acks_late=True,
    max_retries=3,
    default_retry_delay=60,
    soft_time_limit=300,
    time_limit=360,
)
def poll_folder_imports_task(self) -> Dict:
    """Pollt alle aktiven Ordner-Import-Konfigurationen mit Regelauswertung.

    Wird periodisch via Celery Beat aufgerufen.
    Typisches Schedule: Alle 5 Minuten.

    Die FolderImportService.poll_folder() Methode ruft intern
    _apply_import_rules() auf - keine doppelte Regelauswertung.

    Returns:
        Dict mit Ergebnis-Statistiken
    """
    async def _poll_all_folders_async() -> Dict:
        from app.db.session import async_session_factory
        from app.db.models import FolderImportConfig
        from sqlalchemy import select
        from app.services.imports.folder_import_service import FolderImportService

        async with async_session_factory() as db:
            result = await db.execute(
                select(FolderImportConfig).where(
                    FolderImportConfig.is_active == True
                )
            )
            configs = result.scalars().all()

            total_processed: int = 0
            total_created: int = 0
            errors: List[Dict] = []

            for config in configs:
                try:
                    service = FolderImportService(db)
                    import_result = await service.poll_folder(
                        config_id=config.id,
                        user_id=config.user_id,
                    )
                    total_processed += import_result.files_processed
                    total_created += import_result.documents_created
                except Exception as e:
                    errors.append({
                        "config_id": str(config.id),
                        "error": str(e),
                    })
                    logger.warning(
                        "folder_poll_config_failed",
                        config_id=str(config.id),
                        **safe_error_log(e),
                    )

            return {
                "configs_polled": len(configs),
                "total_files_processed": total_processed,
                "total_documents_created": total_created,
                "errors": errors,
            }

    try:
        result = _run_async(_poll_all_folders_async())
        logger.info(
            "folder_import_rule_poll_completed",
            configs_polled=result["configs_polled"],
            total_files_processed=result["total_files_processed"],
            total_documents_created=result["total_documents_created"],
            error_count=len(result["errors"]),
        )
        return result
    except Exception as e:
        logger.error(
            "folder_import_rule_poll_failed",
            **safe_error_log(e),
        )
        raise self.retry(exc=e)


# =============================================================================
# Task 2: Re-evaluate import rules on recently completed imports
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
def apply_rules_to_pending_imports_task(self, company_id: str) -> Dict:
    """Wendet Import-Regeln auf kueerzlich importierte Dokumente an.

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
    async def _apply_rules_pending_async(company_id_str: str) -> Dict:
        from app.db.session import async_session_factory
        from app.db.models import ImportLog
        from app.services.imports.import_rule_service import ImportRuleService
        from sqlalchemy import select, and_
        from datetime import datetime, timezone, timedelta

        async with async_session_factory() as db:
            company_uuid: Optional[uuid.UUID] = None
            if company_id_str:
                try:
                    company_uuid = uuid.UUID(company_id_str)
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

                    metadata: Dict = {
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
        result = _run_async(_apply_rules_pending_async(company_id))
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


# =============================================================================
# Task 3: Scan a specific folder path
# =============================================================================


@celery_app.task(
    bind=True,
    name="folder_import_rules.scan_folder",
    acks_late=True,
    max_retries=2,
    default_retry_delay=60,
    soft_time_limit=300,
    time_limit=360,
)
def scan_import_folder_task(self, folder_path: str, company_id: str) -> Dict:
    """Scannt einen einzelnen Import-Ordner gezielt.

    Findet die passende FolderImportConfig fuer den Pfad
    und fuehrt poll_folder() aus.

    Args:
        folder_path: Absoluter Pfad des zu scannenden Ordners
        company_id: UUID der Firma als String

    Returns:
        Dict mit Scan-Ergebnis
    """
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
            f"Ungültiger Ordnerpfad (Path-Traversal erkannt): {folder_path}"
        )

    async def _scan_folder_async(path: str, cid: str) -> Dict:
        from app.db.session import async_session_factory
        from app.db.models import FolderImportConfig
        from app.services.imports.folder_import_service import FolderImportService
        from sqlalchemy import select, or_, and_

        async with async_session_factory() as db:
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
        result = _run_async(_scan_folder_async(folder_path, company_id))
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

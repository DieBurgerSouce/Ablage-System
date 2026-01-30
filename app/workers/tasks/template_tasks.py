# -*- coding: utf-8 -*-
"""
Document Template Engine Celery Tasks (F11).

Enterprise-Level Template-Automatisierung:
- Batch-Rendering von Templates (z.B. Monats-Rechnungen)
- Temporaere generierte Dokumente aufraemen
- Template-Cache Management

Feinpoliert und durchdacht - Zuverlaessige Template-Verarbeitung.
"""

import structlog
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from celery import shared_task
from sqlalchemy import select, and_, delete, func

from app.workers.celery_app import celery_app
from app.db.session import get_async_session_context
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


# =============================================================================
# Template Rendering Tasks
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.template_tasks.render_template_batch",
    bind=True,
    max_retries=3,
    default_retry_delay=300,
    queue="metadata",
)
def render_template_batch(
    self,
    template_id: str,
    data_items: List[Dict[str, Any]],
    user_id: str,
    company_id: str,
    batch_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Rendert mehrere Dokumente aus einem Template (Batch-Verarbeitung).

    Typische Anwendungsfaelle:
    - Monats-Rechnungen fuer alle Kunden generieren
    - Serienbrief-Erstellung
    - Massenhafte Vertraege generieren
    - Quartals-Reports fuer alle Projekte

    Args:
        template_id: UUID des Document Templates
        data_items: Liste von Daten-Dictionaries (eines pro Dokument)
        user_id: UUID des initiierenden Benutzers
        company_id: UUID der Company (Multi-Tenant)
        batch_name: Optionaler Name fuer den Batch-Job

    Returns:
        Dict mit Batch-Ergebnis:
            - total: Anzahl zu rendernder Dokumente
            - successful: Erfolgreich gerenderte Dokumente
            - failed: Fehlgeschlagene Dokumente
            - document_ids: Liste der erstellten Dokument-IDs
            - errors: Liste von Fehlern

    Raises:
        Retry bei temporaeren Fehlern
    """
    import asyncio

    async def _render_batch():
        from app.services.template_engine_service import TemplateEngineService

        result = {
            "batch_name": batch_name or f"batch_{datetime.now(timezone.utc).isoformat()}",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "total": len(data_items),
            "successful": 0,
            "failed": 0,
            "document_ids": [],
            "errors": [],
        }

        logger.info(
            "template_batch_start",
            template_id=template_id,
            total_items=len(data_items),
            batch_name=batch_name,
        )

        async with get_async_session_context() as db:
            service = TemplateEngineService(db)

            for index, data in enumerate(data_items):
                try:
                    # Template rendern
                    rendered_doc = await service.render_template(
                        template_id=UUID(template_id),
                        data=data,
                        user_id=UUID(user_id),
                        company_id=UUID(company_id),
                        output_format=data.get("output_format", "pdf"),
                    )

                    result["successful"] += 1
                    result["document_ids"].append(str(rendered_doc.id))

                    logger.info(
                        "template_batch_item_success",
                        template_id=template_id,
                        document_id=str(rendered_doc.id),
                        index=index,
                    )

                except Exception as e:
                    result["failed"] += 1
                    error_detail = {
                        "index": index,
                        "error": safe_error_detail(e, "Vorgang"),
                        "data_preview": str(data)[:200],  # Gekuerzter Preview
                    }
                    result["errors"].append(error_detail)

                    logger.error(
                        "template_batch_item_failed",
                        template_id=template_id,
                        index=index,
                        **safe_error_log(e),
                    )

            await db.commit()

        result["completed_at"] = datetime.now(timezone.utc).isoformat()

        logger.info(
            "template_batch_complete",
            template_id=template_id,
            successful=result["successful"],
            failed=result["failed"],
            batch_name=batch_name,
        )

        return result

    try:
        return asyncio.get_event_loop().run_until_complete(_render_batch())
    except Exception as e:
        logger.error(
            "template_batch_error",
            template_id=template_id,
            **safe_error_log(e),
        )
        raise self.retry(exc=e)


@celery_app.task(
    name="app.workers.tasks.template_tasks.render_template_single",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    queue="metadata",
)
def render_template_single(
    self,
    template_id: str,
    data: Dict[str, Any],
    user_id: str,
    company_id: str,
    output_format: str = "pdf",
) -> Dict[str, Any]:
    """Rendert ein einzelnes Dokument aus einem Template.

    Fuer asynchrone Template-Rendering Jobs die nicht sofort
    ausgefuehrt werden muessen.

    Args:
        template_id: UUID des Document Templates
        data: Template-Daten (Jinja2 Context)
        user_id: UUID des Benutzers
        company_id: UUID der Company
        output_format: Ausgabeformat (pdf, docx, html)

    Returns:
        Dict mit Rendering-Ergebnis:
            - success: Boolean
            - document_id: UUID des generierten Dokuments
            - error: Fehlermeldung falls failed

    Raises:
        Retry bei temporaeren Fehlern
    """
    import asyncio

    async def _render_single():
        from app.services.template_engine_service import TemplateEngineService

        async with get_async_session_context() as db:
            try:
                service = TemplateEngineService(db)

                rendered_doc = await service.render_template(
                    template_id=UUID(template_id),
                    data=data,
                    user_id=UUID(user_id),
                    company_id=UUID(company_id),
                    output_format=output_format,
                )

                await db.commit()

                logger.info(
                    "template_single_render_success",
                    template_id=template_id,
                    document_id=str(rendered_doc.id),
                    format=output_format,
                )

                return {
                    "success": True,
                    "document_id": str(rendered_doc.id),
                    "template_id": template_id,
                }

            except Exception as e:
                logger.error(
                    "template_single_render_failed",
                    template_id=template_id,
                    **safe_error_log(e),
                )
                return {
                    "success": False,
                    "error": safe_error_detail(e, "Vorgang"),
                    "template_id": template_id,
                }

    try:
        return asyncio.get_event_loop().run_until_complete(_render_single())
    except Exception as e:
        logger.error(
            "template_single_render_error",
            template_id=template_id,
            **safe_error_log(e),
        )
        raise self.retry(exc=e)


# =============================================================================
# Cleanup Tasks
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.template_tasks.cleanup_temp_files",
    bind=True,
    max_retries=2,
    queue="maintenance",
)
def cleanup_temp_files(
    self,
    max_age_hours: int = 24,
) -> Dict[str, Any]:
    """Raeumt temporaere generierte Dokumente auf.

    Loescht generierte Dokumente die als temporaer markiert sind
    und aelter als max_age_hours sind. Dies verhindert Speicher-Muell
    von einmalig generierten Preview-Dokumenten.

    Typisches Schedule: Taeglich um 02:00.

    Args:
        max_age_hours: Maximales Alter in Stunden (default: 24h)

    Returns:
        Dict mit Cleanup-Statistiken:
            - cleaned_count: Anzahl gelöschter Dokumente
            - freed_bytes: Freigegebener Speicherplatz
            - max_age_hours: Verwendeter Schwellwert

    Raises:
        Retry bei temporaeren Fehlern
    """
    import asyncio

    async def _cleanup():
        from app.db.models import Document
        from app.core.storage import StorageService

        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)

        result = {
            "cleaned_count": 0,
            "freed_bytes": 0,
            "max_age_hours": max_age_hours,
            "cutoff_time": cutoff_time.isoformat(),
        }

        logger.info(
            "temp_files_cleanup_start",
            max_age_hours=max_age_hours,
            cutoff_time=cutoff_time.isoformat(),
        )

        async with get_async_session_context() as db:
            storage = StorageService()

            # Query temporaere Dokumente aelter als cutoff
            query = select(Document).where(
                and_(
                    Document.metadata["is_temporary"].astext.cast(bool) == True,
                    Document.created_at < cutoff_time,
                )
            )

            result_set = await db.execute(query)
            temp_docs = result_set.scalars().all()

            for doc in temp_docs:
                try:
                    # Dateigröße vor Löschung
                    file_size = doc.file_size or 0
                    result["freed_bytes"] += file_size

                    # Storage-Datei löschen
                    if doc.storage_path:
                        await storage.delete_file(doc.storage_path)

                    # DB-Eintrag löschen
                    await db.delete(doc)
                    result["cleaned_count"] += 1

                    logger.debug(
                        "temp_file_deleted",
                        document_id=str(doc.id),
                        file_size=file_size,
                        age_hours=(
                            datetime.now(timezone.utc) - doc.created_at
                        ).total_seconds() / 3600,
                    )

                except Exception as e:
                    logger.warning(
                        "temp_file_cleanup_error",
                        document_id=str(doc.id),
                        **safe_error_log(e),
                    )

            await db.commit()

        # Formatiere Bytes lesbar
        freed_mb = result["freed_bytes"] / (1024 * 1024)
        result["freed_mb"] = round(freed_mb, 2)

        logger.info(
            "temp_files_cleanup_complete",
            cleaned_count=result["cleaned_count"],
            freed_mb=freed_mb,
        )

        return result

    try:
        return asyncio.get_event_loop().run_until_complete(_cleanup())
    except Exception as e:
        logger.error("temp_files_cleanup_error", **safe_error_log(e))
        raise self.retry(exc=e)


@celery_app.task(
    name="app.workers.tasks.template_tasks.cleanup_old_template_versions",
    bind=True,
    max_retries=2,
    queue="maintenance",
)
def cleanup_old_template_versions(
    self,
    keep_versions: int = 10,
) -> Dict[str, Any]:
    """Raeumt alte Template-Versionen auf.

    Behaelt nur die neuesten N Versionen pro Template.
    Aktive Templates und deren Parent-Version werden immer behalten.

    Typisches Schedule: Woechentlich Sonntag 03:00.

    Args:
        keep_versions: Anzahl Versionen die behalten werden (default: 10)

    Returns:
        Dict mit Cleanup-Statistiken:
            - templates_processed: Anzahl verarbeiteter Templates
            - versions_deleted: Geloeschte Versionen
            - keep_versions: Verwendeter Schwellwert

    Raises:
        Retry bei temporaeren Fehlern
    """
    import asyncio

    async def _cleanup_versions():
        from app.db.models import DocumentTemplate
        from sqlalchemy import distinct

        result = {
            "templates_processed": 0,
            "versions_deleted": 0,
            "keep_versions": keep_versions,
        }

        logger.info(
            "template_versions_cleanup_start",
            keep_versions=keep_versions,
        )

        async with get_async_session_context() as db:
            # Alle eindeutigen Template-Namen
            templates_result = await db.execute(
                select(distinct(DocumentTemplate.name)).where(
                    DocumentTemplate.is_deleted == False
                )
            )
            template_names = [row[0] for row in templates_result.all()]

            for template_name in template_names:
                try:
                    # Alle Versionen dieses Templates laden
                    versions_result = await db.execute(
                        select(DocumentTemplate)
                        .where(
                            and_(
                                DocumentTemplate.name == template_name,
                                DocumentTemplate.is_deleted == False,
                            )
                        )
                        .order_by(DocumentTemplate.version.desc())
                    )
                    versions = versions_result.scalars().all()

                    # Skip wenn weniger als keep_versions
                    if len(versions) <= keep_versions:
                        continue

                    result["templates_processed"] += 1

                    # Finde aktive Version und deren Parent
                    active_version = next(
                        (v for v in versions if v.is_active), None
                    )
                    protected_versions = set()
                    if active_version:
                        protected_versions.add(active_version.version)
                        if active_version.parent_version:
                            protected_versions.add(active_version.parent_version)

                    # Behalte neueste N Versionen + geschuetzte
                    to_keep = set(v.version for v in versions[:keep_versions])
                    to_keep.update(protected_versions)

                    # Loesche alte Versionen
                    for version in versions:
                        if version.version not in to_keep:
                            version.is_deleted = True
                            result["versions_deleted"] += 1

                            logger.debug(
                                "template_version_deleted",
                                template_name=template_name,
                                version=version.version,
                            )

                except Exception as e:
                    logger.warning(
                        "template_version_cleanup_error",
                        template_name=template_name,
                        **safe_error_log(e),
                    )

            await db.commit()

        logger.info(
            "template_versions_cleanup_complete",
            templates_processed=result["templates_processed"],
            versions_deleted=result["versions_deleted"],
        )

        return result

    try:
        return asyncio.get_event_loop().run_until_complete(_cleanup_versions())
    except Exception as e:
        logger.error("template_versions_cleanup_error", **safe_error_log(e))
        raise self.retry(exc=e)


# =============================================================================
# Template Statistics & Health Tasks
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.template_tasks.collect_template_stats",
    bind=True,
    queue="metadata",
)
def collect_template_stats(self) -> Dict[str, Any]:
    """Sammelt Statistiken ueber Template-Nutzung.

    Erstellt aggregierte Nutzungs-Statistiken fuer Analytics.

    Typisches Schedule: Taeglich um 04:00.

    Returns:
        Dict mit Template-Statistiken:
            - total_templates: Anzahl aktiver Templates
            - total_renders_today: Renderings heute
            - total_renders_week: Renderings diese Woche
            - most_used_templates: Top 10 Templates nach Nutzung
            - error_rate: Fehlerrate beim Rendering

    Raises:
        Retry bei temporaeren Fehlern
    """
    import asyncio

    async def _collect_stats():
        from app.db.models import DocumentTemplate, Document

        result = {
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "total_templates": 0,
            "total_renders_today": 0,
            "total_renders_week": 0,
            "most_used_templates": [],
            "error_rate": 0.0,
        }

        async with get_async_session_context() as db:
            # Anzahl aktiver Templates
            templates_count = await db.execute(
                select(func.count()).select_from(DocumentTemplate).where(
                    and_(
                        DocumentTemplate.is_active == True,
                        DocumentTemplate.is_deleted == False,
                    )
                )
            )
            result["total_templates"] = templates_count.scalar() or 0

            # Renderings heute
            today_start = datetime.now(timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            today_renders = await db.execute(
                select(func.count()).select_from(Document).where(
                    and_(
                        Document.metadata["template_id"].isnot(None),
                        Document.created_at >= today_start,
                    )
                )
            )
            result["total_renders_today"] = today_renders.scalar() or 0

            # Renderings diese Woche
            week_start = today_start - timedelta(days=today_start.weekday())
            week_renders = await db.execute(
                select(func.count()).select_from(Document).where(
                    and_(
                        Document.metadata["template_id"].isnot(None),
                        Document.created_at >= week_start,
                    )
                )
            )
            result["total_renders_week"] = week_renders.scalar() or 0

            # Note: most_used_templates und error_rate würden komplexere
            # Queries benötigen und sind hier als Platzhalter
            result["most_used_templates"] = []  # TODO: Implementieren
            result["error_rate"] = 0.0  # TODO: Aus Error-Logs berechnen

        logger.info(
            "template_stats_collected",
            total_templates=result["total_templates"],
            renders_today=result["total_renders_today"],
            renders_week=result["total_renders_week"],
        )

        return result

    try:
        return asyncio.get_event_loop().run_until_complete(_collect_stats())
    except Exception as e:
        logger.error("template_stats_collection_error", **safe_error_log(e))
        raise self.retry(exc=e)


# =============================================================================
# Celery Beat Schedule (wird in celery_app.py registriert)
# =============================================================================

TEMPLATE_BEAT_SCHEDULE = {
    # Temp-Files taeglich um 02:00 aufraumen
    "cleanup-template-temp-files": {
        "task": "app.workers.tasks.template_tasks.cleanup_temp_files",
        "schedule": {
            "hour": 2,
            "minute": 0,
        },
        "options": {"queue": "maintenance"},
    },
    # Alte Versionen woechentlich aufraumen (Sonntag 03:00)
    "cleanup-old-template-versions": {
        "task": "app.workers.tasks.template_tasks.cleanup_old_template_versions",
        "schedule": {
            "day_of_week": 0,  # Sonntag
            "hour": 3,
            "minute": 0,
        },
        "options": {"queue": "maintenance"},
    },
    # Statistiken taeglich um 04:00 sammeln
    "collect-template-stats": {
        "task": "app.workers.tasks.template_tasks.collect_template_stats",
        "schedule": {
            "hour": 4,
            "minute": 0,
        },
        "options": {"queue": "metadata"},
    },
}

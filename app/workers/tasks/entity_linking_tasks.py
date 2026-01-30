"""
Entity Linking Celery Tasks.

Automatische Verknuepfung von Dokumenten mit BusinessEntities:
- Batch-Verknuepfung aller unverknuepften Dokumente
- Einzeldokument-Verknuepfung nach OCR
- Automatischer Lauf nach Lexware-Import
- Statistik-Generierung

Feinpoliert und durchdacht - Intelligente Dokument-Entity-Zuordnung.
"""

import structlog
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from uuid import UUID

from celery import shared_task, chain, group
from sqlalchemy import select, and_, func

from app.workers.celery_app import celery_app
from app.db.session import get_async_session_context
from app.db.models import Document, BusinessEntity
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


# =============================================================================
# Batch Linking Tasks
# =============================================================================


@celery_app.task(
    name="entity_linking.link_all_documents",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
)
def link_all_documents_task(
    self,
    min_confidence: float = 0.75,
    batch_size: int = 100,
    only_unlinked: bool = True,
) -> Dict[str, Any]:
    """Verknuepft alle Dokumente mit BusinessEntities.

    Wird nach Lexware-Import automatisch getriggert.
    Kann auch manuell fuer Re-Linking gestartet werden.

    Args:
        min_confidence: Minimale Confidence fuer automatische Verknuepfung
        batch_size: Anzahl Dokumente pro Batch
        only_unlinked: Nur Dokumente ohne business_entity_id

    Returns:
        Dict mit Linking-Statistiken
    """
    import asyncio
    from app.services.document_entity_linker_service import DocumentEntityLinkerService

    async def _link_all():
        async with get_async_session_context() as db:
            service = DocumentEntityLinkerService(db)
            result = await service.link_all_documents(
                min_confidence=min_confidence,
                batch_size=batch_size,
                only_unlinked=only_unlinked,
            )

            return {
                "linked_count": result.linked_count,
                "unlinked_count": result.unlinked_count,
                "low_confidence_count": result.low_confidence_count,
                "error_count": result.error_count,
                "already_linked_count": result.already_linked_count,
            }

    try:
        result = asyncio.get_event_loop().run_until_complete(_link_all())
        logger.info(
            "document_entity_linking_completed",
            linked=result["linked_count"],
            unlinked=result["unlinked_count"],
            low_confidence=result["low_confidence_count"],
            errors=result["error_count"],
        )
        return result
    except Exception as e:
        logger.error("document_entity_linking_failed", **safe_error_log(e))
        raise self.retry(exc=e)


@celery_app.task(
    name="entity_linking.link_single_document",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def link_single_document_task(
    self,
    document_id: str,
    min_confidence: float = 0.75,
) -> Dict[str, Any]:
    """Verknuepft ein einzelnes Dokument mit der besten Entity.

    Wird nach OCR-Completion automatisch getriggert.

    Args:
        document_id: UUID des Dokuments
        min_confidence: Minimale Confidence

    Returns:
        Dict mit Linking-Ergebnis
    """
    import asyncio
    from app.services.document_entity_linker_service import DocumentEntityLinkerService

    async def _link():
        async with get_async_session_context() as db:
            service = DocumentEntityLinkerService(db)
            match = await service.link_document(
                document_id=UUID(document_id),
                min_confidence=min_confidence,
            )

            if match:
                return {
                    "linked": True,
                    "entity_id": str(match.entity.id),
                    "entity_name": match.entity.name,
                    "confidence": match.confidence,
                    "match_type": match.match_type,
                    "match_details": match.match_details,
                }
            else:
                return {
                    "linked": False,
                    "entity_id": None,
                    "reason": "Keine passende Entity gefunden",
                }

    try:
        result = asyncio.get_event_loop().run_until_complete(_link())

        if result["linked"]:
            logger.info(
                "document_linked_to_entity",
                document_id=document_id,
                entity_id=result["entity_id"],
                confidence=result["confidence"],
                match_type=result["match_type"],
            )
        else:
            logger.debug(
                "document_not_linked",
                document_id=document_id,
                reason=result["reason"],
            )

        return result
    except Exception as e:
        logger.error(
            "document_linking_task_failed",
            document_id=document_id,
            **safe_error_log(e),
        )
        raise self.retry(exc=e)


# =============================================================================
# Post-Import Tasks
# =============================================================================


@celery_app.task(
    name="entity_linking.post_lexware_import",
    bind=True,
    max_retries=1,
)
def post_lexware_import_linking_task(self) -> Dict[str, Any]:
    """Startet automatische Verknuepfung nach Lexware-Import.

    Wird nach erfolgreichem LexwareImportService.import_customers()
    oder import_suppliers() aufgerufen.

    Orchestriert:
    1. Batch-Linking aller unverknuepften Dokumente
    2. Statistik-Generierung
    3. Benachrichtigung

    Returns:
        Dict mit Gesamt-Statistiken
    """
    import asyncio
    from app.services.document_entity_linker_service import DocumentEntityLinkerService

    async def _run_post_import():
        stats = {
            "phase": "post_lexware_import",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "documents_processed": 0,
            "linked_count": 0,
            "unlinked_count": 0,
            "low_confidence_count": 0,
        }

        async with get_async_session_context() as db:
            # Zaehle unverknuepfte Dokumente mit OCR-Text
            count_stmt = select(func.count()).select_from(
                select(Document).where(
                    and_(
                        Document.business_entity_id.is_(None),
                        Document.extracted_text.isnot(None),
                        Document.extracted_text != "",
                        Document.deleted_at.is_(None),
                    )
                ).subquery()
            )
            unlinked_count = await db.scalar(count_stmt)

            logger.info(
                "post_import_linking_started",
                unlinked_documents=unlinked_count,
            )

            stats["documents_to_process"] = unlinked_count

            # Linking durchfuehren
            service = DocumentEntityLinkerService(db)
            result = await service.link_all_documents(
                min_confidence=0.75,
                batch_size=100,
                only_unlinked=True,
            )

            stats["documents_processed"] = result.linked_count + result.unlinked_count
            stats["linked_count"] = result.linked_count
            stats["unlinked_count"] = result.unlinked_count
            stats["low_confidence_count"] = result.low_confidence_count
            stats["completed_at"] = datetime.now(timezone.utc).isoformat()

            # Erfolgsrate berechnen
            total = result.linked_count + result.unlinked_count
            if total > 0:
                stats["success_rate"] = round(result.linked_count / total * 100, 1)
            else:
                stats["success_rate"] = 0.0

        return stats

    try:
        result = asyncio.get_event_loop().run_until_complete(_run_post_import())

        logger.info(
            "post_import_linking_completed",
            linked=result["linked_count"],
            success_rate=result["success_rate"],
        )

        return result
    except Exception as e:
        logger.error("post_import_linking_failed", **safe_error_log(e))
        raise self.retry(exc=e)


# =============================================================================
# Statistics Tasks
# =============================================================================


@celery_app.task(name="entity_linking.generate_statistics")
def generate_linking_statistics_task() -> Dict[str, Any]:
    """Generiert Statistiken ueber Entity-Linking.

    Typisches Schedule: Taeglich um 01:00.

    Returns:
        Dict mit Statistiken
    """
    import asyncio

    async def _generate_stats():
        async with get_async_session_context() as db:
            stats = {}

            # Gesamt-Dokumente
            total_docs = await db.scalar(
                select(func.count()).where(Document.deleted_at.is_(None))
            )
            stats["total_documents"] = total_docs

            # Verknuepfte Dokumente
            linked_docs = await db.scalar(
                select(func.count()).where(
                    and_(
                        Document.business_entity_id.isnot(None),
                        Document.deleted_at.is_(None),
                    )
                )
            )
            stats["linked_documents"] = linked_docs

            # Unverknuepfte mit OCR-Text (koennten verknuepft werden)
            unlinked_with_text = await db.scalar(
                select(func.count()).where(
                    and_(
                        Document.business_entity_id.is_(None),
                        Document.extracted_text.isnot(None),
                        Document.extracted_text != "",
                        Document.deleted_at.is_(None),
                    )
                )
            )
            stats["unlinked_with_text"] = unlinked_with_text

            # Unverknuepfte ohne OCR-Text (brauchen erst OCR)
            unlinked_without_text = await db.scalar(
                select(func.count()).where(
                    and_(
                        Document.business_entity_id.is_(None),
                        (Document.extracted_text.is_(None) | (Document.extracted_text == "")),
                        Document.deleted_at.is_(None),
                    )
                )
            )
            stats["unlinked_without_text"] = unlinked_without_text

            # BusinessEntities
            total_entities = await db.scalar(
                select(func.count()).where(BusinessEntity.deleted_at.is_(None))
            )
            stats["total_entities"] = total_entities

            # Entities mit Dokumenten
            entities_with_docs = await db.scalar(
                select(func.count(func.distinct(Document.business_entity_id))).where(
                    and_(
                        Document.business_entity_id.isnot(None),
                        Document.deleted_at.is_(None),
                    )
                )
            )
            stats["entities_with_documents"] = entities_with_docs

            # Linking-Rate berechnen
            if total_docs > 0:
                stats["linking_rate_percent"] = round(linked_docs / total_docs * 100, 1)
            else:
                stats["linking_rate_percent"] = 0.0

            stats["generated_at"] = datetime.now(timezone.utc).isoformat()

            return stats

    result = asyncio.get_event_loop().run_until_complete(_generate_stats())

    logger.info(
        "linking_statistics_generated",
        total_docs=result["total_documents"],
        linked=result["linked_documents"],
        linking_rate=result["linking_rate_percent"],
    )

    return result


# =============================================================================
# Reprocessing Tasks
# =============================================================================


@celery_app.task(
    name="entity_linking.reprocess_low_confidence",
    bind=True,
    max_retries=1,
)
def reprocess_low_confidence_documents_task(
    self,
    confidence_threshold: float = 0.85,
) -> Dict[str, Any]:
    """Re-verarbeitet Dokumente mit niedriger Confidence.

    Kann nach Entity-Updates oder Verbesserungen der
    Matching-Algorithmen laufen.

    Args:
        confidence_threshold: Dokumente unter diesem Wert re-verarbeiten

    Returns:
        Dict mit Re-Processing-Statistiken
    """
    import asyncio
    from app.services.document_entity_linker_service import DocumentEntityLinkerService

    async def _reprocess():
        stats = {
            "reprocessed": 0,
            "improved": 0,
            "unchanged": 0,
            "errors": 0,
        }

        async with get_async_session_context() as db:
            # Dokumente mit niedriger Confidence finden
            # Hinweis: Wir speichern aktuell keine Confidence im Document-Model
            # Dies ist ein Placeholder fuer zukuenftige Erweiterung

            # Alternativ: Alle unverknuepften mit OCR-Text nochmal versuchen
            service = DocumentEntityLinkerService(db)
            result = await service.link_all_documents(
                min_confidence=confidence_threshold,
                batch_size=50,
                only_unlinked=True,
            )

            stats["reprocessed"] = result.linked_count + result.unlinked_count
            stats["improved"] = result.linked_count

        return stats

    try:
        result = asyncio.get_event_loop().run_until_complete(_reprocess())

        logger.info(
            "low_confidence_reprocessing_completed",
            reprocessed=result["reprocessed"],
            improved=result["improved"],
        )

        return result
    except Exception as e:
        logger.error("low_confidence_reprocessing_failed", **safe_error_log(e))
        raise self.retry(exc=e)


# =============================================================================
# Event Handlers (fuer Integration mit anderen Tasks)
# =============================================================================


@celery_app.task(name="entity_linking.on_ocr_completed")
def on_ocr_completed_link_entity(document_id: str) -> Dict[str, Any]:
    """Handler fuer OCR-Completion Events.

    Wird von OCR-Tasks aufgerufen nachdem Text extrahiert wurde.
    Versucht automatisch, das Dokument mit einer Entity zu verknuepfen.

    Args:
        document_id: UUID des Dokuments

    Returns:
        Dict mit Linking-Ergebnis
    """
    # Delegiert an den Haupt-Linking-Task
    return link_single_document_task.delay(
        document_id=document_id,
        min_confidence=0.75,
    ).get(timeout=60)


@celery_app.task(name="entity_linking.on_entity_imported")
def on_entity_imported_check_documents(entity_id: str) -> Dict[str, Any]:
    """Handler fuer Entity-Import Events.

    Wird nach Import einer neuen Entity aufgerufen.
    Sucht Dokumente die zu dieser Entity passen koennten.

    Args:
        entity_id: UUID der neuen Entity

    Returns:
        Dict mit gefundenen Dokumenten
    """
    import asyncio
    from app.services.document_entity_linker_service import (
        DocumentEntityLinkerService,
        extract_customer_numbers,
        extract_matchcodes,
    )

    async def _check_for_entity():
        async with get_async_session_context() as db:
            # Entity laden
            stmt = select(BusinessEntity).where(
                BusinessEntity.id == UUID(entity_id)
            )
            result = await db.execute(stmt)
            entity = result.scalar_one_or_none()

            if not entity:
                return {"error": "Entity nicht gefunden"}

            # Suchbegriffe sammeln
            search_terms = []

            # Kundennummer
            if entity.primary_customer_number:
                search_terms.append(entity.primary_customer_number)

            # Name und Matchcode
            if entity.name:
                search_terms.append(entity.name)
            if entity.short_name:
                search_terms.append(entity.short_name)

            # Lexware IDs
            if entity.lexware_ids:
                for company_data in entity.lexware_ids.values():
                    if isinstance(company_data, dict):
                        if company_data.get("matchcode"):
                            search_terms.append(company_data["matchcode"])
                        if company_data.get("kd_nr"):
                            search_terms.append(company_data["kd_nr"])

            # Unverknuepfte Dokumente durchsuchen
            linked_count = 0
            service = DocumentEntityLinkerService(db)

            docs_stmt = select(Document).where(
                and_(
                    Document.business_entity_id.is_(None),
                    Document.extracted_text.isnot(None),
                    Document.deleted_at.is_(None),
                )
            ).limit(500)

            docs_result = await db.execute(docs_stmt)
            documents = docs_result.scalars().all()

            for doc in documents:
                # Schneller Check ob irgendein Suchbegriff vorkommt
                text_lower = doc.extracted_text.lower()
                for term in search_terms:
                    if term.lower() in text_lower:
                        # Vollstaendiges Linking versuchen
                        match = await service.link_document(doc.id)
                        if match and match.entity.id == entity.id:
                            linked_count += 1
                        break

            await db.commit()

            return {
                "entity_id": entity_id,
                "entity_name": entity.name,
                "documents_checked": len(documents),
                "documents_linked": linked_count,
            }

    result = asyncio.get_event_loop().run_until_complete(_check_for_entity())

    if result.get("documents_linked", 0) > 0:
        logger.info(
            "documents_linked_to_new_entity",
            entity_id=entity_id,
            linked_count=result["documents_linked"],
        )

    return result


# =============================================================================
# Celery Beat Schedule
# =============================================================================

ENTITY_LINKING_BEAT_SCHEDULE = {
    # Statistiken taeglich um 01:00
    "generate-linking-statistics": {
        "task": "entity_linking.generate_statistics",
        "schedule": {
            "hour": 1,
            "minute": 0,
        },
        "options": {"queue": "default"},
    },
    # Re-Processing woechentlich am Sonntag um 04:00
    "reprocess-low-confidence": {
        "task": "entity_linking.reprocess_low_confidence",
        "schedule": {
            "day_of_week": 0,  # Sonntag
            "hour": 4,
            "minute": 0,
        },
        "options": {"queue": "default"},
    },
}

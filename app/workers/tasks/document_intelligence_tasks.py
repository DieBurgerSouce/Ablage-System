# -*- coding: utf-8 -*-
"""
Document Intelligence Tasks fuer Celery.

Dieses Modul enthaelt Tasks fuer intelligente Dokumentenverarbeitung:
- Automatische Dokumentengruppierung (Geheftete/mehrseitige Dokumente)
- Entity Extraction (Geschaeftspartner-Erkennung)
- Batch-Verarbeitung fuer bestehende Dokumente

99%+ Praezision ist das Ziel - lieber konservativ als falsche Positives.
"""

from datetime import datetime, timezone
from typing import Any, Coroutine, Dict, List, Optional, TypeVar
from uuid import UUID
import asyncio

import structlog
from celery import states
from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy import select, update, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_async_session_context
from app.db.models import Document, ProcessingStatus
from app.workers.celery_app import CPUTask, celery_app

logger = structlog.get_logger(__name__)

# Type variable for async return type
T = TypeVar("T")


def run_async_task(coro: Coroutine[Any, Any, T]) -> T:
    """Run an async coroutine in a Celery task context."""
    return asyncio.run(coro)


# NOTE: Wir nutzen get_async_session_context() aus app.db.session
# Das vermeidet Event-Loop-Bugs da Engine INSIDE async context erstellt wird


def update_task_progress(task_id: str, current: int, total: int, message: str) -> None:
    """Update task progress for real-time monitoring."""
    progress = int((current / total) * 100) if total > 0 else 0
    celery_app.backend.store_result(
        task_id,
        {
            "current": current,
            "total": total,
            "progress": progress,
            "message": message,
        },
        states.STARTED,
    )


# =============================================================================
# DOCUMENT GROUPING TASKS
# =============================================================================


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.document_intelligence_tasks.detect_document_groups",
    soft_time_limit=300,
    time_limit=360,
)
def detect_document_groups(
    self,
    folder_path: Optional[str] = None,
    batch_id: Optional[str] = None,
    auto_confirm_threshold: float = 0.99,
) -> Dict[str, Any]:
    """
    Erkenne zusammengehoerige Dokumente (Gruppen).

    Analysiert Dokumente nach:
    - Dateinamen-Sequenzen (Hex-Pattern)
    - Zeitstempel-Naehe (Scan-Batch)
    - Inhaltsaehnlichkeit (Seitennummerierung)

    Args:
        folder_path: Optional - nur Dokumente aus diesem Ordner pruefen
        batch_id: Optional - nur Dokumente aus diesem Scan-Batch pruefen
        auto_confirm_threshold: Konfidenz-Schwelle fuer automatische Bestaetigung

    Returns:
        Dict mit erkannten Gruppen und Statistiken
    """
    task_id = self.request.id
    logger.info(
        "document_grouping_task_started",
        task_id=task_id,
        folder_path=folder_path,
        batch_id=batch_id,
    )

    try:
        result = run_async_task(
            _detect_document_groups_async(
                task_id=task_id,
                folder_path=folder_path,
                batch_id=batch_id,
                auto_confirm_threshold=auto_confirm_threshold,
            )
        )
        return result
    except SoftTimeLimitExceeded:
        logger.warning("document_grouping_task_timeout", task_id=task_id)
        return {
            "success": False,
            "error": "Task-Zeitlimit ueberschritten",
            "task_id": task_id,
        }
    except Exception as e:
        logger.error(
            "document_grouping_task_failed",
            task_id=task_id,
            error=str(e),
            exc_info=True,
        )
        return {
            "success": False,
            "error": str(e),
            "task_id": task_id,
        }


async def _detect_document_groups_async(
    task_id: str,
    folder_path: Optional[str],
    batch_id: Optional[str],
    auto_confirm_threshold: float,
) -> Dict[str, Any]:
    """Async implementation of document group detection."""
    from app.services.document_grouping_service import DocumentGroupingService

    async with get_async_session_context() as session:
        # Build query based on filters
        query = select(Document).where(
            and_(
                Document.deleted_at.is_(None),
                Document.extracted_text.isnot(None),
            )
        )

        if folder_path:
            query = query.where(Document.folder_name == folder_path)

        if batch_id:
            query = query.where(Document.scan_batch_id == batch_id)

        # Order by scan timestamp for sequence detection
        query = query.order_by(Document.scan_timestamp, Document.created_at)

        result = await session.execute(query)
        documents = result.scalars().all()

        if not documents:
            return {
                "success": True,
                "groups_found": 0,
                "documents_analyzed": 0,
                "message": "Keine Dokumente zur Analyse gefunden",
            }

        # Initialize grouping service
        grouping_service = DocumentGroupingService(db=session)

        # Detect groups
        detection_result = await grouping_service.detect_groups(
            documents,
            auto_confirm_threshold=auto_confirm_threshold,
        )

        # Process results
        auto_confirmed = 0
        needs_review = 0
        groups_created = []

        for group_candidate in detection_result.groups:
            if group_candidate.combined_confidence >= auto_confirm_threshold:
                # Auto-confirm high-confidence groups
                created_group = await grouping_service.create_group_from_candidate(
                    group_candidate,
                    user_confirmed=True,
                )
                if created_group:
                    groups_created.append(str(created_group.id))
                    auto_confirmed += 1
            elif not group_candidate.needs_review:
                # Medium confidence - mark for review
                needs_review += 1

        await session.commit()

        stats = grouping_service.get_detection_stats()

        return {
            "success": True,
            "documents_analyzed": len(documents),
            "groups_found": len(detection_result.groups),
            "auto_confirmed": auto_confirmed,
            "needs_review": needs_review,
            "groups_created": groups_created,
            "detection_stats": stats,
            "task_id": task_id,
        }


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.document_intelligence_tasks.batch_detect_groups_by_folder",
    soft_time_limit=1800,
    time_limit=1860,
)
def batch_detect_groups_by_folder(
    self,
    limit: int = 100,
) -> Dict[str, Any]:
    """
    Batch-Erkennung von Dokumentengruppen pro Ordner.

    Verarbeitet alle Ordner mit ungruppierten Dokumenten.

    Args:
        limit: Maximale Anzahl Ordner pro Durchlauf

    Returns:
        Dict mit Verarbeitungsstatistiken
    """
    task_id = self.request.id
    logger.info("batch_group_detection_started", task_id=task_id, limit=limit)

    try:
        result = run_async_task(_batch_detect_groups_async(task_id, limit))
        return result
    except SoftTimeLimitExceeded:
        logger.warning("batch_group_detection_timeout", task_id=task_id)
        return {
            "success": False,
            "error": "Task-Zeitlimit ueberschritten",
        }
    except Exception as e:
        logger.error(
            "batch_group_detection_failed",
            task_id=task_id,
            error=str(e),
            exc_info=True,
        )
        return {"success": False, "error": str(e)}


async def _batch_detect_groups_async(task_id: str, limit: int) -> Dict[str, Any]:
    """Async implementation of batch group detection."""
    from sqlalchemy import func

    async with get_async_session_context() as session:
        # Find folders with ungrouped documents
        query = (
            select(Document.folder_name, func.count(Document.id).label("doc_count"))
            .where(
                and_(
                    Document.deleted_at.is_(None),
                    Document.group_id.is_(None),
                    Document.folder_name.isnot(None),
                )
            )
            .group_by(Document.folder_name)
            .order_by(func.count(Document.id).desc())
            .limit(limit)
        )

        result = await session.execute(query)
        folders = result.all()

        total_folders = len(folders)
        total_groups_found = 0
        total_auto_confirmed = 0
        processed_folders = []

        for i, (folder_name, doc_count) in enumerate(folders):
            try:
                # Trigger detection for each folder
                folder_result = await _detect_document_groups_async(
                    task_id=f"{task_id}:{folder_name}",
                    folder_path=folder_name,
                    batch_id=None,
                    auto_confirm_threshold=0.99,
                )

                if folder_result.get("success"):
                    total_groups_found += folder_result.get("groups_found", 0)
                    total_auto_confirmed += folder_result.get("auto_confirmed", 0)
                    processed_folders.append(
                        {
                            "folder": folder_name,
                            "documents": doc_count,
                            "groups_found": folder_result.get("groups_found", 0),
                        }
                    )

            except Exception as e:
                logger.warning(
                    "folder_processing_failed",
                    folder=folder_name,
                    error=str(e),
                )
                continue

        return {
            "success": True,
            "folders_processed": total_folders,
            "total_groups_found": total_groups_found,
            "total_auto_confirmed": total_auto_confirmed,
            "folder_details": processed_folders,
            "task_id": task_id,
        }


# =============================================================================
# ENTITY EXTRACTION TASKS
# =============================================================================


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.document_intelligence_tasks.extract_entities_from_document",
    soft_time_limit=60,
    time_limit=90,
)
def extract_entities_from_document(
    self,
    document_id: str,
    match_to_existing: bool = True,
) -> Dict[str, Any]:
    """
    Extrahiere Geschaeftspartner-Entitaeten aus einem Dokument.

    Erkennt:
    - USt-IdNr (DE123456789)
    - IBAN mit Pruefziffer-Validierung
    - Firmennamen mit Rechtsform
    - Deutsche Adressen

    Args:
        document_id: UUID des Dokuments
        match_to_existing: Mit existierenden BusinessEntities abgleichen

    Returns:
        Dict mit extrahierten Entitaeten
    """
    task_id = self.request.id
    logger.info(
        "entity_extraction_task_started",
        task_id=task_id,
        document_id=document_id,
    )

    try:
        result = run_async_task(
            _extract_entities_async(task_id, document_id, match_to_existing)
        )
        return result
    except SoftTimeLimitExceeded:
        logger.warning(
            "entity_extraction_timeout",
            task_id=task_id,
            document_id=document_id,
        )
        return {
            "success": False,
            "error": "Task-Zeitlimit ueberschritten",
            "document_id": document_id,
        }
    except Exception as e:
        logger.error(
            "entity_extraction_failed",
            task_id=task_id,
            document_id=document_id,
            error=str(e),
            exc_info=True,
        )
        return {
            "success": False,
            "error": str(e),
            "document_id": document_id,
        }


async def _extract_entities_async(
    task_id: str,
    document_id: str,
    match_to_existing: bool,
) -> Dict[str, Any]:
    """Async implementation of entity extraction."""
    from app.services.entity_extraction_service import EntityExtractionService

    async with get_async_session_context() as session:
        # Load document
        query = select(Document).where(Document.id == document_id)
        result = await session.execute(query)
        document = result.scalar_one_or_none()

        if not document:
            return {
                "success": False,
                "error": "Dokument nicht gefunden",
                "document_id": document_id,
            }

        if not document.extracted_text:
            return {
                "success": False,
                "error": "Kein OCR-Text verfuegbar",
                "document_id": document_id,
            }

        # Initialize entity extraction service
        entity_service = EntityExtractionService(db=session if match_to_existing else None)

        # Extract entities
        extraction_result = await entity_service.extract_entities(document.extracted_text)

        # Store in document's extracted_data
        extracted_data = document.extracted_data or {}
        extracted_data["entities"] = {
            "identifiers": [
                {
                    "type": ident.identifier_type,
                    "value": ident.value,
                    "normalized": ident.normalized_value,
                    "confidence": ident.confidence,
                }
                for ident in extraction_result.identifiers
            ],
            "addresses": [
                {
                    "street": addr.street,
                    "postal_code": addr.postal_code,
                    "city": addr.city,
                    "confidence": addr.confidence,
                }
                for addr in extraction_result.addresses
            ],
            "company_names": [
                {
                    "name": company.name,
                    "legal_form": company.legal_form,
                    "confidence": company.confidence,
                }
                for company in extraction_result.company_names
            ],
            "emails": extraction_result.emails,
            "overall_confidence": extraction_result.overall_confidence,
            "extracted_at": datetime.now(timezone.utc).isoformat(),
        }

        document.extracted_data = extracted_data

        # Match to existing entity if enabled
        matched_entity_id = None
        match_confidence = 0.0
        is_new_entity = True

        if match_to_existing and extraction_result.identifiers:
            match_result = await entity_service.match_to_existing(extraction_result)
            if match_result and not match_result.is_new:
                matched_entity_id = str(match_result.entity_id)
                match_confidence = match_result.confidence
                is_new_entity = False

                # High-confidence match: Link document to entity
                if match_confidence >= 0.99:
                    document.business_entity_id = match_result.entity_id
                    logger.info(
                        "entity_auto_linked",
                        document_id=document_id,
                        entity_id=matched_entity_id,
                        confidence=match_confidence,
                    )

        await session.commit()

        return {
            "success": True,
            "document_id": document_id,
            "identifiers_found": len(extraction_result.identifiers),
            "addresses_found": len(extraction_result.addresses),
            "companies_found": len(extraction_result.company_names),
            "emails_found": len(extraction_result.emails),
            "overall_confidence": extraction_result.overall_confidence,
            "matched_entity_id": matched_entity_id,
            "match_confidence": match_confidence,
            "is_new_entity": is_new_entity,
            "task_id": task_id,
        }


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.document_intelligence_tasks.batch_extract_entities",
    soft_time_limit=1800,
    time_limit=1860,
)
def batch_extract_entities(
    self,
    limit: int = 500,
    skip_already_extracted: bool = True,
) -> Dict[str, Any]:
    """
    Batch-Extraktion von Entitaeten aus Dokumenten.

    Args:
        limit: Maximale Anzahl Dokumente pro Durchlauf
        skip_already_extracted: Bereits verarbeitete Dokumente ueberspringen

    Returns:
        Dict mit Verarbeitungsstatistiken
    """
    task_id = self.request.id
    logger.info(
        "batch_entity_extraction_started",
        task_id=task_id,
        limit=limit,
    )

    try:
        result = run_async_task(
            _batch_extract_entities_async(task_id, limit, skip_already_extracted)
        )
        return result
    except SoftTimeLimitExceeded:
        logger.warning("batch_entity_extraction_timeout", task_id=task_id)
        return {"success": False, "error": "Task-Zeitlimit ueberschritten"}
    except Exception as e:
        logger.error(
            "batch_entity_extraction_failed",
            task_id=task_id,
            error=str(e),
            exc_info=True,
        )
        return {"success": False, "error": str(e)}


async def _batch_extract_entities_async(
    task_id: str,
    limit: int,
    skip_already_extracted: bool,
) -> Dict[str, Any]:
    """Async implementation of batch entity extraction."""
    from sqlalchemy.sql import text

    async with get_async_session_context() as session:
        # Find documents without extracted entities
        base_conditions = [
            Document.deleted_at.is_(None),
            Document.extracted_text.isnot(None),
        ]

        if skip_already_extracted:
            # Check if extracted_data->entities is null or not present
            # Using raw SQL for JSON field check across PostgreSQL and SQLite
            base_conditions.append(
                text("(extracted_data IS NULL OR extracted_data->>'entities' IS NULL)")
            )

        query = (
            select(Document.id)
            .where(and_(*base_conditions))
            .order_by(Document.created_at.desc())
            .limit(limit)
        )

        result = await session.execute(query)
        document_ids = [str(row[0]) for row in result.all()]

        if not document_ids:
            return {
                "success": True,
                "documents_processed": 0,
                "message": "Keine Dokumente zur Verarbeitung",
            }

        # Process documents
        success_count = 0
        error_count = 0
        entities_found = 0

        for i, doc_id in enumerate(document_ids):
            try:
                extraction_result = await _extract_entities_async(
                    task_id=f"{task_id}:{i}",
                    document_id=doc_id,
                    match_to_existing=True,
                )

                if extraction_result.get("success"):
                    success_count += 1
                    entities_found += extraction_result.get("identifiers_found", 0)
                else:
                    error_count += 1

            except Exception as e:
                logger.warning(
                    "document_entity_extraction_failed",
                    document_id=doc_id,
                    error=str(e),
                )
                error_count += 1

        return {
            "success": True,
            "documents_processed": len(document_ids),
            "success_count": success_count,
            "error_count": error_count,
            "total_identifiers_found": entities_found,
            "task_id": task_id,
        }


# =============================================================================
# PERIODIC TASKS
# =============================================================================


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.document_intelligence_tasks.run_document_intelligence_pipeline",
    soft_time_limit=3600,
    time_limit=3660,
)
def run_document_intelligence_pipeline(self) -> Dict[str, Any]:
    """
    Vollstaendige Document Intelligence Pipeline.

    Fuehrt nacheinander aus:
    1. Entity Extraction fuer neue Dokumente
    2. Gruppenerkennung fuer neue Dokumente
    3. Statistik-Update

    Wird taeglich via Celery Beat ausgefuehrt.
    """
    task_id = self.request.id
    logger.info("document_intelligence_pipeline_started", task_id=task_id)

    pipeline_results = {
        "task_id": task_id,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "steps": [],
    }

    try:
        # Step 1: Entity Extraction
        logger.info("pipeline_step_entity_extraction")
        entity_result = run_async_task(
            _batch_extract_entities_async(
                task_id=f"{task_id}:entities",
                limit=1000,
                skip_already_extracted=True,
            )
        )
        pipeline_results["steps"].append(
            {
                "step": "entity_extraction",
                "success": entity_result.get("success", False),
                "documents_processed": entity_result.get("documents_processed", 0),
            }
        )

        # Step 2: Group Detection
        logger.info("pipeline_step_group_detection")
        group_result = run_async_task(
            _batch_detect_groups_async(
                task_id=f"{task_id}:groups",
                limit=50,
            )
        )
        pipeline_results["steps"].append(
            {
                "step": "group_detection",
                "success": group_result.get("success", False),
                "folders_processed": group_result.get("folders_processed", 0),
                "groups_found": group_result.get("total_groups_found", 0),
            }
        )

        pipeline_results["success"] = True
        pipeline_results["completed_at"] = datetime.now(timezone.utc).isoformat()

        logger.info(
            "document_intelligence_pipeline_completed",
            task_id=task_id,
            entity_docs=entity_result.get("documents_processed", 0),
            groups_found=group_result.get("total_groups_found", 0),
        )

        return pipeline_results

    except Exception as e:
        logger.error(
            "document_intelligence_pipeline_failed",
            task_id=task_id,
            error=str(e),
            exc_info=True,
        )
        pipeline_results["success"] = False
        pipeline_results["error"] = str(e)
        return pipeline_results


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.document_intelligence_tasks.update_intelligence_metrics",
    soft_time_limit=60,
    time_limit=90,
)
def update_intelligence_metrics(self) -> Dict[str, Any]:
    """
    Aktualisiere Document Intelligence Metriken.

    Sammelt Statistiken ueber:
    - Anzahl erkannter Gruppen
    - Anzahl verknuepfter Entitaeten
    - Extraktions-Genauigkeit
    """
    task_id = self.request.id

    try:
        result = run_async_task(_update_metrics_async())
        return {"success": True, "metrics": result, "task_id": task_id}
    except Exception as e:
        logger.error(
            "metrics_update_failed",
            task_id=task_id,
            error=str(e),
        )
        return {"success": False, "error": str(e)}


async def _update_metrics_async() -> Dict[str, Any]:
    """Async implementation of metrics update."""
    from sqlalchemy import func

    async with get_async_session_context() as session:
        # Count documents with entities
        docs_with_entities = await session.execute(
            select(func.count(Document.id)).where(
                and_(
                    Document.deleted_at.is_(None),
                    Document.business_entity_id.isnot(None),
                )
            )
        )

        # Count documents in groups
        docs_in_groups = await session.execute(
            select(func.count(Document.id)).where(
                and_(
                    Document.deleted_at.is_(None),
                    Document.group_id.isnot(None),
                )
            )
        )

        # Total documents with OCR text
        docs_with_text = await session.execute(
            select(func.count(Document.id)).where(
                and_(
                    Document.deleted_at.is_(None),
                    Document.extracted_text.isnot(None),
                )
            )
        )

        return {
            "documents_with_entities": docs_with_entities.scalar() or 0,
            "documents_in_groups": docs_in_groups.scalar() or 0,
            "documents_with_text": docs_with_text.scalar() or 0,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

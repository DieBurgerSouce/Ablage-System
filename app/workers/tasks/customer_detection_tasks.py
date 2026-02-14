"""Customer Detection Tasks for Celery.

Automatische Erkennung von Geschaeftskontakten aus verarbeiteten Dokumenten.
Laeuft nach OCR-Verarbeitung als Background-Task.
"""

from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from uuid import UUID
import asyncio

import structlog
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

from app.workers.celery_app import celery_app, CPUTask
from app.core.config import settings
from app.core.safe_errors import safe_error_log
from app.db.models import Document, BusinessContact, DocumentContact
from app.services.customer_detection_service import get_customer_detection_service

logger = structlog.get_logger(__name__)

# Database session factory
engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
async_session_maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.customer_detection_tasks.detect_contacts_task",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    max_retries=3,
)
def detect_contacts_task(
    self,
    document_id: str,
    auto_create: bool = True,
    owner_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Detect and extract business contacts from a processed document.

    This task runs after OCR processing to automatically recognize
    customers, suppliers, and other contacts from document metadata.

    Args:
        document_id: Document UUID as string
        auto_create: Whether to automatically create new contacts
        owner_id: Optional owner ID (uses document owner if not provided)

    Returns:
        Dictionary with detection results
    """
    start_time = datetime.now(timezone.utc)
    doc_uuid = UUID(document_id)
    task_id = self.request.id

    logger.info(
        "contact_detection_starting",
        task_id=task_id,
        document_id=document_id,
        auto_create=auto_create,
    )

    async def detect_async() -> Dict[str, Any]:
        async with async_session_maker() as session:
            try:
                # Get document
                result = await session.execute(
                    select(Document).where(Document.id == doc_uuid)
                )
                document = result.scalar_one_or_none()

                if not document:
                    logger.warning(
                        "document_not_found_for_detection",
                        document_id=document_id,
                    )
                    return {
                        "success": False,
                        "document_id": document_id,
                        "error": "Dokument nicht gefunden",
                    }

                # Check if document type supports contact detection
                supported_types = ["invoice", "contract", "order", "quote", "letter"]
                doc_type = document.document_type or "unknown"

                if doc_type not in supported_types and doc_type != "unknown":
                    logger.info(
                        "skipping_contact_detection_unsupported_type",
                        document_id=document_id,
                        document_type=doc_type,
                    )
                    return {
                        "success": True,
                        "document_id": document_id,
                        "skipped": True,
                        "reason": f"Dokumenttyp '{doc_type}' wird nicht unterstuetzt",
                    }

                # Use document owner if not specified
                actual_owner_id = UUID(owner_id) if owner_id else document.user_id
                if not actual_owner_id:
                    logger.warning(
                        "no_owner_for_detection",
                        document_id=document_id,
                    )
                    return {
                        "success": False,
                        "document_id": document_id,
                        "error": "Kein Besitzer fuer Dokument",
                    }

                # Run detection
                service = get_customer_detection_service()
                results = await service.process_document(
                    db=session,
                    document=document,
                    owner_id=actual_owner_id,
                    auto_create=auto_create,
                )

                await session.commit()

                # Count results
                new_count = sum(1 for r in results if r.get("created", False))
                matched_count = len(results) - new_count

                processing_time = (datetime.now(timezone.utc) - start_time).total_seconds()

                logger.info(
                    "contact_detection_completed",
                    task_id=task_id,
                    document_id=document_id,
                    contacts_found=len(results),
                    new_created=new_count,
                    existing_matched=matched_count,
                    duration_seconds=processing_time,
                )

                return {
                    "success": True,
                    "document_id": document_id,
                    "contacts": results,
                    "new_contacts_created": new_count,
                    "existing_contacts_matched": matched_count,
                    "processing_time_seconds": processing_time,
                }

            except Exception as e:
                logger.exception(
                    "contact_detection_failed",
                    task_id=task_id,
                    document_id=document_id,
                    **safe_error_log(e),
                )
                raise

    # Run async detection
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(detect_async())
    finally:
        loop.close()


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.customer_detection_tasks.batch_detect_contacts_task",
)
def batch_detect_contacts_task(
    self,
    document_ids: List[str],
    auto_create: bool = True,
    owner_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Batch detect contacts from multiple documents.

    Args:
        document_ids: List of document UUIDs
        auto_create: Whether to auto-create new contacts
        owner_id: Optional owner ID

    Returns:
        Dictionary with batch results
    """
    task_id = self.request.id

    logger.info(
        "batch_contact_detection_starting",
        task_id=task_id,
        document_count=len(document_ids),
    )

    results = []
    for doc_id in document_ids:
        try:
            result = detect_contacts_task.apply(
                args=[doc_id, auto_create, owner_id]
            ).get(timeout=60)
            results.append(result)
        except Exception as e:
            logger.warning(
                "batch_detection_single_failure",
                document_id=doc_id,
                **safe_error_log(e),
            )
            results.append({
                "success": False,
                "document_id": doc_id,
                "error": "Verarbeitung fehlgeschlagen",
            })

    successful = sum(1 for r in results if r.get("success", False))
    total_contacts = sum(len(r.get("contacts", [])) for r in results)

    logger.info(
        "batch_contact_detection_completed",
        task_id=task_id,
        documents_processed=len(results),
        successful=successful,
        total_contacts_found=total_contacts,
    )

    return {
        "success": True,
        "documents_processed": len(results),
        "successful": successful,
        "failed": len(results) - successful,
        "total_contacts_found": total_contacts,
        "results": results,
    }


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.customer_detection_tasks.reprocess_all_documents_task",
)
def reprocess_all_documents_task(
    self,
    owner_id: str,
    auto_create: bool = False,
    document_types: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Reprocess all documents for an owner to detect contacts.

    Useful for initial migration or when detection algorithm is updated.

    Args:
        owner_id: Owner UUID as string
        auto_create: Whether to auto-create new contacts
        document_types: Optional list of document types to process

    Returns:
        Dictionary with reprocessing results
    """
    task_id = self.request.id
    owner_uuid = UUID(owner_id)

    if document_types is None:
        document_types = ["invoice", "contract", "order", "quote"]

    logger.info(
        "reprocess_all_documents_starting",
        task_id=task_id,
        owner_id=owner_id,
        document_types=document_types,
    )

    async def reprocess_async() -> Dict[str, Any]:
        async with async_session_maker() as session:
            # Find all documents to process
            query = select(Document.id).where(
                Document.owner_id == owner_uuid,
                Document.document_type.in_(document_types),
            )
            result = await session.execute(query)
            doc_ids = [str(row[0]) for row in result.fetchall()]

            logger.info(
                "found_documents_for_reprocessing",
                task_id=task_id,
                document_count=len(doc_ids),
            )

            return doc_ids

    # Get document IDs
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        doc_ids = loop.run_until_complete(reprocess_async())
    finally:
        loop.close()

    if not doc_ids:
        return {
            "success": True,
            "message": "Keine Dokumente zum Verarbeiten gefunden",
            "documents_processed": 0,
        }

    # Queue batch task
    batch_result = batch_detect_contacts_task.apply_async(
        args=[doc_ids, auto_create, owner_id],
        countdown=5,
    )

    return {
        "success": True,
        "batch_task_id": batch_result.id,
        "documents_queued": len(doc_ids),
        "message": f"{len(doc_ids)} Dokumente zur Kontakterkennung eingereiht",
    }

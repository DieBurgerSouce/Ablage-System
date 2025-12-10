# -*- coding: utf-8 -*-
"""
Strukturierte Extraktion Tasks fuer Celery.

Tasks fuer:
- Batch-Reprocessing aller Dokumente fuer strukturierte Extraktion
- Einzeldokument-Reprocessing
- Statistik-Generierung

Feinpoliert und durchdacht - Enterprise-ready Batch Processing.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID
import asyncio

import structlog
from celery import states
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.workers.celery_app import celery_app, CPUTask
from app.core.config import settings
from app.db.models import Document

logger = structlog.get_logger(__name__)

# Database session factory fuer Worker
engine = create_async_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=settings.DB_WORKER_POOL_SIZE,
    max_overflow=settings.DB_WORKER_MAX_OVERFLOW,
    pool_recycle=settings.DB_WORKER_POOL_RECYCLE,
    pool_timeout=settings.DB_POOL_TIMEOUT,
    echo=False,
)
async_session_maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="extraction.reprocess_all_structured_extraction",
    max_retries=0,
    soft_time_limit=7200,  # 2 Stunden Soft-Limit
    time_limit=7500,  # 2h 5min Hard-Limit
)
def reprocess_all_documents_structured_extraction(
    self,
    batch_size: int = 100,
    document_type_filter: Optional[str] = None,
    skip_already_processed: bool = True,
    owner_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Verarbeitet alle Dokumente fuer strukturierte Extraktion.

    Args:
        batch_size: Dokumente pro Batch (default 100)
        document_type_filter: Nur bestimmte Typen verarbeiten (optional)
        skip_already_processed: Bereits verarbeitete ueberspringen
        owner_id: Nur Dokumente eines bestimmten Users (optional)

    Returns:
        {
            "total_processed": 9876,
            "total_skipped": 124,
            "total_failed": 12,
            "by_type": {"invoice": 5000, "order": 2000, ...},
            "duration_seconds": 3600,
            "errors": [...]
        }
    """
    # asyncio.run() für sauberes Event-Loop Cleanup
    return asyncio.run(
        _async_reprocess_all(
            task=self,
            batch_size=batch_size,
            document_type_filter=document_type_filter,
            skip_already_processed=skip_already_processed,
            owner_id=owner_id,
        )
    )


async def _async_reprocess_all(
    task,
    batch_size: int,
    document_type_filter: Optional[str],
    skip_already_processed: bool,
    owner_id: Optional[str],
) -> Dict[str, Any]:
    """Async Implementation des Batch-Reprocessing."""
    from app.services.structured_extraction_service import (
        get_structured_extraction_service,
    )

    start_time = datetime.now(timezone.utc)
    stats = {
        "total_processed": 0,
        "total_skipped": 0,
        "total_failed": 0,
        "by_type": {},
        "errors": [],
    }

    extraction_service = get_structured_extraction_service()

    from app.db.session import get_async_session_context
    async with get_async_session_context() as db:
        # Basis-Query: Alle Dokumente mit OCR-Text
        query = select(Document).where(
            and_(
                Document.is_deleted == False,
                Document.extracted_text.isnot(None),
                Document.extracted_text != "",
            )
        )

        # Optional: Nur bestimmten User
        if owner_id:
            query = query.where(Document.owner_id == UUID(owner_id))

        # Optional: Bereits verarbeitete ueberspringen
        if skip_already_processed:
            query = query.where(
                or_(
                    Document.extracted_data.is_(None),
                    Document.extracted_data == {},
                )
            )

        # Optional: Dokumenttyp-Filter
        if document_type_filter:
            query = query.where(
                Document.extracted_data["classification"]["document_type"].astext
                == document_type_filter
            )

        # Zaehlen fuer Progress
        count_query = select(func.count()).select_from(query.subquery())
        count_result = await db.execute(count_query)
        total_count = count_result.scalar() or 0

        logger.info(
            "batch_extraction_started",
            total_documents=total_count,
            batch_size=batch_size,
            skip_processed=skip_already_processed,
        )

        # Batch-weise verarbeiten
        offset = 0
        batch_num = 0

        while True:
            batch_query = query.offset(offset).limit(batch_size)
            result = await db.execute(batch_query)
            documents = result.scalars().all()

            if not documents:
                break

            batch_num += 1
            logger.info(
                "processing_batch",
                batch_num=batch_num,
                batch_size=len(documents),
                offset=offset,
                total=total_count,
            )

            # Progress Update
            progress = min(100, int((offset / max(1, total_count)) * 100))
            task.update_state(
                state="PROGRESS",
                meta={
                    "current": offset,
                    "total": total_count,
                    "percent": progress,
                    "processed": stats["total_processed"],
                    "failed": stats["total_failed"],
                },
            )

            # Dokumente verarbeiten
            for doc in documents:
                try:
                    # Sprache aus vorhandenem OCR-Ergebnis oder Dokument holen
                    detected_language = getattr(doc, "detected_language", None)

                    # Strukturierte Extraktion durchfuehren (mit Sprache fuer Uebersetzung)
                    extraction_result = await extraction_service.extract(
                        doc.extracted_text,
                        document_id=str(doc.id),
                        detected_language=detected_language,
                    )

                    if extraction_result:
                        # In DB speichern
                        # WICHTIG: exclude_none=False um Uebersetzungs-Metadaten zu behalten
                        # (original_language, was_translated, translation_confidence)
                        doc.extracted_data = extraction_result.model_dump(
                            mode="json", exclude_none=False
                        )

                        # Dokumenttyp aktualisieren
                        doc_type = extraction_result.classification.document_type.value
                        doc.document_type = doc_type

                        stats["total_processed"] += 1
                        stats["by_type"][doc_type] = (
                            stats["by_type"].get(doc_type, 0) + 1
                        )

                        logger.debug(
                            "document_extracted",
                            document_id=str(doc.id),
                            document_type=doc_type,
                            confidence=extraction_result.classification.confidence,
                        )
                    else:
                        stats["total_skipped"] += 1

                except Exception as e:
                    stats["total_failed"] += 1
                    error_msg = f"Document {doc.id}: {str(e)}"
                    if len(stats["errors"]) < 100:  # Max 100 Fehler speichern
                        stats["errors"].append(error_msg)
                    logger.error(
                        "document_extraction_failed",
                        document_id=str(doc.id),
                        error=str(e),
                    )

            # Batch committen
            await db.commit()
            offset += batch_size

        # Finale Stats
        end_time = datetime.now(timezone.utc)
        duration = (end_time - start_time).total_seconds()
        stats["duration_seconds"] = duration
        stats["documents_per_second"] = (
            stats["total_processed"] / duration if duration > 0 else 0
        )

        logger.info(
            "batch_extraction_completed",
            total_processed=stats["total_processed"],
            total_skipped=stats["total_skipped"],
            total_failed=stats["total_failed"],
            duration_seconds=duration,
            by_type=stats["by_type"],
        )

        return stats


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="extraction.reprocess_single_document",
    max_retries=3,
    soft_time_limit=60,
    time_limit=90,
)
def reprocess_single_document(
    self,
    document_id: str,
) -> Dict[str, Any]:
    """
    Einzelnes Dokument fuer strukturierte Extraktion reprocessen.

    Args:
        document_id: UUID des Dokuments

    Returns:
        {
            "success": True,
            "document_id": "...",
            "document_type": "invoice",
            "confidence": 0.95,
            "fields_extracted": 15
        }
    """
    # asyncio.run() für sauberes Event-Loop Cleanup
    return asyncio.run(_async_reprocess_single(document_id))


async def _async_reprocess_single(document_id: str) -> Dict[str, Any]:
    """Async Implementation fuer Einzeldokument-Reprocessing."""
    from app.services.structured_extraction_service import (
        get_structured_extraction_service,
    )
    from app.db.session import get_async_session_context

    extraction_service = get_structured_extraction_service()

    # Use get_async_session_context to avoid event loop issues
    async with get_async_session_context() as db:
        # Dokument laden
        result = await db.execute(
            select(Document).where(Document.id == UUID(document_id))
        )
        document = result.scalar_one_or_none()

        if not document:
            return {
                "success": False,
                "document_id": document_id,
                "error": "Dokument nicht gefunden",
            }

        if not document.extracted_text:
            return {
                "success": False,
                "document_id": document_id,
                "error": "Kein OCR-Text vorhanden",
            }

        try:
            # Sprache aus vorhandenem OCR-Ergebnis oder Dokument holen
            detected_language = getattr(document, "detected_language", None)

            # Strukturierte Extraktion (mit Sprache fuer Uebersetzung)
            extraction_result = await extraction_service.extract(
                document.extracted_text,
                document_id=document_id,
                detected_language=detected_language,
            )

            if extraction_result:
                # In DB speichern
                # WICHTIG: exclude_none=False um Uebersetzungs-Metadaten zu behalten
                document.extracted_data = extraction_result.model_dump(
                    mode="json", exclude_none=False
                )
                document.document_type = (
                    extraction_result.classification.document_type.value
                )

                await db.commit()

                # Zaehle extrahierte Felder
                fields_count = _count_extracted_fields(extraction_result)

                logger.info(
                    "single_document_reprocessed",
                    document_id=document_id,
                    document_type=document.document_type,
                    fields_extracted=fields_count,
                )

                return {
                    "success": True,
                    "document_id": document_id,
                    "document_type": document.document_type,
                    "confidence": extraction_result.classification.confidence,
                    "fields_extracted": fields_count,
                    "needs_review": getattr(extraction_result, "needs_review", False),
                }
            else:
                return {
                    "success": False,
                    "document_id": document_id,
                    "error": "Extraktion lieferte kein Ergebnis",
                }

        except Exception as e:
            logger.error(
                "single_document_reprocess_failed",
                document_id=document_id,
                error=str(e),
            )
            return {
                "success": False,
                "document_id": document_id,
                "error": str(e),
            }


def _count_extracted_fields(extraction_result) -> int:
    """Zaehlt die Anzahl der extrahierten Felder."""
    count = 0

    if extraction_result.invoice:
        invoice = extraction_result.invoice
        for field in [
            "invoice_number",
            "invoice_date",
            "due_date",
            "net_amount",
            "gross_amount",
            "vat_amount",
            "customer_number",
            "order_number",
        ]:
            if getattr(invoice, field, None) is not None:
                count += 1
        if invoice.line_items:
            count += len(invoice.line_items)

    elif extraction_result.order:
        order = extraction_result.order
        for field in ["order_number", "order_date", "total_amount"]:
            if getattr(order, field, None) is not None:
                count += 1
        if order.line_items:
            count += len(order.line_items)

    elif extraction_result.contract:
        contract = extraction_result.contract
        for field in ["contract_number", "contract_date", "contract_value"]:
            if getattr(contract, field, None) is not None:
                count += 1

    return count


@celery_app.task(
    name="extraction.generate_extraction_stats",
    soft_time_limit=300,
    time_limit=360,
)
def generate_extraction_stats() -> Dict[str, Any]:
    """
    Generiert Statistiken ueber die strukturierte Extraktion.

    Returns:
        {
            "total_documents": 10000,
            "with_extraction": 8500,
            "by_type": {...},
            "avg_confidence": 0.87,
            "needs_review_count": 150,
            ...
        }
    """
    # asyncio.run() für sauberes Event-Loop Cleanup
    return asyncio.run(_async_generate_stats())


async def _async_generate_stats() -> Dict[str, Any]:
    """Async Implementation fuer Stats-Generierung."""
    from app.db.session import get_async_session_context
    async with get_async_session_context() as db:
        # Gesamt-Dokumente
        total_result = await db.execute(
            select(func.count()).select_from(Document).where(
                Document.is_deleted == False
            )
        )
        total_documents = total_result.scalar() or 0

        # Mit Extraktion
        extracted_result = await db.execute(
            select(func.count())
            .select_from(Document)
            .where(
                and_(
                    Document.is_deleted == False,
                    Document.extracted_data.isnot(None),
                )
            )
        )
        with_extraction = extracted_result.scalar() or 0

        # Dokumente laden fuer detaillierte Stats
        docs_result = await db.execute(
            select(Document).where(
                and_(
                    Document.is_deleted == False,
                    Document.extracted_data.isnot(None),
                )
            )
        )
        documents = docs_result.scalars().all()

        # Aggregieren
        by_type: Dict[str, int] = {}
        total_confidence = 0.0
        confidence_count = 0
        needs_review_count = 0
        with_line_items = 0
        total_gross_amount = Decimal("0")
        invoice_count = 0

        for doc in documents:
            if not doc.extracted_data:
                continue

            extracted = doc.extracted_data
            classification = extracted.get("classification", {})

            doc_type = classification.get("document_type", "unknown")
            by_type[doc_type] = by_type.get(doc_type, 0) + 1

            confidence = classification.get("confidence", 0)
            if confidence > 0:
                total_confidence += confidence
                confidence_count += 1

            # Rechnungs-spezifische Stats
            if doc_type == "invoice":
                invoice = extracted.get("invoice", {})
                if invoice.get("needs_review"):
                    needs_review_count += 1
                if invoice.get("line_items"):
                    with_line_items += 1
                if invoice.get("gross_amount"):
                    total_gross_amount += Decimal(str(invoice["gross_amount"]))
                invoice_count += 1

        avg_confidence = (
            total_confidence / confidence_count if confidence_count > 0 else 0
        )

        return {
            "total_documents": total_documents,
            "with_extraction": with_extraction,
            "extraction_rate": (
                with_extraction / total_documents if total_documents > 0 else 0
            ),
            "by_type": by_type,
            "avg_confidence": round(avg_confidence, 3),
            "needs_review_count": needs_review_count,
            "with_line_items": with_line_items,
            "invoice_stats": {
                "count": invoice_count,
                "total_gross_amount": float(total_gross_amount),
                "avg_gross_amount": (
                    float(total_gross_amount / invoice_count)
                    if invoice_count > 0
                    else 0
                ),
            },
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

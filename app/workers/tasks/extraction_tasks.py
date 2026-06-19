# -*- coding: utf-8 -*-
"""
Strukturierte Extraktion Tasks für Celery.

Tasks für:
- Batch-Reprocessing aller Dokumente für strukturierte Extraktion
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
from sqlalchemy import select, func, and_, or_, cast
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.workers.celery_app import celery_app, CPUTask
from app.core.config import settings
from app.core.safe_errors import safe_error_log, safe_error_detail
from app.db.models import Document

logger = structlog.get_logger(__name__)

# Database session factory für Worker
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
    name="app.workers.tasks.extraction_tasks.reprocess_all_documents_structured_extraction",
    # Z.2 FIX: max_retries von 0 auf 3 erhöht für bessere Fehlertoleranz
    max_retries=3,
    default_retry_delay=60,  # 1 Minute zwischen Retries
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
    Verarbeitet alle Dokumente für strukturierte Extraktion.

    Args:
        batch_size: Dokumente pro Batch (default 100)
        document_type_filter: Nur bestimmte Typen verarbeiten (optional)
        skip_already_processed: Bereits verarbeitete überspringen
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
        # HINWEIS: is_deleted ist eine Property, nicht eine Column!
        # Daher muss deleted_at.is_(None) verwendet werden.
        query = select(Document).where(
            and_(
                Document.deleted_at.is_(None),  # Nicht gelöscht
                Document.extracted_text.isnot(None),
                Document.extracted_text != "",
            )
        )

        # Optional: Nur bestimmten User
        if owner_id:
            query = query.where(Document.owner_id == UUID(owner_id))

        # Optional: Bereits verarbeitete überspringen
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
                cast(Document.extracted_data, JSONB)["classification"]["document_type"].astext
                == document_type_filter
            )

        # Zaehlen für Progress
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

                    # Strukturierte Extraktion durchführen (mit Sprache für Übersetzung)
                    # db wird für Eingangs-/Ausgangsrechnung-Erkennung benötigt
                    extraction_result = await extraction_service.extract(
                        doc.extracted_text,
                        document_id=str(doc.id),
                        detected_language=detected_language,
                        page_count=getattr(doc, 'page_count', None),
                        db=db,
                    )

                    if extraction_result:
                        # In DB speichern
                        # WICHTIG: exclude_none=False um Übersetzungs-Metadaten zu behalten
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

                        # ENTERPRISE: Anomalie-Erkennung nach Extraktion
                        try:
                            from app.services.ai.anomaly_detection_service import (
                                get_anomaly_detection_service,
                            )
                            anomaly_service = get_anomaly_detection_service()
                            anomaly_result = await anomaly_service.check_document(
                                db, doc.id, getattr(doc, 'company_id', None)
                            )
                            if anomaly_result.is_suspicious:
                                # Anomalie in extracted_data speichern
                                doc.extracted_data["anomalies"] = {
                                    "is_suspicious": True,
                                    "risk_score": anomaly_result.overall_risk_score,
                                    "anomaly_count": len(anomaly_result.anomalies),
                                    "types": [a.anomaly_type.value for a in anomaly_result.anomalies],
                                }
                                # AI Decision erstellen für Review-Queue
                                await anomaly_service.create_anomaly_decision(
                                    db, doc.id, anomaly_result, getattr(doc, 'company_id', None)
                                )
                                logger.info(
                                    "anomaly_detected_during_extraction",
                                    document_id=str(doc.id),
                                    risk_score=anomaly_result.overall_risk_score,
                                    anomaly_count=len(anomaly_result.anomalies),
                                )
                        except Exception as anomaly_error:
                            logger.warning(
                                "anomaly_check_failed_during_extraction",
                                document_id=str(doc.id),
                                **safe_error_log(anomaly_error),
                            )

                        # ENTERPRISE: Auto-Kategorisierung nach Extraktion
                        try:
                            from app.services.ai.auto_categorization_service import (
                                get_auto_categorization_service,
                            )
                            categorization_service = get_auto_categorization_service()

                            # Kategorisierung durchführen (mit auto_apply_tags=True)
                            categorization_result = await categorization_service.categorize_document(
                                db=db,
                                document_id=doc.id,
                                text=doc.extracted_text,
                                company_id=getattr(doc, 'company_id', None),
                                auto_apply_tags=True,
                            )

                            # Kategorisierung in extracted_data speichern
                            if doc.extracted_data is None:
                                doc.extracted_data = {}
                            doc.extracted_data["categorization"] = {
                                "category": categorization_result.decision_value.get("category"),
                                "display_name": categorization_result.decision_value.get("display_name"),
                                "confidence": categorization_result.confidence,
                                "confidence_level": categorization_result.confidence_level.value,
                                "auto_applied": categorization_result.auto_applied,
                            }

                            if categorization_result.confidence >= 0.7:
                                logger.info(
                                    "auto_categorization_applied",
                                    document_id=str(doc.id),
                                    category=categorization_result.decision_value.get("category"),
                                    confidence=categorization_result.confidence,
                                )
                        except Exception as cat_error:
                            logger.warning(
                                "auto_categorization_failed_during_extraction",
                                document_id=str(doc.id),
                                **safe_error_log(cat_error),
                            )

                        # ENTERPRISE: LLM-NER für erweiterte Entitaetsextraktion
                        try:
                            from app.services.document_intelligence import (
                                get_llm_ner_service,
                            )
                            ner_service = get_llm_ner_service()

                            # NER durchführen
                            ner_result = await ner_service.extract_entities(
                                doc.extracted_text
                            )

                            if ner_result and ner_result.entities:
                                # NER-Ergebnisse in extracted_data speichern
                                doc.extracted_data["ner"] = {
                                    "entities": [
                                        {
                                            "type": e.entity_type.value,
                                            "value": e.value,
                                            "confidence": e.confidence,
                                            "context": e.context,
                                        }
                                        for e in ner_result.entities
                                    ],
                                    "entity_count": len(ner_result.entities),
                                    "processing_time_ms": ner_result.processing_time_ms,
                                    "from_cache": ner_result.from_cache,
                                }

                                logger.info(
                                    "ner_extraction_completed",
                                    document_id=str(doc.id),
                                    entity_count=len(ner_result.entities),
                                    from_cache=ner_result.from_cache,
                                )
                        except Exception as ner_error:
                            logger.warning(
                                "ner_extraction_failed_during_extraction",
                                document_id=str(doc.id),
                                **safe_error_log(ner_error),
                            )

                        # ENTERPRISE: Deadline-Extraktion aus OCR-Text
                        try:
                            from app.services.document_intelligence import (
                                get_deadline_extraction_service,
                            )
                            deadline_service = get_deadline_extraction_service()

                            # Prüfe ob Dokument einem Privat-Space zugeordnet ist
                            privat_space_id = getattr(doc, 'privat_space_id', None)

                            if privat_space_id:
                                # Deadline-Extraktion mit automatischer Erstellung
                                deadline_result = await deadline_service.extract_and_create_deadlines(
                                    text=doc.extracted_text,
                                    db=db,
                                    space_id=privat_space_id,
                                    document_id=doc.id,
                                )

                                if deadline_result and deadline_result.deadlines:
                                    doc.extracted_data["deadlines"] = {
                                        "extracted_count": len(deadline_result.deadlines),
                                        "created_count": deadline_result.created_count,
                                        "deadlines": [
                                            {
                                                "title": d.title,
                                                "due_date": d.due_date.isoformat() if d.due_date else None,
                                                "deadline_type": d.deadline_type,
                                                "original_text": d.original_text,
                                                "confidence": d.confidence,
                                            }
                                            for d in deadline_result.deadlines
                                        ],
                                        "processing_time_ms": deadline_result.processing_time_ms,
                                    }

                                    if deadline_result.created_count > 0:
                                        logger.info(
                                            "deadlines_auto_created",
                                            document_id=str(doc.id),
                                            space_id=str(privat_space_id),
                                            created_count=deadline_result.created_count,
                                        )
                        except Exception as deadline_error:
                            logger.warning(
                                "deadline_extraction_failed_during_extraction",
                                document_id=str(doc.id),
                                **safe_error_log(deadline_error),
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
                    error_msg = f"Document {doc.id}: {safe_error_detail(e, 'Extraktion')}"
                    if len(stats["errors"]) < 100:  # Max 100 Fehler speichern
                        stats["errors"].append(error_msg)
                    logger.error(
                        "document_extraction_failed",
                        document_id=str(doc.id),
                        **safe_error_log(e),
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
    name="app.workers.tasks.extraction_tasks.reprocess_single_document",
    max_retries=3,
    soft_time_limit=60,
    time_limit=90,
)
def reprocess_single_document(
    self,
    document_id: str,
) -> Dict[str, Any]:
    """
    Einzelnes Dokument für strukturierte Extraktion reprocessen.

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
    """Async Implementation für Einzeldokument-Reprocessing."""
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

            # Strukturierte Extraktion (mit Sprache für Übersetzung)
            # db wird für Eingangs-/Ausgangsrechnung-Erkennung benötigt
            extraction_result = await extraction_service.extract(
                document.extracted_text,
                document_id=document_id,
                detected_language=detected_language,
                page_count=getattr(document, 'page_count', None),
                db=db,
            )

            if extraction_result:
                # In DB speichern
                # WICHTIG: exclude_none=False um Übersetzungs-Metadaten zu behalten
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
                **safe_error_log(e),
            )
            return {
                "success": False,
                "document_id": document_id,
                "error": safe_error_detail(e, "Vorgang"),
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
    name="app.workers.tasks.extraction_tasks.generate_extraction_stats",
    soft_time_limit=300,
    time_limit=360,
)
def generate_extraction_stats() -> Dict[str, Any]:
    """
    Generiert Statistiken über die strukturierte Extraktion.

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
    """Async Implementation für Stats-Generierung."""
    from app.db.session import get_async_session_context
    async with get_async_session_context() as db:
        # Gesamt-Dokumente
        total_result = await db.execute(
            select(func.count()).select_from(Document).where(
                Document.deleted_at.is_(None)
            )
        )
        total_documents = total_result.scalar() or 0

        # Mit Extraktion
        extracted_result = await db.execute(
            select(func.count())
            .select_from(Document)
            .where(
                and_(
                    Document.deleted_at.is_(None),
                    Document.extracted_data.isnot(None),
                )
            )
        )
        with_extraction = extracted_result.scalar() or 0

        # Dokumente laden für detaillierte Stats
        docs_result = await db.execute(
            select(Document).where(
                and_(
                    Document.deleted_at.is_(None),
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


# ==================== Quick Classification Task ====================


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.extraction_tasks.quick_classify_document",
    max_retries=1,
    soft_time_limit=30,  # 30 Sekunden Soft-Limit
    time_limit=45,  # 45 Sekunden Hard-Limit
)
def quick_classify_document(
    self,
    document_id: str,
) -> Dict[str, Any]:
    """
    Schnelle Dokumenten-Klassifizierung - läuft PARALLEL zum vollständigen OCR.

    Ziel: Innerhalb von 2-5 Sekunden erkennen ob Eingangs- oder Ausgangsrechnung
    und automatisch den passenden Tag zuweisen.

    Workflow:
    1. Dokument aus MinIO laden (nur erste Seite)
    2. Schnelles OCR mit Surya (CPU-basiert, schneller Start)
    3. QuickClassificationService aufrufen
    4. Tag automatisch zuweisen wenn Confidence >= 70%
    5. Document aktualisieren

    Args:
        document_id: UUID des Dokuments

    Returns:
        {
            "document_id": "...",
            "direction": "incoming" | "outgoing" | "unknown",
            "confidence": 0.95,
            "reason": "Firmen-USt-IdNr im Empfängerbereich gefunden",
            "tag_assigned": true,
            "tag_name": "Eingangsrechnung",
            "processing_time_ms": 2500
        }
    """
    return asyncio.run(_async_quick_classify(self, document_id))


async def _async_quick_classify(task, document_id: str) -> Dict[str, Any]:
    """
    Quick Classification - wartet auf OCR und nutzt vorhandenen OCR-Text.

    Da Surya auf CPU 3+ Minuten braucht, läuft Quick Classification NACH dem
    regulaeren OCR und nutzt dessen Text. Kein eigenes OCR mehr!

    Workflow:
    1. Document laden
    2. Warten bis OCR fertig ist (max 5 Minuten)
    3. Vorhandenen OCR-Text nutzen
    4. Classification durchführen (schnell, nur Text-Analyse)
    5. Tag automatisch zuweisen
    """
    from app.services.quick_classification_service import (
        get_quick_classification_service,
    )
    from app.api.schemas.extracted_data import InvoiceDirection
    from app.db.session import get_async_session_context
    from app.db.models import ProcessingStatus

    start_time = datetime.now(timezone.utc)
    doc_uuid = UUID(document_id)

    logger.info(
        "quick_classification_started",
        document_id=document_id,
        task_id=task.request.id
    )

    async with get_async_session_context() as db:
        try:
            # 1. Document laden und Status auf "processing" setzen
            result = await db.execute(
                select(Document).where(Document.id == doc_uuid)
            )
            doc = result.scalar_one_or_none()

            if not doc:
                logger.warning("quick_classification_document_not_found", document_id=document_id)
                return {"error": "Dokument nicht gefunden", "document_id": document_id}

            # Status auf "processing" setzen
            doc.quick_classification_status = "processing"
            await db.commit()

            # 2. Prüfen ob OCR fertig ist (Task wird jetzt nach OCR getriggert)
            if doc.status == ProcessingStatus.FAILED:
                doc.quick_classification_status = "failed"
                doc.quick_classification_result = {"error": "OCR fehlgeschlagen"}
                await db.commit()
                return {"error": "OCR fehlgeschlagen", "document_id": document_id}

            # 3. Vorhandenen OCR-Text nutzen (kein eigenes OCR!)
            ocr_text = doc.extracted_text

            if not ocr_text or len(ocr_text.strip()) < 20:
                # Zu wenig Text extrahiert
                doc.quick_classification_status = "completed"
                doc.quick_classification_result = {
                    "direction": "unknown",
                    "confidence": 0.0,
                    "reason": "Zu wenig Text extrahiert",
                    "tag_assigned": False
                }
                await db.commit()
                return {
                    "document_id": document_id,
                    "direction": "unknown",
                    "confidence": 0.0,
                    "reason": "Zu wenig Text extrahiert",
                    "tag_assigned": False
                }

            # 5. Quick Classification Service aufrufen
            classification_service = get_quick_classification_service()
            classification_result = await classification_service.classify_document(
                document_id=doc_uuid,
                ocr_text=ocr_text,
                db=db,
                auto_assign_tag=True
            )

            # 6. Document aktualisieren
            # WICHTIG: doc-Objekt neu laden, da _assign_tag() evtl. ein anderes Objekt modifiziert hat
            await db.refresh(doc)

            processing_time = (datetime.now(timezone.utc) - start_time).total_seconds()
            processing_ms = int(processing_time * 1000)

            doc.quick_classification_status = "completed"
            doc.quick_classification_result = classification_service.to_dict(classification_result)
            doc.quick_classification_result["processing_time_ms"] = processing_ms

            await db.commit()

            logger.info(
                "quick_classification_completed",
                document_id=document_id,
                direction=classification_result.direction.value if isinstance(classification_result.direction, InvoiceDirection) else classification_result.direction,
                confidence=classification_result.confidence,
                tag_assigned=classification_result.tag_assigned,
                processing_time_ms=processing_ms
            )

            return {
                "document_id": document_id,
                "direction": classification_result.direction.value if isinstance(classification_result.direction, InvoiceDirection) else classification_result.direction,
                "confidence": classification_result.confidence,
                "reason": classification_result.reason,
                "tag_assigned": classification_result.tag_assigned,
                "tag_name": classification_result.tag_name,
                "processing_time_ms": processing_ms
            }

        except Exception as e:
            logger.error(
                "quick_classification_failed",
                document_id=document_id,
                **safe_error_log(e)
            )

            # Status auf "failed" setzen mit sanitierter Fehlermeldung
            sanitized_error = _sanitize_error_message(str(e))
            try:
                doc.quick_classification_status = "failed"
                doc.quick_classification_result = {"error": sanitized_error}
                await db.commit()
            except Exception as db_error:
                logger.debug(
                    "quick_classification_status_update_failed",
                    document_id=document_id,
                    error_type=type(db_error).__name__,
                )

            return {
                "error": sanitized_error,
                "document_id": document_id
            }


def _sanitize_error_message(error: str) -> str:
    """
    Entfernt sensible Informationen aus Fehlermeldungen.

    Enterprise Refined: Keine internen Pfade oder Stack Traces in DB speichern.

    Args:
        error: Original-Fehlermeldung

    Returns:
        Bereinigte Fehlermeldung (max 200 Zeichen)
    """
    import re

    # Pfade entfernen (Windows und Unix)
    error = re.sub(r'[A-Za-z]:\\[^\s,;:]+', '[PATH]', error)
    error = re.sub(r'/(?:home|usr|var|opt|tmp|etc|app)[^\s,;:]*', '[PATH]', error)

    # Dateinamen mit Zeilennummern entfernen (z.B. "file.py:123")
    error = re.sub(r'\b\w+\.py:\d+', '[FILE]', error)

    # IP-Adressen entfernen
    error = re.sub(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', '[IP]', error)

    # Auf 200 Zeichen begrenzen
    if len(error) > 200:
        error = error[:197] + "..."

    return error.strip()


# =============================================================================
# QUICK CLASSIFICATION RE-PROCESSING (Post-Fix 2025-12-15)
# =============================================================================


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.extraction_tasks.reprocess_quick_classification",
    # Z.2 FIX: max_retries von 0 auf 3 erhöht für bessere Fehlertoleranz
    max_retries=3,
    default_retry_delay=60,  # 1 Minute zwischen Retries
    soft_time_limit=3600,  # 1 Stunde Soft-Limit
    time_limit=3900,  # 1h 5min Hard-Limit
)
def reprocess_quick_classification(
    self,
    batch_size: int = 50,
    skip_correct: bool = False,
    owner_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Reprocessed Quick-Classification für alle Dokumente.

    Aktualisiert rename_suggestion und quick_classification_result
    basierend auf dem bereits vorhandenen OCR-Text.

    Args:
        batch_size: Dokumente pro Batch (default 50)
        skip_correct: Dokumente mit korrekter Extraktion überspringen
        owner_id: Nur Dokumente eines bestimmten Users (optional)

    Returns:
        {
            "total_processed": 293,
            "total_updated": 250,
            "total_skipped": 43,
            "total_failed": 0,
            "duration_seconds": 120,
            "examples": [...]
        }
    """
    return asyncio.run(
        _async_reprocess_quick_classification(
            task=self,
            batch_size=batch_size,
            skip_correct=skip_correct,
            owner_id=owner_id,
        )
    )


async def _async_reprocess_quick_classification(
    task,
    batch_size: int,
    skip_correct: bool,
    owner_id: Optional[str],
) -> Dict[str, Any]:
    """Async Implementation des Quick-Classification Reprocessing."""
    from app.services.quick_classification_service import QuickClassificationService
    from app.db.session import get_async_session_context

    start_time = datetime.now(timezone.utc)
    stats = {
        "total_processed": 0,
        "total_updated": 0,
        "total_skipped": 0,
        "total_failed": 0,
        "examples": [],
    }

    qc_service = QuickClassificationService()

    async with get_async_session_context() as db:
        # Query: Alle Dokumente mit OCR-Text
        # WICHTIG: is_deleted ist eine Property, nicht Column! Filter via deleted_at
        query = select(Document).where(
            and_(
                Document.deleted_at.is_(None),  # Nicht gelöscht (is_deleted property)
                Document.extracted_text.isnot(None),
            )
        )

        if owner_id:
            query = query.where(Document.owner_id == UUID(owner_id))

        # Sortieren nach created_at für konsistente Verarbeitung
        query = query.order_by(Document.created_at.desc())

        result = await db.execute(query)
        documents = result.scalars().all()

        total = len(documents)
        logger.info(
            "quick_classification_reprocess_started",
            total_documents=total,
            batch_size=batch_size,
            skip_correct=skip_correct,
        )

        # Batch-weise verarbeiten
        for i, doc in enumerate(documents):
            try:
                # Task-Progress aktualisieren
                if hasattr(task, 'update_state'):
                    task.update_state(
                        state='PROGRESS',
                        meta={
                            'current': i + 1,
                            'total': total,
                            'percent': round((i + 1) / total * 100, 1),
                        }
                    )

                # Bisherige Werte merken (aus quick_classification_result JSON)
                old_qc = doc.quick_classification_result or {}
                old_suggestion = old_qc.get("rename_suggestion")
                old_invoice = old_qc.get("invoice_number")

                # Quick-Classification ausführen
                # classify_document generiert intern auch die Rename-Suggestion
                qc_result_obj = await qc_service.classify_document(
                    document_id=doc.id,
                    ocr_text=doc.extracted_text,
                    db=db,
                    auto_assign_tag=False,  # Keine Tag-Zuweisung bei Reprocessing
                )

                # Result zu Dict konvertieren
                qc_result = qc_service.to_dict(qc_result_obj)

                # Prüfen ob sich etwas geändert hat
                new_invoice = qc_result.get("invoice_number")
                new_suggestion = qc_result.get("rename_suggestion")
                changed = (
                    new_suggestion != old_suggestion or
                    new_invoice != old_invoice
                )

                if skip_correct and not changed:
                    stats["total_skipped"] += 1
                    continue

                # Dokument aktualisieren
                doc.quick_classification_result = qc_result

                stats["total_processed"] += 1
                if changed:
                    stats["total_updated"] += 1

                    # Beispiele sammeln (max 10)
                    if len(stats["examples"]) < 10:
                        stats["examples"].append({
                            "filename": doc.original_filename,
                            "old_invoice": old_invoice,
                            "new_invoice": new_invoice,
                            "old_suggestion": old_suggestion,
                            "new_suggestion": new_suggestion,
                        })

                # Batch-Commit
                if (i + 1) % batch_size == 0:
                    await db.commit()
                    logger.info(
                        "quick_classification_batch_committed",
                        processed=i + 1,
                        total=total,
                        updated=stats["total_updated"],
                    )

            except Exception as e:
                stats["total_failed"] += 1
                logger.error(
                    "quick_classification_reprocess_failed",
                    document_id=str(doc.id),
                    filename=doc.original_filename,
                    **safe_error_log(e),
                )

        # Finales Commit
        await db.commit()

        # Statistiken finalisieren
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        stats["duration_seconds"] = round(duration, 2)

        logger.info(
            "quick_classification_reprocess_completed",
            total_processed=stats["total_processed"],
            total_updated=stats["total_updated"],
            total_skipped=stats["total_skipped"],
            total_failed=stats["total_failed"],
            duration_seconds=stats["duration_seconds"],
        )

        return stats

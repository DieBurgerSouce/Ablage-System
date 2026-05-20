# -*- coding: utf-8 -*-
"""
Celery Tasks für automatische Dokumentenablage und Matching.

Feature #7: Automation 2.0
- auto_file_new_documents_task: Neue Dokumente automatisch ablegen
- train_filing_model_task: Wöchentlich Filing-Modelle trainieren
- auto_match_documents_task: Einzelnes Dokument matchen
- batch_match_documents_task: Täglich Batch-Matching durchführen
- trigger_auto_filing_pipeline_task: Pipeline nach OCR-Abschluss auslösen
"""

from __future__ import annotations

import asyncio
import json
from typing import Dict, List, Optional
from uuid import UUID

import structlog
from sqlalchemy import and_, select, update

from app.core.config import settings
from app.core.datetime_utils import utc_now
from app.core.safe_errors import safe_error_log, safe_error_detail
from app.db.models import Company, Document
from app.db.models_approval_extended import AutoFilingRule
from app.db.session import get_sync_session
from app.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


@celery_app.task(
    name="app.workers.tasks.auto_filing_tasks.auto_file_new_documents_task",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def auto_file_new_documents_task(
    self,
    company_id: Optional[str] = None,
    limit: int = 100,
) -> Dict[str, object]:
    """Legt neue/unklassifizierte Dokumente automatisch ab.

    Wird regelmäßig via Celery Beat ausgeführt.
    Sucht Dokumente ohne Kategorie und versucht sie automatisch abzulegen.

    Args:
        company_id: Optional: Nur für diese Firma
        limit: Max. Anzahl Dokumente pro Durchlauf

    Returns:
        Dict mit Statistiken
    """
    logger.info("Starte automatische Dokumentenablage...")

    async def _process() -> Dict[str, object]:
        from app.db.session import get_async_session_context
        from app.services.automation.auto_filing_service import (
            AutoFilingService,
        )

        total_processed = 0
        total_filed = 0
        total_skipped = 0
        errors: List[str] = []

        async with get_async_session_context() as db:
            # Companies ermitteln
            if company_id:
                company_ids = [UUID(company_id)]
            else:
                company_result = await db.execute(select(Company.id))
                company_ids = [row[0] for row in company_result.all()]

            for cid in company_ids:
                try:
                    # Unklassifizierte Dokumente finden
                    doc_stmt = (
                        select(Document)
                        .where(
                            and_(
                                Document.company_id == cid,
                                Document.category.is_(None),
                            )
                        )
                        .order_by(Document.created_at.desc())
                        .limit(limit)
                    )
                    doc_result = await db.execute(doc_stmt)
                    documents = doc_result.scalars().all()

                    if not documents:
                        continue

                    service = AutoFilingService(db)

                    for doc in documents:
                        total_processed += 1
                        result = await service.auto_file_document(
                            db, cid, doc.id
                        )

                        if result.filed:
                            total_filed += 1
                        else:
                            total_skipped += 1

                    await db.commit()

                except Exception as exc:
                    error_msg = (
                        f"Fehler bei Auto-Filing für "
                        f"Company {cid}: {exc}"
                    )
                    errors.append(error_msg)
                    logger.error(error_msg)

        return {
            "processed": total_processed,
            "filed": total_filed,
            "skipped": total_skipped,
            "companies_processed": len(company_ids),
            "errors": errors,
        }

    result = asyncio.run(_process())

    logger.info(
        "Auto-Filing abgeschlossen: %d verarbeitet, %d abgelegt, "
        "%d übersprungen",
        result.get("processed", 0),
        result.get("filed", 0),
        result.get("skipped", 0),
    )

    return result


@celery_app.task(
    name="app.workers.tasks.auto_filing_tasks.train_filing_model_task",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
)
def train_filing_model_task(
    self,
    company_id: Optional[str] = None,
) -> Dict[str, object]:
    """Trainiert Filing-Modelle basierend auf historischen Daten.

    Wird wöchentlich via Celery Beat ausgeführt.
    Aktualisiert Accuracy-Werte und Trainingsstatistiken.

    Args:
        company_id: Optional: Nur für diese Firma

    Returns:
        Dict mit Trainings-Statistiken
    """
    logger.info("Starte Filing-Modell-Training...")

    async def _train() -> Dict[str, object]:
        from app.db.session import get_async_session_context
        from app.services.automation.auto_filing_service import (
            AutoFilingService,
        )

        training_results: List[Dict[str, object]] = []
        errors: List[str] = []

        async with get_async_session_context() as db:
            # Companies ermitteln
            if company_id:
                company_ids = [UUID(company_id)]
            else:
                company_result = await db.execute(select(Company.id))
                company_ids = [row[0] for row in company_result.all()]

            for cid in company_ids:
                try:
                    service = AutoFilingService(db)

                    # Alle aktiven Regeln laden
                    rules_stmt = select(AutoFilingRule).where(
                        and_(
                            AutoFilingRule.company_id == cid,
                            AutoFilingRule.is_active.is_(True),
                        )
                    )
                    rules_result = await db.execute(rules_stmt)
                    rules = rules_result.scalars().all()

                    for rule in rules:
                        try:
                            result = await service.train_model(
                                db, cid, rule.id
                            )
                            training_results.append(result)
                        except Exception as exc:
                            error_msg = (
                                f"Fehler beim Training von Regel "
                                f"{rule.id}: {exc}"
                            )
                            errors.append(error_msg)
                            logger.error(error_msg)

                    await db.commit()

                except Exception as exc:
                    error_msg = (
                        f"Fehler beim Training für "
                        f"Company {cid}: {exc}"
                    )
                    errors.append(error_msg)
                    logger.error(error_msg)

        return {
            "models_trained": len(training_results),
            "companies_processed": len(company_ids),
            "results": training_results,
            "errors": errors,
        }

    result = asyncio.run(_train())

    logger.info(
        "Filing-Modell-Training abgeschlossen: %d Modelle trainiert",
        result.get("models_trained", 0),
    )

    return result


@celery_app.task(
    name="app.workers.tasks.auto_filing_tasks.auto_match_documents_task",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def auto_match_documents_task(
    self,
    company_id: str,
    document_id: str,
    confidence_threshold: float = 0.8,
) -> Dict[str, object]:
    """Matched ein einzelnes Dokument mit potenziellen Partnern.

    Wird ausgeloest wenn ein neues Dokument verarbeitet wurde.

    Args:
        company_id: ID der Firma
        document_id: ID des Dokuments
        confidence_threshold: Mindest-Confidence

    Returns:
        Dict mit Match-Ergebnissen
    """
    logger.info(
        "Starte Auto-Matching für Dokument %s...", document_id
    )

    async def _match() -> Dict[str, object]:
        from app.db.session import get_async_session_context
        from app.services.automation.auto_matching_service import (
            AutoMatchingService,
        )

        async with get_async_session_context() as db:
            service = AutoMatchingService(db)

            saved_matches = await service.auto_match_and_save(
                db,
                UUID(company_id),
                UUID(document_id),
                confidence_threshold,
            )

            await db.commit()

            return {
                "document_id": document_id,
                "matches_found": len(saved_matches),
                "matches": [
                    {
                        "match_id": str(m.id),
                        "matched_document_id": str(
                            m.matched_document_id
                        ),
                        "match_type": m.match_type,
                        "confidence": m.confidence,
                    }
                    for m in saved_matches
                ],
            }

    result = asyncio.run(_match())

    logger.info(
        "Auto-Matching abgeschlossen für %s: %d Matches",
        document_id,
        result.get("matches_found", 0),
    )

    return result


@celery_app.task(
    name="app.workers.tasks.auto_filing_tasks.batch_match_documents_task",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
)
def batch_match_documents_task(
    self,
    company_id: Optional[str] = None,
    confidence_threshold: float = 0.8,
    limit: int = 200,
) -> Dict[str, object]:
    """Batch-Matching: Sucht Matches für ungematchte Dokumente.

    Wird täglich via Celery Beat ausgeführt.
    Verarbeitet Dokumente die noch keine Matching-Partner haben.

    Args:
        company_id: Optional: Nur für diese Firma
        confidence_threshold: Mindest-Confidence
        limit: Max. Anzahl Dokumente pro Durchlauf

    Returns:
        Dict mit Statistiken
    """
    logger.info("Starte Batch-Dokumenten-Matching...")

    async def _batch_match() -> Dict[str, object]:
        from app.db.session import get_async_session_context
        from app.services.automation.auto_matching_service import (
            AutoMatchingService,
        )

        total_processed = 0
        total_matches = 0
        errors: List[str] = []

        async with get_async_session_context() as db:
            # Companies ermitteln
            if company_id:
                company_ids = [UUID(company_id)]
            else:
                company_result = await db.execute(select(Company.id))
                company_ids = [row[0] for row in company_result.all()]

            for cid in company_ids:
                try:
                    service = AutoMatchingService(db)

                    # Ungematchte Dokumente holen
                    unmatched = await service.get_unmatched_documents(
                        db, cid, limit=limit
                    )

                    for doc_info in unmatched:
                        doc_id_str = str(doc_info.get("document_id", ""))
                        if not doc_id_str:
                            continue

                        total_processed += 1

                        try:
                            saved = await service.auto_match_and_save(
                                db,
                                cid,
                                UUID(doc_id_str),
                                confidence_threshold,
                            )
                            total_matches += len(saved)
                        except Exception as exc:
                            logger.warning(
                                "Match-Fehler für Dokument %s: %s",
                                doc_id_str,
                                str(exc),
                            )

                    await db.commit()

                except Exception as exc:
                    error_msg = (
                        f"Fehler beim Batch-Matching für "
                        f"Company {cid}: {exc}"
                    )
                    errors.append(error_msg)
                    logger.error(error_msg)

        return {
            "processed": total_processed,
            "matches_found": total_matches,
            "companies_processed": len(company_ids),
            "errors": errors,
        }

    result = asyncio.run(_batch_match())

    logger.info(
        "Batch-Matching abgeschlossen: %d verarbeitet, %d Matches",
        result.get("processed", 0),
        result.get("matches_found", 0),
    )

    return result


@celery_app.task(
    name="app.workers.tasks.auto_filing_tasks.trigger_auto_filing_pipeline_task",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    queue="default",
)
def trigger_auto_filing_pipeline_task(
    self,
    document_id: str,
    company_id: str,
    ocr_text: str,
    user_id: Optional[str] = None,
    metadata: Optional[Dict[str, object]] = None,
) -> Dict[str, object]:
    """Löst die automatische Ablage-Pipeline nach OCR-Abschluss aus.

    Wird von ocr_tasks.py aufgerufen sobald OCR-Text verfügbar ist.
    Koordiniert Klassifizierung, Entity-Linking, Projekt-Zuweisung und
    Kategorisierung in einer vollautomatischen Pipeline.

    Kein Logging von OCR-Text oder PII (DSGVO-konform).

    Args:
        document_id: UUID des Dokuments als String
        company_id: Mandant-UUID als String
        ocr_text: Extrahierter OCR-Text (wird NICHT geloggt)
        user_id: Optional - UUID des auslösenden Benutzers
        metadata: Optional - Zusätzliche Metadaten (Dateiname etc.)

    Returns:
        Dict mit Pipeline-Ergebnis und Status-Informationen
    """
    task_id = self.request.id

    # SECURITY: OCR-Text und andere PII werden NIEMALS geloggt
    logger.info(
        "pipeline_task_starting",
        task_id=task_id,
        document_id=document_id,
        company_id=company_id,
        has_user_id=user_id is not None,
        has_metadata=metadata is not None,
    )

    def _publish_progress(step_name: str, status: str, extra: Optional[Dict[str, object]] = None) -> None:
        """Sendet Pipeline-Fortschritt via Redis Pub/Sub."""
        try:
            import redis as _redis
            redis_client = _redis.Redis.from_url(settings.REDIS_URL)
            payload: Dict[str, object] = {
                "step": step_name,
                "status": status,
                "document_id": document_id,
                "task_id": task_id,
            }
            if extra:
                payload.update(extra)
            redis_client.publish(
                f"pipeline:progress:{document_id}",
                json.dumps(payload),
            )
        except Exception as pub_err:
            # Pub/Sub-Fehler darf Pipeline nicht blockieren
            logger.warning(
                "pipeline_progress_publish_failed",
                task_id=task_id,
                document_id=document_id,
                step=step_name,
                error_type=type(pub_err).__name__,
            )

    async def _run_pipeline() -> Dict[str, object]:
        from app.db.session import get_async_session_context
        from app.services.pipeline.document_pipeline_orchestrator import (
            DocumentPipelineOrchestrator,
        )

        _publish_progress("pipeline_start", "running")

        async with get_async_session_context() as db:
            orchestrator = DocumentPipelineOrchestrator(db)

            # Pipeline ausführen
            pipeline_result = await orchestrator.process_document(
                document_id=UUID(document_id),
                ocr_text=ocr_text,
                company_id=UUID(company_id),
                user_id=UUID(user_id) if user_id else None,
                metadata=metadata,
            )

            _publish_progress(
                "pipeline_complete",
                "done",
                {
                    "auto_processed": pipeline_result.auto_processed,
                    "requires_review": pipeline_result.requires_review,
                    "status": pipeline_result.status.value,
                },
            )

            # Dokument-Record mit Pipeline-Ergebnissen aktualisieren
            result_dict = pipeline_result.to_dict()

            doc_stmt = select(Document).where(
                and_(
                    Document.id == UUID(document_id),
                    Document.company_id == UUID(company_id),
                )
            )
            doc_result = await db.execute(doc_stmt)
            document = doc_result.scalar_one_or_none()

            if document is None:
                logger.error(
                    "pipeline_document_not_found",
                    task_id=task_id,
                    document_id=document_id,
                    company_id=company_id,
                )
                return {
                    "success": False,
                    "document_id": document_id,
                    "error": "Dokument nicht gefunden",
                }

            # Automatisch abgelegte Felder setzen
            if pipeline_result.auto_processed:
                if pipeline_result.category_id:
                    if hasattr(document, "category_id"):
                        document.category_id = pipeline_result.category_id
                    elif hasattr(document, "category"):
                        document.category = pipeline_result.category_name

                if pipeline_result.linked_entity_id and hasattr(document, "entity_id"):
                    document.entity_id = pipeline_result.linked_entity_id

                if pipeline_result.assigned_project_id and hasattr(document, "project_id"):
                    document.project_id = pipeline_result.assigned_project_id

            # Pipeline-Ergebnis in ai_metadata speichern
            existing_meta: Dict[str, object] = document.ai_metadata or {}
            existing_meta["pipeline_result"] = result_dict
            document.ai_metadata = existing_meta

            await db.commit()

            # Redis-Events senden
            try:
                import redis as _redis
                redis_client = _redis.Redis.from_url(settings.REDIS_URL)

                if pipeline_result.auto_processed:
                    redis_client.publish(
                        f"document:events:{company_id}",
                        json.dumps({
                            "event": "document.auto_filed",
                            "document_id": document_id,
                            "company_id": company_id,
                            "category": pipeline_result.category_name,
                            "entity": pipeline_result.linked_entity_name,
                            "project": pipeline_result.assigned_project_name,
                        }),
                    )
                    logger.info(
                        "pipeline_document_auto_filed",
                        task_id=task_id,
                        document_id=document_id,
                        category=pipeline_result.category_name,
                        has_entity=pipeline_result.linked_entity_id is not None,
                        has_project=pipeline_result.assigned_project_id is not None,
                    )

                elif pipeline_result.requires_review:
                    redis_client.publish(
                        f"document:events:{company_id}",
                        json.dumps({
                            "event": "document.review_needed",
                            "document_id": document_id,
                            "company_id": company_id,
                            "review_reasons": pipeline_result.review_reasons,
                        }),
                    )
                    logger.info(
                        "pipeline_document_requires_review",
                        task_id=task_id,
                        document_id=document_id,
                        review_reasons=pipeline_result.review_reasons,
                    )

            except Exception as event_err:
                # Event-Fehler darf Ergebnis nicht blockieren
                logger.warning(
                    "pipeline_event_publish_failed",
                    task_id=task_id,
                    document_id=document_id,
                    **safe_error_log(event_err),
                )

            return {
                "success": True,
                "document_id": document_id,
                "auto_processed": pipeline_result.auto_processed,
                "requires_review": pipeline_result.requires_review,
                "status": pipeline_result.status.value,
                "category": pipeline_result.category_name,
                "entity": pipeline_result.linked_entity_name,
                "project": pipeline_result.assigned_project_name,
                "total_processing_time_ms": pipeline_result.total_processing_time_ms,
                "decisions_count": len(pipeline_result.decisions),
                "anomalies_count": len(pipeline_result.anomalies),
            }

    try:
        result = asyncio.run(_run_pipeline())

        logger.info(
            "pipeline_task_completed",
            task_id=task_id,
            document_id=document_id,
            auto_processed=result.get("auto_processed"),
            requires_review=result.get("requires_review"),
            status=result.get("status"),
        )

        return result

    except Exception as exc:
        _publish_progress("pipeline_error", "failed", {"error_type": type(exc).__name__})

        logger.error(
            "pipeline_task_failed",
            task_id=task_id,
            document_id=document_id,
            **safe_error_log(exc),
        )

        retry_count = self.request.retries
        max_retries = getattr(self, "max_retries", 2)

        if retry_count < max_retries:
            raise self.retry(exc=exc)

        return {
            "success": False,
            "document_id": document_id,
            "error": safe_error_detail(exc, "Pipeline"),
        }

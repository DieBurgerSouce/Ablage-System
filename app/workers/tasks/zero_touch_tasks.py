"""
Zero-Touch OCR Celery Tasks.

Automatische Dokumentenverarbeitung mit Zero-Touch:
- Einzelverarbeitung mit Confidence-Scoring
- Batch-Verarbeitung von Pending-Dokumenten
- Schwellenwert-Neuberechnung basierend auf Reviews
- Automatische Freigabe bei hoher Confidence

Feinpoliert und durchdacht - Enterprise Zero-Touch Processing.
"""

import asyncio
import structlog
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select, and_, or_, func

from app.workers.celery_app import celery_app
from app.workers.celery_metrics import (
    record_task_started,
    record_task_succeeded,
    record_task_failed,
)
from app.db.session import get_async_session_context
from app.db.models import Document, ProcessingStatus, ZeroTouchResult
from app.core.safe_errors import safe_error_log, safe_error_detail

logger = structlog.get_logger(__name__)


# =============================================================================
# Single Document Zero-Touch Processing
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.zero_touch_tasks.process_document_zero_touch",
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 2},
    retry_backoff=True,
    queue="default",
    soft_time_limit=120,
    time_limit=180,
)
def process_document_zero_touch(
    self,
    document_id: str,
    company_id: str,
) -> Dict[str, Any]:
    """Verarbeite ein Dokument durch die Zero-Touch Pipeline.

    Pipeline-Schritte:
    1. OCR-Extraktion validieren
    2. Confidence-Score berechnen
    3. Entity-Matching durchfuehren
    4. Schwellenwerte pruefen
    5. Auto-Freigabe oder Review-Queue

    Args:
        document_id: UUID des Dokuments als String
        company_id: UUID der Firma als String

    Returns:
        Dict mit Verarbeitungsergebnis und Confidence-Scores
    """
    record_task_started("zero_touch.process_document")
    logger.info("zero_touch_task_started", document_id=document_id)

    async def _process_document() -> Dict[str, Any]:
        async with get_async_session_context() as db:
            try:
                doc_uuid = UUID(document_id)
                comp_uuid = UUID(company_id)
            except ValueError as e:
                return {
                    "success": False,
                    "error": safe_error_detail(e, "UUID-Validierung"),
                }

            # Dokument laden
            doc_query = select(Document).where(
                and_(
                    Document.id == doc_uuid,
                    Document.company_id == comp_uuid,
                    Document.deleted_at.is_(None),
                )
            )
            doc_result = await db.execute(doc_query)
            document = doc_result.scalar_one_or_none()

            if not document:
                return {
                    "success": False,
                    "error": "Dokument nicht gefunden oder keine Berechtigung",
                }

            if document.status != ProcessingStatus.COMPLETED.value:
                return {
                    "success": False,
                    "error": f"Dokument noch nicht verarbeitet (Status: {document.status})",
                }

            # Zero-Touch Orchestrator nutzen
            from app.services.zero_touch.zero_touch_orchestrator import (
                ZeroTouchOrchestrator,
            )

            orchestrator = ZeroTouchOrchestrator()
            result = await orchestrator.process_document(
                document_id=doc_uuid,
                company_id=comp_uuid,
                db=db,
            )

            return {
                "success": True,
                "document_id": document_id,
                "auto_processed": result.auto_processed,
                "requires_review": result.requires_review,
                "overall_confidence": result.overall_confidence,
                "field_confidences": result.field_confidences,
                "entity_matched": result.entity_id is not None,
                "entity_confidence": result.entity_confidence,
                "validation_errors": result.validation_errors,
            }

    try:
        result = asyncio.run(_process_document())

        if result.get("success"):
            record_task_succeeded("zero_touch.process_document")
            logger.info(
                "zero_touch_task_completed",
                document_id=document_id,
                auto_processed=result.get("auto_processed", False),
                confidence=result.get("overall_confidence", 0),
            )
        else:
            record_task_failed("zero_touch.process_document", result.get("error", "Unknown"))
            logger.warning(
                "zero_touch_task_failed",
                document_id=document_id,
                error=result.get("error"),
            )

        return result
    except Exception as e:
        record_task_failed("zero_touch.process_document", str(e))
        logger.error("zero_touch_task_exception", document_id=document_id, **safe_error_log(e))
        raise self.retry(exc=e)


# =============================================================================
# Batch Processing of Pending Documents
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.zero_touch_tasks.process_pending_documents",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
    queue="default",
    soft_time_limit=300,
    time_limit=600,
)
def process_pending_documents(
    self,
    batch_size: int = 50,
    created_within_hours: int = 24,
) -> Dict[str, Any]:
    """Pruefe und verarbeite neue Dokumente im Zero-Touch Modus.

    Findet COMPLETED Dokumente ohne ZeroTouchResult und queued sie
    fuer die automatische Verarbeitung.

    Args:
        batch_size: Maximale Anzahl zu verarbeitender Dokumente
        created_within_hours: Nur Dokumente der letzten X Stunden

    Returns:
        Dict mit Verarbeitungsstatistiken
    """
    record_task_started("zero_touch.process_pending")
    logger.info("zero_touch_pending_check_started", batch_size=batch_size)

    async def _process_pending() -> Dict[str, Any]:
        async with get_async_session_context() as db:
            # Zeitgrenze berechnen
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=created_within_hours)

            # Finde Dokumente ohne Zero-Touch Result
            stmt = (
                select(Document.id, Document.company_id)
                .outerjoin(ZeroTouchResult, Document.id == ZeroTouchResult.document_id)
                .where(
                    and_(
                        Document.status == ProcessingStatus.COMPLETED.value,
                        Document.deleted_at.is_(None),
                        Document.created_at >= cutoff_time,
                        ZeroTouchResult.id.is_(None),
                    )
                )
                .limit(batch_size)
            )

            result = await db.execute(stmt)
            pending_docs = result.all()

            stats = {
                "total_found": len(pending_docs),
                "queued": 0,
                "skipped": 0,
            }

            for doc_id, company_id in pending_docs:
                try:
                    process_document_zero_touch.delay(str(doc_id), str(company_id))
                    stats["queued"] += 1
                except Exception as e:
                    stats["skipped"] += 1
                    logger.warning(
                        "zero_touch_queue_failed",
                        document_id=str(doc_id),
                        **safe_error_log(e),
                    )

            return stats

    try:
        result = asyncio.run(_process_pending())
        record_task_succeeded("zero_touch.process_pending")
        logger.info(
            "zero_touch_pending_completed",
            total_found=result["total_found"],
            queued=result["queued"],
            skipped=result["skipped"],
        )
        return result
    except Exception as e:
        record_task_failed("zero_touch.process_pending", str(e))
        logger.error("zero_touch_pending_failed", **safe_error_log(e))
        raise self.retry(exc=e)


# =============================================================================
# Threshold Recalculation Based on Reviews
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.zero_touch_tasks.recalculate_thresholds",
    bind=True,
    max_retries=2,
    default_retry_delay=180,
    queue="maintenance",
    soft_time_limit=120,
    time_limit=180,
)
def recalculate_thresholds(
    self,
    lookback_days: int = 30,
) -> Dict[str, Any]:
    """Berechne optimale Schwellenwerte basierend auf Reviewergebnissen.

    Analysiert die letzten N Tage von Zero-Touch Ergebnissen und
    passt die Auto-Processing und Review-Schwellenwerte an, um
    die Balance zwischen Automatisierung und Genauigkeit zu optimieren.

    Args:
        lookback_days: Anzahl der Tage fuer historische Analyse

    Returns:
        Dict mit neuen Schwellenwerten und Metriken
    """
    record_task_started("zero_touch.recalculate_thresholds")
    logger.info("zero_touch_threshold_recalculation_started", lookback_days=lookback_days)

    async def _recalculate() -> Dict[str, Any]:
        async with get_async_session_context() as db:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=lookback_days)

            # Lade historische Zero-Touch Ergebnisse mit Review-Status
            query = (
                select(ZeroTouchResult)
                .where(
                    and_(
                        ZeroTouchResult.created_at >= cutoff_date,
                        ZeroTouchResult.overall_confidence.isnot(None),
                    )
                )
            )
            result = await db.execute(query)
            results = result.scalars().all()

            if len(results) < 100:
                # Zu wenig Daten fuer zuverlaessige Schwellenwerte
                logger.warning(
                    "zero_touch_threshold_insufficient_data",
                    sample_size=len(results),
                )
                return {
                    "success": False,
                    "error": f"Zu wenig Daten ({len(results)} < 100 Minimum)",
                    "auto_process_threshold": 0.90,
                    "review_threshold": 0.70,
                }

            # Analysiere Korrektheit nach Confidence-Level
            confidence_brackets = {
                "high": [],      # >= 0.90
                "medium": [],    # 0.70 - 0.89
                "low": [],       # < 0.70
            }

            for zt_result in results:
                confidence = zt_result.overall_confidence
                # Korrekt = auto_processed ohne nachträgliche Korrekturen
                # (vereinfachte Heuristik - könnte durch Review-Daten erweitert werden)
                is_correct = zt_result.auto_processed and not zt_result.validation_errors

                if confidence >= 0.90:
                    confidence_brackets["high"].append(is_correct)
                elif confidence >= 0.70:
                    confidence_brackets["medium"].append(is_correct)
                else:
                    confidence_brackets["low"].append(is_correct)

            # Berechne Accuracy pro Bracket
            def calc_accuracy(bracket: List[bool]) -> float:
                if not bracket:
                    return 0.0
                return sum(bracket) / len(bracket)

            high_accuracy = calc_accuracy(confidence_brackets["high"])
            medium_accuracy = calc_accuracy(confidence_brackets["medium"])
            low_accuracy = calc_accuracy(confidence_brackets["low"])

            # Neue Schwellenwerte basierend auf Ziel-Accuracy
            # Ziel: 95%+ Accuracy für Auto-Processing, 80%+ für Review
            new_auto_threshold = 0.90  # Default
            new_review_threshold = 0.70  # Default

            if high_accuracy >= 0.95:
                # High bracket ist zuverlaessig genug
                new_auto_threshold = 0.90
            elif high_accuracy >= 0.90:
                # Etwas restriktiver
                new_auto_threshold = 0.92
            else:
                # Zu viele Fehler, noch restriktiver
                new_auto_threshold = 0.95

            if medium_accuracy >= 0.80:
                new_review_threshold = 0.70
            elif medium_accuracy >= 0.70:
                new_review_threshold = 0.75
            else:
                new_review_threshold = 0.80

            # Schwellenwerte in AppConfig speichern
            from app.db.models import AppConfig

            config_query = select(AppConfig).where(
                AppConfig.key == "zero_touch_thresholds"
            )
            config_result = await db.execute(config_query)
            config = config_result.scalar_one_or_none()

            threshold_data = {
                "auto_process_threshold": new_auto_threshold,
                "review_threshold": new_review_threshold,
                "calculated_at": datetime.now(timezone.utc).isoformat(),
                "sample_size": len(results),
                "accuracy_metrics": {
                    "high": high_accuracy,
                    "medium": medium_accuracy,
                    "low": low_accuracy,
                },
            }

            if config:
                config.value = threshold_data
            else:
                config = AppConfig(
                    key="zero_touch_thresholds",
                    value=threshold_data,
                )
                db.add(config)

            await db.commit()

            return {
                "success": True,
                "auto_process_threshold": new_auto_threshold,
                "review_threshold": new_review_threshold,
                "sample_size": len(results),
                "high_accuracy": round(high_accuracy, 3),
                "medium_accuracy": round(medium_accuracy, 3),
                "low_accuracy": round(low_accuracy, 3),
            }

    try:
        result = asyncio.run(_recalculate())
        record_task_succeeded("zero_touch.recalculate_thresholds")
        logger.info(
            "zero_touch_thresholds_recalculated",
            auto_threshold=result.get("auto_process_threshold"),
            review_threshold=result.get("review_threshold"),
            sample_size=result.get("sample_size"),
        )
        return result
    except Exception as e:
        record_task_failed("zero_touch.recalculate_thresholds", str(e))
        logger.error("zero_touch_threshold_recalculation_failed", **safe_error_log(e))
        raise self.retry(exc=e)


# =============================================================================
# Statistics Task
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.zero_touch_tasks.generate_zero_touch_statistics",
    bind=True,
    max_retries=2,
    default_retry_delay=180,
    queue="maintenance",
    soft_time_limit=60,
    time_limit=120,
)
def generate_zero_touch_statistics(
    self,
    days: int = 30,
) -> Dict[str, Any]:
    """Generiert Statistiken ueber Zero-Touch Verarbeitung.

    Wird regelmaessig fuer Reporting und Monitoring ausgefuehrt.

    Args:
        days: Anzahl der Tage fuer Statistik-Zeitraum

    Returns:
        Dict mit Zero-Touch Statistiken
    """
    record_task_started("zero_touch.generate_statistics")

    async def _generate_stats() -> Dict[str, Any]:
        async with get_async_session_context() as db:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

            # Grundstatistiken
            stats_query = select(
                func.count(ZeroTouchResult.id).label("total"),
                func.sum(
                    func.cast(ZeroTouchResult.auto_processed, int)
                ).label("auto_processed_count"),
                func.avg(ZeroTouchResult.overall_confidence).label("avg_confidence"),
                func.avg(ZeroTouchResult.entity_confidence).label("avg_entity_confidence"),
            ).where(
                ZeroTouchResult.created_at >= cutoff_date
            )

            result = await db.execute(stats_query)
            stats = result.one()

            total = stats.total or 0
            auto_processed = stats.auto_processed_count or 0
            auto_rate = (auto_processed / total * 100) if total > 0 else 0

            return {
                "period_days": days,
                "total_processed": total,
                "auto_processed": auto_processed,
                "auto_processing_rate": round(auto_rate, 2),
                "average_confidence": round(stats.avg_confidence or 0, 3),
                "average_entity_confidence": round(stats.avg_entity_confidence or 0, 3),
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }

    try:
        result = asyncio.run(_generate_stats())
        record_task_succeeded("zero_touch.generate_statistics")
        logger.info(
            "zero_touch_statistics_generated",
            total=result["total_processed"],
            auto_rate=result["auto_processing_rate"],
        )
        return result
    except Exception as e:
        record_task_failed("zero_touch.generate_statistics", str(e))
        logger.error("zero_touch_statistics_failed", **safe_error_log(e))
        raise self.retry(exc=e)

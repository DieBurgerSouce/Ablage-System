# -*- coding: utf-8 -*-
"""
Active Learning Celery Tasks.

Phase 2.4: Hintergrund-Tasks fuer die Active Learning Pipeline:
- Queue-Befuellung (taeglich)
- Impact-Metriken-Berechnung (woechentlich)
- Training aus akkumulierten Korrekturen

Feinpoliert und durchdacht - Automatisierte Active Learning Orchestrierung.
"""

import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional

import structlog

from app.workers.celery_app import celery_app, CPUTask
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


# ==================== Queue Population ====================


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.active_learning_tasks.populate_active_learning_queue",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3},
    retry_backoff=True,
    retry_backoff_max=300,
    soft_time_limit=600,  # 10 Minuten
    time_limit=720,  # 12 Minuten
    acks_late=True,
    reject_on_worker_lost=True,
)
def populate_active_learning_queue(
    self,
    company_id: Optional[str] = None,
    limit: int = 50,
) -> Dict[str, int]:
    """
    Befuellt die Active-Learning-Queue mit neuen Kandidaten.

    Wird taeglich via Celery Beat ausgefuehrt. Identifiziert Dokumente
    mit niedrigem OCR-Confidence und priorisiert sie fuer Review.

    Args:
        company_id: Optionale Company-ID (None = alle Companies).
        limit: Maximale Anzahl neuer Queue-Eintraege pro Company.

    Returns:
        Zusammenfassung der befuellten Queues.
    """
    task_id = self.request.id

    logger.info(
        "populate_al_queue_starting",
        task_id=task_id,
        company_id=company_id,
        limit=limit,
    )

    try:
        from app.services.active_learning.active_learning_service import (
            ActiveLearningService,
        )
        # Worker-Kontext (RLS-Bypass, F-16-Muster): der kontextlose Weg sah
        # nach Migration 273 z.B. 0 companies -> Task tat still nichts.
        from app.db.session import get_worker_session_context
        from app.db.models import Company
        from sqlalchemy import select
        from uuid import UUID

        async def populate() -> Dict[str, int]:
            async with get_worker_session_context() as session:
                total_added = 0
                companies_processed = 0

                if company_id:
                    # Einzelne Company
                    service = ActiveLearningService(session)
                    added = await service.populate_queue(
                        company_id=UUID(company_id),
                        limit=limit,
                    )
                    total_added += added
                    companies_processed = 1
                else:
                    # Alle Companies durchgehen
                    result = await session.execute(select(Company.id))
                    company_ids = [row[0] for row in result.all()]

                    for cid in company_ids:
                        try:
                            service = ActiveLearningService(session)
                            added = await service.populate_queue(
                                company_id=cid,
                                limit=limit,
                            )
                            total_added += added
                            companies_processed += 1
                        except Exception as e:
                            logger.warning(
                                "populate_al_queue_company_failed",
                                company_id=str(cid),
                                **safe_error_log(e),
                            )

                await session.commit()

                return {
                    "total_added": total_added,
                    "companies_processed": companies_processed,
                }

        # asyncio.run() fuer sauberes Event-Loop Cleanup
        result = asyncio.run(populate())

        logger.info(
            "populate_al_queue_completed",
            task_id=task_id,
            total_added=result["total_added"],
            companies=result["companies_processed"],
        )

        return result

    except Exception as e:
        logger.exception(
            "populate_al_queue_failed",
            task_id=task_id,
            **safe_error_log(e),
        )
        raise


# ==================== Metrics Calculation ====================


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.active_learning_tasks.calculate_learning_metrics",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3},
    retry_backoff=True,
    retry_backoff_max=300,
    soft_time_limit=600,  # 10 Minuten
    time_limit=720,  # 12 Minuten
    acks_late=True,
    reject_on_worker_lost=True,
)
def calculate_learning_metrics(
    self,
    company_id: Optional[str] = None,
) -> Dict[str, float]:
    """
    Berechnet Impact-Metriken fuer Active Learning.

    Wird woechentlich via Celery Beat ausgefuehrt. Aggregiert:
    - Anzahl gepruefter Dokumente
    - Tatsaechliche Korrekturen
    - Geschaetzte verhinderte Fehler
    - Confidence-Verbesserung vor/nach Training

    Args:
        company_id: Optionale Company-ID (None = alle Companies).

    Returns:
        Aggregierte Impact-Metriken.
    """
    task_id = self.request.id

    logger.info(
        "calculate_al_metrics_starting",
        task_id=task_id,
        company_id=company_id,
    )

    try:
        from app.services.active_learning.active_learning_service import (
            ActiveLearningService,
        )
        # Worker-Kontext (RLS-Bypass, F-16-Muster): der kontextlose Weg sah
        # nach Migration 273 z.B. 0 companies -> Task tat still nichts.
        from app.db.session import get_worker_session_context
        from app.db.models import Company
        from sqlalchemy import select
        from uuid import UUID

        async def calculate() -> Dict[str, float]:
            async with get_worker_session_context() as session:
                total_reviewed = 0.0
                total_corrections = 0.0
                total_prevented = 0.0
                companies_processed = 0

                if company_id:
                    company_ids_list = [UUID(company_id)]
                else:
                    result = await session.execute(select(Company.id))
                    company_ids_list = [row[0] for row in result.all()]

                for cid in company_ids_list:
                    try:
                        service = ActiveLearningService(session)
                        metrics = await service.calculate_impact_metrics(
                            company_id=cid,
                        )
                        total_reviewed += metrics["total_reviewed_30d"]
                        total_corrections += metrics["total_corrections_30d"]
                        total_prevented += metrics["estimated_errors_prevented"]
                        companies_processed += 1
                    except Exception as e:
                        logger.warning(
                            "calculate_al_metrics_company_failed",
                            company_id=str(cid),
                            **safe_error_log(e),
                        )

                await session.commit()

                return {
                    "total_reviewed": total_reviewed,
                    "total_corrections": total_corrections,
                    "estimated_errors_prevented": total_prevented,
                    "companies_processed": float(companies_processed),
                }

        # asyncio.run() fuer sauberes Event-Loop Cleanup
        result = asyncio.run(calculate())

        logger.info(
            "calculate_al_metrics_completed",
            task_id=task_id,
            total_reviewed=result["total_reviewed"],
            total_corrections=result["total_corrections"],
            prevented=result["estimated_errors_prevented"],
        )

        return result

    except Exception as e:
        logger.exception(
            "calculate_al_metrics_failed",
            task_id=task_id,
            **safe_error_log(e),
        )
        raise


# ==================== Training from Corrections ====================


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.active_learning_tasks.train_from_corrections",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 2},
    retry_backoff=True,
    retry_backoff_max=600,
    soft_time_limit=1800,  # 30 Minuten
    time_limit=2100,  # 35 Minuten
    acks_late=True,
    reject_on_worker_lost=True,
)
def train_from_corrections(
    self,
    company_id: Optional[str] = None,
    min_corrections: int = 10,
) -> Dict[str, int]:
    """
    Triggert die Training-Pipeline aus akkumulierten Korrekturen.

    Sammelt reviewed Items mit Korrekturdaten und leitet sie an
    die Self-Learning Pipeline weiter. Markiert konsumierte Items
    mit der Training-Batch-ID.

    Args:
        company_id: Optionale Company-ID (None = alle Companies).
        min_corrections: Mindestanzahl Korrekturen fuer Training-Trigger.

    Returns:
        Training-Zusammenfassung.
    """
    task_id = self.request.id

    logger.info(
        "train_from_corrections_starting",
        task_id=task_id,
        company_id=company_id,
        min_corrections=min_corrections,
    )

    try:
        # Worker-Kontext (RLS-Bypass, F-16-Muster): der kontextlose Weg sah
        # nach Migration 273 z.B. 0 companies -> Task tat still nichts.
        from app.db.session import get_worker_session_context
        from app.db.models_active_learning import ActiveLearningQueue
        from sqlalchemy import select, and_, update, func
        from uuid import UUID, uuid4

        async def process_corrections() -> Dict[str, int]:
            async with get_worker_session_context() as session:
                # Finde reviewed Items ohne Training-Batch
                query = (
                    select(ActiveLearningQueue)
                    .where(
                        and_(
                            ActiveLearningQueue.status == "reviewed",
                            ActiveLearningQueue.correction_data.isnot(None),
                            ActiveLearningQueue.training_batch_id.is_(None),
                        )
                    )
                    .order_by(ActiveLearningQueue.reviewed_at.asc())
                )

                if company_id:
                    query = query.where(
                        ActiveLearningQueue.company_id == UUID(company_id)
                    )

                result = await session.execute(query)
                items = list(result.scalars().all())

                if len(items) < min_corrections:
                    logger.info(
                        "train_from_corrections_insufficient",
                        task_id=task_id,
                        available=len(items),
                        required=min_corrections,
                    )
                    return {
                        "status_code": 0,
                        "corrections_available": len(items),
                        "corrections_consumed": 0,
                        "message_key": "insufficient_corrections",
                    }

                # Erstelle Training-Batch-ID
                batch_id = uuid4()
                item_ids = [item.id for item in items]

                # Markiere Items als konsumiert
                await session.execute(
                    update(ActiveLearningQueue)
                    .where(ActiveLearningQueue.id.in_(item_ids))
                    .values(training_batch_id=batch_id)
                )

                await session.commit()

                # Sammle Korrekturdaten fuer Feedback-Pipeline
                corrections_data: List[Dict[str, str]] = []
                for item in items:
                    if item.correction_data:
                        corrections_data.append({
                            "document_id": str(item.document_id),
                            "corrections": item.correction_data,
                            "ocr_backend": item.ocr_backend or "unknown",
                            "ocr_confidence": str(item.ocr_confidence or 0.0),
                        })

                # Trigger Feedback-Learning Pipeline
                try:
                    from app.workers.tasks.training_tasks import (
                        process_feedback_queue,
                    )
                    process_feedback_queue.apply_async(
                        kwargs={"batch_size": len(corrections_data)},
                        countdown=10,  # 10s Verzoegerung fuer DB-Konsistenz
                    )
                except ImportError:
                    logger.warning(
                        "feedback_pipeline_not_available",
                        task_id=task_id,
                    )

                return {
                    "status_code": 1,
                    "corrections_available": len(items),
                    "corrections_consumed": len(corrections_data),
                    "training_batch_id": str(batch_id),
                }

        # asyncio.run() fuer sauberes Event-Loop Cleanup
        result = asyncio.run(process_corrections())

        logger.info(
            "train_from_corrections_completed",
            task_id=task_id,
            consumed=result.get("corrections_consumed", 0),
            batch_id=result.get("training_batch_id"),
        )

        return result

    except Exception as e:
        logger.exception(
            "train_from_corrections_failed",
            task_id=task_id,
            **safe_error_log(e),
        )
        raise

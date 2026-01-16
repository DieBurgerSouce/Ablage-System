"""
Risk Scoring Celery Tasks.

Automatische Berechnung von Entity Risk Scores:
- Batch-Berechnung aller Entitaeten (taeglich um 02:00)
- Einzelberechnung nach Invoice-Updates
- Neuberechnung bei Zahlungseingang
- Statistik-Generierung

Feinpoliert und durchdacht - Enterprise Risk Scoring.
"""

import asyncio
import structlog
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy import select, and_, or_, func

from app.workers.celery_app import celery_app
from app.db.session import get_async_session_context
from app.db.models import BusinessEntity, Document

logger = structlog.get_logger(__name__)


# =============================================================================
# Batch Risk Score Calculation Tasks
# =============================================================================


@celery_app.task(
    name="risk_scoring.calculate_all",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
    queue="maintenance",
)
def calculate_all_risk_scores_task(
    self,
    entity_type: Optional[str] = None,
    limit: int = 1000,
    recalculate_all: bool = False,
) -> Dict[str, Any]:
    """Berechnet Risk Scores fuer alle Entitaeten.

    Wird taeglich um 02:00 Uhr automatisch ausgefuehrt.
    Berechnet nur Entitaeten, deren Score veraltet ist (>24h).

    Args:
        entity_type: Nur bestimmten Typ berechnen ("customer", "supplier", "both")
        limit: Maximale Anzahl zu verarbeitender Entitaeten
        recalculate_all: Alle neu berechnen, nicht nur veraltete

    Returns:
        Dict mit Verarbeitungsstatistiken
    """
    from app.services.risk_scoring_service import get_risk_scoring_service

    async def _calculate_all() -> Dict[str, Any]:
        async with get_async_session_context() as db:
            service = get_risk_scoring_service()

            # Entitaeten laden
            query = select(BusinessEntity).where(
                and_(
                    BusinessEntity.is_active == True,
                    BusinessEntity.deleted_at.is_(None),
                )
            )

            # Entity-Type Filter
            if entity_type:
                query = query.where(BusinessEntity.entity_type == entity_type)

            # Nur veraltete Scores berechnen (außer recalculate_all)
            if not recalculate_all:
                cutoff_time = datetime.now(timezone.utc) - timedelta(hours=24)
                query = query.where(
                    or_(
                        BusinessEntity.risk_calculated_at.is_(None),
                        BusinessEntity.risk_calculated_at < cutoff_time,
                    )
                )

            query = query.limit(limit)
            result = await db.execute(query)
            entities = result.scalars().all()

            # Statistiken
            stats = {
                "total_processed": 0,
                "successful": 0,
                "failed": 0,
                "skipped": 0,
                "errors": [],
            }

            start_time = datetime.now(timezone.utc)

            for entity in entities:
                stats["total_processed"] += 1
                try:
                    # Service nutzt db als ersten Parameter der Methode
                    updated_entity = await service.update_entity_risk_score(db, entity.id)
                    if updated_entity:
                        stats["successful"] += 1
                        logger.debug(
                            "risk_score_calculated",
                            entity_id=str(entity.id),
                            # SECURITY: Kein entity_name loggen (PII)
                            risk_score=updated_entity.risk_score,
                        )
                    else:
                        stats["skipped"] += 1
                except Exception as e:
                    stats["failed"] += 1
                    # SECURITY: Kein entity_name in Fehler-Response (PII)
                    stats["errors"].append({
                        "entity_id": str(entity.id),
                        "error": str(e),
                    })
                    logger.warning(
                        "risk_score_calculation_failed",
                        entity_id=str(entity.id),
                        error=str(e),
                    )

            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
            stats["processing_time_ms"] = int(elapsed * 1000)

            return stats

    try:
        result = asyncio.run(_calculate_all())
        logger.info(
            "risk_score_batch_completed",
            total=result["total_processed"],
            successful=result["successful"],
            failed=result["failed"],
            skipped=result["skipped"],
            processing_time_ms=result["processing_time_ms"],
        )
        return result
    except Exception as e:
        logger.error("risk_score_batch_failed", error=str(e))
        raise self.retry(exc=e)


# =============================================================================
# Single Entity Risk Score Calculation
# =============================================================================


@celery_app.task(
    name="risk_scoring.calculate_single",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    queue="metadata",
)
def calculate_single_risk_score_task(
    self,
    entity_id: str,
) -> Dict[str, Any]:
    """Berechnet Risk Score fuer eine einzelne Entitaet.

    Wird getriggert nach:
    - Invoice-Status-Updates
    - Zahlungseingaengen
    - Mahnungs-Versendungen

    Args:
        entity_id: UUID der Entitaet als String

    Returns:
        Dict mit Risk Score Details
    """
    from app.services.risk_scoring_service import get_risk_scoring_service

    async def _calculate_single() -> Dict[str, Any]:
        async with get_async_session_context() as db:
            service = get_risk_scoring_service()
            try:
                entity_uuid = UUID(entity_id)
            except ValueError:
                # Ungueltige UUID - nicht retryable
                return {
                    "entity_id": entity_id,
                    "success": False,
                    "error": "Ungueltige Entity-ID (kein gueltiges UUID-Format)",
                }

            # Service gibt aktualisierte Entity zurueck
            updated_entity = await service.update_entity_risk_score(db, entity_uuid)

            if not updated_entity:
                return {
                    "entity_id": entity_id,
                    "success": False,
                    "error": "Entitaet nicht gefunden oder keine Daten",
                }

            # SECURITY: Kein entity_name zurueckgeben (PII)
            return {
                "entity_id": entity_id,
                "success": True,
                "risk_score": updated_entity.risk_score,
                "payment_behavior_score": updated_entity.payment_behavior_score,
                "risk_factors": updated_entity.risk_factors,
                "calculated_at": datetime.now(timezone.utc).isoformat(),
            }

    try:
        result = asyncio.run(_calculate_single())
        if result.get("success"):
            logger.info(
                "single_risk_score_calculated",
                entity_id=entity_id,
                risk_score=result.get("risk_score"),
            )
        return result
    except Exception as e:
        logger.error(
            "single_risk_score_calculation_failed",
            entity_id=entity_id,
            error=str(e),
        )
        raise self.retry(exc=e)


# =============================================================================
# Invoice-Triggered Risk Recalculation
# =============================================================================


@celery_app.task(
    name="risk_scoring.on_invoice_updated",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    queue="metadata",
)
def on_invoice_updated_recalculate(
    self,
    document_id: str,
) -> Dict[str, Any]:
    """Berechnet Risk Score neu nach Invoice-Update.

    Wird automatisch getriggert wenn:
    - Rechnung als bezahlt markiert wird
    - Mahnstufe erhoeht wird
    - Faelligkeitsdatum ueberschritten wird

    Args:
        document_id: UUID des Dokuments (verknuepft mit Invoice)

    Returns:
        Dict mit Neuberechnungs-Ergebnis
    """
    async def _recalculate_for_document() -> Dict[str, Any]:
        async with get_async_session_context() as db:
            # UUID validieren - nicht retryable bei ungueltigem Format
            try:
                doc_uuid = UUID(document_id)
            except ValueError:
                return {
                    "document_id": document_id,
                    "success": False,
                    "error": "Ungueltige Document-ID (kein gueltiges UUID-Format)",
                }

            # Finde das Dokument und seine Entitaet
            doc_query = select(Document).where(Document.id == doc_uuid)
            doc_result = await db.execute(doc_query)
            document = doc_result.scalar_one_or_none()

            if not document:
                return {
                    "document_id": document_id,
                    "success": False,
                    "error": "Dokument nicht gefunden",
                }

            if not document.business_entity_id:
                return {
                    "document_id": document_id,
                    "success": False,
                    "error": "Dokument nicht mit Entitaet verknuepft",
                }

            # Trigger Neuberechnung
            entity_id = str(document.business_entity_id)
            calculate_single_risk_score_task.delay(entity_id)

            return {
                "document_id": document_id,
                "entity_id": entity_id,
                "success": True,
                "action": "risk_recalculation_triggered",
            }

    try:
        result = asyncio.run(_recalculate_for_document())
        if result.get("success"):
            logger.info(
                "invoice_update_triggered_risk_recalculation",
                document_id=document_id,
                entity_id=result.get("entity_id"),
            )
        return result
    except Exception as e:
        logger.error(
            "invoice_update_risk_recalculation_failed",
            document_id=document_id,
            error=str(e),
        )
        raise self.retry(exc=e)


# =============================================================================
# Risk Threshold Alert Task
# =============================================================================


@celery_app.task(
    name="risk_scoring.check_high_risk_entities",
    bind=True,
    max_retries=2,
    default_retry_delay=120,
    queue="maintenance",
)
def check_high_risk_entities_task(
    self,
    threshold: float = 75.0,
) -> Dict[str, Any]:
    """Prueft auf Entitaeten mit hohem Risiko.

    Wird nach Batch-Berechnung ausgefuehrt.
    Kann Benachrichtigungen triggern (zukuenftige Erweiterung).

    Args:
        threshold: Risk Score Schwellwert (Standard: 75)

    Returns:
        Dict mit High-Risk Entitaeten (ohne PII)
    """
    async def _check_high_risk() -> Dict[str, Any]:
        async with get_async_session_context() as db:
            query = select(BusinessEntity).where(
                and_(
                    BusinessEntity.is_active == True,
                    BusinessEntity.deleted_at.is_(None),
                    BusinessEntity.risk_score.isnot(None),
                    BusinessEntity.risk_score >= threshold,
                )
            ).order_by(BusinessEntity.risk_score.desc()).limit(100)

            result = await db.execute(query)
            high_risk_entities = result.scalars().all()

            # SECURITY: Kein entity_name zurueckgeben (PII)
            entities_list = [
                {
                    "entity_id": str(e.id),
                    "entity_type": e.entity_type,
                    "risk_score": e.risk_score,
                    "payment_behavior_score": e.payment_behavior_score,
                }
                for e in high_risk_entities
            ]

            return {
                "threshold": threshold,
                "count": len(entities_list),
                "high_risk_entities": entities_list,
            }

    try:
        result = asyncio.run(_check_high_risk())
        if result["count"] > 0:
            logger.warning(
                "high_risk_entities_detected",
                threshold=threshold,
                count=result["count"],
            )
        return result
    except Exception as e:
        logger.error("high_risk_check_failed", error=str(e))
        raise self.retry(exc=e)


# =============================================================================
# Statistics Task
# =============================================================================


@celery_app.task(
    name="risk_scoring.generate_statistics",
    bind=True,
    max_retries=2,
    default_retry_delay=180,
    queue="maintenance",
)
def generate_risk_statistics_task(self) -> Dict[str, Any]:
    """Generiert Statistiken ueber Risk Scores.

    Wird woechentlich ausgefuehrt fuer Reporting.

    Returns:
        Dict mit Risk Score Statistiken
    """
    async def _generate_stats() -> Dict[str, Any]:
        async with get_async_session_context() as db:
            # Grundstatistiken
            base_query = select(
                func.count(BusinessEntity.id).label("total"),
                func.avg(BusinessEntity.risk_score).label("avg_risk"),
                func.max(BusinessEntity.risk_score).label("max_risk"),
                func.min(BusinessEntity.risk_score).label("min_risk"),
                func.avg(BusinessEntity.payment_behavior_score).label("avg_payment"),
            ).where(
                and_(
                    BusinessEntity.is_active == True,
                    BusinessEntity.deleted_at.is_(None),
                    BusinessEntity.risk_score.isnot(None),
                )
            )

            result = await db.execute(base_query)
            stats = result.one()

            # Risiko-Verteilung
            risk_distribution = {
                "low": 0,      # 0-25
                "medium": 0,   # 26-50
                "high": 0,     # 51-75
                "critical": 0, # 76-100
            }

            dist_query = select(BusinessEntity.risk_score).where(
                and_(
                    BusinessEntity.is_active == True,
                    BusinessEntity.deleted_at.is_(None),
                    BusinessEntity.risk_score.isnot(None),
                )
            )
            dist_result = await db.execute(dist_query)
            for (score,) in dist_result:
                if score <= 25:
                    risk_distribution["low"] += 1
                elif score <= 50:
                    risk_distribution["medium"] += 1
                elif score <= 75:
                    risk_distribution["high"] += 1
                else:
                    risk_distribution["critical"] += 1

            return {
                "total_entities_with_score": stats.total or 0,
                "average_risk_score": round(stats.avg_risk or 0, 2),
                "max_risk_score": round(stats.max_risk or 0, 2),
                "min_risk_score": round(stats.min_risk or 0, 2),
                "average_payment_behavior": round(stats.avg_payment or 0, 2),
                "risk_distribution": risk_distribution,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }

    try:
        result = asyncio.run(_generate_stats())
        logger.info(
            "risk_statistics_generated",
            total_entities=result["total_entities_with_score"],
            avg_risk=result["average_risk_score"],
        )
        return result
    except Exception as e:
        logger.error("risk_statistics_generation_failed", error=str(e))
        raise self.retry(exc=e)

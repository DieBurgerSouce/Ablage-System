"""
Risk Scoring Celery Tasks v2.0.

Automatische Berechnung von Entity Risk Scores mit erweiterten Funktionen:
- Batch-Berechnung aller Entitaeten (täglich um 02:00)
- Einzelberechnung nach Invoice-Updates
- Neuberechnung bei Zahlungseingang
- Statistik-Generierung
- NEU: Trend-Analyse und History-Speicherung (V2)
- NEU: Industry-basierte Risikobewertung (V2)

Feinpoliert und durchdacht - Enterprise Risk Scoring.
"""

import asyncio
import structlog
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select, and_, or_, func

from app.workers.celery_app import celery_app
from app.db.session import get_async_session_context
from app.db.models import BusinessEntity, Document, Company
from app.core.safe_errors import safe_error_log, safe_error_detail

logger = structlog.get_logger(__name__)


# =============================================================================
# Batch Risk Score Calculation Tasks
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.risk_scoring_tasks.calculate_all_risk_scores_task",
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
    """Berechnet Risk Scores für alle Entitaeten.

    Wird täglich um 02:00 Uhr automatisch ausgeführt.
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
                "version": service.version,
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
                        "error": safe_error_detail(e, "Vorgang"),
                    })
                    logger.warning(
                        "risk_score_calculation_failed",
                        entity_id=str(entity.id),
                        **safe_error_log(e),
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
            version=result["version"],
        )
        return result
    except Exception as e:
        logger.error("risk_score_batch_failed", **safe_error_log(e))
        raise self.retry(exc=e)


@celery_app.task(
    name="app.workers.tasks.risk_scoring_tasks.calculate_all_risk_scores_v2_task",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
    queue="maintenance",
)
def calculate_all_risk_scores_v2_task(
    self,
    entity_type: Optional[str] = None,
    limit: int = 1000,
    recalculate_all: bool = False,
    save_history: bool = True,
) -> Dict[str, Any]:
    """Enhanced daily risk score calculation with trend analysis (V2).

    Erweiterungen gegenüber V1:
    - Branchenrisiko-Bewertung
    - Trend-Analyse (Verbesserung/Verschlechterung)
    - History-Speicherung für spätere Auswertung
    - Empfehlungsgenerierung

    Args:
        entity_type: Nur bestimmten Typ berechnen ("customer", "supplier", "both")
        limit: Maximale Anzahl zu verarbeitender Entitaeten
        recalculate_all: Alle neu berechnen, nicht nur veraltete
        save_history: History-Einträge speichern (Standard: True)

    Returns:
        Dict mit erweiterten Verarbeitungsstatistiken
    """
    from app.services.risk_scoring_service import (
        get_risk_scoring_service,
        TrendDirection,
    )

    async def _calculate_all_v2() -> Dict[str, Any]:
        async with get_async_session_context() as db:
            service = get_risk_scoring_service(use_v2=True)

            # Entitaeten mit Company-Zuordnung laden
            query = (
                select(BusinessEntity, Company.id.label("company_id"))
                .outerjoin(
                    Document,
                    and_(
                        Document.business_entity_id == BusinessEntity.id,
                        Document.deleted_at.is_(None),
                    )
                )
                .outerjoin(Company, Company.id == Document.company_id)
                .where(
                    and_(
                        BusinessEntity.is_active == True,
                        BusinessEntity.deleted_at.is_(None),
                    )
                )
                .group_by(BusinessEntity.id, Company.id)
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
            rows = result.fetchall()

            # Statistiken
            stats = {
                "total_processed": 0,
                "successful": 0,
                "failed": 0,
                "skipped": 0,
                "errors": [],
                "version": service.version,
                # V2-spezifische Statistiken
                "trend_stats": {
                    "improving": 0,
                    "stable": 0,
                    "worsening": 0,
                },
                "risk_distribution": {
                    "low": 0,
                    "medium": 0,
                    "high": 0,
                    "critical": 0,
                },
                "history_saved": 0,
            }

            start_time = datetime.now(timezone.utc)

            for row in rows:
                entity = row[0]
                company_id = row[1] if len(row) > 1 else None

                stats["total_processed"] += 1
                try:
                    # V2: Berechne detaillierten Score mit Trend
                    detailed_result = await service.calculate_risk_score_detailed(
                        db, entity.id
                    )

                    # Entity aktualisieren
                    updated_entity = await service.update_entity_risk_score(
                        db, entity.id
                    )

                    if updated_entity:
                        stats["successful"] += 1

                        # Trend-Statistik
                        trend_key = detailed_result.trend.value.lower()
                        if trend_key in stats["trend_stats"]:
                            stats["trend_stats"][trend_key] += 1

                        # Risk-Distribution
                        risk_key = detailed_result.risk_level.value.lower()
                        if risk_key in stats["risk_distribution"]:
                            stats["risk_distribution"][risk_key] += 1

                        # History speichern (wenn Company verfügbar und save_history=True)
                        if save_history and company_id:
                            try:
                                await service.save_risk_score_history(
                                    db,
                                    entity_id=entity.id,
                                    company_id=company_id,
                                    score=detailed_result.overall_score,
                                    factors=await service._collect_factors(db, entity.id),
                                    trigger_event="scheduled_v2",
                                )
                                stats["history_saved"] += 1
                            except Exception as hist_e:
                                logger.warning(
                                    "risk_score_history_save_failed",
                                    entity_id=str(entity.id),
                                    **safe_error_log(hist_e),
                                )

                        logger.debug(
                            "risk_score_calculated_v2",
                            entity_id=str(entity.id),
                            risk_score=detailed_result.overall_score,
                            trend=detailed_result.trend.value,
                            risk_level=detailed_result.risk_level.value,
                        )
                    else:
                        stats["skipped"] += 1

                except Exception as e:
                    stats["failed"] += 1
                    stats["errors"].append({
                        "entity_id": str(entity.id),
                        "error": safe_error_detail(e, "Vorgang"),
                    })
                    logger.warning(
                        "risk_score_calculation_v2_failed",
                        entity_id=str(entity.id),
                        **safe_error_log(e),
                    )

            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
            stats["processing_time_ms"] = int(elapsed * 1000)

            return stats

    try:
        result = asyncio.run(_calculate_all_v2())
        logger.info(
            "risk_score_batch_v2_completed",
            total=result["total_processed"],
            successful=result["successful"],
            failed=result["failed"],
            skipped=result["skipped"],
            processing_time_ms=result["processing_time_ms"],
            version=result["version"],
            trend_stats=result["trend_stats"],
            risk_distribution=result["risk_distribution"],
            history_saved=result["history_saved"],
        )
        return result
    except Exception as e:
        logger.error("risk_score_batch_v2_failed", **safe_error_log(e))
        raise self.retry(exc=e)


# =============================================================================
# Single Entity Risk Score Calculation
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.risk_scoring_tasks.calculate_single_risk_score_task",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    queue="metadata",
)
def calculate_single_risk_score_task(
    self,
    entity_id: str,
) -> Dict[str, Any]:
    """Berechnet Risk Score für eine einzelne Entitaet.

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
                # Ungültige UUID - nicht retryable
                return {
                    "entity_id": entity_id,
                    "success": False,
                    "error": "Ungültige Entity-ID (kein gültiges UUID-Format)",
                }

            # Service gibt aktualisierte Entity zurück
            updated_entity = await service.update_entity_risk_score(db, entity_uuid)

            if not updated_entity:
                return {
                    "entity_id": entity_id,
                    "success": False,
                    "error": "Entitaet nicht gefunden oder keine Daten",
                }

            # SECURITY: Kein entity_name zurückgeben (PII)
            return {
                "entity_id": entity_id,
                "success": True,
                "risk_score": updated_entity.risk_score,
                "payment_behavior_score": updated_entity.payment_behavior_score,
                "risk_factors": updated_entity.risk_factors,
                "calculated_at": datetime.now(timezone.utc).isoformat(),
                "version": service.version,
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
            **safe_error_log(e),
        )
        raise self.retry(exc=e)


@celery_app.task(
    name="app.workers.tasks.risk_scoring_tasks.calculate_single_risk_score_detailed_task",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    queue="metadata",
)
def calculate_single_risk_score_detailed_task(
    self,
    entity_id: str,
    save_history: bool = True,
    company_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Berechnet detaillierten Risk Score (V2) für eine einzelne Entitaet.

    Erweiterte Version mit:
    - Trend-Analyse
    - Branchenrisiko
    - Empfehlungen
    - Optional: History-Speicherung

    Args:
        entity_id: UUID der Entitaet als String
        save_history: History-Eintrag speichern (Standard: True)
        company_id: Company-ID für History (optional)

    Returns:
        Dict mit detaillierten Risk Score Informationen
    """
    from app.services.risk_scoring_service import get_risk_scoring_service

    async def _calculate_single_detailed() -> Dict[str, Any]:
        async with get_async_session_context() as db:
            service = get_risk_scoring_service(use_v2=True)
            try:
                entity_uuid = UUID(entity_id)
            except ValueError:
                return {
                    "entity_id": entity_id,
                    "success": False,
                    "error": "Ungültige Entity-ID (kein gültiges UUID-Format)",
                }

            # V2: Detaillierte Berechnung
            detailed_result = await service.calculate_risk_score_detailed(
                db, entity_uuid
            )

            # Entity aktualisieren
            updated_entity = await service.update_entity_risk_score(db, entity_uuid)

            if not updated_entity:
                return {
                    "entity_id": entity_id,
                    "success": False,
                    "error": "Entitaet nicht gefunden oder keine Daten",
                }

            # History speichern
            history_saved = False
            if save_history and company_id:
                try:
                    company_uuid = UUID(company_id)
                    factors = await service._collect_factors(db, entity_uuid)
                    await service.save_risk_score_history(
                        db,
                        entity_id=entity_uuid,
                        company_id=company_uuid,
                        score=detailed_result.overall_score,
                        factors=factors,
                        trigger_event="manual_detailed",
                    )
                    history_saved = True
                except Exception as hist_e:
                    logger.warning(
                        "risk_score_history_save_failed",
                        entity_id=entity_id,
                        **safe_error_log(hist_e),
                    )

            # Response mit allen V2-Details
            return {
                "entity_id": entity_id,
                "success": True,
                "overall_score": detailed_result.overall_score,
                "risk_level": detailed_result.risk_level.value,
                "trend": detailed_result.trend.value,
                "trend_score_adjustment": detailed_result.trend_score_adjustment,
                "payment_behavior_score": detailed_result.payment_behavior_score,
                "factors": {
                    name: {
                        "value": f.value,
                        "score": round(f.score, 1),
                        "weight": f.weight,
                        "weighted_score": round(f.weighted_score, 1),
                        "description": f.description,
                    }
                    for name, f in detailed_result.factors.items()
                },
                "recommendations": detailed_result.recommendations,
                "calculated_at": detailed_result.last_calculated.isoformat(),
                "version": detailed_result.version,
                "history_saved": history_saved,
            }

    try:
        result = asyncio.run(_calculate_single_detailed())
        if result.get("success"):
            logger.info(
                "single_risk_score_detailed_calculated",
                entity_id=entity_id,
                overall_score=result.get("overall_score"),
                risk_level=result.get("risk_level"),
                trend=result.get("trend"),
            )
        return result
    except Exception as e:
        logger.error(
            "single_risk_score_detailed_calculation_failed",
            entity_id=entity_id,
            **safe_error_log(e),
        )
        raise self.retry(exc=e)


# =============================================================================
# Invoice-Triggered Risk Recalculation
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.risk_scoring_tasks.on_invoice_updated_recalculate",
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
    - Mahnstufe erhöht wird
    - Fälligkeitsdatum überschritten wird

    Args:
        document_id: UUID des Dokuments (verknüpft mit Invoice)

    Returns:
        Dict mit Neuberechnungs-Ergebnis
    """
    async def _recalculate_for_document() -> Dict[str, Any]:
        async with get_async_session_context() as db:
            # UUID validieren - nicht retryable bei ungültigem Format
            try:
                doc_uuid = UUID(document_id)
            except ValueError:
                return {
                    "document_id": document_id,
                    "success": False,
                    "error": "Ungültige Document-ID (kein gültiges UUID-Format)",
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
                    "error": "Dokument nicht mit Entitaet verknüpft",
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
            **safe_error_log(e),
        )
        raise self.retry(exc=e)


# =============================================================================
# Risk Threshold Alert Task
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.risk_scoring_tasks.check_high_risk_entities_task",
    bind=True,
    max_retries=2,
    default_retry_delay=120,
    queue="maintenance",
)
def check_high_risk_entities_task(
    self,
    threshold: float = 75.0,
) -> Dict[str, Any]:
    """Prüft auf Entitaeten mit hohem Risiko.

    Wird nach Batch-Berechnung ausgeführt.
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

            # SECURITY: Kein entity_name zurückgeben (PII)
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
        logger.error("high_risk_check_failed", **safe_error_log(e))
        raise self.retry(exc=e)


@celery_app.task(
    name="app.workers.tasks.risk_scoring_tasks.check_worsening_trends_task",
    bind=True,
    max_retries=2,
    default_retry_delay=120,
    queue="maintenance",
)
def check_worsening_trends_task(
    self,
    days: int = 30,
    min_invoices: int = 3,
) -> Dict[str, Any]:
    """Prüft auf Entitaeten mit sich verschlechterndem Zahlungstrend.

    NEU in V2: Identifiziert frühzeitig potenzielle Zahlungsprobleme.

    Args:
        days: Beobachtungszeitraum in Tagen (Standard: 30)
        min_invoices: Mindestanzahl Rechnungen für Trend-Analyse

    Returns:
        Dict mit worsening trend entities
    """
    from app.services.risk_scoring_service import TrendDirection

    async def _check_worsening_trends() -> Dict[str, Any]:
        async with get_async_session_context() as db:
            # Entitaeten mit risk_factors laden
            query = select(BusinessEntity).where(
                and_(
                    BusinessEntity.is_active == True,
                    BusinessEntity.deleted_at.is_(None),
                    BusinessEntity.risk_factors.isnot(None),
                )
            ).limit(1000)

            result = await db.execute(query)
            entities = result.scalars().all()

            worsening_entities = []

            for entity in entities:
                if entity.risk_factors and isinstance(entity.risk_factors, dict):
                    trend = entity.risk_factors.get("payment_trend")
                    if trend == TrendDirection.WORSENING.value:
                        worsening_entities.append({
                            "entity_id": str(entity.id),
                            "entity_type": entity.entity_type,
                            "risk_score": entity.risk_score,
                            "trend_slope": entity.risk_factors.get("trend_slope", 0),
                            "trend_adjustment": entity.risk_factors.get("trend_adjustment", 0),
                        })

            # Sortiere nach Trend-Steigung (schlimmste zuerst)
            worsening_entities.sort(
                key=lambda x: x.get("trend_slope", 0),
                reverse=True
            )

            return {
                "observation_days": days,
                "min_invoices": min_invoices,
                "count": len(worsening_entities),
                "worsening_entities": worsening_entities[:50],  # Top 50
            }

    try:
        result = asyncio.run(_check_worsening_trends())
        if result["count"] > 0:
            logger.warning(
                "worsening_payment_trends_detected",
                count=result["count"],
                observation_days=days,
            )
        return result
    except Exception as e:
        logger.error("worsening_trends_check_failed", **safe_error_log(e))
        raise self.retry(exc=e)


# =============================================================================
# Statistics Task
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.risk_scoring_tasks.generate_risk_statistics_task",
    bind=True,
    max_retries=2,
    default_retry_delay=180,
    queue="maintenance",
)
def generate_risk_statistics_task(self) -> Dict[str, Any]:
    """Generiert Statistiken über Risk Scores.

    Wird wöchentlich ausgeführt für Reporting.

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

            # V2: Trend-Verteilung
            trend_distribution = {
                "improving": 0,
                "stable": 0,
                "worsening": 0,
            }

            trend_query = select(BusinessEntity.risk_factors).where(
                and_(
                    BusinessEntity.is_active == True,
                    BusinessEntity.deleted_at.is_(None),
                    BusinessEntity.risk_factors.isnot(None),
                )
            )
            trend_result = await db.execute(trend_query)
            for (factors,) in trend_result:
                if factors and isinstance(factors, dict):
                    trend = factors.get("payment_trend", "STABLE")
                    trend_key = trend.lower() if trend else "stable"
                    if trend_key in trend_distribution:
                        trend_distribution[trend_key] += 1

            return {
                "total_entities_with_score": stats.total or 0,
                "average_risk_score": round(stats.avg_risk or 0, 2),
                "max_risk_score": round(stats.max_risk or 0, 2),
                "min_risk_score": round(stats.min_risk or 0, 2),
                "average_payment_behavior": round(stats.avg_payment or 0, 2),
                "risk_distribution": risk_distribution,
                "trend_distribution": trend_distribution,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "version": "2.0",
            }

    try:
        result = asyncio.run(_generate_stats())
        logger.info(
            "risk_statistics_generated",
            total_entities=result["total_entities_with_score"],
            avg_risk=result["average_risk_score"],
            trend_distribution=result["trend_distribution"],
        )
        return result
    except Exception as e:
        logger.error("risk_statistics_generation_failed", **safe_error_log(e))
        raise self.retry(exc=e)


# =============================================================================
# Industry Risk Update Task
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.risk_scoring_tasks.update_industry_codes_task",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
    queue="maintenance",
)
def update_industry_codes_task(
    self,
    industry_mappings: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Aktualisiert Branchencodes für Entitaeten.

    Kann verwendet werden um:
    - Branchencodes aus Lexware-Import zu übernehmen
    - Manuelle Branchenzuordnungen durchzuführen

    Args:
        industry_mappings: Dict von entity_id -> industry_code
                          z.B. {"uuid1": "manufacturing", "uuid2": "retail"}

    Returns:
        Dict mit Update-Statistiken
    """
    from app.services.risk_scoring_service import INDUSTRY_RISK_SCORES

    if not industry_mappings:
        return {
            "success": True,
            "updated": 0,
            "message": "Keine Mappings übergeben",
        }

    async def _update_codes() -> Dict[str, Any]:
        async with get_async_session_context() as db:
            updated_count = 0
            errors = []

            for entity_id_str, industry_code in industry_mappings.items():
                try:
                    entity_uuid = UUID(entity_id_str)

                    # Branchencode validieren
                    if industry_code not in INDUSTRY_RISK_SCORES:
                        errors.append({
                            "entity_id": entity_id_str,
                            "error": f"Unbekannter Branchencode: {industry_code}",
                        })
                        continue

                    # Entity laden
                    result = await db.execute(
                        select(BusinessEntity).where(BusinessEntity.id == entity_uuid)
                    )
                    entity = result.scalar_one_or_none()

                    if not entity:
                        errors.append({
                            "entity_id": entity_id_str,
                            "error": "Entitaet nicht gefunden",
                        })
                        continue

                    # Branchencode in risk_factors speichern
                    current_factors = entity.risk_factors or {}
                    current_factors["industry_code"] = industry_code
                    entity.risk_factors = current_factors

                    await db.commit()
                    updated_count += 1

                except Exception as e:
                    errors.append({
                        "entity_id": entity_id_str,
                        "error": safe_error_detail(e, "Update"),
                    })

            return {
                "success": True,
                "updated": updated_count,
                "total_requested": len(industry_mappings),
                "errors": errors,
            }

    try:
        result = asyncio.run(_update_codes())
        logger.info(
            "industry_codes_updated",
            updated=result["updated"],
            total_requested=result["total_requested"],
        )
        return result
    except Exception as e:
        logger.error("industry_codes_update_failed", **safe_error_log(e))
        raise self.retry(exc=e)

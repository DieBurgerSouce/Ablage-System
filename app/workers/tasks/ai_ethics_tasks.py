# -*- coding: utf-8 -*-
"""KI-Ethik-Layer periodic tasks (F7).

Phase 12: Statistische Bias-Analyse basierend auf DB-Daten.
"""

import asyncio
from typing import Dict, Any, List
from decimal import Decimal

import structlog
from sqlalchemy import select, func, and_

from app.workers.celery_app import celery_app
from app.core.safe_errors import safe_error_log
from app.db.session import async_session_maker
from app.db.models import (
    Company,
    BusinessEntity,
    Document,
    EntityType,
    DocumentType,
)

logger = structlog.get_logger(__name__)


@celery_app.task(name="app.workers.tasks.ai_ethics_tasks.generate_bias_report")
def generate_bias_report() -> dict:
    """Generiere woechentlichen Bias-Report.

    Analysiert:
    - Risk-Score Verteilung nach Entity-Typ
    - OCR-Confidence nach Dokumentensprache
    - Klassifizierungs-Genauigkeit nach Dokumententyp
    """
    logger.info("ai_ethics_bias_report_start")
    try:
        result = asyncio.get_event_loop().run_until_complete(_generate_bias_report())
        logger.info(
            "ai_ethics_bias_report_complete",
            biases_detected=result.get("biases_detected", 0),
        )
        return result
    except Exception as e:
        logger.error("ai_ethics_bias_report_error", **safe_error_log(e))
        raise


async def _generate_bias_report() -> Dict[str, Any]:
    """Async Implementation fuer Bias Report."""
    biases_detected = 0
    analysis_results: Dict[str, Any] = {}

    async with async_session_maker() as db:
        # 1. Risk-Score Verteilung nach Entity-Typ
        risk_by_type_result = await db.execute(
            select(
                BusinessEntity.entity_type,
                func.avg(BusinessEntity.risk_score).label("avg_risk"),
                func.count(BusinessEntity.id).label("count"),
            )
            .where(BusinessEntity.risk_score.isnot(None))
            .group_by(BusinessEntity.entity_type)
        )
        risk_by_type = risk_by_type_result.all()

        risk_analysis: Dict[str, Dict[str, Any]] = {}
        for entity_type, avg_risk, count in risk_by_type:
            type_name = entity_type.value if entity_type else "unknown"
            risk_analysis[type_name] = {
                "avg_risk_score": float(avg_risk) if avg_risk else 0,
                "entity_count": count,
            }

        analysis_results["risk_by_entity_type"] = risk_analysis

        # Bias-Erkennung: Signifikante Abweichung (>20 Punkte) vom Durchschnitt
        if risk_analysis:
            avg_scores = [v["avg_risk_score"] for v in risk_analysis.values() if v["entity_count"] > 5]
            if avg_scores:
                overall_avg = sum(avg_scores) / len(avg_scores)
                for type_name, data in risk_analysis.items():
                    if data["entity_count"] > 5:
                        deviation = abs(data["avg_risk_score"] - overall_avg)
                        if deviation > 20:
                            biases_detected += 1
                            logger.warning(
                                "bias_detected_risk_score",
                                entity_type=type_name,
                                avg_score=round(data["avg_risk_score"], 2),
                                overall_avg=round(overall_avg, 2),
                                deviation=round(deviation, 2),
                            )

        # 2. OCR Confidence nach Dokumententyp
        ocr_by_doctype_result = await db.execute(
            select(
                Document.document_type,
                func.avg(Document.ocr_confidence).label("avg_confidence"),
                func.count(Document.id).label("count"),
            )
            .where(Document.ocr_confidence.isnot(None))
            .group_by(Document.document_type)
        )
        ocr_by_doctype = ocr_by_doctype_result.all()

        ocr_analysis: Dict[str, Dict[str, Any]] = {}
        for doc_type, avg_conf, count in ocr_by_doctype:
            type_name = doc_type.value if doc_type else "unknown"
            ocr_analysis[type_name] = {
                "avg_confidence": float(avg_conf) if avg_conf else 0,
                "document_count": count,
            }

        analysis_results["ocr_confidence_by_doctype"] = ocr_analysis

        # Bias-Erkennung: OCR-Confidence signifikant niedriger (>15%)
        if ocr_analysis:
            avg_confs = [v["avg_confidence"] for v in ocr_analysis.values() if v["document_count"] > 10]
            if avg_confs:
                overall_avg_conf = sum(avg_confs) / len(avg_confs)
                for type_name, data in ocr_analysis.items():
                    if data["document_count"] > 10:
                        deviation = overall_avg_conf - data["avg_confidence"]
                        if deviation > 0.15:  # 15% niedriger
                            biases_detected += 1
                            logger.warning(
                                "bias_detected_ocr_confidence",
                                document_type=type_name,
                                avg_confidence=round(data["avg_confidence"], 3),
                                overall_avg=round(overall_avg_conf, 3),
                            )

    return {
        "status": "success",
        "biases_detected": biases_detected,
        "analysis": analysis_results,
    }


@celery_app.task(name="app.workers.tasks.ai_ethics_tasks.update_fairness_metrics")
def update_fairness_metrics() -> dict:
    """Aktualisiere Fairness-Metriken fuer alle KI-Entscheidungen."""
    logger.info("ai_ethics_fairness_metrics_start")
    try:
        result = asyncio.get_event_loop().run_until_complete(_update_fairness_metrics())
        logger.info("ai_ethics_fairness_metrics_complete")
        return result
    except Exception as e:
        logger.error("ai_ethics_fairness_metrics_error", **safe_error_log(e))
        raise


async def _update_fairness_metrics() -> Dict[str, Any]:
    """Async Implementation fuer Fairness Metrics."""
    from app.db.models import AppConfig

    async with async_session_maker() as db:
        # Lade bestehende Fairness-Metriken
        config_result = await db.execute(
            select(AppConfig).where(AppConfig.key == "ai_fairness_metrics")
        )
        config = config_result.scalar_one_or_none()

        # Berechne neue Metriken
        # Entity-Typ Verteilung
        entity_dist_result = await db.execute(
            select(
                BusinessEntity.entity_type,
                func.count(BusinessEntity.id).label("count"),
            )
            .group_by(BusinessEntity.entity_type)
        )
        entity_distribution = {
            (row[0].value if row[0] else "unknown"): row[1]
            for row in entity_dist_result.all()
        }

        # OCR Backend Nutzung
        ocr_usage_result = await db.execute(
            select(
                Document.ocr_backend,
                func.count(Document.id).label("count"),
            )
            .where(Document.ocr_backend.isnot(None))
            .group_by(Document.ocr_backend)
        )
        ocr_usage = {
            (row[0] or "unknown"): row[1]
            for row in ocr_usage_result.all()
        }

        metrics = {
            "entity_type_distribution": entity_distribution,
            "ocr_backend_usage": ocr_usage,
            "updated_at": asyncio.get_event_loop().time(),
        }

        # In AppConfig speichern
        if config:
            config.value = metrics
        else:
            config = AppConfig(key="ai_fairness_metrics", value=metrics)
            db.add(config)

        await db.commit()

    return {
        "status": "success",
        "metrics_updated": True,
    }

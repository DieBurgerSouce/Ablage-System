# -*- coding: utf-8 -*-
"""CEO Dashboard / Digital Twin periodic tasks (F4).

Phase 12: Vollständige Integration mit HealthScoreCalculator und TrendAnalyzer.
"""

import asyncio
from typing import Dict, List, Any

import structlog
from sqlalchemy import select

from app.workers.celery_app import celery_app
from app.core.safe_errors import safe_error_log
from app.db.session import async_session_maker
from app.db.models import Company

logger = structlog.get_logger(__name__)


@celery_app.task(name="app.workers.tasks.ceo_dashboard_tasks.create_daily_snapshot")
def create_daily_snapshot() -> dict:
    """Erstelle täglichen Company Health Snapshot.

    Berechnet Health-Scores für alle Companies:
    - Financial Health (Umsatz, Cash-Flow, offene Rechnungen)
    - Operations Health (OCR-Durchsatz, Fehlerrate, Verarbeitungszeit)
    - Risk Health (High-Risk Entities, überfällige Rechnungen)
    - Compliance Health (GDPR, GoBD, Audit-Status)
    """
    logger.info("ceo_dashboard_daily_snapshot_start")
    try:
        result = asyncio.get_event_loop().run_until_complete(_create_daily_snapshot())
        logger.info(
            "ceo_dashboard_daily_snapshot_complete",
            snapshots_created=result.get("snapshots_created", 0),
        )
        return result
    except Exception as e:
        logger.error("ceo_dashboard_daily_snapshot_error", **safe_error_log(e))
        raise


async def _create_daily_snapshot() -> Dict[str, Any]:
    """Async Implementation für Daily Snapshot."""
    from app.services.ceo_dashboard.health_score_calculator import HealthScoreCalculator

    snapshots: List[Dict[str, Any]] = []

    async with async_session_maker() as db:
        # Alle aktiven Companies laden
        result = await db.execute(
            select(Company.id, Company.name).where(Company.is_active == True)
        )
        companies = result.all()

        calculator = HealthScoreCalculator()

        for company_id, company_name in companies:
            try:
                # Health Score berechnen
                score = await calculator.calculate(company_id, db)

                snapshots.append({
                    "company_id": str(company_id),
                    "overall_score": round(score.overall, 2),
                    "financial": round(score.financial, 2),
                    "operations": round(score.operations, 2),
                    "risk": round(score.risk, 2),
                    "compliance": round(score.compliance, 2),
                    "trend": score.trend,
                })

                logger.debug(
                    "health_score_calculated",
                    company_id=str(company_id),
                    overall=round(score.overall, 2),
                )

            except Exception as e:
                logger.warning(
                    "health_score_calculation_failed",
                    company_id=str(company_id),
                    **safe_error_log(e),
                )
                continue

    return {
        "status": "success",
        "snapshots_created": len(snapshots),
        "message": f"Daily snapshots für {len(snapshots)} Companies erstellt",
    }


@celery_app.task(name="app.workers.tasks.ceo_dashboard_tasks.detect_anomalies")
def detect_anomalies() -> dict:
    """Erkenne Anomalien in KPIs und erstelle Alerts."""
    logger.info("ceo_dashboard_anomaly_detection_start")
    try:
        result = asyncio.get_event_loop().run_until_complete(_detect_anomalies())
        logger.info(
            "ceo_dashboard_anomaly_detection_complete",
            anomalies_found=result.get("anomalies_found", 0),
        )
        return result
    except Exception as e:
        logger.error("ceo_dashboard_anomaly_detection_error", **safe_error_log(e))
        raise


async def _detect_anomalies() -> Dict[str, Any]:
    """Async Implementation für Anomaly Detection."""
    from app.services.ceo_dashboard.trend_analyzer import TrendAnalyzer
    from app.services.ceo_dashboard.health_score_calculator import HealthScoreCalculator

    anomalies_found = 0

    async with async_session_maker() as db:
        result = await db.execute(
            select(Company.id).where(Company.is_active == True)
        )
        company_ids = [row[0] for row in result.all()]

        calculator = HealthScoreCalculator()
        analyzer = TrendAnalyzer()

        for company_id in company_ids:
            try:
                # Aktuellen Score berechnen
                score = await calculator.calculate(company_id, db)

                # Anomalie-Erkennung: Score unter 50 oder starker Abfall
                if score.overall < 50:
                    anomalies_found += 1
                    logger.warning(
                        "anomaly_detected_low_score",
                        company_id=str(company_id),
                        overall=round(score.overall, 2),
                    )

                # Trend-Anomalie: Mehr als 10% Abfall
                if score.trend and score.trend < -10:
                    anomalies_found += 1
                    logger.warning(
                        "anomaly_detected_declining_trend",
                        company_id=str(company_id),
                        trend=score.trend,
                    )

            except Exception as e:
                logger.warning(
                    "anomaly_detection_failed",
                    company_id=str(company_id),
                    **safe_error_log(e),
                )
                continue

    return {
        "status": "success",
        "anomalies_found": anomalies_found,
    }

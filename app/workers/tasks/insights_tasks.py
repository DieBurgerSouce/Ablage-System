# -*- coding: utf-8 -*-
"""
Financial Insights Celery Tasks.

Batch-generierte Insights und proaktive Warnungen:
- Tägliche Cashflow-Prognosen
- Betrugs-Scans
- Skonto-Optimierungs-Empfehlungen
- Action Queue Timeout-Verarbeitung

Vision 2.0 Feature: Proactive Insights (Phase 6)
Feinpoliert und durchdacht.
"""

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Union
from uuid import UUID

import structlog

from app.core.safe_errors import safe_error_log, safe_error_detail
from app.workers.celery_app import celery_app, CPUTask

logger = structlog.get_logger(__name__)

# Type aliases for mypy strict mode
InsightDict = Dict[str, Union[str, float, int, bool, None, Dict[str, Any], List[Any]]]
ScanResultDict = Dict[str, Union[str, int, float, List[Dict[str, Any]]]]
OptimizationDict = Dict[str, Union[str, float, int, List[Dict[str, Any]]]]


# =============================================================================
# Cashflow Prediction Tasks
# =============================================================================


@celery_app.task(
    base=CPUTask,
    name="app.workers.tasks.insights_tasks.generate_daily_cashflow_predictions",
    queue="maintenance",
    priority=3,
    ignore_result=False,
    soft_time_limit=290,
    time_limit=300,
)
def generate_daily_cashflow_predictions() -> Dict[str, Any]:
    """
    Generiert tägliche Cashflow-Prognosen für alle aktiven Companies.

    Wird täglich um 06:00 via Celery Beat ausgeführt.
    Erstellt 30-Tage-Prognosen und generiert Warnungen bei Risiko.

    Returns:
        Dict mit Statistiken der generierten Prognosen
    """
    import asyncio
    from sqlalchemy import select
    from app.db.session import async_session_factory
    from app.db.models import Company
    from app.services.insights import get_cashflow_predictor

    async def _generate_predictions() -> Dict[str, Any]:
        predictor = get_cashflow_predictor()
        stats: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "companies_processed": 0,
            "predictions_generated": 0,
            "warnings_generated": 0,
            "errors": 0,
        }

        async with async_session_factory() as db:
            # Hole alle aktiven Companies
            result = await db.execute(
                select(Company.id)
                .where(Company.is_active == True)
                .where(Company.deleted_at.is_(None))
            )
            company_ids = [row[0] for row in result.fetchall()]

            for company_id in company_ids:
                try:
                    prediction = await predictor.predict(
                        db=db,
                        company_id=company_id,
                        horizon_days=30,
                        include_scenarios=False,
                    )

                    stats["companies_processed"] += 1
                    stats["predictions_generated"] += 1

                    # Prüfe auf Risiko und erstelle Alert
                    risk_level = prediction.get("risk_level")
                    if risk_level in ("high", "critical"):
                        stats["warnings_generated"] += 1
                        # Alert Center Integration
                        from app.services.alert_center_service import (
                            AlertCenterService, AlertCategory, AlertSeverity
                        )
                        alert_service = AlertCenterService(db)
                        await alert_service.create_alert(
                            company_id=company_id,
                            alert_code="RISK_002",
                            category=AlertCategory.RISK,
                            severity=AlertSeverity.HIGH if risk_level == "high" else AlertSeverity.CRITICAL,
                            title="Cashflow-Risiko erkannt",
                            message=f"Die Cashflow-Prognose zeigt ein {risk_level}-Risiko in den naechsten 30 Tagen.",
                            source_type="cashflow_predictor",
                            metadata={
                                "predicted_balance": prediction.get("predicted_balance"),
                                "risk_days": prediction.get("risk_days"),
                            },
                            recurrence_key=f"cashflow_risk_{company_id}_{datetime.now(timezone.utc).date()}",
                        )

                except Exception as e:
                    stats["errors"] += 1
                    logger.warning(
                        "cashflow_prediction_failed",
                        company_id=str(company_id),
                        **safe_error_log(e),
                    )

        return stats

    return asyncio.get_event_loop().run_until_complete(_generate_predictions())


@celery_app.task(
    base=CPUTask,
    name="app.workers.tasks.insights_tasks.generate_cashflow_prediction",
    queue="metadata",
    priority=5,
    ignore_result=False,
    soft_time_limit=55,
    time_limit=60,
)
def generate_cashflow_prediction(
    company_id: str,
    horizon_days: int = 30,
    include_scenarios: bool = False,
) -> InsightDict:
    """
    Generiert Cashflow-Prognose für eine einzelne Company.

    Args:
        company_id: UUID der Company
        horizon_days: Prognosezeitraum (7-90)
        include_scenarios: What-If Szenarien einbeziehen

    Returns:
        Dict mit Prognose-Ergebnis
    """
    import asyncio
    from app.db.session import async_session_factory
    from app.services.insights import get_cashflow_predictor

    async def _generate() -> InsightDict:
        predictor = get_cashflow_predictor()

        async with async_session_factory() as db:
            try:
                prediction = await predictor.predict(
                    db=db,
                    company_id=UUID(company_id),
                    horizon_days=horizon_days,
                    include_scenarios=include_scenarios,
                )
                return {
                    "success": True,
                    "company_id": company_id,
                    "prediction": prediction,
                }
            except Exception as e:
                logger.error(
                    "cashflow_prediction_error",
                    company_id=company_id,
                    **safe_error_log(e),
                )
                return {
                    "success": False,
                    "company_id": company_id,
                    "error": safe_error_detail(e, "Vorgang"),
                }

    return asyncio.get_event_loop().run_until_complete(_generate())


# =============================================================================
# Fraud Detection Tasks
# =============================================================================


@celery_app.task(
    base=CPUTask,
    name="app.workers.tasks.insights_tasks.run_daily_fraud_scan",
    queue="maintenance",
    priority=3,
    ignore_result=False,
    soft_time_limit=590,
    time_limit=600,
)
def run_daily_fraud_scan() -> Dict[str, Any]:
    """
    Führt täglichen Betrugs-Scan für alle aktiven Companies durch.

    Wird täglich um 03:00 via Celery Beat ausgeführt.
    Prüft die letzten 30 Tage auf Anomalien.

    Returns:
        Dict mit Scan-Statistiken
    """
    import asyncio
    from sqlalchemy import select
    from app.db.session import async_session_factory
    from app.db.models import Company
    from app.services.insights import get_fraud_early_warning_service

    async def _run_scans() -> Dict[str, Any]:
        fraud_service = get_fraud_early_warning_service()
        stats: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "companies_scanned": 0,
            "total_alerts": 0,
            "critical_alerts": 0,
            "high_alerts": 0,
            "errors": 0,
        }

        async with async_session_factory() as db:
            result = await db.execute(
                select(Company.id)
                .where(Company.is_active == True)
                .where(Company.deleted_at.is_(None))
            )
            company_ids = [row[0] for row in result.fetchall()]

            for company_id in company_ids:
                try:
                    scan_result = await fraud_service.scan(
                        db=db,
                        company_id=company_id,
                        scan_days=30,
                    )

                    stats["companies_scanned"] += 1
                    stats["total_alerts"] += scan_result.get("alerts_found", 0)

                    # Zähle nach Schweregrad
                    by_severity = scan_result.get("by_severity", {})
                    stats["critical_alerts"] += by_severity.get("critical", 0)
                    stats["high_alerts"] += by_severity.get("high", 0)

                except Exception as e:
                    stats["errors"] += 1
                    logger.warning(
                        "fraud_scan_failed",
                        company_id=str(company_id),
                        **safe_error_log(e),
                    )

        return stats

    return asyncio.get_event_loop().run_until_complete(_run_scans())


@celery_app.task(
    base=CPUTask,
    name="app.workers.tasks.insights_tasks.scan_company_for_fraud",
    queue="metadata",
    priority=5,
    ignore_result=False,
    soft_time_limit=115,
    time_limit=120,
)
def scan_company_for_fraud(
    company_id: str,
    scan_days: int = 30,
) -> ScanResultDict:
    """
    Führt Betrugs-Scan für eine einzelne Company durch.

    Args:
        company_id: UUID der Company
        scan_days: Tage zurück zu scannen

    Returns:
        Dict mit Scan-Ergebnis
    """
    import asyncio
    from app.db.session import async_session_factory
    from app.services.insights import get_fraud_early_warning_service

    async def _scan() -> ScanResultDict:
        fraud_service = get_fraud_early_warning_service()

        async with async_session_factory() as db:
            try:
                result = await fraud_service.scan(
                    db=db,
                    company_id=UUID(company_id),
                    scan_days=scan_days,
                )
                return {
                    "success": True,
                    "company_id": company_id,
                    **result,
                }
            except Exception as e:
                logger.error(
                    "fraud_scan_error",
                    company_id=company_id,
                    **safe_error_log(e),
                )
                return {
                    "success": False,
                    "company_id": company_id,
                    "error": safe_error_detail(e, "Vorgang"),
                }

    return asyncio.get_event_loop().run_until_complete(_scan())


# =============================================================================
# Skonto Optimization Tasks
# =============================================================================


@celery_app.task(
    base=CPUTask,
    name="app.workers.tasks.insights_tasks.generate_daily_skonto_recommendations",
    queue="maintenance",
    priority=3,
    ignore_result=False,
    soft_time_limit=290,
    time_limit=300,
)
def generate_daily_skonto_recommendations() -> Dict[str, Any]:
    """
    Generiert tägliche Skonto-Empfehlungen für alle aktiven Companies.

    Wird täglich um 07:00 via Celery Beat ausgeführt.
    Analysiert die nächsten 14 Tage auf Skonto-Möglichkeiten.

    Returns:
        Dict mit Optimierungs-Statistiken
    """
    import asyncio
    from sqlalchemy import select
    from app.db.session import async_session_factory
    from app.db.models import Company
    from app.services.insights import get_skonto_optimizer

    async def _generate_recommendations() -> Dict[str, Any]:
        optimizer = get_skonto_optimizer()
        stats: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "companies_processed": 0,
            "total_invoices_with_skonto": 0,
            "total_potential_savings": 0.0,
            "urgent_recommendations": 0,
            "errors": 0,
        }

        async with async_session_factory() as db:
            result = await db.execute(
                select(Company.id)
                .where(Company.is_active == True)
                .where(Company.deleted_at.is_(None))
            )
            company_ids = [row[0] for row in result.fetchall()]

            for company_id in company_ids:
                try:
                    optimization = await optimizer.optimize(
                        db=db,
                        company_id=company_id,
                        days_ahead=14,
                        min_savings=10.0,
                    )

                    stats["companies_processed"] += 1
                    stats["total_invoices_with_skonto"] += optimization.get(
                        "total_invoices", 0
                    )
                    stats["total_potential_savings"] += optimization.get(
                        "total_skonto_available", 0.0
                    )

                    # Zähle dringende Empfehlungen (< 3 Tage)
                    for rec in optimization.get("recommendations", []):
                        if rec.get("days_until_deadline", 100) <= 3:
                            stats["urgent_recommendations"] += 1

                except Exception as e:
                    stats["errors"] += 1
                    logger.warning(
                        "skonto_optimization_failed",
                        company_id=str(company_id),
                        **safe_error_log(e),
                    )

        return stats

    return asyncio.get_event_loop().run_until_complete(_generate_recommendations())


@celery_app.task(
    base=CPUTask,
    name="app.workers.tasks.insights_tasks.optimize_skonto_for_company",
    queue="metadata",
    priority=5,
    ignore_result=False,
    soft_time_limit=55,
    time_limit=60,
)
def optimize_skonto_for_company(
    company_id: str,
    days_ahead: int = 14,
    min_savings: float = 10.0,
) -> OptimizationDict:
    """
    Optimiert Skonto-Nutzung für eine einzelne Company.

    Args:
        company_id: UUID der Company
        days_ahead: Tage voraus zu analysieren
        min_savings: Mindest-Ersparnis in EUR

    Returns:
        Dict mit Optimierungs-Ergebnis
    """
    import asyncio
    from app.db.session import async_session_factory
    from app.services.insights import get_skonto_optimizer

    async def _optimize() -> OptimizationDict:
        optimizer = get_skonto_optimizer()

        async with async_session_factory() as db:
            try:
                result = await optimizer.optimize(
                    db=db,
                    company_id=UUID(company_id),
                    days_ahead=days_ahead,
                    min_savings=min_savings,
                )
                return {
                    "success": True,
                    "company_id": company_id,
                    **result,
                }
            except Exception as e:
                logger.error(
                    "skonto_optimization_error",
                    company_id=company_id,
                    **safe_error_log(e),
                )
                return {
                    "success": False,
                    "company_id": company_id,
                    "error": safe_error_detail(e, "Vorgang"),
                }

    return asyncio.get_event_loop().run_until_complete(_optimize())


# =============================================================================
# Action Queue Tasks
# =============================================================================


@celery_app.task(
    base=CPUTask,
    name="app.workers.tasks.insights_tasks.process_action_queue_timeouts",
    queue="maintenance",
    priority=2,
    ignore_result=False,
    soft_time_limit=55,
    time_limit=60,
)
def process_action_queue_timeouts() -> Dict[str, int]:
    """
    Verarbeitet abgelaufene Timeouts in der Action Approval Queue.

    Wird alle 5 Minuten via Celery Beat ausgeführt.
    Genehmigt oder verwirft Aktionen basierend auf Timeout-Konfiguration.

    Returns:
        Dict mit Anzahl verarbeiteter Aktionen
    """
    import asyncio
    from app.db.session import async_session_factory
    from app.services.autonomy import get_action_queue

    async def _process_timeouts() -> Dict[str, int]:
        queue = get_action_queue()

        try:
            async with async_session_factory() as db:
                processed = await queue.process_timeouts(db)
                return {
                    "processed": processed,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
        except Exception as e:
            logger.error(
                "process_timeouts_error",
                **safe_error_log(e),
            )
            return {
                "processed": 0,
                "error": safe_error_detail(e, "Vorgang"),
            }

    return asyncio.get_event_loop().run_until_complete(_process_timeouts())


# =============================================================================
# Combined Daily Insights Task
# =============================================================================


@celery_app.task(
    base=CPUTask,
    name="app.workers.tasks.insights_tasks.generate_all_daily_insights",
    queue="maintenance",
    priority=4,
    ignore_result=False,
    soft_time_limit=1790,
    time_limit=1800,
)
def generate_all_daily_insights() -> Dict[str, Any]:
    """
    Generiert alle täglichen Insights in einem Batch.

    Wird täglich um 05:00 via Celery Beat ausgeführt.
    Koordiniert Cashflow, Fraud und Skonto Tasks.

    Returns:
        Dict mit Gesamtstatistiken
    """
    from celery import chain, group

    logger.info("starting_daily_insights_generation")

    # Starte Tasks parallel
    job = group(
        generate_daily_cashflow_predictions.s(),
        run_daily_fraud_scan.s(),
        generate_daily_skonto_recommendations.s(),
    )

    result = job.apply_async()

    # Warte auf Ergebnisse
    try:
        results = result.get(timeout=1700)
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "success": True,
            "cashflow": results[0] if len(results) > 0 else {},
            "fraud": results[1] if len(results) > 1 else {},
            "skonto": results[2] if len(results) > 2 else {},
        }
    except Exception as e:
        logger.error("daily_insights_generation_failed", **safe_error_log(e))
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "success": False,
            "error": safe_error_detail(e, "Vorgang"),
        }


# =============================================================================
# Urgent Skonto Alert Task
# =============================================================================


@celery_app.task(
    base=CPUTask,
    name="app.workers.tasks.insights_tasks.check_urgent_skonto_deadlines",
    queue="metadata",
    priority=2,
    ignore_result=False,
    soft_time_limit=115,
    time_limit=120,
)
def check_urgent_skonto_deadlines() -> Dict[str, Any]:
    """
    Prüft auf dringende Skonto-Fristen (< 48 Stunden).

    Wird alle 4 Stunden via Celery Beat ausgeführt.
    Generiert Alerts für ablaufende Skonto-Fristen.

    Returns:
        Dict mit gefundenen dringenden Fristen
    """
    import asyncio
    from sqlalchemy import select
    from app.db.session import async_session_factory
    from app.db.models import Company
    from app.services.insights import get_skonto_optimizer

    async def _check_urgent() -> Dict[str, Any]:
        optimizer = get_skonto_optimizer()
        stats: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "companies_checked": 0,
            "urgent_invoices": 0,
            "total_urgent_savings": 0.0,
            "alerts_created": 0,
        }

        async with async_session_factory() as db:
            result = await db.execute(
                select(Company.id)
                .where(Company.is_active == True)
                .where(Company.deleted_at.is_(None))
            )
            company_ids = [row[0] for row in result.fetchall()]

            for company_id in company_ids:
                try:
                    recommendations = await optimizer.get_recommendations(
                        db=db,
                        company_id=company_id,
                        days_ahead=2,  # Nur nächste 48 Stunden
                        only_urgent=True,
                        limit=100,
                    )

                    stats["companies_checked"] += 1

                    for rec in recommendations:
                        stats["urgent_invoices"] += 1
                        skonto_amount = rec.get("skonto_amount", 0)
                        stats["total_urgent_savings"] += skonto_amount

                        # Alert Center Integration fuer dringende Skonto-Fristen
                        from app.services.alert_center_service import (
                            AlertCenterService, AlertCategory, AlertSeverity
                        )
                        alert_service = AlertCenterService(db)
                        await alert_service.create_alert(
                            company_id=company_id,
                            alert_code="DEAD_001",
                            category=AlertCategory.DEADLINE,
                            severity=AlertSeverity.HIGH,
                            title="Skonto-Frist laeuft ab",
                            message=f"Rechnung {rec.get('invoice_number', 'N/A')}: Skonto von {skonto_amount:.2f} EUR verfaellt in {rec.get('days_remaining', 0)} Tagen.",
                            source_type="skonto_optimizer",
                            document_id=rec.get("invoice_id"),
                            entity_id=rec.get("entity_id"),
                            metadata={
                                "invoice_number": rec.get("invoice_number"),
                                "skonto_amount": skonto_amount,
                                "days_remaining": rec.get("days_remaining"),
                                "deadline": rec.get("deadline"),
                            },
                            recurrence_key=f"skonto_urgent_{rec.get('invoice_id')}",
                            available_actions=["pay_now", "dismiss", "snooze"],
                        )
                        stats["alerts_created"] += 1
                        stats["alerts_created"] += 1

                except Exception as e:
                    logger.warning(
                        "urgent_skonto_check_failed",
                        company_id=str(company_id),
                        **safe_error_log(e),
                    )

        return stats

    return asyncio.get_event_loop().run_until_complete(_check_urgent())

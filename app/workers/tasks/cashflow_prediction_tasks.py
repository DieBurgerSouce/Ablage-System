# -*- coding: utf-8 -*-
"""
Cashflow Prediction Celery Tasks.

Enterprise Feature: Februar 2026

Tasks:
- Daily forecast update for all companies
- Cache warming for expensive calculations
- Prediction accuracy evaluation
- Alert generation for critical cashflow situations

Feinpoliert und durchdacht.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Union

import structlog

from app.core.safe_errors import safe_error_log, safe_error_detail
from app.workers.celery_app import celery_app, CPUTask

logger = structlog.get_logger(__name__)

# Type aliases
TaskResult = Dict[str, Union[str, int, float, bool, None]]


@celery_app.task(
    base=CPUTask,
    name="cashflow_prediction.update_daily_forecast",
    queue="metadata",
    priority=2,
    ignore_result=True,
    soft_time_limit=290,
    time_limit=300,
)
def update_daily_forecast(company_id: Optional[str] = None) -> TaskResult:
    """
    Aktualisiert die Cashflow-Prognose fuer alle oder eine bestimmte Firma.

    Wird taeglich um 06:00 via Celery Beat ausgefuehrt.
    Cached die Ergebnisse fuer schnelleren API-Zugriff.

    Args:
        company_id: Optional - nur fuer bestimmte Firma

    Returns:
        Dict mit Task-Ergebnissen
    """
    import asyncio
    from uuid import UUID
    from app.db.async_session import get_async_session

    result: TaskResult = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "success": True,
        "task": "update_daily_forecast",
        "companies_processed": 0,
        "warnings_generated": 0,
    }

    async def _update_forecasts() -> Dict:
        """Async Forecast-Update Logik."""
        from sqlalchemy import select
        from app.db.models import Company
        from app.services.ai.cashflow_prediction_service import (
            get_cashflow_prediction_service,
            WarningSeverity,
        )

        update_result: Dict = {
            "companies_processed": 0,
            "forecasts_created": 0,
            "warnings_generated": 0,
            "critical_warnings": 0,
            "errors": [],
        }

        async for session in get_async_session():
            try:
                service = get_cashflow_prediction_service(session)

                # Company IDs ermitteln
                if company_id:
                    company_ids = [UUID(company_id)]
                else:
                    # Alle aktiven Companies
                    company_query = select(Company.id).where(
                        Company.is_active == True
                    ).limit(100)
                    company_result = await session.execute(company_query)
                    company_ids = [row[0] for row in company_result.fetchall()]

                for cid in company_ids:
                    try:
                        # 30-Tage Prognose erstellen
                        forecasts = await service.get_cashflow_forecast(
                            company_id=cid,
                            days=30,
                        )
                        update_result["forecasts_created"] += 1

                        # Warnungen generieren
                        warnings = await service.get_cashflow_warnings(
                            company_id=cid,
                            days=30,
                        )
                        update_result["warnings_generated"] += len(warnings)

                        # Kritische Warnungen zaehlen
                        critical = sum(
                            1 for w in warnings
                            if w.severity == WarningSeverity.CRITICAL
                        )
                        update_result["critical_warnings"] += critical

                        # Bei kritischen Warnungen: Alert erstellen
                        if critical > 0:
                            await _create_cashflow_alert(session, cid, warnings)

                        update_result["companies_processed"] += 1

                    except Exception as e:
                        logger.warning(
                            "company_forecast_failed",
                            company_id=str(cid),
                            **safe_error_log(e),
                        )
                        update_result["errors"].append({
                            "company_id": str(cid),
                            "error": safe_error_detail(e, "Forecast"),
                        })

            except Exception as e:
                logger.error("forecast_update_failed", **safe_error_log(e))
                update_result["error"] = safe_error_detail(e, "ForecastUpdate")
            finally:
                await session.close()

        return update_result

    try:
        update_result = asyncio.run(_update_forecasts())
        result.update(update_result)

        logger.info(
            "daily_forecast_update_completed",
            companies=result.get("companies_processed"),
            warnings=result.get("warnings_generated"),
            critical=result.get("critical_warnings"),
        )

    except Exception as e:
        logger.error("daily_forecast_update_failed", **safe_error_log(e))
        result["success"] = False
        result["error"] = safe_error_detail(e, "ForecastUpdate")

    return result


@celery_app.task(
    base=CPUTask,
    name="cashflow_prediction.evaluate_accuracy",
    queue="maintenance",
    priority=3,
    ignore_result=True,
    soft_time_limit=590,
    time_limit=600,
)
def evaluate_prediction_accuracy() -> TaskResult:
    """
    Evaluiert die Genauigkeit der Cashflow-Vorhersagen.

    Wird woechentlich (Sonntag 04:00) via Celery Beat ausgefuehrt.
    Vergleicht historische Vorhersagen mit tatsaechlichen Zahlungen.

    Returns:
        Dict mit Evaluations-Metriken
    """
    import asyncio
    from app.db.async_session import get_async_session

    result: TaskResult = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "success": True,
        "task": "evaluate_prediction_accuracy",
    }

    async def _evaluate() -> Dict:
        """Async Evaluation Logik."""
        from sqlalchemy import select
        from app.db.models import Company
        from app.services.ai.cashflow_prediction_service import (
            get_cashflow_prediction_service,
        )

        eval_result: Dict = {
            "companies_evaluated": 0,
            "total_predictions": 0,
            "avg_accuracy_rate": 0.0,
            "avg_mae_days": 0.0,
        }

        accuracies: List[float] = []
        maes: List[float] = []

        async for session in get_async_session():
            try:
                service = get_cashflow_prediction_service(session)

                # Alle aktiven Companies
                company_query = select(Company.id).where(
                    Company.is_active == True
                ).limit(50)
                company_result = await session.execute(company_query)
                company_ids = [row[0] for row in company_result.fetchall()]

                for cid in company_ids:
                    try:
                        metrics = await service.get_prediction_metrics(
                            company_id=cid
                        )

                        if metrics.total_predictions > 0:
                            eval_result["total_predictions"] += metrics.total_predictions
                            accuracies.append(metrics.accuracy_rate)
                            maes.append(metrics.mean_absolute_error_days)
                            eval_result["companies_evaluated"] += 1

                    except Exception as e:
                        logger.warning(
                            "company_evaluation_failed",
                            company_id=str(cid),
                            **safe_error_log(e),
                        )

                # Durchschnitte berechnen
                if accuracies:
                    eval_result["avg_accuracy_rate"] = round(
                        sum(accuracies) / len(accuracies), 2
                    )
                if maes:
                    eval_result["avg_mae_days"] = round(
                        sum(maes) / len(maes), 2
                    )

            except Exception as e:
                logger.error("evaluation_failed", **safe_error_log(e))
                eval_result["error"] = safe_error_detail(e, "Evaluation")
            finally:
                await session.close()

        return eval_result

    try:
        eval_result = asyncio.run(_evaluate())
        result.update(eval_result)

        logger.info(
            "prediction_accuracy_evaluation_completed",
            companies=result.get("companies_evaluated"),
            accuracy=result.get("avg_accuracy_rate"),
            mae=result.get("avg_mae_days"),
        )

    except Exception as e:
        logger.error("prediction_accuracy_evaluation_failed", **safe_error_log(e))
        result["success"] = False
        result["error"] = safe_error_detail(e, "Evaluation")

    return result


@celery_app.task(
    base=CPUTask,
    name="cashflow_prediction.generate_alerts",
    queue="metadata",
    priority=1,
    ignore_result=True,
    soft_time_limit=110,
    time_limit=120,
)
def generate_cashflow_alerts(company_id: str) -> TaskResult:
    """
    Generiert Alerts fuer kritische Cashflow-Situationen.

    Wird nach Forecast-Updates oder on-demand ausgefuehrt.

    Args:
        company_id: Firmen-ID

    Returns:
        Dict mit Alert-Ergebnissen
    """
    import asyncio
    from uuid import UUID
    from app.db.async_session import get_async_session

    result: TaskResult = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "success": True,
        "task": "generate_cashflow_alerts",
        "company_id": company_id,
    }

    async def _generate_alerts() -> Dict:
        """Async Alert-Generation Logik."""
        from app.services.ai.cashflow_prediction_service import (
            get_cashflow_prediction_service,
            WarningSeverity,
        )

        alert_result: Dict = {
            "warnings_found": 0,
            "alerts_created": 0,
        }

        async for session in get_async_session():
            try:
                service = get_cashflow_prediction_service(session)
                cid = UUID(company_id)

                # Warnungen generieren
                warnings = await service.get_cashflow_warnings(
                    company_id=cid,
                    days=30,
                )

                alert_result["warnings_found"] = len(warnings)

                # Alerts fuer kritische Warnungen erstellen
                critical_warnings = [
                    w for w in warnings
                    if w.severity == WarningSeverity.CRITICAL
                ]

                if critical_warnings:
                    alerts_created = await _create_cashflow_alert(
                        session, cid, critical_warnings
                    )
                    alert_result["alerts_created"] = alerts_created

            except Exception as e:
                logger.error("alert_generation_failed", **safe_error_log(e))
                alert_result["error"] = safe_error_detail(e, "AlertGeneration")
            finally:
                await session.close()

        return alert_result

    try:
        alert_result = asyncio.run(_generate_alerts())
        result.update(alert_result)

        logger.info(
            "cashflow_alerts_generated",
            company_id=company_id,
            warnings=result.get("warnings_found"),
            alerts=result.get("alerts_created"),
        )

    except Exception as e:
        logger.error("cashflow_alerts_generation_failed", **safe_error_log(e))
        result["success"] = False
        result["error"] = safe_error_detail(e, "AlertGeneration")

    return result


@celery_app.task(
    base=CPUTask,
    name="cashflow_prediction.warm_cache",
    queue="maintenance",
    priority=3,
    ignore_result=True,
    soft_time_limit=290,
    time_limit=300,
)
def warm_forecast_cache() -> TaskResult:
    """
    Waermt den Forecast-Cache fuer alle aktiven Companies.

    Wird stuendlich via Celery Beat ausgefuehrt um schnellere API-Responses zu ermoeglichen.

    Returns:
        Dict mit Cache-Warming Ergebnissen
    """
    import asyncio
    from app.db.async_session import get_async_session

    result: TaskResult = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "success": True,
        "task": "warm_forecast_cache",
        "companies_cached": 0,
    }

    async def _warm_cache() -> Dict:
        """Async Cache-Warming Logik."""
        from redis import Redis
        from sqlalchemy import select
        import json
        from app.core.config import settings
        from app.db.models import Company
        from app.services.ai.cashflow_prediction_service import (
            get_cashflow_prediction_service,
        )

        cache_result: Dict = {
            "companies_cached": 0,
            "cache_hits": 0,
            "cache_misses": 0,
        }

        try:
            redis_client = Redis.from_url(
                settings.CELERY_BROKER_URL,
                decode_responses=True,
                socket_timeout=5.0,
            )
        except Exception as e:
            logger.warning("redis_connection_failed", **safe_error_log(e))
            return cache_result

        async for session in get_async_session():
            try:
                service = get_cashflow_prediction_service(session)

                # Aktive Companies mit Bankkonten
                company_query = select(Company.id).where(
                    Company.is_active == True
                ).limit(50)
                company_result = await session.execute(company_query)
                company_ids = [row[0] for row in company_result.fetchall()]

                for cid in company_ids:
                    cache_key = f"cashflow_forecast:{cid}:30d"

                    # Cache pruefen
                    cached = redis_client.get(cache_key)
                    if cached:
                        cache_result["cache_hits"] += 1
                        continue

                    cache_result["cache_misses"] += 1

                    try:
                        # Prognose erstellen
                        forecasts = await service.get_cashflow_forecast(
                            company_id=cid,
                            days=30,
                        )

                        # In Cache speichern (1 Stunde TTL)
                        cache_data = {
                            "generated_at": datetime.now(timezone.utc).isoformat(),
                            "forecast_count": len(forecasts),
                            "min_balance": float(min(
                                f.predicted_balance for f in forecasts
                            )) if forecasts else 0,
                        }

                        redis_client.setex(
                            cache_key,
                            3600,  # 1 Stunde
                            json.dumps(cache_data),
                        )

                        cache_result["companies_cached"] += 1

                    except Exception as e:
                        logger.debug(
                            "cache_warming_company_failed",
                            company_id=str(cid),
                            **safe_error_log(e),
                        )

            except Exception as e:
                logger.error("cache_warming_failed", **safe_error_log(e))
                cache_result["error"] = safe_error_detail(e, "CacheWarming")
            finally:
                await session.close()

        return cache_result

    try:
        cache_result = asyncio.run(_warm_cache())
        result.update(cache_result)

        logger.info(
            "forecast_cache_warming_completed",
            cached=result.get("companies_cached"),
            hits=result.get("cache_hits"),
            misses=result.get("cache_misses"),
        )

    except Exception as e:
        logger.error("forecast_cache_warming_failed", **safe_error_log(e))
        result["success"] = False
        result["error"] = safe_error_detail(e, "CacheWarming")

    return result


# =============================================================================
# Helper Functions
# =============================================================================


async def _create_cashflow_alert(
    session,
    company_id,
    warnings: List,
) -> int:
    """
    Erstellt Alert Center Eintraege fuer kritische Cashflow-Warnungen.

    Returns:
        Anzahl erstellter Alerts
    """
    from app.db.models import Alert, AlertCategory, AlertSeverity

    alerts_created = 0

    try:
        for warning in warnings[:5]:  # Max 5 Alerts pro Company
            # Pruefen ob Alert fuer dieses Datum bereits existiert
            # (Deduplizierung in Produktion implementieren)

            alert = Alert(
                company_id=company_id,
                alert_code="CASH_001",
                title="Liquiditaetsengpass erwartet",
                message=warning.message,
                category=AlertCategory.RISK,
                severity=AlertSeverity.CRITICAL if warning.severity.value == "critical" else AlertSeverity.HIGH,
                context={
                    "type": warning.type.value,
                    "date": warning.date.isoformat(),
                    "predicted_balance": float(warning.predicted_balance),
                    "suggested_actions": warning.suggested_actions,
                },
            )
            session.add(alert)
            alerts_created += 1

        await session.commit()

    except Exception as e:
        logger.warning("alert_creation_failed", **safe_error_log(e))
        await session.rollback()

    return alerts_created


# =============================================================================
# Phase 2.2: Entity-based Prediction Tasks
# =============================================================================


@celery_app.task(
    base=CPUTask,
    name="cashflow_prediction.update_entity_profiles",
    queue="maintenance",
    priority=3,
    ignore_result=True,
    soft_time_limit=590,
    time_limit=600,
)
def update_entity_profiles(company_id: Optional[str] = None) -> TaskResult:
    """
    Aktualisiert alle Entity-Zahlungsprofile.

    Wird woechentlich (Sonntag 03:00) via Celery Beat ausgefuehrt.
    Berechnet Payment Consistency, Seasonal Patterns und Risk-adjusted Probability.

    Args:
        company_id: Optional - nur fuer bestimmte Firma

    Returns:
        Dict mit Task-Ergebnissen
    """
    import asyncio
    from uuid import UUID
    from app.db.async_session import get_async_session

    result: TaskResult = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "success": True,
        "task": "update_entity_profiles",
        "companies_processed": 0,
        "profiles_updated": 0,
    }

    async def _update_profiles() -> Dict:
        """Async Profile-Update Logik."""
        from sqlalchemy import select
        from app.db.models import Company
        from app.services.predictive.cashflow_predictor_service import (
            get_cashflow_predictor_service,
        )

        update_result: Dict = {
            "companies_processed": 0,
            "profiles_updated": 0,
            "errors": [],
        }

        async for session in get_async_session():
            try:
                service = get_cashflow_predictor_service(session)

                # Company IDs ermitteln
                if company_id:
                    company_ids = [UUID(company_id)]
                else:
                    # Alle aktiven Companies
                    company_query = select(Company.id).where(
                        Company.is_active == True
                    ).limit(50)
                    company_result = await session.execute(company_query)
                    company_ids = [row[0] for row in company_result.fetchall()]

                for cid in company_ids:
                    try:
                        updated = await service.update_all_entity_profiles(
                            company_id=cid,
                            limit=100,
                        )
                        update_result["profiles_updated"] += updated
                        update_result["companies_processed"] += 1

                    except Exception as e:
                        logger.warning(
                            "company_profile_update_failed",
                            company_id=str(cid),
                            **safe_error_log(e),
                        )
                        update_result["errors"].append({
                            "company_id": str(cid),
                            "error": safe_error_detail(e, "ProfileUpdate"),
                        })

            except Exception as e:
                logger.error("profile_update_failed", **safe_error_log(e))
                update_result["error"] = safe_error_detail(e, "ProfileUpdate")
            finally:
                await session.close()

        return update_result

    try:
        update_result = asyncio.run(_update_profiles())
        result.update(update_result)

        logger.info(
            "entity_profiles_update_completed",
            companies=result.get("companies_processed"),
            profiles=result.get("profiles_updated"),
        )

    except Exception as e:
        logger.error("entity_profiles_update_failed", **safe_error_log(e))
        result["success"] = False
        result["error"] = safe_error_detail(e, "ProfileUpdate")

    return result


@celery_app.task(
    base=CPUTask,
    name="cashflow_prediction.check_liquidity_alerts",
    queue="metadata",
    priority=1,
    ignore_result=True,
    soft_time_limit=230,
    time_limit=240,
)
def check_liquidity_alerts(company_id: Optional[str] = None) -> TaskResult:
    """
    Prueft auf Liquiditaetsprobleme und erstellt Alerts.

    Wird alle 4 Stunden via Celery Beat ausgefuehrt.
    Integriert mit Alert Center Service.

    Args:
        company_id: Optional - nur fuer bestimmte Firma

    Returns:
        Dict mit Task-Ergebnissen
    """
    import asyncio
    from uuid import UUID
    from app.db.async_session import get_async_session

    result: TaskResult = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "success": True,
        "task": "check_liquidity_alerts",
        "companies_checked": 0,
        "alerts_created": 0,
        "critical_alerts": 0,
    }

    async def _check_alerts() -> Dict:
        """Async Alert-Check Logik."""
        from sqlalchemy import select
        from app.db.models import Company
        from app.services.predictive.cashflow_predictor_service import (
            get_cashflow_predictor_service,
        )
        from app.services.alert_center_service import (
            AlertCenterService,
            AlertCodes,
        )
        from app.db.models_alert import AlertCategory, AlertSeverity

        check_result: Dict = {
            "companies_checked": 0,
            "alerts_created": 0,
            "critical_alerts": 0,
            "errors": [],
        }

        async for session in get_async_session():
            try:
                predictor = get_cashflow_predictor_service(session)
                alert_service = AlertCenterService(session)

                # Company IDs ermitteln
                if company_id:
                    company_ids = [UUID(company_id)]
                else:
                    company_query = select(Company.id).where(
                        Company.is_active == True
                    ).limit(100)
                    company_result = await session.execute(company_query)
                    company_ids = [row[0] for row in company_result.fetchall()]

                for cid in company_ids:
                    try:
                        # Liquiditaetswarnungen generieren
                        alerts = await predictor.get_liquidity_alerts(
                            company_id=cid,
                            forecast_days=30,
                        )

                        check_result["companies_checked"] += 1

                        # Kritische Alerts an Alert Center weiterleiten
                        for alert in alerts:
                            if alert.severity.value == "critical":
                                await alert_service.create_alert(
                                    company_id=cid,
                                    alert_code="CASH_002",
                                    category=AlertCategory.RISK,
                                    severity=AlertSeverity.CRITICAL,
                                    title="Kritischer Liquiditaetsengpass erwartet",
                                    message=alert.message,
                                    context={
                                        "alert_type": alert.alert_type.value,
                                        "trigger_date": alert.trigger_date.isoformat(),
                                        "predicted_balance": float(alert.predicted_balance),
                                        "recommendations": alert.recommendations,
                                    },
                                    recurrence_key=f"cashflow_{cid}_{alert.trigger_date.isoformat()}",
                                    auto_dismiss_hours=48,
                                )
                                check_result["alerts_created"] += 1
                                check_result["critical_alerts"] += 1

                            elif alert.severity.value == "warning" and alert.days_until_trigger <= 7:
                                await alert_service.create_alert(
                                    company_id=cid,
                                    alert_code="CASH_003",
                                    category=AlertCategory.RISK,
                                    severity=AlertSeverity.HIGH,
                                    title="Liquiditaetswarnung",
                                    message=alert.message,
                                    context={
                                        "alert_type": alert.alert_type.value,
                                        "trigger_date": alert.trigger_date.isoformat(),
                                        "predicted_balance": float(alert.predicted_balance),
                                        "recommendations": alert.recommendations,
                                    },
                                    recurrence_key=f"cashflow_warn_{cid}_{alert.trigger_date.isoformat()}",
                                    auto_dismiss_hours=72,
                                )
                                check_result["alerts_created"] += 1

                        await session.commit()

                    except Exception as e:
                        logger.warning(
                            "company_alert_check_failed",
                            company_id=str(cid),
                            **safe_error_log(e),
                        )
                        check_result["errors"].append({
                            "company_id": str(cid),
                            "error": safe_error_detail(e, "AlertCheck"),
                        })
                        await session.rollback()

            except Exception as e:
                logger.error("alert_check_failed", **safe_error_log(e))
                check_result["error"] = safe_error_detail(e, "AlertCheck")
            finally:
                await session.close()

        return check_result

    try:
        check_result = asyncio.run(_check_alerts())
        result.update(check_result)

        logger.info(
            "liquidity_alert_check_completed",
            companies=result.get("companies_checked"),
            alerts=result.get("alerts_created"),
            critical=result.get("critical_alerts"),
        )

    except Exception as e:
        logger.error("liquidity_alert_check_failed", **safe_error_log(e))
        result["success"] = False
        result["error"] = safe_error_detail(e, "AlertCheck")

    return result


@celery_app.task(
    base=CPUTask,
    name="cashflow_prediction.calculate_daily_forecast_v2",
    queue="metadata",
    priority=2,
    ignore_result=True,
    soft_time_limit=290,
    time_limit=300,
)
def calculate_daily_forecast_v2(company_id: Optional[str] = None) -> TaskResult:
    """
    Berechnet taegliche Cashflow-Prognose (V2 mit Entity-Profilen).

    Wird taeglich um 06:00 via Celery Beat ausgefuehrt.
    Verwendet Entity-basierte Zahlungsprofile fuer praezisere Vorhersagen.

    Args:
        company_id: Optional - nur fuer bestimmte Firma

    Returns:
        Dict mit Task-Ergebnissen
    """
    import asyncio
    from uuid import UUID
    from app.db.async_session import get_async_session

    result: TaskResult = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "success": True,
        "task": "calculate_daily_forecast_v2",
        "companies_processed": 0,
        "forecasts_created": 0,
    }

    async def _calculate_forecasts() -> Dict:
        """Async Forecast-Berechnung Logik."""
        from sqlalchemy import select
        from app.db.models import Company
        from app.services.predictive.cashflow_predictor_service import (
            get_cashflow_predictor_service,
        )

        calc_result: Dict = {
            "companies_processed": 0,
            "forecasts_created": 0,
            "min_balances": [],
            "errors": [],
        }

        async for session in get_async_session():
            try:
                service = get_cashflow_predictor_service(session)

                # Company IDs ermitteln
                if company_id:
                    company_ids = [UUID(company_id)]
                else:
                    company_query = select(Company.id).where(
                        Company.is_active == True
                    ).limit(100)
                    company_result = await session.execute(company_query)
                    company_ids = [row[0] for row in company_result.fetchall()]

                for cid in company_ids:
                    try:
                        # 30-Tage Prognose erstellen
                        forecasts = await service.get_cashflow_forecast(
                            company_id=cid,
                            days=30,
                        )

                        if forecasts:
                            calc_result["forecasts_created"] += 1
                            min_balance = min(f.confidence_mid for f in forecasts)
                            calc_result["min_balances"].append(float(min_balance))

                        calc_result["companies_processed"] += 1

                    except Exception as e:
                        logger.warning(
                            "company_forecast_v2_failed",
                            company_id=str(cid),
                            **safe_error_log(e),
                        )
                        calc_result["errors"].append({
                            "company_id": str(cid),
                            "error": safe_error_detail(e, "ForecastV2"),
                        })

            except Exception as e:
                logger.error("forecast_v2_calculation_failed", **safe_error_log(e))
                calc_result["error"] = safe_error_detail(e, "ForecastV2")
            finally:
                await session.close()

        return calc_result

    try:
        calc_result = asyncio.run(_calculate_forecasts())
        result.update(calc_result)

        # Durchschnittliche Min-Balance berechnen
        if calc_result.get("min_balances"):
            avg_min = sum(calc_result["min_balances"]) / len(calc_result["min_balances"])
            result["avg_min_balance"] = round(avg_min, 2)

        logger.info(
            "daily_forecast_v2_completed",
            companies=result.get("companies_processed"),
            forecasts=result.get("forecasts_created"),
            avg_min_balance=result.get("avg_min_balance"),
        )

    except Exception as e:
        logger.error("daily_forecast_v2_failed", **safe_error_log(e))
        result["success"] = False
        result["error"] = safe_error_detail(e, "ForecastV2")

    return result

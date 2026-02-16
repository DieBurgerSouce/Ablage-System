# -*- coding: utf-8 -*-
"""
Deutsche Finanz-Feature Celery Tasks.

Feature #11: Deutsche Finanz-Features
Tasks:
- Monatliche USt-Voranmeldung berechnen
- Monatliche BWA generieren
- Tägliche Cashflow-Prognose aktualisieren
- Tägliche Liquiditätswarnungen prüfen
- Wöchentliche Prognose-Genauigkeit evaluieren

Feinpoliert und durchdacht - Enterprise-grade Deutsche Finanzberichterstattung.
"""

import asyncio
from datetime import date, datetime, timezone, timedelta
from typing import Dict, List, Optional, Union
from uuid import UUID

import structlog

from app.core.safe_errors import safe_error_log, safe_error_detail
from app.workers.celery_app import celery_app, CPUTask

logger = structlog.get_logger(__name__)

# Type alias
TaskResult = Dict[str, Union[str, int, float, bool, None, List[Dict[str, str]]]]


# =============================================================================
# USt-Voranmeldung Task
# =============================================================================


@celery_app.task(
    base=CPUTask,
    name="app.workers.tasks.german_finance_tasks.calculate_monthly_ust_task",
    queue="maintenance",
    priority=2,
    ignore_result=True,
    soft_time_limit=290,
    time_limit=300,
)
def calculate_monthly_ust_task(
    company_id: Optional[str] = None,
    year: Optional[int] = None,
    month: Optional[int] = None,
) -> TaskResult:
    """
    Berechnet die monatliche USt-Voranmeldung.

    Wird am 1. jeden Monats via Celery Beat ausgeführt.
    Aggregiert Vorsteuer und Umsatzsteuer des Vormonats.

    Args:
        company_id: Optional - nur für bestimmte Firma
        year: Optional - Steuerjahr (Standard: Vormonat)
        month: Optional - Steuermonat (Standard: Vormonat)

    Returns:
        Dict mit Task-Ergebnissen
    """
    result: TaskResult = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "success": True,
        "task": "calculate_monthly_ust_task",
        "companies_processed": 0,
        "voranmeldungen_created": 0,
        "errors": [],
    }

    # Vormonat bestimmen wenn nicht angegeben
    if year is None or month is None:
        today = date.today()
        first_of_month = today.replace(day=1)
        last_month = first_of_month - timedelta(days=1)
        year = year or last_month.year
        month = month or last_month.month

    async def _calculate() -> Dict[str, Union[str, int, List[Dict[str, str]]]]:
        from sqlalchemy import select
        from app.db.session import get_async_session_context
        from app.db.models import Company
        from app.services.finance.ust_voranmeldung_service import (
            get_ust_voranmeldung_service,
        )

        calc_result: Dict[str, Union[str, int, List[Dict[str, str]]]] = {
            "companies_processed": 0,
            "voranmeldungen_created": 0,
            "errors": [],
        }

        async with get_async_session_context() as session:
            try:
                service = get_ust_voranmeldung_service()

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
                        voranmeldung = await service.calculate_period(
                            db=session,
                            company_id=cid,
                            year=year,
                            month=month,
                        )
                        await session.commit()

                        calc_result["companies_processed"] += 1
                        calc_result["voranmeldungen_created"] += 1

                        logger.debug(
                            "ust_voranmeldung_berechnet",
                            company_id=str(cid),
                            zahllast=voranmeldung.zahllast,
                            period=f"{year}-{month:02d}",
                        )

                    except Exception as e:
                        await session.rollback()
                        logger.warning(
                            "ust_voranmeldung_failed",
                            company_id=str(cid),
                            **safe_error_log(e),
                        )
                        calc_result["errors"].append({
                            "company_id": str(cid),
                            "error": safe_error_detail(e, "UStVA"),
                        })

            except Exception as e:
                logger.error("ust_task_failed", **safe_error_log(e))
                calc_result["error"] = safe_error_detail(e, "UStVA")

        return calc_result

    try:
        calc_result = asyncio.run(_calculate())
        result.update(calc_result)

        logger.info(
            "monthly_ust_task_completed",
            companies=result.get("companies_processed"),
            created=result.get("voranmeldungen_created"),
            period=f"{year}-{month:02d}",
            errors=len(result.get("errors", [])),
        )

    except Exception as e:
        logger.error("monthly_ust_task_failed", **safe_error_log(e))
        result["success"] = False
        result["error"] = safe_error_detail(e, "UStVA")

    return result


# =============================================================================
# BWA Task
# =============================================================================


@celery_app.task(
    base=CPUTask,
    name="app.workers.tasks.german_finance_tasks.generate_monthly_bwa_task",
    queue="maintenance",
    priority=2,
    ignore_result=True,
    soft_time_limit=290,
    time_limit=300,
)
def generate_monthly_bwa_task(
    company_id: Optional[str] = None,
    year: Optional[int] = None,
    month: Optional[int] = None,
    skr_schema: str = "SKR03",
) -> TaskResult:
    """
    Generiert die monatliche BWA.

    Wird am 1. jeden Monats via Celery Beat ausgeführt.
    Aggregiert Buchungsdaten des Vormonats nach SKR03/SKR04.

    Args:
        company_id: Optional - nur für bestimmte Firma
        year: Optional - Geschäftsjahr (Standard: Vormonat)
        month: Optional - Geschäftsmonat (Standard: Vormonat)
        skr_schema: SKR03 oder SKR04

    Returns:
        Dict mit Task-Ergebnissen
    """
    result: TaskResult = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "success": True,
        "task": "generate_monthly_bwa_task",
        "companies_processed": 0,
        "bwa_reports_created": 0,
        "errors": [],
    }

    # Vormonat bestimmen wenn nicht angegeben
    if year is None or month is None:
        today = date.today()
        first_of_month = today.replace(day=1)
        last_month = first_of_month - timedelta(days=1)
        year = year or last_month.year
        month = month or last_month.month

    async def _generate() -> Dict[str, Union[str, int, List[Dict[str, str]]]]:
        from sqlalchemy import select
        from app.db.session import get_async_session_context
        from app.db.models import Company
        from app.db.models_german_finance import BWAPeriod, SKRSchema
        from app.services.finance.bwa_service import get_bwa_service

        gen_result: Dict[str, Union[str, int, List[Dict[str, str]]]] = {
            "companies_processed": 0,
            "bwa_reports_created": 0,
            "errors": [],
        }

        async with get_async_session_context() as session:
            try:
                service = get_bwa_service()
                skr_enum = SKRSchema(skr_schema)

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
                        bwa = await service.generate_bwa(
                            db=session,
                            company_id=cid,
                            skr_schema=skr_enum,
                            period_type=BWAPeriod.MONTHLY,
                            year=year,
                            month=month,
                        )
                        await session.commit()

                        gen_result["companies_processed"] += 1
                        gen_result["bwa_reports_created"] += 1

                        logger.debug(
                            "bwa_generiert",
                            company_id=str(cid),
                            jahresueberschuss=bwa.jahresueberschuss,
                            period=f"{year}-{month:02d}",
                            schema=skr_schema,
                        )

                    except Exception as e:
                        await session.rollback()
                        logger.warning(
                            "bwa_generation_failed",
                            company_id=str(cid),
                            **safe_error_log(e),
                        )
                        gen_result["errors"].append({
                            "company_id": str(cid),
                            "error": safe_error_detail(e, "BWA"),
                        })

            except Exception as e:
                logger.error("bwa_task_failed", **safe_error_log(e))
                gen_result["error"] = safe_error_detail(e, "BWA")

        return gen_result

    try:
        gen_result = asyncio.run(_generate())
        result.update(gen_result)

        logger.info(
            "monthly_bwa_task_completed",
            companies=result.get("companies_processed"),
            created=result.get("bwa_reports_created"),
            period=f"{year}-{month:02d}",
            schema=skr_schema,
            errors=len(result.get("errors", [])),
        )

    except Exception as e:
        logger.error("monthly_bwa_task_failed", **safe_error_log(e))
        result["success"] = False
        result["error"] = safe_error_detail(e, "BWA")

    return result


# =============================================================================
# Cashflow Forecast Task
# =============================================================================


@celery_app.task(
    base=CPUTask,
    name="app.workers.tasks.german_finance_tasks.update_cashflow_forecast_task",
    queue="metadata",
    priority=2,
    ignore_result=True,
    soft_time_limit=290,
    time_limit=300,
)
def update_cashflow_forecast_task(
    company_id: Optional[str] = None,
    horizon_days: int = 90,
) -> TaskResult:
    """
    Aktualisiert die Cashflow-Prognose.

    Wird täglich um 06:00 via Celery Beat ausgeführt.
    Erstellt Basis-Szenario für alle aktiven Firmen.

    Args:
        company_id: Optional - nur für bestimmte Firma
        horizon_days: Prognosehorizont in Tagen

    Returns:
        Dict mit Task-Ergebnissen
    """
    result: TaskResult = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "success": True,
        "task": "update_cashflow_forecast_task",
        "companies_processed": 0,
        "forecasts_created": 0,
        "warnings_found": 0,
        "errors": [],
    }

    async def _update() -> Dict[str, Union[str, int, List[Dict[str, str]]]]:
        from sqlalchemy import select
        from app.db.session import get_async_session_context
        from app.db.models import Company
        from app.services.finance.cashflow_forecast_service import (
            get_cashflow_forecast_service,
        )

        update_result: Dict[str, Union[str, int, List[Dict[str, str]]]] = {
            "companies_processed": 0,
            "forecasts_created": 0,
            "warnings_found": 0,
            "errors": [],
        }

        async with get_async_session_context() as session:
            try:
                service = get_cashflow_forecast_service()

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
                        forecast = await service.generate_forecast(
                            db=session,
                            company_id=cid,
                            horizon_days=horizon_days,
                            scenario_type="basis",
                        )
                        await session.commit()

                        update_result["companies_processed"] += 1
                        update_result["forecasts_created"] += 1

                        if forecast.warnung_liquiditaetsengpass:
                            update_result["warnings_found"] += 1

                        logger.debug(
                            "cashflow_forecast_aktualisiert",
                            company_id=str(cid),
                            predicted_balance=forecast.predicted_balance,
                            warnung=forecast.warnung_liquiditaetsengpass,
                        )

                    except Exception as e:
                        await session.rollback()
                        logger.warning(
                            "cashflow_forecast_failed",
                            company_id=str(cid),
                            **safe_error_log(e),
                        )
                        update_result["errors"].append({
                            "company_id": str(cid),
                            "error": safe_error_detail(e, "CashflowForecast"),
                        })

            except Exception as e:
                logger.error("cashflow_forecast_task_failed", **safe_error_log(e))
                update_result["error"] = safe_error_detail(e, "CashflowForecast")

        return update_result

    try:
        update_result = asyncio.run(_update())
        result.update(update_result)

        logger.info(
            "cashflow_forecast_task_completed",
            companies=result.get("companies_processed"),
            forecasts=result.get("forecasts_created"),
            warnings=result.get("warnings_found"),
            horizon_days=horizon_days,
            errors=len(result.get("errors", [])),
        )

    except Exception as e:
        logger.error("cashflow_forecast_task_failed", **safe_error_log(e))
        result["success"] = False
        result["error"] = safe_error_detail(e, "CashflowForecast")

    return result


# =============================================================================
# Liquidity Warning Task
# =============================================================================


@celery_app.task(
    base=CPUTask,
    name="app.workers.tasks.german_finance_tasks.check_liquidity_warnings_task",
    queue="metadata",
    priority=1,
    ignore_result=True,
    soft_time_limit=230,
    time_limit=240,
)
def check_liquidity_warnings_task(
    company_id: Optional[str] = None,
) -> TaskResult:
    """
    Prüft auf drohende Liquiditätsengpaesse.

    Wird täglich um 07:00 via Celery Beat ausgeführt.
    Erstellt Alerts bei kritischen Situationen.

    Args:
        company_id: Optional - nur für bestimmte Firma

    Returns:
        Dict mit Task-Ergebnissen
    """
    result: TaskResult = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "success": True,
        "task": "check_liquidity_warnings_task",
        "companies_checked": 0,
        "warnings_found": 0,
        "critical_warnings": 0,
        "errors": [],
    }

    async def _check() -> Dict[str, Union[str, int, List[Dict[str, str]]]]:
        from sqlalchemy import select
        from app.db.session import get_async_session_context
        from app.db.models import Company
        from app.services.finance.cashflow_forecast_service import (
            get_cashflow_forecast_service,
        )

        check_result: Dict[str, Union[str, int, List[Dict[str, str]]]] = {
            "companies_checked": 0,
            "warnings_found": 0,
            "critical_warnings": 0,
            "errors": [],
        }

        async with get_async_session_context() as session:
            try:
                service = get_cashflow_forecast_service()

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
                        warning = await service.check_liquidity_warnings(
                            db=session,
                            company_id=cid,
                        )
                        await session.commit()

                        check_result["companies_checked"] += 1

                        if warning:
                            check_result["warnings_found"] += 1
                            if warning.get("severity") == "critical":
                                check_result["critical_warnings"] += 1

                            logger.info(
                                "liquiditaetswarnung_erkannt",
                                company_id=str(cid),
                                severity=warning.get("severity"),
                                engpass_datum=warning.get("engpass_datum"),
                            )

                    except Exception as e:
                        await session.rollback()
                        logger.warning(
                            "liquidity_check_failed",
                            company_id=str(cid),
                            **safe_error_log(e),
                        )
                        check_result["errors"].append({
                            "company_id": str(cid),
                            "error": safe_error_detail(e, "LiquidityCheck"),
                        })

            except Exception as e:
                logger.error("liquidity_warnings_task_failed", **safe_error_log(e))
                check_result["error"] = safe_error_detail(e, "LiquidityCheck")

        return check_result

    try:
        check_result = asyncio.run(_check())
        result.update(check_result)

        logger.info(
            "liquidity_warnings_task_completed",
            companies=result.get("companies_checked"),
            warnings=result.get("warnings_found"),
            critical=result.get("critical_warnings"),
            errors=len(result.get("errors", [])),
        )

    except Exception as e:
        logger.error("liquidity_warnings_task_failed", **safe_error_log(e))
        result["success"] = False
        result["error"] = safe_error_detail(e, "LiquidityCheck")

    return result


# =============================================================================
# Forecast Accuracy Task
# =============================================================================


@celery_app.task(
    base=CPUTask,
    name="app.workers.tasks.german_finance_tasks.compare_forecast_accuracy_task",
    queue="maintenance",
    priority=3,
    ignore_result=True,
    soft_time_limit=590,
    time_limit=600,
)
def compare_forecast_accuracy_task(
    company_id: Optional[str] = None,
) -> TaskResult:
    """
    Evaluiert die Genauigkeit der Cashflow-Prognosen.

    Wird wöchentlich (Sonntag 04:00) via Celery Beat ausgeführt.
    Vergleicht historische Prognosen mit tatsächlichen Werten.

    Args:
        company_id: Optional - nur für bestimmte Firma

    Returns:
        Dict mit Evaluations-Metriken
    """
    result: TaskResult = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "success": True,
        "task": "compare_forecast_accuracy_task",
        "companies_evaluated": 0,
        "forecasts_compared": 0,
        "errors": [],
    }

    async def _evaluate() -> Dict[str, Union[str, int, List[Dict[str, str]]]]:
        from sqlalchemy import select, and_
        from app.db.session import get_async_session_context
        from app.db.models import Company
        from app.db.models_german_finance import CashflowForecast
        from app.services.finance.cashflow_forecast_service import (
            get_cashflow_forecast_service,
        )

        eval_result: Dict[str, Union[str, int, List[Dict[str, str]]]] = {
            "companies_evaluated": 0,
            "forecasts_compared": 0,
            "comparisons": [],
            "errors": [],
        }

        async with get_async_session_context() as session:
            try:
                service = get_cashflow_forecast_service()

                # Company IDs ermitteln
                if company_id:
                    company_ids = [UUID(company_id)]
                else:
                    company_query = select(Company.id).where(
                        Company.is_active == True
                    ).limit(50)
                    company_result = await session.execute(company_query)
                    company_ids = [row[0] for row in company_result.fetchall()]

                for cid in company_ids:
                    try:
                        # Abgelaufene Prognosen finden (Horizont überschritten)
                        today = date.today()
                        expired_stmt = (
                            select(CashflowForecast.id)
                            .where(
                                and_(
                                    CashflowForecast.company_id == cid,
                                    CashflowForecast.scenario_type == "basis",
                                )
                            )
                            .order_by(CashflowForecast.forecast_date.desc())
                            .limit(10)
                        )
                        expired_result = await session.execute(expired_stmt)
                        forecast_ids = [row[0] for row in expired_result.fetchall()]

                        for fid in forecast_ids:
                            try:
                                comparison = await service.compare_forecast_accuracy(
                                    db=session,
                                    company_id=cid,
                                    forecast_id=fid,
                                )
                                if comparison.get("status") == "verfügbar":
                                    eval_result["forecasts_compared"] += 1
                            except ValueError:
                                pass

                        eval_result["companies_evaluated"] += 1

                    except Exception as e:
                        logger.warning(
                            "forecast_accuracy_failed",
                            company_id=str(cid),
                            **safe_error_log(e),
                        )
                        eval_result["errors"].append({
                            "company_id": str(cid),
                            "error": safe_error_detail(e, "ForecastAccuracy"),
                        })

            except Exception as e:
                logger.error("forecast_accuracy_task_failed", **safe_error_log(e))
                eval_result["error"] = safe_error_detail(e, "ForecastAccuracy")

        return eval_result

    try:
        eval_result = asyncio.run(_evaluate())
        result.update(eval_result)

        logger.info(
            "forecast_accuracy_task_completed",
            companies=result.get("companies_evaluated"),
            compared=result.get("forecasts_compared"),
            errors=len(result.get("errors", [])),
        )

    except Exception as e:
        logger.error("forecast_accuracy_task_failed", **safe_error_log(e))
        result["success"] = False
        result["error"] = safe_error_detail(e, "ForecastAccuracy")

    return result

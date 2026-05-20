# -*- coding: utf-8 -*-
"""
Liquidity Monitoring Celery Tasks.

Enhanced liquidity monitoring tasks:
- Daily liquidity alerts check (07:00)
- Liquidity forecast with warning thresholds
- Large outflow detection
- Critical liquidity situation notifications

Feinpoliert und durchdacht - Enterprise Liquidity Monitoring.
"""

import asyncio
import structlog
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select

from app.workers.celery_app import celery_app
from app.db.session import get_async_session_context
from app.db.models import Company
from app.core.safe_errors import safe_error_log, safe_error_detail

logger = structlog.get_logger(__name__)


# =============================================================================
# Alert Codes for Liquidity
# =============================================================================

LIQUIDITY_ALERT_CODES = {
    "shortfall": "CASH_001",  # Liquidity shortfall expected
    "large_outflow": "CASH_002",  # Unexpected large outflow detected
    "critical_balance": "CASH_003",  # Critical balance threshold reached
    "negative_forecast": "CASH_004",  # Negative balance forecasted
}


# =============================================================================
# Liquidity Check Task
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.liquidity_tasks.check_liquidity_alerts_task",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
    queue="maintenance",
)
def check_liquidity_alerts_task(
    self,
    company_id: Optional[str] = None,
    days_ahead: int = 30,
    warning_threshold_days: int = 14,
) -> Dict[str, Any]:
    """
    Checks liquidity situation for all companies.

    Runs daily at 07:00 via Celery Beat.
    Uses CashflowPredictionService to:
    - Forecast cash position for upcoming days
    - Generate CASH_001 alerts for liquidity shortfalls
    - Generate CASH_002 alerts for unexpected large outflows
    - Generate CASH_003 alerts for critical balance levels

    Args:
        company_id: Optional - only for specific company
        days_ahead: Forecast horizon in days (default: 30)
        warning_threshold_days: Days ahead for critical warnings (default: 14)

    Returns:
        Dict with statistics
    """
    async def _check_liquidity() -> Dict[str, Any]:
        async with get_async_session_context() as db:
            from app.services.ai.cashflow_prediction_service import (
                get_cashflow_prediction_service,
                WarningSeverity,
            )
            from app.services.alert_center_service import (
                AlertCenterService,
                AlertCodes,
            )
            from app.db.models_alert import AlertCategory, AlertSeverity

            stats = {
                "companies_checked": 0,
                "total_alerts_created": 0,
                "shortfall_alerts": 0,
                "large_outflow_alerts": 0,
                "critical_balance_alerts": 0,
                "companies_with_issues": [],
                "errors": [],
            }

            # Load companies
            query = select(Company).where(Company.is_active == True)
            if company_id:
                query = query.where(Company.id == UUID(company_id))

            result = await db.execute(query)
            companies = result.scalars().all()

            for company in companies:
                stats["companies_checked"] += 1
                company_alerts = {
                    "shortfall": 0,
                    "large_outflow": 0,
                    "critical_balance": 0,
                }

                try:
                    cashflow_service = get_cashflow_prediction_service(db)
                    alert_service = AlertCenterService(db)

                    # Get cashflow forecast
                    forecasts = await cashflow_service.get_cashflow_forecast(
                        company_id=company.id,
                        days=days_ahead,
                    )

                    # Get cashflow warnings
                    warnings = await cashflow_service.get_cashflow_warnings(
                        company_id=company.id,
                        days=days_ahead,
                    )

                    # Process warnings and create alerts
                    for warning in warnings:
                        # Determine alert code and severity based on warning type
                        if warning.severity == WarningSeverity.CRITICAL:
                            severity = AlertSeverity.CRITICAL
                        elif warning.severity == WarningSeverity.HIGH:
                            severity = AlertSeverity.HIGH
                        else:
                            severity = AlertSeverity.MEDIUM

                        # Check if this is within the warning threshold
                        days_until = (warning.date - datetime.now(timezone.utc).date()).days
                        if days_until <= warning_threshold_days:
                            severity = AlertSeverity.CRITICAL

                        # Create alert based on warning type
                        alert_code = LIQUIDITY_ALERT_CODES.get(
                            warning.type.value, "CASH_001"
                        )

                        await alert_service.create_alert(
                            company_id=company.id,
                            alert_code=alert_code,
                            category=AlertCategory.RISK,
                            severity=severity,
                            title=_get_alert_title(warning.type.value, days_until),
                            message=warning.message,
                            metadata={
                                "warning_type": warning.type.value,
                                "date": warning.date.isoformat(),
                                "predicted_balance": float(warning.predicted_balance),
                                "days_until": days_until,
                            },
                            context={
                                "suggested_actions": warning.suggested_actions,
                                "forecast_period_days": days_ahead,
                            },
                            recurrence_key=f"liquidity_{company.id}_{warning.type.value}_{warning.date.isoformat()}",
                            auto_dismiss_hours=48,
                        )

                        stats["total_alerts_created"] += 1

                        if "shortfall" in warning.type.value.lower():
                            company_alerts["shortfall"] += 1
                            stats["shortfall_alerts"] += 1
                        elif "outflow" in warning.type.value.lower():
                            company_alerts["large_outflow"] += 1
                            stats["large_outflow_alerts"] += 1
                        else:
                            company_alerts["critical_balance"] += 1
                            stats["critical_balance_alerts"] += 1

                    # Check for negative balance in forecast
                    negative_days = [
                        f for f in forecasts
                        if f.predicted_balance < 0
                    ]

                    if negative_days:
                        first_negative = min(negative_days, key=lambda x: x.date)
                        days_until = (first_negative.date - datetime.now(timezone.utc).date()).days

                        await alert_service.create_alert(
                            company_id=company.id,
                            alert_code="CASH_004",
                            category=AlertCategory.RISK,
                            severity=AlertSeverity.CRITICAL if days_until <= 7 else AlertSeverity.HIGH,
                            title=f"Negativer Kontostand in {days_until} Tagen erwartet",
                            message=(
                                f"Die Prognose zeigt einen negativen Kontostand von "
                                f"{first_negative.predicted_balance:,.2f} EUR am {first_negative.date}."
                            ),
                            metadata={
                                "first_negative_date": first_negative.date.isoformat(),
                                "predicted_balance": float(first_negative.predicted_balance),
                                "days_until": days_until,
                                "total_negative_days": len(negative_days),
                            },
                            recurrence_key=f"negative_balance_{company.id}_{first_negative.date.isoformat()}",
                            auto_dismiss_hours=24,
                        )
                        stats["total_alerts_created"] += 1

                    # Track companies with issues
                    if sum(company_alerts.values()) > 0:
                        stats["companies_with_issues"].append({
                            "company_id": str(company.id),
                            "alerts": company_alerts,
                        })

                    await db.commit()

                except Exception as e:
                    stats["errors"].append({
                        "company_id": str(company.id),
                        "error": safe_error_detail(e, "Liquidity check"),
                    })
                    logger.warning(
                        "liquidity_check_failed_for_company",
                        company_id=str(company.id),
                        **safe_error_log(e),
                    )

            return stats

    try:
        result = asyncio.run(_check_liquidity())
        logger.info(
            "liquidity_check_task_completed",
            companies_checked=result["companies_checked"],
            total_alerts=result["total_alerts_created"],
            shortfall_alerts=result["shortfall_alerts"],
            large_outflow_alerts=result["large_outflow_alerts"],
            critical_balance_alerts=result["critical_balance_alerts"],
            companies_with_issues=len(result["companies_with_issues"]),
            errors=len(result["errors"]),
        )
        return result
    except Exception as e:
        logger.error("liquidity_check_task_failed", **safe_error_log(e))
        raise self.retry(exc=e)


def _get_alert_title(warning_type: str, days_until: int) -> str:
    """Generate German alert title based on warning type and urgency."""
    urgency = "KRITISCH" if days_until <= 7 else "Warnung"

    titles = {
        "shortfall": f"{urgency}: Liquiditätsengpass in {days_until} Tagen",
        "large_outflow": f"{urgency}: Grosse Zahlung in {days_until} Tagen fällig",
        "critical_balance": f"{urgency}: Kritischer Kontostand erwartet",
        "negative_forecast": f"{urgency}: Negativer Saldo in {days_until} Tagen",
    }

    return titles.get(warning_type, f"Liquiditätswarnung in {days_until} Tagen")


# =============================================================================
# Large Outflow Detection Task
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.liquidity_tasks.detect_large_outflows_task",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
    queue="maintenance",
)
def detect_large_outflows_task(
    self,
    company_id: Optional[str] = None,
    days_ahead: int = 14,
    threshold_percentage: float = 20.0,
) -> Dict[str, Any]:
    """
    Detects unusually large upcoming outflows.

    Runs daily at 07:30 via Celery Beat.
    Identifies outflows that exceed the configured percentage of average monthly outflow.

    Args:
        company_id: Optional - only for specific company
        days_ahead: Days to look ahead (default: 14)
        threshold_percentage: Percentage threshold for large outflows (default: 20%)

    Returns:
        Dict with statistics
    """
    async def _detect_outflows() -> Dict[str, Any]:
        async with get_async_session_context() as db:
            from app.services.ai.cashflow_prediction_service import (
                get_cashflow_prediction_service,
            )
            from app.services.alert_center_service import AlertCenterService
            from app.db.models_alert import AlertCategory, AlertSeverity

            stats = {
                "companies_checked": 0,
                "large_outflows_detected": 0,
                "alerts_created": 0,
                "total_amount_flagged": Decimal("0"),
                "errors": [],
            }

            # Load companies
            query = select(Company).where(Company.is_active == True)
            if company_id:
                query = query.where(Company.id == UUID(company_id))

            result = await db.execute(query)
            companies = result.scalars().all()

            for company in companies:
                stats["companies_checked"] += 1

                try:
                    cashflow_service = get_cashflow_prediction_service(db)
                    alert_service = AlertCenterService(db)

                    # Get upcoming large outflows
                    large_outflows = await cashflow_service.get_large_outflows(
                        company_id=company.id,
                        days=days_ahead,
                        threshold_percentage=threshold_percentage,
                    )

                    for outflow in large_outflows:
                        stats["large_outflows_detected"] += 1
                        stats["total_amount_flagged"] += Decimal(str(outflow.amount))

                        days_until = (outflow.date - datetime.now(timezone.utc).date()).days

                        await alert_service.create_alert(
                            company_id=company.id,
                            alert_code="CASH_002",
                            category=AlertCategory.RISK,
                            severity=AlertSeverity.HIGH if days_until <= 3 else AlertSeverity.MEDIUM,
                            title=f"Grosse Zahlung in {days_until} Tagen: {outflow.amount:,.2f} EUR",
                            message=(
                                f"Eine überdurchschnittlich grosse Zahlung von {outflow.amount:,.2f} EUR "
                                f"ist am {outflow.date} fällig. Dies entspricht {outflow.percentage_of_average:.1f}% "
                                f"des monatlichen Durchschnitts."
                            ),
                            metadata={
                                "amount": float(outflow.amount),
                                "date": outflow.date.isoformat(),
                                "percentage_of_average": outflow.percentage_of_average,
                                "days_until": days_until,
                                "description": outflow.description,
                            },
                            recurrence_key=f"large_outflow_{company.id}_{outflow.date.isoformat()}_{outflow.amount}",
                            auto_dismiss_hours=24,
                        )
                        stats["alerts_created"] += 1

                    await db.commit()

                except Exception as e:
                    stats["errors"].append({
                        "company_id": str(company.id),
                        "error": safe_error_detail(e, "Large outflow detection"),
                    })
                    logger.warning(
                        "large_outflow_detection_failed",
                        company_id=str(company.id),
                        **safe_error_log(e),
                    )

            stats["total_amount_flagged"] = float(stats["total_amount_flagged"])
            return stats

    try:
        result = asyncio.run(_detect_outflows())
        logger.info(
            "large_outflow_detection_completed",
            companies_checked=result["companies_checked"],
            outflows_detected=result["large_outflows_detected"],
            alerts_created=result["alerts_created"],
            total_amount=result["total_amount_flagged"],
            errors=len(result["errors"]),
        )
        return result
    except Exception as e:
        logger.error("large_outflow_detection_failed", **safe_error_log(e))
        raise self.retry(exc=e)


# =============================================================================
# Liquidity Summary Report Task
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.liquidity_tasks.generate_liquidity_summary_task",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
    queue="maintenance",
)
def generate_liquidity_summary_task(
    self,
    company_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generates weekly liquidity summary report.

    Runs weekly on Monday at 07:00 via Celery Beat.
    Provides overview of:
    - Current cash position
    - 30-day forecast summary
    - Risk assessment
    - Recommendations

    Args:
        company_id: Optional - only for specific company

    Returns:
        Dict with summary data
    """
    async def _generate_summary() -> Dict[str, Any]:
        async with get_async_session_context() as db:
            from app.services.ai.cashflow_prediction_service import (
                get_cashflow_prediction_service,
            )

            stats = {
                "companies_processed": 0,
                "summaries_generated": 0,
                "high_risk_companies": 0,
                "errors": [],
            }

            # Load companies
            query = select(Company).where(Company.is_active == True)
            if company_id:
                query = query.where(Company.id == UUID(company_id))

            result = await db.execute(query)
            companies = result.scalars().all()

            for company in companies:
                stats["companies_processed"] += 1

                try:
                    cashflow_service = get_cashflow_prediction_service(db)

                    # Get summary metrics
                    summary = await cashflow_service.get_liquidity_summary(
                        company_id=company.id,
                        days=30,
                    )

                    if summary:
                        stats["summaries_generated"] += 1

                        if summary.risk_level in ("high", "critical"):
                            stats["high_risk_companies"] += 1

                        logger.debug(
                            "liquidity_summary_generated",
                            company_id=str(company.id),
                            current_balance=float(summary.current_balance),
                            min_forecast_balance=float(summary.min_forecast_balance),
                            risk_level=summary.risk_level,
                        )

                except Exception as e:
                    stats["errors"].append({
                        "company_id": str(company.id),
                        "error": safe_error_detail(e, "Summary generation"),
                    })
                    logger.warning(
                        "liquidity_summary_generation_failed",
                        company_id=str(company.id),
                        **safe_error_log(e),
                    )

            return stats

    try:
        result = asyncio.run(_generate_summary())
        logger.info(
            "liquidity_summary_task_completed",
            companies_processed=result["companies_processed"],
            summaries_generated=result["summaries_generated"],
            high_risk_companies=result["high_risk_companies"],
            errors=len(result["errors"]),
        )
        return result
    except Exception as e:
        logger.error("liquidity_summary_task_failed", **safe_error_log(e))
        raise self.retry(exc=e)

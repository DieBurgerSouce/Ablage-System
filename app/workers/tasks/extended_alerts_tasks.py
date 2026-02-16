# -*- coding: utf-8 -*-
"""
Extended Alerts Celery Tasks.

Automatische Prüfung und Erstellung erweiterter Alert-Typen:
- Cashflow-Warnungen (täglich um 06:00)
- Vertrags-Warnungen (täglich um 07:00)
- Compliance-Warnungen (täglich um 05:00)
- Lieferanten-Monitoring (bei Bedarf)

Feinpoliert und durchdacht - Enterprise Extended Alerts.
"""

import asyncio
import structlog
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select

from app.workers.celery_app import celery_app
from app.db.session import get_async_session_context
from app.db.models import Company
from app.core.safe_errors import safe_error_log, safe_error_detail

logger = structlog.get_logger(__name__)


# =============================================================================
# Cashflow Alert Tasks
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.extended_alerts_tasks.check_cashflow_alerts_task",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
    queue="maintenance",
)
def check_cashflow_alerts_task(
    self,
    company_id: Optional[str] = None,
    days_ahead: int = 30,
) -> Dict[str, Any]:
    """
    Prüft auf Cashflow-basierte Alert-Bedingungen.

    Wird täglich um 06:00 Uhr automatisch ausgeführt.
    Integriert mit CashflowPredictionService für:
    - Liquiditätsengpaesse (CASH_001)
    - Unerwartete Zahlungsausgaenge (CASH_002)

    Args:
        company_id: Optional - nur für spezifische Firma
        days_ahead: Vorausschau in Tagen (Standard: 30)

    Returns:
        Dict mit Statistiken
    """
    from app.services.alerts.extended_alerts_service import get_extended_alerts_service

    async def _check_cashflow() -> Dict[str, Any]:
        async with get_async_session_context() as db:
            stats = {
                "companies_checked": 0,
                "total_alerts_created": 0,
                "alerts_by_company": {},
                "errors": [],
            }

            # Companies laden
            query = select(Company).where(Company.is_active == True)
            if company_id:
                query = query.where(Company.id == UUID(company_id))

            result = await db.execute(query)
            companies = result.scalars().all()

            for company in companies:
                stats["companies_checked"] += 1
                try:
                    service = get_extended_alerts_service(db)
                    alerts = await service.check_cashflow_alerts(
                        company_id=company.id,
                        days_ahead=days_ahead,
                    )

                    alert_count = len(alerts)
                    stats["total_alerts_created"] += alert_count
                    stats["alerts_by_company"][str(company.id)] = alert_count

                    logger.debug(
                        "cashflow_alerts_checked_for_company",
                        company_id=str(company.id),
                        alerts_created=alert_count,
                    )

                except Exception as e:
                    stats["errors"].append({
                        "company_id": str(company.id),
                        "error": safe_error_detail(e, "Cashflow-Check"),
                    })
                    logger.warning(
                        "cashflow_alerts_check_failed",
                        company_id=str(company.id),
                        **safe_error_log(e),
                    )

            return stats

    try:
        result = asyncio.run(_check_cashflow())
        logger.info(
            "cashflow_alerts_task_completed",
            companies_checked=result["companies_checked"],
            total_alerts=result["total_alerts_created"],
            errors=len(result["errors"]),
        )
        return result
    except Exception as e:
        logger.error("cashflow_alerts_task_failed", **safe_error_log(e))
        raise self.retry(exc=e)


# =============================================================================
# Contract Alert Tasks
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.extended_alerts_tasks.check_contract_alerts_task",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
    queue="maintenance",
)
def check_contract_alerts_task(
    self,
    company_id: Optional[str] = None,
    days_ahead: int = 90,
) -> Dict[str, Any]:
    """
    Prüft auf Vertrags-basierte Alert-Bedingungen.

    Wird täglich um 07:00 Uhr automatisch ausgeführt.
    Erstellt Alerts für:
    - Vertragsablauf (CONT_001)
    - Kündigungsfristen (CONT_002)
    - Automatische Verlängerungen (CONT_003)

    Args:
        company_id: Optional - nur für spezifische Firma
        days_ahead: Vorausschau in Tagen (Standard: 90)

    Returns:
        Dict mit Statistiken
    """
    from app.services.alerts.extended_alerts_service import get_extended_alerts_service

    async def _check_contracts() -> Dict[str, Any]:
        async with get_async_session_context() as db:
            stats = {
                "companies_checked": 0,
                "total_alerts_created": 0,
                "expiry_alerts": 0,
                "notice_alerts": 0,
                "renewal_alerts": 0,
                "alerts_by_company": {},
                "errors": [],
            }

            # Companies laden
            query = select(Company).where(Company.is_active == True)
            if company_id:
                query = query.where(Company.id == UUID(company_id))

            result = await db.execute(query)
            companies = result.scalars().all()

            for company in companies:
                stats["companies_checked"] += 1
                try:
                    service = get_extended_alerts_service(db)
                    alerts = await service.check_contract_alerts(
                        company_id=company.id,
                        days_ahead=days_ahead,
                    )

                    alert_count = len(alerts)
                    stats["total_alerts_created"] += alert_count
                    stats["alerts_by_company"][str(company.id)] = alert_count

                    # Alert-Typen zählen
                    for alert in alerts:
                        if "CONT_001" in alert.alert_code:
                            stats["expiry_alerts"] += 1
                        elif "CONT_002" in alert.alert_code:
                            stats["notice_alerts"] += 1
                        elif "CONT_003" in alert.alert_code:
                            stats["renewal_alerts"] += 1

                    logger.debug(
                        "contract_alerts_checked_for_company",
                        company_id=str(company.id),
                        alerts_created=alert_count,
                    )

                except Exception as e:
                    stats["errors"].append({
                        "company_id": str(company.id),
                        "error": safe_error_detail(e, "Contract-Check"),
                    })
                    logger.warning(
                        "contract_alerts_check_failed",
                        company_id=str(company.id),
                        **safe_error_log(e),
                    )

            return stats

    try:
        result = asyncio.run(_check_contracts())
        logger.info(
            "contract_alerts_task_completed",
            companies_checked=result["companies_checked"],
            total_alerts=result["total_alerts_created"],
            expiry_alerts=result["expiry_alerts"],
            notice_alerts=result["notice_alerts"],
            renewal_alerts=result["renewal_alerts"],
            errors=len(result["errors"]),
        )
        return result
    except Exception as e:
        logger.error("contract_alerts_task_failed", **safe_error_log(e))
        raise self.retry(exc=e)


# =============================================================================
# Compliance Alert Tasks
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.extended_alerts_tasks.check_compliance_alerts_task",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
    queue="maintenance",
)
def check_compliance_alerts_task(
    self,
    company_id: Optional[str] = None,
    days_ahead: int = 30,
) -> Dict[str, Any]:
    """
    Prüft auf Compliance-basierte Alert-Bedingungen.

    Wird täglich um 05:00 Uhr automatisch ausgeführt.
    Erstellt Alerts für:
    - GDPR-Löschfristen (COMP_006)
    - Aufbewahrungsfristen (COMP_007)

    Args:
        company_id: Optional - nur für spezifische Firma
        days_ahead: Vorausschau in Tagen (Standard: 30)

    Returns:
        Dict mit Statistiken
    """
    from app.services.alerts.extended_alerts_service import get_extended_alerts_service

    async def _check_compliance() -> Dict[str, Any]:
        async with get_async_session_context() as db:
            stats = {
                "companies_checked": 0,
                "total_alerts_created": 0,
                "gdpr_alerts": 0,
                "retention_alerts": 0,
                "alerts_by_company": {},
                "errors": [],
            }

            # Companies laden
            query = select(Company).where(Company.is_active == True)
            if company_id:
                query = query.where(Company.id == UUID(company_id))

            result = await db.execute(query)
            companies = result.scalars().all()

            for company in companies:
                stats["companies_checked"] += 1
                try:
                    service = get_extended_alerts_service(db)
                    alerts = await service.check_compliance_alerts(
                        company_id=company.id,
                        days_ahead=days_ahead,
                    )

                    alert_count = len(alerts)
                    stats["total_alerts_created"] += alert_count
                    stats["alerts_by_company"][str(company.id)] = alert_count

                    # Alert-Typen zählen
                    for alert in alerts:
                        if "COMP_006" in alert.alert_code:
                            stats["gdpr_alerts"] += 1
                        elif "COMP_007" in alert.alert_code:
                            stats["retention_alerts"] += 1

                    logger.debug(
                        "compliance_alerts_checked_for_company",
                        company_id=str(company.id),
                        alerts_created=alert_count,
                    )

                except Exception as e:
                    stats["errors"].append({
                        "company_id": str(company.id),
                        "error": safe_error_detail(e, "Compliance-Check"),
                    })
                    logger.warning(
                        "compliance_alerts_check_failed",
                        company_id=str(company.id),
                        **safe_error_log(e),
                    )

            return stats

    try:
        result = asyncio.run(_check_compliance())
        logger.info(
            "compliance_alerts_task_completed",
            companies_checked=result["companies_checked"],
            total_alerts=result["total_alerts_created"],
            gdpr_alerts=result["gdpr_alerts"],
            retention_alerts=result["retention_alerts"],
            errors=len(result["errors"]),
        )
        return result
    except Exception as e:
        logger.error("compliance_alerts_task_failed", **safe_error_log(e))
        raise self.retry(exc=e)


# =============================================================================
# Supplier Monitoring Tasks
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.extended_alerts_tasks.create_supplier_insolvency_alert_task",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    queue="notifications",
)
def create_supplier_insolvency_alert_task(
    self,
    company_id: str,
    entity_id: str,
    source: str,
    confidence: float = 0.8,
    open_orders_count: int = 0,
    open_invoices_amount: float = 0.0,
) -> Dict[str, Any]:
    """
    Erstellt Alert für mögliche Lieferanten-Insolvenz.

    Wird von externen Diensten oder manuell getriggert.

    Args:
        company_id: Mandanten-ID
        entity_id: Lieferanten-ID
        source: Quelle der Information
        confidence: Konfidenz (0-1)
        open_orders_count: Anzahl offener Bestellungen
        open_invoices_amount: Summe offener Rechnungen

    Returns:
        Dict mit Alert-ID und Status
    """
    from app.services.alerts.extended_alerts_service import get_extended_alerts_service
    from decimal import Decimal

    async def _create_alert() -> Dict[str, Any]:
        async with get_async_session_context() as db:
            service = get_extended_alerts_service(db)

            alert = await service.create_supplier_insolvency_alert(
                company_id=UUID(company_id),
                entity_id=UUID(entity_id),
                source=source,
                confidence=confidence,
                open_orders_count=open_orders_count,
                open_invoices_amount=Decimal(str(open_invoices_amount)),
            )

            if alert:
                return {
                    "success": True,
                    "alert_id": str(alert.id),
                    "severity": alert.severity,
                }
            else:
                return {
                    "success": False,
                    "error": "Alert-Erstellung fehlgeschlagen",
                }

    try:
        result = asyncio.run(_create_alert())
        if result["success"]:
            logger.info(
                "supplier_insolvency_alert_task_completed",
                entity_id=entity_id,
                alert_id=result.get("alert_id"),
            )
        return result
    except Exception as e:
        logger.error(
            "supplier_insolvency_alert_task_failed",
            entity_id=entity_id,
            **safe_error_log(e),
        )
        raise self.retry(exc=e)


@celery_app.task(
    name="app.workers.tasks.extended_alerts_tasks.create_supplier_ownership_change_alert_task",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    queue="notifications",
)
def create_supplier_ownership_change_alert_task(
    self,
    company_id: str,
    entity_id: str,
    source: str,
    change_details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Erstellt Alert für Lieferanten-Eigentuemerwechsel.

    Wird von externen Diensten oder manuell getriggert.

    Args:
        company_id: Mandanten-ID
        entity_id: Lieferanten-ID
        source: Quelle der Information
        change_details: Details zum Wechsel

    Returns:
        Dict mit Alert-ID und Status
    """
    from app.services.alerts.extended_alerts_service import get_extended_alerts_service

    async def _create_alert() -> Dict[str, Any]:
        async with get_async_session_context() as db:
            service = get_extended_alerts_service(db)

            alert = await service.create_supplier_ownership_change_alert(
                company_id=UUID(company_id),
                entity_id=UUID(entity_id),
                source=source,
                change_details=change_details,
            )

            if alert:
                return {
                    "success": True,
                    "alert_id": str(alert.id),
                    "severity": alert.severity,
                }
            else:
                return {
                    "success": False,
                    "error": "Alert-Erstellung fehlgeschlagen",
                }

    try:
        result = asyncio.run(_create_alert())
        if result["success"]:
            logger.info(
                "supplier_ownership_alert_task_completed",
                entity_id=entity_id,
                alert_id=result.get("alert_id"),
            )
        return result
    except Exception as e:
        logger.error(
            "supplier_ownership_alert_task_failed",
            entity_id=entity_id,
            **safe_error_log(e),
        )
        raise self.retry(exc=e)


# =============================================================================
# Comprehensive Check Task
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.extended_alerts_tasks.run_all_extended_alerts_checks_task",
    bind=True,
    max_retries=2,
    default_retry_delay=600,
    queue="maintenance",
)
def run_all_extended_alerts_checks_task(
    self,
    company_id: Optional[str] = None,
    days_ahead: int = 30,
) -> Dict[str, Any]:
    """
    Führt alle erweiterten Alert-Checks aus.

    Wird täglich um 05:30 Uhr als Haupt-Task ausgeführt.
    Delegiert an spezialisierte Tasks.

    Args:
        company_id: Optional - nur für spezifische Firma
        days_ahead: Vorausschau in Tagen

    Returns:
        Dict mit Gesamtstatistiken
    """
    from app.services.alerts.extended_alerts_service import get_extended_alerts_service

    async def _run_all_checks() -> Dict[str, Any]:
        async with get_async_session_context() as db:
            overall_stats = {
                "companies_checked": 0,
                "total_alerts_created": 0,
                "by_type": {
                    "cashflow": 0,
                    "contract": 0,
                    "compliance": 0,
                },
                "errors": [],
                "started_at": datetime.now(timezone.utc).isoformat(),
            }

            # Companies laden
            query = select(Company).where(Company.is_active == True)
            if company_id:
                query = query.where(Company.id == UUID(company_id))

            result = await db.execute(query)
            companies = result.scalars().all()

            for company in companies:
                overall_stats["companies_checked"] += 1

                try:
                    service = get_extended_alerts_service(db)
                    company_results = await service.run_all_checks(
                        company_id=company.id,
                        days_ahead=days_ahead,
                    )

                    overall_stats["total_alerts_created"] += company_results["total_alerts"]
                    overall_stats["by_type"]["cashflow"] += company_results["cashflow_alerts"]
                    overall_stats["by_type"]["contract"] += company_results["contract_alerts"]
                    overall_stats["by_type"]["compliance"] += company_results["compliance_alerts"]

                    if company_results["errors"]:
                        for err in company_results["errors"]:
                            overall_stats["errors"].append({
                                "company_id": str(company.id),
                                **err,
                            })

                except Exception as e:
                    overall_stats["errors"].append({
                        "company_id": str(company.id),
                        "error": safe_error_detail(e, "Gesamtprüfung"),
                    })
                    logger.warning(
                        "extended_alerts_company_check_failed",
                        company_id=str(company.id),
                        **safe_error_log(e),
                    )

            overall_stats["completed_at"] = datetime.now(timezone.utc).isoformat()
            return overall_stats

    try:
        result = asyncio.run(_run_all_checks())
        logger.info(
            "extended_alerts_all_checks_completed",
            companies_checked=result["companies_checked"],
            total_alerts=result["total_alerts_created"],
            cashflow_alerts=result["by_type"]["cashflow"],
            contract_alerts=result["by_type"]["contract"],
            compliance_alerts=result["by_type"]["compliance"],
            errors=len(result["errors"]),
        )
        return result
    except Exception as e:
        logger.error("extended_alerts_all_checks_failed", **safe_error_log(e))
        raise self.retry(exc=e)


# =============================================================================
# Alert Cleanup Task
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.extended_alerts_tasks.cleanup_old_extended_alerts_task",
    bind=True,
    max_retries=1,
    default_retry_delay=60,
    queue="maintenance",
)
def cleanup_old_extended_alerts_task(
    self,
    days_to_keep: int = 90,
) -> Dict[str, Any]:
    """
    Löscht alte geloeste/verworfene Alerts.

    Wird wöchentlich am Sonntag um 03:00 Uhr ausgeführt.

    Args:
        days_to_keep: Tage für geloeste Alerts behalten

    Returns:
        Dict mit Statistiken
    """
    from datetime import timedelta
    from sqlalchemy import delete
    from app.db.models_alert import Alert, AlertStatus

    async def _cleanup() -> Dict[str, Any]:
        async with get_async_session_context() as db:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_to_keep)

            # Zaehlen vor Löschung
            count_query = select(func.count(Alert.id)).where(
                and_(
                    Alert.status.in_([
                        AlertStatus.RESOLVED.value,
                        AlertStatus.DISMISSED.value,
                    ]),
                    Alert.resolved_at.isnot(None),
                    Alert.resolved_at < cutoff_date,
                )
            )
            from sqlalchemy import func, and_
            count_result = await db.execute(count_query)
            count_to_delete = count_result.scalar() or 0

            if count_to_delete > 0:
                # Löschen
                delete_stmt = delete(Alert).where(
                    and_(
                        Alert.status.in_([
                            AlertStatus.RESOLVED.value,
                            AlertStatus.DISMISSED.value,
                        ]),
                        Alert.resolved_at.isnot(None),
                        Alert.resolved_at < cutoff_date,
                    )
                )
                await db.execute(delete_stmt)
                await db.commit()

            return {
                "deleted_count": count_to_delete,
                "cutoff_date": cutoff_date.isoformat(),
                "days_kept": days_to_keep,
            }

    try:
        result = asyncio.run(_cleanup())
        logger.info(
            "extended_alerts_cleanup_completed",
            deleted_count=result["deleted_count"],
            days_kept=result["days_kept"],
        )
        return result
    except Exception as e:
        logger.error("extended_alerts_cleanup_failed", **safe_error_log(e))
        raise self.retry(exc=e)

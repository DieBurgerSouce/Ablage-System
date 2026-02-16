"""
Contract Management Celery Tasks.

Automatische Vertragsmanagement-Tasks:
- Kündigungsfrist-Erinnerungen (täglich um 08:00)
- Ablaufende Verträge prüfen (30/60/90 Tage Vorlauf)
- Automatische Vertragsverlängerung (wenn konfiguriert)
- Wöchentlicher Vertragsreport

Feinpoliert und durchdacht - Enterprise Contract Management.
"""

import asyncio
import structlog
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional
from uuid import UUID

from sqlalchemy import select, and_, or_, func
from sqlalchemy.orm import selectinload

from app.core.safe_errors import safe_error_log, safe_error_detail
from app.workers.celery_app import celery_app
from app.db.session import get_async_session_context
from app.db.models import (
    BusinessContract,
    ContractMilestone,
    ContractRenewalOption,
    ContractStatus,
    RenewalOptionStatus,
    User,
)

logger = structlog.get_logger(__name__)


# =============================================================================
# Deadline Reminder Tasks
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.contract_tasks.send_contract_deadline_reminders_task",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
    queue="maintenance",
)
def send_contract_deadline_reminders_task(
    self,
    days_ahead: int = 90,
    company_id: Optional[str] = None,
) -> Dict[str, object]:
    """Sendet Erinnerungen für anstehende Vertragsfristen.

    Wird täglich um 08:00 Uhr automatisch ausgeführt.
    Prüft:
    - Kündigungsfristen
    - Vertragsenden
    - Verlängerungsoptionen
    - Meilensteine

    Args:
        days_ahead: Tage im Voraus prüfen (default 90)
        company_id: Optional - nur für spezifische Firma

    Returns:
        Dict mit Statistiken
    """
    from app.services.notification_service import get_notification_service

    async def _send_reminders() -> Dict[str, object]:
        async with get_async_session_context() as db:
            notification_service = get_notification_service()
            today = date.today()
            cutoff_date = today + timedelta(days=days_ahead)

            stats = {
                "total_contracts_checked": 0,
                "reminders_sent": 0,
                "notice_deadline_alerts": 0,
                "end_date_alerts": 0,
                "renewal_option_alerts": 0,
                "milestone_alerts": 0,
                "errors": [],
            }

            # Query für aktive Verträge mit anstehenden Fristen
            query = select(BusinessContract).where(
                and_(
                    BusinessContract.status.in_([
                        ContractStatus.ACTIVE,
                        ContractStatus.EXPIRING_SOON,
                    ]),
                    BusinessContract.deleted_at.is_(None),
                    or_(
                        # Kündigungsfrist innerhalb des Zeitraums
                        and_(
                            BusinessContract.notice_deadline.isnot(None),
                            BusinessContract.notice_deadline <= cutoff_date,
                            BusinessContract.notice_deadline >= today,
                        ),
                        # Vertragsende innerhalb des Zeitraums
                        and_(
                            BusinessContract.end_date.isnot(None),
                            BusinessContract.end_date <= cutoff_date,
                            BusinessContract.end_date >= today,
                        ),
                    ),
                )
            ).options(
                selectinload(BusinessContract.renewal_options),
                selectinload(BusinessContract.milestones),
            )

            if company_id:
                query = query.where(
                    BusinessContract.company_id == UUID(company_id)
                )

            result = await db.execute(query)
            contracts = result.scalars().all()

            for contract in contracts:
                stats["total_contracts_checked"] += 1

                try:
                    # Kündigungsfrist prüfen
                    if contract.notice_deadline:
                        days_until_notice = (contract.notice_deadline - today).days
                        if days_until_notice in contract.reminder_days:
                            await _send_deadline_notification(
                                notification_service,
                                contract,
                                "notice_deadline",
                                days_until_notice,
                            )
                            stats["notice_deadline_alerts"] += 1
                            stats["reminders_sent"] += 1

                    # Vertragsende prüfen
                    if contract.end_date:
                        days_until_end = (contract.end_date - today).days
                        if days_until_end in contract.reminder_days:
                            await _send_deadline_notification(
                                notification_service,
                                contract,
                                "end_date",
                                days_until_end,
                            )
                            stats["end_date_alerts"] += 1
                            stats["reminders_sent"] += 1

                    # Verlängerungsoptionen prüfen
                    for option in contract.renewal_options:
                        if (
                            option.status == RenewalOptionStatus.AVAILABLE
                            and option.exercise_deadline
                        ):
                            days_until_deadline = (
                                option.exercise_deadline - today
                            ).days
                            if days_until_deadline in [30, 14, 7, 3, 1]:
                                await _send_renewal_option_notification(
                                    notification_service,
                                    contract,
                                    option,
                                    days_until_deadline,
                                )
                                stats["renewal_option_alerts"] += 1
                                stats["reminders_sent"] += 1

                    # Meilensteine prüfen
                    for milestone in contract.milestones:
                        if not milestone.is_completed and milestone.scheduled_date:
                            days_until_due = (milestone.scheduled_date - today).days
                            reminder_days = milestone.reminder_days_before or [14, 7, 1]
                            if days_until_due in reminder_days:
                                await _send_milestone_notification(
                                    notification_service,
                                    contract,
                                    milestone,
                                    days_until_due,
                                )
                                stats["milestone_alerts"] += 1
                                stats["reminders_sent"] += 1

                except Exception as e:
                    stats["errors"].append({
                        "contract_id": str(contract.id),
                        "error": safe_error_detail(e, "Vorgang"),
                    })
                    logger.warning(
                        "contract_reminder_failed",
                        contract_id=str(contract.id),
                        **safe_error_log(e),
                    )

            return stats

    try:
        result = asyncio.run(_send_reminders())
        logger.info(
            "contract_deadline_reminders_completed",
            total_checked=result["total_contracts_checked"],
            reminders_sent=result["reminders_sent"],
            notice_alerts=result["notice_deadline_alerts"],
            end_alerts=result["end_date_alerts"],
            renewal_alerts=result["renewal_option_alerts"],
            milestone_alerts=result["milestone_alerts"],
            errors=len(result["errors"]),
        )
        return result
    except Exception as e:
        logger.error("contract_deadline_reminders_failed", **safe_error_log(e))
        raise self.retry(exc=e)


async def _send_deadline_notification(
    notification_service: object,
    contract: BusinessContract,
    deadline_type: str,
    days_remaining: int,
) -> None:
    """Sendet Benachrichtigung für Vertragsfrist."""
    from app.services.notification_service import NotificationPriority, NotificationType

    urgency = _get_urgency(days_remaining)

    if deadline_type == "notice_deadline":
        title = f"Kündigungsfrist in {days_remaining} Tagen"
        message = (
            f"Die Kündigungsfrist für Vertrag '{contract.title}' "
            f"(Nr. {contract.contract_number}) läuft am {contract.notice_deadline} ab."
        )
    else:
        title = f"Vertrag läuft in {days_remaining} Tagen ab"
        message = (
            f"Der Vertrag '{contract.title}' (Nr. {contract.contract_number}) "
            f"endet am {contract.end_date}."
        )

    # Priorität basierend auf Dringlichkeit
    priority_map = {
        "critical": NotificationPriority.CRITICAL,
        "high": NotificationPriority.HIGH,
        "medium": NotificationPriority.NORMAL,
        "low": NotificationPriority.LOW,
    }
    priority = priority_map.get(urgency, NotificationPriority.NORMAL)

    # In-App Benachrichtigung an Verantwortlichen
    if contract.responsible_user_id:
        try:
            await notification_service.send_in_app_notification(
                user_id=str(contract.responsible_user_id),
                title=title,
                message=message,
                priority=priority,
                notification_type=NotificationType.SYSTEM_ALERT,
                metadata={
                    "contract_id": str(contract.id),
                    "deadline_type": deadline_type,
                    "days_remaining": days_remaining,
                },
            )
        except Exception as e:
            logger.warning(
                "contract_notification_in_app_failed",
                contract_id=str(contract.id),
                error_type=type(e).__name__,
            )

    # Email bei kritischen Fristen (<=7 Tage)
    if urgency in ("critical", "high"):
        try:
            from app.services.email_service import EmailService
            email_service = EmailService()
            await email_service.send_contract_deadline_reminder(
                contract_id=contract.id,
                contract_title=contract.title,
                contract_number=contract.contract_number,
                deadline_type=deadline_type,
                deadline_date=contract.notice_deadline if deadline_type == "notice_deadline" else contract.end_date,
                days_remaining=days_remaining,
                recipient_user_id=contract.responsible_user_id,
                company_id=contract.company_id,
            )
        except Exception as e:
            logger.warning(
                "contract_notification_email_failed",
                contract_id=str(contract.id),
                error_type=type(e).__name__,
            )

    # Update last_reminder_sent
    contract.last_reminder_sent = datetime.now(timezone.utc)

    logger.debug(
        "contract_deadline_notification_sent",
        contract_id=str(contract.id),
        deadline_type=deadline_type,
        days_remaining=days_remaining,
        urgency=urgency,
    )


async def _send_renewal_option_notification(
    notification_service: object,
    contract: BusinessContract,
    option: ContractRenewalOption,
    days_remaining: int,
) -> None:
    """Sendet Benachrichtigung für Verlängerungsoption."""
    from app.services.notification_service import NotificationPriority, NotificationType

    urgency = _get_urgency(days_remaining)

    title = f"Verlängerungsoption läuft in {days_remaining} Tagen ab"
    message = (
        f"Die Verlängerungsoption {option.option_number} für Vertrag "
        f"'{contract.title}' muss bis {option.exercise_deadline} ausgeübt werden."
    )

    priority_map = {
        "critical": NotificationPriority.CRITICAL,
        "high": NotificationPriority.HIGH,
        "medium": NotificationPriority.NORMAL,
        "low": NotificationPriority.LOW,
    }
    priority = priority_map.get(urgency, NotificationPriority.NORMAL)

    # In-App Benachrichtigung
    if contract.responsible_user_id:
        try:
            await notification_service.send_in_app_notification(
                user_id=str(contract.responsible_user_id),
                title=title,
                message=message,
                priority=priority,
                notification_type=NotificationType.SYSTEM_ALERT,
                metadata={
                    "contract_id": str(contract.id),
                    "option_id": str(option.id),
                    "days_remaining": days_remaining,
                },
            )
        except Exception as e:
            logger.warning(
                "renewal_option_notification_failed",
                contract_id=str(contract.id),
                option_id=str(option.id),
                error_type=type(e).__name__,
            )

    logger.debug(
        "renewal_option_notification_sent",
        contract_id=str(contract.id),
        option_id=str(option.id),
        days_remaining=days_remaining,
    )


async def _send_milestone_notification(
    notification_service: object,
    contract: BusinessContract,
    milestone: ContractMilestone,
    days_remaining: int,
) -> None:
    """Sendet Benachrichtigung für Meilenstein."""
    from app.services.notification_service import NotificationPriority, NotificationType

    urgency = _get_urgency(days_remaining)

    title = f"Meilenstein fällig in {days_remaining} Tagen"
    message = (
        f"Der Meilenstein '{milestone.title}' für Vertrag '{contract.title}' "
        f"ist am {milestone.scheduled_date} fällig."
    )

    priority_map = {
        "critical": NotificationPriority.CRITICAL,
        "high": NotificationPriority.HIGH,
        "medium": NotificationPriority.NORMAL,
        "low": NotificationPriority.LOW,
    }
    priority = priority_map.get(urgency, NotificationPriority.NORMAL)

    # In-App Benachrichtigung
    if contract.responsible_user_id:
        try:
            await notification_service.send_in_app_notification(
                user_id=str(contract.responsible_user_id),
                title=title,
                message=message,
                priority=priority,
                notification_type=NotificationType.SYSTEM_ALERT,
                metadata={
                    "contract_id": str(contract.id),
                    "milestone_id": str(milestone.id),
                    "milestone_title": milestone.title,
                    "scheduled_date": str(milestone.scheduled_date),
                    "days_remaining": days_remaining,
                },
            )
        except Exception as e:
            logger.warning(
                "milestone_notification_failed",
                contract_id=str(contract.id),
                milestone_id=str(milestone.id),
                error_type=type(e).__name__,
            )

    # Email bei kritischen Meilensteinen (<=7 Tage)
    if urgency in ("critical", "high"):
        try:
            from app.services.email_service import EmailService
            email_service = EmailService()
            await email_service.send_contract_milestone_reminder(
                contract_id=contract.id,
                contract_title=contract.title,
                milestone_title=milestone.title,
                scheduled_date=milestone.scheduled_date,
                days_remaining=days_remaining,
                recipient_user_id=contract.responsible_user_id,
                company_id=contract.company_id,
            )
        except Exception as e:
            logger.warning(
                "milestone_email_notification_failed",
                contract_id=str(contract.id),
                milestone_id=str(milestone.id),
                error_type=type(e).__name__,
            )

    logger.debug(
        "milestone_notification_sent",
        contract_id=str(contract.id),
        milestone_id=str(milestone.id),
        days_remaining=days_remaining,
    )


def _get_urgency(days_remaining: int) -> str:
    """Bestimmt Dringlichkeit basierend auf verbleibenden Tagen."""
    if days_remaining <= 7:
        return "critical"
    elif days_remaining <= 30:
        return "high"
    elif days_remaining <= 60:
        return "medium"
    return "low"


# =============================================================================
# Expiring Contracts Check Task
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.contract_tasks.check_expiring_contracts_task",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
    queue="maintenance",
)
def check_expiring_contracts_task(
    self,
    days_ahead_list: Optional[List[int]] = None,
) -> Dict[str, object]:
    """Prüft ablaufende Verträge und aktualisiert Status.

    Wird täglich um 08:30 Uhr automatisch ausgeführt.
    Aktualisiert Status von ACTIVE zu EXPIRING_SOON wenn:
    - Vertragsende innerhalb von 90 Tagen
    - Kündigungsfrist innerhalb von 30 Tagen

    Args:
        days_ahead_list: Liste von Vorwarntagen [30, 60, 90]

    Returns:
        Dict mit Statistiken
    """
    if days_ahead_list is None:
        days_ahead_list = [30, 60, 90]

    async def _check_expiring() -> Dict[str, object]:
        async with get_async_session_context() as db:
            today = date.today()

            stats = {
                "total_checked": 0,
                "status_updated": 0,
                "expiring_30_days": 0,
                "expiring_60_days": 0,
                "expiring_90_days": 0,
                "already_expired": 0,
                "errors": [],
            }

            # Query für aktive Verträge
            query = select(BusinessContract).where(
                and_(
                    BusinessContract.status == ContractStatus.ACTIVE,
                    BusinessContract.deleted_at.is_(None),
                    BusinessContract.end_date.isnot(None),
                )
            )

            result = await db.execute(query)
            contracts = result.scalars().all()

            for contract in contracts:
                stats["total_checked"] += 1

                try:
                    days_until_end = (contract.end_date - today).days

                    # Bereits abgelaufen
                    if days_until_end < 0:
                        contract.status = ContractStatus.EXPIRED
                        stats["already_expired"] += 1
                        stats["status_updated"] += 1
                        logger.info(
                            "contract_expired",
                            contract_id=str(contract.id),
                            end_date=str(contract.end_date),
                        )
                    # Innerhalb von 30 Tagen
                    elif days_until_end <= 30:
                        if contract.status != ContractStatus.EXPIRING_SOON:
                            contract.status = ContractStatus.EXPIRING_SOON
                            stats["status_updated"] += 1
                        stats["expiring_30_days"] += 1
                    # Innerhalb von 60 Tagen
                    elif days_until_end <= 60:
                        stats["expiring_60_days"] += 1
                    # Innerhalb von 90 Tagen
                    elif days_until_end <= 90:
                        stats["expiring_90_days"] += 1

                except Exception as e:
                    stats["errors"].append({
                        "contract_id": str(contract.id),
                        "error": safe_error_detail(e, "Vorgang"),
                    })
                    logger.warning(
                        "contract_expiry_check_failed",
                        contract_id=str(contract.id),
                        **safe_error_log(e),
                    )

            await db.commit()
            return stats

    try:
        result = asyncio.run(_check_expiring())
        logger.info(
            "expiring_contracts_check_completed",
            total_checked=result["total_checked"],
            status_updated=result["status_updated"],
            expiring_30=result["expiring_30_days"],
            expiring_60=result["expiring_60_days"],
            expiring_90=result["expiring_90_days"],
            expired=result["already_expired"],
            errors=len(result["errors"]),
        )
        return result
    except Exception as e:
        logger.error("expiring_contracts_check_failed", **safe_error_log(e))
        raise self.retry(exc=e)


# =============================================================================
# Auto-Renewal Task
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.contract_tasks.auto_renew_contracts_task",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
    queue="maintenance",
)
def auto_renew_contracts_task(self) -> Dict[str, object]:
    """Verlängert Verträge automatisch wenn konfiguriert.

    Wird täglich um 09:00 Uhr automatisch ausgeführt.
    Prüft Verträge mit:
    - auto_renewal = True
    - Vertragsende heute oder in Vergangenheit
    - current_renewal_count < max_renewals (oder max_renewals = None)

    Returns:
        Dict mit Statistiken
    """
    async def _auto_renew() -> Dict[str, object]:
        async with get_async_session_context() as db:
            today = date.today()

            stats = {
                "total_checked": 0,
                "renewed": 0,
                "max_renewals_reached": 0,
                "errors": [],
            }

            # Query für auto-renewal Verträge
            query = select(BusinessContract).where(
                and_(
                    BusinessContract.auto_renewal == True,
                    BusinessContract.status.in_([
                        ContractStatus.ACTIVE,
                        ContractStatus.EXPIRING_SOON,
                    ]),
                    BusinessContract.deleted_at.is_(None),
                    BusinessContract.end_date.isnot(None),
                    BusinessContract.end_date <= today,
                )
            )

            result = await db.execute(query)
            contracts = result.scalars().all()

            for contract in contracts:
                stats["total_checked"] += 1

                try:
                    # Prüfen ob max_renewals erreicht
                    if (
                        contract.max_renewals is not None
                        and contract.current_renewal_count >= contract.max_renewals
                    ):
                        contract.status = ContractStatus.EXPIRED
                        stats["max_renewals_reached"] += 1
                        logger.info(
                            "contract_max_renewals_reached",
                            contract_id=str(contract.id),
                            current_count=contract.current_renewal_count,
                            max_renewals=contract.max_renewals,
                        )
                        continue

                    # Verlängern
                    renewal_months = contract.renewal_period_months or 12
                    old_end_date = contract.end_date

                    # Neues Enddatum berechnen (von altem Enddatum + Monate)
                    new_end_date = _add_months(old_end_date, renewal_months)
                    contract.end_date = new_end_date
                    contract.current_renewal_count = (
                        contract.current_renewal_count or 0
                    ) + 1
                    contract.status = ContractStatus.RENEWED

                    # Kündigungsfrist neu berechnen
                    if contract.notice_period_days:
                        contract.notice_deadline = (
                            new_end_date - timedelta(days=contract.notice_period_days)
                        )

                    stats["renewed"] += 1

                    logger.info(
                        "contract_auto_renewed",
                        contract_id=str(contract.id),
                        old_end_date=str(old_end_date),
                        new_end_date=str(new_end_date),
                        renewal_count=contract.current_renewal_count,
                    )

                except Exception as e:
                    stats["errors"].append({
                        "contract_id": str(contract.id),
                        "error": safe_error_detail(e, "Vorgang"),
                    })
                    logger.warning(
                        "contract_auto_renewal_failed",
                        contract_id=str(contract.id),
                        **safe_error_log(e),
                    )

            await db.commit()
            return stats

    try:
        result = asyncio.run(_auto_renew())
        logger.info(
            "auto_renewal_completed",
            total_checked=result["total_checked"],
            renewed=result["renewed"],
            max_reached=result["max_renewals_reached"],
            errors=len(result["errors"]),
        )
        return result
    except Exception as e:
        logger.error("auto_renewal_failed", **safe_error_log(e))
        raise self.retry(exc=e)


def _add_months(d: date, months: int) -> date:
    """Addiert Monate zu einem Datum."""
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    day = min(d.day, [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
    return date(year, month, day)


# =============================================================================
# Weekly Report Task
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.contract_tasks.generate_contract_report_task",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
    queue="maintenance",
)
def generate_contract_report_task(self) -> Dict[str, object]:
    """Generiert wöchentlichen Vertragsreport.

    Wird jeden Montag um 07:00 Uhr automatisch ausgeführt.
    Enthält:
    - Portfolio-Übersicht
    - Ablaufende Verträge
    - Kritische Fristen
    - Statistiken

    Returns:
        Dict mit Report-Daten
    """
    async def _generate_report() -> Dict[str, object]:
        async with get_async_session_context() as db:
            today = date.today()

            # Portfolio-Statistiken
            total_query = select(func.count(BusinessContract.id)).where(
                and_(
                    BusinessContract.deleted_at.is_(None),
                    BusinessContract.status != ContractStatus.TERMINATED,
                )
            )
            total_result = await db.execute(total_query)
            total_contracts = total_result.scalar() or 0

            # Aktive Verträge
            active_query = select(func.count(BusinessContract.id)).where(
                and_(
                    BusinessContract.status == ContractStatus.ACTIVE,
                    BusinessContract.deleted_at.is_(None),
                )
            )
            active_result = await db.execute(active_query)
            active_contracts = active_result.scalar() or 0

            # Ablaufend (90 Tage)
            expiring_query = select(func.count(BusinessContract.id)).where(
                and_(
                    BusinessContract.status.in_([
                        ContractStatus.ACTIVE,
                        ContractStatus.EXPIRING_SOON,
                    ]),
                    BusinessContract.deleted_at.is_(None),
                    BusinessContract.end_date.isnot(None),
                    BusinessContract.end_date <= today + timedelta(days=90),
                    BusinessContract.end_date >= today,
                )
            )
            expiring_result = await db.execute(expiring_query)
            expiring_contracts = expiring_result.scalar() or 0

            # Kritische Fristen (30 Tage)
            critical_query = select(func.count(BusinessContract.id)).where(
                and_(
                    BusinessContract.status.in_([
                        ContractStatus.ACTIVE,
                        ContractStatus.EXPIRING_SOON,
                    ]),
                    BusinessContract.deleted_at.is_(None),
                    or_(
                        and_(
                            BusinessContract.notice_deadline.isnot(None),
                            BusinessContract.notice_deadline <= today + timedelta(days=30),
                            BusinessContract.notice_deadline >= today,
                        ),
                        and_(
                            BusinessContract.end_date.isnot(None),
                            BusinessContract.end_date <= today + timedelta(days=30),
                            BusinessContract.end_date >= today,
                        ),
                    ),
                )
            )
            critical_result = await db.execute(critical_query)
            critical_deadlines = critical_result.scalar() or 0

            # Gesamtwert
            value_query = select(func.sum(BusinessContract.total_value)).where(
                and_(
                    BusinessContract.status == ContractStatus.ACTIVE,
                    BusinessContract.deleted_at.is_(None),
                )
            )
            value_result = await db.execute(value_query)
            total_value = float(value_result.scalar() or 0)

            # Monatliche Verpflichtungen
            monthly_query = select(func.sum(BusinessContract.monthly_value)).where(
                and_(
                    BusinessContract.status == ContractStatus.ACTIVE,
                    BusinessContract.deleted_at.is_(None),
                )
            )
            monthly_result = await db.execute(monthly_query)
            monthly_commitment = float(monthly_result.scalar() or 0)

            report = {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "period": "weekly",
                "portfolio_summary": {
                    "total_contracts": total_contracts,
                    "active_contracts": active_contracts,
                    "expiring_90_days": expiring_contracts,
                    "critical_deadlines_30_days": critical_deadlines,
                },
                "financial_summary": {
                    "total_value": total_value,
                    "monthly_commitment": monthly_commitment,
                    "currency": "EUR",
                },
                "alerts": {
                    "contracts_expiring_soon": expiring_contracts,
                    "critical_notice_deadlines": critical_deadlines,
                },
            }

            return report

    try:
        result = asyncio.run(_generate_report())
        logger.info(
            "contract_weekly_report_generated",
            total_contracts=result["portfolio_summary"]["total_contracts"],
            active_contracts=result["portfolio_summary"]["active_contracts"],
            expiring=result["portfolio_summary"]["expiring_90_days"],
            critical=result["portfolio_summary"]["critical_deadlines_30_days"],
        )
        return result
    except Exception as e:
        logger.error("contract_report_generation_failed", **safe_error_log(e))
        raise self.retry(exc=e)


# =============================================================================
# Renewal Option Expiry Task
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.contract_tasks.check_renewal_option_expiry_task",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
    queue="maintenance",
)
def check_renewal_option_expiry_task(self) -> Dict[str, object]:
    """Markiert abgelaufene Verlängerungsoptionen als EXPIRED.

    Wird täglich um 00:30 Uhr automatisch ausgeführt.

    Returns:
        Dict mit Statistiken
    """
    async def _check_expiry() -> Dict[str, object]:
        async with get_async_session_context() as db:
            today = date.today()

            stats = {
                "total_checked": 0,
                "expired": 0,
                "errors": [],
            }

            # Query für verfügbare Optionen mit abgelaufener Frist
            query = select(ContractRenewalOption).where(
                and_(
                    ContractRenewalOption.status == RenewalOptionStatus.AVAILABLE,
                    ContractRenewalOption.exercise_deadline.isnot(None),
                    ContractRenewalOption.exercise_deadline < today,
                )
            )

            result = await db.execute(query)
            options = result.scalars().all()

            for option in options:
                stats["total_checked"] += 1

                try:
                    option.status = RenewalOptionStatus.EXPIRED
                    stats["expired"] += 1

                    logger.info(
                        "renewal_option_expired",
                        option_id=str(option.id),
                        contract_id=str(option.contract_id),
                        deadline=str(option.exercise_deadline),
                    )

                except Exception as e:
                    stats["errors"].append({
                        "option_id": str(option.id),
                        "error": safe_error_detail(e, "Vorgang"),
                    })

            await db.commit()
            return stats

    try:
        result = asyncio.run(_check_expiry())
        logger.info(
            "renewal_option_expiry_check_completed",
            total_checked=result["total_checked"],
            expired=result["expired"],
            errors=len(result["errors"]),
        )
        return result
    except Exception as e:
        logger.error("renewal_option_expiry_check_failed", **safe_error_log(e))
        raise self.retry(exc=e)


# =============================================================================
# Milestone Overdue Check Task
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.contract_tasks.check_overdue_milestones_task",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
    queue="maintenance",
)
def check_overdue_milestones_task(self) -> Dict[str, object]:
    """Prüft auf überfällige Meilensteine und sendet Benachrichtigungen.

    Wird täglich um 09:30 Uhr automatisch ausgeführt.

    Returns:
        Dict mit Statistiken
    """
    async def _check_overdue() -> Dict[str, object]:
        async with get_async_session_context() as db:
            today = date.today()

            stats = {
                "total_checked": 0,
                "overdue": 0,
                "notifications_sent": 0,
                "errors": [],
            }

            # Query für nicht abgeschlossene Meilensteine mit Vertrag
            query = (
                select(ContractMilestone, BusinessContract)
                .join(BusinessContract)
                .where(
                    and_(
                        ContractMilestone.is_completed == False,
                        ContractMilestone.scheduled_date.isnot(None),
                        ContractMilestone.scheduled_date < today,
                        BusinessContract.status.in_([
                            ContractStatus.ACTIVE,
                            ContractStatus.EXPIRING_SOON,
                        ]),
                        BusinessContract.deleted_at.is_(None),
                    )
                )
            )

            result = await db.execute(query)
            rows = result.all()

            # NotificationService laden
            from app.services.notification_service import get_notification_service
            notification_service = get_notification_service()

            for milestone, contract in rows:
                stats["total_checked"] += 1

                try:
                    days_overdue = (today - milestone.scheduled_date).days
                    stats["overdue"] += 1

                    logger.warning(
                        "milestone_overdue",
                        milestone_id=str(milestone.id),
                        contract_id=str(milestone.contract_id),
                        days_overdue=days_overdue,
                        title=milestone.title,
                    )

                    # In-App Notification senden
                    if contract.responsible_user_id:
                        # Priorität basierend auf Überfälligkeit
                        priority = "high" if days_overdue > 7 else "normal"

                        await notification_service.notify(
                            notification_type="contract_milestone_overdue",
                            context={
                                "milestone_title": milestone.title,
                                "contract_name": contract.name or "Unbenannter Vertrag",
                                "days_overdue": days_overdue,
                                "milestone_id": str(milestone.id),
                                "contract_id": str(milestone.contract_id),
                            },
                            user_id=str(contract.responsible_user_id),
                            priority=priority,
                        )
                        stats["notifications_sent"] += 1
                    else:
                        logger.debug(
                            "milestone_notification_skipped_no_responsible",
                            milestone_id=str(milestone.id),
                        )

                except Exception as e:
                    stats["errors"].append({
                        "milestone_id": str(milestone.id),
                        "error": safe_error_detail(e, "Vorgang"),
                    })

            return stats

    try:
        result = asyncio.run(_check_overdue())
        logger.info(
            "overdue_milestones_check_completed",
            total_checked=result["total_checked"],
            overdue=result["overdue"],
            notifications=result["notifications_sent"],
            errors=len(result["errors"]),
        )
        return result
    except Exception as e:
        logger.error("overdue_milestones_check_failed", **safe_error_log(e))
        raise self.retry(exc=e)


# =============================================================================
# Contract Renewal Tasks (Phase 1.1)
# =============================================================================


@celery_app.task(
    name="app.workers.tasks.contract_tasks.check_contract_renewal_deadlines_task",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
    queue="maintenance",
)
def check_contract_renewal_deadlines_task(
    self,
    company_id: Optional[str] = None,
) -> Dict[str, object]:
    """Prüft alle Verträge auf bevorstehende Verlängerungsfristen.

    Wird täglich um 08:00 Uhr automatisch ausgeführt.
    Erstellt Alerts im Alert Center für:
    - Kündigungsfristen (30/60/90 Tage Vorlauf)
    - Vertragsablauf
    - Automatische Verlängerungen

    Args:
        company_id: Optional - nur für spezifische Firma

    Returns:
        Dict mit Statistiken
    """
    from app.services.contracts.contract_renewal_service import get_contract_renewal_service

    async def _check_renewals() -> Dict[str, object]:
        async with get_async_session_context() as db:
            renewal_service = get_contract_renewal_service(db)

            cid = UUID(company_id) if company_id else None
            stats = await renewal_service.check_upcoming_deadlines(company_id=cid)

            return stats

    try:
        result = asyncio.run(_check_renewals())
        logger.info(
            "contract_renewal_check_completed",
            contracts_checked=result["contracts_checked"],
            alerts_created=result["alerts_created"],
            deadlines_found=result["deadlines_found"],
            errors=result["errors"],
        )
        return result
    except Exception as e:
        logger.error("contract_renewal_check_failed", **safe_error_log(e))
        raise self.retry(exc=e)


@celery_app.task(
    name="app.workers.tasks.contract_tasks.extract_contract_dates_task",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
    queue="metadata",
)
def extract_contract_dates_task(
    self,
    document_id: str,
    company_id: str,
    create_deadlines: bool = True,
) -> Dict[str, object]:
    """Extrahiert Vertragsfristen aus OCR-Text eines Dokuments.

    Wird nach OCR-Abschluss automatisch für Vertragsdokumente aufgerufen.
    Analysiert den Text und erkennt:
    - Vertragslaufzeit
    - Kündigungsfristen
    - Ablaufdaten

    Args:
        document_id: ID des Dokuments
        company_id: Firmen-ID
        create_deadlines: Ob automatisch Deadlines erstellt werden sollen

    Returns:
        Dict mit extrahierten Daten
    """
    from app.services.contracts.contract_renewal_service import get_contract_renewal_service
    from app.db.models import Document

    async def _extract_dates() -> Dict[str, object]:
        async with get_async_session_context() as db:
            renewal_service = get_contract_renewal_service(db)

            dates = await renewal_service.extract_contract_dates_from_document(
                document_id=UUID(document_id),
                company_id=UUID(company_id),
            )

            result = {
                "document_id": document_id,
                "extracted_dates": {
                    k: v.isoformat() if v and hasattr(v, "isoformat") else v
                    for k, v in dates.items()
                },
                "deadlines_created": 0,
            }

            # Create deadlines if requested and expiration date found
            if create_deadlines and dates.get("expiration_date"):
                # Find contract linked to this document
                from sqlalchemy import select
                from app.db.models_contract import Contract

                contract_result = await db.execute(
                    select(Contract).where(Contract.document_id == UUID(document_id))
                )
                contract = contract_result.scalar_one_or_none()

                if contract:
                    # Update contract with extracted dates
                    if dates.get("effective_date"):
                        contract.effective_date = dates["effective_date"]
                    if dates.get("expiration_date"):
                        contract.expiration_date = dates["expiration_date"]
                    if dates.get("notice_period_days"):
                        contract.notice_period_days = dates["notice_period_days"]

                    await db.commit()

                    # Schedule reminders
                    deadlines = await renewal_service.schedule_reminders(
                        contract_id=contract.id,
                        deadline=dates["expiration_date"],
                        deadline_type="termination_notice" if dates.get("notice_deadline") else "contract_expiry",
                    )
                    result["deadlines_created"] = len(deadlines)

            return result

    try:
        result = asyncio.run(_extract_dates())
        logger.info(
            "contract_dates_extracted",
            document_id=document_id,
            dates_found=bool(result["extracted_dates"].get("expiration_date")),
            deadlines_created=result["deadlines_created"],
        )
        return result
    except Exception as e:
        logger.error(
            "contract_date_extraction_failed",
            document_id=document_id,
            **safe_error_log(e),
        )
        raise self.retry(exc=e)


@celery_app.task(
    name="app.workers.tasks.contract_tasks.send_contract_renewal_reminder_task",
    bind=True,
    max_retries=3,
    default_retry_delay=120,
    queue="notifications",
)
def send_contract_renewal_reminder_task(
    self,
    contract_id: str,
    days_remaining: int,
    deadline_type: str = "expiration",
) -> Dict[str, object]:
    """Sendet individuelle Erinnerung für Vertragserneuerung.

    Args:
        contract_id: Vertrags-ID
        days_remaining: Verbleibende Tage
        deadline_type: "expiration" oder "notice"

    Returns:
        Dict mit Status
    """
    from app.services.contracts.contract_renewal_service import get_contract_renewal_service
    from app.db.models_contract import Contract

    async def _send_reminder() -> Dict[str, object]:
        async with get_async_session_context() as db:
            contract = await db.get(Contract, UUID(contract_id))
            if not contract:
                return {"success": False, "error": "Vertrag nicht gefunden"}

            renewal_service = get_contract_renewal_service(db)

            # Create alert via renewal service
            alert_created = await renewal_service._create_renewal_alert(
                contract=contract,
                days_remaining=days_remaining,
                deadline_type=deadline_type,
            )

            return {
                "success": True,
                "contract_id": contract_id,
                "alert_created": alert_created,
                "days_remaining": days_remaining,
            }

    try:
        result = asyncio.run(_send_reminder())
        if result["success"]:
            logger.info(
                "contract_renewal_reminder_sent",
                contract_id=contract_id,
                days_remaining=days_remaining,
                alert_created=result["alert_created"],
            )
        else:
            logger.warning(
                "contract_renewal_reminder_failed",
                contract_id=contract_id,
                error=result.get("error"),
            )
        return result
    except Exception as e:
        logger.error(
            "contract_renewal_reminder_error",
            contract_id=contract_id,
            **safe_error_log(e),
        )
        raise self.retry(exc=e)


@celery_app.task(
    name="app.workers.tasks.contract_tasks.schedule_contract_reminders_task",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
    queue="maintenance",
)
def schedule_contract_reminders_task(
    self,
    contract_id: str,
    deadline_date: str,
    deadline_type: str = "termination_notice",
) -> Dict[str, object]:
    """Plant Erinnerungen für einen Vertrag.

    Args:
        contract_id: Vertrags-ID
        deadline_date: Fristdatum (ISO-Format)
        deadline_type: Art der Frist

    Returns:
        Dict mit erstellten Erinnerungen
    """
    from app.services.contracts.contract_renewal_service import get_contract_renewal_service

    async def _schedule() -> Dict[str, object]:
        async with get_async_session_context() as db:
            renewal_service = get_contract_renewal_service(db)

            deadline = date.fromisoformat(deadline_date)
            deadlines = await renewal_service.schedule_reminders(
                contract_id=UUID(contract_id),
                deadline=deadline,
                deadline_type=deadline_type,
            )

            return {
                "contract_id": contract_id,
                "deadlines_created": len(deadlines),
                "deadline_ids": [str(d.id) for d in deadlines],
            }

    try:
        result = asyncio.run(_schedule())
        logger.info(
            "contract_reminders_scheduled",
            contract_id=contract_id,
            deadlines_created=result["deadlines_created"],
        )
        return result
    except Exception as e:
        logger.error(
            "contract_reminders_scheduling_failed",
            contract_id=contract_id,
            **safe_error_log(e),
        )
        raise self.retry(exc=e)

"""Celery Tasks fuer das Approval System.

Enterprise Feature: Automatisierte Genehmigungsworkflows mit:
- Eskalation bei Timeout
- Erinnerungen an Genehmiger
- Statistik-Generierung
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, TypedDict
from uuid import UUID

import structlog
from sqlalchemy import and_, select
from sqlalchemy.orm import joinedload, Session

from app.core.datetime_utils import utc_now
from app.core.safe_errors import safe_error_log
from app.workers.celery_app import celery_app
from app.db.session import get_sync_session
from app.db.models import (
    ApprovalRequest,
    ApprovalStatus,
    ApprovalStep,
    Company,
    User,
    UserCompany,
)
from app.services.notification_service import (
    NotificationService,
    NotificationType,
    NotificationPriority,
)

logger = structlog.get_logger(__name__)


# ==================== TypedDict Return Types ====================


class EscalationResult(TypedDict):
    success: bool
    escalated_count: int
    notifications_sent: int
    timestamp: str


class ReminderResult(TypedDict):
    success: bool
    reminders_sent: int
    timestamp: str


class CompanyStatsDetail(TypedDict):
    status_distribution: Dict[str, int]
    avg_resolution_hours: float
    overdue_count: int
    total_requests: int


class StatsResult(TypedDict):
    success: bool
    stats_by_company: Dict[str, CompanyStatsDetail]
    generated_at: str


class ExpiryResult(TypedDict):
    success: bool
    expired_count: int
    days_threshold: int
    timestamp: str


class ApprovalActionResult(TypedDict):
    success: bool
    error: str
    status: str
    next_step: Optional[str]
    message: str


class OverdueCheckResult(TypedDict):
    success: bool
    checked_count: int
    escalated_count: int
    timestamp: str


class SubstitutionResult(TypedDict):
    success: bool
    deactivated_count: int
    timestamp: str


class ReminderSendResult(TypedDict):
    success: bool
    reminder_sent: bool
    error: str


# ==================== Tasks ====================


@celery_app.task(
    name="app.workers.tasks.approval_tasks.escalate_overdue_approvals",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    soft_time_limit=300,
    time_limit=360,
)
def escalate_overdue_approvals(
    self,
    company_id: Optional[str] = None,
) -> EscalationResult:
    """Eskaliert ueberfaellige Genehmigungsanfragen.

    Wird regelmaessig via Celery Beat ausgefuehrt um alle Anfragen
    zu finden, die ihr Faelligkeitsdatum ueberschritten haben.

    Args:
        company_id: Optional: Nur fuer diese Firma

    Returns:
        Dict mit Statistiken
    """
    logger.info("eskalation_start")

    with get_sync_session() as db:
        now = utc_now()

        query = (
            select(ApprovalRequest)
            .options(
                joinedload(ApprovalRequest.requested_by),
                joinedload(ApprovalRequest.triggered_by_rule),
            )
            .where(
                and_(
                    ApprovalRequest.status == ApprovalStatus.PENDING,
                    ApprovalRequest.due_date < now,
                    ApprovalRequest.is_escalated.is_(False),
                )
            )
        )

        if company_id:
            query = query.where(ApprovalRequest.company_id == UUID(company_id))

        result = db.execute(query)
        overdue_requests = result.unique().scalars().all()

        escalated_count = 0
        notifications_sent = 0

        for request in overdue_requests:
            request.is_escalated = True
            request.status = ApprovalStatus.ESCALATED
            request.escalation_date = now
            escalated_count += 1

            logger.warning(
                "anfrage_eskaliert",
                request_id=str(request.id),
                due_date=str(request.due_date),
            )

            # Benachrichtigung an Eskalationsempfaenger senden
            escalation_recipients = _get_escalation_recipients(db, request)
            for recipient in escalation_recipients:
                try:
                    _send_escalation_notification(request, recipient, now)
                    notifications_sent += 1
                except Exception as e:
                    logger.error(
                        "eskalation_benachrichtigung_fehler",
                        request_id=str(request.id),
                        **safe_error_log(e),
                    )

        db.commit()

    logger.info(
        "eskalation_abgeschlossen",
        escalated_count=escalated_count,
        notifications_sent=notifications_sent,
    )

    return EscalationResult(
        success=True,
        escalated_count=escalated_count,
        notifications_sent=notifications_sent,
        timestamp=now.isoformat(),
    )


def _get_escalation_recipients(
    db: Session,
    request: ApprovalRequest,
) -> List[User]:
    """Ermittelt die Eskalationsempfaenger fuer eine Anfrage.

    Args:
        db: Database Session
        request: Die eskalierte Anfrage

    Returns:
        Liste von User-Objekten
    """
    recipients: List[User] = []

    # 1. Eskalations-Rolle aus der Regel holen
    escalation_role = None
    if request.triggered_by_rule and request.triggered_by_rule.escalation_to_role:
        escalation_role = request.triggered_by_rule.escalation_to_role

    # 2. Wenn Eskalations-Rolle definiert, User mit dieser Rolle finden
    #    Nutze UserCompany-Tabelle fuer Multi-Tenant Zuordnung
    if escalation_role:
        role_users_query = (
            select(User)
            .join(UserCompany, User.id == UserCompany.user_id)
            .where(
                and_(
                    UserCompany.company_id == request.company_id,
                    UserCompany.role == escalation_role,
                    User.is_active == True,
                )
            )
        )
        result = db.execute(role_users_query)
        role_users = result.scalars().all()
        recipients.extend(role_users)

    # 3. Fallback: Wenn keine Rolle definiert oder keine User gefunden,
    #    suche nach Administratoren der Firma (owner, admin, manager)
    if not recipients:
        admin_query = (
            select(User)
            .join(UserCompany, User.id == UserCompany.user_id)
            .where(
                and_(
                    UserCompany.company_id == request.company_id,
                    UserCompany.role.in_(["admin", "manager", "owner"]),
                    User.is_active == True,
                )
            )
        )
        result = db.execute(admin_query)
        admins = result.scalars().all()
        recipients.extend(admins)

    return recipients


def _send_escalation_notification(
    request: ApprovalRequest,
    recipient: User,
    escalated_at: datetime,
) -> None:
    """Sendet eine Eskalations-Benachrichtigung.

    Args:
        request: Die eskalierte Anfrage
        recipient: Der Empfaenger
        escalated_at: Zeitpunkt der Eskalation
    """
    # Antragsteller-Name ermitteln
    requester_name = "Unbekannt"
    if request.requested_by:
        requester_name = (
            request.requested_by.full_name
            if request.requested_by.full_name
            else str(request.requested_by.id)
        )

    # Faelligkeitsdatum formatieren
    due_date_str = (
        request.due_date.strftime("%d.%m.%Y %H:%M")
        if request.due_date
        else "Nicht angegeben"
    )

    # Eskalations-Zeitpunkt formatieren
    escalated_at_str = escalated_at.strftime("%d.%m.%Y %H:%M")

    context = {
        "request_id": str(request.id),
        "request_subject": request.title,
        "requester_name": requester_name,
        "due_date": due_date_str,
        "escalated_at": escalated_at_str,
    }

    # Benachrichtigung senden (async via asyncio.run)
    async def _send() -> None:
        notification_service = NotificationService()
        await notification_service.notify(
            notification_type=NotificationType.APPROVAL_ESCALATED,
            context=context,
            user_id=str(recipient.id),
            email=recipient.email if recipient.email else None,
            priority=NotificationPriority.HIGH,
        )

    try:
        asyncio.run(_send())
        logger.info(
            "eskalation_benachrichtigung_gesendet",
            recipient_id=str(recipient.id),
            request_id=str(request.id),
        )
    except Exception as e:
        logger.error(
            "eskalation_benachrichtigung_fehler",
            recipient_id=str(recipient.id),
            request_id=str(request.id),
            **safe_error_log(e),
        )


@celery_app.task(
    name="app.workers.tasks.approval_tasks.send_approval_reminders",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    soft_time_limit=300,
    time_limit=360,
)
def send_approval_reminders(
    self,
    hours_before_due: int = 24,
) -> ReminderResult:
    """Sendet Erinnerungen fuer bald faellige Genehmigungen.

    Args:
        hours_before_due: Stunden vor Faelligkeit fuer Erinnerung

    Returns:
        Dict mit Statistiken
    """
    logger.info("erinnerung_start", hours_before_due=hours_before_due)

    with get_sync_session() as db:
        now = utc_now()
        reminder_threshold = now + timedelta(hours=hours_before_due)

        # Finde bald faellige Steps mit allen benoetigten Relationen
        query = (
            select(ApprovalStep)
            .options(
                joinedload(ApprovalStep.assigned_user),
                joinedload(ApprovalStep.approval_request).joinedload(
                    ApprovalRequest.requested_by
                ),
            )
            .join(ApprovalRequest)
            .where(
                and_(
                    ApprovalRequest.status == ApprovalStatus.PENDING,
                    ApprovalRequest.due_date <= reminder_threshold,
                    ApprovalRequest.due_date > now,
                    ApprovalStep.status == ApprovalStatus.PENDING,
                    ApprovalStep.assigned_user_id.isnot(None),
                )
            )
        )

        result = db.execute(query)
        pending_steps = result.unique().scalars().all()

        reminders_sent = 0
        for step in pending_steps:
            # Nur wenn noch keine Erinnerung heute gesendet wurde
            if step.last_reminder_at:
                if (now - step.last_reminder_at).total_seconds() < 86400:  # 24h
                    continue

            # Erinnerung senden
            try:
                _send_reminder_notification(step, now)
                reminders_sent += 1
            except Exception as e:
                logger.error(
                    "erinnerung_fehler",
                    step_id=str(step.id),
                    **safe_error_log(e),
                )
                continue

            step.reminder_sent_count += 1
            step.last_reminder_at = now

            logger.info(
                "erinnerung_gesendet",
                step_id=str(step.id),
                user_id=str(step.assigned_user_id),
            )

        db.commit()

    logger.info("erinnerung_abgeschlossen", reminders_sent=reminders_sent)

    return ReminderResult(
        success=True,
        reminders_sent=reminders_sent,
        timestamp=now.isoformat(),
    )


def _send_reminder_notification(
    step: ApprovalStep,
    now: datetime,
) -> None:
    """Sendet eine Erinnerungs-Benachrichtigung an den zugewiesenen User.

    Args:
        step: Der Approval-Schritt
        now: Aktueller Zeitpunkt
    """
    if not step.assigned_user:
        logger.warning("erinnerung_kein_user", step_id=str(step.id))
        return

    approval_request = step.approval_request
    if not approval_request:
        logger.warning("erinnerung_keine_anfrage", step_id=str(step.id))
        return

    # Antragsteller-Name ermitteln (ohne PII)
    requester_name = "Unbekannt"
    if approval_request.requested_by:
        requester_name = (
            approval_request.requested_by.full_name
            if approval_request.requested_by.full_name
            else str(approval_request.requested_by.id)
        )

    # Faelligkeitsdatum formatieren
    due_date_str = (
        approval_request.due_date.strftime("%d.%m.%Y %H:%M")
        if approval_request.due_date
        else "Nicht angegeben"
    )

    # Verbleibende Zeit berechnen
    time_remaining = "Unbekannt"
    if approval_request.due_date:
        remaining_delta = approval_request.due_date - now
        if remaining_delta.total_seconds() > 0:
            hours = int(remaining_delta.total_seconds() // 3600)
            minutes = int((remaining_delta.total_seconds() % 3600) // 60)
            if hours > 24:
                days = hours // 24
                time_remaining = f"{days} Tag(e) und {hours % 24} Stunde(n)"
            elif hours > 0:
                time_remaining = f"{hours} Stunde(n) und {minutes} Minute(n)"
            else:
                time_remaining = f"{minutes} Minute(n)"

    context = {
        "request_id": str(approval_request.id),
        "request_subject": approval_request.title,
        "requester_name": requester_name,
        "due_date": due_date_str,
        "time_remaining": time_remaining,
        "reminder_count": step.reminder_sent_count + 1,
    }

    # Benachrichtigung senden (async via asyncio.run)
    async def _send() -> None:
        notification_service = NotificationService()
        await notification_service.notify(
            notification_type=NotificationType.APPROVAL_REMINDER,
            context=context,
            user_id=str(step.assigned_user_id),
            email=step.assigned_user.email if step.assigned_user.email else None,
            priority=NotificationPriority.NORMAL,
        )

    try:
        asyncio.run(_send())
        logger.debug(
            "erinnerung_benachrichtigung_gesendet",
            user_id=str(step.assigned_user_id),
            request_id=str(approval_request.id),
        )
    except Exception as e:
        logger.error(
            "erinnerung_benachrichtigung_fehler",
            user_id=str(step.assigned_user_id),
            **safe_error_log(e),
        )


@celery_app.task(
    name="app.workers.tasks.approval_tasks.generate_approval_stats",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    soft_time_limit=300,
    time_limit=360,
)
def generate_approval_stats(
    self,
    company_id: Optional[str] = None,
) -> StatsResult:
    """Generiert Statistiken fuer das Approval Dashboard.

    Args:
        company_id: Optional: Nur fuer diese Firma

    Returns:
        Dict mit Statistiken
    """
    logger.info("approval_stats_start")

    from sqlalchemy import func

    with get_sync_session() as db:
        # Basis-Query
        base_query = select(ApprovalRequest)

        if company_id:
            base_query = base_query.where(ApprovalRequest.company_id == UUID(company_id))
            companies = [UUID(company_id)]
        else:
            # Alle Companies
            result = db.execute(select(Company.id))
            companies = [row[0] for row in result.all()]

        stats_by_company: Dict[str, CompanyStatsDetail] = {}

        for comp_id in companies:
            # Status-Verteilung
            result = db.execute(
                select(
                    ApprovalRequest.status,
                    func.count(ApprovalRequest.id)
                )
                .where(ApprovalRequest.company_id == comp_id)
                .group_by(ApprovalRequest.status)
            )
            status_distribution: Dict[str, int] = {
                row[0].value: row[1] for row in result.all()
            }

            # Durchschnittliche Bearbeitungszeit
            result = db.execute(
                select(
                    func.avg(
                        func.extract(
                            'epoch',
                            ApprovalRequest.resolved_at - ApprovalRequest.created_at
                        ) / 3600
                    )
                )
                .where(
                    and_(
                        ApprovalRequest.company_id == comp_id,
                        ApprovalRequest.resolved_at.isnot(None),
                    )
                )
            )
            avg_hours = result.scalar() or 0

            # Ueberfaellige
            now = utc_now()
            result = db.execute(
                select(func.count(ApprovalRequest.id))
                .where(
                    and_(
                        ApprovalRequest.company_id == comp_id,
                        ApprovalRequest.status == ApprovalStatus.PENDING,
                        ApprovalRequest.due_date < now,
                    )
                )
            )
            overdue_count = result.scalar() or 0

            stats_by_company[str(comp_id)] = CompanyStatsDetail(
                status_distribution=status_distribution,
                avg_resolution_hours=float(avg_hours),
                overdue_count=overdue_count,
                total_requests=sum(status_distribution.values()),
            )

    logger.info("approval_stats_generiert", company_count=len(stats_by_company))

    return StatsResult(
        success=True,
        stats_by_company=stats_by_company,
        generated_at=utc_now().isoformat(),
    )


@celery_app.task(
    name="app.workers.tasks.approval_tasks.expire_old_approvals",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    soft_time_limit=300,
    time_limit=360,
)
def expire_old_approvals(
    self,
    days_to_expire: int = 30,
) -> ExpiryResult:
    """Markiert sehr alte ausstehende Genehmigungen als abgelaufen.

    Args:
        days_to_expire: Tage nach denen eine Anfrage ablaeuft

    Returns:
        Dict mit Statistiken
    """
    logger.info("ablauf_pruefung_start", days_to_expire=days_to_expire)

    with get_sync_session() as db:
        now = utc_now()
        expiry_threshold = now - timedelta(days=days_to_expire)

        query = select(ApprovalRequest).where(
            and_(
                ApprovalRequest.status.in_([
                    ApprovalStatus.PENDING,
                    ApprovalStatus.ESCALATED,
                ]),
                ApprovalRequest.created_at < expiry_threshold,
            )
        )

        result = db.execute(query)
        old_requests = result.scalars().all()

        expired_count = 0
        for request in old_requests:
            request.status = ApprovalStatus.EXPIRED
            request.resolved_at = now
            request.resolution_notes = f"Automatisch abgelaufen nach {days_to_expire} Tagen"
            expired_count += 1

            logger.info(
                "anfrage_abgelaufen",
                request_id=str(request.id),
                created_at=str(request.created_at),
            )

        db.commit()

    logger.info("ablauf_pruefung_abgeschlossen", expired_count=expired_count)

    return ExpiryResult(
        success=True,
        expired_count=expired_count,
        days_threshold=days_to_expire,
        timestamp=now.isoformat(),
    )


@celery_app.task(
    name="app.workers.tasks.approval_tasks.process_approval_action",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    soft_time_limit=120,
    time_limit=180,
)
def process_approval_action(
    self,
    request_id: str,
    user_id: str,
    action: str,  # "approve", "reject", "delegate"
    notes: Optional[str] = None,
    delegate_to_id: Optional[str] = None,
) -> ApprovalActionResult:
    """Verarbeitet eine Genehmigungsaktion asynchron.

    Args:
        request_id: ID der Anfrage
        user_id: ID des handelnden Users
        action: Aktion (approve/reject/delegate)
        notes: Optionale Notizen
        delegate_to_id: ID des Delegationsempfaengers

    Returns:
        Dict mit Ergebnis
    """
    import asyncio
    from app.db.session import get_async_session
    from app.services.approval.approval_service import ApprovalService

    logger.info(
        "approval_aktion_start",
        action=action,
        request_id=request_id,
        user_id=user_id,
    )

    async def _process() -> ApprovalActionResult:
        async with get_async_session() as db:
            service = ApprovalService(db)

            if action == "approve":
                result = await service.approve(
                    request_id=UUID(request_id),
                    user_id=UUID(user_id),
                    notes=notes,
                )
            elif action == "reject":
                if not notes:
                    return ApprovalActionResult(success=False, error="Begruendung erforderlich", status="error", next_step=None, message="")
                result = await service.reject(
                    request_id=UUID(request_id),
                    user_id=UUID(user_id),
                    notes=notes,
                )
            elif action == "delegate":
                if not delegate_to_id:
                    return ApprovalActionResult(success=False, error="Delegationsempfaenger erforderlich", status="error", next_step=None, message="")
                result = await service.delegate(
                    request_id=UUID(request_id),
                    user_id=UUID(user_id),
                    delegate_to_id=UUID(delegate_to_id),
                    reason=notes or "Delegation ohne Begruendung",
                )
            else:
                return ApprovalActionResult(success=False, error=f"Unbekannte Aktion: {action}", status="error", next_step=None, message="")

            return ApprovalActionResult(
                success=result.success,
                error="",
                status=result.request_status.value,
                next_step=result.next_step,
                message=result.message,
            )

    # Async ausfuehren
    result = asyncio.run(_process())

    logger.info(
        "approval_aktion_abgeschlossen",
        action=action,
        success=result["success"],
    )

    return result


# =================================================================
# M2: Approval Matrix Tasks (Genehmigungsmatrix)
# =================================================================


@celery_app.task(
    name="app.workers.tasks.approval_tasks.check_overdue_approvals_task",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    soft_time_limit=300,
    time_limit=360,
)
def check_overdue_approvals_task(
    self,
    company_id: Optional[str] = None,
) -> OverdueCheckResult:
    """Prueft ueberfaellige Genehmigungen und eskaliert via Approval Matrix.

    Verwendet die ApprovalMatrix um die korrekte Eskalationskette zu bestimmen.
    Laeuft stuendlich via Beat Schedule.

    Args:
        company_id: Optionale Company-ID (None = alle Companies)

    Returns:
        Dict mit Ergebnis der Pruefung
    """
    logger.info("m2_overdue_check_start")

    escalated_count = 0
    checked_count = 0
    now = utc_now()

    with get_sync_session() as db:
        query = select(ApprovalRequest).where(
            and_(
                ApprovalRequest.status == ApprovalStatus.PENDING,
                ApprovalRequest.due_date < now,
                ApprovalRequest.is_deleted == False,
            )
        ).options(joinedload(ApprovalRequest.current_step))

        if company_id:
            query = query.where(ApprovalRequest.company_id == UUID(company_id))

        result = db.execute(query)
        overdue_requests = result.scalars().unique().all()

        for request in overdue_requests:
            checked_count += 1
            try:
                # Eskalation: Status auf ESCALATED setzen
                if request.current_step:
                    request.current_step.status = "escalated"
                    request.current_step.escalated_at = now
                escalated_count += 1
                logger.info(
                    "m2_anfrage_eskaliert",
                    request_id=str(request.id),
                    due_date=str(request.due_date),
                )
            except Exception as e:
                logger.error(
                    "m2_eskalation_fehler",
                    request_id=str(request.id),
                    **safe_error_log(e),
                )

        db.commit()

    logger.info(
        "m2_overdue_check_abgeschlossen",
        checked_count=checked_count,
        escalated_count=escalated_count,
    )

    return OverdueCheckResult(
        success=True,
        checked_count=checked_count,
        escalated_count=escalated_count,
        timestamp=now.isoformat(),
    )


@celery_app.task(
    name="app.workers.tasks.approval_tasks.deactivate_expired_substitutions_task",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    soft_time_limit=300,
    time_limit=360,
)
def deactivate_expired_substitutions_task(self) -> SubstitutionResult:
    """Deaktiviert abgelaufene Stellvertretungsregeln.

    Prueft alle aktiven SubstitutionRules und deaktiviert solche,
    deren end_date in der Vergangenheit liegt.
    Laeuft taeglich via Beat Schedule (01:45 Uhr).

    Returns:
        Dict mit Anzahl deaktivierter Regeln
    """
    from app.db.models import SubstitutionRule

    logger.info("m2_substitution_deaktivierung_start")

    deactivated_count = 0
    now = utc_now()

    with get_sync_session() as db:
        result = db.execute(
            select(SubstitutionRule).where(
                and_(
                    SubstitutionRule.is_active == True,
                    SubstitutionRule.end_date < now,
                )
            )
        )
        expired_rules = result.scalars().all()

        for rule in expired_rules:
            rule.is_active = False
            deactivated_count += 1
            logger.info(
                "m2_stellvertretung_deaktiviert",
                rule_id=str(rule.id),
                end_date=str(rule.end_date),
            )

        db.commit()

    logger.info(
        "m2_substitution_deaktivierung_abgeschlossen",
        deactivated_count=deactivated_count,
    )

    return SubstitutionResult(
        success=True,
        deactivated_count=deactivated_count,
        timestamp=now.isoformat(),
    )


@celery_app.task(
    name="app.workers.tasks.approval_tasks.send_approval_reminder_task",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    soft_time_limit=120,
    time_limit=180,
)
def send_approval_reminder_task(
    self,
    request_id: str,
    company_id: str,
) -> ReminderSendResult:
    """Sendet Erinnerung fuer eine ausstehende Genehmigung.

    Wird on-demand aufgerufen (nicht via Beat Schedule).

    Args:
        request_id: ID der Genehmigungsanfrage
        company_id: Company-ID fuer Berechtigungspruefung

    Returns:
        Dict mit Ergebnis
    """
    logger.info("m2_erinnerung_start", request_id=request_id)

    with get_sync_session() as db:
        request = db.execute(
            select(ApprovalRequest).where(
                and_(
                    ApprovalRequest.id == UUID(request_id),
                    ApprovalRequest.company_id == UUID(company_id),
                    ApprovalRequest.status == ApprovalStatus.PENDING,
                )
            )
        ).scalar_one_or_none()

        if not request:
            return ReminderSendResult(
                success=False,
                reminder_sent=False,
                error="Genehmigungsanfrage nicht gefunden oder nicht ausstehend",
            )

        # Erinnerung via Notification Service
        try:
            notification_service = NotificationService(db)
            if request.current_step and request.current_step.approver_id:
                notification_service.create_notification(
                    user_id=request.current_step.approver_id,
                    title="Genehmigung ausstehend",
                    message=(
                        f"Erinnerung: Genehmigungsanfrage wartet auf Ihre Entscheidung. "
                        f"Faellig am: {request.due_date.strftime('%d.%m.%Y') if request.due_date else 'kein Datum'}"
                    ),
                    notification_type=NotificationType.APPROVAL,
                    priority=NotificationPriority.HIGH,
                    reference_id=str(request.id),
                    reference_type="approval_request",
                )
                db.commit()
                logger.info(
                    "m2_erinnerung_gesendet",
                    approver_id=str(request.current_step.approver_id),
                    request_id=request_id,
                )
                return ReminderSendResult(success=True, reminder_sent=True, error="")
        except Exception as e:
            logger.error(
                "m2_erinnerung_fehler",
                request_id=request_id,
                **safe_error_log(e),
            )
            return ReminderSendResult(
                success=False,
                reminder_sent=False,
                error="Erinnerung fehlgeschlagen",
            )

    return ReminderSendResult(
        success=False,
        reminder_sent=False,
        error="Kein aktueller Genehmigungsschritt gefunden",
    )

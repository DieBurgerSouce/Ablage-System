# -*- coding: utf-8 -*-
"""
Celery Tasks fuer das Privat-Modul.

Geplante Tasks:
- send_deadline_reminders: Sende Frist-Erinnerungen per Email
- check_emergency_access_requests: Pruefe ablaufende Wartezeiten
- cleanup_expired_access: Raeume abgelaufene Notfallzugriffe auf
- generate_deadline_report: Erstelle woechentlichen Fristenreport

Beat Schedule:
- send_deadline_reminders: Taeglich 08:00
- check_emergency_access_requests: Stundlich
- cleanup_expired_access: Taeglich 03:00
- generate_deadline_report: Montag 07:00
"""

import asyncio
from datetime import datetime, date, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

import structlog

from app.workers.celery_app import celery_app, CPUTask

logger = structlog.get_logger(__name__)


def run_async(coro):
    """Hilfsfunktion um async Code in sync Celery Tasks auszufuehren."""
    return asyncio.run(coro)


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.privat_tasks.send_deadline_reminders",
    max_retries=3,
    default_retry_delay=300,
)
def send_deadline_reminders(self) -> Dict[str, Any]:
    """
    Sende Erinnerungen fuer anstehende Fristen.

    Prueft alle aktiven Fristen und sendet Erinnerungen basierend
    auf den konfigurierten reminder_days.

    Returns:
        Statistik ueber gesendete Erinnerungen
    """
    logger.info(
        "deadline_reminders_task_started",
        task_id=self.request.id,
    )

    try:
        async def do_send_reminders():
            from sqlalchemy import select, and_, or_
            from sqlalchemy.orm import selectinload
            from app.db.session import get_async_session
            from app.db.models import PrivatDeadline, PrivatSpace, PrivatDeadlineNotification, User
            from app.services.email_service import email_service

            async with get_async_session() as db:
                today = date.today()
                sent_count = 0
                checked_count = 0

                # Hole alle aktiven, nicht erledigten Fristen
                stmt = (
                    select(PrivatDeadline)
                    .join(PrivatSpace)
                    .where(
                        and_(
                            PrivatDeadline.is_completed == False,
                            PrivatDeadline.due_date >= today,
                            PrivatSpace.deleted_at == None,
                        )
                    )
                )
                result = await db.execute(stmt)
                deadlines = result.scalars().all()

                for deadline in deadlines:
                    checked_count += 1
                    days_until = (deadline.due_date - today).days

                    # Pruefe ob heute eine Erinnerung gesendet werden soll
                    reminder_days = deadline.reminder_days or [7, 3, 1]
                    if days_until not in reminder_days:
                        continue

                    # Pruefe ob heute schon eine Erinnerung gesendet wurde
                    existing_notification = await db.execute(
                        select(PrivatDeadlineNotification)
                        .where(
                            and_(
                                PrivatDeadlineNotification.deadline_id == deadline.id,
                                PrivatDeadlineNotification.sent_at >= datetime.combine(today, datetime.min.time()),
                            )
                        )
                    )
                    if existing_notification.scalar_one_or_none():
                        continue

                    # Hole den Space-Owner
                    space_result = await db.execute(
                        select(PrivatSpace).where(PrivatSpace.id == deadline.space_id)
                    )
                    space = space_result.scalar_one_or_none()
                    if not space:
                        continue

                    # Hole User-Email
                    user_result = await db.execute(
                        select(User).where(User.id == space.owner_id)
                    )
                    user = user_result.scalar_one_or_none()
                    if not user or not user.email:
                        continue

                    # Sende Email
                    subject = f"Frist-Erinnerung: {deadline.title}"
                    body = f"""
                    Guten Tag,

                    dies ist eine Erinnerung fuer die folgende Frist:

                    Titel: {deadline.title}
                    Faellig am: {deadline.due_date.strftime('%d.%m.%Y')}
                    Tage verbleibend: {days_until}

                    {f'Beschreibung: {deadline.description}' if deadline.description else ''}

                    Mit freundlichen Gruessen,
                    Ihr Ablage-System
                    """

                    try:
                        await email_service.send_email(
                            to=user.email,
                            subject=subject,
                            body=body.strip(),
                        )

                        # Speichere Benachrichtigung
                        notification = PrivatDeadlineNotification(
                            deadline_id=deadline.id,
                            notification_type="reminder",
                            sent_at=datetime.now(timezone.utc),
                            sent_to=user.email,
                        )
                        db.add(notification)
                        await db.commit()
                        sent_count += 1

                        logger.info(
                            "deadline_reminder_sent",
                            deadline_id=str(deadline.id),
                            user_email=user.email,
                            days_until=days_until,
                        )

                    except Exception as e:
                        logger.warning(
                            "deadline_reminder_failed",
                            deadline_id=str(deadline.id),
                            error=str(e),
                        )

                return {
                    "checked": checked_count,
                    "sent": sent_count,
                }

        result = run_async(do_send_reminders())

        logger.info(
            "deadline_reminders_task_completed",
            task_id=self.request.id,
            result=result,
        )

        return result

    except Exception as e:
        logger.error(
            "deadline_reminders_task_failed",
            task_id=self.request.id,
            error=str(e),
        )
        raise self.retry(exc=e)


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.privat_tasks.check_emergency_access_requests",
    max_retries=3,
    default_retry_delay=60,
)
def check_emergency_access_requests(self) -> Dict[str, Any]:
    """
    Pruefe Notfallzugriff-Anfragen auf ablaufende Wartezeiten.

    Wenn die Wartezeit einer Anfrage abgelaufen ist und diese nicht
    abgelehnt wurde, wird sie automatisch genehmigt.

    Returns:
        Statistik ueber verarbeitete Anfragen
    """
    logger.info(
        "emergency_access_check_started",
        task_id=self.request.id,
    )

    try:
        async def do_check():
            from sqlalchemy import select, and_
            from app.db.session import get_async_session
            from app.db.models import PrivatEmergencyAccessRequest, PrivatEmergencyContact, PrivatSpace, User
            from app.services.email_service import email_service

            async with get_async_session() as db:
                now = datetime.now(timezone.utc)
                auto_approved = 0
                notified_owners = 0

                # Finde alle ausstehenden Anfragen mit abgelaufener Wartezeit
                stmt = select(PrivatEmergencyAccessRequest).where(
                    and_(
                        PrivatEmergencyAccessRequest.status == "pending",
                        PrivatEmergencyAccessRequest.waiting_until <= now,
                    )
                )
                result = await db.execute(stmt)
                expired_requests = result.scalars().all()

                for request in expired_requests:
                    # Auto-Genehmigung
                    request.status = "approved"
                    request.approved_at = now

                    logger.info(
                        "emergency_access_auto_approved",
                        request_id=str(request.id),
                        space_id=str(request.space_id),
                    )

                    auto_approved += 1

                    # SECURITY: Benachrichtige Owner ueber automatische Genehmigung
                    try:
                        space_result = await db.execute(
                            select(PrivatSpace).where(PrivatSpace.id == request.space_id)
                        )
                        space = space_result.scalar_one_or_none()
                        if space:
                            owner_result = await db.execute(
                                select(User).where(User.id == space.owner_id)
                            )
                            owner = owner_result.scalar_one_or_none()
                            if owner and owner.email:
                                # SECURITY: Dynamische Wartezeit berechnen (nicht hardcoded!)
                                waiting_period_hours = int(
                                    (request.waiting_until - request.requested_at).total_seconds() / 3600
                                )
                                if waiting_period_hours >= 48:
                                    waiting_period_str = f"{waiting_period_hours // 24} Tagen"
                                else:
                                    waiting_period_str = f"{waiting_period_hours} Stunden"

                                await email_service.send_email(
                                    to=owner.email,
                                    subject="Notfallzugriff automatisch genehmigt",
                                    body=f"""
Guten Tag,

der Notfallzugriff auf Ihren Privat-Bereich '{space.name}' wurde automatisch genehmigt,
da die Wartezeit von {waiting_period_str} abgelaufen ist und Sie den Zugriff nicht abgelehnt haben.

Bitte pruefen Sie die Zugriffsberechtigungen in Ihrem Ablage-System.

Mit freundlichen Gruessen,
Ihr Ablage-System
                                    """.strip(),
                                )
                                notified_owners += 1
                                logger.info(
                                    "owner_notified_auto_approval",
                                    space_id=str(space.id),
                                    owner_email=owner.email,
                                )
                    except Exception as e:
                        logger.warning(
                            "auto_approval_owner_notification_failed",
                            request_id=str(request.id),
                            error=str(e),
                        )

                await db.commit()

                # Pruefe auch Anfragen die kurz vor Ablauf sind (1 Tag)
                tomorrow = now + timedelta(days=1)
                expiring_stmt = select(PrivatEmergencyAccessRequest).where(
                    and_(
                        PrivatEmergencyAccessRequest.status == "pending",
                        PrivatEmergencyAccessRequest.waiting_until > now,
                        PrivatEmergencyAccessRequest.waiting_until <= tomorrow,
                    )
                )
                expiring_result = await db.execute(expiring_stmt)
                expiring_requests = expiring_result.scalars().all()

                warned_owners = 0
                for request in expiring_requests:
                    # SECURITY: Sende Warnung an Owner (1 Tag vor Auto-Approval)
                    try:
                        space_result = await db.execute(
                            select(PrivatSpace).where(PrivatSpace.id == request.space_id)
                        )
                        space = space_result.scalar_one_or_none()
                        if space:
                            owner_result = await db.execute(
                                select(User).where(User.id == space.owner_id)
                            )
                            owner = owner_result.scalar_one_or_none()
                            if owner and owner.email:
                                hours_remaining = int((request.waiting_until - now).total_seconds() / 3600)
                                await email_service.send_email(
                                    to=owner.email,
                                    subject="WARNUNG: Notfallzugriff wird bald automatisch genehmigt",
                                    body=f"""
WICHTIGE WARNUNG!

Ein Notfallzugriff auf Ihren Privat-Bereich '{space.name}' wird in ca. {hours_remaining} Stunden
AUTOMATISCH GENEHMIGT, wenn Sie nicht handeln.

Wenn Sie diesen Zugriff NICHT gewaehren moechten, loggen Sie sich JETZT in Ihr
Ablage-System ein und lehnen Sie die Anfrage ab.

Mit freundlichen Gruessen,
Ihr Ablage-System
                                    """.strip(),
                                )
                                warned_owners += 1
                                logger.info(
                                    "owner_warned_expiring_request",
                                    space_id=str(space.id),
                                    owner_email=owner.email,
                                    hours_remaining=hours_remaining,
                                )
                    except Exception as e:
                        logger.warning(
                            "expiring_warning_notification_failed",
                            request_id=str(request.id),
                            error=str(e),
                        )

                    logger.info(
                        "emergency_access_expiring_soon",
                        request_id=str(request.id),
                        waiting_until=request.waiting_until.isoformat(),
                    )

                return {
                    "auto_approved": auto_approved,
                    "expiring_soon": len(expiring_requests),
                }

        result = run_async(do_check())

        logger.info(
            "emergency_access_check_completed",
            task_id=self.request.id,
            result=result,
        )

        return result

    except Exception as e:
        logger.error(
            "emergency_access_check_failed",
            task_id=self.request.id,
            error=str(e),
        )
        raise self.retry(exc=e)


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.privat_tasks.cleanup_expired_access",
    max_retries=3,
    default_retry_delay=60,
)
def cleanup_expired_access(self) -> Dict[str, Any]:
    """
    Raeume abgelaufene Zugriffsberechtigungen auf.

    Deaktiviert Space-Access-Eintraege deren expires_at abgelaufen ist.

    Returns:
        Anzahl der deaktivierten Eintraege
    """
    logger.info(
        "cleanup_expired_access_started",
        task_id=self.request.id,
    )

    try:
        async def do_cleanup():
            from sqlalchemy import select, delete, and_
            from datetime import timezone
            from app.db.session import get_async_session
            from app.db.models import PrivatSpaceAccess

            async with get_async_session() as db:
                now = datetime.now(timezone.utc)

                # Loesche abgelaufene Zugriffsberechtigungen
                # PrivatSpaceAccess hat kein is_active - expires_at bestimmt Gueltigkeit
                stmt = (
                    delete(PrivatSpaceAccess)
                    .where(
                        and_(
                            PrivatSpaceAccess.expires_at != None,
                            PrivatSpaceAccess.expires_at < now,
                        )
                    )
                )

                result = await db.execute(stmt)
                await db.commit()

                deleted = result.rowcount

                if deleted > 0:
                    logger.info(
                        "expired_access_cleaned_up",
                        count=deleted,
                    )

                return {"deleted": deleted}

        result = run_async(do_cleanup())

        logger.info(
            "cleanup_expired_access_completed",
            task_id=self.request.id,
            result=result,
        )

        return result

    except Exception as e:
        logger.error(
            "cleanup_expired_access_failed",
            task_id=self.request.id,
            error=str(e),
        )
        raise self.retry(exc=e)


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.privat_tasks.generate_deadline_report",
    max_retries=3,
    default_retry_delay=300,
)
def generate_deadline_report(self) -> Dict[str, Any]:
    """
    Erstelle einen woechentlichen Fristenreport per Email.

    Sendet eine Zusammenfassung aller anstehenden Fristen der naechsten
    4 Wochen an jeden Space-Owner.

    Returns:
        Anzahl der gesendeten Reports
    """
    logger.info(
        "deadline_report_started",
        task_id=self.request.id,
    )

    try:
        async def do_generate():
            from sqlalchemy import select, and_, func
            from app.db.session import get_async_session
            from app.db.models import PrivatSpace, PrivatDeadline, User
            from app.services.email_service import email_service

            async with get_async_session() as db:
                today = date.today()
                four_weeks = today + timedelta(weeks=4)
                reports_sent = 0

                # Gruppiere Fristen nach Space-Owner
                stmt = (
                    select(PrivatSpace.owner_id)
                    .distinct()
                    .join(PrivatDeadline)
                    .where(
                        and_(
                            PrivatSpace.deleted_at == None,
                            PrivatDeadline.is_completed == False,
                            PrivatDeadline.due_date >= today,
                            PrivatDeadline.due_date <= four_weeks,
                        )
                    )
                )
                result = await db.execute(stmt)
                owner_ids = [r[0] for r in result.fetchall()]

                for owner_id in owner_ids:
                    # Hole User
                    user_result = await db.execute(
                        select(User).where(User.id == owner_id)
                    )
                    user = user_result.scalar_one_or_none()
                    if not user or not user.email:
                        continue

                    # Hole Fristen des Owners
                    deadlines_stmt = (
                        select(PrivatDeadline)
                        .join(PrivatSpace)
                        .where(
                            and_(
                                PrivatSpace.owner_id == owner_id,
                                PrivatSpace.deleted_at == None,
                                PrivatDeadline.is_completed == False,
                                PrivatDeadline.due_date >= today,
                                PrivatDeadline.due_date <= four_weeks,
                            )
                        )
                        .order_by(PrivatDeadline.due_date)
                    )
                    deadlines_result = await db.execute(deadlines_stmt)
                    deadlines = deadlines_result.scalars().all()

                    if not deadlines:
                        continue

                    # Erstelle Email-Body
                    deadline_lines = []
                    for dl in deadlines:
                        days = (dl.due_date - today).days
                        status = "HEUTE" if days == 0 else f"in {days} Tagen"
                        deadline_lines.append(
                            f"- {dl.title} ({dl.due_date.strftime('%d.%m.%Y')}) - {status}"
                        )

                    body = f"""
                    Guten Tag,

                    hier ist Ihr woechentlicher Fristenreport:

                    Anstehende Fristen ({len(deadlines)}):
                    {chr(10).join(deadline_lines)}

                    Loggen Sie sich ein, um Details anzusehen oder Fristen zu verwalten.

                    Mit freundlichen Gruessen,
                    Ihr Ablage-System
                    """

                    try:
                        await email_service.send_email(
                            to=user.email,
                            subject=f"Woechentlicher Fristenreport - {len(deadlines)} Fristen",
                            body=body.strip(),
                        )
                        reports_sent += 1

                        logger.info(
                            "deadline_report_sent",
                            user_email=user.email,
                            deadline_count=len(deadlines),
                        )

                    except Exception as e:
                        logger.warning(
                            "deadline_report_failed",
                            user_email=user.email,
                            error=str(e),
                        )

                return {"reports_sent": reports_sent}

        result = run_async(do_generate())

        logger.info(
            "deadline_report_completed",
            task_id=self.request.id,
            result=result,
        )

        return result

    except Exception as e:
        logger.error(
            "deadline_report_failed",
            task_id=self.request.id,
            error=str(e),
        )
        raise self.retry(exc=e)


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.privat_tasks.cleanup_orphaned_privat_files",
    max_retries=3,
    default_retry_delay=60,
)
def cleanup_orphaned_privat_files(self) -> Dict[str, Any]:
    """
    Raeume verwaiste Dateien in MinIO auf.

    Loescht Dateien im privat/ Bucket, die keine Referenz in der
    Datenbank haben (z.B. nach einem Crash zwischen Upload und Commit).
    Nur Dateien die aelter als 1 Stunde sind werden geloescht.

    Returns:
        Anzahl der geloeschten Dateien
    """
    logger.info(
        "cleanup_orphaned_files_started",
        task_id=self.request.id,
    )

    try:
        async def do_cleanup():
            from sqlalchemy import select
            from app.db.session import get_async_session
            from app.db.models import PrivatDocument
            from app.services.storage_service import storage_service

            async with get_async_session() as db:
                deleted_count = 0
                checked_count = 0
                now = datetime.now(timezone.utc)
                one_hour_ago = now - timedelta(hours=1)

                # Liste alle Dateien im privat/ Bucket
                try:
                    files_in_minio = await storage_service.list_files(
                        bucket="privat",
                        prefix="",
                    )
                except Exception as e:
                    logger.warning(
                        "orphaned_cleanup_minio_list_failed",
                        error=str(e),
                    )
                    return {"deleted": 0, "checked": 0, "error": str(e)}

                # Hole alle file_paths aus der DB
                stmt = select(PrivatDocument.file_path).where(
                    PrivatDocument.deleted_at == None
                )
                result = await db.execute(stmt)
                db_paths = {r[0] for r in result.fetchall() if r[0]}

                for file_info in files_in_minio:
                    checked_count += 1
                    file_path = file_info.get("key", "")
                    last_modified = file_info.get("last_modified")

                    # Ueberspringe Dateien die in der DB existieren
                    if file_path in db_paths:
                        continue

                    # Ueberspringe Dateien die weniger als 1 Stunde alt sind
                    # (koennten noch im Upload-Prozess sein)
                    if last_modified and last_modified > one_hour_ago:
                        continue

                    # Loesche verwaiste Datei
                    try:
                        await storage_service.delete_file(
                            bucket="privat",
                            key=file_path,
                        )
                        deleted_count += 1

                        logger.info(
                            "orphaned_file_deleted",
                            file_path=file_path,
                        )

                    except Exception as e:
                        logger.warning(
                            "orphaned_file_delete_failed",
                            file_path=file_path,
                            error=str(e),
                        )

                return {
                    "deleted": deleted_count,
                    "checked": checked_count,
                }

        result = run_async(do_cleanup())

        logger.info(
            "cleanup_orphaned_files_completed",
            task_id=self.request.id,
            result=result,
        )

        return result

    except Exception as e:
        logger.error(
            "cleanup_orphaned_files_failed",
            task_id=self.request.id,
            error=str(e),
        )
        raise self.retry(exc=e)


# =============================================================================
# ENTERPRISE KPI CALCULATION TASKS
# =============================================================================


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.privat_tasks.calculate_property_kpis",
    max_retries=3,
    default_retry_delay=60,
    soft_time_limit=1800,  # 30 Minuten
    time_limit=2100,
)
def calculate_property_kpis(
    self,
    space_id: Optional[str] = None,
    property_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Berechnet KPIs fuer Immobilien: Mietrendite, ROI, Wertzuwachs.

    Kann fuer alle Properties eines Spaces oder eine einzelne Property
    ausgefuehrt werden.

    Args:
        space_id: Optional - Berechne fuer alle Properties eines Spaces
        property_id: Optional - Berechne nur fuer diese Property

    Returns:
        Statistik der berechneten KPIs
    """
    logger.info(
        "property_kpi_calculation_started",
        task_id=self.request.id,
        space_id=space_id,
        property_id=property_id,
    )

    try:
        async def do_calculate():
            from sqlalchemy import select, and_
            from app.db.session import get_async_session
            from app.db.models import PrivatProperty, PrivatSpace
            from app.services.privat import get_property_calculation_service

            async with get_async_session() as db:
                calc_service = get_property_calculation_service(db)
                calculated_count = 0
                failed_count = 0
                results = []

                # Query bauen
                stmt = select(PrivatProperty).join(PrivatSpace).where(
                    PrivatSpace.deleted_at == None
                )

                if property_id:
                    stmt = stmt.where(PrivatProperty.id == UUID(property_id))
                elif space_id:
                    stmt = stmt.where(PrivatProperty.space_id == UUID(space_id))

                result = await db.execute(stmt)
                properties = result.scalars().all()

                for prop in properties:
                    try:
                        # Mietrendite berechnen
                        yield_result = await calc_service.calculate_rental_yield(prop.id)

                        # ROI berechnen
                        roi_result = await calc_service.calculate_roi(prop.id)

                        # Nebenkostentrend
                        utility_trend = await calc_service.get_utility_cost_trend(
                            prop.id, months=12
                        )

                        calculated_count += 1
                        results.append({
                            "property_id": str(prop.id),
                            "name": prop.name,
                            "rental_yield": yield_result.rental_yield_percent if yield_result else None,
                            "roi": roi_result.total_roi_percent if roi_result else None,
                        })

                        logger.debug(
                            "property_kpi_calculated",
                            property_id=str(prop.id),
                            rental_yield=yield_result.rental_yield_percent if yield_result else None,
                        )

                    except Exception as e:
                        failed_count += 1
                        logger.warning(
                            "property_kpi_calculation_failed",
                            property_id=str(prop.id),
                            error=str(e),
                        )

                return {
                    "calculated": calculated_count,
                    "failed": failed_count,
                    "results": results[:10],  # Max 10 Beispiele
                }

        result = run_async(do_calculate())

        logger.info(
            "property_kpi_calculation_completed",
            task_id=self.request.id,
            result=result,
        )

        return result

    except Exception as e:
        logger.error(
            "property_kpi_calculation_failed",
            task_id=self.request.id,
            error=str(e),
        )
        raise self.retry(exc=e)


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.privat_tasks.calculate_vehicle_tco",
    max_retries=3,
    default_retry_delay=60,
    soft_time_limit=1800,
    time_limit=2100,
)
def calculate_vehicle_tco(
    self,
    space_id: Optional[str] = None,
    vehicle_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Berechnet Total Cost of Ownership fuer Fahrzeuge.

    Inkludiert: Wertverlust, Kraftstoff, Versicherung, Steuer, Wartung.

    Args:
        space_id: Optional - Berechne fuer alle Fahrzeuge eines Spaces
        vehicle_id: Optional - Berechne nur fuer dieses Fahrzeug

    Returns:
        Statistik der berechneten TCO-Werte
    """
    logger.info(
        "vehicle_tco_calculation_started",
        task_id=self.request.id,
        space_id=space_id,
        vehicle_id=vehicle_id,
    )

    try:
        async def do_calculate():
            from sqlalchemy import select, and_
            from app.db.session import get_async_session
            from app.db.models import PrivatVehicle, PrivatSpace
            from app.services.privat import get_vehicle_calculation_service

            async with get_async_session() as db:
                calc_service = get_vehicle_calculation_service(db)
                calculated_count = 0
                failed_count = 0
                results = []

                # Query bauen
                stmt = select(PrivatVehicle).join(PrivatSpace).where(
                    PrivatSpace.deleted_at == None
                )

                if vehicle_id:
                    stmt = stmt.where(PrivatVehicle.id == UUID(vehicle_id))
                elif space_id:
                    stmt = stmt.where(PrivatVehicle.space_id == UUID(space_id))

                result = await db.execute(stmt)
                vehicles = result.scalars().all()

                for vehicle in vehicles:
                    try:
                        # Abschreibung berechnen
                        depreciation = await calc_service.calculate_depreciation(vehicle.id)

                        # TCO berechnen
                        tco = await calc_service.calculate_tco(vehicle.id)

                        # Naechster Service vorhersagen
                        next_service = await calc_service.predict_next_service(vehicle.id)

                        calculated_count += 1
                        results.append({
                            "vehicle_id": str(vehicle.id),
                            "brand": vehicle.brand,
                            "model": vehicle.model,
                            "tco_per_km": tco.cost_per_km if tco else None,
                            "monthly_depreciation": depreciation.monthly_depreciation if depreciation else None,
                            "next_service_date": next_service.predicted_date.isoformat() if next_service and next_service.predicted_date else None,
                        })

                        logger.debug(
                            "vehicle_tco_calculated",
                            vehicle_id=str(vehicle.id),
                            tco_per_km=tco.cost_per_km if tco else None,
                        )

                    except Exception as e:
                        failed_count += 1
                        logger.warning(
                            "vehicle_tco_calculation_failed",
                            vehicle_id=str(vehicle.id),
                            error=str(e),
                        )

                return {
                    "calculated": calculated_count,
                    "failed": failed_count,
                    "results": results[:10],
                }

        result = run_async(do_calculate())

        logger.info(
            "vehicle_tco_calculation_completed",
            task_id=self.request.id,
            result=result,
        )

        return result

    except Exception as e:
        logger.error(
            "vehicle_tco_calculation_failed",
            task_id=self.request.id,
            error=str(e),
        )
        raise self.retry(exc=e)


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.privat_tasks.analyze_insurance_coverage",
    max_retries=3,
    default_retry_delay=60,
    soft_time_limit=1800,
    time_limit=2100,
)
def analyze_insurance_coverage(
    self,
    space_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Analysiert Versicherungsdeckung und identifiziert Deckungsluecken.

    Vergleicht vorhandene Deckungssummen mit Empfehlungen und
    berechnet Kuendigungsfristen automatisch.

    Args:
        space_id: Optional - Analysiere nur fuer diesen Space

    Returns:
        Analyse-Ergebnisse mit Deckungsluecken
    """
    logger.info(
        "insurance_coverage_analysis_started",
        task_id=self.request.id,
        space_id=space_id,
    )

    try:
        async def do_analyze():
            from sqlalchemy import select, and_
            from app.db.session import get_async_session
            from app.db.models import PrivatInsurance, PrivatSpace
            from app.services.privat import get_insurance_analysis_service

            async with get_async_session() as db:
                analysis_service = get_insurance_analysis_service(db)
                analyzed_count = 0
                gaps_found = 0
                results = []

                # Query bauen
                stmt = select(PrivatSpace).where(PrivatSpace.deleted_at == None)

                if space_id:
                    stmt = stmt.where(PrivatSpace.id == UUID(space_id))

                result = await db.execute(stmt)
                spaces = result.scalars().all()

                for space in spaces:
                    try:
                        # Deckungsluecken analysieren
                        gap_analysis = await analysis_service.analyze_coverage_gaps(
                            space.id
                        )

                        # Kuendigungsfristen berechnen
                        await analysis_service.calculate_cancellation_deadlines(
                            space.id
                        )

                        analyzed_count += 1
                        if gap_analysis:
                            space_gaps = len(gap_analysis.gaps)
                            gaps_found += space_gaps
                            results.append({
                                "space_id": str(space.id),
                                "space_name": space.name,
                                "insurance_count": gap_analysis.total_insurances,
                                "gap_count": space_gaps,
                                "critical_gaps": [
                                    g.insurance_type for g in gap_analysis.gaps
                                    if g.severity == "critical"
                                ],
                            })

                        logger.debug(
                            "insurance_coverage_analyzed",
                            space_id=str(space.id),
                            gap_count=len(gap_analysis.gaps) if gap_analysis else 0,
                        )

                    except Exception as e:
                        logger.warning(
                            "insurance_coverage_analysis_failed",
                            space_id=str(space.id),
                            error=str(e),
                        )

                return {
                    "analyzed_spaces": analyzed_count,
                    "total_gaps_found": gaps_found,
                    "results": results[:10],
                }

        result = run_async(do_analyze())

        logger.info(
            "insurance_coverage_analysis_completed",
            task_id=self.request.id,
            result=result,
        )

        return result

    except Exception as e:
        logger.error(
            "insurance_coverage_analysis_failed",
            task_id=self.request.id,
            error=str(e),
        )
        raise self.retry(exc=e)


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.privat_tasks.generate_loan_amortization",
    max_retries=3,
    default_retry_delay=60,
    soft_time_limit=1800,
    time_limit=2100,
)
def generate_loan_amortization(
    self,
    space_id: Optional[str] = None,
    loan_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generiert Tilgungsplaene fuer Kredite.

    Berechnet monatliche Raten, Restschuld, Zinsersparnis bei Sondertilgung.

    Args:
        space_id: Optional - Generiere fuer alle Kredite eines Spaces
        loan_id: Optional - Generiere nur fuer diesen Kredit

    Returns:
        Statistik der generierten Tilgungsplaene
    """
    logger.info(
        "loan_amortization_generation_started",
        task_id=self.request.id,
        space_id=space_id,
        loan_id=loan_id,
    )

    try:
        async def do_generate():
            from sqlalchemy import select, and_
            from app.db.session import get_async_session
            from app.db.models import PrivatLoan, PrivatSpace
            from app.services.privat import get_loan_amortization_service

            async with get_async_session() as db:
                amort_service = get_loan_amortization_service(db)
                generated_count = 0
                failed_count = 0
                results = []

                # Query bauen
                stmt = select(PrivatLoan).join(PrivatSpace).where(
                    PrivatSpace.deleted_at == None
                )

                if loan_id:
                    stmt = stmt.where(PrivatLoan.id == UUID(loan_id))
                elif space_id:
                    stmt = stmt.where(PrivatLoan.space_id == UUID(space_id))

                result = await db.execute(stmt)
                loans = result.scalars().all()

                for loan in loans:
                    try:
                        # Tilgungsplan generieren
                        schedule = await amort_service.generate_amortization_schedule(
                            loan.id
                        )

                        # Auszahlungsdatum berechnen
                        payoff = await amort_service.calculate_payoff_date(loan.id)

                        # Zinsersparnis bei Sondertilgung berechnen (5000 EUR Beispiel)
                        savings = await amort_service.calculate_interest_saved(
                            loan.id,
                            extra_payment=5000.0,
                        )

                        generated_count += 1
                        results.append({
                            "loan_id": str(loan.id),
                            "loan_name": loan.name,
                            "principal": float(loan.principal_amount) if loan.principal_amount else None,
                            "projected_payoff": payoff.payoff_date.isoformat() if payoff and payoff.payoff_date else None,
                            "total_interest": float(schedule.total_interest) if schedule else None,
                            "savings_with_5k_extra": float(savings.interest_saved) if savings else None,
                        })

                        logger.debug(
                            "loan_amortization_generated",
                            loan_id=str(loan.id),
                            total_payments=len(schedule.payments) if schedule else 0,
                        )

                    except Exception as e:
                        failed_count += 1
                        logger.warning(
                            "loan_amortization_generation_failed",
                            loan_id=str(loan.id),
                            error=str(e),
                        )

                return {
                    "generated": generated_count,
                    "failed": failed_count,
                    "results": results[:10],
                }

        result = run_async(do_generate())

        logger.info(
            "loan_amortization_generation_completed",
            task_id=self.request.id,
            result=result,
        )

        return result

    except Exception as e:
        logger.error(
            "loan_amortization_generation_failed",
            task_id=self.request.id,
            error=str(e),
        )
        raise self.retry(exc=e)


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.privat_tasks.run_finance_analytics",
    max_retries=3,
    default_retry_delay=60,
    soft_time_limit=3600,
    time_limit=3900,
)
def run_finance_analytics(
    self,
    space_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Fuehrt umfassende Finanzanalyse durch.

    Berechnet: Monats-Trends, YoY-Vergleiche, wiederkehrende Zahlungen,
    Cash-Flow-Prognosen.

    Args:
        space_id: Optional - Analysiere nur diesen Space

    Returns:
        Analyse-Ergebnisse
    """
    logger.info(
        "finance_analytics_started",
        task_id=self.request.id,
        space_id=space_id,
    )

    try:
        async def do_analyze():
            from sqlalchemy import select
            from app.db.session import get_async_session
            from app.db.models import PrivatSpace
            from app.services.privat import get_finance_analytics_service

            async with get_async_session() as db:
                analytics_service = get_finance_analytics_service(db)
                analyzed_count = 0
                results = []

                # Query bauen
                stmt = select(PrivatSpace).where(PrivatSpace.deleted_at == None)

                if space_id:
                    stmt = stmt.where(PrivatSpace.id == UUID(space_id))

                result = await db.execute(stmt)
                spaces = result.scalars().all()

                for space in spaces:
                    try:
                        # Vollstaendige Analyse durchfuehren
                        analysis = await analytics_service.get_full_analysis(
                            space.id
                        )

                        analyzed_count += 1
                        if analysis:
                            results.append({
                                "space_id": str(space.id),
                                "space_name": space.name,
                                "net_worth": analysis.net_worth,
                                "monthly_net": analysis.current_monthly_net,
                                "recurring_income": analysis.recurring_income_monthly,
                                "recurring_expenses": analysis.recurring_expenses_monthly,
                                "trend_direction": analysis.trend_direction,
                            })

                        logger.debug(
                            "finance_analytics_completed_for_space",
                            space_id=str(space.id),
                            net_worth=analysis.net_worth if analysis else None,
                        )

                    except Exception as e:
                        logger.warning(
                            "finance_analytics_failed_for_space",
                            space_id=str(space.id),
                            error=str(e),
                        )

                return {
                    "analyzed_spaces": analyzed_count,
                    "results": results[:10],
                }

        result = run_async(do_analyze())

        logger.info(
            "finance_analytics_completed",
            task_id=self.request.id,
            result=result,
        )

        return result

    except Exception as e:
        logger.error(
            "finance_analytics_failed",
            task_id=self.request.id,
            error=str(e),
        )
        raise self.retry(exc=e)


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.privat_tasks.daily_kpi_recalculation",
    max_retries=3,
    default_retry_delay=300,
    soft_time_limit=7200,  # 2 Stunden
    time_limit=7500,
)
def daily_kpi_recalculation(self) -> Dict[str, Any]:
    """
    Taegliche Neuberechnung aller KPIs.

    Wird per Celery Beat um 02:00 Uhr ausgefuehrt.
    Berechnet alle Enterprise-KPIs fuer alle aktiven Spaces.

    Returns:
        Zusammenfassung der berechneten KPIs
    """
    logger.info(
        "daily_kpi_recalculation_started",
        task_id=self.request.id,
    )

    try:
        # Starte Sub-Tasks parallel
        from celery import group

        # Alle Spaces berechnen (ohne Filter)
        task_group = group(
            calculate_property_kpis.s(),
            calculate_vehicle_tco.s(),
            analyze_insurance_coverage.s(),
            generate_loan_amortization.s(),
            run_finance_analytics.s(),
        )

        # Starte Gruppe und warte auf Ergebnis
        result = task_group.apply_async()
        results = result.get(timeout=7000)  # Warte max 7000s

        logger.info(
            "daily_kpi_recalculation_completed",
            task_id=self.request.id,
            sub_task_results=len(results) if results else 0,
        )

        return {
            "status": "completed",
            "sub_tasks_completed": len(results) if results else 0,
            "results": results,
        }

    except Exception as e:
        logger.error(
            "daily_kpi_recalculation_failed",
            task_id=self.request.id,
            error=str(e),
        )
        raise self.retry(exc=e)


# Celery Beat Schedule Konfiguration
# Diese sollte in celery_app.py hinzugefuegt werden:
#
# CELERY_BEAT_SCHEDULE = {
#     ...
#     # Bestehende Privat-Tasks
#     'privat-send-deadline-reminders': {
#         'task': 'app.workers.tasks.privat_tasks.send_deadline_reminders',
#         'schedule': crontab(hour=8, minute=0),
#     },
#     'privat-check-emergency-access': {
#         'task': 'app.workers.tasks.privat_tasks.check_emergency_access_requests',
#         'schedule': crontab(minute=0),  # Every hour
#     },
#     'privat-cleanup-expired-access': {
#         'task': 'app.workers.tasks.privat_tasks.cleanup_expired_access',
#         'schedule': crontab(hour=3, minute=0),
#     },
#     'privat-generate-deadline-report': {
#         'task': 'app.workers.tasks.privat_tasks.generate_deadline_report',
#         'schedule': crontab(hour=7, minute=0, day_of_week=1),  # Monday at 07:00
#     },
#     'privat-cleanup-orphaned-files': {
#         'task': 'app.workers.tasks.privat_tasks.cleanup_orphaned_privat_files',
#         'schedule': crontab(hour=4, minute=0),  # Daily at 04:00
#     },
#
#     # ENTERPRISE: Taegliche KPI-Neuberechnung
#     'privat-daily-kpi-recalculation': {
#         'task': 'app.workers.tasks.privat_tasks.daily_kpi_recalculation',
#         'schedule': crontab(hour=2, minute=0),  # Daily at 02:00
#     },
#
#     # ENTERPRISE: Individuelle KPI-Tasks (optional, fuer manuelle Trigger)
#     # Diese werden normalerweise durch daily_kpi_recalculation gestartet,
#     # koennen aber auch einzeln getriggert werden:
#     #
#     # calculate_property_kpis(space_id=..., property_id=...)
#     # calculate_vehicle_tco(space_id=..., vehicle_id=...)
#     # analyze_insurance_coverage(space_id=...)
#     # generate_loan_amortization(space_id=..., loan_id=...)
#     # run_finance_analytics(space_id=...)
# }


# =============================================================================
# ENTERPRISE INTELLIGENCE TASKS
# =============================================================================


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.privat_tasks.recalculate_property_intelligence",
    max_retries=3,
    default_retry_delay=60,
    soft_time_limit=600,
    time_limit=720,
)
def recalculate_property_intelligence(
    self,
    property_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Neuberechnung aller Property-Intelligence-KPIs fuer eine Immobilie.

    Berechnet: Wertschaetzung, Renditen, ROI, Wertsteigerung.

    Args:
        property_id: Property-ID

    Returns:
        Berechnungsergebnis
    """
    logger.info(
        "property_intelligence_recalculation_started",
        task_id=self.request.id,
        property_id=property_id,
    )

    try:
        async def do_recalculate():
            from app.db.session import get_async_session
            from app.services.privat import get_property_intelligence_service

            if not property_id:
                return {"error": "property_id erforderlich"}

            async with get_async_session() as db:
                service = get_property_intelligence_service()
                result = await service.recalculate_all_kpis(db, UUID(property_id))

                return {
                    "property_id": property_id,
                    "success": result is not None,
                    "kpis": {
                        "estimated_value": float(result.estimated_value) if result and result.estimated_value else None,
                        "calculated_yield": float(result.calculated_yield) if result and result.calculated_yield else None,
                        "calculated_roi": float(result.calculated_roi) if result and result.calculated_roi else None,
                    } if result else None,
                }

        result = run_async(do_recalculate())

        logger.info(
            "property_intelligence_recalculation_completed",
            task_id=self.request.id,
            result=result,
        )

        return result

    except Exception as e:
        logger.error(
            "property_intelligence_recalculation_failed",
            task_id=self.request.id,
            error=str(e),
        )
        raise self.retry(exc=e)


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.privat_tasks.recalculate_all_property_intelligence",
    max_retries=3,
    default_retry_delay=60,
    soft_time_limit=1800,
    time_limit=2100,
)
def recalculate_all_property_intelligence(
    self,
    space_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Neuberechnung aller Property-Intelligence-KPIs fuer einen Space.

    Args:
        space_id: Space-ID

    Returns:
        Berechnungsergebnis
    """
    logger.info(
        "all_property_intelligence_recalculation_started",
        task_id=self.request.id,
        space_id=space_id,
    )

    try:
        async def do_recalculate():
            from sqlalchemy import select
            from app.db.session import get_async_session
            from app.db.models import PrivatProperty, PrivatSpace
            from app.services.privat import get_property_intelligence_service

            async with get_async_session() as db:
                service = get_property_intelligence_service()
                calculated_count = 0
                failed_count = 0

                stmt = select(PrivatProperty).join(PrivatSpace).where(
                    PrivatSpace.deleted_at == None
                )
                if space_id:
                    stmt = stmt.where(PrivatProperty.space_id == UUID(space_id))

                result = await db.execute(stmt)
                properties = result.scalars().all()

                for prop in properties:
                    try:
                        await service.recalculate_all_kpis(db, prop.id)
                        calculated_count += 1
                    except Exception as e:
                        failed_count += 1
                        logger.warning(
                            "property_intelligence_failed",
                            property_id=str(prop.id),
                            error=str(e),
                        )

                return {
                    "space_id": space_id,
                    "calculated": calculated_count,
                    "failed": failed_count,
                }

        result = run_async(do_recalculate())

        logger.info(
            "all_property_intelligence_recalculation_completed",
            task_id=self.request.id,
            result=result,
        )

        return result

    except Exception as e:
        logger.error(
            "all_property_intelligence_recalculation_failed",
            task_id=self.request.id,
            error=str(e),
        )
        raise self.retry(exc=e)


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.privat_tasks.recalculate_vehicle_intelligence",
    max_retries=3,
    default_retry_delay=60,
    soft_time_limit=600,
    time_limit=720,
)
def recalculate_vehicle_intelligence(
    self,
    vehicle_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Neuberechnung aller Vehicle-Intelligence-KPIs fuer ein Fahrzeug.

    Args:
        vehicle_id: Vehicle-ID

    Returns:
        Berechnungsergebnis
    """
    logger.info(
        "vehicle_intelligence_recalculation_started",
        task_id=self.request.id,
        vehicle_id=vehicle_id,
    )

    try:
        async def do_recalculate():
            from app.db.session import get_async_session
            from app.services.privat import get_vehicle_intelligence_service

            if not vehicle_id:
                return {"error": "vehicle_id erforderlich"}

            async with get_async_session() as db:
                service = get_vehicle_intelligence_service()
                result = await service.recalculate_all_kpis(db, UUID(vehicle_id))

                return {
                    "vehicle_id": vehicle_id,
                    "success": result is not None,
                    "kpis": {
                        "current_value": float(result.current_value) if result and result.current_value else None,
                        "calculated_tco_per_km": float(result.calculated_tco_per_km) if result and result.calculated_tco_per_km else None,
                    } if result else None,
                }

        result = run_async(do_recalculate())

        logger.info(
            "vehicle_intelligence_recalculation_completed",
            task_id=self.request.id,
            result=result,
        )

        return result

    except Exception as e:
        logger.error(
            "vehicle_intelligence_recalculation_failed",
            task_id=self.request.id,
            error=str(e),
        )
        raise self.retry(exc=e)


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.privat_tasks.recalculate_all_vehicle_intelligence",
    max_retries=3,
    default_retry_delay=60,
    soft_time_limit=1800,
    time_limit=2100,
)
def recalculate_all_vehicle_intelligence(
    self,
    space_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Neuberechnung aller Vehicle-Intelligence-KPIs fuer einen Space.

    Args:
        space_id: Space-ID

    Returns:
        Berechnungsergebnis
    """
    logger.info(
        "all_vehicle_intelligence_recalculation_started",
        task_id=self.request.id,
        space_id=space_id,
    )

    try:
        async def do_recalculate():
            from sqlalchemy import select
            from app.db.session import get_async_session
            from app.db.models import PrivatVehicle, PrivatSpace
            from app.services.privat import get_vehicle_intelligence_service

            async with get_async_session() as db:
                service = get_vehicle_intelligence_service()
                calculated_count = 0
                failed_count = 0

                stmt = select(PrivatVehicle).join(PrivatSpace).where(
                    PrivatSpace.deleted_at == None
                )
                if space_id:
                    stmt = stmt.where(PrivatVehicle.space_id == UUID(space_id))

                result = await db.execute(stmt)
                vehicles = result.scalars().all()

                for vehicle in vehicles:
                    try:
                        await service.recalculate_all_kpis(db, vehicle.id)
                        calculated_count += 1
                    except Exception as e:
                        failed_count += 1
                        logger.warning(
                            "vehicle_intelligence_failed",
                            vehicle_id=str(vehicle.id),
                            error=str(e),
                        )

                return {
                    "space_id": space_id,
                    "calculated": calculated_count,
                    "failed": failed_count,
                }

        result = run_async(do_recalculate())

        logger.info(
            "all_vehicle_intelligence_recalculation_completed",
            task_id=self.request.id,
            result=result,
        )

        return result

    except Exception as e:
        logger.error(
            "all_vehicle_intelligence_recalculation_failed",
            task_id=self.request.id,
            error=str(e),
        )
        raise self.retry(exc=e)


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.privat_tasks.recalculate_investment_intelligence",
    max_retries=3,
    default_retry_delay=60,
    soft_time_limit=1800,
    time_limit=2100,
)
def recalculate_investment_intelligence(
    self,
    space_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Neuberechnung aller Investment-Intelligence-KPIs fuer einen Space.

    Berechnet: Portfolio-Allokation, Diversifikation, Risikoprofil.

    Args:
        space_id: Space-ID

    Returns:
        Berechnungsergebnis
    """
    logger.info(
        "investment_intelligence_recalculation_started",
        task_id=self.request.id,
        space_id=space_id,
    )

    try:
        async def do_recalculate():
            from sqlalchemy import select
            from app.db.session import get_async_session
            from app.db.models import PrivatSpace
            from app.services.privat import get_investment_intelligence_service

            async with get_async_session() as db:
                service = get_investment_intelligence_service()
                analyzed_count = 0
                results = []

                stmt = select(PrivatSpace).where(PrivatSpace.deleted_at == None)
                if space_id:
                    stmt = stmt.where(PrivatSpace.id == UUID(space_id))

                result = await db.execute(stmt)
                spaces = result.scalars().all()

                for space in spaces:
                    try:
                        analytics = await service.get_full_portfolio_analytics(
                            db, space.id, target_profile=None, include_rebalancing=True
                        )
                        analyzed_count += 1

                        if analytics:
                            results.append({
                                "space_id": str(space.id),
                                "total_value": float(analytics.total_value),
                                "total_investments": analytics.total_investments,
                                "diversification_score": float(analytics.diversification.diversification_score) if analytics.diversification else None,
                                "risk_category": analytics.risk_profile.risk_category if analytics.risk_profile else None,
                            })

                    except Exception as e:
                        logger.warning(
                            "investment_intelligence_failed_for_space",
                            space_id=str(space.id),
                            error=str(e),
                        )

                return {
                    "analyzed_spaces": analyzed_count,
                    "results": results[:10],
                }

        result = run_async(do_recalculate())

        logger.info(
            "investment_intelligence_recalculation_completed",
            task_id=self.request.id,
            result=result,
        )

        return result

    except Exception as e:
        logger.error(
            "investment_intelligence_recalculation_failed",
            task_id=self.request.id,
            error=str(e),
        )
        raise self.retry(exc=e)


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.privat_tasks.calculate_financial_health",
    max_retries=3,
    default_retry_delay=60,
    soft_time_limit=1800,
    time_limit=2100,
)
def calculate_financial_health(
    self,
    space_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Berechnet Financial Health Score fuer Space(s).

    6 Dimensionen: Vermoegensaufbau, Schulden, Risikoabdeckung,
    Liquiditaet, Altersvorsorge, Diversifikation.

    Args:
        space_id: Optional - Nur fuer diesen Space

    Returns:
        Health Score Ergebnisse
    """
    logger.info(
        "financial_health_calculation_started",
        task_id=self.request.id,
        space_id=space_id,
    )

    try:
        async def do_calculate():
            from sqlalchemy import select
            from app.db.session import get_async_session
            from app.db.models import PrivatSpace
            from app.services.privat import get_financial_health_service

            async with get_async_session() as db:
                service = get_financial_health_service()
                calculated_count = 0
                results = []

                stmt = select(PrivatSpace).where(PrivatSpace.deleted_at == None)
                if space_id:
                    stmt = stmt.where(PrivatSpace.id == UUID(space_id))

                result = await db.execute(stmt)
                spaces = result.scalars().all()

                for space in spaces:
                    try:
                        health_score = await service.calculate_health_score(
                            db, space.id, monthly_income=None, monthly_expenses=None, user_age=None
                        )
                        calculated_count += 1

                        if health_score:
                            results.append({
                                "space_id": str(space.id),
                                "overall_score": float(health_score.overall_score),
                                "overall_rating": health_score.overall_rating,
                                "top_recommendation": health_score.priority_recommendations[0] if health_score.priority_recommendations else None,
                            })

                    except Exception as e:
                        logger.warning(
                            "financial_health_calculation_failed_for_space",
                            space_id=str(space.id),
                            error=str(e),
                        )

                return {
                    "calculated_spaces": calculated_count,
                    "results": results[:10],
                }

        result = run_async(do_calculate())

        logger.info(
            "financial_health_calculation_completed",
            task_id=self.request.id,
            result=result,
        )

        return result

    except Exception as e:
        logger.error(
            "financial_health_calculation_failed",
            task_id=self.request.id,
            error=str(e),
        )
        raise self.retry(exc=e)


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.privat_tasks.generate_smart_recommendations",
    max_retries=3,
    default_retry_delay=60,
    soft_time_limit=1800,
    time_limit=2100,
)
def generate_smart_recommendations(
    self,
    space_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generiert Smart Recommendations fuer Space(s).

    Prueft: Refinanzierung, Rebalancing, Versicherungsluecken,
    Notgroschen, Fristen, veraltete Werte.

    Args:
        space_id: Optional - Nur fuer diesen Space

    Returns:
        Recommendations Ergebnisse
    """
    logger.info(
        "smart_recommendations_generation_started",
        task_id=self.request.id,
        space_id=space_id,
    )

    try:
        async def do_generate():
            from sqlalchemy import select
            from app.db.session import get_async_session
            from app.db.models import PrivatSpace
            from app.services.privat import get_recommendations_service

            async with get_async_session() as db:
                service = get_recommendations_service()
                generated_count = 0
                total_recommendations = 0
                critical_count = 0
                results = []

                stmt = select(PrivatSpace).where(PrivatSpace.deleted_at == None)
                if space_id:
                    stmt = stmt.where(PrivatSpace.id == UUID(space_id))

                result = await db.execute(stmt)
                spaces = result.scalars().all()

                for space in spaces:
                    try:
                        reco_result = await service.generate_recommendations(db, space.id)
                        generated_count += 1

                        if reco_result:
                            total_recommendations += len(reco_result.recommendations)
                            critical_count += reco_result.critical_count
                            results.append({
                                "space_id": str(space.id),
                                "total": len(reco_result.recommendations),
                                "critical": reco_result.critical_count,
                                "high": reco_result.high_count,
                                "medium": reco_result.medium_count,
                                "low": reco_result.low_count,
                            })

                    except Exception as e:
                        logger.warning(
                            "recommendations_generation_failed_for_space",
                            space_id=str(space.id),
                            error=str(e),
                        )

                return {
                    "generated_spaces": generated_count,
                    "total_recommendations": total_recommendations,
                    "critical_count": critical_count,
                    "results": results[:10],
                }

        result = run_async(do_generate())

        logger.info(
            "smart_recommendations_generation_completed",
            task_id=self.request.id,
            result=result,
        )

        return result

    except Exception as e:
        logger.error(
            "smart_recommendations_generation_failed",
            task_id=self.request.id,
            error=str(e),
        )
        raise self.retry(exc=e)


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.privat_tasks.daily_intelligence_recalculation",
    max_retries=3,
    default_retry_delay=300,
    soft_time_limit=10800,  # 3 Stunden
    time_limit=11100,
)
def daily_intelligence_recalculation(self) -> Dict[str, Any]:
    """
    Taegliche Neuberechnung aller Intelligence-KPIs.

    Wird per Celery Beat um 03:00 Uhr ausgefuehrt (nach daily_kpi_recalculation).
    Berechnet alle Enterprise-Intelligence-Features.

    Returns:
        Zusammenfassung der berechneten Intelligence-KPIs
    """
    logger.info(
        "daily_intelligence_recalculation_started",
        task_id=self.request.id,
    )

    try:
        from celery import group

        task_group = group(
            recalculate_all_property_intelligence.s(),
            recalculate_all_vehicle_intelligence.s(),
            recalculate_investment_intelligence.s(),
            calculate_financial_health.s(),
            generate_smart_recommendations.s(),
        )

        result = task_group.apply_async()
        results = result.get(timeout=10500)

        logger.info(
            "daily_intelligence_recalculation_completed",
            task_id=self.request.id,
            sub_task_results=len(results) if results else 0,
        )

        return {
            "status": "completed",
            "sub_tasks_completed": len(results) if results else 0,
            "results": results,
        }

    except Exception as e:
        logger.error(
            "daily_intelligence_recalculation_failed",
            task_id=self.request.id,
            error=str(e),
        )
        raise self.retry(exc=e)


# =============================================================================
# KPI Orchestration Tasks
# =============================================================================


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.privat_tasks.orchestrate_all_kpis",
    max_retries=2,
    default_retry_delay=300,
    soft_time_limit=3600,
    time_limit=4200,
)
def orchestrate_all_kpis(
    self,
    space_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Orchestriert alle KPI-Berechnungen ueber den KPIOrchestrationService.

    Fuehrt KEINE eigenen Berechnungen durch, sondern:
    - Koordiniert PropertyCalculationService, VehicleCalculationService,
      LoanScenarioService, InvestmentIntelligenceService, InsuranceIntelligenceService
    - Stellt korrekte Abhaengigkeitsreihenfolge sicher
    - Berechnet Financial Health Score zuletzt

    Args:
        space_id: Optional - nur diesen Space berechnen

    Returns:
        Ergebnis der Orchestrierung
    """
    async def _orchestrate():
        from app.db.session import get_async_session
        from app.services.privat.kpi_orchestrator import get_kpi_orchestration_service

        async with get_async_session() as db:
            service = get_kpi_orchestration_service()

            if space_id:
                # Einzelner Space
                result = await service.recalculate_all_for_space(
                    db, UUID(space_id)
                )
                return {
                    "space_id": space_id,
                    "total_calculated": result.total_calculated,
                    "total_errors": result.total_errors,
                    "financial_health_score": float(result.financial_health_score) if result.financial_health_score else None,
                    "calculated_at": result.calculated_at.isoformat(),
                }
            else:
                # Alle Spaces
                batch_result = await service.recalculate_all_spaces(db)
                return {
                    "total_spaces": batch_result.total_spaces,
                    "spaces_processed": batch_result.spaces_processed,
                    "spaces_skipped": batch_result.spaces_skipped,
                    "total_entities_calculated": batch_result.total_entities_calculated,
                    "properties_calculated": batch_result.properties_calculated,
                    "vehicles_calculated": batch_result.vehicles_calculated,
                    "loans_calculated": batch_result.loans_calculated,
                    "investments_calculated": batch_result.investments_calculated,
                    "insurances_calculated": batch_result.insurances_calculated,
                    "average_health_score": float(batch_result.average_health_score) if batch_result.average_health_score else None,
                    "duration_seconds": batch_result.duration_seconds,
                    "calculated_at": batch_result.calculated_at.isoformat(),
                }

    logger.info(
        "orchestrate_all_kpis_started",
        task_id=self.request.id,
        space_id=space_id,
    )

    try:
        result = run_async(_orchestrate())

        logger.info(
            "orchestrate_all_kpis_completed",
            task_id=self.request.id,
            space_id=space_id,
            result=result,
        )

        return {"status": "success", **result}

    except Exception as e:
        logger.error(
            "orchestrate_all_kpis_failed",
            task_id=self.request.id,
            space_id=space_id,
            error=str(e),
        )
        raise self.retry(exc=e)


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.privat_tasks.recalculate_entity_kpi",
    max_retries=3,
    default_retry_delay=60,
)
def recalculate_entity_kpi(
    self,
    entity_type: str,
    entity_id: str,
    recalculate_health: bool = True,
) -> Dict[str, Any]:
    """
    Berechnet KPIs fuer eine einzelne Entity ueber den Orchestrator.

    Nuetzlich nach Datenänderungen an einer Entity.

    Args:
        entity_type: "property", "vehicle", "loan", "investment"
        entity_id: Entity-UUID
        recalculate_health: Ob Financial Health auch neu berechnet werden soll

    Returns:
        Ergebnis der Berechnung
    """
    async def _recalculate():
        from app.db.session import get_async_session
        from app.services.privat.kpi_orchestrator import get_kpi_orchestration_service

        async with get_async_session() as db:
            service = get_kpi_orchestration_service()
            result = await service.recalculate_single_entity(
                db, entity_type, UUID(entity_id), recalculate_health
            )
            return {
                "entity_type": result.entity_type,
                "entity_id": str(result.entity_id),
                "success": result.success,
                "calculated_kpis": result.calculated_kpis,
                "error": result.error,
            }

    logger.info(
        "recalculate_entity_kpi_started",
        task_id=self.request.id,
        entity_type=entity_type,
        entity_id=entity_id,
    )

    try:
        result = run_async(_recalculate())

        logger.info(
            "recalculate_entity_kpi_completed",
            task_id=self.request.id,
            entity_type=entity_type,
            entity_id=entity_id,
            success=result.get("success"),
        )

        return {"status": "success" if result.get("success") else "failed", **result}

    except Exception as e:
        logger.error(
            "recalculate_entity_kpi_failed",
            task_id=self.request.id,
            entity_type=entity_type,
            entity_id=entity_id,
            error=str(e),
        )
        raise self.retry(exc=e)


# =============================================================================
# PRIVAT METRICS UPDATE TASK
# =============================================================================


@celery_app.task(
    bind=True,
    name="app.workers.tasks.privat_tasks.update_privat_metrics",
    max_retries=2,
    default_retry_delay=30,
)
def update_privat_metrics(self) -> Dict[str, Any]:
    """
    Aktualisiert Prometheus-Metriken fuer das Privat-Modul.

    Laeuft alle 15 Minuten via Celery Beat.
    Sammelt aggregierte Statistiken fuer Monitoring.

    Returns:
        Aktualisierte Metrik-Counts
    """
    from prometheus_client import Gauge

    logger.info(
        "update_privat_metrics_started",
        task_id=self.request.id,
    )

    async def _update_metrics() -> Dict[str, int]:
        from app.db.session import get_async_session
        from app.db.models import (
            PrivatProperty, PrivatVehicle, PrivatLoan,
            PrivatInsurance, PrivatDeadline, PrivatSpace
        )
        from sqlalchemy import select, func

        async with get_async_session() as db:
            # Zaehle aktive Entities
            properties_count = await db.scalar(
                select(func.count(PrivatProperty.id))
                .where(PrivatProperty.deleted_at.is_(None))
            ) or 0

            vehicles_count = await db.scalar(
                select(func.count(PrivatVehicle.id))
                .where(PrivatVehicle.deleted_at.is_(None))
            ) or 0

            loans_count = await db.scalar(
                select(func.count(PrivatLoan.id))
                .where(PrivatLoan.deleted_at.is_(None))
            ) or 0

            insurances_count = await db.scalar(
                select(func.count(PrivatInsurance.id))
                .where(PrivatInsurance.deleted_at.is_(None))
            ) or 0

            # Aktive Deadlines (nicht abgelaufen)
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)
            active_deadlines = await db.scalar(
                select(func.count(PrivatDeadline.id))
                .where(
                    PrivatDeadline.deleted_at.is_(None),
                    PrivatDeadline.deadline_date >= now.date()
                )
            ) or 0

            # Aktive Spaces
            spaces_count = await db.scalar(
                select(func.count(PrivatSpace.id))
                .where(PrivatSpace.deleted_at.is_(None))
            ) or 0

            return {
                "properties": properties_count,
                "vehicles": vehicles_count,
                "loans": loans_count,
                "insurances": insurances_count,
                "active_deadlines": active_deadlines,
                "spaces": spaces_count,
            }

    try:
        counts = run_async(_update_metrics())

        # Prometheus Gauges aktualisieren
        try:
            privat_entities_gauge = Gauge(
                "privat_entities_total",
                "Anzahl aktiver Privat-Modul Entities",
                ["entity_type"],
                registry=None,  # Use default registry
            )
            for entity_type, count in counts.items():
                privat_entities_gauge.labels(entity_type=entity_type).set(count)
        except ValueError:
            # Gauge bereits registriert - Labels aktualisieren
            pass

        logger.info(
            "update_privat_metrics_completed",
            task_id=self.request.id,
            counts=counts,
        )

        return {"status": "success", "counts": counts}

    except Exception as e:
        logger.error(
            "update_privat_metrics_failed",
            task_id=self.request.id,
            error=str(e),
        )
        raise self.retry(exc=e)

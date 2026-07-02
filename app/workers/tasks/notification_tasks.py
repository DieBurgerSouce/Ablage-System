# -*- coding: utf-8 -*-
"""
Celery Tasks für Benachrichtigungen.

Geplante Tasks:
- send_daily_digest: Tägliche E-Mail-Zusammenfassung (08:00 Uhr)
- send_weekly_digest: Wöchentliche E-Mail-Zusammenfassung (Montag 08:00)
- cleanup_old_notifications: Alte Benachrichtigungen löschen (Sonntag 04:00)

Feinpoliert und durchdacht - Zuverlässige Benachrichtigungen für Benutzer.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import select, func, and_, cast
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from app.workers.celery_app import celery_app, CPUTask
from app.db.session import get_async_session_context
from app.db.models import User, Document, UserNotification
from app.core.safe_errors import safe_error_log, safe_error_detail

logger = structlog.get_logger(__name__)


def run_async(coro):
    """Hilfsfunktion um async Code in sync Celery Tasks auszuführen.

    MEMORY FIX: Verwendet asyncio.run() statt new_event_loop() um Memory Leaks
    zu verhindern. asyncio.run() erstellt einen neuen Event-Loop, führt die
    Coroutine aus und schließt den Loop korrekt inkl. aller pending Tasks.
    """
    return asyncio.run(coro)


# =============================================================================
# DIGEST TEMPLATES (German)
# =============================================================================

DAILY_DIGEST_TEMPLATE = """
Guten Morgen {username},

Hier ist Ihre tägliche Zusammenfassung für den {date}:

📄 DOKUMENTE
{documents_section}

🔔 BENACHRICHTIGUNGEN
{notifications_section}

📊 STATISTIKEN
- Dokumente verarbeitet: {total_documents}
- Neue Benachrichtigungen: {total_notifications}
- Ungelesene Nachrichten: {unread_count}

---
Ablage-System - Feinpoliert und durchdacht
Diese E-Mail wurde automatisch generiert.
""".strip()

WEEKLY_DIGEST_TEMPLATE = """
Guten Morgen {username},

Hier ist Ihre wöchentliche Zusammenfassung ({week_start} - {week_end}):

📄 DOKUMENTE DIESE WOCHE
{documents_section}

🔔 WICHTIGE BENACHRICHTIGUNGEN
{notifications_section}

📊 WOCHENSTATISTIKEN
- Dokumente verarbeitet: {total_documents}
- OCR-Erfolgsrate: {ocr_success_rate}%
- Benachrichtigungen erhalten: {total_notifications}
- Durchschnittliche Verarbeitungszeit: {avg_processing_time}

📈 TREND
{trend_section}

---
Ablage-System - Feinpoliert und durchdacht
Diese E-Mail wurde automatisch generiert.
""".strip()


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def format_avg_processing_time(avg_ms: Optional[float]) -> str:
    """Formatiere durchschnittliche Verarbeitungszeit für Anzeige."""
    if avg_ms is None:
        return "Nicht verfügbar"
    if avg_ms < 1000:
        return f"< 1 Sekunde"
    elif avg_ms < 60000:
        seconds = avg_ms / 1000
        return f"{seconds:.1f} Sekunden"
    else:
        minutes = avg_ms / 60000
        return f"{minutes:.1f} Minuten"


async def get_users_with_digest_preference(
    db: AsyncSession,
    digest_type: str
) -> List[User]:
    """Hole alle Benutzer mit aktiviertem Digest."""
    # Benutzer mit aktiver digest-Einstellung
    result = await db.execute(
        select(User).where(
            and_(
                User.is_active == True,
                User.email.isnot(None),
                # JSONB-Abfrage für preferences->notifications->email_digest
                cast(User.preferences, JSONB)["notifications"]["email_digest"].astext == digest_type
            )
        )
    )
    return list(result.scalars().all())


async def get_user_document_stats(
    db: AsyncSession,
    user_id: str,
    since: datetime
) -> Dict[str, Any]:
    """Hole Dokumentstatistiken für einen Benutzer."""
    # Dokumente seit Zeitpunkt
    doc_result = await db.execute(
        select(func.count(Document.id)).where(
            and_(
                Document.uploaded_by_id == user_id,
                Document.uploaded_at >= since
            )
        )
    )
    total_docs = doc_result.scalar() or 0

    # Erfolgreiche OCR
    ocr_result = await db.execute(
        select(func.count(Document.id)).where(
            and_(
                Document.uploaded_by_id == user_id,
                Document.uploaded_at >= since,
                Document.ocr_status == "completed"
            )
        )
    )
    successful_ocr = ocr_result.scalar() or 0

    # Fehlgeschlagene OCR
    failed_result = await db.execute(
        select(func.count(Document.id)).where(
            and_(
                Document.uploaded_by_id == user_id,
                Document.uploaded_at >= since,
                Document.ocr_status == "failed"
            )
        )
    )
    failed_ocr = failed_result.scalar() or 0

    # Durchschnittliche Verarbeitungszeit berechnen
    avg_time_result = await db.execute(
        select(func.avg(Document.processing_duration_ms)).where(
            and_(
                Document.uploaded_by_id == user_id,
                Document.uploaded_at >= since,
                Document.processing_duration_ms.isnot(None),
            )
        )
    )
    avg_processing_ms = avg_time_result.scalar()

    return {
        "total": total_docs,
        "successful": successful_ocr,
        "failed": failed_ocr,
        "success_rate": round(successful_ocr / total_docs * 100, 1) if total_docs > 0 else 0,
        "avg_processing_time_ms": avg_processing_ms,
    }


async def get_user_notifications(
    db: AsyncSession,
    user_id: str,
    since: datetime,
    limit: int = 10
) -> List[UserNotification]:
    """Hole Benachrichtigungen für einen Benutzer."""
    result = await db.execute(
        select(UserNotification).where(
            and_(
                UserNotification.user_id == user_id,
                UserNotification.created_at >= since
            )
        ).order_by(UserNotification.created_at.desc()).limit(limit)
    )
    return list(result.scalars().all())


async def get_unread_notification_count(
    db: AsyncSession,
    user_id: str
) -> int:
    """Hole Anzahl ungelesener Benachrichtigungen."""
    result = await db.execute(
        select(func.count(UserNotification.id)).where(
            and_(
                UserNotification.user_id == user_id,
                UserNotification.is_read == False
            )
        )
    )
    return result.scalar() or 0


def format_documents_section(stats: Dict[str, Any]) -> str:
    """Formatiere Dokumenten-Sektion für E-Mail."""
    if stats["total"] == 0:
        return "- Keine neuen Dokumente"

    lines = [
        f"- {stats['total']} Dokument(e) hochgeladen",
        f"- {stats['successful']} erfolgreich verarbeitet",
    ]

    if stats["failed"] > 0:
        lines.append(f"- ⚠️ {stats['failed']} mit Fehlern")

    return "\n".join(lines)


def format_notifications_section(notifications: List[UserNotification]) -> str:
    """Formatiere Benachrichtigungs-Sektion für E-Mail."""
    if not notifications:
        return "- Keine neuen Benachrichtigungen"

    lines = []
    for notif in notifications[:5]:  # Max 5 Benachrichtigungen
        icon = "📬" if not notif.is_read else "📭"
        lines.append(f"{icon} {notif.title}")

    if len(notifications) > 5:
        lines.append(f"... und {len(notifications) - 5} weitere")

    return "\n".join(lines)


async def send_digest_email(
    user: User,
    subject: str,
    body: str
) -> bool:
    """Sende Digest-E-Mail an Benutzer."""
    from app.services.notification_service import EmailNotifier

    notifier = EmailNotifier()

    if not notifier.is_configured:
        logger.warning(
            "digest_email_not_configured",
            user_id=str(user.id)
        )
        return False

    if not user.email:
        logger.warning(
            "user_has_no_email",
            user_id=str(user.id)
        )
        return False

    return await notifier.send(
        to_email=user.email,
        subject=subject,
        body=body
    )


# =============================================================================
# CELERY TASKS
# =============================================================================

@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.notification_tasks.send_daily_digest",
    max_retries=3,
    default_retry_delay=300,
)
def send_daily_digest(self) -> Dict[str, Any]:
    """
    Celery Task für tägliche E-Mail-Zusammenfassung.

    Sendet eine Zusammenfassung an alle Benutzer mit email_digest='daily'.
    Wird täglich um 08:00 Uhr ausgeführt.

    Returns:
        Dict mit Ergebnissen (gesendet, fehlgeschlagen, übersprungen)
    """
    logger.info("daily_digest_task_gestartet", task_id=self.request.id)

    async def run_digest():
        async with get_async_session_context() as db:
            users = await get_users_with_digest_preference(db, "daily")

            results = {
                "gesendet": 0,
                "fehlgeschlagen": 0,
                "übersprungen": 0,
                "benutzer_insgesamt": len(users)
            }

            # Zeitraum: Letzte 24 Stunden
            since = datetime.now(timezone.utc) - timedelta(days=1)
            today = datetime.now(timezone.utc).strftime("%d.%m.%Y")

            for user in users:
                try:
                    # Statistiken sammeln
                    doc_stats = await get_user_document_stats(db, str(user.id), since)
                    notifications = await get_user_notifications(db, str(user.id), since)
                    unread = await get_unread_notification_count(db, str(user.id))

                    # Keine Aktivität? Überspringen
                    if doc_stats["total"] == 0 and len(notifications) == 0:
                        results["übersprungen"] += 1
                        continue

                    # E-Mail-Body erstellen
                    body = DAILY_DIGEST_TEMPLATE.format(
                        username=user.full_name or user.username,
                        date=today,
                        documents_section=format_documents_section(doc_stats),
                        notifications_section=format_notifications_section(notifications),
                        total_documents=doc_stats["total"],
                        total_notifications=len(notifications),
                        unread_count=unread
                    )

                    # E-Mail senden
                    success = await send_digest_email(
                        user=user,
                        subject=f"Ablage-System - Tägliche Zusammenfassung ({today})",
                        body=body
                    )

                    if success:
                        results["gesendet"] += 1
                    else:
                        results["fehlgeschlagen"] += 1

                except Exception as e:
                    logger.error(
                        "daily_digest_user_error",
                        user_id=str(user.id),
                        **safe_error_log(e)
                    )
                    results["fehlgeschlagen"] += 1

            return results

    try:
        results = run_async(run_digest())
        logger.info(
            "daily_digest_task_abgeschlossen",
            task_id=self.request.id,
            **results
        )
        return results

    except Exception as e:
        logger.error(
            "daily_digest_task_fehler",
            task_id=self.request.id,
            **safe_error_log(e)
        )
        raise self.retry(exc=e)


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.notification_tasks.send_weekly_digest",
    max_retries=3,
    default_retry_delay=300,
)
def send_weekly_digest(self) -> Dict[str, Any]:
    """
    Celery Task für wöchentliche E-Mail-Zusammenfassung.

    Sendet eine Zusammenfassung an alle Benutzer mit email_digest='weekly'.
    Wird jeden Montag um 08:00 Uhr ausgeführt.

    Returns:
        Dict mit Ergebnissen (gesendet, fehlgeschlagen, übersprungen)
    """
    logger.info("weekly_digest_task_gestartet", task_id=self.request.id)

    async def run_digest():
        async with get_async_session_context() as db:
            users = await get_users_with_digest_preference(db, "weekly")

            results = {
                "gesendet": 0,
                "fehlgeschlagen": 0,
                "übersprungen": 0,
                "benutzer_insgesamt": len(users)
            }

            # Zeitraum: Letzte 7 Tage
            now = datetime.now(timezone.utc)
            since = now - timedelta(days=7)
            week_start = since.strftime("%d.%m.%Y")
            week_end = now.strftime("%d.%m.%Y")

            for user in users:
                try:
                    # Statistiken sammeln
                    doc_stats = await get_user_document_stats(db, str(user.id), since)
                    notifications = await get_user_notifications(db, str(user.id), since, limit=15)
                    unread = await get_unread_notification_count(db, str(user.id))

                    # Keine Aktivität? Überspringen
                    if doc_stats["total"] == 0 and len(notifications) == 0:
                        results["übersprungen"] += 1
                        continue

                    # Trend-Sektion
                    prev_week_since = since - timedelta(days=7)
                    prev_stats = await get_user_document_stats(db, str(user.id), prev_week_since)

                    if prev_stats["total"] > 0:
                        change = ((doc_stats["total"] - prev_stats["total"]) / prev_stats["total"]) * 100
                        if change > 0:
                            trend = f"📈 {change:.0f}% mehr Dokumente als letzte Woche"
                        elif change < 0:
                            trend = f"📉 {abs(change):.0f}% weniger Dokumente als letzte Woche"
                        else:
                            trend = "➡️ Gleiche Aktivität wie letzte Woche"
                    else:
                        trend = "📊 Keine Vergleichsdaten verfügbar"

                    # E-Mail-Body erstellen
                    body = WEEKLY_DIGEST_TEMPLATE.format(
                        username=user.full_name or user.username,
                        week_start=week_start,
                        week_end=week_end,
                        documents_section=format_documents_section(doc_stats),
                        notifications_section=format_notifications_section(notifications),
                        total_documents=doc_stats["total"],
                        ocr_success_rate=doc_stats["success_rate"],
                        total_notifications=len(notifications),
                        avg_processing_time=format_avg_processing_time(doc_stats.get("avg_processing_time_ms")),
                        trend_section=trend
                    )

                    # E-Mail senden
                    success = await send_digest_email(
                        user=user,
                        subject=f"Ablage-System - Wöchentliche Zusammenfassung",
                        body=body
                    )

                    if success:
                        results["gesendet"] += 1
                    else:
                        results["fehlgeschlagen"] += 1

                except Exception as e:
                    logger.error(
                        "weekly_digest_user_error",
                        user_id=str(user.id),
                        **safe_error_log(e)
                    )
                    results["fehlgeschlagen"] += 1

            return results

    try:
        results = run_async(run_digest())
        logger.info(
            "weekly_digest_task_abgeschlossen",
            task_id=self.request.id,
            **results
        )
        return results

    except Exception as e:
        logger.error(
            "weekly_digest_task_fehler",
            task_id=self.request.id,
            **safe_error_log(e)
        )
        raise self.retry(exc=e)


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.notification_tasks.send_dunning_email_with_retry",
    max_retries=5,
    default_retry_delay=30,  # Base delay, wird exponentiell erhöht
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,  # Max 10 Minuten zwischen Retries
    retry_jitter=True,  # Zufällige Variation um Thundering Herd zu vermeiden
)
def send_dunning_email_with_retry(
    self,
    notification_id: str,
    recipient_email: str,
    subject: str,
    body: str,
    pdf_attachment: Optional[bytes] = None,
    attachment_filename: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Sendet Mahnungs-E-Mails mit exponential backoff Retry-Logik.

    Retry-Intervalle (mit Jitter):
    - Versuch 1: sofort
    - Versuch 2: ~30s
    - Versuch 3: ~60s
    - Versuch 4: ~120s
    - Versuch 5: ~240s
    - Versuch 6: ~480s

    Args:
        notification_id: ID der zugehoerigen Notification
        recipient_email: Empfänger-E-Mail
        subject: E-Mail-Betreff
        body: E-Mail-Text (Plain Text oder HTML)
        pdf_attachment: Optional PDF als Bytes
        attachment_filename: Dateiname für Anhang

    Returns:
        Dict mit Sendestatus und Versuchszaehler
    """
    attempt = self.request.retries + 1
    logger.info(
        "dunning_email_attempt",
        task_id=self.request.id,
        notification_id=notification_id,
        attempt=attempt,
        max_retries=self.max_retries,
    )

    async def do_send():
        from app.services.notification_service import EmailNotifier
        from app.db.session import get_async_session_context
        from app.db.models import Notification, NotificationStatus

        notifier = EmailNotifier()

        if not notifier.is_configured:
            logger.error(
                "dunning_email_not_configured",
                notification_id=notification_id,
            )
            return {
                "success": False,
                "error": "E-Mail-Server nicht konfiguriert",
                "attempt": attempt,
            }

        try:
            # Sende E-Mail mit oder ohne Anhang
            if pdf_attachment and attachment_filename:
                success = await notifier.send_with_attachment(
                    to_email=recipient_email,
                    subject=subject,
                    body=body,
                    attachment=pdf_attachment,
                    attachment_filename=attachment_filename,
                )
            else:
                success = await notifier.send(
                    to_email=recipient_email,
                    subject=subject,
                    body=body,
                )

            # Aktualisiere Notification-Status in DB
            async with get_async_session_context() as db:
                from uuid import UUID
                from sqlalchemy import update

                new_status = NotificationStatus.SENT if success else NotificationStatus.FAILED

                await db.execute(
                    update(Notification)
                    .where(Notification.id == UUID(notification_id))
                    .values(
                        status=new_status,
                        retry_count=attempt,
                        last_attempt_at=datetime.now(timezone.utc),
                        error_message=None if success else "Zustellung fehlgeschlagen",
                    )
                )
                await db.commit()

            if success:
                logger.info(
                    "dunning_email_sent",
                    notification_id=notification_id,
                    attempt=attempt,
                )
                return {
                    "success": True,
                    "attempt": attempt,
                    "recipient": recipient_email,
                }
            else:
                raise Exception("E-Mail-Zustellung fehlgeschlagen")

        except Exception as e:
            logger.warning(
                "dunning_email_failed",
                notification_id=notification_id,
                attempt=attempt,
                **safe_error_log(e)
            )
            raise

    try:
        return run_async(do_send())

    except Exception as e:
        # Letzter Versuch fehlgeschlagen?
        if attempt >= self.max_retries + 1:
            logger.error(
                "dunning_email_final_failure",
                notification_id=notification_id,
                total_attempts=attempt,
                **safe_error_log(e),
            )
            # Markiere als endgültig fehlgeschlagen
            async def mark_failed():
                async with get_async_session_context() as db:
                    from uuid import UUID
                    from sqlalchemy import update
                    from app.db.models import Notification, NotificationStatus

                    await db.execute(
                        update(Notification)
                        .where(Notification.id == UUID(notification_id))
                        .values(
                            status=NotificationStatus.FAILED,
                            retry_count=attempt,
                            error_message=safe_error_detail(e, "Notification-Retry"),
                        )
                    )
                    await db.commit()

            run_async(mark_failed())

            return {
                "success": False,
                "error": safe_error_detail(e, "Vorgang"),
                "attempt": attempt,
                "final_failure": True,
            }

        # Retry mit exponential backoff
        raise self.retry(exc=e)


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.notification_tasks.retry_failed_dunning_emails",
    max_retries=1,
)
def retry_failed_dunning_emails(self) -> Dict[str, Any]:
    """
    Retry-Task für fehlgeschlagene Dunning-E-Mails.

    Sucht Notifications mit Status FAILED und retry_count < max_retries,
    die älter als 1 Stunde sind, und startet neue Zustellversuche.

    Wird stündlich ausgeführt (siehe Beat Schedule).

    Returns:
        Dict mit Anzahl der gestarteten Retry-Tasks
    """
    logger.info(
        "retry_failed_dunning_emails_started",
        task_id=self.request.id,
    )

    async def do_retry():
        from app.db.session import get_async_session_context
        from app.db.models import Notification, NotificationStatus
        from uuid import UUID

        stats = {
            "checked": 0,
            "retried": 0,
            "skipped_max_retries": 0,
            "errors": 0,
        }

        async with get_async_session_context() as db:
            # Finde fehlgeschlagene Dunning-Notifications
            one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
            max_retry_attempts = 5

            result = await db.execute(
                select(Notification).where(
                    and_(
                        Notification.notification_type.in_([
                            "dunning_notification",
                            "payment_reminder",
                            "dunning_letter",
                        ]),
                        Notification.status == NotificationStatus.FAILED,
                        Notification.retry_count < max_retry_attempts,
                        Notification.last_attempt_at < one_hour_ago,
                    )
                ).limit(50)  # Batch-Größe
            )
            failed_notifications = result.scalars().all()
            stats["checked"] = len(failed_notifications)

            for notif in failed_notifications:
                try:
                    if notif.retry_count >= max_retry_attempts:
                        stats["skipped_max_retries"] += 1
                        continue

                    # Hole zugehoerige Daten
                    recipient_email = notif.metadata.get("recipient_email") if notif.metadata else None
                    if not recipient_email:
                        # Versuche User-Email zu laden
                        if notif.user_id:
                            from app.db.models import User
                            user_result = await db.execute(
                                select(User).where(User.id == notif.user_id)
                            )
                            user = user_result.scalar_one_or_none()
                            if user and user.email:
                                recipient_email = user.email

                    if not recipient_email:
                        stats["errors"] += 1
                        continue

                    # Starte neuen Zustellversuch
                    send_dunning_email_with_retry.delay(
                        notification_id=str(notif.id),
                        recipient_email=recipient_email,
                        subject=notif.title or "Zahlungserinnerung",
                        body=notif.message or "",
                    )

                    stats["retried"] += 1

                except Exception as e:
                    stats["errors"] += 1
                    logger.warning(
                        "retry_dunning_email_error",
                        notification_id=str(notif.id),
                        **safe_error_log(e),
                    )

        return stats

    try:
        result = run_async(do_retry())
        logger.info(
            "retry_failed_dunning_emails_completed",
            task_id=self.request.id,
            **result,
        )
        return result

    except Exception as e:
        logger.error(
            "retry_failed_dunning_emails_failed",
            task_id=self.request.id,
            **safe_error_log(e),
        )
        raise


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.notification_tasks.cleanup_old_notifications",
    max_retries=2,
    default_retry_delay=60,
)
def cleanup_old_notifications(self, days: int = 90) -> Dict[str, Any]:
    """
    Celery Task zum Löschen alter Benachrichtigungen.

    Löscht gelesene Benachrichtigungen älter als X Tage.
    Wird wöchentlich am Sonntag um 04:00 Uhr ausgeführt.

    Args:
        days: Anzahl Tage nach denen gelöscht wird (Default: 90)

    Returns:
        Dict mit Anzahl gelöschter Benachrichtigungen
    """
    logger.info(
        "cleanup_notifications_task_gestartet",
        task_id=self.request.id,
        days=days
    )

    async def run_cleanup():
        async with get_async_session_context() as db:
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)

            # Zaehle zu löschende
            count_result = await db.execute(
                select(func.count(UserNotification.id)).where(
                    and_(
                        UserNotification.is_read == True,
                        UserNotification.created_at < cutoff
                    )
                )
            )
            count = count_result.scalar() or 0

            if count > 0:
                # Lösche in Batches
                from sqlalchemy import delete
                await db.execute(
                    delete(UserNotification).where(
                        and_(
                            UserNotification.is_read == True,
                            UserNotification.created_at < cutoff
                        )
                    )
                )
                await db.commit()

            return {"gelöscht": count, "cutoff_datum": cutoff.isoformat()}

    try:
        results = run_async(run_cleanup())
        logger.info(
            "cleanup_notifications_task_abgeschlossen",
            task_id=self.request.id,
            **results
        )
        return results

    except Exception as e:
        logger.error(
            "cleanup_notifications_task_fehler",
            task_id=self.request.id,
            **safe_error_log(e)
        )
        raise self.retry(exc=e)

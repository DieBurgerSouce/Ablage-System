# -*- coding: utf-8 -*-
"""
Celery Tasks fuer Benachrichtigungen.

Geplante Tasks:
- send_daily_digest: Taegliche E-Mail-Zusammenfassung (08:00 Uhr)
- send_weekly_digest: Woechentliche E-Mail-Zusammenfassung (Montag 08:00)
- cleanup_old_notifications: Alte Benachrichtigungen loeschen (Sonntag 04:00)

Feinpoliert und durchdacht - Zuverlaessige Benachrichtigungen fuer Benutzer.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.workers.celery_app import celery_app, CPUTask
from app.db.session import get_async_session_context
from app.db.models import User, Document, UserNotification

logger = structlog.get_logger(__name__)


def run_async(coro):
    """Hilfsfunktion um async Code in sync Celery Tasks auszufuehren.

    MEMORY FIX: Verwendet asyncio.run() statt new_event_loop() um Memory Leaks
    zu verhindern. asyncio.run() erstellt einen neuen Event-Loop, fuehrt die
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
                # JSONB-Abfrage fuer preferences->notifications->email_digest
                User.preferences["notifications"]["email_digest"].astext == digest_type
            )
        )
    )
    return list(result.scalars().all())


async def get_user_document_stats(
    db: AsyncSession,
    user_id: str,
    since: datetime
) -> Dict[str, Any]:
    """Hole Dokumentstatistiken fuer einen Benutzer."""
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

    return {
        "total": total_docs,
        "successful": successful_ocr,
        "failed": failed_ocr,
        "success_rate": round(successful_ocr / total_docs * 100, 1) if total_docs > 0 else 0
    }


async def get_user_notifications(
    db: AsyncSession,
    user_id: str,
    since: datetime,
    limit: int = 10
) -> List[UserNotification]:
    """Hole Benachrichtigungen fuer einen Benutzer."""
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
    """Formatiere Dokumenten-Sektion fuer E-Mail."""
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
    """Formatiere Benachrichtigungs-Sektion fuer E-Mail."""
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
    Celery Task fuer taegliche E-Mail-Zusammenfassung.

    Sendet eine Zusammenfassung an alle Benutzer mit email_digest='daily'.
    Wird taeglich um 08:00 Uhr ausgefuehrt.

    Returns:
        Dict mit Ergebnissen (gesendet, fehlgeschlagen, uebersprungen)
    """
    logger.info("daily_digest_task_gestartet", task_id=self.request.id)

    async def run_digest():
        async with get_async_session_context() as db:
            users = await get_users_with_digest_preference(db, "daily")

            results = {
                "gesendet": 0,
                "fehlgeschlagen": 0,
                "uebersprungen": 0,
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

                    # Keine Aktivitaet? Ueberspringen
                    if doc_stats["total"] == 0 and len(notifications) == 0:
                        results["uebersprungen"] += 1
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
                        error=str(e)
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
            error=str(e)
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
    Celery Task fuer woechentliche E-Mail-Zusammenfassung.

    Sendet eine Zusammenfassung an alle Benutzer mit email_digest='weekly'.
    Wird jeden Montag um 08:00 Uhr ausgefuehrt.

    Returns:
        Dict mit Ergebnissen (gesendet, fehlgeschlagen, uebersprungen)
    """
    logger.info("weekly_digest_task_gestartet", task_id=self.request.id)

    async def run_digest():
        async with get_async_session_context() as db:
            users = await get_users_with_digest_preference(db, "weekly")

            results = {
                "gesendet": 0,
                "fehlgeschlagen": 0,
                "uebersprungen": 0,
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

                    # Keine Aktivitaet? Ueberspringen
                    if doc_stats["total"] == 0 and len(notifications) == 0:
                        results["uebersprungen"] += 1
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
                        avg_processing_time="< 5 Sekunden",  # TODO: Echte Berechnung
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
                        error=str(e)
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
            error=str(e)
        )
        raise self.retry(exc=e)


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.notification_tasks.cleanup_old_notifications",
    max_retries=2,
    default_retry_delay=60,
)
def cleanup_old_notifications(self, days: int = 90) -> Dict[str, Any]:
    """
    Celery Task zum Loeschen alter Benachrichtigungen.

    Loescht gelesene Benachrichtigungen aelter als X Tage.
    Wird woechentlich am Sonntag um 04:00 Uhr ausgefuehrt.

    Args:
        days: Anzahl Tage nach denen geloescht wird (Default: 90)

    Returns:
        Dict mit Anzahl geloeschter Benachrichtigungen
    """
    logger.info(
        "cleanup_notifications_task_gestartet",
        task_id=self.request.id,
        days=days
    )

    async def run_cleanup():
        async with get_async_session_context() as db:
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)

            # Zaehle zu loeschende
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
                # Loesche in Batches
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

            return {"geloescht": count, "cutoff_datum": cutoff.isoformat()}

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
            error=str(e)
        )
        raise self.retry(exc=e)

"""
GDPR Automatisierungstasks für Ablage-System.

Automatische Tasks für:
- Datenaufbewahrungsfristen (Retention)
- Breach-Benachrichtigungen
- Benutzer-Löschanfragen (Art. 17 DSGVO)
- Compliance-Berichte

Feinpoliert und durchdacht - GDPR-konforme Automatisierung.
"""

from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from uuid import UUID
import hashlib

import structlog
from sqlalchemy import select, delete, update, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.cache import invalidate_user_cache, invalidate_all_caches
from app.workers.celery_app import celery_app, CPUTask

logger = structlog.get_logger(__name__)

# Konstanten
GDPR_DELETION_DEADLINE_DAYS = 30  # Art. 17: 30 Tage für Löschanfragen
BREACH_NOTIFICATION_HOURS = 72  # Art. 33: 72 Stunden für Breach-Meldung
RETENTION_CHECK_BATCH_SIZE = 500


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.gdpr_tasks.process_deletion_requests",
    max_retries=3,
    default_retry_delay=600,  # 10 Minuten
    soft_time_limit=1800,  # 30 Minuten Soft-Limit (GDPR-kritisch)
    time_limit=1860,  # 31 Minuten Hard-Limit
    acks_late=True,
)
def process_deletion_requests(self) -> Dict[str, Any]:
    """
    Verarbeite ausstehende GDPR-Löschanfragen (Art. 17 DSGVO).

    Löscht alle Benutzerdaten für Anfragen, deren Frist abgelaufen ist.
    Sendet Benachrichtigungen an Benutzer nach Abschluss.

    Returns:
        Dict mit Statistiken über verarbeitete Anfragen
    """
    import asyncio
    # asyncio.run() für sauberes Event-Loop Cleanup
    return asyncio.run(_process_deletion_requests_async())


async def _process_deletion_requests_async() -> Dict[str, Any]:
    """Async Implementation der Löschanfrage-Verarbeitung.

    Verarbeitet zwei Quellen von Löschanfragen:
    1. GDPRDeletionRequest-Tabelle (legacy)
    2. User.deletion_scheduled_for (neu - Art. 17 via API)
    """
    from app.db.database import get_db_session
    from app.db.models import User, Document, AuditLog, GDPRDeletionRequest

    logger.info("gdpr_deletion_processing_started")

    stats = {
        "requests_processed": 0,
        "users_deleted": 0,
        "documents_deleted": 0,
        "audit_entries_anonymized": 0,
        "errors": [],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    now = datetime.now(timezone.utc)

    try:
        async with get_db_session() as db:
            # 1. Verarbeite User.deletion_scheduled_for (neue Methode)
            user_query = select(User).where(
                and_(
                    User.deletion_scheduled_for <= now,
                    User.deletion_confirmed == True,
                )
            ).limit(50)

            user_result = await db.execute(user_query)
            users_to_delete = user_result.scalars().all()

            for user in users_to_delete:
                try:
                    user_stats = await _delete_user_data(db, user.id, None)
                    stats["users_deleted"] += 1
                    stats["documents_deleted"] += user_stats.get("documents", 0)
                    stats["audit_entries_anonymized"] += user_stats.get("audit_entries", 0)
                    stats["requests_processed"] += 1

                    logger.info(
                        "gdpr_deletion_completed",
                        user_id=str(user.id)[:8] + "...",
                        source="user_field",
                    )
                except Exception as e:
                    stats["errors"].append({
                        "user_id": str(user.id)[:8] + "...",
                        "error": str(e),
                    })
                    logger.error(
                        "gdpr_deletion_failed",
                        user_id=str(user.id)[:8] + "...",
                        error=str(e),
                    )

            # 2. Verarbeite GDPRDeletionRequest-Tabelle (legacy)
            try:
                request_query = select(GDPRDeletionRequest).where(
                    and_(
                        GDPRDeletionRequest.status == "pending",
                        GDPRDeletionRequest.deletion_deadline <= now,
                    )
                ).limit(50)

                result = await db.execute(request_query)
                requests = result.scalars().all()

                for request in requests:
                    try:
                        user_stats = await _delete_user_data(
                            db,
                            request.user_id,
                            request.id,
                        )
                        stats["users_deleted"] += 1
                        stats["documents_deleted"] += user_stats.get("documents", 0)
                        stats["audit_entries_anonymized"] += user_stats.get("audit_entries", 0)

                        request.status = "completed"
                        request.completed_at = now
                        stats["requests_processed"] += 1

                        logger.info(
                            "gdpr_deletion_completed",
                            request_id=str(request.id),
                            user_id=str(request.user_id)[:8] + "...",
                            source="request_table",
                        )

                    except Exception as e:
                        stats["errors"].append({
                            "request_id": str(request.id),
                            "error": str(e),
                        })
                        logger.error(
                            "gdpr_deletion_failed",
                            request_id=str(request.id),
                            error=str(e),
                        )
            except Exception as e:
                # GDPRDeletionRequest-Tabelle existiert möglicherweise nicht
                logger.debug(
                    "gdpr_deletion_request_table_missing",
                    error_type=type(e).__name__,
                )

            await db.commit()

    except Exception as e:
        logger.error("gdpr_deletion_processing_error", error=str(e))
        stats["errors"].append({"type": "general", "error": str(e)})

    logger.info(
        "gdpr_deletion_processing_completed",
        requests_processed=stats["requests_processed"],
        errors=len(stats["errors"]),
    )

    return stats


async def _delete_user_data(
    db: AsyncSession,
    user_id: UUID,
    request_id: UUID,
) -> Dict[str, int]:
    """
    Lösche alle Benutzerdaten (GDPR Art. 17).

    Args:
        db: Datenbank-Session
        user_id: Benutzer-ID
        request_id: Löschanfrage-ID

    Returns:
        Dict mit Anzahl gelöschter Elemente
    """
    from app.db.models import User, Document, AuditLog
    from app.services.storage_service import get_storage_service

    stats = {"documents": 0, "audit_entries": 0}

    # 1. Lösche Dokumente aus Storage
    storage = get_storage_service()
    doc_query = select(Document).where(Document.owner_id == user_id)
    result = await db.execute(doc_query)
    documents = result.scalars().all()

    for doc in documents:
        try:
            if doc.file_path:
                await storage.delete_document(str(doc.id))
            stats["documents"] += 1
        except Exception as e:
            logger.warning(
                "gdpr_storage_delete_failed",
                document_id=str(doc.id),
                error=str(e),
            )

    # 2. Lösche Dokumente aus DB
    await db.execute(delete(Document).where(Document.owner_id == user_id))

    # 3. Anonymisiere Audit-Logs (nicht löschen für Compliance)
    anonymized_user = f"[GDPR_DELETED:{hashlib.sha256(str(user_id).encode()).hexdigest()[:16]}]"
    audit_update = update(AuditLog).where(
        AuditLog.user_id == user_id
    ).values(
        user_id=None,
        ip_address="[ANONYMIZED]",
        audit_metadata=func.jsonb_set(
            func.coalesce(AuditLog.audit_metadata, func.cast("{}", func.json())),
            '{gdpr_anonymized}',
            'true'
        ),
    )
    result = await db.execute(audit_update)
    stats["audit_entries"] = result.rowcount

    # 4. Lösche Benutzer
    await db.execute(delete(User).where(User.id == user_id))

    # 5. Cache Invalidation: Alle Caches für gelöschten Benutzer invalidieren
    try:
        cache_result = await invalidate_user_cache(str(user_id))
        logger.info(
            "gdpr_user_cache_invalidated",
            user_id=str(user_id),
            invalidated_keys=cache_result
        )
    except Exception as cache_error:
        # Cache-Invalidation sollte GDPR-Löschung nicht blockieren
        logger.warning(
            "gdpr_cache_invalidation_failed",
            user_id=str(user_id),
            error=str(cache_error)
        )

    return stats


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.gdpr_tasks.check_retention_compliance",
    max_retries=2,
    soft_time_limit=1200,  # 20 Minuten Soft-Limit
    time_limit=1260,  # 21 Minuten Hard-Limit
    acks_late=True,
)
def check_retention_compliance(self, dry_run: bool = False) -> Dict[str, Any]:
    """
    Prüfe und erzwinge Datenaufbewahrungsfristen.

    Löscht automatisch Daten, die ihre Aufbewahrungsfrist überschritten haben.
    Basiert auf Datenkategorien und gesetzlichen Anforderungen.

    Args:
        dry_run: Nur prüfen, nicht löschen

    Returns:
        Dict mit Compliance-Status
    """
    import asyncio
    # asyncio.run() für sauberes Event-Loop Cleanup
    return asyncio.run(_check_retention_compliance_async(dry_run))


async def _check_retention_compliance_async(dry_run: bool) -> Dict[str, Any]:
    """Async Implementation der Retention-Prüfung."""
    from app.db.database import get_db_session
    from app.db.models import Document
    from app.core.gdpr import DataCategory

    # Aufbewahrungsfristen nach Kategorie (in Tagen)
    RETENTION_PERIODS = {
        "personal_identifiable": 365,  # 1 Jahr
        "special_category": 180,  # 6 Monate
        "financial": 3650,  # 10 Jahre (HGB)
        "contact": 365,  # 1 Jahr
        "document_content": 2555,  # 7 Jahre (HGB)
        "metadata": 90,  # 3 Monate
        "anonymous": None,  # Unbegrenzt
    }

    logger.info("retention_compliance_check_started", dry_run=dry_run)

    stats = {
        "documents_checked": 0,
        "documents_expired": 0,
        "documents_deleted": 0,
        "by_category": {},
        "dry_run": dry_run,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    now = datetime.now(timezone.utc)

    async with get_db_session() as db:
        # Prüfe jede Kategorie
        for category, retention_days in RETENTION_PERIODS.items():
            if retention_days is None:
                continue  # Unbegrenzte Aufbewahrung

            cutoff_date = now - timedelta(days=retention_days)

            # Finde abgelaufene Dokumente dieser Kategorie
            query = select(Document).where(
                and_(
                    Document.data_category == category,
                    Document.created_at < cutoff_date,
                    Document.deleted_at.is_(None),  # Nicht bereits gelöscht
                )
            ).limit(RETENTION_CHECK_BATCH_SIZE)

            result = await db.execute(query)
            expired_docs = result.scalars().all()

            stats["documents_checked"] += len(expired_docs)
            category_count = len(expired_docs)
            stats["by_category"][category] = category_count
            stats["documents_expired"] += category_count

            if not dry_run and expired_docs:
                # Soft-Delete (GDPR-konform, 30 Tage Aufbewahrung vor permanenter Löschung)
                doc_ids = [doc.id for doc in expired_docs]
                await db.execute(
                    update(Document)
                    .where(Document.id.in_(doc_ids))
                    .values(
                        deleted_at=now,
                        deletion_reason="retention_expired",
                    )
                )
                stats["documents_deleted"] += len(doc_ids)

        await db.commit()

    logger.info(
        "retention_compliance_check_completed",
        documents_expired=stats["documents_expired"],
        documents_deleted=stats["documents_deleted"],
    )

    return stats


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.gdpr_tasks.send_breach_notification",
    max_retries=5,
    default_retry_delay=300,
    soft_time_limit=600,  # 10 Minuten Soft-Limit
    time_limit=660,  # 11 Minuten Hard-Limit
    acks_late=True,
)
def send_breach_notification(
    self,
    breach_id: str,
    breach_type: str,
    affected_records: int,
    description: str,
    notify_authority: bool = True,
    notify_users: bool = False,
) -> Dict[str, Any]:
    """
    Sende Breach-Benachrichtigung (Art. 33/34 DSGVO).

    Art. 33: Meldung an Aufsichtsbehörde binnen 72 Stunden
    Art. 34: Meldung an betroffene Personen bei hohem Risiko

    Args:
        breach_id: Eindeutige Breach-ID
        breach_type: Art des Vorfalls
        affected_records: Anzahl betroffener Datensätze
        description: Beschreibung des Vorfalls
        notify_authority: An Behörde melden
        notify_users: An betroffene Benutzer melden

    Returns:
        Dict mit Benachrichtigungsstatus
    """
    import asyncio
    # asyncio.run() für sauberes Event-Loop Cleanup
    return asyncio.run(
        _send_breach_notification_async(
            breach_id,
            breach_type,
            affected_records,
            description,
            notify_authority,
            notify_users,
        )
    )


async def _send_breach_notification_async(
    breach_id: str,
    breach_type: str,
    affected_records: int,
    description: str,
    notify_authority: bool,
    notify_users: bool,
) -> Dict[str, Any]:
    """Async Implementation der Breach-Benachrichtigung."""
    from app.services.notification_service import get_notification_service

    logger.critical(
        "breach_notification_initiated",
        breach_id=breach_id,
        breach_type=breach_type,
        affected_records=affected_records,
    )

    stats = {
        "breach_id": breach_id,
        "authority_notified": False,
        "users_notified": 0,
        "admin_notified": False,
        "errors": [],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "deadline": (datetime.now(timezone.utc) + timedelta(hours=72)).isoformat(),
    }

    notification_service = get_notification_service()

    # 1. Immer Admin benachrichtigen
    try:
        await notification_service.send_admin_alert(
            subject="[KRITISCH] Datenschutzvorfall erkannt",
            message=f"""
Datenschutzvorfall erkannt!

Breach-ID: {breach_id}
Art: {breach_type}
Betroffene Datensätze: {affected_records}
Beschreibung: {description}

Frist für Behördenmeldung: 72 Stunden
Deadline: {stats['deadline']}

Sofortmaßnahmen erforderlich!
""",
            priority="critical",
        )
        stats["admin_notified"] = True
    except Exception as e:
        stats["errors"].append({"type": "admin_notification", "error": str(e)})
        logger.error("breach_admin_notification_failed", error=str(e))

    # 2. Behördenmeldung (Art. 33)
    if notify_authority and affected_records > 0:
        try:
            # Erstelle Behördenmeldung
            authority_report = {
                "breach_id": breach_id,
                "organization": settings.APP_NAME,
                "contact_email": settings.SMTP_FROM_EMAIL,
                "breach_type": breach_type,
                "affected_records": affected_records,
                "description": description,
                "detection_time": datetime.now(timezone.utc).isoformat(),
                "measures_taken": "Untersuchung eingeleitet, betroffene Systeme gesichert",
            }

            # Log für Audit
            logger.critical(
                "breach_authority_report_generated",
                breach_id=breach_id,
                report=authority_report,
            )

            # Sende E-Mail an DPO/Admin für manuelle Weiterleitung
            await notification_service.send_admin_alert(
                subject="[DSGVO Art. 33] Behördenmeldung erforderlich",
                message=f"""
BEHÖRDENMELDUNG ERFORDERLICH

Bitte leiten Sie folgenden Bericht an die zuständige Aufsichtsbehörde weiter:

{_format_authority_report(authority_report)}

Frist: 72 Stunden ab Erkennung
""",
                priority="critical",
            )
            stats["authority_notified"] = True

        except Exception as e:
            stats["errors"].append({"type": "authority_notification", "error": str(e)})
            logger.error("breach_authority_notification_failed", error=str(e))

    # 3. Benutzerbenachrichtigung (Art. 34) bei hohem Risiko
    if notify_users and affected_records > 0:
        try:
            from app.db.database import get_db_session
            from app.db.models import User

            async with get_db_session() as db:
                # Finde betroffene Benutzer (vereinfacht - alle aktiven Benutzer)
                query = select(User).where(User.is_active == True).limit(1000)
                result = await db.execute(query)
                users = result.scalars().all()

                for user in users:
                    try:
                        await notification_service.send_email(
                            to_email=user.email,
                            subject="Wichtige Datenschutzbenachrichtigung",
                            body=f"""
Sehr geehrte/r {user.full_name or user.username},

wir informieren Sie über einen Datenschutzvorfall in unserem System.

Art des Vorfalls: {breach_type}
Beschreibung: {description}

Wir haben sofortige Maßnahmen ergriffen, um Ihre Daten zu schützen.

Falls Sie Fragen haben, kontaktieren Sie uns bitte unter {settings.SMTP_FROM_EMAIL}.

Mit freundlichen Grüßen,
{settings.APP_NAME}
""",
                        )
                        stats["users_notified"] += 1
                    except Exception as e:
                        logger.warning(
                            "breach_user_notification_failed",
                            user_id=str(user.id),
                            error=str(e),
                        )

        except Exception as e:
            stats["errors"].append({"type": "user_notification", "error": str(e)})
            logger.error("breach_user_notification_batch_failed", error=str(e))

    # 4. Speichere Breach-Eintrag in DB für Audit
    try:
        from app.db.database import get_db_session
        from app.db.models import GDPRBreachLog

        async with get_db_session() as db:
            breach_log = GDPRBreachLog(
                breach_id=breach_id,
                breach_type=breach_type,
                affected_records=affected_records,
                description=description,
                authority_notified=stats["authority_notified"],
                users_notified=stats["users_notified"],
                notification_deadline=datetime.now(timezone.utc) + timedelta(hours=72),
            )
            db.add(breach_log)
            await db.commit()

    except Exception as e:
        stats["errors"].append({"type": "breach_log", "error": str(e)})
        logger.error("breach_log_save_failed", error=str(e))

    logger.info(
        "breach_notification_completed",
        breach_id=breach_id,
        authority_notified=stats["authority_notified"],
        users_notified=stats["users_notified"],
    )

    return stats


def _format_authority_report(report: Dict[str, Any]) -> str:
    """Formatiere Behördenbericht."""
    return f"""
Meldung gemäß Art. 33 DSGVO

1. Organisation: {report['organization']}
2. Kontakt: {report['contact_email']}
3. Breach-ID: {report['breach_id']}
4. Art des Vorfalls: {report['breach_type']}
5. Betroffene Datensätze: {report['affected_records']}
6. Beschreibung: {report['description']}
7. Erkennungszeitpunkt: {report['detection_time']}
8. Getroffene Maßnahmen: {report['measures_taken']}
"""


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.gdpr_tasks.generate_compliance_report",
    soft_time_limit=300,  # 5 Minuten Soft-Limit
    time_limit=360,  # 6 Minuten Hard-Limit
    acks_late=True,
)
def generate_compliance_report(self) -> Dict[str, Any]:
    """
    Generiere GDPR-Compliance-Bericht.

    Übersicht über:
    - Aktive Löschanfragen
    - Retention-Status
    - Breach-Historie
    - Verarbeitungsaktivitäten

    Returns:
        Dict mit Compliance-Übersicht
    """
    import asyncio
    # asyncio.run() für sauberes Event-Loop Cleanup
    return asyncio.run(_generate_compliance_report_async())


async def _generate_compliance_report_async() -> Dict[str, Any]:
    """Async Implementation des Compliance-Berichts."""
    from app.db.database import get_db_session
    from app.db.models import User, Document, GDPRDeletionRequest, GDPRBreachLog
    from app.core.gdpr import get_gdpr_manager

    logger.info("compliance_report_generation_started")

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "retention": {},
        "deletion_requests": {},
        "breaches": {},
        "users": {},
        "documents": {},
    }

    async with get_db_session() as db:
        # Benutzerstatistiken
        user_count = await db.execute(select(func.count(User.id)))
        active_users = await db.execute(
            select(func.count(User.id)).where(User.is_active == True)
        )
        report["users"] = {
            "total": user_count.scalar() or 0,
            "active": active_users.scalar() or 0,
        }

        # Dokumentstatistiken
        doc_count = await db.execute(select(func.count(Document.id)))
        deleted_docs = await db.execute(
            select(func.count(Document.id)).where(Document.deleted_at.isnot(None))
        )
        report["documents"] = {
            "total": doc_count.scalar() or 0,
            "soft_deleted": deleted_docs.scalar() or 0,
        }

        # Löschanfragen
        try:
            pending_requests = await db.execute(
                select(func.count(GDPRDeletionRequest.id)).where(
                    GDPRDeletionRequest.status == "pending"
                )
            )
            completed_requests = await db.execute(
                select(func.count(GDPRDeletionRequest.id)).where(
                    GDPRDeletionRequest.status == "completed"
                )
            )
            report["deletion_requests"] = {
                "pending": pending_requests.scalar() or 0,
                "completed": completed_requests.scalar() or 0,
            }
        except Exception as e:
            logger.debug(
                "gdpr_deletion_requests_table_missing",
                error_type=type(e).__name__,
            )
            report["deletion_requests"] = {"note": "Table not yet created"}

        # Breach-Historie
        try:
            breach_count = await db.execute(select(func.count(GDPRBreachLog.id)))
            report["breaches"] = {
                "total": breach_count.scalar() or 0,
            }
        except Exception as e:
            logger.debug(
                "gdpr_breach_log_table_missing",
                error_type=type(e).__name__,
            )
            report["breaches"] = {"note": "Table not yet created"}

    # GDPR Manager Status
    gdpr_manager = get_gdpr_manager()
    report["retention"] = gdpr_manager.check_retention_compliance()

    logger.info("compliance_report_generated")

    return report

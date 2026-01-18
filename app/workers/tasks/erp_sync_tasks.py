"""
ERP Sync Celery Tasks.

Enterprise-Level ERP-Synchronisation:
- Periodische Delta-Syncs
- Manuelle Full-Syncs
- Konflikt-Benachrichtigungen
- Sync-Status-Tracking

Feinpoliert und durchdacht - Zuverlaessige ERP-Sync-Automatisierung.
"""

import structlog
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from celery import shared_task
from sqlalchemy import select, and_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.workers.celery_app import celery_app
from app.db.session import get_async_session_context
from app.db.models import (
    ERPConnection,
    ERPSyncHistory,
    ERPConflict,
    ERPEntityMapping,
    ERPSyncStatus,
    ERPConflictStatus,
)
from app.services.erp.base_connector import (
    ERPConnectionConfig,
    ERPSyncDirection,
    ERPSyncResult,
    ERPEntity,
)
from app.services.erp.odoo_connector import OdooConnector
from app.services.erp.sync_engine import SyncEngine, SyncType, SyncStrategy, create_sync_engine

logger = structlog.get_logger(__name__)


# =============================================================================
# Helper Functions
# =============================================================================


async def get_connection_config(db: AsyncSession, connection_id: UUID) -> Optional[ERPConnectionConfig]:
    """Laedt ERP-Verbindungskonfiguration aus der Datenbank."""
    result = await db.execute(
        select(ERPConnection).where(ERPConnection.id == connection_id)
    )
    connection = result.scalar_one_or_none()

    if not connection:
        return None

    # Decrypt API key mit AES-256-GCM (Connection-ID als AAD)
    api_key: Optional[str] = None
    if connection.encrypted_api_key:
        try:
            from app.core.encryption import decrypt_api_key, DecryptionError
            api_key = decrypt_api_key(
                connection.encrypted_api_key,
                str(connection.id)
            )
        except DecryptionError as e:
            logger.warning(
                "erp_api_key_decryption_failed",
                connection_id=str(connection.id),
                error=str(e)
            )
            # Bei Entschluesselungsfehler: Key ist nicht verfuegbar
            api_key = None
        except Exception as e:
            # Fallback: Wenn Key nicht verschluesselt ist (Legacy-Daten)
            logger.debug(
                "erp_api_key_plaintext_fallback",
                connection_id=str(connection.id)
            )
            api_key = connection.encrypted_api_key

    return ERPConnectionConfig(
        id=connection.id,
        company_id=connection.company_id,
        erp_type=connection.erp_type,
        name=connection.name,
        url=connection.url,
        database=connection.database_name or "",
        username=connection.username,
        api_key=api_key,
        sync_direction=ERPSyncDirection(connection.sync_direction),
        sync_interval_minutes=connection.sync_interval_minutes,
        enabled_entities=[ERPEntity(e) for e in connection.enabled_entities],
        max_requests_per_minute=connection.max_requests_per_minute,
        batch_size=connection.batch_size,
        max_retries=connection.max_retries,
        retry_delay_seconds=connection.retry_delay_seconds,
        connect_timeout_seconds=connection.connect_timeout_seconds,
        read_timeout_seconds=connection.read_timeout_seconds,
        last_sync_at=connection.last_sync_at,
        is_active=connection.is_active,
    )


async def create_connector(config: ERPConnectionConfig) -> OdooConnector:
    """Erstellt ERP-Connector basierend auf Konfiguration."""
    if config.erp_type == "odoo":
        return OdooConnector(config)
    else:
        raise ValueError(f"Unbekannter ERP-Typ: {config.erp_type}")


async def save_sync_history(
    db: AsyncSession,
    connection_id: UUID,
    result: ERPSyncResult,
    sync_type: str,
    triggered_by: Optional[UUID] = None,
    task_id: Optional[str] = None,
) -> ERPSyncHistory:
    """Speichert Sync-Historie in der Datenbank."""
    history = ERPSyncHistory(
        connection_id=connection_id,
        sync_type=sync_type,
        entity=result.entity.value,
        direction=result.direction.value,
        status=ERPSyncStatus.SUCCESS.value if result.success else ERPSyncStatus.FAILED.value,
        records_synced=result.records_synced,
        records_created=result.records_created,
        records_updated=result.records_updated,
        records_deleted=result.records_deleted,
        records_failed=result.records_failed,
        conflicts_detected=result.conflicts_detected,
        conflicts_resolved=result.conflicts_resolved,
        started_at=result.started_at,
        completed_at=result.completed_at,
        duration_seconds=result.duration_seconds,
        error_message=result.error_message,
        triggered_by=triggered_by,
        task_id=task_id,
    )

    db.add(history)
    await db.commit()
    await db.refresh(history)

    return history


async def update_connection_sync_status(
    db: AsyncSession,
    connection_id: UUID,
    success: bool,
    error_message: Optional[str] = None,
) -> None:
    """Aktualisiert Sync-Status der Verbindung."""
    now = datetime.now(timezone.utc)

    update_data = {
        "last_sync_at": now,
        "next_scheduled_sync": now + timedelta(minutes=15),  # Default interval
        "updated_at": now,
    }

    if success:
        update_data["connection_status"] = "connected"
        update_data["last_successful_connection"] = now
        update_data["last_error"] = None
    else:
        update_data["connection_status"] = "error"
        update_data["last_error"] = error_message

    await db.execute(
        update(ERPConnection)
        .where(ERPConnection.id == connection_id)
        .values(**update_data)
    )
    await db.commit()


# =============================================================================
# Sync Tasks
# =============================================================================


@celery_app.task(
    name="erp.sync_connection",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(Exception,),
    retry_backoff=True,
)
def sync_connection(
    self,
    connection_id: str,
    sync_type: str = "delta",
    triggered_by: Optional[str] = None,
) -> Dict[str, Any]:
    """Synchronisiert alle Entities einer ERP-Verbindung.

    Args:
        connection_id: UUID der ERP-Verbindung
        sync_type: "delta" oder "full"
        triggered_by: User-UUID (bei manueller Ausloesung)

    Returns:
        Sync-Ergebnis mit Statistiken
    """
    import asyncio

    async def _sync() -> Dict[str, Any]:
        async with get_async_session_context() as db:
            # Load configuration
            config = await get_connection_config(db, UUID(connection_id))
            if not config:
                logger.error("erp_connection_not_found", connection_id=connection_id)
                return {"success": False, "error": "Verbindung nicht gefunden"}

            if not config.is_active:
                logger.warning("erp_connection_inactive", connection_id=connection_id)
                return {"success": False, "error": "Verbindung ist deaktiviert"}

            # Create connector
            try:
                connector = await create_connector(config)
            except ValueError as e:
                logger.error("erp_connector_creation_failed", error=str(e))
                return {"success": False, "error": str(e)}

            # Connect
            if not await connector.connect():
                error_msg = connector.last_error or "Verbindung fehlgeschlagen"
                await update_connection_sync_status(db, UUID(connection_id), False, error_msg)
                return {"success": False, "error": error_msg}

            # Create sync engine
            engine = create_sync_engine(
                connector,
                strategy=SyncStrategy.LAST_WRITE_WINS,
            )

            results: List[Dict[str, Any]] = []
            total_success = True

            # Sync each enabled entity
            for entity in config.enabled_entities:
                try:
                    result = await engine.sync_entity(
                        entity=entity,
                        direction=config.sync_direction,
                        sync_type=SyncType(sync_type),
                    )

                    # Save history
                    await save_sync_history(
                        db=db,
                        connection_id=UUID(connection_id),
                        result=result,
                        sync_type=sync_type,
                        triggered_by=UUID(triggered_by) if triggered_by else None,
                        task_id=self.request.id,
                    )

                    results.append({
                        "entity": entity.value,
                        "success": result.success,
                        "records_synced": result.records_synced,
                        "conflicts": result.conflicts_detected,
                        "error": result.error_message,
                    })

                    if not result.success:
                        total_success = False

                except Exception as e:
                    logger.exception(
                        "erp_entity_sync_failed",
                        entity=entity.value,
                        error=str(e),
                    )
                    results.append({
                        "entity": entity.value,
                        "success": False,
                        "error": str(e),
                    })
                    total_success = False

            # Disconnect
            await connector.disconnect()

            # Update connection status
            await update_connection_sync_status(db, UUID(connection_id), total_success)

            logger.info(
                "erp_sync_completed",
                connection_id=connection_id,
                sync_type=sync_type,
                success=total_success,
                entities_synced=len(results),
            )

            return {
                "success": total_success,
                "connection_id": connection_id,
                "sync_type": sync_type,
                "results": results,
            }

    return asyncio.get_event_loop().run_until_complete(_sync())


@celery_app.task(
    name="erp.sync_entity",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def sync_entity(
    self,
    connection_id: str,
    entity: str,
    sync_type: str = "delta",
) -> Dict[str, Any]:
    """Synchronisiert eine einzelne Entity.

    Args:
        connection_id: UUID der ERP-Verbindung
        entity: Entity-Typ (customer, supplier, invoice)
        sync_type: "delta" oder "full"

    Returns:
        Sync-Ergebnis
    """
    import asyncio

    async def _sync() -> Dict[str, Any]:
        async with get_async_session_context() as db:
            config = await get_connection_config(db, UUID(connection_id))
            if not config:
                return {"success": False, "error": "Verbindung nicht gefunden"}

            connector = await create_connector(config)
            if not await connector.connect():
                return {"success": False, "error": connector.last_error}

            engine = create_sync_engine(connector)

            try:
                result = await engine.sync_entity(
                    entity=ERPEntity(entity),
                    direction=config.sync_direction,
                    sync_type=SyncType(sync_type),
                )

                await save_sync_history(
                    db=db,
                    connection_id=UUID(connection_id),
                    result=result,
                    sync_type=sync_type,
                    task_id=self.request.id,
                )

                return {
                    "success": result.success,
                    "entity": entity,
                    "records_synced": result.records_synced,
                    "records_created": result.records_created,
                    "records_updated": result.records_updated,
                    "conflicts": result.conflicts_detected,
                    "error": result.error_message,
                }

            finally:
                await connector.disconnect()

    return asyncio.get_event_loop().run_until_complete(_sync())


@celery_app.task(name="erp.scheduled_sync_all")
def scheduled_sync_all() -> Dict[str, Any]:
    """Periodischer Task: Synchronisiert alle faelligen Verbindungen.

    Wird vom Celery Beat Schedule aufgerufen.
    """
    import asyncio

    async def _sync_all() -> Dict[str, Any]:
        async with get_async_session_context() as db:
            now = datetime.now(timezone.utc)

            # Find connections due for sync
            result = await db.execute(
                select(ERPConnection).where(
                    and_(
                        ERPConnection.is_active == True,
                        or_(
                            ERPConnection.next_scheduled_sync <= now,
                            ERPConnection.next_scheduled_sync == None,
                        ),
                    )
                )
            )
            connections = result.scalars().all()

            tasks_queued = 0
            for conn in connections:
                # Queue sync task
                sync_connection.delay(
                    connection_id=str(conn.id),
                    sync_type="delta",
                )
                tasks_queued += 1

                logger.info(
                    "erp_sync_queued",
                    connection_id=str(conn.id),
                    connection_name=conn.name,
                )

            return {
                "success": True,
                "connections_queued": tasks_queued,
            }

    return asyncio.get_event_loop().run_until_complete(_sync_all())


@celery_app.task(name="erp.test_connection")
def test_connection(connection_id: str) -> Dict[str, Any]:
    """Testet eine ERP-Verbindung.

    Args:
        connection_id: UUID der Verbindung

    Returns:
        Test-Ergebnis mit Version etc.
    """
    import asyncio

    async def _test() -> Dict[str, Any]:
        async with get_async_session_context() as db:
            config = await get_connection_config(db, UUID(connection_id))
            if not config:
                return {"success": False, "error": "Verbindung nicht gefunden"}

            try:
                connector = await create_connector(config)
                connected = await connector.test_connection()

                if connected:
                    version = await connector.get_version()
                    await connector.disconnect()

                    # Update status
                    await update_connection_sync_status(db, UUID(connection_id), True)

                    return {
                        "success": True,
                        "connected": True,
                        "version": version,
                        "erp_type": config.erp_type,
                    }
                else:
                    error = connector.last_error or "Verbindungstest fehlgeschlagen"
                    await update_connection_sync_status(db, UUID(connection_id), False, error)

                    return {
                        "success": False,
                        "connected": False,
                        "error": error,
                    }

            except Exception as e:
                logger.exception("erp_connection_test_failed", error=str(e))
                return {"success": False, "error": str(e)}

    return asyncio.get_event_loop().run_until_complete(_test())


# =============================================================================
# Conflict Resolution Tasks
# =============================================================================


@celery_app.task(name="erp.notify_conflicts")
def notify_conflicts() -> Dict[str, Any]:
    """Benachrichtigt ueber offene Konflikte.

    Wird periodisch ausgefuehrt um Admins ueber
    ungeloeste Konflikte zu informieren.
    """
    import asyncio

    async def _notify() -> Dict[str, Any]:
        async with get_async_session_context() as db:
            # Count pending conflicts per connection
            result = await db.execute(
                select(ERPConflict).where(
                    ERPConflict.status == ERPConflictStatus.PENDING.value
                )
            )
            pending_conflicts = result.scalars().all()

            if not pending_conflicts:
                return {"success": True, "conflicts_pending": 0}

            # Group by connection
            conflicts_by_connection: Dict[str, int] = {}
            for conflict in pending_conflicts:
                conn_id = str(conflict.connection_id)
                conflicts_by_connection[conn_id] = conflicts_by_connection.get(conn_id, 0) + 1

            logger.warning(
                "erp_conflicts_pending",
                total=len(pending_conflicts),
                by_connection=conflicts_by_connection,
            )

            # Send notifications via NotificationService to all admins
            from app.services.notification_service import (
                NotificationService,
                NotificationType,
                NotificationPriority,
            )
            from app.db.models import User

            # Hole alle Admin-User
            admin_result = await db.execute(
                select(User).where(
                    and_(User.is_superuser == True, User.is_active == True)
                )
            )
            admins = admin_result.scalars().all()

            # Formatiere Konflikte nach Verbindung
            conflicts_list = "\n".join([
                f"- Verbindung {conn_id}: {count} Konflikte"
                for conn_id, count in conflicts_by_connection.items()
            ])

            notification_service = NotificationService()
            notifications_sent = 0

            for admin in admins:
                if admin.email:
                    try:
                        await notification_service.notify(
                            notification_type=NotificationType.ERP_CONFLICT_PENDING,
                            context={
                                "total_conflicts": len(pending_conflicts),
                                "connection_count": len(conflicts_by_connection),
                                "conflicts_by_connection_list": conflicts_list,
                            },
                            user_id=str(admin.id),
                            email=admin.email,
                            priority=NotificationPriority.HIGH,
                        )
                        notifications_sent += 1
                    except Exception as e:
                        logger.warning(
                            "erp_conflict_notification_failed",
                            admin_id=str(admin.id),
                            error=str(e),
                        )

            return {
                "success": True,
                "conflicts_pending": len(pending_conflicts),
                "by_connection": conflicts_by_connection,
                "notifications_sent": notifications_sent,
            }

    return asyncio.get_event_loop().run_until_complete(_notify())


@celery_app.task(name="erp.cleanup_old_history")
def cleanup_old_history(days: int = 90) -> Dict[str, Any]:
    """Bereinigt alte Sync-Historie.

    Args:
        days: Eintraege aelter als X Tage loeschen

    Returns:
        Anzahl geloeschter Eintraege
    """
    import asyncio
    from sqlalchemy import delete

    async def _cleanup() -> Dict[str, Any]:
        async with get_async_session_context() as db:
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)

            result = await db.execute(
                delete(ERPSyncHistory).where(
                    ERPSyncHistory.started_at < cutoff
                )
            )
            await db.commit()

            deleted = result.rowcount

            logger.info(
                "erp_history_cleanup",
                deleted=deleted,
                cutoff_days=days,
            )

            return {
                "success": True,
                "deleted": deleted,
                "cutoff_days": days,
            }

    return asyncio.get_event_loop().run_until_complete(_cleanup())


# =============================================================================
# Celery Beat Schedule (to be added to celery_app.py)
# =============================================================================

ERP_BEAT_SCHEDULE = {
    "erp-scheduled-sync": {
        "task": "erp.scheduled_sync_all",
        "schedule": 900.0,  # Alle 15 Minuten
        "options": {"queue": "erp"},
    },
    "erp-notify-conflicts": {
        "task": "erp.notify_conflicts",
        "schedule": 3600.0,  # Stuendlich
        "options": {"queue": "erp"},
    },
    "erp-cleanup-history": {
        "task": "erp.cleanup_old_history",
        "schedule": 86400.0,  # Taeglich
        "args": (90,),
        "options": {"queue": "erp"},
    },
}

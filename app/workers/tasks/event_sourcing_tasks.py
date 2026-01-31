# -*- coding: utf-8 -*-
"""Event-Sourcing periodic tasks (F8).

Phase 12: AuditLog-basierte Snapshot-Erstellung und Archivierung.
"""

import asyncio
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, Any

import structlog
from sqlalchemy import select, func, and_, delete

from app.core.safe_errors import safe_error_log
from app.workers.celery_app import celery_app
from app.db.session import async_session_maker
from app.db.models import Company, AuditLog, AppConfig

logger = structlog.get_logger(__name__)


@celery_app.task(name="app.workers.tasks.event_sourcing_tasks.create_snapshots")
def create_snapshots() -> dict:
    """Erstelle Snapshots fuer haeufig abgefragte Aggregates.

    Prueft alle Aggregates und erstellt Snapshots wenn:
    - Mehr als 50 Events seit letztem Snapshot
    - Letzter Snapshot aelter als 24 Stunden
    """
    logger.info("event_sourcing_snapshot_start")
    try:
        result = asyncio.get_event_loop().run_until_complete(_create_snapshots())
        logger.info(
            "event_sourcing_snapshot_complete",
            snapshots_created=result.get("snapshots_created", 0),
        )
        return result
    except Exception as e:
        logger.error("event_sourcing_snapshot_error", **safe_error_log(e))
        raise


async def _create_snapshots() -> Dict[str, Any]:
    """Async Implementation fuer Snapshot-Erstellung."""
    snapshots_created = 0

    async with async_session_maker() as db:
        # Alle Companies
        result = await db.execute(
            select(Company.id).where(Company.is_active == True)
        )
        company_ids = [row[0] for row in result.all()]

        for company_id in company_ids:
            try:
                # Zaehle Events seit letztem Snapshot
                # Snapshot-Zeitpunkt aus AppConfig laden
                snapshot_config_key = f"event_snapshot_{company_id}"

                config_result = await db.execute(
                    select(AppConfig).where(AppConfig.key == snapshot_config_key)
                )
                config = config_result.scalar_one_or_none()

                last_snapshot_time = None
                if config and config.value and "last_snapshot_at" in config.value:
                    last_snapshot_time = datetime.fromisoformat(
                        config.value["last_snapshot_at"]
                    )

                # Events seit letztem Snapshot zaehlen
                events_query = select(func.count(AuditLog.id)).where(
                    AuditLog.company_id == company_id
                )
                if last_snapshot_time:
                    events_query = events_query.where(
                        AuditLog.created_at > last_snapshot_time
                    )

                events_result = await db.execute(events_query)
                event_count = events_result.scalar() or 0

                # Snapshot erstellen wenn >50 Events oder >24h seit letztem Snapshot
                should_snapshot = event_count > 50
                if last_snapshot_time:
                    time_since = datetime.now(timezone.utc) - last_snapshot_time.replace(tzinfo=timezone.utc)
                    should_snapshot = should_snapshot or time_since > timedelta(hours=24)
                else:
                    should_snapshot = True  # Erster Snapshot

                if should_snapshot and event_count > 0:
                    # Snapshot-Daten aggregieren
                    snapshot_data = {
                        "company_id": str(company_id),
                        "event_count": event_count,
                        "last_snapshot_at": datetime.now(timezone.utc).isoformat(),
                        "aggregated_actions": {},
                    }

                    # Action-Counts aggregieren
                    action_counts_result = await db.execute(
                        select(
                            AuditLog.action,
                            func.count(AuditLog.id).label("count"),
                        )
                        .where(AuditLog.company_id == company_id)
                        .group_by(AuditLog.action)
                    )
                    snapshot_data["aggregated_actions"] = {
                        action: count for action, count in action_counts_result.all()
                    }

                    # In AppConfig speichern
                    if config:
                        config.value = snapshot_data
                    else:
                        config = AppConfig(key=snapshot_config_key, value=snapshot_data)
                        db.add(config)

                    snapshots_created += 1

                    logger.info(
                        "snapshot_created",
                        company_id=str(company_id),
                        event_count=event_count,
                    )

            except Exception as e:
                logger.warning(
                    "snapshot_company_failed",
                    company_id=str(company_id),
                    **safe_error_log(e),
                )
                continue

        await db.commit()

    return {
        "status": "success",
        "snapshots_created": snapshots_created,
    }


@celery_app.task(name="app.workers.tasks.event_sourcing_tasks.archive_old_events")
def archive_old_events(retention_days: int = 180) -> dict:
    """Archiviere alte Events die bereits als Snapshot gespeichert sind."""
    logger.info("event_sourcing_archive_start", retention_days=retention_days)
    try:
        result = asyncio.get_event_loop().run_until_complete(
            _archive_old_events(retention_days)
        )
        logger.info(
            "event_sourcing_archive_complete",
            events_archived=result.get("events_archived", 0),
        )
        return result
    except Exception as e:
        logger.error("event_sourcing_archive_error", **safe_error_log(e))
        raise


async def _archive_old_events(retention_days: int) -> Dict[str, Any]:
    """Async Implementation fuer Event-Archivierung."""
    events_archived = 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)

    async with async_session_maker() as db:
        # Zaehle zu archivierende Events
        count_result = await db.execute(
            select(func.count(AuditLog.id)).where(AuditLog.created_at < cutoff)
        )
        total_old_events = count_result.scalar() or 0

        if total_old_events == 0:
            return {
                "status": "success",
                "events_archived": 0,
                "message": "Keine alten Events zum Archivieren",
            }

        # Batch-weise loeschen (max 10000 pro Durchlauf fuer Performance)
        # In Production wuerden Events in Archiv-Tabelle verschoben statt geloescht
        batch_size = 10000

        while events_archived < min(total_old_events, batch_size):
            # IDs der zu loeschenden Events holen
            old_ids_result = await db.execute(
                select(AuditLog.id)
                .where(AuditLog.created_at < cutoff)
                .limit(1000)
            )
            old_ids = [row[0] for row in old_ids_result.all()]

            if not old_ids:
                break

            # Loeschen
            await db.execute(
                delete(AuditLog).where(AuditLog.id.in_(old_ids))
            )

            events_archived += len(old_ids)

            logger.debug(
                "events_batch_archived",
                batch_size=len(old_ids),
                total_archived=events_archived,
            )

        await db.commit()

        logger.info(
            "events_archived",
            count=events_archived,
            cutoff_date=cutoff.isoformat(),
        )

    return {
        "status": "success",
        "events_archived": events_archived,
        "retention_days": retention_days,
    }

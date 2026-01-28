"""Snapshot Service - Snapshot-Verwaltung fuer Event-Sourcing Performance."""

import structlog
from dataclasses import dataclass
from typing import Optional, Dict, Any
from uuid import UUID
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc

logger = structlog.get_logger(__name__)


@dataclass
class SnapshotData:
    """Snapshot-Daten eines Aggregats."""

    snapshot_id: UUID
    aggregate_type: str
    aggregate_id: UUID
    sequence_number: int
    state: Dict[str, Any]
    version: int
    created_at: datetime


class SnapshotService:
    """Service fuer Snapshot-Verwaltung.

    Snapshots verbessern die Performance beim Event-Replay,
    indem der Zustand nicht jedes Mal von Grund auf neu berechnet wird.
    """

    # Snapshot nach jeweils N Events
    SNAPSHOT_INTERVAL = 50

    async def create_snapshot(
        self,
        aggregate_type: str,
        aggregate_id: UUID,
        state: Dict[str, Any],
        sequence_number: int,
        company_id: UUID,
        db: AsyncSession = None,
    ) -> SnapshotData:
        """Erstellt einen neuen Snapshot.

        Args:
            aggregate_type: Typ des Aggregats
            aggregate_id: ID des Aggregats
            state: Aktueller Zustand des Aggregats
            sequence_number: Sequenznummer bis zu der der Snapshot gilt
            company_id: Mandanten-ID
            db: Datenbank-Session

        Returns:
            SnapshotData: Der erstellte Snapshot
        """
        from app.db.models import EventSnapshot

        if not db:
            raise ValueError("Datenbank-Session erforderlich")

        # Validierung der Aggregate-Type Whitelist
        allowed_types = {"document", "invoice", "payment", "entity", "alert", "workflow"}
        if aggregate_type not in allowed_types:
            logger.warning(
                "ungueltige_aggregate_type_snapshot",
                aggregate_type=aggregate_type,
                allowed=list(allowed_types)
            )
            raise ValueError(f"Ungueltiger Aggregat-Typ: {aggregate_type}")

        # Letzten Snapshot holen fuer Versionierung
        latest = await self.get_latest_snapshot(
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            company_id=company_id,
            db=db,
        )

        next_version = (latest.version + 1) if latest else 1

        snapshot = EventSnapshot(
            company_id=company_id,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            sequence_number=sequence_number,
            state=state,
            version=next_version,
        )

        db.add(snapshot)
        await db.flush()
        await db.refresh(snapshot)

        logger.info(
            "snapshot_created",
            aggregate_type=aggregate_type,
            sequence_number=sequence_number,
            version=next_version,
        )

        return SnapshotData(
            snapshot_id=snapshot.id,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            sequence_number=sequence_number,
            state=state,
            version=next_version,
            created_at=snapshot.created_at,
        )

    async def get_latest_snapshot(
        self,
        aggregate_type: str,
        aggregate_id: UUID,
        company_id: UUID,
        db: AsyncSession = None,
    ) -> Optional[SnapshotData]:
        """Holt den neuesten Snapshot fuer ein Aggregat.

        Args:
            aggregate_type: Typ des Aggregats
            aggregate_id: ID des Aggregats
            company_id: Mandanten-ID fuer Multi-Tenant Isolation
            db: Datenbank-Session

        Returns:
            Optional[SnapshotData]: Der neueste Snapshot oder None
        """
        from app.db.models import EventSnapshot

        if not db:
            raise ValueError("Datenbank-Session erforderlich")

        # SECURITY FIX: company_id Filter für Multi-Tenant Isolation
        stmt = (
            select(EventSnapshot)
            .where(
                and_(
                    EventSnapshot.aggregate_type == aggregate_type,
                    EventSnapshot.company_id == company_id,
                    EventSnapshot.aggregate_id == aggregate_id,
                )
            )
            .order_by(desc(EventSnapshot.sequence_number))
            .limit(1)
        )

        result = await db.execute(stmt)
        snapshot = result.scalar_one_or_none()

        if not snapshot:
            return None

        return SnapshotData(
            snapshot_id=snapshot.id,
            aggregate_type=snapshot.aggregate_type,
            aggregate_id=snapshot.aggregate_id,
            sequence_number=snapshot.sequence_number,
            state=snapshot.state,
            version=snapshot.version,
            created_at=snapshot.created_at,
        )

    async def should_create_snapshot(
        self,
        aggregate_type: str,
        aggregate_id: UUID,
        current_sequence: int,
        company_id: UUID,
        db: AsyncSession = None,
    ) -> bool:
        """Prueft ob ein Snapshot erstellt werden sollte.

        Args:
            aggregate_type: Typ des Aggregats
            aggregate_id: ID des Aggregats
            current_sequence: Aktuelle Sequenznummer
            company_id: Mandanten-ID fuer Multi-Tenant Isolation
            db: Datenbank-Session

        Returns:
            True wenn Snapshot erstellt werden sollte
        """
        if not db:
            raise ValueError("Datenbank-Session erforderlich")

        latest = await self.get_latest_snapshot(
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            company_id=company_id,
            db=db,
        )

        if not latest:
            # Ersten Snapshot nach SNAPSHOT_INTERVAL Events
            return current_sequence >= self.SNAPSHOT_INTERVAL

        # Snapshot wenn SNAPSHOT_INTERVAL Events seit letztem Snapshot
        return (current_sequence - latest.sequence_number) >= self.SNAPSHOT_INTERVAL

    async def cleanup_old_snapshots(
        self,
        aggregate_type: str,
        aggregate_id: UUID,
        company_id: UUID,
        keep_count: int = 5,
        db: AsyncSession = None,
    ) -> int:
        """Loescht alte Snapshots und behaelt nur die neuesten.

        Args:
            aggregate_type: Typ des Aggregats
            aggregate_id: ID des Aggregats
            company_id: Mandanten-ID fuer Multi-Tenant Isolation
            keep_count: Anzahl zu behaltender Snapshots
            db: Datenbank-Session

        Returns:
            Anzahl geloeschter Snapshots
        """
        from app.db.models import EventSnapshot

        if not db:
            raise ValueError("Datenbank-Session erforderlich")

        # SECURITY FIX: company_id Filter für Multi-Tenant Isolation
        # Snapshots nach Sequenznummer sortiert holen
        stmt = (
            select(EventSnapshot)
            .where(
                and_(
                    EventSnapshot.aggregate_type == aggregate_type,
                    EventSnapshot.aggregate_id == aggregate_id,
                    EventSnapshot.company_id == company_id,
                )
            )
            .order_by(desc(EventSnapshot.sequence_number))
        )

        result = await db.execute(stmt)
        snapshots = result.scalars().all()

        if len(snapshots) <= keep_count:
            return 0

        # Alte Snapshots loeschen
        to_delete = snapshots[keep_count:]
        deleted_count = 0

        for snapshot in to_delete:
            await db.delete(snapshot)
            deleted_count += 1

        await db.flush()

        logger.info(
            "snapshots_cleaned_up",
            aggregate_type=aggregate_type,
            deleted_count=deleted_count,
            kept_count=keep_count,
        )

        return deleted_count

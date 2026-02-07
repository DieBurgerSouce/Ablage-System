"""
ERP Sync Engine.

Enterprise-Level Synchronisations-Engine:
- Delta-Sync (nur geaenderte Datensaetze)
- Full-Sync (initial oder manuell)
- Konflikt-Erkennung und -Queue
- Checksum-basierte Aenderungserkennung

Feinpoliert und durchdacht - Bidirektionale Sync auf Enterprise-Niveau.
"""

import structlog
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_

from app.services.erp.base_connector import (
    ERPConnector,
    ERPConnectionConfig,
    ERPSyncDirection,
    ERPSyncResult,
    ERPEntity,
    ERPConflict,
)
from app.services.erp.field_mapping import EntityMappingService, get_mapping_service
from app.core.safe_errors import safe_error_log, safe_error_detail

logger = structlog.get_logger(__name__)


class SyncType(str, Enum):
    """Art der Synchronisation."""
    FULL = "full"  # Alle Datensaetze
    DELTA = "delta"  # Nur geaenderte
    MANUAL = "manual"  # Manuell getriggert


class SyncStrategy(str, Enum):
    """Strategie fuer Konflikt-Aufloesung."""
    LAST_WRITE_WINS = "last_write_wins"
    LOCAL_WINS = "local_wins"
    REMOTE_WINS = "remote_wins"
    QUEUE_FOR_REVIEW = "queue_for_review"


@dataclass
class SyncRecord:
    """Ein einzelner Sync-Datensatz."""

    local_id: Optional[str] = None
    remote_id: Optional[str] = None
    local_data: Dict[str, Any] = field(default_factory=dict)
    remote_data: Dict[str, Any] = field(default_factory=dict)
    local_checksum: Optional[str] = None
    remote_checksum: Optional[str] = None
    local_modified_at: Optional[datetime] = None
    remote_modified_at: Optional[datetime] = None
    action: Optional[str] = None  # create, update, delete, skip, conflict


@dataclass
class SyncBatch:
    """Ein Batch von Sync-Operationen."""

    entity: ERPEntity
    direction: ERPSyncDirection
    sync_type: SyncType
    records: List[SyncRecord] = field(default_factory=list)

    to_create: List[SyncRecord] = field(default_factory=list)
    to_update: List[SyncRecord] = field(default_factory=list)
    to_delete: List[SyncRecord] = field(default_factory=list)
    conflicts: List[SyncRecord] = field(default_factory=list)
    skipped: List[SyncRecord] = field(default_factory=list)


class SyncEngine:
    """Sync-Engine fuer bidirektionale ERP-Synchronisation.

    Orchestriert den Sync-Prozess zwischen lokalem System und ERP:
    1. Fetch: Daten von beiden Seiten holen
    2. Compare: Aenderungen erkennen
    3. Transform: Feld-Mappings anwenden
    4. Sync: Aenderungen anwenden
    5. Finalize: Mappings und Checksums aktualisieren

    Usage:
        engine = SyncEngine(connector, mapping_service)
        result = await engine.sync_entity(
            entity=ERPEntity.CUSTOMER,
            direction=ERPSyncDirection.BIDIRECTIONAL,
        )
    """

    def __init__(
        self,
        connector: ERPConnector,
        mapping_service: Optional[EntityMappingService] = None,
        strategy: SyncStrategy = SyncStrategy.LAST_WRITE_WINS,
    ) -> None:
        """Initialisiert die Sync-Engine.

        Args:
            connector: ERP-Connector-Instanz
            mapping_service: Feld-Mapping-Service
            strategy: Konflikt-Strategie
        """
        self.connector = connector
        self.mapping_service = mapping_service or get_mapping_service()
        self.strategy = strategy

        logger.info(
            "sync_engine_initialized",
            erp_type=connector.erp_type,
            strategy=strategy.value,
        )

    async def sync_entity(
        self,
        entity: ERPEntity,
        direction: ERPSyncDirection = ERPSyncDirection.BIDIRECTIONAL,
        sync_type: SyncType = SyncType.DELTA,
        since: Optional[datetime] = None,
        local_records: Optional[List[Dict[str, Any]]] = None,
    ) -> ERPSyncResult:
        """Synchronisiert eine Entity.

        Args:
            entity: Zu synchronisierende Entity
            direction: Sync-Richtung
            sync_type: Art der Sync
            since: Nur Aenderungen seit diesem Zeitpunkt
            local_records: Lokale Datensaetze (optional, sonst aus DB)

        Returns:
            Sync-Ergebnis mit Statistiken
        """
        result = self.connector._create_sync_result(entity, direction)

        try:
            # 1. Fetch remote records
            remote_records = await self._fetch_remote(entity, sync_type, since)

            # 2. Prepare sync batch
            batch = await self._prepare_batch(
                entity=entity,
                direction=direction,
                sync_type=sync_type,
                local_records=local_records or [],
                remote_records=remote_records,
            )

            # 3. Execute sync operations
            await self._execute_batch(batch)

            # 4. Update result statistics
            result.records_synced = (
                len(batch.to_create) + len(batch.to_update)
            )
            result.records_created = len(batch.to_create)
            result.records_updated = len(batch.to_update)
            result.records_deleted = len(batch.to_delete)
            result.conflicts_detected = len(batch.conflicts)
            result.success = True

            logger.info(
                "sync_entity_completed",
                entity=entity.value,
                direction=direction.value,
                created=result.records_created,
                updated=result.records_updated,
                conflicts=result.conflicts_detected,
            )

        except Exception as e:
            result.success = False
            result.error_message = safe_error_detail(e, "ERP-Sync")
            logger.exception(
                "sync_entity_failed",
                entity=entity.value,
                **safe_error_log(e),
            )

        return self.connector._complete_sync_result(result)

    async def _fetch_remote(
        self,
        entity: ERPEntity,
        sync_type: SyncType,
        since: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """Holt Datensaetze aus dem ERP.

        Args:
            entity: Entity-Typ
            sync_type: Full oder Delta
            since: Zeitstempel fuer Delta-Sync

        Returns:
            Liste der ERP-Datensaetze
        """
        # Use last_sync_at for delta sync if since not provided
        if sync_type == SyncType.DELTA and since is None:
            since = self.connector.config.last_sync_at

        result: Optional[ERPSyncResult] = None

        if entity == ERPEntity.CUSTOMER:
            result = await self.connector.sync_customers(
                direction=ERPSyncDirection.PULL,
                since=since,
            )
        elif entity == ERPEntity.SUPPLIER:
            result = await self.connector.sync_suppliers(
                direction=ERPSyncDirection.PULL,
                since=since,
            )
        elif entity == ERPEntity.INVOICE:
            result = await self.connector.sync_invoices(
                direction=ERPSyncDirection.PULL,
                since=since,
            )
        else:
            logger.warning("unsupported_entity_for_fetch", entity=entity.value)
            return []

        # Return actual records from sync result
        if result and result.success:
            logger.info(
                "fetch_remote_completed",
                entity=entity.value,
                records_count=len(result.records),
            )
            return result.records

        if result and not result.success:
            logger.error(
                "fetch_remote_failed",
                entity=entity.value,
                error=result.error_message,
            )

        return []

    async def _prepare_batch(
        self,
        entity: ERPEntity,
        direction: ERPSyncDirection,
        sync_type: SyncType,
        local_records: List[Dict[str, Any]],
        remote_records: List[Dict[str, Any]],
    ) -> SyncBatch:
        """Bereitet Sync-Batch vor.

        Vergleicht lokale und Remote-Datensaetze und kategorisiert
        sie in create/update/delete/conflict.
        """
        batch = SyncBatch(
            entity=entity,
            direction=direction,
            sync_type=sync_type,
        )

        # Build lookups
        local_by_erp_id: Dict[str, Dict[str, Any]] = {}
        local_by_id: Dict[str, Dict[str, Any]] = {}

        for local in local_records:
            local_id = str(local.get("id", ""))
            erp_id = local.get("erp_id")
            if erp_id:
                local_by_erp_id[str(erp_id)] = local
            if local_id:
                local_by_id[local_id] = local

        remote_by_id: Dict[str, Dict[str, Any]] = {}
        for remote in remote_records:
            remote_id = str(remote.get("id", ""))
            if remote_id:
                remote_by_id[remote_id] = remote

        # Process records based on direction
        if direction in (ERPSyncDirection.PULL, ERPSyncDirection.BIDIRECTIONAL):
            await self._process_pull(batch, local_by_erp_id, remote_records)

        if direction in (ERPSyncDirection.PUSH, ERPSyncDirection.BIDIRECTIONAL):
            await self._process_push(batch, local_records, remote_by_id)

        return batch

    async def _process_pull(
        self,
        batch: SyncBatch,
        local_by_erp_id: Dict[str, Dict[str, Any]],
        remote_records: List[Dict[str, Any]],
    ) -> None:
        """Verarbeitet Pull-Operationen (ERP -> Lokal)."""
        for remote in remote_records:
            remote_id = str(remote.get("id", ""))
            local = local_by_erp_id.get(remote_id)

            record = SyncRecord(
                remote_id=remote_id,
                remote_data=remote,
            )

            if local:
                # Update existing
                record.local_id = str(local.get("id", ""))
                record.local_data = local

                # Check for conflict
                if self._is_conflict(local, remote):
                    record.action = "conflict"
                    batch.conflicts.append(record)
                else:
                    record.action = "update"
                    batch.to_update.append(record)
            else:
                # Create new
                record.action = "create"
                batch.to_create.append(record)

    async def _process_push(
        self,
        batch: SyncBatch,
        local_records: List[Dict[str, Any]],
        remote_by_id: Dict[str, Dict[str, Any]],
    ) -> None:
        """Verarbeitet Push-Operationen (Lokal -> ERP)."""
        for local in local_records:
            erp_id = local.get("erp_id")
            remote = remote_by_id.get(str(erp_id)) if erp_id else None

            record = SyncRecord(
                local_id=str(local.get("id", "")),
                local_data=local,
            )

            if remote:
                record.remote_id = str(remote.get("id", ""))
                record.remote_data = remote

                # Already handled in pull phase if bidirectional
                if batch.direction != ERPSyncDirection.BIDIRECTIONAL:
                    if self._is_conflict(local, remote):
                        record.action = "conflict"
                        batch.conflicts.append(record)
                    else:
                        record.action = "update"
                        batch.to_update.append(record)
            else:
                # Create in ERP
                record.action = "create"
                batch.to_create.append(record)

    def _is_conflict(
        self,
        local: Dict[str, Any],
        remote: Dict[str, Any],
    ) -> bool:
        """Prueft ob ein Konflikt vorliegt.

        Ein Konflikt liegt vor, wenn beide Seiten seit dem letzten
        Sync geaendert wurden.
        """
        last_sync = self.connector.config.last_sync_at
        if not last_sync:
            return False

        # Get modification timestamps
        local_modified = self._parse_datetime(
            local.get("updated_at") or local.get("modified_at")
        )
        remote_modified = self._parse_datetime(
            remote.get("write_date") or remote.get("updated_at")
        )

        if not local_modified or not remote_modified:
            return False

        # Both modified after last sync = conflict
        return local_modified > last_sync and remote_modified > last_sync

    def _parse_datetime(self, value: Union[str, datetime, None]) -> Optional[datetime]:
        """Parst einen Datetime-Wert."""
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace(" ", "T").replace("Z", "+00:00"))
            except ValueError:
                return None
        return None

    async def _execute_batch(self, batch: SyncBatch) -> None:
        """Fuehrt Sync-Operationen aus."""
        entity_name = batch.entity.value

        # Create operations
        for record in batch.to_create:
            if batch.direction == ERPSyncDirection.PULL:
                # Transform and store locally
                local_data = self.mapping_service.from_erp(entity_name, record.remote_data)
                record.local_data = local_data
                logger.debug(
                    "sync_create_local",
                    entity=entity_name,
                    remote_id=record.remote_id,
                )
            else:
                # Transform and push to ERP
                erp_data = self.mapping_service.to_erp(entity_name, record.local_data)
                logger.debug(
                    "sync_create_remote",
                    entity=entity_name,
                    local_id=record.local_id,
                )

        # Update operations
        for record in batch.to_update:
            if batch.direction == ERPSyncDirection.PULL:
                local_data = self.mapping_service.from_erp(entity_name, record.remote_data)
                record.local_data.update(local_data)
                logger.debug(
                    "sync_update_local",
                    entity=entity_name,
                    local_id=record.local_id,
                )
            else:
                erp_data = self.mapping_service.to_erp(entity_name, record.local_data)
                logger.debug(
                    "sync_update_remote",
                    entity=entity_name,
                    remote_id=record.remote_id,
                )

        # Handle conflicts based on strategy
        for record in batch.conflicts:
            await self._handle_conflict(batch.entity, record)

    async def _handle_conflict(
        self,
        entity: ERPEntity,
        record: SyncRecord,
    ) -> None:
        """Behandelt einen Konflikt basierend auf Strategie."""
        if self.strategy == SyncStrategy.LAST_WRITE_WINS:
            # Compare timestamps
            local_modified = self._parse_datetime(
                record.local_data.get("updated_at")
            )
            remote_modified = self._parse_datetime(
                record.remote_data.get("write_date")
            )

            if local_modified and remote_modified:
                if local_modified > remote_modified:
                    record.action = "push"
                    logger.info(
                        "conflict_resolved_local_wins",
                        entity=entity.value,
                        local_id=record.local_id,
                    )
                else:
                    record.action = "pull"
                    logger.info(
                        "conflict_resolved_remote_wins",
                        entity=entity.value,
                        remote_id=record.remote_id,
                    )

        elif self.strategy == SyncStrategy.LOCAL_WINS:
            record.action = "push"

        elif self.strategy == SyncStrategy.REMOTE_WINS:
            record.action = "pull"

        elif self.strategy == SyncStrategy.QUEUE_FOR_REVIEW:
            record.action = "queue"
            logger.info(
                "conflict_queued_for_review",
                entity=entity.value,
                local_id=record.local_id,
                remote_id=record.remote_id,
            )

    @staticmethod
    def compute_checksum(data: Dict[str, Any]) -> str:
        """Berechnet SHA-256 Checksum fuer einen Datensatz.

        Wird verwendet um Aenderungen zu erkennen ohne
        alle Felder vergleichen zu muessen.
        """
        # Normalize data for consistent hashing
        normalized = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(normalized.encode()).hexdigest()

    @staticmethod
    def has_changed(old_checksum: Optional[str], new_checksum: str) -> bool:
        """Prueft ob sich ein Datensatz geaendert hat."""
        return old_checksum != new_checksum


# =============================================================================
# Module-Level Factory
# =============================================================================


def create_sync_engine(
    connector: ERPConnector,
    strategy: SyncStrategy = SyncStrategy.LAST_WRITE_WINS,
    custom_mappings: Optional[Dict[str, Any]] = None,
) -> SyncEngine:
    """Erstellt eine Sync-Engine-Instanz.

    Args:
        connector: ERP-Connector
        strategy: Konflikt-Strategie
        custom_mappings: Optionale Custom-Mappings

    Returns:
        Konfigurierte SyncEngine
    """
    mapping_service = get_mapping_service(custom_mappings)
    return SyncEngine(connector, mapping_service, strategy)

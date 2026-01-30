"""Delta-Sync Service - Offline-First Synchronisierung mit Konfliktlösung."""

import structlog
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, desc

logger = structlog.get_logger(__name__)


class ConflictResolution(str, Enum):
    """Konfliktlösungsstrategie."""
    LAST_WRITE_WINS = "last_write_wins"
    SERVER_WINS = "server_wins"
    CLIENT_WINS = "client_wins"
    MERGE = "merge"


@dataclass
class DeltaResponse:
    """Delta-Änderungen seit einem Zeitpunkt."""

    entity_type: str
    changes: List[Dict[str, Any]]
    server_timestamp: datetime
    has_more: bool


@dataclass
class ChangeRecord:
    """Änderungs-Record vom Client."""

    entity_type: str
    entity_id: UUID
    operation: str  # create, update, delete
    data: Dict[str, Any]
    client_timestamp: datetime
    version: Optional[int] = None  # Optimistic Locking


@dataclass
class SyncResult:
    """Ergebnis der Synchronisierung."""

    accepted: int
    rejected: int
    conflicts: List[Dict[str, Any]]
    server_timestamp: datetime


class DeltaSyncService:
    """Service für Delta-Synchronisierung.

    Ermöglicht Offline-First Workflows mit konfliktsicherer Synchronisierung.
    """

    # Batch-Größe für Delta-Queries
    BATCH_SIZE = 100

    # SECURITY FIX: Whitelist statt Blacklist für Mass Assignment
    # Nur diese Felder dürfen via Sync aktualisiert werden (CWE-915)
    SYNC_ALLOWED_FIELDS: Dict[str, List[str]] = {
        "Document": [
            "name", "description", "category_id", "folder_id", "tags",
            "retention_date", "document_metadata",
        ],
        "InvoiceTracking": [
            "status", "due_date", "notes", "paid_at", "paid_amount",
            "dunning_level", "skonto_used",
        ],
        "BusinessEntity": [
            "display_name", "contact_email", "contact_phone", "address",
            "notes", "tags",
        ],
        "Alert": [
            "status", "acknowledged_at", "resolved_at", "resolution_note",
        ],
        "SmartInboxItem": [
            "status", "snoozed_until", "completed_at", "dismissed_at",
        ],
    }

    async def get_changes_since(
        self,
        entity_type: str,
        since: datetime,
        company_id: UUID,
        db: AsyncSession = None,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> DeltaResponse:
        """Holt Änderungen seit einem Zeitpunkt.

        Args:
            entity_type: Entitätstyp (document, entity, invoice, etc.)
            since: Zeitpunkt ab dem Änderungen geholt werden
            company_id: Mandanten-ID
            db: Datenbank-Session
            limit: Max. Anzahl Änderungen
            offset: Offset für Paginierung

        Returns:
            DeltaResponse mit Änderungen

        Raises:
            ValueError: Bei ungültigem Entity-Typ
        """
        if not db:
            raise ValueError("Datenbank-Session erforderlich")

        # Entity-Type Whitelist
        allowed_types = {"document", "entity", "invoice", "alert", "workflow", "payment"}
        if entity_type not in allowed_types:
            raise ValueError(f"Ungültiger Entity-Typ: {entity_type}")

        model_class = self._get_model_class(entity_type)

        # Query für Änderungen seit Timestamp
        stmt = (
            select(model_class)
            .where(
                and_(
                    model_class.company_id == company_id,
                    model_class.updated_at > since,
                )
            )
            .order_by(model_class.updated_at)
        )

        # Limit und Offset
        query_limit = limit or self.BATCH_SIZE
        stmt = stmt.limit(query_limit + 1).offset(offset)  # +1 für has_more Check

        result = await db.execute(stmt)
        items = result.scalars().all()

        # Has-More Check
        has_more = len(items) > query_limit
        if has_more:
            items = items[:query_limit]

        # Änderungen konvertieren
        changes = [self._item_to_change(item) for item in items]

        server_timestamp = datetime.now(timezone.utc)

        logger.info(
            "delta_changes_retrieved",
            entity_type=entity_type,
            since=since.isoformat(),
            changes_count=len(changes),
            has_more=has_more,
        )

        return DeltaResponse(
            entity_type=entity_type,
            changes=changes,
            server_timestamp=server_timestamp,
            has_more=has_more,
        )

    async def push_changes(
        self,
        changes: List[ChangeRecord],
        company_id: UUID,
        user_id: UUID,
        conflict_resolution: ConflictResolution = ConflictResolution.LAST_WRITE_WINS,
        db: AsyncSession = None,
    ) -> SyncResult:
        """Pusht Änderungen vom Client zum Server.

        Args:
            changes: Liste von Änderungs-Records
            company_id: Mandanten-ID
            user_id: Benutzer-ID
            conflict_resolution: Strategie für Konfliktlösung
            db: Datenbank-Session

        Returns:
            SyncResult mit Statistiken

        Raises:
            ValueError: Bei Validierungsfehlern
        """
        if not db:
            raise ValueError("Datenbank-Session erforderlich")

        accepted = 0
        rejected = 0
        conflicts: List[Dict[str, Any]] = []

        for change in changes:
            try:
                # Änderung anwenden
                result = await self._apply_change(
                    change=change,
                    company_id=company_id,
                    user_id=user_id,
                    conflict_resolution=conflict_resolution,
                    db=db,
                )

                if result["status"] == "accepted":
                    accepted += 1
                elif result["status"] == "conflict":
                    conflicts.append(result["conflict"])
                    rejected += 1
                else:
                    rejected += 1

            except Exception as e:
                logger.error(
                    "change_apply_error",
                    entity_type=change.entity_type,
                    entity_id=str(change.entity_id),
                    **safe_error_log(e),
                )
                rejected += 1

        server_timestamp = datetime.now(timezone.utc)

        logger.info(
            "changes_pushed",
            total=len(changes),
            accepted=accepted,
            rejected=rejected,
            conflicts=len(conflicts),
        )

        return SyncResult(
            accepted=accepted,
            rejected=rejected,
            conflicts=conflicts,
            server_timestamp=server_timestamp,
        )

    async def resolve_conflict(
        self,
        entity_type: str,
        entity_id: UUID,
        server_version: Dict[str, Any],
        client_version: Dict[str, Any],
        strategy: ConflictResolution = ConflictResolution.LAST_WRITE_WINS,
    ) -> Dict[str, Any]:
        """Löst einen Konflikt zwischen Server- und Client-Version.

        Args:
            entity_type: Entitätstyp
            entity_id: Entity-ID
            server_version: Server-Daten
            client_version: Client-Daten
            strategy: Konfliktlösungsstrategie

        Returns:
            Gelöste Daten
        """
        logger.info(
            "conflict_resolution_started",
            entity_type=entity_type,
            entity_id=str(entity_id),
            strategy=strategy.value,
        )

        if strategy == ConflictResolution.SERVER_WINS:
            return server_version

        elif strategy == ConflictResolution.CLIENT_WINS:
            return client_version

        elif strategy == ConflictResolution.LAST_WRITE_WINS:
            # Timestamps vergleichen
            server_ts = server_version.get("updated_at")
            client_ts = client_version.get("updated_at")

            if server_ts and client_ts:
                if isinstance(server_ts, str):
                    server_ts = datetime.fromisoformat(server_ts.replace("Z", "+00:00"))
                if isinstance(client_ts, str):
                    client_ts = datetime.fromisoformat(client_ts.replace("Z", "+00:00"))

                if server_ts > client_ts:
                    return server_version
                else:
                    return client_version

            # Fallback: Server gewinnt
            return server_version

        elif strategy == ConflictResolution.MERGE:
            # Intelligente Merge-Strategie
            merged = server_version.copy()

            # Client-Änderungen übernehmen wenn neuere Timestamps
            for key, client_value in client_version.items():
                if key in ["id", "created_at", "company_id"]:
                    continue  # Diese Felder nicht mergen

                server_value = server_version.get(key)

                # Wert übernehmen wenn auf Server None/leer
                if server_value is None or server_value == "":
                    merged[key] = client_value
                # Liste: Unique merge
                elif isinstance(client_value, list) and isinstance(server_value, list):
                    merged[key] = list(set(server_value + client_value))
                # Dict: Recursive merge
                elif isinstance(client_value, dict) and isinstance(server_value, dict):
                    merged[key] = {**server_value, **client_value}
                # Sonst: Client-Wert wenn unterschiedlich
                elif client_value != server_value:
                    merged[key] = client_value

            return merged

        return server_version

    def _get_model_class(self, entity_type: str) -> Any:
        """Gibt Model-Klasse für Entity-Typ zurück."""
        from app.db.models import Document, BusinessEntity, InvoiceTracking
        from app.db.models_alert import Alert


        mapping = {
            "document": Document,
            "entity": BusinessEntity,
            "invoice": InvoiceTracking,
            "alert": Alert,
        }

        if entity_type not in mapping:
            raise ValueError(f"Ungültiger Entity-Typ: {entity_type}")

        return mapping[entity_type]

    def _item_to_change(self, item: Any) -> Dict[str, Any]:
        """Konvertiert DB-Item zu Change-Dict."""
        from sqlalchemy.inspection import inspect

        result = {}
        mapper = inspect(item.__class__)

        for col in mapper.columns:
            value = getattr(item, col.key)

            # UUID zu String
            if isinstance(value, UUID):
                value = str(value)
            # Datetime zu ISO String
            elif isinstance(value, datetime):
                value = value.isoformat()
            # Enum zu String
            elif hasattr(value, "value"):
                value = value.value

            result[col.key] = value

        return result

    async def _apply_change(
        self,
        change: ChangeRecord,
        company_id: UUID,
        user_id: UUID,
        conflict_resolution: ConflictResolution,
        db: AsyncSession,
    ) -> Dict[str, Any]:
        """Wendet eine Änderung an.

        Returns:
            Dict mit status: "accepted", "rejected", oder "conflict"
        """
        model_class = self._get_model_class(change.entity_type)

        # Entity auf Server holen
        stmt = select(model_class).where(
            and_(
                model_class.id == change.entity_id,
                model_class.company_id == company_id,
            )
        )
        result = await db.execute(stmt)
        server_item = result.scalar_one_or_none()

        if change.operation == "create":
            if server_item:
                # Entity existiert bereits - Konflikt
                return {
                    "status": "conflict",
                    "conflict": {
                        "entity_type": change.entity_type,
                        "entity_id": str(change.entity_id),
                        "reason": "entity_already_exists",
                        "server_version": self._item_to_change(server_item),
                        "client_version": change.data,
                    }
                }

            # Neue Entity erstellen
            new_item = model_class(
                id=change.entity_id,
                company_id=company_id,
                **change.data
            )
            db.add(new_item)
            return {"status": "accepted"}

        elif change.operation == "update":
            if not server_item:
                # Entity existiert nicht
                return {
                    "status": "rejected",
                    "reason": "entity_not_found",
                }

            # Version-Check (Optimistic Locking)
            if change.version is not None:
                server_version = getattr(server_item, "version", None)
                if server_version is not None and server_version != change.version:
                    # Konflikt: Version stimmt nicht
                    server_data = self._item_to_change(server_item)
                    resolved = await self.resolve_conflict(
                        entity_type=change.entity_type,
                        entity_id=change.entity_id,
                        server_version=server_data,
                        client_version=change.data,
                        strategy=conflict_resolution,
                    )

                    # Resolved Daten anwenden - WHITELIST (Security Fix)
                    allowed_fields = self.SYNC_ALLOWED_FIELDS.get(
                        change.entity_type, []
                    )
                    for key, value in resolved.items():
                        if key in allowed_fields and hasattr(server_item, key):
                            setattr(server_item, key, value)

                    return {
                        "status": "conflict",
                        "conflict": {
                            "entity_type": change.entity_type,
                            "entity_id": str(change.entity_id),
                            "reason": "version_mismatch",
                            "resolved": resolved,
                        }
                    }

            # Update durchführen - WHITELIST (Security Fix)
            allowed_fields = self.SYNC_ALLOWED_FIELDS.get(
                change.entity_type, []
            )
            for key, value in change.data.items():
                if key in allowed_fields and hasattr(server_item, key):
                    setattr(server_item, key, value)

            # Version incrementieren
            if hasattr(server_item, "version"):
                server_item.version = (server_item.version or 0) + 1

            return {"status": "accepted"}

        elif change.operation == "delete":
            if not server_item:
                return {"status": "accepted"}  # Bereits gelöscht

            await db.delete(server_item)
            return {"status": "accepted"}

        return {"status": "rejected", "reason": "unknown_operation"}

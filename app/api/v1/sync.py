"""Sync API - Offline-First Delta-Synchronisierung."""

import structlog
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db, get_current_user
from app.core.safe_errors import safe_error_detail, safe_error_log
from app.db.models import User
from app.services.sync import (
    DeltaSyncService,
    DeltaResponse,
    ChangeRecord,
    SyncResult,
    ConflictResolution,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/sync", tags=["sync"])


# ============================================================================
# Pydantic Models
# ============================================================================


class SyncChangeRequest(BaseModel):
    """Client-Change für Sync."""

    entity_type: str
    entity_id: UUID
    operation: str = Field(..., description="create, update, delete")
    data: Dict[str, Any]
    client_timestamp: datetime
    version: Optional[int] = None

    @validator("operation")
    def validate_operation(cls, v: str) -> str:
        """Validiert Operation."""
        allowed = {"create", "update", "delete"}
        if v not in allowed:
            raise ValueError(f"Ungültige Operation. Erlaubt: {allowed}")
        return v


class SyncPushRequest(BaseModel):
    """Push-Anfrage mit mehreren Changes."""

    changes: List[SyncChangeRequest]
    conflict_resolution: ConflictResolution = ConflictResolution.LAST_WRITE_WINS


class SyncChangeResponse(BaseModel):
    """Change-Response für Client."""

    entity_type: str
    entity_id: str
    operation: str
    data: Dict[str, Any]
    server_timestamp: str


class SyncDeltaResponse(BaseModel):
    """Delta-Response."""

    entity_type: str
    changes: List[SyncChangeResponse]
    server_timestamp: datetime
    has_more: bool


class SyncConflictInfo(BaseModel):
    """Konflikt-Information."""

    entity_type: str
    entity_id: str
    reason: str
    server_version: Optional[Dict[str, Any]] = None
    client_version: Optional[Dict[str, Any]] = None
    resolved: Optional[Dict[str, Any]] = None


class SyncPushResponse(BaseModel):
    """Push-Antwort."""

    accepted: int
    rejected: int
    conflicts: List[SyncConflictInfo]
    server_timestamp: datetime


class SyncStatusResponse(BaseModel):
    """Sync-Status."""

    last_sync: Optional[datetime]
    pending_changes: int
    server_timestamp: datetime
    sync_enabled: bool


# ============================================================================
# API Endpoints
# ============================================================================


@router.get(
    "/changes",
    response_model=SyncDeltaResponse,
    summary="Änderungen abrufen",
    description="Holt Änderungen seit einem Zeitpunkt für Delta-Sync."
)
async def get_changes(
    entity_type: str = Query(..., description="Entitätstyp (document, entity, invoice, alert)"),
    since: datetime = Query(..., description="Zeitpunkt ab dem Änderungen geholt werden"),
    limit: int = Query(100, ge=1, le=500, description="Max. Anzahl Änderungen"),
    offset: int = Query(0, ge=0, description="Offset für Paginierung"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SyncDeltaResponse:
    """Holt Änderungen seit einem Zeitpunkt."""
    try:
        sync_service = DeltaSyncService()

        delta = await sync_service.get_changes_since(
            entity_type=entity_type,
            since=since,
            company_id=current_user.company_id,
            db=db,
            limit=limit,
            offset=offset,
        )

        # Konvertierung zu Response-Format
        changes = [
            SyncChangeResponse(
                entity_type=delta.entity_type,
                entity_id=str(change.get("id")),
                operation="update",  # Delta-Changes sind immer Updates
                data=change,
                server_timestamp=change.get("updated_at", delta.server_timestamp.isoformat()),
            )
            for change in delta.changes
        ]

        return SyncDeltaResponse(
            entity_type=delta.entity_type,
            changes=changes,
            server_timestamp=delta.server_timestamp,
            has_more=delta.has_more,
        )

    except ValueError as e:
        logger.warning("sync_changes_fehler", **safe_error_log(e))
        raise HTTPException(status_code=400, detail=safe_error_detail(e, "Synchronisierung"))
    except Exception as e:
        logger.error("sync_changes_fehler", exc_info=True, **safe_error_log(e))
        raise HTTPException(status_code=500, detail="Fehler beim Abrufen der Änderungen")


@router.post(
    "/push",
    response_model=SyncPushResponse,
    summary="Änderungen pushen",
    description="Pusht Client-Änderungen zum Server mit Konfliktlösung."
)
async def push_changes(
    request: SyncPushRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SyncPushResponse:
    """Pusht Änderungen vom Client."""
    try:
        sync_service = DeltaSyncService()

        # ChangeRecords erstellen
        change_records = [
            ChangeRecord(
                entity_type=change.entity_type,
                entity_id=change.entity_id,
                operation=change.operation,
                data=change.data,
                client_timestamp=change.client_timestamp,
                version=change.version,
            )
            for change in request.changes
        ]

        # Push durchführen
        result = await sync_service.push_changes(
            changes=change_records,
            company_id=current_user.company_id,
            user_id=current_user.id,
            conflict_resolution=request.conflict_resolution,
            db=db,
        )

        await db.commit()

        # Konflikt-Infos konvertieren
        conflicts = [
            SyncConflictInfo(
                entity_type=conflict.get("entity_type"),
                entity_id=conflict.get("entity_id"),
                reason=conflict.get("reason"),
                server_version=conflict.get("server_version"),
                client_version=conflict.get("client_version"),
                resolved=conflict.get("resolved"),
            )
            for conflict in result.conflicts
        ]

        return SyncPushResponse(
            accepted=result.accepted,
            rejected=result.rejected,
            conflicts=conflicts,
            server_timestamp=result.server_timestamp,
        )

    except ValueError as e:
        logger.warning("sync_push_fehler", **safe_error_log(e))
        await db.rollback()
        raise HTTPException(status_code=400, detail=safe_error_detail(e, "Synchronisierung"))
    except Exception as e:
        logger.error("sync_push_fehler", exc_info=True, **safe_error_log(e))
        await db.rollback()
        raise HTTPException(status_code=500, detail="Fehler beim Pushen der Änderungen")


@router.post(
    "/resolve-conflict",
    response_model=Dict[str, Any],
    summary="Konflikt lösen",
    description="Löst manuell einen Sync-Konflikt."
)
async def resolve_conflict(
    entity_type: str,
    entity_id: UUID,
    server_version: Dict[str, Any],
    client_version: Dict[str, Any],
    strategy: ConflictResolution = Query(ConflictResolution.LAST_WRITE_WINS),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Löst einen Konflikt manuell."""
    try:
        sync_service = DeltaSyncService()

        resolved = await sync_service.resolve_conflict(
            entity_type=entity_type,
            entity_id=entity_id,
            server_version=server_version,
            client_version=client_version,
            strategy=strategy,
        )

        logger.info(
            "conflict_resolved",
            entity_type=entity_type,
            entity_id=str(entity_id),
            strategy=strategy.value,
        )

        return {
            "entity_type": entity_type,
            "entity_id": str(entity_id),
            "resolved": resolved,
            "strategy": strategy.value,
        }

    except Exception as e:
        logger.error("conflict_resolution_fehler", exc_info=True, **safe_error_log(e))
        raise HTTPException(status_code=500, detail="Fehler bei der Konfliktlösung")


@router.get(
    "/status",
    response_model=SyncStatusResponse,
    summary="Sync-Status",
    description="Holt den aktuellen Sync-Status des Users."
)
async def get_sync_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SyncStatusResponse:
    """Holt Sync-Status."""
    try:
        # User-Preferences für Sync-Status
        user_prefs = current_user.preferences or {}
        sync_prefs = user_prefs.get("sync", {})

        last_sync_str = sync_prefs.get("last_sync")
        last_sync = None
        if last_sync_str:
            try:
                last_sync = datetime.fromisoformat(last_sync_str)
            except (ValueError, TypeError):
                pass

        # Pending Changes zählen (würde echte Implementation erfordern)
        pending_changes = 0

        return SyncStatusResponse(
            last_sync=last_sync,
            pending_changes=pending_changes,
            server_timestamp=datetime.now(),
            sync_enabled=sync_prefs.get("enabled", True),
        )

    except Exception as e:
        logger.error("sync_status_fehler", **safe_error_log(e))
        raise HTTPException(status_code=500, detail="Fehler beim Abrufen des Sync-Status")

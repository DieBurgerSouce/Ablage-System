"""
ERP Admin API Endpoints.

Enterprise-Level ERP-Verbindungsverwaltung:
- CRUD für ERP-Verbindungen
- Verbindungstest
- Sync-Status und Historie
- Konflikt-Management

Feinpoliert und durchdacht - ERP-Administration auf Enterprise-Niveau.
"""

import structlog
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, update, delete
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.encryption import (
    EncryptionError,
    decrypt_data,
    encrypt_api_key,
    encrypt_data,
)
from app.core.safe_errors import safe_error_detail, safe_error_log

from app.db.models import (
    User,
    Company,
    ERPConnection,
    ERPSyncHistory,
    ERPConflict,
    ERPFieldMapping,
    ERPEntityMapping,
    ERPSyncStatus,
    ERPConflictStatus,
    OdooSyncStatus,
)
from app.api.dependencies import get_current_user, get_db, require_admin
from app.middleware.company_context import require_company
from pydantic import BaseModel, ConfigDict, Field

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/erp", tags=["erp-admin"])


# =============================================================================
# Pydantic Schemas
# =============================================================================


class ERPConnectionCreate(BaseModel):
    """Schema für neue ERP-Verbindung."""

    name: str = Field(..., min_length=1, max_length=255)
    erp_type: str = Field(default="odoo", pattern="^(odoo|lexware|sap_b1|custom)$")
    url: str = Field(..., min_length=1, max_length=500)
    database_name: Optional[str] = Field(None, max_length=255)
    username: str = Field(..., min_length=1, max_length=255)
    api_key: str = Field(..., min_length=1)

    sync_direction: str = Field(default="bidirectional")
    sync_interval_minutes: int = Field(default=15, ge=5, le=1440)
    enabled_entities: List[str] = Field(default=["customer", "supplier", "invoice"])

    max_requests_per_minute: int = Field(default=60, ge=1, le=1000)
    batch_size: int = Field(default=100, ge=10, le=1000)

    # Odoo-interne Company-ID (Spargelmesser = 2). Wird per-Connection in
    # OdooSyncStatus.sync_state["odoo_company_id"] persistiert und hat
    # Vorrang vor dem globalen ODOO_MIRROR_COMPANY_ID (Fallback).
    odoo_company_id: Optional[int] = Field(None, ge=1)


class ERPConnectionUpdate(BaseModel):
    """Schema für Verbindungs-Update."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    url: Optional[str] = Field(None, min_length=1, max_length=500)
    database_name: Optional[str] = None
    username: Optional[str] = None
    api_key: Optional[str] = None

    sync_direction: Optional[str] = None
    sync_interval_minutes: Optional[int] = Field(None, ge=5, le=1440)
    enabled_entities: Optional[List[str]] = None

    max_requests_per_minute: Optional[int] = Field(None, ge=1, le=1000)
    batch_size: Optional[int] = Field(None, ge=10, le=1000)

    is_active: Optional[bool] = None

    # Explizit gesendetes null loescht den per-Connection-Wert (Fallback
    # auf ODOO_MIRROR_COMPANY_ID greift dann wieder); nicht gesendet = unveraendert.
    odoo_company_id: Optional[int] = Field(None, ge=1)


class ERPConnectionResponse(BaseModel):
    """Response Schema für ERP-Verbindung."""

    id: str
    company_id: str
    name: str
    erp_type: str
    url: str
    database_name: Optional[str]
    username: str

    sync_direction: str
    sync_interval_minutes: int
    enabled_entities: List[str]

    is_active: bool
    connection_status: str
    last_error: Optional[str]
    last_successful_connection: Optional[str]

    last_sync_at: Optional[str]
    last_full_sync_at: Optional[str]
    next_scheduled_sync: Optional[str]

    created_at: str
    updated_at: str

    # Effektive Odoo-Company-ID (per-Connection-Wert oder globaler Fallback)
    odoo_company_id: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class ERPConnectionTestResult(BaseModel):
    """Ergebnis eines Verbindungstests."""

    success: bool
    connected: bool
    version: Optional[str] = None
    erp_type: str
    error: Optional[str] = None


class ERPSyncHistoryResponse(BaseModel):
    """Response Schema für Sync-Historie."""

    id: str
    connection_id: str
    sync_type: str
    entity: str
    direction: str
    status: str

    records_synced: int
    records_created: int
    records_updated: int
    records_deleted: int
    records_failed: int

    conflicts_detected: int
    conflicts_resolved: int

    started_at: str
    completed_at: Optional[str]
    duration_seconds: Optional[float]

    error_message: Optional[str]
    triggered_by: Optional[str]

    model_config = ConfigDict(from_attributes=True)


class ERPConflictResponse(BaseModel):
    """Response Schema für Konflikte."""

    id: str
    connection_id: str
    entity: str
    local_id: str
    remote_id: str

    local_data: dict
    remote_data: dict
    diff: Optional[dict]

    local_modified_at: Optional[str]
    remote_modified_at: Optional[str]
    detected_at: str

    status: str
    resolution: Optional[str]
    priority: str

    model_config = ConfigDict(from_attributes=True)


class ERPConflictResolve(BaseModel):
    """Schema für Konflikt-Auflösung."""

    resolution: str = Field(..., pattern="^(local_wins|remote_wins|merged|ignored)$")
    resolved_data: Optional[dict] = None
    notes: Optional[str] = None


# =============================================================================
# Helper Functions
# =============================================================================


def _format_datetime(dt: Optional[datetime]) -> Optional[str]:
    """Formatiert datetime zu ISO string."""
    return dt.isoformat() if dt else None


def _encrypt_connection_api_key(api_key: str, connection_id: UUID) -> str:
    """Verschluesselt den API-Key mit der AAD, die der Worker erwartet.

    Die AAD MUSS ``erp_connection:{connection_id}`` sein — genau damit
    entschluesselt ``decrypt_api_key`` in erp_sync_tasks. Die fruehere
    Company-AAD (``erp:{company_id}``) war der Go-Live-P1-Fund 2026-07-11:
    AES-GCM InvalidTag -> api_key=None -> jede UI-Connection scheiterte
    beim Odoo-Login.
    """
    return encrypt_api_key(api_key, str(connection_id))


async def _set_connection_odoo_company_id(
    db: AsyncSession, connection_id: UUID, value: Optional[int]
) -> None:
    """Persistiert die Odoo-Company-ID per-Connection (migrationsfrei).

    Ablageort ist ``OdooSyncStatus.sync_state["odoo_company_id"]`` der
    Mirror-Zeile — dieselbe Quelle, die Mirror UND Push aufloesen
    (Vorrang vor dem globalen ODOO_MIRROR_COMPANY_ID). ``None`` loescht
    den Wert (Fallback greift wieder).
    """
    # Lazy-Import der Konstante: vermeidet Import-Gewicht im API-Modul
    from app.services.erp.odoo_mirror_service import MIRROR_DATA_TYPE

    result = await db.execute(
        select(OdooSyncStatus).where(
            and_(
                OdooSyncStatus.connection_id == connection_id,
                OdooSyncStatus.data_type == MIRROR_DATA_TYPE,
            )
        )
    )
    sync_status = result.scalar_one_or_none()

    if sync_status is None:
        if value is None:
            return
        db.add(
            OdooSyncStatus(
                connection_id=connection_id,
                data_type=MIRROR_DATA_TYPE,
                sync_state={"odoo_company_id": int(value)},
                consecutive_failures=0,
                is_paused=False,
            )
        )
        return

    # WICHTIG: komplettes Dict neu zuweisen, damit SQLAlchemy die Aenderung
    # am CrossDBJSON-Feld erkennt (kein MutableDict).
    state = dict(sync_status.sync_state or {})
    if value is None:
        state.pop("odoo_company_id", None)
    else:
        state["odoo_company_id"] = int(value)
    sync_status.sync_state = state


async def _effective_odoo_company_ids(
    db: AsyncSession, connection_ids: Sequence[UUID]
) -> Dict[UUID, Optional[int]]:
    """Effektive Odoo-Company-ID je Connection (sync_state -> Env-Fallback)."""
    from app.services.erp.odoo_mirror_service import MIRROR_DATA_TYPE

    per_connection: Dict[UUID, int] = {}
    ids = list(connection_ids)
    if ids:
        result = await db.execute(
            select(OdooSyncStatus).where(
                and_(
                    OdooSyncStatus.connection_id.in_(ids),
                    OdooSyncStatus.data_type == MIRROR_DATA_TYPE,
                )
            )
        )
        for row in result.scalars().all():
            value = dict(row.sync_state or {}).get("odoo_company_id")
            if value is None:
                continue
            try:
                per_connection[row.connection_id] = int(value)
            except (TypeError, ValueError):
                logger.warning(
                    "odoo_company_id_invalid_in_sync_state",
                    connection_id=str(row.connection_id),
                    value=str(value),
                )

    fallback: Optional[int] = None
    if settings.ODOO_MIRROR_COMPANY_ID is not None:
        try:
            fallback = int(settings.ODOO_MIRROR_COMPANY_ID)
        except (TypeError, ValueError):
            fallback = None

    return {cid: per_connection.get(cid, fallback) for cid in ids}


def _connection_to_response(
    conn: ERPConnection, odoo_company_id: Optional[int] = None
) -> ERPConnectionResponse:
    """Konvertiert DB-Model zu Response."""
    return ERPConnectionResponse(
        odoo_company_id=odoo_company_id,
        id=str(conn.id),
        company_id=str(conn.company_id),
        name=conn.name,
        erp_type=conn.erp_type,
        url=conn.url,
        database_name=conn.database_name,
        username=conn.username,
        sync_direction=conn.sync_direction,
        sync_interval_minutes=conn.sync_interval_minutes,
        enabled_entities=conn.enabled_entities or [],
        is_active=conn.is_active,
        connection_status=conn.connection_status,
        last_error=conn.last_error,
        last_successful_connection=_format_datetime(conn.last_successful_connection),
        last_sync_at=_format_datetime(conn.last_sync_at),
        last_full_sync_at=_format_datetime(conn.last_full_sync_at),
        next_scheduled_sync=_format_datetime(conn.next_scheduled_sync),
        created_at=_format_datetime(conn.created_at) or "",
        updated_at=_format_datetime(conn.updated_at) or "",
    )


# =============================================================================
# Connection Endpoints
# =============================================================================


@router.get(
    "/connections",
    response_model=List[ERPConnectionResponse],
    summary="ERP-Verbindungen auflisten",
    description="Listet alle ERP-Verbindungen der aktuellen Firma auf.",
)
async def list_connections(
    active_only: bool = Query(False, description="Nur aktive Verbindungen"),
    current_user: User = Depends(require_admin),
    company: Company = Depends(require_company),
    db: AsyncSession = Depends(get_db),
) -> List[ERPConnectionResponse]:
    """Listet alle ERP-Verbindungen auf."""
    # SECURITY FIX: company.id via require_company (Multi-Tenant-validiert)
    query = select(ERPConnection).where(
        ERPConnection.company_id == company.id
    )

    if active_only:
        query = query.where(ERPConnection.is_active == True)

    query = query.order_by(ERPConnection.name)

    result = await db.execute(query)
    connections = result.scalars().all()

    effective = await _effective_odoo_company_ids(db, [c.id for c in connections])
    return [
        _connection_to_response(conn, effective.get(conn.id)) for conn in connections
    ]


@router.get(
    "/connections/{connection_id}",
    response_model=ERPConnectionResponse,
    summary="ERP-Verbindung abrufen",
)
async def get_connection(
    connection_id: UUID,
    current_user: User = Depends(require_admin),
    company: Company = Depends(require_company),
    db: AsyncSession = Depends(get_db),
) -> ERPConnectionResponse:
    """Ruft Details einer ERP-Verbindung ab."""
    # SECURITY FIX: company.id via require_company (Multi-Tenant-validiert)
    result = await db.execute(
        select(ERPConnection).where(
            and_(
                ERPConnection.id == connection_id,
                ERPConnection.company_id == company.id,
            )
        )
    )
    connection = result.scalar_one_or_none()

    if not connection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ERP-Verbindung nicht gefunden",
        )

    effective = await _effective_odoo_company_ids(db, [connection.id])
    return _connection_to_response(connection, effective.get(connection.id))


@router.post(
    "/connections",
    response_model=ERPConnectionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="ERP-Verbindung erstellen",
)
async def create_connection(
    data: ERPConnectionCreate,
    current_user: User = Depends(require_admin),
    company: Company = Depends(require_company),
    db: AsyncSession = Depends(get_db),
) -> ERPConnectionResponse:
    """Erstellt eine neue ERP-Verbindung."""
    # SECURITY FIX: API Key mit AES-256-GCM verschluesseln
    # SECURITY FIX: company.id via require_company (Multi-Tenant-validiert)
    # Die ID wird VOR der Verschluesselung erzeugt, weil sie die AAD ist
    # (Worker entschluesselt mit decrypt_api_key(connection_id)).
    connection_id = uuid4()
    try:
        encrypted_key = _encrypt_connection_api_key(data.api_key, connection_id)
    except EncryptionError as e:
        logger.error(
            "erp_api_key_encryption_failed",
            **safe_error_log(e),
            user_id=str(current_user.id),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "ERP-Verschluesselung"),
        )

    connection = ERPConnection(
        id=connection_id,
        company_id=company.id,
        name=data.name,
        erp_type=data.erp_type,
        url=data.url,
        database_name=data.database_name,
        username=data.username,
        encrypted_api_key=encrypted_key,
        sync_direction=data.sync_direction,
        sync_interval_minutes=data.sync_interval_minutes,
        enabled_entities=data.enabled_entities,
        max_requests_per_minute=data.max_requests_per_minute,
        batch_size=data.batch_size,
        created_by=current_user.id,
        updated_by=current_user.id,
    )

    db.add(connection)
    if data.odoo_company_id is not None:
        await db.flush()  # Connection zuerst (FK von OdooSyncStatus)
        await _set_connection_odoo_company_id(db, connection_id, data.odoo_company_id)
    await db.commit()
    await db.refresh(connection)

    logger.info(
        "erp_connection_created",
        connection_id=str(connection.id),
        name=connection.name,
        erp_type=connection.erp_type,
        user_id=str(current_user.id),
    )

    effective = await _effective_odoo_company_ids(db, [connection.id])
    return _connection_to_response(connection, effective.get(connection.id))


@router.put(
    "/connections/{connection_id}",
    response_model=ERPConnectionResponse,
    summary="ERP-Verbindung aktualisieren",
)
async def update_connection(
    connection_id: UUID,
    data: ERPConnectionUpdate,
    current_user: User = Depends(require_admin),
    company: Company = Depends(require_company),
    db: AsyncSession = Depends(get_db),
) -> ERPConnectionResponse:
    """Aktualisiert eine ERP-Verbindung."""
    # SECURITY FIX: company.id via require_company (Multi-Tenant-validiert)
    result = await db.execute(
        select(ERPConnection).where(
            and_(
                ERPConnection.id == connection_id,
                ERPConnection.company_id == company.id,
            )
        )
    )
    connection = result.scalar_one_or_none()

    if not connection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ERP-Verbindung nicht gefunden",
        )

    # Update fields
    update_data = data.model_dump(exclude_unset=True)

    # Odoo-Company-ID lebt NICHT auf erp_connections, sondern im
    # sync_state (siehe _set_connection_odoo_company_id) — vor dem
    # setattr-Loop herausnehmen. Explizites null loescht den Wert.
    if "odoo_company_id" in update_data:
        await _set_connection_odoo_company_id(
            db, connection_id, update_data.pop("odoo_company_id")
        )

    # SECURITY FIX: Handle API key encryption (AAD = connection_id,
    # exakt wie decrypt_api_key im Worker — P1-Fund 2026-07-11)
    if "api_key" in update_data:
        try:
            encrypted_key = _encrypt_connection_api_key(
                update_data.pop("api_key"), connection_id
            )
            update_data["encrypted_api_key"] = encrypted_key
        except EncryptionError as e:
            logger.error(
                "erp_api_key_encryption_failed",
                **safe_error_log(e),
                connection_id=str(connection_id),
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=safe_error_detail(e, "ERP-Verschluesselung"),
            )

    for key, value in update_data.items():
        setattr(connection, key, value)

    connection.updated_by = current_user.id
    # TIMEZONE FIX: Verwende timezone-aware datetime
    connection.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(connection)

    logger.info(
        "erp_connection_updated",
        connection_id=str(connection_id),
        user_id=str(current_user.id),
    )

    effective = await _effective_odoo_company_ids(db, [connection.id])
    return _connection_to_response(connection, effective.get(connection.id))


@router.delete(
    "/connections/{connection_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="ERP-Verbindung löschen",
)
async def delete_connection(
    connection_id: UUID,
    current_user: User = Depends(require_admin),
    company: Company = Depends(require_company),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Löscht eine ERP-Verbindung."""
    # SECURITY FIX: company.id via require_company (Multi-Tenant-validiert)
    result = await db.execute(
        select(ERPConnection).where(
            and_(
                ERPConnection.id == connection_id,
                ERPConnection.company_id == company.id,
            )
        )
    )
    connection = result.scalar_one_or_none()

    if not connection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ERP-Verbindung nicht gefunden",
        )

    await db.delete(connection)
    await db.commit()

    logger.info(
        "erp_connection_deleted",
        connection_id=str(connection_id),
        user_id=str(current_user.id),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/connections/{connection_id}/test",
    response_model=ERPConnectionTestResult,
    summary="Verbindung testen",
)
async def test_connection(
    connection_id: UUID,
    current_user: User = Depends(require_admin),
    company: Company = Depends(require_company),
    db: AsyncSession = Depends(get_db),
) -> ERPConnectionTestResult:
    """Testet eine ERP-Verbindung."""
    from app.workers.tasks.erp_sync_tasks import test_connection as test_task

    # SECURITY FIX: company.id via require_company (Multi-Tenant-validiert)
    result = await db.execute(
        select(ERPConnection).where(
            and_(
                ERPConnection.id == connection_id,
                ERPConnection.company_id == company.id,
            )
        )
    )
    connection = result.scalar_one_or_none()

    if not connection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ERP-Verbindung nicht gefunden",
        )

    # Execute test synchronously for immediate feedback
    try:
        task_result = test_task.delay(str(connection_id))
        result_data = task_result.get(timeout=30)

        return ERPConnectionTestResult(**result_data)

    except Exception as e:
        logger.exception("erp_test_connection_failed", **safe_error_log(e))
        return ERPConnectionTestResult(
            success=False,
            connected=False,
            erp_type=connection.erp_type,
            error=safe_error_detail(e, "ERP-Verbindungstest"),
        )


# =============================================================================
# Sync Endpoints
# =============================================================================


@router.post(
    "/connections/{connection_id}/sync",
    summary="Sync manuell starten",
    description="Startet eine manuelle Synchronisation.",
)
async def trigger_sync(
    connection_id: UUID,
    sync_type: str = Query("delta", pattern="^(full|delta)$"),
    current_user: User = Depends(require_admin),
    company: Company = Depends(require_company),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Startet manuelle Synchronisation."""
    from app.workers.tasks.erp_sync_tasks import sync_connection

    # SECURITY FIX: company.id via require_company (Multi-Tenant-validiert)
    result = await db.execute(
        select(ERPConnection).where(
            and_(
                ERPConnection.id == connection_id,
                ERPConnection.company_id == company.id,
            )
        )
    )
    connection = result.scalar_one_or_none()

    if not connection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ERP-Verbindung nicht gefunden",
        )

    if not connection.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ERP-Verbindung ist deaktiviert",
        )

    # Queue sync task
    task = sync_connection.delay(
        connection_id=str(connection_id),
        sync_type=sync_type,
        triggered_by=str(current_user.id),
    )

    logger.info(
        "erp_sync_triggered",
        connection_id=str(connection_id),
        sync_type=sync_type,
        task_id=task.id,
        user_id=str(current_user.id),
    )

    return {
        "message": "Synchronisation gestartet",
        "task_id": task.id,
        "sync_type": sync_type,
    }


@router.get(
    "/connections/{connection_id}/sync/history",
    response_model=List[ERPSyncHistoryResponse],
    summary="Sync-Historie abrufen",
)
async def get_sync_history(
    connection_id: UUID,
    page: int = Query(1, ge=1, description="Seitennummer (1-basiert)"),
    per_page: int = Query(50, ge=1, le=100, description="Eintraege pro Seite"),
    entity: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    current_user: User = Depends(require_admin),
    company: Company = Depends(require_company),
    db: AsyncSession = Depends(get_db),
) -> List[ERPSyncHistoryResponse]:
    """Ruft Sync-Historie ab."""
    # SECURITY FIX: company.id via require_company (Multi-Tenant-validiert)
    conn_result = await db.execute(
        select(ERPConnection.id).where(
            and_(
                ERPConnection.id == connection_id,
                ERPConnection.company_id == company.id,
            )
        )
    )
    if not conn_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ERP-Verbindung nicht gefunden",
        )

    query = select(ERPSyncHistory).where(
        ERPSyncHistory.connection_id == connection_id
    )

    if entity:
        query = query.where(ERPSyncHistory.entity == entity)
    if status_filter:
        query = query.where(ERPSyncHistory.status == status_filter)

    query = query.order_by(ERPSyncHistory.started_at.desc()).limit(per_page).offset((page - 1) * per_page)

    result = await db.execute(query)
    history = result.scalars().all()

    return [
        ERPSyncHistoryResponse(
            id=str(h.id),
            connection_id=str(h.connection_id),
            sync_type=h.sync_type,
            entity=h.entity,
            direction=h.direction,
            status=h.status,
            records_synced=h.records_synced,
            records_created=h.records_created,
            records_updated=h.records_updated,
            records_deleted=h.records_deleted,
            records_failed=h.records_failed,
            conflicts_detected=h.conflicts_detected,
            conflicts_resolved=h.conflicts_resolved,
            started_at=_format_datetime(h.started_at) or "",
            completed_at=_format_datetime(h.completed_at),
            duration_seconds=h.duration_seconds,
            error_message=h.error_message,
            triggered_by=str(h.triggered_by) if h.triggered_by else None,
        )
        for h in history
    ]


# =============================================================================
# Conflict Endpoints
# =============================================================================


@router.get(
    "/conflicts",
    response_model=List[ERPConflictResponse],
    summary="Konflikte auflisten",
)
async def list_conflicts(
    connection_id: Optional[UUID] = None,
    status_filter: str = Query("pending", alias="status"),
    page: int = Query(1, ge=1, description="Seitennummer (1-basiert)"),
    per_page: int = Query(50, ge=1, le=100, description="Eintraege pro Seite"),
    current_user: User = Depends(require_admin),
    company: Company = Depends(require_company),
    db: AsyncSession = Depends(get_db),
) -> List[ERPConflictResponse]:
    """Listet offene Konflikte auf."""
    # SECURITY FIX: company.id via require_company (Multi-Tenant-validiert)
    conn_query = select(ERPConnection.id).where(
        ERPConnection.company_id == company.id
    )
    conn_result = await db.execute(conn_query)
    connection_ids = [row[0] for row in conn_result.fetchall()]

    query = select(ERPConflict).where(
        ERPConflict.connection_id.in_(connection_ids)
    )

    if connection_id:
        query = query.where(ERPConflict.connection_id == connection_id)
    if status_filter:
        query = query.where(ERPConflict.status == status_filter)

    query = query.order_by(
        ERPConflict.priority.desc(),
        ERPConflict.detected_at.desc(),
    ).limit(per_page).offset((page - 1) * per_page)

    result = await db.execute(query)
    conflicts = result.scalars().all()

    return [
        ERPConflictResponse(
            id=str(c.id),
            connection_id=str(c.connection_id),
            entity=c.entity,
            local_id=c.local_id,
            remote_id=c.remote_id,
            local_data=c.local_data,
            remote_data=c.remote_data,
            diff=c.diff,
            local_modified_at=_format_datetime(c.local_modified_at),
            remote_modified_at=_format_datetime(c.remote_modified_at),
            detected_at=_format_datetime(c.detected_at) or "",
            status=c.status,
            resolution=c.resolution,
            priority=c.priority,
        )
        for c in conflicts
    ]


@router.post(
    "/conflicts/{conflict_id}/resolve",
    response_model=ERPConflictResponse,
    summary="Konflikt aufloesen",
)
async def resolve_conflict(
    conflict_id: UUID,
    data: ERPConflictResolve,
    current_user: User = Depends(require_admin),
    company: Company = Depends(require_company),
    db: AsyncSession = Depends(get_db),
) -> ERPConflictResponse:
    """Loest einen Konflikt auf."""
    # SECURITY FIX: company.id via require_company (Multi-Tenant-validiert)
    result = await db.execute(
        select(ERPConflict)
        .join(ERPConnection)
        .where(
            and_(
                ERPConflict.id == conflict_id,
                ERPConnection.company_id == company.id,
            )
        )
    )
    conflict = result.scalar_one_or_none()

    if not conflict:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Konflikt nicht gefunden",
        )

    if conflict.status != ERPConflictStatus.PENDING.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Konflikt wurde bereits aufgeloest",
        )

    # Update conflict
    conflict.status = ERPConflictStatus.RESOLVED.value
    conflict.resolution = data.resolution
    conflict.resolved_data = data.resolved_data
    conflict.resolved_at = datetime.now(timezone.utc)
    conflict.resolved_by = current_user.id
    conflict.resolution_notes = data.notes

    await db.commit()
    await db.refresh(conflict)

    logger.info(
        "erp_conflict_resolved",
        conflict_id=str(conflict_id),
        resolution=data.resolution,
        user_id=str(current_user.id),
    )

    return ERPConflictResponse(
        id=str(conflict.id),
        connection_id=str(conflict.connection_id),
        entity=conflict.entity,
        local_id=conflict.local_id,
        remote_id=conflict.remote_id,
        local_data=conflict.local_data,
        remote_data=conflict.remote_data,
        diff=conflict.diff,
        local_modified_at=_format_datetime(conflict.local_modified_at),
        remote_modified_at=_format_datetime(conflict.remote_modified_at),
        detected_at=_format_datetime(conflict.detected_at) or "",
        status=conflict.status,
        resolution=conflict.resolution,
        priority=conflict.priority,
    )


# =============================================================================
# Stats Endpoints
# =============================================================================


@router.get(
    "/stats",
    summary="ERP-Statistiken abrufen",
)
async def get_erp_stats(
    current_user: User = Depends(require_admin),
    company: Company = Depends(require_company),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Ruft aggregierte ERP-Statistiken ab."""
    # SECURITY FIX: company.id via require_company (Multi-Tenant-validiert)
    # Connection count
    conn_result = await db.execute(
        select(func.count(ERPConnection.id)).where(
            ERPConnection.company_id == company.id
        )
    )
    total_connections = conn_result.scalar() or 0

    # Active connections
    active_result = await db.execute(
        select(func.count(ERPConnection.id)).where(
            and_(
                ERPConnection.company_id == company.id,
                ERPConnection.is_active == True,
            )
        )
    )
    active_connections = active_result.scalar() or 0

    # Pending conflicts
    conn_ids = await db.execute(
        select(ERPConnection.id).where(
            ERPConnection.company_id == company.id
        )
    )
    connection_ids = [row[0] for row in conn_ids.fetchall()]

    conflict_result = await db.execute(
        select(func.count(ERPConflict.id)).where(
            and_(
                ERPConflict.connection_id.in_(connection_ids),
                ERPConflict.status == ERPConflictStatus.PENDING.value,
            )
        )
    )
    pending_conflicts = conflict_result.scalar() or 0

    # Recent syncs (last 24h)
    from datetime import timedelta
    yesterday = datetime.now(timezone.utc) - timedelta(hours=24)

    sync_result = await db.execute(
        select(func.count(ERPSyncHistory.id)).where(
            and_(
                ERPSyncHistory.connection_id.in_(connection_ids),
                ERPSyncHistory.started_at >= yesterday,
            )
        )
    )
    recent_syncs = sync_result.scalar() or 0

    return {
        "total_connections": total_connections,
        "active_connections": active_connections,
        "pending_conflicts": pending_conflicts,
        "syncs_last_24h": recent_syncs,
    }


# =============================================================================
# Odoo-Spiegel-Monitoring (Neuausrichtung Phase 3, Plan par.4c.2)
# =============================================================================


class OdooMirrorStatusResponse(BaseModel):
    """Status-Zeile des Odoo->Ablage Vollarchiv-Spiegels."""

    connection_id: str
    connection_name: str
    data_type: str

    last_sync_cursor: Optional[str]
    last_sync_at: Optional[str]
    last_successful_sync_at: Optional[str]

    total_records_synced: int
    last_record_count: Optional[int]
    last_run: Optional[dict]

    consecutive_failures: int
    is_paused: bool
    last_error: Optional[str]

    model_config = ConfigDict(from_attributes=True)


@router.get(
    "/mirror-status",
    response_model=List[OdooMirrorStatusResponse],
    summary="Status des Odoo-Vollarchiv-Spiegels",
)
async def get_mirror_status(
    current_user: User = Depends(require_admin),
    company: Company = Depends(require_company),
    db: AsyncSession = Depends(get_db),
) -> List[OdooMirrorStatusResponse]:
    """Liest die Spiegel-Status-Eintraege (data_type mirror_*) der Firma.

    Zeigt je Verbindung: Cursor, letzte Laufzeit, Zaehler des letzten
    Laufs (sync_state["last_run"]) und consecutive_failures.
    """
    # SECURITY FIX: company.id via require_company (Multi-Tenant-validiert)
    result = await db.execute(
        select(OdooSyncStatus, ERPConnection.name)
        .join(ERPConnection, OdooSyncStatus.connection_id == ERPConnection.id)
        .where(
            and_(
                ERPConnection.company_id == company.id,
                OdooSyncStatus.data_type.like("mirror_%"),
            )
        )
        .order_by(ERPConnection.name, OdooSyncStatus.data_type)
    )
    rows = result.all()

    return [
        OdooMirrorStatusResponse(
            connection_id=str(sync_status.connection_id),
            connection_name=connection_name,
            data_type=sync_status.data_type,
            last_sync_cursor=sync_status.last_sync_cursor,
            last_sync_at=_format_datetime(sync_status.last_sync_at),
            last_successful_sync_at=_format_datetime(
                sync_status.last_successful_sync_at
            ),
            total_records_synced=sync_status.total_records_synced or 0,
            last_record_count=sync_status.last_record_count,
            last_run=(sync_status.sync_state or {}).get("last_run"),
            consecutive_failures=sync_status.consecutive_failures or 0,
            is_paused=bool(sync_status.is_paused),
            last_error=sync_status.last_error,
        )
        for sync_status, connection_name in rows
    ]

# -*- coding: utf-8 -*-
"""Export Jobs API - Zentraler Endpoint fuer Export-Status und -Verwaltung.

Enthaelt:
- Export-Job starten (async via Celery)
- Export-Job Status abfragen (Polling)
- Export-Job abbrechen (Cancellation)
- WebSocket fuer Echtzeit-Updates
"""

import asyncio
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID, uuid4

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, Request
from jose import JWTError, jwt
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

# SECURITY FIX 27-6: Rate Limiting fuer Export Endpoints
from app.core.rate_limiting import limiter, get_user_identifier

from app.api.dependencies import get_current_active_user, get_db
from app.core.config import settings
from app.db.models import User, BatchJob, ProcessingStatus
from app.db.schemas import ExportFormat
from app.db.session import get_async_session_context

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/exports", tags=["exports"])


# ==============================================================================
# Pydantic Schemas
# ==============================================================================


class ExportJobRequest(BaseModel):
    """Request fuer neuen Export-Job."""
    document_ids: List[UUID] = Field(..., min_length=1, max_length=1000)
    format: ExportFormat = Field(default=ExportFormat.JSON)
    include_text: bool = Field(default=True)
    include_metadata: bool = Field(default=True)


class ExportJobStatus(BaseModel):
    """Status eines Export-Jobs."""
    job_id: UUID
    status: str
    progress: int = Field(ge=0, le=100)
    total_documents: int
    processed_documents: int
    failed_documents: int
    message: Optional[str] = None
    current_document: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    estimated_completion: Optional[datetime] = None
    is_cancelled: bool = False
    is_paused: bool = False
    result_summary: Optional[dict] = None
    error_message: Optional[str] = None


class ExportJobResponse(BaseModel):
    """Response nach Job-Erstellung."""
    job_id: UUID
    status: str
    message: str
    total_documents: int


class CancelJobResponse(BaseModel):
    """Response nach Job-Abbruch."""
    job_id: UUID
    status: str
    message: str
    cancelled_at: datetime


class ExportJobListResponse(BaseModel):
    """Liste von Export-Jobs."""
    jobs: List[ExportJobStatus]
    total: int


# ==============================================================================
# API Endpoints
# ==============================================================================


# SECURITY FIX 27-6: Rate-Limit fuer Export-Jobs - ressourcenintensiv!
@limiter.limit("10/hour", key_func=get_user_identifier)
@router.post("/jobs", response_model=ExportJobResponse, status_code=202)
async def create_export_job(
    request: Request,  # SECURITY FIX 27-6: Required for rate limiter
    export_request: ExportJobRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Neuen Export-Job starten (asynchron).

    Der Export wird im Hintergrund via Celery verarbeitet.
    Status kann via GET /exports/jobs/{job_id} abgefragt werden.

    Args:
        export_request: Export-Konfiguration

    Returns:
        ExportJobResponse mit Job-ID
    """
    job_id = uuid4()

    # BatchJob erstellen
    batch_job = BatchJob(
        id=job_id,
        user_id=current_user.id,
        job_type="export",
        status=ProcessingStatus.QUEUED,
        priority=5,
        total_documents=len(export_request.document_ids),
        processed_documents=0,
        failed_documents=0,
        document_ids=[str(doc_id) for doc_id in export_request.document_ids],
        progress=0,
        message="Export wird vorbereitet...",
        options={
            "format": export_request.format.value,
            "include_text": export_request.include_text,
            "include_metadata": export_request.include_metadata,
        },
    )

    db.add(batch_job)
    await db.commit()

    # Celery Task starten
    from app.workers.tasks.export_tasks import batch_export_task

    batch_export_task.delay(
        job_id=str(job_id),
        document_ids=[str(doc_id) for doc_id in export_request.document_ids],
        user_id=str(current_user.id),
        format_str=export_request.format.value,
        include_text=export_request.include_text,
        include_metadata=export_request.include_metadata,
    )

    logger.info(
        "export_job_created",
        job_id=str(job_id),
        user_id=str(current_user.id),
        total_documents=len(export_request.document_ids),
        format=export_request.format.value,
    )

    return ExportJobResponse(
        job_id=job_id,
        status="queued",
        message=f"Export-Job erstellt. {len(export_request.document_ids)} Dokument(e) werden verarbeitet.",
        total_documents=len(export_request.document_ids),
    )


@router.get("/jobs/{job_id}", response_model=ExportJobStatus)
async def get_export_job_status(
    job_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Status eines Export-Jobs abfragen.

    Kann fuer Polling verwendet werden.

    Args:
        job_id: BatchJob UUID

    Returns:
        ExportJobStatus
    """
    result = await db.execute(
        select(BatchJob).where(
            BatchJob.id == job_id,
            BatchJob.user_id == current_user.id,
            BatchJob.job_type == "export",
        )
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=404,
            detail="Export-Job nicht gefunden oder keine Berechtigung",
        )

    return ExportJobStatus(
        job_id=job.id,
        status=job.status,
        progress=job.progress or 0,
        total_documents=job.total_documents or 0,
        processed_documents=job.processed_documents or 0,
        failed_documents=job.failed_documents or 0,
        message=job.message,
        current_document=job.current_document,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        estimated_completion=job.estimated_completion,
        is_cancelled=job.is_cancelled or False,
        is_paused=job.is_paused or False,
        result_summary=job.result_summary,
        error_message=job.error_message,
    )


@router.get("/jobs", response_model=ExportJobListResponse)
async def list_export_jobs(
    status: Optional[str] = Query(None, description="Filter nach Status"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Liste aller Export-Jobs des Benutzers.

    Args:
        status: Optional Status-Filter
        limit: Maximale Anzahl
        offset: Offset fuer Pagination

    Returns:
        ExportJobListResponse
    """
    query = select(BatchJob).where(
        BatchJob.user_id == current_user.id,
        BatchJob.job_type == "export",
    )

    if status:
        query = query.where(BatchJob.status == status)

    query = query.order_by(BatchJob.created_at.desc()).limit(limit).offset(offset)

    result = await db.execute(query)
    jobs = result.scalars().all()

    # Count total
    count_query = select(BatchJob.id).where(
        BatchJob.user_id == current_user.id,
        BatchJob.job_type == "export",
    )
    if status:
        count_query = count_query.where(BatchJob.status == status)

    count_result = await db.execute(count_query)
    total = len(count_result.all())

    job_statuses = [
        ExportJobStatus(
            job_id=job.id,
            status=job.status,
            progress=job.progress or 0,
            total_documents=job.total_documents or 0,
            processed_documents=job.processed_documents or 0,
            failed_documents=job.failed_documents or 0,
            message=job.message,
            current_document=job.current_document,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
            estimated_completion=job.estimated_completion,
            is_cancelled=job.is_cancelled or False,
            is_paused=job.is_paused or False,
            result_summary=job.result_summary,
            error_message=job.error_message,
        )
        for job in jobs
    ]

    return ExportJobListResponse(jobs=job_statuses, total=total)


@router.post("/jobs/{job_id}/cancel", response_model=CancelJobResponse)
async def cancel_export_job(
    job_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Export-Job abbrechen.

    Setzt is_cancelled Flag und revoked Celery Task.

    Args:
        job_id: BatchJob UUID

    Returns:
        CancelJobResponse
    """
    result = await db.execute(
        select(BatchJob).where(
            BatchJob.id == job_id,
            BatchJob.user_id == current_user.id,
            BatchJob.job_type == "export",
        )
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=404,
            detail="Export-Job nicht gefunden oder keine Berechtigung",
        )

    # Nur laufende Jobs koennen abgebrochen werden
    if job.status in [ProcessingStatus.COMPLETED, ProcessingStatus.FAILED]:
        raise HTTPException(
            status_code=400,
            detail=f"Job kann nicht abgebrochen werden (Status: {job.status})",
        )

    if job.is_cancelled:
        raise HTTPException(
            status_code=400,
            detail="Job wurde bereits abgebrochen",
        )

    cancelled_at = datetime.now(timezone.utc)

    # Update in database
    await db.execute(
        update(BatchJob)
        .where(BatchJob.id == job_id)
        .values(
            is_cancelled=True,
            status=ProcessingStatus.FAILED,
            error_message="Export wurde abgebrochen",
            completed_at=cancelled_at,
        )
    )
    await db.commit()

    # Revoke Celery task if running
    if job.celery_task_id:
        try:
            from app.workers.celery_app import celery_app
            celery_app.control.revoke(job.celery_task_id, terminate=True)
            logger.info(
                "celery_task_revoked",
                task_id=job.celery_task_id,
                job_id=str(job_id),
            )
        except Exception as e:
            logger.warning(
                "celery_task_revoke_failed",
                task_id=job.celery_task_id,
                error=str(e),
            )

    logger.info(
        "export_job_cancelled",
        job_id=str(job_id),
        user_id=str(current_user.id),
    )

    return CancelJobResponse(
        job_id=job_id,
        status="cancelled",
        message="Export-Job wurde abgebrochen",
        cancelled_at=cancelled_at,
    )


@router.post("/jobs/{job_id}/pause", response_model=ExportJobStatus)
async def pause_export_job(
    job_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Export-Job pausieren.

    Args:
        job_id: BatchJob UUID

    Returns:
        ExportJobStatus
    """
    result = await db.execute(
        select(BatchJob).where(
            BatchJob.id == job_id,
            BatchJob.user_id == current_user.id,
            BatchJob.job_type == "export",
        )
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=404,
            detail="Export-Job nicht gefunden oder keine Berechtigung",
        )

    if job.status != ProcessingStatus.PROCESSING:
        raise HTTPException(
            status_code=400,
            detail=f"Nur laufende Jobs koennen pausiert werden (Status: {job.status})",
        )

    await db.execute(
        update(BatchJob)
        .where(BatchJob.id == job_id)
        .values(
            is_paused=True,
            paused_at=datetime.now(timezone.utc),
        )
    )
    await db.commit()

    logger.info("export_job_paused", job_id=str(job_id))

    # Refresh job
    await db.refresh(job)

    return ExportJobStatus(
        job_id=job.id,
        status=job.status,
        progress=job.progress or 0,
        total_documents=job.total_documents or 0,
        processed_documents=job.processed_documents or 0,
        failed_documents=job.failed_documents or 0,
        message="Job pausiert",
        current_document=job.current_document,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        is_cancelled=False,
        is_paused=True,
    )


@router.post("/jobs/{job_id}/resume", response_model=ExportJobStatus)
async def resume_export_job(
    job_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Pausierten Export-Job fortsetzen.

    Args:
        job_id: BatchJob UUID

    Returns:
        ExportJobStatus
    """
    result = await db.execute(
        select(BatchJob).where(
            BatchJob.id == job_id,
            BatchJob.user_id == current_user.id,
            BatchJob.job_type == "export",
        )
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=404,
            detail="Export-Job nicht gefunden oder keine Berechtigung",
        )

    if not job.is_paused:
        raise HTTPException(
            status_code=400,
            detail="Job ist nicht pausiert",
        )

    await db.execute(
        update(BatchJob)
        .where(BatchJob.id == job_id)
        .values(
            is_paused=False,
            paused_at=None,
        )
    )
    await db.commit()

    # Re-trigger Celery task from resume_from_index
    from app.workers.tasks.export_tasks import batch_export_task

    batch_export_task.delay(
        job_id=str(job_id),
        document_ids=job.document_ids,
        user_id=str(current_user.id),
        format_str=job.options.get("format", "json"),
        include_text=job.options.get("include_text", True),
        include_metadata=job.options.get("include_metadata", True),
    )

    logger.info("export_job_resumed", job_id=str(job_id))

    await db.refresh(job)

    return ExportJobStatus(
        job_id=job.id,
        status=job.status,
        progress=job.progress or 0,
        total_documents=job.total_documents or 0,
        processed_documents=job.processed_documents or 0,
        failed_documents=job.failed_documents or 0,
        message="Job fortgesetzt",
        current_document=job.current_document,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        is_cancelled=False,
        is_paused=False,
    )


# ==============================================================================
# WebSocket Endpoint - Multi-Worker Support via Redis Pub/Sub
# ==============================================================================


class ExportConnectionManager:
    """Manager fuer WebSocket-Verbindungen zu Export-Jobs.

    Verwendet Redis Pub/Sub fuer Multi-Worker Support:
    - Lokale WebSocket-Clients werden direkt informiert
    - Redis Pub/Sub verteilt Updates an alle Worker
    """

    CHANNEL_PREFIX = "export_progress:"

    def __init__(self):
        self.active_connections: dict[str, list[WebSocket]] = {}
        self._pubsub_task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()

    async def connect(self, websocket: WebSocket, job_id: str):
        """WebSocket-Verbindung registrieren."""
        await websocket.accept()
        if job_id not in self.active_connections:
            self.active_connections[job_id] = []
        self.active_connections[job_id].append(websocket)

    def disconnect(self, websocket: WebSocket, job_id: str):
        """WebSocket-Verbindung entfernen."""
        if job_id in self.active_connections:
            if websocket in self.active_connections[job_id]:
                self.active_connections[job_id].remove(websocket)
            if not self.active_connections[job_id]:
                del self.active_connections[job_id]

    async def broadcast_to_job(self, job_id: str, message: dict):
        """Broadcast Message an alle Clients fuer diesen Job.

        1. Sendet direkt an lokale WebSocket-Clients
        2. Publiziert via Redis fuer andere Worker
        """
        # 1. Lokale WebSocket-Clients direkt informieren
        if job_id in self.active_connections:
            disconnected = []
            for connection in self.active_connections[job_id]:
                try:
                    await connection.send_json(message)
                except Exception:
                    disconnected.append(connection)

            # Cleanup disconnected
            for conn in disconnected:
                self.disconnect(conn, job_id)

        # 2. Redis Pub/Sub fuer Multi-Worker Support
        try:
            from app.core.redis_state import get_redis

            redis = await get_redis()
            await redis.publish_event(
                event_type="export.progress",
                data={"job_id": job_id, **message},
                channel=f"{self.CHANNEL_PREFIX}{job_id}"
            )
        except Exception as e:
            logger.warning(
                "redis_pubsub_broadcast_failed",
                job_id=job_id,
                error=str(e),
            )

    async def _handle_redis_message(self, channel: str, data: dict):
        """Handler fuer eingehende Redis Pub/Sub Messages."""
        if data.get("type") == "export.progress":
            payload = data.get("data", {})
            job_id = payload.get("job_id")

            if job_id and job_id in self.active_connections:
                # Nur lokal bekannte Jobs verarbeiten
                # (verhindert Duplikate, da wir selbst auch publizieren)
                message = {k: v for k, v in payload.items() if k != "job_id"}
                for connection in self.active_connections[job_id]:
                    try:
                        await connection.send_json(message)
                    except Exception as e:
                        logger.debug(
                            "websocket_send_failed",
                            error_type=type(e).__name__,
                        )

    async def start_pubsub_listener(self):
        """Startet Redis Pub/Sub Listener fuer diesen Worker."""
        if self._pubsub_task is not None:
            return

        async def listener():
            try:
                from app.core.redis_state import get_redis

                redis = await get_redis()
                await redis.subscribe_to_events(
                    patterns=[f"{self.CHANNEL_PREFIX}*"],
                    callback=self._handle_redis_message,
                    stop_event=self._stop_event,
                )
            except Exception as e:
                logger.error("export_pubsub_listener_error", error=str(e))

        self._pubsub_task = asyncio.create_task(listener())
        logger.info("export_pubsub_listener_started")

    async def stop_pubsub_listener(self):
        """Stoppt Redis Pub/Sub Listener."""
        if self._pubsub_task:
            self._stop_event.set()
            self._pubsub_task.cancel()
            try:
                await self._pubsub_task
            except asyncio.CancelledError:
                pass
            self._pubsub_task = None
            self._stop_event.clear()
            logger.info("export_pubsub_listener_stopped")


export_manager = ExportConnectionManager()


async def _authenticate_websocket_user(token: str) -> tuple[User | None, str | None]:
    """
    Authentifiziert einen WebSocket-User via JWT Token.

    U.2 SECURITY FIX: WebSocket-Authentifizierung hinzugefuegt.

    Args:
        token: JWT Access Token

    Returns:
        Tuple von (User, error_message)
    """
    try:
        secret_key = settings.SECRET_KEY.get_secret_value() if hasattr(settings.SECRET_KEY, 'get_secret_value') else settings.SECRET_KEY
        payload = jwt.decode(
            token,
            secret_key,
            algorithms=[settings.ALGORITHM],
            options={"verify_exp": True, "require_exp": True}
        )
        user_id = payload.get("sub")
        if not user_id:
            return None, "Ungültiger Token"

        async with get_async_session_context() as db:
            user = await db.get(User, UUID(user_id))
            if not user:
                return None, "Benutzer nicht gefunden"
            if not user.is_active:
                return None, "Benutzer deaktiviert"

            return user, None

    except JWTError as e:
        logger.warning("websocket_auth_failed", error=str(e))
        return None, "Token ungültig oder abgelaufen"
    except Exception as e:
        logger.error("websocket_auth_error", error=str(e))
        return None, "Authentifizierungsfehler"


@router.websocket("/jobs/{job_id}/ws")
async def export_job_websocket(
    websocket: WebSocket,
    job_id: UUID,
    token: str = Query(..., description="JWT Access Token"),
):
    """WebSocket fuer Echtzeit-Updates eines Export-Jobs.

    U.2 SECURITY FIX: Authentifizierung + Ownership-Check hinzugefuegt.

    Sendet Progress-Updates als JSON-Objekte.

    Args:
        websocket: WebSocket connection
        job_id: BatchJob UUID
        token: JWT Access Token (Query Parameter)
    """
    # U.2 SECURITY FIX: Authenticate user via JWT token
    user, error = await _authenticate_websocket_user(token)
    if not user:
        await websocket.close(code=4001, reason=error or "Nicht authentifiziert")
        return

    job_id_str = str(job_id)

    # U.2 SECURITY FIX: Verify job exists AND belongs to current user
    async with get_async_session_context() as db:
        result = await db.execute(
            select(BatchJob.id).where(
                BatchJob.id == job_id,
                BatchJob.job_type == "export",
                BatchJob.user_id == user.id,  # U.2 SECURITY FIX: Ownership check!
            )
        )
        job = result.scalar_one_or_none()

    if not job:
        await websocket.close(code=4004, reason="Job nicht gefunden oder kein Zugriff")
        return

    await export_manager.connect(websocket, job_id_str)

    try:
        while True:
            # Receive and ignore client messages (keep-alive)
            try:
                await websocket.receive_text()
            except WebSocketDisconnect:
                break
    finally:
        export_manager.disconnect(websocket, job_id_str)

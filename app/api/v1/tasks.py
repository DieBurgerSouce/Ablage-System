"""Task management API endpoints.

Provides REST API and WebSocket endpoints for:
- Task status monitoring
- Task cancellation
- User task listing
- Real-time progress updates via WebSocket
"""

import asyncio
import structlog
from typing import Optional, List, Dict, Set
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import JSONResponse
# Sprint 0 / G02: PyJWT statt python-jose (CVE-2024-33664).
import jwt
from jwt.exceptions import InvalidTokenError as JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services.task_service import TaskService
from app.db.models import User
from app.db.session import get_async_session_context
from app.api.dependencies import get_current_user, get_current_superuser, get_db
from app.core.german_messages import StatusMessages, HTTPErrors
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/tasks", tags=["tasks"])
task_service = TaskService()


# ==================== WebSocket Authentication ====================

async def _authenticate_websocket_user(token: str) -> tuple[User | None, str | None]:
    """
    Authentifiziert einen WebSocket-User via JWT Token.

    U.3 SECURITY FIX: WebSocket-Authentifizierung hinzugefuegt.

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
        logger.warning("websocket_auth_failed", **safe_error_log(e))
        return None, "Token ungültig oder abgelaufen"
    except Exception as e:
        logger.error("websocket_auth_error", **safe_error_log(e))
        return None, "Authentifizierungsfehler"


# ==================== WebSocket Connection Manager ====================

class ConnectionManager:
    """Manage WebSocket connections for real-time updates.

    Supports multiple connections per task for broadcast capabilities.
    Thread-safe connection management with automatic cleanup.
    """

    def __init__(self):
        """Initialize connection manager."""
        # Multiple connections per task_id for broadcast support
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, task_id: str, websocket: WebSocket) -> bool:
        """Accept and store WebSocket connection.

        Args:
            task_id: Task ID for this connection
            websocket: WebSocket connection

        Returns:
            True if connection was accepted successfully
        """
        try:
            await websocket.accept()
            async with self._lock:
                if task_id not in self.active_connections:
                    self.active_connections[task_id] = set()
                self.active_connections[task_id].add(websocket)
            logger.info("websocket_connected", task_id=task_id, connections=len(self.active_connections.get(task_id, [])))
            return True
        except Exception as e:
            logger.error("websocket_connect_error", task_id=task_id, **safe_error_log(e))
            return False

    async def disconnect(self, task_id: str, websocket: WebSocket):
        """Remove WebSocket connection.

        Args:
            task_id: Task ID to disconnect
            websocket: Specific WebSocket to remove
        """
        async with self._lock:
            if task_id in self.active_connections:
                self.active_connections[task_id].discard(websocket)
                if not self.active_connections[task_id]:
                    del self.active_connections[task_id]
                logger.info("websocket_disconnected", task_id=task_id)

    async def broadcast(self, task_id: str, message: dict):
        """Broadcast update to all connected clients for a task.

        Args:
            task_id: Task ID
            message: Message data to send
        """
        if task_id not in self.active_connections:
            return

        disconnected = set()
        for websocket in self.active_connections.get(task_id, set()).copy():
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.error("websocket_broadcast_error", task_id=task_id, **safe_error_log(e))
                disconnected.add(websocket)

        # Clean up disconnected clients
        for ws in disconnected:
            await self.disconnect(task_id, ws)

    async def send_update(self, task_id: str, websocket: WebSocket, message: dict) -> bool:
        """Send update to a specific connected client.

        Args:
            task_id: Task ID
            websocket: Target WebSocket
            message: Message data to send

        Returns:
            True if message was sent successfully
        """
        try:
            await websocket.send_json(message)
            return True
        except Exception as e:
            logger.error("websocket_send_error", task_id=task_id, **safe_error_log(e))
            await self.disconnect(task_id, websocket)
            return False

    def get_connection_count(self, task_id: str = None) -> int:
        """Get number of active connections.

        Args:
            task_id: Optional specific task ID

        Returns:
            Number of active connections
        """
        if task_id:
            return len(self.active_connections.get(task_id, set()))
        return sum(len(conns) for conns in self.active_connections.values())


manager = ConnectionManager()


# ==================== REST API Endpoints ====================

@router.get(
    "/{task_id}",
    summary="Task-Status abrufen",
    description="Gibt den aktuellen Status eines Tasks zurück. Nur eigene Tasks (Admins können alle sehen).",
)
async def get_task_status(
    task_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """Get current status of a task.

    Y.1 SECURITY FIX: Ownership-Check hinzugefuegt.
    User kann nur eigene Tasks abrufen, Admins können alle sehen.

    Args:
        task_id: Celery task ID
        current_user: Authenticated user
        session: Database session

    Returns:
        Task status information including progress

    Raises:
        403: Access denied if task belongs to another user
    """
    try:
        # Y.1 SECURITY FIX: Verify task ownership (admins bypass)
        if not current_user.is_superuser:
            is_owner = await task_service.verify_task_ownership(session, task_id, current_user.id)
            if not is_owner:
                logger.warning(
                    "task_access_denied_idor_attempt",
                    task_id=task_id,
                    user_id=str(current_user.id),
                )
                raise HTTPException(
                    status_code=403,
                    detail="Zugriff verweigert - Task gehoert einem anderen Benutzer"
                )

        status = task_service.get_task_status(task_id)

        logger.info("task_status_retrieved", task_id=task_id, user_id=str(current_user.id), state=status['state'])

        return status

    except HTTPException:
        raise
    except Exception as e:
        # SECURITY FIX 29: Generic error message - no internal details
        logger.error("task_status_error", task_id=task_id, **safe_error_log(e))
        raise HTTPException(
            status_code=500,
            detail="Verarbeitung fehlgeschlagen. Bitte erneut versuchen."
        )


@router.delete(
    "/{task_id}",
    summary="Task abbrechen",
    description="Bricht einen laufenden Task ab. Nur eigene Tasks (Admins können alle abbrechen).",
)
async def cancel_task(
    task_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """Cancel a running task.

    Y.1 SECURITY FIX: Ownership-Check hinzugefuegt.
    User kann nur eigene Tasks abbrechen, Admins können alle abbrechen.

    Args:
        task_id: Celery task ID
        current_user: Authenticated user
        session: Database session

    Returns:
        Cancellation result

    Raises:
        403: Access denied if task belongs to another user
    """
    try:
        # Y.1 SECURITY FIX: Verify task ownership (admins bypass)
        if not current_user.is_superuser:
            is_owner = await task_service.verify_task_ownership(session, task_id, current_user.id)
            if not is_owner:
                logger.warning(
                    "task_cancel_denied_idor_attempt",
                    task_id=task_id,
                    user_id=str(current_user.id),
                )
                raise HTTPException(
                    status_code=403,
                    detail="Zugriff verweigert - Task gehoert einem anderen Benutzer"
                )

        result = task_service.cancel_task(task_id)

        logger.info("task_cancellation_requested", task_id=task_id, user_id=str(current_user.id), cancelled=result['cancelled'])

        if result["cancelled"]:
            return JSONResponse(
                status_code=200,
                content=result
            )
        else:
            return JSONResponse(
                status_code=400,
                content=result
            )

    except HTTPException:
        raise
    except Exception as e:
        # SECURITY FIX 29: Generic error message - no internal details
        logger.error("task_cancellation_error", task_id=task_id, **safe_error_log(e))
        raise HTTPException(
            status_code=500,
            detail="Verarbeitung fehlgeschlagen. Bitte erneut versuchen."
        )


@router.get(
    "/",
    summary="Benutzer-Tasks auflisten",
    description="Listet die letzten Tasks des aktuellen Benutzers auf.",
)
async def list_user_tasks(
    limit: int = Query(10, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """Get list of user's recent tasks.

    Args:
        limit: Maximum number of tasks to return (1-100)
        current_user: Authenticated user
        session: Database session

    Returns:
        List of task information
    """
    try:
        tasks = await task_service.get_user_tasks(
            session=session,
            user_id=current_user.id,
            limit=limit
        )

        logger.info("user_tasks_listed", user_id=str(current_user.id), task_count=len(tasks))

        return {
            "user_id": str(current_user.id),
            "tasks": tasks,
            "total": len(tasks),
        }

    except Exception as e:
        # SECURITY FIX 29: Generic error message - no internal details
        logger.error("list_tasks_error", user_id=str(current_user.id), **safe_error_log(e))
        raise HTTPException(
            status_code=500,
            detail="Verarbeitung fehlgeschlagen. Bitte erneut versuchen."
        )


@router.get(
    "/{task_id}/result",
    summary="Task-Ergebnis abrufen",
    description="Gibt das Ergebnis eines abgeschlossenen Tasks zurück. Nur eigene Tasks (Admins können alle sehen).",
)
async def get_task_result(
    task_id: str,
    timeout: Optional[float] = Query(None, ge=1, le=300),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """Get task result.

    Y.2 SECURITY FIX: Ownership-Check hinzugefuegt.
    User kann nur eigene Task-Ergebnisse abrufen, Admins können alle sehen.

    Args:
        task_id: Celery task ID
        timeout: Optional timeout in seconds (1-300)
        current_user: Authenticated user
        session: Database session

    Returns:
        Task result if available

    Raises:
        403: Access denied if task belongs to another user
    """
    try:
        # Y.2 SECURITY FIX: Verify task ownership (admins bypass)
        if not current_user.is_superuser:
            is_owner = await task_service.verify_task_ownership(session, task_id, current_user.id)
            if not is_owner:
                logger.warning(
                    "task_result_denied_idor_attempt",
                    task_id=task_id,
                    user_id=str(current_user.id),
                )
                raise HTTPException(
                    status_code=403,
                    detail="Zugriff verweigert - Task gehoert einem anderen Benutzer"
                )

        result = task_service.get_task_result(task_id, timeout=timeout)

        logger.info("task_result_retrieved", task_id=task_id, user_id=str(current_user.id))

        return {
            "task_id": task_id,
            "result": result,
        }

    except HTTPException:
        raise
    except ValueError as e:
        # SECURITY FIX 29: Generic error message - no internal details
        logger.warning("task_result_validation_error", task_id=task_id, **safe_error_log(e))
        raise HTTPException(
            status_code=400,
            detail="Ungültige Anfrage. Bitte Eingaben prüfen."
        )
    except TimeoutError:
        raise HTTPException(
            status_code=408,
            detail=HTTPErrors.PROCESSING_TIMEOUT
        )
    except Exception as e:
        # SECURITY FIX 29: Generic error message - no internal details
        logger.error("task_result_error", task_id=task_id, **safe_error_log(e))
        raise HTTPException(
            status_code=500,
            detail="Verarbeitung fehlgeschlagen. Bitte erneut versuchen."
        )


# ==================== WebSocket Endpoints ====================

@router.websocket("/ws/{task_id}")
async def task_progress_websocket(
    websocket: WebSocket,
    task_id: str,
    token: str = Query(..., description="JWT Access Token"),
):
    """WebSocket endpoint for real-time task progress updates.

    U.3 SECURITY FIX: Authentifizierung hinzugefuegt.

    Provides continuous updates on task progress, state changes, and results.
    Supports multiple simultaneous connections per task.

    Args:
        websocket: WebSocket connection
        task_id: Celery task ID to monitor
        token: JWT Access Token (Query Parameter)

    Message Format:
        {
            "task_id": str,
            "state": str,
            "progress": int (0-100),
            "message": str (German),
            "current": int,
            "total": int,
            "result": dict (if completed),
            "error": str (if failed)
        }
    """
    # U.3 SECURITY FIX: Authenticate user via JWT token
    user, error = await _authenticate_websocket_user(token)
    if not user:
        await websocket.close(code=4001, reason=error or "Nicht authentifiziert")
        return

    logger.info("websocket_authenticated", task_id=task_id, user_id=str(user.id))

    # Accept connection
    if not await manager.connect(task_id, websocket):
        return

    try:
        # Send initial status
        status = task_service.get_task_status(task_id)
        status["message"] = StatusMessages.PROCESSING if status["state"] == "PENDING" else status.get("message", "")
        await manager.send_update(task_id, websocket, status)

        # Continuous monitoring loop
        while True:
            # Get current status
            status = task_service.get_task_status(task_id)

            # Add German status messages
            if status["state"] == "PENDING":
                status["message"] = StatusMessages.QUEUED
            elif status["state"] == "STARTED":
                status["message"] = StatusMessages.PROCESSING

            # Send update
            await manager.send_update(task_id, websocket, status)

            # If task is complete, send final message and close
            if status["ready"]:
                if status["successful"]:
                    final_message = {
                        "task_id": task_id,
                        "state": "SUCCESS",
                        "message": StatusMessages.COMPLETED,
                        "result": status.get("result"),
                    }
                else:
                    final_message = {
                        "task_id": task_id,
                        "state": "FAILURE",
                        "message": StatusMessages.FAILED,
                        "error": status.get("error"),
                    }
                await manager.send_update(task_id, websocket, final_message)
                break

            # Wait before next update (1 second for responsiveness)
            await asyncio.sleep(1)

    except WebSocketDisconnect:
        logger.info("websocket_client_disconnected", task_id=task_id)
    except Exception as e:
        logger.error("websocket_error", task_id=task_id, **safe_error_log(e))
        try:
            await websocket.close(code=1011, reason=str(e))
        except Exception as close_error:
            logger.debug("websocket_close_failed", task_id=task_id, error=str(close_error))
    finally:
        await manager.disconnect(task_id, websocket)


@router.get(
    "/ws/status",
    summary="WebSocket-Verbindungsstatus",
    description="Gibt Statistiken zu aktiven WebSocket-Verbindungen zurück. Nur für Administratoren.",
)
async def get_websocket_status(
    current_user: User = Depends(get_current_superuser),  # X.1 SECURITY FIX: Admin required
):
    """Get WebSocket connection statistics.

    **REQUIRES ADMIN AUTHENTICATION**

    Args:
        current_user: Authenticated admin user (required)

    Returns:
        Connection count and status information
    """
    return {
        "total_connections": manager.get_connection_count(),
        "active_tasks": list(manager.active_connections.keys()),
    }

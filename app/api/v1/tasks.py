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
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.task_service import TaskService
from app.db.models import User
from app.api.dependencies import get_current_user, get_db
from app.core.german_messages import StatusMessages, HTTPErrors

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/tasks", tags=["tasks"])
task_service = TaskService()


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
            logger.error("websocket_connect_error", task_id=task_id, error=str(e))
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
                logger.error("websocket_broadcast_error", task_id=task_id, error=str(e))
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
            logger.error("websocket_send_error", task_id=task_id, error=str(e))
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

@router.get("/{task_id}")
async def get_task_status(
    task_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get current status of a task.

    Args:
        task_id: Celery task ID
        current_user: Authenticated user

    Returns:
        Task status information including progress
    """
    try:
        status = task_service.get_task_status(task_id)

        logger.info("task_status_retrieved", task_id=task_id, user_id=str(current_user.id), state=status['state'])

        return status

    except Exception as e:
        logger.error("task_status_error", task_id=task_id, error=str(e))
        raise HTTPException(
            status_code=500,
            detail=HTTPErrors.PROCESSING_FAILED.format(details=str(e))
        )


@router.delete("/{task_id}")
async def cancel_task(
    task_id: str,
    current_user: User = Depends(get_current_user)
):
    """Cancel a running task.

    Args:
        task_id: Celery task ID
        current_user: Authenticated user

    Returns:
        Cancellation result
    """
    try:
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

    except Exception as e:
        logger.error("task_cancellation_error", task_id=task_id, error=str(e))
        raise HTTPException(
            status_code=500,
            detail=HTTPErrors.PROCESSING_FAILED.format(details=str(e))
        )


@router.get("/")
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
        logger.error("list_tasks_error", user_id=str(current_user.id), error=str(e))
        raise HTTPException(
            status_code=500,
            detail=HTTPErrors.PROCESSING_FAILED.format(details=str(e))
        )


@router.get("/{task_id}/result")
async def get_task_result(
    task_id: str,
    timeout: Optional[float] = Query(None, ge=1, le=300),
    current_user: User = Depends(get_current_user)
):
    """Get task result.

    Args:
        task_id: Celery task ID
        timeout: Optional timeout in seconds (1-300)
        current_user: Authenticated user

    Returns:
        Task result if available
    """
    try:
        result = task_service.get_task_result(task_id, timeout=timeout)

        logger.info("task_result_retrieved", task_id=task_id, user_id=str(current_user.id))

        return {
            "task_id": task_id,
            "result": result,
        }

    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )
    except TimeoutError:
        raise HTTPException(
            status_code=408,
            detail=HTTPErrors.PROCESSING_TIMEOUT
        )
    except Exception as e:
        logger.error("task_result_error", task_id=task_id, error=str(e))
        raise HTTPException(
            status_code=500,
            detail=HTTPErrors.PROCESSING_FAILED.format(details=str(e))
        )


# ==================== WebSocket Endpoints ====================

@router.websocket("/ws/{task_id}")
async def task_progress_websocket(
    websocket: WebSocket,
    task_id: str
):
    """WebSocket endpoint for real-time task progress updates.

    Provides continuous updates on task progress, state changes, and results.
    Supports multiple simultaneous connections per task.

    Args:
        websocket: WebSocket connection
        task_id: Celery task ID to monitor

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
        logger.error("websocket_error", task_id=task_id, error=str(e))
        try:
            await websocket.close(code=1011, reason=str(e))
        except Exception:
            pass
    finally:
        await manager.disconnect(task_id, websocket)


@router.get("/ws/status")
async def get_websocket_status():
    """Get WebSocket connection statistics.

    Returns:
        Connection count and status information
    """
    return {
        "total_connections": manager.get_connection_count(),
        "active_tasks": list(manager.active_connections.keys()),
    }

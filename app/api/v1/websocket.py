"""
WebSocket API Endpoints fuer Echtzeit-Updates.

Bietet WebSocket-Verbindungen fuer:
- Dokument-Updates (Upload, OCR-Progress, Kategorisierung)
- Validation Queue Updates
- Approval Notifications
- Finance/Banking Updates
- System Notifications
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.security import HTTPBearer
import jwt
import structlog

from app.core.config import settings
from app.core.safe_errors import safe_error_log
from app.services.realtime import (

    get_event_broadcaster,
    get_realtime_ws_manager,
    RealtimeEventType,
)

logger = structlog.get_logger(__name__)

router = APIRouter()
security = HTTPBearer(auto_error=False)


async def get_user_from_token(token: str) -> Optional[dict]:
    """
    Validiert JWT Token und extrahiert User-Info.

    Args:
        token: JWT Token

    Returns:
        User-Dictionary mit id, email, company_id oder None bei ungueltigem Token
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return {
            "id": payload.get("sub"),
            "email": payload.get("email"),
            "company_id": payload.get("company_id"),
        }
    except jwt.ExpiredSignatureError:
        logger.warning("websocket_token_expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning("websocket_invalid_token", **safe_error_log(e))
        return None


@router.websocket("/ws/realtime")
async def websocket_realtime_endpoint(
    websocket: WebSocket,
    token: Optional[str] = Query(None, description="JWT Token fuer Authentifizierung"),
):
    """
    WebSocket-Endpoint fuer Echtzeit-Updates.

    ## Verbindung

    URL: `wss://server/api/v1/ws/realtime?token=<JWT_TOKEN>`

    ## Message Format

    Alle Nachrichten sind JSON mit der Struktur:
    ```json
    {
        "type": "event_type",
        "payload": {...},
        "timestamp": "2026-01-18T10:30:00Z"
    }
    ```

    ## Client → Server Messages

    ### Ping
    Heartbeat zum Server:
    ```json
    {"type": "ping"}
    ```
    Antwort: `{"type": "pong", "payload": {"server_time": "..."}}`

    ### Subscribe
    Event-Typen abonnieren:
    ```json
    {
        "type": "subscribe",
        "event_types": ["document.ocr_completed", "validation.item_added"]
    }
    ```
    Antwort: `{"type": "subscribed", "payload": {"event_types": [...]}}`

    ### Unsubscribe
    Event-Typen abbestellen:
    ```json
    {
        "type": "unsubscribe",
        "event_types": ["document.ocr_completed"]
    }
    ```
    Antwort: `{"type": "unsubscribed", "payload": {"event_types": [...]}}`

    ### Get History
    Events seit letzter Verbindung abrufen:
    ```json
    {
        "type": "get_history",
        "since": "2026-01-18T10:00:00Z"
    }
    ```
    Antwort: `{"type": "history", "payload": {"events": [...], "count": 5}}`

    ## Server → Client Messages

    ### Connected
    Bei erfolgreicher Verbindung:
    ```json
    {
        "type": "connected",
        "payload": {
            "user_id": "...",
            "company_id": "...",
            "server_time": "..."
        }
    }
    ```

    ### Event
    Bei eingehenden Events:
    ```json
    {
        "type": "event",
        "payload": {
            "event_type": "document.ocr_completed",
            "payload": {"document_id": "...", "filename": "..."},
            "event_id": "...",
            "timestamp": "...",
            "priority": "normal"
        }
    }
    ```

    ## Event Types

    - `document.uploaded` - Dokument hochgeladen
    - `document.ocr_started` - OCR gestartet
    - `document.ocr_progress` - OCR Fortschritt (0-100%)
    - `document.ocr_completed` - OCR abgeschlossen
    - `document.categorized` - Dokument kategorisiert
    - `validation.item_added` - Neues Item in Validation Queue
    - `validation.item_resolved` - Item aufgeloest
    - `validation.queue_updated` - Queue-Status geaendert
    - `approval.requested` - Genehmigung angefordert
    - `approval.approved` - Genehmigt
    - `approval.rejected` - Abgelehnt
    - `invoice.created` - Rechnung erstellt
    - `invoice.paid` - Rechnung bezahlt
    - `invoice.overdue` - Rechnung ueberfaellig
    - `system.notification` - System-Benachrichtigung
    - `system.error` - Systemfehler
    """
    # Validate token
    if not token:
        await websocket.close(code=4001, reason="Token erforderlich")
        return

    user = await get_user_from_token(token)
    if not user or not user.get("id"):
        await websocket.close(code=4002, reason="Ungueltiges Token")
        return

    user_id = user["id"]
    company_id = user.get("company_id")

    # Get WebSocket manager
    ws_manager = get_realtime_ws_manager()

    # Connect user
    connected = await ws_manager.connect(
        websocket=websocket,
        user_id=user_id,
        company_id=company_id,
    )

    if not connected:
        await websocket.close(code=4003, reason="Verbindung fehlgeschlagen")
        return

    try:
        # Message loop
        while True:
            try:
                data = await websocket.receive_text()
                await ws_manager.handle_message(user_id, data)
            except WebSocketDisconnect:
                break

    except Exception as e:
        logger.error(
            "websocket_error",
            user_id=user_id,
            **safe_error_log(e),
        )
    finally:
        await ws_manager.disconnect(user_id)


@router.get("/ws/stats")
async def get_websocket_stats():
    """
    Gibt Statistiken ueber aktive WebSocket-Verbindungen zurueck.

    Nur fuer Admin-Zwecke.
    """
    ws_manager = get_realtime_ws_manager()
    return ws_manager.get_stats()


@router.get("/ws/event-types")
async def get_event_types():
    """
    Gibt alle verfuegbaren Echtzeit-Event-Typen zurueck.

    Nuetzlich fuer Client-Side Subscribe/Unsubscribe.
    """
    return {
        "event_types": [
            {
                "type": event_type.value,
                "category": event_type.value.split(".")[0],
                "name": event_type.name,
            }
            for event_type in RealtimeEventType
        ],
        "categories": list(set(
            event_type.value.split(".")[0]
            for event_type in RealtimeEventType
        )),
    }


@router.get("/ws/presence/{document_id}")
async def get_document_presence(
    document_id: str,
    token: Optional[str] = Query(None, description="JWT Token fuer Authentifizierung"),
):
    """
    Gibt alle User zurueck die ein Dokument gerade betrachten.

    Args:
        document_id: Dokument ID

    Returns:
        Liste von Usern mit Presence-Informationen
    """
    # Validate token
    if not token:
        raise HTTPException(status_code=401, detail="Token erforderlich")

    user = await get_user_from_token(token)
    if not user or not user.get("id"):
        raise HTTPException(status_code=401, detail="Ungueltiges Token")

    ws_manager = get_realtime_ws_manager()
    viewers = await ws_manager.get_document_viewers(document_id)

    return {
        "document_id": document_id,
        "viewers": viewers,
        "viewer_count": len(viewers),
    }


@router.get("/ws/presence/company/{company_id}")
async def get_company_presence_endpoint(
    company_id: str,
    token: Optional[str] = Query(None, description="JWT Token fuer Authentifizierung"),
):
    """
    Gibt Presence-Informationen aller User einer Company zurueck.

    Args:
        company_id: Company ID

    Returns:
        Liste von User-Presence-Informationen
    """
    # Validate token
    if not token:
        raise HTTPException(status_code=401, detail="Token erforderlich")

    user = await get_user_from_token(token)
    if not user or not user.get("id"):
        raise HTTPException(status_code=401, detail="Ungueltiges Token")

    # Verify user belongs to company
    if user.get("company_id") != company_id:
        raise HTTPException(status_code=403, detail="Zugriff verweigert")

    ws_manager = get_realtime_ws_manager()
    presence = await ws_manager.get_company_presence(company_id)

    return {
        "company_id": company_id,
        "users": presence,
        "online_count": len(presence),
    }


@router.get("/ws/rooms")
async def get_user_rooms(
    token: Optional[str] = Query(None, description="JWT Token fuer Authentifizierung"),
):
    """
    Gibt alle Rooms zurueck in denen der User Mitglied ist.

    Returns:
        Liste von Rooms
    """
    # Validate token
    if not token:
        raise HTTPException(status_code=401, detail="Token erforderlich")

    user = await get_user_from_token(token)
    if not user or not user.get("id"):
        raise HTTPException(status_code=401, detail="Ungueltiges Token")

    user_id = user["id"]
    ws_manager = get_realtime_ws_manager()

    rooms_info = []
    async with ws_manager._lock:
        for room_id, room in ws_manager._rooms.items():
            if user_id in room.members:
                rooms_info.append({
                    "room_id": room_id,
                    "room_type": room.room_type,
                    "member_count": len(room.members),
                    "created_at": room.created_at.isoformat(),
                })

    return {
        "user_id": user_id,
        "rooms": rooms_info,
        "room_count": len(rooms_info),
    }


# Startup/Shutdown Events
async def startup_realtime_services():
    """Startet Realtime Services beim Server-Start."""
    broadcaster = get_event_broadcaster()
    await broadcaster.start()

    ws_manager = get_realtime_ws_manager()
    await ws_manager.start()

    logger.info("Realtime Services gestartet")


async def shutdown_realtime_services():
    """Stoppt Realtime Services beim Server-Stop."""
    ws_manager = get_realtime_ws_manager()
    await ws_manager.stop()

    broadcaster = get_event_broadcaster()
    await broadcaster.stop()

    logger.info("Realtime Services gestoppt")

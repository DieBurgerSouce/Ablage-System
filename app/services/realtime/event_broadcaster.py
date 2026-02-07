"""
Event Broadcaster Service.

Bruecke zwischen Event Bus und WebSocket fuer Echtzeit-Updates.
Filtert Events nach User/Company und broadcastet an verbundene Clients.

Features:
- User-spezifische Event-Filterung
- Company-Isolation (Multi-Tenant)
- Rate Limiting fuer Event-Flooding
- Event-Aggregation fuer High-Volume Events
- Reconnection-Support mit Event-History
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
from uuid import UUID

import structlog

from app.services.events.event_bus import Event, EventBus, EventType, get_event_bus
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


class RealtimeEventType(str, Enum):
    """Echtzeit-Event-Typen fuer Frontend."""

    # Document Events
    DOCUMENT_UPLOADED = "document.uploaded"
    DOCUMENT_OCR_STARTED = "document.ocr_started"
    DOCUMENT_OCR_PROGRESS = "document.ocr_progress"
    DOCUMENT_OCR_COMPLETED = "document.ocr_completed"
    DOCUMENT_CATEGORIZED = "document.categorized"
    DOCUMENT_DELETED = "document.deleted"
    DOCUMENT_UPDATED = "document.updated"

    # Validation Queue Events
    VALIDATION_ITEM_ADDED = "validation.item_added"
    VALIDATION_ITEM_RESOLVED = "validation.item_resolved"
    VALIDATION_QUEUE_UPDATED = "validation.queue_updated"

    # Approval Events
    APPROVAL_REQUESTED = "approval.requested"
    APPROVAL_APPROVED = "approval.approved"
    APPROVAL_REJECTED = "approval.rejected"
    APPROVAL_ESCALATED = "approval.escalated"

    # Finance Events
    INVOICE_CREATED = "invoice.created"
    INVOICE_PAID = "invoice.paid"
    INVOICE_OVERDUE = "invoice.overdue"
    PAYMENT_RECEIVED = "payment.received"
    CASHFLOW_UPDATED = "cashflow.updated"
    BUDGET_ALERT = "budget.alert"

    # Banking Events
    TRANSACTION_IMPORTED = "transaction.imported"
    RECONCILIATION_MATCH = "reconciliation.match"
    DUNNING_ESCALATED = "dunning.escalated"

    # Entity Events
    ENTITY_LINKED = "entity.linked"
    ENTITY_RISK_CHANGED = "entity.risk_changed"

    # System Events
    SYSTEM_NOTIFICATION = "system.notification"
    SYSTEM_ERROR = "system.error"
    SYSTEM_MAINTENANCE = "system.maintenance"

    # User Events
    USER_TASK_ASSIGNED = "user.task_assigned"
    USER_MENTION = "user.mention"

    # Comment/Collaboration Events
    COMMENT_CREATED = "comment.created"
    COMMENT_UPDATED = "comment.updated"
    COMMENT_DELETED = "comment.deleted"
    COMMENT_REPLIED = "comment.replied"
    COMMENT_REACTION = "comment.reaction"

    # Widget Events (Real-time Updates - Phase 4.7)
    WIDGET_UPDATE = "widget.update"
    WIDGET_DATA_CHANGED = "widget.data_changed"
    WIDGET_REFRESH_REQUIRED = "widget.refresh_required"

    # Presence Events
    USER_PRESENCE = "user.presence"
    DOCUMENT_VIEWER_JOINED = "document.viewer_joined"
    DOCUMENT_VIEWER_LEFT = "document.viewer_left"
    CURSOR_MOVED = "cursor.moved"


@dataclass
class RealtimeEvent:
    """Ein Echtzeit-Event fuer WebSocket-Broadcast."""

    event_type: RealtimeEventType
    payload: Dict[str, Any]
    event_id: str
    timestamp: datetime
    target_users: Optional[Set[str]] = None  # None = broadcast to all
    target_company_id: Optional[str] = None
    priority: str = "normal"  # low, normal, high, critical

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary fuer JSON-Serialisierung."""
        return {
            "event_type": self.event_type.value,
            "payload": self.payload,
            "event_id": self.event_id,
            "timestamp": self.timestamp.isoformat(),
            "priority": self.priority,
        }


@dataclass
class RateLimitState:
    """Rate Limit State fuer einen Event-Typ."""

    count: int = 0
    window_start: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    aggregated_events: List[Dict[str, Any]] = field(default_factory=list)


class EventBroadcaster:
    """
    Event Broadcaster - Bruecke zwischen Event Bus und WebSocket.

    Features:
    - Abonniert relevante Events vom Event Bus
    - Filtert nach User/Company
    - Rate Limiting (max N events pro Zeitfenster)
    - Event-Aggregation bei High-Volume
    - Callback-Registration fuer WebSocket Manager
    """

    # Rate Limiting Configuration
    RATE_LIMIT_WINDOW_SECONDS = 5
    RATE_LIMIT_MAX_EVENTS = 20
    AGGREGATION_THRESHOLD = 10

    def __init__(self, event_bus: Optional[EventBus] = None) -> None:
        """
        Initialisiert den Event Broadcaster.

        Args:
            event_bus: Optional Event Bus Instanz. Falls None, wird Singleton verwendet.
        """
        self._event_bus = event_bus or get_event_bus()
        self._callbacks: List[Callable[[RealtimeEvent], asyncio.Future]] = []
        self._rate_limits: Dict[str, RateLimitState] = defaultdict(RateLimitState)
        self._subscribed = False
        self._event_history: List[RealtimeEvent] = []
        self._history_max_size = 100

    async def start(self) -> None:
        """Startet den Event Broadcaster und abonniert Event Bus."""
        if self._subscribed:
            logger.warning("Event Broadcaster laeuft bereits")
            return

        # Abonniere alle relevanten Event-Typen
        self._subscribe_to_events()
        self._subscribed = True
        logger.info("Event Broadcaster gestartet")

    async def stop(self) -> None:
        """Stoppt den Event Broadcaster."""
        self._subscribed = False
        self._callbacks.clear()
        logger.info("Event Broadcaster gestoppt")

    def register_callback(
        self,
        callback: Callable[[RealtimeEvent], asyncio.Future],
    ) -> Callable[[], None]:
        """
        Registriert einen Callback fuer neue Events.

        Args:
            callback: Async-Funktion die bei neuen Events aufgerufen wird

        Returns:
            Unsubscribe-Funktion
        """
        self._callbacks.append(callback)

        def unsubscribe() -> None:
            if callback in self._callbacks:
                self._callbacks.remove(callback)

        return unsubscribe

    def _subscribe_to_events(self) -> None:
        """Abonniert relevante Event-Typen vom Event Bus."""
        # Document Events
        self._event_bus.subscribe_pattern("document.*", self._handle_document_event)

        # Finance Events
        self._event_bus.subscribe_pattern("finance.*", self._handle_finance_event)

        # Property, Vehicle, Insurance, Loan Events
        self._event_bus.subscribe_pattern("property.*", self._handle_kpi_event)
        self._event_bus.subscribe_pattern("vehicle.*", self._handle_kpi_event)
        self._event_bus.subscribe_pattern("insurance.*", self._handle_kpi_event)
        self._event_bus.subscribe_pattern("loan.*", self._handle_kpi_event)
        self._event_bus.subscribe_pattern("investment.*", self._handle_kpi_event)

        # Deadline Events
        self._event_bus.subscribe_pattern("deadline.*", self._handle_deadline_event)

        # System Events
        self._event_bus.subscribe_pattern("system.*", self._handle_system_event)

        # Comment/Collaboration Events
        self._event_bus.subscribe_pattern("comment.*", self._handle_comment_event)

    async def _handle_document_event(self, event: Event) -> None:
        """Verarbeitet Document Events."""
        event_type_mapping = {
            EventType.DOCUMENT_UPLOADED: RealtimeEventType.DOCUMENT_UPLOADED,
            EventType.DOCUMENT_OCR_COMPLETED: RealtimeEventType.DOCUMENT_OCR_COMPLETED,
            EventType.DOCUMENT_CATEGORIZED: RealtimeEventType.DOCUMENT_CATEGORIZED,
            EventType.DOCUMENT_DELETED: RealtimeEventType.DOCUMENT_DELETED,
        }

        realtime_type = event_type_mapping.get(event.event_type)
        if realtime_type:
            await self._broadcast_event(
                event_type=realtime_type,
                payload=event.payload,
                event_id=str(event.event_id),
                user_id=str(event.user_id) if event.user_id else None,
                company_id=event.payload.get("company_id"),
                priority="high" if realtime_type == RealtimeEventType.DOCUMENT_OCR_COMPLETED else "normal",
            )

    async def _handle_finance_event(self, event: Event) -> None:
        """Verarbeitet Finance Events."""
        event_type_mapping = {
            EventType.FINANCE_TRANSACTION_ADDED: RealtimeEventType.TRANSACTION_IMPORTED,
            EventType.FINANCE_ANOMALY_DETECTED: RealtimeEventType.SYSTEM_NOTIFICATION,
            EventType.FINANCE_BUDGET_EXCEEDED: RealtimeEventType.BUDGET_ALERT,
        }

        realtime_type = event_type_mapping.get(event.event_type)
        if realtime_type:
            await self._broadcast_event(
                event_type=realtime_type,
                payload=event.payload,
                event_id=str(event.event_id),
                user_id=str(event.user_id) if event.user_id else None,
                company_id=event.payload.get("company_id"),
                priority="high" if realtime_type == RealtimeEventType.BUDGET_ALERT else "normal",
            )

    async def _handle_kpi_event(self, event: Event) -> None:
        """Verarbeitet KPI-bezogene Events (Property, Vehicle, etc.)."""
        # Diese Events aggregieren wir und senden als Cashflow-Update
        await self._broadcast_event(
            event_type=RealtimeEventType.CASHFLOW_UPDATED,
            payload={
                "source": event.event_type.value,
                "data": event.payload,
            },
            event_id=str(event.event_id),
            user_id=str(event.user_id) if event.user_id else None,
            company_id=event.payload.get("company_id"),
            priority="low",
        )

    async def _handle_deadline_event(self, event: Event) -> None:
        """Verarbeitet Deadline Events."""
        priority = "critical" if event.event_type == EventType.DEADLINE_OVERDUE else "high"

        await self._broadcast_event(
            event_type=RealtimeEventType.SYSTEM_NOTIFICATION,
            payload={
                "notification_type": "deadline",
                "deadline_type": event.event_type.value.split(".")[-1],
                "data": event.payload,
            },
            event_id=str(event.event_id),
            user_id=str(event.user_id) if event.user_id else None,
            company_id=event.payload.get("company_id"),
            priority=priority,
        )

    async def _handle_system_event(self, event: Event) -> None:
        """Verarbeitet System Events."""
        if event.event_type == EventType.SYSTEM_ERROR:
            realtime_type = RealtimeEventType.SYSTEM_ERROR
            priority = "critical"
        else:
            realtime_type = RealtimeEventType.SYSTEM_NOTIFICATION
            priority = "normal"

        await self._broadcast_event(
            event_type=realtime_type,
            payload=event.payload,
            event_id=str(event.event_id),
            user_id=None,  # System events go to all users
            company_id=event.payload.get("company_id"),
            priority=priority,
        )

    async def _handle_comment_event(self, event: Event) -> None:
        """Verarbeitet Comment/Collaboration Events."""
        # Map event type to realtime event type
        event_type_name = event.event_type.value if hasattr(event.event_type, 'value') else str(event.event_type)

        realtime_type_mapping = {
            "comment.created": RealtimeEventType.COMMENT_CREATED,
            "comment.updated": RealtimeEventType.COMMENT_UPDATED,
            "comment.deleted": RealtimeEventType.COMMENT_DELETED,
            "comment.replied": RealtimeEventType.COMMENT_REPLIED,
            "comment.reaction": RealtimeEventType.COMMENT_REACTION,
        }

        realtime_type = realtime_type_mapping.get(event_type_name)
        if not realtime_type:
            # Try to match by pattern
            for pattern, rt_type in realtime_type_mapping.items():
                if pattern in event_type_name:
                    realtime_type = rt_type
                    break

        if realtime_type:
            # Determine target users - include document owner and thread participants
            target_users = set()
            if event.user_id:
                target_users.add(str(event.user_id))

            # Add mentioned users from payload
            mentioned_users = event.payload.get("mentioned_users", [])
            for user_id in mentioned_users:
                target_users.add(str(user_id))

            # Add thread participants if available
            thread_participants = event.payload.get("thread_participants", [])
            for user_id in thread_participants:
                target_users.add(str(user_id))

            await self._broadcast_event(
                event_type=realtime_type,
                payload=event.payload,
                event_id=str(event.event_id),
                user_id=str(event.user_id) if event.user_id else None,
                company_id=event.payload.get("company_id"),
                priority="high" if realtime_type == RealtimeEventType.COMMENT_REPLIED else "normal",
            )

    async def _broadcast_event(
        self,
        event_type: RealtimeEventType,
        payload: Dict[str, Any],
        event_id: str,
        user_id: Optional[str] = None,
        company_id: Optional[str] = None,
        priority: str = "normal",
    ) -> None:
        """
        Broadcastet ein Event an alle registrierten Callbacks.

        Wendet Rate Limiting und Aggregation an.
        """
        # Rate Limiting Check
        rate_key = f"{company_id or 'global'}:{event_type.value}"
        rate_state = self._rate_limits[rate_key]

        now = datetime.now(timezone.utc)
        window_age = (now - rate_state.window_start).total_seconds()

        # Reset window if expired
        if window_age > self.RATE_LIMIT_WINDOW_SECONDS:
            rate_state.count = 0
            rate_state.window_start = now
            rate_state.aggregated_events.clear()

        rate_state.count += 1

        # Check if we need to aggregate
        if rate_state.count > self.RATE_LIMIT_MAX_EVENTS:
            # Aggregate events instead of sending individually
            rate_state.aggregated_events.append(payload)

            if len(rate_state.aggregated_events) >= self.AGGREGATION_THRESHOLD:
                # Send aggregated batch
                await self._send_aggregated_events(
                    event_type=event_type,
                    events=rate_state.aggregated_events,
                    company_id=company_id,
                )
                rate_state.aggregated_events.clear()
            return

        # Create realtime event
        realtime_event = RealtimeEvent(
            event_type=event_type,
            payload=payload,
            event_id=event_id,
            timestamp=now,
            target_users={user_id} if user_id else None,
            target_company_id=company_id,
            priority=priority,
        )

        # Store in history
        self._store_in_history(realtime_event)

        # Send to all callbacks
        await self._dispatch_to_callbacks(realtime_event)

    async def _send_aggregated_events(
        self,
        event_type: RealtimeEventType,
        events: List[Dict[str, Any]],
        company_id: Optional[str] = None,
    ) -> None:
        """Sendet aggregierte Events als Batch."""
        aggregated_event = RealtimeEvent(
            event_type=event_type,
            payload={
                "aggregated": True,
                "count": len(events),
                "events": events[:10],  # Limit payload size
                "total_count": len(events),
            },
            event_id=f"agg-{datetime.now(timezone.utc).timestamp()}",
            timestamp=datetime.now(timezone.utc),
            target_company_id=company_id,
            priority="low",
        )

        await self._dispatch_to_callbacks(aggregated_event)

    async def _dispatch_to_callbacks(self, event: RealtimeEvent) -> None:
        """Sendet Event an alle registrierten Callbacks."""
        for callback in self._callbacks:
            try:
                await callback(event)
            except Exception as e:
                logger.error(
                    "callback_execution_failed",
                    **safe_error_log(e),
                    event_type=event.event_type.value,
                )

    def _store_in_history(self, event: RealtimeEvent) -> None:
        """Speichert Event in der History fuer Reconnection-Support."""
        self._event_history.append(event)
        if len(self._event_history) > self._history_max_size:
            self._event_history = self._event_history[-self._history_max_size:]

    def get_recent_events(
        self,
        since: Optional[datetime] = None,
        event_types: Optional[List[RealtimeEventType]] = None,
        company_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[RealtimeEvent]:
        """
        Holt kuerzliche Events (fuer Reconnection).

        Args:
            since: Nur Events nach diesem Zeitpunkt
            event_types: Optional Filter nach Event-Typen
            company_id: Optional Filter nach Company
            limit: Maximale Anzahl Events

        Returns:
            Liste von Events
        """
        events = self._event_history

        if since:
            events = [e for e in events if e.timestamp > since]

        if event_types:
            events = [e for e in events if e.event_type in event_types]

        if company_id:
            events = [
                e for e in events
                if e.target_company_id is None or e.target_company_id == company_id
            ]

        return events[-limit:]

    # Convenience Methods fuer direkte Event-Emission

    async def emit_document_uploaded(
        self,
        document_id: str,
        filename: str,
        user_id: str,
        company_id: Optional[str] = None,
    ) -> None:
        """Emittiert Document Uploaded Event."""
        await self._broadcast_event(
            event_type=RealtimeEventType.DOCUMENT_UPLOADED,
            payload={
                "document_id": document_id,
                "filename": filename,
            },
            event_id=f"doc-upload-{document_id}",
            user_id=user_id,
            company_id=company_id,
            priority="normal",
        )

    async def emit_ocr_progress(
        self,
        document_id: str,
        progress: int,
        stage: str,
        user_id: str,
        company_id: Optional[str] = None,
    ) -> None:
        """Emittiert OCR Progress Event."""
        await self._broadcast_event(
            event_type=RealtimeEventType.DOCUMENT_OCR_PROGRESS,
            payload={
                "document_id": document_id,
                "progress": progress,
                "stage": stage,
            },
            event_id=f"ocr-progress-{document_id}-{progress}",
            user_id=user_id,
            company_id=company_id,
            priority="normal",
        )

    async def emit_validation_queue_update(
        self,
        queue_id: str,
        action: str,
        item_count: int,
        company_id: Optional[str] = None,
    ) -> None:
        """Emittiert Validation Queue Update Event."""
        await self._broadcast_event(
            event_type=RealtimeEventType.VALIDATION_QUEUE_UPDATED,
            payload={
                "queue_id": queue_id,
                "action": action,
                "item_count": item_count,
            },
            event_id=f"validation-{queue_id}-{action}",
            user_id=None,
            company_id=company_id,
            priority="normal",
        )

    async def emit_approval_status_change(
        self,
        approval_id: str,
        status: str,
        user_id: str,
        company_id: Optional[str] = None,
    ) -> None:
        """Emittiert Approval Status Change Event."""
        event_type_mapping = {
            "requested": RealtimeEventType.APPROVAL_REQUESTED,
            "approved": RealtimeEventType.APPROVAL_APPROVED,
            "rejected": RealtimeEventType.APPROVAL_REJECTED,
            "escalated": RealtimeEventType.APPROVAL_ESCALATED,
        }

        event_type = event_type_mapping.get(status, RealtimeEventType.APPROVAL_REQUESTED)

        await self._broadcast_event(
            event_type=event_type,
            payload={
                "approval_id": approval_id,
                "status": status,
            },
            event_id=f"approval-{approval_id}-{status}",
            user_id=user_id,
            company_id=company_id,
            priority="high",
        )

    async def emit_system_notification(
        self,
        title: str,
        message: str,
        notification_type: str = "info",
        target_users: Optional[Set[str]] = None,
        company_id: Optional[str] = None,
    ) -> None:
        """Emittiert System Notification Event."""
        await self._broadcast_event(
            event_type=RealtimeEventType.SYSTEM_NOTIFICATION,
            payload={
                "title": title,
                "message": message,
                "notification_type": notification_type,
            },
            event_id=f"notification-{datetime.now(timezone.utc).timestamp()}",
            user_id=None,
            company_id=company_id,
            priority="normal" if notification_type != "error" else "high",
        )

    # Comment Event Convenience Methods

    async def emit_comment_created(
        self,
        comment_id: str,
        document_id: str,
        user_id: str,
        content_preview: str,
        parent_id: Optional[str] = None,
        mentioned_users: Optional[List[str]] = None,
        company_id: Optional[str] = None,
    ) -> None:
        """Emittiert Comment Created Event."""
        await self._broadcast_event(
            event_type=RealtimeEventType.COMMENT_CREATED,
            payload={
                "comment_id": comment_id,
                "document_id": document_id,
                "content_preview": content_preview[:100] if content_preview else "",
                "parent_id": parent_id,
                "mentioned_users": mentioned_users or [],
                "is_reply": parent_id is not None,
            },
            event_id=f"comment-created-{comment_id}",
            user_id=user_id,
            company_id=company_id,
            priority="high" if parent_id else "normal",
        )

    async def emit_comment_updated(
        self,
        comment_id: str,
        document_id: str,
        user_id: str,
        company_id: Optional[str] = None,
    ) -> None:
        """Emittiert Comment Updated Event."""
        await self._broadcast_event(
            event_type=RealtimeEventType.COMMENT_UPDATED,
            payload={
                "comment_id": comment_id,
                "document_id": document_id,
            },
            event_id=f"comment-updated-{comment_id}",
            user_id=user_id,
            company_id=company_id,
            priority="normal",
        )

    async def emit_comment_deleted(
        self,
        comment_id: str,
        document_id: str,
        user_id: str,
        company_id: Optional[str] = None,
    ) -> None:
        """Emittiert Comment Deleted Event."""
        await self._broadcast_event(
            event_type=RealtimeEventType.COMMENT_DELETED,
            payload={
                "comment_id": comment_id,
                "document_id": document_id,
            },
            event_id=f"comment-deleted-{comment_id}",
            user_id=user_id,
            company_id=company_id,
            priority="normal",
        )

    async def emit_comment_replied(
        self,
        comment_id: str,
        parent_id: str,
        document_id: str,
        user_id: str,
        content_preview: str,
        thread_participants: Optional[List[str]] = None,
        company_id: Optional[str] = None,
    ) -> None:
        """Emittiert Comment Replied Event (Thread-Antwort)."""
        await self._broadcast_event(
            event_type=RealtimeEventType.COMMENT_REPLIED,
            payload={
                "comment_id": comment_id,
                "parent_id": parent_id,
                "document_id": document_id,
                "content_preview": content_preview[:100] if content_preview else "",
                "thread_participants": thread_participants or [],
            },
            event_id=f"comment-replied-{comment_id}",
            user_id=user_id,
            company_id=company_id,
            priority="high",  # Replies are high priority for notifications
        )

    async def emit_comment_reaction(
        self,
        comment_id: str,
        document_id: str,
        user_id: str,
        reaction: str,
        action: str = "added",  # "added" or "removed"
        company_id: Optional[str] = None,
    ) -> None:
        """Emittiert Comment Reaction Event."""
        await self._broadcast_event(
            event_type=RealtimeEventType.COMMENT_REACTION,
            payload={
                "comment_id": comment_id,
                "document_id": document_id,
                "reaction": reaction,
                "action": action,
            },
            event_id=f"comment-reaction-{comment_id}-{reaction}",
            user_id=user_id,
            company_id=company_id,
            priority="low",
        )

    async def emit_user_mention(
        self,
        mentioned_user_id: str,
        mentioner_user_id: str,
        context_type: str,  # "comment", "document", etc.
        context_id: str,
        content_preview: str,
        company_id: Optional[str] = None,
    ) -> None:
        """Emittiert User Mention Event."""
        await self._broadcast_event(
            event_type=RealtimeEventType.USER_MENTION,
            payload={
                "mentioned_user_id": mentioned_user_id,
                "mentioner_user_id": mentioner_user_id,
                "context_type": context_type,
                "context_id": context_id,
                "content_preview": content_preview[:100] if content_preview else "",
            },
            event_id=f"mention-{context_type}-{context_id}-{mentioned_user_id}",
            user_id=mentioned_user_id,  # Target the mentioned user
            company_id=company_id,
            priority="high",
        )

    # Widget Event Convenience Methods (Phase 4.7)

    async def broadcast_widget_update(
        self,
        widget_type: str,
        update_type: str = "partial",
        data: Optional[Dict[str, Any]] = None,
        changed_fields: Optional[List[str]] = None,
        company_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> None:
        """
        Broadcastet ein Widget-Update Event.

        Args:
            widget_type: Typ des Widgets (cashflow, dunning, etc.)
            update_type: Art des Updates (full, partial, refresh_hint)
            data: Optional Daten fuer das Update
            changed_fields: Liste der geaenderten Felder
            company_id: Optional Company-ID fuer Multi-Tenant
            user_id: Optional User-ID fuer User-spezifische Updates

        Widget Types:
            - cashflow: Cash-Flow Prognose
            - recent_documents: Letzte Dokumente
            - finance_status: Finanz-Uebersicht
            - dunning: Mahnwesen
            - ocr_performance: OCR Leistung
            - aging_report: Faelligkeitsanalyse
            - skonto: Skonto-Tracking
            - system_status: System-Status
            - today: Heute-Widget
            - quick_links: Schnelllinks
            - upload: Upload-Widget
        """
        await self._broadcast_event(
            event_type=RealtimeEventType.WIDGET_UPDATE,
            payload={
                "widget_type": widget_type,
                "update_type": update_type,
                "data": data or {},
                "changed_fields": changed_fields or [],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            event_id=f"widget-update-{widget_type}-{datetime.now(timezone.utc).timestamp()}",
            user_id=user_id,
            company_id=company_id,
            priority="normal",
        )

    async def broadcast_widget_data_changed(
        self,
        widget_type: str,
        source: str,
        data: Optional[Dict[str, Any]] = None,
        company_id: Optional[str] = None,
    ) -> None:
        """
        Signalisiert dass sich die Daten eines Widgets geaendert haben.

        Wird typischerweise von Services gesendet, wenn sich relevante Daten aendern.

        Args:
            widget_type: Typ des Widgets
            source: Quelle der Aenderung (z.B. "invoice.paid", "transaction.imported")
            data: Optional Kontext-Daten
            company_id: Optional Company-ID
        """
        await self._broadcast_event(
            event_type=RealtimeEventType.WIDGET_DATA_CHANGED,
            payload={
                "widget_type": widget_type,
                "update_type": "partial",
                "source": source,
                "data": data or {},
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            event_id=f"widget-data-{widget_type}-{datetime.now(timezone.utc).timestamp()}",
            user_id=None,
            company_id=company_id,
            priority="low",
        )

    async def broadcast_widget_refresh_required(
        self,
        widget_type: str,
        reason: str,
        company_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> None:
        """
        Fordert ein sofortiges Refresh eines Widgets an.

        Wird bei kritischen Aenderungen verwendet, die sofort sichtbar sein muessen.

        Args:
            widget_type: Typ des Widgets
            reason: Grund fuer das Refresh
            company_id: Optional Company-ID
            user_id: Optional User-ID fuer User-spezifische Updates
        """
        await self._broadcast_event(
            event_type=RealtimeEventType.WIDGET_REFRESH_REQUIRED,
            payload={
                "widget_type": widget_type,
                "update_type": "full",
                "reason": reason,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            event_id=f"widget-refresh-{widget_type}-{datetime.now(timezone.utc).timestamp()}",
            user_id=user_id,
            company_id=company_id,
            priority="high",
        )


# Singleton Instance
_broadcaster_instance: Optional[EventBroadcaster] = None


def get_event_broadcaster() -> EventBroadcaster:
    """Factory-Funktion fuer EventBroadcaster Singleton."""
    global _broadcaster_instance
    if _broadcaster_instance is None:
        _broadcaster_instance = EventBroadcaster()
    return _broadcaster_instance


async def reset_event_broadcaster() -> None:
    """Setzt den EventBroadcaster zurueck (fuer Tests)."""
    global _broadcaster_instance
    if _broadcaster_instance:
        await _broadcaster_instance.stop()
        _broadcaster_instance = None

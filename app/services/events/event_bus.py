"""
Event Bus Service.

Redis PubSub-basierter Event Bus fuer interne Kommunikation zwischen Services.
Ermoeglicht Event-Driven Architecture im Ablage-System.

Features:
- Async Event Publishing
- Event Subscription mit Pattern-Matching
- Event History Tracking
- Retry-Mechanismus bei Fehlern
- Metriken-Integration

Events:
- document.ocr_completed
- document.categorized
- document.anomaly_detected
- property.rental_received
- property.costs_updated
- vehicle.fuel_logged
- vehicle.service_completed
- insurance.policy_updated
- insurance.deadline_approaching
- finance.transaction_added
- deadline.approaching
- deadline.overdue
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set
from uuid import UUID, uuid4

import redis.asyncio as redis

from app.core.config import settings

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    """Alle verfuegbaren Event-Typen."""

    # Document Events
    DOCUMENT_OCR_COMPLETED = "document.ocr_completed"
    DOCUMENT_CATEGORIZED = "document.categorized"
    DOCUMENT_ANOMALY_DETECTED = "document.anomaly_detected"
    DOCUMENT_UPLOADED = "document.uploaded"
    DOCUMENT_DELETED = "document.deleted"

    # Property Events
    PROPERTY_RENTAL_RECEIVED = "property.rental_received"
    PROPERTY_COSTS_UPDATED = "property.costs_updated"
    PROPERTY_KPIS_CALCULATED = "property.kpis_calculated"
    PROPERTY_VALUE_UPDATED = "property.value_updated"

    # Vehicle Events
    VEHICLE_FUEL_LOGGED = "vehicle.fuel_logged"
    VEHICLE_SERVICE_COMPLETED = "vehicle.service_completed"
    VEHICLE_KPIS_CALCULATED = "vehicle.kpis_calculated"
    VEHICLE_SERVICE_DUE = "vehicle.service_due"

    # Insurance Events
    INSURANCE_POLICY_UPDATED = "insurance.policy_updated"
    INSURANCE_DEADLINE_APPROACHING = "insurance.deadline_approaching"
    INSURANCE_GAP_DETECTED = "insurance.gap_detected"
    INSURANCE_PREMIUM_DUE = "insurance.premium_due"
    INSURANCE_KPIS_CALCULATED = "insurance.kpis_calculated"

    # Loan Events
    LOAN_KPIS_CALCULATED = "loan.kpis_calculated"
    LOAN_SCENARIO_UPDATED = "loan.scenario_updated"
    LOAN_PAYMENT_DUE = "loan.payment_due"
    LOAN_EXTRA_PAYMENT_APPLIED = "loan.extra_payment_applied"

    # Investment Events
    INVESTMENT_PERFORMANCE_CALCULATED = "investment.performance_calculated"
    INVESTMENT_REBALANCING_NEEDED = "investment.rebalancing_needed"
    INVESTMENT_DIVIDEND_RECEIVED = "investment.dividend_received"
    INVESTMENT_TARGET_REACHED = "investment.target_reached"

    # Finance Events
    FINANCE_TRANSACTION_ADDED = "finance.transaction_added"
    FINANCE_ANOMALY_DETECTED = "finance.anomaly_detected"
    FINANCE_RECURRING_DETECTED = "finance.recurring_detected"
    FINANCE_BUDGET_EXCEEDED = "finance.budget_exceeded"

    # Deadline Events
    DEADLINE_APPROACHING = "deadline.approaching"
    DEADLINE_OVERDUE = "deadline.overdue"
    DEADLINE_COMPLETED = "deadline.completed"

    # System Events
    SYSTEM_KPI_RECALCULATION = "system.kpi_recalculation"
    SYSTEM_BACKUP_COMPLETED = "system.backup_completed"
    SYSTEM_ERROR = "system.error"


@dataclass
class Event:
    """Ein Event im System."""

    event_type: EventType
    payload: Dict[str, Any]
    event_id: UUID = field(default_factory=uuid4)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = "unknown"
    correlation_id: Optional[UUID] = None
    user_id: Optional[UUID] = None
    space_id: Optional[UUID] = None

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert Event zu Dictionary."""
        return {
            "event_id": str(self.event_id),
            "event_type": self.event_type.value,
            "payload": self.payload,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "correlation_id": str(self.correlation_id) if self.correlation_id else None,
            "user_id": str(self.user_id) if self.user_id else None,
            "space_id": str(self.space_id) if self.space_id else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Event":
        """Erstellt Event aus Dictionary."""
        return cls(
            event_id=UUID(data["event_id"]),
            event_type=EventType(data["event_type"]),
            payload=data["payload"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            source=data.get("source", "unknown"),
            correlation_id=UUID(data["correlation_id"]) if data.get("correlation_id") else None,
            user_id=UUID(data["user_id"]) if data.get("user_id") else None,
            space_id=UUID(data["space_id"]) if data.get("space_id") else None,
        )

    def to_json(self) -> str:
        """Serialisiert Event zu JSON."""
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, json_str: str) -> "Event":
        """Deserialisiert Event aus JSON."""
        return cls.from_dict(json.loads(json_str))


# Type alias fuer Event Handler
EventHandler = Callable[[Event], Coroutine[Any, Any, None]]


class EventBus:
    """
    Redis PubSub-basierter Event Bus.

    Ermoeglicht:
    - Publish/Subscribe Pattern
    - Pattern-basiertes Matching (z.B. "document.*")
    - Event History
    - Async Handler Execution
    """

    CHANNEL_PREFIX = "ablage:events:"
    HISTORY_KEY = "ablage:event_history"
    HISTORY_MAX_SIZE = 1000

    def __init__(self, redis_url: Optional[str] = None) -> None:
        """
        Initialisiert den Event Bus.

        Args:
            redis_url: Redis-Verbindungs-URL. Falls None, wird Settings verwendet.
        """
        self._redis_url = redis_url or getattr(settings, "REDIS_URL", "redis://localhost:6379/0")
        self._redis: Optional[redis.Redis] = None
        self._pubsub: Optional[redis.client.PubSub] = None
        self._handlers: Dict[str, List[EventHandler]] = {}
        self._pattern_handlers: Dict[str, List[EventHandler]] = {}
        self._running = False
        self._listener_task: Optional[asyncio.Task] = None
        self._metrics = {
            "events_published": 0,
            "events_received": 0,
            "handlers_executed": 0,
            "handler_errors": 0,
        }

    async def connect(self) -> None:
        """Stellt Verbindung zu Redis her."""
        if self._redis is None:
            self._redis = redis.from_url(self._redis_url, decode_responses=True)
            self._pubsub = self._redis.pubsub()
            logger.info("Event Bus mit Redis verbunden")

    async def disconnect(self) -> None:
        """Trennt Verbindung zu Redis."""
        await self.stop_listening()
        if self._pubsub:
            await self._pubsub.close()
            self._pubsub = None
        if self._redis:
            await self._redis.close()
            self._redis = None
            logger.info("Event Bus Verbindung getrennt")

    def subscribe(
        self,
        event_type: EventType,
        handler: EventHandler,
    ) -> None:
        """
        Registriert einen Handler fuer einen Event-Typ.

        Args:
            event_type: Der Event-Typ, auf den reagiert werden soll
            handler: Async Callback-Funktion
        """
        channel = event_type.value
        if channel not in self._handlers:
            self._handlers[channel] = []
        self._handlers[channel].append(handler)
        logger.debug(f"Handler registriert fuer {channel}")

    def subscribe_pattern(
        self,
        pattern: str,
        handler: EventHandler,
    ) -> None:
        """
        Registriert einen Handler fuer ein Event-Pattern.

        Beispiel: "document.*" matched alle document Events.

        Args:
            pattern: Glob-Pattern (z.B. "document.*", "*.completed")
            handler: Async Callback-Funktion
        """
        if pattern not in self._pattern_handlers:
            self._pattern_handlers[pattern] = []
        self._pattern_handlers[pattern].append(handler)
        logger.debug(f"Pattern-Handler registriert fuer {pattern}")

    def unsubscribe(
        self,
        event_type: EventType,
        handler: EventHandler,
    ) -> bool:
        """
        Entfernt einen Handler.

        Args:
            event_type: Der Event-Typ
            handler: Der zu entfernende Handler

        Returns:
            True wenn Handler entfernt wurde, sonst False
        """
        channel = event_type.value
        if channel in self._handlers and handler in self._handlers[channel]:
            self._handlers[channel].remove(handler)
            return True
        return False

    async def publish(self, event: Event) -> int:
        """
        Publiziert ein Event.

        Args:
            event: Das zu publizierende Event

        Returns:
            Anzahl der Subscriber, die das Event erhalten haben
        """
        await self.connect()

        channel = f"{self.CHANNEL_PREFIX}{event.event_type.value}"
        message = event.to_json()

        # Publish to Redis
        subscriber_count = await self._redis.publish(channel, message)

        # Store in history
        await self._store_event_history(event)

        # Update metrics
        self._metrics["events_published"] += 1

        logger.debug(
            f"Event publiziert: {event.event_type.value} "
            f"(ID: {event.event_id}, Subscribers: {subscriber_count})"
        )

        return subscriber_count

    async def publish_event(
        self,
        event_type: EventType,
        payload: Dict[str, Any],
        source: str = "system",
        user_id: Optional[UUID] = None,
        space_id: Optional[UUID] = None,
        correlation_id: Optional[UUID] = None,
    ) -> Event:
        """
        Convenience-Methode zum Erstellen und Publizieren eines Events.

        Args:
            event_type: Der Event-Typ
            payload: Die Event-Daten
            source: Quelle des Events
            user_id: Optional User-ID
            space_id: Optional Space-ID
            correlation_id: Optional Correlation-ID

        Returns:
            Das publizierte Event
        """
        event = Event(
            event_type=event_type,
            payload=payload,
            source=source,
            user_id=user_id,
            space_id=space_id,
            correlation_id=correlation_id,
        )
        await self.publish(event)
        return event

    async def start_listening(self) -> None:
        """Startet den Event-Listener."""
        if self._running:
            logger.warning("Event Listener laeuft bereits")
            return

        await self.connect()

        # Subscribe to all registered channels
        channels = [f"{self.CHANNEL_PREFIX}*"]
        await self._pubsub.psubscribe(*channels)

        self._running = True
        self._listener_task = asyncio.create_task(self._listen_loop())
        logger.info("Event Listener gestartet")

    async def stop_listening(self) -> None:
        """Stoppt den Event-Listener."""
        self._running = False
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
            self._listener_task = None

        if self._pubsub:
            await self._pubsub.punsubscribe()

        logger.info("Event Listener gestoppt")

    async def _listen_loop(self) -> None:
        """Interne Listener-Loop."""
        while self._running:
            try:
                message = await self._pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=1.0
                )

                if message and message["type"] == "pmessage":
                    await self._handle_message(message)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Fehler im Event Listener: {e}")
                await asyncio.sleep(1)

    async def _handle_message(self, message: Dict[str, Any]) -> None:
        """Verarbeitet eine eingehende Nachricht."""
        try:
            # Extract channel and data
            channel = message["channel"]
            if isinstance(channel, bytes):
                channel = channel.decode("utf-8")

            data = message["data"]
            if isinstance(data, bytes):
                data = data.decode("utf-8")

            # Parse event
            event = Event.from_json(data)

            self._metrics["events_received"] += 1

            # Find matching handlers
            event_type = event.event_type.value
            handlers: List[EventHandler] = []

            # Exact match handlers
            if event_type in self._handlers:
                handlers.extend(self._handlers[event_type])

            # Pattern match handlers
            for pattern, pattern_handlers in self._pattern_handlers.items():
                if self._match_pattern(pattern, event_type):
                    handlers.extend(pattern_handlers)

            # Execute handlers
            for handler in handlers:
                try:
                    await handler(event)
                    self._metrics["handlers_executed"] += 1
                except Exception as e:
                    self._metrics["handler_errors"] += 1
                    logger.error(
                        f"Fehler bei Handler fuer {event_type}: {e}",
                        exc_info=True
                    )

        except Exception as e:
            logger.error(f"Fehler beim Verarbeiten der Nachricht: {e}", exc_info=True)

    def _match_pattern(self, pattern: str, event_type: str) -> bool:
        """
        Prueft ob ein Pattern auf einen Event-Typ matched.

        Unterstuetzt:
        - "*" matched alles
        - "prefix.*" matched alles mit prefix
        - "*.suffix" matched alles mit suffix
        """
        if pattern == "*":
            return True

        if pattern.endswith(".*"):
            prefix = pattern[:-2]
            return event_type.startswith(prefix + ".")

        if pattern.startswith("*."):
            suffix = pattern[2:]
            return event_type.endswith("." + suffix)

        return pattern == event_type

    async def _store_event_history(self, event: Event) -> None:
        """Speichert Event in der History."""
        try:
            await self._redis.lpush(self.HISTORY_KEY, event.to_json())
            await self._redis.ltrim(self.HISTORY_KEY, 0, self.HISTORY_MAX_SIZE - 1)
        except Exception as e:
            logger.warning(f"Fehler beim Speichern der Event History: {e}")

    async def get_event_history(
        self,
        limit: int = 100,
        event_type: Optional[EventType] = None,
    ) -> List[Event]:
        """
        Holt die Event History.

        Args:
            limit: Maximale Anzahl Events
            event_type: Optional Filter nach Event-Typ

        Returns:
            Liste der Events (neueste zuerst)
        """
        await self.connect()

        events_json = await self._redis.lrange(self.HISTORY_KEY, 0, limit - 1)
        events = [Event.from_json(e) for e in events_json]

        if event_type:
            events = [e for e in events if e.event_type == event_type]

        return events

    def get_metrics(self) -> Dict[str, int]:
        """Gibt aktuelle Metriken zurueck."""
        return self._metrics.copy()

    async def clear_history(self) -> int:
        """
        Loescht die Event History.

        Returns:
            Anzahl der geloeschten Events
        """
        await self.connect()
        count = await self._redis.llen(self.HISTORY_KEY)
        await self._redis.delete(self.HISTORY_KEY)
        return count


# Singleton Instance
_event_bus_instance: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """
    Factory-Funktion fuer EventBus Singleton.

    Returns:
        Die globale EventBus-Instanz
    """
    global _event_bus_instance
    if _event_bus_instance is None:
        _event_bus_instance = EventBus()
    return _event_bus_instance


async def reset_event_bus() -> None:
    """Setzt den EventBus zurueck (fuer Tests)."""
    global _event_bus_instance
    if _event_bus_instance:
        await _event_bus_instance.disconnect()
        _event_bus_instance = None

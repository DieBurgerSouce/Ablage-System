"""Event-Sourcing - Hybrid-Ansatz für kritische Geschäftspfade."""

from .event_store import EventStore, StoredEvent
from .event_emitter import emit_domain_event
from .snapshot_service import SnapshotService, SnapshotData
from .projection_service import ProjectionService

__all__ = [
    "EventStore",
    "StoredEvent",
    "emit_domain_event",
    "SnapshotService",
    "SnapshotData",
    "ProjectionService",
]

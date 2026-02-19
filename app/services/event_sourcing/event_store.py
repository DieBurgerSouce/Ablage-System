"""Event Store - Append-Only Event Storage für Event-Sourcing."""

import time

import structlog
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime

from prometheus_client import Counter, Histogram
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func

from app.db.bpmn_models.gobd import AuditChainEventType

logger = structlog.get_logger(__name__)

# =============================================================================
# Prometheus Metriken
# =============================================================================

EVENTS_APPENDED = Counter(
    "event_store_events_appended_total",
    "Gesamtzahl gespeicherter Events",
    ["aggregate_type"],
)
EVENT_APPEND_DURATION = Histogram(
    "event_store_append_duration_seconds",
    "Dauer des Event-Append-Vorgangs",
)
AUDIT_BRIDGE_ERRORS = Counter(
    "event_store_audit_bridge_errors_total",
    "Fehler beim Schreiben in die Audit-Chain",
)

# =============================================================================
# Compliance Bridge: EventStore -> AuditChain
# =============================================================================

COMPLIANCE_EVENT_MAP: Dict[str, AuditChainEventType] = {
    "document_created": AuditChainEventType.DOCUMENT_CREATED,
    "document_archived": AuditChainEventType.DOCUMENT_ARCHIVED,
    "document_deleted": AuditChainEventType.DOCUMENT_DELETED,
    "document_exported": AuditChainEventType.DOCUMENT_EXPORTED,
    "document_modified": AuditChainEventType.DOCUMENT_MODIFIED,
    "document_accessed": AuditChainEventType.DOCUMENT_ACCESSED,
}


@dataclass
class StoredEvent:
    """Gespeichertes Domain Event."""

    event_id: UUID
    aggregate_type: str
    aggregate_id: UUID
    sequence_number: int
    event_type: str
    event_data: Dict[str, Any]
    metadata: Dict[str, Any]
    correlation_id: Optional[UUID]
    causation_id: Optional[UUID]
    user_id: Optional[UUID]
    created_at: datetime


class EventStore:
    """Append-Only Event Store für Domain Events.

    Speichert alle Zustandsänderungen als unveränderliche Events.
    Ermöglicht Event-Replay und Audit-Trail.
    """

    async def append(
        self,
        aggregate_type: str,
        aggregate_id: UUID,
        event_type: str,
        event_data: Dict[str, Any],
        company_id: UUID,
        user_id: Optional[UUID] = None,
        correlation_id: Optional[UUID] = None,
        causation_id: Optional[UUID] = None,
        metadata: Optional[Dict[str, Any]] = None,
        db: Optional[AsyncSession] = None,
    ) -> StoredEvent:
        """Fuegt ein neues Event zum Store hinzu.

        Args:
            aggregate_type: Typ des Aggregats (z.B. "document", "invoice")
            aggregate_id: ID des Aggregats
            event_type: Typ des Events (z.B. "document_created")
            event_data: Event-Daten (JSONB)
            company_id: Mandanten-ID für Multi-Tenant
            user_id: Benutzer der das Event ausgeloest hat
            correlation_id: Korrelations-ID für Event-Ketten
            causation_id: ID des Ursachen-Events
            metadata: Zusätzliche Metadaten
            db: Datenbank-Session

        Returns:
            StoredEvent: Das gespeicherte Event

        Raises:
            ValueError: Bei Validierungsfehlern
        """
        from app.db.models import DomainEvent

        if not db:
            raise ValueError("Datenbank-Session erforderlich")

        start_time = time.monotonic()

        # Validierung der Aggregate-Type Whitelist
        allowed_types = {"document", "invoice", "payment", "entity", "alert", "workflow"}
        if aggregate_type not in allowed_types:
            logger.warning(
                "ungültige_aggregate_type",
                aggregate_type=aggregate_type,
                allowed=list(allowed_types)
            )
            raise ValueError(f"Ungültiger Aggregat-Typ: {aggregate_type}")

        # Nächste Sequenznummer ermitteln
        stmt = select(func.coalesce(func.max(DomainEvent.sequence_number), 0)).where(
            and_(
                DomainEvent.aggregate_type == aggregate_type,
                DomainEvent.aggregate_id == aggregate_id
            )
        )
        result = await db.execute(stmt)
        next_seq = result.scalar() + 1

        # Event erstellen
        event = DomainEvent(
            company_id=company_id,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            sequence_number=next_seq,
            event_type=event_type,
            event_data=event_data,
            metadata=metadata or {},
            correlation_id=correlation_id,
            causation_id=causation_id,
            user_id=user_id,
        )

        db.add(event)
        await db.flush()
        await db.refresh(event)

        # Prometheus Metriken
        duration = time.monotonic() - start_time
        EVENTS_APPENDED.labels(aggregate_type=aggregate_type).inc()
        EVENT_APPEND_DURATION.observe(duration)

        # AuditChain Bridge: Compliance-relevante Events in die Audit-Chain schreiben
        await self._bridge_to_audit_chain(
            db=db,
            company_id=company_id,
            event_type=event_type,
            event_data=event_data,
            user_id=user_id,
            aggregate_id=aggregate_id,
        )

        logger.info(
            "event_appended",
            aggregate_type=aggregate_type,
            event_type=event_type,
            sequence_number=next_seq,
            correlation_id=str(correlation_id) if correlation_id else None,
        )

        return StoredEvent(
            event_id=event.id,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            sequence_number=next_seq,
            event_type=event_type,
            event_data=event_data,
            metadata=metadata or {},
            correlation_id=correlation_id,
            causation_id=causation_id,
            user_id=user_id,
            created_at=event.created_at,
        )

    async def _bridge_to_audit_chain(
        self,
        db: "AsyncSession",
        company_id: UUID,
        event_type: str,
        event_data: Dict[str, Any],
        user_id: Optional[UUID],
        aggregate_id: UUID,
    ) -> None:
        """Schreibt compliance-relevante Events in die GoBD Audit-Chain.

        Non-blocking: Bei Fehler wird nur gewarnt, das Event bleibt gespeichert.
        Nur Events aus COMPLIANCE_EVENT_MAP werden weitergeleitet.
        """
        chain_event_type = COMPLIANCE_EVENT_MAP.get(event_type)
        if chain_event_type is None:
            return

        try:
            from app.services.compliance.audit_chain_service import (
                audit_chain_service,
                ChainEntry,
            )

            entry = ChainEntry(
                event_type=chain_event_type,
                event_data={
                    "source": "event_store",
                    "original_event_type": event_type,
                    **{k: str(v) if isinstance(v, UUID) else v
                       for k, v in event_data.items()
                       if k not in ("password", "token", "secret")},
                },
                document_id=aggregate_id if event_type.startswith("document_") else None,
                user_id=user_id,
            )

            await audit_chain_service.append_entry(db, company_id, entry)

            logger.debug(
                "audit_chain_bridge_success",
                event_type=event_type,
                chain_event_type=chain_event_type.value,
            )
        except Exception as e:
            AUDIT_BRIDGE_ERRORS.inc()
            logger.warning(
                "audit_chain_bridge_error",
                event_type=event_type,
                error_type=type(e).__name__,
                error_msg=str(e)[:200],
            )

    async def get_events(
        self,
        aggregate_type: str,
        aggregate_id: UUID,
        company_id: UUID,
        after_sequence: int = 0,
        db: Optional[AsyncSession] = None,
    ) -> List[StoredEvent]:
        """Holt Events für ein Aggregat nach einer Sequenznummer.

        Args:
            aggregate_type: Typ des Aggregats
            aggregate_id: ID des Aggregats
            company_id: Mandanten-ID für Multi-Tenant Isolation
            after_sequence: Nur Events nach dieser Sequenznummer
            db: Datenbank-Session

        Returns:
            Liste von Events in zeitlicher Reihenfolge
        """
        from app.db.models import DomainEvent

        if not db:
            raise ValueError("Datenbank-Session erforderlich")

        # SECURITY FIX: company_id Filter für Multi-Tenant Isolation
        stmt = (
            select(DomainEvent)
            .where(
                and_(
                    DomainEvent.aggregate_type == aggregate_type,
                    DomainEvent.aggregate_id == aggregate_id,
                    DomainEvent.company_id == company_id,
                    DomainEvent.sequence_number > after_sequence,
                )
            )
            .order_by(DomainEvent.sequence_number)
        )

        result = await db.execute(stmt)
        events = result.scalars().all()

        return [
            StoredEvent(
                event_id=event.id,
                aggregate_type=event.aggregate_type,
                aggregate_id=event.aggregate_id,
                sequence_number=event.sequence_number,
                event_type=event.event_type,
                event_data=event.event_data,
                metadata=event.metadata,
                correlation_id=event.correlation_id,
                causation_id=event.causation_id,
                user_id=event.user_id,
                created_at=event.created_at,
            )
            for event in events
        ]

    async def get_all_events(
        self,
        aggregate_type: str,
        aggregate_id: UUID,
        company_id: UUID,
        db: Optional[AsyncSession] = None,
    ) -> List[StoredEvent]:
        """Holt alle Events für ein Aggregat.

        Args:
            aggregate_type: Typ des Aggregats
            aggregate_id: ID des Aggregats
            company_id: Mandanten-ID für Multi-Tenant Isolation
            db: Datenbank-Session

        Returns:
            Liste aller Events in zeitlicher Reihenfolge
        """
        return await self.get_events(
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            company_id=company_id,
            after_sequence=0,
            db=db,
        )

    async def get_events_by_correlation(
        self,
        correlation_id: UUID,
        company_id: UUID,
        db: Optional[AsyncSession] = None,
    ) -> List[StoredEvent]:
        """Holt alle Events mit einer bestimmten Korrelations-ID.

        Nützlich für Tracing von Event-Ketten.

        Args:
            correlation_id: Korrelations-ID
            company_id: Mandanten-ID für Multi-Tenant Isolation
            db: Datenbank-Session

        Returns:
            Liste von Events mit dieser Korrelations-ID
        """
        from app.db.models import DomainEvent

        if not db:
            raise ValueError("Datenbank-Session erforderlich")

        # SECURITY FIX: company_id Filter für Multi-Tenant Isolation
        stmt = (
            select(DomainEvent)
            .where(
                and_(
                    DomainEvent.correlation_id == correlation_id,
                    DomainEvent.company_id == company_id,
                )
            )
            .order_by(DomainEvent.created_at)
        )

        result = await db.execute(stmt)
        events = result.scalars().all()

        return [
            StoredEvent(
                event_id=event.id,
                aggregate_type=event.aggregate_type,
                aggregate_id=event.aggregate_id,
                sequence_number=event.sequence_number,
                event_type=event.event_type,
                event_data=event.event_data,
                metadata=event.metadata,
                correlation_id=event.correlation_id,
                causation_id=event.causation_id,
                user_id=event.user_id,
                created_at=event.created_at,
            )
            for event in events
        ]

    async def get_event_count(
        self,
        aggregate_type: str,
        aggregate_id: UUID,
        company_id: UUID,
        db: Optional[AsyncSession] = None,
    ) -> int:
        """Zaehlt Events für ein Aggregat.

        Args:
            aggregate_type: Typ des Aggregats
            aggregate_id: ID des Aggregats
            company_id: Mandanten-ID für Multi-Tenant Isolation
            db: Datenbank-Session

        Returns:
            Anzahl der Events
        """
        from app.db.models import DomainEvent

        if not db:
            raise ValueError("Datenbank-Session erforderlich")

        # SECURITY FIX: company_id Filter für Multi-Tenant Isolation
        stmt = select(func.count(DomainEvent.id)).where(
            and_(
                DomainEvent.aggregate_type == aggregate_type,
                DomainEvent.aggregate_id == aggregate_id,
                DomainEvent.company_id == company_id,
            )
        )

        result = await db.execute(stmt)
        return result.scalar() or 0

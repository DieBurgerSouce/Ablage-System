"""Event Store - Append-Only Event Storage für Event-Sourcing."""

import hashlib
import json
import time

import structlog
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime

from prometheus_client import Counter, Histogram
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from sqlalchemy.exc import IntegrityError

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
# SHA-256 Hash-Chain Konstanten
# =============================================================================

GENESIS_PREVIOUS_HASH = "0" * 64  # 64 Nullen als Anfangs-Hash der Kette

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
    event_hash: Optional[str] = None
    previous_hash: Optional[str] = None
    chain_hash: Optional[str] = None


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

        # Nächste Sequenznummer atomar ermitteln (FOR UPDATE verhindert Race Conditions)
        max_retries = 3
        for attempt in range(max_retries):
            try:
                stmt = select(
                    func.coalesce(func.max(DomainEvent.sequence_number), 0)
                ).where(
                    and_(
                        DomainEvent.aggregate_type == aggregate_type,
                        DomainEvent.aggregate_id == aggregate_id
                    )
                ).with_for_update()
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

                # SHA-256 Hash-Chain berechnen
                event_hash = self._calculate_event_hash(
                    event_type=event_type,
                    event_data=event_data,
                    aggregate_type=aggregate_type,
                    aggregate_id=aggregate_id,
                    sequence_number=next_seq,
                )
                previous_chain_hash = await self._get_previous_chain_hash(
                    db=db,
                    aggregate_type=aggregate_type,
                    aggregate_id=aggregate_id,
                    sequence_number=next_seq,
                )
                chain_hash = self._calculate_chain_hash(previous_chain_hash, event_hash)

                event.event_hash = event_hash
                event.previous_hash = previous_chain_hash
                event.chain_hash = chain_hash

                db.add(event)
                await db.flush()
                await db.refresh(event)
                break  # Erfolg - Schleife verlassen

            except IntegrityError:
                if attempt < max_retries - 1:
                    await db.rollback()
                    logger.warning(
                        "event_sequence_conflict_retry",
                        aggregate_type=aggregate_type,
                        aggregate_id=str(aggregate_id),
                        attempt=attempt + 1,
                    )
                    continue
                raise

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
            event_hash=event_hash,
            previous_hash=previous_chain_hash,
            chain_hash=chain_hash,
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
                event_hash=event.event_hash,
                previous_hash=event.previous_hash,
                chain_hash=event.chain_hash,
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
                event_hash=event.event_hash,
                previous_hash=event.previous_hash,
                chain_hash=event.chain_hash,
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

    # =========================================================================
    # SHA-256 Hash-Chain Methoden
    # =========================================================================

    @staticmethod
    def _calculate_event_hash(
        event_type: str,
        event_data: Dict[str, Any],
        aggregate_type: str,
        aggregate_id: UUID,
        sequence_number: int,
    ) -> str:
        """Berechnet SHA-256 Hash des Event-Inhalts (kanonisches JSON)."""
        canonical_data = {
            "aggregate_type": aggregate_type,
            "aggregate_id": str(aggregate_id),
            "sequence_number": sequence_number,
            "event_type": event_type,
            "event_data": event_data,
        }
        canonical_json = json.dumps(
            canonical_data,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        )
        return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

    @staticmethod
    def _calculate_chain_hash(
        previous_hash: str,
        event_hash: str,
    ) -> str:
        """Berechnet den verketteten Hash: SHA-256(previous_hash + event_hash)."""
        combined = previous_hash + event_hash
        return hashlib.sha256(combined.encode("utf-8")).hexdigest()

    async def _get_previous_chain_hash(
        self,
        db: AsyncSession,
        aggregate_type: str,
        aggregate_id: UUID,
        sequence_number: int,
    ) -> str:
        """Holt den chain_hash des vorherigen Events (oder Genesis-Hash)."""
        from app.db.models import DomainEvent

        if sequence_number <= 1:
            return GENESIS_PREVIOUS_HASH

        stmt = select(DomainEvent.chain_hash).where(
            and_(
                DomainEvent.aggregate_type == aggregate_type,
                DomainEvent.aggregate_id == aggregate_id,
                DomainEvent.sequence_number == sequence_number - 1,
            )
        )
        result = await db.execute(stmt)
        prev_hash = result.scalar()
        return prev_hash if prev_hash else GENESIS_PREVIOUS_HASH

    async def verify_chain(
        self,
        aggregate_type: str,
        aggregate_id: UUID,
        company_id: UUID,
        db: AsyncSession,
    ) -> Dict[str, Any]:
        """Verifiziert die Integritaet der Hash-Chain fuer ein Aggregat.

        Returns:
            Dict mit status ("valid"/"broken"/"empty"), total_events,
            verified_events, und optional broken_at_sequence + error_message.
        """
        events = await self.get_all_events(
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            company_id=company_id,
            db=db,
        )

        if not events:
            return {"status": "empty", "total_events": 0, "verified_events": 0}

        verified = 0
        expected_previous = GENESIS_PREVIOUS_HASH

        for event in events:
            if not event.event_hash or not event.chain_hash:
                # Legacy Events ohne Hash-Chain ueberspringen
                verified += 1
                if event.chain_hash:
                    expected_previous = event.chain_hash
                continue

            # event_hash verifizieren
            computed_event_hash = self._calculate_event_hash(
                event_type=event.event_type,
                event_data=event.event_data,
                aggregate_type=event.aggregate_type,
                aggregate_id=event.aggregate_id,
                sequence_number=event.sequence_number,
            )
            if computed_event_hash != event.event_hash:
                return {
                    "status": "broken",
                    "total_events": len(events),
                    "verified_events": verified,
                    "broken_at_sequence": event.sequence_number,
                    "error_message": f"Event-Hash stimmt nicht bei Sequenz {event.sequence_number}",
                }

            # chain_hash verifizieren
            computed_chain_hash = self._calculate_chain_hash(
                expected_previous, computed_event_hash
            )
            if computed_chain_hash != event.chain_hash:
                return {
                    "status": "broken",
                    "total_events": len(events),
                    "verified_events": verified,
                    "broken_at_sequence": event.sequence_number,
                    "error_message": f"Chain-Hash stimmt nicht bei Sequenz {event.sequence_number}",
                }

            verified += 1
            expected_previous = event.chain_hash

        return {
            "status": "valid",
            "total_events": len(events),
            "verified_events": verified,
        }

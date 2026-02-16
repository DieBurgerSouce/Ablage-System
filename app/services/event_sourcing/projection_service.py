"""Projection Service - Event-Replay und Zustandsrekonstruktion."""

import structlog
from typing import Dict, Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from .event_store import EventStore, StoredEvent
from .snapshot_service import SnapshotService

logger = structlog.get_logger(__name__)


class ProjectionService:
    """Service für Event-Replay und Projektion.

    Rekonstruiert den aktuellen Zustand eines Aggregats durch Replay
    aller Events ab dem letzten Snapshot.
    """

    def __init__(self):
        self.event_store = EventStore()
        self.snapshot_service = SnapshotService()

    async def project(
        self,
        aggregate_type: str,
        aggregate_id: UUID,
        company_id: UUID,
        db: AsyncSession = None,
    ) -> Dict[str, Any]:
        """Projiziert den aktuellen Zustand eines Aggregats.

        Args:
            aggregate_type: Typ des Aggregats
            aggregate_id: ID des Aggregats
            company_id: Mandanten-ID für Multi-Tenant Isolation
            db: Datenbank-Session

        Returns:
            Dict mit dem aktuellen Zustand des Aggregats
        """
        if not db:
            raise ValueError("Datenbank-Session erforderlich")

        # Letzten Snapshot holen
        snapshot = await self.snapshot_service.get_latest_snapshot(
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            company_id=company_id,
            db=db,
        )

        # Startzustand ermitteln
        if snapshot:
            state = snapshot.state.copy()
            after_sequence = snapshot.sequence_number
            logger.debug(
                "projection_from_snapshot",
                aggregate_type=aggregate_type,
                snapshot_sequence=after_sequence,
            )
        else:
            state = self._get_initial_state(aggregate_type)
            after_sequence = 0
            logger.debug(
                "projection_from_scratch",
                aggregate_type=aggregate_type,
            )

        # Events nach Snapshot abspielen
        events = await self.event_store.get_events(
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            company_id=company_id,
            after_sequence=after_sequence,
            db=db,
        )

        # Event-Replay
        for event in events:
            state = self._apply_event(state, event)

        logger.info(
            "projection_completed",
            aggregate_type=aggregate_type,
            events_replayed=len(events),
            final_sequence=events[-1].sequence_number if events else after_sequence,
        )

        return state

    def _get_initial_state(self, aggregate_type: str) -> Dict[str, Any]:
        """Gibt den initialen Zustand für einen Aggregat-Typ zurück.

        Args:
            aggregate_type: Typ des Aggregats

        Returns:
            Initialer Zustand als Dict
        """
        initial_states = {
            "document": {
                "status": "pending",
                "metadata": {},
                "processing_history": [],
            },
            "invoice": {
                "status": "open",
                "amount": 0.0,
                "paid_amount": 0.0,
                "payments": [],
            },
            "payment": {
                "status": "pending",
                "amount": 0.0,
                "invoices": [],
            },
            "entity": {
                "type": "customer",
                "metadata": {},
                "documents": [],
            },
            "alert": {
                "status": "new",
                "severity": "low",
                "resolved": False,
            },
            "workflow": {
                "status": "pending",
                "steps": [],
                "current_step": None,
            },
        }

        return initial_states.get(aggregate_type, {})

    def _apply_event(self, state: Dict[str, Any], event: StoredEvent) -> Dict[str, Any]:
        """Wendet ein Event auf den Zustand an.

        Args:
            state: Aktueller Zustand
            event: Anzuwendendes Event

        Returns:
            Neuer Zustand nach Event-Anwendung
        """
        event_type = event.event_type
        event_data = event.event_data

        # Event-Handler basierend auf Event-Typ
        if event_type == "document_created":
            state.update({
                "id": str(event.aggregate_id),
                "filename": event_data.get("filename"),
                "status": "created",
                "created_at": event_data.get("created_at"),
            })

        elif event_type == "document_ocr_started":
            state["status"] = "processing"
            state.setdefault("processing_history", []).append({
                "step": "ocr_started",
                "timestamp": event_data.get("timestamp"),
                "backend": event_data.get("backend"),
            })

        elif event_type == "document_ocr_completed":
            state["status"] = "completed"
            state["ocr_text"] = event_data.get("text")
            state["ocr_confidence"] = event_data.get("confidence")
            state.setdefault("processing_history", []).append({
                "step": "ocr_completed",
                "timestamp": event_data.get("timestamp"),
            })

        elif event_type == "document_ocr_failed":
            state["status"] = "failed"
            state["error"] = event_data.get("error")
            state.setdefault("processing_history", []).append({
                "step": "ocr_failed",
                "timestamp": event_data.get("timestamp"),
                "error": event_data.get("error"),
            })

        elif event_type == "invoice_created":
            state.update({
                "id": str(event.aggregate_id),
                "number": event_data.get("invoice_number"),
                "amount": event_data.get("amount", 0.0),
                "status": "open",
            })

        elif event_type == "invoice_paid":
            state["status"] = "paid"
            state["paid_amount"] = state.get("amount", 0.0)
            state["paid_at"] = event_data.get("paid_at")

        elif event_type == "payment_received":
            payment_amount = event_data.get("amount", 0.0)
            state.setdefault("payments", []).append({
                "amount": payment_amount,
                "received_at": event_data.get("received_at"),
            })
            state["paid_amount"] = state.get("paid_amount", 0.0) + payment_amount

        elif event_type == "alert_created":
            state.update({
                "id": str(event.aggregate_id),
                "category": event_data.get("category"),
                "severity": event_data.get("severity"),
                "status": "new",
                "resolved": False,
            })

        elif event_type == "alert_acknowledged":
            state["status"] = "acknowledged"
            state["acknowledged_by"] = event_data.get("user_id")
            state["acknowledged_at"] = event_data.get("timestamp")

        elif event_type == "alert_resolved":
            state["status"] = "resolved"
            state["resolved"] = True
            state["resolved_by"] = event_data.get("user_id")
            state["resolved_at"] = event_data.get("timestamp")

        elif event_type == "workflow_started":
            state.update({
                "id": str(event.aggregate_id),
                "status": "running",
                "steps": event_data.get("steps", []),
                "current_step": event_data.get("first_step"),
            })

        elif event_type == "workflow_step_completed":
            state["current_step"] = event_data.get("next_step")
            state.setdefault("completed_steps", []).append(
                event_data.get("completed_step")
            )

        elif event_type == "workflow_completed":
            state["status"] = "completed"
            state["current_step"] = None
            state["completed_at"] = event_data.get("completed_at")

        else:
            # Generisches Update für unbekannte Event-Typen
            logger.warning(
                "unknown_event_type_in_projection",
                event_type=event_type,
                aggregate_type=event.aggregate_type,
            )
            state.setdefault("metadata", {}).update(event_data)

        return state

    async def project_at_sequence(
        self,
        aggregate_type: str,
        aggregate_id: UUID,
        target_sequence: int,
        company_id: UUID,
        db: AsyncSession = None,
    ) -> Dict[str, Any]:
        """Projiziert den Zustand bis zu einer bestimmten Sequenznummer.

        Nützlich für Zeitreisen (Temporal Queries).

        Args:
            aggregate_type: Typ des Aggregats
            aggregate_id: ID des Aggregats
            target_sequence: Ziel-Sequenznummer
            company_id: Mandanten-ID für Multi-Tenant Isolation
            db: Datenbank-Session

        Returns:
            Zustand des Aggregats bei der Ziel-Sequenznummer
        """
        if not db:
            raise ValueError("Datenbank-Session erforderlich")

        # Snapshot holen (falls vorhanden und vor Ziel-Sequenz)
        snapshot = await self.snapshot_service.get_latest_snapshot(
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            company_id=company_id,
            db=db,
        )

        if snapshot and snapshot.sequence_number <= target_sequence:
            state = snapshot.state.copy()
            after_sequence = snapshot.sequence_number
        else:
            state = self._get_initial_state(aggregate_type)
            after_sequence = 0

        # Events bis zur Ziel-Sequenz abspielen
        all_events = await self.event_store.get_events(
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            company_id=company_id,
            after_sequence=after_sequence,
            db=db,
        )

        # Nur Events bis zur Ziel-Sequenz
        events = [e for e in all_events if e.sequence_number <= target_sequence]

        for event in events:
            state = self._apply_event(state, event)

        logger.info(
            "temporal_projection_completed",
            aggregate_type=aggregate_type,
            target_sequence=target_sequence,
            events_replayed=len(events),
        )

        return state

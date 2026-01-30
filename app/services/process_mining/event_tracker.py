# -*- coding: utf-8 -*-
"""
Process Event Tracker Service.

Trackt alle Ereignisse im Dokumenten-Lebenszyklus fuer Process Mining.
Unterstuetzt:
- Event-Erfassung mit Timing
- Event-Verkettung (previous_event)
- Automatische Dauer-Berechnung
- Process Instance Tracking

Feinpoliert und durchdacht.
"""

import logging
import time
from app.core.safe_errors import safe_error_detail, safe_error_log
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from uuid import UUID
from contextlib import asynccontextmanager

from sqlalchemy import select, and_, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_process_mining import (
    ProcessEvent,
    EventType,
    ActorType,
)

logger = logging.getLogger(__name__)


class ProcessEventTracker:
    """
    Service fuer die Erfassung von Prozess-Ereignissen.

    Trackt den gesamten Dokumenten-Lebenszyklus:
    Upload → OCR → Klassifikation → Validierung → Freigabe → Archiv
    """

    def __init__(self, db: AsyncSession):
        """
        Initialisiere Tracker.

        Args:
            db: AsyncSession fuer Datenbankzugriff
        """
        self.db = db
        self._timing_context: Dict[str, float] = {}

    async def track_event(
        self,
        company_id: UUID,
        event_type: EventType,
        document_id: Optional[UUID] = None,
        entity_id: Optional[UUID] = None,
        actor_type: ActorType = ActorType.SYSTEM,
        actor_id: Optional[UUID] = None,
        duration_ms: Optional[int] = None,
        success: bool = True,
        error_message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        event_subtype: Optional[str] = None,
        process_instance_id: Optional[str] = None,
        activity_name: Optional[str] = None,
        resource: Optional[str] = None,
    ) -> ProcessEvent:
        """
        Erfasse ein Prozess-Ereignis.

        Args:
            company_id: Mandanten-ID
            event_type: Typ des Ereignisses
            document_id: Optional Dokument-Referenz
            entity_id: Optional Entity-Referenz
            actor_type: Wer hat die Aktion ausgeloest
            actor_id: User-ID wenn manuell
            duration_ms: Dauer der Aktion in ms
            success: War die Aktion erfolgreich
            error_message: Fehlermeldung bei Misserfolg
            metadata: Zusaetzliche Daten
            event_subtype: Untertyp des Events
            process_instance_id: ID der Prozessinstanz (XES)
            activity_name: Name der Aktivitaet (XES)
            resource: Bearbeiter/System (XES)

        Returns:
            Das erstellte ProcessEvent
        """
        # Finde vorheriges Event fuer dieses Dokument
        previous_event = None
        time_since_previous_ms = None

        if document_id:
            previous_event = await self._get_last_event_for_document(
                document_id, company_id
            )
            if previous_event and previous_event.timestamp:
                time_since_previous_ms = int(
                    (datetime.utcnow() - previous_event.timestamp.replace(tzinfo=None))
                    .total_seconds() * 1000
                )

        # Erstelle Event
        event = ProcessEvent(
            company_id=company_id,
            document_id=document_id,
            entity_id=entity_id,
            event_type=event_type.value if isinstance(event_type, EventType) else event_type,
            event_subtype=event_subtype,
            actor_type=actor_type.value if isinstance(actor_type, ActorType) else actor_type,
            actor_id=actor_id,
            duration_ms=duration_ms,
            previous_event_id=previous_event.id if previous_event else None,
            time_since_previous_ms=time_since_previous_ms,
            process_instance_id=process_instance_id or (str(document_id) if document_id else None),
            activity_name=activity_name or event_type.value,
            resource=resource,
            success=success,
            error_message=error_message,
            metadata=metadata or {},
        )

        self.db.add(event)
        await self.db.flush()

        logger.debug(
            f"Process event tracked: {event_type.value if isinstance(event_type, EventType) else event_type} "
            f"for document {document_id}"
        )

        return event

    async def _get_last_event_for_document(
        self,
        document_id: UUID,
        company_id: UUID,
    ) -> Optional[ProcessEvent]:
        """Hole letztes Event fuer ein Dokument."""
        result = await self.db.execute(
            select(ProcessEvent)
            .where(
                and_(
                    ProcessEvent.document_id == document_id,
                    ProcessEvent.company_id == company_id,
                )
            )
            .order_by(desc(ProcessEvent.timestamp))
            .limit(1)
        )
        return result.scalar_one_or_none()

    @asynccontextmanager
    async def timed_event(
        self,
        company_id: UUID,
        event_type: EventType,
        document_id: Optional[UUID] = None,
        entity_id: Optional[UUID] = None,
        actor_type: ActorType = ActorType.SYSTEM,
        actor_id: Optional[UUID] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs,
    ):
        """
        Context Manager fuer automatisches Timing von Events.

        Usage:
            async with tracker.timed_event(company_id, EventType.OCR_STARTED, doc_id):
                # OCR-Verarbeitung
                result = await ocr_service.process(doc)

        Args:
            company_id: Mandanten-ID
            event_type: Typ des Ereignisses
            document_id: Optional Dokument-Referenz
            entity_id: Optional Entity-Referenz
            actor_type: Wer hat die Aktion ausgeloest
            actor_id: User-ID wenn manuell
            metadata: Zusaetzliche Daten
            **kwargs: Weitere Event-Parameter
        """
        start_time = time.perf_counter()
        success = True
        error_message = None

        try:
            yield
        except Exception as e:
            success = False
            error_message = safe_error_detail(e, "Event")  # Limitiere Fehlermeldung
            raise
        finally:
            duration_ms = int((time.perf_counter() - start_time) * 1000)

            await self.track_event(
                company_id=company_id,
                event_type=event_type,
                document_id=document_id,
                entity_id=entity_id,
                actor_type=actor_type,
                actor_id=actor_id,
                duration_ms=duration_ms,
                success=success,
                error_message=error_message,
                metadata=metadata,
                **kwargs,
            )

    async def track_document_upload(
        self,
        company_id: UUID,
        document_id: UUID,
        actor_id: Optional[UUID] = None,
        file_size: Optional[int] = None,
        file_type: Optional[str] = None,
        source: str = "upload",
    ) -> ProcessEvent:
        """Tracke Dokument-Upload."""
        event_type = EventType.DOCUMENT_UPLOADED
        if source == "import":
            event_type = EventType.DOCUMENT_IMPORTED
        elif source == "email":
            event_type = EventType.EMAIL_RECEIVED

        return await self.track_event(
            company_id=company_id,
            event_type=event_type,
            document_id=document_id,
            actor_type=ActorType.USER if actor_id else ActorType.SYSTEM,
            actor_id=actor_id,
            metadata={
                "file_size": file_size,
                "file_type": file_type,
                "source": source,
            },
        )

    async def track_ocr_start(
        self,
        company_id: UUID,
        document_id: UUID,
        backend: str,
    ) -> ProcessEvent:
        """Tracke OCR-Start."""
        return await self.track_event(
            company_id=company_id,
            event_type=EventType.OCR_STARTED,
            document_id=document_id,
            event_subtype=EventType.OCR_BACKEND_SELECTED.value,
            metadata={"backend": backend},
            resource=backend,
        )

    async def track_ocr_completion(
        self,
        company_id: UUID,
        document_id: UUID,
        backend: str,
        duration_ms: int,
        confidence: float,
        page_count: int = 1,
        success: bool = True,
        error_message: Optional[str] = None,
    ) -> ProcessEvent:
        """Tracke OCR-Abschluss."""
        event_type = EventType.OCR_COMPLETED if success else EventType.OCR_FAILED

        return await self.track_event(
            company_id=company_id,
            event_type=event_type,
            document_id=document_id,
            duration_ms=duration_ms,
            success=success,
            error_message=error_message,
            metadata={
                "backend": backend,
                "confidence": confidence,
                "page_count": page_count,
            },
            resource=backend,
        )

    async def track_classification(
        self,
        company_id: UUID,
        document_id: UUID,
        document_type: str,
        confidence: float,
        is_correction: bool = False,
        actor_id: Optional[UUID] = None,
    ) -> ProcessEvent:
        """Tracke Dokument-Klassifikation."""
        if is_correction:
            event_type = EventType.CLASSIFICATION_CORRECTED
            actor_type = ActorType.USER
        else:
            event_type = EventType.CLASSIFICATION_COMPLETED
            actor_type = ActorType.SYSTEM

        return await self.track_event(
            company_id=company_id,
            event_type=event_type,
            document_id=document_id,
            actor_type=actor_type,
            actor_id=actor_id,
            metadata={
                "document_type": document_type,
                "confidence": confidence,
            },
        )

    async def track_validation(
        self,
        company_id: UUID,
        document_id: UUID,
        success: bool,
        validation_type: str = "auto",
        issues: Optional[List[str]] = None,
        actor_id: Optional[UUID] = None,
    ) -> ProcessEvent:
        """Tracke Dokument-Validierung."""
        if validation_type == "manual":
            event_type = EventType.MANUAL_CORRECTION
            actor_type = ActorType.USER
        elif success:
            event_type = EventType.VALIDATION_COMPLETED
            actor_type = ActorType.SYSTEM
        else:
            event_type = EventType.VALIDATION_FAILED
            actor_type = ActorType.SYSTEM

        return await self.track_event(
            company_id=company_id,
            event_type=event_type,
            document_id=document_id,
            actor_type=actor_type,
            actor_id=actor_id,
            success=success,
            metadata={
                "validation_type": validation_type,
                "issues": issues or [],
            },
        )

    async def track_approval(
        self,
        company_id: UUID,
        document_id: UUID,
        approved: bool,
        actor_id: UUID,
        reason: Optional[str] = None,
    ) -> ProcessEvent:
        """Tracke Freigabe-Entscheidung."""
        if approved:
            event_type = EventType.APPROVAL_GRANTED
        else:
            event_type = EventType.APPROVAL_REJECTED

        return await self.track_event(
            company_id=company_id,
            event_type=event_type,
            document_id=document_id,
            actor_type=ActorType.USER,
            actor_id=actor_id,
            metadata={"reason": reason} if reason else {},
        )

    async def track_archive(
        self,
        company_id: UUID,
        document_id: UUID,
        archive_location: Optional[str] = None,
    ) -> ProcessEvent:
        """Tracke Archivierung."""
        return await self.track_event(
            company_id=company_id,
            event_type=EventType.ARCHIVE_COMPLETED,
            document_id=document_id,
            metadata={"location": archive_location} if archive_location else {},
        )

    async def track_entity_link(
        self,
        company_id: UUID,
        document_id: UUID,
        entity_id: UUID,
        confidence: float,
        strategy: str,
        is_unlink: bool = False,
    ) -> ProcessEvent:
        """Tracke Entity-Verknuepfung."""
        event_type = EventType.ENTITY_UNLINKED if is_unlink else EventType.ENTITY_LINKED

        return await self.track_event(
            company_id=company_id,
            event_type=event_type,
            document_id=document_id,
            entity_id=entity_id,
            metadata={
                "confidence": confidence,
                "strategy": strategy,
            },
        )

    async def track_export(
        self,
        company_id: UUID,
        document_id: UUID,
        export_type: str,
        actor_id: Optional[UUID] = None,
    ) -> ProcessEvent:
        """Tracke Dokument-Export."""
        if export_type.lower() == "datev":
            event_type = EventType.EXPORTED_DATEV
        else:
            event_type = EventType.EXPORTED_PDF

        return await self.track_event(
            company_id=company_id,
            event_type=event_type,
            document_id=document_id,
            actor_type=ActorType.USER if actor_id else ActorType.SYSTEM,
            actor_id=actor_id,
            metadata={"export_type": export_type},
        )

    async def get_document_history(
        self,
        document_id: UUID,
        company_id: UUID,
        limit: int = 100,
    ) -> List[ProcessEvent]:
        """
        Hole Event-Historie fuer ein Dokument.

        Args:
            document_id: Dokument-ID
            company_id: Mandanten-ID
            limit: Maximale Anzahl Events

        Returns:
            Liste der Events chronologisch sortiert
        """
        result = await self.db.execute(
            select(ProcessEvent)
            .where(
                and_(
                    ProcessEvent.document_id == document_id,
                    ProcessEvent.company_id == company_id,
                )
            )
            .order_by(ProcessEvent.timestamp)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_process_timeline(
        self,
        document_id: UUID,
        company_id: UUID,
    ) -> Dict[str, Any]:
        """
        Erstelle Timeline-Ansicht fuer ein Dokument.

        Args:
            document_id: Dokument-ID
            company_id: Mandanten-ID

        Returns:
            Timeline mit Events und Dauern
        """
        events = await self.get_document_history(document_id, company_id)

        if not events:
            return {"document_id": str(document_id), "events": [], "total_duration_ms": 0}

        timeline = []
        total_duration_ms = 0

        for i, event in enumerate(events):
            entry = event.to_dict()
            entry["step"] = i + 1

            if event.duration_ms:
                total_duration_ms += event.duration_ms

            timeline.append(entry)

        # Berechne Gesamtdauer von erstem bis letztem Event
        if len(events) >= 2:
            first_ts = events[0].timestamp
            last_ts = events[-1].timestamp
            if first_ts and last_ts:
                total_duration_ms = int(
                    (last_ts.replace(tzinfo=None) - first_ts.replace(tzinfo=None))
                    .total_seconds() * 1000
                )

        return {
            "document_id": str(document_id),
            "events": timeline,
            "event_count": len(timeline),
            "total_duration_ms": total_duration_ms,
            "first_event": events[0].timestamp.isoformat() if events else None,
            "last_event": events[-1].timestamp.isoformat() if events else None,
        }

    async def get_event_statistics(
        self,
        company_id: UUID,
        days: int = 30,
    ) -> Dict[str, Any]:
        """
        Berechne Event-Statistiken.

        Args:
            company_id: Mandanten-ID
            days: Anzahl Tage zurueck

        Returns:
            Statistiken ueber Events
        """
        since = datetime.utcnow() - timedelta(days=days)

        # Gesamtzahl Events
        total_result = await self.db.execute(
            select(func.count(ProcessEvent.id))
            .where(
                and_(
                    ProcessEvent.company_id == company_id,
                    ProcessEvent.timestamp >= since,
                )
            )
        )
        total_count = total_result.scalar() or 0

        # Events nach Typ
        type_result = await self.db.execute(
            select(
                ProcessEvent.event_type,
                func.count(ProcessEvent.id).label("count"),
            )
            .where(
                and_(
                    ProcessEvent.company_id == company_id,
                    ProcessEvent.timestamp >= since,
                )
            )
            .group_by(ProcessEvent.event_type)
        )
        events_by_type = {row.event_type: row.count for row in type_result}

        # Events nach Actor-Typ
        actor_result = await self.db.execute(
            select(
                ProcessEvent.actor_type,
                func.count(ProcessEvent.id).label("count"),
            )
            .where(
                and_(
                    ProcessEvent.company_id == company_id,
                    ProcessEvent.timestamp >= since,
                )
            )
            .group_by(ProcessEvent.actor_type)
        )
        events_by_actor = {row.actor_type: row.count for row in actor_result}

        # Erfolgsrate
        success_result = await self.db.execute(
            select(
                func.count(ProcessEvent.id).filter(ProcessEvent.success == True).label("success"),
                func.count(ProcessEvent.id).filter(ProcessEvent.success == False).label("failure"),
            )
            .where(
                and_(
                    ProcessEvent.company_id == company_id,
                    ProcessEvent.timestamp >= since,
                )
            )
        )
        success_row = success_result.one()
        success_count = success_row.success or 0
        failure_count = success_row.failure or 0
        success_rate = success_count / total_count if total_count > 0 else 0

        # Durchschnittliche Dauer
        duration_result = await self.db.execute(
            select(
                func.avg(ProcessEvent.duration_ms).label("avg"),
                func.min(ProcessEvent.duration_ms).label("min"),
                func.max(ProcessEvent.duration_ms).label("max"),
            )
            .where(
                and_(
                    ProcessEvent.company_id == company_id,
                    ProcessEvent.timestamp >= since,
                    ProcessEvent.duration_ms.isnot(None),
                )
            )
        )
        duration_row = duration_result.one()

        return {
            "period_days": days,
            "total_events": total_count,
            "events_by_type": events_by_type,
            "events_by_actor": events_by_actor,
            "success_count": success_count,
            "failure_count": failure_count,
            "success_rate": round(success_rate, 4),
            "avg_duration_ms": int(duration_row.avg) if duration_row.avg else None,
            "min_duration_ms": duration_row.min,
            "max_duration_ms": duration_row.max,
        }

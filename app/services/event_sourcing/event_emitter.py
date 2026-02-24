"""Event Emitter - Non-blocking Wrapper um EventStore.append().

Stellt eine einfache Schnittstelle fuer Services bereit,
um Domain Events zu emittieren, ohne sich um Fehlerbehandlung
oder EventStore-Details kuemmern zu muessen.

Non-blocking: Bei Fehler wird gewarnt, aber der aufrufende Service
wird nicht unterbrochen.
"""

import structlog
from typing import Dict, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.event_sourcing.event_store import EventStore

logger = structlog.get_logger(__name__)

# Module-level singleton
_event_store = EventStore()


async def emit_domain_event(
    db: AsyncSession,
    aggregate_type: str,
    aggregate_id: UUID,
    event_type: str,
    event_data: Dict[str, object],
    company_id: UUID,
    user_id: Optional[UUID] = None,
    correlation_id: Optional[UUID] = None,
) -> None:
    """Emittiert ein Domain Event (non-blocking).

    Bei Fehler wird nur eine Warnung geloggt, der aufrufende
    Service wird nicht unterbrochen.

    Args:
        db: Aktive Datenbank-Session
        aggregate_type: Typ des Aggregats (document, invoice, payment, entity)
        aggregate_id: ID des Aggregats
        event_type: Typ des Events (z.B. document_created)
        event_data: Event-Daten als Dict
        company_id: Mandanten-ID
        user_id: Optional - ID des ausloesenden Users
        correlation_id: Optional - Korrelations-ID fuer Event-Ketten
    """
    try:
        await _event_store.append(
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            event_type=event_type,
            event_data=event_data,
            company_id=company_id,
            user_id=user_id,
            correlation_id=correlation_id,
            db=db,
        )
        # EventStore.append() macht nur flush(), daher explizit committen
        await db.commit()
        logger.debug(
            "domain_event_emitted",
            aggregate_type=aggregate_type,
            event_type=event_type,
        )
    except Exception as e:
        logger.warning(
            "domain_event_emission_failed",
            aggregate_type=aggregate_type,
            event_type=event_type,
            error_type=type(e).__name__,
            error_msg=str(e)[:200],
        )

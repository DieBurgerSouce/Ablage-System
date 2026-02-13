"""
Document Timeline API Endpoints.

Provides complete document lifecycle tracking:
- Upload -> OCR -> Correction -> Categorization -> Entity Linking -> Approval -> Archive

Shows all events for a specific document in chronological order.
"""

from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db, get_current_user, verify_document_ownership
from app.db.models import User
from app.services.document_timeline_service import get_document_timeline_service

router = APIRouter(prefix="/documents", tags=["Document Timeline"])


# ==================== Schemas ====================

class TimelineEvent(BaseModel):
    """Timeline Event."""
    event_type: str
    timestamp: Optional[str]
    user_id: Optional[str] = None
    details: Dict[str, Any]
    description: str


class TimelineResponse(BaseModel):
    """Timeline Response."""
    document_id: str
    events: List[TimelineEvent]
    total_events: int


# ==================== Endpoints ====================

@router.get(
    "/{document_id}/timeline",
    response_model=TimelineResponse,
    summary="Dokument-Timeline",
    description="Liefert vollständige Timeline eines Dokuments"
)
async def get_document_timeline(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TimelineResponse:
    """
    Liefert vollständige Timeline eines Dokuments.

    **Timeline-Events:**
    - **upload**: Dokument hochgeladen
    - **ocr_start**: OCR gestartet
    - **ocr_complete**: OCR erfolgreich abgeschlossen
    - **ocr_failed**: OCR fehlgeschlagen
    - **correction**: Benutzer-Korrektur
    - **categorization**: Automatische Kategorisierung
    - **entity_linked**: Geschäftspartner verknüpft
    - **approval**: Dokument genehmigt
    - **rejection**: Dokument abgelehnt
    - **export**: Dokument exportiert
    - **share**: Dokument geteilt
    - **version_create**: Neue Version erstellt
    - **archive**: Dokument archiviert (GoBD)
    - **delete**: Dokument gelöscht (GDPR)

    **Nutzung:**
    - Vollständiger Audit-Trail
    - GDPR Art. 30 compliant
    - Nachvollziehbarkeit aller Änderungen

    **Beispiel Timeline:**
    1. 2026-01-15 10:00 - Upload: rechnung.pdf
    2. 2026-01-15 10:01 - OCR gestartet mit DeepSeek
    3. 2026-01-15 10:03 - OCR abgeschlossen (94.5% Konfidenz)
    4. 2026-01-15 10:05 - Korrektur: Betrag von 1.234,56 auf 1.234,65
    5. 2026-01-15 10:10 - Kategorisiert als: invoice
    6. 2026-01-15 10:15 - Geschäftspartner verknüpft
    7. 2026-01-15 11:00 - Dokument genehmigt
    """
    if not current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Keine Company-Zuordnung gefunden"
        )

    # Verify ownership (checks company_id isolation)
    await verify_document_ownership(document_id, current_user, db)

    service = get_document_timeline_service(db)
    timeline = await service.get_document_timeline(document_id, current_user.company_id)

    return TimelineResponse(
        document_id=str(document_id),
        events=[TimelineEvent(**event) for event in timeline],
        total_events=len(timeline),
    )

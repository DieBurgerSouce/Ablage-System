"""
API Endpoints fuer One-Click-Validierung.

Schnelle Entscheidungs-Queue fuer mobile und Desktop-Nutzung.
Optimiert fuer Swipe-UI und Keyboard-Shortcuts.
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db, get_current_user
from app.db.models import User
from app.services.oneclick_validation_service import (
    OneClickValidationService,
    OneClickItem,
    OneClickDecision,
    OneClickActionType,
    KeyboardShortcuts,
    get_oneclick_validation_service,
)
import structlog

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/oneclick", tags=["oneclick"])


# ============================================================================
# Pydantic Schemas
# ============================================================================


class OneClickItemResponse(BaseModel):
    """Response fuer ein One-Click-Item."""

    id: UUID
    action_type: str
    priority: int
    created_at: datetime

    title: str
    subtitle: str
    description: str
    question: str

    primary_action_label: str
    secondary_action_label: str
    skip_label: str

    document_id: Optional[UUID] = None
    entity_id: Optional[UUID] = None
    invoice_id: Optional[UUID] = None

    confidence: Optional[float] = None
    confidence_reason: Optional[str] = None
    metadata: Optional[dict] = None


class OneClickDecisionRequest(BaseModel):
    """Request fuer eine Entscheidung."""

    item_id: UUID
    decision: str = Field(..., pattern="^(approve|reject|skip)$")
    notes: Optional[str] = None
    corrected_value: Optional[str] = None
    decision_time_ms: Optional[int] = Field(None, ge=0)


class BatchDecisionRequest(BaseModel):
    """Request fuer Batch-Entscheidungen."""

    decisions: List[OneClickDecisionRequest]


class DecisionResponse(BaseModel):
    """Response fuer eine Entscheidung."""

    success: bool
    item_id: str
    decision: Optional[str] = None
    item_type: Optional[str] = None
    error: Optional[str] = None


class BatchDecisionResponse(BaseModel):
    """Response fuer Batch-Entscheidungen."""

    success_count: int
    error_count: int
    total: int
    results: List[DecisionResponse]


class QueueStatsResponse(BaseModel):
    """Response fuer Queue-Statistiken."""

    total_pending: int
    by_type: dict
    avg_decision_time_ms: float
    decisions_today: int
    approval_rate: float


class ShortcutsResponse(BaseModel):
    """Response fuer Keyboard-Shortcuts."""

    shortcuts: dict


# ============================================================================
# Endpoints
# ============================================================================


@router.get("/queue", response_model=List[OneClickItemResponse])
async def get_validation_queue(
    action_types: Optional[str] = Query(
        None,
        description="Komma-separierte Liste von Aktionstypen (invoice_approval,filing_suggestion,etc.)"
    ),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Holt die naechsten Items zur One-Click-Validierung.

    Optimiert fuer schnelle Entscheidungen:
    - Sortiert nach Prioritaet
    - Vorformatierte Fragen und Labels
    - Confidence-Scores fuer KI-Vorschlaege
    """
    service = await get_oneclick_validation_service(db, current_user.id)

    # Aktionstypen parsen
    types_filter = None
    if action_types:
        try:
            types_filter = [
                OneClickActionType(t.strip())
                for t in action_types.split(",")
                if t.strip()
            ]
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Ungueltiger Aktionstyp: {e}"
            )

    items = await service.get_next_items(action_types=types_filter, limit=limit)

    return [
        OneClickItemResponse(
            id=item.id,
            action_type=item.action_type.value,
            priority=item.priority,
            created_at=item.created_at,
            title=item.title,
            subtitle=item.subtitle,
            description=item.description,
            question=item.question,
            primary_action_label=item.primary_action_label,
            secondary_action_label=item.secondary_action_label,
            skip_label=item.skip_label,
            document_id=item.document_id,
            entity_id=item.entity_id,
            invoice_id=item.invoice_id,
            confidence=item.confidence,
            confidence_reason=item.confidence_reason,
            metadata=item.metadata,
        )
        for item in items
    ]


@router.post("/decide", response_model=DecisionResponse)
async def process_decision(
    request: OneClickDecisionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Verarbeitet eine einzelne Entscheidung.

    Entscheidungs-Optionen:
    - approve: Freigeben/Genehmigen
    - reject: Ablehnen
    - skip: Ueberspringen (fuer spaeter)
    """
    service = await get_oneclick_validation_service(db, current_user.id)

    decision = OneClickDecision(
        item_id=request.item_id,
        decision=request.decision,
        notes=request.notes,
        corrected_value=request.corrected_value,
        decision_time_ms=request.decision_time_ms,
    )

    result = await service.process_decision(decision)

    return DecisionResponse(
        success=result.get("success", False),
        item_id=result.get("item_id", str(request.item_id)),
        decision=result.get("decision"),
        item_type=result.get("item_type"),
        error=result.get("error"),
    )


@router.post("/decide/batch", response_model=BatchDecisionResponse)
async def process_batch_decisions(
    request: BatchDecisionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Verarbeitet mehrere Entscheidungen gleichzeitig.

    Optimiert fuer Batch-Genehmigungen wie:
    - "Alle sichtbaren genehmigen" (Ctrl+Enter)
    - "Alle mit Confidence > 95% genehmigen"
    """
    service = await get_oneclick_validation_service(db, current_user.id)

    decisions = [
        OneClickDecision(
            item_id=d.item_id,
            decision=d.decision,
            notes=d.notes,
            corrected_value=d.corrected_value,
            decision_time_ms=d.decision_time_ms,
        )
        for d in request.decisions
    ]

    result = await service.process_batch_decisions(decisions)

    return BatchDecisionResponse(
        success_count=result.get("success_count", 0),
        error_count=result.get("error_count", 0),
        total=result.get("total", len(decisions)),
        results=[
            DecisionResponse(
                success=r.get("success", False),
                item_id=r.get("item_id", ""),
                decision=r.get("decision"),
                item_type=r.get("item_type"),
                error=r.get("error"),
            )
            for r in result.get("results", [])
        ],
    )


@router.get("/stats", response_model=QueueStatsResponse)
async def get_queue_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Holt Statistiken zur Validierungs-Queue.

    Enthaelt:
    - Anzahl offener Items
    - Aufschluesselung nach Typ
    - Durchschnittliche Entscheidungszeit
    - Heutige Entscheidungen
    - Genehmigungsrate
    """
    service = await get_oneclick_validation_service(db, current_user.id)
    stats = await service.get_queue_stats()

    return QueueStatsResponse(
        total_pending=stats.total_pending,
        by_type=stats.by_type,
        avg_decision_time_ms=stats.avg_decision_time_ms,
        decisions_today=stats.decisions_today,
        approval_rate=stats.approval_rate,
    )


@router.get("/shortcuts", response_model=ShortcutsResponse)
async def get_keyboard_shortcuts(
    current_user: User = Depends(get_current_user),
):
    """Gibt alle verfuegbaren Keyboard-Shortcuts zurueck.

    Fuer Desktop-Integration:
    - Y/Enter: Genehmigen
    - N/Backspace: Ablehnen
    - Space/Tab: Ueberspringen
    - Ctrl+Enter: Batch-Genehmigung
    """
    return ShortcutsResponse(shortcuts=KeyboardShortcuts.get_shortcut_map())


@router.get("/action-types")
async def get_action_types(
    current_user: User = Depends(get_current_user),
):
    """Gibt alle verfuegbaren Aktionstypen zurueck."""
    return {
        "action_types": [
            {
                "value": action_type.value,
                "label": {
                    OneClickActionType.INVOICE_APPROVAL: "Rechnungsfreigabe",
                    OneClickActionType.FILING_SUGGESTION: "Ablagevorschlag",
                    OneClickActionType.DUPLICATE_MERGE: "Duplikat-Zusammenfuehrung",
                    OneClickActionType.MASTER_DATA_UPDATE: "Stammdaten-Korrektur",
                    OneClickActionType.OCR_CORRECTION: "OCR-Korrektur",
                    OneClickActionType.ENTITY_ASSIGNMENT: "Entity-Zuweisung",
                }.get(action_type, action_type.value),
            }
            for action_type in OneClickActionType
        ]
    }


@router.post("/swipe")
async def process_swipe(
    item_id: UUID,
    direction: str = Query(..., pattern="^(left|right|up|down)$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Verarbeitet eine Swipe-Geste.

    Mobile-optimiert:
    - Rechts: Genehmigen
    - Links: Ablehnen
    - Oben: Ueberspringen
    - Unten: Details anzeigen (keine Aktion)
    """
    service = await get_oneclick_validation_service(db, current_user.id)

    # Direction zu Decision mappen
    decision_map = {
        "right": "approve",
        "left": "reject",
        "up": "skip",
        "down": None,  # Keine Aktion
    }

    decision_value = decision_map.get(direction)

    if decision_value is None:
        return {
            "action": "show_details",
            "item_id": str(item_id),
            "message": "Details werden angezeigt",
        }

    decision = OneClickDecision(
        item_id=item_id,
        decision=decision_value,
    )

    result = await service.process_decision(decision)

    return {
        "action": decision_value,
        "item_id": str(item_id),
        "success": result.get("success", False),
        "error": result.get("error"),
    }

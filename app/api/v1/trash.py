# -*- coding: utf-8 -*-
"""Papierkorb (Trash) API - Soft Delete Management.

Benutzerfreundliche Schnittstelle fuer:
- Geloeschte Dokumente auflisten
- Dokumente wiederherstellen
- Dokumente permanent loeschen

GDPR-konform mit 30-Tage-Wiederherstellungsfrist.
"""

from typing import Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db, get_current_user
from app.core.safe_errors import safe_error_detail, safe_error_log
from app.db.models import User
from app.db.schemas import (
    SoftDeleteResponse,
    RestoreDocumentResponse,
    DeletedDocumentsListResponse,
)
from app.services.document_services.gdpr_service import get_gdpr_service

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/trash", tags=["Papierkorb"])


# =============================================================================
# Response Schemas
# =============================================================================


class TrashStatsResponse(BaseModel):
    """Statistiken zum Papierkorb."""

    total_items: int = Field(..., description="Anzahl Dokumente im Papierkorb")
    can_restore_count: int = Field(
        ..., description="Davon noch wiederherstellbar"
    )
    expiring_soon_count: int = Field(
        ..., description="Laufen in 7 Tagen ab"
    )
    storage_used_bytes: int = Field(
        0, description="Speicherplatz der geloeschten Dokumente"
    )


class PermanentDeleteResponse(BaseModel):
    """Response nach permanenter Loeschung."""

    document_id: UUID
    message: str = "Dokument wurde permanent geloescht"


class EmptyTrashResponse(BaseModel):
    """Response nach Leeren des Papierkorbs."""

    deleted_count: int
    message: str


# =============================================================================
# Endpoints
# =============================================================================


@router.get(
    "",
    response_model=DeletedDocumentsListResponse,
    summary="Papierkorb auflisten",
    description="Listet alle soft-geloeschten Dokumente des aktuellen Benutzers auf.",
)
async def list_trash(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DeletedDocumentsListResponse:
    """Alle Dokumente im Papierkorb auflisten.

    Zeigt geloeschte Dokumente mit:
    - Loeschdatum
    - Verbleibende Tage bis zur permanenten Loeschung
    - Wiederherstellbarkeit

    Returns:
        DeletedDocumentsListResponse mit allen geloeschten Dokumenten
    """
    service = get_gdpr_service()
    result = await service.list_deleted_documents(db=db, user_id=current_user.id)

    logger.debug(
        "trash_listed",
        user_id=str(current_user.id),
        count=result.total,
    )

    return result


@router.get(
    "/stats",
    response_model=TrashStatsResponse,
    summary="Papierkorb-Statistiken",
    description="Gibt Statistiken ueber den Papierkorb zurueck.",
)
async def get_trash_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TrashStatsResponse:
    """Statistiken zum Papierkorb abrufen.

    Returns:
        TrashStatsResponse mit Anzahl, wiederherstellbar, bald ablaufend
    """
    service = get_gdpr_service()
    result = await service.list_deleted_documents(db=db, user_id=current_user.id)

    can_restore = sum(1 for doc in result.documents if doc.can_restore)
    expiring_soon = sum(
        1 for doc in result.documents
        if doc.days_until_permanent_deletion is not None
        and doc.days_until_permanent_deletion <= 7
    )

    return TrashStatsResponse(
        total_items=result.total,
        can_restore_count=can_restore,
        expiring_soon_count=expiring_soon,
        storage_used_bytes=0,  # TODO: Berechnung wenn file_size verfuegbar
    )


@router.get(
    "/{document_id}",
    summary="Dokument-Details im Papierkorb",
    description="Gibt Details zu einem geloeschten Dokument zurueck.",
)
async def get_trash_item(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Details eines geloeschten Dokuments abrufen.

    Args:
        document_id: ID des Dokuments

    Returns:
        Dict mit Aufbewahrungsinformationen

    Raises:
        HTTPException 404: Dokument nicht gefunden
    """
    service = get_gdpr_service()
    info = await service.get_retention_info(
        db=db, document_id=document_id, user_id=current_user.id
    )

    if not info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dokument nicht gefunden",
        )

    if not info.get("is_deleted"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dokument befindet sich nicht im Papierkorb",
        )

    return info


@router.post(
    "/{document_id}/restore",
    response_model=RestoreDocumentResponse,
    summary="Dokument wiederherstellen",
    description="Stellt ein soft-geloeschtes Dokument wieder her.",
)
async def restore_document(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RestoreDocumentResponse:
    """Soft-geloeschtes Dokument wiederherstellen.

    Nur moeglich innerhalb der 30-Tage-Frist.

    Args:
        document_id: ID des wiederherzustellenden Dokuments

    Returns:
        RestoreDocumentResponse bei Erfolg

    Raises:
        HTTPException 404: Dokument nicht gefunden
        HTTPException 410: 30-Tage-Frist abgelaufen
    """
    service = get_gdpr_service()

    try:
        result = await service.restore_document(
            db=db, document_id=document_id, user_id=current_user.id
        )
    except ValueError as e:
        # 30-Tage-Frist abgelaufen
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=safe_error_detail(e, "Papierkorb"),
        )

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dokument nicht gefunden oder nicht im Papierkorb",
        )

    logger.info(
        "document_restored_from_trash",
        document_id=str(document_id),
        user_id=str(current_user.id),
    )

    return result


@router.delete(
    "/{document_id}",
    response_model=PermanentDeleteResponse,
    summary="Dokument permanent loeschen",
    description="Loescht ein Dokument permanent aus dem Papierkorb.",
)
async def permanently_delete_document(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PermanentDeleteResponse:
    """Dokument permanent aus dem Papierkorb loeschen.

    ACHTUNG: Diese Aktion kann nicht rueckgaengig gemacht werden!

    Args:
        document_id: ID des zu loeschenden Dokuments

    Returns:
        PermanentDeleteResponse bei Erfolg

    Raises:
        HTTPException 404: Dokument nicht gefunden
    """
    from app.db.models import Document
    from sqlalchemy import select, and_

    # Nur geloeschte Dokumente des Benutzers finden
    query = select(Document).where(
        and_(
            Document.id == document_id,
            Document.owner_id == current_user.id,
            Document.deleted_at.isnot(None),
        )
    )
    result = await db.execute(query)
    doc = result.scalar_one_or_none()

    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dokument nicht gefunden oder nicht im Papierkorb",
        )

    await db.delete(doc)
    await db.commit()

    logger.warning(
        "document_permanently_deleted",
        document_id=str(document_id),
        user_id=str(current_user.id),
    )

    return PermanentDeleteResponse(document_id=document_id)


@router.delete(
    "",
    response_model=EmptyTrashResponse,
    summary="Papierkorb leeren",
    description="Loescht alle Dokumente im Papierkorb permanent.",
)
async def empty_trash(
    only_expired: bool = Query(
        False,
        description="Nur abgelaufene Dokumente loeschen (>30 Tage)",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EmptyTrashResponse:
    """Papierkorb leeren.

    ACHTUNG: Diese Aktion kann nicht rueckgaengig gemacht werden!

    Args:
        only_expired: Wenn True, nur >30 Tage alte Dokumente loeschen

    Returns:
        EmptyTrashResponse mit Anzahl geloeschter Dokumente
    """
    from datetime import datetime, timezone, timedelta
    from app.db.models import Document
    from sqlalchemy import select, and_, delete

    conditions = [
        Document.owner_id == current_user.id,
        Document.deleted_at.isnot(None),
    ]

    if only_expired:
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        conditions.append(Document.deleted_at < cutoff)

    # Zaehlen vor dem Loeschen
    count_query = select(Document).where(and_(*conditions))
    result = await db.execute(count_query)
    docs = result.scalars().all()
    count = len(docs)

    # Loeschen
    for doc in docs:
        await db.delete(doc)

    await db.commit()

    action = "abgelaufene Dokumente" if only_expired else "alle Dokumente"
    logger.warning(
        "trash_emptied",
        user_id=str(current_user.id),
        count=count,
        only_expired=only_expired,
    )

    return EmptyTrashResponse(
        deleted_count=count,
        message=f"{count} {action} wurden permanent geloescht",
    )

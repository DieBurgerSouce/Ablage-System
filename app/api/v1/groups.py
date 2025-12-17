# -*- coding: utf-8 -*-
"""
Document Groups API Endpoints.

REST API fuer Dokumentgruppen (zusammengehoerige Dokumente):
- CRUD Operationen
- Automatische Erkennung
- Manuelle Bestaetigung/Ablehnung
- Gruppen teilen/zusammenfuehren
- Validation Queue

Feinpoliert und durchdacht - 99%+ Praezision.
"""

from typing import Optional, List
from uuid import UUID
from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, status, Query, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, func
from sqlalchemy.orm import selectinload

from app.db.models import User, DocumentGroup, Document, DocumentRelationship
from app.db.schemas import (
    DocumentGroupCreate,
    DocumentGroupUpdate,
    DocumentGroupResponse,
    DocumentGroupListResponse,
    DocumentGroupDetailResponse,
    DocumentGroupType,
    GroupDetectionRequest,
    GroupDetectionResponse,
    GroupConfirmRequest,
    GroupSplitRequest,
    GroupMergeRequest,
    ValidationQueueResponse,
    MessageResponse,
    SortOrder,
)
from app.api.dependencies import get_db, get_current_active_user
from app.services.document_grouping_service import DocumentGroupingService


logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/groups", tags=["Document Groups"])


# =============================================================================
# LIST / SEARCH
# =============================================================================

@router.get(
    "",
    response_model=DocumentGroupListResponse,
    summary="Dokumentgruppen auflisten",
    description="Listet alle Dokumentgruppen mit Filter- und Paginierungsoptionen"
)
async def list_groups(
    page: int = Query(1, ge=1, description="Seitennummer"),
    per_page: int = Query(20, ge=1, le=100, description="Eintraege pro Seite"),
    search: Optional[str] = Query(
        None, min_length=1, max_length=100,
        description="Suche in Name, Referenznummer"
    ),
    group_type: Optional[DocumentGroupType] = Query(
        None, description="Nach Gruppentyp filtern"
    ),
    needs_review: Optional[bool] = Query(
        None, description="Nur Gruppen in Validation Queue"
    ),
    user_confirmed: Optional[bool] = Query(
        None, description="Nach Bestaetigung filtern"
    ),
    min_confidence: Optional[float] = Query(
        None, ge=0.0, le=1.0, description="Minimale Konfidenz"
    ),
    sort_by: str = Query("created_at", description="Sortierfeld"),
    sort_order: SortOrder = Query(SortOrder.DESC, description="Sortierrichtung"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentGroupListResponse:
    """
    Listet alle Dokumentgruppen auf.

    **Filter:**
    - **group_type**: stapled, multi_page, transaction, etc.
    - **needs_review**: Nur Gruppen die Ueberpruefung benoetigen
    - **user_confirmed**: Manuell bestaetigte Gruppen
    - **min_confidence**: Minimale Erkennungs-Konfidenz

    **Sortierung:**
    - created_at, detection_confidence, total_pages
    """
    query = select(DocumentGroup).where(
        DocumentGroup.deleted_at.is_(None),
        DocumentGroup.owner_id == current_user.id
    )

    # Filter
    if search:
        search_term = f"%{search}%"
        query = query.where(
            or_(
                DocumentGroup.name.ilike(search_term),
                DocumentGroup.reference_number.ilike(search_term),
            )
        )

    if group_type:
        query = query.where(DocumentGroup.group_type == group_type.value)

    if needs_review is not None:
        query = query.where(DocumentGroup.needs_review == needs_review)

    if user_confirmed is not None:
        query = query.where(DocumentGroup.user_confirmed == user_confirmed)

    if min_confidence is not None:
        query = query.where(DocumentGroup.detection_confidence >= min_confidence)

    # Count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Sorting
    sort_column = getattr(DocumentGroup, sort_by, DocumentGroup.created_at)
    if sort_order == SortOrder.DESC:
        sort_column = sort_column.desc()
    query = query.order_by(sort_column)

    # Pagination
    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page)

    result = await db.execute(query)
    groups = result.scalars().all()

    return DocumentGroupListResponse(
        items=[DocumentGroupResponse.model_validate(g) for g in groups],
        total=total,
        page=page,
        per_page=per_page,
        total_pages=(total + per_page - 1) // per_page,
    )


# =============================================================================
# NEXT NUMBER (fuer Vorgang-Benennung)
# =============================================================================

@router.get(
    "/next-number",
    summary="Naechste laufende Nummer fuer Entity",
    description="Gibt die naechste freie laufende Nummer fuer einen Entity-Namen zurueck (z.B. Alpac -> 3 wenn Alpac_001 und Alpac_002 existieren)"
)
async def get_next_transaction_number(
    entity: str = Query(..., min_length=1, max_length=200, description="Entity-Name (z.B. Lieferantenname)"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Ermittelt die naechste laufende Nummer fuer Vorgaenge eines Entity.

    Durchsucht bestehende Gruppen nach dem Pattern `{entity}_XXX` und
    gibt die naechste freie Nummer zurueck.

    **Beispiel:**
    - Existiert: Alpac_001, Alpac_002
    - Rueckgabe: {"next_number": 3}
    """
    # Suche nach bestehenden Gruppen mit diesem Entity-Prefix
    pattern = f"{entity}_%"
    query = select(func.count()).select_from(DocumentGroup).where(
        DocumentGroup.name.like(pattern),
        DocumentGroup.owner_id == current_user.id,
        DocumentGroup.deleted_at.is_(None),
        DocumentGroup.group_type == "transaction"
    )

    result = await db.execute(query)
    count = result.scalar() or 0

    logger.info(
        "next_transaction_number_calculated",
        entity=entity,
        existing_count=count,
        next_number=count + 1,
        user_id=str(current_user.id)[:8]
    )

    return {"next_number": count + 1, "entity": entity}


# =============================================================================
# GET SINGLE
# =============================================================================

@router.get(
    "/{group_id}",
    response_model=DocumentGroupDetailResponse,
    summary="Dokumentgruppe abrufen",
    description="Ruft detaillierte Informationen zu einer Dokumentgruppe ab"
)
async def get_group(
    group_id: UUID,
    include_documents: bool = Query(True, description="Dokumente mitladen"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentGroupDetailResponse:
    """
    Ruft eine Dokumentgruppe mit allen Details ab.

    Beinhaltet standardmaessig alle Dokumente der Gruppe.
    """
    query = select(DocumentGroup).where(
        DocumentGroup.id == group_id,
        DocumentGroup.deleted_at.is_(None)
    )

    if include_documents:
        query = query.options(selectinload(DocumentGroup.documents))

    result = await db.execute(query)
    group = result.scalar_one_or_none()

    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dokumentgruppe nicht gefunden"
        )

    # Zugriffspruefung
    if group.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Zugriff verweigert"
        )

    response = DocumentGroupDetailResponse.model_validate(group)

    if include_documents and group.documents:
        response.documents = [
            {
                "id": str(doc.id),
                "filename": doc.original_filename,
                "page_number": doc.page_number_in_group,
                "is_primary": doc.is_group_primary,
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
            }
            for doc in sorted(group.documents, key=lambda d: d.page_number_in_group or 0)
        ]

    return response


# =============================================================================
# CREATE (Manual)
# =============================================================================

@router.post(
    "",
    response_model=DocumentGroupResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Dokumentgruppe manuell erstellen",
    description="Erstellt eine neue Dokumentgruppe manuell"
)
async def create_group(
    data: DocumentGroupCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentGroupResponse:
    """
    Erstellt eine neue Dokumentgruppe manuell.

    **Pflichtfelder:**
    - **name**: Gruppenname
    - **document_ids**: Liste von Dokument-IDs

    Manuell erstellte Gruppen haben immer `user_confirmed=True`.
    """
    # Dokumente pruefen
    if not data.document_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mindestens ein Dokument erforderlich"
        )

    docs_result = await db.execute(
        select(Document).where(
            Document.id.in_(data.document_ids),
            Document.deleted_at.is_(None),
            Document.owner_id == current_user.id
        )
    )
    documents = docs_result.scalars().all()

    if len(documents) != len(data.document_ids):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Eines oder mehrere Dokumente nicht gefunden"
        )

    # Pruefen ob Dokumente bereits in einer Gruppe
    for doc in documents:
        if doc.group_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Dokument {doc.original_filename} ist bereits in einer Gruppe"
            )

    # Gruppe erstellen
    group = DocumentGroup(
        name=data.name,
        description=data.description,
        group_type=data.group_type.value if data.group_type else "manual",
        detection_method="manual",
        detection_confidence=1.0,
        total_pages=len(documents),
        user_confirmed=True,
        needs_review=False,
        owner_id=current_user.id,
        confirmed_by_id=current_user.id,
        confirmation_date=datetime.utcnow(),
    )

    db.add(group)
    await db.flush()

    # Dokumente zuordnen
    for i, doc in enumerate(documents):
        doc.group_id = group.id
        doc.page_number_in_group = i + 1
        doc.is_group_primary = (i == 0)

    # Primary document setzen
    group.primary_document_id = documents[0].id

    await db.commit()
    await db.refresh(group)

    logger.info(
        "document_group_created_manually",
        group_id=str(group.id),
        document_count=len(documents),
        user_id=str(current_user.id),
    )

    return DocumentGroupResponse.model_validate(group)


# =============================================================================
# UPDATE
# =============================================================================

@router.put(
    "/{group_id}",
    response_model=DocumentGroupResponse,
    summary="Dokumentgruppe aktualisieren",
    description="Aktualisiert Metadaten einer Dokumentgruppe"
)
async def update_group(
    group_id: UUID,
    data: DocumentGroupUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentGroupResponse:
    """
    Aktualisiert Metadaten einer Dokumentgruppe.

    Aenderbare Felder:
    - name, description
    - reference_number
    - document_date
    """
    result = await db.execute(
        select(DocumentGroup).where(
            DocumentGroup.id == group_id,
            DocumentGroup.deleted_at.is_(None)
        )
    )
    group = result.scalar_one_or_none()

    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dokumentgruppe nicht gefunden"
        )

    if group.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Zugriff verweigert"
        )

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(group, key, value)

    await db.commit()
    await db.refresh(group)

    logger.info(
        "document_group_updated",
        group_id=str(group_id),
        user_id=str(current_user.id),
    )

    return DocumentGroupResponse.model_validate(group)


# =============================================================================
# DELETE
# =============================================================================

@router.delete(
    "/{group_id}",
    response_model=MessageResponse,
    summary="Dokumentgruppe loeschen",
    description="Loescht eine Dokumentgruppe (Soft-Delete)"
)
async def delete_group(
    group_id: UUID,
    unlink_documents: bool = Query(
        True, description="Dokumente aus Gruppe entfernen (nicht loeschen)"
    ),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """
    Loescht eine Dokumentgruppe (Soft-Delete).

    Dokumente werden standardmaessig nur aus der Gruppe entfernt,
    nicht geloescht.
    """
    result = await db.execute(
        select(DocumentGroup)
        .where(
            DocumentGroup.id == group_id,
            DocumentGroup.deleted_at.is_(None)
        )
        .options(selectinload(DocumentGroup.documents))
    )
    group = result.scalar_one_or_none()

    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dokumentgruppe nicht gefunden"
        )

    if group.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Zugriff verweigert"
        )

    # Dokumente aus Gruppe entfernen
    if unlink_documents and group.documents:
        for doc in group.documents:
            doc.group_id = None
            doc.page_number_in_group = None
            doc.is_group_primary = False

    # Soft-Delete
    group.deleted_at = datetime.utcnow()

    await db.commit()

    logger.info(
        "document_group_deleted",
        group_id=str(group_id),
        user_id=str(current_user.id),
    )

    return MessageResponse(message="Dokumentgruppe erfolgreich geloescht")


# =============================================================================
# DETECTION
# =============================================================================

@router.post(
    "/detect",
    response_model=GroupDetectionResponse,
    summary="Gruppierung erkennen",
    description="Erkennt automatisch zusammengehoerige Dokumente"
)
async def detect_groups(
    data: GroupDetectionRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> GroupDetectionResponse:
    """
    Erkennt automatisch zusammengehoerige Dokumente.

    Erkennungsstrategien:
    1. **Dateinamen-Sequenz**: Fortlaufende hex-Nummern
    2. **Zeitstempel-Naehe**: Kurz nacheinander gescannt
    3. **Seitennummerierung**: "Seite X von Y"
    4. **Referenzen**: Bezuege zwischen Dokumenten

    **Konfidenz-Schwellenwerte (99%+ Praezision):**
    - >= 0.99: Automatisch gruppieren
    - 0.80-0.99: Zur Ueberpruefung markieren
    - < 0.60: Ignorieren

    **Request:**
    - document_ids: Zu analysierende Dokumente
    - auto_create: Gruppen automatisch erstellen (nur bei >= 99%)
    """
    service = DocumentGroupingService(db)

    result = await service.detect_groups(
        document_ids=data.document_ids,
        owner_id=current_user.id
    )

    # Optional: Gruppen automatisch erstellen
    created_group_ids = []
    if data.auto_create:
        for candidate in result.groups:
            if candidate.combined_confidence >= 0.99:
                group_id = await service.create_group(
                    candidate=candidate,
                    owner_id=current_user.id,
                    auto_confirm=True
                )
                if group_id:
                    created_group_ids.append(str(group_id))

    return GroupDetectionResponse(
        groups=[
            {
                "document_ids": [str(d) for d in g.document_ids],
                "group_type": g.group_type,
                "confidence": g.combined_confidence,
                "signals": [
                    {"type": s.signal_type, "confidence": s.confidence}
                    for s in g.signals
                ],
                "suggested_name": g.suggested_name,
                "needs_review": g.needs_review,
                "auto_confirmed": g.combined_confidence >= 0.99 and data.auto_create,
            }
            for g in result.groups
        ],
        relationships=[
            {
                "source_id": str(r.source_document_id),
                "target_id": str(r.target_document_id),
                "type": r.relationship_type,
                "confidence": r.confidence,
            }
            for r in result.relationships
        ],
        stats=result.detection_stats,
        created_group_ids=created_group_ids,
    )


# =============================================================================
# CONFIRM / REJECT
# =============================================================================

@router.post(
    "/{group_id}/confirm",
    response_model=DocumentGroupResponse,
    summary="Gruppe bestaetigen",
    description="Bestaetigt eine automatisch erkannte Gruppe manuell"
)
async def confirm_group(
    group_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentGroupResponse:
    """
    Bestaetigt eine Dokumentgruppe manuell.

    Entfernt die Gruppe aus der Validation Queue.
    """
    service = DocumentGroupingService(db)

    success = await service.confirm_group(group_id, current_user.id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dokumentgruppe nicht gefunden"
        )

    result = await db.execute(
        select(DocumentGroup).where(DocumentGroup.id == group_id)
    )
    group = result.scalar_one()

    return DocumentGroupResponse.model_validate(group)


@router.post(
    "/{group_id}/reject",
    response_model=MessageResponse,
    summary="Gruppe ablehnen",
    description="Lehnt eine automatisch erkannte Gruppe ab und loest sie auf"
)
async def reject_group(
    group_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """
    Lehnt eine Dokumentgruppe ab und loest sie auf.

    Die Dokumente werden aus der Gruppe entfernt und bleiben einzeln.
    """
    result = await db.execute(
        select(DocumentGroup)
        .where(
            DocumentGroup.id == group_id,
            DocumentGroup.deleted_at.is_(None)
        )
        .options(selectinload(DocumentGroup.documents))
    )
    group = result.scalar_one_or_none()

    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dokumentgruppe nicht gefunden"
        )

    if group.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Zugriff verweigert"
        )

    # Dokumente aus Gruppe entfernen
    if group.documents:
        for doc in group.documents:
            doc.group_id = None
            doc.page_number_in_group = None
            doc.is_group_primary = False

    # Gruppe als abgelehnt markieren und loeschen
    group.deleted_at = datetime.utcnow()
    group.needs_review = False

    await db.commit()

    logger.info(
        "document_group_rejected",
        group_id=str(group_id),
        user_id=str(current_user.id),
    )

    return MessageResponse(message="Dokumentgruppe wurde abgelehnt und aufgeloest")


# =============================================================================
# SPLIT / MERGE
# =============================================================================

@router.post(
    "/{group_id}/split",
    summary="Gruppe teilen",
    description="Teilt eine Gruppe in mehrere neue Gruppen"
)
async def split_group(
    group_id: UUID,
    data: GroupSplitRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Teilt eine Dokumentgruppe in mehrere neue Gruppen.

    **Request:**
    - new_groups: Liste von Listen mit Dokument-IDs fuer jede neue Gruppe

    **Beispiel:**
    ```json
    {
        "new_groups": [
            ["doc-id-1", "doc-id-2"],
            ["doc-id-3", "doc-id-4", "doc-id-5"]
        ]
    }
    ```
    """
    # Gruppe pruefen
    result = await db.execute(
        select(DocumentGroup).where(
            DocumentGroup.id == group_id,
            DocumentGroup.deleted_at.is_(None)
        )
    )
    group = result.scalar_one_or_none()

    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dokumentgruppe nicht gefunden"
        )

    if group.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Zugriff verweigert"
        )

    service = DocumentGroupingService(db)

    new_group_ids = await service.split_group(
        group_id=group_id,
        user_id=current_user.id,
        new_groups=data.new_groups
    )

    return {
        "message": f"Gruppe in {len(new_group_ids)} neue Gruppen aufgeteilt",
        "new_group_ids": [str(g) for g in new_group_ids],
    }


@router.post(
    "/merge",
    response_model=DocumentGroupResponse,
    summary="Gruppen zusammenfuehren",
    description="Fuehrt mehrere Gruppen zu einer zusammen"
)
async def merge_groups(
    data: GroupMergeRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentGroupResponse:
    """
    Fuehrt mehrere Dokumentgruppen zu einer zusammen.

    - **target_id**: Gruppe die erhalten bleibt
    - **source_ids**: Gruppen die zusammengefuehrt werden
    """
    # Target laden
    target_result = await db.execute(
        select(DocumentGroup)
        .where(
            DocumentGroup.id == data.target_id,
            DocumentGroup.deleted_at.is_(None)
        )
        .options(selectinload(DocumentGroup.documents))
    )
    target = target_result.scalar_one_or_none()

    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ziel-Gruppe nicht gefunden"
        )

    if target.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Zugriff verweigert"
        )

    merged_count = 0
    total_docs = len(target.documents) if target.documents else 0

    for source_id in data.source_ids:
        if source_id == data.target_id:
            continue

        source_result = await db.execute(
            select(DocumentGroup)
            .where(
                DocumentGroup.id == source_id,
                DocumentGroup.deleted_at.is_(None)
            )
            .options(selectinload(DocumentGroup.documents))
        )
        source = source_result.scalar_one_or_none()

        if not source or source.owner_id != current_user.id:
            continue

        # Dokumente umhaengen
        if source.documents:
            for doc in source.documents:
                doc.group_id = target.id
                doc.page_number_in_group = total_docs + 1
                doc.is_group_primary = False
                total_docs += 1

        # Source loeschen
        source.deleted_at = datetime.utcnow()
        merged_count += 1

    # Target aktualisieren
    target.total_pages = total_docs
    target.user_confirmed = True
    target.confirmed_by_id = current_user.id
    target.confirmation_date = datetime.utcnow()

    await db.commit()
    await db.refresh(target)

    logger.info(
        "document_groups_merged",
        target_id=str(data.target_id),
        merged_count=merged_count,
        user_id=str(current_user.id),
    )

    return DocumentGroupResponse.model_validate(target)


# =============================================================================
# VALIDATION QUEUE
# =============================================================================

@router.get(
    "/queue/review",
    response_model=ValidationQueueResponse,
    summary="Validation Queue",
    description="Listet Gruppen auf die manuelle Ueberpruefung benoetigen"
)
async def get_review_queue(
    limit: int = Query(50, ge=1, le=100, description="Maximale Anzahl"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> ValidationQueueResponse:
    """
    Gibt Dokumentgruppen zurueck die auf Ueberpruefung warten.

    Sortiert nach Prioritaet (1=hoechste) und Erstellungsdatum.

    Diese Gruppen haben:
    - Konfidenz zwischen 80% und 99%
    - Wurden automatisch erkannt aber nicht bestaetigt
    """
    service = DocumentGroupingService(db)

    groups = await service.get_review_queue(
        owner_id=current_user.id,
        limit=limit
    )

    return ValidationQueueResponse(
        items=[
            {
                "id": str(g.id),
                "name": g.name,
                "group_type": g.group_type,
                "detection_confidence": g.detection_confidence,
                "detection_method": g.detection_method,
                "total_pages": g.total_pages,
                "review_priority": g.review_priority,
                "created_at": g.created_at.isoformat() if g.created_at else None,
            }
            for g in groups
        ],
        total=len(groups),
    )


@router.get(
    "/stats",
    summary="Gruppierungsstatistiken",
    description="Gibt Statistiken ueber Dokumentgruppen zurueck"
)
async def get_group_stats(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Gibt Statistiken ueber Dokumentgruppen zurueck.

    - Gesamtzahl Gruppen
    - Aufschluesselung nach Typ
    - Durchschnittliche Konfidenz
    - Queue-Status
    """
    # Gesamt
    total_query = select(func.count()).select_from(
        select(DocumentGroup).where(
            DocumentGroup.owner_id == current_user.id,
            DocumentGroup.deleted_at.is_(None)
        ).subquery()
    )
    total = (await db.execute(total_query)).scalar() or 0

    # Nach Typ
    type_query = (
        select(DocumentGroup.group_type, func.count())
        .where(
            DocumentGroup.owner_id == current_user.id,
            DocumentGroup.deleted_at.is_(None)
        )
        .group_by(DocumentGroup.group_type)
    )
    type_result = await db.execute(type_query)
    by_type = dict(type_result.all())

    # Bestaetigt vs nicht bestaetigt
    confirmed_query = select(func.count()).select_from(
        select(DocumentGroup).where(
            DocumentGroup.owner_id == current_user.id,
            DocumentGroup.deleted_at.is_(None),
            DocumentGroup.user_confirmed == True
        ).subquery()
    )
    confirmed = (await db.execute(confirmed_query)).scalar() or 0

    # In Queue
    queue_query = select(func.count()).select_from(
        select(DocumentGroup).where(
            DocumentGroup.owner_id == current_user.id,
            DocumentGroup.deleted_at.is_(None),
            DocumentGroup.needs_review == True
        ).subquery()
    )
    in_queue = (await db.execute(queue_query)).scalar() or 0

    # Durchschnittliche Konfidenz
    avg_conf_query = (
        select(func.avg(DocumentGroup.detection_confidence))
        .where(
            DocumentGroup.owner_id == current_user.id,
            DocumentGroup.deleted_at.is_(None)
        )
    )
    avg_confidence = (await db.execute(avg_conf_query)).scalar() or 0

    return {
        "total_groups": total,
        "by_type": by_type,
        "confirmed": confirmed,
        "pending_confirmation": total - confirmed,
        "in_review_queue": in_queue,
        "average_confidence": round(float(avg_confidence), 4),
    }

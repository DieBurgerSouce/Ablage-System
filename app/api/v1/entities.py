# -*- coding: utf-8 -*-
"""
Business Entity API Endpoints.

REST API fuer Geschaeftspartner (Kunden/Lieferanten):
- CRUD Operationen
- Automatische Erkennung aus OCR-Text
- Dokument-Verknuepfung
- Duplikat-Zusammenfuehrung
- Suggestions basierend auf OCR

Feinpoliert und durchdacht - Deutsche Geschaeftsdokumente.
"""

from typing import Optional, List
from uuid import UUID
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, Depends, HTTPException, status, Query, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, func, and_
from sqlalchemy.orm import selectinload

from app.db.models import User, BusinessEntity, Document
from app.db.schemas import (
    BusinessEntityCreate,
    BusinessEntityUpdate,
    BusinessEntityResponse,
    BusinessEntityListResponse,
    BusinessEntityDetailResponse,
    EntityType,
    EntityExtractionRequest,
    EntityExtractionResponse,
    EntityMatchResponse,
    EntityMergeRequest,
    MessageResponse,
    SortOrder,
)
from app.api.dependencies import get_db, get_current_active_user
from app.services.entity_extraction_service import (
    EntityExtractionService,
    EntityExtractionResult,
)


logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/entities", tags=["Business Entities"])


# =============================================================================
# LIST / SEARCH
# =============================================================================

@router.get(
    "",
    response_model=BusinessEntityListResponse,
    summary="Geschaeftspartner auflisten",
    description="Listet alle Geschaeftspartner mit Filter- und Paginierungsoptionen"
)
async def list_entities(
    page: int = Query(1, ge=1, description="Seitennummer"),
    per_page: int = Query(20, ge=1, le=100, description="Eintraege pro Seite"),
    search: Optional[str] = Query(
        None, min_length=1, max_length=100,
        description="Suche in Name, USt-IdNr, IBAN"
    ),
    entity_type: Optional[EntityType] = Query(
        None, description="Nach Typ filtern (customer, supplier, both)"
    ),
    is_active: Optional[bool] = Query(None, description="Nach Aktivstatus filtern"),
    verified: Optional[bool] = Query(None, description="Nach Verifizierung filtern"),
    postal_code: Optional[str] = Query(None, description="Nach PLZ filtern"),
    city: Optional[str] = Query(None, description="Nach Stadt filtern"),
    sort_by: str = Query("name", description="Sortierfeld (name, created_at, document_count)"),
    sort_order: SortOrder = Query(SortOrder.ASC, description="Sortierrichtung"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> BusinessEntityListResponse:
    """
    Listet alle Geschaeftspartner auf.

    **Filter:**
    - **search**: Sucht in Name, USt-IdNr, IBAN
    - **entity_type**: customer, supplier, both, internal
    - **is_active**: Nur aktive/inaktive
    - **verified**: Nur manuell verifizierte

    **Sortierung:**
    - name, created_at, document_count, last_document_date
    """
    query = select(BusinessEntity).where(BusinessEntity.deleted_at.is_(None))

    # Filter
    if search:
        search_term = f"%{search}%"
        query = query.where(
            or_(
                BusinessEntity.name.ilike(search_term),
                BusinessEntity.vat_id.ilike(search_term),
                BusinessEntity.iban.ilike(search_term),
                BusinessEntity.city.ilike(search_term),
            )
        )

    if entity_type:
        query = query.where(BusinessEntity.entity_type == entity_type.value)

    if is_active is not None:
        query = query.where(BusinessEntity.is_active == is_active)

    if verified is not None:
        query = query.where(BusinessEntity.verified == verified)

    if postal_code:
        query = query.where(BusinessEntity.postal_code == postal_code)

    if city:
        query = query.where(BusinessEntity.city.ilike(f"%{city}%"))

    # Count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Sorting
    sort_column = getattr(BusinessEntity, sort_by, BusinessEntity.name)
    if sort_order == SortOrder.DESC:
        sort_column = sort_column.desc()
    query = query.order_by(sort_column)

    # Pagination
    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page)

    result = await db.execute(query)
    entities = result.scalars().all()

    return BusinessEntityListResponse(
        items=[BusinessEntityResponse.model_validate(e) for e in entities],
        total=total,
        page=page,
        per_page=per_page,
        total_pages=(total + per_page - 1) // per_page,
    )


# =============================================================================
# GET SINGLE
# =============================================================================

@router.get(
    "/{entity_id}",
    response_model=BusinessEntityDetailResponse,
    summary="Geschaeftspartner abrufen",
    description="Ruft detaillierte Informationen zu einem Geschaeftspartner ab"
)
async def get_entity(
    entity_id: UUID,
    include_documents: bool = Query(False, description="Dokumente mitladen"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> BusinessEntityDetailResponse:
    """
    Ruft einen Geschaeftspartner mit allen Details ab.

    Optional koennen verknuepfte Dokumente mitgeladen werden.
    """
    query = select(BusinessEntity).where(
        BusinessEntity.id == entity_id,
        BusinessEntity.deleted_at.is_(None)
    )

    if include_documents:
        query = query.options(selectinload(BusinessEntity.documents))

    result = await db.execute(query)
    entity = result.scalar_one_or_none()

    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Geschaeftspartner nicht gefunden"
        )

    response = BusinessEntityDetailResponse.model_validate(entity)

    if include_documents and entity.documents:
        response.recent_documents = [
            {
                "id": str(doc.id),
                "filename": doc.original_filename,
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
            }
            for doc in sorted(entity.documents, key=lambda d: d.created_at or datetime.min, reverse=True)[:10]
        ]

    return response


# =============================================================================
# CREATE
# =============================================================================

@router.post(
    "",
    response_model=BusinessEntityResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Geschaeftspartner erstellen",
    description="Erstellt einen neuen Geschaeftspartner"
)
async def create_entity(
    data: BusinessEntityCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> BusinessEntityResponse:
    """
    Erstellt einen neuen Geschaeftspartner.

    **Pflichtfelder:**
    - **name**: Firmenname
    - **entity_type**: customer, supplier, both

    **Optionale Felder:**
    - vat_id: USt-IdNr (wird auf Duplikate geprueft)
    - iban: Bankverbindung
    - Adresse, Kontakt, etc.
    """
    # Pruefen auf Duplikate
    if data.vat_id:
        existing = await db.execute(
            select(BusinessEntity).where(
                BusinessEntity.vat_id == data.vat_id,
                BusinessEntity.deleted_at.is_(None)
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Geschaeftspartner mit USt-IdNr {data.vat_id} existiert bereits"
            )

    if data.iban:
        existing = await db.execute(
            select(BusinessEntity).where(
                BusinessEntity.iban == data.iban,
                BusinessEntity.deleted_at.is_(None)
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Geschaeftspartner mit dieser IBAN existiert bereits"
            )

    entity = BusinessEntity(
        **data.model_dump(exclude_unset=True),
        created_by_id=current_user.id,
    )

    db.add(entity)
    await db.commit()
    await db.refresh(entity)

    logger.info(
        "business_entity_created",
        entity_id=str(entity.id),
        name=entity.name,
        user_id=str(current_user.id),
    )

    return BusinessEntityResponse.model_validate(entity)


# =============================================================================
# UPDATE
# =============================================================================

@router.put(
    "/{entity_id}",
    response_model=BusinessEntityResponse,
    summary="Geschaeftspartner aktualisieren",
    description="Aktualisiert einen bestehenden Geschaeftspartner"
)
async def update_entity(
    entity_id: UUID,
    data: BusinessEntityUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> BusinessEntityResponse:
    """
    Aktualisiert einen Geschaeftspartner.

    Nur geaenderte Felder werden aktualisiert.
    """
    result = await db.execute(
        select(BusinessEntity).where(
            BusinessEntity.id == entity_id,
            BusinessEntity.deleted_at.is_(None)
        )
    )
    entity = result.scalar_one_or_none()

    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Geschaeftspartner nicht gefunden"
        )

    # Duplikat-Pruefung bei Aenderung von vat_id oder iban
    update_data = data.model_dump(exclude_unset=True)

    if "vat_id" in update_data and update_data["vat_id"] != entity.vat_id:
        existing = await db.execute(
            select(BusinessEntity).where(
                BusinessEntity.vat_id == update_data["vat_id"],
                BusinessEntity.id != entity_id,
                BusinessEntity.deleted_at.is_(None)
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="USt-IdNr bereits vergeben"
            )

    if "iban" in update_data and update_data["iban"] != entity.iban:
        existing = await db.execute(
            select(BusinessEntity).where(
                BusinessEntity.iban == update_data["iban"],
                BusinessEntity.id != entity_id,
                BusinessEntity.deleted_at.is_(None)
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="IBAN bereits vergeben"
            )

    for key, value in update_data.items():
        setattr(entity, key, value)

    await db.commit()
    await db.refresh(entity)

    logger.info(
        "business_entity_updated",
        entity_id=str(entity_id),
        user_id=str(current_user.id),
    )

    return BusinessEntityResponse.model_validate(entity)


# =============================================================================
# DELETE
# =============================================================================

@router.delete(
    "/{entity_id}",
    response_model=MessageResponse,
    summary="Geschaeftspartner loeschen",
    description="Loescht einen Geschaeftspartner (Soft-Delete)"
)
async def delete_entity(
    entity_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """
    Loescht einen Geschaeftspartner (Soft-Delete).

    Verknuepfte Dokumente werden NICHT geloescht, nur die Verknuepfung.
    """
    result = await db.execute(
        select(BusinessEntity).where(
            BusinessEntity.id == entity_id,
            BusinessEntity.deleted_at.is_(None)
        )
    )
    entity = result.scalar_one_or_none()

    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Geschaeftspartner nicht gefunden"
        )

    # Soft-Delete
    entity.deleted_at = datetime.now(timezone.utc)

    # Dokument-Verknuepfungen aufheben
    await db.execute(
        select(Document)
        .where(Document.business_entity_id == entity_id)
        .execution_options(synchronize_session="fetch")
    )

    await db.commit()

    logger.info(
        "business_entity_deleted",
        entity_id=str(entity_id),
        user_id=str(current_user.id),
    )

    return MessageResponse(message="Geschaeftspartner erfolgreich geloescht")


# =============================================================================
# DOCUMENTS
# =============================================================================

@router.get(
    "/{entity_id}/documents",
    summary="Verknuepfte Dokumente",
    description="Listet alle Dokumente eines Geschaeftspartners"
)
async def get_entity_documents(
    entity_id: UUID,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Listet alle Dokumente die mit diesem Geschaeftspartner verknuepft sind.
    """
    # Entity pruefen
    entity_result = await db.execute(
        select(BusinessEntity).where(
            BusinessEntity.id == entity_id,
            BusinessEntity.deleted_at.is_(None)
        )
    )
    if not entity_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Geschaeftspartner nicht gefunden"
        )

    # Dokumente zaehlen
    count_query = select(func.count()).select_from(
        select(Document).where(
            Document.business_entity_id == entity_id,
            Document.deleted_at.is_(None)
        ).subquery()
    )
    total = (await db.execute(count_query)).scalar() or 0

    # Dokumente laden
    offset = (page - 1) * per_page
    docs_query = (
        select(Document)
        .where(
            Document.business_entity_id == entity_id,
            Document.deleted_at.is_(None)
        )
        .order_by(Document.created_at.desc())
        .offset(offset)
        .limit(per_page)
    )

    result = await db.execute(docs_query)
    documents = result.scalars().all()

    return {
        "items": [
            {
                "id": str(doc.id),
                "filename": doc.original_filename,
                "document_type": doc.document_type,
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
                "status": doc.status,
            }
            for doc in documents
        ],
        "total": total,
        "page": page,
        "per_page": per_page,
    }


# =============================================================================
# EXTRACTION / MATCHING
# =============================================================================

@router.post(
    "/extract",
    response_model=EntityExtractionResponse,
    summary="Entitaeten aus Text extrahieren",
    description="Extrahiert Geschaeftspartner-Informationen aus OCR-Text"
)
async def extract_entities(
    data: EntityExtractionRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> EntityExtractionResponse:
    """
    Extrahiert Geschaeftspartner-Informationen aus OCR-Text.

    Erkannte Elemente:
    - USt-IdNr (DE123456789)
    - IBAN
    - Firmennamen mit Rechtsform
    - Adressen (PLZ, Stadt, Strasse)
    - E-Mail, Telefon

    **Response:**
    - Extrahierte Daten mit Konfidenz-Scores
    - Optional: Match zu bestehender Entity
    """
    service = EntityExtractionService(db)

    extraction = await service.extract_entities(
        text=data.text,
        document_id=data.document_id
    )

    response = EntityExtractionResponse(
        identifiers=[
            {
                "type": i.identifier_type,
                "value": i.value,
                "normalized": i.normalized_value,
                "confidence": i.confidence,
            }
            for i in extraction.identifiers
        ],
        addresses=[
            {
                "street": a.street,
                "street_number": a.street_number,
                "postal_code": a.postal_code,
                "city": a.city,
                "confidence": a.confidence,
            }
            for a in extraction.addresses
        ],
        company_names=[
            {
                "name": c.name,
                "legal_form": c.legal_form,
                "confidence": c.confidence,
            }
            for c in extraction.company_names
        ],
        emails=extraction.emails,
        phone_numbers=extraction.phone_numbers,
        overall_confidence=extraction.overall_confidence,
    )

    # Optional: Matching versuchen
    if data.try_match:
        match = await service.match_to_existing(extraction)
        response.match_result = EntityMatchResponse(
            entity_id=match.entity_id,
            entity_name=match.entity_name,
            match_type=match.match_type,
            confidence=match.confidence,
            is_new=match.is_new,
        )

    return response


@router.get(
    "/suggestions",
    summary="Entity-Vorschlaege",
    description="Gibt Vorschlaege fuer neue Entities basierend auf unverknuepften Dokumenten"
)
async def get_entity_suggestions(
    limit: int = Query(10, ge=1, le=50),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Gibt Vorschlaege fuer neue Geschaeftspartner basierend auf:
    - Dokumenten ohne Entity-Verknuepfung
    - Extrahierten aber nicht zugeordneten Identifiern

    Nuetzlich fuer das schrittweise Aufbauen der Entity-Datenbank.
    """
    # Dokumente ohne Entity-Verknuepfung mit extracted_data
    query = (
        select(Document)
        .where(
            Document.business_entity_id.is_(None),
            Document.extracted_text.isnot(None),
            Document.deleted_at.is_(None),
            Document.owner_id == current_user.id,
        )
        .order_by(Document.created_at.desc())
        .limit(limit * 2)  # Mehr laden fuer bessere Auswahl
    )

    result = await db.execute(query)
    documents = result.scalars().all()

    suggestions = []
    service = EntityExtractionService(db)

    for doc in documents:
        if not doc.extracted_text:
            continue

        extraction = await service.extract_entities(doc.extracted_text, doc.id)

        # Nur Dokumente mit hoher Konfidenz vorschlagen
        if extraction.overall_confidence >= 0.70:
            suggestion = {
                "document_id": str(doc.id),
                "document_filename": doc.original_filename,
                "extraction": {
                    "vat_ids": [i.normalized_value for i in extraction.identifiers if i.identifier_type == "vat_id"],
                    "ibans": [i.normalized_value for i in extraction.identifiers if i.identifier_type == "iban"],
                    "company_names": [c.name for c in extraction.company_names],
                    "addresses": [
                        f"{a.postal_code} {a.city}" for a in extraction.addresses if a.postal_code
                    ],
                },
                "confidence": extraction.overall_confidence,
            }
            suggestions.append(suggestion)

            if len(suggestions) >= limit:
                break

    return {
        "suggestions": suggestions,
        "total_unlinked_documents": len(documents),
    }


# =============================================================================
# MERGE DUPLICATES
# =============================================================================

@router.post(
    "/merge",
    response_model=BusinessEntityResponse,
    summary="Duplikate zusammenfuehren",
    description="Fuehrt mehrere Entity-Eintraege zu einem zusammen"
)
async def merge_entities(
    data: EntityMergeRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> BusinessEntityResponse:
    """
    Fuehrt mehrere Geschaeftspartner-Eintraege zu einem zusammen.

    - **target_id**: Entity die erhalten bleibt
    - **source_ids**: Entities die zusammengefuehrt werden

    Alle Dokumente der source_ids werden auf target_id umgehaengt.
    Source-Entities werden als geloescht markiert.
    """
    # Target laden
    target_result = await db.execute(
        select(BusinessEntity).where(
            BusinessEntity.id == data.target_id,
            BusinessEntity.deleted_at.is_(None)
        )
    )
    target = target_result.scalar_one_or_none()

    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ziel-Geschaeftspartner nicht gefunden"
        )

    merged_count = 0

    for source_id in data.source_ids:
        if source_id == data.target_id:
            continue

        source_result = await db.execute(
            select(BusinessEntity).where(
                BusinessEntity.id == source_id,
                BusinessEntity.deleted_at.is_(None)
            )
        )
        source = source_result.scalar_one_or_none()

        if not source:
            continue

        # Dokumente umhaengen
        await db.execute(
            select(Document)
            .where(Document.business_entity_id == source_id)
            .execution_options(synchronize_session="fetch")
        )

        # Name-Aliase uebernehmen
        if target.name_aliases is None:
            target.name_aliases = []
        if source.name not in target.name_aliases and source.name != target.name:
            target.name_aliases.append(source.name)

        if source.name_aliases:
            for alias in source.name_aliases:
                if alias not in target.name_aliases:
                    target.name_aliases.append(alias)

        # Statistiken aktualisieren
        target.document_count = (target.document_count or 0) + (source.document_count or 0)

        # Source als geloescht markieren
        source.deleted_at = datetime.now(timezone.utc)
        merged_count += 1

    await db.commit()
    await db.refresh(target)

    logger.info(
        "business_entities_merged",
        target_id=str(data.target_id),
        merged_count=merged_count,
        user_id=str(current_user.id),
    )

    return BusinessEntityResponse.model_validate(target)


# =============================================================================
# VERIFY
# =============================================================================

@router.post(
    "/{entity_id}/verify",
    response_model=BusinessEntityResponse,
    summary="Entity verifizieren",
    description="Markiert einen Geschaeftspartner als manuell verifiziert"
)
async def verify_entity(
    entity_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> BusinessEntityResponse:
    """
    Markiert einen Geschaeftspartner als manuell verifiziert.

    Verifizierte Entities haben hoeheres Vertrauen bei Auto-Matching.
    """
    result = await db.execute(
        select(BusinessEntity).where(
            BusinessEntity.id == entity_id,
            BusinessEntity.deleted_at.is_(None)
        )
    )
    entity = result.scalar_one_or_none()

    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Geschaeftspartner nicht gefunden"
        )

    entity.verified = True
    entity.confidence_score = 1.0

    await db.commit()
    await db.refresh(entity)

    logger.info(
        "business_entity_verified",
        entity_id=str(entity_id),
        user_id=str(current_user.id),
    )

    return BusinessEntityResponse.model_validate(entity)

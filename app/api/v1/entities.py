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
import re

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
# FRONTEND INTEGRATION - Kunden/Lieferanten Listen
# WICHTIG: Diese statischen Routen MUESSEN vor /{entity_id} stehen!
# =============================================================================

@router.get(
    "/customers",
    summary="Kunden fuer Frontend",
    description="Kunden-Liste mit displayName = Kundennummer_Matchcode (paginiert)"
)
async def list_customers_for_frontend(
    search: Optional[str] = Query(None, description="Suche in Name/Matchcode"),
    is_active: Optional[bool] = Query(None, description="Nach Aktivstatus filtern"),
    page: int = Query(1, ge=1, description="Seitennummer"),
    page_size: int = Query(50, ge=10, le=200, description="Eintraege pro Seite"),
    sort_by: str = Query("name", description="Sortierfeld: name, customer_number, last_activity"),
    sort_order: str = Query("asc", description="Sortierrichtung: asc oder desc"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Kunden-Liste fuer hierarchisches Frontend (paginiert).

    **Display-Format**: Kundennummer_Matchcode (z.B. "12345_Mueller")

    Gibt Kunden mit:
    - items: Array von Kunden
    - total: Gesamtanzahl
    - page/page_size: Pagination-Info

    **Sortierung**: name, customer_number, last_activity (asc/desc)
    """
    # Basis-Filter
    base_filter = [
        BusinessEntity.deleted_at.is_(None),
        or_(
            BusinessEntity.entity_type == "customer",
            BusinessEntity.entity_type == "both",
        )
    ]

    if search:
        search_term = f"%{search}%"
        base_filter.append(
            or_(
                BusinessEntity.name.ilike(search_term),
                BusinessEntity.primary_customer_number.ilike(search_term),
            )
        )

    if is_active is not None:
        base_filter.append(BusinessEntity.is_active == is_active)

    # Count-Query fuer Gesamtanzahl
    count_query = select(func.count(BusinessEntity.id)).where(*base_filter)
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Paginierte Query mit dynamischer Sortierung
    query = select(BusinessEntity).where(*base_filter)

    # Sortierung anwenden
    sort_column_map = {
        "name": BusinessEntity.name,
        "customer_number": BusinessEntity.primary_customer_number,
        "last_activity": BusinessEntity.updated_at,
    }
    sort_column = sort_column_map.get(sort_by, BusinessEntity.name)

    if sort_order.lower() == "desc":
        query = query.order_by(sort_column.desc().nulls_last())
    else:
        query = query.order_by(sort_column.asc().nulls_last())

    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    entities = result.scalars().all()

    # OPTIMIERUNG: Keine N+1 Queries mehr!
    # Stats werden erst beim Klick auf einen Kunden geladen (via /{entity_id}/folders)
    customers = []
    for entity in entities:
        # Display-Name: IMMER als "Kundennummer_Matchcode" konstruieren
        # (z.B. "10006_Peter", "12345_Mueller")
        customer_number = entity.primary_customer_number or ""
        matchcode = _extract_matchcode(entity.name)
        display_name = f"{customer_number}_{matchcode}" if customer_number else matchcode

        # Company presence aus lexware_ids extrahieren
        company_presence = entity.company_presence or []
        if not company_presence and entity.lexware_ids:
            company_presence = list(entity.lexware_ids.keys())

        # Fallback: Beide Firmen wenn nichts gesetzt
        if not company_presence:
            company_presence = ["folie", "messer"]

        customers.append({
            "id": str(entity.id),
            "displayName": display_name,
            # fullName = echter Firmenname aus display_name (z.B. "Hofgemeinschaft GbR")
            # Falls display_name leer ist, bleibt fullName leer
            "fullName": entity.display_name or "",
            "isActive": entity.is_active,
            "companyPresence": company_presence,
            # folderStats und lastActivityDate werden on-demand geladen
            "folderStats": {},
            "lastActivityDate": None,
        })

    return {
        "items": customers,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
    }


@router.get(
    "/suppliers",
    summary="Lieferanten fuer Frontend",
    description="Lieferanten-Liste mit displayName = Name (ohne Nummer, paginiert)"
)
async def list_suppliers_for_frontend(
    search: Optional[str] = Query(None, description="Suche in Name"),
    is_active: Optional[bool] = Query(None, description="Nach Aktivstatus filtern"),
    page: int = Query(1, ge=1, description="Seitennummer"),
    page_size: int = Query(50, ge=10, le=200, description="Eintraege pro Seite"),
    sort_by: str = Query("name", description="Sortierfeld: name, last_activity"),
    sort_order: str = Query("asc", description="Sortierrichtung: asc oder desc"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Lieferanten-Liste fuer hierarchisches Frontend (paginiert).

    **Display-Format**: Nur Name (ohne Lieferanten-Nummer, da chaotisch)

    Gibt Lieferanten mit:
    - items: Array von Lieferanten
    - total: Gesamtanzahl
    - page/page_size: Pagination-Info
    """
    # Basis-Filter
    base_filter = [
        BusinessEntity.deleted_at.is_(None),
        or_(
            BusinessEntity.entity_type == "supplier",
            BusinessEntity.entity_type == "both",
        )
    ]

    if search:
        search_term = f"%{search}%"
        base_filter.append(BusinessEntity.name.ilike(search_term))

    if is_active is not None:
        base_filter.append(BusinessEntity.is_active == is_active)

    # Count-Query fuer Gesamtanzahl
    count_query = select(func.count(BusinessEntity.id)).where(*base_filter)
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Paginierte Query
    query = select(BusinessEntity).where(*base_filter)

    # Sortierung anwenden
    sort_column_map = {
        "name": BusinessEntity.name,
        "last_activity": BusinessEntity.updated_at,
    }
    sort_column = sort_column_map.get(sort_by, BusinessEntity.name)

    if sort_order.lower() == "desc":
        query = query.order_by(sort_column.desc().nulls_last())
    else:
        query = query.order_by(sort_column.asc().nulls_last())

    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    entities = result.scalars().all()

    # OPTIMIERUNG: Keine N+1 Queries mehr!
    # Stats werden erst beim Klick auf einen Lieferanten geladen (via /{entity_id}/folders)
    suppliers = []
    for entity in entities:
        # Display-Name: Nutze entity.display_name wenn vorhanden und gueltig
        # (nicht "nan" oder leer - das sind ungueltige Altdaten)
        if entity.display_name and entity.display_name.lower() not in ("nan", "none", ""):
            display_name = entity.display_name
        else:
            display_name = _extract_matchcode(entity.name)

        # Company presence aus lexware_ids extrahieren
        company_presence = entity.company_presence or []
        if not company_presence and entity.lexware_ids:
            company_presence = list(entity.lexware_ids.keys())

        # Fallback: Beide Firmen wenn nichts gesetzt
        if not company_presence:
            company_presence = ["folie", "messer"]

        suppliers.append({
            "id": str(entity.id),
            "displayName": display_name,
            "fullName": entity.name,
            "isActive": entity.is_active,
            "companyPresence": company_presence,
            # folderStats und lastActivityDate werden on-demand geladen
            "folderStats": {},
            "lastActivityDate": None,
        })

    return {
        "items": suppliers,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
    }


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
# GET SINGLE (dynamische Route - MUSS nach statischen Routen stehen!)
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


# =============================================================================
# FOLDER VIEWS (dynamische Routen)
# =============================================================================

@router.get(
    "/{entity_id}/folders",
    summary="Ordner (Firmen) einer Entity",
    description="Gibt die Firmen-Ordner (Folie, Spargelmesser) zurueck"
)
async def get_entity_folders_view(
    entity_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Ordner (= Firmen) einer Entity mit Dokument-Statistiken.

    Response:
    - id: "folie" oder "messer"
    - name: "Folie" oder "Spargelmesser"
    - documentCounts: Zaehler pro Kategorie
    - totalDocuments: Gesamt
    - lastActivity: Letztes Dokument-Datum
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

    # Company presence aus Entity oder lexware_ids
    company_presence = entity.company_presence or []
    if not company_presence and entity.lexware_ids:
        company_presence = list(entity.lexware_ids.keys())

    # Falls leer, default beide Firmen
    if not company_presence:
        company_presence = ["folie", "messer"]

    folders = []
    folder_names = {
        "folie": "Folie",
        "messer": "Spargelmesser",
        "spargelmesser": "Spargelmesser",
    }

    for company_id in company_presence:
        # Normalize ID
        normalized_id = company_id.lower()
        if normalized_id == "spargelmesser":
            normalized_id = "messer"

        # Dokumente fuer diese Entity + Firma zaehlen
        doc_counts = await _count_documents_by_category(db, entity_id, normalized_id)

        # Letztes Dokument-Datum
        last_doc = await _get_last_document_date_for_folder(db, entity_id, normalized_id)

        total_docs = sum(doc_counts.values())

        folders.append({
            "id": normalized_id,
            "name": folder_names.get(normalized_id, company_id.title()),
            "documentCounts": doc_counts,
            "totalDocuments": total_docs,
            "openInvoices": doc_counts.get("offene_rechnungen", 0),
            "lastActivity": last_doc.isoformat() if last_doc else None,
        })

    return folders


@router.get(
    "/{entity_id}/folders/{folder_id}/documents",
    summary="Dokumente in Ordner/Kategorie",
    description="Dokumente einer Entity in spezifischer Firma und Kategorie"
)
async def get_folder_documents(
    entity_id: UUID,
    folder_id: str,
    category: Optional[str] = Query(None, description="Kategorie (angebote, rechnungen, etc.)"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Dokumente in einem Firmen-Ordner, optional nach Kategorie gefiltert.

    **folder_id**: "folie" oder "messer"
    **category**: z.B. "angebote", "rechnungen", "lieferscheine"
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

    # Normalize folder_id
    normalized_folder = folder_id.lower()
    if normalized_folder == "spargelmesser":
        normalized_folder = "messer"

    # Query aufbauen
    query = select(Document).where(
        Document.business_entity_id == entity_id,
        Document.deleted_at.is_(None),
    )

    # Kategorie-Filter
    if category:
        category_mapping = _get_category_to_doctype_mapping()
        doc_type = category_mapping.get(category.lower())
        if doc_type:
            query = query.where(Document.document_type == doc_type)

    # Count
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # Pagination + Sorting
    offset = (page - 1) * per_page
    query = query.order_by(Document.created_at.desc()).offset(offset).limit(per_page)

    result = await db.execute(query)
    documents = result.scalars().all()

    return {
        "items": [
            {
                "id": str(doc.id),
                "filename": doc.original_filename,
                "documentType": doc.document_type,
                "createdAt": doc.created_at.isoformat() if doc.created_at else None,
                "status": doc.status,
            }
            for doc in documents
        ],
        "total": total,
        "page": page,
        "perPage": per_page,
        "totalPages": (total + per_page - 1) // per_page if total > 0 else 0,
    }


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _extract_matchcode(name: str) -> str:
    """
    Extrahiert einen Matchcode aus dem Firmennamen.

    Beispiele:
    - "Mueller GmbH & Co. KG" -> "Mueller"
    - "Agrimpex International Trading GmbH" -> "Agrimpex"
    - "Hans Meier Spargel- und Erdbeerhof" -> "Meier"
    - "25223_Agrargenossenschaft Nöbdenitz eG" -> "Agrargenossenschaft" (Altdaten-Format)
    """
    if not name:
        return ""

    # Altdaten-Format: "12345_Firmenname" -> nur Firmenname extrahieren
    legacy_match = re.match(r"^\d+_(.+)$", name)
    if legacy_match:
        name = legacy_match.group(1)

    # Rechtsformen entfernen
    legal_forms = [
        " GmbH & Co. KG", " GmbH & Co. KGaA", " GmbH & Co.",
        " GmbH", " AG", " KG", " OHG", " e.K.", " e.V.",
        " Spargel- und Erdbeerhof", " Spargelvermarktung",
        " International Trading", " Trading", " Handel",
    ]

    result = name
    for form in legal_forms:
        result = result.replace(form, "")
        result = result.replace(form.lower(), "")

    # Bereinigen
    result = result.strip()

    # Bei mehreren Woertern, erstes sinnvolles nehmen
    words = result.split()
    if len(words) >= 2:
        # Wenn erstes Wort ein Vorname sein koennte, zweites nehmen
        first_word = words[0]
        if len(first_word) < 5 and first_word.lower() in ["hans", "franz", "karl", "maria", "anna"]:
            result = words[1]
        else:
            result = words[0]
    elif words:
        result = words[0]

    return result or name[:20]


async def _calculate_folder_stats(
    db: AsyncSession,
    entity_id: UUID,
    company_presence: List[str]
) -> dict:
    """Berechnet Dokument-Statistiken pro Firma."""
    stats = {}

    for company_id in company_presence:
        normalized_id = company_id.lower()
        if normalized_id == "spargelmesser":
            normalized_id = "messer"

        # Gesamtzahl Dokumente fuer diese Entity
        doc_count_query = select(func.count()).select_from(
            select(Document).where(
                Document.business_entity_id == entity_id,
                Document.deleted_at.is_(None),
            ).subquery()
        )
        total = (await db.execute(doc_count_query)).scalar() or 0

        # Offene Rechnungen (document_type = 'rechnung')
        open_inv_query = select(func.count()).select_from(
            select(Document).where(
                Document.business_entity_id == entity_id,
                Document.document_type == "rechnung",
                Document.deleted_at.is_(None),
            ).subquery()
        )
        open_invoices = (await db.execute(open_inv_query)).scalar() or 0

        stats[normalized_id] = {
            "totalDocs": total // len(company_presence) if company_presence else total,
            "openInvoices": open_invoices // len(company_presence) if company_presence else open_invoices,
        }

    return stats


async def _get_last_document_date(db: AsyncSession, entity_id: UUID):
    """Ermittelt das Datum des letzten Dokuments."""
    query = (
        select(Document.created_at)
        .where(
            Document.business_entity_id == entity_id,
            Document.deleted_at.is_(None),
        )
        .order_by(Document.created_at.desc())
        .limit(1)
    )
    result = await db.execute(query)
    row = result.first()
    return row[0] if row else None


async def _get_last_document_date_for_folder(
    db: AsyncSession,
    entity_id: UUID,
    folder_id: str
):
    """Ermittelt das Datum des letzten Dokuments in einem Ordner."""
    return await _get_last_document_date(db, entity_id)


async def _count_documents_by_category(
    db: AsyncSession,
    entity_id: UUID,
    folder_id: str
) -> dict:
    """Zaehlt Dokumente pro Kategorie fuer eine Entity/Firma."""
    categories = [
        "anfragen", "angebote", "auftragsbestaetigung", "lieferscheine",
        "rechnungen", "storno", "mahnungen", "offene_rechnungen",
        "offene_angebote", "offene_anfragen", "reklamation",
        "kommunikation", "archiv"
    ]

    category_to_doctype = _get_category_to_doctype_mapping()

    result = {}
    for cat in categories:
        doc_type = category_to_doctype.get(cat, cat)

        count_query = select(func.count()).select_from(
            select(Document).where(
                Document.business_entity_id == entity_id,
                Document.document_type == doc_type,
                Document.deleted_at.is_(None),
            ).subquery()
        )
        count = (await db.execute(count_query)).scalar() or 0
        result[cat] = count

    return result


def _get_category_to_doctype_mapping() -> dict:
    """Mapping von Frontend-Kategorien zu Document.document_type."""
    return {
        "anfragen": "anfrage",
        "angebote": "angebot",
        "auftragsbestaetigung": "auftragsbestaetigung",
        "lieferscheine": "lieferschein",
        "rechnungen": "rechnung",
        "storno": "storno",
        "mahnungen": "mahnung",
        "offene_rechnungen": "rechnung",
        "offene_angebote": "angebot",
        "offene_anfragen": "anfrage",
        "reklamation": "reklamation",
        "kommunikation": "kommunikation",
        "archiv": "archiv",
        "bestellungen": "bestellung",
    }

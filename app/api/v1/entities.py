# -*- coding: utf-8 -*-
"""
Business Entity API Endpoints.

REST API für Geschäftspartner (Kunden/Lieferanten):
- CRUD Operationen
- Automatische Erkennung aus OCR-Text
- Dokument-Verknüpfung
- Duplikat-Zusammenführung
- Suggestions basierend auf OCR

Feinpoliert und durchdacht - Deutsche Geschäftsdokumente.
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
from app.services.company_service import get_company_service


logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/entities", tags=["Business Entities"])


# =============================================================================
# LIST / SEARCH
# =============================================================================

@router.get(
    "",
    response_model=BusinessEntityListResponse,
    summary="Geschäftspartner auflisten",
    description="Listet alle Geschäftspartner mit Filter- und Paginierungsoptionen"
)
async def list_entities(
    page: int = Query(1, ge=1, description="Seitennummer"),
    per_page: int = Query(20, ge=1, le=100, description="Einträge pro Seite"),
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
    Listet alle Geschäftspartner auf.

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
    # SECURITY: Explicit Whitelist gegen Reflection-Angriffe (CWE-89)
    # Verhindert SQL Injection via dynamischen getattr()-Aufruf
    ALLOWED_SORT_FIELDS = {"name", "created_at", "document_count", "updated_at"}
    if sort_by not in ALLOWED_SORT_FIELDS:
        sort_by = "name"  # Safe default
    sort_column = getattr(BusinessEntity, sort_by)
    if sort_order == SortOrder.DESC:
        sort_column = sort_column.desc()
    query = query.order_by(sort_column)

    # Pagination
    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page)

    result = await db.execute(query)
    entities = result.scalars().all()

    return BusinessEntityListResponse(
        entities=[BusinessEntityResponse.model_validate(e) for e in entities],
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
    summary="Kunden für Frontend",
    description="Kunden-Liste mit displayName = Kundennummer_Matchcode (paginiert)"
)
async def list_customers_for_frontend(
    search: Optional[str] = Query(None, description="Suche in Name/Matchcode"),
    is_active: Optional[bool] = Query(None, description="Nach Aktivstatus filtern"),
    page: int = Query(1, ge=1, description="Seitennummer"),
    page_size: int = Query(50, ge=10, le=200, description="Einträge pro Seite"),
    sort_by: str = Query("name", description="Sortierfeld: name, customer_number, last_activity"),
    sort_order: str = Query("asc", description="Sortierrichtung: asc oder desc"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Kunden-Liste für hierarchisches Frontend (paginiert).

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

    # Count-Query für Gesamtanzahl
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

        # Fallback: Alle aktiven Firmen wenn nichts gesetzt
        # MULTI-TENANT: Dynamisch statt hardcoded "folie"/"messer"
        if not company_presence:
            company_service = get_company_service()
            company_presence = await company_service.get_company_short_names(db)

        customers.append({
            "id": str(entity.id),
            "displayName": display_name,
            # fullName = echter Firmenname aus display_name (z.B. "Hofgemeinschaft GbR")
            # Falls display_name leer ist, bleibt fullName leer
            "fullName": entity.display_name or "",
            "isActive": entity.is_active,
            "companyPresence": company_presence,
            # Risk Score für Frontend-Anzeige (0-100, höher = riskanter)
            "riskScore": entity.risk_score,
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
    summary="Lieferanten für Frontend",
    description="Lieferanten-Liste mit displayName = Name (ohne Nummer, paginiert)"
)
async def list_suppliers_for_frontend(
    search: Optional[str] = Query(None, description="Suche in Name"),
    is_active: Optional[bool] = Query(None, description="Nach Aktivstatus filtern"),
    page: int = Query(1, ge=1, description="Seitennummer"),
    page_size: int = Query(50, ge=10, le=200, description="Einträge pro Seite"),
    sort_by: str = Query("name", description="Sortierfeld: name, last_activity"),
    sort_order: str = Query("asc", description="Sortierrichtung: asc oder desc"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Lieferanten-Liste für hierarchisches Frontend (paginiert).

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

    # Count-Query für Gesamtanzahl
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
        # Display-Name: Nutze entity.display_name wenn vorhanden und gültig
        # (nicht "nan" oder leer - das sind ungültige Altdaten)
        if entity.display_name and entity.display_name.lower() not in ("nan", "none", ""):
            display_name = entity.display_name
        else:
            display_name = _extract_matchcode(entity.name)

        # Company presence aus lexware_ids extrahieren
        company_presence = entity.company_presence or []
        if not company_presence and entity.lexware_ids:
            company_presence = list(entity.lexware_ids.keys())

        # Fallback: Alle aktiven Firmen wenn nichts gesetzt
        # MULTI-TENANT: Dynamisch statt hardcoded "folie"/"messer"
        if not company_presence:
            company_service = get_company_service()
            company_presence = await company_service.get_company_short_names(db)

        suppliers.append({
            "id": str(entity.id),
            "displayName": display_name,
            "fullName": entity.name,
            "isActive": entity.is_active,
            "companyPresence": company_presence,
            # Risk Score für Frontend-Anzeige (0-100, höher = riskanter)
            "riskScore": entity.risk_score,
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
    summary="Entity-Vorschläge",
    description="Gibt Vorschläge für neue Entities basierend auf unverknüpften Dokumenten"
)
async def get_entity_suggestions(
    limit: int = Query(10, ge=1, le=50),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Gibt Vorschläge für neue Geschäftspartner basierend auf:
    - Dokumenten ohne Entity-Verknüpfung
    - Extrahierten aber nicht zugeordneten Identifiern

    Nuetzlich für das schrittweise Aufbauen der Entity-Datenbank.
    """
    # Dokumente ohne Entity-Verknüpfung mit extracted_data
    query = (
        select(Document)
        .where(
            Document.business_entity_id.is_(None),
            Document.extracted_text.isnot(None),
            Document.deleted_at.is_(None),
            Document.owner_id == current_user.id,
        )
        .order_by(Document.created_at.desc())
        .limit(limit * 2)  # Mehr laden für bessere Auswahl
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
# CROSS-COMPANY VIEW
# =============================================================================

@router.get(
    "/cross-company",
    summary="Cross-Company Übersicht",
    description="Zeigt Entities mit Praesenz in mehreren Firmen und Statistiken"
)
async def get_cross_company_entities(
    page: int = Query(1, ge=1, description="Seitennummer"),
    per_page: int = Query(50, ge=1, le=100, description="Einträge pro Seite"),
    search: Optional[str] = Query(None, min_length=1, description="Suche in Name"),
    entity_type: Optional[EntityType] = Query(None, description="Nach Typ filtern"),
    company_filter: Optional[str] = Query(
        None, description="Nur Entities in dieser Firma (folie, messer)"
    ),
    multi_company_only: bool = Query(
        False, description="Nur Entities in mehreren Firmen zeigen"
    ),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Gibt eine Übersicht der Geschäftspartner mit Firmen-Statistiken.

    Zeigt für jede Entity:
    - In welchen Firmen sie existiert (Folie, Messer)
    - Anzahl Dokumente pro Firma
    - Letzte Aktivitaet pro Firma

    **Ideal für:**
    - Vergleich der Kundenaktivitaet zwischen Firmen
    - Erkennen von nur einseitig gepflegten Kunden/Lieferanten
    """
    # Basis-Query
    query = select(BusinessEntity).where(BusinessEntity.deleted_at.is_(None))

    # Filter: Nur Multi-Company Entities
    if multi_company_only:
        query = query.where(
            func.jsonb_array_length(BusinessEntity.company_presence) > 1
        )

    # Filter: Bestimmte Firma
    if company_filter:
        query = query.where(
            BusinessEntity.company_presence.contains([company_filter])
        )

    # Filter: Suchbegriff
    if search:
        search_term = f"%{search}%"
        query = query.where(
            or_(
                BusinessEntity.name.ilike(search_term),
                BusinessEntity.primary_customer_number.ilike(search_term),
                BusinessEntity.primary_supplier_number.ilike(search_term),
            )
        )

    # Filter: Entity-Type
    if entity_type:
        query = query.where(BusinessEntity.entity_type == entity_type.value)

    # Zaehle Gesamt
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Paginierung und Sortierung
    query = query.order_by(BusinessEntity.name).offset((page - 1) * per_page).limit(per_page)

    result = await db.execute(query)
    entities = result.scalars().all()

    # Sammle Statistiken pro Entity und Firma
    items = []
    for entity in entities:
        company_presence = entity.company_presence or []
        lexware_ids = entity.lexware_ids or {}

        # Dokument-Zaehlung pro Firma
        doc_count_query = (
            select(
                Document.document_type,
                func.count(Document.id).label("count")
            )
            .where(
                Document.business_entity_id == entity.id,
                Document.deleted_at.is_(None),
            )
            .group_by(Document.document_type)
        )
        doc_result = await db.execute(doc_count_query)
        doc_counts = {str(row.document_type): row.count for row in doc_result}

        # Letzte Aktivitaet pro Firma
        last_activity_query = (
            select(
                Document.document_type,
                func.max(Document.created_at).label("last_date")
            )
            .where(
                Document.business_entity_id == entity.id,
                Document.deleted_at.is_(None),
            )
            .group_by(Document.document_type)
        )
        activity_result = await db.execute(last_activity_query)
        last_activities = {
            str(row.document_type): row.last_date.isoformat() if row.last_date else None
            for row in activity_result
        }

        # Baue Firmendaten auf - MULTI-TENANT: Dynamisch statt hardcoded
        company_service = get_company_service()
        all_companies = await company_service.get_company_short_names(db)
        company_stats = {}
        for company in all_companies:
            company_data = lexware_ids.get(company, {})
            # Finde passende Category-IDs für diese Firma (basierend auf Name-Pattern)
            company_doc_count = 0
            company_last_activity = None

            for cat_id, count in doc_counts.items():
                # Vereinfacht: Summiere alle Dokumente
                company_doc_count += count

            company_stats[company] = {
                "isPresent": company in company_presence,
                "customerNumber": company_data.get("kd_nr"),
                "supplierNumber": company_data.get("lief_nr"),
                "matchcode": company_data.get("matchcode"),
                "documentCount": company_doc_count if company in company_presence else 0,
                "lastActivity": last_activities.get(company) if company in company_presence else None,
            }

        items.append({
            "id": str(entity.id),
            "name": entity.name,
            "entityType": entity.entity_type,
            "isActive": entity.is_active,
            "companyPresence": company_presence,
            "companyStats": company_stats,
            "totalDocuments": sum(doc_counts.values()),
            "primaryCustomerNumber": entity.primary_customer_number,
            "primarySupplierNumber": entity.primary_supplier_number,
        })

    # Aggregierte Statistiken - MULTI-TENANT: Dynamisch pro Firma
    multi_company_count_query = select(func.count()).where(
        BusinessEntity.deleted_at.is_(None),
        func.jsonb_array_length(BusinessEntity.company_presence) > 1
    )
    multi_company_result = await db.execute(multi_company_count_query)
    multi_company_count = multi_company_result.scalar() or 0

    # Zaehle Entities pro einzelner Firma (dynamisch)
    company_only_counts: dict = {}
    for company_short in all_companies:
        single_company_query = select(func.count()).where(
            BusinessEntity.deleted_at.is_(None),
            BusinessEntity.company_presence == [company_short]
        )
        single_result = await db.execute(single_company_query)
        company_only_counts[f"{company_short}OnlyCount"] = single_result.scalar() or 0

    return {
        "items": items,
        "total": total,
        "page": page,
        "perPage": per_page,
        "totalPages": (total + per_page - 1) // per_page,
        "summary": {
            "multiCompanyCount": multi_company_count,
            **company_only_counts,  # Dynamisch: folieOnlyCount, messerOnlyCount, etc.
            "totalEntities": multi_company_count + sum(company_only_counts.values()),
        }
    }


# =============================================================================
# RELATIONSHIP DASHBOARD
# =============================================================================

@router.get(
    "/dashboard/stats",
    summary="Relationship Dashboard Statistiken",
    description="Aggregierte Statistiken für das Relationship-Dashboard"
)
async def get_relationship_dashboard(
    period: str = Query("30d", description="Zeitraum: 7d, 30d, 90d, 365d"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Gibt aggregierte Statistiken für das Relationship-Dashboard zurück.

    Enthält:
    - Top-Kunden nach Dokumentanzahl
    - Top-Lieferanten nach Dokumentanzahl
    - Trend-Daten für neue Dokumente
    - Verteilung nach Entity-Type
    """
    from datetime import timedelta

    # Zeitraum berechnen
    days_map = {"7d": 7, "30d": 30, "90d": 90, "365d": 365}
    days = days_map.get(period, 30)
    start_date = datetime.now(timezone.utc) - timedelta(days=days)

    # Top-Kunden nach Dokumentanzahl (letzte N Tage)
    top_customers_query = (
        select(
            BusinessEntity.id,
            BusinessEntity.name,
            BusinessEntity.display_name,
            BusinessEntity.primary_customer_number,
            func.count(Document.id).label("document_count"),
            func.max(Document.created_at).label("last_activity")
        )
        .join(Document, Document.business_entity_id == BusinessEntity.id, isouter=True)
        .where(
            BusinessEntity.deleted_at.is_(None),
            or_(
                BusinessEntity.entity_type == "customer",
                BusinessEntity.entity_type == "both",
            ),
            or_(
                Document.created_at >= start_date,
                Document.id.is_(None),  # Include entities with no documents
            ),
        )
        .group_by(BusinessEntity.id)
        .order_by(func.count(Document.id).desc())
        .limit(10)
    )
    top_customers_result = await db.execute(top_customers_query)
    top_customers = [
        {
            "id": str(row.id),
            "name": row.display_name or row.name,
            "customerNumber": row.primary_customer_number,
            "documentCount": row.document_count,
            "lastActivity": row.last_activity.isoformat() if row.last_activity else None,
        }
        for row in top_customers_result
    ]

    # Top-Lieferanten nach Dokumentanzahl
    top_suppliers_query = (
        select(
            BusinessEntity.id,
            BusinessEntity.name,
            BusinessEntity.display_name,
            BusinessEntity.primary_supplier_number,
            func.count(Document.id).label("document_count"),
            func.max(Document.created_at).label("last_activity")
        )
        .join(Document, Document.business_entity_id == BusinessEntity.id, isouter=True)
        .where(
            BusinessEntity.deleted_at.is_(None),
            or_(
                BusinessEntity.entity_type == "supplier",
                BusinessEntity.entity_type == "both",
            ),
            or_(
                Document.created_at >= start_date,
                Document.id.is_(None),
            ),
        )
        .group_by(BusinessEntity.id)
        .order_by(func.count(Document.id).desc())
        .limit(10)
    )
    top_suppliers_result = await db.execute(top_suppliers_query)
    top_suppliers = [
        {
            "id": str(row.id),
            "name": row.display_name or row.name,
            "supplierNumber": row.primary_supplier_number,
            "documentCount": row.document_count,
            "lastActivity": row.last_activity.isoformat() if row.last_activity else None,
        }
        for row in top_suppliers_result
    ]

    # Trend-Daten: Dokumente pro Tag (letzte N Tage)
    trend_query = (
        select(
            func.date_trunc('day', Document.created_at).label("date"),
            func.count(Document.id).label("count")
        )
        .where(
            Document.deleted_at.is_(None),
            Document.created_at >= start_date,
            Document.business_entity_id.isnot(None),
        )
        .group_by(func.date_trunc('day', Document.created_at))
        .order_by(func.date_trunc('day', Document.created_at))
    )
    trend_result = await db.execute(trend_query)
    trend_data = [
        {
            "date": row.date.strftime("%Y-%m-%d") if row.date else None,
            "count": row.count,
        }
        for row in trend_result
    ]

    # Verteilung nach Entity-Type
    type_distribution_query = (
        select(
            BusinessEntity.entity_type,
            func.count(BusinessEntity.id).label("count")
        )
        .where(BusinessEntity.deleted_at.is_(None))
        .group_by(BusinessEntity.entity_type)
    )
    type_result = await db.execute(type_distribution_query)
    type_distribution = {row.entity_type: row.count for row in type_result}

    # Gesamtstatistiken
    total_customers_query = select(func.count()).where(
        BusinessEntity.deleted_at.is_(None),
        or_(
            BusinessEntity.entity_type == "customer",
            BusinessEntity.entity_type == "both",
        ),
    )
    total_customers_result = await db.execute(total_customers_query)
    total_customers = total_customers_result.scalar() or 0

    total_suppliers_query = select(func.count()).where(
        BusinessEntity.deleted_at.is_(None),
        or_(
            BusinessEntity.entity_type == "supplier",
            BusinessEntity.entity_type == "both",
        ),
    )
    total_suppliers_result = await db.execute(total_suppliers_query)
    total_suppliers = total_suppliers_result.scalar() or 0

    # Dokumente mit Entity-Verknüpfung im Zeitraum
    linked_docs_query = select(func.count()).where(
        Document.deleted_at.is_(None),
        Document.created_at >= start_date,
        Document.business_entity_id.isnot(None),
    )
    linked_docs_result = await db.execute(linked_docs_query)
    linked_documents = linked_docs_result.scalar() or 0

    # Neue Entities im Zeitraum
    new_entities_query = select(func.count()).where(
        BusinessEntity.deleted_at.is_(None),
        BusinessEntity.created_at >= start_date,
    )
    new_entities_result = await db.execute(new_entities_query)
    new_entities = new_entities_result.scalar() or 0

    return {
        "period": period,
        "summary": {
            "totalCustomers": total_customers,
            "totalSuppliers": total_suppliers,
            "linkedDocuments": linked_documents,
            "newEntities": new_entities,
        },
        "topCustomers": top_customers,
        "topSuppliers": top_suppliers,
        "documentTrend": trend_data,
        "typeDistribution": type_distribution,
    }


# =============================================================================
# ENTITY GRAPH
# =============================================================================

@router.get(
    "/graph/data",
    summary="Entity-Graph-Daten",
    description="Liefert Nodes und Edges für die Entity-Graph-Visualisierung"
)
async def get_entity_graph_data(
    entity_type: Optional[EntityType] = Query(
        None, description="Filter nach Entity-Typ"
    ),
    min_documents: int = Query(
        1, ge=0, description="Minimum Dokumente für Anzeige"
    ),
    include_documents: bool = Query(
        False, description="Dokument-Nodes einbeziehen"
    ),
    limit: int = Query(
        50, ge=10, le=200, description="Maximale Anzahl Entities"
    ),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Gibt Graph-Daten für React Flow zurück.

    **Nodes:**
    - Entity-Nodes (Kunden/Lieferanten)
    - Optional: Dokument-Nodes

    **Edges:**
    - Entity-zu-Dokument (wenn include_documents=True)
    - Entity-zu-Entity (wenn gemeinsame Dokumente)

    **Verwendung:**
    Für die Visualisierung mit @xyflow/react.
    """
    # Basis-Query: Entities mit Dokument-Anzahl
    entity_query = (
        select(
            BusinessEntity.id,
            BusinessEntity.name,
            BusinessEntity.display_name,
            BusinessEntity.entity_type,
            BusinessEntity.primary_customer_number,
            BusinessEntity.primary_supplier_number,
            BusinessEntity.company_presence,
            func.count(Document.id).label("document_count"),
        )
        .join(Document, Document.business_entity_id == BusinessEntity.id, isouter=True)
        .where(
            BusinessEntity.deleted_at.is_(None),
            Document.deleted_at.is_(None),
        )
        .group_by(BusinessEntity.id)
        .having(func.count(Document.id) >= min_documents)
        .order_by(func.count(Document.id).desc())
        .limit(limit)
    )

    if entity_type:
        entity_query = entity_query.where(
            BusinessEntity.entity_type == entity_type.value
        )

    entity_result = await db.execute(entity_query)
    entities = entity_result.all()

    nodes = []
    edges = []
    entity_ids = set()

    # Erstelle Entity-Nodes
    for idx, entity in enumerate(entities):
        entity_ids.add(str(entity.id))

        # Berechne Position im Kreis
        angle = (2 * 3.14159 * idx) / max(len(entities), 1)
        radius = 300
        x = 400 + radius * (1 if idx % 2 == 0 else -1) * (0.5 + (idx % 3) * 0.3)
        y = 300 + radius * (1 if idx % 4 < 2 else -1) * (0.3 + (idx % 5) * 0.2)

        # Node-Typ basierend auf Entity-Type
        node_type = "customer" if entity.entity_type in ("customer", "both") else "supplier"

        nodes.append({
            "id": str(entity.id),
            "type": "entityNode",
            "position": {"x": x, "y": y},
            "data": {
                "id": str(entity.id),
                "name": entity.display_name or entity.name,
                "entityType": entity.entity_type,
                "nodeType": node_type,
                "customerNumber": entity.primary_customer_number,
                "supplierNumber": entity.primary_supplier_number,
                "documentCount": entity.document_count,
                "companyPresence": entity.company_presence or [],
            },
        })

    # Finde gemeinsame Dokumente zwischen Entities (für Edges)
    if len(entity_ids) > 1:
        # Suche Dokumente die mit mehreren Entities verknüpft sind
        # (über manuelle Verknüpfung oder gleiche Kategorie)
        shared_docs_query = (
            select(
                Document.id.label("doc_id"),
                Document.business_entity_id.label("entity_id"),
            )
            .where(
                Document.deleted_at.is_(None),
                Document.business_entity_id.in_([UUID(eid) for eid in entity_ids]),
            )
        )
        shared_result = await db.execute(shared_docs_query)

        # Gruppiere Dokumente nach Entity
        entity_docs = {}
        for row in shared_result:
            eid = str(row.entity_id)
            if eid not in entity_docs:
                entity_docs[eid] = set()
            entity_docs[eid].add(str(row.doc_id))

    # Optional: Fuege Dokument-Nodes hinzu
    if include_documents:
        doc_query = (
            select(Document)
            .where(
                Document.deleted_at.is_(None),
                Document.business_entity_id.in_([UUID(eid) for eid in entity_ids]),
            )
            .order_by(Document.created_at.desc())
            .limit(100)  # Begrenzen um Graph nicht zu überladen
        )
        doc_result = await db.execute(doc_query)
        documents = doc_result.scalars().all()

        doc_positions = {}
        for idx, doc in enumerate(documents):
            doc_id = str(doc.id)
            entity_id = str(doc.business_entity_id)

            # Position nahe der Entity
            base_x = next(
                (n["position"]["x"] for n in nodes if n["id"] == entity_id),
                400
            )
            base_y = next(
                (n["position"]["y"] for n in nodes if n["id"] == entity_id),
                300
            )

            # Versetze leicht
            offset_angle = (2 * 3.14159 * idx) / max(len(documents), 1)
            doc_x = base_x + 100 * (1 if idx % 2 == 0 else -1)
            doc_y = base_y + 80 * (1 if idx % 3 == 0 else -1)

            doc_positions[doc_id] = {"x": doc_x, "y": doc_y}

            # Dokument-Typ Icon
            doc_type_map = {
                "invoice": "receipt",
                "delivery_note": "truck",
                "order": "file-check",
            }
            doc_icon = doc_type_map.get(doc.status, "file")

            nodes.append({
                "id": f"doc-{doc_id}",
                "type": "documentNode",
                "position": doc_positions[doc_id],
                "data": {
                    "id": doc_id,
                    "name": doc.original_filename or doc.filename,
                    "documentType": doc.status,
                    "icon": doc_icon,
                    "mimeType": doc.mime_type,
                },
            })

            # Edge von Entity zu Dokument
            edges.append({
                "id": f"edge-{entity_id}-{doc_id}",
                "source": entity_id,
                "target": f"doc-{doc_id}",
                "type": "smoothstep",
                "animated": False,
                "style": {"stroke": "#94a3b8", "strokeWidth": 1},
            })

    # Statistiken
    customer_count = sum(
        1 for n in nodes
        if n.get("type") == "entityNode" and n["data"].get("nodeType") == "customer"
    )
    supplier_count = sum(
        1 for n in nodes
        if n.get("type") == "entityNode" and n["data"].get("nodeType") == "supplier"
    )
    doc_node_count = sum(1 for n in nodes if n.get("type") == "documentNode")

    return {
        "nodes": nodes,
        "edges": edges,
        "statistics": {
            "totalNodes": len(nodes),
            "entityNodes": len(entity_ids),
            "documentNodes": doc_node_count,
            "customerCount": customer_count,
            "supplierCount": supplier_count,
            "totalEdges": len(edges),
        },
    }


# =============================================================================
# ENTITY TIMELINE
# =============================================================================

@router.get(
    "/{entity_id}/timeline",
    summary="Entity-Timeline abrufen",
    description="Chronologische Aktivitaeten eines Geschäftspartners"
)
async def get_entity_timeline(
    entity_id: UUID,
    limit: int = Query(50, ge=1, le=200, description="Maximale Anzahl Events"),
    event_types: Optional[List[str]] = Query(
        None,
        description="Filter: document_linked, entity_updated, invoice_created"
    ),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Gibt chronologische Events für einen Geschäftspartner zurück.

    **Event-Typen:**
    - **document_linked**: Dokument wurde verknüpft
    - **entity_created**: Geschäftspartner wurde erstellt
    - **entity_updated**: Geschäftspartner wurde aktualisiert

    **Response:**
    Sortiert nach Datum (neueste zuerst), mit Event-Typ, Beschreibung und Metadaten.
    """
    # Prüfe ob Entity existiert
    entity_result = await db.execute(
        select(BusinessEntity).where(
            BusinessEntity.id == entity_id,
            BusinessEntity.deleted_at.is_(None)
        )
    )
    entity = entity_result.scalar_one_or_none()

    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Geschäftspartner nicht gefunden"
        )

    events = []

    # 1. Entity Created Event
    if not event_types or "entity_created" in event_types:
        events.append({
            "id": f"created-{entity.id}",
            "eventType": "entity_created",
            "title": "Geschäftspartner erstellt",
            "description": f"{entity.name} wurde angelegt",
            "timestamp": entity.created_at.isoformat() if entity.created_at else None,
            "icon": "plus-circle",
            "metadata": {
                "entityType": entity.entity_type,
            }
        })

    # 2. Entity Updated Event (nur wenn updated_at != created_at)
    if not event_types or "entity_updated" in event_types:
        if entity.updated_at and entity.created_at:
            if entity.updated_at > entity.created_at:
                events.append({
                    "id": f"updated-{entity.id}",
                    "eventType": "entity_updated",
                    "title": "Geschäftspartner aktualisiert",
                    "description": f"{entity.name} wurde bearbeitet",
                    "timestamp": entity.updated_at.isoformat(),
                    "icon": "edit",
                    "metadata": {}
                })

    # 3. Document Linked Events
    if not event_types or "document_linked" in event_types:
        doc_query = (
            select(Document)
            .where(
                Document.business_entity_id == entity_id,
                Document.deleted_at.is_(None),
            )
            .order_by(Document.created_at.desc())
            .limit(limit)
        )
        doc_result = await db.execute(doc_query)
        documents = doc_result.scalars().all()

        for doc in documents:
            # Bestimme Dokument-Typ für Icon
            doc_type = doc.status or "document"
            icon_map = {
                "invoice": "receipt",
                "delivery_note": "truck",
                "order": "file-check",
                "offer": "file-text",
                "payment": "banknote",
            }
            icon = icon_map.get(doc_type, "file")

            events.append({
                "id": f"doc-{doc.id}",
                "eventType": "document_linked",
                "title": f"Dokument verknüpft",
                "description": doc.original_filename or doc.filename,
                "timestamp": doc.created_at.isoformat() if doc.created_at else None,
                "icon": icon,
                "metadata": {
                    "documentId": str(doc.id),
                    "filename": doc.original_filename or doc.filename,
                    "documentType": doc.status,
                    "mimeType": doc.mime_type,
                }
            })

    # Sortiere alle Events nach Timestamp (neueste zuerst)
    events.sort(
        key=lambda e: e.get("timestamp") or "",
        reverse=True
    )

    # Limitiere
    events = events[:limit]

    return {
        "entityId": str(entity_id),
        "entityName": entity.name,
        "events": events,
        "total": len(events),
    }


# =============================================================================
# GET SINGLE (dynamische Route - MUSS nach statischen Routen stehen!)
# =============================================================================

@router.get(
    "/{entity_id}",
    response_model=BusinessEntityDetailResponse,
    summary="Geschäftspartner abrufen",
    description="Ruft detaillierte Informationen zu einem Geschäftspartner ab"
)
async def get_entity(
    entity_id: UUID,
    include_documents: bool = Query(False, description="Dokumente mitladen"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> BusinessEntityDetailResponse:
    """
    Ruft einen Geschäftspartner mit allen Details ab.

    Optional können verknüpfte Dokumente mitgeladen werden.
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
            detail="Geschäftspartner nicht gefunden"
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
    summary="Geschäftspartner erstellen",
    description="Erstellt einen neuen Geschäftspartner"
)
async def create_entity(
    data: BusinessEntityCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> BusinessEntityResponse:
    """
    Erstellt einen neuen Geschäftspartner.

    **Pflichtfelder:**
    - **name**: Firmenname
    - **entity_type**: customer, supplier, both

    **Optionale Felder:**
    - vat_id: USt-IdNr (wird auf Duplikate geprüft)
    - iban: Bankverbindung
    - Adresse, Kontakt, etc.
    """
    # Prüfen auf Duplikate
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
                detail=f"Geschäftspartner mit USt-IdNr {data.vat_id} existiert bereits"
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
                detail="Geschäftspartner mit dieser IBAN existiert bereits"
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
    summary="Geschäftspartner aktualisieren",
    description="Aktualisiert einen bestehenden Geschäftspartner"
)
async def update_entity(
    entity_id: UUID,
    data: BusinessEntityUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> BusinessEntityResponse:
    """
    Aktualisiert einen Geschäftspartner.

    Nur geänderte Felder werden aktualisiert.
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
            detail="Geschäftspartner nicht gefunden"
        )

    # Duplikat-Prüfung bei Änderung von vat_id oder iban
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
    summary="Geschäftspartner löschen",
    description="Löscht einen Geschäftspartner (Soft-Delete)"
)
async def delete_entity(
    entity_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """
    Löscht einen Geschäftspartner (Soft-Delete).

    Verknüpfte Dokumente werden NICHT gelöscht, nur die Verknüpfung.
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
            detail="Geschäftspartner nicht gefunden"
        )

    # Soft-Delete
    entity.deleted_at = datetime.now(timezone.utc)

    # Dokument-Verknüpfungen aufheben
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

    return MessageResponse(message="Geschäftspartner erfolgreich gelöscht")


# =============================================================================
# DOCUMENTS
# =============================================================================

@router.get(
    "/{entity_id}/documents",
    summary="Verknüpfte Dokumente",
    description="Listet alle Dokumente eines Geschäftspartners"
)
async def get_entity_documents(
    entity_id: UUID,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Listet alle Dokumente die mit diesem Geschäftspartner verknüpft sind.
    """
    # Entity prüfen
    entity_result = await db.execute(
        select(BusinessEntity).where(
            BusinessEntity.id == entity_id,
            BusinessEntity.deleted_at.is_(None)
        )
    )
    if not entity_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Geschäftspartner nicht gefunden"
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
    description="Extrahiert Geschäftspartner-Informationen aus OCR-Text"
)
async def extract_entities(
    data: EntityExtractionRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> EntityExtractionResponse:
    """
    Extrahiert Geschäftspartner-Informationen aus OCR-Text.

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
    summary="Duplikate zusammenführen",
    description="Führt mehrere Entity-Einträge zu einem zusammen"
)
async def merge_entities(
    data: EntityMergeRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> BusinessEntityResponse:
    """
    Führt mehrere Geschäftspartner-Einträge zu einem zusammen.

    - **target_id**: Entity die erhalten bleibt
    - **source_ids**: Entities die zusammengeführt werden

    Alle Dokumente der source_ids werden auf target_id umgehaengt.
    Source-Entities werden als gelöscht markiert.
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
            detail="Ziel-Geschäftspartner nicht gefunden"
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

        # Name-Aliase übernehmen
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

        # Source als gelöscht markieren
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
    description="Markiert einen Geschäftspartner als manuell verifiziert"
)
async def verify_entity(
    entity_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> BusinessEntityResponse:
    """
    Markiert einen Geschäftspartner als manuell verifiziert.

    Verifizierte Entities haben höheres Vertrauen bei Auto-Matching.
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
            detail="Geschäftspartner nicht gefunden"
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
    description="Gibt die Firmen-Ordner (Folie, Spargelmesser) zurück"
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
            detail="Geschäftspartner nicht gefunden"
        )

    # Company presence aus Entity oder lexware_ids
    company_presence = entity.company_presence or []
    if not company_presence and entity.lexware_ids:
        company_presence = list(entity.lexware_ids.keys())

    # Lade Company Service für dynamische Namen
    company_service = get_company_service()

    # Falls leer, default alle aktiven Firmen (MULTI-TENANT)
    if not company_presence:
        company_presence = await company_service.get_company_short_names(db)

    # Lade Display-Namen dynamisch aus DB
    folder_names = await company_service.get_company_display_map(db)

    folders = []

    for company_id in company_presence:
        # Normalize ID via Company Service (Legacy-Alias-Support)
        normalized_id = company_service.normalize_company_short_name(company_id)

        # Dokumente für diese Entity + Firma zaehlen
        doc_counts = await _count_documents_by_category(db, entity_id, normalized_id)

        # Letztes Dokument-Datum
        last_doc = await _get_last_document_date_for_folder(db, entity_id, normalized_id)

        total_docs = sum(doc_counts.values())

        folders.append({
            "id": normalized_id,
            "name": folder_names.get(normalized_id, company_service.get_legacy_display_name(company_id)),
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
    # Entity prüfen
    entity_result = await db.execute(
        select(BusinessEntity).where(
            BusinessEntity.id == entity_id,
            BusinessEntity.deleted_at.is_(None)
        )
    )
    if not entity_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Geschäftspartner nicht gefunden"
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
# RISK SCORING - Static Routes (must be before /{entity_id})
# =============================================================================

@router.get(
    "/risk",
    summary="Alle Entities mit Risiko-Scores",
    description="Listet alle Geschäftspartner mit ihren Risiko-Scores auf"
)
async def get_all_entities_with_risk(
    page: int = Query(1, ge=1, description="Seitennummer"),
    per_page: int = Query(20, ge=1, le=100, description="Einträge pro Seite"),
    entity_type: Optional[EntityType] = Query(None, description="Nach Typ filtern"),
    min_score: Optional[float] = Query(None, ge=0, le=100, description="Minimum Risk Score"),
    max_score: Optional[float] = Query(None, ge=0, le=100, description="Maximum Risk Score"),
    risk_level: Optional[str] = Query(
        None,
        description="Risiko-Level: low (0-25), medium (25-50), high (50-75), critical (75-100)"
    ),
    sort_by: str = Query("risk_score", description="Sortierfeld: risk_score, name, updated_at"),
    sort_order: SortOrder = Query(SortOrder.DESC, description="Sortierrichtung"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Listet alle Geschäftspartner mit Risiko-Scores auf.

    **Filter:**
    - **entity_type**: customer, supplier, both
    - **min_score/max_score**: Bereich filtern
    - **risk_level**: low, medium, high, critical

    **Response:**
    Paginierte Liste mit Risiko-Informationen pro Entity.
    """
    query = select(BusinessEntity).where(
        BusinessEntity.deleted_at.is_(None),
        BusinessEntity.risk_score.isnot(None),
    )

    # Filter
    if entity_type:
        query = query.where(BusinessEntity.entity_type == entity_type.value)

    if min_score is not None:
        query = query.where(BusinessEntity.risk_score >= min_score)

    if max_score is not None:
        query = query.where(BusinessEntity.risk_score <= max_score)

    if risk_level:
        level_ranges = {
            "low": (0, 25),
            "medium": (25, 50),
            "high": (50, 75),
            "critical": (75, 100),
        }
        if risk_level.lower() in level_ranges:
            low, high = level_ranges[risk_level.lower()]
            query = query.where(
                BusinessEntity.risk_score >= low,
                BusinessEntity.risk_score < high if risk_level.lower() != "critical" else BusinessEntity.risk_score <= high,
            )

    # Count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Sorting
    sort_columns = {
        "risk_score": BusinessEntity.risk_score,
        "name": BusinessEntity.name,
        "updated_at": BusinessEntity.updated_at,
        "payment_behavior_score": BusinessEntity.payment_behavior_score,
    }
    sort_column = sort_columns.get(sort_by, BusinessEntity.risk_score)
    if sort_order == SortOrder.DESC:
        sort_column = sort_column.desc().nulls_last()
    else:
        sort_column = sort_column.asc().nulls_last()
    query = query.order_by(sort_column)

    # Pagination
    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page)

    result = await db.execute(query)
    entities = result.scalars().all()

    def get_risk_level(score: float) -> str:
        if score is None:
            return "unknown"
        if score < 25:
            return "low"
        if score < 50:
            return "medium"
        if score < 75:
            return "high"
        return "critical"

    items = [
        {
            "id": str(e.id),
            "name": e.display_name or e.name,
            "entityType": e.entity_type,
            "riskScore": e.risk_score,
            "paymentBehaviorScore": e.payment_behavior_score,
            "riskLevel": get_risk_level(e.risk_score),
            "riskFactors": e.risk_factors or {},
            "calculatedAt": e.risk_calculated_at.isoformat() if e.risk_calculated_at else None,
        }
        for e in entities
    ]

    return {
        "items": items,
        "total": total,
        "page": page,
        "perPage": per_page,
        "totalPages": (total + per_page - 1) // per_page if total > 0 else 0,
    }


@router.get(
    "/risk/high-risk",
    summary="High-Risk Entities",
    description="Listet Geschäftspartner mit hohem Risiko (Score >= 50)"
)
async def get_high_risk_entities(
    page: int = Query(1, ge=1, description="Seitennummer"),
    per_page: int = Query(20, ge=1, le=100, description="Einträge pro Seite"),
    entity_type: Optional[EntityType] = Query(None, description="Nach Typ filtern"),
    min_score: float = Query(50, ge=0, le=100, description="Minimum Risk Score (default: 50)"),
    sort_by: str = Query("risk_score", description="Sortierfeld"),
    sort_order: SortOrder = Query(SortOrder.DESC, description="Sortierrichtung"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Listet alle Geschäftspartner mit hohem Risiko auf.

    Standard: Score >= 50 (HIGH und CRITICAL Level)

    **Response:**
    Paginierte Liste mit detaillierten Risiko-Informationen.
    """
    query = select(BusinessEntity).where(
        BusinessEntity.deleted_at.is_(None),
        BusinessEntity.risk_score.isnot(None),
        BusinessEntity.risk_score >= min_score,
    )

    if entity_type:
        query = query.where(BusinessEntity.entity_type == entity_type.value)

    # Count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Sorting
    sort_columns = {
        "risk_score": BusinessEntity.risk_score,
        "name": BusinessEntity.name,
        "updated_at": BusinessEntity.updated_at,
    }
    sort_column = sort_columns.get(sort_by, BusinessEntity.risk_score)
    if sort_order == SortOrder.DESC:
        sort_column = sort_column.desc().nulls_last()
    else:
        sort_column = sort_column.asc().nulls_last()
    query = query.order_by(sort_column)

    # Pagination
    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page)

    result = await db.execute(query)
    entities = result.scalars().all()

    def get_risk_level(score: float) -> str:
        if score < 25:
            return "low"
        if score < 50:
            return "medium"
        if score < 75:
            return "high"
        return "critical"

    items = [
        {
            "id": str(e.id),
            "name": e.display_name or e.name,
            "entityType": e.entity_type,
            "riskScore": e.risk_score,
            "paymentBehaviorScore": e.payment_behavior_score,
            "riskLevel": get_risk_level(e.risk_score),
            "riskFactors": e.risk_factors or {},
            "calculatedAt": e.risk_calculated_at.isoformat() if e.risk_calculated_at else None,
        }
        for e in entities
    ]

    return {
        "items": items,
        "total": total,
        "page": page,
        "perPage": per_page,
        "totalPages": (total + per_page - 1) // per_page if total > 0 else 0,
    }


@router.get(
    "/risk/statistics",
    summary="Risiko-Statistiken",
    description="Aggregierte Risiko-Statistiken über alle Geschäftspartner"
)
async def get_risk_statistics(
    entity_type: Optional[EntityType] = Query(None, description="Nach Typ filtern"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Gibt aggregierte Risiko-Statistiken zurück.

    **Response:**
    - **totalEntities**: Anzahl aller Entities mit Risk Score
    - **highRiskCount**: Anzahl mit Score >= 50
    - **criticalRiskCount**: Anzahl mit Score >= 75
    - **averageRiskScore**: Durchschnittlicher Risk Score
    - **riskDistribution**: Verteilung nach Level
    - **topRiskFactors**: Häufigste Risiko-Faktoren
    """
    base_filter = [
        BusinessEntity.deleted_at.is_(None),
        BusinessEntity.risk_score.isnot(None),
    ]
    if entity_type:
        base_filter.append(BusinessEntity.entity_type == entity_type.value)

    # Total entities with risk score
    total_query = select(func.count()).where(*base_filter)
    total_result = await db.execute(total_query)
    total_entities = total_result.scalar() or 0

    # High risk count (>= 50)
    high_risk_query = select(func.count()).where(
        *base_filter,
        BusinessEntity.risk_score >= 50,
    )
    high_risk_result = await db.execute(high_risk_query)
    high_risk_count = high_risk_result.scalar() or 0

    # Critical risk count (>= 75)
    critical_risk_query = select(func.count()).where(
        *base_filter,
        BusinessEntity.risk_score >= 75,
    )
    critical_risk_result = await db.execute(critical_risk_query)
    critical_risk_count = critical_risk_result.scalar() or 0

    # Average risk score
    avg_query = select(func.avg(BusinessEntity.risk_score)).where(*base_filter)
    avg_result = await db.execute(avg_query)
    average_risk_score = avg_result.scalar() or 0

    # Risk distribution
    distribution = {"low": 0, "medium": 0, "high": 0, "critical": 0}

    low_query = select(func.count()).where(
        *base_filter,
        BusinessEntity.risk_score < 25,
    )
    distribution["low"] = (await db.execute(low_query)).scalar() or 0

    medium_query = select(func.count()).where(
        *base_filter,
        BusinessEntity.risk_score >= 25,
        BusinessEntity.risk_score < 50,
    )
    distribution["medium"] = (await db.execute(medium_query)).scalar() or 0

    high_query = select(func.count()).where(
        *base_filter,
        BusinessEntity.risk_score >= 50,
        BusinessEntity.risk_score < 75,
    )
    distribution["high"] = (await db.execute(high_query)).scalar() or 0

    critical_query = select(func.count()).where(
        *base_filter,
        BusinessEntity.risk_score >= 75,
    )
    distribution["critical"] = (await db.execute(critical_query)).scalar() or 0

    # Top risk factors (aggregate from risk_factors JSONB)
    # This is a simplified version - in production you'd want more sophisticated aggregation
    top_factors = [
        {"name": "payment_delay", "label": "Zahlungsverzögerung", "weight": 0.35},
        {"name": "default_rate", "label": "Ausfallrate", "weight": 0.25},
        {"name": "invoice_volume", "label": "Rechnungsvolumen", "weight": 0.15},
        {"name": "document_frequency", "label": "Dokumentenfrequenz", "weight": 0.10},
        {"name": "relationship_age", "label": "Beziehungsdauer", "weight": 0.15},
    ]

    return {
        "totalEntities": total_entities,
        "highRiskCount": high_risk_count,
        "criticalRiskCount": critical_risk_count,
        "averageRiskScore": round(average_risk_score, 2) if average_risk_score else 0,
        "riskDistribution": distribution,
        "topRiskFactors": top_factors,
        "entityType": entity_type.value if entity_type else "all",
    }


# =============================================================================
# RISK SCORING - Dynamic Routes
# =============================================================================

@router.get(
    "/{entity_id}/risk",
    summary="Risiko-Score abrufen",
    description="Liefert den aktuellen Risiko-Score und Faktoren eines Geschäftspartners"
)
async def get_entity_risk_score(
    entity_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Ruft den Risiko-Score eines Geschäftspartners ab.

    **Response:**
    - **riskScore**: Gesamt-Risiko (0-100, höher = riskanter)
    - **paymentBehaviorScore**: Zahlungsverhalten (0-100, höher = besser)
    - **riskFactors**: Detaillierte Faktor-Aufschluesselung
    - **calculatedAt**: Zeitpunkt der letzten Berechnung
    """
    entity_result = await db.execute(
        select(BusinessEntity).where(
            BusinessEntity.id == entity_id,
            BusinessEntity.deleted_at.is_(None)
        )
    )
    entity = entity_result.scalar_one_or_none()

    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Geschäftspartner nicht gefunden"
        )

    return {
        "entityId": str(entity.id),
        "entityName": entity.name,
        "riskScore": entity.risk_score,
        "paymentBehaviorScore": entity.payment_behavior_score,
        "riskFactors": entity.risk_factors or {},
        "calculatedAt": entity.risk_calculated_at.isoformat() if entity.risk_calculated_at else None,
    }


@router.post(
    "/{entity_id}/risk/calculate",
    summary="Risiko-Score berechnen",
    description="Berechnet den Risiko-Score für einen Geschäftspartner neu"
)
async def calculate_entity_risk_score(
    entity_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Berechnet den Risiko-Score eines Geschäftspartners neu.

    Die Berechnung berücksichtigt:
    - Zahlungsverzögerungen
    - Ausfallraten
    - Rechnungsvolumen
    - Dokumentenfrequenz
    - Beziehungsdauer
    """
    from app.services.risk_scoring_service import get_risk_scoring_service

    risk_service = get_risk_scoring_service()
    entity = await risk_service.update_entity_risk_score(db, entity_id)

    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Geschäftspartner nicht gefunden"
        )

    return {
        "entityId": str(entity.id),
        "entityName": entity.name,
        "riskScore": entity.risk_score,
        "paymentBehaviorScore": entity.payment_behavior_score,
        "riskFactors": entity.risk_factors or {},
        "calculatedAt": entity.risk_calculated_at.isoformat() if entity.risk_calculated_at else None,
    }


@router.get(
    "/{entity_id}/risk/trend",
    summary="Risiko-Score Trend",
    description="Gibt die historische Entwicklung des Risiko-Scores zurück"
)
async def get_entity_risk_trend(
    entity_id: UUID,
    days: int = Query(30, ge=7, le=365, description="Anzahl Tage für Trend"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Gibt die historische Entwicklung des Risiko-Scores zurück.

    **Hinweis:** Da Risk Scores aktuell nicht historisch gespeichert werden,
    generiert diese Funktion eine simulierte Trend-Linie basierend auf
    dem aktuellen Score mit leichter Variation.

    In einer vollständigen Implementierung wuerde hier eine
    RiskScoreHistory-Tabelle abgefragt werden.

    **Response:**
    - **trend**: Array mit {date, riskScore} Objekten
    - **currentScore**: Aktueller Risk Score
    - **changePercent**: Veränderung in Prozent (simuliert)
    """
    from datetime import timedelta
    import random

    # Entity prüfen
    entity_result = await db.execute(
        select(BusinessEntity).where(
            BusinessEntity.id == entity_id,
            BusinessEntity.deleted_at.is_(None)
        )
    )
    entity = entity_result.scalar_one_or_none()

    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Geschäftspartner nicht gefunden"
        )

    current_score = entity.risk_score or 0

    # Generiere simulierten Trend basierend auf aktuellem Score
    # In Produktion: Query auf RiskScoreHistory-Tabelle
    trend = []
    today = datetime.now(timezone.utc).date()

    # Seed basierend auf Entity-ID für konsistente Ergebnisse
    random.seed(str(entity_id))

    # Startpunkt: Score vor 'days' Tagen (leicht unterschiedlich)
    base_score = max(0, min(100, current_score + random.uniform(-15, 15)))

    for i in range(days):
        date = today - timedelta(days=days - i - 1)
        # Lineare Interpolation mit leichtem Rauschen
        progress = i / max(days - 1, 1)
        score = base_score + (current_score - base_score) * progress
        noise = random.uniform(-3, 3)
        score = max(0, min(100, score + noise))

        trend.append({
            "date": date.isoformat(),
            "riskScore": round(score, 1),
        })

    # Letzter Punkt ist der aktuelle Score
    trend[-1]["riskScore"] = current_score

    # Change berechnen
    first_score = trend[0]["riskScore"] if trend else current_score
    change_percent = ((current_score - first_score) / max(first_score, 1)) * 100 if first_score else 0

    return {
        "entityId": str(entity.id),
        "entityName": entity.name,
        "trend": trend,
        "currentScore": current_score,
        "firstScore": first_score,
        "changePercent": round(change_percent, 1),
        "days": days,
    }


@router.post(
    "/risk/calculate-all",
    summary="Alle Risiko-Scores berechnen",
    description="Berechnet Risiko-Scores für alle aktiven Geschäftspartner"
)
async def calculate_all_risk_scores(
    entity_type: Optional[EntityType] = Query(None, description="Nur bestimmten Typ berechnen"),
    limit: int = Query(1000, ge=1, le=10000, description="Maximale Anzahl zu berechnender Entities"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Berechnet Risiko-Scores für alle (oder gefilterte) Geschäftspartner.

    **Filter:**
    - **entity_type**: Nur customer, supplier, oder both berechnen
    - **limit**: Maximale Anzahl (Standard: 1000)
    """
    from app.services.risk_scoring_service import get_risk_scoring_service

    risk_service = get_risk_scoring_service()
    updated_count = await risk_service.update_all_risk_scores(
        db,
        entity_type=entity_type.value if entity_type else None,
        limit=limit,
    )

    return {
        "message": f"Risiko-Scores berechnet für {updated_count} Geschäftspartner",
        "updatedCount": updated_count,
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
        # Wenn erstes Wort ein Vorname sein könnte, zweites nehmen
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

        # Gesamtzahl Dokumente für diese Entity
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
    """Zählt Dokumente pro Kategorie für eine Entity/Firma."""
    # Basis-Kategorien für alle Ordner
    categories = [
        "anfragen", "angebote", "auftragsbestaetigung", "lieferscheine",
        "rechnungen", "storno", "mahnungen", "offene_rechnungen",
        "offene_angebote", "offene_anfragen", "reklamation",
        "kommunikation", "archiv"
    ]

    # Druckdaten nur für Spargelmesser-Ordner
    if folder_id == "messer":
        categories.append("druckdaten")

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
        "auftragsbestätigung": "auftragsbestaetigung",  # Mit Umlaut (Fallback)
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
        "druckdaten": "druckdaten",  # NUR für Spargelmesser-Kunden!
    }

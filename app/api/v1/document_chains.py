# -*- coding: utf-8 -*-
"""
Document Chain API Endpoints.

REST API fuer Auftragsketten-Tracking:
- Verknuepfung von Dokumenten (Angebot → Auftrag → Lieferschein → Rechnung)
- Automatische Erkennung zusammengehoeriger Dokumente
- Differenz-Erkennung zwischen Dokumenten
- Chain-Visualisierung

Feinpoliert und durchdacht - Enterprise Document Chain Tracking.
"""

from typing import Optional, List
from uuid import UUID
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.db.models import User, Document
from app.api.dependencies import get_db, get_current_active_user
from app.core.safe_errors import safe_error_detail, safe_error_log
from app.services.document_chain_service import (
    DocumentChainService,
    RelationshipType,
    DiscrepancySeverity,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/document-chains", tags=["Document Chains"])


# =============================================================================
# CHAIN MANAGEMENT
# =============================================================================


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Auftragskette erstellen",
    description="Erstellt eine neue Auftragskette aus mehreren Dokumenten"
)
async def create_chain(
    document_ids: List[UUID],
    chain_id: Optional[str] = Query(None, description="Optionale Chain-ID (sonst auto-generiert)"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Erstellt eine neue Auftragskette.

    **Parameter:**
    - document_ids: Liste von Dokument-IDs (min. 1)
    - chain_id: Optionale eigene Chain-ID (Format: CHAIN-YYYY-NNNNN)

    **Response:**
    - chain_id: Die ID der erstellten Kette
    - document_count: Anzahl der verknuepften Dokumente
    """
    if not document_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mindestens ein Dokument erforderlich"
        )

    company_id = current_user.company_id
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer hat keine Firmenzuordnung"
        )

    # SECURITY: Pruefen ob alle Dokumente dem User gehoeren
    for doc_id in document_ids:
        result = await db.execute(
            select(Document).where(
                Document.id == doc_id,
                Document.owner_id == current_user.id,
                Document.deleted_at.is_(None),
            )
        )
        if not result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Dokument {doc_id} nicht gefunden oder keine Berechtigung"
            )

    chain_service = DocumentChainService()

    try:
        new_chain_id = await chain_service.create_chain(
            db=db,
            documents=document_ids,
            company_id=company_id,
            user_id=current_user.id,
            chain_id=chain_id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Dokumentenkette")
        )

    await db.commit()

    logger.info(
        "document_chain_created",
        chain_id=new_chain_id,
        document_count=len(document_ids),
    )

    return {
        "chain_id": new_chain_id,
        "document_count": len(document_ids),
        "message": "Auftragskette erfolgreich erstellt",
    }


@router.get(
    "/{chain_id}",
    summary="Auftragskette abrufen",
    description="Liefert alle Dokumente und Details einer Auftragskette"
)
async def get_chain(
    chain_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Ruft eine Auftragskette ab.

    **Response:**
    - chain_id: ID der Kette
    - documents: Liste der Dokumente mit Position und Details
    - has_quote/has_order/has_delivery_note/has_invoice: Vorhandene Dokumenttypen
    - open_discrepancies: Anzahl offener Abweichungen
    - is_complete: Ob alle erwarteten Dokumente vorhanden sind
    """
    company_id = current_user.company_id
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer hat keine Firmenzuordnung"
        )

    chain_service = DocumentChainService()
    chain = await chain_service.get_chain(db=db, chain_id=chain_id, company_id=company_id)

    if not chain:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Auftragskette nicht gefunden"
        )

    return {
        "chain_id": chain.chain_id,
        "document_count": chain.document_count,
        "chain_started_at": chain.chain_started_at.isoformat(),
        "chain_updated_at": chain.chain_updated_at.isoformat(),
        "has_quote": chain.has_quote,
        "has_order": chain.has_order,
        "has_delivery_note": chain.has_delivery_note,
        "has_invoice": chain.has_invoice,
        "has_credit_note": chain.has_credit_note,
        "open_discrepancies": chain.open_discrepancies,
        "is_complete": chain.is_complete,
        "documents": [
            {
                "id": str(d.id),
                "document_type": d.document_type,
                "chain_position": d.chain_position,
                "filename": d.filename,
                "document_date": d.document_date.isoformat() if d.document_date else None,
                "amount": float(d.amount) if d.amount else None,
                "reference_numbers": d.reference_numbers,
                "created_at": d.created_at.isoformat(),
            }
            for d in chain.documents
        ],
    }


@router.get(
    "/by-document/{document_id}",
    summary="Auftragskette eines Dokuments abrufen",
    description="Findet die Auftragskette zu der ein bestimmtes Dokument gehoert"
)
async def get_chain_by_document(
    document_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Findet die Auftragskette eines Dokuments.

    Falls das Dokument keiner Kette zugeordnet ist, wird ein leeres Ergebnis zurueckgegeben.
    """
    company_id = current_user.company_id
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer hat keine Firmenzuordnung"
        )

    # SECURITY: Pruefen ob Dokument dem User gehoert
    result = await db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.owner_id == current_user.id,
            Document.deleted_at.is_(None),
        )
    )
    doc = result.scalar_one_or_none()

    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dokument nicht gefunden"
        )

    if not doc.chain_id:
        return {
            "document_id": str(document_id),
            "chain_id": None,
            "message": "Dokument ist keiner Auftragskette zugeordnet",
        }

    chain_service = DocumentChainService()
    chain = await chain_service.get_chain(db=db, chain_id=doc.chain_id, company_id=company_id)

    if not chain:
        return {
            "document_id": str(document_id),
            "chain_id": doc.chain_id,
            "message": "Auftragskette nicht gefunden",
        }

    return {
        "document_id": str(document_id),
        "chain_id": chain.chain_id,
        "document_count": chain.document_count,
        "is_complete": chain.is_complete,
        "open_discrepancies": chain.open_discrepancies,
    }


# =============================================================================
# DOCUMENT LINKING
# =============================================================================


@router.post(
    "/link",
    status_code=status.HTTP_201_CREATED,
    summary="Dokumente verknuepfen",
    description="Verknuepft zwei Dokumente miteinander"
)
async def link_documents(
    source_document_id: UUID,
    target_document_id: UUID,
    relationship_type: str = Query(
        ...,
        description="Art der Beziehung: quote_to_order, order_to_delivery, delivery_to_invoice, etc."
    ),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Verknuepft zwei Dokumente in einer Auftragskette.

    **Beziehungstypen:**
    - quote_to_order: Angebot → Auftrag
    - order_to_delivery: Auftrag → Lieferschein
    - delivery_to_invoice: Lieferschein → Rechnung
    - invoice_to_credit_note: Rechnung → Gutschrift
    - order_to_invoice: Auftrag → Rechnung (ohne Lieferschein)
    - related: Allgemeine Verwandtschaft
    """
    company_id = current_user.company_id
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer hat keine Firmenzuordnung"
        )

    # Beziehungstyp validieren
    try:
        rel_type = RelationshipType(relationship_type)
    except ValueError:
        valid_types = [t.value for t in RelationshipType]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ungueltiger Beziehungstyp. Erlaubt: {', '.join(valid_types)}"
        )

    # SECURITY: Pruefen ob beide Dokumente dem User gehoeren
    for doc_id in [source_document_id, target_document_id]:
        result = await db.execute(
            select(Document).where(
                Document.id == doc_id,
                Document.owner_id == current_user.id,
                Document.deleted_at.is_(None),
            )
        )
        if not result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Dokument {doc_id} nicht gefunden oder keine Berechtigung"
            )

    chain_service = DocumentChainService()

    try:
        relationship_id = await chain_service.link_documents(
            db=db,
            source_document_id=source_document_id,
            target_document_id=target_document_id,
            relationship_type=rel_type,
            company_id=company_id,
            user_id=current_user.id,
            auto_detected=False,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Dokumentenkette")
        )

    await db.commit()

    logger.info(
        "documents_linked",
        source_id=str(source_document_id),
        target_id=str(target_document_id),
        relationship_type=relationship_type,
    )

    return {
        "relationship_id": str(relationship_id),
        "source_document_id": str(source_document_id),
        "target_document_id": str(target_document_id),
        "relationship_type": relationship_type,
        "message": "Dokumente erfolgreich verknuepft",
    }


# =============================================================================
# AUTO-MATCHING
# =============================================================================


@router.get(
    "/auto-match/{document_id}",
    summary="Automatische Dokumenten-Suche",
    description="Sucht automatisch nach verwandten Dokumenten"
)
async def auto_match_documents(
    document_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Sucht automatisch nach verwandten Dokumenten.

    **Matching-Strategien:**
    - Referenznummern (Bestellnummer, Angebotsnummer)
    - Kundennummer + aehnlicher Betrag
    - Textanalyse

    **Response:**
    - matches: Liste moeglicher Matches mit Konfidenz
    """
    company_id = current_user.company_id
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer hat keine Firmenzuordnung"
        )

    # SECURITY: Pruefen ob Dokument dem User gehoert
    result = await db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.owner_id == current_user.id,
            Document.deleted_at.is_(None),
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dokument nicht gefunden"
        )

    chain_service = DocumentChainService()
    matches = await chain_service.auto_match_documents(
        db=db,
        document_id=document_id,
        company_id=company_id,
    )

    return {
        "document_id": str(document_id),
        "match_count": len(matches),
        "matches": [
            {
                "matched_document_ids": [str(d) for d in m.matched_documents],
                "chain_id": m.chain_id,
                "relationship_type": m.relationship_type.value if m.relationship_type else None,
                "confidence": m.confidence,
                "match_reason": m.match_reason,
            }
            for m in matches
        ],
    }


# =============================================================================
# DISCREPANCIES
# =============================================================================


@router.get(
    "/{chain_id}/discrepancies",
    summary="Abweichungen einer Kette abrufen",
    description="Listet alle Abweichungen zwischen Dokumenten einer Kette"
)
async def get_chain_discrepancies(
    chain_id: str,
    include_resolved: bool = Query(False, description="Auch geloeste Abweichungen anzeigen"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Listet Abweichungen in einer Auftragskette.

    **Abweichungstypen:**
    - amount_mismatch: Betragsabweichung
    - quantity_mismatch: Mengenabweichung
    - missing_position: Fehlende Position
    - customer_mismatch: Unterschiedlicher Kunde
    - date_inconsistency: Datumsinkonsistenz

    **Schweregrade:**
    - info: Harmlos
    - warning: Pruefung empfohlen
    - error: Muss geprueft werden
    - critical: Blockiert Workflow
    """
    company_id = current_user.company_id
    if not company_id:
        return {"chain_id": chain_id, "discrepancies": [], "message": "Keine Firmenzuordnung"}

    chain_service = DocumentChainService()

    # Erst pruefen ob Chain existiert und zugaenglich ist
    chain = await chain_service.get_chain(db=db, chain_id=chain_id, company_id=company_id)
    if not chain:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Auftragskette nicht gefunden"
        )

    # SECURITY: Multi-Tenant Isolation - company_id uebergeben!
    discrepancies = await chain_service.get_chain_discrepancies(
        db=db,
        chain_id=chain_id,
        company_id=company_id,
        include_resolved=include_resolved,
    )

    return {
        "chain_id": chain_id,
        "discrepancy_count": len(discrepancies),
        "discrepancies": [
            {
                "id": str(d.id),
                "source_document_id": str(d.source_document_id),
                "target_document_id": str(d.target_document_id),
                "discrepancy_type": d.discrepancy_type.value,
                "field_name": d.field_name,
                "expected_value": d.expected_value,  # Renamed from source_value
                "actual_value": d.actual_value,      # Renamed from target_value
                "difference_percentage": d.difference_percentage,
                "severity": d.severity.value,
                "is_resolved": d.is_resolved,        # Renamed from resolved
                "created_at": d.created_at.isoformat(),  # Renamed from detected_at
            }
            for d in discrepancies
        ],
    }


@router.post(
    "/discrepancies/{discrepancy_id}/resolve",
    summary="Abweichung als geloest markieren",
    description="Markiert eine Abweichung als geprueft und geloest"
)
async def resolve_discrepancy(
    discrepancy_id: UUID,
    resolution_notes: Optional[str] = Query(None, description="Begruendung/Notizen"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Markiert eine Abweichung als geloest.

    Die Abweichung wird nicht geloescht, sondern nur als "resolved" markiert
    mit Timestamp und User-Referenz.

    SECURITY: Multi-Tenant Isolation - nur Abweichungen der eigenen Firma koennen geloest werden.
    """
    # SECURITY: Multi-Tenant Isolation
    company_id = current_user.company_id
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Keine Firmenzuordnung vorhanden"
        )

    chain_service = DocumentChainService()

    success = await chain_service.resolve_discrepancy(
        db=db,
        discrepancy_id=discrepancy_id,
        company_id=company_id,  # SECURITY: Multi-Tenant Check
        user_id=current_user.id,
        resolution_notes=resolution_notes,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Abweichung nicht gefunden oder nicht berechtigt"
        )

    await db.commit()

    logger.info(
        "discrepancy_resolved",
        discrepancy_id=str(discrepancy_id),
        user_id=str(current_user.id),
    )

    return {
        "discrepancy_id": str(discrepancy_id),
        "resolved": True,
        "resolved_at": datetime.now(timezone.utc).isoformat(),
        "message": "Abweichung erfolgreich als geloest markiert",
    }


# =============================================================================
# LIST ALL CHAINS
# =============================================================================


@router.get(
    "",
    summary="Alle Auftragsketten auflisten",
    description="Listet alle Auftragsketten mit Filteroptionen"
)
async def list_chains(
    page: int = Query(1, ge=1, description="Seitennummer"),
    per_page: int = Query(20, ge=1, le=100, description="Eintraege pro Seite"),
    has_discrepancies: Optional[bool] = Query(None, description="Nur Ketten mit/ohne Abweichungen"),
    is_complete: Optional[bool] = Query(None, description="Nur vollstaendige/unvollstaendige Ketten"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Listet alle Auftragsketten auf.

    **Filter:**
    - has_discrepancies: true = nur mit offenen Abweichungen
    - is_complete: true = nur Ketten mit Rechnung
    """
    company_id = current_user.company_id
    if not company_id:
        return {"chains": [], "total": 0, "page": page, "per_page": per_page}

    # Query ueber die View v_document_chains
    query = """
        SELECT
            chain_id,
            document_count,
            chain_started_at,
            chain_updated_at,
            document_types,
            invoice_count,
            delivery_note_count,
            order_count,
            open_discrepancies
        FROM v_document_chains
        WHERE company_id = :company_id
    """

    params = {"company_id": str(company_id)}

    if has_discrepancies is not None:
        if has_discrepancies:
            query += " AND open_discrepancies > 0"
        else:
            query += " AND open_discrepancies = 0"

    if is_complete is not None:
        if is_complete:
            query += " AND invoice_count > 0"
        else:
            query += " AND invoice_count = 0"

    query += " ORDER BY chain_updated_at DESC"
    query += f" LIMIT {per_page} OFFSET {(page - 1) * per_page}"

    from sqlalchemy import text
    result = await db.execute(text(query), params)
    rows = result.fetchall()

    chains = []
    for row in rows:
        chains.append({
            "chain_id": row.chain_id,
            "document_count": row.document_count,
            "chain_started_at": row.chain_started_at.isoformat() if row.chain_started_at else None,
            "chain_updated_at": row.chain_updated_at.isoformat() if row.chain_updated_at else None,
            "document_types": row.document_types,
            "invoice_count": row.invoice_count,
            "delivery_note_count": row.delivery_note_count,
            "order_count": row.order_count,
            "open_discrepancies": row.open_discrepancies,
            "is_complete": row.invoice_count > 0,
        })

    return {
        "chains": chains,
        "total": len(chains),  # Fuer echte Pagination: COUNT(*) Query
        "page": page,
        "per_page": per_page,
    }

# -*- coding: utf-8 -*-
"""
Extended Document Chain API Endpoints V2.

REST API für erweitertes Auftragsketten-Tracking:
- Vertragserfuellung (Vertrag -> Lieferung -> Mahnung)
- Beschaffungsketten (Bestellung -> Wareneingang -> QC)
- Projekt-basierte Dokumentengruppierung
- ML-basiertes Auto-Matching
- Visualisierungs-API

Phase 6.2: Extended Document Chains für Enterprise-Dokumentenmanagement.
Feinpoliert und durchdacht - Deutsche Dokumente mit hoechster Präzision.
"""

from typing import Optional, List
from uuid import UUID
from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, status, Query, Body
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.models import User, Document
from app.api.dependencies import get_db, get_current_active_user
from app.core.safe_errors import safe_error_detail, safe_error_log
from app.services.document_chain_service_v2 import (
    ExtendedDocumentChainServiceV2,
    ChainType,
    get_extended_chain_service,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/document-chains/v2", tags=["Document Chains V2"])


# =============================================================================
# SCHEMAS
# =============================================================================


class CreateChainRequest(BaseModel):
    """Anfrage zur Erstellung einer erweiterten Kette."""
    document_ids: List[UUID] = Field(..., min_length=1)
    chain_type: ChainType
    project_id: Optional[UUID] = None
    chain_id: Optional[str] = Field(None, max_length=100)
    metadata: Optional[dict] = None


class CreateContractChainRequest(BaseModel):
    """Anfrage zur Erstellung einer Vertragserfuellungskette."""
    contract_document_id: UUID
    contract_number: Optional[str] = Field(None, max_length=100)


class CreateProcurementChainRequest(BaseModel):
    """Anfrage zur Erstellung einer Beschaffungskette."""
    purchase_order_id: UUID
    order_number: Optional[str] = Field(None, max_length=100)
    supplier_id: Optional[UUID] = None


class AddDunningRequest(BaseModel):
    """Anfrage zum Hinzufuegen einer Mahnung."""
    dunning_document_id: UUID
    dunning_level: int = Field(..., ge=0, le=3)


class AddQualityControlRequest(BaseModel):
    """Anfrage zum Hinzufuegen eines QC-Protokolls."""
    qc_document_id: UUID
    qc_passed: bool
    qc_notes: Optional[str] = Field(None, max_length=1000)


class MLAutoLinkRequest(BaseModel):
    """Anfrage für ML-basiertes Auto-Linking."""
    document_id: UUID
    min_confidence: float = Field(0.80, ge=0.0, le=1.0)
    chain_types: Optional[List[ChainType]] = None


class ChainDocumentResponse(BaseModel):
    """Antwort für ein Dokument in der Kette."""
    id: str
    document_type: str
    chain_position: int
    filename: str
    document_date: Optional[str]
    amount: Optional[float]
    reference_numbers: dict
    ml_confidence: Optional[float]
    entity_name: Optional[str]

    class Config:
        from_attributes = True


class ExtendedChainResponse(BaseModel):
    """Antwort für eine erweiterte Kette."""
    chain_id: str
    chain_type: str
    document_count: int
    chain_started_at: str
    chain_updated_at: str
    document_type_flags: dict
    open_discrepancies: int
    total_amount: Optional[float]
    is_complete: bool
    completion_percentage: float
    project_id: Optional[str]
    project_code: Optional[str]
    project_name: Optional[str]
    primary_entity_name: Optional[str]
    documents: List[ChainDocumentResponse]
    visualization_data: Optional[dict] = None


class MLMatchResponse(BaseModel):
    """Antwort für ML-Matching."""
    matched: bool
    chain_id: Optional[str]
    chain_type: str
    relationship_type: Optional[str]
    confidence: float
    matched_document_ids: List[str]
    match_reason: str
    ml_features: dict
    feature_contributions: dict


class VisualizationResponse(BaseModel):
    """Antwort für Visualisierung."""
    chain_id: str
    chain_type: str
    nodes: List[dict]
    edges: List[dict]
    layout: str
    total_amount: Optional[float]
    completion_percentage: float
    critical_path: List[str]


# =============================================================================
# CHAIN CREATION ENDPOINTS
# =============================================================================


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=dict,
    summary="Erweiterte Auftragskette erstellen",
    description="Erstellt eine erweiterte Auftragskette mit spezifischem Typ"
)
async def create_extended_chain(
    request: CreateChainRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Erstellt eine erweiterte Auftragskette.

    **Unterstützte Chain-Typen:**
    - quote_to_order: Standard Angebots-zu-Auftrag Kette
    - contract_fulfillment: Vertragserfuellung
    - procurement: Beschaffungskette
    - project: Projektbasierte Gruppierung

    **Response:**
    - chain_id: Die ID der erstellten Kette
    - chain_type: Typ der Kette
    - document_count: Anzahl der verknüpften Dokumente
    """
    company_id = current_user.company_id
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer hat keine Firmenzuordnung"
        )

    # SECURITY: Alle Dokumente prüfen
    for doc_id in request.document_ids:
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

    service = get_extended_chain_service()

    try:
        chain_id = await service.create_extended_chain(
            db=db,
            documents=request.document_ids,
            company_id=company_id,
            user_id=current_user.id,
            chain_type=request.chain_type,
            project_id=request.project_id,
            chain_id=request.chain_id,
            metadata=request.metadata,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Dokumentenkette")
        )

    await db.commit()

    logger.info(
        "extended_chain_created_via_api",
        chain_id=chain_id,
        chain_type=request.chain_type.value,
        document_count=len(request.document_ids),
    )

    return {
        "chain_id": chain_id,
        "chain_type": request.chain_type.value,
        "document_count": len(request.document_ids),
        "project_id": str(request.project_id) if request.project_id else None,
        "message": "Erweiterte Auftragskette erfolgreich erstellt",
    }


@router.post(
    "/contract",
    status_code=status.HTTP_201_CREATED,
    summary="Vertragserfuellungskette erstellen",
    description="Erstellt eine Kette für Vertragserfuellung mit Mahnungsverfolgung"
)
async def create_contract_chain(
    request: CreateContractChainRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Erstellt eine Vertragserfuellungskette.

    Diese Kette ermöglicht das Tracking von:
    - Vertrag -> Lieferungen -> Rechnung -> Mahnungen
    """
    company_id = current_user.company_id
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer hat keine Firmenzuordnung"
        )

    # Dokument prüfen
    result = await db.execute(
        select(Document).where(
            Document.id == request.contract_document_id,
            Document.owner_id == current_user.id,
            Document.deleted_at.is_(None),
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vertragsdokument nicht gefunden"
        )

    service = get_extended_chain_service()

    chain_id = await service.create_contract_chain(
        db=db,
        contract_document_id=request.contract_document_id,
        company_id=company_id,
        user_id=current_user.id,
        contract_number=request.contract_number,
    )

    await db.commit()

    return {
        "chain_id": chain_id,
        "chain_type": ChainType.CONTRACT_FULFILLMENT.value,
        "contract_number": request.contract_number,
        "message": "Vertragserfuellungskette erfolgreich erstellt",
    }


@router.post(
    "/procurement",
    status_code=status.HTTP_201_CREATED,
    summary="Beschaffungskette erstellen",
    description="Erstellt eine Kette für Beschaffungsprozess mit QC-Verfolgung"
)
async def create_procurement_chain(
    request: CreateProcurementChainRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Erstellt eine Beschaffungskette.

    Diese Kette ermöglicht das Tracking von:
    - Bestellung -> Auftragsbestätigung -> Lieferschein -> Wareneingang -> QC -> Rechnung
    """
    company_id = current_user.company_id
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer hat keine Firmenzuordnung"
        )

    # Dokument prüfen
    result = await db.execute(
        select(Document).where(
            Document.id == request.purchase_order_id,
            Document.owner_id == current_user.id,
            Document.deleted_at.is_(None),
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bestelldokument nicht gefunden"
        )

    service = get_extended_chain_service()

    chain_id = await service.create_procurement_chain(
        db=db,
        purchase_order_id=request.purchase_order_id,
        company_id=company_id,
        user_id=current_user.id,
        order_number=request.order_number,
        supplier_id=request.supplier_id,
    )

    await db.commit()

    return {
        "chain_id": chain_id,
        "chain_type": ChainType.PROCUREMENT.value,
        "order_number": request.order_number,
        "message": "Beschaffungskette erfolgreich erstellt",
    }


# =============================================================================
# CHAIN INTELLIGENCE ENDPOINTS (MUST be before /{chain_id} catch-all)
# =============================================================================


class ChainGapResponse(BaseModel):
    """Antwort für eine Kettenlücke."""
    chain_id: str
    chain_name: str
    expected_type: str
    after_document: str
    days_overdue: int
    severity: str
    suggested_matches: List[str]


class OrphanDocumentResponse(BaseModel):
    """Antwort für ein verwaistes Dokument."""
    document_id: str
    filename: str
    document_type: str
    document_date: Optional[str]
    reference_numbers: dict
    potential_chain_ids: List[str]
    match_confidence: float


class ChainIntelligenceReportResponse(BaseModel):
    """Antwort für den Ketten-Intelligenz-Bericht."""
    total_chains: int
    complete_chains: int
    chains_with_gaps: int
    gaps: List[ChainGapResponse]
    orphan_count: int
    suggested_new_chains: List[dict]
    scan_timestamp: str
    average_completion: float


@router.get(
    "/intelligence/gaps",
    response_model=ChainIntelligenceReportResponse,
    summary="Kettenlücken analysieren",
    description="Scannt alle Ketten auf fehlende Glieder und generiert Vorschläge"
)
async def get_chain_gaps(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> ChainIntelligenceReportResponse:
    """
    Analysiert alle Auftragsketten auf Lücken.

    Erkennt fehlende Dokumente in bestehenden Ketten:
    - Bestellung vorhanden, aber kein Lieferschein
    - Lieferschein vorhanden, aber keine Rechnung
    - Vertrag vorhanden, aber keine Lieferung

    **Severity-Stufen:**
    - info: Lücke erkannt
    - warning: Über 14 Tage überfällig
    - critical: Über 30 Tage überfällig
    """
    from app.services.document_chain_intelligence_service import (
        get_chain_intelligence_service,
    )

    company_id = current_user.company_id
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer hat keine Firmenzuordnung"
        )

    service = get_chain_intelligence_service()

    try:
        report = await service.scan_for_gaps(
            company_id=company_id,
            db=db,
        )
    except Exception as e:
        logger.error(
            "chain_intelligence_scan_failed",
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Kettenanalyse")
        )

    return ChainIntelligenceReportResponse(
        total_chains=report.total_chains,
        complete_chains=report.complete_chains,
        chains_with_gaps=report.chains_with_gaps,
        gaps=[
            ChainGapResponse(
                chain_id=g.chain_id,
                chain_name=g.chain_name,
                expected_type=g.expected_type,
                after_document=g.after_document,
                days_overdue=g.days_overdue,
                severity=g.severity,
                suggested_matches=g.suggested_matches,
            )
            for g in report.gaps
        ],
        orphan_count=len(report.orphan_documents),
        suggested_new_chains=report.suggested_new_chains,
        scan_timestamp=report.scan_timestamp.isoformat(),
        average_completion=report.average_completion,
    )


@router.get(
    "/intelligence/orphans",
    summary="Verwaiste Dokumente erkennen",
    description="Findet Dokumente ohne Kettenverknüpfung die zu bestehenden Ketten passen könnten"
)
async def get_orphan_documents(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Erkennt Dokumente ohne Kettenverknüpfung.

    Sucht nach Dokumenten die aufgrund von Referenznummern,
    Dokumenttyp und Geschäftspartner zu bestehenden Ketten passen könnten.
    """
    from app.services.document_chain_intelligence_service import (
        get_chain_intelligence_service,
    )

    company_id = current_user.company_id
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer hat keine Firmenzuordnung"
        )

    service = get_chain_intelligence_service()

    try:
        orphans = await service.detect_orphan_documents(
            company_id=company_id,
            db=db,
        )
    except Exception as e:
        logger.error(
            "orphan_detection_failed",
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Verwaiste-Dokumente-Erkennung")
        )

    return {
        "orphan_count": len(orphans),
        "orphans": [
            OrphanDocumentResponse(
                document_id=o.document_id,
                filename=o.filename,
                document_type=o.document_type,
                document_date=o.document_date,
                reference_numbers=o.reference_numbers,
                potential_chain_ids=o.potential_chain_ids,
                match_confidence=o.match_confidence,
            ).model_dump()
            for o in orphans
        ],
    }


@router.get(
    "/intelligence/{chain_id}/suggestions",
    summary="Vervollständigungs-Vorschläge",
    description="Generiert Vorschläge zur Vervollständigung einer spezifischen Kette"
)
async def get_chain_suggestions(
    chain_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Generiert Vorschläge für eine spezifische Kette.

    Analysiert welche Dokumenttypen in der Kette fehlen und sucht
    nach passenden unchained Dokumenten die die Lücken fuellen könnten.
    """
    from app.services.document_chain_intelligence_service import (
        get_chain_intelligence_service,
    )

    company_id = current_user.company_id
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer hat keine Firmenzuordnung"
        )

    service = get_chain_intelligence_service()

    try:
        suggestions = await service.suggest_chain_completions(
            chain_id=chain_id,
            db=db,
            company_id=company_id,
        )
    except Exception as e:
        logger.error(
            "chain_suggestions_failed",
            chain_id=chain_id,
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Kettenvorschläge")
        )

    return {
        "chain_id": chain_id,
        "suggestion_count": len(suggestions),
        "suggestions": [
            ChainGapResponse(
                chain_id=s.chain_id,
                chain_name=s.chain_name,
                expected_type=s.expected_type,
                after_document=s.after_document,
                days_overdue=s.days_overdue,
                severity=s.severity,
                suggested_matches=s.suggested_matches,
            ).model_dump()
            for s in suggestions
        ],
    }


# =============================================================================
# CHAIN RETRIEVAL ENDPOINTS
# =============================================================================


@router.get(
    "/{chain_id}",
    response_model=ExtendedChainResponse,
    summary="Erweiterte Kette abrufen",
    description="Liefert alle Details einer erweiterten Auftragskette"
)
async def get_extended_chain(
    chain_id: str,
    include_visualization: bool = Query(False, description="Visualisierungsdaten einschließen"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> ExtendedChainResponse:
    """
    Ruft eine erweiterte Auftragskette ab.

    Liefert alle Dokumente mit erweiterten Metadaten und optional
    Visualisierungsdaten für das Frontend.
    """
    company_id = current_user.company_id
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer hat keine Firmenzuordnung"
        )

    service = get_extended_chain_service()
    chain = await service.get_extended_chain(
        db=db,
        chain_id=chain_id,
        company_id=company_id,
        include_visualization=include_visualization,
    )

    if not chain:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Auftragskette nicht gefunden"
        )

    documents = [
        ChainDocumentResponse(
            id=str(d.id),
            document_type=d.document_type,
            chain_position=d.chain_position,
            filename=d.filename,
            document_date=d.document_date.isoformat() if d.document_date else None,
            amount=float(d.amount) if d.amount else None,
            reference_numbers=d.reference_numbers,
            ml_confidence=d.ml_confidence,
            entity_name=d.entity_name,
        )
        for d in chain.documents
    ]

    return ExtendedChainResponse(
        chain_id=chain.chain_id,
        chain_type=chain.chain_type.value,
        document_count=chain.document_count,
        chain_started_at=chain.chain_started_at.isoformat(),
        chain_updated_at=chain.chain_updated_at.isoformat(),
        document_type_flags=chain.document_type_flags,
        open_discrepancies=chain.open_discrepancies,
        total_amount=float(chain.total_amount) if chain.total_amount else None,
        is_complete=chain.is_complete,
        completion_percentage=chain.completion_percentage,
        project_id=str(chain.project_id) if chain.project_id else None,
        project_code=chain.project_code,
        project_name=chain.project_name,
        primary_entity_name=chain.primary_entity_name,
        documents=documents,
        visualization_data=chain.visualization_data,
    )


@router.get(
    "/by-project/{project_id}",
    summary="Ketten eines Projekts abrufen",
    description="Liefert alle Auftragsketten eines Projekts"
)
async def get_chains_by_project(
    project_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Ruft alle Auftragsketten eines Projekts ab.
    """
    company_id = current_user.company_id
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer hat keine Firmenzuordnung"
        )

    service = get_extended_chain_service()
    chains = await service.get_chains_by_project(
        db=db,
        project_id=project_id,
        company_id=company_id,
    )

    return {
        "project_id": str(project_id),
        "chain_count": len(chains),
        "chains": [
            {
                "chain_id": c.chain_id,
                "chain_type": c.chain_type.value,
                "document_count": c.document_count,
                "is_complete": c.is_complete,
                "completion_percentage": c.completion_percentage,
                "total_amount": float(c.total_amount) if c.total_amount else None,
            }
            for c in chains
        ],
    }


# =============================================================================
# ML AUTO-MATCHING ENDPOINTS
# =============================================================================


@router.get(
    "/ml-match/{document_id}",
    summary="ML-basierte Matching-Vorschläge",
    description="Sucht automatisch nach verwandten Dokumenten mit ML-Konfidenz"
)
async def ml_auto_match(
    document_id: UUID,
    chain_types: Optional[str] = Query(None, description="Komma-getrennte Chain-Typen"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    ML-basierte Suche nach verwandten Dokumenten.

    Verwendet mehrere Features für praezises Matching:
    - Referenznummern (hoechste Gewichtung)
    - Betragsähnlichkeit
    - Datumsnaehe
    - Entity-Match
    - Dokumenttyp-Sequenz
    """
    company_id = current_user.company_id
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer hat keine Firmenzuordnung"
        )

    # Dokument prüfen
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

    # Chain-Typen parsen
    parsed_chain_types: Optional[List[ChainType]] = None
    if chain_types:
        try:
            parsed_chain_types = [ChainType(t.strip()) for t in chain_types.split(",")]
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Ungültiger Chain-Typ: {e}"
            )

    service = get_extended_chain_service()
    matches = await service.ml_auto_match(
        db=db,
        document_id=document_id,
        company_id=company_id,
        chain_types=parsed_chain_types,
    )

    return {
        "document_id": str(document_id),
        "match_count": len(matches),
        "matches": [
            MLMatchResponse(
                matched=m.matched,
                chain_id=m.chain_id,
                chain_type=m.chain_type.value,
                relationship_type=m.relationship_type.value if m.relationship_type else None,
                confidence=m.confidence,
                matched_document_ids=[str(d) for d in m.matched_documents],
                match_reason=m.match_reason,
                ml_features=m.ml_features,
                feature_contributions=m.feature_contributions,
            ).model_dump()
            for m in matches
        ],
    }


@router.post(
    "/ml-auto-link",
    status_code=status.HTTP_201_CREATED,
    summary="ML-basiertes Auto-Linking",
    description="Verknüpft Dokument automatisch basierend auf ML-Matching"
)
async def ml_auto_link(
    request: MLAutoLinkRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Automatisches Linking basierend auf ML-Matching.

    Führt Auto-Linking nur durch wenn Konfidenz über Schwellenwert.
    """
    company_id = current_user.company_id
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer hat keine Firmenzuordnung"
        )

    # Dokument prüfen
    result = await db.execute(
        select(Document).where(
            Document.id == request.document_id,
            Document.owner_id == current_user.id,
            Document.deleted_at.is_(None),
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dokument nicht gefunden"
        )

    service = get_extended_chain_service()
    chain_id = await service.ml_auto_link(
        db=db,
        document_id=request.document_id,
        company_id=company_id,
        user_id=current_user.id,
        min_confidence=request.min_confidence,
    )

    if not chain_id:
        return {
            "linked": False,
            "document_id": str(request.document_id),
            "message": "Kein passendes Match mit ausreichender Konfidenz gefunden",
        }

    await db.commit()

    return {
        "linked": True,
        "document_id": str(request.document_id),
        "chain_id": chain_id,
        "message": "Dokument erfolgreich verknüpft",
    }


# =============================================================================
# CONTRACT FULFILLMENT ENDPOINTS
# =============================================================================


@router.post(
    "/{chain_id}/dunning",
    summary="Mahnung hinzufuegen",
    description="Fuegt eine Mahnung zur Vertragserfuellungskette hinzu"
)
async def add_dunning(
    chain_id: str,
    request: AddDunningRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Fuegt eine Mahnung zur Vertragserfuellungskette hinzu.

    **Mahnstufen:**
    - 0: Zahlungserinnerung
    - 1: 1. Mahnung
    - 2: 2. Mahnung
    - 3: 3. Mahnung (Inkasso-Androhung)
    """
    company_id = current_user.company_id
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer hat keine Firmenzuordnung"
        )

    # Mahnungsdokument prüfen
    result = await db.execute(
        select(Document).where(
            Document.id == request.dunning_document_id,
            Document.owner_id == current_user.id,
            Document.deleted_at.is_(None),
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mahnungsdokument nicht gefunden"
        )

    service = get_extended_chain_service()
    success = await service.add_dunning_to_contract_chain(
        db=db,
        chain_id=chain_id,
        dunning_document_id=request.dunning_document_id,
        dunning_level=request.dunning_level,
        company_id=company_id,
        user_id=current_user.id,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Kette nicht gefunden oder falscher Typ (nur CONTRACT_FULFILLMENT erlaubt)"
        )

    await db.commit()

    dunning_labels = {
        0: "Zahlungserinnerung",
        1: "1. Mahnung",
        2: "2. Mahnung",
        3: "3. Mahnung",
    }

    return {
        "chain_id": chain_id,
        "dunning_document_id": str(request.dunning_document_id),
        "dunning_level": request.dunning_level,
        "dunning_label": dunning_labels.get(request.dunning_level, f"Stufe {request.dunning_level}"),
        "message": "Mahnung erfolgreich hinzugefuegt",
    }


# =============================================================================
# PROCUREMENT CHAIN ENDPOINTS
# =============================================================================


@router.post(
    "/{chain_id}/quality-control",
    summary="Qualitaetskontrolle hinzufuegen",
    description="Fuegt ein QC-Protokoll zur Beschaffungskette hinzu"
)
async def add_quality_control(
    chain_id: str,
    request: AddQualityControlRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Fuegt ein QC-Protokoll zur Beschaffungskette hinzu.

    Bei fehlgeschlagener QC wird automatisch eine Abweichung erstellt.
    """
    company_id = current_user.company_id
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer hat keine Firmenzuordnung"
        )

    # QC-Dokument prüfen
    result = await db.execute(
        select(Document).where(
            Document.id == request.qc_document_id,
            Document.owner_id == current_user.id,
            Document.deleted_at.is_(None),
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="QC-Dokument nicht gefunden"
        )

    service = get_extended_chain_service()
    success = await service.add_quality_control_to_procurement(
        db=db,
        chain_id=chain_id,
        qc_document_id=request.qc_document_id,
        qc_passed=request.qc_passed,
        qc_notes=request.qc_notes,
        company_id=company_id,
        user_id=current_user.id,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Kette nicht gefunden oder falscher Typ (nur PROCUREMENT erlaubt)"
        )

    await db.commit()

    return {
        "chain_id": chain_id,
        "qc_document_id": str(request.qc_document_id),
        "qc_passed": request.qc_passed,
        "qc_notes": request.qc_notes,
        "discrepancy_created": not request.qc_passed,
        "message": "Qualitaetskontrolle erfolgreich hinzugefuegt",
    }


# =============================================================================
# VISUALIZATION ENDPOINTS
# =============================================================================


@router.get(
    "/{chain_id}/visualization",
    response_model=VisualizationResponse,
    summary="Visualisierungsdaten abrufen",
    description="Liefert Daten für die Chain-Visualisierung im Frontend"
)
async def get_visualization(
    chain_id: str,
    layout: str = Query("horizontal", regex="^(horizontal|vertical|radial)$"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> VisualizationResponse:
    """
    Ruft Visualisierungsdaten für eine Kette ab.

    **Layouts:**
    - horizontal: Links-nach-rechts Fluss
    - vertical: Oben-nach-unten Fluss
    - radial: Kreisfoermige Anordnung
    """
    company_id = current_user.company_id
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer hat keine Firmenzuordnung"
        )

    service = get_extended_chain_service()
    viz = await service.get_chain_visualization(
        db=db,
        chain_id=chain_id,
        company_id=company_id,
        layout=layout,
    )

    if not viz:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Auftragskette nicht gefunden"
        )

    return VisualizationResponse(
        chain_id=viz.chain_id,
        chain_type=viz.chain_type.value,
        nodes=viz.nodes,
        edges=viz.edges,
        layout=viz.layout,
        total_amount=float(viz.total_amount) if viz.total_amount else None,
        completion_percentage=viz.completion_percentage,
        critical_path=viz.critical_path,
    )

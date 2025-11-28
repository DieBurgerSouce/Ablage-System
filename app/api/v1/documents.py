"""Documents API endpoints with search and batch operations.

Provides REST API endpoints for:
- Document CRUD operations
- Full-text and semantic search
- Similar documents discovery
- Batch operations (delete, tag, export)
"""

from typing import Optional, List
from datetime import datetime
from uuid import UUID
import io

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Response, UploadFile, File, Form, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.db.schemas import (
    # Search
    SearchType, SearchFilters, SearchResponse, SimilarDocumentItem,
    SortField, SortOrder, DocumentType, ProcessingStatus,
    # Documents
    DocumentDetailResponse, DocumentListResponseExtended, DocumentUpdateRequest,
    DocumentSummary,
    # Batch
    BatchDeleteRequest, BatchTagRequest, BatchExportRequest,
    BatchOperationResult, BatchExportResult, TagOperation, ExportFormat,
    # Common
    MessageResponse
)
from app.api.dependencies import (
    get_current_active_user, get_db, check_rate_limit, check_batch_rate_limit
)
from app.services.search_service import get_search_service
from app.services.document_service import get_document_service

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])


# ==================== Document CRUD Endpoints ====================

@router.get("/", response_model=DocumentListResponseExtended)
async def list_documents(
    page: int = Query(1, ge=1, description="Seitennummer"),
    per_page: int = Query(20, ge=1, le=100, description="Eintraege pro Seite"),
    document_type: Optional[DocumentType] = Query(None, description="Dokumenttyp filtern"),
    status: Optional[ProcessingStatus] = Query(None, description="Status filtern"),
    date_from: Optional[datetime] = Query(None, description="Erstellt nach"),
    date_to: Optional[datetime] = Query(None, description="Erstellt vor"),
    confidence_min: Optional[float] = Query(None, ge=0, le=100, description="Min. OCR-Konfidenz"),
    has_embedding: Optional[bool] = Query(None, description="Mit Embedding"),
    language: Optional[str] = Query(None, pattern="^(de|en)$", description="Sprache"),
    sort_by: SortField = Query(SortField.CREATED_AT, description="Sortierfeld"),
    sort_order: SortOrder = Query(SortOrder.DESC, description="Sortierreihenfolge"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Dokumente auflisten mit Filterung und Pagination.

    Gibt eine paginierte Liste der eigenen Dokumente zurueck,
    optional gefiltert nach verschiedenen Kriterien.
    """
    filters = SearchFilters(
        document_type=document_type,
        status=status,
        date_from=date_from,
        date_to=date_to,
        confidence_min=confidence_min,
        has_embedding=has_embedding,
        language=language
    )

    service = get_document_service()
    return await service.list_documents(
        db=db,
        user_id=current_user.id,
        filters=filters,
        page=page,
        per_page=per_page,
        sort_by=sort_by,
        sort_order=sort_order
    )


@router.get("/search/", response_model=SearchResponse)
async def search_documents(
    request: Request,
    q: str = Query(..., min_length=1, max_length=1000, description="Suchbegriff"),
    search_type: SearchType = Query(SearchType.HYBRID, description="Art der Suche"),
    page: int = Query(1, ge=1, description="Seitennummer"),
    per_page: int = Query(20, ge=1, le=100, description="Eintraege pro Seite"),
    document_type: Optional[DocumentType] = Query(None, description="Dokumenttyp filtern"),
    status: Optional[ProcessingStatus] = Query(None, description="Status filtern"),
    date_from: Optional[datetime] = Query(None, description="Erstellt nach"),
    date_to: Optional[datetime] = Query(None, description="Erstellt vor"),
    confidence_min: Optional[float] = Query(None, ge=0, le=100, description="Min. OCR-Konfidenz"),
    has_embedding: Optional[bool] = Query(None, description="Mit Embedding"),
    tags: Optional[List[str]] = Query(None, description="Tags filtern"),
    sort_by: SortField = Query(SortField.RELEVANCE, description="Sortierfeld"),
    sort_order: SortOrder = Query(SortOrder.DESC, description="Sortierreihenfolge"),
    highlight: bool = Query(True, description="Textausschnitte hervorheben"),
    similarity_threshold: float = Query(0.5, ge=0, le=1, description="Min. Aehnlichkeit fuer semantische Suche"),
    session_id: Optional[str] = Query(None, description="Session-ID fuer Analytics"),
    current_user: User = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_db)
):
    """Dokumente durchsuchen.

    Unterstuetzt drei Suchmodi:
    - **fts**: PostgreSQL Volltextsuche mit deutschen Wortstaemmen
    - **semantic**: Semantische Suche mit Embeddings (multilingual-e5-large)
    - **hybrid**: Kombination beider Methoden (empfohlen)

    Die Hybrid-Suche kombiniert Volltext- und semantische Ergebnisse
    mittels Reciprocal Rank Fusion fuer optimale Relevanz.
    """
    import time
    start_time = time.time()

    logger.info(
        "search_request",
        query=q[:50],
        search_type=search_type.value,
        user_id=str(current_user.id)
    )

    filters = SearchFilters(
        document_type=document_type,
        status=status,
        date_from=date_from,
        date_to=date_to,
        confidence_min=confidence_min,
        has_embedding=has_embedding,
        tags=tags
    )

    service = get_search_service()
    result = await service.search(
        db=db,
        query=q,
        user_id=current_user.id,
        search_type=search_type,
        filters=filters,
        page=page,
        per_page=per_page,
        sort_by=sort_by,
        sort_order=sort_order,
        highlight=highlight,
        similarity_threshold=similarity_threshold
    )

    # Log analytics asynchronously (non-blocking)
    try:
        from app.services.search_analytics_service import get_search_analytics_service
        analytics_service = get_search_analytics_service()

        execution_time_ms = int((time.time() - start_time) * 1000)

        # Get request metadata
        user_agent = request.headers.get("user-agent")
        # Get client IP (respect X-Forwarded-For for proxied requests)
        forwarded_for = request.headers.get("x-forwarded-for")
        client_ip = forwarded_for.split(",")[0].strip() if forwarded_for else request.client.host if request.client else None

        analytics_id = await analytics_service.log_search(
            db=db,
            query=q,
            search_type=search_type,
            total_results=result.total,
            execution_time_ms=execution_time_ms,
            user_id=current_user.id,
            filters=filters,
            page=page,
            per_page=per_page,
            session_id=session_id,
            user_agent=user_agent,
            ip_address=client_ip,
        )

        # Add analytics_id to response for click tracking
        result.analytics_id = analytics_id
    except Exception as e:
        # Don't fail the search if analytics logging fails
        logger.warning(
            "analytics_logging_failed",
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True  # Include full traceback for debugging
        )

    return result


@router.get("/{document_id}", response_model=DocumentDetailResponse)
async def get_document(
    document_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Einzelnes Dokument mit allen Details abrufen.

    Gibt alle Metadaten, OCR-Ergebnisse und Tags fuer
    das angeforderte Dokument zurueck.
    """
    service = get_document_service()
    document = await service.get_document(db, document_id, current_user.id)

    if not document:
        raise HTTPException(
            status_code=404,
            detail="Dokument nicht gefunden oder keine Berechtigung"
        )

    return document


@router.put("/{document_id}", response_model=DocumentDetailResponse)
async def update_document(
    document_id: UUID,
    update: DocumentUpdateRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Dokumentmetadaten aktualisieren.

    Erlaubt das Aendern von:
    - Dokumenttyp
    - Sprache
    - Tags
    - Benutzerdefinierte Metadaten
    """
    service = get_document_service()
    document = await service.update_document(
        db=db,
        document_id=document_id,
        user_id=current_user.id,
        document_type=update.document_type,
        language=update.language,
        tags=update.tags,
        metadata=update.metadata
    )

    if not document:
        raise HTTPException(
            status_code=404,
            detail="Dokument nicht gefunden oder keine Berechtigung"
        )

    logger.info(
        "document_updated_api",
        document_id=str(document_id),
        user_id=str(current_user.id)
    )

    return document


@router.delete("/{document_id}", status_code=204)
async def delete_document(
    document_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Dokument loeschen.

    Loescht das Dokument vollstaendig aus der Datenbank
    und dem Objektspeicher (MinIO).
    """
    service = get_document_service()
    success = await service.delete_document(db, document_id, current_user.id)

    if not success:
        raise HTTPException(
            status_code=404,
            detail="Dokument nicht gefunden oder keine Berechtigung"
        )

    logger.info(
        "document_deleted_api",
        document_id=str(document_id),
        user_id=str(current_user.id)
    )

    return Response(status_code=204)


# ==================== Similar Documents ====================

@router.get("/{document_id}/similar", response_model=List[SimilarDocumentItem])
async def get_similar_documents(
    document_id: UUID,
    limit: int = Query(10, ge=1, le=50, description="Maximale Anzahl Ergebnisse"),
    similarity_threshold: float = Query(0.6, ge=0, le=1, description="Min. Aehnlichkeit"),
    exclude_same_type: bool = Query(False, description="Gleichen Dokumenttyp ausschliessen"),
    current_user: User = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_db)
):
    """Aehnliche Dokumente basierend auf Inhalt finden.

    Verwendet semantische Embeddings um inhaltlich aehnliche
    Dokumente zu identifizieren. Nuetzlich fuer:
    - Duplikaterkennung
    - Thematisch verwandte Dokumente
    - Dokumentengruppierung
    """
    # Pruefen ob Dokument existiert und Zugriff erlaubt
    doc_service = get_document_service()
    document = await doc_service.get_document(db, document_id, current_user.id)

    if not document:
        raise HTTPException(
            status_code=404,
            detail="Dokument nicht gefunden oder keine Berechtigung"
        )

    if not document.has_embedding:
        raise HTTPException(
            status_code=400,
            detail="Dokument hat kein Embedding. Bitte OCR-Verarbeitung durchfuehren."
        )

    search_service = get_search_service()
    return await search_service.find_similar_documents(
        db=db,
        document_id=document_id,
        user_id=current_user.id,
        limit=limit,
        similarity_threshold=similarity_threshold,
        exclude_same_type=exclude_same_type
    )


# ==================== Batch Operations ====================

@router.post("/batch/delete", response_model=BatchOperationResult)
async def batch_delete_documents(
    request: BatchDeleteRequest,
    current_user: User = Depends(check_batch_rate_limit),
    db: AsyncSession = Depends(get_db)
):
    """Mehrere Dokumente gleichzeitig loeschen.

    Erfordert explizite Bestaetigung mit `confirm: true`.
    Maximal 100 Dokumente pro Anfrage.
    """
    if not request.confirm:
        raise HTTPException(
            status_code=400,
            detail="Loeschung muss mit confirm=true bestaetigt werden"
        )

    logger.info(
        "batch_delete_request",
        count=len(request.document_ids),
        user_id=str(current_user.id)
    )

    service = get_document_service()
    return await service.batch_delete(
        db=db,
        document_ids=request.document_ids,
        user_id=current_user.id
    )


@router.post("/batch/tag", response_model=BatchOperationResult)
async def batch_tag_documents(
    request: BatchTagRequest,
    current_user: User = Depends(check_batch_rate_limit),
    db: AsyncSession = Depends(get_db)
):
    """Tags fuer mehrere Dokumente verwalten.

    Operationen:
    - **add**: Tags hinzufuegen (Standard)
    - **remove**: Tags entfernen
    - **set**: Alle Tags ersetzen

    Maximal 100 Dokumente pro Anfrage.
    """
    logger.info(
        "batch_tag_request",
        count=len(request.document_ids),
        operation=request.operation.value,
        tags=request.tags,
        user_id=str(current_user.id)
    )

    service = get_document_service()
    return await service.batch_tag(
        db=db,
        document_ids=request.document_ids,
        tags=request.tags,
        user_id=current_user.id,
        operation=request.operation
    )


@router.post("/batch/export")
async def batch_export_documents(
    request: BatchExportRequest,
    current_user: User = Depends(check_batch_rate_limit),
    db: AsyncSession = Depends(get_db)
):
    """Mehrere Dokumente exportieren.

    Exportformate:
    - **json**: JSON-Array mit Dokumentdaten
    - **csv**: CSV-Tabelle (Text gekuerzt auf 1000 Zeichen)
    - **zip**: ZIP-Archiv mit einzelnen JSON-Dateien

    Maximal 100 Dokumente pro Anfrage.
    """
    logger.info(
        "batch_export_request",
        count=len(request.document_ids),
        format=request.format.value,
        user_id=str(current_user.id)
    )

    service = get_document_service()
    export_data, content_type, result = await service.batch_export(
        db=db,
        document_ids=request.document_ids,
        user_id=current_user.id,
        format=request.format,
        include_text=request.include_text,
        include_metadata=request.include_metadata
    )

    # Filename basierend auf Format
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    extension_map = {
        ExportFormat.JSON: "json",
        ExportFormat.CSV: "csv",
        ExportFormat.ZIP: "zip",
        ExportFormat.PDF: "pdf"
    }
    extension = extension_map.get(request.format, "json")
    filename = f"dokumente_export_{timestamp}.{extension}"

    return StreamingResponse(
        io.BytesIO(export_data),
        media_type=content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Export-Count": str(result.processed),
            "X-Export-Failed": str(result.failed)
        }
    )


# ==================== Statistics and Info ====================

@router.get("/stats/summary")
async def get_document_stats(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Dokumentstatistiken fuer den aktuellen Benutzer abrufen.

    Gibt aggregierte Statistiken ueber alle Dokumente zurueck:
    - Gesamtzahl Dokumente
    - Nach Status aufgeteilt
    - Nach Dokumenttyp aufgeteilt
    - Durchschnittliche OCR-Konfidenz
    - Anzahl mit Embeddings
    """
    from sqlalchemy import select, func
    from app.db.models import Document

    # Basis-Query fuer Benutzer
    base_filter = Document.owner_id == current_user.id

    # Gesamtzahl
    total_query = select(func.count(Document.id)).where(base_filter)
    total_result = await db.execute(total_query)
    total = total_result.scalar() or 0

    # Nach Status
    status_query = select(
        Document.status,
        func.count(Document.id)
    ).where(base_filter).group_by(Document.status)
    status_result = await db.execute(status_query)
    by_status = {row[0]: row[1] for row in status_result.fetchall()}

    # Nach Dokumenttyp
    type_query = select(
        Document.document_type,
        func.count(Document.id)
    ).where(base_filter).group_by(Document.document_type)
    type_result = await db.execute(type_query)
    by_type = {row[0]: row[1] for row in type_result.fetchall()}

    # Durchschnittliche Konfidenz
    conf_query = select(func.avg(Document.ocr_confidence)).where(
        base_filter,
        Document.ocr_confidence.isnot(None)
    )
    conf_result = await db.execute(conf_query)
    avg_confidence = conf_result.scalar() or 0

    # Mit Embeddings
    emb_query = select(func.count(Document.id)).where(
        base_filter,
        Document.embedding.isnot(None)
    )
    emb_result = await db.execute(emb_query)
    with_embeddings = emb_result.scalar() or 0

    return {
        "total_documents": total,
        "by_status": by_status,
        "by_document_type": by_type,
        "average_ocr_confidence": round(avg_confidence, 2) if avg_confidence else None,
        "documents_with_embeddings": with_embeddings,
        "embedding_coverage_percent": round(with_embeddings / total * 100, 1) if total > 0 else 0
    }


# ==================== Search Analytics ====================

@router.get("/stats/search-analytics")
async def get_search_analytics(
    days: int = Query(30, ge=1, le=365, description="Analysezeitraum in Tagen"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Such-Statistiken abrufen.

    Liefert aggregierte Statistiken ueber Suchanfragen:
    - Gesamtzahl der Suchen
    - Durchschnittliche Ergebnisse
    - Aufteilung nach Suchtyp
    - Top-Suchbegriffe
    - Filter-Nutzung
    """
    from app.services.search_analytics_service import get_search_analytics_service

    service = get_search_analytics_service()

    # Admin sieht alle Statistiken, normale Benutzer nur eigene
    user_filter = None if current_user.is_superuser else current_user.id

    return await service.get_search_statistics(
        db=db,
        days=days,
        user_id=user_filter
    )


@router.get("/stats/search-analytics/daily")
async def get_daily_search_analytics(
    days: int = Query(30, ge=1, le=365, description="Analysezeitraum in Tagen"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Taegliche Such-Statistiken abrufen.

    Liefert Statistiken pro Tag fuer Dashboard-Graphen:
    - Suchen pro Tag
    - Durchschnittliche Ausfuehrungszeit
    - Null-Ergebnis-Suchen
    """
    from app.services.search_analytics_service import get_search_analytics_service

    if not current_user.is_superuser:
        raise HTTPException(
            status_code=403,
            detail="Nur Administratoren koennen taegliche Statistiken abrufen"
        )

    service = get_search_analytics_service()
    return await service.get_daily_statistics(db=db, days=days)


@router.get("/stats/search-analytics/popular-terms")
async def get_popular_search_terms(
    days: int = Query(7, ge=1, le=90, description="Analysezeitraum in Tagen"),
    limit: int = Query(20, ge=1, le=100, description="Max. Anzahl Ergebnisse"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Beliebte Suchbegriffe abrufen.

    Nuetzlich fuer:
    - Verbesserung der Suchhilfe
    - Auto-Vervollstaendigung
    - Trend-Analyse
    """
    from app.services.search_analytics_service import get_search_analytics_service

    if not current_user.is_superuser:
        raise HTTPException(
            status_code=403,
            detail="Nur Administratoren koennen beliebte Suchbegriffe abrufen"
        )

    service = get_search_analytics_service()
    return await service.get_popular_search_terms(db=db, days=days, limit=limit)


@router.get("/stats/search-analytics/zero-results")
async def get_zero_result_queries(
    days: int = Query(7, ge=1, le=90, description="Analysezeitraum in Tagen"),
    limit: int = Query(20, ge=1, le=100, description="Max. Anzahl Ergebnisse"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Suchanfragen ohne Ergebnisse abrufen.

    Hilft bei der Identifikation von:
    - Fehlenden Dokumenten
    - Verbesserungsmoeglichkeiten bei der Suche
    - Haeufigen Tippfehlern
    """
    from app.services.search_analytics_service import get_search_analytics_service

    if not current_user.is_superuser:
        raise HTTPException(
            status_code=403,
            detail="Nur Administratoren koennen Null-Ergebnis-Suchen abrufen"
        )

    service = get_search_analytics_service()
    return await service.get_zero_result_queries(db=db, days=days, limit=limit)


@router.post("/stats/search-analytics/click")
async def log_search_click(
    analytics_id: UUID = Query(..., description="ID des Such-Analytics-Eintrags"),
    position: int = Query(..., ge=1, description="Position des geklickten Ergebnisses"),
    is_download: bool = Query(False, description="Wurde das Dokument heruntergeladen?"),
    current_user: User = Depends(check_rate_limit),  # Rate limiting hinzugefuegt
    db: AsyncSession = Depends(get_db)
):
    """Klick auf Suchergebnis protokollieren.

    Wird vom Frontend aufgerufen wenn ein Benutzer auf
    ein Suchergebnis klickt oder es herunterlädt.
    """
    from app.services.search_analytics_service import get_search_analytics_service

    service = get_search_analytics_service()
    await service.log_click(
        db=db,
        analytics_id=analytics_id,
        result_position=position,
        is_download=is_download
    )

    return {"status": "ok"}

# -*- coding: utf-8 -*-
"""
Lexware Import API Endpoints.

REST API für Lexware-Integration:
- Kunden-Import (Excel-Dateien von Folie/Messer)
- Lieferanten-Import (Excel-Dateien von Folie/Messer)
- Entity-Linking (Dokumente mit importierten Entities verknüpfen)
- Import-Status und Statistiken

Feinpoliert und durchdacht - Deutsche Geschäftsdokumente.
"""

from typing import Optional, List, Dict
from uuid import UUID
from datetime import datetime, timezone
from pathlib import Path
import tempfile

import structlog
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
    Query,
    UploadFile,
    File,
    BackgroundTasks,
)
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User, EntityType
from app.api.dependencies import get_db, get_current_active_user
from app.core.config import settings
from app.core.safe_errors import safe_error_log, safe_error_detail


logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/lexware", tags=["Lexware Integration"])


# =============================================================================
# PYDANTIC SCHEMAS
# =============================================================================


class LexwareImportRequest(BaseModel):
    """Request für Lexware-Import."""

    company: str = Field(
        ...,
        pattern="^(folie|messer)$",
        description="Firma: 'folie' oder 'messer'"
    )
    skip_conflicts: bool = Field(
        default=True,
        description="Kritische Konflikte überspringen (empfohlen)"
    )
    dry_run: bool = Field(
        default=False,
        description="Nur simulieren, keine Daten ändern"
    )

    model_config = ConfigDict(from_attributes=True)


class ConflictInfo(BaseModel):
    """Info über einen Import-Konflikt."""

    identifier: str = Field(..., description="Kundennummer oder Name")
    conflict_type: str = Field(..., description="critical, harmless, or duplicate")
    reason: str = Field(..., description="Grund für Konflikt")
    folie_value: Optional[str] = None
    messer_value: Optional[str] = None


class LexwareImportResponse(BaseModel):
    """Response für Lexware-Import."""

    success: bool
    imported_count: int = Field(..., description="Erfolgreich importierte Entities")
    updated_count: int = Field(..., description="Aktualisierte Entities")
    skipped_count: int = Field(..., description="Übersprungene Konflikte")
    error_count: int = Field(..., description="Fehler beim Import")
    conflicts: List[ConflictInfo] = Field(default_factory=list)
    message: str
    task_id: Optional[str] = Field(
        None,
        description="Celery Task ID für asynchronen Import"
    )

    model_config = ConfigDict(from_attributes=True)


class EntityLinkingRequest(BaseModel):
    """Request für Entity-Linking."""

    min_confidence: float = Field(
        default=0.75,
        ge=0.0,
        le=1.0,
        description="Minimale Confidence für automatische Verknüpfung"
    )
    only_unlinked: bool = Field(
        default=True,
        description="Nur Dokumente ohne BusinessEntity verknüpfen"
    )
    batch_size: int = Field(
        default=100,
        ge=1,
        le=1000,
        description="Batch-Größe für Verarbeitung"
    )
    async_mode: bool = Field(
        default=True,
        description="Asynchrone Verarbeitung via Celery"
    )

    model_config = ConfigDict(from_attributes=True)


class EntityLinkingResponse(BaseModel):
    """Response für Entity-Linking."""

    success: bool
    linked_count: int = Field(..., description="Erfolgreich verknüpfte Dokumente")
    unlinked_count: int = Field(..., description="Dokumente ohne Match")
    low_confidence_count: int = Field(
        ...,
        description="Dokumente mit Confidence unter Schwelle"
    )
    error_count: int = Field(..., description="Fehler bei Verknüpfung")
    already_linked_count: int = Field(
        default=0,
        description="Bereits verknüpfte Dokumente (übersprungen)"
    )
    message: str
    task_id: Optional[str] = Field(
        None,
        description="Celery Task ID für asynchrone Verarbeitung"
    )

    model_config = ConfigDict(from_attributes=True)


class LinkingStatistics(BaseModel):
    """Statistiken zum Entity-Linking."""

    total_documents: int
    linked_documents: int
    unlinked_documents: int
    linked_percentage: float
    by_match_type: dict = Field(
        default_factory=dict,
        description="Verknüpfungen nach Match-Typ"
    )
    by_confidence: dict = Field(
        default_factory=dict,
        description="Verteilung nach Confidence-Level"
    )
    by_entity_type: dict = Field(
        default_factory=dict,
        description="Verknüpfungen nach Entity-Typ"
    )

    model_config = ConfigDict(from_attributes=True)


class EntitySearchRequest(BaseModel):
    """Request für Entity-Suche."""

    query: str = Field(..., min_length=1, max_length=255)
    entity_type: Optional[str] = Field(
        None,
        pattern="^(customer|supplier)$",
        description="Optional: customer oder supplier"
    )
    company: Optional[str] = Field(
        None,
        pattern="^(folie|messer)$",
        description="Optional: folie oder messer"
    )
    limit: int = Field(default=20, ge=1, le=100)

    model_config = ConfigDict(from_attributes=True)


class EntitySearchResult(BaseModel):
    """Suchergebnis für Entity-Suche."""

    id: UUID
    name: str
    display_name: Optional[str]
    entity_type: str
    primary_customer_number: Optional[str]
    primary_supplier_number: Optional[str]
    company_presence: List[str] = Field(default_factory=list)
    similarity: float = Field(..., description="Ähnlichkeit (0.0-1.0)")
    match_type: str = Field(..., description="Art des Matches")

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# IMPORT ENDPOINTS
# =============================================================================


@router.post(
    "/import/customers",
    response_model=LexwareImportResponse,
    summary="Kunden aus Lexware importieren",
    description="Importiert Kundendaten aus Lexware Excel-Export"
)
async def import_customers(
    background_tasks: BackgroundTasks,
    folie_file: UploadFile = File(
        ...,
        description="Excel-Datei mit Folie-Kunden"
    ),
    messer_file: UploadFile = File(
        ...,
        description="Excel-Datei mit Messer-Kunden"
    ),
    skip_conflicts: bool = Query(
        True,
        description="Kritische Konflikte überspringen"
    ),
    dry_run: bool = Query(
        False,
        description="Nur simulieren, keine Daten ändern"
    ),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> LexwareImportResponse:
    """
    Importiert Kunden aus Lexware Excel-Dateien.

    **Ablauf:**
    1. Beide Excel-Dateien werden geladen
    2. Kunden werden nach Kundennummer gemerged
    3. Kritische Konflikte werden übersprungen (optional)
    4. Harmlose Varianten werden zu name_aliases zusammengeführt
    5. BusinessEntity wird pro Kunde erstellt

    **Schema:**
    - name = "{Kundennummer}_{Matchcode}" (z.B. "12345_MUELLER")
    - display_name = Firmenname
    - lexware_ids = {folie: {kd_nr, matchcode}, messer: {...}}

    **Konflikte:**
    - Kritische Konflikte (unterschiedliche Daten) werden ausgelassen
    - Harmlose Varianten (gleiche Daten) werden zusammengeführt
    """
    # Check admin permission
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nur Administratoren können Lexware-Daten importieren"
        )

    # WICHTIG: User-ID sofort erfassen, BEVOR DB-Operationen stattfinden!
    # Nach db.commit() kann der Zugriff auf current_user.id einen Lazy-Load
    # auslösen, der MissingGreenlet verursacht.
    user_id_str = str(current_user.id)

    # Validate file types
    for file in [folie_file, messer_file]:
        if not file.filename.endswith(('.xlsx', '.xls')):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Ungültiges Dateiformat: {file.filename}. Nur Excel-Dateien erlaubt."
            )

    # Import service
    from app.services.lexware_import_service import (
        LexwareImportService,
        get_lexware_import_service,
    )

    # Temp-Dateien für Excel-Uploads
    folie_path: Optional[Path] = None
    messer_path: Optional[Path] = None

    try:
        service = get_lexware_import_service(db)

        # Schreibe Upload-Bytes in temp-Dateien (Service erwartet Path)
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
            f.write(await folie_file.read())
            folie_path = Path(f.name)

        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
            f.write(await messer_file.read())
            messer_path = Path(f.name)

        # Import customers (Service erwartet Path-Objekte)
        result = await service.import_customers(
            folie_file=folie_path,
            messer_file=messer_path,
            skip_conflicts=skip_conflicts,
            dry_run=dry_run,
        )

        # Trigger entity linking in background (nur bei echtem Import)
        task_id = None
        if result.imported_count > 0 and not dry_run:
            from app.workers.tasks.entity_linking_tasks import (
                post_lexware_import_linking_task
            )
            task = post_lexware_import_linking_task.delay()
            task_id = task.id

        logger.info(
            "lexware_customer_import_completed",
            imported=result.imported_count,
            merged=result.merged_count,
            skipped=result.skipped_count,
            errors=result.error_count,
            dry_run=dry_run,
            user_id=user_id_str,
        )

        return LexwareImportResponse(
            success=True,
            imported_count=result.imported_count,
            updated_count=result.merged_count,  # merged_count = updated_count
            skipped_count=result.skipped_count,
            error_count=result.error_count,
            conflicts=[
                ConflictInfo(**c) for c in result.conflicts
            ] if hasattr(result, 'conflicts') else [],
            message=f"Import abgeschlossen: "
                    f"{result.imported_count} importiert, {result.merged_count} gemerged, "
                    f"{result.skipped_count} übersprungen",
            task_id=task_id,
        )

    except Exception as e:
        logger.exception(
            "lexware_customer_import_failed",
            **safe_error_log(e),
            user_id=user_id_str,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Import")
        )

    finally:
        # Cleanup temp files
        if folie_path and folie_path.exists():
            folie_path.unlink(missing_ok=True)
        if messer_path and messer_path.exists():
            messer_path.unlink(missing_ok=True)


@router.post(
    "/import/suppliers",
    response_model=LexwareImportResponse,
    summary="Lieferanten aus Lexware importieren",
    description="Importiert Lieferantendaten aus Lexware Excel-Export"
)
async def import_suppliers(
    background_tasks: BackgroundTasks,
    folie_file: UploadFile = File(
        ...,
        description="Excel-Datei mit Folie-Lieferanten"
    ),
    messer_file: UploadFile = File(
        ...,
        description="Excel-Datei mit Messer-Lieferanten"
    ),
    skip_conflicts: bool = Query(
        True,
        description="Kritische Konflikte überspringen"
    ),
    dry_run: bool = Query(
        False,
        description="Nur simulieren, keine Daten ändern"
    ),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> LexwareImportResponse:
    """
    Importiert Lieferanten aus Lexware Excel-Dateien.

    **Ablauf:**
    1. Beide Excel-Dateien werden geladen
    2. Lieferanten werden nach normalisiertem Namen gemerged
    3. Kritische Konflikte werden übersprungen (optional)
    4. Namensvarianten werden zusammengeführt

    **Schema:**
    - name = Lieferantenname (ohne Nummer, wegen Nummern-Chaos)
    - lexware_ids = {folie: {lief_nr, matchcode}, messer: {...}}
    """
    # Check admin permission
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nur Administratoren können Lexware-Daten importieren"
        )

    # WICHTIG: User-ID sofort erfassen, BEVOR DB-Operationen stattfinden!
    # Nach db.commit() kann der Zugriff auf current_user.id einen Lazy-Load
    # auslösen, der MissingGreenlet verursacht.
    user_id_str = str(current_user.id)

    # Validate file types
    for file in [folie_file, messer_file]:
        if not file.filename.endswith(('.xlsx', '.xls')):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Ungültiges Dateiformat: {file.filename}. Nur Excel-Dateien erlaubt."
            )

    # Import service
    from app.services.lexware_import_service import (
        LexwareImportService,
        get_lexware_import_service,
    )

    # Temp-Dateien für Excel-Uploads
    folie_path: Optional[Path] = None
    messer_path: Optional[Path] = None

    try:
        service = get_lexware_import_service(db)

        # Schreibe Upload-Bytes in temp-Dateien (Service erwartet Path)
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
            f.write(await folie_file.read())
            folie_path = Path(f.name)

        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
            f.write(await messer_file.read())
            messer_path = Path(f.name)

        # Import suppliers (Service erwartet Path-Objekte)
        result = await service.import_suppliers(
            folie_file=folie_path,
            messer_file=messer_path,
            skip_conflicts=skip_conflicts,
            dry_run=dry_run,
        )

        # Trigger entity linking in background (nur bei echtem Import)
        task_id = None
        if result.imported_count > 0 and not dry_run:
            from app.workers.tasks.entity_linking_tasks import (
                post_lexware_import_linking_task
            )
            task = post_lexware_import_linking_task.delay()
            task_id = task.id

        logger.info(
            "lexware_supplier_import_completed",
            imported=result.imported_count,
            merged=result.merged_count,
            skipped=result.skipped_count,
            errors=result.error_count,
            dry_run=dry_run,
            user_id=user_id_str,
        )

        return LexwareImportResponse(
            success=True,
            imported_count=result.imported_count,
            updated_count=result.merged_count,  # merged_count = updated_count
            skipped_count=result.skipped_count,
            error_count=result.error_count,
            conflicts=[
                ConflictInfo(**c) for c in result.conflicts
            ] if hasattr(result, 'conflicts') else [],
            message=f"Import abgeschlossen: "
                    f"{result.imported_count} importiert, {result.merged_count} gemerged, "
                    f"{result.skipped_count} übersprungen",
            task_id=task_id,
        )

    except Exception as e:
        logger.exception(
            "lexware_supplier_import_failed",
            **safe_error_log(e),
            user_id=user_id_str,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Import")
        )

    finally:
        # Cleanup temp files
        if folie_path and folie_path.exists():
            folie_path.unlink(missing_ok=True)
        if messer_path and messer_path.exists():
            messer_path.unlink(missing_ok=True)


# =============================================================================
# ENTITY LINKING ENDPOINTS
# =============================================================================


@router.post(
    "/link-documents",
    response_model=EntityLinkingResponse,
    summary="Dokumente mit Entities verknüpfen",
    description="Verknüpft bestehende Dokumente automatisch mit BusinessEntities"
)
async def link_documents(
    request: EntityLinkingRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> EntityLinkingResponse:
    """
    Verknüpft bestehende Dokumente mit BusinessEntities.

    **Matching-Strategien (nach Priorität):**
    1. Exakte Kundennummer im OCR-Text (99% Confidence)
    2. Exakter Matchcode im OCR-Text (95% Confidence)
    3. IBAN/VAT-ID Match (90% Confidence)
    4. Firmenname Fuzzy-Match (80% Confidence)
    5. Adress-Match (75% Confidence)

    **Modi:**
    - async_mode=True: Verarbeitung via Celery (empfohlen)
    - async_mode=False: Synchrone Verarbeitung (nur kleine Mengen)
    """
    # Check admin permission
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nur Administratoren können Entity-Linking durchführen"
        )

    if request.async_mode:
        # Async processing via Celery
        from app.workers.tasks.entity_linking_tasks import link_all_documents_task

        task = link_all_documents_task.delay(
            min_confidence=request.min_confidence,
            batch_size=request.batch_size,
            only_unlinked=request.only_unlinked,
        )

        logger.info(
            "entity_linking_started_async",
            task_id=task.id,
            min_confidence=request.min_confidence,
            user_id=str(current_user.id),
        )

        return EntityLinkingResponse(
            success=True,
            linked_count=0,
            unlinked_count=0,
            low_confidence_count=0,
            error_count=0,
            message="Entity-Linking gestartet. Task-ID für Status-Abfrage.",
            task_id=task.id,
        )

    else:
        # Synchronous processing
        from app.services.document_entity_linker_service import (
            DocumentEntityLinkerService,
            get_document_entity_linker_service,
        )

        try:
            service = get_document_entity_linker_service(db)
            result = await service.link_all_documents(
                min_confidence=request.min_confidence,
                batch_size=request.batch_size,
                only_unlinked=request.only_unlinked,
            )

            logger.info(
                "entity_linking_completed",
                linked=result.linked_count,
                unlinked=result.unlinked_count,
                low_confidence=result.low_confidence_count,
                errors=result.error_count,
                user_id=str(current_user.id),
            )

            return EntityLinkingResponse(
                success=True,
                linked_count=result.linked_count,
                unlinked_count=result.unlinked_count,
                low_confidence_count=result.low_confidence_count,
                error_count=result.error_count,
                already_linked_count=result.already_linked_count,
                message=f"Entity-Linking abgeschlossen: {result.linked_count} Dokumente verknüpft",
                task_id=None,
            )

        except Exception as e:
            logger.exception(
                "entity_linking_failed",
                **safe_error_log(e),
                user_id=str(current_user.id),
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=safe_error_detail(e, "Entity-Linking")
            )


@router.post(
    "/link-document/{document_id}",
    response_model=EntityLinkingResponse,
    summary="Einzelnes Dokument verknüpfen",
    description="Verknüpft ein einzelnes Dokument mit der besten BusinessEntity"
)
async def link_single_document(
    document_id: UUID,
    min_confidence: float = Query(
        0.75,
        ge=0.0,
        le=1.0,
        description="Minimale Confidence für Verknüpfung"
    ),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> EntityLinkingResponse:
    """
    Verknüpft ein einzelnes Dokument mit der besten BusinessEntity.

    Gibt Match-Details zurück (Entity, Confidence, Match-Typ).
    """
    from app.services.document_entity_linker_service import (
        get_document_entity_linker_service,
    )

    try:
        service = get_document_entity_linker_service(db)
        match = await service.link_document(
            document_id=document_id,
            min_confidence=min_confidence,
        )

        if match:
            return EntityLinkingResponse(
                success=True,
                linked_count=1,
                unlinked_count=0,
                low_confidence_count=0,
                error_count=0,
                message=f"Dokument verknüpft mit '{match.entity.name}' "
                        f"({match.match_type}, {match.confidence:.0%})",
                task_id=None,
            )
        else:
            return EntityLinkingResponse(
                success=True,
                linked_count=0,
                unlinked_count=1,
                low_confidence_count=0,
                error_count=0,
                message="Kein passender Geschäftspartner gefunden",
                task_id=None,
            )

    except Exception as e:
        logger.exception(
            "single_document_linking_failed",
            document_id=str(document_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Verknüpfen")
        )


@router.get(
    "/linking-statistics",
    response_model=LinkingStatistics,
    summary="Entity-Linking Statistiken",
    description="Statistiken zur Dokument-Entity-Verknüpfung"
)
async def get_linking_statistics(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> LinkingStatistics:
    """
    Liefert Statistiken zum Entity-Linking:
    - Anzahl verknüpfter/unverknüpfter Dokumente
    - Verteilung nach Match-Typ
    - Verteilung nach Confidence-Level
    """
    from sqlalchemy import select, func
    from app.db.models import Document

    # Total documents with OCR text
    total_stmt = select(func.count()).select_from(Document).where(
        Document.extracted_text.isnot(None),
        Document.extracted_text != "",
        Document.deleted_at.is_(None),
    )
    total_count = await db.scalar(total_stmt)

    # Linked documents
    linked_stmt = select(func.count()).select_from(Document).where(
        Document.extracted_text.isnot(None),
        Document.extracted_text != "",
        Document.deleted_at.is_(None),
        Document.business_entity_id.isnot(None),
    )
    linked_count = await db.scalar(linked_stmt)

    unlinked_count = total_count - linked_count
    linked_percentage = (linked_count / total_count * 100) if total_count > 0 else 0

    # Aggregate by entity type
    from app.db.models import BusinessEntity
    entity_type_stmt = (
        select(
            BusinessEntity.entity_type,
            func.count(Document.id).label("count")
        )
        .select_from(Document)
        .join(BusinessEntity, Document.business_entity_id == BusinessEntity.id)
        .where(
            Document.extracted_text.isnot(None),
            Document.deleted_at.is_(None),
        )
        .group_by(BusinessEntity.entity_type)
    )
    entity_type_results = await db.execute(entity_type_stmt)
    by_entity_type = {
        row.entity_type: row.count
        for row in entity_type_results
    }

    # Extract match type statistics from extracted_data if available
    # Format: extracted_data.entity_linking.match_type
    by_match_type: Dict[str, int] = {}
    by_confidence: Dict[str, int] = {}

    try:
        # Query documents with entity_linking data
        linked_docs_stmt = (
            select(Document.extracted_data)
            .where(
                Document.business_entity_id.isnot(None),
                Document.extracted_data.isnot(None),
                Document.deleted_at.is_(None),
            )
            .limit(1000)  # Limit für Performance
        )
        linked_docs_result = await db.execute(linked_docs_stmt)

        for row in linked_docs_result:
            data = row[0] or {}
            entity_link_info = data.get("entity_linking", {})

            # Match type aggregation
            match_type = entity_link_info.get("match_type")
            if match_type:
                by_match_type[match_type] = by_match_type.get(match_type, 0) + 1

            # Confidence bucketing
            confidence = entity_link_info.get("confidence")
            if confidence is not None:
                if confidence >= 0.95:
                    bucket = "excellent (>=95%)"
                elif confidence >= 0.85:
                    bucket = "good (85-94%)"
                elif confidence >= 0.75:
                    bucket = "fair (75-84%)"
                else:
                    bucket = "low (<75%)"
                by_confidence[bucket] = by_confidence.get(bucket, 0) + 1

    except Exception as e:
        logger.warning("linking_statistics_extended_error", **safe_error_log(e))

    return LinkingStatistics(
        total_documents=total_count,
        linked_documents=linked_count,
        unlinked_documents=unlinked_count,
        linked_percentage=round(linked_percentage, 1),
        by_match_type=by_match_type,
        by_confidence=by_confidence,
        by_entity_type=by_entity_type,
    )


# =============================================================================
# SEARCH ENDPOINTS
# =============================================================================


@router.post(
    "/search",
    response_model=List[EntitySearchResult],
    summary="Intelligente Entity-Suche",
    description="Sucht Entities nach Kundennummer, Matchcode, IBAN, oder Name"
)
async def search_entities(
    request: EntitySearchRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> List[EntitySearchResult]:
    """
    Intelligente Suche über alle Entity-Felder.

    Erkennt automatisch:
    - Kundennummer (nur Ziffern)
    - IBAN (beginnt mit Ländercode)
    - VAT-ID (DE + 9 Ziffern)
    - Name/Matchcode (alles andere)
    """
    from app.services.entity_search_service import (
        EntitySearchService,
        get_entity_search_service,
    )
    from app.db.models import EntityType as DbEntityType

    try:
        service = get_entity_search_service(db)

        # Map entity type
        entity_type_enum = None
        if request.entity_type:
            entity_type_enum = DbEntityType[request.entity_type.upper()]

        results = await service.smart_search(
            query=request.query,
            entity_type=entity_type_enum,
            company=request.company,
            limit=request.limit,
        )

        return [
            EntitySearchResult(
                id=entity.id,
                name=entity.name,
                display_name=entity.display_name,
                entity_type=entity.entity_type,
                primary_customer_number=entity.primary_customer_number,
                primary_supplier_number=entity.primary_supplier_number,
                company_presence=entity.company_presence or [],
                similarity=similarity,
                match_type=match_type,
            )
            for entity, similarity, match_type in results
        ]

    except Exception as e:
        logger.exception(
            "entity_search_failed",
            query=request.query,
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Suche")
        )


@router.get(
    "/entities/by-customer-number/{kd_nr}",
    summary="Entity nach Kundennummer finden",
    description="Findet BusinessEntity anhand der Kundennummer"
)
async def get_entity_by_customer_number(
    kd_nr: str,
    company: Optional[str] = Query(
        None,
        pattern="^(folie|messer)$",
        description="Optional: folie oder messer"
    ),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Findet BusinessEntity anhand der Kundennummer.

    Sucht in:
    1. primary_customer_number
    2. lexware_ids->folie->kd_nr
    3. lexware_ids->messer->kd_nr
    """
    from app.services.entity_search_service import get_entity_search_service

    service = get_entity_search_service(db)
    entity = await service.find_by_customer_number(kd_nr, company)

    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Kein Kunde mit Kundennummer '{kd_nr}' gefunden"
        )

    return {
        "id": str(entity.id),
        "name": entity.name,
        "display_name": entity.display_name,
        "primary_customer_number": entity.primary_customer_number,
        "company_presence": entity.company_presence or [],
        "lexware_ids": entity.lexware_ids or {},
    }


@router.get(
    "/entities/by-company/{company}",
    summary="Entities nach Firma auflisten",
    description="Listet alle Entities einer bestimmten Firma"
)
async def list_entities_by_company(
    company: str,
    entity_type: Optional[str] = Query(
        None,
        pattern="^(customer|supplier)$",
        description="Optional: customer oder supplier"
    ),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Listet alle Entities einer bestimmten Firma.
    """
    from app.services.entity_search_service import get_entity_search_service
    from app.db.models import EntityType as DbEntityType


    if company not in ("folie", "messer"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="company muss 'folie' oder 'messer' sein"
        )

    service = get_entity_search_service(db)

    entity_type_enum = None
    if entity_type:
        entity_type_enum = DbEntityType[entity_type.upper()]

    entities = await service.find_by_company(
        company=company,
        entity_type=entity_type_enum,
        limit=limit,
        offset=offset,
    )

    return {
        "count": len(entities),
        "entities": [
            {
                "id": str(e.id),
                "name": e.name,
                "display_name": e.display_name,
                "entity_type": e.entity_type,
                "primary_customer_number": e.primary_customer_number,
                "primary_supplier_number": e.primary_supplier_number,
            }
            for e in entities
        ]
    }

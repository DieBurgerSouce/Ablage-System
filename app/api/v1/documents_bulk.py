# -*- coding: utf-8 -*-
"""
Bulk Operations API - Massenaktionen fuer Dokumente.

Endpunkte fuer:
- POST /api/v1/documents/bulk/delete - Mehrere Dokumente loeschen
- POST /api/v1/documents/bulk/move - Mehrere Dokumente verschieben
- POST /api/v1/documents/bulk/tag - Tags fuer mehrere Dokumente setzen
- POST /api/v1/documents/bulk/export - Mehrere Dokumente exportieren
- POST /api/v1/documents/bulk/update - Mehrere Dokumente aktualisieren

Alle Operationen sind transaktionssicher und unterstuetzen dry_run Modus.
"""

import logging
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_active_user
from app.db.database import get_async_db
from app.db.models import User
from app.db.schemas import (
    BatchOperationResult,
    TagOperation,
    DocumentFilterForBulkUpdate,
    DocumentPartialUpdateRequest,
    BulkUpdateResult,
)
from app.services.document_services.batch_service import get_batch_service
from app.core.safe_errors import safe_error_log

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents/bulk", tags=["Bulk Operations"])


# =============================================================================
# REQUEST SCHEMAS
# =============================================================================

class BulkDeleteRequest(BaseModel):
    """Request fuer Bulk-Loeschung."""
    document_ids: List[UUID] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Liste der zu loeschenden Dokument-IDs (max. 100)"
    )
    soft_delete: bool = Field(
        True,
        description="True fuer Soft-Delete (30 Tage wiederherstellbar), "
                   "False fuer permanente Loeschung"
    )


class BulkMoveRequest(BaseModel):
    """Request fuer Bulk-Verschiebung."""
    document_ids: List[UUID] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Liste der zu verschiebenden Dokument-IDs"
    )
    target_folder_id: UUID = Field(
        ...,
        description="Zielordner-ID"
    )


class BulkTagRequest(BaseModel):
    """Request fuer Bulk-Tag-Operation."""
    document_ids: List[UUID] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Liste der Dokument-IDs"
    )
    tags: List[str] = Field(
        ...,
        min_length=1,
        max_length=20,
        description="Liste der Tag-Namen"
    )
    operation: TagOperation = Field(
        TagOperation.ADD,
        description="ADD (hinzufuegen), REMOVE (entfernen) oder SET (ersetzen)"
    )


class BulkExportRequest(BaseModel):
    """Request fuer Bulk-Export."""
    document_ids: List[UUID] = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Liste der zu exportierenden Dokument-IDs (max. 50)"
    )
    format: str = Field(
        "zip",
        pattern="^(zip|pdf|csv)$",
        description="Export-Format: zip, pdf (zusammengefuegt), csv (Metadaten)"
    )
    include_metadata: bool = Field(
        True,
        description="Metadaten-JSON beilegen"
    )


class BulkUpdateRequest(BaseModel):
    """Request fuer Bulk-Update."""
    filter: DocumentFilterForBulkUpdate = Field(
        ...,
        description="Filter fuer zu aktualisierende Dokumente"
    )
    updates: DocumentPartialUpdateRequest = Field(
        ...,
        description="Anzuwendende Aenderungen"
    )


# =============================================================================
# BULK DELETE
# =============================================================================

@router.post(
    "/delete",
    response_model=BatchOperationResult,
    summary="Mehrere Dokumente loeschen",
    description="""
    Loescht mehrere Dokumente in einer atomaren Operation.

    **Soft-Delete (Standard):**
    - Dokumente werden als geloescht markiert
    - 30 Tage lang wiederherstellbar
    - DSGVO-konform

    **Hard-Delete:**
    - Permanente Loeschung
    - Nicht wiederherstellbar
    - Nur mit expliziter Bestaetigung

    **Limits:**
    - Maximal 100 Dokumente pro Request
    """
)
async def bulk_delete(
    request: BulkDeleteRequest,
    dry_run: bool = Query(
        False,
        description="Nur simulieren, keine echte Loeschung"
    ),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_user),
) -> BatchOperationResult:
    """Loescht mehrere Dokumente."""
    batch_service = get_batch_service()

    try:
        result = await batch_service.batch_delete(
            db=db,
            document_ids=request.document_ids,
            user_id=current_user.id,
            dry_run=dry_run,
            soft_delete=request.soft_delete,
        )

        if not result.success and result.processed == 0:
            raise HTTPException(
                status_code=400,
                detail=result.message
            )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error("bulk_delete_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=500,
            detail="Bulk-Loeschung fehlgeschlagen"
        )


# =============================================================================
# BULK MOVE
# =============================================================================

@router.post(
    "/move",
    response_model=BatchOperationResult,
    summary="Mehrere Dokumente verschieben",
    description="""
    Verschiebt mehrere Dokumente in einen anderen Ordner.

    **Hinweise:**
    - Zielordner muss existieren und dem Benutzer gehoeren
    - Dokumente behalten ihre Tags und Metadaten

    **Limits:**
    - Maximal 100 Dokumente pro Request
    """
)
async def bulk_move(
    request: BulkMoveRequest,
    dry_run: bool = Query(
        False,
        description="Nur simulieren"
    ),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_user),
) -> BatchOperationResult:
    """Verschiebt mehrere Dokumente."""
    from sqlalchemy import select, update, and_
    from app.db.models import Document, Folder

    try:
        # Zielordner validieren
        folder_query = select(Folder).where(
            and_(
                Folder.id == request.target_folder_id,
                Folder.owner_id == current_user.id
            )
        )
        folder_result = await db.execute(folder_query)
        target_folder = folder_result.scalar_one_or_none()

        if not target_folder:
            raise HTTPException(
                status_code=404,
                detail="Zielordner nicht gefunden oder keine Berechtigung"
            )

        if dry_run:
            # Zaehlen wie viele Dokumente gefunden werden
            count_query = select(Document.id).where(
                and_(
                    Document.id.in_(request.document_ids),
                    Document.owner_id == current_user.id
                )
            )
            count_result = await db.execute(count_query)
            found_count = len(count_result.fetchall())

            return BatchOperationResult(
                success=True,
                operation="move",
                total_requested=len(request.document_ids),
                processed=found_count,
                failed=len(request.document_ids) - found_count,
                errors=[],
                message=f"[DRY RUN] {found_count} Dokument(e) wuerden verschoben",
                dry_run=True,
            )

        # Bulk-Move ausfuehren
        update_stmt = update(Document).where(
            and_(
                Document.id.in_(request.document_ids),
                Document.owner_id == current_user.id
            )
        ).values(folder_id=request.target_folder_id)

        result = await db.execute(update_stmt)
        await db.commit()

        processed = result.rowcount
        failed = len(request.document_ids) - processed

        return BatchOperationResult(
            success=failed == 0,
            operation="move",
            total_requested=len(request.document_ids),
            processed=processed,
            failed=failed,
            errors=[],
            message=f"{processed} Dokument(e) verschoben" if failed == 0
                   else f"{processed} von {len(request.document_ids)} Dokument(en) verschoben",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("bulk_move_failed", **safe_error_log(e))
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Bulk-Verschiebung fehlgeschlagen"
        )


# =============================================================================
# BULK TAG
# =============================================================================

@router.post(
    "/tag",
    response_model=BatchOperationResult,
    summary="Tags fuer mehrere Dokumente setzen",
    description="""
    Fuegt Tags hinzu, entfernt sie oder ersetzt alle Tags.

    **Operationen:**
    - ADD: Tags zu bestehenden hinzufuegen
    - REMOVE: Tags entfernen
    - SET: Alle Tags ersetzen

    **Limits:**
    - Maximal 100 Dokumente pro Request
    - Maximal 20 Tags pro Request
    """
)
async def bulk_tag(
    request: BulkTagRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_user),
) -> BatchOperationResult:
    """Setzt Tags fuer mehrere Dokumente."""
    batch_service = get_batch_service()

    try:
        result = await batch_service.batch_tag(
            db=db,
            document_ids=request.document_ids,
            tags=request.tags,
            user_id=current_user.id,
            operation=request.operation,
        )

        return result

    except Exception as e:
        logger.error("bulk_tag_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=500,
            detail="Bulk-Tag-Operation fehlgeschlagen"
        )


# =============================================================================
# BULK EXPORT
# =============================================================================

@router.post(
    "/export",
    summary="Mehrere Dokumente exportieren",
    description="""
    Exportiert mehrere Dokumente in einem Archiv.

    **Formate:**
    - zip: Alle Dokumente als ZIP-Archiv
    - pdf: Alle PDFs in einem zusammengefuegten PDF
    - csv: Nur Metadaten als CSV

    **Limits:**
    - Maximal 50 Dokumente pro Request

    **Rueckgabe:**
    - Task-ID fuer asynchronen Export
    """
)
async def bulk_export(
    request: BulkExportRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_user),
) -> dict:
    """Exportiert mehrere Dokumente."""
    from app.workers.tasks import document_bulk_export_task

    try:
        # Celery Task starten
        task = document_bulk_export_task.delay(
            document_ids=[str(doc_id) for doc_id in request.document_ids],
            user_id=str(current_user.id),
            export_format=request.format,
            include_metadata=request.include_metadata,
        )

        return {
            "task_id": task.id,
            "status": "queued",
            "message": f"Export von {len(request.document_ids)} Dokumenten gestartet",
            "format": request.format,
            "document_count": len(request.document_ids),
        }

    except Exception as e:
        logger.error("bulk_export_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=500,
            detail="Export konnte nicht gestartet werden"
        )


# =============================================================================
# BULK UPDATE
# =============================================================================

@router.post(
    "/update",
    response_model=BulkUpdateResult,
    summary="Mehrere Dokumente aktualisieren",
    description="""
    Aktualisiert Dokumente basierend auf Filterkriterien.

    **Filter-Optionen:**
    - document_ids: Spezifische IDs
    - document_type: Dokumenttyp
    - status: Status
    - date_from/date_to: Datumsbereich
    - tags: Mit bestimmten Tags

    **Update-Optionen:**
    - document_type: Neuer Typ
    - language: Neue Sprache
    - metadata: Metadaten erweitern
    - tags/add_tags/remove_tags: Tag-Operationen
    """
)
async def bulk_update(
    request: BulkUpdateRequest,
    dry_run: bool = Query(
        False,
        description="Nur simulieren"
    ),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_user),
) -> BulkUpdateResult:
    """Aktualisiert mehrere Dokumente."""
    batch_service = get_batch_service()

    try:
        result = await batch_service.bulk_update(
            db=db,
            user_id=current_user.id,
            filter_criteria=request.filter,
            updates=request.updates,
            dry_run=dry_run,
        )

        return result

    except Exception as e:
        logger.error("bulk_update_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=500,
            detail="Bulk-Update fehlgeschlagen"
        )


# =============================================================================
# BULK RESTORE (Soft-Delete rueckgaengig machen)
# =============================================================================

@router.post(
    "/restore",
    response_model=BatchOperationResult,
    summary="Geloeschte Dokumente wiederherstellen",
    description="""
    Stellt soft-geloeschte Dokumente wieder her.

    **Hinweise:**
    - Nur fuer Dokumente im Soft-Delete-Status
    - Maximal 30 Tage nach Loeschung

    **Limits:**
    - Maximal 100 Dokumente pro Request
    """
)
async def bulk_restore(
    document_ids: List[UUID] = Query(
        ...,
        min_length=1,
        max_length=100,
        description="Liste der wiederherzustellenden Dokument-IDs"
    ),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_user),
) -> BatchOperationResult:
    """Stellt geloeschte Dokumente wieder her."""
    from sqlalchemy import select, update, and_
    from app.db.models import Document

    try:
        # Nur soft-geloeschte Dokumente aktualisieren
        update_stmt = update(Document).where(
            and_(
                Document.id.in_(document_ids),
                Document.owner_id == current_user.id,
                Document.deleted_at.isnot(None)  # Muss soft-deleted sein
            )
        ).values(
            deleted_at=None,
            deleted_by_id=None
        )

        result = await db.execute(update_stmt)
        await db.commit()

        processed = result.rowcount
        failed = len(document_ids) - processed

        return BatchOperationResult(
            success=failed == 0,
            operation="restore",
            total_requested=len(document_ids),
            processed=processed,
            failed=failed,
            errors=[],
            message=f"{processed} Dokument(e) wiederhergestellt" if failed == 0
                   else f"{processed} von {len(document_ids)} Dokument(en) wiederhergestellt",
        )

    except Exception as e:
        logger.error("bulk_restore_failed", **safe_error_log(e))
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Wiederherstellung fehlgeschlagen"
        )

"""
Portal Documents API.

Dokument-Upload für Kundenportal.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from fastapi.responses import Response
from app.core.safe_errors import safe_error_detail
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db
from app.api.v1.portal.auth import get_current_portal_user
from app.services.portal import get_portal_document_service, PortalDocumentService
from app.db.models_portal import PortalUser

router = APIRouter(prefix="/documents", tags=["Portal-Dokumente"])


@router.get("/allowed-types")
async def get_allowed_file_types():
    """
    Hole erlaubte Dateitypen für Upload.
    """
    return {
        "types": PortalDocumentService.get_allowed_file_types(),
        "max_file_size": PortalDocumentService.get_max_file_size(),
        "max_file_size_mb": PortalDocumentService.get_max_file_size() // (1024 * 1024),
    }


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    description: Optional[str] = Form(None),
    document_type: Optional[str] = Form(None),
    complaint_id: Optional[UUID] = Form(None),
    message_id: Optional[UUID] = Form(None),
    portal_user: PortalUser = Depends(get_current_portal_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Lade ein Dokument hoch.
    """
    if not portal_user.can_upload_documents:
        raise HTTPException(
            status_code=403,
            detail="Keine Berechtigung für Dokument-Upload",
        )

    # Lese Dateiinhalt
    content = await file.read()

    service = get_portal_document_service(db)

    try:
        portal_doc = await service.upload_document(
            portal_user=portal_user,
            filename=file.filename or "unknown",
            content=content,
            content_type=file.content_type,
            description=description,
            document_type=document_type,
            complaint_id=complaint_id,
            message_id=message_id,
        )

        return {
            "success": True,
            "document_id": str(portal_doc.id),
            "filename": portal_doc.original_filename,
            "file_size": portal_doc.file_size,
            "message": "Dokument erfolgreich hochgeladen",
        }

    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=safe_error_detail(e, "Dokument"),
        )


@router.get("")
async def list_documents(
    complaint_id: Optional[UUID] = Query(None),
    document_type: Optional[str] = Query(None),
    page: int = Query(1, ge=1, description="Seitennummer (1-basiert)"),
    per_page: int = Query(50, ge=1, le=100, description="Eintraege pro Seite"),
    portal_user: PortalUser = Depends(get_current_portal_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Liste alle hochgeladenen Dokumente.
    """
    service = get_portal_document_service(db)

    documents, total = await service.get_documents(
        entity_id=portal_user.entity_id,
        company_id=portal_user.company_id,
        complaint_id=complaint_id,
        document_type=document_type,
        limit=per_page,
        offset=(page - 1) * per_page,
    )

    return {
        "items": documents,
        "total": total,
        "page": page,
        "per_page": per_page,
    }


@router.get("/{document_id}")
async def get_document_detail(
    document_id: UUID,
    portal_user: PortalUser = Depends(get_current_portal_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Hole Details eines Dokuments.
    """
    service = get_portal_document_service(db)

    detail = await service.get_document_detail(
        document_id=document_id,
        entity_id=portal_user.entity_id,
        company_id=portal_user.company_id,
    )

    if not detail:
        raise HTTPException(
            status_code=404,
            detail="Dokument nicht gefunden",
        )

    return detail


@router.get("/{document_id}/download")
async def download_document(
    document_id: UUID,
    portal_user: PortalUser = Depends(get_current_portal_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Lade ein Dokument herunter.
    """
    service = get_portal_document_service(db)

    result = await service.get_document_content(
        document_id=document_id,
        entity_id=portal_user.entity_id,
        company_id=portal_user.company_id,
    )

    if not result:
        raise HTTPException(
            status_code=404,
            detail="Dokument nicht gefunden",
        )

    content, filename, content_type = result

    return Response(
        content=content,
        media_type=content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@router.delete("/{document_id}")
async def delete_document(
    document_id: UUID,
    portal_user: PortalUser = Depends(get_current_portal_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Lösche ein hochgeladenes Dokument.

    Nur möglich wenn noch nicht verarbeitet.
    """
    service = get_portal_document_service(db)

    success = await service.delete_document(
        document_id=document_id,
        portal_user=portal_user,
    )

    if not success:
        raise HTTPException(
            status_code=400,
            detail="Löschen nicht möglich (nicht gefunden oder bereits verarbeitet)",
        )

    return {
        "success": True,
        "message": "Dokument gelöscht",
    }

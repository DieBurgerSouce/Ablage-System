"""Visual Version Diff API Router.

Endpoints für Seite-an-Seite Dokumentenvergleich.
"""
from __future__ import annotations

import base64
from dataclasses import asdict
from typing import Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from uuid import UUID
from app.api.dependencies import get_current_user, get_user_company_id_dep
from app.db.session import get_async_session
from app.services.diff.visual_diff_service import VisualDiffService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/visual-diff", tags=["visual-diff"])


class DiffRequest(BaseModel):
    """Schema für Vergleichsanfrage."""
    text_a: str = Field(..., min_length=1, max_length=500000)
    text_b: str = Field(..., min_length=1, max_length=500000)
    document_a_id: Optional[str] = None
    document_b_id: Optional[str] = None
    context_lines: int = Field(default=3, ge=0, le=10)


class DiffBlockResponse(BaseModel):
    """Schema für einen Diff-Block."""
    diff_type: str
    old_text: str = ""
    new_text: str = ""
    old_line_start: int = 0
    old_line_end: int = 0
    new_line_start: int = 0
    new_line_end: int = 0
    page_number: int = 1


class DiffResponse(BaseModel):
    """Schema für Vergleichsergebnis."""
    document_a_id: str
    document_b_id: str
    total_changes: int
    additions: int
    deletions: int
    modifications: int
    similarity_ratio: float
    blocks: list[DiffBlockResponse]
    summary: str


class ChangeSummaryResponse(BaseModel):
    """Schema für Änderungszusammenfassung."""
    total_changes: int
    additions: int
    deletions: int
    modifications: int
    similarity_percentage: float
    key_changes: list[str]
    risk_level: str


class ImageDiffRequest(BaseModel):
    """Schema fuer Bild-Vergleichsanfrage."""
    document_a_id: UUID = Field(..., description="ID des ersten Dokuments")
    document_b_id: UUID = Field(..., description="ID des zweiten Dokuments")
    page: int = Field(1, ge=1, description="Seitennummer (1-basiert)")
    threshold: int = Field(30, ge=0, le=255, description="Pixel-Differenz-Schwellwert")


class DocumentDiffRequest(BaseModel):
    """Schema fuer Dokumenten-Vergleichsanfrage per ID."""
    document_a_id: UUID = Field(..., description="ID des ersten Dokuments")
    document_b_id: UUID = Field(..., description="ID des zweiten Dokuments")
    context_lines: int = Field(default=3, ge=0, le=10, description="Kontext-Zeilen um Aenderungen")


class ImageDiffResponse(BaseModel):
    """Schema fuer Bild-Vergleichsergebnis."""
    similarity_score: float = Field(..., ge=0.0, le=1.0)
    changed_percentage: float = Field(..., ge=0.0, le=100.0)
    diff_image_base64: str = Field(..., description="Diff-Bild als Base64-PNG")
    overlay_image_base64: str = Field(..., description="Overlay-Bild als Base64-PNG")
    dimensions: list[int] = Field(..., description="Bildgroesse [breite, hoehe]")


@router.post("/compare", response_model=DiffResponse)
async def compare_texts(
    data: DiffRequest,
    current_user: dict = Depends(get_current_user),
) -> DiffResponse:
    """Vergleicht zwei Texte und gibt Diff zurück."""
    service = VisualDiffService()
    result = service.compare_texts(
        text_a=data.text_a,
        text_b=data.text_b,
        document_a_id=data.document_a_id or "",
        document_b_id=data.document_b_id or "",
        context_lines=data.context_lines,
    )
    return DiffResponse(
        document_a_id=result.document_a_id,
        document_b_id=result.document_b_id,
        total_changes=result.total_changes,
        additions=result.additions,
        deletions=result.deletions,
        modifications=result.modifications,
        similarity_ratio=result.similarity_ratio,
        blocks=[
            DiffBlockResponse(
                diff_type=b.diff_type.value,
                old_text=b.old_text,
                new_text=b.new_text,
                old_line_start=b.old_line_start,
                old_line_end=b.old_line_end,
                new_line_start=b.new_line_start,
                new_line_end=b.new_line_end,
                page_number=b.page_number,
            )
            for b in result.blocks
        ],
        summary=result.summary,
    )


@router.post("/compare/summary", response_model=ChangeSummaryResponse)
async def compare_texts_summary(
    data: DiffRequest,
    current_user: dict = Depends(get_current_user),
) -> ChangeSummaryResponse:
    """Vergleicht zwei Texte und gibt nur die Zusammenfassung zurück."""
    service = VisualDiffService()
    result = service.compare_texts(
        text_a=data.text_a,
        text_b=data.text_b,
        document_a_id=data.document_a_id or "",
        document_b_id=data.document_b_id or "",
    )
    summary = service.generate_change_summary(result)
    return ChangeSummaryResponse(
        total_changes=summary.total_changes,
        additions=summary.additions,
        deletions=summary.deletions,
        modifications=summary.modifications,
        similarity_percentage=summary.similarity_percentage,
        key_changes=summary.key_changes,
        risk_level=summary.risk_level,
    )


@router.post("/hash")
async def compute_hash(
    text: str = Body(..., min_length=1, embed=True),
    current_user: dict = Depends(get_current_user),
) -> dict[str, str]:
    """Berechnet SHA-256 Hash eines Textes."""
    service = VisualDiffService()
    return {"hash": service.compute_text_hash(text)}


@router.post("/compare/image", response_model=ImageDiffResponse)
async def compare_document_images(
    request: ImageDiffRequest,
    db: AsyncSession = Depends(get_async_session),
    current_user: dict = Depends(get_current_user),
) -> ImageDiffResponse:
    """Vergleicht zwei Dokumente pixelweise als Bilder.

    Rendert die angegebene Seite beider Dokumente und erstellt
    einen pixelweisen Vergleich mit Diff- und Overlay-Bildern.
    """
    from app.db.models import Document
    from app.services.diff.image_diff_service import ImageDiffService
    from app.services.storage_service import StorageService
    from sqlalchemy import select

    try:
        # Dokumente laden
        doc_a_result = await db.execute(
            select(Document).where(Document.id == request.document_a_id)
        )
        doc_a = doc_a_result.scalar_one_or_none()
        if not doc_a:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Dokument A nicht gefunden: {request.document_a_id}",
            )

        doc_b_result = await db.execute(
            select(Document).where(Document.id == request.document_b_id)
        )
        doc_b = doc_b_result.scalar_one_or_none()
        if not doc_b:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Dokument B nicht gefunden: {request.document_b_id}",
            )

        # Dateien aus MinIO laden
        storage = StorageService()
        response_a = storage.client.get_object(
            bucket_name=storage.config.DOCUMENTS_BUCKET,
            object_name=doc_a.file_path,
        )
        try:
            file_a_bytes = response_a.read()
        finally:
            response_a.close()
            response_a.release_conn()

        response_b = storage.client.get_object(
            bucket_name=storage.config.DOCUMENTS_BUCKET,
            object_name=doc_b.file_path,
        )
        try:
            file_b_bytes = response_b.read()
        finally:
            response_b.close()
            response_b.release_conn()

        # Bildvergleich durchfuehren
        service = ImageDiffService()
        result = service.compare_document_pages(
            doc_a_bytes=file_a_bytes,
            doc_b_bytes=file_b_bytes,
            page=request.page,
            threshold=request.threshold,
        )

        return ImageDiffResponse(
            similarity_score=result.similarity_score,
            changed_percentage=result.changed_percentage,
            diff_image_base64=base64.b64encode(result.diff_image_bytes).decode("ascii"),
            overlay_image_base64=base64.b64encode(result.overlay_image_bytes).decode("ascii"),
            dimensions=list(result.dimensions),
        )

    except HTTPException:
        raise
    except Exception as e:
        from app.core.safe_errors import safe_error_detail, safe_error_log
        logger.error(
            "image_diff_error",
            document_a_id=str(request.document_a_id),
            document_b_id=str(request.document_b_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Bild-Vergleich"),
        )


@router.post("/compare/documents", response_model=DiffResponse)
async def compare_documents_by_id(
    request: DocumentDiffRequest,
    db: AsyncSession = Depends(get_async_session),
    current_user: "User" = Depends(get_current_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> DiffResponse:
    """Vergleicht zwei Dokumente anhand ihrer IDs per Text-Diff.

    Laedt den extrahierten Text beider Dokumente aus der Datenbank
    und fuehrt einen zeilenweisen Textvergleich durch.
    """
    from app.db.models import Document
    from app.core.safe_errors import safe_error_detail, safe_error_log
    from sqlalchemy import select

    try:
        # Dokument A laden
        doc_a_result = await db.execute(
            select(Document).where(Document.id == request.document_a_id)
        )
        doc_a = doc_a_result.scalar_one_or_none()
        if not doc_a:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Dokument A nicht gefunden: {request.document_a_id}",
            )

        # Multi-Tenant-Isolation fuer Dokument A pruefen
        if doc_a.company_id != company_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Kein Zugriff auf dieses Dokument",
            )

        # Dokument B laden
        doc_b_result = await db.execute(
            select(Document).where(Document.id == request.document_b_id)
        )
        doc_b = doc_b_result.scalar_one_or_none()
        if not doc_b:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Dokument B nicht gefunden: {request.document_b_id}",
            )

        # Multi-Tenant-Isolation fuer Dokument B pruefen
        if doc_b.company_id != company_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Kein Zugriff auf dieses Dokument",
            )

        # Extrahierten Text validieren
        if not doc_a.extracted_text:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Dokument {request.document_a_id} hat keinen extrahierten Text",
            )
        if not doc_b.extracted_text:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Dokument {request.document_b_id} hat keinen extrahierten Text",
            )

        # Text-Diff durchfuehren
        service = VisualDiffService()
        result = service.compare_texts(
            text_a=doc_a.extracted_text,
            text_b=doc_b.extracted_text,
            document_a_id=str(request.document_a_id),
            document_b_id=str(request.document_b_id),
            context_lines=request.context_lines,
        )

        return DiffResponse(
            document_a_id=result.document_a_id,
            document_b_id=result.document_b_id,
            total_changes=result.total_changes,
            additions=result.additions,
            deletions=result.deletions,
            modifications=result.modifications,
            similarity_ratio=result.similarity_ratio,
            blocks=[
                DiffBlockResponse(
                    diff_type=b.diff_type.value,
                    old_text=b.old_text,
                    new_text=b.new_text,
                    old_line_start=b.old_line_start,
                    old_line_end=b.old_line_end,
                    new_line_start=b.new_line_start,
                    new_line_end=b.new_line_end,
                    page_number=b.page_number,
                )
                for b in result.blocks
            ],
            summary=result.summary,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "document_diff_error",
            document_a_id=str(request.document_a_id),
            document_b_id=str(request.document_b_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Dokument-Vergleich"),
        )

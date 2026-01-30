"""Dokument-Annotationen API Router.

Endpoints fuer PDF/Bild-Annotationen mit Threading und @-Mentions.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.db.session import get_async_session
from app.services.annotations.annotation_service import AnnotationService

router = APIRouter(prefix="/annotations", tags=["annotations"])


class AnnotationCreate(BaseModel):
    """Schema fuer neue Annotation."""
    document_id: UUID
    annotation_type: str = Field(..., pattern="^(comment|highlight|drawing|approval|rejection)$")
    content: str = Field(..., min_length=1, max_length=5000)
    page_number: int = Field(default=1, ge=1)
    position: Optional[dict[str, float]] = None
    svg_data: Optional[str] = None
    parent_annotation_id: Optional[UUID] = None
    mentioned_user_ids: Optional[list[UUID]] = None


class AnnotationUpdate(BaseModel):
    """Schema fuer Annotation-Update."""
    content: Optional[str] = Field(None, min_length=1, max_length=5000)
    is_resolved: Optional[bool] = None


class AnnotationResponse(BaseModel):
    """Schema fuer Annotation-Antwort."""
    id: UUID
    document_id: UUID
    user_id: UUID
    annotation_type: str
    content: str
    page: int  # Matches DocumentAnnotation.page field
    position: dict[str, float]
    svg_data: Optional[str] = None
    parent_annotation_id: Optional[UUID] = None
    mentioned_user_ids: list[str]
    is_resolved: bool
    resolved_by_id: Optional[UUID] = None
    created_at: str

    model_config = {"from_attributes": True}


@router.post("", response_model=AnnotationResponse, status_code=status.HTTP_201_CREATED)
async def create_annotation(
    data: AnnotationCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> AnnotationResponse:
    """Erstellt eine neue Annotation."""
    service = AnnotationService(db)
    annotation = await service.create_annotation(
        document_id=data.document_id,
        user_id=current_user["id"],
        company_id=current_user["company_id"],
        annotation_type=data.annotation_type,
        content=data.content,
        page_number=data.page_number,
        position=data.position,
        svg_data=data.svg_data,
        parent_annotation_id=data.parent_annotation_id,
        mentioned_user_ids=data.mentioned_user_ids,
    )
    await db.commit()
    return annotation


@router.get("/document/{document_id}")
async def get_document_annotations(
    document_id: UUID,
    page_number: Optional[int] = None,
    annotation_type: Optional[str] = None,
    include_resolved: bool = False,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> list[AnnotationResponse]:
    """Holt alle Annotationen fuer ein Dokument."""
    service = AnnotationService(db)
    annotations = await service.get_annotations_for_document(
        document_id=document_id,
        company_id=current_user["company_id"],
        page_number=page_number,
        annotation_type=annotation_type,
        include_resolved=include_resolved,
    )
    return annotations


@router.get("/{annotation_id}/thread")
async def get_annotation_thread(
    annotation_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> list[AnnotationResponse]:
    """Holt einen Annotation-Thread."""
    service = AnnotationService(db)
    thread = await service.get_thread(
        annotation_id=annotation_id,
        company_id=current_user["company_id"],
    )
    return thread


@router.patch("/{annotation_id}", response_model=AnnotationResponse)
async def update_annotation(
    annotation_id: UUID,
    data: AnnotationUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> AnnotationResponse:
    """Aktualisiert eine Annotation."""
    service = AnnotationService(db)
    annotation = await service.update_annotation(
        annotation_id=annotation_id,
        company_id=current_user["company_id"],
        user_id=current_user["id"],
        content=data.content,
        is_resolved=data.is_resolved,
    )
    if not annotation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Annotation nicht gefunden",
        )
    await db.commit()
    return annotation


@router.delete("/{annotation_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_annotation(
    annotation_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Loescht eine Annotation (nur eigene)."""
    service = AnnotationService(db)
    deleted = await service.delete_annotation(
        annotation_id=annotation_id,
        company_id=current_user["company_id"],
        user_id=current_user["id"],
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Annotation nicht gefunden oder keine Berechtigung",
        )
    await db.commit()


@router.get("/document/{document_id}/stats")
async def get_annotation_stats(
    document_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> dict[str, int]:
    """Statistiken fuer Dokument-Annotationen."""
    service = AnnotationService(db)
    return await service.get_annotation_stats(
        document_id=document_id,
        company_id=current_user["company_id"],
    )
